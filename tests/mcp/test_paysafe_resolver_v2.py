"""Tests for Paysafe resolver v2 — startup cache and latest-only resolution."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from migration_oracle.paysafe import findit
from migration_oracle.paysafe.findit import _FindItError
from migration_oracle.paysafe.gitlab import _GitError
from migration_oracle.paysafe.resolver import resolve


@pytest.fixture(autouse=True)
def _findit_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FINDIT_AUTH_TOKEN", "test-token")
    monkeypatch.setenv("FINDIT_CACHE_STRATEGY", "none")


@pytest.fixture
def static_registry_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    registry = tmp_path / "static_registry.json"

    def _write(data: dict) -> Path:
        registry.write_text(json.dumps(data), encoding="utf-8")
        monkeypatch.setattr(findit, "_load_static_registry", lambda: json.loads(registry.read_text()))
        return registry

    return _write


def _warm_gitlab(tags: list[str] | None = None):
    if tags is None:
        tags = ["2.0.0"]
    return patch("migration_oracle.paysafe.resolver.gitlab.list_tags", return_value=tags)


def test_static_registry_loaded_on_startup(static_registry_file):
    static_registry_file(
        {
            "payment-service": "https://gitlab.example.com/platform/payment-service",
            "risk-engine": "https://gitlab.example.com/platform/risk-engine",
        }
    )
    findit._REPO_CACHE.clear()
    findit.populate_cache()
    assert len(findit._REPO_CACHE) >= 1
    assert findit._REPO_CACHE["payment-service"] == (
        "https://gitlab.example.com/platform/payment-service"
    )


def test_static_registry_missing_raises(static_registry_file):
    findit._REPO_CACHE.clear()

    def _missing():
        raise FileNotFoundError("missing")

    with patch.object(findit, "_load_static_registry", side_effect=_missing):
        with pytest.raises(FileNotFoundError):
            findit.populate_cache()


def test_static_registry_invalid_json_raises(static_registry_file, tmp_path: Path):
    bad = tmp_path / "static_registry.json"
    bad.write_text("not json", encoding="utf-8")
    findit._REPO_CACHE.clear()

    def _bad_json():
        return json.loads(bad.read_text())

    with patch.object(findit, "_load_static_registry", side_effect=_bad_json):
        with pytest.raises(json.JSONDecodeError):
            findit.populate_cache()


def test_populate_cache_timeout(static_registry_file, monkeypatch: pytest.MonkeyPatch):
    static_registry_file({"payment-service": "https://static.example.com/payment-service"})
    findit._REPO_CACHE.clear()
    monkeypatch.setattr(findit.config, "FINDIT_CACHE_STRATEGY", "bulk")

    def _slow():
        time.sleep(60)

    with patch.object(findit, "_load_findit_bulk", side_effect=_slow):
        start = time.monotonic()
        findit.populate_cache(timeout_seconds=0.1)
        elapsed = time.monotonic() - start
    assert elapsed < 2
    assert findit._REPO_CACHE["payment-service"] == "https://static.example.com/payment-service"


def test_server_starts_when_findit_unreachable(static_registry_file, monkeypatch: pytest.MonkeyPatch):
    static_registry_file({"payment-service": "https://static.example.com/payment-service"})
    findit._REPO_CACHE.clear()
    monkeypatch.setattr(findit.config, "FINDIT_CACHE_STRATEGY", "bulk")

    with patch.object(findit, "_load_findit_bulk", side_effect=Exception("network error")):
        findit.populate_cache()
    assert findit._REPO_CACHE["payment-service"] == "https://static.example.com/payment-service"


def test_findit_overwrites_static_on_conflict(static_registry_file, monkeypatch: pytest.MonkeyPatch):
    static_registry_file({"payment-service": "https://static.example.com/payment-service"})
    findit._REPO_CACHE.clear()
    monkeypatch.setattr(findit.config, "FINDIT_CACHE_STRATEGY", "bulk")

    findit_data = {"payment-service": "https://findit.example.com/payment-service"}
    with patch.object(findit, "_load_findit_bulk", return_value=findit_data):
        findit.populate_cache()
    assert findit._REPO_CACHE["payment-service"] == "https://findit.example.com/payment-service"


def test_static_entry_kept_when_findit_absent(static_registry_file, monkeypatch: pytest.MonkeyPatch):
    static_registry_file({"payment-service": "https://static.example.com/payment-service"})
    findit._REPO_CACHE.clear()
    monkeypatch.setattr(findit.config, "FINDIT_CACHE_STRATEGY", "bulk")

    with patch.object(findit, "_load_findit_bulk", return_value={}):
        findit.populate_cache()
    assert findit._REPO_CACHE["payment-service"] == "https://static.example.com/payment-service"


def test_cache_hit_skips_findit_lookup():
    findit._REPO_CACHE.clear()
    findit._REPO_CACHE["payment-service"] = "https://gitlab.paysafe.com/platform/payment-service"
    with (
        patch("migration_oracle.paysafe.findit.lookup") as mock_lookup,
        _warm_gitlab(["2.0.0"]),
    ):
        result = resolve("payment-service")
    mock_lookup.assert_not_called()
    assert result["status"] == "ok"


def test_cache_miss_falls_back_to_lookup():
    findit._REPO_CACHE.clear()
    with (
        patch(
            "migration_oracle.paysafe.findit.lookup",
            return_value={"codeRepoLink": "https://gitlab.example.com/new-service"},
        ) as mock_lookup,
        _warm_gitlab(["1.0.0"]),
    ):
        result = resolve("new-service")
    mock_lookup.assert_called_once()
    assert result["status"] == "ok"
    assert result["code_repo_link"] == "https://gitlab.example.com/new-service"


def test_cache_miss_fallback_warms_cache():
    findit._REPO_CACHE.clear()
    with (
        patch(
            "migration_oracle.paysafe.findit.lookup",
            return_value={"codeRepoLink": "https://gitlab.example.com/new-service"},
        ) as mock_lookup,
        _warm_gitlab(["1.0.0"]),
    ):
        resolve("new-service")
        resolve("new-service")
    mock_lookup.assert_called_once()


def test_returns_latest_tag():
    findit._REPO_CACHE.clear()
    findit._REPO_CACHE["payment-service"] = "https://gitlab.example.com/payment-service"
    with _warm_gitlab(["2.0.0", "1.9.0", "1.8.5"]):
        result = resolve("payment-service")
    assert result["selected_version"] == "2.0.0"


def test_selection_strategy_is_always_latest_overall():
    findit._REPO_CACHE.clear()
    findit._REPO_CACHE["payment-service"] = "https://gitlab.example.com/payment-service"
    with _warm_gitlab(["2.0.0"]):
        result_with = resolve("payment-service", target_version="3.2.0")
        result_without = resolve("payment-service", target_version=None)
    assert result_with["selection_strategy"] == "latest_overall"
    assert result_without["selection_strategy"] == "latest_overall"


def test_compatibility_is_null():
    findit._REPO_CACHE.clear()
    findit._REPO_CACHE["payment-service"] = "https://gitlab.example.com/payment-service"
    with _warm_gitlab(["2.0.0"]):
        result = resolve("payment-service")
    assert result["compatibility"] is None


def test_framework_version_is_null():
    findit._REPO_CACHE.clear()
    findit._REPO_CACHE["payment-service"] = "https://gitlab.example.com/payment-service"
    with _warm_gitlab(["2.0.0"]):
        result = resolve("payment-service")
    assert result["framework_version"] is None


def test_target_version_ignored():
    findit._REPO_CACHE.clear()
    findit._REPO_CACHE["payment-service"] = "https://gitlab.example.com/payment-service"
    with _warm_gitlab(["2.0.0"]):
        r1 = resolve("payment-service", target_version=None)
        r2 = resolve("payment-service", target_version="2.7")
    assert r1["selected_version"] == r2["selected_version"]
    assert r1["status"] == r2["status"] == "ok"


def test_pinned_version_still_works():
    with (
        patch("migration_oracle.paysafe.findit.get_repo_link") as mock_cache,
        patch("migration_oracle.paysafe.resolver.gitlab.list_tags") as mock_tags,
    ):
        result = resolve(
            "payment-service",
            pinned_version="1.5.0",
            pinned_tag="v1.5.0",
        )
    assert result["selected_version"] == "1.5.0"
    assert result["selection_strategy"] == "pinned"
    mock_cache.assert_not_called()
    mock_tags.assert_not_called()


def test_invalid_service_name():
    with patch("migration_oracle.paysafe.findit.get_repo_link") as mock_cache:
        result = resolve("")
    assert result["status"] == "error"
    assert result["error"]["error_code"] == "invalid_service_name"
    mock_cache.assert_not_called()


def test_no_repo_url_error():
    findit._REPO_CACHE.clear()
    with patch("migration_oracle.paysafe.findit.lookup", return_value={}):
        result = resolve("unknown-service")
    assert result["error"]["error_code"] == "no_repo_url"
    assert "static_registry.json" in result["error"]["actionable_hint"]


def test_no_tags_found_error():
    findit._REPO_CACHE.clear()
    findit._REPO_CACHE["payment-service"] = "https://gitlab.example.com/payment-service"
    with patch(
        "migration_oracle.paysafe.resolver.gitlab.list_tags",
        side_effect=_GitError("no_tags_found"),
    ):
        result = resolve("payment-service")
    assert result["error"]["error_code"] == "no_tags_found"


def test_fetch_framework_version_never_called():
    findit._REPO_CACHE.clear()
    findit._REPO_CACHE["payment-service"] = "https://gitlab.example.com/payment-service"
    with (
        _warm_gitlab(["2.0.0"]),
        patch("migration_oracle.paysafe.gitlab.fetch_framework_version") as mock_ffv,
    ):
        resolve("payment-service", target_version="3.2.0", allow_latest_overall=False)
        resolve("payment-service", allow_latest_overall=True)
    mock_ffv.assert_not_called()
