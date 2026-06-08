"""Framework HTTP extractor registry."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Type

from migration_oracle.models.entities import DocumentedChange, ExtractionResult
from migration_oracle.pipeline.extractors.angular import AngularExtractor
from migration_oracle.pipeline.extractors.base import BaseExtractor
from migration_oracle.pipeline.extractors.eap import EAPExtractor
from migration_oracle.pipeline.extractors.elytron import ElytronExtractor
from migration_oracle.pipeline.extractors.hibernate import HibernateExtractor
from migration_oracle.pipeline.extractors.infinispan import InfinispanExtractor
from migration_oracle.pipeline.extractors.jakarta_ee import JakartaEEExtractor
from migration_oracle.pipeline.extractors.resteasy import RestEasyExtractor
from migration_oracle.pipeline.extractors.spring_boot import SpringBootExtractor
from migration_oracle.pipeline.extractors.stub_framework import StubFrameworkExtractor
from migration_oracle.pipeline.extractors.wildfly import WildFlyExtractor

FRAMEWORK_DISPLAY_NAMES: dict[str, str] = {
    "spring-boot": "Spring Boot",
    "angular": "Angular",
    "wildfly": "WildFly",
    "eap": "JBoss EAP",
    "hibernate": "Hibernate ORM",
    "resteasy": "RESTEasy",
    "infinispan": "Infinispan",
    "elytron": "WildFly Elytron",
    "jakarta-ee": "Jakarta EE",
}

REGISTRY_KEYS: list[str] = list(FRAMEWORK_DISPLAY_NAMES.keys())

_EXTRACTOR_CLASSES: dict[str, Type[BaseExtractor]] = {
    "stub_framework": StubFrameworkExtractor,
    "spring-boot": SpringBootExtractor,
    "angular": AngularExtractor,
    "wildfly": WildFlyExtractor,
    "eap": EAPExtractor,
    "hibernate": HibernateExtractor,
    "resteasy": RestEasyExtractor,
    "infinispan": InfinispanExtractor,
    "elytron": ElytronExtractor,
    "jakarta-ee": JakartaEEExtractor,
}


def get_extractor(framework: str) -> BaseExtractor:
    """Return a new extractor instance for the given CLI framework key."""
    key = framework.strip().lower().replace(" ", "-")
    try:
        cls = _EXTRACTOR_CLASSES[key]
    except KeyError as exc:
        supported = ", ".join(sorted(_EXTRACTOR_CLASSES))
        raise ValueError(
            f"Unknown framework {framework!r}. Supported: {supported}"
        ) from exc
    return cls()


def supported_framework_keys() -> list[str]:
    return sorted(_EXTRACTOR_CLASSES)


def render_raw_markdown(
    *,
    framework_key: str,
    framework_display: str,
    from_version: str,
    to_version: str,
    hop_changes: list[tuple[str, str, list[DocumentedChange]]],
    metadata: dict | None = None,
) -> str:
    """Render multi-hop raw Markdown from extraction output."""
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
    ]
    if metadata:
        for key, value in metadata.items():
            if key in ("bom_diff", "blog_insights") and value:
                lines.append(f"- **{key}:** present in extraction metadata")
        lines.append("")

    for hop_from, hop_to, changes in hop_changes:
        lines.extend(
            [
                f"## `{hop_from}` → `{hop_to}`",
                "",
                "| Type | Confidence | Source | Statement |",
                "|------|------------|--------|-----------|",
            ]
        )
        for change in changes:
            statement = (
                change.statement.replace("|", " ")
                .replace("\r", " ")
                .replace("\n", " ")
            )
            lines.append(
                f"| {change.type} | {change.confidence} | "
                f"{change.source_url} | {statement} |"
            )
        lines.append("")

    return "\n".join(lines) + "\n"


__all__ = [
    "BaseExtractor",
    "DocumentedChange",
    "ExtractionResult",
    "FRAMEWORK_DISPLAY_NAMES",
    "REGISTRY_KEYS",
    "get_extractor",
    "render_raw_markdown",
    "supported_framework_keys",
]
