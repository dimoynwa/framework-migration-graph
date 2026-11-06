"""One place for the ``MigrationRule.ruleId`` format (``pipeline://…``).

The populator, the rule-signal stage and the signal backfill script must agree
on the id, otherwise a backfill cannot find the rules that populate wrote.
"""

from __future__ import annotations


def rule_id_for(framework_display: str, to_version: str, title: str) -> str:
    """Canonical ``ruleId`` of one pipeline rule."""
    return f"pipeline://{framework_display}/{to_version}/{title}"
