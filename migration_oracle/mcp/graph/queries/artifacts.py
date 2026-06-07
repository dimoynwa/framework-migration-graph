"""Pipeline artifact path Cypher queries."""

from __future__ import annotations

from migration_oracle.graph.driver import read_session

_LIST_PIPELINE_RUNS = """
MATCH (v:Version) WHERE v.rawMdPath IS NOT NULL
RETURN v.framework AS framework,
       v.version AS version,
       v.rawMdPath AS raw_md_path,
       v.filteredMdPath AS filtered_md_path,
       v.entitiesJsonPath AS entities_json_path
ORDER BY v.framework, v.sortableVersion
"""

_GET_VERSION_ARTIFACT_PATH = """
MATCH (v:Version {framework: $framework, version: $to_version})
RETURN v.rawMdPath AS rawMdPath,
       v.filteredMdPath AS filteredMdPath,
       v.entitiesJsonPath AS entitiesJsonPath
"""


def list_pipeline_runs() -> list[dict]:
    with read_session() as session:
        return [dict(row) for row in session.run(_LIST_PIPELINE_RUNS)]


def get_version_artifact_path(*, framework: str, to_version: str) -> dict | None:
    with read_session() as session:
        record = session.run(
            _GET_VERSION_ARTIFACT_PATH,
            framework=framework,
            to_version=to_version,
        ).single()
    if record is None:
        return None
    data = dict(record)
    if not any(data.values()):
        return None
    return data
