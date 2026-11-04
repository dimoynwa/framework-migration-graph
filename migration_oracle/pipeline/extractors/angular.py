"""Angular HTTP extractor."""

from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

from migration_oracle import config
from migration_oracle.models.entities import DocumentedChange, ExtractionResult
from migration_oracle.pipeline.extractors.base import BaseExtractor, HopContext
from migration_oracle.pipeline.extractors.github_enrichment import (
    GitHubCommit,
    GitHubIssue,
    build_commit_change,
    build_issue_change,
    extract_angular_issue_numbers,
    extract_commit_shas,
)
from migration_oracle.pipeline.extractors.parsing import (
    filter_release_versions,
    parse_github_release_text,
)

logger = logging.getLogger(__name__)

ANGULAR_REPO = "angular/angular"
NPM_REGISTRY_URL = "https://registry.npmjs.org/@angular/core"
CHANGELOG_URL = (
    "https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md"
)
_BLOG_LINK_RE = re.compile(
    r"https://(?:blog\.)?angular\.dev/[^\s\)]+"
)
_COMMIT_HASH_RE = re.compile(r"github\.com/angular/angular/commit/([0-9a-f]+)")
_EMBEDDED_CHANGELOG_COMMIT_OVERLAP = 0.95


def _extract_changelog_section(changelog_text: str, version: str) -> str:
    """Extract the CHANGELOG.md section for a given version."""
    anchor = f'<a name="{version}"></a>'
    start = changelog_text.find(anchor)
    if start == -1:
        return ""

    next_anchor_start = changelog_text.find('<a name="', start + len(anchor))
    if next_anchor_start == -1:
        section = changelog_text[start:]
    else:
        section = changelog_text[start:next_anchor_start]

    return section.strip()


def _commit_prefix(statement: str) -> str | None:
    match = _COMMIT_HASH_RE.search(statement)
    return match.group(1)[:10] if match else None


def _is_badge_entry(statement: str) -> bool:
    return "img.shields.io" in statement


def _deduplicate_against_changelog(
    gh_changes: list[DocumentedChange],
    changelog_changes: list[DocumentedChange],
) -> list[DocumentedChange]:
    """Prefer CHANGELOG entries when GH release body repeats the same changes."""
    cl_statements = {change.statement for change in changelog_changes}
    cl_prefixes = {
        prefix
        for change in changelog_changes
        if (prefix := _commit_prefix(change.statement))
    }
    gh_prefixes = {
        prefix for change in gh_changes if (prefix := _commit_prefix(change.statement))
    }
    overlap_ratio = (
        len(gh_prefixes & cl_prefixes) / len(gh_prefixes) if gh_prefixes else 0.0
    )
    use_hash_dedup = overlap_ratio >= _EMBEDDED_CHANGELOG_COMMIT_OVERLAP

    gh_unique: list[DocumentedChange] = []
    for change in gh_changes:
        if change.statement in cl_statements:
            continue
        if use_hash_dedup:
            prefix = _commit_prefix(change.statement)
            if (
                prefix
                and prefix in cl_prefixes
                and _is_badge_entry(change.statement)
            ):
                continue
        gh_unique.append(change)

    combined = gh_unique + changelog_changes
    seen: set[str] = set()
    deduped: list[DocumentedChange] = []
    for change in combined:
        if change.statement in seen:
            continue
        seen.add(change.statement)
        deduped.append(change)
    return deduped


class AngularExtractor(BaseExtractor):
    framework_key = "angular"
    display_name = "Angular"

    async def discover_versions(self) -> list[str]:
        data = await self.fetch_json(NPM_REGISTRY_URL)
        versions = list(data.get("versions", {}).keys())
        return filter_release_versions(versions, final_only=False)

    async def _get_changelog(self) -> str:
        """Fetch Angular CHANGELOG.md (cached at most once per run)."""
        if CHANGELOG_URL in self._cache:
            cached = self._cache[CHANGELOG_URL]
            return cached.decode() if isinstance(cached, bytes) else cached
        try:
            return await self.fetch(CHANGELOG_URL, accept_status={200})
        except RuntimeError as exc:
            logger.warning("Angular CHANGELOG.md fetch failed: %s", exc)
            return ""

    def _fetch_blog_summary(self, url: str) -> str:
        """Fetch a blog page and extract a text summary."""
        try:
            html = self._http_get_cached(url)
            if not html:
                return ""
            soup = BeautifulSoup(html, "html.parser")

            tag = soup.find("meta", attrs={"name": "description"})
            if tag and tag.get("content"):
                return tag["content"].strip()

            tag = soup.find("meta", attrs={"property": "og:description"})
            if tag and tag.get("content"):
                return tag["content"].strip()

            for p in soup.find_all("p"):
                text = p.get_text(strip=True)
                if len(text) >= 80:
                    return text

            return ""
        except Exception:
            return ""

    async def extract(
        self, from_version: str, to_version: str, *, hop_context: HopContext | None = None
    ) -> ExtractionResult:
        tag_candidates = [f"v{to_version}", to_version]
        source_url, body = await self.fetch_github_release(
            ANGULAR_REPO, to_version, tag_candidates
        )
        changelog_text = await self._get_changelog()
        changelog_section = _extract_changelog_section(changelog_text, to_version)

        changes = parse_github_release_text(body, source_url)
        if changelog_section:
            changelog_changes = parse_github_release_text(
                changelog_section, CHANGELOG_URL
            )
            changes = _deduplicate_against_changelog(changes, changelog_changes)
        try:
            changes = await self._enrich_github_changes(changes)
        except Exception as exc:
            logger.warning("Angular GitHub enrichment skipped: %s", exc)
        raw_blog_urls = sorted(set(_BLOG_LINK_RE.findall(body)))
        blog_insights = [
            {"url": url, "summary": self._fetch_blog_summary(url)}
            for url in raw_blog_urls
        ]
        if not changes:
            raise RuntimeError(
                f"Angular: no changes parsed for hop {from_version} → {to_version} "
                f"from {source_url}"
            )
        metadata = {"blog_insights": blog_insights}
        return ExtractionResult(changes=changes, metadata=metadata)

    async def _enrich_github_changes(
        self, changes: list[DocumentedChange]
    ) -> list[DocumentedChange]:
        """Attach commit messages, and issue bodies when a row has no commit.

        Runs after changelog dedup. Blog insights are not rows and are left alone.
        """
        if not config.ANGULAR_GITHUB_ENRICHMENT:
            return changes
        if not self._github_token:
            if not getattr(self, "_github_enrichment_skip_logged", False):
                logger.info(
                    "Angular GitHub enrichment skipped: GITHUB_TOKEN is not set"
                )
                self._github_enrichment_skip_logged = True
            return changes

        row_shas = [extract_commit_shas(change.statement) for change in changes]
        fallback_numbers: list[int] = []
        for change, shas in zip(changes, row_shas, strict=True):
            if shas:
                continue
            fallback_numbers.extend(extract_angular_issue_numbers(change.statement))
        shas = [sha for row in row_shas for sha in row]
        if not shas and not fallback_numbers:
            return changes

        commits = (
            await self.fetch_github_commits(ANGULAR_REPO, shas) if shas else {}
        )
        linked_numbers: list[int] = []
        for row in row_shas:
            chosen = next((sha for sha in row if sha in commits), None)
            if chosen is None:
                continue
            fixes = commits[chosen]["fixes"]
            if fixes:
                linked_numbers.append(fixes[0])
        issue_numbers = fallback_numbers + linked_numbers
        issues = (
            await self.fetch_github_issues(ANGULAR_REPO, issue_numbers)
            if issue_numbers
            else {}
        )
        return _apply_angular_enrichment(changes, commits, issues)


def _apply_angular_enrichment(
    changes: list[DocumentedChange],
    commits: dict[str, GitHubCommit],
    issues: dict[int, GitHubIssue],
) -> list[DocumentedChange]:
    enriched: list[DocumentedChange] = []
    for change in changes:
        shas = extract_commit_shas(change.statement)
        chosen_sha = next((sha for sha in shas if sha in commits), None)
        if chosen_sha is not None:
            commit = commits[chosen_sha]
            issue = issues.get(commit["fixes"][0]) if commit["fixes"] else None
            enriched.append(build_commit_change(change, commit, issue))
            continue
        if not shas:
            numbers = extract_angular_issue_numbers(change.statement)
            chosen = next((number for number in numbers if number in issues), None)
            if chosen is not None:
                issue = issues[chosen]
                enriched.append(build_issue_change(change, issue, issue["body"]))
                continue
        enriched.append(change)
    return enriched
