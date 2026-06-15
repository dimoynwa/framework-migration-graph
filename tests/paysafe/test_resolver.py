"""Integration-style tests for the Paysafe resolver."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from migration_oracle.paysafe._types import CompatibilityInfoObj
from migration_oracle.paysafe.findit import _FindItError
from migration_oracle.paysafe.gitlab import _GitError
from migration_oracle.paysafe.resolver import resolve


def test_pinned_mode_short_circuit():
    with (
        patch("migration_oracle.paysafe.resolver.findit.lookup") as mock_lookup,
        patch("migration_oracle.paysafe.resolver.gitlab.list_tags") as mock_tags,
    ):
        mock_lookup.side_effect = AssertionError("findit must not be called")
        mock_tags.side_effect = AssertionError("gitlab must not be called")

        result = resolve(
            "any-name",
            pinned_version="3.5.10",
            pinned_tag="3.5.10.A",
        )

    assert result["status"] == "ok"
    assert result["selection_strategy"] == "pinned"
    assert result["selected_version"] == "3.5.10"
    assert result["selected_tag"] == "3.5.10.A"
    assert result["compatibility"] is None
    assert "name_resolution" not in result
    assert result["effective_settings"]["max_tags_returned"] == 100


def test_error_invalid_service_name():
    result = resolve("   ")
    assert result["status"] == "error"
    assert result["error"]["error_code"] == "invalid_service_name"


def test_error_service_not_found():
    with patch(
        "migration_oracle.paysafe.resolver.findit.lookup",
        side_effect=_FindItError("service_not_found", "not found"),
    ):
        result = resolve("missing-lib")
    assert result["status"] == "error"
    assert result["error"]["error_code"] == "service_not_found"


def test_error_no_repo_url():
    with patch(
        "migration_oracle.paysafe.resolver.findit.lookup",
        return_value={"name": "my-lib"},
    ):
        result = resolve("my-lib", target_version="3.5.6")
    assert result["status"] == "error"
    assert result["error"]["error_code"] == "no_repo_url"


def test_error_no_tags_found():
    with (
        patch(
            "migration_oracle.paysafe.resolver.findit.lookup",
            return_value={"name": "my-lib", "codeRepoLink": "https://gitlab.example.com/a/b.git"},
        ),
        patch(
            "migration_oracle.paysafe.resolver.gitlab.list_tags",
            side_effect=_GitError("no_tags_found"),
        ),
    ):
        result = resolve("my-lib", target_version="3.5.6")
    assert result["status"] == "error"
    assert result["error"]["error_code"] == "no_tags_found"


def test_error_no_compatible_version():
    compat_info = CompatibilityInfoObj("3.4.0", "pom.xml", "spring-boot-starter-parent")
    with (
        patch(
            "migration_oracle.paysafe.resolver.findit.lookup",
            return_value={"name": "my-lib", "codeRepoLink": "https://gitlab.example.com/a/b.git"},
        ),
        patch(
            "migration_oracle.paysafe.resolver.gitlab.list_tags",
            return_value=["3.4.0"],
        ),
        patch(
            "migration_oracle.paysafe.resolver.gitlab.fetch_framework_version",
            return_value=compat_info,
        ),
    ):
        result = resolve("my-lib", target_version="3.5.6")
    assert result["status"] == "error"
    assert result["error"]["error_code"] == "no_compatible_version"


def test_error_compatibility_unknown():
    with (
        patch(
            "migration_oracle.paysafe.resolver.findit.lookup",
            return_value={"name": "my-lib", "codeRepoLink": "https://gitlab.example.com/a/b.git"},
        ),
        patch(
            "migration_oracle.paysafe.resolver.gitlab.list_tags",
            return_value=["3.5.10"],
        ),
        patch(
            "migration_oracle.paysafe.resolver.gitlab.fetch_framework_version",
            return_value=None,
        ),
    ):
        result = resolve("my-lib", target_version="3.5.6")
    assert result["status"] == "error"
    assert result["error"]["error_code"] == "compatibility_unknown"


def test_error_http_timeout():
    with patch(
        "migration_oracle.paysafe.resolver.findit.lookup",
        side_effect=_FindItError("http_timeout", "timed out"),
    ):
        result = resolve("my-lib", target_version="3.5.6")
    assert result["status"] == "RESOLUTION_FAILED"
    assert result["subStatus"] == "transport_error"


def test_error_http_request_failed():
    with patch(
        "migration_oracle.paysafe.resolver.findit.lookup",
        side_effect=_FindItError("http_request_failed", "failed"),
    ):
        result = resolve("my-lib", target_version="3.5.6")
    assert result["status"] == "error"
    assert result["error"]["error_code"] == "http_request_failed"


def test_latest_compatible_happy_path():
    compat_3510 = CompatibilityInfoObj("3.5.10", "pom.xml", "spring-boot-starter-parent")
    compat_340 = CompatibilityInfoObj("3.4.0", "pom.xml", "spring-boot-starter-parent")

    def fetch_side_effect(_repo, tag):
        if tag == "3.5.10":
            return compat_3510
        if tag == "3.4.0":
            return compat_340
        return None

    with (
        patch(
            "migration_oracle.paysafe.resolver.findit.lookup",
            return_value={
                "name": "my-lib",
                "codeRepoLink": "https://gitlab.example.com/payment/my-lib.git",
            },
        ),
        patch(
            "migration_oracle.paysafe.resolver.gitlab.list_tags",
            return_value=["3.5.10", "3.4.0"],
        ),
        patch(
            "migration_oracle.paysafe.resolver.gitlab.fetch_framework_version",
            side_effect=fetch_side_effect,
        ),
    ):
        result = resolve("my-lib", target_version="3.5.6", framework="spring-boot")

    assert result["status"] == "ok"
    assert result["selected_tag"] == "3.5.10"
    assert result["selection_strategy"] == "latest_compatible"
    assert isinstance(result["compatibility"], dict)
    assert result["compatibility"]["source_precedence"] == "spring-boot-starter-parent"
    assert result["effective_settings"]["max_tags_returned"] == 100
    assert result["code_repo_link"] == "https://gitlab.example.com/payment/my-lib.git"


def test_latest_overall_fallback():
    compat_340 = CompatibilityInfoObj("3.4.0", "pom.xml", "spring-boot-starter-parent")
    with (
        patch(
            "migration_oracle.paysafe.resolver.findit.lookup",
            return_value={"name": "my-lib", "codeRepoLink": "https://gitlab.example.com/a/b.git"},
        ),
        patch(
            "migration_oracle.paysafe.resolver.gitlab.list_tags",
            return_value=["3.4.0"],
        ),
        patch(
            "migration_oracle.paysafe.resolver.gitlab.fetch_framework_version",
            return_value=compat_340,
        ),
    ):
        result = resolve("my-lib", target_version="3.5.6", allow_latest_overall=True)

    assert result["status"] == "ok"
    assert result["selection_strategy"] == "latest_overall"
    assert result["compatibility"] is None


def test_effective_settings_present():
    result = resolve("any", pinned_version="1.0.0")
    assert "effective_settings" in result
    assert result["effective_settings"]["git_timeout_seconds"] == 30


def test_compatibility_is_dict_not_boolean():
    compat = CompatibilityInfoObj("3.5.10", "pom.xml", "spring-boot-starter-parent")
    with (
        patch(
            "migration_oracle.paysafe.resolver.findit.lookup",
            return_value={"name": "my-lib", "codeRepoLink": "https://gitlab.example.com/a/b.git"},
        ),
        patch(
            "migration_oracle.paysafe.resolver.gitlab.list_tags",
            return_value=["3.5.10"],
        ),
        patch(
            "migration_oracle.paysafe.resolver.gitlab.fetch_framework_version",
            return_value=compat,
        ),
    ):
        result = resolve("my-lib", target_version="3.5.6")
    assert isinstance(result["compatibility"], dict)


def test_latest_with_known_compatibility_no_target():
    compat = CompatibilityInfoObj("3.5.10", "pom.xml", "spring-boot-starter-parent")
    with (
        patch(
            "migration_oracle.paysafe.resolver.findit.lookup",
            return_value={"name": "my-lib", "codeRepoLink": "https://gitlab.example.com/a/b.git"},
        ),
        patch(
            "migration_oracle.paysafe.resolver.gitlab.list_tags",
            return_value=["3.5.10"],
        ),
        patch(
            "migration_oracle.paysafe.resolver.gitlab.fetch_framework_version",
            return_value=compat,
        ),
        patch(
            "migration_oracle.paysafe.resolver.gitlab.detect_framework_at_head",
            return_value="spring-boot",
        ),
    ):
        result = resolve("my-lib", allow_latest_overall=True)

    assert result["status"] == "ok"
    assert result["selection_strategy"] == "latest_with_known_compatibility"
    assert result["framework_version"] == "3.5.10"


def test_latest_overall_no_target_unreadable_build_file():
    with (
        patch(
            "migration_oracle.paysafe.resolver.findit.lookup",
            return_value={"name": "my-lib", "codeRepoLink": "https://gitlab.example.com/a/b.git"},
        ),
        patch(
            "migration_oracle.paysafe.resolver.gitlab.list_tags",
            return_value=["3.5.10"],
        ),
        patch(
            "migration_oracle.paysafe.resolver.gitlab.fetch_framework_version",
            return_value=None,
        ),
        patch(
            "migration_oracle.paysafe.resolver.gitlab.detect_framework_at_head",
            return_value="spring-boot",
        ),
    ):
        result = resolve("my-lib", allow_latest_overall=True)

    assert result["status"] == "ok"
    assert result["selection_strategy"] == "latest_overall"
    assert result["framework_version"] is None


def test_allow_latest_overall_not_defaulted():
    compat = CompatibilityInfoObj("3.4.0", "pom.xml", "spring-boot-starter-parent")
    with (
        patch(
            "migration_oracle.paysafe.resolver.findit.lookup",
            return_value={"name": "my-lib", "codeRepoLink": "https://gitlab.example.com/a/b.git"},
        ),
        patch(
            "migration_oracle.paysafe.resolver.gitlab.list_tags",
            return_value=["3.4.0"],
        ),
        patch(
            "migration_oracle.paysafe.resolver.gitlab.fetch_framework_version",
            return_value=compat,
        ),
    ):
        result = resolve("my-lib", target_version="3.5.6")

    assert result["error"]["error_code"] == "no_compatible_version"


def test_framework_from_head_detection():
    compat = CompatibilityInfoObj("3.5.10", "pom.xml", "spring-boot-starter-parent")
    with (
        patch(
            "migration_oracle.paysafe.resolver.findit.lookup",
            return_value={"name": "my-lib", "codeRepoLink": "https://gitlab.example.com/a/b.git"},
        ),
        patch(
            "migration_oracle.paysafe.resolver.gitlab.list_tags",
            return_value=["3.5.10"],
        ),
        patch(
            "migration_oracle.paysafe.resolver.gitlab.fetch_framework_version",
            return_value=compat,
        ),
        patch(
            "migration_oracle.paysafe.resolver.gitlab.detect_framework_at_head",
            return_value="angular",
        ),
    ):
        result = resolve("my-lib", allow_latest_overall=True)

    assert result["framework"] == "angular"
