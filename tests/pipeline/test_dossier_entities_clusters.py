"""AC-2: specific URLs cluster rows; changelogs do not; oversized chains split."""

from __future__ import annotations

from migration_oracle.pipeline.entities.clusters import cluster_kept, verdict_of
from migration_oracle.pipeline.entities.gate import InputRow
from migration_oracle.pipeline.research.markdown import FilteredRow
from migration_oracle.pipeline.research.schema import ResearchDossier

PULL = "https://github.com/angular/angular/pull/{n}"
COMMIT = "https://github.com/angular/angular/commit/abcdef1234567890"
CHANGELOG = "https://github.com/angular/angular/blob/main/CHANGELOG.md"
RELEASE = "https://github.com/angular/angular/releases/tag/20.0.0"


def _member(
    title: str,
    sources: list[str],
    *,
    position: int,
    dossier_sources: list[str] | None = None,
    status: str = "ok",
) -> InputRow:
    row = FilteredRow(
        section="🟡 Behavioral Changes",
        index=position + 1,
        jira_keys=(),
        title=title,
        impact=title,
        sources=tuple(sources),
    )
    dossier = ResearchDossier(
        row_key=row.row_key,
        status=status,
        text="**Action:** required",
        sources=list(dossier_sources or []),
    )
    evidence = "dossier" if status == "ok" else "row_only"
    return InputRow(
        position=position,
        row=row,
        category="behavior_change",
        impact_score="1",
        row_type="behavioral",
        source=sources[0] if sources else "",
        statement=f"Title: {title}",
        dossier=dossier,
        decision="keep",
        reason="action_required",
        evidence=evidence,
    )


def test_shared_pull_url_is_one_cluster() -> None:
    rows = [
        _member("A", [PULL.format(n=1)], position=0),
        _member("B", [PULL.format(n=1)], position=1),
    ]
    clusters = cluster_kept(rows, max_rows=4)
    assert len(clusters) == 1
    assert len(clusters[0].members) == 2


def test_changelog_and_release_tag_stay_apart() -> None:
    rows = [
        _member("A", [CHANGELOG], position=0),
        _member("B", [CHANGELOG], position=1),
        _member("C", [RELEASE], position=2),
        _member("D", [RELEASE], position=3),
    ]
    clusters = cluster_kept(rows, max_rows=4)
    assert len(clusters) == 4


def test_dossier_fetched_commit_joins_the_source_row() -> None:
    rows = [
        _member("A", [COMMIT], position=0),
        _member("B", [CHANGELOG], position=1, dossier_sources=[COMMIT]),
    ]
    clusters = cluster_kept(rows, max_rows=4)
    assert len(clusters) == 1
    assert {member.row.title for member in clusters[0].members} == {"A", "B"}


def test_dossier_only_urls_do_not_join_rows() -> None:
    rows = [
        _member("A", [CHANGELOG], position=0, dossier_sources=[COMMIT]),
        _member("B", [RELEASE], position=1, dossier_sources=[COMMIT]),
    ]
    assert len(cluster_kept(rows, max_rows=4)) == 2


def test_oversized_chain_is_split_and_logged(capsys) -> None:
    rows = []
    for index in range(6):
        sources = [PULL.format(n=index + 1)]
        if index:
            sources.append(PULL.format(n=index))
        rows.append(_member(f"row{index}", sources, position=index))
    clusters = cluster_kept(rows, max_rows=4)
    assert len(clusters) == 6
    assert all(len(cluster.members) == 1 for cluster in clusters)
    logged = capsys.readouterr().err
    assert "cluster split" in logged
    assert "pull/1" in logged
    assert "CLUSTER_MAX_ROWS=4" in logged


def test_confirm_split_breaks_a_cluster_into_singles() -> None:
    rows = [
        _member("A", [PULL.format(n=1)], position=0),
        _member("B", [PULL.format(n=1)], position=1),
    ]
    assert len(cluster_kept(rows, max_rows=4, confirmer=lambda _cluster: "split")) == 2
    assert len(cluster_kept(rows, max_rows=4, confirmer=lambda _cluster: "same")) == 1
    assert verdict_of("split\n") == "split"
    assert verdict_of("they look the same") == "same"
