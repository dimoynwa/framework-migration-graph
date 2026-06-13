"""Tests for spec 011 US4: resolve_deprecation and entity_evolution via seed data."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _make_deprecation_row(class_name: str, replacement: str | None = None) -> dict:
    return {
        "class_name": class_name,
        "deprecated_in": "3.2.0",
        "replacement": replacement,
        "status": "found" if True else "not_found",
    }


# ---------------------------------------------------------------------------
# FR-013: Seed data covers known Spring Boot 3.x deprecated classes
# ---------------------------------------------------------------------------

def test_rest_template_found():
    """RestTemplate must be in the SPRING_BOOT_3X_DEPRECATED seed list."""
    from migration_oracle.pipeline.seeds.deprecated_classes import SPRING_BOOT_3X_DEPRECATED

    names = {c.name for c in SPRING_BOOT_3X_DEPRECATED}
    assert "RestTemplate" in names


def test_rest_template_replaced_by_rest_client():
    """RestTemplate seed entry must declare RestClient as the replacement."""
    from migration_oracle.pipeline.seeds.deprecated_classes import SPRING_BOOT_3X_DEPRECATED

    rest_template = next(c for c in SPRING_BOOT_3X_DEPRECATED if c.name == "RestTemplate")
    assert rest_template.replacement == "RestClient"


def test_web_mvc_configurer_found():
    """WebMvcConfigurer must be in the seed list."""
    from migration_oracle.pipeline.seeds.deprecated_classes import SPRING_BOOT_3X_DEPRECATED

    names = {c.name for c in SPRING_BOOT_3X_DEPRECATED}
    assert "WebMvcConfigurer" in names


def test_unknown_class_not_found():
    """A class not in the seed data should not appear in the list."""
    from migration_oracle.pipeline.seeds.deprecated_classes import SPRING_BOOT_3X_DEPRECATED

    names = {c.name for c in SPRING_BOOT_3X_DEPRECATED}
    assert "UnknownClass12345" not in names


# ---------------------------------------------------------------------------
# FR-014: seed_deprecated_classes is idempotent (MERGE-based)
# ---------------------------------------------------------------------------

@patch("migration_oracle.pipeline.populator.write_session")
def test_seed_idempotent(mock_write_ctx):
    """seed_deprecated_classes uses MERGE so calling it twice produces no duplicates."""
    session = MagicMock()
    mock_write_ctx.return_value.__enter__.return_value = session
    session.run.return_value = MagicMock()

    from migration_oracle.pipeline.populator import seed_deprecated_classes

    seed_deprecated_classes()
    seed_deprecated_classes()

    # All Cypher statements must contain MERGE, not CREATE
    for call_args in session.run.call_args_list:
        cypher = call_args[0][0] if call_args[0] else ""
        if cypher.strip():
            assert "MERGE" in cypher, f"Expected MERGE in Cypher, got: {cypher[:100]}"
