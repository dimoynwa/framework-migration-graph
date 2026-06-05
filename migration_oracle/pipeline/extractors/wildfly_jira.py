"""WildFly Jira enrichment helpers."""

from __future__ import annotations

import logging
import re
from typing import TypedDict

logger = logging.getLogger(__name__)

JIRA_KEY_PREFIXES = (
    "WFLY",
    "WFCORE",
    "WFMP",
    "JBEAP",
    "EAP7",
    "UNDERTOW",
    "HAL",
    "ISPN",
    "HHH",
)
_PREFIX_PATTERN = "|".join(JIRA_KEY_PREFIXES)
JIRA_KEY_RE = re.compile(rf"\b(({_PREFIX_PATTERN})-\d+)\b", re.I)

_HTML_EXPORT_RE = re.compile(
    rf'\[<a href="https://issues\.redhat\.com/browse/({_PREFIX_PATTERN}-\d+)"[^>]*>',
    re.I,
)
_ISSUES_HOST_RE = re.compile(
    r"https://issues\.redhat\.com/browse/([A-Z]+-\d+)", re.I
)

REST_TEMPLATE = (
    "https://redhat.atlassian.net/rest/api/2/issue/{key}"
    "?fields=summary,description,issuetype,priority,status"
)
BROWSE_TEMPLATE = "https://redhat.atlassian.net/browse/{key}"


class WildFlyJiraEntry(TypedDict):
    summary: str
    source_url: str
    issue_type: str
    description: str
    priority: str


def normalize_jira_url(url: str) -> str:
    match = _ISSUES_HOST_RE.search(url)
    if match:
        return BROWSE_TEMPLATE.format(key=match.group(1).upper())
    return url


def build_release_index(body: str) -> dict[str, WildFlyJiraEntry]:
    index: dict[str, WildFlyJiraEntry] = {}
    for match in JIRA_KEY_RE.finditer(body):
        key = match.group(1).upper()
        if key in index:
            continue
        index[key] = {
            "summary": "",
            "source_url": BROWSE_TEMPLATE.format(key=key),
            "issue_type": "",
            "description": "",
            "priority": "",
        }
    for match in _HTML_EXPORT_RE.finditer(body):
        key = match.group(1).upper()
        index.setdefault(
            key,
            {
                "summary": "",
                "source_url": BROWSE_TEMPLATE.format(key=key),
                "issue_type": "",
                "description": "",
                "priority": "",
            },
        )
    return index


def collect_jira_keys(body: str, statements: list[str]) -> set[str]:
    keys = set(build_release_index(body))
    for stmt in statements:
        keys.update(m.group(1).upper() for m in JIRA_KEY_RE.finditer(stmt))
    return keys


def parse_jira_fields(fields: dict) -> WildFlyJiraEntry:
    """Build a cache entry from Jira REST API fields."""
    description = fields.get("description") or ""
    if isinstance(description, dict):
        description = str(description)
    return {
        "summary": fields.get("summary") or "",
        "source_url": "",
        "issue_type": (fields.get("issuetype") or {}).get("name", ""),
        "description": description.strip(),
        "priority": (fields.get("priority") or {}).get("name", ""),
    }


async def fetch_jira_entry(
    client_fetch,
    key: str,
    *,
    timeout: float = 10.0,
) -> WildFlyJiraEntry | None:
    rest_url = REST_TEMPLATE.format(key=key)
    try:
        data = await client_fetch(
            rest_url,
            timeout=timeout,
            headers={"Accept": "application/json"},
            accept_status={200},
        )
        import json

        parsed = json.loads(data) if isinstance(data, str) else data
        fields = parsed.get("fields", {})
        entry = parse_jira_fields(fields)
        entry["source_url"] = BROWSE_TEMPLATE.format(key=key)
        entry["summary"] = entry["summary"] or key
        return entry
    except Exception:
        pass

    browse_url = BROWSE_TEMPLATE.format(key=key)
    try:
        html = await client_fetch(
            browse_url,
            timeout=timeout,
            headers={
                "Accept": "text/html",
                "User-Agent": "migration-oracle/1.0",
            },
            accept_status={200},
        )
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        title_tag = soup.find("meta", property="og:title")
        desc_tag = soup.find("meta", property="og:description") or soup.find(
            "meta", attrs={"name": "description"}
        )
        return {
            "summary": title_tag["content"] if title_tag else key,
            "source_url": browse_url,
            "issue_type": "",
            "description": desc_tag["content"].strip() if desc_tag else "",
            "priority": "",
        }
    except Exception as exc:
        logger.warning("Jira fetch failed for %s: %s", key, exc)
        return None


async def enrich_with_jira(
    extractor,
    body: str,
    changes: list,
) -> list:
    """Async entry point used by legacy callers and tests."""
    cache, index = await extractor._load_jira_cache(body, changes)
    return extractor.enrich_with_jira(
        changes, cache=cache, index=index, body=body
    )
