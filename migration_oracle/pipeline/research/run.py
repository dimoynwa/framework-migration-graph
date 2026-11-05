"""Run per-row research and write ``runs/research`` artifacts."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import sys
import time
from collections import Counter
from pathlib import Path

from migration_oracle.pipeline._progress import progress_bar
from migration_oracle.pipeline._paths import (
    default_research_jsonl_path,
    default_research_summary_path,
)
from migration_oracle.pipeline.research.agent import ChatCompletionsModel, research_row
from migration_oracle.pipeline.research.markdown import FilteredRow
from migration_oracle.pipeline.research.schema import PROMPT_VERSION, ResearchDossier, action_of
from migration_oracle.pipeline.research.settings import ResearchSettings, load_settings
from migration_oracle.pipeline.research.tools import (
    PageFetcher,
    ResearchQuotaExceeded,
    SearchClient,
    SearchTool,
    TavilyQuotaError,
    TavilySearchClient,
    github_token,
    ssl_verify,
)

logger = logging.getLogger("migration_oracle.pipeline.research")

_notices: set[str] = set()


def reset_notices() -> None:
    """Test hook. Disabled and skip notices are once per process."""
    _notices.clear()


def _notify_once(key: str, message: str) -> None:
    if key in _notices:
        return
    _notices.add(key)
    logger.info(message)
    print(message)


def build_model(settings: ResearchSettings) -> ChatCompletionsModel:
    return ChatCompletionsModel(settings)


def build_search(settings: ResearchSettings) -> TavilySearchClient:
    return TavilySearchClient(settings.tavily_api_key, timeout_sec=settings.timeout_sec)


def build_fetcher(settings: ResearchSettings, *, force: bool) -> PageFetcher:
    return PageFetcher(
        cache_dir=settings.cache_dir,
        max_chars=settings.fetch_max_chars,
        token=github_token(),
        verify=ssl_verify(),
        force=force,
    )


def run_research(
    rows: list[FilteredRow],
    framework: str,
    hop: tuple[str, str],
    *,
    framework_key: str | None = None,
    settings: ResearchSettings | None = None,
    model: ChatCompletionsModel | None = None,
    search: SearchClient | None = None,
    fetcher: PageFetcher | None = None,
    skip: bool = False,
    force: bool = False,
) -> list[ResearchDossier]:
    """Research each filtered row. Disabled or skipped runs return ``[]`` and write nothing."""
    settings = settings or load_settings()
    if skip:
        _notify_once(
            "skip",
            "Research skipped (--skip-research); the entity step uses the filtered Markdown only.",
        )
        return []
    if not settings.enabled:
        _notify_once(
            "disabled",
            "Research disabled (set RESEARCH_BASE_URL and RESEARCH_MODEL_ID to enable); "
            "the entity step uses the filtered Markdown only.",
        )
        return []
    if search is None and not settings.search_enabled:
        _notify_once(
            "no-search",
            "Research without web search (TAVILY_API_KEY is empty): the model reads the "
            "row Sources and linked pages with fetch_url only.",
        )
    key = framework_key or framework.strip().lower().replace(" ", "-")
    try:
        dossiers, tool_calls, cache_hits, elapsed = asyncio.run(
            _research_all(
                rows,
                framework=framework,
                framework_key=key,
                hop=hop,
                settings=settings,
                model=model,
                search=search,
                fetcher=fetcher,
                force=force,
            )
        )
    except ResearchQuotaExceeded:
        raise
    _write_artifacts(
        dossiers,
        framework=framework,
        framework_key=key,
        hop=hop,
        model=settings.model_id,
        tool_calls=tool_calls,
        cache_hits=cache_hits,
        elapsed=elapsed,
    )
    return dossiers


async def _research_all(
    rows: list[FilteredRow],
    *,
    framework: str,
    framework_key: str,
    hop: tuple[str, str],
    settings: ResearchSettings,
    model: ChatCompletionsModel | None,
    search: SearchClient | None,
    fetcher: PageFetcher | None,
    force: bool,
) -> tuple[list[ResearchDossier], int, int, float]:
    started = time.perf_counter()
    results: list[ResearchDossier | None] = [None] * len(rows)
    call_counts = [0] * len(rows)
    cache_hits = 0
    resolved_model = model
    resolved_search = search
    # No injected client and no Tavily key: fetch_url only, no web_search tool.
    search_on = search is not None or settings.search_enabled
    resolved_fetcher = fetcher or build_fetcher(settings, force=force)
    semaphore = asyncio.Semaphore(settings.max_concurrent)
    bar = progress_bar(len(rows), f"Research {framework} {hop[0]}→{hop[1]}")
    counts = {"ok": 0, "not_found": 0, "error": 0, "cached": 0}

    def tick(dossier: ResearchDossier, *, cached: bool = False) -> None:
        counts[dossier.status] = counts.get(dossier.status, 0) + 1
        if cached:
            counts["cached"] += 1
        bar.update(1)
        bar.set_postfix(counts, refresh=False)

    async def worker(index: int, row: FilteredRow) -> None:
        nonlocal cache_hits, resolved_model, resolved_search
        cached = None if force else _read_cache(settings, row, framework_key, hop)
        if cached is not None:
            results[index] = cached
            cache_hits += 1
            tick(cached, cached=True)
            return
        async with semaphore:
            if resolved_model is None:
                resolved_model = build_model(settings)
            search_tool: SearchTool | None = None
            if search_on:
                if resolved_search is None:
                    resolved_search = build_search(settings)
                search_tool = SearchTool(
                    resolved_search,
                    cache_dir=settings.cache_dir,
                    framework=framework,
                    to_version=hop[1],
                    max_results=settings.search_results,
                    force=force,
                )
            try:
                dossier, calls = await asyncio.wait_for(
                    research_row(
                        row,
                        framework=framework,
                        hop=hop,
                        settings=settings,
                        model=resolved_model,
                        search=search_tool,
                        fetcher=resolved_fetcher,
                    ),
                    settings.timeout_sec,
                )
            except TimeoutError:
                dossier, calls = _timeout_dossier(row, settings), 0
            if dossier.status == "error":
                logger.warning(
                    "research error for row %s (%s): %s",
                    row.row_key[:12],
                    row.title,
                    dossier.error,
                )
            if dossier.status != "error":
                # Errors are often transient (model or Tavily outage, timeout).
                # Caching them would hide the row from every later run.
                _write_cache(settings, dossier, framework_key, hop)
            results[index] = dossier
            call_counts[index] = calls
            tick(dossier)

    try:
        async with asyncio.TaskGroup() as group:
            for index, row in enumerate(rows):
                group.create_task(worker(index, row))
    except* TavilyQuotaError:
        done = sum(item is not None for item in results)
        raise ResearchQuotaExceeded(framework, hop, done, len(rows)) from None
    finally:
        bar.close()
    elapsed = time.perf_counter() - started
    dossiers = [
        item
        if item is not None
        else _timeout_dossier(row, settings, "row did not finish (research run aborted)")
        for item, row in zip(results, rows)
    ]
    return dossiers, sum(call_counts), cache_hits, elapsed


def _timeout_dossier(
    row: FilteredRow, settings: ResearchSettings, reason: str | None = None
) -> ResearchDossier:
    from migration_oracle.pipeline.research.schema import error_dossier

    return error_dossier(
        row.row_key,
        settings.model_id,
        reason or f"timeout: row research exceeded {settings.timeout_sec}s",
    )


def row_cache_path(
    settings: ResearchSettings,
    row_key: str,
    framework_key: str,
    hop: tuple[str, str],
) -> Path:
    """Cache file for one row of one hop.

    The framework and hop are part of the key: dossiers are anchored to the hop
    target version, and rows without Sources or JIRA keys share a ``row_key``.
    ``enable_thinking`` is part of the key too, so the two modes never share rows.
    Fetch-only rows (no ``TAVILY_API_KEY``) get their own key; Tavily-mode keys are
    unchanged, so earlier caches stay valid.
    """
    material = (
        f"{PROMPT_VERSION}\n{settings.model_id}\n{framework_key}\n"
        f"{hop[0]}\n{hop[1]}\n{row_key}\nthinking={settings.enable_thinking}"
    )
    if not settings.search_enabled:
        material += "\nsearch=off"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return settings.cache_dir / "research" / digest


def _read_cache(
    settings: ResearchSettings,
    row: FilteredRow,
    framework_key: str,
    hop: tuple[str, str],
) -> ResearchDossier | None:
    path = row_cache_path(settings, row.row_key, framework_key, hop)
    if not path.exists():
        return None
    try:
        dossier = ResearchDossier.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return None if dossier.status == "error" else dossier


def _write_cache(
    settings: ResearchSettings,
    dossier: ResearchDossier,
    framework_key: str,
    hop: tuple[str, str],
) -> None:
    path = row_cache_path(settings, dossier.row_key, framework_key, hop)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dossier.model_dump_json(), encoding="utf-8")


def _write_artifacts(
    dossiers: list[ResearchDossier],
    *,
    framework: str,
    framework_key: str,
    hop: tuple[str, str],
    model: str,
    tool_calls: int,
    cache_hits: int,
    elapsed: float,
) -> None:
    jsonl_path = default_research_jsonl_path(framework_key, hop[0], hop[1])
    summary_path = default_research_summary_path(framework_key, hop[0], hop[1])
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [dossier.model_dump_json() for dossier in dossiers]
    jsonl_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    status_counts = Counter(dossier.status for dossier in dossiers)
    action_counts = Counter(
        action_of(dossier.text) for dossier in dossiers if dossier.status == "ok"
    )
    error_counts = Counter(
        _error_category(dossier.error) for dossier in dossiers if dossier.status == "error"
    )
    summary = {
        "framework": framework,
        "from_version": hop[0],
        "to_version": hop[1],
        "rows": len(dossiers),
        "status": {
            "ok": status_counts.get("ok", 0),
            "not_found": status_counts.get("not_found", 0),
            "error": status_counts.get("error", 0),
        },
        # From the ``**Action:**`` line of ok descriptions; "missing" = format not followed.
        "action": {
            key: action_counts.get(key, 0) for key in ("required", "none", "unclear", "missing")
        },
        "errors": dict(error_counts.most_common()),
        "tool_calls": tool_calls,
        "cache_hits": cache_hits,
        "wall_time_sec": round(elapsed, 3),
        "model": model,
        "prompt_version": PROMPT_VERSION,
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def _error_category(error: str) -> str:
    """Group error strings for the summary: drop the variable tail after the type."""
    if not error:
        return "unknown"
    if error.startswith("timeout"):
        return "timeout"
    stage, _, detail = error.partition(": ")
    stage = stage.split(" (")[0]
    if stage.startswith("tools "):
        stage = "tools"
    kind = detail.split(":")[0] if detail else ""
    return f"{stage}: {kind}" if kind else stage


def report_quota(exc: ResearchQuotaExceeded) -> None:
    """Print the single quota line. The CLI exits 2 after this."""
    print(exc.message, file=sys.stderr)
