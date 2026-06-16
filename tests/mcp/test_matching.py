"""Unit tests for migration_oracle.mcp.matching.compute_matched_entities."""

from __future__ import annotations

from migration_oracle.mcp.matching import compute_matched_entities


def _norm(**kwargs) -> dict:
    base = {
        "scanned_classes": [],
        "scanned_class_simple": [],
        "scanned_deps_ga": [],
        "scanned_dep_artifacts": [],
        "scanned_props": [],
    }
    base.update(kwargs)
    return base


def test_direct_hit_class_fqcn():
    rule = {
        "match_count": 1,
        "affected_entities": ["com.example.Foo"],
    }
    norm = _norm(scanned_classes=["com.example.Foo"])
    assert compute_matched_entities(rule, norm) == ["com.example.Foo"]


def test_dependency_group_id_prefix_bridge():
    rule = {
        "match_count": 1,
        "affected_entities": ["org.springframework:spring-web"],
    }
    norm = _norm(scanned_classes=["org.springframework.web.bind.annotation.RestController"])
    matched = compute_matched_entities(rule, norm)
    assert "org.springframework.web.bind.annotation.RestController" in matched


def test_jackson_truncated_group_id_bridge():
    rule = {
        "match_count": 1,
        "affected_entities": ["com.fasterxml.jackson.core:jackson-databind"],
    }
    norm = _norm(scanned_classes=["com.fasterxml.jackson.databind.ObjectMapper"])
    matched = compute_matched_entities(rule, norm)
    assert "com.fasterxml.jackson.databind.ObjectMapper" in matched


def test_match_count_zero_returns_only_direct():
    rule = {
        "match_count": 0,
        "affected_entities": ["org.springframework:spring-web"],
    }
    norm = _norm(scanned_classes=["org.springframework.web.bind.annotation.RestController"])
    assert compute_matched_entities(rule, norm) == []
