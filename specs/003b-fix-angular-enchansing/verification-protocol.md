# Verification Protocol — Angular CHANGELOG Enhancement Fix

**Spec:** `specs/003b-fix-angular-enchansing/spec.md`
**Fixes verified:** AW-1 (separate `source_url`), AW-2 (deduplication)

---

## Scope

Four major-version hops in scope for Paysafe's Angular migration path:

| Hop | From | To | CHANGELOG H2 sections | CHANGELOG chars |
|-----|------|----|-----------------------|---------------:|
| A   | 18.0.0 | 19.0.0 | `Breaking Changes` | 35,411 |
| B   | 19.0.0 | 20.0.0 | `Breaking Changes`, `Deprecations` | 37,248 |
| C   | 20.0.0 | 21.0.0 | `Breaking Changes`, `Deprecations` | 30,983 |
| D   | 21.0.0 | 22.0.0 | `Breaking Changes`, `Deprecations` | 25,788 |

---

## Ground Truth Table

Live-measured baselines to verify against after the fix is applied:

| Hop | GH body (unique) | CHANGELOG | Expected total after dedup | Min typed (breaking + deprecation + mandatory_migration) |
|-----|-----------------|-----------|---------------------------|----------------------------------------------------------|
| A (→19.0.0) | 135 | 122 | ≥ 200 | ≥ 20 |
| B (→20.0.0) | 145 | 145 | ≥ 130, ≤ 170 | ≥ 8 |
| C (→21.0.0) | 110 | 111 | ≥ 100, ≤ 130 | ≥ 10 |
| D (→22.0.0) | 153 | 154 | ≥ 140, ≤ 180 | ≥ 10 |

> Ranges for B–D are wide because near-full deduplication is expected (GH body embeds CHANGELOG),
> and minor variation from classifier non-determinism is normal.

---

## Level 0 — Environment prerequisites

**0-A. CHANGELOG URL is reachable and non-empty**

```python
import httpx
r = httpx.get("https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md", timeout=15)
assert r.status_code == 200
assert len(r.text) > 500_000  # full CHANGELOG is ~600k+ chars
```

**0-B. All four target version anchors exist in CHANGELOG**

```python
changelog = r.text
for version in ["19.0.0", "20.0.0", "21.0.0", "22.0.0"]:
    anchor = f'<a name="{version}"></a>'
    assert anchor in changelog, f"Missing anchor for {version}"
```

**0-C. GitHub releases exist for all four target versions**

```bash
for v in 19.0.0 20.0.0 21.0.0 22.0.0; do
    curl -sf "https://api.github.com/repos/angular/angular/releases/tags/v${v}" \
         -H "Authorization: Bearer $GITHUB_TOKEN" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['tag_name'])"
done
```

Expected: `v19.0.0`, `v20.0.0`, `v21.0.0`, `v22.0.0` — one per line, no errors.

---

## Level 1 — CHANGELOG section extraction

**1-A. `_extract_changelog_section` returns non-empty for all four versions**

```python
import asyncio
from migration_oracle.pipeline.extractors.angular import AngularExtractor, _extract_changelog_section

async def check():
    e = AngularExtractor()
    changelog = await e._get_changelog()
    for version, min_chars in [("19.0.0", 30000), ("20.0.0", 30000), ("21.0.0", 25000), ("22.0.0", 20000)]:
        section = _extract_changelog_section(changelog, version)
        assert section, f"Empty section for {version}"
        assert len(section) >= min_chars, f"{version}: section too short ({len(section)} chars)"
        print(f"  {version}: {len(section)} chars ✓")

asyncio.run(check())
```

**1-B. Each section contains the correct anchor and at least one H2**

```python
import re

for version in ["19.0.0", "20.0.0", "21.0.0", "22.0.0"]:
    section = _extract_changelog_section(changelog, version)
    assert f'<a name="{version}"></a>' in section
    h2s = re.findall(r'^## (.+)$', section, re.MULTILINE)
    assert len(h2s) >= 1, f"{version}: no H2 sections found"
    assert any("Breaking" in h for h in h2s), f"{version}: no Breaking Changes H2"
    print(f"  {version}: H2 sections = {h2s} ✓")
```

Expected H2 sections per version:
- `19.0.0`: `['Breaking Changes']`
- `20.0.0`: `['Breaking Changes', 'Deprecations']`
- `21.0.0`: `['Breaking Changes', 'Deprecations']`
- `22.0.0`: `['Breaking Changes', 'Deprecations']` (or similar)

**1-C. Section is bounded — does not bleed into the next version**

```python
for version in ["19.0.0", "20.0.0", "21.0.0"]:
    section = _extract_changelog_section(changelog, version)
    next_versions = {"19.0.0": "18", "20.0.0": "19", "21.0.0": "20"}
    bleed_check = f'<a name="{next_versions[version]}'
    assert bleed_check not in section, f"{version}: section bleeds into previous version"
```

---

## Level 2 — AW-1: `source_url` attribution (centrepiece)

These checks verify the primary fix. Run against the **patched** `angular.py`.

**2-A. CHANGELOG entries carry `CHANGELOG_URL` as `source_url`**

```python
import asyncio
from migration_oracle.pipeline.extractors.angular import AngularExtractor, CHANGELOG_URL

async def check_source_urls():
    e = AngularExtractor()
    result = await e.extract("18.0.0", "19.0.0")

    gh_url = next(c.source_url for c in result.changes)  # first entry should be GitHub
    changelog_entries = [c for c in result.changes if c.source_url == CHANGELOG_URL]
    gh_entries = [c for c in result.changes if c.source_url != CHANGELOG_URL]

    print(f"  GitHub-sourced entries:    {len(gh_entries)}")
    print(f"  CHANGELOG-sourced entries: {len(changelog_entries)}")

    assert len(changelog_entries) > 0, "No entries carry CHANGELOG_URL — AW-1 not applied"
    assert len(gh_entries) > 0, "No GitHub entries found"

    # Confirm CHANGELOG_URL is correct
    assert CHANGELOG_URL == "https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md"

    # Confirm no CHANGELOG entry carries the release tag URL
    release_url_pattern = "releases/tag"
    misattributed = [c for c in changelog_entries if release_url_pattern in c.source_url]
    assert len(misattributed) == 0, f"{len(misattributed)} CHANGELOG entries still carry release URL"
    print("  source_url attribution ✓")

asyncio.run(check_source_urls())
```

**2-B. GitHub release entries carry the release tag URL, not CHANGELOG_URL**

```python
async def check_gh_source_urls():
    e = AngularExtractor()
    result = await e.extract("18.0.0", "19.0.0")

    misattributed = [c for c in result.changes
                     if CHANGELOG_URL in c.source_url
                     and "releases/tag" not in c.source_url]
    # This check is implicitly satisfied by 2-A, but verify explicitly:
    for c in result.changes:
        assert c.source_url in {
            CHANGELOG_URL,
            "https://github.com/angular/angular/releases/tag/v19.0.0",
            "https://github.com/angular/angular/releases/tag/19.0.0",
        }, f"Unexpected source_url: {c.source_url}"
    print("  All source_urls are one of the two expected values ✓")

asyncio.run(check_gh_source_urls())
```

**2-C. Distinct `source_url` values appear for ALL four hops**

```python
async def check_all_hops_provenance():
    e = AngularExtractor()
    hops = [
        ("18.0.0", "19.0.0"),
        ("19.0.0", "20.0.0"),
        ("20.0.0", "21.0.0"),
        ("21.0.0", "22.0.0"),
    ]
    for from_v, to_v in hops:
        result = await e.extract(from_v, to_v)
        source_urls = {c.source_url for c in result.changes}
        assert len(source_urls) == 2, (
            f"{from_v}→{to_v}: expected 2 distinct source_urls, got {len(source_urls)}: {source_urls}"
        )
        assert CHANGELOG_URL in source_urls
        print(f"  {from_v}→{to_v}: 2 source_urls ✓")

asyncio.run(check_all_hops_provenance())
```

---

## Level 3 — AW-2: deduplication

**3-A. v20, v21, v22 hops do not double the entry count**

```python
async def check_dedup():
    e = AngularExtractor()
    # For hops where GH body == CHANGELOG content, total should be ~1x, not ~2x
    for from_v, to_v, gh_baseline, max_total in [
        ("19.0.0", "20.0.0", 145, 170),
        ("20.0.0", "21.0.0", 110, 130),
        ("21.0.0", "22.0.0", 153, 180),
    ]:
        result = await e.extract(from_v, to_v)
        total = len(result.changes)
        assert total <= max_total, (
            f"{from_v}→{to_v}: {total} entries — exceeds max {max_total}; "
            f"deduplication (AW-2) likely not applied"
        )
        print(f"  {from_v}→{to_v}: {total} entries (≤{max_total}) ✓")

asyncio.run(check_dedup())
```

**3-B. v18→v19 hop retains both sources (no over-deduplication)**

```python
async def check_no_over_dedup():
    e = AngularExtractor()
    result = await e.extract("18.0.0", "19.0.0")
    total = len(result.changes)
    # GH=135, CL=122, low overlap → expect ≥ 200
    assert total >= 200, (
        f"18→19: only {total} entries — expected ≥ 200; over-deduplication or CHANGELOG not applied"
    )
    print(f"  18→19: {total} entries (≥200) ✓")

asyncio.run(check_no_over_dedup())
```

**3-C. No identical statement appears twice in any result**

```python
async def check_no_exact_dupes():
    e = AngularExtractor()
    for from_v, to_v in [("18.0.0","19.0.0"),("19.0.0","20.0.0"),("20.0.0","21.0.0"),("21.0.0","22.0.0")]:
        result = await e.extract(from_v, to_v)
        statements = [c.statement for c in result.changes]
        dupes = [s for s in statements if statements.count(s) > 1]
        assert len(dupes) == 0, f"{from_v}→{to_v}: {len(dupes)//2} duplicate statements found"
        print(f"  {from_v}→{to_v}: no exact duplicates ✓")

asyncio.run(check_no_exact_dupes())
```

---

## Level 4 — Typed entry quality

**4-A. `deprecation/confirmed` entries present for all hops**

```python
async def check_typed_entries():
    e = AngularExtractor()
    expected_typed = {
        ("18.0.0", "19.0.0"): 20,  # 31 typed from GH body alone in baseline
        ("19.0.0", "20.0.0"): 8,
        ("20.0.0", "21.0.0"): 10,
        ("21.0.0", "22.0.0"): 10,
    }
    for hop, min_typed in expected_typed.items():
        result = await e.extract(*hop)
        typed = [c for c in result.changes
                 if c.type in ("breaking", "deprecation", "mandatory_migration")]
        assert len(typed) >= min_typed, (
            f"{hop[0]}→{hop[1]}: only {len(typed)} typed entries, expected ≥ {min_typed}"
        )
        print(f"  {hop[0]}→{hop[1]}: {len(typed)} typed entries (≥{min_typed}) ✓")

asyncio.run(check_typed_entries())
```

**4-B. Representative known deprecation entries present for 18→19**

The following entries must appear in the 18→19 result (CHANGELOG `## Breaking Changes` section,
H3 `core` and other packages). Each is confirmed by live CHANGELOG inspection:

```python
async def check_known_entries():
    e = AngularExtractor()
    result = await e.extract("18.0.0", "19.0.0")
    statements = [c.statement for c in result.changes]

    known_substrings = [
        "standalone by default",          # core: standalone default change
        "TypeScript versions less than 5.5",  # core: TS version drop
        "BrowserModule.withServerTransition",  # deprecation removal
    ]
    for substr in known_substrings:
        matches = [s for s in statements if substr in s]
        assert matches, f"Expected entry containing '{substr}' not found"
        print(f"  '{substr[:50]}': found ✓")

asyncio.run(check_known_entries())
```

**4-C. Representative known deprecation entries present for 19→20**

```python
async def check_known_entries_v20():
    e = AngularExtractor()
    result = await e.extract("19.0.0", "20.0.0")
    statements = [c.statement for c in result.changes]

    known_substrings = [
        "ngIf",               # ngIf/ngFor/ngSwitch deprecated for control flow
        "HammerJS",           # HammerJS deprecated
        "ng-reflect",         # ng-reflect-* attributes deprecated
    ]
    for substr in known_substrings:
        matches = [s for s in statements if substr in s]
        assert matches, f"Expected entry containing '{substr}' not found in 19→20"
        print(f"  '{substr}': found ✓")

asyncio.run(check_known_entries_v20())
```

---

## Level 5 — Regression: existing behaviour unchanged

**5-A. `ExtractionResult` structure is unchanged**

```python
from migration_oracle.models.entities import ExtractionResult, DocumentedChange

async def check_result_structure():
    e = AngularExtractor()
    result = await e.extract("18.0.0", "19.0.0")

    assert isinstance(result, ExtractionResult)
    assert isinstance(result.changes, list)
    assert len(result.changes) > 0
    assert all(isinstance(c, DocumentedChange) for c in result.changes)
    assert "blog_insights" in result.metadata
    # Blog insights: URL captured, summary may be empty (JS SPA limitation)
    for insight in result.metadata["blog_insights"]:
        assert "url" in insight
        assert "summary" in insight
    print("  ExtractionResult structure ✓")

asyncio.run(check_result_structure())
```

**5-B. No exception raised for any in-scope hop**

```python
async def check_no_exceptions():
    e = AngularExtractor()
    for from_v, to_v in [
        ("18.0.0", "19.0.0"),
        ("19.0.0", "20.0.0"),
        ("20.0.0", "21.0.0"),
        ("21.0.0", "22.0.0"),
    ]:
        try:
            result = await e.extract(from_v, to_v)
            assert len(result.changes) > 0
            print(f"  {from_v}→{to_v}: {len(result.changes)} changes, no exception ✓")
        except Exception as exc:
            raise AssertionError(f"{from_v}→{to_v} raised {type(exc).__name__}: {exc}")

asyncio.run(check_no_exceptions())
```

**5-C. CLI extraction produces output files for all four hops**

```bash
export $(grep -v '^#' .env | xargs)
for hop in "18.0.0 19.0.0" "19.0.0 20.0.0" "20.0.0 21.0.0" "21.0.0 22.0.0"; do
    set -- $hop
    uv run migration-oracle export-extract-populate-framework \
        --framework angular --extract-only --force-extract "$1" "$2"
done

# Verify output files exist
ls runs/raw/angular-*.md
```

Expected: four files, one per hop, each non-empty.

---

## Edge cases

**E-1. CHANGELOG section not found for an unknown version**

`_extract_changelog_section` returns `""` when the anchor does not exist. In this case
`extract()` must fall back to GitHub body only — no exception, non-empty result:

```python
async def check_missing_anchor():
    e = AngularExtractor()
    # Use a version that exists on GitHub but has no CHANGELOG anchor
    # (patch releases are not anchored individually in the CHANGELOG)
    result = await e.extract("18.0.0", "18.0.1")
    assert len(result.changes) > 0, "18→18.0.1: expected GH-only fallback, got empty result"
    source_urls = {c.source_url for c in result.changes}
    assert CHANGELOG_URL not in source_urls, "Patch hop should have no CHANGELOG entries"
    print(f"  18.0.0→18.0.1: {len(result.changes)} GH-only entries, CHANGELOG absent ✓")

asyncio.run(check_missing_anchor())
```

**E-2. CHANGELOG fetch failure degrades gracefully**

```python
from unittest.mock import AsyncMock, patch

async def check_changelog_fetch_failure():
    e = AngularExtractor()
    with patch.object(e, "_get_changelog", new_callable=AsyncMock, return_value=""):
        result = await e.extract("18.0.0", "19.0.0")
        assert len(result.changes) > 0, "Should fall back to GH body when CHANGELOG unavailable"
        source_urls = {c.source_url for c in result.changes}
        assert CHANGELOG_URL not in source_urls
        print(f"  CHANGELOG failure fallback: {len(result.changes)} changes from GH body ✓")

asyncio.run(check_changelog_fetch_failure())
```

---

## Pass criteria

| Level | Check | Pass condition |
|-------|-------|----------------|
| 0-A | CHANGELOG URL reachable | HTTP 200, >500k chars |
| 0-B | All 4 anchors in CHANGELOG | No assertion errors |
| 0-C | All 4 GitHub releases exist | 4 tag names returned |
| 1-A | CHANGELOG sections non-empty | All 4 sections ≥ min chars |
| 1-B | H2 sections present per version | `Breaking Changes` in all 4 |
| 1-C | Sections bounded | No bleed-through |
| **2-A** | CHANGELOG entries carry `CHANGELOG_URL` | ≥1 entry with CHANGELOG_URL, 0 misattributed |
| **2-B** | GH entries carry release tag URL | No unexpected source_urls |
| **2-C** | Both source_urls present in all 4 hops | Exactly 2 distinct source_urls each |
| **3-A** | v20–v22 not doubled | Total ≤ max per hop |
| **3-B** | v18→19 not over-deduplicated | Total ≥ 200 |
| **3-C** | No exact-duplicate statements | 0 duplicates in any hop |
| 4-A | Typed entries meet minimums | ≥ threshold per hop |
| 4-B | Known 18→19 entries present | All substrings found |
| 4-C | Known 19→20 entries present | All substrings found |
| 5-A | ExtractionResult structure intact | No attribute errors |
| 5-B | No exceptions for any in-scope hop | 4/4 complete |
| 5-C | CLI output files produced | 4 files, non-empty |
| E-1 | Patch version degrades to GH-only | No CHANGELOG entries, no exception |
| E-2 | CHANGELOG fetch failure handled | GH-only fallback, no exception |

Bold rows (2-A, 2-B, 2-C, 3-A, 3-B, 3-C) are the core validation for AW-1 and AW-2.
All 19 checks must pass for the implementation to be considered correct.
