"""Run System-1 triage over extracted changes and persist its artifacts."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path

from migration_oracle.models.entities import DocumentedChange
from migration_oracle.pipeline._progress import progress_bar
from migration_oracle.pipeline._paths import (
    default_triage_jsonl_path,
    default_triage_summary_path,
)
from migration_oracle.pipeline.triage.client import (
    System1HttpClient,
    TriageClient,
    TriageRejected,
    TriageTransportError,
    TriageUnavailable,
    emit,
    reset_client_notices,
)
from migration_oracle.pipeline.triage.markdown import (
    build_filter_markdown,
    has_triage_columns,
    parse_raw_markdown,
    render_raw_markdown,
)
from migration_oracle.pipeline.triage.questions import triage_questions
from migration_oracle.pipeline.triage import questions as questions_module
from migration_oracle.pipeline.triage.rules import pre_triage, should_drop
from migration_oracle.pipeline.triage.settings import TriageSettings, load_settings

_notices: set[str] = set()


def reset_notices() -> None:
    """Test hook. The disabled/skip notices are once per process."""
    _notices.clear()
    reset_client_notices()


def notify_once(key: str, level: int, message: str) -> None:
    if key in _notices:
        return
    _notices.add(key)
    emit(level, message)


@dataclass
class TriagedRow:
    hop_from: str
    hop_to: str
    change: DocumentedChange
    decision: str
    source: str
    answers: dict | None
    state: str
    input_tokens: int = 0
    from_cache: bool = False


@dataclass
class TriageResult:
    kept: list[TriagedRow]
    dropped: list[TriagedRow]
    rows: list[TriagedRow]
    applied: bool
    input_tokens: int
    wall_time_sec: float
    model: str
    questions_version: int
    cache_hits: int = 0


@dataclass
class PreparedRange:
    raw_md: str
    filter_md: str
    rewrite_raw: bool


def default_client(settings: TriageSettings) -> System1HttpClient:
    return System1HttpClient(settings)


def run_triage(
    changes: list[DocumentedChange],
    framework: str,
    hop: tuple[str, str],
    *,
    client: TriageClient | None = None,
    settings: TriageSettings | None = None,
    force: bool = False,
) -> TriageResult:
    """Classify one hop. ``framework`` is the display name used in the state text."""
    return asyncio.run(
        run_triage_async(
            [(hop[0], hop[1], changes)],
            framework,
            client=client,
            settings=settings,
            force=force,
        )
    )


async def run_triage_async(
    hop_changes: list[tuple[str, str, list[DocumentedChange]]],
    framework: str,
    *,
    client: TriageClient | None = None,
    settings: TriageSettings | None = None,
    force: bool = False,
) -> TriageResult:
    settings = settings or load_settings()
    started = time.perf_counter()
    version = questions_module.TRIAGE_QUESTIONS_VERSION
    if not settings.enabled:
        rows = [
            _plain_row(hop_from, hop_to, change)
            for hop_from, hop_to, changes in hop_changes
            for change in changes
        ]
        return _result(rows, applied=False, started=started, settings=settings, version=version)

    questions = triage_questions()
    pending = [
        _Work(hop_from, hop_to, change, render_state(
            change,
            framework=framework,
            hop=(hop_from, hop_to),
            max_chars=settings.state_max_chars,
        ))
        for hop_from, hop_to, changes in hop_changes
        for change in changes
    ]
    owns_client = client is None
    if client is None:
        client = default_client(settings)
    if hop_changes:
        span = f"{hop_changes[0][0]}→{hop_changes[-1][1]}"
    else:
        span = ""
    try:
        rows, cache_hits = await _classify_pending(
            pending,
            client=client,
            settings=settings,
            questions=questions,
            version=version,
            force=force,
            desc=f"Triage {framework} {span}".strip(),
        )
    finally:
        if owns_client:
            await client.aclose()
    return _result(
        rows,
        applied=True,
        started=started,
        settings=settings,
        version=version,
        cache_hits=cache_hits,
    )


def prepare_range_documents(
    *,
    framework_key: str,
    framework_display: str,
    from_version: str,
    to_version: str,
    hop_changes: list[tuple[str, str, list[DocumentedChange]]] | None,
    existing_raw: str | None,
    range_metadata: dict | None,
    skip_triage: bool,
    force_triage: bool,
    retriage_from_cache: bool,
    client: TriageClient | None = None,
    settings: TriageSettings | None = None,
) -> PreparedRange:
    """Return the raw Markdown to store and the Markdown the filter LLM should see."""
    settings = settings or load_settings()
    if skip_triage and (force_triage or retriage_from_cache):
        raise ValueError(
            "--skip-triage cannot be combined with --force-triage or --retriage-from-cache"
        )

    if skip_triage or not settings.enabled:
        if skip_triage:
            notify_once(
                "skip",
                logging.INFO,
                "Triage skipped (--skip-triage); keeping every row.",
            )
        else:
            notify_once(
                "disabled",
                logging.INFO,
                "Triage disabled (TRIAGE_BASE_URL or TRIAGE_MODEL unset); keeping every row.",
            )
        raw_md = _plain_raw(
            framework_key=framework_key,
            framework_display=framework_display,
            from_version=from_version,
            to_version=to_version,
            hop_changes=hop_changes,
            existing_raw=existing_raw,
            range_metadata=range_metadata,
        )
        filter_md = raw_md if not has_triage_columns(raw_md) else _all_rows_plain(raw_md)
        return PreparedRange(
            raw_md=raw_md,
            filter_md=filter_md,
            rewrite_raw=hop_changes is not None,
        )

    if retriage_from_cache:
        if not existing_raw:
            raise ValueError("--retriage-from-cache requires an existing raw Markdown file")
        raw_md = _retriage(
            existing_raw,
            framework_key=framework_key,
            framework_display=framework_display,
            from_version=from_version,
            to_version=to_version,
            settings=settings,
        )
        return PreparedRange(
            raw_md=raw_md,
            filter_md=build_filter_markdown(raw_md),
            rewrite_raw=True,
        )

    if hop_changes is not None:
        result = run_triage_hops(
            hop_changes,
            framework_display,
            client=client,
            settings=settings,
            force=force_triage,
        )
    else:
        if not existing_raw:
            raise ValueError("triage has no extracted changes and no raw Markdown file")
        if has_triage_columns(existing_raw) and not force_triage:
            emit(
                logging.INFO,
                f"Triage: reusing decisions already stored in the raw file "
                f"for {framework_display} {from_version} → {to_version}.",
            )
            return PreparedRange(
                raw_md=existing_raw,
                filter_md=build_filter_markdown(existing_raw),
                rewrite_raw=False,
            )
        notify_once(
            "statement-only",
            logging.WARNING,
            "Triage is classifying from statements only because extraction "
            "metadata is not in the raw file. Pass --force-extract for best signal.",
        )
        parsed = parse_raw_markdown(existing_raw)
        statement_hops = _hops_without_triage(parsed.hops)
        result = run_triage_hops(
            statement_hops,
            framework_display or parsed.framework_display,
            client=client,
            settings=settings,
            force=force_triage,
        )
        raw_md = render_raw_markdown(
            framework_key=parsed.framework_key or framework_key,
            framework_display=parsed.framework_display or framework_display,
            from_version=parsed.from_version or from_version,
            to_version=parsed.to_version or to_version,
            hop_changes=_group(result),
            extra_lines=parsed.extra_lines or None,
        )
        _write_artifacts(
            framework_key, from_version, to_version, result, settings
        )
        _log_summary(framework_display, from_version, to_version, result)
        return PreparedRange(
            raw_md=raw_md,
            filter_md=build_filter_markdown(raw_md),
            rewrite_raw=True,
        )

    raw_md = render_raw_markdown(
        framework_key=framework_key,
        framework_display=framework_display,
        from_version=from_version,
        to_version=to_version,
        hop_changes=_group(result),
        metadata=range_metadata,
    )
    _write_artifacts(framework_key, from_version, to_version, result, settings)
    _log_summary(framework_display, from_version, to_version, result)
    return PreparedRange(
        raw_md=raw_md,
        filter_md=build_filter_markdown(raw_md) if result.applied else raw_md,
        rewrite_raw=True,
    )


def run_triage_hops(
    hop_changes: list[tuple[str, str, list[DocumentedChange]]],
    framework: str,
    *,
    client: TriageClient | None = None,
    settings: TriageSettings | None = None,
    force: bool = False,
) -> TriageResult:
    return asyncio.run(
        run_triage_async(
            hop_changes,
            framework,
            client=client,
            settings=settings,
            force=force,
        )
    )


def render_state(
    change: DocumentedChange,
    *,
    framework: str,
    hop: tuple[str, str],
    max_chars: int,
) -> str:
    """Labelled state string. The ``Release:`` line is omitted; the result is capped."""
    meta = change.metadata or {}
    lines = [f"Framework: {framework}", f"Hop: {hop[0]} → {hop[1]}"]
    if change.type and change.confidence:
        lines.append(f"Raw type: {change.type} ({change.confidence})")
    elif change.type:
        lines.append(f"Raw type: {change.type}")
    package = meta.get("angular_package")
    if package:
        lines.append(f"Package: {package}")
    commit_type = meta.get("angular_commit_type")
    if commit_type:
        lines.append(f"Commit type: {commit_type}")
    labels = meta.get("github_labels")
    if isinstance(labels, list) and labels:
        label_text = ", ".join(str(label) for label in labels)
        if len(label_text) > 400:
            label_text = label_text[:399] + "…"
        lines.append(f"Labels: {label_text}")
    if "has_schematic" in meta:
        lines.append(
            "Has ng-update schematic: "
            + ("yes" if meta.get("has_schematic") else "no")
        )
    files = meta.get("github_files")
    if isinstance(files, list) and files:
        files_text = ", ".join(str(path) for path in files if path)
        if len(files_text) > 800:
            files_text = files_text[:799] + "…"
        if files_text:
            lines.append(f"Files: {files_text}")
    lines.append("Change:")
    for line in (change.statement or "").splitlines():
        if line.startswith("Release:"):
            continue
        lines.append(line)
    text = "\n".join(lines)
    if len(text) > max_chars:
        return text[:max_chars]
    return text


@dataclass
class _Work:
    hop_from: str
    hop_to: str
    change: DocumentedChange
    state: str


async def _classify_pending(
    pending: list[_Work],
    *,
    client: TriageClient,
    settings: TriageSettings,
    questions: dict,
    version: int,
    force: bool,
    desc: str = "Triage",
) -> tuple[list[TriagedRow], int]:
    resolved: list[TriagedRow | None] = [None] * len(pending)
    model_indexes: list[int] = []
    for index, work in enumerate(pending):
        ruled = pre_triage(work.change)
        if ruled is None:
            model_indexes.append(index)
            continue
        resolved[index] = _finish(
            work,
            decision=ruled,
            source="rule",
            answers=None,
            model=settings.model,
            version=version,
        )

    if not model_indexes:
        return [row for row in resolved if row is not None], 0

    # Rule-decided rows are already done; the bar tracks the classifier calls.
    bar = progress_bar(len(pending), desc, initial=len(pending) - len(model_indexes))
    counts = {"keep": 0, "drop": 0, "error": 0}
    for row in resolved:
        if row is not None:
            counts[row.decision] = counts.get(row.decision, 0) + 1

    def tick(row: TriagedRow) -> None:
        key = "error" if row.source == "error" else row.decision
        counts[key] = counts.get(key, 0) + 1
        bar.update(1)
        bar.set_postfix(counts, refresh=False)

    try:
        return await _classify_with_bar(
            pending,
            resolved,
            model_indexes,
            client=client,
            settings=settings,
            questions=questions,
            version=version,
            force=force,
            tick=tick,
        )
    finally:
        bar.close()


async def _classify_with_bar(
    pending: list[_Work],
    resolved: list[TriagedRow | None],
    model_indexes: list[int],
    *,
    client: TriageClient,
    settings: TriageSettings,
    questions: dict,
    version: int,
    force: bool,
    tick,
) -> tuple[list[TriagedRow], int]:
    async def resolve_at(index: int) -> TriagedRow:
        work = pending[index]
        try:
            decision, answers, tokens, from_cache = await _resolve_model(
                work.state,
                client=client,
                settings=settings,
                questions=questions,
                version=version,
                force=force,
            )
        except TriageTransportError:
            return _finish(
                work,
                decision="keep",
                source="error",
                answers=None,
                model=settings.model,
                version=version,
            )
        return _finish(
            work,
            decision=decision,
            source="model",
            answers=answers,
            model=settings.model,
            version=version,
            input_tokens=tokens,
            from_cache=from_cache,
        )

    try:
        resolved[model_indexes[0]] = await resolve_at(model_indexes[0])
    except (TriageUnavailable, TriageRejected):
        return _all_errors(pending, settings.model, version), 0
    tick(resolved[model_indexes[0]])

    semaphore = asyncio.Semaphore(settings.max_concurrent)

    async def limited(index: int) -> tuple[int, TriagedRow | Exception]:
        async with semaphore:
            try:
                row = await resolve_at(index)
                tick(row)
                return index, row
            except TriageRejected as exc:
                return index, exc
            except TriageUnavailable as exc:
                return index, exc

    if len(model_indexes) > 1:
        outcomes = await asyncio.gather(
            *(limited(index) for index in model_indexes[1:])
        )
        if any(
            isinstance(outcome, (TriageRejected, TriageUnavailable))
            for _index, outcome in outcomes
        ):
            return _all_errors(pending, settings.model, version), 0
        for index, outcome in outcomes:
            resolved[index] = outcome

    rows = [row for row in resolved if row is not None]
    return rows, sum(1 for row in rows if row.from_cache)


async def _resolve_model(
    state: str,
    *,
    client: TriageClient,
    settings: TriageSettings,
    questions: dict,
    version: int,
    force: bool,
) -> tuple[str, dict, int, bool]:
    key = _cache_key(version, settings.model, state)
    if not force:
        cached = _cache_get(settings, key)
        if cached is not None:
            answers = cached["answers"]
            decision = "drop" if should_drop(answers, settings) else "keep"
            return decision, answers, 0, True
    request = getattr(client, "classify_request", None)
    if request is not None:
        answers, usage = await request(state, questions)
    else:
        answers = await client.classify(state, questions)
        usage = {}
    if not isinstance(answers, dict):
        raise TriageTransportError("classifier returned no answers object")
    tokens = 0
    if isinstance(usage, dict):
        try:
            tokens = int(usage.get("input_tokens") or 0)
        except (TypeError, ValueError):
            tokens = 0
    _cache_put(settings, key, answers, {"input_tokens": tokens}, version)
    decision = "drop" if should_drop(answers, settings) else "keep"
    return decision, answers, tokens, False


def _finish(
    work: _Work,
    *,
    decision: str,
    source: str,
    answers: dict | None,
    model: str,
    version: int,
    input_tokens: int = 0,
    from_cache: bool = False,
) -> TriagedRow:
    change = _annotate(
        work.change,
        decision=decision,
        source=source,
        answers=answers,
        model=model,
        version=version,
    )
    return TriagedRow(
        hop_from=work.hop_from,
        hop_to=work.hop_to,
        change=change,
        decision=decision,
        source=source,
        answers=answers,
        state=work.state,
        input_tokens=input_tokens,
        from_cache=from_cache,
    )


def _annotate(
    change: DocumentedChange,
    *,
    decision: str,
    source: str,
    answers: dict | None,
    model: str,
    version: int,
) -> DocumentedChange:
    category = (answers or {}).get("category") if answers else None
    action = (answers or {}).get("requires_action") if answers else None
    impact = (answers or {}).get("impact") if answers else None
    choice = category.get("choice") if isinstance(category, dict) else None
    probabilities = category.get("probabilities") if isinstance(category, dict) else None
    category_prob = None
    if isinstance(probabilities, dict) and isinstance(choice, str):
        category_prob = probabilities.get(choice)
    meta = dict(change.metadata or {})
    meta.update(
        {
            "triage_decision": decision,
            "triage_source": source,
            "triage_category": choice,
            "triage_category_prob": category_prob,
            "triage_category_confidence": (
                category.get("confidence") if isinstance(category, dict) else None
            ),
            "triage_action_prob": action.get("noul") if isinstance(action, dict) else None,
            "triage_impact_score": impact.get("score") if isinstance(impact, dict) else None,
            "triage_questions_version": version,
            "triage_model": model,
        }
    )
    return replace(change, metadata=meta)


def _all_errors(pending: list[_Work], model: str, version: int) -> list[TriagedRow]:
    return [
        _finish(
            work,
            decision="keep",
            source="error",
            answers=None,
            model=model,
            version=version,
        )
        for work in pending
    ]


def _plain_row(hop_from: str, hop_to: str, change: DocumentedChange) -> TriagedRow:
    return TriagedRow(
        hop_from=hop_from,
        hop_to=hop_to,
        change=change,
        decision="keep",
        source="",
        answers=None,
        state="",
    )


def _result(
    rows: list[TriagedRow],
    *,
    applied: bool,
    started: float,
    settings: TriageSettings,
    version: int,
    cache_hits: int = 0,
) -> TriageResult:
    kept = [row for row in rows if row.decision != "drop"]
    dropped = [row for row in rows if row.decision == "drop"]
    return TriageResult(
        kept=kept,
        dropped=dropped,
        rows=rows,
        applied=applied,
        input_tokens=sum(row.input_tokens for row in rows),
        wall_time_sec=time.perf_counter() - started,
        model=settings.model,
        questions_version=version,
        cache_hits=cache_hits,
    )


def _group(result: TriageResult) -> list[tuple[str, str, list[DocumentedChange]]]:
    hops: list[tuple[str, str, list[DocumentedChange]]] = []
    for row in result.rows:
        if not hops or hops[-1][0] != row.hop_from or hops[-1][1] != row.hop_to:
            hops.append((row.hop_from, row.hop_to, []))
        hops[-1][2].append(row.change)
    return hops


def _plain_raw(
    *,
    framework_key: str,
    framework_display: str,
    from_version: str,
    to_version: str,
    hop_changes: list[tuple[str, str, list[DocumentedChange]]] | None,
    existing_raw: str | None,
    range_metadata: dict | None,
) -> str:
    if hop_changes is None:
        if existing_raw is None:
            raise ValueError("no raw Markdown to keep")
        return existing_raw
    stripped = [
        (hop_from, hop_to, [_strip_triage(change) for change in changes])
        for hop_from, hop_to, changes in hop_changes
    ]
    return render_raw_markdown(
        framework_key=framework_key,
        framework_display=framework_display,
        from_version=from_version,
        to_version=to_version,
        hop_changes=stripped,
        metadata=range_metadata,
    )


def _strip_triage(change: DocumentedChange) -> DocumentedChange:
    if not change.metadata:
        return change
    meta = {
        key: value
        for key, value in change.metadata.items()
        if not str(key).startswith("triage_")
    }
    return replace(change, metadata=meta or None)


def _all_rows_plain(raw_markdown: str) -> str:
    """4-column filter input containing every row, including ones a previous triage dropped."""
    parsed = parse_raw_markdown(raw_markdown)
    hops = _hops_without_triage(parsed.hops)
    return render_raw_markdown(
        framework_key=parsed.framework_key,
        framework_display=parsed.framework_display,
        from_version=parsed.from_version,
        to_version=parsed.to_version,
        hop_changes=hops,
        extra_lines=parsed.extra_lines or None,
    )


def _hops_without_triage(
    hops: list[tuple[str, str, list]],
) -> list[tuple[str, str, list[DocumentedChange]]]:
    from migration_oracle.pipeline.triage.markdown import RawRow

    rendered: list[tuple[str, str, list[DocumentedChange]]] = []
    for hop_from, hop_to, rows in hops:
        changes: list[DocumentedChange] = []
        for row in rows:
            if isinstance(row, RawRow):
                changes.append(
                    DocumentedChange(
                        type=row.type,
                        confidence=row.confidence,
                        source_url=row.source_url,
                        statement=row.statement,
                        metadata=None,
                    )
                )
            else:
                changes.append(_strip_triage(row))
        rendered.append((hop_from, hop_to, changes))
    return rendered


def _retriage(
    raw_markdown: str,
    *,
    framework_key: str,
    framework_display: str,
    from_version: str,
    to_version: str,
    settings: TriageSettings,
) -> str:
    jsonl_path = default_triage_jsonl_path(framework_key, from_version, to_version)
    if not jsonl_path.exists():
        raise FileNotFoundError(
            f"No triage cache at {jsonl_path}. Run triage once before --retriage-from-cache."
        )
    records = _read_jsonl(jsonl_path)
    parsed = parse_raw_markdown(raw_markdown)
    flat = [
        (hop_from, hop_to, row)
        for hop_from, hop_to, rows in parsed.hops
        for row in rows
    ]
    if len(records) != len(flat):
        raise ValueError(
            f"Triage cache has {len(records)} rows but the raw file has {len(flat)}"
        )
    version = questions_module.TRIAGE_QUESTIONS_VERSION
    rebuilt: list[tuple[str, str, list[DocumentedChange]]] = []
    rewritten_records: list[dict] = []
    input_tokens = 0
    for (hop_from, hop_to, row), record in zip(flat, records, strict=True):
        if record.get("source_url") != row.source_url:
            raise ValueError(
                "Triage cache row order does not match the raw file "
                f"({record.get('source_url')} vs {row.source_url})"
            )
        answers = record.get("answers") if isinstance(record.get("answers"), dict) else None
        source = str(record.get("triage_source") or row.triage_source or "model")
        if source == "rule" or answers is None:
            decision = str(record.get("decision") or row.triage_decision or "keep")
        else:
            decision = "drop" if should_drop(answers, settings) else "keep"
            source = "model"
        model = str(record.get("model") or settings.model or "—")
        record_version = record.get("questions_version", version)
        change = _annotate(
            DocumentedChange(
                type=row.type,
                confidence=row.confidence,
                source_url=row.source_url,
                statement=row.statement,
            ),
            decision=decision,
            source=source,
            answers=answers,
            model=model,
            version=record_version if isinstance(record_version, int) else version,
        )
        if not rebuilt or rebuilt[-1][0] != hop_from or rebuilt[-1][1] != hop_to:
            rebuilt.append((hop_from, hop_to, []))
        rebuilt[-1][2].append(change)
        updated = dict(record)
        updated["decision"] = decision
        updated["triage_source"] = source
        rewritten_records.append(updated)
        try:
            input_tokens += int(record.get("input_tokens") or 0)
        except (TypeError, ValueError):
            pass

    summary_path = default_triage_summary_path(framework_key, from_version, to_version)
    if summary_path.exists():
        try:
            previous = json.loads(summary_path.read_text(encoding="utf-8"))
            input_tokens = int(previous.get("input_tokens") or input_tokens)
        except (OSError, ValueError, TypeError):
            pass
    raw_md = render_raw_markdown(
        framework_key=parsed.framework_key or framework_key,
        framework_display=parsed.framework_display or framework_display,
        from_version=parsed.from_version or from_version,
        to_version=parsed.to_version or to_version,
        hop_changes=rebuilt,
        extra_lines=parsed.extra_lines or None,
    )
    started = time.perf_counter()
    _write_jsonl(jsonl_path, rewritten_records)
    result = _result(
        _rows_from_changes(rebuilt, rewritten_records),
        applied=True,
        started=started,
        settings=settings,
        version=version,
    )
    result.input_tokens = input_tokens
    _write_summary(summary_path, result, settings)
    emit(
        logging.INFO,
        f"Triage: recomputed decisions from cache for {framework_display} "
        f"{from_version} → {to_version} "
        f"(kept {len(result.kept)} / dropped {len(result.dropped)}).",
    )
    return raw_md


def _rows_from_changes(
    hops: list[tuple[str, str, list[DocumentedChange]]],
    records: list[dict],
) -> list[TriagedRow]:
    rows: list[TriagedRow] = []
    cursor = 0
    for hop_from, hop_to, changes in hops:
        for change in changes:
            record = records[cursor]
            cursor += 1
            answers = record.get("answers") if isinstance(record.get("answers"), dict) else None
            meta = change.metadata or {}
            rows.append(
                TriagedRow(
                    hop_from=hop_from,
                    hop_to=hop_to,
                    change=change,
                    decision=str(meta.get("triage_decision")),
                    source=str(meta.get("triage_source")),
                    answers=answers,
                    state="",
                )
            )
    return rows


def _write_artifacts(
    framework_key: str,
    from_version: str,
    to_version: str,
    result: TriageResult,
    settings: TriageSettings,
) -> None:
    if not result.applied:
        return
    jsonl_path = default_triage_jsonl_path(framework_key, from_version, to_version)
    summary_path = default_triage_summary_path(framework_key, from_version, to_version)
    records = []
    for index, row in enumerate(result.rows):
        records.append(
            {
                "index": index,
                "hop_from": row.hop_from,
                "hop_to": row.hop_to,
                "source_url": row.change.source_url,
                "statement": row.change.statement,
                "decision": row.decision,
                "triage_source": row.source,
                "answers": row.answers,
                "questions_version": result.questions_version,
                "model": result.model or settings.model,
                "input_tokens": row.input_tokens,
            }
        )
    _write_jsonl(jsonl_path, records)
    _write_summary(summary_path, result, settings)


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
    path.write_text(body, encoding="utf-8")


def _write_summary(path: Path, result: TriageResult, settings: TriageSettings) -> None:
    by_source = Counter(row.source for row in result.rows)
    by_decision = Counter(row.decision for row in result.rows)
    by_category: Counter[str] = Counter()
    for row in result.rows:
        choice = "—"
        if row.answers and isinstance(row.answers.get("category"), dict):
            choice = str(row.answers["category"].get("choice") or "—")
        by_category[choice] += 1
    summary = {
        "model": result.model,
        "questions_version": result.questions_version,
        "kept": sum(1 for row in result.rows if row.decision == "keep"),
        "dropped": sum(1 for row in result.rows if row.decision == "drop"),
        "error": sum(1 for row in result.rows if row.source == "error"),
        "rows": len(result.rows),
        "by_source": dict(by_source),
        "by_decision": dict(by_decision),
        "by_category": dict(by_category),
        "input_tokens": result.input_tokens,
        "wall_time_sec": round(result.wall_time_sec, 3),
        "cache_hits": result.cache_hits,
        "thresholds": {
            "drop_max_action_prob": settings.drop_max_action_prob,
            "drop_min_category_prob": settings.drop_min_category_prob,
            "drop_max_impact_score": settings.drop_max_impact_score,
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def _log_summary(
    framework: str, from_version: str, to_version: str, result: TriageResult
) -> None:
    if not result.applied:
        return
    errors = sum(1 for row in result.rows if row.source == "error")
    emit(
        logging.INFO,
        f"Triage {framework} {from_version} → {to_version}: "
        f"kept {len(result.kept)} / dropped {len(result.dropped)} / error {errors} "
        f"in {result.wall_time_sec:.1f}s"
        + (f" ({result.cache_hits} cache hits)" if result.cache_hits else ""),
    )


def _cache_key(version: int, model: str, state: str) -> str:
    payload = f"{version}\n{model}\n{state}".encode()
    return hashlib.sha256(payload).hexdigest()


def _cache_file(settings: TriageSettings, key: str) -> Path:
    return settings.cache_dir / "triage" / f"{key}.json"


def _cache_get(settings: TriageSettings, key: str) -> dict | None:
    path = _cache_file(settings, key)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("answers"), dict):
        return None
    return data


def _cache_put(
    settings: TriageSettings,
    key: str,
    answers: dict,
    usage: dict,
    version: int,
) -> None:
    path = _cache_file(settings, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "questions_version": version,
                "model": settings.model,
                "answers": answers,
                "usage": usage,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
