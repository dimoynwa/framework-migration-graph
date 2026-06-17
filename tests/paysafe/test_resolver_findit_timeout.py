"""Tests for spec 011 US9: resolver returns structured error on FindIt timeout."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _set_findit_token(monkeypatch):
    monkeypatch.setenv("FINDIT_AUTH_TOKEN", "test-token")


@patch("migration_oracle.paysafe.findit.get_repo_link")
def test_timeout_returns_structured_findit_timeout_error(mock_get_repo_link):
    """When get_repo_link raises http_timeout, resolver returns transport_error."""
    from migration_oracle.paysafe.findit import _FindItError
    from migration_oracle.paysafe.resolver import resolve

    mock_get_repo_link.side_effect = _FindItError("http_timeout", "timed out")

    result = resolve("paysafe-wallet-switch")

    assert result["status"] == "RESOLUTION_FAILED"
    assert result["subStatus"] == "transport_error"


@patch("migration_oracle.paysafe.findit.get_repo_link")
@patch("migration_oracle.paysafe.resolver.gitlab.list_tags")
@patch("migration_oracle.paysafe.resolver.gitlab.fetch_framework_version")
def test_normal_response_resolves(mock_ffv, mock_tags, mock_get_repo_link):
    """When cache returns a repo link, resolution returns latest tag in v2."""
    mock_get_repo_link.return_value = "https://gitlab.example.com/paysafe/wallet-switch"
    mock_tags.return_value = ["v1.2.0"]

    from migration_oracle.paysafe.resolver import resolve

    result = resolve("paysafe-wallet-switch", target_version="3.5.0")

    assert result["status"] == "ok"
    assert result["selected_tag"] == "v1.2.0"
    assert result["selection_strategy"] == "latest_overall"
    mock_ffv.assert_not_called()


@patch("migration_oracle.paysafe.findit.get_repo_link")
def test_unregistered_service_returns_not_found(mock_get_repo_link):
    """An unregistered service returns the service_not_found error (no timeout)."""
    from migration_oracle.paysafe.findit import _FindItError
    from migration_oracle.paysafe.resolver import resolve

    mock_get_repo_link.side_effect = _FindItError(
        error_code="service_not_found",
        message="No service matched",
        details={},
    )

    result = resolve("unknown-service-xyz")

    assert result["status"] == "error"
    assert result["error"]["error_code"] == "service_not_found"
