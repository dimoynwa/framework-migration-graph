"""Framework extractor registry."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from migration_oracle.models.changes import DocumentedChange

ExtractFn = Callable[[str, str, str], list[DocumentedChange]]


@dataclass(frozen=True)
class ExtractorSpec:
    key: str
    display_name: str
    extract: ExtractFn


def _stub_extract(framework: str, from_version: str, to_version: str) -> list[DocumentedChange]:
    return [
        DocumentedChange(
            change_type="breaking",
            confidence="confirmed",
            source_url=f"https://example.com/{framework}/{to_version}",
            statement=(
                f"Sample breaking change for {framework} upgrade "
                f"{from_version} → {to_version}: remove legacy API."
            ),
        ),
        DocumentedChange(
            change_type="behavioral",
            confidence="inferred",
            source_url=f"https://example.com/{framework}/{to_version}/behavior",
            statement="Default timeout value changed from 30s to 60s.",
        ),
    ]


EXTRACTORS: dict[str, ExtractorSpec] = {
    "stub_framework": ExtractorSpec(
        key="stub_framework",
        display_name="Stub Framework",
        extract=_stub_extract,
    ),
    "spring-boot": ExtractorSpec(
        key="spring-boot",
        display_name="spring-boot",
        extract=_stub_extract,
    ),
}


def get_extractor(framework: str) -> ExtractorSpec:
    try:
        return EXTRACTORS[framework]
    except KeyError as exc:
        supported = ", ".join(sorted(EXTRACTORS))
        raise ValueError(
            f"Unknown framework {framework!r}. Supported: {supported}"
        ) from exc


def render_raw_markdown(
    *,
    framework_key: str,
    framework_display: str,
    from_version: str,
    to_version: str,
    changes: list[DocumentedChange],
) -> str:
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        f"# {framework_display} — documented changes (extract-only)",
        "",
        f"- **Framework key:** `{framework_key}`",
        f"- **Resolved range:** `{from_version}` → `{to_version}`",
        f"- **Generated (UTC):** {timestamp}",
        "",
        "---",
        "",
        f"## `{from_version}` → `{to_version}`",
        "",
        "| Type | Confidence | Source | Statement |",
        "|------|------------|--------|-----------|",
    ]
    for change in changes:
        statement = (
            change.statement.replace("|", " ")
            .replace("\r", " ")
            .replace("\n", " ")
        )
        lines.append(
            f"| {change.change_type} | {change.confidence} | "
            f"{change.source_url} | {statement} |"
        )
    return "\n".join(lines) + "\n"
