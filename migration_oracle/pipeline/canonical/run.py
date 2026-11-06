"""Canonicalize one entity batch and write the FR-5 audit artifacts.

``runs/canonical/<framework>-<from>-to-<to>-canonical.jsonl`` gets one line per
entity occurrence; ``…-summary.json`` the counts. ``--dry-run`` writes both
without graph writes, which is the cheap way to review a hop.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from migration_oracle.models.entities import MigrationEntitiesBatch
from migration_oracle.pipeline.canonical.api_index import HopApiIndex, load_hop_index
from migration_oracle.pipeline.canonical.normalize import NormalizedEntity, normalize_rule
from migration_oracle.pipeline.canonical.profiles import FrameworkProfile

# npm profiles verify against the published API index; maven profiles do not.
_INDEX_FRAMEWORKS = ("angular",)


@dataclass
class CanonicalRule:
    title: str
    occurrences: list[NormalizedEntity] = field(default_factory=list)


@dataclass
class CanonicalizedBatch:
    profile: FrameworkProfile
    rules: list[CanonicalRule] = field(default_factory=list)
    api_index_status: str = "not-applicable"  # ok | partial | unavailable | not-applicable
    api_index_versions: list[str] = field(default_factory=list)
    api_index_missing_versions: list[str] = field(default_factory=list)

    def occurrence_count(self) -> int:
        return sum(len(rule.occurrences) for rule in self.rules)


def canonicalize_batch(
    batch: MigrationEntitiesBatch,
    *,
    profile: FrameworkProfile,
    from_version: str,
    to_version: str,
    index: HopApiIndex | None = None,
    cache_dir: Path | None = None,
    token: str = "",
) -> CanonicalizedBatch:
    """Normalize + verify every occurrence of every rule in the batch.

    ``index`` is injected by tests; otherwise the Angular profile fetches (or
    reuses) the golden-file index for both hop versions. When the index cannot
    be fetched, populate continues and every npm entity is ``verified: false``.
    """
    if profile.is_npm and profile.key in _INDEX_FRAMEWORKS and index is None:
        from migration_oracle import config

        if cache_dir is None:
            cache_dir = Path(config.ARTIFACT_CACHE_DIR)
        # Unauthenticated GitHub API calls are limited to 60/h; populate runs
        # pass no token, so fall back to the configured one (spec 021).
        index = load_hop_index(
            from_version,
            to_version,
            cache_dir=cache_dir,
            token=token or config.GITHUB_TOKEN,
        )
    elif not profile.is_npm:
        index = None

    rules = [
        CanonicalRule(
            title=entity.title,
            occurrences=normalize_rule(entity, profile, index),
        )
        for entity in batch.entities
    ]
    return CanonicalizedBatch(
        profile=profile,
        rules=rules,
        api_index_status=(index.status if index is not None else "not-applicable"),
        api_index_versions=(list(index.versions) if index is not None else []),
        api_index_missing_versions=(
            list(index.missing_versions) if index is not None else []
        ),
    )


def write_canonical_audit(
    canonicalized: CanonicalizedBatch,
    *,
    framework: str,
    hop: tuple[str, str],
    jsonl_path: Path,
    summary_path: Path,
) -> None:
    """FR-5: one JSONL line per occurrence plus a summary file."""
    lines: list[str] = []
    kind_counts: dict[str, int] = {}
    verified_counts = {"true": 0, "false": 0, "ambiguous": 0, "unchecked": 0}
    keys: dict[str, set[tuple[str, str]]] = {}
    for rule in canonicalized.rules:
        for occurrence in rule.occurrences:
            kind_counts[occurrence.kind.value] = kind_counts.get(occurrence.kind.value, 0) + 1
            verified_counts[occurrence.verified] = verified_counts.get(occurrence.verified, 0) + 1
            keys.setdefault(occurrence.key, set()).add((occurrence.raw_kind, occurrence.raw_name))
            lines.append(
                json.dumps(
                    {
                        "ruleId": rule.title,
                        "role": occurrence.role,
                        "rawKind": occurrence.raw_kind,
                        "rawName": occurrence.raw_name,
                        "llmPackage": occurrence.llm_package,
                        "canonical": occurrence.to_canonical().model_dump(mode="json"),
                        "applied": occurrence.applied,
                        "verified": occurrence.verified,
                    },
                    ensure_ascii=False,
                )
            )
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    jsonl_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    total = sum(kind_counts.values())
    collapsed = sum(len(raw) for raw in keys.values()) - len(keys)
    # Keys whose every occurrence is unverified — the manual-review list (AC-6).
    unverified_keys: dict[str, list[str]] = {}
    for rule in canonicalized.rules:
        for occurrence in rule.occurrences:
            if occurrence.verified not in ("true", "unchecked"):
                unverified_keys.setdefault(occurrence.key, []).append(rule.title)
    summary = {
        "framework": framework,
        "from_version": hop[0],
        "to_version": hop[1],
        "occurrences": total,
        "counts_by_kind": kind_counts,
        "verified_true": verified_counts["true"],
        "verified_false": verified_counts["false"],
        "verified_ambiguous": verified_counts["ambiguous"],
        "verified_true_pct": round(100 * verified_counts["true"] / total, 1) if total else 0.0,
        "verified_ambiguous_pct": round(100 * verified_counts["ambiguous"] / total, 1)
        if total
        else 0.0,
        "verified_false_pct": round(100 * verified_counts["false"] / total, 1) if total else 0.0,
        "verified_unchecked": verified_counts["unchecked"],
        "raw_names_collapsed": collapsed,
        "distinct_keys": len(keys),
        "unverified_keys": {
            key: sorted(set(titles)) for key, titles in sorted(unverified_keys.items())
        },
        "api_index": {
            "status": canonicalized.api_index_status,
            "versions": canonicalized.api_index_versions,
            "missing_versions": canonicalized.api_index_missing_versions,
        },
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")