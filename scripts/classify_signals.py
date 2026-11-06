#!/usr/bin/env python3
"""Backfill rule-signal properties on ``MigrationRule`` nodes (spec 027 FR-6).

Hops already in the graph are not repopulated, so their rules never get the
signal classification that a fresh populate writes. This script classifies the
cached ``runs/json/*-entities.json`` artifacts and runs

    MATCH (r:MigrationRule {ruleId: $id}) SET r += $props

for each rule. It sets only the FR-5 properties, is idempotent, and reports
rules whose ``ruleId`` is not in the graph.

Usage:
    python scripts/classify_signals.py --framework angular 19.2.0 20.0.0
    python scripts/classify_signals.py --framework angular --all
    python scripts/classify_signals.py --framework spring-boot --all --dry-run

Requires NEO4J_URI and NEO4J_PASSWORD (loaded from .env).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(PROJECT_ROOT))


def _load_env() -> None:
    """Load ``.env`` before any module that needs ``NEO4J_*`` is imported."""
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")


_load_env()

from migration_oracle.models.entities import MigrationEntitiesBatch  # noqa: E402
from migration_oracle.pipeline._paths import (  # noqa: E402
    RUNS_JSON,
    default_canonical_jsonl_path,
    default_canonical_summary_path,
    default_signals_jsonl_path,
    default_signals_summary_path,
)
from migration_oracle.pipeline.canonical import (  # noqa: E402
    canonicalize_batch,
    profile_for,
    write_canonical_audit,
)
from migration_oracle.pipeline.extractors import FRAMEWORK_DISPLAY_NAMES  # noqa: E402
from migration_oracle.pipeline.signals import classify_signals  # noqa: E402


def _parse_entities_filename(path: Path) -> tuple[str, str, str] | None:
    stem = path.name.removesuffix("-entities.json")
    for framework in sorted(FRAMEWORK_DISPLAY_NAMES, key=len, reverse=True):
        prefix = f"{framework}-"
        if not stem.startswith(prefix):
            continue
        rest = stem[len(prefix) :]
        if "-to-" not in rest:
            continue
        from_version, to_version = rest.split("-to-", 1)
        return framework, from_version, to_version
    return None


def _apply(properties: dict[str, dict], *, dry_run: bool) -> tuple[int, int, list[str]]:
    """``(updated, unchanged, unknown_rule_ids)``."""
    if not properties:
        return 0, 0, []
    # Imported here so ``--dry-run`` and the ``--help`` path do not need a graph.
    from migration_oracle.graph.driver import read_session, write_session

    with read_session() as session:
        existing = {
            record["ruleId"]
            for record in session.run(
                "MATCH (r:MigrationRule) WHERE r.ruleId IN $ids RETURN r.ruleId AS ruleId",
                ids=list(properties),
            )
        }
    unknown = sorted(rule_id for rule_id in properties if rule_id not in existing)
    known = {rule_id: props for rule_id, props in properties.items() if rule_id in existing}
    if dry_run or not known:
        return 0, len(known), unknown

    updated = 0
    with write_session() as session:
        for rule_id, props in known.items():
            record = session.run(
                """
                MATCH (r:MigrationRule {ruleId: $id})
                WITH r, properties(r) AS before
                SET r += $props
                RETURN before
                """,
                id=rule_id,
                props=props,
            ).single()
            before = record["before"] if record else {}
            # "updated" = any FR-5 property was new or changed, not only a
            # first classification; a re-classification is an update too.
            if any(before.get(name) != value for name, value in props.items()):
                updated += 1
    return updated, len(known) - updated, unknown


def _classify_one(
    *,
    framework: str,
    from_version: str,
    to_version: str,
    force: bool,
    dry_run: bool,
) -> int:
    display_name = FRAMEWORK_DISPLAY_NAMES.get(framework, framework)
    json_path = RUNS_JSON / f"{framework}-{from_version}-to-{to_version}-entities.json"
    label = f"{framework} {from_version} → {to_version}"
    if not json_path.exists():
        print(f"SKIP  {label}: missing {json_path}")
        return 0

    batch = MigrationEntitiesBatch.model_validate_json(
        json_path.read_text(encoding="utf-8")
    )
    canonicalized = canonicalize_batch(
        batch,
        profile=profile_for(framework, display_name),
        from_version=from_version,
        to_version=to_version,
    )
    write_canonical_audit(
        canonicalized,
        framework=framework,
        hop=(from_version, to_version),
        jsonl_path=default_canonical_jsonl_path(framework, from_version, to_version),
        summary_path=default_canonical_summary_path(framework, from_version, to_version),
    )
    result = classify_signals(
        batch=batch,
        canonicalized=canonicalized,
        framework_key=framework,
        framework_display=display_name,
        hop=(from_version, to_version),
        force=force,
        jsonl_path=default_signals_jsonl_path(framework, from_version, to_version),
        summary_path=default_signals_summary_path(framework, from_version, to_version),
    )
    properties = result.properties_by_rule_id()
    if dry_run:
        print(
            f"DRY   {label}: nimble={result.status}, "
            f"{len(properties)}/{len(result.records)} rules classified "
            f"({result.calls} calls, {result.cache_hits} cache hits)"
        )
        return 0
    if not properties:
        print(f"WARN  {label}: nimble={result.status}, nothing to write")
        return 0

    updated, unchanged, unknown = _apply(properties, dry_run=False)
    print(
        f"OK    {label}: nimble={result.status}, {updated} updated, "
        f"{unchanged} unchanged, "
        f"{len(properties)} classified of {len(result.records)} rules"
    )
    if unknown:
        print(
            f"WARN  {label}: {len(unknown)} ruleId(s) not in the graph "
            "(populate that hop first, or the rule title changed):"
        )
        for rule_id in unknown[:10]:
            print(f"        {rule_id}")
        if len(unknown) > 10:
            print(f"        … and {len(unknown) - 10} more")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill rule-signal properties on MigrationRule nodes."
    )
    parser.add_argument(
        "--framework",
        required=True,
        help="Registered framework extractor key (e.g. angular, spring-boot).",
    )
    parser.add_argument("from_version", nargs="?", help="Source version (unless --all).")
    parser.add_argument("to_version", nargs="?", help="Target version (unless --all).")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Every runs/json/*-entities.json file of this framework.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Classify and write artifacts, but do not touch the graph.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ignore the rule-signal answer cache.",
    )
    return parser.parse_args()


def main() -> int:
    # Loaded here, not at import time: importing this module (as the tests do)
    # must not pull the developer's .env into the process.
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
    args = _parse_args()
    hops: list[tuple[str, str]] = []
    if args.all:
        for path in sorted(RUNS_JSON.glob(f"{args.framework}-*-entities.json")):
            parsed = _parse_entities_filename(path)
            if parsed is None or parsed[0] != args.framework:
                continue
            hops.append((parsed[1], parsed[2]))
        if not hops:
            print(
                f"No entities JSON files for {args.framework} under {RUNS_JSON}/",
                file=sys.stderr,
            )
            return 1
    else:
        if not args.from_version or not args.to_version:
            print(
                "Provide FROM TO, or --all.\n"
                "Example: python scripts/classify_signals.py --framework angular --all",
                file=sys.stderr,
            )
            return 2
        hops.append((args.from_version, args.to_version))

    for from_version, to_version in hops:
        _classify_one(
            framework=args.framework,
            from_version=from_version,
            to_version=to_version,
            force=args.force,
            dry_run=args.dry_run,
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        from migration_oracle.graph.driver import close_driver

        close_driver()
