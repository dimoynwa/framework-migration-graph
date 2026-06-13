"""Regression guard: canonical sortableVersion formula must stay unchanged in docs/graph-schema.md."""

from pathlib import Path


def test_graph_schema_formula_unchanged():
    schema = Path("docs/graph-schema.md").read_text()
    assert "major * 1_000_000 + minor * 1_000 + patch" in schema, (
        "Canonical sortableVersion formula changed or missing in docs/graph-schema.md"
    )
