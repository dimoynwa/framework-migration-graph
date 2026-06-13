"""Tests for spec 011 US9: resolver returns structured error on FindIt timeout."""

from __future__ import annotations

import time
from concurrent.futures import TimeoutError as FuturesTimeout
from unittest.mock import MagicMock, patch


@patch("migration_oracle.paysafe.resolver.findit.lookup")
def test_timeout_returns_structured_findit_timeout_error(mock_lookup):
    """When findit.lookup hangs past the timeout, resolver returns findit_timeout error."""
    def _hang(*args, **kwargs):
        time.sleep(60)

    mock_lookup.side_effect = _hang

    from migration_oracle.paysafe.resolver import resolve

    start = time.monotonic()
    result = resolve("paysafe-wallet-switch")
    elapsed = time.monotonic() - start

    assert result["status"] == "error"
    assert result["error"]["error_code"] == "findit_timeout"
    assert result["error"]["recoverable"] is True
    assert elapsed < 15, f"Resolver hung for {elapsed:.1f}s — timeout not applied"


@patch("migration_oracle.paysafe.resolver.findit.lookup")
@patch("migration_oracle.paysafe.resolver.gitlab.list_tags")
@patch("migration_oracle.paysafe.resolver.gitlab.fetch_framework_version")
def test_normal_response_resolves(mock_ffv, mock_tags, mock_lookup):
    """When findit responds normally, resolution proceeds as before."""
    mock_lookup.return_value = {
        "codeRepoLink": "https://gitlab.example.com/paysafe/wallet-switch",
        "name": "paysafe-wallet-switch",
    }
    mock_tags.return_value = ["v1.2.0"]
    compat = MagicMock()
    compat.framework_version = "3.5.0"
    compat.to_dict.return_value = {"framework_version": "3.5.0", "compatible": True}
    mock_ffv.return_value = compat

    from migration_oracle.paysafe.resolver import resolve

    result = resolve("paysafe-wallet-switch", target_version="3.5.0")

    assert result["status"] == "ok"
    assert result["selected_tag"] == "v1.2.0"


@patch("migration_oracle.paysafe.resolver.findit.lookup")
def test_unregistered_service_returns_not_found(mock_lookup):
    """An unregistered service returns the service_not_found error (no timeout)."""
    from migration_oracle.paysafe.findit import _FindItError

    mock_lookup.side_effect = _FindItError(
        error_code="service_not_found",
        message="No service matched",
        details={},
    )

    from migration_oracle.paysafe.resolver import resolve

    result = resolve("unknown-service-xyz")

    assert result["status"] == "error"
    assert result["error"]["error_code"] == "service_not_found"
