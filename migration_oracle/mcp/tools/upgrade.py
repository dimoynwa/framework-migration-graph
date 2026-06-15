"""Upgrade MCP tool handlers."""

from __future__ import annotations

import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import NamedTuple

import requests

from typing import Literal

from migration_oracle.graph.driver import read_session
from migration_oracle.mcp.graph.queries import upgrade as upgrade_queries
from migration_oracle.mcp.graph.queries.upgrade import _CHECK_VERSION_IN_GRAPH, resolve_version
from migration_oracle.mcp.instance import mcp
from migration_oracle.models.graph import VersionResolutionFailure


def _to_minor_zero(version: str) -> str:
    """Normalise 'major.minor.patch' → 'major.minor.0' for graph lookups."""
    parts = version.split(".", 2)
    return f"{parts[0]}.{parts[1]}.0"


# Public alias — used by tools/context.py and tests
to_minor_zero = _to_minor_zero


_MAVEN_CACHE: dict[tuple, tuple] = {}
_MAVEN_CACHE_TTL = 86400
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
    """Resolve any accepted framework spelling to the canonical record."""
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


def normalize_entities(entities: list[str]) -> dict:
    """Classify a flat list of entity strings into 5 typed buckets.

    Buckets:
    - scanned_classes: FQCNs — have a dot AND last segment starts uppercase.
      Matched by exact name only.
    - scanned_class_simple: simple class/annotation names — no dot, starts uppercase.
      Built ONLY from genuinely dotless tokens; never derived from FQCN tails.
    - scanned_deps_ga: groupId:artifactId — contains colon, first part has dots.
      Strips any third segment (version).
    - scanned_dep_artifacts: bare artifact ID — no colon, no dot, hyphenated-lowercase
      or lowercase. Also includes the second segment of each GA coord.
    - scanned_props: dotted property keys — has a dot, all segments lowercase.
    """
    fqcns: list[str] = []
    simple_names: list[str] = []
    deps_ga: list[str] = []
    dep_artifacts: list[str] = []
    props: list[str] = []

    for e in entities:
        if not e:
            continue
        if ':' in e:                                   # group:artifact[:version]
            g, a = e.split(':')[:2]
            deps_ga.append(f'{g}:{a}')
            dep_artifacts.append(a)                    # second segment of GA coord
        elif '.' in e:
            if e.rsplit('.', 1)[-1][:1].isupper():     # last segment uppercase -> FQCN
                fqcns.append(e)                        # exact-match only; no simple derivation
            else:                                      # all-lowercase dotted -> property key
                props.append(e)
        elif e[:1].isupper():                          # bare uppercase -> annotation / simple class
            simple_names.append(e)
        else:                                          # bare lowercase/hyphenated -> artifact ID
            dep_artifacts.append(e)

    return {
        "scanned_classes": list(dict.fromkeys(fqcns)),
        "scanned_class_simple": list(dict.fromkeys(simple_names)),
        "scanned_deps_ga": list(dict.fromkeys(deps_ga)),
        "scanned_dep_artifacts": list(dict.fromkeys(dep_artifacts)),
        "scanned_props": list(dict.fromkeys(props)),
    }

def _has_entity_filter(norm: dict) -> bool:
    return any(norm[k] for k in norm)


def _flatten_rules(rows: list[dict], *, has_entity_filter_flag: bool, top_n: int) -> tuple[list[dict], int, int, int]:
    """Flatten rules from all version rows, separate excluded, sort, and cap.

    Returns: (capped_rules, rules_included_before_cap, rules_excluded, rules_uncertain)
    """
    all_rules: list[dict] = []
    excluded_count = 0

    for row in rows:
        for rule in row.get("rules") or []:
            applicability = rule.get("applicability") or "informational"
            if has_entity_filter_flag and applicability == "excluded":
                excluded_count += 1
            else:
                all_rules.append(rule)

    # Sort: uncertain first (by sev_rank asc), then matched, then informational/universal
    _applicability_order = {"uncertain": 0, "matched": 1, "informational": 2, "universal": 2}

    def _sort_key(rule: dict):
        app = rule.get("applicability") or "informational"
        sev = rule.get("severity")
        sev_rank_map = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        sev_rank = sev_rank_map.get(sev, 4) if sev else 4
        return (_applicability_order.get(app, 3), sev_rank)

    all_rules.sort(key=_sort_key)
    rules_included = len(all_rules)
    uncertain_count = sum(1 for r in all_rules if r.get("applicability") == "uncertain")

    # Promote severity from scopes if not already at rule level
    for rule in all_rules:
        if rule.get("severity") is None:
            for scope_entry in rule.get("scopes") or []:
                if scope_entry.get("severity"):
                    rule["severity"] = scope_entry["severity"]
                    break

    capped = all_rules[:top_n]
    return capped, rules_included, excluded_count, uncertain_count


def _build_diagnostics(norm: dict, rules_included: int, excluded_count: int, uncertain_count: int, top_n: int, actual_returned: int) -> dict:
    """Build diagnostics dict for entity-filtered responses."""
    all_entities: list[str] = []
    for bucket in norm.values():
        all_entities.extend(bucket)
    unique_entities = list(dict.fromkeys(all_entities))
    scanned_total = len(unique_entities)

    diag: dict = {
        "scanned_total": scanned_total,
        "rules_included": rules_included,
        "rules_excluded_by_entity_filter": excluded_count,
        "rules_via_safety_net": uncertain_count,
    }
    if actual_returned < rules_included:
        diag["rules_capped_at"] = top_n
    else:
        diag["rules_capped_at"] = None
    return diag


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

    Returns: rules list (statement, steps, scopes, recipes), lifecycle_alerts list.
    Each rule contains steps: [] and scopes: [] when no MigrationStep/BreakingScope nodes
    exist in the graph (pre-redesign data) — this is expected, not an error.

    When include_recipes=True, each rule includes a recipes list. Recipes are per step
    (traversal: REQUIRES_STEP → AUTOMATED_BY). Each recipe entry includes step_id identifying
    the MigrationStep that has the AUTOMATED_BY edge.
    """
    norm = normalize_entities(user_entities or [])
    has_filter = _has_entity_filter(norm)

    resolved_from = resolve_version(framework, current_version, mode="floor")
    resolved_to = resolve_version(framework, target_version, mode="ceil")
    from_ver = resolved_from.resolvedVersion if not isinstance(resolved_from, VersionResolutionFailure) else _to_minor_zero(current_version)
    to_ver = resolved_to.resolvedVersion if not isinstance(resolved_to, VersionResolutionFailure) else _to_minor_zero(target_version)

    rows = upgrade_queries.analyze_upgrade_path(
        framework=framework,
        current_version=from_ver,
        target_version=to_ver,
        scanned_classes=norm["scanned_classes"],
        scanned_class_simple=norm["scanned_class_simple"],
        scanned_deps_ga=norm["scanned_deps_ga"],
        scanned_dep_artifacts=norm["scanned_dep_artifacts"],
        scanned_props=norm["scanned_props"],
        has_entity_filter=has_filter,
        classification=classification,
        scope_filter=scope_filter or [],
        min_severity=min_severity,
    )

    rules, rules_included, excluded_count, uncertain_count = _flatten_rules(
        rows, has_entity_filter_flag=has_filter, top_n=top_n
    )

    lifecycle_alerts = []
    if include_lifecycle:
        for row in rows:
            lifecycle_alerts.extend(row.get("lifecycle_events") or [])
            # new Cypher returns raw_phase_alerts key
            lifecycle_alerts.extend(row.get("raw_phase_alerts") or [])

    diagnostics = None
    if has_filter:
        diagnostics = _build_diagnostics(
            norm, rules_included, excluded_count, uncertain_count, top_n, len(rules)
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

    result = {
        "status": "ok",
        "framework": framework,
        "from_version": current_version,
        "to_version": target_version,
        "rules": rules,
        "lifecycle_alerts": lifecycle_alerts,
        "format": format,
    }
    if diagnostics is not None:
        result["diagnostics"] = diagnostics
    return result


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
    norm = normalize_entities(user_entities or [])
    has_filter = _has_entity_filter(norm)

    resolved_from = resolve_version(framework, current_version, mode="floor")
    resolved_to = resolve_version(framework, target_version, mode="ceil")
    from_ver = resolved_from.resolvedVersion if not isinstance(resolved_from, VersionResolutionFailure) else _to_minor_zero(current_version)
    to_ver = resolved_to.resolvedVersion if not isinstance(resolved_to, VersionResolutionFailure) else _to_minor_zero(target_version)

    plan = upgrade_queries.build_recipe_plan(
        framework=framework,
        current_version=from_ver,
        target_version=to_ver,
        scanned_classes=norm["scanned_classes"],
        scanned_class_simple=norm["scanned_class_simple"],
        scanned_deps_ga=norm["scanned_deps_ga"],
        scanned_dep_artifacts=norm["scanned_dep_artifacts"],
        scanned_props=norm["scanned_props"],
        has_entity_filter=has_filter,
        classification=classification,
        scope_filter=scope_filter or [],
        min_severity=min_severity,
    )
    manual_track = plan["manual_track"]
    if auto_only:
        manual_track = []

    diagnostics = None
    if has_filter:
        diagnostics = _build_diagnostics(
            norm,
            plan.get("rules_included", 0),
            plan.get("excluded_count", 0),
            plan.get("uncertain_count", 0),
            50,
            len(plan["auto_track"]) + len(manual_track),
        )

    result = {
        "status": "ok",
        "auto_track": plan["auto_track"],
        "manual_track": manual_track,
        "fallback_to_rule_cards": plan["fallback_to_rule_cards"],
    }
    if diagnostics is not None:
        result["diagnostics"] = diagnostics
    return result


@mcp.tool()
def check_version_availability(
    framework: str,
    version: str,
    direction: Literal["floor", "ceil"] = "floor",
) -> dict:
    """Check whether a framework version exists in the graph and on Maven Central.

    direction='floor' (default): resolve to the highest graph node <= requested version.
    direction='ceil': resolve to the lowest graph node >= requested version (for target checks).

    Returns: status, exists_in_graph, nodeId, resolved_version, rounded, ahead_of_catalogue,
             ga_available, latest_patch, hint.
    On Maven Central probe failure, returns status='ok' with ga_available=False and a hint.
    """
    cf = canonical_framework(framework)
    if isinstance(cf, dict):
        return cf

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

    resolution = resolve_version(cf.display, version, mode=direction)
    if isinstance(resolution, VersionResolutionFailure):
        return {
            "status": "ok",
            "exists_in_graph": False,
            "nodeId": None,
            "resolved_version": None,
            "rounded": False,
            "ahead_of_catalogue": False,
            "ga_available": False,
            "latest_patch": None,
            "hint": (
                f"Version {version!r} has no matching node in the graph "
                f"(direction={direction}). Candidates considered: "
                f"{', '.join(resolution.candidatesConsidered) or 'none (framework unknown)'}"
            ),
            "candidates_considered": resolution.candidatesConsidered,
        }

    exists_in_graph = True
    resolved_v = resolution.resolvedVersion
    node_id = resolution.nodeId

    group_id, artifact_id = coords
    _maven_base = "https://search.maven.org/solrsearch/select"
    cache_key = (group_id, artifact_id, resolved_v)
    cached = _MAVEN_CACHE.get(cache_key)
    if cached and time.time() < cached[2]:
        ga_available: bool = cached[0]
        latest_patch: str | None = cached[1]
    else:
        try:
            def _fetch_ga() -> bool:
                r = requests.get(
                    f"{_maven_base}?q=g:{group_id}+AND+a:{artifact_id}+AND+v:{resolved_v}&rows=1&wt=json",
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
                "nodeId": node_id,
                "resolved_version": resolved_v,
                "rounded": resolution.rounded,
                "ahead_of_catalogue": resolution.aheadOfCatalogue,
                "ga_available": False,
                "latest_patch": None,
                "hint": "Maven Central unavailable — could not verify GA status",
            }

    hint = f"Version {resolved_v} {'is' if ga_available else 'is not'} available on Maven Central."
    if latest_patch:
        hint += f" Latest patch: {latest_patch}."
    if resolution.rounded:
        hint += f" Requested {version!r} resolved to {resolved_v!r} (direction={direction})."
    if resolution.aheadOfCatalogue:
        hint += f" Version {version!r} is ahead of the highest catalogued version ({resolved_v})."

    return {
        "status": "ok",
        "exists_in_graph": exists_in_graph,
        "nodeId": node_id,
        "resolved_version": resolved_v,
        "rounded": resolution.rounded,
        "ahead_of_catalogue": resolution.aheadOfCatalogue,
        "ga_available": ga_available,
        "latest_patch": latest_patch,
        "hint": hint,
    }
