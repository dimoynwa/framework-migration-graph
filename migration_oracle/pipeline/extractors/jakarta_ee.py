"""Jakarta EE namespace migration extractor (no HTTP)."""

from __future__ import annotations

from dataclasses import dataclass

from migration_oracle.models.entities import DocumentedChange, ExtractionResult
from migration_oracle.pipeline.extractors.base import BaseExtractor
from migration_oracle.pipeline.extractors.parsing import compare_versions

PIPELINE_DOC = "export-extract-populate-framework-pipeline.md"

JAKARTA_EE_SPEC_VERSIONS = [
    "8.0.0",
    "9.0.0",
    "9.1.0",
    "10.0.0",
    "11.0.0",
]


@dataclass(frozen=True)
class JakartaEENamespaceMapping:
    javax_package: str
    jakarta_package: str
    spec_version: str


NAMESPACE_MAPPINGS: list[JakartaEENamespaceMapping] = [
    JakartaEENamespaceMapping("javax.annotation", "jakarta.annotation", "9.0"),
    JakartaEENamespaceMapping("javax.batch", "jakarta.batch", "9.0"),
    JakartaEENamespaceMapping("javax.ejb", "jakarta.ejb", "9.0"),
    JakartaEENamespaceMapping("javax.el", "jakarta.el", "9.0"),
    JakartaEENamespaceMapping("javax.enterprise", "jakarta.enterprise", "9.0"),
    JakartaEENamespaceMapping("javax.faces", "jakarta.faces", "9.0"),
    JakartaEENamespaceMapping("javax.inject", "jakarta.inject", "9.0"),
    JakartaEENamespaceMapping("javax.interceptor", "jakarta.interceptor", "9.0"),
    JakartaEENamespaceMapping("javax.jms", "jakarta.jms", "9.0"),
    JakartaEENamespaceMapping("javax.json", "jakarta.json", "9.0"),
    JakartaEENamespaceMapping("javax.mail", "jakarta.mail", "9.0"),
    JakartaEENamespaceMapping("javax.persistence", "jakarta.persistence", "9.0"),
    JakartaEENamespaceMapping("javax.resource", "jakarta.resource", "9.0"),
    JakartaEENamespaceMapping("javax.security.auth.message", "jakarta.security.auth.message", "9.0"),
    JakartaEENamespaceMapping("javax.security.enterprise", "jakarta.security.enterprise", "9.0"),
    JakartaEENamespaceMapping("javax.servlet", "jakarta.servlet", "9.0"),
    JakartaEENamespaceMapping("javax.transaction", "jakarta.transaction", "9.0"),
    JakartaEENamespaceMapping("javax.validation", "jakarta.validation", "9.0"),
    JakartaEENamespaceMapping("javax.websocket", "jakarta.websocket", "9.0"),
    JakartaEENamespaceMapping("javax.ws.rs", "jakarta.ws.rs", "9.0"),
    JakartaEENamespaceMapping("javax.xml.bind", "jakarta.xml.bind", "9.0"),
    JakartaEENamespaceMapping("javax.xml.ws", "jakarta.xml.ws", "9.0"),
]


class JakartaEEExtractor(BaseExtractor):
    framework_key = "jakarta-ee"
    display_name = "Jakarta EE"

    async def discover_versions(self) -> list[str]:
        return list(JAKARTA_EE_SPEC_VERSIONS)

    async def extract(self, from_version: str, to_version: str) -> ExtractionResult:
        if compare_versions(from_version, "9.0.0") >= 0:
            return ExtractionResult(changes=[], metadata={})
        if compare_versions(to_version, "9.0.0") < 0:
            return ExtractionResult(changes=[], metadata={})

        major = "9"
        source_url = f"https://jakarta.ee/specifications/platform/{major}/"
        changes = [
            DocumentedChange(
                type="mandatory_migration",
                confidence="confirmed",
                source_url=source_url,
                statement=(
                    f"Migrate package namespace from {mapping.javax_package} to "
                    f"{mapping.jakarta_package} (Jakarta EE {mapping.spec_version})."
                ),
                metadata={"javax_package": mapping.javax_package, "jakarta_package": mapping.jakarta_package},
            )
            for mapping in NAMESPACE_MAPPINGS
        ]
        return ExtractionResult(changes=changes, metadata={"namespace_migration": True})
