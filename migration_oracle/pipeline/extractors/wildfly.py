"""WildFly HTTP extractor with Jira enrichment."""

from __future__ import annotations

import asyncio
import logging
import re

from migration_oracle.models.entities import DocumentedChange, ExtractionResult
from migration_oracle.pipeline.extractors.base import BaseExtractor, is_jboss_ga_version
from migration_oracle.pipeline.extractors.filters import _skip_prerelease
from migration_oracle.pipeline.extractors.parsing import (
    apply_cli_hints,
    filter_release_versions,
    html_to_text,
    normalize_wildfly_maven_version,
    parse_github_release_text,
    parse_maven_metadata_versions,
    parse_version,
)
from migration_oracle.pipeline.extractors.wildfly_jira import (
    BROWSE_TEMPLATE,
    JIRA_KEY_RE,
    build_release_index,
    collect_jira_keys,
    fetch_jira_entry,
    normalize_jira_url as normalize_jira_host,
    parse_jira_fields,
)

__all__ = ["WildFlyExtractor", "JIRA_KEY_RE", "normalize_jira_host"]

logger = logging.getLogger(__name__)

MAVEN_METADATA_URL = (
    "https://repo1.maven.org/maven2/org/wildfly/wildfly-dist/maven-metadata.xml"
)


class WildFlyExtractor(BaseExtractor):
    framework_key = "wildfly"
    display_name = "WildFly"

    @staticmethod
    def _priority_from_jira_fields(fields: dict) -> str:
        return (fields.get("priority") or {}).get("name", "")

    async def discover_versions(self) -> list[str]:
        xml = await self.fetch(MAVEN_METADATA_URL)
        raw = parse_maven_metadata_versions(xml)
        if _skip_prerelease():
            raw = [v for v in raw if is_jboss_ga_version(v)]
        normalized = [normalize_wildfly_maven_version(v) for v in raw]
        return filter_release_versions(normalized, final_only=False)

    def enrich_with_jira(
        self,
        changes: list[DocumentedChange],
        *,
        cache: dict | None = None,
        index: dict | None = None,
        body: str = "",
    ) -> list[DocumentedChange]:
        """Enrich changes with Jira data; accepts pre-built cache/index for testing."""
        if cache is None:
            return changes
        if index is None:
            index = build_release_index(body)

        enriched: list[DocumentedChange] = []
        for change in changes:
            all_keys = [
                m.group(1).upper() for m in re.finditer(JIRA_KEY_RE, change.statement)
            ]
            if not all_keys:
                enriched.append(change)
                continue

            key = next((k for k in all_keys if k in cache), all_keys[0])
            jira = cache.get(key)
            release_line = index.get(key, {}).get("summary") or change.statement

            if jira and jira.get("summary"):
                description = jira.get("description") or "N/A"
                statement = (
                    f"Title: {jira['summary']}\n"
                    f"Jira: {description}\n"
                    f"Release: {release_line or 'N/A'}"
                )
                source_url = jira.get("source_url") or BROWSE_TEMPLATE.format(key=key)
                meta = dict(change.metadata or {})
                issue_type = jira.get("issue_type") or index.get(key, {}).get("issue_type")
                if issue_type:
                    meta["issue_type"] = issue_type
                jira_priority = jira.get("priority")
                if jira_priority:
                    meta["jira_priority"] = jira_priority
            else:
                statement = change.statement
                source_url = BROWSE_TEMPLATE.format(key=key)
                meta = dict(change.metadata or {})

            enriched.append(
                DocumentedChange(
                    type=change.type,
                    confidence=change.confidence,
                    source_url=source_url,
                    statement=statement,
                    metadata=meta,
                )
            )
        return enriched

    async def _load_jira_cache(
        self, body: str, changes: list[DocumentedChange]
    ) -> tuple[dict, dict]:
        statements = [c.statement for c in changes]
        keys = sorted(collect_jira_keys(body, statements))
        index = build_release_index(body)
        if not keys:
            return {}, index

        cache: dict = {}
        semaphore = asyncio.Semaphore(self.jira_max_concurrent)

        async def load_key(key: str) -> None:
            async with semaphore:
                entry = await fetch_jira_entry(self.fetch, key)
                if entry:
                    cache[key] = entry

        await asyncio.gather(*(load_key(key) for key in keys))
        return cache, index

    async def extract(self, from_version: str, to_version: str) -> ExtractionResult:
        version = to_version
        tag_candidates = [f"{version}.Final", f"{version}"]
        source_url, body = await self._fetch_release_body(to_version, tag_candidates)
        changes = parse_github_release_text(body, source_url)
        try:
            cache, index = await self._load_jira_cache(body, changes)
            changes = self.enrich_with_jira(
                changes, cache=cache, index=index, body=body
            )
        except Exception as exc:
            logger.warning("WildFly Jira enrichment skipped: %s", exc)
        changes = apply_cli_hints(changes)
        if not changes:
            raise RuntimeError(
                f"WildFly: no changes parsed for hop {from_version} → {to_version}"
            )
        return ExtractionResult(changes=changes, metadata={})

    async def _fetch_release_body(
        self, version: str, tag_candidates: list[str]
    ) -> tuple[str, str]:
        repo = "wildfly/wildfly"
        try:
            return await self.fetch_github_release(repo, version, tag_candidates)
        except RuntimeError:
            pass

        major, _, _, _ = parse_version(version)
        guide_url = f"https://docs.wildfly.org/{major}/Migration_Guide.html"
        try:
            html = await self.fetch(guide_url, timeout=60.0)
            return guide_url, html_to_text(html)
        except RuntimeError:
            fallback = "https://www.wildfly.org/news/"
            html = await self.fetch(fallback, timeout=60.0)
            return fallback, html_to_text(html)
