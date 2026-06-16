"""Shared entity-match projection helpers.

Mirrors entity-match CASE semantics in ``_GET_PENDING_STEPS`` (context.py L148-162).
"""

from __future__ import annotations


def _package_prefix_from_fqcn(fqcn: str) -> str:
    """Package prefix with trailing dot — mirrors Cypher ``left(ruleClass, ...) + '.'``."""
    parts = fqcn.split(".")
    if len(parts) <= 1:
        return fqcn + "."
    return ".".join(parts[:-1]) + "."


def _is_class_fqcn(name: str) -> bool:
    return ":" not in name and "." in name and name.rsplit(".", 1)[-1][:1].isupper()


def _has_class_anchor(affected: list[str]) -> bool:
    return any(_is_class_fqcn(a) for a in affected)


def _all_scanned(norm: dict) -> set[str]:
    return set(
        (norm.get("scanned_classes") or [])
        + (norm.get("scanned_class_simple") or [])
        + (norm.get("scanned_deps_ga") or [])
        + (norm.get("scanned_dep_artifacts") or [])
        + (norm.get("scanned_props") or [])
    )


def _truncated_group_id_prefix(group_id: str) -> str:
    """Strip last dot-segment of groupId — ``com.fasterxml.jackson.core`` → ``com.fasterxml.jackson.``."""
    parts = group_id.split(".")
    if len(parts) <= 1:
        return group_id + "."
    return ".".join(parts[:-1]) + "."


def compute_matched_entities(rule: dict, norm: dict) -> list[str]:
    """Return scanned user-entity strings that matched this rule.

    When ``match_count > 0`` but ``affected_entities`` holds graph node names (e.g.
    ``groupId:artifact`` coords) rather than scanned FQCNs, apply the same
    package-prefix bridges Cypher uses for applicability.
    """
    affected = rule.get("affected_entities") or []
    match_count = rule.get("match_count") or 0
    scanned_classes = norm.get("scanned_classes") or []
    scanned_simple = norm.get("scanned_class_simple") or []
    scanned_ga = norm.get("scanned_deps_ga") or []
    scanned_artifacts = norm.get("scanned_dep_artifacts") or []
    scanned_props = norm.get("scanned_props") or []
    scanned_set = _all_scanned(norm)

    matched: list[str] = []

    def _add(entity: str) -> None:
        if entity and entity not in matched:
            matched.append(entity)

    # 1. Direct hits — affected graph names present in typed scan buckets
    for ae in affected:
        if ae in scanned_set:
            _add(ae)

    # Class simple-name bridge (FQCN in graph, simple name in scan)
    for ae in affected:
        if not _is_class_fqcn(ae):
            continue
        simple = ae.rsplit(".", 1)[-1]
        if simple in scanned_simple:
            for cls in scanned_classes:
                if cls.rsplit(".", 1)[-1] == simple:
                    _add(cls)
            if ae in scanned_classes:
                _add(ae)

    # Dependency GA / artifact direct
    for ae in affected:
        if ":" not in ae:
            continue
        parts = ae.split(":")
        if len(parts) >= 2:
            ga = f"{parts[0]}:{parts[1]}"
            if ga in scanned_ga:
                _add(ga)
            if parts[1] in scanned_artifacts:
                _add(parts[1])

    for ae in affected:
        if ae in scanned_props:
            _add(ae)

    if match_count <= 0:
        return matched

    # 2. Package-prefix bridges — align serializer with Cypher ``entity_match``
    class_fqcns = [a for a in affected if _is_class_fqcn(a)]

    # Primary: derive prefix from Class anchor FQCNs in affected_entities
    for rule_class in class_fqcns:
        prefix = _package_prefix_from_fqcn(rule_class)
        for cls in scanned_classes:
            if cls.startswith(prefix):
                _add(cls)

    # Fallback: Dependency-only rules — groupId prefix (see _GET_PENDING_STEPS L155-161)
    if not _has_class_anchor(affected):
        for ae in affected:
            if ":" not in ae or len(ae.split(":")) < 2:
                continue
            gid = ae.split(":")[0]
            gid_prefix = gid + "."
            for cls in scanned_classes:
                if cls.startswith(gid_prefix):
                    _add(cls)
            # Truncated groupId (T046 / ISSUE-027): e.g. jackson.core → com.fasterxml.jackson.
            if not any(cls.startswith(gid_prefix) for cls in scanned_classes):
                truncated = _truncated_group_id_prefix(gid)
                for cls in scanned_classes:
                    if cls.startswith(truncated):
                        _add(cls)

    return matched
