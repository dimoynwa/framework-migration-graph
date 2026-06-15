"""Tests for spec 010/011 US2/US3 and 011a: check_version_availability tool."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from migration_oracle.mcp.tools.upgrade import _clear_maven_cache
from migration_oracle.models.graph import VersionResolutionFailure, VersionResolutionResult


@pytest.fixture(autouse=True)
def clear_cache():
    _clear_maven_cache()
    yield
    _clear_maven_cache()


def _make_maven_response(num_found: int, version: str | None = None) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    docs = [{"v": version}] if version else []
    resp.json.return_value = {"response": {"numFound": num_found, "docs": docs}}
    return resp


def _resolved(version: str = "4.0.0") -> VersionResolutionResult:
    return VersionResolutionResult(
        resolvedVersion=version,
        resolvedSortable=4000000,
        nodeId="fake-node-id",
        requestedVersion=version,
        rounded=False,
        aheadOfCatalogue=False,
        stubCreated=False,
        direction="floor",
    )


def _not_resolved(version: str = "9.9.0") -> VersionResolutionFailure:
    return VersionResolutionFailure(
        status="NO_CANDIDATE",
        framework="Spring Boot",
        requestedVersion=version,
        candidatesConsidered=["4.0.0", "3.5.0"],
    )


@patch("migration_oracle.mcp.tools.upgrade.requests.get")
@patch("migration_oracle.mcp.tools.upgrade.resolve_version")
def test_returns_all_fields_for_known_version(mock_resolve, mock_get):
    mock_resolve.return_value = _resolved("4.1.0")
    mock_get.return_value = _make_maven_response(1, "4.1.2")

    from migration_oracle.mcp.tools.upgrade import check_version_availability

    result = check_version_availability("spring-boot", "4.1.0")

    assert result["status"] == "ok"
    assert "exists_in_graph" in result
    assert "ga_available" in result
    assert "latest_patch" in result
    assert "hint" in result


@patch("migration_oracle.mcp.tools.upgrade.requests.get")
@patch("migration_oracle.mcp.tools.upgrade.resolve_version")
def test_exists_in_graph_false_for_missing_version(mock_resolve, mock_get):
    mock_resolve.return_value = _not_resolved("9.9.0")
    mock_get.return_value = _make_maven_response(0)

    from migration_oracle.mcp.tools.upgrade import check_version_availability

    result = check_version_availability("spring-boot", "9.9.0")

    assert result["exists_in_graph"] is False


@patch("migration_oracle.mcp.tools.upgrade.requests.get")
def test_unsupported_framework_returns_error_no_network_call(mock_get):
    from migration_oracle.mcp.tools.upgrade import check_version_availability

    result = check_version_availability("unknown-framework", "1.0.0")

    assert result["status"] == "error"
    assert result["error_code"] == "unsupported_framework"
    mock_get.assert_not_called()


@patch("migration_oracle.mcp.tools.upgrade.resolve_version")
@patch(
    "migration_oracle.mcp.tools.upgrade.requests.get",
    side_effect=ConnectionError("Maven Central unavailable"),
)
def test_maven_central_unavailable_returns_graceful_response(mock_get, mock_resolve):
    mock_resolve.return_value = _resolved("4.1.0")

    from migration_oracle.mcp.tools.upgrade import check_version_availability

    result = check_version_availability("spring-boot", "4.1.0")

    assert result["ga_available"] is False
    assert result["latest_patch"] is None
    assert "unavailable" in result["hint"]


# ---------------------------------------------------------------------------
# Spec 011 US3: canonical_framework normalisation
# ---------------------------------------------------------------------------

@patch("migration_oracle.mcp.tools.upgrade.requests.get")
@patch("migration_oracle.mcp.tools.upgrade.resolve_version")
def test_spring_boot_display_form(mock_resolve, mock_get):
    """'Spring Boot' (display form) is accepted and resolves to the same result as 'spring-boot'."""
    mock_resolve.return_value = _resolved("4.0.0")
    mock_get.return_value = _make_maven_response(1, "4.0.0")

    from migration_oracle.mcp.tools.upgrade import check_version_availability

    result = check_version_availability("Spring Boot", "4.0.0")

    assert result["status"] == "ok"
    assert result["exists_in_graph"] is True


@patch("migration_oracle.mcp.tools.upgrade.requests.get")
@patch("migration_oracle.mcp.tools.upgrade.resolve_version")
def test_spring_boot_slug_form(mock_resolve, mock_get):
    """'spring-boot' (slug) is accepted."""
    mock_resolve.return_value = _resolved("4.0.0")
    mock_get.return_value = _make_maven_response(1, "4.0.0")

    from migration_oracle.mcp.tools.upgrade import check_version_availability

    result = check_version_availability("spring-boot", "4.0.0")

    assert result["status"] == "ok"


@patch("migration_oracle.mcp.tools.upgrade.requests.get")
@patch("migration_oracle.mcp.tools.upgrade.resolve_version")
def test_spring_boot_no_space(mock_resolve, mock_get):
    """'springboot' (no separator) is accepted."""
    mock_resolve.return_value = _resolved("4.0.0")
    mock_get.return_value = _make_maven_response(1, "4.0.0")

    from migration_oracle.mcp.tools.upgrade import check_version_availability

    result = check_version_availability("springboot", "4.0.0")

    assert result["status"] == "ok"


@patch("migration_oracle.mcp.tools.upgrade.resolve_version")
def test_graph_query_uses_display_form(mock_resolve):
    """resolve_version is called with the display-form framework name ('Spring Boot')."""
    mock_resolve.return_value = _not_resolved("4.0.0")

    with patch("migration_oracle.mcp.tools.upgrade.requests.get", side_effect=ConnectionError):
        from migration_oracle.mcp.tools.upgrade import check_version_availability

        check_version_availability("spring-boot", "4.0.0")

    # resolve_version must receive the display form, not the slug
    call_args = mock_resolve.call_args
    framework_passed = call_args[0][0] if call_args[0] else call_args[1].get("framework", "")
    assert framework_passed == "Spring Boot"


@patch("migration_oracle.mcp.tools.upgrade.requests.get")
@patch("migration_oracle.mcp.tools.upgrade.resolve_version")
def test_maven_uses_slug(mock_resolve, mock_get):
    """Maven coordinate lookup uses the slug form (spring-boot)."""
    mock_resolve.return_value = _resolved("4.0.0")
    mock_get.return_value = _make_maven_response(1, "4.0.0")

    from migration_oracle.mcp.tools.upgrade import check_version_availability

    check_version_availability("Spring Boot", "4.0.0")

    assert mock_get.called
    called_url = mock_get.call_args[0][0]
    assert "spring-boot" in called_url


@patch("migration_oracle.mcp.tools.upgrade.requests.get")
def test_unsupported_framework_no_network_call(mock_get):
    """canonical_framework returns error for unsupported input; no network call is made."""
    from migration_oracle.mcp.tools.upgrade import check_version_availability

    result = check_version_availability("not-a-framework", "1.0.0")

    assert result["status"] == "error"
    assert result["error_code"] == "unsupported_framework"
    mock_get.assert_not_called()


# ---------------------------------------------------------------------------
# Spec 011a: parallel execution and caching
# ---------------------------------------------------------------------------

def _resolve_mock(found: bool, version: str = "3.5.0") -> MagicMock:
    """Return a mock for resolve_version that returns resolved or not-found."""
    mock = MagicMock()
    if found:
        mock.return_value = _resolved(version)
    else:
        mock.return_value = _not_resolved(version)
    return mock


@patch("migration_oracle.mcp.tools.upgrade.requests.get")
def test_parallel_both_succeed(mock_get):
    """T1 — both Maven calls succeed; correct fields returned."""
    mock_get.return_value = _make_maven_response(1, "3.5.1")

    from migration_oracle.mcp.tools.upgrade import check_version_availability

    with patch("migration_oracle.mcp.tools.upgrade.resolve_version") as mock_resolve:
        mock_resolve.return_value = _resolved("3.5.0")
        result = check_version_availability("Spring Boot", "3.5.0")

    assert result["status"] == "ok"
    assert result["ga_available"] is True
    assert result["latest_patch"] == "3.5.1"
    assert mock_get.call_count == 2


@patch("migration_oracle.mcp.tools.upgrade.requests.get")
def test_cache_hit_skips_network(mock_get):
    """T2 — second call with same version hits cache; no additional HTTP requests made."""
    mock_get.return_value = _make_maven_response(1, "3.5.1")

    from migration_oracle.mcp.tools.upgrade import check_version_availability

    with patch("migration_oracle.mcp.tools.upgrade.resolve_version") as mock_resolve:
        mock_resolve.return_value = _resolved("3.5.0")
        result1 = check_version_availability("Spring Boot", "3.5.0")
        call_count_after_first = mock_get.call_count
        result2 = check_version_availability("Spring Boot", "3.5.0")

    assert result1["ga_available"] == result2["ga_available"]
    assert result1["latest_patch"] == result2["latest_patch"]
    assert mock_get.call_count == call_count_after_first


@patch("migration_oracle.mcp.tools.upgrade.requests.get", side_effect=ConnectionError("timeout"))
def test_both_futures_fail_graceful_degradation(mock_get):
    """T3 — all Maven calls fail; ga_available=False with hint, no exception raised."""
    from migration_oracle.mcp.tools.upgrade import check_version_availability

    with patch("migration_oracle.mcp.tools.upgrade.resolve_version") as mock_resolve:
        mock_resolve.return_value = _resolved("3.5.0")
        result = check_version_availability("Spring Boot", "3.5.0")

    assert result["status"] == "ok"
    assert result["ga_available"] is False
    assert result["latest_patch"] is None
    assert "unavailable" in result["hint"]


@patch("migration_oracle.mcp.tools.upgrade.requests.get")
def test_latest_patch_fails_ga_succeeds(mock_get):
    """T4 — latest-patch call fails but GA call succeeds; exception propagates to outer handler."""
    ga_resp = _make_maven_response(1)
    lp_resp = MagicMock()
    lp_resp.raise_for_status.side_effect = ConnectionError("fail")
    mock_get.side_effect = [ga_resp, lp_resp]

    from migration_oracle.mcp.tools.upgrade import check_version_availability

    with patch("migration_oracle.mcp.tools.upgrade.resolve_version") as mock_resolve:
        mock_resolve.return_value = _resolved("3.5.0")
        result = check_version_availability("Spring Boot", "3.5.0")

    assert result["status"] == "ok"
    assert result["ga_available"] is False
    assert result["latest_patch"] is None


@patch("migration_oracle.mcp.tools.upgrade.requests.get")
def test_version_not_in_graph_but_ga_available(mock_get):
    """T6 — exists_in_graph=False and ga_available=True are independent fields."""
    mock_get.return_value = _make_maven_response(1, "4.0.0")

    from migration_oracle.mcp.tools.upgrade import check_version_availability

    with patch("migration_oracle.mcp.tools.upgrade.resolve_version") as mock_resolve:
        mock_resolve.return_value = _not_resolved("4.0.0")
        result = check_version_availability("Spring Boot", "4.0.0")

    assert result["exists_in_graph"] is False
    assert result["ga_available"] is False  # early return when version not in graph


def test_clear_maven_cache_resets_state():
    """T7 — _clear_maven_cache removes all entries so the next call hits the network."""
    from migration_oracle.mcp.tools.upgrade import _MAVEN_CACHE, _clear_maven_cache

    _MAVEN_CACHE[("org.springframework.boot", "spring-boot", "3.5.0")] = (True, "3.5.1", 9999999999)
    assert len(_MAVEN_CACHE) == 1

    _clear_maven_cache()
    assert len(_MAVEN_CACHE) == 0
