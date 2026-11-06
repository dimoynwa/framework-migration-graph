"""GitHub issue and commit enrichment helpers.

Mirrors ``wildfly_jira.py``: pure parsing, no HTTP. ``BaseExtractor`` performs the
requests and calls :func:`parse_github_issue` / :func:`parse_github_commit`.
"""

from __future__ import annotations

import re
from typing import TypedDict

from migration_oracle import config
from migration_oracle.models.entities import DocumentedChange
from migration_oracle.pipeline.extractors.parsing import html_to_text

# Spring Boot release rows cite issues as bare ``#123`` or as full GitHub URLs.
_SPRING_ISSUE_URL_RE = re.compile(
    r"https://github\.com/spring-projects/spring-boot/(?:issues|pull)/(\d+)",
    re.IGNORECASE,
)
_BARE_ISSUE_RE = re.compile(r"#(\d+)")

# ``Backport of #39900``, ``Forward port of issue #39900 to 3.2.x``.
_BACKPORT_RE = re.compile(
    r"(?i)(?:back|forward)[- ]?port of (?:issue )?#(\d+)"
)
_BACKPORT_BODY_LIMIT = 200

_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_HTML_TAG_RE = re.compile(
    r"</?(?:p|div|br|li|ul|ol|h[1-6]|pre|code|a|span|table|img|blockquote|script|style)\b",
    re.IGNORECASE,
)
_FENCE_RE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
_EMPTY_FENCE_RE = re.compile(r"```[^\n`]*\n(?:[ \t]*\n)*```")

_EXCEPTION_LINE_RE = re.compile(
    r"^[ \t]*(?:Exception in thread \"[^\"]+\" )?(?:Caused by:\s*|Suppressed:\s*)?"
    r"(?:[\w$]+\.)*[\w$]*(?:Exception|Error|Throwable)\b[^\n]*$"
)
_FRAME_LINE_RE = re.compile(
    r"^[ \t]+(?:"
    r"at (?:[\w$.]+/)?(?:[\w$]+\.)+[\w$<>]+\([^)\n]*\)"
    r"|\.\.\. \d+ more"
    r")\s*$"
)
_PY_TRACE_RE = re.compile(
    r"Traceback \(most recent call last\):\n(?:[ \t]+[^\n]*\n)+[^\n]*(?:Error|Exception):[^\n]*"
)


class GitHubIssue(TypedDict):
    number: int
    title: str
    body: str
    labels: list[str]
    is_pull_request: bool
    state_reason: str
    html_url: str


class GitHubCommit(TypedDict):
    sha: str
    html_url: str
    header: str
    type: str
    scope: str
    body: str
    breaking: str
    deprecated: str
    fixes: list[int]
    pr: int | None
    files: list[str]
    bang: bool


# Conventional-commit header, including an optional ``(#123)`` pull trailer.
_COMMIT_HEADER_RE = re.compile(
    r"^(?P<type>\w+)(\((?P<scope>[^)]+)\))?(?P<bang>!)?:\s*(?P<subject>.+?)"
    r"(\s*\(#(?P<pr>\d+)\))?$"
)
_ANGULAR_COMMIT_RE = re.compile(
    r"angular/angular/commit/([0-9a-f]{7,40})",
    re.IGNORECASE,
)
_ANGULAR_ISSUE_URL_RE = re.compile(
    r"https://github\.com/angular/angular/(?:issues|pull)/(\d+)",
    re.IGNORECASE,
)
_SCHEMATIC_RE = re.compile(r"^packages/[^/]+/schematics/")
_BREAKING_FOOTER_RE = re.compile(r"(?i)^breaking changes?:\s*(.*)$")
_DEPRECATED_FOOTER_RE = re.compile(r"(?i)^deprecated:\s*(.*)$")
_FIXES_FOOTER_RE = re.compile(r"(?i)^(?:fixes|closes|resolves)\s+#\d+")
_PR_CLOSE_FOOTER_RE = re.compile(r"(?i)^pr close\s+#(\d+)")
_ISSUE_NUMBER_RE = re.compile(r"#(\d+)")

LINKED_ISSUE_EXCERPT_CHARS = 500


def issue_api_url(repo: str, number: int) -> str:
    return f"https://api.github.com/repos/{repo}/issues/{number}"


def commit_api_url(repo: str, sha: str) -> str:
    return f"https://api.github.com/repos/{repo}/commits/{sha}"


def extract_issue_numbers(statement: str) -> list[int]:
    """Issue numbers in left-to-right order, de-duplicated."""
    found: list[tuple[int, int]] = []
    for match in _SPRING_ISSUE_URL_RE.finditer(statement):
        found.append((match.start(), int(match.group(1))))
    for match in _BARE_ISSUE_RE.finditer(statement):
        found.append((match.start(), int(match.group(1))))
    found.sort(key=lambda item: item[0])
    ordered: list[int] = []
    seen: set[int] = set()
    for _, number in found:
        if number in seen:
            continue
        seen.add(number)
        ordered.append(number)
    return ordered


def backport_target(body: str) -> int | None:
    """Return the referenced issue when ``body`` is only a backport pointer.

    One level only: callers must not run this on the issue they substitute in.
    """
    if len(body) >= _BACKPORT_BODY_LIMIT:
        return None
    match = _BACKPORT_RE.search(body)
    if not match:
        return None
    return int(match.group(1))


def github_issue_type(labels: list[str]) -> str:
    """Value of the first ``type: …`` label, or ``""``."""
    for label in labels:
        if label.lower().startswith("type:"):
            return label.split(":", 1)[1].strip()
    return ""


def clean_issue_body(body: str, *, max_chars: int | None = None) -> str:
    """Strip template noise and cap the body length. Empty result is ``N/A``."""
    if max_chars is None:
        max_chars = config.GITHUB_ENRICH_BODY_MAX_CHARS
    text = body or ""
    text = _HTML_COMMENT_RE.sub("", text)
    text = _omit_long_fences(text)
    text = _strip_stack_traces(text)
    text = _EMPTY_FENCE_RE.sub("", text)
    text = _through_html_to_text(text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return "N/A"
    if len(text) > max_chars:
        keep = max(max_chars, 1) - 1
        text = text[:keep].rstrip() + "…"
    return text


def parse_github_issue(
    payload: dict,
    *,
    number: int,
    max_chars: int | None = None,
) -> GitHubIssue:
    """Build a :class:`GitHubIssue` from a GitHub REST issue or pull payload."""
    if not isinstance(payload, dict):
        raise TypeError(f"GitHub issue payload for #{number} is not an object")
    raw_number = payload.get("number", number)
    labels = _label_names(payload.get("labels"))
    state_reason = payload.get("state_reason") or ""
    html_url = payload.get("html_url") or ""
    return {
        "number": int(raw_number),
        "title": payload.get("title") or "",
        "body": clean_issue_body(payload.get("body") or "", max_chars=max_chars),
        "labels": labels,
        "is_pull_request": bool(payload.get("pull_request")),
        "state_reason": str(state_reason),
        "html_url": str(html_url),
    }


def extract_commit_shas(statement: str) -> list[str]:
    """Commit SHAs in left-to-right order, lower-cased and de-duplicated."""
    ordered: list[str] = []
    seen: set[str] = set()
    for match in _ANGULAR_COMMIT_RE.finditer(statement):
        sha = match.group(1).lower()
        if sha in seen:
            continue
        seen.add(sha)
        ordered.append(sha)
    return ordered


def extract_angular_issue_numbers(statement: str) -> list[int]:
    """Angular issue/PR numbers from full GitHub URLs, in order."""
    ordered: list[int] = []
    seen: set[int] = set()
    for match in _ANGULAR_ISSUE_URL_RE.finditer(statement):
        number = int(match.group(1))
        if number in seen:
            continue
        seen.add(number)
        ordered.append(number)
    return ordered


def parse_github_commit(
    payload: dict,
    *,
    sha: str,
    repo: str = "",
    max_chars: int | None = None,
) -> GitHubCommit:
    """Build a :class:`GitHubCommit` from a GitHub REST commit payload."""
    if not isinstance(payload, dict):
        raise TypeError(f"GitHub commit payload for {sha} is not an object")
    message = ((payload.get("commit") or {}).get("message")) or ""
    parsed = _parse_commit_message(message, max_chars=max_chars)
    full_sha = str(payload.get("sha") or sha)
    html_url = payload.get("html_url") or ""
    if not html_url and repo:
        html_url = f"https://github.com/{repo}/commit/{full_sha}"
    return {
        "sha": full_sha,
        "html_url": str(html_url),
        "header": parsed["header"],
        "type": parsed["type"],
        "scope": parsed["scope"],
        "body": parsed["body"],
        "breaking": parsed["breaking"],
        "deprecated": parsed["deprecated"],
        "fixes": parsed["fixes"],
        "pr": parsed["pr"],
        "files": _filenames(payload.get("files")),
        "bang": parsed["bang"],
    }


def has_schematic(files: list[str]) -> bool:
    """True when a changed file is an Angular ``ng update`` schematic."""
    return any(_SCHEMATIC_RE.search(path) for path in files)


def build_issue_change(
    change: DocumentedChange,
    issue: GitHubIssue,
    body: str,
    *,
    backport_of: int | None = None,
) -> DocumentedChange:
    """Title / Issue / Release row used by Spring Boot and the Angular issue fallback."""
    statement = (
        f"Title: {issue['title']}\n"
        f"Issue: {body}\n"
        f"Release: {change.statement}"
    )
    source_url = issue["html_url"] or change.source_url
    meta = dict(change.metadata or {})
    meta["release_url"] = change.source_url
    meta["github_issue"] = issue["number"]
    meta["github_labels"] = list(issue["labels"])
    meta["github_issue_type"] = github_issue_type(issue["labels"])
    meta["github_state_reason"] = issue["state_reason"]
    if issue["state_reason"] == "not_planned":
        meta["github_not_planned"] = True
    if backport_of is not None:
        meta["github_backport_of"] = backport_of
    change_type, confidence = refine_issue_type(
        change.type, change.confidence, issue["labels"]
    )
    return DocumentedChange(
        type=change_type,
        confidence=confidence,
        source_url=source_url,
        statement=statement,
        metadata=meta,
    )


def build_commit_change(
    change: DocumentedChange,
    commit: GitHubCommit,
    issue: GitHubIssue | None = None,
) -> DocumentedChange:
    """Title / Commit / optional Breaking, Deprecated, Issue / Release row."""
    lines = [
        f"Title: {commit['header']}",
        f"Commit: {commit['body']}",
    ]
    if commit["breaking"]:
        lines.append(f"Breaking: {commit['breaking']}")
    if commit["deprecated"]:
        lines.append(f"Deprecated: {commit['deprecated']}")
    if issue is not None:
        excerpt = issue["body"][:LINKED_ISSUE_EXCERPT_CHARS]
        lines.append(f"Issue: #{issue['number']} {issue['title']} — {excerpt}")
    lines.append(f"Release: {change.statement}")
    meta = dict(change.metadata or {})
    meta["release_url"] = change.source_url
    meta["github_commit"] = commit["sha"]
    meta["angular_package"] = commit["scope"]
    meta["angular_commit_type"] = commit["type"]
    meta["github_fixes"] = list(commit["fixes"])
    meta["github_files"] = list(commit["files"])
    meta["has_schematic"] = has_schematic(commit["files"])
    if commit["pr"] is not None:
        meta["github_pr"] = commit["pr"]
    change_type, confidence = refine_commit_type(
        change.type, change.confidence, commit
    )
    source_url = commit["html_url"] or change.source_url
    return DocumentedChange(
        type=change_type,
        confidence=confidence,
        source_url=source_url,
        statement="\n".join(lines),
        metadata=meta,
    )


def refine_issue_type(
    change_type: str, confidence: str, labels: list[str]
) -> tuple[str, str]:
    """Map ``type: dependency-upgrade`` onto rows still at the default class."""
    if change_type != "behavioral" or confidence != "inferred":
        return change_type, confidence
    if github_issue_type(labels).lower() == "dependency-upgrade":
        return "dependency_upgrade", "inferred"
    return change_type, confidence


def refine_commit_type(
    change_type: str, confidence: str, commit: GitHubCommit
) -> tuple[str, str]:
    """Breaking and deprecation footers override the section-derived type."""
    if commit["breaking"] or commit["bang"]:
        return "breaking", "confirmed"
    if commit["deprecated"]:
        return "deprecation", "confirmed"
    return change_type, confidence


def _parse_commit_message(
    message: str, *, max_chars: int | None
) -> dict:
    lines = message.splitlines()
    header = lines[0].strip() if lines else ""
    match = _COMMIT_HEADER_RE.match(header)
    commit_type = match.group("type") if match else ""
    scope = match.group("scope") if match and match.group("scope") else ""
    bang = bool(match and match.group("bang"))
    header_pr = int(match.group("pr")) if match and match.group("pr") else None

    body_lines: list[str] = []
    footers: list[tuple[str, str]] = []
    current: list[str] | None = None
    for line in lines[1:]:
        kind = _footer_kind(line)
        if kind is not None:
            if current is not None:
                footers.append((current[0], current[1].strip()))
            current = [kind, _footer_initial(kind, line)]
            continue
        if current is not None:
            extra = line.strip()
            if extra:
                current[1] = f"{current[1]} {extra}".strip()
            continue
        body_lines.append(line)
    if current is not None:
        footers.append((current[0], current[1].strip()))

    breaking = _footer_prose(next((text for kind, text in footers if kind == "breaking"), ""))
    deprecated = _footer_prose(
        next((text for kind, text in footers if kind == "deprecated"), "")
    )
    fixes: list[int] = []
    seen_fixes: set[int] = set()
    pr_close: int | None = None
    for kind, text in footers:
        if kind == "fixes":
            for number in _ISSUE_NUMBER_RE.findall(text):
                value = int(number)
                if value in seen_fixes:
                    continue
                seen_fixes.add(value)
                fixes.append(value)
        elif kind == "pr" and pr_close is None:
            found = _ISSUE_NUMBER_RE.search(text)
            if found:
                pr_close = int(found.group(1))

    return {
        "header": header,
        "type": commit_type,
        "scope": scope or "",
        "bang": bang,
        "body": clean_issue_body("\n".join(body_lines), max_chars=max_chars),
        "breaking": breaking,
        "deprecated": deprecated,
        "fixes": fixes,
        "pr": pr_close if pr_close is not None else header_pr,
    }


def _footer_kind(line: str) -> str | None:
    stripped = line.strip()
    if _BREAKING_FOOTER_RE.match(stripped):
        return "breaking"
    if _DEPRECATED_FOOTER_RE.match(stripped):
        return "deprecated"
    if _PR_CLOSE_FOOTER_RE.match(stripped):
        return "pr"
    if _FIXES_FOOTER_RE.match(stripped):
        return "fixes"
    return None


def _footer_initial(kind: str, line: str) -> str:
    stripped = line.strip()
    if kind in ("breaking", "deprecated"):
        return stripped.split(":", 1)[1].strip()
    return stripped


def _footer_prose(text: str) -> str:
    if not text.strip():
        return ""
    cleaned = clean_issue_body(text)
    return "" if cleaned == "N/A" else cleaned


def _filenames(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    names: list[str] = []
    for item in raw:
        if isinstance(item, str) and item:
            names.append(item)
        elif isinstance(item, dict):
            filename = item.get("filename")
            if isinstance(filename, str) and filename:
                names.append(filename)
    return names


def _label_names(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    names: list[str] = []
    for item in raw:
        if isinstance(item, str) and item:
            names.append(item)
        elif isinstance(item, dict):
            name = item.get("name")
            if isinstance(name, str) and name:
                names.append(name)
    return names


def _omit_long_fences(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        inner = match.group(1)
        if len(inner.splitlines()) > 10:
            return "[code omitted]"
        return match.group(0)

    return _FENCE_RE.sub(replace, text)


def _strip_stack_traces(text: str) -> str:
    text = _PY_TRACE_RE.sub("", text)
    lines = text.splitlines(keepends=True)
    kept: list[str] = []
    index = 0
    total = len(lines)
    while index < total:
        current = lines[index].rstrip("\r\n")
        if _EXCEPTION_LINE_RE.match(current) and _frame_index(lines, index + 1) is not None:
            index += 1
            while index < total:
                stripped = lines[index].rstrip("\r\n")
                if _FRAME_LINE_RE.match(stripped) or _EXCEPTION_LINE_RE.match(stripped):
                    index += 1
                    continue
                if stripped.strip() == "" and _frame_or_exception_index(lines, index + 1):
                    index += 1
                    continue
                break
            continue
        kept.append(lines[index])
        index += 1
    return "".join(kept)


def _frame_index(lines: list[str], start: int) -> int | None:
    index = start
    if index < len(lines) and lines[index].strip() == "":
        index += 1
    if index < len(lines) and _FRAME_LINE_RE.match(lines[index].rstrip("\r\n")):
        return index
    return None


def _frame_or_exception_index(lines: list[str], start: int) -> int | None:
    if start >= len(lines):
        return None
    stripped = lines[start].rstrip("\r\n")
    if _FRAME_LINE_RE.match(stripped) or _EXCEPTION_LINE_RE.match(stripped):
        return start
    return None


def _through_html_to_text(text: str) -> str:
    """Run ``html_to_text`` on HTML and leave plain text, including generics, intact.

    ``html_to_text`` only keeps headings, paragraphs, and list items, and an HTML
    parser treats ``Record<string, Foo>`` as a tag. Skip that parse unless the
    text actually contains markup.
    """
    if not _HTML_TAG_RE.search(text):
        return text
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(text, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    plain = soup.get_text("\n", strip=False)
    converted = html_to_text(str(soup))
    if not converted.strip():
        return plain
    if len(converted.strip()) < len(plain.strip()) * 0.8:
        return plain
    return converted
