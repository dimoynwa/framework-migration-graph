"""Integration-style tests for the Paysafe resolver."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from migration_oracle.paysafe.findit import _FindItError
from migration_oracle.paysafe.gitlab import _GitError
from migration_oracle.paysafe.resolver import resolve


def _repo_link(url: str = "https://gitlab.example.com/a/b.git"):
    return patch(
        "migration_oracle.paysafe.findit.get_repo_link",
        return_value=url,
    )


def test_pinned_mode_short_circuit():
    with (
        patch("migration_oracle.paysafe.findit.get_repo_link") as mock_lookup,
        patch("migration_oracle.paysafe.resolver.gitlab.list_tags") as mock_tags,
    ):
        mock_lookup.side_effect = AssertionError("get_repo_link must not be called")
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
    assert result["effective_settings"]["max_tags_returned"] == 15


def test_error_invalid_service_name():
    result = resolve("   ")
    assert result["status"] == "error"
    assert result["error"]["error_code"] == "invalid_service_name"


def test_error_service_not_found():
    with patch(
        "migration_oracle.paysafe.findit.get_repo_link",
        side_effect=_FindItError("service_not_found", "not found"),
    ):
        result = resolve("missing-lib")
    assert result["status"] == "error"
    assert result["error"]["error_code"] == "service_not_found"


def test_error_no_repo_url():
    with patch(
        "migration_oracle.paysafe.findit.get_repo_link",
        return_value=None,
    ):
        result = resolve("my-lib", target_version="3.5.6")
    assert result["status"] == "error"
    assert result["error"]["error_code"] == "no_repo_url"


def test_error_no_tags_found():
    with (
        _repo_link(),
        patch(
            "migration_oracle.paysafe.resolver.gitlab.list_tags",
            side_effect=_GitError("no_tags_found"),
        ),
    ):
        result = resolve("my-lib", target_version="3.5.6")
    assert result["status"] == "error"
    assert result["error"]["error_code"] == "no_tags_found"


@pytest.mark.parametrize(
    "removed_test_name",
    [
        "no_compatible_version",
        "compatibility_unknown",
    ],
)
def test_removed_compatibility_errors(removed_test_name):
    """removed: compatibility loop eliminated in resolver v2"""
    pytest.skip(f"{removed_test_name} is unreachable in resolver v2")


def test_error_http_timeout():
    with patch(
        "migration_oracle.paysafe.findit.get_repo_link",
        side_effect=_FindItError("http_timeout", "timed out"),
    ):
        result = resolve("my-lib", target_version="3.5.6")
    assert result["status"] == "RESOLUTION_FAILED"
    assert result["subStatus"] == "transport_error"


def test_error_http_request_failed():
    with patch(
        "migration_oracle.paysafe.findit.get_repo_link",
        side_effect=_FindItError("http_request_failed", "failed"),
    ):
        result = resolve("my-lib", target_version="3.5.6")
    assert result["status"] == "error"
    assert result["error"]["error_code"] == "http_request_failed"


def test_latest_tag_happy_path():
    with (
        _repo_link("https://gitlab.example.com/payment/my-lib.git"),
        patch(
            "migration_oracle.paysafe.resolver.gitlab.list_tags",
            return_value=["3.5.10", "3.4.0"],
        ),
        patch(
            "migration_oracle.paysafe.resolver.gitlab.fetch_framework_version",
        ) as mock_fetch,
    ):
        result = resolve("my-lib", target_version="3.5.6", framework="spring-boot")

    assert result["status"] == "ok"
    assert result["selected_tag"] == "3.5.10"
    assert result["selection_strategy"] == "latest_overall"
    assert result["compatibility"] is None
    assert result["framework_version"] is None
    mock_fetch.assert_not_called()
    assert result["code_repo_link"] == "https://gitlab.example.com/payment/my-lib.git"


def test_no_target_returns_latest_tag_only():
    with (
        _repo_link(),
        patch(
            "migration_oracle.paysafe.resolver.gitlab.list_tags",
            return_value=["3.5.10", "3.4.0", "3.3.0"],
        ),
        patch(
            "migration_oracle.paysafe.resolver.gitlab.fetch_framework_version",
        ) as mock_fetch,
        patch(
            "migration_oracle.paysafe.resolver.gitlab.detect_framework_at_head",
        ) as mock_detect,
    ):
        result = resolve("my-lib")

    assert result["status"] == "ok"
    assert result["selected_tag"] == "3.5.10"
    mock_fetch.assert_not_called()
    mock_detect.assert_not_called()


def test_latest_overall_with_target_version():
    with (
        _repo_link(),
        patch(
            "migration_oracle.paysafe.resolver.gitlab.list_tags",
            return_value=["3.4.0"],
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


def test_compatibility_is_always_null_with_target():
    with (
        _repo_link(),
        patch(
            "migration_oracle.paysafe.resolver.gitlab.list_tags",
            return_value=["3.5.10"],
        ),
    ):
        result = resolve("my-lib", target_version="3.5.6")
    assert result["compatibility"] is None


def test_latest_overall_no_target():
    with (
        _repo_link(),
        patch(
            "migration_oracle.paysafe.resolver.gitlab.list_tags",
            return_value=["3.5.10"],
        ),
    ):
        result = resolve("my-lib", allow_latest_overall=True)

    assert result["status"] == "ok"
    assert result["selection_strategy"] == "latest_overall"
    assert result["framework_version"] is None


def test_target_version_does_not_block_latest():
    with (
        _repo_link(),
        patch(
            "migration_oracle.paysafe.resolver.gitlab.list_tags",
            return_value=["3.4.0"],
        ),
    ):
        result = resolve("my-lib", target_version="3.5.6")

    assert result["status"] == "ok"
    assert result["selection_strategy"] == "latest_overall"


def test_framework_param_passthrough():
    with (
        _repo_link(),
        patch(
            "migration_oracle.paysafe.resolver.gitlab.list_tags",
            return_value=["3.5.10"],
        ),
    ):
        result = resolve("my-lib", framework="angular")

    assert result["framework"] == "angular"
