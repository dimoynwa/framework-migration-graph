"""FindIt HTTP client with 30-day cache and four-level name matching."""

from __future__ import annotations

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from datetime import datetime, timezone
from pathlib import Path

import httpx
from rapidfuzz import fuzz

from migration_oracle import config
from migration_oracle.paysafe._types import NameResolution

logger = logging.getLogger(__name__)

_cache: dict[str, tuple[list[dict], datetime]] = {}
_REPO_CACHE: dict[str, str] = {}

_HTTP_TIMEOUT_SECONDS = 10
_RETRIES = 2
_BACKOFF_SECONDS = [1.0, 3.0]
_CACHE_TTL_DAYS = 30


class _FindItError(Exception):
    def __init__(self, error_code: str, message: str = "", details: dict | None = None) -> None:
        self.error_code = error_code
        self.message = message
        self.details = details or {}
        super().__init__(message or error_code)


def _normalize_alphanumeric(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _normalise(name: str) -> str:
    """Return the best cache key for a service name lookup."""
    if name in _REPO_CACHE:
        return name
    lower = name.lower()
    if lower in _REPO_CACHE:
        return lower
    alpha = _normalize_alphanumeric(name)
    if alpha in _REPO_CACHE:
        return alpha
    return name


def _cache_key_variants(service_name: str) -> set[str]:
    """All normalised key forms inserted at load time for maximum hit rate."""
    variants = {service_name, service_name.lower(), _normalize_alphanumeric(service_name)}
    return {variant for variant in variants if variant}


def _write_cache_entries(service_name: str, code_repo_link: str) -> None:
    for key in _cache_key_variants(service_name):
        _REPO_CACHE[key] = code_repo_link


def _load_static_registry() -> dict[str, str]:
    """Load static_registry.json. Raises FileNotFoundError or json.JSONDecodeError on failure."""
    path = Path(__file__).parent / "static_registry.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _services_to_repo_map(services: list[dict]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for svc in services:
        name = svc.get("name", "")
        link = svc.get("codeRepoLink")
        if name and link:
            mapping[name] = link
    return mapping


def _load_findit_bulk() -> dict[str, str]:
    """Single GET /services call. Raises _FindItError on failure."""
    # TODO: implement once endpoint is confirmed
    raise NotImplementedError(
        "FindIt bulk endpoint not yet confirmed — set FINDIT_CACHE_STRATEGY=none"
    )


def _load_findit_paginated() -> dict[str, str]:
    """Paginated GET /services?page=N loop. Raises _FindItError on failure."""
    # TODO: implement once endpoint is confirmed
    raise NotImplementedError(
        "FindIt bulk endpoint not yet confirmed — set FINDIT_CACHE_STRATEGY=none"
    )


def populate_cache(timeout_seconds: float | None = None) -> None:
    """
    Build the two-layer repo-link cache. Always called once at server startup.

    Layer 1 (always): load static_registry.json into _REPO_CACHE.
    Layer 2 (optional): fetch from FindIt per FINDIT_CACHE_STRATEGY and merge in.
    FindIt entries overwrite static entries on key conflict.

    Raises if static_registry.json is missing or invalid JSON.
    Logs WARNING and continues if FindIt is unreachable or times out.
    """
    _REPO_CACHE.clear()

    static_entries = _load_static_registry()
    for service_name, code_repo_link in static_entries.items():
        _write_cache_entries(service_name, code_repo_link)

    static_count = len(static_entries)
    findit_count = 0
    strategy = config.FINDIT_CACHE_STRATEGY

    if strategy == "none":
        logger.info("FINDIT_CACHE_STRATEGY=none; skipping FindIt merge")
        logger.info(
            "Cache populated: %d static entries, %d FindIt entries, %d total",
            static_count,
            findit_count,
            len(_REPO_CACHE),
        )
        return

    timeout = (
        config.FINDIT_CACHE_LOAD_TIMEOUT_SECONDS
        if timeout_seconds is None
        else timeout_seconds
    )
    loader = _load_findit_bulk if strategy == "bulk" else _load_findit_paginated

    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(loader)
        findit_entries = future.result(timeout=timeout)
    except FuturesTimeout:
        logger.warning(
            "FindIt cache load timed out after %ss; using static registry only",
            timeout,
        )
        logger.info(
            "Cache populated: %d static entries, %d FindIt entries, %d total",
            static_count,
            findit_count,
            len(_REPO_CACHE),
        )
        return
    except Exception as exc:
        logger.warning("FindIt cache load failed: %s; using static registry only", exc)
        logger.info(
            "Cache populated: %d static entries, %d FindIt entries, %d total",
            static_count,
            findit_count,
            len(_REPO_CACHE),
        )
        return
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    findit_count = len(findit_entries)
    for service_name, code_repo_link in findit_entries.items():
        _write_cache_entries(service_name, code_repo_link)

    logger.info(
        "Cache populated: %d static entries, %d FindIt entries, %d total",
        static_count,
        findit_count,
        len(_REPO_CACHE),
    )


def get_repo_link(service_name: str) -> str | None:
    """
    Look up a service's codeRepoLink.

    1. Check _REPO_CACHE (populated at startup from static registry + FindIt).
    2. On cache miss: call lookup() live (original slow path).
    3. On live hit: warm _REPO_CACHE for subsequent calls.
    4. Return None if neither source has a record.
    """
    cache_key = _normalise(service_name)
    hit = _REPO_CACHE.get(cache_key)
    if hit:
        return hit

    record = lookup(service_name)
    link = record.get("codeRepoLink")
    if link:
        _write_cache_entries(service_name, link)
    return link


def _get_services(base_url: str) -> list[dict]:
    entry = _cache.get(base_url)
    if entry is not None:
        services, fetched_at = entry
        elapsed = datetime.now(timezone.utc) - fetched_at
        if elapsed.days < _CACHE_TTL_DAYS:
            return services

    services = _fetch_services(base_url)
    _cache[base_url] = (services, datetime.now(timezone.utc))
    return services


def _fetch_services(base_url: str) -> list[dict]:
    url = f"{base_url.rstrip('/')}/services"
    headers: dict[str, str] = {}
    if config.FINDIT_AUTH_TOKEN:
        headers["Authorization"] = f"Bearer {config.FINDIT_AUTH_TOKEN}"

    last_exc: Exception | None = None
    for attempt in range(_RETRIES + 1):
        try:
            with httpx.Client(timeout=_HTTP_TIMEOUT_SECONDS) as client:
                response = client.get(url, headers=headers)
            if response.status_code >= 400:
                raise _FindItError(
                    "http_request_failed",
                    f"FindIt returned HTTP {response.status_code}",
                    {"status_code": response.status_code, "url": url},
                )
            payload = response.json()
            if isinstance(payload, list):
                services = payload
            elif isinstance(payload, dict):
                services = payload.get("services", [])
            else:
                services = []
            if not isinstance(services, list):
                services = []
            return services
        except httpx.TimeoutException as exc:
            last_exc = exc
            if attempt < _RETRIES:
                time.sleep(_BACKOFF_SECONDS[attempt])
                continue
            raise _FindItError("http_timeout", "FindIt request timed out", {"url": url}) from exc
        except _FindItError:
            raise
        except httpx.HTTPError as exc:
            last_exc = exc
            if attempt < _RETRIES:
                time.sleep(_BACKOFF_SECONDS[attempt])
                continue
            raise _FindItError(
                "http_request_failed",
                f"FindIt request failed: {exc}",
                {"url": url},
            ) from exc

    raise _FindItError("http_request_failed", "FindIt request failed", {"url": url}) from last_exc


def _match(name: str, services: list[dict]) -> tuple[dict, str, NameResolution | None] | None:
    if not services:
        return None

    # Level 1: exact
    for svc in services:
        svc_name = svc.get("name", "")
        if svc_name == name:
            return svc, "exact", None

    # Level 2: case-insensitive
    name_lower = name.lower()
    for svc in services:
        svc_name = svc.get("name", "")
        if svc_name.lower() == name_lower:
            resolution: NameResolution = {
                "method": "case_insensitive",
                "matched_name": svc_name,
            }
            return svc, "case_insensitive", resolution

    # Level 3: alphanumeric normalization
    norm_input = _normalize_alphanumeric(name)
    for svc in services:
        svc_name = svc.get("name", "")
        if _normalize_alphanumeric(svc_name) == norm_input:
            resolution = {
                "method": "alphanumeric_normalized",
                "matched_name": svc_name,
            }
            return svc, "alphanumeric_normalized", resolution

    # Level 4: fuzzy
    threshold = config.FINDIT_SERVICE_NAME_FUZZY_THRESHOLD
    candidates: list[tuple[float, dict]] = []
    for svc in services:
        svc_name = svc.get("name", "")
        norm_candidate = _normalize_alphanumeric(svc_name)
        if not norm_candidate:
            continue
        score = fuzz.ratio(norm_input, norm_candidate) / 100.0
        if score >= threshold:
            candidates.append((score, svc))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    best_score, best_svc = candidates[0]
    best_name = best_svc.get("name", "")
    alternatives = [
        c[1].get("name", "")
        for c in candidates[1:4]
        if c[1].get("name", "") != best_name
    ]
    resolution = {
        "method": "fuzzy",
        "matched_name": best_name,
        "similarity": best_score,
        "threshold_used": threshold,
        "alternatives": alternatives,
    }
    return best_svc, "fuzzy", resolution


def lookup(service_name: str) -> dict:
    """Look up a service in FindIt; returns the matched record dict."""
    base_url = config.FINDIT_BASE_URL
    services = _get_services(base_url)
    match_result = _match(service_name, services)
    if match_result is None:
        raise _FindItError(
            "service_not_found",
            f"No FindIt service matched {service_name!r} at any matching level.",
            {
                "input_name": service_name,
                "candidates_checked": len(services),
                "fuzzy_threshold": config.FINDIT_SERVICE_NAME_FUZZY_THRESHOLD,
            },
        )

    record, _method, name_resolution = match_result
    result = dict(record)
    if name_resolution is not None:
        result["name_resolution"] = name_resolution
    return result
