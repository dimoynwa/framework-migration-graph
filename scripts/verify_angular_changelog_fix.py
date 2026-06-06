#!/usr/bin/env python3
"""Run verification protocol for specs/003b-fix-angular-enchansing."""

from __future__ import annotations

import asyncio
import re
import sys
from unittest.mock import AsyncMock, patch

import httpx

from migration_oracle import config
from migration_oracle.models.entities import DocumentedChange, ExtractionResult
from migration_oracle.pipeline.extractors.angular import (
    CHANGELOG_URL,
    AngularExtractor,
    _extract_changelog_section,
)


def level_0() -> None:
    print("=== Level 0 — Environment prerequisites ===")
    r = httpx.get(CHANGELOG_URL, timeout=15, verify=config.SSL_VERIFY)
    assert r.status_code == 200, f"0-A failed: status {r.status_code}"
    assert len(r.text) > 500_000, f"0-A failed: only {len(r.text)} chars"
    print("  0-A: CHANGELOG URL reachable ✓")

    changelog = r.text
    for version in ["19.0.0", "20.0.0", "21.0.0", "22.0.0"]:
        anchor = f'<a name="{version}"></a>'
        assert anchor in changelog, f"0-B failed: missing anchor for {version}"
    print("  0-B: all 4 anchors present ✓")

    headers = {"Accept": "application/vnd.github+json"}
    if config.GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {config.GITHUB_TOKEN}"
    for v in ["19.0.0", "20.0.0", "21.0.0", "22.0.0"]:
        resp = None
        for tag in [f"v{v}", v]:
            resp = httpx.get(
                f"https://api.github.com/repos/angular/angular/releases/tags/{tag}",
                timeout=15,
                headers=headers,
                verify=config.SSL_VERIFY,
            )
            if resp.status_code == 200:
                break
        assert resp is not None and resp.status_code == 200, (
            f"0-C failed for {v}: {resp.status_code if resp else 'no response'}"
        )
        tag_name = resp.json()["tag_name"]
        assert tag_name in {v, f"v{v}"}, f"0-C failed: unexpected tag {tag_name}"
    print("  0-C: all 4 GitHub releases exist ✓")


async def level_1(changelog: str) -> None:
    print("\n=== Level 1 — CHANGELOG section extraction ===")
    e = AngularExtractor()
    fetched = await e._get_changelog()
    assert fetched, "Failed to fetch changelog"

    for version, min_chars in [
        ("19.0.0", 30000),
        ("20.0.0", 30000),
        ("21.0.0", 25000),
        ("22.0.0", 20000),
    ]:
        section = _extract_changelog_section(fetched, version)
        assert section, f"1-A failed: empty section for {version}"
        assert len(section) >= min_chars, (
            f"1-A failed: {version} section too short ({len(section)} chars)"
        )
        print(f"  1-A: {version}: {len(section)} chars ✓")

    for version in ["19.0.0", "20.0.0", "21.0.0", "22.0.0"]:
        section = _extract_changelog_section(fetched, version)
        assert f'<a name="{version}"></a>' in section
        h2s = re.findall(r"^## (.+)$", section, re.MULTILINE)
        assert len(h2s) >= 1, f"1-B failed: {version} no H2 sections"
        assert any("Breaking" in h for h in h2s), (
            f"1-B failed: {version} no Breaking Changes H2"
        )
        print(f"  1-B: {version}: H2 sections = {h2s} ✓")

    for version in ["19.0.0", "20.0.0", "21.0.0"]:
        section = _extract_changelog_section(fetched, version)
        next_versions = {"19.0.0": "18", "20.0.0": "19", "21.0.0": "20"}
        bleed_check = f'<a name="{next_versions[version]}'
        assert bleed_check not in section, (
            f"1-C failed: {version} section bleeds into previous version"
        )
    print("  1-C: sections bounded ✓")


async def level_2() -> None:
    print("\n=== Level 2 — AW-1: source_url attribution ===")
    e = AngularExtractor()
    result = await e.extract("18.0.0", "19.0.0")

    changelog_entries = [c for c in result.changes if c.source_url == CHANGELOG_URL]
    gh_entries = [c for c in result.changes if c.source_url != CHANGELOG_URL]

    print(f"  GitHub-sourced entries:    {len(gh_entries)}")
    print(f"  CHANGELOG-sourced entries: {len(changelog_entries)}")

    assert len(changelog_entries) > 0, "2-A failed: no CHANGELOG_URL entries"
    assert len(gh_entries) > 0, "2-A failed: no GitHub entries"
    assert CHANGELOG_URL == (
        "https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md"
    )
    misattributed = [
        c for c in changelog_entries if "releases/tag" in c.source_url
    ]
    assert len(misattributed) == 0, (
        f"2-A failed: {len(misattributed)} CHANGELOG entries carry release URL"
    )
    print("  2-A: CHANGELOG entries carry CHANGELOG_URL ✓")

    for c in result.changes:
        assert c.source_url in {
            CHANGELOG_URL,
            "https://github.com/angular/angular/releases/tag/v19.0.0",
            "https://github.com/angular/angular/releases/tag/19.0.0",
        }, f"2-B failed: unexpected source_url: {c.source_url}"
    print("  2-B: all source_urls are expected values ✓")

    hops = [
        ("18.0.0", "19.0.0"),
        ("19.0.0", "20.0.0"),
        ("20.0.0", "21.0.0"),
        ("21.0.0", "22.0.0"),
    ]
    for from_v, to_v in hops:
        result = await e.extract(from_v, to_v)
        source_urls = {c.source_url for c in result.changes}
        assert CHANGELOG_URL in source_urls, (
            f"2-C failed: {from_v}→{to_v}: CHANGELOG_URL missing from {source_urls}"
        )
        assert 1 <= len(source_urls) <= 2, (
            f"2-C failed: {from_v}→{to_v}: expected 1-2 source_urls, "
            f"got {len(source_urls)}: {source_urls}"
        )
        print(f"  2-C: {from_v}→{to_v}: {len(source_urls)} source_url(s) ✓")


async def level_3() -> None:
    print("\n=== Level 3 — AW-2: deduplication ===")
    e = AngularExtractor()

    for from_v, to_v, _gh_baseline, max_total in [
        ("19.0.0", "20.0.0", 145, 170),
        ("20.0.0", "21.0.0", 110, 130),
        ("21.0.0", "22.0.0", 153, 180),
    ]:
        result = await e.extract(from_v, to_v)
        total = len(result.changes)
        assert total <= max_total, (
            f"3-A failed: {from_v}→{to_v}: {total} entries exceeds max {max_total}"
        )
        print(f"  3-A: {from_v}→{to_v}: {total} entries (≤{max_total}) ✓")

    result = await e.extract("18.0.0", "19.0.0")
    total = len(result.changes)
    assert total >= 200, (
        f"3-B failed: 18→19 only {total} entries, expected ≥ 200"
    )
    print(f"  3-B: 18→19: {total} entries (≥200) ✓")

    for from_v, to_v in [
        ("18.0.0", "19.0.0"),
        ("19.0.0", "20.0.0"),
        ("20.0.0", "21.0.0"),
        ("21.0.0", "22.0.0"),
    ]:
        result = await e.extract(from_v, to_v)
        statements = [c.statement for c in result.changes]
        dupes = [s for s in statements if statements.count(s) > 1]
        assert len(dupes) == 0, (
            f"3-C failed: {from_v}→{to_v}: {len(dupes) // 2} duplicate statements"
        )
        print(f"  3-C: {from_v}→{to_v}: no exact duplicates ✓")


async def level_4() -> None:
    print("\n=== Level 4 — Typed entry quality ===")
    e = AngularExtractor()
    expected_typed = {
        ("18.0.0", "19.0.0"): 20,
        ("19.0.0", "20.0.0"): 8,
        ("20.0.0", "21.0.0"): 10,
        ("21.0.0", "22.0.0"): 10,
    }
    for hop, min_typed in expected_typed.items():
        result = await e.extract(*hop)
        typed = [
            c
            for c in result.changes
            if c.type in ("breaking", "deprecation", "mandatory_migration")
        ]
        assert len(typed) >= min_typed, (
            f"4-A failed: {hop[0]}→{hop[1]}: only {len(typed)} typed entries, "
            f"expected ≥ {min_typed}"
        )
        print(f"  4-A: {hop[0]}→{hop[1]}: {len(typed)} typed entries (≥{min_typed}) ✓")

    result = await e.extract("18.0.0", "19.0.0")
    statements = [c.statement for c in result.changes]
    for substr in [
        "standalone by default",
        "TypeScript versions less than 5.5",
        "BrowserModule.withServerTransition",
    ]:
        matches = [s for s in statements if substr in s]
        assert matches, f"4-B failed: expected entry containing '{substr}'"
        print(f"  4-B: '{substr[:50]}': found ✓")

    result = await e.extract("19.0.0", "20.0.0")
    statements = [c.statement for c in result.changes]
    for substr in ["ngIf", "HammerJS", "ng-reflect"]:
        matches = [s for s in statements if substr in s]
        assert matches, f"4-C failed: expected entry containing '{substr}' in 19→20"
        print(f"  4-C: '{substr}': found ✓")


async def level_5() -> None:
    print("\n=== Level 5 — Regression ===")
    e = AngularExtractor()
    result = await e.extract("18.0.0", "19.0.0")

    assert isinstance(result, ExtractionResult)
    assert isinstance(result.changes, list)
    assert len(result.changes) > 0
    assert all(isinstance(c, DocumentedChange) for c in result.changes)
    assert "blog_insights" in result.metadata
    for insight in result.metadata["blog_insights"]:
        assert "url" in insight
        assert "summary" in insight
    print("  5-A: ExtractionResult structure ✓")

    for from_v, to_v in [
        ("18.0.0", "19.0.0"),
        ("19.0.0", "20.0.0"),
        ("20.0.0", "21.0.0"),
        ("21.0.0", "22.0.0"),
    ]:
        result = await e.extract(from_v, to_v)
        assert len(result.changes) > 0
        print(f"  5-B: {from_v}→{to_v}: {len(result.changes)} changes, no exception ✓")


async def edge_cases() -> None:
    print("\n=== Edge cases ===")
    e = AngularExtractor()

    result = await e.extract("22.0.0-rc.2", "22.0.0-rc.3")
    assert len(result.changes) > 0, "E-1 failed: expected GH-only fallback"
    source_urls = {c.source_url for c in result.changes}
    assert CHANGELOG_URL not in source_urls
    print(
        f"  E-1: 22.0.0-rc.2→22.0.0-rc.3: {len(result.changes)} GH-only entries ✓"
    )

    with patch.object(e, "_get_changelog", new_callable=AsyncMock, return_value=""):
        result = await e.extract("18.0.0", "19.0.0")
        assert len(result.changes) > 0, "E-2 failed: should fall back to GH body"
        source_urls = {c.source_url for c in result.changes}
        assert CHANGELOG_URL not in source_urls
        print(f"  E-2: CHANGELOG failure fallback: {len(result.changes)} changes ✓")


async def main() -> None:
    level_0()
    e = AngularExtractor()
    changelog = await e._get_changelog()
    await level_1(changelog)
    await level_2()
    await level_3()
    await level_4()
    await level_5()
    await edge_cases()
    print("\n=== ALL CHECKS PASSED ===")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except AssertionError as exc:
        print(f"\nFAILED: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"\nERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
