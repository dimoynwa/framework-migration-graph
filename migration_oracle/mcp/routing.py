"""Executor-selection logic for Loop III migration step routing (T054).

Implements the 7-row decision table from contracts/loop3_executor_selection.md.
The `automatable` flag is metadata only — it is NOT a routing input.
"""

from __future__ import annotations

import re
from typing import Literal

ExecutorTrack = Literal["openrewrite", "prompted-auto", "agent-codemod", "human-review"]

# Patterns that indicate a concrete instruction (before/after, named op, or pattern+replacement)
_CONCRETE_PATTERNS = [
    re.compile(r"\brename\b.+\bto\b", re.IGNORECASE),
    re.compile(r"\breplace\b.+\bwith\b", re.IGNORECASE),
    re.compile(r"\bremove\b.+\b(import|class|method|annotation)\b", re.IGNORECASE),
    re.compile(r"\badd\b.+\bto\b", re.IGNORECASE),
    re.compile(r"(before|after)\s*[:\-\>]", re.IGNORECASE),
    re.compile(r"→|->|\=\>"),
    re.compile(r"`[^`]+`\s*(→|->|\=\>|to)\s*`[^`]+`", re.IGNORECASE),
    re.compile(r"\bfrom\b.+\bto\b.+\bimport\b", re.IGNORECASE),
]


def is_concrete_instruction(instruction: str) -> bool:
    """Return True only when the instruction contains a transformation pattern.

    A concrete instruction has at least one of:
    (a) a before/after transformation example
    (b) a named operation (rename/replace/remove/add) with explicit source and target
    (c) a pattern (string, glob, or regex) plus a replacement target

    Free-text-only descriptions return False.
    """
    if not instruction or not instruction.strip():
        return False
    return any(p.search(instruction) for p in _CONCRETE_PATTERNS)


def select_executor(step: dict) -> ExecutorTrack:
    """Select the executor track for a migration step using the 7-row decision table.

    Decision table (evaluated top-to-bottom; first matching row wins):

    | # | Recipe state         | Effort         | Instruction + entity anchor | Track          |
    |---|----------------------|----------------|-----------------------------|----------------|
    | 1 | Fully resolved       | any            | any                         | openrewrite    |
    | 2 | Partially resolved   | any            | any                         | prompted-auto  |
    | 3 | None                 | mechanical     | Yes                         | agent-codemod  |
    | 4 | None                 | moderate       | Yes                         | agent-codemod  |
    | 5 | None                 | mechanical     | No                          | human-review   |
    | 6 | None                 | moderate       | No                          | human-review   |
    | 7 | None                 | architectural  | any                         | human-review   |

    The `automatable` flag is ignored as a routing input (it is metadata only).
    """
    recipe_id = step.get("recipe_id")
    auto = step.get("auto")
    missing_params = step.get("missing_required_params") or []
    effort = (step.get("effort") or "").lower()
    instruction = step.get("instruction") or ""
    # entity anchor = applicability is 'matched' (at least one entity matched)
    has_entity_anchor = step.get("applicability") in ("matched",)

    # Row 1: Fully resolved recipe
    if recipe_id and auto is True and not missing_params:
        return "openrewrite"

    # Row 2: Partially resolved recipe (edge exists but not fully resolved)
    if recipe_id and (auto is False or missing_params):
        return "prompted-auto"

    # No recipe — rows 3–7
    concrete = is_concrete_instruction(instruction)

    if effort in ("mechanical", "moderate"):
        if concrete and has_entity_anchor:
            return "agent-codemod"
        return "human-review"

    # Row 7: architectural or anything else
    return "human-review"
