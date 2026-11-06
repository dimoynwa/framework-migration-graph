"""System-1 question set for rule signals (spec 027 FR-3).

Wording is part of the decision contract. Any change to the instructions, the
criteria, the feature vocabulary or the state layout must bump
``SIGNAL_QUESTIONS_VERSION`` so cached answers are not reused.
"""

from __future__ import annotations

from migration_oracle.pipeline.signals.features import Feature
from migration_oracle.pipeline.triage.questions import Question

SIGNAL_QUESTIONS_VERSION = 1

SIGNAL_INSTRUCTIONS = (
    "What in an application's code or build shows that this rule applies to "
    "that application?"
)

SIGNAL_CRITERIA: dict[str, str] = {
    "symbol": (
        "Using a specific API named in the rule (class, function, method, "
        "decorator option) is enough: every application that uses it must act, "
        "and no other application must."
    ),
    "config": (
        "A specific key in angular.json, tsconfig.json, package.json or another "
        "config file decides it."
    ),
    "dependency": "Declaring a specific package, or a version of it, decides it.",
    "syntax": "Using specific template syntax decides it.",
    "behavioral": (
        "Using the named API is not enough; only code that relies on the old "
        "behaviour is affected, which needs reading the code."
    ),
    "universal": (
        "Every application upgrading across this version hop is affected."
    ),
}

SIGNAL_TYPES: tuple[str, ...] = tuple(SIGNAL_CRITERIA)

#: Types the planner can decide from a profile key alone (FR-1).
SEARCHABLE_SIGNALS: frozenset[str] = frozenset(
    {"symbol", "config", "dependency", "syntax"}
)


def signal_questions(features: tuple[Feature, ...]) -> dict[str, Question]:
    """One ``signal`` choice plus one ``noul`` per feature, in one request.

    System-1 has no multi-select type, so every feature is its own yes/no
    question. Sending them together keeps the state on the wire once per rule.
    """
    questions: dict[str, Question] = {
        "signal": {
            "type": "choice",
            "instructions": SIGNAL_INSTRUCTIONS,
            "criteria": dict(SIGNAL_CRITERIA),
        }
    }
    for feature in features:
        questions[f"feature.{feature.id}"] = {
            "type": "noul",
            "instructions": feature.question,
        }
    return questions
