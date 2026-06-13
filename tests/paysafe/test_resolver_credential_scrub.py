"""Tests for spec 010 US6 (credential scrub) and US7 (Artifactory fallback)."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from migration_oracle.paysafe.resolver import _build_error, _scrub


# ---------------------------------------------------------------------------
# US6 — Credential scrub in _build_error
# ---------------------------------------------------------------------------

def test_scrubs_oauth2_token():
    result = _build_error(
        "test_error",
        "oauth2:SECRETTOKEN@gitlab.example.com/repo",
        recoverable=False,
        actionable_hint="fix it",
    )
    msg = result["error"]["message"]
    assert "SECRETTOKEN" not in msg
    assert "<redacted>@" in msg


def test_scrubs_basic_auth():
    result = _build_error(
        "test_error",
        "https://user:pass@host/path failed",
        recoverable=False,
        actionable_hint="fix it",
    )
    msg = result["error"]["message"]
    assert "pass" not in msg
    assert "<redacted>@" in msg


def test_clean_message_unchanged():
    result = _build_error(
        "test_error",
        "something went wrong",
        recoverable=False,
        actionable_hint="fix it",
    )
    assert result["error"]["message"] == "something went wrong"


# ---------------------------------------------------------------------------
# US7 — Artifactory fallback
# ---------------------------------------------------------------------------

@patch("migration_oracle.paysafe.gitlab.fetch_framework_version", return_value=None)
@patch("migration_oracle.paysafe.gitlab.detect_framework_at_head", return_value=None)
@patch("migration_oracle.paysafe.resolver.requests.get")
@patch("migration_oracle.paysafe.gitlab.list_tags")
@patch("migration_oracle.paysafe.findit.lookup")
def test_artifactory_fallback_called(
    mock_findit, mock_list_tags, mock_requests_get, mock_detect, mock_fetch
):
    from migration_oracle.paysafe.gitlab import _GitError

    mock_findit.return_value = {"codeRepoLink": "https://gitlab.example.com/org/my-service"}
    mock_list_tags.side_effect = _GitError("git_ls_remote_failed", "git failed")

    art_response = MagicMock()
    art_response.ok = True
    art_response.text = "2.3.1"
    mock_requests_get.return_value = art_response

    from migration_oracle.paysafe.resolver import resolve

    with patch.dict(os.environ, {"ARTIFACTORY_BASE_URL": "https://art.example.com"}):
        result = resolve("my-service")

    assert result["status"] == "ok"
    mock_requests_get.assert_called_once()
    call_args = mock_requests_get.call_args
    url_called = call_args[0][0] if call_args[0] else call_args[1].get("url", "")
    assert "a=" in url_called
    assert "Authorization" not in (call_args[1] or {})


@patch("migration_oracle.paysafe.resolver.requests.get")
@patch("migration_oracle.paysafe.gitlab.list_tags")
@patch("migration_oracle.paysafe.findit.lookup")
def test_no_fallback_without_env_var(mock_findit, mock_list_tags, mock_requests_get):
    from migration_oracle.paysafe.gitlab import _GitError

    mock_findit.return_value = {"codeRepoLink": "https://gitlab.example.com/org/my-service"}
    mock_list_tags.side_effect = _GitError("git_ls_remote_failed", "git failed")

    from migration_oracle.paysafe.resolver import resolve

    env_without_artifactory = {k: v for k, v in os.environ.items() if k != "ARTIFACTORY_BASE_URL"}
    with patch.dict(os.environ, env_without_artifactory, clear=True):
        result = resolve("my-service")

    assert result["status"] == "error"
    mock_requests_get.assert_not_called()
