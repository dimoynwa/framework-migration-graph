"""Unit tests for the GitLab client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from migration_oracle.paysafe._types import CompatibilityInfoObj
from migration_oracle.paysafe.gitlab import (
    _GitError,
    _https_to_scp,
    _is_compatible,
    _parse_gradle,
    _parse_package_json,
    _parse_pom_xml,
    _parse_tag_version,
    _tag_ref_candidates,
    _version_token_from_tag,
    detect_framework_at_head,
    list_tags,
)


def _mock_subprocess(stdout: str = "", returncode: int = 0):
    mock_result = MagicMock()
    mock_result.returncode = returncode
    mock_result.stdout = stdout
    mock_result.stderr = ""
    return mock_result


def test_https_to_scp():
    url = "https://gitlab.paysafe.com/payment/payment-service.git"
    assert _https_to_scp(url) == "git@gitlab.paysafe.com:payment/payment-service.git"


def test_list_tags_strips_v_prefix_and_sorts_descending():
    stdout = (
        "abc\trefs/tags/v3.5.10\n"
        "def\trefs/tags/3.4.0\n"
        "ghi\trefs/tags/3.5.10.A\n"
        "jkl\trefs/tags/bad-tag\n"
    )
    with patch(
        "migration_oracle.paysafe.gitlab.subprocess.run",
        return_value=_mock_subprocess(stdout),
    ):
        tags = list_tags("https://gitlab.example.com/a/b.git")
    assert tags[0] in ("v3.5.10", "3.5.10.A", "3.5.10")
    assert "3.4.0" in tags
    assert "bad-tag" not in tags
    assert tags == sorted(tags, key=lambda t: _parse_tag_version(t) or _parse_tag_version("0"), reverse=True)


def test_list_tags_no_tags_raises():
    with patch(
        "migration_oracle.paysafe.gitlab.subprocess.run",
        return_value=_mock_subprocess(""),
    ):
        with pytest.raises(_GitError) as exc_info:
            list_tags("https://gitlab.example.com/a/b.git")
    assert exc_info.value.error_code == "no_tags_found"


def test_list_tags_no_parseable_tags_raises():
    stdout = "abc\trefs/tags/not-a-version\n"
    with patch(
        "migration_oracle.paysafe.gitlab.subprocess.run",
        return_value=_mock_subprocess(stdout),
    ):
        with pytest.raises(_GitError) as exc_info:
            list_tags("https://gitlab.example.com/a/b.git")
    assert exc_info.value.error_code == "no_parseable_tags"


def test_version_token_from_maven_coordinate_tag():
    tag = "com.paysafe.op/paysafe-op-dependencies/4.0.7.A"
    assert _version_token_from_tag(tag) == "4.0.7.A"
    assert _parse_tag_version(tag) is not None


def test_tag_ref_candidates_maven_coordinate_tag():
    tag = "com.paysafe.op/paysafe-op-dependencies/4.0.7"
    assert _tag_ref_candidates(tag) == [tag]


def test_list_tags_parses_maven_coordinate_tags():
    stdout = (
        "a\trefs/tags/com.paysafe.op/paysafe-op-dependencies/3.2.5\n"
        "b\trefs/tags/com.paysafe.op/paysafe-op-dependencies/4.0.7\n"
        "c\trefs/tags/com.paysafe.op/paysafe-op-dependencies/4.0.7.A\n"
        "d\trefs/tags/DEPLOYED\n"
        "e\trefs/tags/not-a-version\n"
    )
    with patch(
        "migration_oracle.paysafe.gitlab.subprocess.run",
        return_value=_mock_subprocess(stdout),
    ):
        tags = list_tags("https://gitlab.example.com/a/b.git")
    assert tags[0] in (
        "com.paysafe.op/paysafe-op-dependencies/4.0.7",
        "com.paysafe.op/paysafe-op-dependencies/4.0.7.A",
    )
    assert tags[-1] == "com.paysafe.op/paysafe-op-dependencies/3.2.5"
    assert "DEPLOYED" not in tags
    assert "not-a-version" not in tags


@pytest.mark.parametrize(
    "declared,target,expected",
    [
        ("3.6.0", "3.5.6", True),
        ("3.5.10", "3.5.6", True),
        ("3.5.6", "3.5.6", True),
        ("3.5.5", "3.5.6", False),
        ("3.4.99", "3.5.6", False),
        ("4.0.0", "3.5.6", False),
        ("2.9.0", "3.5.6", False),
        ("3.5.0", "3.5.0", True),
        ("3.5.1", "3.5.0", True),
        ("3.4.9", "3.5.0", False),
        ("3.6.0", "3.5.0", True),
        ("3.0.0", "3.0.0", True),
        ("3.0.1", "3.0.0", True),
        ("2.99.99", "3.0.0", False),
        ("4.1.0", "4.0.0", True),
        ("4.0.0", "4.0.0", True),
        ("3.99.0", "4.0.0", False),
        ("1.2.3", "1.2.3", True),
        ("1.2.4", "1.2.3", True),
        ("1.1.9", "1.2.3", False),
        ("2.0.0", "1.2.3", False),
        ("10.1.0", "10.0.5", True),
        ("10.0.4", "10.0.5", False),
        ("10.0.5", "10.0.5", True),
    ],
)
def test_is_compatible_boundary(declared: str, target: str, expected: bool):
    assert _is_compatible(declared, target) is expected


def test_parse_pom_starter_parent():
    pom = b"""<?xml version="1.0"?>
<project>
  <parent>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.10</version>
  </parent>
</project>"""
    info = _parse_pom_xml(pom)
    assert info is not None
    assert info.framework_version == "3.5.10"
    assert info.source_precedence == "spring-boot-starter-parent"


def test_parse_pom_spring_boot_version_property():
    pom = b"""<?xml version="1.0"?>
<project>
  <properties>
    <spring-boot.version>3.4.2</spring-boot.version>
  </properties>
</project>"""
    info = _parse_pom_xml(pom)
    assert info is not None
    assert info.source_precedence == "spring-boot.version-property"


def test_parse_gradle_plugin_version():
    content = 'id("org.springframework.boot") version "3.5.10"'
    info = _parse_gradle(content)
    assert info is not None
    assert info.source_precedence == "gradle-plugin-version"


def test_parse_gradle_spring_boot_version_ext_property():
    content = """
buildscript {
  ext {
    springBootVersion = "4.0.6"
  }
}
"""
    info = _parse_gradle(content)
    assert info is not None
    assert info.framework_version == "4.0.6"
    assert info.source_precedence == "gradle-springBootVersion-property"


def test_parse_gradle_properties_spring_boot_version():
    from migration_oracle.paysafe.gitlab import _parse_gradle_properties

    content = "springBootVersion=4.0.6\nversion=6.0.0"
    info = _parse_gradle_properties(content)
    assert info is not None
    assert info.framework_version == "4.0.6"
    assert info.source_file == "gradle.properties"


def test_parse_pom_spring_boot_dependencies_bom():
    pom = b"""<?xml version="1.0"?>
<project>
  <dependencyManagement>
    <dependencies>
      <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-dependencies</artifactId>
        <version>4.0.6</version>
        <type>pom</type>
        <scope>import</scope>
      </dependency>
    </dependencies>
  </dependencyManagement>
</project>"""
    info = _parse_pom_xml(pom)
    assert info is not None
    assert info.framework_version == "4.0.6"
    assert info.source_precedence == "spring-boot-dependencies-bom"


def test_parse_angular_core_dependencies():
    content = b'{"dependencies": {"@angular/core": "^17.3.0"}}'
    info = _parse_package_json(content)
    assert info is not None
    assert info.source_precedence == "angular-core-dep"
    assert "17.3.0" in info.framework_version


def test_parse_angular_core_dev_dependencies():
    content = b'{"devDependencies": {"@angular/core": "16.2.1"}}'
    info = _parse_package_json(content)
    assert info is not None
    assert info.source_precedence == "angular-core-dep"


def test_detect_framework_at_head_pom_first():
    with patch(
        "migration_oracle.paysafe.gitlab._head_has_file",
        side_effect=lambda _repo, path: path == "pom.xml",
    ):
        assert detect_framework_at_head("https://gitlab.example.com/a/b.git") == "spring-boot"


def test_detect_framework_at_head_gradle_second():
    with patch(
        "migration_oracle.paysafe.gitlab._head_has_file",
        side_effect=lambda _repo, path: path == "build.gradle",
    ):
        assert detect_framework_at_head("https://gitlab.example.com/a/b.git") == "spring-boot"


def test_detect_framework_at_head_package_json_third():
    with patch(
        "migration_oracle.paysafe.gitlab._head_has_file",
        side_effect=lambda _repo, path: path == "package.json",
    ):
        assert detect_framework_at_head("https://gitlab.example.com/a/b.git") == "angular"
