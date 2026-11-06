"""Audit artifacts (spec 025 FR-5) and the AC-5 Spring Boot check."""

from __future__ import annotations

import json
from pathlib import Path

from migration_oracle.models.entities import (
    AffectedEntity,
    EntityKind,
    EntityRole,
    MigrationEntitiesBatch,
)
from migration_oracle.pipeline.canonical import (
    canonicalize_batch,
    profile_for,
    write_canonical_audit,
)
from migration_oracle.pipeline.canonical.api_index import HopApiIndex, build_hop_index

RUNS_JSON = Path("runs/json")


def _batch() -> MigrationEntitiesBatch:
    return MigrationEntitiesBatch(
        entities=[
            {
                "source_section": "breaking_change",
                "title": "InjectFlags removed",
                "change_type": "breaking_change",
                "reason": "r",
                "scopes": [{"scope": "api-surface", "severity": "high"}],
                "entities": [
                    AffectedEntity(
                        kind=EntityKind.CLASS,
                        name="@angular/core InjectFlags",
                        role=EntityRole.REMOVED,
                    ).model_dump(),
                    AffectedEntity(
                        kind=EntityKind.CLASS,
                        name="InjectFlags",
                        role=EntityRole.MENTIONED,
                    ).model_dump(),
                    AffectedEntity(
                        kind=EntityKind.PROPERTY, name="in", role=EntityRole.MENTIONED
                    ).model_dump(),
                ],
            }
        ]
    )


def _index() -> HopApiIndex:
    return build_hop_index(
        ("20.0.0", "20.1.0"), [{"@angular/core": {"InjectFlags": ["Static"]}}]
    )


def test_audit_jsonl_and_summary(tmp_path: Path) -> None:
    result = canonicalize_batch(
        _batch(),
        profile=profile_for("angular"),
        from_version="20.0.0",
        to_version="20.1.0",
        index=_index(),
    )
    jsonl_path = tmp_path / "canonical.jsonl"
    summary_path = tmp_path / "summary.json"
    write_canonical_audit(
        result,
        framework="angular",
        hop=("20.0.0", "20.1.0"),
        jsonl_path=jsonl_path,
        summary_path=summary_path,
    )

    lines = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 3
    assert lines[0]["ruleId"] == "InjectFlags removed"
    assert lines[0]["rawKind"] == "class"
    assert lines[0]["rawName"] == "@angular/core InjectFlags"
    assert lines[0]["canonical"]["key"] == "npm:@angular/core#InjectFlags"
    assert lines[0]["verified"] == "true"
    assert "split-package" in lines[0]["applied"]
    assert lines[2]["canonical"]["kind"] == "syntax"

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["framework"] == "angular"
    assert summary["occurrences"] == 3
    assert summary["counts_by_kind"] == {"class": 2, "syntax": 1}
    assert summary["verified_true"] == 3
    # InjectFlags appears twice (raw names collapse into one key)
    assert summary["raw_names_collapsed"] == 1
    assert summary["distinct_keys"] == 2
    assert summary["api_index"] == {
        "status": "ok",
        "versions": ["20.0.0", "20.1.0"],
        "missing_versions": [],
    }
    assert summary["verified_true_pct"] == 100.0


def test_summary_records_unavailable_api_index(tmp_path: Path) -> None:
    """AC-4: an unfetchable index keeps populate going and says so."""
    result = canonicalize_batch(
        _batch(),
        profile=profile_for("angular"),
        from_version="20.0.0",
        to_version="20.1.0",
        index=HopApiIndex.unavailable(("20.0.0", "20.1.0")),
    )
    jsonl_path = tmp_path / "canonical.jsonl"
    summary_path = tmp_path / "summary.json"
    write_canonical_audit(
        result,
        framework="angular",
        hop=("20.0.0", "20.1.0"),
        jsonl_path=jsonl_path,
        summary_path=summary_path,
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["api_index"]["status"] == "unavailable"
    assert summary["verified_true"] == 1  # only the syntax token
    assert summary["verified_false"] == 2
    # every unverified key is listed for manual review
    assert "npm:?#InjectFlags" in summary["unverified_keys"]


def test_unverified_keys_listed_for_manual_review(tmp_path: Path) -> None:
    result = canonicalize_batch(
        _batch(),
        profile=profile_for("angular"),
        from_version="20.0.0",
        to_version="20.1.0",
        index=build_hop_index(("20.0.0", "20.1.0"), [{"@angular/core": {}}]),
    )
    jsonl_path = tmp_path / "canonical.jsonl"
    summary_path = tmp_path / "summary.json"
    write_canonical_audit(
        result,
        framework="angular",
        hop=("20.0.0", "20.1.0"),
        jsonl_path=jsonl_path,
        summary_path=summary_path,
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert "npm:?#InjectFlags" in summary["unverified_keys"]
    assert summary["unverified_keys"]["npm:?#InjectFlags"] == ["InjectFlags removed"]


def test_spring_boot_runs_json_unchanged_with_maven_and_cfg_keys() -> None:
    """AC-5: every Spring Boot entities file keeps names byte-for-byte."""
    files = sorted(RUNS_JSON.glob("spring-boot-*-entities.json"))
    assert files, "spring-boot entities files are expected in runs/json/"
    for path in files:
        batch = MigrationEntitiesBatch.model_validate_json(path.read_text(encoding="utf-8"))
        result = canonicalize_batch(
            batch,
            profile=profile_for("spring-boot"),
            from_version="0",
            to_version="0",
        )
        for rule in result.rules:
            for occurrence in rule.occurrences:
                assert occurrence.name == occurrence.raw_name, (path, occurrence.raw_name)
                assert occurrence.verified == "unchecked"
                assert occurrence.key.startswith("maven:") or occurrence.key.startswith(
                    "cfg:application.properties#"
                ), (path, occurrence.key)
                # FR-4.4: class and property names never look like a
                # groupId:artifactId coordinate to the matching heuristic.
                if occurrence.kind in (EntityKind.CLASS, EntityKind.PROPERTY):
                    assert ":" not in occurrence.name, (path, occurrence.name)
        assert result.api_index_status == "not-applicable"

def test_index_fetch_uses_configured_github_token(monkeypatch, tmp_path: Path) -> None:
    """Populate passes no token; the configured GITHUB_TOKEN must be used."""
    from migration_oracle import config
    from migration_oracle.pipeline.canonical import run as run_module
    from migration_oracle.pipeline.canonical.api_index import HopApiIndex

    seen: dict = {}

    def fake_load(from_version, to_version, *, cache_dir, token="", **_kw):
        seen["token"] = token
        return HopApiIndex.unavailable((from_version, to_version))

    monkeypatch.setattr(config, "GITHUB_TOKEN", "ghp_configured")
    monkeypatch.setattr(run_module, "load_hop_index", fake_load)
    batch = MigrationEntitiesBatch(entities=[])
    canonicalize_batch(
        batch,
        profile=profile_for("angular"),
        from_version="20.0.0",
        to_version="20.1.0",
        cache_dir=tmp_path,
    )
    assert seen["token"] == "ghp_configured"
