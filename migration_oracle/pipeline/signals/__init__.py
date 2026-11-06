"""Rule detection signals (spec 027): how a service shows that a rule applies.

Public entry points:

- :func:`classify_signals` — classify one hop's rules, write ``runs/signals/``
- :func:`signal_questions` — the System-1 question set (``SIGNAL_QUESTIONS_VERSION``)
- :func:`features_for` — the per-framework feature vocabulary and evidence keys
- :func:`apply_contract` — the rule-based guard and confidence floors
"""

from migration_oracle.pipeline.signals.contract import (
    ContractResult,
    apply_contract,
    chosen_features,
    rule_shortcut,
    shortcut_result,
    signal_keys,
)
from migration_oracle.pipeline.signals.features import (
    ANGULAR_FEATURES,
    SPRING_BOOT_FEATURES,
    Feature,
    feature_ids,
    features_for,
)
from migration_oracle.pipeline.signals.questions import (
    SEARCHABLE_SIGNALS,
    SIGNAL_CRITERIA,
    SIGNAL_QUESTIONS_VERSION,
    signal_questions,
)
from migration_oracle.pipeline.signals.run import (
    NIMBLE_DISABLED,
    NIMBLE_OK,
    NIMBLE_PARTIAL,
    NIMBLE_UNAVAILABLE,
    SignalRecord,
    SignalRunResult,
    cache_key,
    classify_signals,
    render_state,
    reset_notices,
)
from migration_oracle.pipeline.signals.settings import SignalSettings, load_settings

__all__ = [
    "ANGULAR_FEATURES",
    "ContractResult",
    "Feature",
    "NIMBLE_DISABLED",
    "NIMBLE_OK",
    "NIMBLE_PARTIAL",
    "NIMBLE_UNAVAILABLE",
    "SEARCHABLE_SIGNALS",
    "SIGNAL_CRITERIA",
    "SIGNAL_QUESTIONS_VERSION",
    "SPRING_BOOT_FEATURES",
    "SignalRecord",
    "SignalRunResult",
    "SignalSettings",
    "apply_contract",
    "cache_key",
    "chosen_features",
    "classify_signals",
    "feature_ids",
    "features_for",
    "load_settings",
    "render_state",
    "reset_notices",
    "rule_shortcut",
    "shortcut_result",
    "signal_keys",
    "signal_questions",
]
