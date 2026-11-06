"""Cache reuse, raw-file round trip, and filter-input shape."""

from __future__ import annotations

import pytest

from migration_oracle.models.entities import DocumentedChange
from migration_oracle.pipeline.filters import FILTER_PROMPT, _filter_chunks
from migration_oracle.pipeline.triage.client import FakeTriageClient
from migration_oracle.pipeline.triage.markdown import (
    FILTER_TABLE_HEADER,
    TRIAGE_TABLE_HEADER,
    build_filter_markdown,
    parse_raw_markdown,
    render_raw_markdown,
)
from migration_oracle.pipeline.triage import questions as questions_module
from migration_oracle.pipeline.triage.run import prepare_range_documents, run_triage
from migration_oracle.pipeline.triage.settings import load_settings

DROP_ANSWERS = {
    "requires_action": {"type": "noul", "noul": 0.05},
    "category": {
        "type": "choice",
        "choice": "internal_fix",
        "probabilities": {"internal_fix": 0.91},
        "confidence": 0.2,
    },
    "impact": {"type": "score", "score": 0.4, "confidence": 0.2},
}


def _enable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRIAGE_BASE_URL", "http://triage.example")
    monkeypatch.setenv("TRIAGE_MODEL", "nimble")


def _plain(statement: str, *, source: str = "https://example.com/row") -> DocumentedChange:
    return DocumentedChange(
        type="behavioral",
        confidence="inferred",
        source_url=source,
        statement=statement,
    )


def test_ac5_unset_config_keeps_the_historical_raw_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TRIAGE_BASE_URL", raising=False)
    monkeypatch.delenv("TRIAGE_MODEL", raising=False)
    changes = [
        (
            "1.0.0",
            "2.0.0",
            [
                DocumentedChange(
                    type="breaking",
                    confidence="confirmed",
                    source_url="https://example.com/break",
                    statement="Title: remove the legacy API\n",
                )
            ],
        )
    ]
    client = FakeTriageClient(DROP_ANSWERS)
    prepared = prepare_range_documents(
        framework_key="stub_framework",
        framework_display="Stub Framework",
        from_version="1.0.0",
        to_version="2.0.0",
        hop_changes=changes,
        existing_raw=None,
        range_metadata=None,
        skip_triage=False,
        force_triage=False,
        retriage_from_cache=False,
        client=client,
        settings=load_settings(),
    )
    assert client.calls == []
    assert TRIAGE_TABLE_HEADER not in prepared.raw_md
    assert prepared.filter_md == prepared.raw_md
    assert "| Type | Confidence | Source | Statement |" in prepared.raw_md
    assert "| breaking | confirmed | https://example.com/break |" in prepared.raw_md


def test_ac6_cache_is_reused_until_the_question_version_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable(monkeypatch)
    settings = load_settings()
    client = FakeTriageClient(DROP_ANSWERS)
    change = _plain("Title: fix an internal counter\n")
    hop = ("3.0.0", "3.0.1")

    first = run_triage([change], "Spring Boot", hop, client=client, settings=settings)
    second = run_triage([change], "Spring Boot", hop, client=client, settings=settings)

    assert len(client.calls) == 1
    assert first.rows[0].decision == "drop"
    assert second.rows[0].decision == "drop"
    assert second.cache_hits == 1

    monkeypatch.setattr(questions_module, "TRIAGE_QUESTIONS_VERSION", 2)
    third = run_triage([change], "Spring Boot", hop, client=client, settings=settings)
    assert len(client.calls) == 2
    assert third.rows[0].source == "model"


def test_ac6a_raw_file_keeps_every_row_and_round_trips_decisions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable(monkeypatch)
    kept = DocumentedChange(
        type="breaking",
        confidence="confirmed",
        source_url="https://example.com/keep",
        statement="Title: breaking public API removal\n",
    )
    dropped = _plain("Title: fix an internal counter\n", source="https://example.com/drop")
    prepared = prepare_range_documents(
        framework_key="angular",
        framework_display="Angular",
        from_version="19.0.0",
        to_version="19.0.1",
        hop_changes=[("19.0.0", "19.0.1", [kept, dropped])],
        existing_raw=None,
        range_metadata=None,
        skip_triage=False,
        force_triage=False,
        retriage_from_cache=False,
        client=FakeTriageClient(DROP_ANSWERS),
        settings=load_settings(),
    )
    assert "- **Triage:**" in prepared.raw_md
    assert TRIAGE_TABLE_HEADER in prepared.raw_md
    parsed = parse_raw_markdown(prepared.raw_md)
    assert [row.triage_decision for row in parsed.rows] == ["keep", "drop"]
    assert [row.triage_source for row in parsed.rows] == ["rule", "model"]
    assert [row.source_url for row in parsed.rows] == [
        "https://example.com/keep",
        "https://example.com/drop",
    ]
    again = render_raw_markdown(
        framework_key="angular",
        framework_display="Angular",
        from_version="19.0.0",
        to_version="19.0.1",
        hop_changes=[
            (
                "19.0.0",
                "19.0.1",
                [
                    DocumentedChange(
                        type=row.type,
                        confidence=row.confidence,
                        source_url=row.source_url,
                        statement=row.statement,
                        metadata={
                            "triage_decision": row.triage_decision,
                            "triage_source": row.triage_source,
                            "triage_category": row.triage_category,
                            "triage_category_prob": row.triage_category_prob,
                            "triage_action_prob": row.triage_action_prob,
                            "triage_impact_score": row.triage_impact,
                            "triage_model": "nimble",
                            "triage_questions_version": 1,
                        },
                    )
                    for row in parsed.rows
                ],
            )
        ],
    )
    reparsed = parse_raw_markdown(again)
    assert [row.triage_decision for row in reparsed.rows] == ["keep", "drop"]
    assert [row.triage_source for row in reparsed.rows] == ["rule", "model"]


def test_ac6b_filter_input_is_keep_rows_and_six_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable(monkeypatch)
    prepared = prepare_range_documents(
        framework_key="angular",
        framework_display="Angular",
        from_version="19.0.0",
        to_version="19.0.1",
        hop_changes=[
            (
                "19.0.0",
                "19.0.1",
                [
                    DocumentedChange(
                        type="breaking",
                        confidence="confirmed",
                        source_url="https://example.com/keep",
                        statement="Title: breaking public API removal\n",
                    ),
                    _plain("Title: fix an internal counter\n", source="https://example.com/drop"),
                ],
            )
        ],
        existing_raw=None,
        range_metadata=None,
        skip_triage=False,
        force_triage=False,
        retriage_from_cache=False,
        client=FakeTriageClient(DROP_ANSWERS),
        settings=load_settings(),
    )
    filtered = build_filter_markdown(prepared.raw_md)
    assert filtered == prepared.filter_md
    assert FILTER_TABLE_HEADER in filtered
    assert "Cat. prob" not in filtered
    assert "Triage source" not in filtered
    assert "https://example.com/keep" in filtered
    assert "https://example.com/drop" not in filtered
    assert "| breaking | confirmed | https://example.com/keep |" in filtered


def test_ac6c_existing_triage_columns_and_retriage_make_no_http_calls(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
) -> None:
    _enable(monkeypatch)
    monkeypatch.chdir(tmp_path)
    client = FakeTriageClient(DROP_ANSWERS)
    hops = [
        (
            "3.0.0",
            "3.0.1",
            [_plain("Title: fix an internal counter\n")],
        )
    ]
    first = prepare_range_documents(
        framework_key="spring-boot",
        framework_display="Spring Boot",
        from_version="3.0.0",
        to_version="3.0.1",
        hop_changes=hops,
        existing_raw=None,
        range_metadata=None,
        skip_triage=False,
        force_triage=False,
        retriage_from_cache=False,
        client=client,
        settings=load_settings(),
    )
    assert len(client.calls) == 1
    assert "| drop |" in first.raw_md or "| drop |" in first.raw_md.replace("  ", " ")
    reused = prepare_range_documents(
        framework_key="spring-boot",
        framework_display="Spring Boot",
        from_version="3.0.0",
        to_version="3.0.1",
        hop_changes=None,
        existing_raw=first.raw_md,
        range_metadata=None,
        skip_triage=False,
        force_triage=False,
        retriage_from_cache=False,
        client=client,
        settings=load_settings(),
    )
    assert len(client.calls) == 1
    assert reused.rewrite_raw is False
    assert parse_raw_markdown(reused.raw_md).rows[0].triage_decision == "drop"

    monkeypatch.setenv("TRIAGE_DROP_MAX_ACTION_PROB", "0.01")
    rewritten = prepare_range_documents(
        framework_key="spring-boot",
        framework_display="Spring Boot",
        from_version="3.0.0",
        to_version="3.0.1",
        hop_changes=None,
        existing_raw=first.raw_md,
        range_metadata=None,
        skip_triage=False,
        force_triage=False,
        retriage_from_cache=True,
        client=client,
        settings=load_settings(),
    )
    assert len(client.calls) == 1
    assert rewritten.rewrite_raw is True
    assert parse_raw_markdown(rewritten.raw_md).rows[0].triage_decision == "keep"


def test_filter_prompt_mentions_category_and_large_input_is_grouped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert "Use `Category` to choose the output section" in FILTER_PROMPT
    assert "Category | Impact score" in FILTER_PROMPT
    assert "Developer:" not in FILTER_PROMPT
    monkeypatch.setenv("FILTER_MAX_INPUT_TOKENS", "1")
    table = "\n".join(
        [
            FILTER_TABLE_HEADER,
            "|------|------------|--------|-----------|----------|--------------|",
            "| behavioral | inferred | https://example.com/a | Title: one | breaking | 2.00 |",
            "| behavioral | inferred | https://example.com/b | Title: two | noise | 0.10 |",
            "",
        ]
    )
    chunks = _filter_chunks(table)
    assert len(chunks) == 2
    assert "https://example.com/a" in chunks[0]
    assert "https://example.com/b" in chunks[1]
    assert "https://example.com/b" not in chunks[0]
