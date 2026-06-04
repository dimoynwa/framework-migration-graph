"""Artifact path helpers for the pipeline cache."""

from pathlib import Path


RUNS_RAW = Path("runs/raw")
RUNS_NODES = Path("runs/nodes")
RUNS_JSON = Path("runs/json")


def artifact_key(framework: str, from_version: str, to_version: str) -> str:
    return f"{framework}-{from_version}-to-{to_version}"


def default_raw_md_path(framework: str, from_version: str, to_version: str) -> Path:
    return RUNS_RAW / f"{artifact_key(framework, from_version, to_version)}-changes.md"


def default_filtered_md_path(
    framework: str, from_version: str, to_version: str
) -> Path:
    return (
        RUNS_NODES
        / f"{artifact_key(framework, from_version, to_version)}-changes_filtered.md"
    )


def default_entities_json_path(
    framework: str, from_version: str, to_version: str
) -> Path:
    return RUNS_JSON / f"{artifact_key(framework, from_version, to_version)}-entities.json"


def ensure_runs_directories() -> None:
    """Create runs/raw, runs/nodes, runs/json or raise if not writable."""
    for directory in (RUNS_RAW, RUNS_NODES, RUNS_JSON):
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise OSError(
                f"Cannot create or write to runs directory {directory!s}: {exc}"
            ) from exc
