"""Deterministic pre-triage: hard keep wins, and hard drop never calls the model."""

from __future__ import annotations

import pytest

from migration_oracle.models.entities import DocumentedChange
from migration_oracle.pipeline.triage.client import FakeTriageClient
from migration_oracle.pipeline.triage.rules import pre_triage
from migration_oracle.pipeline.triage.run import run_triage
from migration_oracle.pipeline.triage.settings import load_settings


def _change(statement: str, **kwargs: object) -> DocumentedChange:
    metadata = kwargs.pop("metadata", None)
    return DocumentedChange(
        type=str(kwargs.pop("type", "behavioral")),
        confidence=str(kwargs.pop("confidence", "inferred")),
        source_url=str(kwargs.pop("source_url", "https://example.com/change")),
        statement=statement,
        metadata=metadata if isinstance(metadata, dict) else None,
    )


def _settings():
    return load_settings()


def test_ac1_breaking_footer_is_kept_without_a_model_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TRIAGE_BASE_URL", "http://triage.example")
    monkeypatch.setenv("TRIAGE_MODEL", "nimble")
    change = _change(
        "Title: refactor(core): adjust provider tokens\n"
        "Commit: details of the change.\n"
        "Breaking: the old token is removed\n",
        metadata={"angular_commit_type": "refactor", "angular_package": "core"},
    )
    client = FakeTriageClient({})

    result = run_triage(
        [change],
        "Angular",
        ("19.0.0", "19.0.1"),
        client=client,
        settings=_settings(),
    )

    assert client.calls == []
    assert result.rows[0].source == "rule"
    assert result.rows[0].decision == "keep"
    assert result.dropped == []


def test_ac2_docs_commit_outside_package_src_is_dropped_by_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TRIAGE_BASE_URL", "http://triage.example")
    monkeypatch.setenv("TRIAGE_MODEL", "nimble")
    change = _change(
        "Title: docs(adev): fix a typo in the guide\nCommit: wording only\n",
        metadata={
            "angular_commit_type": "docs",
            "github_files": ["adev/src/content/guide/cli.md"],
        },
    )
    client = FakeTriageClient({})

    result = run_triage(
        [change],
        "Angular",
        ("19.0.0", "19.0.1"),
        client=client,
        settings=_settings(),
    )

    assert client.calls == []
    assert result.rows[0].decision == "drop"
    assert result.rows[0].source == "rule"


def test_docs_commit_touching_package_src_is_not_dropped() -> None:
    change = _change(
        "Title: docs(core): describe the renderer\n",
        metadata={
            "angular_commit_type": "docs",
            "github_files": ["adev/guide.md", "packages/core/src/render3/instructions.ts"],
        },
    )
    assert pre_triage(change) is None


def test_docs_commit_without_a_file_list_is_kept_for_the_model() -> None:
    change = _change(
        "Title: docs(core): describe the renderer\n",
        metadata={"angular_commit_type": "docs"},
    )
    assert pre_triage(change) is None


def test_title_keyword_beats_a_tooling_drop() -> None:
    change = _change(
        "Title: docs(core): removed the public guide for the old API\n",
        metadata={
            "angular_commit_type": "docs",
            "github_files": ["adev/src/content/old.md"],
        },
    )
    assert pre_triage(change) == "keep"


def test_body_keyword_does_not_keep_when_the_title_is_quiet() -> None:
    change = _change(
        "Title: docs(adev): tidy the sidebar\nCommit: the old page was removed\n",
        metadata={
            "angular_commit_type": "docs",
            "github_files": ["adev/src/content/old.md"],
        },
    )
    assert pre_triage(change) == "drop"


@pytest.mark.parametrize(
    "issue_type",
    ["documentation", "task", "type: documentation", "type: task"],
)
def test_spring_doc_and_task_issues_are_dropped(issue_type: str) -> None:
    change = _change(
        "Title: Improve the gradle plugin tags documentation\nIssue: N/A\n",
        metadata={"github_issue_type": issue_type},
    )
    assert pre_triage(change) == "drop"


def test_spring_not_planned_is_dropped() -> None:
    change = _change(
        "Title: Consider a different actuator default\n",
        metadata={"github_not_planned": True},
    )
    assert pre_triage(change) == "drop"


def test_changelog_pointer_rows_are_dropped() -> None:
    compare = _change(
        "For all changes since WildFly 35.0.0.Final, see the "
        "[full changelog](https://github.com/wildfly/wildfly/compare/35.0.0.Final...36.0.0.Final)."
    )
    core = _change(
        "Changes in the underlying WildFly Core 31 releases are listed in the "
        "[WildFly Core Jira](https://issues.redhat.com/issues/?jql=project)."
    )
    assert pre_triage(compare) == "drop"
    assert pre_triage(core) == "drop"


def test_confirmed_migration_types_and_schematic_and_bang_are_kept() -> None:
    mandatory = _change("Title: fix(core): adjust control flow", type="mandatory_migration", confidence="confirmed")
    schematic = _change(
        "Title: fix(core): migration helper\n",
        metadata={"has_schematic": True, "angular_commit_type": "fix"},
    )
    bang = _change("Title: fix(core)!: stop accepting the old token\n")
    assert pre_triage(mandatory) == "keep"
    assert pre_triage(schematic) == "keep"
    assert pre_triage(bang) == "keep"
