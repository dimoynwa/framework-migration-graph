"""Unit tests for the FindIt client."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import httpx
import pytest
import respx

from migration_oracle.paysafe import findit
from migration_oracle.paysafe.findit import _FindItError, _cache


@pytest.fixture(autouse=True)
def _clear_cache():
    _cache.clear()
    yield
    _cache.clear()


SERVICES_URL = "https://findit-api.icd.paysafe.cloud/services"


def _services_payload(services: list[dict]) -> dict:
    return {"services": services}


@respx.mock
def test_exact_match_no_name_resolution():
    respx.get(SERVICES_URL).mock(
        return_value=httpx.Response(
            200,
            json=_services_payload(
                [{"name": "payment-service", "codeRepoLink": "https://gitlab.example.com/a.git"}]
            ),
        )
    )
    result = findit.lookup("payment-service")
    assert result["name"] == "payment-service"
    assert "name_resolution" not in result


@respx.mock
def test_case_insensitive_match():
    respx.get(SERVICES_URL).mock(
        return_value=httpx.Response(
            200,
            json=_services_payload(
                [{"name": "payment-service", "codeRepoLink": "https://gitlab.example.com/a.git"}]
            ),
        )
    )
    result = findit.lookup("Payment-Service")
    assert result["name_resolution"]["method"] == "case_insensitive"
    assert result["name_resolution"]["matched_name"] == "payment-service"


@respx.mock
def test_alphanumeric_normalized_match():
    respx.get(SERVICES_URL).mock(
        return_value=httpx.Response(
            200,
            json=_services_payload(
                [{"name": "payment-service", "codeRepoLink": "https://gitlab.example.com/a.git"}]
            ),
        )
    )
    result = findit.lookup("PaymentService")
    assert result["name_resolution"]["method"] == "alphanumeric_normalized"


@respx.mock
def test_fuzzy_match_above_threshold():
    respx.get(SERVICES_URL).mock(
        return_value=httpx.Response(
            200,
            json=_services_payload(
                [{"name": "payment-service", "codeRepoLink": "https://gitlab.example.com/a.git"}]
            ),
        )
    )
    with patch("migration_oracle.paysafe.findit.config.FINDIT_SERVICE_NAME_FUZZY_THRESHOLD", 0.5):
        result = findit.lookup("payment-servic")
    assert result["name_resolution"]["method"] == "fuzzy"
    assert isinstance(result["name_resolution"]["similarity"], float)
    assert isinstance(result["name_resolution"]["alternatives"], list)


@respx.mock
def test_fuzzy_match_below_threshold_service_not_found():
    respx.get(SERVICES_URL).mock(
        return_value=httpx.Response(
            200,
            json=_services_payload(
                [{"name": "payment-service", "codeRepoLink": "https://gitlab.example.com/a.git"}]
            ),
        )
    )
    with pytest.raises(_FindItError) as exc_info:
        findit.lookup("xyz")
    assert exc_info.value.error_code == "service_not_found"


@respx.mock
def test_cache_hit_within_30_days():
    route = respx.get(SERVICES_URL).mock(
        return_value=httpx.Response(
            200,
            json=_services_payload(
                [{"name": "payment-service", "codeRepoLink": "https://gitlab.example.com/a.git"}]
            ),
        )
    )
    findit.lookup("payment-service")
    findit.lookup("payment-service")
    assert route.call_count == 1


@respx.mock
def test_cache_miss_after_30_days():
    route = respx.get(SERVICES_URL).mock(
        return_value=httpx.Response(
            200,
            json=_services_payload(
                [{"name": "payment-service", "codeRepoLink": "https://gitlab.example.com/a.git"}]
            ),
        )
    )
    findit.lookup("payment-service")
    stale_time = datetime.now(timezone.utc) - timedelta(days=31)
    _cache["https://findit-api.icd.paysafe.cloud"] = (
        _cache["https://findit-api.icd.paysafe.cloud"][0],
        stale_time,
    )
    findit.lookup("payment-service")
    assert route.call_count == 2


@respx.mock
def test_http_timeout_error():
    respx.get(SERVICES_URL).mock(side_effect=httpx.TimeoutException("timeout"))
    with pytest.raises(_FindItError) as exc_info:
        findit.lookup("payment-service")
    assert exc_info.value.error_code == "http_timeout"


@respx.mock
def test_http_request_failed_error():
    respx.get(SERVICES_URL).mock(return_value=httpx.Response(500))
    with pytest.raises(_FindItError) as exc_info:
        findit.lookup("payment-service")
    assert exc_info.value.error_code == "http_request_failed"


@respx.mock
def test_retry_behavior_before_error():
    route = respx.get(SERVICES_URL).mock(side_effect=httpx.TimeoutException("timeout"))
    with pytest.raises(_FindItError):
        findit.lookup("payment-service")
    assert route.call_count == 3
