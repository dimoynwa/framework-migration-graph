"""Angular public-API index: fetch, parse, cache (spec 025 FR-3).

Angular publishes its public API as golden files,
``goldens/public-api/<entry-point>/index.api.md`` in ``angular/angular``. For a
hop ``from → to`` the goldens at both version tags are fetched (removed symbols
exist only in ``from``, introduced ones only in ``to``) and cached under
``ARTIFACT_CACHE_DIR/api-index/angular/<version>.json``.

When the index cannot be fetched, populate continues: callers get an index with
``status == "unavailable"`` and every npm entity is written with
``verified: false``.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import httpx

from migration_oracle.pipeline.extractors.base import GITHUB_HEADERS

logger = logging.getLogger(__name__)

ANGULAR_REPO = "angular/angular"
_GOLDENS_ROOT = "goldens/public-api"
_TREES_URL = f"https://api.github.com/repos/{ANGULAR_REPO}/git/trees"
_RAW_URL = f"https://raw.githubusercontent.com/{ANGULAR_REPO}"

# Bumped when parse_golden changes, so stale cached indexes are rebuilt.
PARSER_VERSION = 3

# Version index cache: package -> {symbol: [members]}
VersionIndex = dict[str, dict[str, list[str]]]


class ApiIndexUnavailable(Exception):
    """Raised by the default client when GitHub cannot be reached."""


class GoldenClient(Protocol):
    """The two GitHub reads the index needs. Tests inject a fake."""

    def entry_point_paths(self) -> list[str]:
        """Paths like ``["core/index.api.md", "core/testing/index.api.md"]``."""

    def golden_text(self, path: str) -> str:
        """Raw text of one golden file at the hop's version tag."""


class HttpGoldenClient:
    """GitHub REST + raw reader for one Angular version tag."""

    def __init__(self, version: str, token: str = "") -> None:
        self._version = version
        self._token = token

    def _headers(self, accept: str) -> dict[str, str]:
        headers = dict(GITHUB_HEADERS)
        headers["Accept"] = accept
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def entry_point_paths(self) -> list[str]:
        """Golden paths relative to ``goldens/public-api``, one tree request.

        ``git/trees/<tag>:<dir>?recursive=1`` returns paths relative to the
        goldens root, so ``core/testing/index.api.md`` keeps its entry point.
        Tags before v19 name the file ``index.md``; both are accepted.
        """
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            response = client.get(
                f"{_TREES_URL}/{self._version}:{_GOLDENS_ROOT}",
                params={"recursive": "1"},
                headers=self._headers("application/vnd.github+json"),
            )
            if response.status_code == 404:
                raise ApiIndexUnavailable(
                    f"no {_GOLDENS_ROOT} at {ANGULAR_REPO}@{self._version} (tag missing?)"
                )
            response.raise_for_status()
            payload = response.json()
        if payload.get("truncated"):
            raise ApiIndexUnavailable(
                f"git tree for {ANGULAR_REPO}@{self._version} is truncated"
            )
        return sorted(
            item["path"]
            for item in payload.get("tree") or []
            if isinstance(item, dict)
            and item.get("type") == "blob"
            and is_golden_path(item.get("path", ""))
        )

    def golden_text(self, path: str) -> str:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            response = client.get(
                f"{_RAW_URL}/{self._version}/{_GOLDENS_ROOT}/{path}",
                headers=self._headers("text/plain"),
            )
            response.raise_for_status()
            return response.text


_GOLDEN_FILENAMES = ("index.api.md", "index.md")


def is_golden_path(path: str) -> bool:
    """``core/index.api.md`` (v19+) or ``core/index.md`` (before v19)."""
    return path.rsplit("/", 1)[-1] in _GOLDEN_FILENAMES


# API Extractor report syntax (the ```ts block of a golden file):
#   export class X {            export interface X<T> extends Y {
#   export abstract class X {   export function f(options: {
#   export const X: Y;          export type X = ...;
#   class X_2 {  + later  export { X_2 as X }   (non-exported declaration)
_DECL_RE = re.compile(
    r"^(?P<export>export\s+)?(?:declare\s+)?(?:abstract\s+)?"
    r"(?:const\s+enum|class|interface|function|const|let|var|type|enum|namespace)\s+"
    r"(?P<name>[A-Za-z_$\u0275][\w$\u0275]*)"
)
_CONST_TYPE_RE = re.compile(
    r"^export\s+(?:declare\s+)?const\s+[\w$\u0275]+\s*:\s*(?P<type>[A-Za-z_$][\w$]*)\s*;"
)
_EXPORT_LIST_RE = re.compile(r"^export\s*\{(?P<items>[^}]*)\}")
_MEMBER_RE = re.compile(
    r"^\s+(?:(?:static|readonly|abstract|override|protected|public|private|declare|"
    r"(?:get|set)(?=\s+[\w$#]))\s+)*"
    r"(?P<name>[A-Za-z_$#\u0275][\w$\u0275]*)\s*[?!]?\s*[(<:=,;]"
)


def parse_golden(text: str) -> dict[str, list[str]]:
    """One golden file → ``{exported symbol: [members]}``.

    - Declarations open a block when their line leaves ``{`` unclosed. Members
      are the identifiers at brace depth 1 of that block: class / interface /
      enum members, and the inline option fields of a function signature
      (``provideCheckNoChangesConfig(options: { exhaustive: false; })``).
      Overloads and declaration merging union their members.
    - Non-exported declarations (``class NgForOf``) become public through
      ``export { NgForOf }`` / ``export { NgForOf as NgFor }`` /
      ``export { Location_2 as Location }``.
    - Re-exports of imported symbols (``export { DOCUMENT }`` in
      ``@angular/common``) are skipped; the declaring package owns the symbol.
    - ``export const TestBed: TestBedStatic;`` gives ``TestBed`` the members of
      ``TestBedStatic`` as well (static API surfaced through a const).
    """
    declared: dict[str, list[str]] = {}
    exported: set[str] = set()
    aliases: list[tuple[str, str]] = []  # (local, exported)
    const_types: list[tuple[str, str]] = []
    owner: str | None = None
    depth = 0
    for line in text.splitlines():
        if owner is not None:
            if depth == 1:
                member = _MEMBER_RE.match(line)
                if member:
                    name = member.group("name")
                    if name not in declared[owner]:
                        declared[owner].append(name)
            depth += line.count("{") - line.count("}")
            if depth <= 0:
                owner, depth = None, 0
            continue
        export_list = _EXPORT_LIST_RE.match(line)
        if export_list:
            for item in export_list.group("items").split(","):
                parts = item.split()
                if len(parts) == 3 and parts[1] == "as":
                    aliases.append((parts[0], parts[2]))
                elif len(parts) == 1:
                    aliases.append((parts[0], parts[0]))
            continue
        declaration = _DECL_RE.match(line)
        if not declaration:
            continue
        name = declaration.group("name")
        declared.setdefault(name, [])
        if declaration.group("export"):
            exported.add(name)
            const_type = _CONST_TYPE_RE.match(line)
            if const_type:
                const_types.append((name, const_type.group("type")))
        opened = line.count("{") - line.count("}")
        if opened > 0:
            owner, depth = name, opened

    symbols: dict[str, list[str]] = {name: list(declared[name]) for name in sorted(exported)}
    for local, public in aliases:
        if local not in declared:
            # `import { DOCUMENT } from '@angular/core'` + `export { DOCUMENT }`:
            # a re-export of a symbol declared elsewhere. Only the declaring
            # package counts, so one symbol keeps one identity.
            continue
        members = symbols.setdefault(public, [])
        for member in declared.get(local, []):
            if member not in members:
                members.append(member)
    for name, type_name in const_types:
        members = symbols[name]
        for member in declared.get(type_name, []):
            if member not in members:
                members.append(member)
    return symbols


def package_for_path(path: str) -> str:
    """``core/testing/index.api.md`` (or ``index.md``) → ``@angular/core/testing``."""
    parts = path.strip("/").split("/")
    if parts and parts[-1] in _GOLDEN_FILENAMES:
        parts = parts[:-1]
    return "/".join(["@angular"] + parts)


def _cache_path(cache_dir: Path, version: str) -> Path:
    return cache_dir / "api-index" / "angular" / f"{version}.json"


def load_version_index(
    version: str,
    *,
    cache_dir: Path,
    token: str = "",
    client: GoldenClient | None = None,
    force: bool = False,
) -> VersionIndex:
    """Cached per-version index: ``{package: {symbol: [members]}}``.

    Raises on any fetch or parse failure; the hop loader turns that into an
    ``unavailable`` status so populate can continue.
    """
    path = _cache_path(cache_dir, version)
    if not force and path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if (
            isinstance(payload, dict)
            and "packages" in payload
            and payload.get("parser") == PARSER_VERSION
        ):
            return {pkg: dict(symbols) for pkg, symbols in payload["packages"].items()}
    active_client = client or HttpGoldenClient(version, token=token)
    index: VersionIndex = {}
    paths = active_client.entry_point_paths()
    for entry_path in paths:
        package = package_for_path(entry_path)
        golden = parse_golden(active_client.golden_text(entry_path))
        if golden:
            index[package] = golden
    if not index:
        raise ApiIndexUnavailable(
            f"no symbols parsed from {ANGULAR_REPO}@{version} goldens "
            f"({len(paths)} file(s) listed)"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"version": version, "parser": PARSER_VERSION, "packages": index},
            ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )
    return index


@dataclass(frozen=True)
class HopApiIndex:
    """Both versions of a hop merged for lookup by the normalizer."""

    status: str  # "ok" | "partial" | "unavailable"
    versions: tuple[str, ...]
    packages: frozenset[str] = field(default_factory=frozenset)
    # symbol -> entry points exporting it (union over both versions)
    symbol_packages: dict[str, frozenset[str]] = field(default_factory=dict)
    # (package, symbol) -> member names (union over both versions)
    members: dict[tuple[str, str], frozenset[str]] = field(default_factory=dict)

    # Versions whose goldens could not be loaded ("partial" status only).
    missing_versions: tuple[str, ...] = ()

    @property
    def usable(self) -> bool:
        """True when at least one version's goldens were loaded."""
        return self.status in ("ok", "partial")

    def entry_points(self, symbol: str) -> frozenset[str]:
        return self.symbol_packages.get(symbol, frozenset())

    def members_of(self, package: str, symbol: str) -> frozenset[str]:
        return self.members.get((package, symbol), frozenset())

    def is_known_symbol(self, symbol: str) -> bool:
        return symbol in self.symbol_packages

    @classmethod
    def unavailable(cls, versions: tuple[str, ...]) -> "HopApiIndex":
        return cls(status="unavailable", versions=versions)


def build_hop_index(
    versions: tuple[str, ...],
    version_indexes: list[VersionIndex],
    missing_versions: tuple[str, ...] = (),
) -> HopApiIndex:
    symbol_packages: dict[str, set[str]] = {}
    members: dict[tuple[str, str], set[str]] = {}
    packages: set[str] = set()
    for index in version_indexes:
        for package, symbols in index.items():
            packages.add(package)
            for symbol, member_list in symbols.items():
                symbol_packages.setdefault(symbol, set()).add(package)
                if member_list:
                    members.setdefault((package, symbol), set()).update(member_list)
    return HopApiIndex(
        status="partial" if missing_versions else "ok",
        versions=versions,
        missing_versions=missing_versions,
        packages=frozenset(packages),
        symbol_packages={symbol: frozenset(entry) for symbol, entry in symbol_packages.items()},
        members={pair: frozenset(names) for pair, names in members.items()},
    )


def load_hop_index(
    from_version: str,
    to_version: str,
    *,
    cache_dir: Path,
    token: str = "",
    client_for: "callable | None" = None,
    force: bool = False,
) -> HopApiIndex:
    """Index for a hop.

    ``ok`` when both versions load, ``partial`` when only one does (for example
    a ``to`` tag that does not exist yet), ``unavailable`` when none does.
    ``client_for(version)`` builds the per-version client; tests inject it.
    """
    versions: list[str] = []
    for version in (from_version, to_version):
        if version and version not in versions:
            versions.append(version)
    if not versions:
        return HopApiIndex.unavailable(())
    loaded: list[VersionIndex] = []
    missing: list[str] = []
    for version in versions:
        try:
            loaded.append(
                load_version_index(
                    version,
                    cache_dir=cache_dir,
                    token=token,
                    client=(client_for(version) if client_for else None),
                    force=force,
                )
            )
        except Exception as exc:  # network, GitHub, parse, or cache failure
            logger.warning("Angular API index for %s unavailable: %s", version, exc)
            missing.append(version)
    if not loaded:
        logger.warning("Angular API index unavailable for %s; entities stay unverified", versions)
        return HopApiIndex.unavailable(tuple(versions))
    return build_hop_index(tuple(versions), loaded, missing_versions=tuple(missing))
