"""Live research settings.

Read from the environment on each call so tests and CLI flags see current values.
An empty ``RESEARCH_BASE_URL`` or ``RESEARCH_MODEL_ID`` turns the stage off.
An empty ``TAVILY_API_KEY`` keeps the stage on without ``web_search``: the model
then reads the row's Sources and the links on fetched pages with ``fetch_url``.

Two timeouts, on purpose: ``timeout_sec`` is the wall-clock budget for one row
(the whole tool-calling loop) and ``model_timeout_sec`` is the budget for one
HTTP request to the model. Keeping them apart stops a single hung completion
from eating the row.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("migration_oracle.pipeline.research")

_CHAT_COMPLETIONS_SUFFIX = "/chat/completions"
_trim_logged = False


def reset_url_notice() -> None:
    """Test hook. The base-URL trim is logged once per process."""
    global _trim_logged
    _trim_logged = False


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value


def _flag(name: str, default: str = "false") -> bool:
    return _env(name, default).strip().lower() in {"1", "true", "yes", "on"}


def normalize_base_url(raw: str) -> str:
    """Return the OpenAI API root.

    The client appends ``/chat/completions`` itself. A value that already ends
    in that path is trimmed once, with one DEBUG line.
    """
    global _trim_logged
    value = raw.strip().rstrip("/")
    if not value.endswith(_CHAT_COMPLETIONS_SUFFIX):
        return value
    trimmed = value[: -len(_CHAT_COMPLETIONS_SUFFIX)].rstrip("/")
    if not _trim_logged:
        logger.debug(
            "RESEARCH_BASE_URL ending in /chat/completions was trimmed to %s",
            trimmed,
        )
        _trim_logged = True
    return trimmed


def completions_url(base_url: str) -> str:
    """Request URL for a chat completion. Both accepted base forms match."""
    root = normalize_base_url(base_url)
    return root.rstrip("/") + "/chat/completions"


@dataclass(frozen=True)
class ResearchSettings:
    base_url: str
    model_id: str
    api_key: str
    tavily_api_key: str
    enable_thinking: bool
    max_concurrent: int
    max_tool_calls: int
    timeout_sec: float
    search_results: int
    fetch_max_chars: int
    entity_max_input_tokens: int
    cache_dir: Path
    shared_url_max_rows: int = 3
    raw_context_max_chars: int = 8000
    model_timeout_sec: float = 60.0

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and self.model_id)

    @property
    def search_enabled(self) -> bool:
        """``web_search`` (Tavily) is offered only when a key is set."""
        return bool(self.tavily_api_key)

    @property
    def completions_url(self) -> str:
        return completions_url(self.base_url)


def load_settings() -> ResearchSettings:
    timeout_sec = float(_env("RESEARCH_TIMEOUT_SEC", "240"))
    # A per-request timeout at or above the row budget would never fire first.
    model_timeout_sec = min(float(_env("RESEARCH_MODEL_TIMEOUT_SEC", "60")), timeout_sec)
    return ResearchSettings(
        base_url=normalize_base_url(_env("RESEARCH_BASE_URL", "")),
        model_id=_env("RESEARCH_MODEL_ID", "").strip(),
        api_key=_env("RESEARCH_API_KEY", "").strip(),
        tavily_api_key=_env("TAVILY_API_KEY", "").strip(),
        enable_thinking=_flag("RESEARCH_ENABLE_THINKING"),
        max_concurrent=max(1, int(_env("RESEARCH_MAX_CONCURRENT", "4"))),
        max_tool_calls=max(1, int(_env("RESEARCH_MAX_TOOL_CALLS", "8"))),
        timeout_sec=timeout_sec,
        search_results=max(1, int(_env("RESEARCH_SEARCH_RESULTS", "5"))),
        fetch_max_chars=max(1, int(_env("RESEARCH_FETCH_MAX_CHARS", "20000"))),
        shared_url_max_rows=max(1, int(_env("RESEARCH_SHARED_URL_MAX_ROWS", "3"))),
        raw_context_max_chars=max(1, int(_env("RESEARCH_RAW_CONTEXT_MAX_CHARS", "8000"))),
        entity_max_input_tokens=max(1, int(_env("ENTITY_MAX_INPUT_TOKENS", "60000"))),
        cache_dir=Path(_env("ARTIFACT_CACHE_DIR", "./artifacts")),
        model_timeout_sec=model_timeout_sec,
    )
