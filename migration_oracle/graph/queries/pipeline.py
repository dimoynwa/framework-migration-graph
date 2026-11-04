"""Pipeline graph query helpers."""

from __future__ import annotations

from dataclasses import dataclass

from migration_oracle.graph.driver import read_session, write_session
from migration_oracle.models.graph import (
    is_prerelease,
    prerelease_suffix,
    sortable_version,
)


@dataclass(frozen=True)
class PipelineRunRecord:
    framework: str
    version: str
    raw_md_path: str
    filtered_md_path: str | None
    entities_json_path: str | None


def merge_version(
    *,
    framework: str,
    version: str,
    sortable_version: int,
    pre_release: bool | None = None,
) -> None:
    """MERGE a Version node, flagging milestone/RC builds.

    ``pre_release`` is derived from the version string when not supplied, so a
    build such as ``4.1.0-RC1`` is always recorded as a prerelease node whose
    ``sortableVersion`` sits below the ``4.1.0`` GA release it precedes.
    """
    if pre_release is None:
        pre_release = is_prerelease(version)
    query = """
    MERGE (v:Version {framework: $framework, version: $version})
    ON CREATE SET v.sortableVersion = $sortable_version,
                  v.preRelease = $pre_release,
                  v.preReleaseLabel = $pre_release_label
    ON MATCH SET v.sortableVersion = $sortable_version,
                 v.preRelease = $pre_release,
                 v.preReleaseLabel = $pre_release_label
    """
    with write_session() as session:
        session.run(
            query,
            framework=framework,
            version=version,
            sortable_version=sortable_version,
            pre_release=pre_release,
            pre_release_label=prerelease_suffix(version),
        )


def version_exists(framework: str, version: str) -> bool:
    query = """
    MATCH (v:Version {framework: $framework, version: $version})
    RETURN count(v) AS cnt
    """
    with read_session() as session:
        record = session.run(
            query, framework=framework, version=version
        ).single()
    return bool(record and record["cnt"] > 0)


def upsert_version_artifact_paths(
    *,
    framework: str,
    version: str,
    raw_md_path: str,
    filtered_md_path: str,
    entities_json_path: str,
    from_version: str = "",
) -> None:
    merge_version(
        framework=framework,
        version=version,
        sortable_version=sortable_version(version),
    )
    query = """
    MATCH (v:Version {framework: $framework, version: $version})
    SET v.rawMdPath = $raw_md_path,
        v.filteredMdPath = $filtered_md_path,
        v.entitiesJsonPath = $entities_json_path,
        v.fromVersion = $from_version
    """
    with write_session() as session:
        session.run(
            query,
            framework=framework,
            version=version,
            raw_md_path=raw_md_path,
            filtered_md_path=filtered_md_path,
            entities_json_path=entities_json_path,
            from_version=from_version,
        )


def list_pipeline_runs(*, framework: str | None = None) -> list[dict[str, str | None]]:
    query = """
    MATCH (v:Version)
    WHERE v.rawMdPath IS NOT NULL
      AND ($framework IS NULL OR v.framework = $framework)
    OPTIONAL MATCH (v)
    RETURN v.framework AS framework,
           v.version AS version,
           v.rawMdPath AS rawMdPath,
           v.filteredMdPath AS filteredMdPath,
           v.entitiesJsonPath AS entitiesJsonPath
    ORDER BY v.framework, v.version
    """
    with read_session() as session:
        records = session.run(query, framework=framework)
        return [
            {
                "framework": row["framework"],
                "version": row["version"],
                "rawMdPath": row["rawMdPath"],
                "filteredMdPath": row.get("filteredMdPath"),
                "entitiesJsonPath": row.get("entitiesJsonPath"),
            }
            for row in records
        ]
