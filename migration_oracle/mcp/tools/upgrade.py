"""Upgrade MCP tool handlers."""

from __future__ import annotations

import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import NamedTuple

import requests

from migration_oracle.graph.driver import read_session
from migration_oracle.mcp.graph.queries import upgrade as upgrade_queries
from migration_oracle.mcp.graph.queries.upgrade import _CHECK_VERSION_IN_GRAPH
from migration_oracle.mcp.instance import mcp


_MAVEN_CACHE: dict[tuple, tuple] = {}
_MAVEN_CACHE_TTL = 86400  # seconds (1 day)
_MAVEN_CACHE_LOCK = threading.Lock()


def _clear_maven_cache() -> None:
    _MAVEN_CACHE.clear()


class _CanonicalFramework(NamedTuple):
    display: str
    slug: str


_FRAMEWORK_ALIASES: dict[str, _CanonicalFramework] = {
    "springboot": _CanonicalFramework(display="Spring Boot", slug="spring-boot"),
}

_MAVEN_COORDS: dict[str, tuple[str, str]] = {
    "spring-boot": ("org.springframework.boot", "spring-boot"),
}


def _normalise_key(framework: str) -> str:
    return re.sub(r"[\s\-_]", "", framework).lower()


def canonical_framework(framework: str) -> "_CanonicalFramework | dict":
    """Resolve any accepted framework spelling to the canonical record.

    Returns _CanonicalFramework on success, or an unsupported_framework error dict on failure.
    Call sites must check the return type before using .display/.slug.
    """
    key = _normalise_key(framework)
    cf = _FRAMEWORK_ALIASES.get(key)
    if cf is None:
        display_names = ", ".join(sorted({v.display for v in _FRAMEWORK_ALIASES.values()}))
        return {
            "status": "error",
            "error_code": "unsupported_framework",
            "exists_in_graph": False,
            "ga_available": False,
            "latest_patch": None,
            "hint": f"Unknown framework; supported: {display_names}",
        }
    return cf


def to_minor_zero(version: str) -> str:
    """Normalise 'major.minor.patch' → 'major.minor.0' for graph lookups."""
    parts = version.split(".", 2)
    return f"{parts[0]}.{parts[1]}.0"


def _flatten_rules(rows: list[dict]) -> list[dict]:
    rules: list[dict] = []
    for row in rows:
        for rule in row.get("rules") or []:
            scopes = rule.get("scopes") or []
            severity = next(
                (s["severity"] for s in scopes if s.get("severity")),
                None,
            )
            rules.append({**rule, "severity": severity})
    return rules


@mcp.tool()
def analyze_upgrade_path(
    framework: str,
    current_version: str,
    target_version: str,
    user_entities: list[str] | None = None,
    format: str = "json",
    classification: list[str] | None = None,
    include_recipes: bool = False,
    include_lifecycle: bool = True,
    top_n: int = 50,
    verbose: bool = False,
    scope_filter: list[str] | None = None,
    min_severity: str | None = None,
) -> dict:
    """Return migration rules and lifecycle alerts for a framework version range.

    Queries all MigrationRule nodes whose version range covers [current_version, target_version].
    Optionally filter by scope ('api-surface', 'runtime', 'config', 'build', 'test') and
    severity ('low', 'medium', 'high', 'critical').

    user_entities: Optional list of project identifiers used to filter and annotate rules.
      Accepts three identifier types:
        (1) Java class names — short form (e.g. 'ObjectMapper') or fully-qualified
            (e.g. 'com.fasterxml.jackson.databind.ObjectMapper').
        (2) Spring property keys as they appear in config files (e.g. 'spring.redis.host').
        (3) Maven dependency artifact IDs in artifact-only form
            (e.g. 'spring-boot-starter-data-redis') — do NOT pass the full 'group:artifact'
            coordinate; the graph stores some Dependency nodes in artifact-only format and
            the substring match will fail for the longer form.
      Matching is substring-based: graphNodeName.contains(userEntity).
      When provided, each returned rule includes matched_entities (the user entity values
      that matched), applicability ('universal' | 'applicable' | 'not_applicable'), and
      universally_applicable (true when the rule has no entity links in the graph).

    Returns: rules list (statement, steps, scopes, recipes, matched_entities, applicability),
    lifecycle_alerts list. Each rule contains steps: [] and scopes: [] when no
    MigrationStep/BreakingScope nodes exist in the graph — this is expected, not an error.
    """
    rows = upgrade_queries.analyze_upgrade_path(
        framework=framework,
        current_version=to_minor_zero(current_version),
        target_version=to_minor_zero(target_version),
        user_entities=user_entities or [],
        classification=classification,
        scope_filter=scope_filter or [],
        min_severity=min_severity,
    )
    rules = _flatten_rules(rows)[:top_n]
    lifecycle_alerts = []
    if include_lifecycle:
        for row in rows:
            lifecycle_alerts.extend(
                [a for a in (row.get("raw_phase_alerts") or []) if a.get("message")]
            )

    if format == "markdown":
        lines = [
            f"# Upgrade path: {framework} {current_version} → {target_version}",
            "",
            f"Rules: {len(rules)}",
        ]
        for rule in rules:
            lines.append(f"- {rule.get('statement', '')}")
        return {"status": "ok", "format": "markdown", "content": "\n".join(lines)}

    return {
        "status": "ok",
        "framework": framework,
        "from_version": current_version,
        "to_version": target_version,
        "rules": rules,
        "lifecycle_alerts": lifecycle_alerts,
        "format": format,
    }


@mcp.tool()
def build_recipe_plan(
    current_version: str,
    target_version: str,
    framework: str = "Spring Boot",
    user_entities: list[str] | None = None,
    auto_only: bool = False,
    classification: list[str] | None = None,
    scope_filter: list[str] | None = None,
    min_severity: str | None = None,
) -> dict:
    """Produce a two-track migration plan: auto (scriptable) and manual (human review required).

    Auto track: steps with automatable=true, effort=mechanical, and a linked OpenRewrite recipe.
    Manual track: all other steps. Falls back to rule-level cards when no MigrationStep nodes exist.

    Returns: auto_track list, manual_track list, fallback_to_rule_cards bool.
    An empty auto_track is expected in the first release (no AUTOMATED_BY edges yet).
    """
    plan = upgrade_queries.build_recipe_plan(
        framework=framework,
        current_version=to_minor_zero(current_version),
        target_version=to_minor_zero(target_version),
        user_entities=user_entities,
        classification=classification,
        scope_filter=scope_filter or [],
        min_severity=min_severity,
    )
    manual_track = plan["manual_track"]
    if auto_only:
        manual_track = []
    return {
        "status": "ok",
        "auto_track": plan["auto_track"],
        "manual_track": manual_track,
        "fallback_to_rule_cards": plan["fallback_to_rule_cards"],
    }


@mcp.tool()
def check_version_availability(framework: str, version: str) -> dict:
    """Check whether a framework version exists in the graph and on Maven Central.

    Returns: status, exists_in_graph, ga_available, latest_patch, hint.
    On Maven Central probe failure, returns status='ok' with ga_available=False and a hint.
    """
    cf = canonical_framework(framework)
    if isinstance(cf, dict):
        return cf

    normalised = to_minor_zero(version)

    coords = _MAVEN_COORDS.get(cf.slug)
    if coords is None:
        return {
            "status": "error",
            "error_code": "unsupported_framework",
            "exists_in_graph": False,
            "ga_available": False,
            "latest_patch": None,
            "hint": f"Unknown framework; supported: {', '.join(sorted(_MAVEN_COORDS))}",
        }

    group_id, artifact_id = coords

    with read_session() as session:
        record = session.run(
            _CHECK_VERSION_IN_GRAPH,
            framework=cf.display,
            version=normalised,
        ).single()
    exists_in_graph: bool = bool(record["found"]) if record else False

    _maven_base = "https://search.maven.org/solrsearch/select"
    cache_key = (group_id, artifact_id, normalised)
    cached = _MAVEN_CACHE.get(cache_key)
    if cached and time.time() < cached[2]:
        ga_available: bool = cached[0]
        latest_patch: str | None = cached[1]
    else:
        try:
            def _fetch_ga() -> bool:
                r = requests.get(
                    f"{_maven_base}?q=g:{group_id}+AND+a:{artifact_id}+AND+v:{normalised}&rows=1&wt=json",
                    timeout=3,
                )
                r.raise_for_status()
                return r.json()["response"]["numFound"] >= 1

            def _fetch_latest() -> str | None:
                r = requests.get(
                    f"{_maven_base}?q=g:{group_id}+AND+a:{artifact_id}&rows=1&wt=json&sort=version+desc",
                    timeout=3,
                )
                r.raise_for_status()
                docs = r.json()["response"]["docs"]
                return docs[0]["v"] if docs else None

            with ThreadPoolExecutor(max_workers=2) as executor:
                fut_ga = executor.submit(_fetch_ga)
                fut_lp = executor.submit(_fetch_latest)
                ga_available = fut_ga.result(timeout=4)
                latest_patch = fut_lp.result(timeout=4)

            with _MAVEN_CACHE_LOCK:
                _MAVEN_CACHE[cache_key] = (ga_available, latest_patch, time.time() + _MAVEN_CACHE_TTL)

        except Exception:
            return {
                "status": "ok",
                "exists_in_graph": exists_in_graph,
                "ga_available": False,
                "latest_patch": None,
                "hint": "Maven Central unavailable — could not verify GA status",
            }

    hint = (
        f"Version {normalised} {'is' if ga_available else 'is not'} available on Maven Central."
    )
    if latest_patch:
        hint += f" Latest patch: {latest_patch}."

    return {
        "status": "ok",
        "exists_in_graph": exists_in_graph,
        "ga_available": ga_available,
        "latest_patch": latest_patch,
        "hint": hint,
    }
