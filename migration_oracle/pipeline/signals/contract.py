"""Signal keys, the contract guard and the confidence floors (spec 027 FR-4).

Nimble picks the signal type and the features; code derives what the planner
would search for and rejects a type that has nothing to search for. The
expensive mistake is **exclusion** — marking a rule ``symbol`` when no symbol
can be found makes the planner drop a rule that applies. Everything uncertain
therefore falls back to ``behavioral``, which is decided by reading the code or
by asking, never by a missing name.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from migration_oracle.models.entities import EntityKind, EntityRole
from migration_oracle.pipeline.canonical.normalize import NormalizedEntity
from migration_oracle.pipeline.signals.questions import SEARCHABLE_SIGNALS
from migration_oracle.pipeline.signals.settings import SignalSettings

#: Roles whose keys the planner can look for. ``replacement`` and
#: ``co-required`` are excluded: finding the replacement means the service has
#: already migrated.
SEARCHABLE_ROLES: frozenset[str] = frozenset(
    {EntityRole.REMOVED.value, EntityRole.MENTIONED.value}
)

#: Which canonical kind proves which signal type.
_SIGNAL_KINDS: dict[str, tuple[EntityKind, ...]] = {
    "symbol": (EntityKind.CLASS, EntityKind.MEMBER),
    "config": (EntityKind.PROPERTY,),
    "dependency": (EntityKind.DEPENDENCY,),
    "syntax": (EntityKind.SYNTAX,),
}

#: A ``behavioral`` rule is decided by reading the code, so its keys are
#: *locators*: every searchable-role key of any kind tells the planner where to
#: look (``DestroyRef`` for the onDestroy timing rule).
_LOCATOR_KINDS: tuple[EntityKind, ...] = (
    EntityKind.CLASS,
    EntityKind.MEMBER,
    EntityKind.PROPERTY,
    EntityKind.DEPENDENCY,
    EntityKind.SYNTAX,
    EntityKind.DIAGNOSTIC,
)

#: An unresolved package (``npm:?#X``) has no key to search for.
_UNRESOLVED_PREFIX = "npm:?#"

BEHAVIORAL = "behavioral"
UNIVERSAL = "universal"

SOURCE_MODEL = "model"
SOURCE_RULE = "rule"
SOURCE_GUARD = "guard"
SOURCE_LOW_CONFIDENCE = "low_confidence"


@dataclass
class ContractResult:
    """What code decided after reading one System-1 answer."""

    signal: str
    confidence: float
    source: str
    keys: list[str] = field(default_factory=list)
    #: Keys that cannot be searched by key but can be searched by name.
    name_only_keys: list[str] = field(default_factory=list)
    #: Keys whose verification failed (``verified: false``).
    unverified_keys: list[str] = field(default_factory=list)
    reason: str = ""


def signal_keys(
    occurrences: list[NormalizedEntity], signal: str
) -> tuple[list[str], list[str], list[str]]:
    """``(keys, name_only_keys, unverified_keys)`` for one signal type.

    Only ``removed`` and ``mentioned`` occurrences count, and only the kind the
    signal type searches. Order follows the rule's own occurrence order and
    duplicates are dropped.
    """
    kinds = _LOCATOR_KINDS if signal == BEHAVIORAL else _SIGNAL_KINDS.get(signal)
    if kinds is None:
        return [], [], []
    keys: list[str] = []
    name_only: list[str] = []
    unverified: list[str] = []
    for occurrence in occurrences:
        if occurrence.role not in SEARCHABLE_ROLES or occurrence.kind not in kinds:
            continue
        if signal == "config" and not occurrence.file:
            # A config key with no known file cannot be looked up.
            continue
        if not occurrence.key:
            continue
        if occurrence.key.startswith(_UNRESOLVED_PREFIX):
            name_only.append(occurrence.key)
        if occurrence.verified in ("false", "ambiguous"):
            unverified.append(occurrence.key)
        if occurrence.key not in keys:
            keys.append(occurrence.key)
    return keys, name_only, unverified


def choose_signal(answers: dict, settings: SignalSettings) -> tuple[str, float]:
    """Chosen type and its probability from the ``signal`` answer."""
    answer = answers.get("signal")
    if not isinstance(answer, dict):
        return BEHAVIORAL, 0.0
    choice = answer.get("choice")
    probabilities = answer.get("probabilities")
    if not isinstance(choice, str) or not isinstance(probabilities, dict):
        return BEHAVIORAL, 0.0
    confidence = _as_float(probabilities.get(choice))
    return choice, confidence if confidence is not None else 0.0


def apply_contract(
    *,
    answer: dict,
    occurrences: list[NormalizedEntity],
    settings: SignalSettings,
) -> ContractResult:
    """FR-4.2 – FR-4.3: the guard and the confidence floors."""
    chosen, confidence = choose_signal(answer, settings)
    keys, name_only, unverified = signal_keys(occurrences, chosen)
    # Every fallback to ``behavioral`` carries the locator keys, so the planner
    # still knows where in the code to look (spec 027 FR-5).
    locators, locator_name_only, locator_unverified = signal_keys(occurrences, BEHAVIORAL)
    # After the guard the type is ``behavioral``; its own probability is the
    # honest confidence to record (FR-5).
    behavioral_prob = _probability(answer, BEHAVIORAL)

    if chosen in SEARCHABLE_SIGNALS:
        if not keys:
            return _guarded(
                "no searchable key for the chosen type",
                behavioral_prob,
                locators,
                locator_name_only,
                locator_unverified,
            )
        if confidence < settings.searchable_min_prob:
            return _floor(
                confidence, locators, locator_name_only, locator_unverified, settings
            )
    elif chosen == UNIVERSAL:
        if confidence < settings.universal_min_prob:
            return _floor(
                confidence, locators, locator_name_only, locator_unverified, settings
            )
        return ContractResult(
            signal=UNIVERSAL,
            confidence=confidence,
            source=SOURCE_MODEL,
            unverified_keys=unverified,
        )
    elif chosen != BEHAVIORAL:
        # Unknown label from the model: never trust it.
        return _guarded(
            f"unknown signal type {chosen!r}",
            behavioral_prob,
            locators,
            locator_name_only,
            locator_unverified,
        )
    return ContractResult(
        signal=chosen,
        confidence=confidence,
        source=SOURCE_MODEL,
        keys=keys,
        name_only_keys=name_only,
        unverified_keys=unverified,
    )


def rule_shortcut(
    *, occurrences: list[NormalizedEntity], change_type: str, source_section: str
) -> bool:
    """FR-4.5: an all-dependency component upgrade is a ``dependency`` rule.

    No model call is needed for the type; the features are still asked.
    """
    if not occurrences:
        return False
    if not all(occurrence.kind == EntityKind.DEPENDENCY for occurrence in occurrences):
        return False
    section = (change_type or "").strip().lower()
    return section == "component_upgrade" or (
        (source_section or "").strip().lower() == "component_upgrade"
    )


def shortcut_result(occurrences: list[NormalizedEntity]) -> ContractResult:
    keys, name_only, unverified = signal_keys(occurrences, "dependency")
    return ContractResult(
        signal="dependency",
        confidence=1.0,
        source=SOURCE_RULE,
        keys=keys,
        name_only_keys=name_only,
        unverified_keys=unverified,
        reason="every entity is a dependency and the change is a component upgrade",
    )


def chosen_features(answers: dict, feature_ids: list[str], settings: SignalSettings) -> tuple[list[str], dict[str, float]]:
    """Feature ids at or above the floor, plus every probability (FR-4.4)."""
    probabilities: dict[str, float] = {}
    chosen: list[str] = []
    for feature_id in feature_ids:
        answer = answers.get(f"feature.{feature_id}")
        probability = _as_float(answer.get("noul")) if isinstance(answer, dict) else None
        if probability is None:
            continue
        probabilities[feature_id] = probability
        if probability >= settings.feature_min_prob:
            chosen.append(feature_id)
    return chosen, probabilities


def _guarded(
    reason: str,
    confidence: float,
    keys: list[str],
    name_only: list[str],
    unverified: list[str],
) -> ContractResult:
    return ContractResult(
        signal=BEHAVIORAL,
        confidence=confidence,
        source=SOURCE_GUARD,
        keys=keys,
        name_only_keys=name_only,
        unverified_keys=unverified,
        reason=f"guard: {reason}",
    )


def _floor(
    confidence: float,
    keys: list[str],
    name_only: list[str],
    unverified: list[str],
    settings: SignalSettings,
) -> ContractResult:
    return ContractResult(
        signal=BEHAVIORAL,
        confidence=confidence,
        source=SOURCE_LOW_CONFIDENCE,
        keys=keys,
        name_only_keys=name_only,
        unverified_keys=unverified,
        reason=(
            f"low_confidence: probability {confidence:.2f} is below the floor "
            f"(searchable {settings.searchable_min_prob:.2f}, "
            f"universal {settings.universal_min_prob:.2f})"
        ),
    )


def _probability(answer: dict, choice: str) -> float:
    """Probability the model gave to ``choice``, ``0.0`` when absent."""
    entry = answer.get("signal")
    if not isinstance(entry, dict):
        return 0.0
    probabilities = entry.get("probabilities")
    if not isinstance(probabilities, dict):
        return 0.0
    value = _as_float(probabilities.get(choice))
    return value if value is not None else 0.0


def _as_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None
