"""Classify every rule by how a service shows that the rule applies (spec 027).

One System-1 call per rule per question version, cached. Rule-level and
service-independent: no service data is involved. The result is written to
``runs/signals/`` and, later in populate, to the ``MigrationRule`` node.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from migration_oracle.models.entities import MigrationEntitiesBatch, MigrationEntity
from migration_oracle.pipeline._paths import (
    default_signals_jsonl_path,
    default_signals_summary_path,
)
from migration_oracle.pipeline._progress import progress_bar
from migration_oracle.pipeline.canonical.run import CanonicalRule, CanonicalizedBatch
from migration_oracle.pipeline.rule_ids import rule_id_for
from migration_oracle.pipeline.signals import questions as questions_module
from migration_oracle.pipeline.signals.contract import (
    BEHAVIORAL,
    ContractResult,
    apply_contract,
    chosen_features,
    rule_shortcut,
    shortcut_result,
)
from migration_oracle.pipeline.signals.features import features_for
from migration_oracle.pipeline.signals.questions import signal_questions
from migration_oracle.pipeline.signals.settings import SignalSettings, load_settings
from migration_oracle.pipeline.triage.client import (
    System1HttpClient,
    TriageClient,
    TriageRejected,
    TriageTransportError,
    TriageUnavailable,
    emit,
    reset_client_notices,
)

logger = logging.getLogger("migration_oracle.pipeline.signals")

NIMBLE_OK = "ok"
NIMBLE_DISABLED = "disabled"
NIMBLE_UNAVAILABLE = "unavailable"
NIMBLE_PARTIAL = "partial"

#: ``signalModel`` value on the graph node (FR-5).
SIGNAL_MODEL_NAME = "nimble"

SOURCE_ERROR = "error"
#: Never asked: Nimble is off for the run, so the rule is simply unclassified.
SOURCE_DISABLED = "disabled"

_notices: set[str] = set()


def reset_notices() -> None:
    """Test hook. Notices are once per process, and the run notices reset too."""
    _notices.clear()
    reset_client_notices()


def notify_once(key: str, level: int, message: str) -> None:
    if key in _notices:
        return
    _notices.add(key)
    emit(level, message)


@dataclass
class SignalRecord:
    """One rule's classification, as written to the artifact and the graph."""

    rule_id: str
    title: str
    state: str
    signal: str
    signal_source: str
    applied: bool = True
    reason: str = ""
    signal_keys: list[str] = field(default_factory=list)
    name_only_keys: list[str] = field(default_factory=list)
    unverified_keys: list[str] = field(default_factory=list)
    features: list[str] = field(default_factory=list)
    feature_probabilities: dict[str, float] = field(default_factory=dict)
    confidence: float = 0.0
    answers: dict | None = None
    input_tokens: int = 0
    from_cache: bool = False

    def graph_properties(self, model: str, version: int) -> dict:
        """FR-5 properties for ``MigrationRule``."""
        return {
            "signal": self.signal,
            "signalConfidence": float(self.confidence),
            "signalSource": self.signal_source,
            "signalKeys": list(self.signal_keys),
            "features": list(self.features),
            "signalQuestionsVersion": version,
            "signalModel": model,
        }


@dataclass
class SignalRunResult:
    records: list[SignalRecord]
    applied: bool
    status: str
    calls: int = 0
    cache_hits: int = 0
    input_tokens: int = 0
    wall_time_sec: float = 0.0
    errors: int = 0

    def properties_by_rule_id(self) -> dict[str, dict]:
        """Only the rules that were actually classified (FR-5)."""
        version = questions_module.SIGNAL_QUESTIONS_VERSION
        return {
            record.rule_id: record.graph_properties(SIGNAL_MODEL_NAME, version)
            for record in self.records
            if record.applied
        }


@dataclass
class _Work:
    entity: MigrationEntity
    canonical_rule: CanonicalRule
    rule_id: str
    state: str
    shortcut: ContractResult | None


def classify_signals(
    *,
    batch: MigrationEntitiesBatch,
    canonicalized: CanonicalizedBatch,
    framework_key: str,
    framework_display: str,
    hop: tuple[str, str],
    client: TriageClient | None = None,
    settings: SignalSettings | None = None,
    force: bool = False,
    jsonl_path: Path | None = None,
    summary_path: Path | None = None,
) -> SignalRunResult:
    """Classify every rule of one hop. Never raises for a Nimble problem."""
    started = time.perf_counter()
    settings = settings or load_settings()
    version = questions_module.SIGNAL_QUESTIONS_VERSION
    features = features_for(framework_key, framework_display)

    work = [
        _prepare(
            entity=entity,
            canonical_rule=canonical_rule,
            framework_display=framework_display,
            hop=hop,
            settings=settings,
        )
        for entity, canonical_rule in zip(batch.entities, canonicalized.rules)
    ]

    if not settings.enabled:
        notify_once(
            "signals-disabled",
            logging.INFO,
            "Rule signals disabled (TRIAGE_BASE_URL or TRIAGE_MODEL unset); "
            "no signal properties are written.",
        )
        result = SignalRunResult(
            records=[
                _unclassified(item, "Nimble is not configured", SOURCE_DISABLED)
                for item in work
            ],
            applied=False,
            status=NIMBLE_DISABLED,
        )
        result.wall_time_sec = time.perf_counter() - started
        # The summary still records the status, so the hop says "nimble:
        # disabled" instead of looking like a hop that was never classified.
        _write_artifacts(
            result,
            version=version,
            model=settings.model,
            framework=framework_key,
            hop=hop,
            jsonl_path=jsonl_path
            or default_signals_jsonl_path(framework_key, hop[0], hop[1]),
            summary_path=summary_path
            or default_signals_summary_path(framework_key, hop[0], hop[1]),
            feature_ids=[feature.id for feature in features],
        )
        return result

    try:
        records, calls, cache_hits, status = asyncio.run(
            _classify_async(
                work,
                client=client,
                settings=settings,
                features=features,
                framework=framework_display,
                hop=hop,
                version=version,
                force=force,
            )
        )
    except Exception as exc:  # noqa: BLE001 - populate must continue
        logger.warning("Rule signals failed: %s", exc)
        emit(
            logging.WARNING,
            f"Rule signals skipped ({exc}); no signal properties are written.",
        )
        result = SignalRunResult(
            records=[_unclassified(item, str(exc)) for item in work],
            applied=False,
            status=NIMBLE_UNAVAILABLE,
        )
        result.wall_time_sec = time.perf_counter() - started
        _write_artifacts(
            result,
            version=version,
            model=settings.model,
            framework=framework_key,
            hop=hop,
            jsonl_path=jsonl_path
            or default_signals_jsonl_path(framework_key, hop[0], hop[1]),
            summary_path=summary_path
            or default_signals_summary_path(framework_key, hop[0], hop[1]),
            feature_ids=[feature.id for feature in features],
        )
        return result

    result = SignalRunResult(
        records=records,
        applied=status in (NIMBLE_OK, NIMBLE_PARTIAL),
        status=status,
        calls=calls,
        cache_hits=cache_hits,
        input_tokens=sum(record.input_tokens for record in records),
        errors=sum(record.signal_source == SOURCE_ERROR for record in records),
    )
    result.wall_time_sec = time.perf_counter() - started
    _write_artifacts(
        result,
        version=version,
        model=settings.model,
        framework=framework_key,
        hop=hop,
        jsonl_path=jsonl_path
        or default_signals_jsonl_path(framework_key, hop[0], hop[1]),
        summary_path=summary_path
        or default_signals_summary_path(framework_key, hop[0], hop[1]),
        feature_ids=[feature.id for feature in features],
    )
    _log_summary(framework_display, hop, result)
    return result


# --- state rendering (FR-3) -------------------------------------------------


def render_state(
    entity: MigrationEntity,
    canonical_rule: CanonicalRule,
    *,
    framework: str,
    hop: tuple[str, str],
    max_chars: int,
) -> str:
    """The labelled state string, capped at ``max_chars``."""
    lines = [
        f"Framework: {framework} · Hop: {hop[0]} → {hop[1]}",
        f"Rule: {entity.title}",
        f"Type: {entity.change_type} · Section: {entity.source_section}",
    ]
    if entity.reason:
        lines.append(f"Reason: {entity.reason}")
    if canonical_rule.occurrences:
        lines.append("Entities (role · canonical key · verified):")
        for occurrence in canonical_rule.occurrences:
            lines.append(f"  {occurrence.role} · {occurrence.key} · {occurrence.verified}")
    if entity.steps:
        lines.append("Steps:")
        for step in entity.steps:
            lines.append(f"  {step.index} {step.step_type.value} · {step.summary}")
    text = "\n".join(lines)
    return text[:max_chars] if len(text) > max_chars else text


def _prepare(
    *,
    entity: MigrationEntity,
    canonical_rule: CanonicalRule,
    framework_display: str,
    hop: tuple[str, str],
    settings: SignalSettings,
) -> _Work:
    shortcut = (
        shortcut_result(canonical_rule.occurrences)
        if rule_shortcut(
            occurrences=canonical_rule.occurrences,
            change_type=entity.change_type,
            source_section=entity.source_section,
        )
        else None
    )
    return _Work(
        entity=entity,
        canonical_rule=canonical_rule,
        rule_id=rule_id_for(framework_display, hop[1], entity.title),
        state=render_state(
            entity,
            canonical_rule,
            framework=framework_display,
            hop=hop,
            max_chars=settings.state_max_chars,
        ),
        shortcut=shortcut,
    )


# --- the async run ----------------------------------------------------------


async def _classify_async(
    work: list[_Work],
    *,
    client: TriageClient | None,
    settings: SignalSettings,
    features,
    framework: str,
    hop: tuple[str, str],
    version: int,
    force: bool,
) -> tuple[list[SignalRecord], int, int, str]:
    questions = signal_questions(features)
    feature_ids = [feature.id for feature in features]
    resolved: list[SignalRecord | None] = [None] * len(work)
    pending: list[int] = []
    for index, item in enumerate(work):
        if item.shortcut is not None and not feature_ids:
            resolved[index] = _from_contract(
                item, item.shortcut, features=[], probabilities={}, answers=None
            )
            continue
        pending.append(index)

    if not pending:
        return [record for record in resolved if record is not None], 0, 0, NIMBLE_OK

    owns_client = client is None
    if client is None:
        client = System1HttpClient(settings.client)

    calls = 0
    cache_hits = 0
    status = NIMBLE_OK
    bar = progress_bar(len(work), f"Signals {framework} {hop[0]}→{hop[1]}")
    for record in resolved:
        if record is not None:
            bar.update(1)

    async def resolve_at(index: int) -> tuple[SignalRecord, bool, int]:
        item = work[index]
        answers, tokens, from_cache = await _answers_for(
            item.state,
            client=client,
            settings=settings,
            questions=questions,
            version=version,
            framework=framework,
            force=force,
        )
        contract = item.shortcut or apply_contract(
            answer=answers,
            occurrences=item.canonical_rule.occurrences,
            settings=settings,
        )
        chosen, probabilities = chosen_features(answers, feature_ids, settings)
        record = _from_contract(
            item,
            contract,
            features=chosen,
            probabilities=probabilities,
            answers=answers,
            from_cache=from_cache,
            input_tokens=tokens,
        )
        return record, not from_cache, tokens

    semaphore = asyncio.Semaphore(settings.max_concurrent)

    async def limited(index: int) -> tuple[int, SignalRecord, bool]:
        async with semaphore:
            try:
                record, did_call, _tokens = await resolve_at(index)
            except (TriageTransportError, TriageUnavailable, TriageRejected) as exc:
                record = _unclassified(work[index], str(exc))
                record.answers = None
                bar.update(1)
                return index, record, False
            bar.update(1)
            bar.set_postfix(
                {
                    "calls": calls + did_call,
                    "cache": cache_hits + (not did_call),
                },
                refresh=False,
            )
            return index, record, did_call

    try:
        # The first rule probes the endpoint: a hard failure means the whole
        # stage is skipped, as in triage.
        first_index = pending[0]
        try:
            record, did_call, _tokens = await resolve_at(first_index)
        except (TriageUnavailable, TriageRejected) as exc:
            notify_once(
                "signals-unavailable",
                logging.WARNING,
                f"Rule signals unavailable ({exc}); no signal properties are written.",
            )
            return (
                [_unclassified(item, str(exc)) for item in work],
                0,
                0,
                NIMBLE_UNAVAILABLE,
            )
        except TriageTransportError as exc:
            record = _unclassified(work[first_index], str(exc))
            did_call = False
        resolved[first_index] = record
        calls += did_call
        cache_hits += not did_call
        bar.update(1)
        bar.set_postfix({"calls": calls, "cache": cache_hits}, refresh=False)

        rest = pending[1:]
        if rest:
            outcomes = await asyncio.gather(*(limited(index) for index in rest))
            for index, record, did_call in outcomes:
                resolved[index] = record
                calls += did_call
                cache_hits += not did_call
    finally:
        bar.close()
        if owns_client:
            await client.aclose()

    records = [record for record in resolved if record is not None]
    if any(record.signal_source == SOURCE_ERROR for record in records):
        status = NIMBLE_PARTIAL
    return records, calls, cache_hits, status


async def _answers_for(
    state: str,
    *,
    client: TriageClient,
    settings: SignalSettings,
    questions: dict,
    version: int,
    framework: str,
    force: bool,
) -> tuple[dict, int, bool]:
    key = cache_key(version, settings.model, framework, state)
    if not force:
        cached = cache_get(settings, key)
        if cached is not None:
            return cached["answers"], 0, True
    request = getattr(client, "classify_request", None)
    if request is not None:
        answers, usage = await request(state, questions)
    else:
        answers = await client.classify(state, questions)
        usage = {}
    if not isinstance(answers, dict):
        raise TriageTransportError("classifier returned no answers object")
    tokens = _as_int(usage.get("input_tokens")) if isinstance(usage, dict) else 0
    cache_put(settings, key, answers, {"input_tokens": tokens}, version, settings.model)
    return answers, tokens, False


# --- records ----------------------------------------------------------------


def _from_contract(
    item: _Work,
    contract: ContractResult,
    *,
    features: list[str],
    probabilities: dict[str, float],
    answers: dict | None,
    from_cache: bool = False,
    input_tokens: int = 0,
) -> SignalRecord:
    return SignalRecord(
        rule_id=item.rule_id,
        title=item.entity.title,
        state=item.state,
        signal=contract.signal,
        signal_source=contract.source,
        reason=contract.reason,
        signal_keys=list(contract.keys),
        name_only_keys=list(contract.name_only_keys),
        unverified_keys=list(contract.unverified_keys),
        features=list(features),
        feature_probabilities=dict(probabilities),
        confidence=float(contract.confidence),
        answers=answers,
        input_tokens=input_tokens,
        from_cache=from_cache,
    )


def _unclassified(item: _Work, reason: str, source: str = SOURCE_ERROR) -> SignalRecord:
    """A rule Nimble could not classify. The planner reads it as ``behavioral``."""
    return SignalRecord(
        rule_id=item.rule_id,
        title=item.entity.title,
        state=item.state,
        signal=BEHAVIORAL,
        signal_source=source,
        applied=False,
        reason=reason,
    )


# --- cache (FR-7) -----------------------------------------------------------


def cache_key(version: int, model: str, framework: str, state: str) -> str:
    payload = f"{version}\n{model}\n{framework}\n{state}".encode()
    return hashlib.sha256(payload).hexdigest()


def _cache_file(settings: SignalSettings, key: str) -> Path:
    return settings.cache_dir / "signals" / f"{key}.json"


def cache_get(settings: SignalSettings, key: str) -> dict | None:
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


def cache_put(
    settings: SignalSettings,
    key: str,
    answers: dict,
    usage: dict,
    version: int,
    model: str,
) -> None:
    path = _cache_file(settings, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "questions_version": version,
                "model": model,
                "answers": answers,
                "usage": usage,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


# --- artifacts (FR-7) -------------------------------------------------------


def _write_artifacts(
    result: SignalRunResult,
    *,
    version: int,
    model: str,
    framework: str,
    hop: tuple[str, str],
    jsonl_path: Path,
    summary_path: Path,
    feature_ids: list[str],
) -> None:
    lines = [
        json.dumps(
            {
                "ruleId": record.rule_id,
                "title": record.title,
                "state": record.state,
                "answers": record.answers,
                "signal": record.signal,
                "signalSource": record.signal_source,
                "signalConfidence": record.confidence,
                "reason": record.reason,
                "signalKeys": record.signal_keys,
                "nameOnlyKeys": record.name_only_keys,
                "unverifiedKeys": record.unverified_keys,
                "features": record.features,
                "featureProbabilities": record.feature_probabilities,
                "applied": record.applied,
                "cacheHit": record.from_cache,
                "inputTokens": record.input_tokens,
            },
            ensure_ascii=False,
        )
        for record in result.records
    ]
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    jsonl_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    by_signal = Counter(record.signal for record in result.records)
    by_source = Counter(record.signal_source for record in result.records)
    by_feature: Counter[str] = Counter()
    for record in result.records:
        for feature in record.features:
            by_feature[feature] += 1
    summary = {
        "framework": framework,
        "from_version": hop[0],
        "to_version": hop[1],
        "rules": len(result.records),
        "nimble": result.status,
        "by_signal": dict(sorted(by_signal.items())),
        "by_source": dict(sorted(by_source.items())),
        "by_feature": dict(sorted(by_feature.items())),
        "guard": by_source.get("guard", 0),
        "low_confidence": by_source.get("low_confidence", 0),
        "errors": result.errors,
        "unclassified": sum(not record.applied for record in result.records),
        "calls": result.calls,
        "cache_hits": result.cache_hits,
        "input_tokens": result.input_tokens,
        "wall_time_sec": round(result.wall_time_sec, 3),
        "questions_version": version,
        "model": model,
        "features": list(feature_ids),
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def _log_summary(framework: str, hop: tuple[str, str], result: SignalRunResult) -> None:
    if result.status == NIMBLE_UNAVAILABLE:
        return
    counts = Counter(record.signal for record in result.records)
    detail = ", ".join(f"{name} {count}" for name, count in sorted(counts.items()))
    emit(
        logging.INFO,
        f"Rule signals {framework} {hop[0]} → {hop[1]}: "
        f"{len(result.records)} rules ({detail}) "
        f"in {result.wall_time_sec:.1f}s"
        + (f", {result.cache_hits} cache hits" if result.cache_hits else ""),
    )


def _as_int(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
