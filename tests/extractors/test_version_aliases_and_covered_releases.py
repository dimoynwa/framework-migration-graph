"""Version aliases (latest / SNAPSHOT), minor-hop release coverage, stale raw detection."""

from __future__ import annotations

from pathlib import Path

import pytest
import respx
from httpx import Response

from migration_oracle.cli import _raw_is_stale
from migration_oracle.pipeline.extractors.base import HopContext
from migration_oracle.pipeline.extractors.parsing import (
    is_version_alias,
    releases_covered_by_hop,
    resolve_version_alias,
)
from migration_oracle.pipeline.extractors.spring_boot import SpringBootExtractor

VERSIONS = [
    "4.0.0", "4.0.1", "4.0.9",
    "4.1.0-M1", "4.1.0-RC1", "4.1.0", "4.1.1", "4.1.2",
    "4.2.0-M1", "4.2.0-RC2",
]


@pytest.mark.parametrize(
    ("alias", "expected"),
    [
        ("latest", "4.2.0-RC2"),
        ("LATEST", "4.2.0-RC2"),
        ("latest-ga", "4.1.2"),
        ("4.2.0-SNAPSHOT", "4.2.0-RC2"),
        ("4.1.0-SNAPSHOT", "4.1.0"),
        ("4.1.2", "4.1.2"),
        ("4.1.0-RC1", "4.1.0-RC1"),
    ],
)
def test_resolve_version_alias(alias: str, expected: str) -> None:
    assert resolve_version_alias(VERSIONS, alias) == expected


def test_snapshot_without_published_build_is_explained() -> None:
    with pytest.raises(ValueError, match="no milestone, RC, or GA build of 4.3.0"):
        resolve_version_alias(VERSIONS, "4.3.0-SNAPSHOT")


def test_is_version_alias() -> None:
    assert is_version_alias("latest")
    assert is_version_alias("4.2.0-SNAPSHOT")
    assert not is_version_alias("4.2.0-RC2")
    assert not is_version_alias("4.1.2")


def test_minor_hop_covers_target_line_milestones_not_old_patches() -> None:
    assert releases_covered_by_hop(VERSIONS, "4.0.0", "4.1.0") == (
        "4.1.0-M1", "4.1.0-RC1", "4.1.0",
    )
    assert releases_covered_by_hop(VERSIONS, "4.1.0", "4.1.2") == ("4.1.1", "4.1.2")
    assert releases_covered_by_hop(VERSIONS, "4.1.2", "4.2.0-RC2") == (
        "4.2.0-M1", "4.2.0-RC2",
    )
    assert releases_covered_by_hop(VERSIONS, "4.1.1", "4.1.2") == ("4.1.2",)


def _release(body: str, version: str) -> dict:
    return {
        "body": body,
        "html_url": f"https://github.com/spring-projects/spring-boot/releases/tag/v{version}",
    }


@pytest.mark.asyncio
@respx.mock
async def test_minor_hop_reads_every_covered_release() -> None:
    api = "https://api.github.com/repos/spring-projects/spring-boot/releases/tags/"
    respx.get(f"{api}v4.1.0-M1").mock(
        return_value=Response(200, json=_release("## Breaking Changes\n- Removed Foo API\n", "4.1.0-M1"))
    )
    # RC1 has no release (API 404 and HTML 404) — must be skipped, not fatal.
    respx.get(f"{api}v4.1.0-RC1").mock(return_value=Response(404))
    respx.get(f"{api}4.1.0-RC1").mock(return_value=Response(404))
    respx.get(url__startswith="https://github.com/spring-projects/spring-boot/releases/tag/").mock(
        return_value=Response(404)
    )
    respx.get(f"{api}v4.1.0").mock(
        return_value=Response(
            200,
            json=_release("## Bug Fixes\n- Fixed a startup failure\n- Removed Foo API\n", "4.1.0"),
        )
    )
    respx.get(
        "https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.1-Release-Notes"
    ).mock(return_value=Response(404))

    context = HopContext(
        "4.0.0", "4.1.0", "minor", covered_versions=("4.1.0-M1", "4.1.0-RC1", "4.1.0")
    )
    async with SpringBootExtractor() as extractor:
        result = await extractor.extract("4.0.0", "4.1.0", hop_context=context)

    statements = [change.statement for change in result.changes]
    assert statements.count("Removed Foo API") == 1
    assert "Fixed a startup failure" in statements


def _raw(range_from: str, range_to: str, hops: list[tuple[str, str]]) -> str:
    lines = [
        "# Spring Boot — documented changes (extract-only)",
        "",
        "- **Framework key:** `spring-boot`",
        f"- **Resolved range:** `{range_from}` → `{range_to}`",
        "",
        "---",
        "",
    ]
    for hop_from, hop_to in hops:
        lines += [
            f"## `{hop_from}` → `{hop_to}`",
            "",
            "| Type | Confidence | Source | Statement |",
            "|------|------------|--------|-----------|",
            "| breaking | confirmed | https://x | Removed Foo |",
            "",
        ]
    return "\n".join(lines)


def test_raw_is_stale(tmp_path: Path) -> None:
    path = tmp_path / "spring-boot-4.0.0-to-4.1.0-changes.md"
    assert not _raw_is_stale(path, "4.0.0", "4.1.0")

    path.write_text(_raw("4.0.0", "4.1.0", [("4.0.0", "4.1.0")]), encoding="utf-8")
    assert not _raw_is_stale(path, "4.0.0", "4.1.0")

    path.write_text(
        _raw("4.0.0", "4.1.0-RC1", [("4.0.0-M1", "4.0.0-M2"), ("4.1.0-M3", "4.1.0-RC1")]),
        encoding="utf-8",
    )
    assert _raw_is_stale(path, "4.0.0", "4.1.0")
