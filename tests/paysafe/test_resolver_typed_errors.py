"""Tests for typed RESOLUTION_FAILED responses from the Paysafe resolver (spec 013 T037)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from migration_oracle.paysafe.findit import _FindItError
from migration_oracle.paysafe.resolver import resolve


_FAKE_SERVICE = "paysafe-wallet-switch"


class TestAuthError:
    """RESOLUTION_FAILED with subStatus='auth_error'."""

    def test_http_401_from_findit_maps_to_auth_error(self):
        """HTTP 401 from FindIt produces subStatus='auth_error'."""
        with (
            patch.dict("os.environ", {"FINDIT_AUTH_TOKEN": "some-token"}),
            patch(
                "migration_oracle.paysafe.resolver.findit.get_repo_link",
                side_effect=_FindItError(
                    "http_request_failed",
                    "FindIt returned HTTP 401",
                    {"status_code": 401, "url": "https://findit/services"},
                ),
            ),
        ):
            result = resolve(_FAKE_SERVICE)

        assert result["status"] == "RESOLUTION_FAILED"
        assert result["subStatus"] == "auth_error"

    def test_absent_findit_auth_token_maps_to_auth_error(self):
        """Absent FINDIT_AUTH_TOKEN env var produces subStatus='auth_error' before any HTTP call."""
        with patch.dict("os.environ", {"FINDIT_AUTH_TOKEN": ""}):
            result = resolve(_FAKE_SERVICE)

        assert result["status"] == "RESOLUTION_FAILED"
        assert result["subStatus"] == "auth_error"
        steps_text = " ".join(result["remediationSteps"])
        assert "FINDIT_AUTH_TOKEN" in steps_text

    def test_http_403_from_findit_maps_to_auth_error(self):
        """HTTP 403 from FindIt also produces subStatus='auth_error'."""
        with (
            patch.dict("os.environ", {"FINDIT_AUTH_TOKEN": "some-token"}),
            patch(
                "migration_oracle.paysafe.resolver.findit.get_repo_link",
                side_effect=_FindItError(
                    "http_request_failed",
                    "FindIt returned HTTP 403",
                    {"status_code": 403, "url": "https://findit/services"},
                ),
            ),
        ):
            result = resolve(_FAKE_SERVICE)

        assert result["status"] == "RESOLUTION_FAILED"
        assert result["subStatus"] == "auth_error"


class TestTransportError:
    """RESOLUTION_FAILED with subStatus='transport_error'."""

    def test_futures_timeout_maps_to_transport_error(self, monkeypatch):
        """http_timeout from FindIt lookup maps to subStatus='transport_error'."""
        monkeypatch.setenv("FINDIT_AUTH_TOKEN", "some-token")

        with patch(
            "migration_oracle.paysafe.resolver.findit.get_repo_link",
            side_effect=_FindItError("http_timeout", "timed out"),
        ):
            result = resolve(_FAKE_SERVICE)

        assert result["status"] == "RESOLUTION_FAILED"
        assert result["subStatus"] == "transport_error"


class TestCommonFields:
    """Both auth_error and transport_error must populate unresolvedDependencies and fallbackInstructions."""

    def test_unresolved_dependencies_populated_auth_error(self):
        """unresolvedDependencies contains service_name for auth_error."""
        with (
            patch.dict("os.environ", {"FINDIT_AUTH_TOKEN": "tok"}),
            patch(
                "migration_oracle.paysafe.resolver.findit.get_repo_link",
                side_effect=_FindItError(
                    "http_request_failed",
                    "FindIt returned HTTP 401",
                    {"status_code": 401},
                ),
            ),
        ):
            result = resolve(_FAKE_SERVICE)

        assert result["status"] == "RESOLUTION_FAILED"
        assert _FAKE_SERVICE in result["unresolvedDependencies"]

    def test_fallback_instructions_present_auth_error(self):
        """fallbackInstructions is present for auth_error."""
        with (
            patch.dict("os.environ", {"FINDIT_AUTH_TOKEN": "tok"}),
            patch(
                "migration_oracle.paysafe.resolver.findit.get_repo_link",
                side_effect=_FindItError(
                    "http_request_failed",
                    "FindIt returned HTTP 401",
                    {"status_code": 401},
                ),
            ),
        ):
            result = resolve(_FAKE_SERVICE)

        assert result["status"] == "RESOLUTION_FAILED"
        assert "fallbackInstructions" in result
        assert result["fallbackInstructions"]

    def test_fallback_instructions_present_transport_error(self, monkeypatch):
        """fallbackInstructions is present for transport_error."""
        monkeypatch.setenv("FINDIT_AUTH_TOKEN", "some-token")

        with patch(
            "migration_oracle.paysafe.resolver.findit.get_repo_link",
            side_effect=_FindItError("http_timeout", "timed out"),
        ):
            result = resolve(_FAKE_SERVICE)

        assert result["status"] == "RESOLUTION_FAILED"
        assert "fallbackInstructions" in result
        assert result["fallbackInstructions"]


class TestBackwardCompat:
    """Existing error codes must remain unchanged."""

    def test_service_not_found_error_code_unchanged(self):
        """service_not_found must still produce status='error' with error_code (not RESOLUTION_FAILED)."""
        with (
            patch.dict("os.environ", {"FINDIT_AUTH_TOKEN": "tok"}),
            patch(
                "migration_oracle.paysafe.resolver.findit.get_repo_link",
                side_effect=_FindItError("service_not_found", "No service matched"),
            ),
        ):
            result = resolve(_FAKE_SERVICE)

        assert result["status"] == "error"
        assert result["error"]["error_code"] == "service_not_found"
