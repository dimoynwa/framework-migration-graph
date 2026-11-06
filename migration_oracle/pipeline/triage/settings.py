"""Live triage settings. Read from the environment on each call so tests and CLI flags see current values."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value


@dataclass(frozen=True)
class TriageSettings:
    base_url: str
    endpoint_path: str
    model: str
    api_key: str
    timeout_sec: float
    max_concurrent: int
    state_max_chars: int
    drop_max_action_prob: float
    drop_min_category_prob: float
    drop_max_impact_score: float
    filter_max_input_tokens: int
    cache_dir: Path

    @property
    def enabled(self) -> bool:
        return bool(self.base_url.strip() and self.model.strip())

    @property
    def endpoint_url(self) -> str:
        return self.base_url.rstrip("/") + "/" + self.endpoint_path.lstrip("/")


def load_settings() -> TriageSettings:
    return TriageSettings(
        base_url=_env("TRIAGE_BASE_URL", "").strip(),
        endpoint_path=_env("TRIAGE_ENDPOINT_PATH", "/v1/systemone").strip(),
        model=_env("TRIAGE_MODEL", "").strip(),
        api_key=_env("TRIAGE_API_KEY", "").strip(),
        timeout_sec=float(_env("TRIAGE_TIMEOUT_SEC", "30")),
        max_concurrent=max(1, int(_env("TRIAGE_MAX_CONCURRENT", "2"))),
        state_max_chars=max(1, int(_env("TRIAGE_STATE_MAX_CHARS", "6000"))),
        drop_max_action_prob=float(_env("TRIAGE_DROP_MAX_ACTION_PROB", "0.20")),
        drop_min_category_prob=float(_env("TRIAGE_DROP_MIN_CATEGORY_PROB", "0.80")),
        drop_max_impact_score=float(_env("TRIAGE_DROP_MAX_IMPACT_SCORE", "1.0")),
        filter_max_input_tokens=int(_env("FILTER_MAX_INPUT_TOKENS", "60000")),
        cache_dir=Path(_env("ARTIFACT_CACHE_DIR", "./artifacts")),
    )
