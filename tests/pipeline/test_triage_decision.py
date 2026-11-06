"""Decision rule, HTTP contract, and fail-open behaviour."""

from __future__ import annotations

import json
import logging

import httpx
import pytest

from migration_oracle.models.entities import DocumentedChange
from migration_oracle.pipeline.triage.client import (
    System1HttpClient,
    TriageRejected,
    TriageUnavailable,
)
from migration_oracle.pipeline.triage.questions import triage_questions
from migration_oracle.pipeline.triage.rules import should_drop
from migration_oracle.pipeline.triage.run import render_state, run_triage
from migration_oracle.pipeline.triage.settings import TriageSettings, load_settings

RECORDED = {
    "model": "nimble",
    "answers": {
        "requires_action": {"type": "noul", "noul": 0.8495},
        "category": {
            "type": "choice",
            "choice": "behavior_change",
            "probabilities": {
                "breaking": 0.022,
                "behavior_change": 0.815,
                "internal_fix": 0.161,
                "noise": 0.002,
            },
            "confidence": 0.599,
        },
        "impact": {
            "type": "score",
            "score": 1.127,
            "legend": {"0": "none", "1": "low", "2": "medium", "3": "high"},
            "probabilities": {"0": 0.051, "1": 0.772, "2": 0.174, "3": 0.002},
            "confidence": 0.517,
        },
    },
    "usage": {"input_tokens": 1537, "output_tokens": 4},
}


def _settings(**overrides: object) -> TriageSettings:
    base = load_settings()
    data = {
        "base_url": "http://triage.example",
        "model": "nimble",
        "endpoint_path": "/v1/systemone",
    }
    data.update(overrides)
    return TriageSettings(
        base_url=str(data.get("base_url", base.base_url)),
        endpoint_path=str(data.get("endpoint_path", base.endpoint_path)),
        model=str(data.get("model", base.model)),
        api_key=str(data.get("api_key", base.api_key)),
        timeout_sec=float(data.get("timeout_sec", base.timeout_sec)),
        max_concurrent=int(data.get("max_concurrent", base.max_concurrent)),
        state_max_chars=int(data.get("state_max_chars", base.state_max_chars)),
        drop_max_action_prob=float(data.get("drop_max_action_prob", base.drop_max_action_prob)),
        drop_min_category_prob=float(
            data.get("drop_min_category_prob", base.drop_min_category_prob)
        ),
        drop_max_impact_score=float(
            data.get("drop_max_impact_score", base.drop_max_impact_score)
        ),
        filter_max_input_tokens=int(
            data.get("filter_max_input_tokens", base.filter_max_input_tokens)
        ),
        cache_dir=base.cache_dir,
    )


def _answers(*, noul: float, probability: float, score: float, choice: str = "internal_fix") -> dict:
    return {
        "requires_action": {"type": "noul", "noul": noul},
        "category": {
            "type": "choice",
            "choice": choice,
            "probabilities": {choice: probability},
            "confidence": 0.4,
        },
        "impact": {"type": "score", "score": score, "confidence": 0.4},
    }


def _change(statement: str = "Title: fix(core): adjust an internal counter\n") -> DocumentedChange:
    return DocumentedChange(
        type="behavioral",
        confidence="inferred",
        source_url="https://example.com/row",
        statement=statement,
    )


class _ScriptedTransport(httpx.AsyncBaseTransport):
    def __init__(self, script: list[httpx.Response | Exception]) -> None:
        self.script = list(script)
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


async def _no_sleep(_delay: float) -> None:
    return None


def test_ac3_drop_only_when_every_condition_holds() -> None:
    settings = _settings()
    assert should_drop(_answers(noul=0.05, probability=0.9, score=0.4), settings)
    assert not should_drop(_answers(noul=0.05, probability=0.7, score=0.4), settings)
    assert not should_drop(_answers(noul=0.05, probability=0.9, score=1.2), settings)
    assert not should_drop(
        _answers(noul=0.05, probability=0.9, score=0.4, choice="behavior_change"),
        settings,
    )


def test_ac3a_client_serialises_questions_and_parses_the_recorded_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TRIAGE_BASE_URL", "http://triage.example")
    monkeypatch.setenv("TRIAGE_MODEL", "nimble")
    transport = _ScriptedTransport([httpx.Response(200, json=RECORDED)])
    client = System1HttpClient(_settings(), transport=transport, sleep=_no_sleep)

    result = run_triage(
        [_change()],
        "Angular",
        ("19.0.0", "19.0.1"),
        client=client,
        settings=_settings(),
    )

    body = json.loads(transport.requests[0].content)
    assert body["model"] == "nimble"
    assert body["questions"]["requires_action"]["type"] == "noul"
    assert "criteria" not in body["questions"]["requires_action"]
    assert isinstance(body["questions"]["category"]["criteria"], dict)
    assert body["questions"]["category"]["criteria"]["behavior_change"]
    assert body["questions"]["impact"]["criteria"] == ["none", "low", "medium", "high"]
    assert set(body["questions"]) == set(triage_questions())
    row = result.rows[0]
    assert row.decision == "keep"
    assert row.source == "model"
    meta = row.change.metadata or {}
    assert meta["triage_action_prob"] == 0.8495
    assert meta["triage_category"] == "behavior_change"
    assert meta["triage_category_prob"] == 0.815
    assert meta["triage_category_confidence"] == 0.599
    assert meta["triage_impact_score"] == 1.127
    assert result.input_tokens == 1537


def test_ac3a_http_400_disables_the_run_with_one_error(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("TRIAGE_BASE_URL", "http://triage.example")
    monkeypatch.setenv("TRIAGE_MODEL", "nimble")
    transport = _ScriptedTransport(
        [httpx.Response(400, json={"error": "score criteria must be an array"})]
    )
    client = System1HttpClient(_settings(), transport=transport, sleep=_no_sleep)
    caplog.set_level(logging.ERROR, logger="migration_oracle.pipeline.triage")

    result = run_triage(
        [_change("Title: one\n"), _change("Title: two\n")],
        "Angular",
        ("19.0.0", "19.0.1"),
        client=client,
        settings=_settings(),
    )

    assert len(transport.requests) == 1
    assert all(row.decision == "keep" and row.source == "error" for row in result.rows)
    errors = [rec for rec in caplog.records if rec.levelno >= logging.ERROR]
    assert len(errors) == 1
    assert "score criteria must be an array" in errors[0].message


def test_ac4_timeout_keeps_the_row_and_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TRIAGE_BASE_URL", "http://triage.example")
    monkeypatch.setenv("TRIAGE_MODEL", "nimble")
    transport = _ScriptedTransport(
        [
            httpx.ReadTimeout("slow"),
            httpx.ReadTimeout("slow"),
            httpx.ReadTimeout("slow"),
            httpx.Response(200, json=RECORDED),
        ]
    )
    client = System1HttpClient(_settings(), transport=transport, sleep=_no_sleep)

    result = run_triage(
        [
            _change("Title: first row that times out\n"),
            _change("Title: second row that succeeds\n"),
        ],
        "Spring Boot",
        ("3.0.0", "3.0.1"),
        client=client,
        settings=_settings(),
    )

    assert result.rows[0].decision == "keep"
    assert result.rows[0].source == "error"
    assert result.rows[1].source == "model"
    assert result.rows[1].decision == "keep"
    assert len(transport.requests) == 4


def test_http_5xx_is_retried_then_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRIAGE_BASE_URL", "http://triage.example")
    monkeypatch.setenv("TRIAGE_MODEL", "nimble")
    transport = _ScriptedTransport(
        [
            httpx.Response(503, text="busy"),
            httpx.Response(503, text="busy"),
            httpx.Response(503, text="busy"),
        ]
    )
    client = System1HttpClient(_settings(), transport=transport, sleep=_no_sleep)
    result = run_triage(
        [_change()],
        "Spring Boot",
        ("3.0.0", "3.0.1"),
        client=client,
        settings=_settings(),
    )
    assert len(transport.requests) == 3
    assert result.rows[0].source == "error"
    assert result.rows[0].decision == "keep"


def test_ac5a_connection_refused_keeps_every_row_with_one_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("TRIAGE_BASE_URL", "http://triage.example")
    monkeypatch.setenv("TRIAGE_MODEL", "nimble")
    transport = _ScriptedTransport([httpx.ConnectError("connection refused")] * 3)
    client = System1HttpClient(_settings(), transport=transport, sleep=_no_sleep)
    caplog.set_level(logging.WARNING, logger="migration_oracle.pipeline.triage")
    breaking = DocumentedChange(
        type="breaking",
        confidence="confirmed",
        source_url="https://example.com/breaking",
        statement="Title: remove the legacy API\n",
    )

    result = run_triage(
        [breaking, _change()],
        "Angular",
        ("19.0.0", "19.0.1"),
        client=client,
        settings=_settings(),
    )

    assert all(row.decision == "keep" and row.source == "error" for row in result.rows)
    warnings = [rec for rec in caplog.records if rec.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "unreachable" in warnings[0].message.lower()


def test_state_omits_the_release_line_and_includes_only_present_fields() -> None:
    change = DocumentedChange(
        type="behavioral",
        confidence="inferred",
        source_url="https://example.com/c",
        statement=(
            "Title: fix(core): correctly perform lazy routes migration\n"
            "Commit: the migration would crash\n"
            "Issue: #58793 Lazy routes migration crashes\n"
            "Release: fix(core): correctly perform lazy routes migration\n"
        ),
        metadata={
            "angular_package": "core",
            "angular_commit_type": "fix",
            "github_labels": ["type: bug"],
            "has_schematic": False,
            "github_files": ["packages/core/src/render3/jit/environment.ts"],
        },
    )
    state = render_state(
        change, framework="Angular", hop=("19.0.0", "19.0.1"), max_chars=6000
    )
    assert "Framework: Angular" in state
    assert "Hop: 19.0.0 → 19.0.1" in state
    assert "Raw type: behavioral (inferred)" in state
    assert "Package: core" in state
    assert "Commit type: fix" in state
    assert "Labels: type: bug" in state
    assert "Has ng-update schematic: no" in state
    assert "packages/core/src/render3/jit/environment.ts" in state
    assert "Release:" not in state
    assert state.index("Change:") < state.index("Title:")


def test_rejected_and_unavailable_are_distinct() -> None:
    assert issubclass(TriageRejected, Exception)
    assert issubclass(TriageUnavailable, Exception)
