#!/usr/bin/env python3
"""Run verification protocol for specs/003b-fix-spring-wiki-enchansing."""

from __future__ import annotations

import asyncio
import inspect
import sys
import textwrap
import unittest.mock as mock

from bs4 import BeautifulSoup

from migration_oracle.models.entities import DocumentedChange
from migration_oracle.pipeline.extractors.base import is_spring_boot_ga_version
from migration_oracle.pipeline.extractors.parsing import (
    parse_maven_metadata_versions,
    parse_version,
)
from migration_oracle.pipeline.extractors.spring_boot import (
    SpringBootExtractor,
    parse_github_release_text,
    parse_wiki_upgrade_section,
)

PASS = 0
FAIL = 0


def check(name: str, fn) -> None:
    global PASS, FAIL
    try:
        fn()
        print(f"✓ {name}")
        PASS += 1
    except Exception as exc:
        print(f"✗ {name}: {exc}")
        FAIL += 1


def level_0() -> None:
    print("\n=== Level 0 — Static checks ===")

    def _0a():
        assert hasattr(SpringBootExtractor, "_fetch_wiki_release_notes")
        sig = inspect.signature(SpringBootExtractor._fetch_wiki_release_notes)
        assert "to_version" in sig.parameters

    check("0-A _fetch_wiki_release_notes present", _0a)

    def _0b():
        src = textwrap.dedent(
            inspect.getsource(SpringBootExtractor._fetch_wiki_release_notes)
        )
        has_tuple_return = (
            "tuple[str" in src
            or "Tuple[str" in src
            or "return wiki_text," in src
            or 'return "", []' in src
            or "return '', []" in src
        )
        assert has_tuple_return

    check("0-B tuple return type", _0b)

    def _0c():
        src = inspect.getsource(SpringBootExtractor._fetch_wiki_release_notes)
        assert "#wiki-body .markdown-body" in src
        assert "BeautifulSoup" in src or "select_one" in src

    check("0-C BeautifulSoup selector", _0c)

    def _0d():
        import ast

        src = textwrap.dedent(
            inspect.getsource(SpringBootExtractor._fetch_wiki_release_notes)
        )
        tree = ast.parse(src)
        calls = [
            (
                node.func.attr
                if isinstance(node.func, ast.Attribute)
                else node.func.id if isinstance(node.func, ast.Name) else ""
            )
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
        ]
        assert "_strip_dependency_upgrades" in calls

    check("0-D _strip_dependency_upgrades called", _0d)

    def _0e():
        sig = inspect.signature(parse_wiki_upgrade_section)
        params = list(sig.parameters.keys())
        assert "wiki_text" in params and "source_url" in params

    check("0-E parse_wiki_upgrade_section importable", _0e)

    def _0f():
        src = inspect.getsource(SpringBootExtractor.extract)
        assert 'body + "\\n\\n" + wiki' not in src
        assert "body + '\\n\\n' + wiki" not in src
        assert "wiki_url" in src

    check("0-F extract() separate parsing", _0f)

    def _0g():
        ALL_VERSIONS = [
            "3.3.0", "3.3.1", "3.3.2", "3.3.3", "3.3.4", "3.3.5", "3.3.6", "3.3.7",
            "3.3.8", "3.3.9", "3.3.10", "3.3.11", "3.3.12", "3.3.13",
            "3.4.0", "3.4.1", "3.4.2", "3.4.3", "3.4.4", "3.4.5", "3.4.6", "3.4.7",
            "3.4.8", "3.4.9", "3.4.10", "3.4.11", "3.4.12", "3.4.13",
            "3.5.0", "3.5.1", "3.5.2", "3.5.3", "3.5.4", "3.5.5", "3.5.6", "3.5.7",
            "3.5.8", "3.5.9", "3.5.10", "3.5.11", "3.5.12", "3.5.13", "3.5.14",
            "4.0.0", "4.0.1", "4.0.2", "4.0.3", "4.0.4", "4.0.5", "4.0.6",
            "4.1.0-RC1",
        ]
        EXPECTED_SLUGS = {
            "3.3": "Spring-Boot-3.3-Release-Notes",
            "3.4": "Spring-Boot-3.4-Release-Notes",
            "3.5": "Spring-Boot-3.5-Release-Notes",
            "4.0": "Spring-Boot-4.0-Release-Notes",
            "4.1": "Spring-Boot-4.1-Release-Notes",
        }
        _WIKI_URL_TEMPLATE = (
            "https://github.com/spring-projects/spring-boot/wiki/"
            "Spring-Boot-{major}.{minor}-Release-Notes"
        )
        for v in ALL_VERSIONS:
            major, minor, _, _ = parse_version(v)
            derived_url = _WIKI_URL_TEMPLATE.format(major=major, minor=minor)
            expected_slug = EXPECTED_SLUGS.get(f"{major}.{minor}")
            assert expected_slug and derived_url.endswith(expected_slug)

    check("0-G slug derivation", _0g)


def level_1() -> None:
    print("\n=== Level 1 — Interface structure ===")

    SAMPLE = """\
## Upgrading from Spring Boot 3.4
### Actuator heapdump Endpoint
The heapdump actuator endpoint now defaults to access=NONE. If you want to use it,
you now need to both expose it and configure access.
### Validation of Profile Naming
Rules for profile naming have been tightened. Profiles can now only contain dash,
underscore, letters and digits.
## New and Noteworthy
### New Feature One
New feature description — must NOT appear in results.
"""

    def _1a():
        changes = parse_wiki_upgrade_section(SAMPLE, "https://wiki.example.com/3.5")
        assert len(changes) == 2
        assert all(isinstance(c, DocumentedChange) for c in changes)
        assert "heapdump" in changes[0].statement.lower() or "Actuator" in changes[0].statement
        assert not any("New Feature" in c.statement for c in changes)

    check("1-A H3-scoped changes", _1a)

    def _1b():
        WIKI_40_STYLE = """\
## Upgrading from Spring Boot 3.5
Since this is a major release, we've put together a dedicated migration guide.
If you're running an earlier version, upgrade to 3.5 first.
## New and Noteworthy
### Gradle 9
Gradle 9 is now supported.
"""
        assert parse_wiki_upgrade_section(WIKI_40_STYLE, "https://wiki.example.com/4.0") == []

    check("1-B no H3s returns []", _1b)

    def _1c():
        WIKI_41_STYLE = """\
Full release notes will be available when 4.1 has been released.
For now you can check out the release notes for the individual milestones:
- v4.1.0-RC1
- v4.1.0-M4
"""
        assert parse_wiki_upgrade_section(WIKI_41_STYLE, "https://wiki.example.com/4.1") == []

    check("1-C placeholder returns []", _1c)

    def _1d():
        WIKI_URL = (
            "https://github.com/spring-projects/spring-boot/wiki/"
            "Spring-Boot-3.5-Release-Notes"
        )
        SAMPLE2 = """\
## Upgrading from Spring Boot 3.4
### Redis Configuration Change
When spring.data.redis.url is configured, the database is determined by the URL.
"""
        changes = parse_wiki_upgrade_section(SAMPLE2, WIKI_URL)
        assert len(changes) == 1
        assert changes[0].source_url == WIKI_URL

    check("1-D wiki URL on prose changes", _1d)


def level_2() -> None:
    print("\n=== Level 2 — Isolation behaviour ===")

    def _2a():
        extractor = SpringBootExtractor.__new__(SpringBootExtractor)
        with mock.patch.object(
            extractor.__class__,
            "fetch",
            side_effect=RuntimeError("Spring Boot HTTP 404 for https://github.com/..."),
        ):
            result = asyncio.run(extractor._fetch_wiki_release_notes("3.5.0"))
        assert result == ("", [])

    check("2-A failure returns ('', [])", _2a)

    def _2b():
        extractor = SpringBootExtractor.__new__(SpringBootExtractor)
        MOCK_HTML = """
<html><body>
<nav>Why GitHub Documentation Blog Premium Support Enterprise-grade 24/7 support</nav>
<div id="wiki-body"><div class="markdown-body">
  <h2>Upgrading from Spring Boot 3.4</h2>
  <h3>Redis Configuration Change</h3>
  <p>When spring.data.redis.url is configured, the database is determined by the URL.</p>
  <h2>New and Noteworthy</h2>
  <ul><li>New feature: annotation support added.</li></ul>
</div></div>
<footer>GitHub Copilot Write better code with AI MCP Registry Integrate external tools
Uh oh! There was an error while loading. Please reload this page.</footer>
</body></html>
"""
        with mock.patch.object(extractor.__class__, "fetch", return_value=MOCK_HTML):
            wiki_text, prose_changes = asyncio.run(
                extractor._fetch_wiki_release_notes("3.5.0")
            )
        for noise in (
            "Why GitHub",
            "GitHub Copilot",
            "Uh oh",
            "Enterprise-grade",
            "MCP Registry",
        ):
            assert noise not in wiki_text
        assert "Redis" in wiki_text or "annotation support" in wiki_text
        assert len(prose_changes) >= 1 and "Redis" in prose_changes[0].statement

    check("2-B noise eliminated", _2b)

    def _2c():
        extractor = SpringBootExtractor.__new__(SpringBootExtractor)
        MOCK_HTML = """<html><body><div id="wiki-body"><div class="markdown-body">
## Upgrading from Spring Boot 3.4
### Redis Configuration Change
Database determined by URL.
## Dependency Upgrades
- HikariCP 6.3
- Kafka 3.9
- Testcontainers 1.21
## New and Noteworthy
- New feature added.
</div></div></body></html>"""
        with mock.patch.object(extractor.__class__, "fetch", return_value=MOCK_HTML):
            wiki_text, _ = asyncio.run(extractor._fetch_wiki_release_notes("3.5.0"))
        for lib in ("HikariCP", "Kafka", "Testcontainers"):
            assert lib not in wiki_text
        assert "New feature" in wiki_text or "Redis" in wiki_text

    check("2-C dep upgrades stripped", _2c)

    def _2d():
        extractor = SpringBootExtractor.__new__(SpringBootExtractor)
        RELEASE_URL = "https://github.com/spring-projects/spring-boot/releases/tag/v3.5.0"
        WIKI_URL = (
            "https://github.com/spring-projects/spring-boot/wiki/"
            "Spring-Boot-3.5-Release-Notes"
        )
        with mock.patch.object(
            extractor.__class__,
            "fetch_github_release",
            return_value=(RELEASE_URL, "- Fix NPE [#45000](https://github.com/x)\n"),
        ), mock.patch.object(
            extractor.__class__,
            "_fetch_wiki_release_notes",
            return_value=("- Wiki bullet change\n", []),
        ):
            result = asyncio.run(extractor.extract("3.4.0", "3.5.0"))
        source_urls = {c.source_url for c in result.changes}
        assert RELEASE_URL in source_urls
        assert WIKI_URL in source_urls

    check("2-D distinct source URLs", _2d)

    def _2e():
        extractor = SpringBootExtractor.__new__(SpringBootExtractor)
        with mock.patch.object(
            extractor.__class__,
            "_fetch_wiki_release_notes",
            return_value=("", []),
        ), mock.patch.object(
            extractor.__class__,
            "fetch_github_release",
            return_value=(
                "https://github.com/spring-projects/spring-boot/releases/tag/v3.5.0",
                "- Fix issue A [#45000](https://github.com/x)\n",
            ),
        ):
            result = asyncio.run(extractor.extract("3.4.0", "3.5.0"))
        assert result is not None and len(result.changes) >= 1

    check("2-E wiki failure does not abort", _2e)

    def _2f():
        extractor = SpringBootExtractor.__new__(SpringBootExtractor)
        PLACEHOLDER_HTML = """<html><body><div id="wiki-body"><div class="markdown-body">
Full release notes will be available when 4.1 has been released.
For now you can check out the release notes for the individual milestones:
- v4.1.0-RC1
- v4.1.0-M4
- v4.1.0-M3
</div></div></body></html>"""
        with mock.patch.object(extractor.__class__, "fetch", return_value=PLACEHOLDER_HTML):
            wiki_text, prose_changes = asyncio.run(
                extractor._fetch_wiki_release_notes("4.1.0-RC1")
            )
        assert isinstance(wiki_text, str)
        assert prose_changes == []

    check("2-F 4.1 placeholder handled", _2f)


async def level_4() -> None:
    print("\n=== Level 4 — Full version range coverage (live HTTP) ===")

    WIKI_URLS = {
        "3.3": "https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.3-Release-Notes",
        "3.4": "https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4-Release-Notes",
        "3.5": "https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.5-Release-Notes",
        "4.0": "https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Release-Notes",
        "4.1": "https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.1-Release-Notes",
    }

    async with SpringBootExtractor() as extractor:
        # 4-A
        failures = []
        for series, url in WIKI_URLS.items():
            try:
                html = await extractor.fetch(url, accept_status={200})
                print(f"  4-A [{series}] HTTP 200 — {len(html):,} chars")
            except RuntimeError as e:
                failures.append(f"[{series}] {e}")
        if failures:
            raise AssertionError(f"4-A failed: {failures}")
        check("4-A all wiki URLs HTTP 200", lambda: None)

        # 4-B
        selector_failures = []
        for series, url in WIKI_URLS.items():
            html = await extractor.fetch(url, accept_status={200})
            soup = BeautifulSoup(html, "html.parser")
            if soup.select_one("#wiki-body .markdown-body") is None:
                selector_failures.append(series)
        if selector_failures:
            raise AssertionError(f"4-B selector missing: {selector_failures}")
        check("4-B selector present on all pages", lambda: None)

        # 4-C
        REPRESENTATIVE_VERSIONS = {
            "3.3": "3.3.6",
            "3.4": "3.4.5",
            "3.5": "3.5.0",
            "4.0": "4.0.3",
            "4.1": "4.1.0-RC1",
        }
        THRESHOLDS = {
            "3.3": {"min_text": 8_000, "max_text": 50_000, "min_prose": 5, "min_bullets": 30},
            "3.4": {"min_text": 10_000, "max_text": 50_000, "min_prose": 10, "min_bullets": 50},
            "3.5": {"min_text": 10_000, "max_text": 50_000, "min_prose": 10, "min_bullets": 50},
            "4.0": {"min_text": 0, "max_text": 50_000, "min_prose": 0, "min_bullets": 15},
            "4.1": {"min_text": 0, "max_text": 5_000, "min_prose": 0, "min_bullets": 0},
        }
        c_failures = []
        for series, to_version in REPRESENTATIVE_VERSIONS.items():
            t = THRESHOLDS[series]
            wiki_text, prose_changes = await extractor._fetch_wiki_release_notes(to_version)
            major, minor, _, _ = parse_version(to_version)
            wiki_url = (
                f"https://github.com/spring-projects/spring-boot/wiki/"
                f"Spring-Boot-{major}.{minor}-Release-Notes"
            )
            bullet_changes = [
                c
                for c in parse_github_release_text(wiki_text, wiki_url)
                if len(c.statement) > 30
            ] if wiki_text else []
            errs = []
            if not (t["min_text"] <= len(wiki_text) <= t["max_text"]):
                errs.append(f"text={len(wiki_text)}")
            if len(prose_changes) < t["min_prose"]:
                errs.append(f"prose={len(prose_changes)}")
            if len(bullet_changes) < t["min_bullets"]:
                errs.append(f"bullets={len(bullet_changes)}")
            dep_noise = [
                lib
                for lib in ("HikariCP", "Testcontainers 1.", "Kafka 3.")
                if lib in wiki_text
            ]
            if dep_noise:
                errs.append(f"noise={dep_noise}")
            status = "PASS" if not errs else f"FAIL: {errs}"
            print(f"  4-C [{series}] text={len(wiki_text)} prose={len(prose_changes)} "
                  f"bullets={len(bullet_changes)} {status}")
            if errs:
                c_failures.append(f"[{series}] {errs}")
        if c_failures:
            raise AssertionError(f"4-C failed: {c_failures}")
        check("4-C thresholds per series", lambda: None)

        # 4-D
        PROSE_SERIES = {"3.3": ("3.3.0", 5), "3.4": ("3.4.0", 10), "3.5": ("3.5.0", 10)}
        d_failures = []
        for series, (to_version, min_count) in PROSE_SERIES.items():
            _, prose_changes = await extractor._fetch_wiki_release_notes(to_version)
            if len(prose_changes) < min_count:
                d_failures.append(f"[{series}] count={len(prose_changes)}")
                continue
            short = [c for c in prose_changes if len(c.statement) < 30]
            if short:
                d_failures.append(f"[{series}] {len(short)} too short")
            wrong_url = [
                c
                for c in prose_changes
                if not c.source_url.startswith(
                    "https://github.com/spring-projects/spring-boot/wiki/"
                )
            ]
            if wrong_url:
                d_failures.append(f"[{series}] wrong source_url")
            high_value = [
                c
                for c in prose_changes
                if c.type in ("mandatory_migration", "breaking", "deprecation")
            ]
            if not high_value:
                d_failures.append(
                    f"[{series}] no high-value types: {set(c.type for c in prose_changes)}"
                )
            print(f"  4-D [{series}] {len(prose_changes)} prose, "
                  f"{len(high_value)} high-value")
        if d_failures:
            raise AssertionError(f"4-D failed: {d_failures}")
        check("4-D prose quality", lambda: None)

        # 4-E
        VERSIONS = [
            ("3.3", "3.3.0", "3.3.1", True, True),
            ("3.4", "3.4.0", "3.4.1", True, True),
            ("3.5", "3.5.0", "3.5.1", True, True),
            ("4.0", "4.0.0", "4.0.1", True, False),
            ("4.1", "4.0.6", "4.1.0-RC1", False, False),
        ]
        e_failures = []
        for series, from_v, to_v, expect_wiki, expect_prose in VERSIONS:
            try:
                result = await extractor.extract(from_v, to_v)
            except Exception as e:
                e_failures.append(f"[{series}] extract raised: {e}")
                continue
            gh = [c for c in result.changes if "/releases/tag/" in c.source_url]
            wiki = [c for c in result.changes if "/wiki/Spring-Boot-" in c.source_url]
            prose = [
                c for c in wiki if ": " in c.statement and len(c.statement) > 60
            ]
            errs = []
            if len(gh) < 5:
                errs.append(f"gh={len(gh)}")
            if expect_wiki and len(wiki) == 0:
                errs.append("no wiki entries")
            if expect_prose and len(prose) == 0:
                errs.append("no prose entries")
            if len(result.changes) > 400:
                errs.append(f"total={len(result.changes)}")
            print(f"  4-E [{series}] total={len(result.changes)} gh={len(gh)} "
                  f"wiki={len(wiki)} prose={len(prose)} "
                  f"{'PASS' if not errs else errs}")
            if errs:
                e_failures.append(f"[{series}] {errs}")
        if e_failures:
            raise AssertionError(f"4-E failed: {e_failures}")
        check("4-E end-to-end extract", lambda: None)

        # 4-F
        MAVEN_URL = (
            "https://repo1.maven.org/maven2/org/springframework/boot/"
            "spring-boot-dependencies/maven-metadata.xml"
        )
        xml = await extractor.fetch(MAVEN_URL)
        raw = parse_maven_metadata_versions(xml)
        ga = [v for v in raw if is_spring_boot_ga_version(v)]
        in_range = [
            v
            for v in ga
            if (3, 3) <= (parse_version(v)[0], parse_version(v)[1]) <= (4, 1)
        ]
        assert len(in_range) >= 50, f"only {len(in_range)} GA versions"
        KNOWN_SERIES = {"3.3", "3.4", "3.5", "4.0", "4.1"}
        unknowns = []
        for v in in_range:
            major, minor, _, _ = parse_version(v)
            if f"{major}.{minor}" not in KNOWN_SERIES:
                unknowns.append(v)
        if unknowns:
            raise AssertionError(f"unknown series: {unknowns}")
        print(f"  4-F {len(in_range)} GA versions map to known series")
        check("4-F Maven Central version mapping", lambda: None)


async def level_7() -> None:
    print("\n=== Level 7 — Edge-case paths ===")

    def _7a():
        ALL_VERSIONS = [
            "3.3.0", "3.3.1", "3.3.2", "3.3.3", "3.3.4", "3.3.5", "3.3.6", "3.3.7",
            "3.3.8", "3.3.9", "3.3.10", "3.3.11", "3.3.12", "3.3.13",
            "3.4.0", "3.4.1", "3.4.2", "3.4.3", "3.4.4", "3.4.5", "3.4.6", "3.4.7",
            "3.4.8", "3.4.9", "3.4.10", "3.4.11", "3.4.12", "3.4.13",
            "3.5.0", "3.5.1", "3.5.2", "3.5.3", "3.5.4", "3.5.5", "3.5.6", "3.5.7",
            "3.5.8", "3.5.9", "3.5.10", "3.5.11", "3.5.12", "3.5.13", "3.5.14",
            "4.0.0", "4.0.1", "4.0.2", "4.0.3", "4.0.4", "4.0.5", "4.0.6",
            "4.1.0-RC1",
        ]
        _WIKI_TEMPLATE = (
            "https://github.com/spring-projects/spring-boot/wiki/"
            "Spring-Boot-{major}.{minor}-Release-Notes"
        )
        EXPECTED = {
            "3.3": "Spring-Boot-3.3-Release-Notes",
            "3.4": "Spring-Boot-3.4-Release-Notes",
            "3.5": "Spring-Boot-3.5-Release-Notes",
            "4.0": "Spring-Boot-4.0-Release-Notes",
            "4.1": "Spring-Boot-4.1-Release-Notes",
        }
        for v in ALL_VERSIONS:
            major, minor, _, _ = parse_version(v)
            url = _WIKI_TEMPLATE.format(major=major, minor=minor)
            expected_slug = EXPECTED.get(f"{major}.{minor}")
            assert expected_slug and url.endswith(expected_slug)

    check("7-A slug parametric", _7a)

    async with SpringBootExtractor() as extractor:
        # 7-B
        wiki_text, prose_changes = await extractor._fetch_wiki_release_notes("4.0.0")
        assert prose_changes == []
        major, minor, _, _ = parse_version("4.0.0")
        wiki_url = (
            f"https://github.com/spring-projects/spring-boot/wiki/"
            f"Spring-Boot-{major}.{minor}-Release-Notes"
        )
        bullet_changes = [
            c
            for c in parse_github_release_text(wiki_text, wiki_url)
            if len(c.statement) > 30
        ]
        assert len(bullet_changes) >= 15, f"got {len(bullet_changes)}"
        print(f"  7-B 4.0 prose=[] bullets={len(bullet_changes)}")
        check("7-B 4.0 bullets without prose", lambda: None)

        # 7-C
        wiki_text, prose_changes = await extractor._fetch_wiki_release_notes("4.1.0-RC1")
        assert isinstance(wiki_text, str)
        assert prose_changes == []
        assert len(wiki_text) < 2000
        print(f"  7-C 4.1 placeholder {len(wiki_text)} chars")
        check("7-C 4.1 placeholder graceful", lambda: None)

    # 7-D
    extractor = SpringBootExtractor.__new__(SpringBootExtractor)
    fetch_calls: list[str] = []
    MOCK_HTML = (
        "<html><body><div id='wiki-body'><div class='markdown-body'>"
        "<p>Content</p></div></div></body></html>"
    )

    async def counting_fetch(self, url, **kwargs):
        if url in self._cache:
            return self._cache[url]
        if "wiki" in url:
            fetch_calls.append(url)
        self._cache[url] = MOCK_HTML
        return MOCK_HTML

    with mock.patch.object(SpringBootExtractor, "fetch", counting_fetch):
        extractor._cache = {}
        await extractor._fetch_wiki_release_notes("3.5.0")
        await extractor._fetch_wiki_release_notes("3.5.1")
        await extractor._fetch_wiki_release_notes("3.5.2")
    assert len(set(fetch_calls)) == 1 and len(fetch_calls) == 1
    print("  7-D 1 wiki fetch for 3 patch hops")
    check("7-D cache de-duplicates wiki fetches", lambda: None)


def main() -> int:
    global PASS, FAIL
    level_0()
    level_1()
    level_2()
    try:
        asyncio.run(level_4())
        asyncio.run(level_7())
    except Exception as exc:
        print(f"\n✗ Live HTTP checks failed: {exc}")
        FAIL += 1

    print(f"\n{'='*50}")
    print(f"Results: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
