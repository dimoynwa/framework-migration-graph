"""Group gate-kept rows that describe the same change.

Edges are specific pull, commit, issue, JIRA, or compare-anchor URLs. A row's
own sources can meet another row's sources or that row's fetched pages.
Oversized components are split back to row-source edges, then to single rows.
"""

from __future__ import annotations

import hashlib
import logging
import re
import sys
from collections import defaultdict
from dataclasses import dataclass

from migration_oracle.pipeline.entities.gate import InputRow
from migration_oracle.pipeline.research.schema import normalize_url

logger = logging.getLogger("migration_oracle.pipeline.entities")

_PULL = re.compile(r"/pull/\d+", re.IGNORECASE)
_COMMIT = re.compile(r"/commit/[0-9a-f]{7,}", re.IGNORECASE)
_ISSUES = re.compile(r"/issues/\d+", re.IGNORECASE)
_BROWSE = re.compile(r"/browse/[A-Z][A-Z0-9]+-\d+", re.IGNORECASE)
_WHAT_CHANGED = re.compile(r"^\s*\*\*What changed:\*\*\s*(.*)$", re.MULTILINE)
# github.com and patch-diff.githubusercontent.com/raw: owner, repo, kind, id.
# Suffixes (.patch, .diff, /files, /commits/<sha>) are not part of the match.
_GITHUB_CHANGE = re.compile(
    r"^https?://(?:www\.)?(?:github\.com|patch-diff\.githubusercontent\.com/raw)/"
    r"([^/\s]+)/([^/\s]+)/(pull|commit|issues)/([0-9a-f]+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Cluster:
    members: tuple[InputRow, ...]

    @property
    def cluster_key(self) -> str:
        material = "\n".join(sorted(member.row.row_key for member in self.members))
        return hashlib.sha256(material.encode("utf-8")).hexdigest()


def is_specific_url(url: str) -> bool:
    """Pull, commit, issue, JIRA browse, or a compare URL that anchors one change.

    Release tags, changelog files, docs, and blog pages are not specific.
    """
    if not url or not url.lower().startswith("http"):
        return False
    lowered = normalize_url(url).lower()
    if "/releases/tag/" in lowered or "changelog.md" in lowered:
        return False
    if _PULL.search(lowered) or _COMMIT.search(lowered) or _ISSUES.search(lowered):
        return True
    if _BROWSE.search(url):
        return True
    return "/compare/" in lowered and "#" in url


def specific_key(url: str) -> str | None:
    """Normalized identity of a specific URL, or ``None``.

    GitHub pull, commit, and issue URLs collapse to
    ``https://github.com/<owner>/<repo>/<kind>/<id>``, so ``commit/<sha>.patch``,
    ``pull/<n>.diff``, ``pull/<n>/files`` and the patch-diff host meet the plain URL.
    """
    if not is_specific_url(url):
        return None
    normalized = normalize_url(url)
    github = _GITHUB_CHANGE.match(normalized)
    if github:
        owner, repo, kind, ident = (part.lower() for part in github.groups())
        return f"https://github.com/{owner}/{repo}/{kind}/{ident}"
    if "/compare/" in normalized.lower() and "#" in normalized:
        return normalized
    return normalized.split("#", 1)[0].rstrip("/")


def cluster_kept(
    rows: list[InputRow],
    *,
    max_rows: int,
    confirmer=None,
) -> list[Cluster]:
    """Connected components of the gate-kept rows, in raw order."""
    kept = [row for row in rows if row.decision == "keep"]
    if not kept:
        return []
    row_sets = [_specific(member.row.sources) for member in kept]
    dossier_sets = [_dossier_urls(member) for member in kept]
    groups = _components(len(kept), row_sets, dossier_sets, dossier_edges=True)
    pieces: list[list[int]] = []
    for group in groups:
        pieces.extend(_cap(group, row_sets, dossier_sets, max_rows))
    clusters = [
        Cluster(tuple(kept[index] for index in sorted(piece))) for piece in pieces
    ]
    clusters.sort(key=lambda cluster: cluster.members[0].position)
    if confirmer is None:
        return clusters
    return _apply_confirm(clusters, confirmer)


def render_confirm_prompt(cluster: Cluster) -> str:
    """Titles and ``What changed`` lines for the optional same/split check."""
    lines = [
        "These rows were grouped because they share a pull request, commit, or issue.",
        "Answer with one word: same if they are one change, split if they are different changes.",
        "",
    ]
    for number, member in enumerate(cluster.members, start=1):
        changed = ""
        if member.dossier is not None:
            match = _WHAT_CHANGED.search(member.dossier.text or "")
            changed = match.group(1).strip() if match else ""
        lines.append(f"{number}. {member.row.title}")
        if changed:
            lines.append(f"What changed: {changed}")
    return "\n".join(lines)


def verdict_of(text: str) -> str:
    """``split`` only when that is the answer. Anything else stays merged."""
    word = (text or "").strip().lower().split(None, 1)[0] if (text or "").strip() else ""
    word = word.strip(".,:;\"'`")
    return "split" if word == "split" else "same"


def _specific(urls: tuple[str, ...] | list[str]) -> set[str]:
    keys: set[str] = set()
    for url in urls:
        key = specific_key(url)
        if key:
            keys.add(key)
    return keys


def _dossier_urls(member: InputRow) -> set[str]:
    if member.dossier is None or member.dossier.status != "ok":
        return set()
    return _specific(member.dossier.sources)


def _components(
    count: int,
    row_sets: list[set[str]],
    dossier_sets: list[set[str]],
    *,
    dossier_edges: bool,
) -> list[list[int]]:
    parent = list(range(count))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    row_index: dict[str, list[int]] = defaultdict(list)
    dossier_index: dict[str, list[int]] = defaultdict(list)
    for index, urls in enumerate(row_sets):
        for url in urls:
            row_index[url].append(index)
    if dossier_edges:
        for index, urls in enumerate(dossier_sets):
            for url in urls:
                dossier_index[url].append(index)
    for url, owners in row_index.items():
        targets = set(owners)
        if dossier_edges:
            targets.update(dossier_index.get(url, []))
        anchor = owners[0]
        for other in targets:
            if other != anchor:
                union(anchor, other)
    groups: dict[int, list[int]] = defaultdict(list)
    for index in range(count):
        groups[find(index)].append(index)
    return sorted(groups.values(), key=lambda members: members[0])


def _cap(
    indices: list[int],
    row_sets: list[set[str]],
    dossier_sets: list[set[str]],
    max_rows: int,
) -> list[list[int]]:
    if len(indices) <= max_rows:
        return [indices]
    urls = _joining_urls(indices, row_sets, dossier_sets)
    message = (
        f"cluster split: {len(indices)} rows exceed CLUSTER_MAX_ROWS={max_rows}; "
        f"urls: {', '.join(urls) if urls else '(none)'}"
    )
    # Printed for the operator; logged at INFO so the root handler does not repeat it.
    logger.info(message)
    print(message, file=sys.stderr)
    local_rows = [row_sets[index] for index in indices]
    local_dossiers = [set() for _ in indices]
    parts = _components(len(indices), local_rows, local_dossiers, dossier_edges=False)
    pieces: list[list[int]] = []
    for part in parts:
        mapped = [indices[local] for local in part]
        if len(mapped) <= max_rows:
            pieces.append(mapped)
            continue
        for index in mapped:
            pieces.append([index])
    pieces.sort(key=lambda piece: piece[0])
    return pieces


def _joining_urls(
    indices: list[int],
    row_sets: list[set[str]],
    dossier_sets: list[set[str]],
) -> list[str]:
    counts: dict[str, int] = defaultdict(int)
    for index in indices:
        for url in row_sets[index] | dossier_sets[index]:
            counts[url] += 1
    return sorted(url for url, count in counts.items() if count >= 2)


def _apply_confirm(clusters: list[Cluster], confirmer) -> list[Cluster]:
    confirmed: list[Cluster] = []
    for cluster in clusters:
        if len(cluster.members) < 2:
            confirmed.append(cluster)
            continue
        try:
            verdict = confirmer(cluster)
        except Exception as exc:
            logger.warning("cluster confirm failed (%s); keeping the cluster", exc)
            verdict = "same"
        if verdict_of(str(verdict)) == "split":
            confirmed.extend(Cluster((member,)) for member in cluster.members)
        else:
            confirmed.append(cluster)
    return confirmed
