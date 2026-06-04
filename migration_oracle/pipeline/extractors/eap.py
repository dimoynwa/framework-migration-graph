"""JBoss EAP HTTP extractor."""

from __future__ import annotations

from dataclasses import dataclass

from migration_oracle.models.entities import ExtractionResult
from migration_oracle.pipeline.extractors.base import BaseExtractor
from migration_oracle.pipeline.extractors.parsing import (
    apply_cli_hints,
    html_to_text,
    parse_markdown_statements,
)

MIGRATION_GUIDE_URL = (
    "https://access.redhat.com/documentation/en-us/"
    "red_hat_jboss_enterprise_application_platform/{slug}/html/migration_guide/"
)
RELEASE_NOTES_URL = (
    "https://access.redhat.com/documentation/en-us/"
    "red_hat_jboss_enterprise_application_platform/{slug}/html/release_notes/"
)


@dataclass(frozen=True)
class EAPVersionEntry:
    eap_version: str
    slug: str
    wildfly_base: str


EAP_VERSION_TABLE: list[EAPVersionEntry] = [
    EAPVersionEntry("7.0.0", "7.0", "10.1.0"),
    EAPVersionEntry("7.1.0", "7.1", "11.0.0"),
    EAPVersionEntry("7.2.0", "7.2", "13.0.0"),
    EAPVersionEntry("7.3.0", "7.3", "18.0.0"),
    EAPVersionEntry("7.4.0", "7.4", "26.1.0"),
    EAPVersionEntry("8.0.0", "8.0", "29.0.0"),
]


class EAPExtractor(BaseExtractor):
    framework_key = "eap"
    display_name = "JBoss EAP"
    default_timeout = 60.0

    async def discover_versions(self) -> list[str]:
        return [entry.eap_version for entry in EAP_VERSION_TABLE]

    def _entry_for(self, version: str) -> EAPVersionEntry:
        for entry in EAP_VERSION_TABLE:
            if entry.eap_version == version:
                return entry
        raise ValueError(f"EAP version {version!r} not in fixed version table")

    async def extract(self, from_version: str, to_version: str) -> ExtractionResult:
        entry = self._entry_for(to_version)
        sources: list[tuple[str, str]] = []
        for template in (MIGRATION_GUIDE_URL, RELEASE_NOTES_URL):
            url = template.format(slug=entry.slug)
            await self.sleep_redhat()
            try:
                html = await self.fetch(url, timeout=60.0, accept_status={200})
                sources.append((url, html_to_text(html)))
            except RuntimeError:
                continue

        if not sources:
            raise RuntimeError(
                f"EAP: no documentation fetched for version {to_version!r}"
            )

        combined = "\n\n".join(text for _, text in sources)
        source_url = sources[0][0]
        changes = parse_markdown_statements(combined, source_url)
        changes = apply_cli_hints(changes)
        if not changes:
            raise RuntimeError(
                f"EAP: no changes parsed for hop {from_version} → {to_version}"
            )
        return ExtractionResult(
            changes=changes,
            metadata={"wildfly_base": entry.wildfly_base},
        )
