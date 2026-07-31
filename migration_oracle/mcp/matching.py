"""Shared entity-match projection helpers."""

from __future__ import annotations


def _package_prefix_from_fqcn(fqcn: str) -> str:
    """Package prefix with trailing dot — mirrors Cypher ``left(ruleClass, ...) + '.'``."""
    parts = fqcn.split(".")
    if len(parts) <= 1:
        return fqcn + "."
    return ".".join(parts[:-1]) + "."


def _is_class_fqcn(name: str) -> bool:
    return ":" not in name and "." in name and name.rsplit(".", 1)[-1][:1].isupper()


def _all_scanned(norm: dict) -> set[str]:
    return set(
        (norm.get("scanned_classes") or [])
        + (norm.get("scanned_class_simple") or [])
        + (norm.get("scanned_deps_ga") or [])
        + (norm.get("scanned_dep_artifacts") or [])
        + (norm.get("scanned_props") or [])
    )


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

    # 2. Class package-prefix bridge — align serializer with Cypher ``entity_match``.
    # Dependency nodes only match explicit scanned build dependencies. Bridging a
    # dependency groupId to arbitrary classes is too broad for project-specific plans
    # (for example, any org.springframework.boot import would match any Boot starter).
    class_fqcns = [a for a in affected if _is_class_fqcn(a)]

    # Primary: derive prefix from Class anchor FQCNs in affected_entities
    for rule_class in class_fqcns:
        prefix = _package_prefix_from_fqcn(rule_class)
        for cls in scanned_classes:
            if cls.startswith(prefix):
                _add(cls)

    return matched
