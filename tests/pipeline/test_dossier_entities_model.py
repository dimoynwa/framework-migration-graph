"""Dedicated entity model: settings, request shape, strict schema, wiring."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from migration_oracle import config
from migration_oracle.models.entities import MigrationEntitiesBatch
from migration_oracle.pipeline.entities import run as entity_run
from migration_oracle.pipeline.entities.model import (
    build_complete,
    load_entity_model,
    request_kwargs,
    strict_schema,
)

_ENV = (
    "ENTITY_MODEL_ID",
    "ENTITY_MODEL_PROVIDER",
    "ENTITY_BASE_URL",
    "ENTITY_API_KEY",
    "ENTITY_OUTPUT_FORMAT",
    "ENTITY_THINKING",
    "ENTITY_REASONING_EFFORT",
    "ENTITY_MAX_OUTPUT_TOKENS",
    "ENTITY_TIMEOUT_SEC",
    "OPENAI_API_KEY",
    "DEEPSEEK_API_KEY",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _ENV:
        monkeypatch.delenv(name, raising=False)


def test_unset_model_id_keeps_main_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "MODEL_ID", "main-model")
    assert load_entity_model() is None
    assert entity_run.entity_model_label() == "main-model"


def test_openai_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENTITY_MODEL_ID", "gpt-x")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    settings = load_entity_model()
    assert settings is not None
    assert settings.provider == "openai"
    assert settings.base_url == "https://api.openai.com/v1"
    assert settings.api_key == "sk-test"
    assert settings.output == "json_schema"
    assert settings.thinking is True
    assert settings.reasoning_effort == "high"
    kwargs = request_kwargs(settings, "PROMPT")
    assert kwargs["model"] == "gpt-x"
    assert kwargs["messages"] == [{"role": "user", "content": "PROMPT"}]
    assert kwargs["reasoning_effort"] == "high"
    assert kwargs["max_completion_tokens"] == 32000
    assert "max_tokens" not in kwargs
    fmt = kwargs["response_format"]
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["strict"] is True


def test_deepseek_uses_json_object_and_thinking_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENTITY_MODEL_PROVIDER", "deepseek")
    monkeypatch.setenv("ENTITY_MODEL_ID", "deepseek-v4-pro")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-test")
    monkeypatch.setenv("ENTITY_REASONING_EFFORT", "max")
    settings = load_entity_model()
    assert settings is not None
    assert settings.base_url == "https://api.deepseek.com"
    assert settings.api_key == "ds-test"
    kwargs = request_kwargs(settings, "PROMPT")
    assert kwargs["response_format"] == {"type": "json_object"}
    assert kwargs["extra_body"] == {"thinking": {"type": "enabled"}}
    assert kwargs["reasoning_effort"] == "max"
    assert kwargs["max_tokens"] == 32000


def test_deepseek_thinking_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENTITY_MODEL_PROVIDER", "deepseek")
    monkeypatch.setenv("ENTITY_MODEL_ID", "deepseek-v4-pro")
    monkeypatch.setenv("ENTITY_THINKING", "off")
    kwargs = request_kwargs(load_entity_model(), "PROMPT")
    assert kwargs["extra_body"] == {"thinking": {"type": "disabled"}}
    assert "reasoning_effort" not in kwargs


def test_deepseek_rejects_json_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENTITY_MODEL_PROVIDER", "deepseek")
    monkeypatch.setenv("ENTITY_MODEL_ID", "deepseek-v4-pro")
    monkeypatch.setenv("ENTITY_OUTPUT_FORMAT", "json_schema")
    with pytest.raises(ValueError, match="not supported by DeepSeek"):
        load_entity_model()


def test_bad_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENTITY_MODEL_ID", "x")
    monkeypatch.setenv("ENTITY_MODEL_PROVIDER", "qwen")
    with pytest.raises(ValueError, match="ENTITY_MODEL_PROVIDER"):
        load_entity_model()


def test_entity_api_key_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENTITY_MODEL_ID", "gpt-x")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    monkeypatch.setenv("ENTITY_API_KEY", "sk-entity")
    assert load_entity_model().api_key == "sk-entity"


def test_cache_label_changes_with_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENTITY_MODEL_ID", "gpt-x")
    first = entity_run.entity_model_label()
    monkeypatch.setenv("ENTITY_REASONING_EFFORT", "low")
    assert entity_run.entity_model_label() != first


def _objects(node):
    if isinstance(node, dict):
        if node.get("type") == "object" and "properties" in node:
            yield node
        for value in node.values():
            yield from _objects(value)
    elif isinstance(node, list):
        for item in node:
            yield from _objects(item)


def test_strict_schema_shape() -> None:
    schema = strict_schema()
    objects = list(_objects(schema))
    assert len(objects) >= 5  # batch, entity, scope, affected entity, step
    for obj in objects:
        assert obj["additionalProperties"] is False
        assert set(obj["required"]) == set(obj["properties"])
    assert "default" not in json.dumps(schema).replace('"default_', "")
    # The schema stays valid for the model it came from.
    MigrationEntitiesBatch.model_validate({"entities": []})


class _FakeCompletions:
    def __init__(self, reply: str | None, finish_reason: str = "stop") -> None:
        self.reply = reply
        self.finish_reason = finish_reason
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        message = SimpleNamespace(content=self.reply, refusal=None)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message, finish_reason=self.finish_reason)]
        )


def _fake_openai(monkeypatch: pytest.MonkeyPatch, completions: _FakeCompletions) -> dict:
    seen: dict = {}

    class FakeOpenAI:
        def __init__(self, **kwargs) -> None:
            seen.update(kwargs)
            self.chat = SimpleNamespace(completions=completions)

    import openai

    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)
    return seen


def test_build_complete_sends_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENTITY_MODEL_ID", "gpt-x")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    completions = _FakeCompletions('{"entities": []}')
    seen = _fake_openai(monkeypatch, completions)
    complete = build_complete(load_entity_model())
    assert complete("PROMPT") == '{"entities": []}'
    assert seen["api_key"] == "sk-test"
    assert seen["base_url"] == "https://api.openai.com/v1"
    assert completions.calls[0]["model"] == "gpt-x"


@pytest.mark.parametrize(
    ("reply", "finish", "message"),
    [("", "stop", "empty reply"), ('{"entit', "length", "cut off")],
)
def test_build_complete_errors(
    monkeypatch: pytest.MonkeyPatch, reply: str, finish: str, message: str
) -> None:
    monkeypatch.setenv("ENTITY_MODEL_ID", "gpt-x")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    _fake_openai(monkeypatch, _FakeCompletions(reply, finish))
    complete = build_complete(load_entity_model())
    with pytest.raises(RuntimeError, match=message):
        complete("PROMPT")


def test_missing_key_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENTITY_MODEL_ID", "gpt-x")
    with pytest.raises(SystemExit):
        entity_run._require_model()


def test_entity_model_does_not_need_main_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "MODEL_ID", "")
    monkeypatch.setattr(config, "MODEL_PROVIDER", "")
    monkeypatch.setenv("ENTITY_MODEL_ID", "gpt-x")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    entity_run._require_model()


TABLE = """\
| Type | Confidence | Source | Statement | Category | Impact score |
| --- | --- | --- | --- | --- | --- |
| breaking | confirmed | https://github.com/angular/angular/pull/1 | Title: Alpha change | breaking | 2 |
"""


def test_run_uses_entity_model(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from migration_oracle.pipeline.entities.settings import EntitySettings
    from migration_oracle.pipeline.research.schema import ResearchDossier

    monkeypatch.setattr(config, "MODEL_ID", "")
    monkeypatch.setattr(config, "MODEL_PROVIDER", "")
    monkeypatch.setenv("ENTITY_MODEL_ID", "gpt-x")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    reply = json.dumps(
        {
            "entities": [
                {
                    "source_section": "breaking_change",
                    "title": "Alpha change",
                    "jira_keys": [],
                    "source_url": "",
                    "change_type": "breaking_change",
                    "reason_type": "",
                    "reason": "Alpha was removed.",
                    "scopes": [{"scope": "api-surface", "severity": "high"}],
                    "entities": [],
                    "steps": [],
                    "subsystem": "",
                }
            ]
        }
    )
    completions = _FakeCompletions(reply)
    _fake_openai(monkeypatch, completions)

    def forbid(_prompt: str) -> str:
        raise AssertionError("main model must not run when ENTITY_MODEL_ID is set")

    monkeypatch.setattr(entity_run, "_default_complete", forbid)
    result = entity_run.run_dossier_entities(
        filter_md=TABLE,
        dossiers=[
            ResearchDossier(
                row_key="k",
                status="ok",
                text="**Action:** required\n\n**What changed:** Alpha change",
                sources=["https://github.com/angular/angular/pull/1"],
            )
        ],
        framework_key="angular",
        framework_display="Angular",
        hop=("19.0.0", "20.0.0"),
        filtered_path=tmp_path / "filtered.md",
        json_path=tmp_path / "entities.json",
        settings=EntitySettings(
            concurrency=1,
            cluster_max_rows=4,
            cluster_confirm="off",
            protected_categories=frozenset({"breaking"}),
            cache_dir=tmp_path / "cache",
        ),
        clusters_jsonl=tmp_path / "clusters.jsonl",
        clusters_summary=tmp_path / "summary.json",
    )
    assert [entity.title for entity in result.batch.entities] == ["Alpha change"]
    assert len(completions.calls) == 1
    assert completions.calls[0]["response_format"]["type"] == "json_schema"
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["model"].startswith("openai:gpt-x:json_schema")
