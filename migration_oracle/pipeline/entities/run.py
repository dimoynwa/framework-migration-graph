"""Run the dossier entity path: gate, cluster, one call per cluster, artifacts."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import sys
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from migration_oracle import config
from migration_oracle.models.entities import MigrationEntitiesBatch, MigrationEntity
from migration_oracle.pipeline._llm import get_llm, invoke_with_retry
from migration_oracle.pipeline._paths import (
    default_clusters_jsonl_path,
    default_clusters_summary_path,
)
from migration_oracle.pipeline._progress import progress_bar
from migration_oracle.pipeline.entities.clusters import (
    Cluster,
    cluster_kept,
    render_confirm_prompt,
    specific_key,
    verdict_of,
)
from migration_oracle.pipeline.entities.gate import InputRow, load_input_rows
from migration_oracle.pipeline.entities.model import (
    build_complete,
    load_entity_model,
    require_entity_model,
)
from migration_oracle.pipeline.entities.prompt import (
    DOSSIER_ENTITY_PROMPT_VERSION,
    render_cluster_input,
    render_prompt,
)
from migration_oracle.pipeline.entities.render import render_filtered_markdown
from migration_oracle.pipeline.entities.settings import EntitySettings, load_settings
from migration_oracle.pipeline.extractor import (
    ExtractionResult,
    _parse_json_response,
    entity_input_digest_path,
)
from migration_oracle.pipeline.filters import filter_input_digest_path
from migration_oracle.pipeline.research.schema import ResearchDossier

logger = logging.getLogger("migration_oracle.pipeline.entities")

Complete = Callable[[str], str]


@dataclass
class Outcome:
    cluster: Cluster
    status: str
    entity: MigrationEntity | None = None
    error: str = ""
    from_cache: bool = False


def run_dossier_entities(
    *,
    filter_md: str,
    dossiers: list[ResearchDossier],
    framework_key: str,
    framework_display: str,
    hop: tuple[str, str],
    filtered_path: Path,
    json_path: Path,
    force_llm: bool = False,
    stop_after_clusters: bool = False,
    complete: Complete | None = None,
    confirmer=None,
    settings: EntitySettings | None = None,
    clusters_jsonl: Path | None = None,
    clusters_summary: Path | None = None,
) -> ExtractionResult | None:
    """Gate, cluster, and extract. ``None`` when stopping after the cluster artifact.

    A cluster that fails is left out of the entities file. The hop exits non-zero
    only when every cluster failed. ``--force-llm`` ignores the per-cluster cache.
    """
    started = time.perf_counter()
    settings = settings or load_settings()
    rows = load_input_rows(filter_md, dossiers, protected=settings.protected_categories)
    if confirmer is None and settings.cluster_confirm == "llm":
        confirmer = _research_confirmer(framework_display, hop)
    clusters = cluster_kept(rows, max_rows=settings.cluster_max_rows, confirmer=confirmer)
    jsonl_path = clusters_jsonl or default_clusters_jsonl_path(
        framework_key, hop[0], hop[1]
    )
    summary_path = clusters_summary or default_clusters_summary_path(
        framework_key, hop[0], hop[1]
    )
    if stop_after_clusters:
        outcomes = [Outcome(cluster, "skipped") for cluster in clusters]
        _write_audit(
            rows,
            outcomes,
            jsonl_path=jsonl_path,
            summary_path=summary_path,
            framework=framework_display,
            hop=hop,
            elapsed=time.perf_counter() - started,
            model="",
            calls=0,
            cache_hits=0,
        )
        return None

    model_id = entity_model_label()
    outcomes, calls, cache_hits = _extract_all(
        clusters,
        framework_key=framework_key,
        framework_display=framework_display,
        hop=hop,
        model_id=model_id,
        settings=settings,
        force_llm=force_llm,
        complete=complete,
    )
    outcomes = disambiguate_titles(outcomes)
    _write_audit(
        rows,
        outcomes,
        jsonl_path=jsonl_path,
        summary_path=summary_path,
        framework=framework_display,
        hop=hop,
        elapsed=time.perf_counter() - started,
        model=model_id,
        calls=calls,
        cache_hits=cache_hits,
    )
    if clusters and all(item.status == "error" for item in outcomes):
        for path in (json_path, filtered_path, entity_input_digest_path(json_path)):
            path.unlink(missing_ok=True)
        print(
            f"Every dossier entity cluster failed for {framework_display} "
            f"{hop[0]}→{hop[1]}.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    entities = [item.entity for item in outcomes if item.entity is not None]
    batch = MigrationEntitiesBatch(entities=entities)
    items = [(item.entity, item.cluster) for item in outcomes if item.entity is not None]
    filtered = render_filtered_markdown(
        items, framework=framework_display, hop=hop
    )
    filtered_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    filtered_path.write_text(filtered, encoding="utf-8")
    # The rendered document replaces the filter LLM's. Its input sidecar would
    # let a later ``--entity-source filter`` run reuse this file as filter output.
    filter_input_digest_path(filtered_path).unlink(missing_ok=True)
    json_path.write_text(
        json.dumps(batch.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    digest_path = entity_input_digest_path(json_path)
    if outcomes and all(item.status != "error" for item in outcomes):
        keys = [
            _cache_digest(item.cluster, model_id, framework_key, hop) for item in outcomes
        ]
        digest_path.write_text(_sidecar(keys) + "\n", encoding="utf-8")
    else:
        digest_path.unlink(missing_ok=True)
    failed = sum(item.status == "error" for item in outcomes)
    print(
        f"Dossier entities {framework_display} {hop[0]}→{hop[1]}: "
        f"{len(entities)} entities, "
        f"{sum(item.status == 'empty' for item in outcomes)} empty, "
        f"{failed} errors, "
        f"{calls} calls.",
        file=sys.stderr,
    )
    return ExtractionResult(batch=batch, artifact_path=json_path, failed_clusters=failed)


def disambiguate_titles(outcomes: list[Outcome]) -> list[Outcome]:
    """Append the source URL tail when two entities in one hop share a title."""
    used: dict[str, int] = {}
    renamed: list[Outcome] = []
    for outcome in outcomes:
        entity = outcome.entity
        if entity is None:
            renamed.append(outcome)
            continue
        title = entity.title.strip() or "untitled"
        if title not in used:
            used[title] = 1
            if title != entity.title:
                entity = entity.model_copy(update={"title": title})
                outcome = Outcome(
                    outcome.cluster, outcome.status, entity, outcome.error, outcome.from_cache
                )
            renamed.append(outcome)
            continue
        tail = _url_tail(cluster_source_url(outcome.cluster)) or "2"
        candidate = f"{title} ({tail})"
        suffix = 2
        while candidate in used:
            suffix += 1
            candidate = f"{title} ({tail} {suffix})"
        used[title] = used.get(title, 1) + 1
        used[candidate] = 1
        message = f"renamed duplicate entity title {title!r} to {candidate!r}"
        logger.info(message)
        print(message, file=sys.stderr)
        renamed.append(
            Outcome(
                outcome.cluster,
                outcome.status,
                entity.model_copy(update={"title": candidate}),
                outcome.error,
                outcome.from_cache,
            )
        )
    return renamed


def cluster_source_url(cluster: Cluster) -> str:
    """First specific row source, otherwise the first row source."""
    for member in cluster.members:
        for source in member.row.sources:
            if specific_key(source):
                return source
    for member in cluster.members:
        if member.row.sources:
            return member.row.sources[0]
        if member.source.startswith("http"):
            return member.source
    return ""


def cluster_jira_keys(cluster: Cluster) -> list[str]:
    keys: list[str] = []
    for member in cluster.members:
        for key in member.row.jira_keys:
            if key not in keys:
                keys.append(key)
    return keys


def _extract_all(
    clusters: list[Cluster],
    *,
    framework_key: str,
    framework_display: str,
    hop: tuple[str, str],
    model_id: str,
    settings: EntitySettings,
    force_llm: bool,
    complete: Complete | None,
) -> tuple[list[Outcome], int, int]:
    if not clusters:
        return [], 0, 0
    pending = [
        _load_cached(cluster, model_id, framework_key, hop, settings)
        if not force_llm
        else None
        for cluster in clusters
    ]
    misses = [index for index, item in enumerate(pending) if item is None]
    caller = complete
    if misses and caller is None:
        _require_model()
        entity_model = load_entity_model()
        caller = build_complete(entity_model) if entity_model else _default_complete
    calls = 0
    if misses:
        fresh, calls = asyncio.run(
            _extract_missing(
                [clusters[index] for index in misses],
                framework_key=framework_key,
                framework_display=framework_display,
                hop=hop,
                model_id=model_id,
                settings=settings,
                complete=caller or _default_complete,
            )
        )
        for index, outcome in zip(misses, fresh):
            pending[index] = outcome
    outcomes = [item if item is not None else Outcome(clusters[i], "error") for i, item in enumerate(pending)]
    cache_hits = sum(item.from_cache for item in outcomes)
    return outcomes, calls, cache_hits


async def _extract_missing(
    clusters: list[Cluster],
    *,
    framework_key: str,
    framework_display: str,
    hop: tuple[str, str],
    model_id: str,
    settings: EntitySettings,
    complete: Complete,
) -> tuple[list[Outcome], int]:
    semaphore = asyncio.Semaphore(settings.concurrency)
    bar = progress_bar(
        len(clusters),
        f"Entities {framework_display} {hop[0]}→{hop[1]}",
        unit="cluster",
    )
    call_count = 0

    async def worker(cluster: Cluster) -> Outcome:
        nonlocal call_count
        async with semaphore:
            outcome, used = await asyncio.to_thread(
                _extract_cluster,
                cluster,
                framework_display,
                hop,
                complete,
            )
            call_count += used
            if outcome.status != "error":
                _write_cache(cluster, outcome, model_id, framework_key, hop, settings)
            bar.update(1)
            return outcome

    try:
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(worker(cluster)) for cluster in clusters]
    finally:
        bar.close()
    return [task.result() for task in tasks], call_count


def _extract_cluster(
    cluster: Cluster,
    framework: str,
    hop: tuple[str, str],
    complete: Complete,
) -> tuple[Outcome, int]:
    prompt = render_prompt(framework, render_cluster_input(cluster, framework, hop))
    last_error = "entity call failed"
    for _attempt in range(2):
        try:
            batch = _parse_json_response(complete(prompt))
        except Exception as exc:
            last_error = str(exc)
            continue
        if len(batch.entities) > 1:
            last_error = f"{len(batch.entities)} entities returned; at most one is valid"
            continue
        if not batch.entities:
            return Outcome(cluster, "empty"), _attempt + 1
        entity = batch.entities[0].model_copy(
            update={
                "source_url": cluster_source_url(cluster),
                "jira_keys": cluster_jira_keys(cluster),
            }
        )
        return Outcome(cluster, "ok", entity), _attempt + 1
    message = f"entity cluster {cluster.cluster_key[:12]} failed: {last_error}"
    # Printed for the operator; logged at INFO so the root handler does not repeat it.
    logger.info(message)
    print(message, file=sys.stderr)
    return Outcome(cluster, "error", error=last_error), 2


def _default_complete(prompt: str) -> str:
    return invoke_with_retry(get_llm(), prompt)


def entity_model_label() -> str:
    """The model named in the cache key and the summary.

    ``ENTITY_MODEL_ID`` when set (with provider, output mode and reasoning, so a
    change of any of them re-runs the clusters), otherwise ``MODEL_ID``.
    """
    entity_model = load_entity_model()
    return entity_model.cache_label if entity_model else config.MODEL_ID


def _require_model() -> None:
    entity_model = load_entity_model()
    if entity_model is not None:
        try:
            require_entity_model(entity_model)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            raise SystemExit(1) from exc
        return
    if not config.MODEL_PROVIDER.strip() or not config.MODEL_ID.strip():
        print(
            "Set ENTITY_MODEL_ID (with ENTITY_MODEL_PROVIDER), or MODEL_PROVIDER and "
            "MODEL_ID, for dossier entity calls.",
            file=sys.stderr,
        )
        raise SystemExit(1)


def _research_confirmer(framework: str, hop: tuple[str, str]):
    def confirm(cluster: Cluster) -> str:
        from migration_oracle.pipeline.research.run import build_model
        from migration_oracle.pipeline.research.settings import load_settings as load_research

        research = load_research()
        if not research.enabled:
            logger.warning("CLUSTER_CONFIRM=llm but research is disabled; keeping the cluster")
            return "same"
        model = build_model(research)
        prompt = render_confirm_prompt(cluster)
        turn = asyncio.run(
            model.complete(
                [{"role": "user", "content": prompt}],
                tools=None,
                response_format=None,
            )
        )
        verdict = verdict_of(turn.content)
        logger.info(
            "cluster confirm %s → %s (%s %s→%s)",
            cluster.cluster_key[:12],
            verdict,
            framework,
            hop[0],
            hop[1],
        )
        return verdict

    return confirm


def _cache_digest(cluster: Cluster, model_id: str, framework_key: str, hop: tuple[str, str]) -> str:
    parts = [
        str(DOSSIER_ENTITY_PROMPT_VERSION),
        model_id,
        framework_key,
        hop[0],
        hop[1],
        cluster.cluster_key,
        *(_member_material(member) for member in cluster.members),
    ]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _member_material(member: InputRow) -> str:
    """Everything ``render_cluster_input`` sends for one member.

    A re-triage can change the category or statement while ``row_key`` stays the
    same, so those are part of the key, not only the dossier text.
    """
    dossier = member.dossier
    return "\x1f".join(
        [
            member.category,
            member.impact_score,
            member.row_type,
            member.source,
            member.statement,
            member.evidence,
            dossier.status if dossier is not None else "",
            dossier.text if dossier is not None else "",
            "\x1e".join(dossier.sources) if dossier is not None else "",
        ]
    )


def _cache_path(
    cluster: Cluster,
    model_id: str,
    framework_key: str,
    hop: tuple[str, str],
    settings: EntitySettings,
) -> Path:
    digest = _cache_digest(cluster, model_id, framework_key, hop)
    return settings.cache_dir / "entities" / digest


def _load_cached(
    cluster: Cluster,
    model_id: str,
    framework_key: str,
    hop: tuple[str, str],
    settings: EntitySettings,
) -> Outcome | None:
    path = _cache_path(cluster, model_id, framework_key, hop, settings)
    if not path.exists():
        return None
    try:
        batch = MigrationEntitiesBatch.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not batch.entities:
        return Outcome(cluster, "empty", from_cache=True)
    return Outcome(cluster, "ok", batch.entities[0], from_cache=True)


def _write_cache(
    cluster: Cluster,
    outcome: Outcome,
    model_id: str,
    framework_key: str,
    hop: tuple[str, str],
    settings: EntitySettings,
) -> None:
    batch = MigrationEntitiesBatch(entities=[outcome.entity] if outcome.entity else [])
    path = _cache_path(cluster, model_id, framework_key, hop, settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(batch.model_dump_json(), encoding="utf-8")


def _sidecar(cache_keys: list[str]) -> str:
    return hashlib.sha256("\n".join(cache_keys).encode("utf-8")).hexdigest()


def _url_tail(url: str) -> str:
    if not url:
        return ""
    parsed = urlsplit(url)
    path = parsed.path.rstrip("/")
    tail = path.rsplit("/", 1)[-1] if path else ""
    return tail or parsed.fragment


def _write_audit(
    rows: list[InputRow],
    outcomes: list[Outcome],
    *,
    jsonl_path: Path,
    summary_path: Path,
    framework: str,
    hop: tuple[str, str],
    elapsed: float,
    model: str,
    calls: int,
    cache_hits: int,
) -> None:
    lines: list[str] = []
    for row in rows:
        cluster_key = None
        if row.decision == "keep":
            for outcome in outcomes:
                if any(member.position == row.position for member in outcome.cluster.members):
                    cluster_key = outcome.cluster.cluster_key
                    break
        lines.append(
            json.dumps(
                {
                    "type": "row",
                    "row_key": row.row.row_key,
                    "decision": row.decision,
                    "reason": row.reason,
                    "cluster_key": cluster_key,
                    "evidence": row.evidence,
                },
                ensure_ascii=False,
            )
        )
    for outcome in outcomes:
        lines.append(
            json.dumps(
                {
                    "type": "cluster",
                    "cluster_key": outcome.cluster.cluster_key,
                    "members": [member.row.row_key for member in outcome.cluster.members],
                    "title": outcome.entity.title if outcome.entity else None,
                    "status": outcome.status,
                    **({"error": outcome.error} if outcome.error else {}),
                },
                ensure_ascii=False,
            )
        )
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    jsonl_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    reasons = Counter(row.reason for row in rows)
    sizes = Counter(str(len(outcome.cluster.members)) for outcome in outcomes)
    summary = {
        "framework": framework,
        "from_version": hop[0],
        "to_version": hop[1],
        "gate_reasons": dict(reasons),
        "cluster_sizes": dict(sorted(sizes.items(), key=lambda item: int(item[0]))),
        "entities_written": sum(outcome.entity is not None for outcome in outcomes),
        "empty_results": sum(outcome.status == "empty" for outcome in outcomes),
        "errors": sum(outcome.status == "error" for outcome in outcomes),
        "row_only_clusters": sum(
            any(member.evidence == "row_only" for member in outcome.cluster.members)
            for outcome in outcomes
        ),
        "wall_time_sec": round(elapsed, 3),
        "model": model,
        "entity_calls": calls,
        "cache_hits": cache_hits,
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
