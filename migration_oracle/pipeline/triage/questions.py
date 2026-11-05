"""Fixed System-1 question set.

Wording is part of the decision contract. Any change to instructions or
criteria must bump ``TRIAGE_QUESTIONS_VERSION`` so cached answers are not reused.
"""

from __future__ import annotations

from typing import TypedDict


TRIAGE_QUESTIONS_VERSION = 1

REQUIRES_ACTION_INSTRUCTIONS = (
    "Would a typical application upgrading across this version hop need to "
    "change code, configuration, dependencies, build, deployment or runtime "
    "environment, or re-verify a behaviour it relies on?"
)

CATEGORY_INSTRUCTIONS = (
    "Which best describes the effect of this change on an upgrading user?"
)

IMPACT_INSTRUCTIONS = (
    "Rate the migration effort this change forces on applications that use "
    "the framework. Documentation, test, build and typo changes force no effort."
)

# A bug fix that changes observable behaviour is behavior_change; one users
# need not react to is internal_fix.
CATEGORY_CRITERIA: dict[str, str] = {
    "breaking": (
        "Removes or incompatibly changes an API, default, or runtime contract "
        "so existing applications fail until they are updated."
    ),
    "behavior_change": (
        "Changes observable behaviour, defaults, or output, including a bug "
        "fix that applications may have been relying on."
    ),
    "deprecation": (
        "Marks an API, configuration, or feature for removal; upgrading users "
        "should plan to move off it."
    ),
    "config_change": (
        "Requires a configuration, property, build, or deployment setting change."
    ),
    "dependency_upgrade": (
        "Bumps or replaces a dependency that upgrading applications must align with."
    ),
    "security": (
        "Fixes a vulnerability or requires a security configuration or dependency change."
    ),
    "new_optional_feature": (
        "Adds a capability applications can ignore without changing existing behaviour."
    ),
    "internal_fix": (
        "Corrects an internal defect that users need not react to and that does "
        "not change observable behaviour."
    ),
    "noise": (
        "Documentation, tests, CI, build tooling, examples, or typos with no "
        "effect on upgrading applications."
    ),
}

IMPACT_CRITERIA: list[str] = ["none", "low", "medium", "high"]

DROP_CATEGORIES = frozenset({"internal_fix", "noise", "new_optional_feature"})


class Question(TypedDict, total=False):
    type: str
    instructions: str
    criteria: dict[str, str] | list[str]


def triage_questions() -> dict[str, Question]:
    """Payload fragment sent as the ``questions`` object. Read live so tests can patch wording."""
    return {
        "requires_action": {
            "type": "noul",
            "instructions": REQUIRES_ACTION_INSTRUCTIONS,
        },
        "category": {
            "type": "choice",
            "instructions": CATEGORY_INSTRUCTIONS,
            "criteria": dict(CATEGORY_CRITERIA),
        },
        "impact": {
            "type": "score",
            "instructions": IMPACT_INSTRUCTIONS,
            "criteria": list(IMPACT_CRITERIA),
        },
    }
