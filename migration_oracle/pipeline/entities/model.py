"""Dedicated model for dossier entity calls.

``ENTITY_MODEL_ID`` set: the entity step calls its own OpenAI-compatible endpoint
(OpenAI or DeepSeek) with JSON output and reasoning. Unset: it uses the main
``MODEL_PROVIDER`` / ``MODEL_ID`` through LangChain, as before.

Providers:

- ``openai``: ``response_format`` ``json_schema`` with ``strict: true``, built from
  ``MigrationEntitiesBatch``, so the reply always matches the schema.
  ``reasoning_effort`` sets the depth of thinking.
- ``deepseek``: ``response_format`` ``json_object``. DeepSeek has no schema-enforced
  mode, so the reply is still validated by ``_parse_json_response``. Thinking
  is switched with ``thinking: {"type": "enabled" | "disabled"}``, and
  ``reasoning_effort`` sets its depth.

Read from the environment on each call so tests and CLI flags see current values.
"""

from __future__ import annotations

import copy
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from migration_oracle.models.entities import MigrationEntitiesBatch

PROVIDERS = ("openai", "deepseek")
OUTPUT_MODES = ("json_schema", "json_object", "off")

_DEFAULT_BASE_URL = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com",
}
_KEY_ENV = {"openai": "OPENAI_API_KEY", "deepseek": "DEEPSEEK_API_KEY"}
_DEFAULT_OUTPUT = {"openai": "json_schema", "deepseek": "json_object"}


def _env(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip()


@dataclass(frozen=True)
class EntityModelSettings:
    provider: str
    model_id: str
    base_url: str
    api_key: str
    output: str
    thinking: bool
    reasoning_effort: str
    max_tokens: int
    timeout_sec: float

    @property
    def cache_label(self) -> str:
        """Part of the per-cluster cache key: a different model or mode is a miss."""
        effort = self.reasoning_effort or "-"
        thinking = "think" if self.thinking else "nothink"
        return f"{self.provider}:{self.model_id}:{self.output}:{thinking}:{effort}"


def load_entity_model() -> EntityModelSettings | None:
    """``None`` when ``ENTITY_MODEL_ID`` is unset (use the main model)."""
    model_id = _env("ENTITY_MODEL_ID")
    if not model_id:
        return None
    provider = _env("ENTITY_MODEL_PROVIDER", "openai").lower()
    if provider not in PROVIDERS:
        raise ValueError(f"ENTITY_MODEL_PROVIDER must be one of: {', '.join(PROVIDERS)}")
    output = _env("ENTITY_OUTPUT_FORMAT", _DEFAULT_OUTPUT[provider]).lower()
    if output not in OUTPUT_MODES:
        raise ValueError(f"ENTITY_OUTPUT_FORMAT must be one of: {', '.join(OUTPUT_MODES)}")
    if provider == "deepseek" and output == "json_schema":
        raise ValueError(
            "ENTITY_OUTPUT_FORMAT=json_schema is not supported by DeepSeek; use json_object"
        )
    thinking = _env("ENTITY_THINKING", "on").lower()
    if thinking not in {"on", "off"}:
        raise ValueError("ENTITY_THINKING must be 'on' or 'off'")
    api_key = _env("ENTITY_API_KEY") or _env(_KEY_ENV[provider])
    return EntityModelSettings(
        provider=provider,
        model_id=model_id,
        base_url=_env("ENTITY_BASE_URL", _DEFAULT_BASE_URL[provider]),
        api_key=api_key,
        output=output,
        thinking=thinking == "on",
        reasoning_effort=_env("ENTITY_REASONING_EFFORT", "high").lower(),
        max_tokens=max(1024, int(_env("ENTITY_MAX_OUTPUT_TOKENS", "32000"))),
        timeout_sec=float(_env("ENTITY_TIMEOUT_SEC", "300")),
    )


def require_entity_model(settings: EntityModelSettings) -> None:
    if not settings.api_key:
        raise ValueError(
            f"ENTITY_API_KEY or {_KEY_ENV[settings.provider]} must be set "
            f"for ENTITY_MODEL_PROVIDER={settings.provider}"
        )


def strict_schema(model: type = MigrationEntitiesBatch) -> dict[str, Any]:
    """JSON Schema in the shape OpenAI strict mode accepts.

    Every object gets ``additionalProperties: false`` and lists all properties
    in ``required``. Defaults are removed, so a field with a default becomes a
    required field the model fills (``""`` or ``[]``).
    """
    schema = copy.deepcopy(model.model_json_schema())

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            node.pop("default", None)
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(schema)
    return schema


def request_kwargs(settings: EntityModelSettings, prompt: str) -> dict[str, Any]:
    """Arguments for ``client.chat.completions.create`` for one entity call."""
    kwargs: dict[str, Any] = {
        "model": settings.model_id,
        "messages": [{"role": "user", "content": prompt}],
    }
    if settings.output == "json_schema":
        kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "migration_entities_batch",
                "strict": True,
                "schema": strict_schema(),
            },
        }
    elif settings.output == "json_object":
        kwargs["response_format"] = {"type": "json_object"}

    if settings.provider == "openai":
        kwargs["max_completion_tokens"] = settings.max_tokens
        if settings.thinking and settings.reasoning_effort:
            kwargs["reasoning_effort"] = settings.reasoning_effort
        elif not settings.thinking:
            kwargs["reasoning_effort"] = "none"
    else:  # deepseek
        kwargs["max_tokens"] = settings.max_tokens
        kwargs["extra_body"] = {
            "thinking": {"type": "enabled" if settings.thinking else "disabled"}
        }
        if settings.thinking and settings.reasoning_effort:
            kwargs["reasoning_effort"] = settings.reasoning_effort
    return kwargs


def build_complete(settings: EntityModelSettings) -> Callable[[str], str]:
    """A ``prompt -> reply text`` callable over the OpenAI SDK.

    The SDK retries connection errors, 429 and 5xx. An empty reply (DeepSeek
    blanks invalid JSON) raises, so the caller's second attempt runs.
    """
    from openai import OpenAI

    require_entity_model(settings)
    client = OpenAI(
        api_key=settings.api_key,
        base_url=settings.base_url,
        timeout=settings.timeout_sec,
        max_retries=3,
    )

    def complete(prompt: str) -> str:
        response = client.chat.completions.create(**request_kwargs(settings, prompt))
        choice = response.choices[0]
        refusal = getattr(choice.message, "refusal", None)
        if refusal:
            raise RuntimeError(f"model refused: {refusal}")
        if choice.finish_reason == "length":
            raise RuntimeError(
                "reply cut off at ENTITY_MAX_OUTPUT_TOKENS="
                f"{settings.max_tokens}; raise it"
            )
        content = (choice.message.content or "").strip()
        if not content:
            raise RuntimeError("empty reply from entity model")
        return content

    return complete
