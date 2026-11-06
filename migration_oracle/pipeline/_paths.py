"""Artifact path helpers for the pipeline cache."""

from pathlib import Path


RUNS_RAW = Path("runs/raw")
RUNS_NODES = Path("runs/nodes")
RUNS_JSON = Path("runs/json")
RUNS_TRIAGE = Path("runs/triage")
RUNS_RESEARCH = Path("runs/research")
RUNS_CLUSTERS = Path("runs/clusters")
RUNS_CANONICAL = Path("runs/canonical")
RUNS_SIGNALS = Path("runs/signals")


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


def default_triage_jsonl_path(
    framework: str, from_version: str, to_version: str
) -> Path:
    return RUNS_TRIAGE / f"{artifact_key(framework, from_version, to_version)}-triage.jsonl"


def default_triage_summary_path(
    framework: str, from_version: str, to_version: str
) -> Path:
    return RUNS_TRIAGE / f"{artifact_key(framework, from_version, to_version)}-summary.json"


def default_research_jsonl_path(
    framework: str, from_version: str, to_version: str
) -> Path:
    return RUNS_RESEARCH / f"{artifact_key(framework, from_version, to_version)}-research.jsonl"


def default_research_summary_path(
    framework: str, from_version: str, to_version: str
) -> Path:
    return RUNS_RESEARCH / f"{artifact_key(framework, from_version, to_version)}-summary.json"


def default_clusters_jsonl_path(
    framework: str, from_version: str, to_version: str
) -> Path:
    return RUNS_CLUSTERS / f"{artifact_key(framework, from_version, to_version)}-clusters.jsonl"


def default_clusters_summary_path(
    framework: str, from_version: str, to_version: str
) -> Path:
    return RUNS_CLUSTERS / f"{artifact_key(framework, from_version, to_version)}-summary.json"


def default_canonical_jsonl_path(
    framework: str, from_version: str, to_version: str
) -> Path:
    return (
        RUNS_CANONICAL / f"{artifact_key(framework, from_version, to_version)}-canonical.jsonl"
    )


def default_canonical_summary_path(
    framework: str, from_version: str, to_version: str
) -> Path:
    return (
        RUNS_CANONICAL / f"{artifact_key(framework, from_version, to_version)}-summary.json"
    )


def default_signals_jsonl_path(
    framework: str, from_version: str, to_version: str
) -> Path:
    return (
        RUNS_SIGNALS / f"{artifact_key(framework, from_version, to_version)}-signals.jsonl"
    )


def default_signals_summary_path(
    framework: str, from_version: str, to_version: str
) -> Path:
    return (
        RUNS_SIGNALS / f"{artifact_key(framework, from_version, to_version)}-summary.json"
    )


def ensure_runs_directories() -> None:
    """Create runs artifact directories or raise if not writable."""
    for directory in (
        RUNS_RAW,
        RUNS_NODES,
        RUNS_JSON,
        RUNS_TRIAGE,
        RUNS_RESEARCH,
        RUNS_CLUSTERS,
        RUNS_CANONICAL,
        RUNS_SIGNALS,
    ):
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise OSError(
                f"Cannot create or write to runs directory {directory!s}: {exc}"
            ) from exc
