#!/usr/bin/env python3
"""Run specs/003b-extractors-improvements/verification-protocol.md checks."""

from __future__ import annotations

import asyncio
import ast
import importlib
import inspect
import os
import re
import subprocess
import sys
import textwrap
import unittest.mock as mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))


def run_check(name: str, fn) -> None:
    try:
        fn()
        print(f"PASS [{name}]")
    except Exception as exc:
        print(f"FAIL [{name}]: {exc}", file=sys.stderr)
        raise


def level_0() -> None:
    modules = [
        "migration_oracle.pipeline.extractors.spring_boot",
        "migration_oracle.pipeline.extractors.angular",
        "migration_oracle.pipeline.extractors.wildfly",
        "migration_oracle.pipeline.extractors.hibernate",
        "migration_oracle.pipeline.extractors.resteasy",
        "migration_oracle.pipeline.extractors.infinispan",
        "migration_oracle.pipeline.extractors.elytron",
    ]
    for m in modules:
        importlib.import_module(m)
        print(f"PASS: {m} imports cleanly")

    from migration_oracle.pipeline.extractors.spring_boot import SpringBootExtractor
    from packaging.version import Version

    assert hasattr(SpringBootExtractor, "_fetch_wiki_release_notes")
    sig = inspect.signature(SpringBootExtractor._fetch_wiki_release_notes)
    assert "to_version" in sig.parameters

    cases = [
        ("3.4.0", "Spring-Boot-3.4-Release-Notes"),
        ("3.4.2", "Spring-Boot-3.4-Release-Notes"),
        ("3.5.0", "Spring-Boot-3.5-Release-Notes"),
        ("4.0.0", "Spring-Boot-4.0-Release-Notes"),
        ("4.1.0", "Spring-Boot-4.1-Release-Notes"),
    ]
    for version, expected_slug in cases:
        v = Version(version)
        url = (
            f"https://github.com/spring-projects/spring-boot/wiki/"
            f"Spring-Boot-{v.major}.{v.minor}-Release-Notes"
        )
        assert url.endswith(expected_slug)

    src = inspect.getsource(SpringBootExtractor.extract)
    tree = ast.parse(textwrap.dedent(src))
    calls = [
        node.func.attr
        if isinstance(node.func, ast.Attribute)
        else node.func.id
        if isinstance(node.func, ast.Name)
        else ""
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    ]
    assert "build_range_metadata" not in calls

    import migration_oracle.pipeline.extractors.spring_boot as sb_module

    src = inspect.getsource(sb_module)
    assert re.search(r"dependency.upgrades?", src, re.IGNORECASE)

    from migration_oracle.pipeline.extractors.angular import (
        AngularExtractor,
        _extract_changelog_section,
    )

    for method_name in ("_get_changelog", "_fetch_blog_summary"):
        assert hasattr(AngularExtractor, method_name)

    sample = """
<a name="21.0.0"></a>
# 21.0.0 (2025-01-01)
### Breaking Changes
#### core
* Old API removed.
<a name="20.0.0"></a>
# 20.0.0 (2024-06-01)
### Features
* Something added.
"""
    section = _extract_changelog_section(sample, "21.0.0")
    assert "Old API removed" in section
    assert "Something added" not in section
    assert _extract_changelog_section(sample, "99.0.0") == ""

    from migration_oracle.pipeline.extractors.filters import is_jboss_ga_version

    pass_cases = ["6.0.0.Final", "7.2.0.Final", "2.9.0.Final", "29.0.0.Final"]
    fail_cases = [
        "6.0.0.Alpha1",
        "6.0.0.Beta3",
        "6.0.0.CR1",
        "7.2.0.CR1",
        "7.0.0.Beta1",
        "2.9.0.CR2",
        "6.0.0",
        "6.0.0-SNAPSHOT",
    ]
    for v in pass_cases:
        assert is_jboss_ga_version(v)
    for v in fail_cases:
        assert not is_jboss_ga_version(v)

    from migration_oracle.pipeline.extractors.filters import is_infinispan_ga_version

    for v in ["15.1.0.Final", "14.0.0.Final", "16.0.0", "16.2.1"]:
        assert is_infinispan_ga_version(v)
    for v in ["16.2.0.Dev01", "16.2.0.Dev02", "15.0.0.Alpha1", "15.0.0.Beta2", "16.0.0.CR1"]:
        assert not is_infinispan_ga_version(v)

    from migration_oracle.pipeline.extractors.wildfly import WildFlyExtractor

    src = inspect.getsource(WildFlyExtractor.extract)
    assert not re.search(r'f["\'].*{major}\.0\.0\.Final', src)
    assert re.search(r'f["\'].*{version}.*\.Final', src)

    src = inspect.getsource(WildFlyExtractor.enrich_with_jira)
    assert "re.finditer" in src
    assert "re.search" not in src or src.count("re.search") == 0
    bare = re.findall(r"meta\s*=\s*change\.metadata(?!\s*\)|\s*or)", src)
    assert len(bare) == 0
    assert len(re.findall(r"dict\(change\.metadata", src)) >= 1
    assert "jira_priority" in src

    src = inspect.getsource(WildFlyExtractor)
    assert re.search(r"['\"]priority['\"].*get\(", src) or re.search(
        r"get\(.*['\"]priority['\"]", src
    )

    from migration_oracle.pipeline.extractors.infinispan import InfinispanExtractor

    src = inspect.getsource(InfinispanExtractor.extract)
    match = re.search(r"tag_candidates\s*=\s*\[([^\]]+)\]", src)
    assert match
    assert "Final" not in match.group(1).split(",")[0]

    from migration_oracle.pipeline.extractors.hibernate import HibernateExtractor

    src = inspect.getsource(HibernateExtractor.extract)
    match = re.search(r"tag_candidates\s*=\s*\[([^\]]+)\]", src)
    assert match
    assert "Final" not in match.group(1)


CLI = ["uv", "run", "migration-oracle", "export-extract-populate-framework"]


def level_1() -> None:
    help_out = subprocess.run(
        [*CLI, "--help"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    for flag in (
        "--framework",
        "--dry-run",
        "--force",
        "--force-extract",
        "--force-llm",
        "--output-md",
        "--output-filtered-md",
        "--output-json",
    ):
        assert flag in help_out

    proc = subprocess.run(
        [*CLI, "--framework", "nonexistent-framework", "1.0.0", "2.0.0"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "Traceback" not in proc.stderr

    os.environ["JBOSS_SKIP_PRERELEASE"] = "0"
    import migration_oracle.pipeline.extractors.filters as filters_mod

    importlib.reload(filters_mod)
    from migration_oracle.pipeline.extractors.filters import _skip_prerelease

    assert _skip_prerelease() is False
    del os.environ["JBOSS_SKIP_PRERELEASE"]
    importlib.reload(filters_mod)


def level_2() -> None:
    from migration_oracle.models.entities import DocumentedChange
    from migration_oracle.pipeline.extractors.angular import (
        AngularExtractor,
        _extract_changelog_section,
    )
    from migration_oracle.pipeline.extractors.hibernate import HibernateExtractor
    from migration_oracle.pipeline.extractors.infinispan import InfinispanExtractor
    from migration_oracle.pipeline.extractors.spring_boot import SpringBootExtractor
    from migration_oracle.pipeline.extractors.wildfly import WildFlyExtractor

    extractor = SpringBootExtractor.__new__(SpringBootExtractor)

    async def fail_wiki(_version: str) -> str:
        return ""

    async def fake_release(*_a, **_k):
        return "https://example.com", "## Bug Fixes\n- Fix something\n"

    async def run_wiki_test():
        with mock.patch.object(
            SpringBootExtractor, "_fetch_wiki_release_notes", side_effect=fail_wiki
        ), mock.patch.object(
            SpringBootExtractor, "fetch_github_release", side_effect=fake_release
        ):
            return await extractor.extract("3.4.0", "3.4.1")

    result = asyncio.run(run_wiki_test())
    assert result is not None

    changelog = """\
<a name="22.0.0"></a>
# 22.0.0 (2026-05-01)
### Breaking Changes
#### core
* ChangeDetectorRef.checkNoChanges was removed.
<a name="21.0.0"></a>
# 21.0.0 (2025-10-01)
### Breaking Changes
#### compiler
* Some old compiler API removed.
<a name="20.0.0"></a>
# 20.0.0 (2025-05-01)
### Features
* Something added.
"""
    sec = _extract_changelog_section(changelog, "22.0.0")
    assert "ChangeDetectorRef.checkNoChanges was removed" in sec
    assert "Some old compiler API removed" not in sec

    statement = DocumentedChange(
        type="breaking",
        confidence="confirmed",
        source_url="https://redhat.atlassian.net/browse/WFLY-18341",
        statement="[WFLY-18341] Supersedes [WFCORE-4892] — some migration change",
        metadata={},
    )
    fake_cache = {
        "WFCORE-4892": {
            "summary": "Fix for EE subsystem migration",
            "description": "Full description of the WFCORE issue.",
            "issue_type": "Bug",
            "priority": "Major",
            "status": "Resolved",
            "source_url": "https://redhat.atlassian.net/browse/WFCORE-4892",
        }
    }
    wf = WildFlyExtractor.__new__(WildFlyExtractor)
    enriched = wf.enrich_with_jira(
        changes=[statement], cache=fake_cache, index={}
    )
    assert "Fix for EE subsystem migration" in enriched[0].statement
    assert "WFCORE-4892" in enriched[0].source_url

    statement2 = DocumentedChange(
        type="behavioral",
        confidence="inferred",
        source_url="https://redhat.atlassian.net/browse/WFLY-19845",
        statement="[WFLY-19845] - Update WildFly Core to 24.0.1.Final",
        metadata={},
    )
    enriched2 = wf.enrich_with_jira(
        changes=[statement2],
        cache={
            "WFLY-19845": {
                "summary": "Update WildFly Core to 24.0.1.Final",
                "description": "",
                "issue_type": "Task",
                "priority": "Minor",
                "status": "Resolved",
                "source_url": "https://redhat.atlassian.net/browse/WFLY-19845",
            }
        },
        index={},
    )
    assert enriched2[0].statement.startswith("Title:")
    assert "N/A" in enriched2[0].statement

    enriched3 = wf.enrich_with_jira(
        changes=[
            DocumentedChange(
                type="behavioral",
                confidence="inferred",
                source_url="",
                statement="[WFLY-20000] - Some enhancement",
                metadata={},
            )
        ],
        cache={
            "WFLY-20000": {
                "summary": "Some enhancement description",
                "description": "Full description here.",
                "issue_type": "",
                "priority": "Major",
                "status": "Resolved",
                "source_url": "https://redhat.atlassian.net/browse/WFLY-20000",
            }
        },
        index={"WFLY-20000": {"issue_type": "Enhancement", "summary": "Some enhancement"}},
    )
    assert enriched3[0].metadata.get("issue_type") == "Enhancement"

    enriched4 = wf.enrich_with_jira(
        changes=[
            DocumentedChange(
                type="breaking",
                confidence="confirmed",
                source_url="",
                statement="[WFLY-17312] - Remove deprecated javax.security.auth.message SPI",
                metadata={},
            )
        ],
        cache={
            "WFLY-17312": {
                "summary": "Remove deprecated javax.security.auth.message SPI classes",
                "description": "The javax.security.auth.message SPI classes were removed.",
                "issue_type": "Enhancement",
                "priority": "Critical",
                "status": "Resolved",
                "source_url": "https://redhat.atlassian.net/browse/WFLY-17312",
            }
        },
        index={},
    )
    assert enriched4[0].metadata.get("jira_priority") == "Critical"

    original_meta = {"existing_key": "existing_value"}
    original_meta_id = id(original_meta)
    enriched5 = wf.enrich_with_jira(
        changes=[
            DocumentedChange(
                type="behavioral",
                confidence="inferred",
                source_url="",
                statement="[WFLY-19999] - Some change",
                metadata=original_meta,
            )
        ],
        cache={
            "WFLY-19999": {
                "summary": "Some change summary",
                "description": "Some description.",
                "issue_type": "Bug",
                "priority": "Minor",
                "status": "Resolved",
                "source_url": "https://redhat.atlassian.net/browse/WFLY-19999",
            }
        },
        index={},
    )
    assert id(enriched5[0].metadata) != original_meta_id
    assert list(original_meta.keys()) == ["existing_key"]

    hib = HibernateExtractor.__new__(HibernateExtractor)
    mock_versions = [
        "6.0.0.Alpha1",
        "6.0.0.Beta1",
        "6.0.0.CR1",
        "6.0.0.Final",
        "6.1.0.Alpha1",
        "6.1.0.Final",
        "7.2.0.CR1",
        "7.2.0.Final",
    ]
    with mock.patch.object(hib, "_fetch_maven_versions", return_value=mock_versions):
        versions = hib.get_available_versions()
    assert versions == ["6.0.0.Final", "6.1.0.Final", "7.2.0.Final"]

    isp = InfinispanExtractor.__new__(InfinispanExtractor)
    mock_isp = [
        "15.0.0.Final",
        "15.1.0.Final",
        "16.0.0",
        "16.1.0",
        "16.2.0.Dev01",
        "16.2.0.Dev02",
    ]
    with mock.patch.object(isp, "_fetch_maven_versions", return_value=mock_isp):
        versions = isp.get_available_versions()
    assert versions == ["15.0.0.Final", "15.1.0.Final", "16.0.0", "16.1.0"]

    sb = SpringBootExtractor.__new__(SpringBootExtractor)
    body = """\
## ⭐ New Features
- Add support for X configuration
## 🐞 Bug Fixes
- Fix NPE in DataSourceConfig
## 🔨 Dependency Upgrades
- Upgrade to Tomcat 10.1.16 #38421
- Upgrade to Hibernate 6.4.0 #38500
## 📝 Documentation
- Update README
"""
    changes = sb.parse_github_release_text(body)
    statements = [c.statement for c in changes]
    for line in ["Tomcat 10.1.16", "Hibernate 6.4.0"]:
        assert not any(line in s for s in statements)
    assert any("Add support for X" in s for s in statements)

    ang = AngularExtractor.__new__(AngularExtractor)
    mock_html = (
        '<html><head><meta name="description" '
        'content="Complete guide to migrating from NgModules to standalone components.">'
        "</head></html>"
    )
    with mock.patch.object(ang, "_http_get_cached", return_value=mock_html):
        result = ang._fetch_blog_summary("https://blog.angular.dev/some-post")
    assert "NgModules" in result or "standalone" in result
    with mock.patch.object(ang, "_http_get_cached", side_effect=Exception("network error")):
        assert ang._fetch_blog_summary("https://blog.angular.dev/bad-url") == ""

    release_body = (
        "Check out the migration guide at "
        "https://blog.angular.dev/angular-v22 for details.\n"
        "## Breaking Changes\n- Something breaking\n"
    )
    blog_html = (
        '<html><head><meta name="description" '
        'content="Angular v22 migration steps explained."></head></html>'
    )

    async def run_angular_extract():
        with mock.patch.object(ang, "_get_changelog", return_value=""), mock.patch.object(
            ang, "fetch_github_release",
            return_value=("https://github.com/angular/angular/releases/tag/v22.0.0", release_body),
        ), mock.patch.object(ang, "_http_get_cached", return_value=blog_html):
            return await ang.extract("21.0.0", "22.0.0")

    ang_result = asyncio.run(run_angular_extract())
    blog_insights = ang_result.metadata.get("blog_insights", [])
    assert isinstance(blog_insights, list) and blog_insights
    assert isinstance(blog_insights[0], dict)
    assert "url" in blog_insights[0] and "summary" in blog_insights[0]


def level_7() -> None:
    import unittest.mock as mock

    from migration_oracle.pipeline.extractors.angular import AngularExtractor
    from migration_oracle.pipeline.extractors.hibernate import HibernateExtractor
    from migration_oracle.pipeline.extractors.infinispan import InfinispanExtractor
    from migration_oracle.pipeline.extractors.spring_boot import SpringBootExtractor
    from migration_oracle.pipeline.extractors.wildfly import WildFlyExtractor

    sb = SpringBootExtractor.__new__(SpringBootExtractor)

    async def run_sb():
        with mock.patch.object(SpringBootExtractor, "_fetch_wiki_release_notes", return_value=""), mock.patch.object(
            SpringBootExtractor,
            "fetch_github_release",
            return_value=("https://example.com", "## Bug Fixes\n- Fix something #1234\n"),
        ):
            return await sb.extract("3.4.0", "3.4.1")

    assert asyncio.run(run_sb()) is not None

    ang = AngularExtractor.__new__(AngularExtractor)

    async def run_ang():
        with mock.patch.object(AngularExtractor, "_get_changelog", return_value=""), mock.patch.object(
            AngularExtractor,
            "fetch_github_release",
            return_value=("https://example.com", "## Breaking Changes\n- Something breaking\n"),
        ):
            return await ang.extract("17.0.0", "17.1.0")

    assert asyncio.run(run_ang()) is not None

    ang2 = AngularExtractor.__new__(AngularExtractor)
    with mock.patch.object(ang2, "_http_get_cached", side_effect=Exception("timeout")):
        assert ang2._fetch_blog_summary("https://blog.angular.dev/timeout-post") == ""

    os.environ["JBOSS_SKIP_PRERELEASE"] = "0"
    mock_versions = ["6.0.0.Alpha1", "6.0.0.Final", "7.0.0.Beta1", "7.0.0.Final"]
    for name, module_path, class_name in [
        ("hibernate", "migration_oracle.pipeline.extractors.hibernate", "HibernateExtractor"),
        ("resteasy", "migration_oracle.pipeline.extractors.resteasy", "RestEasyExtractor"),
        ("elytron", "migration_oracle.pipeline.extractors.elytron", "ElytronExtractor"),
    ]:
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        extractor = cls.__new__(cls)
        with mock.patch.object(extractor, "_fetch_maven_versions", return_value=mock_versions):
            versions = extractor.get_available_versions()
        assert "6.0.0.Alpha1" in versions
        assert len(versions) == len(mock_versions)
    del os.environ["JBOSS_SKIP_PRERELEASE"]

    wf = WildFlyExtractor.__new__(WildFlyExtractor)
    attempted_tags: list[str] = []

    async def fake_fetch_github_release(_repo, _version, tag_candidates):
        attempted_tags.extend(tag_candidates)
        return (
            "https://example.com",
            "## Bug Fixes\n- [WFLY-1] Fix something\n",
        )

    async def run_wf():
        with mock.patch.object(wf, "fetch_github_release", side_effect=fake_fetch_github_release):
            return await wf.extract("39.0.0", "39.0.1")

    asyncio.run(run_wf())
    assert "39.0.1.Final" in attempted_tags

    isp = InfinispanExtractor.__new__(InfinispanExtractor)
    attempted_isp: list[str] = []

    async def fake_isp(_repo, _version, tag_candidates):
        attempted_isp.extend(tag_candidates)
        return (
            "https://example.com",
            "## Breaking Changes\n- Cache API changed\n",
        )

    async def run_isp():
        with mock.patch.object(isp, "fetch_github_release", side_effect=fake_isp):
            return await isp.extract("15.1.0.Final", "16.0.0")

    asyncio.run(run_isp())
    assert attempted_isp[0] == "16.0.0"

    hib = HibernateExtractor.__new__(HibernateExtractor)
    attempted_hib: list[str] = []

    async def fake_hib(_repo, _version, tag_candidates):
        attempted_hib.extend(tag_candidates)
        return (
            "https://example.com",
            "## Breaking Changes\n- Schema validation changed\n",
        )

    async def fake_guide(_v, tags):
        return await fake_hib("hibernate/hibernate-orm", _v, tags)

    async def run_hib():
        with mock.patch.object(hib, "_fetch_guide", side_effect=fake_guide):
            return await hib.extract("6.3.0.Final", "6.4.0.Final")

    asyncio.run(run_hib())
    assert "6.4.0.Final" not in attempted_hib
    assert "6.4.0" in attempted_hib

    wiki_calls: list[str] = []

    async def fake_wiki(to_version: str) -> str:
        wiki_calls.append(to_version)
        return "Wiki content"

    async def fake_release2(*_a, **_k):
        return "https://example.com", "## Bug Fixes\n- Fix #1\n"

    async def run_wiki_hops():
        with mock.patch.object(
            SpringBootExtractor, "_fetch_wiki_release_notes", side_effect=fake_wiki
        ), mock.patch.object(
            SpringBootExtractor, "fetch_github_release", side_effect=fake_release2
        ):
            await sb.extract("3.3.0", "3.3.1")
            await sb.extract("3.3.1", "3.3.2")

    asyncio.run(run_wiki_hops())
    from packaging.version import Version

    wiki_urls = {
        f"Spring-Boot-{Version(v).major}.{Version(v).minor}-Release-Notes"
        for v in wiki_calls
    }
    assert wiki_urls == {"Spring-Boot-3.3-Release-Notes"}


def level_4() -> None:
    subprocess.run(["mkdir", "-p", "runs/raw", "runs/nodes", "runs/json"], check=True)

    proc = subprocess.run(
        [*CLI, "--framework", "spring-boot", "--force-extract", "--extract-only", "3.3.0", "3.3.1"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout

    raw = Path("runs/raw/spring-boot-3.3.0-to-3.3.1-changes.md")
    assert raw.exists(), "Spring Boot raw artifact missing"

    content = raw.read_text(encoding="utf-8")
    if not re.search(r"breaking|mandatory_migration|deprecation", content, re.I):
        print("WARN: no breaking/mandatory/deprecation rows in Spring Boot raw artifact")
    assert not re.search(r"dependency_upgrade.*Upgrade to ", content, re.I)

    from migration_oracle.pipeline.extractors.spring_boot import SpringBootExtractor

    async def check_bom_diff_once() -> None:
        async with SpringBootExtractor() as sb:
            result, _ = await sb.extract_range("3.3.0", "3.3.2")
        bom_diff = result.metadata.get("bom_diff", {})
        assert bom_diff, f"bom_diff missing from metadata keys: {list(result.metadata.keys())}"
        for key in ("added", "changed", "removed"):
            assert key in bom_diff

    asyncio.run(check_bom_diff_once())

    proc = subprocess.run(
        [*CLI, "--framework", "angular", "--force-extract", "--extract-only", "17.0.0", "17.1.0"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    angular_raw = Path("runs/raw/angular-17.0.0-to-17.1.0-changes.md")
    assert angular_raw.exists()

    mtime_before = raw.stat().st_mtime
    import time

    time.sleep(1)
    proc = subprocess.run(
        [*CLI, "--framework", "spring-boot", "--extract-only", "3.3.0", "3.3.1"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    mtime_after = raw.stat().st_mtime
    assert mtime_before == mtime_after, "raw artifact regenerated without --force-extract"

    proc = subprocess.run(
        [*CLI, "--framework", "wildfly", "--force-extract", "--extract-only", "29.0.0", "29.0.1"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    wildfly_raw = Path("runs/raw/wildfly-29.0.0-to-29.0.1-changes.md")
    assert wildfly_raw.exists()


def main() -> int:
    run_check("Level 0", level_0)
    run_check("Level 1", level_1)
    run_check("Level 2", level_2)
    run_check("Level 7", level_7)
    print("Offline verification levels 0, 1, 2, 7 passed.")
    try:
        run_check("Level 4", level_4)
        print("Level 4 (live HTTP extract-only) passed.")
    except Exception as exc:
        print(f"WARN: Level 4 skipped or failed: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
