"""Shared parsing utilities for framework HTTP extractors."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Iterable

from migration_oracle.models.entities import DocumentedChange
from migration_oracle.models.graph import is_prerelease, version_parts

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(.*)$")
_BULLET_RE = re.compile(r"^[\s]*[-*+]\s+(.+)$")
_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$")
_CLI_SUBSYSTEM_RE = re.compile(r"/subsystem=")

_SECTION_TYPE_MAP: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"breaking", re.I), "breaking", "confirmed"),
    (re.compile(r"deprecat", re.I), "deprecation", "confirmed"),
    (re.compile(r"mandatory|migration|upgrade guide", re.I), "mandatory_migration", "confirmed"),
    (re.compile(r"dependency|bom|component", re.I), "dependency_upgrade", "inferred"),
    (re.compile(r"security|cve", re.I), "mandatory_migration", "confirmed"),
    (re.compile(r"behavior", re.I), "behavioral", "inferred"),
]

_STABILITY_MARKERS = {
    "[experimental]": "experimental",
    "[preview]": "preview",
    "[community]": "community",
}


def parse_version(version: str) -> tuple[int, int, int, str]:
    match = _VERSION_RE.match(version.strip())
    if not match:
        raise ValueError(f"Invalid semver: {version!r}")
    return int(match.group(1)), int(match.group(2)), int(match.group(3)), match.group(4)


def version_key(version: str) -> tuple[int, int, int, int]:
    """
    Sort/compare key: ``(major, minor, patch, prerelease_offset)``.

    The offset term is 0 for GA builds and negative for milestone/RC builds.
    Without it ``4.1.0-M1``, ``4.1.0-RC1`` and ``4.1.0`` all compare equal, so
    discovery order decided hop sequences and a range ending at ``4.1.0-RC1``
    also pulled in the ``4.1.0`` GA release.
    """
    try:
        return version_parts(version)
    except ValueError:
        major, minor, patch, _ = parse_version(version)
        return (major, minor, patch, 0)


def compare_versions(left: str, right: str) -> int:
    lk, rk = version_key(left), version_key(right)
    if lk < rk:
        return -1
    if lk > rk:
        return 1
    return 0


def normalize_wildfly_maven_version(maven_version: str) -> str:
    if maven_version.endswith(".Final"):
        return maven_version[: -len(".Final")]
    return maven_version


def parse_maven_metadata_versions(xml_text: str) -> list[str]:
    root = ET.fromstring(xml_text)

    def local(tag: str) -> str:
        return tag.split("}")[-1] if "}" in tag else tag

    versions: list[str] = []
    for elem in root.iter():
        if local(elem.tag) == "version" and elem.text:
            versions.append(elem.text.strip())
    return versions


def filter_release_versions(
    versions: Iterable[str],
    *,
    final_only: bool = False,
    semver_only: bool = True,
) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in versions:
        v = raw.strip()
        if not v or v in seen:
            continue
        match = _VERSION_RE.match(v)
        if semver_only and not match:
            continue
        if match:
            suffix = match.group(4)
            if suffix and suffix != ".Final":
                continue
        if final_only and not v.endswith(".Final"):
            continue
        seen.add(v)
        result.append(v)
    result.sort(key=version_key)
    return result


def versions_in_range(
    versions: list[str], from_version: str, to_version: str
) -> list[str]:
    ordered = sorted(versions, key=version_key)
    if compare_versions(from_version, to_version) > 0:
        raise ValueError(
            f"from_version {from_version!r} is after to_version {to_version!r}"
        )
    if from_version not in ordered:
        raise ValueError(f"from_version {from_version!r} not found in metadata")
    if to_version not in ordered:
        raise ValueError(f"to_version {to_version!r} not found in metadata")

    selected = [
        v
        for v in ordered
        if compare_versions(from_version, v) <= 0
        and compare_versions(v, to_version) <= 0
    ]
    if len(selected) < 2:
        raise ValueError(
            f"Need at least two versions in range {from_version!r} → {to_version!r}; "
            f"found {selected!r}"
        )
    return selected


#: Version arguments that resolve against the discovered release list.
LATEST_ALIASES: frozenset[str] = frozenset({"latest"})
LATEST_GA_ALIASES: frozenset[str] = frozenset({"latest-ga", "latest-stable"})
_SNAPSHOT_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)-SNAPSHOT$", re.IGNORECASE)


def is_version_alias(version: str) -> bool:
    """True for ``latest``, ``latest-ga``/``latest-stable`` and ``X.Y.Z-SNAPSHOT``."""
    normalized = version.strip().lower()
    return (
        normalized in LATEST_ALIASES
        or normalized in LATEST_GA_ALIASES
        or bool(_SNAPSHOT_RE.match(version.strip()))
    )


def resolve_version_alias(versions: list[str], version: str) -> str:
    """
    Map a version alias to a concrete published release from ``versions``.

    ``latest``             → newest discovered release (milestones/RCs included
                             when the extractor discovers them).
    ``latest-ga``          → newest GA release.
    ``X.Y.Z-SNAPSHOT``     → newest published build of ``X.Y.Z`` (GA if out,
                             else its newest milestone/RC). Snapshots are never
                             published with release notes, so the last tagged
                             build is the closest documented state.

    Non-alias versions are returned unchanged.
    """
    raw = version.strip()
    normalized = raw.lower()
    ordered = sorted(versions, key=version_key)
    if normalized in LATEST_ALIASES:
        if not ordered:
            raise ValueError("Cannot resolve 'latest': no versions discovered")
        return ordered[-1]
    if normalized in LATEST_GA_ALIASES:
        ga = [v for v in ordered if not is_prerelease(v)]
        if not ga:
            raise ValueError(f"Cannot resolve {raw!r}: no GA versions discovered")
        return ga[-1]
    snapshot = _SNAPSHOT_RE.match(raw)
    if snapshot:
        triple = tuple(int(part) for part in snapshot.groups())
        builds = [v for v in ordered if parse_version(v)[:3] == triple]
        if not builds:
            raise ValueError(
                f"{raw}: no milestone, RC, or GA build of "
                f"{'.'.join(map(str, triple))} is published yet. Snapshot builds "
                "have no release notes; use the newest published version instead."
            )
        return builds[-1]
    return raw


def releases_covered_by_hop(
    versions: list[str], from_version: str, to_version: str
) -> tuple[str, ...]:
    """
    Releases whose notes document a ``from_version → to_version`` hop.

    Every discovered release after ``from_version`` up to and including
    ``to_version`` on the target's ``major.minor`` line. A minor hop
    ``4.0.0 → 4.1.0`` therefore covers ``4.1.0-M1 … 4.1.0-RC1, 4.1.0``: the GA
    release notes list only what changed since the last RC, so the milestones
    carry most of the line's changes. Earlier-line patches (``4.0.x``) are left
    out — their fixes reach the new line as forward ports listed in its notes.
    """
    to_line = parse_version(to_version)[:2]
    covered = [
        v
        for v in sorted(versions, key=version_key)
        if compare_versions(from_version, v) < 0
        and compare_versions(v, to_version) <= 0
        and parse_version(v)[:2] == to_line
    ]
    if to_version not in covered:
        covered.append(to_version)
    return tuple(covered)


def compute_hops(versions: list[str]) -> list[tuple[str, str]]:
    if len(versions) < 2:
        raise ValueError("Need at least two versions to compute hops")
    return [(versions[i], versions[i + 1]) for i in range(len(versions) - 1)]


#: Supported hop granularities for ``select_hop_versions``.
HOP_GRANULARITIES: tuple[str, ...] = ("patch", "minor")


def validate_hop_granularity(granularity: str) -> str:
    """Return ``granularity`` if it is a supported hop granularity."""
    normalized = granularity.strip().lower()
    if normalized not in HOP_GRANULARITIES:
        raise ValueError(
            f"Unknown hop granularity {granularity!r}; "
            f"expected one of {', '.join(HOP_GRANULARITIES)}"
        )
    return normalized


def select_hop_versions(
    versions: list[str],
    from_version: str,
    to_version: str,
    granularity: str = "patch",
) -> list[str]:
    """
    Version boundaries that become hops for the requested granularity.

    ``patch`` — every released version in range, so every patch release is its
                own hop (the historical behaviour of the raw extraction stage),
                including milestone/RC builds when prereleases are enabled.
    ``minor`` — only GA ``X.Y.0`` releases plus the requested endpoints, so one
                hop per minor line even when the endpoints are patch releases
                (``3.1.12 → 3.2.4`` yields ``3.1.12 → 3.2.0 → 3.2.4``).
                Prereleases are skipped unless the caller asked for one
                explicitly, e.g. ``4.0.6 → 4.1.0-RC1`` stays a single hop.
    """
    selected_granularity = validate_hop_granularity(granularity)
    in_range = versions_in_range(versions, from_version, to_version)
    if selected_granularity == "patch":
        return in_range
    return [
        version
        for version in in_range
        if version in (from_version, to_version)
        or (parse_version(version)[2] == 0 and not is_prerelease(version))
    ]


def enters_new_minor_line(from_version: str, to_version: str) -> bool:
    """
    True when a hop crosses into a different ``major.minor`` line.

    Minor-line release notes (Spring Boot wiki pages, migration guides) describe
    what changes when you *enter* a line, so they belong to the hop that crosses
    the boundary — not to every patch hop inside the line, which would duplicate
    the same prose across the whole line.
    """
    from_major, from_minor, _, _ = parse_version(from_version)
    to_major, to_minor, _, _ = parse_version(to_version)
    return (to_major, to_minor) != (from_major, from_minor)


def classify_statement(section: str, text: str) -> tuple[str, str]:
    combined = f"{section} {text}"
    for pattern, change_type, confidence in _SECTION_TYPE_MAP:
        if pattern.search(combined):
            return change_type, confidence
    if _CLI_SUBSYSTEM_RE.search(text):
        return "mandatory_migration", "confirmed"
    return "behavioral", "inferred"


def detect_stability_level(text: str) -> str | None:
    lowered = text.lower()
    for marker, level in _STABILITY_MARKERS.items():
        if marker in lowered:
            return level
    return None


_SECTION_LINE_RE = re.compile(
    r"^(⭐|🐞|💥|🛠|📔|🚨|‼️|\*\*)?.{0,3}(New Features|Bug Fixes|Breaking Changes|"
    r"Deprecat|Documentation|Dependency|Changes|Enhancement)",
    re.I,
)


def parse_github_release_text(body: str, source_url: str) -> list[DocumentedChange]:
    """Parse plain text from GitHub release HTML or API markdown."""
    markdown_changes = parse_markdown_statements(body, source_url)
    if markdown_changes:
        return markdown_changes

    section = ""
    changes: list[DocumentedChange] = []
    pending: str | None = None

    def flush(statement: str) -> None:
        if len(statement) < 8:
            return
        change_type, confidence = classify_statement(section, statement)
        changes.append(
            DocumentedChange(
                type=change_type,
                confidence=confidence,
                source_url=source_url,
                statement=statement,
            )
        )

    for line in body.splitlines():
        text = line.strip()
        if not text or text.startswith("#") and text[1:].isdigit():
            if pending:
                flush(pending)
                pending = None
            continue
        if _SECTION_LINE_RE.match(text) or (
            len(text) < 80 and text[0].isupper() and ":" not in text and not text.startswith("-")
        ):
            if pending:
                flush(pending)
                pending = None
            section = text
            continue
        if pending:
            flush(f"{pending} ({text})")
            pending = None
        else:
            pending = text

    if pending:
        flush(pending)
    return changes


def parse_markdown_statements(
    body: str,
    source_url: str,
    *,
    default_section: str = "",
) -> list[DocumentedChange]:
    if not body or not body.strip():
        return []

    section = default_section
    changes: list[DocumentedChange] = []
    stability = detect_stability_level(body)

    for line in body.splitlines():
        heading = _HEADING_RE.match(line)
        if heading:
            section = heading.group(1).strip()
            continue
        bullet = _BULLET_RE.match(line)
        if bullet:
            text = bullet.group(1).strip()
            if len(text) < 4:
                continue
            change_type, confidence = classify_statement(section, text)
            meta = {"stability_level": stability} if stability else None
            changes.append(
                DocumentedChange(
                    type=change_type,
                    confidence=confidence,
                    source_url=source_url,
                    statement=text,
                    metadata=meta,
                )
            )
            continue
        if line.strip() and len(line.strip()) > 20 and "[" in line:
            change_type, confidence = classify_statement(section, line)
            changes.append(
                DocumentedChange(
                    type=change_type,
                    confidence=confidence,
                    source_url=source_url,
                    statement=line.strip(),
                    metadata={"stability_level": stability} if stability else None,
                )
            )
    return changes


def html_to_text(html: str) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    lines: list[str] = []
    for element in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li"]):
        text = element.get_text(" ", strip=True)
        if not text:
            continue
        if element.name.startswith("h"):
            level = int(element.name[1])
            lines.append("#" * level + f" {text}")
        elif element.name == "li":
            lines.append(f"- {text}")
        else:
            lines.append(text)
    return "\n".join(lines)


def parse_asciidoc_migration_guide(content: str, source_url: str) -> list[DocumentedChange]:
    section = ""
    changes: list[DocumentedChange] = []
    for line in content.splitlines():
        if line.startswith("="):
            section = line.lstrip("=").strip()
            continue
        if line.startswith("- ") or line.startswith("* "):
            text = line[2:].strip()
            if len(text) < 4:
                continue
            change_type, confidence = classify_statement(section, text)
            changes.append(
                DocumentedChange(
                    type=change_type,
                    confidence=confidence,
                    source_url=source_url,
                    statement=text,
                )
            )
    return changes


def apply_cli_hints(changes: list[DocumentedChange]) -> list[DocumentedChange]:
    updated: list[DocumentedChange] = []
    for change in changes:
        if _CLI_SUBSYSTEM_RE.search(change.statement):
            updated.append(
                DocumentedChange(
                    type="mandatory_migration",
                    confidence="confirmed",
                    source_url=change.source_url,
                    statement=change.statement,
                    metadata=change.metadata,
                )
            )
        else:
            updated.append(change)
    return updated


def parse_pom_dependencies(pom_xml: str) -> dict[str, str]:
    root = ET.fromstring(pom_xml)

    def local(tag: str) -> str:
        return tag.split("}")[-1] if "}" in tag else tag

    deps: dict[str, str] = {}
    in_dm = False
    for elem in root.iter():
        tag = local(elem.tag)
        if tag == "dependencyManagement":
            in_dm = True
        if not in_dm:
            continue
        if tag == "dependency":
            group = artifact = version = None
            for child in elem:
                ct = local(child.tag)
                if ct == "groupId" and child.text:
                    group = child.text.strip()
                elif ct == "artifactId" and child.text:
                    artifact = child.text.strip()
                elif ct == "version" and child.text:
                    version = child.text.strip()
            if group and artifact and version:
                deps[f"{group}:{artifact}"] = version
    return deps


def bom_diff(
    from_deps: dict[str, str], to_deps: dict[str, str]
) -> dict[str, list[dict[str, str]]]:
    added: list[dict[str, str]] = []
    changed: list[dict[str, str]] = []
    removed: list[dict[str, str]] = []
    all_keys = set(from_deps) | set(to_deps)
    for key in sorted(all_keys):
        if key not in from_deps:
            added.append({"coordinate": key, "version": to_deps[key]})
        elif key not in to_deps:
            removed.append({"coordinate": key, "version": from_deps[key]})
        elif from_deps[key] != to_deps[key]:
            changed.append(
                {
                    "coordinate": key,
                    "from_version": from_deps[key],
                    "to_version": to_deps[key],
                }
            )
    return {"added": added, "changed": changed, "removed": removed}
