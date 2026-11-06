"""Thresholds and client settings for the rule-signal stage (spec 027 FR-6).

The System-1 endpoint is the one triage uses (``TRIAGE_*``); only the
classification thresholds are new. Everything is read live from the
environment so tests and CLI flags see current values.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from migration_oracle.pipeline.triage.settings import TriageSettings


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value


@dataclass(frozen=True)
class SignalSettings:
    client: TriageSettings
    state_max_chars: int
    searchable_min_prob: float
    universal_min_prob: float
    feature_min_prob: float
    cache_dir: Path

    @property
    def enabled(self) -> bool:
        """Same off switch as triage: an empty base URL or model disables it."""
        return self.client.enabled

    @property
    def model(self) -> str:
        return self.client.model

    @property
    def max_concurrent(self) -> int:
        return self.client.max_concurrent


def load_settings() -> SignalSettings:
    return SignalSettings(
        client=TriageSettings(
            base_url=_env("TRIAGE_BASE_URL", "").strip(),
            endpoint_path=_env("TRIAGE_ENDPOINT_PATH", "/v1/systemone").strip(),
            model=_env("TRIAGE_MODEL", "").strip(),
            api_key=_env("TRIAGE_API_KEY", "").strip(),
            timeout_sec=float(_env("TRIAGE_TIMEOUT_SEC", "30")),
            max_concurrent=max(1, int(_env("TRIAGE_MAX_CONCURRENT", "2"))),
            # Triage's own cap is irrelevant here; the signal stage has its own.
            state_max_chars=int(_env("TRIAGE_STATE_MAX_CHARS", "6000")),
            drop_max_action_prob=0.0,
            drop_min_category_prob=0.0,
            drop_max_impact_score=0.0,
            filter_max_input_tokens=0,
            cache_dir=Path(_env("ARTIFACT_CACHE_DIR", "./artifacts")),
        ),
        state_max_chars=max(1, int(_env("SIGNAL_STATE_MAX_CHARS", "4000"))),
        searchable_min_prob=float(_env("SIGNAL_SEARCHABLE_MIN_PROB", "0.60")),
        universal_min_prob=float(_env("SIGNAL_UNIVERSAL_MIN_PROB", "0.60")),
        feature_min_prob=float(_env("SIGNAL_FEATURE_MIN_PROB", "0.50")),
        cache_dir=Path(_env("ARTIFACT_CACHE_DIR", "./artifacts")),
    )
