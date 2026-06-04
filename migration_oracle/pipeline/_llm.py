"""LangChain provider factory and LLM invocation helpers."""

from __future__ import annotations

import re
import time
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage

from migration_oracle import config

_PROVIDER_MAP: dict[str, str] = {
    "bedrock": "bedrock",
    "openai": "openai",
    "anthropic": "anthropic",
    "ollama": "ollama",
    "litellm": "litellm",
    "google": "google_genai",
}


class LLMInvocationError(RuntimeError):
    """Raised when an LLM call fails after retries or validation."""


def get_llm() -> BaseChatModel:
    """Return a LangChain chat model for ``MODEL_PROVIDER``."""
    provider = config.MODEL_PROVIDER.lower()
    if provider not in _PROVIDER_MAP:
        supported = ", ".join(sorted(_PROVIDER_MAP))
        raise ValueError(
            f"Unsupported MODEL_PROVIDER {provider!r}; expected one of: {supported}"
        )

    model_id = config.MODEL_ID or None
    kwargs: dict[str, Any] = {"model_provider": _PROVIDER_MAP[provider]}
    if model_id:
        kwargs["model"] = model_id

    if provider == "litellm":
        base_url = config.LITELLM_BASE_URL or config.OPENAI_BASE_URL
        if base_url:
            kwargs["base_url"] = base_url
    elif provider == "openai":
        if config.OPENAI_BASE_URL:
            kwargs["base_url"] = config.OPENAI_BASE_URL
    elif provider == "ollama":
        kwargs["base_url"] = config.OLLAMA_HOST
    elif provider == "bedrock":
        kwargs["region_name"] = config.AWS_REGION

    return init_chat_model(**kwargs)


def _is_rate_limit_error(exc: BaseException) -> bool:
    if getattr(exc, "status_code", None) == 429:
        return True
    message = str(exc).lower()
    return "rate limit" in message or "429" in message or "throttl" in message


def invoke_with_retry(llm: BaseChatModel, prompt: str) -> str:
    """Invoke the LLM with exponential backoff on rate-limit errors only."""
    last_error: BaseException | None = None
    for attempt in range(config.EXTRACTION_RATE_LIMIT_RETRIES + 1):
        try:
            response = llm.invoke([HumanMessage(content=prompt)])
            content = response.content
            if isinstance(content, list):
                return "".join(
                    block.get("text", "") if isinstance(block, dict) else str(block)
                    for block in content
                )
            return str(content)
        except Exception as exc:
            last_error = exc
            if not _is_rate_limit_error(exc) or attempt >= config.EXTRACTION_RATE_LIMIT_RETRIES:
                raise LLMInvocationError(str(exc)) from exc
            delay = config.EXTRACTION_RETRY_BASE_DELAY * (2**attempt)
            time.sleep(delay)
    raise LLMInvocationError(str(last_error)) from last_error


_FENCE_RE = re.compile(
    r"^```(?:markdown|md)?\s*\n?(.*?)\n?```\s*$", re.DOTALL | re.IGNORECASE
)
_SECTION_START_RE = re.compile(r"^##\s+[🔴🟠🟡🔵]")


def strip_markdown_fences(text: str) -> str:
    """Remove wrapping ```markdown fences if present."""
    stripped = text.strip()
    match = _FENCE_RE.match(stripped)
    if match:
        return match.group(1).strip()
    return stripped


def strip_preamble(text: str) -> str:
    """Drop conversational preamble before the first severity section heading."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if _SECTION_START_RE.match(line.strip()):
            return "\n".join(lines[index:]).strip()
    return text.strip()
