#!/usr/bin/env python3
"""Populate the Neo4j graph from cached pipeline artifacts in runs/json/.

Reads entities JSON produced by the filter/extract pipeline and writes Version,
MigrationRule, MigrationStep, and related nodes. Also loads community insights
from neo4j_community_insights.json (MigrationRule nodes with
ruleType='community_insight'). Does not call LLMs or re-extract upstream data.

Usage:
  python scripts/populate_graph.py --framework spring-boot 3.5.0 4.0.0
  python scripts/populate_graph.py --all
  python scripts/populate_graph.py --community-insights-only
  python scripts/populate_graph.py --framework spring-boot 3.5.0 4.0.0 --force

Requires NEO4J_URI and NEO4J_PASSWORD (load from .env via python-dotenv or envFile).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_COMMUNITY_INSIGHTS_PATH = PROJECT_ROOT / "neo4j_community_insights.json"
load_dotenv(PROJECT_ROOT / ".env")

sys.path.insert(0, str(PROJECT_ROOT))

from migration_oracle.graph.driver import close_driver
from migration_oracle.mcp.graph.queries import community as community_queries
from migration_oracle.mcp.graph.queries.upgrade import resolve_version
from migration_oracle.models.entities import MigrationEntitiesBatch
from migration_oracle.models.graph import VersionResolutionFailure
from migration_oracle.pipeline._paths import (
    RUNS_JSON,
    default_entities_json_path,
    default_filtered_md_path,
    default_raw_md_path,
)
from migration_oracle.pipeline.extractors import FRAMEWORK_DISPLAY_NAMES
from migration_oracle.pipeline.populator import populate_graph


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


def _populate_one(
    *,
    framework: str,
    from_version: str,
    to_version: str,
    dry_run: bool,
    force: bool,
) -> int:
    display_name = FRAMEWORK_DISPLAY_NAMES.get(framework, framework)
    raw_path = default_raw_md_path(framework, from_version, to_version)
    filtered_path = default_filtered_md_path(framework, from_version, to_version)
    json_path = default_entities_json_path(framework, from_version, to_version)

    if not json_path.exists():
        print(f"SKIP  {framework} {from_version} → {to_version}: missing {json_path}")
        return 0

    batch = MigrationEntitiesBatch.model_validate_json(
        json_path.read_text(encoding="utf-8")
    )
    result = populate_graph(
        batch=batch,
        framework_display=display_name,
        framework_key=framework,
        to_version=to_version,
        from_version=from_version,
        raw_md_path=str(raw_path),
        filtered_md_path=str(filtered_path),
        entities_json_path=str(json_path),
        dry_run=dry_run,
        skip_if_version_exists=not force,
    )

    label = f"{framework} {from_version} → {to_version}"
    if dry_run:
        print(f"DRY   {label}: graph untouched")
    elif result.skipped:
        print(f"SKIP  {label}: Version node already exists (use --force to re-populate)")
    else:
        print(
            f"OK    {label}: {result.rules_written} rules, "
            f"{result.steps_written} steps, {result.entities_written} entities"
        )
    return 0


def _insight_field(record: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in record and record[key] is not None:
            return record[key]
    return default


def _normalize_community_insight(record: dict[str, Any]) -> dict[str, Any] | None:
    statement = _insight_field(record, "statement")
    if not statement or not str(statement).strip():
        return None

    version = _insight_field(
        record, "frameworkVersion", "spring_boot_version", "version"
    )
    framework = _insight_field(record, "framework", default="Spring Boot")
    if not version:
        return None

    source_url = _insight_field(record, "sourceUrl", "evidence_url", default="")
    source_url = str(source_url).strip() or None

    return {
        "statement": str(statement).strip(),
        "framework": str(framework).strip(),
        "version": str(version).strip(),
        "solution": _insight_field(record, "solution"),
        "confidence": _insight_field(record, "confidence"),
        "evidence_url": source_url,
        "affected_classes": list(
            _insight_field(record, "affectedClasses", "affected_classes", default=[])
            or []
        ),
        "affected_properties": list(
            _insight_field(record, "affectedProperties", "affected_properties", default=[])
            or []
        ),
        "affected_dependencies": list(
            _insight_field(
                record, "affectedDependencies", "affected_dependencies", default=[]
            )
            or []
        ),
        "submitted_by": _insight_field(
            record, "submittedBy", "submitted_by", default="populate-graph-script"
        ),
    }


def _maybe_embedding(statement: str) -> list[float] | None:
    if os.environ.get("POPULATE_MIGRATION_EMBEDDINGS", "").lower() in {
        "0",
        "false",
        "no",
        "off",
    }:
        return None
    try:
        from migration_oracle.mcp.tools.search import get_embedding_model

        return get_embedding_model().encode(statement).tolist()
    except Exception:
        return None


def _populate_community_insights(*, path: Path, dry_run: bool) -> int:
    if not path.is_file():
        print(f"SKIP  community insights: file not found ({path})")
        return 0

    try:
        records = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"FAIL  community insights: invalid JSON in {path}: {exc}", file=sys.stderr)
        return 1

    if not isinstance(records, list):
        print(f"FAIL  community insights: expected JSON array in {path}", file=sys.stderr)
        return 1

    created = 0
    duplicates = 0
    skipped = 0
    failed = 0

    print(f"\nCommunity insights from {path.name} ({len(records)} records)")
    for index, raw in enumerate(records, start=1):
        if not isinstance(raw, dict):
            print(f"SKIP  insight #{index}: expected object, got {type(raw).__name__}")
            skipped += 1
            continue

        insight = _normalize_community_insight(raw)
        if insight is None:
            print(f"SKIP  insight #{index}: missing statement or version")
            skipped += 1
            continue

        label = (
            f"{insight['framework']} {insight['version']}: "
            f"{insight['statement'][:72]}..."
        )

        if dry_run:
            print(f"DRY   {label}")
            continue

        resolution = resolve_version(insight["framework"], insight["version"], mode="floor")
        if isinstance(resolution, VersionResolutionFailure):
            print(
                f"WARN  {label}\n"
                f"      Version not in graph "
                f"({resolution.status}; candidates: "
                f"{', '.join(resolution.candidatesConsidered) or 'none'})"
            )
            failed += 1
            continue

        embedding = _maybe_embedding(insight["statement"])
        try:
            insight_id, is_duplicate = community_queries.submit_insight(
                statement=insight["statement"],
                framework=insight["framework"],
                version=resolution.resolvedVersion,
                solution=insight["solution"],
                affected_properties=insight["affected_properties"],
                affected_classes=insight["affected_classes"],
                affected_dependencies=insight["affected_dependencies"],
                evidence_url=insight["evidence_url"],
                confidence=insight["confidence"],
                submitted_by=str(insight["submitted_by"]),
                embedding=embedding,
            )
        except ValueError as exc:
            print(f"WARN  {label}\n      {exc}")
            failed += 1
            continue

        if is_duplicate:
            print(f"DUP   {label}\n      existing insight_id={insight_id}")
            duplicates += 1
        else:
            print(f"OK    {label}\n      insight_id={insight_id}")
            created += 1

    if dry_run:
        print(f"DRY   community insights: {len(records)} record(s) validated")
    else:
        print(
            f"Done  community insights: {created} created, "
            f"{duplicates} duplicate(s), {skipped} skipped, {failed} failed"
        )
    return 1 if failed else 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Populate the graph from cached runs/json/*-entities.json artifacts."
    )
    parser.add_argument(
        "--framework",
        help="Registered framework extractor key (e.g. spring-boot, angular, wildfly).",
    )
    parser.add_argument(
        "from_version",
        nargs="?",
        help="Source version (required unless --all).",
    )
    parser.add_argument(
        "to_version",
        nargs="?",
        help="Target version (required unless --all).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Populate every *-entities.json file under runs/json/.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate artifacts only; do not write to the graph.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-populate even when the target Version node already exists.",
    )
    parser.add_argument(
        "--community-insights",
        type=Path,
        default=DEFAULT_COMMUNITY_INSIGHTS_PATH,
        help="JSON file of community insights to submit after migration populate.",
    )
    parser.add_argument(
        "--skip-community-insights",
        action="store_true",
        help="Do not load neo4j_community_insights.json.",
    )
    parser.add_argument(
        "--community-insights-only",
        action="store_true",
        help="Only submit community insights; skip runs/json migration populate.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    exit_code = 0

    run_migration = not args.community_insights_only

    if run_migration and args.all:
        json_files = sorted(RUNS_JSON.glob("*-entities.json"))
        if not json_files:
            print(f"No entities JSON files found under {RUNS_JSON}/", file=sys.stderr)
            exit_code = 1
        else:
            for json_path in json_files:
                parsed = _parse_entities_filename(json_path)
                if parsed is None:
                    print(f"SKIP  {json_path.name}: cannot parse framework/versions")
                    continue
                framework, from_version, to_version = parsed
                if _populate_one(
                    framework=framework,
                    from_version=from_version,
                    to_version=to_version,
                    dry_run=args.dry_run,
                    force=args.force,
                ):
                    exit_code = 1

    elif run_migration:
        if not args.framework or not args.from_version or not args.to_version:
            print(
                "Provide --framework FROM TO, use --all, or --community-insights-only.\n"
                "Example: python scripts/populate_graph.py --framework spring-boot 3.5.0 4.0.0",
                file=sys.stderr,
            )
            return 2
        exit_code = _populate_one(
                framework=args.framework,
                from_version=args.from_version,
                to_version=args.to_version,
            dry_run=args.dry_run,
            force=args.force,
        )

    if not args.skip_community_insights:
        community_exit = _populate_community_insights(
            path=args.community_insights,
            dry_run=args.dry_run,
        )
        exit_code = max(exit_code, community_exit)

    return exit_code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        close_driver()
