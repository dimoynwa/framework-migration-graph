"""Extractor contract for the service scanner (spec 026).

Every later 026 spec adds one module and registers it here, so the scan loop
never changes:

- **Manifest readers** get a module root plus the manifest files in it and
  return ``dependencies`` / ``config`` / ``frameworks`` / ``diagnostics``
  fragments (spec2 npm, spec6 Maven + Gradle, spec8 Spring config).
- **Source extractors** get one file (path, bytes, module, ``test`` flag) and
  return per-file facts (``symbols``, ``members``, ``side_effect_imports``,
  ``wildcard_imports``, ``templates``, ``diagnostics`` and an export map for
  spec4). They are pure functions of the file content, so spec9 can cache them
  and run them in a process pool.
- **Post-passes** run on the collected facts (barrel resolution in spec4,
  own-package filtering in spec7).

A spec that is not implemented yet registers nothing, and its profile section
stays an empty list.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

# Bumped whenever a parser or the merge rules change: it is part of
# ``inputs_hash`` and invalidates the incremental cache (spec9). Spec1's test
# pins the value on purpose, so it only moves with a deliberate edit.
SCANNER_VERSION = "026.1"


# --- shared records --------------------------------------------------------


@dataclass(frozen=True)
class Diagnostic:
    """Something the scanner could not resolve. Never fails the scan."""

    kind: str
    file: str = ""
    line: int | None = None
    detail: str = ""


@dataclass(frozen=True)
class Location:
    """One import site (or member access, template token) of a fact."""

    file: str
    line: int
    test: bool = False


@dataclass(frozen=True)
class Usage:
    """One occurrence of an external key in one file.

    ``type_only`` is only meaningful for symbols (``import type``).
    """

    key: str
    file: str
    line: int
    test: bool = False
    type_only: bool = False


@dataclass(frozen=True)
class DependencyFact:
    """One declared dependency.

    ``kind`` separates the roles one artifact can have in a build (spec6):
    ``dependency`` | ``bom`` | ``parent`` | ``plugin``. The same key with a
    different ``scope`` or ``kind`` is a separate entry.
    """

    key: str
    name: str = ""
    range: str = ""
    version: str | None = None
    scope: str = "dependencies"
    module: str = "."
    kind: str = "dependency"
    # Where ``version`` came from: ``"lockfile"`` (installed), ``"range"`` (the
    # lowest version the declared range allows) or ``None`` (no version).
    version_source: str | None = None


@dataclass(frozen=True)
class ConfigFact:
    """One occurrence of a config key in one file.

    The same key in several files, modules or Spring profiles is one fact per
    occurrence (spec8 FR-8a), so a matcher can tell "set only in test" from
    "set in production". ``value`` is ``None`` when values are not stored
    (``--no-values``, spec8). The Spring-only fields stay ``None`` for npm,
    Maven and Gradle config.
    """

    key: str
    value: str | None = ""
    file: str = ""
    module: str = "."
    line: int | None = None
    raw_key: str | None = None
    profile: str | None = None  # Spring profile, spec8
    kind: str | None = None  # "application" | "bootstrap", spec8
    test: bool = False


@dataclass(frozen=True)
class FrameworkFact:
    """A detected framework version, per module."""

    name: str
    version: str = ""
    raw: str = ""
    source: str = ""


@dataclass(frozen=True)
class PathMap:
    """The effective TypeScript import map of one module (spec2 → spec3 / spec4).

    ``base_url`` and ``paths_dir`` are scan-root-relative, so resolution never
    depends on where the repo sits. ``paths`` keeps the targets as written
    (``{"@app/*": ("src/app/*",)}``); ``paths_dir`` is the directory they are
    relative to — ``baseUrl`` when the config sets one, else the directory of
    the config file that declared ``paths`` (TypeScript's own rule).
    """

    base_url: str = ""  # "" when the config sets none
    paths: dict[str, tuple[str, ...]] = field(default_factory=dict)
    paths_dir: str = "."
    tsconfig: str = ""  # module-relative file the map came from


@dataclass(frozen=True)
class ModuleEnv:
    """What the manifest readers learned about a module that source extractors need.

    Not part of the profile: the profile records facts about *use*, while these
    are the rules for deciding what counts as an import at all (spec3, spec4).
    ``own_packages`` are the names this repo is importable under; ``path_map``
    is the effective tsconfig import map.
    """

    module: str = "."
    own_packages: tuple[str, ...] = ()
    path_map: PathMap | None = None

    def owns(self, specifier: str) -> bool:
        """Whether a bare specifier names this repo's own code (``@demo/ui``)."""
        for package in self.own_packages:
            if specifier == package or specifier.startswith(package + "/"):
                return True
        return False


# --- manifest readers ------------------------------------------------------


@dataclass(frozen=True)
class ManifestFile:
    """One manifest of one module; ``read_text`` is lazy and best effort."""

    name: str  # relative to the module root
    kind: str  # classification, for example "package.json" / "pom.xml"
    path: Path

    def read_text(self) -> str | None:
        """UTF-8 text, or ``None`` when the file cannot be read."""
        try:
            return self.path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

    def read_bytes(self) -> bytes | None:
        try:
            return self.path.read_bytes()
        except OSError:
            return None


@dataclass(frozen=True)
class ManifestContext:
    """Everything a manifest reader gets for one module."""

    root: Path  # absolute module root
    module: str  # module path relative to the scan root ("." at the root)
    files: tuple[ManifestFile, ...]  # sorted by name
    # Absolute scan root, so a reader can follow a reference that leaves the
    # module but stays inside the repo (``tsconfig`` ``extends``, spec2).
    scan_root: Path | None = None

    def by_kind(self, *kinds: str) -> tuple[ManifestFile, ...]:
        return tuple(manifest for manifest in self.files if manifest.kind in kinds)

    def named(self, *names: str) -> ManifestFile | None:
        for manifest in self.files:
            if manifest.name in names:
                return manifest
        return None


@dataclass
class ManifestFacts:
    dependencies: list[DependencyFact] = field(default_factory=list)
    config: list[ConfigFact] = field(default_factory=list)
    frameworks: list[FrameworkFact] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    # ``modules[].angular_projects`` (spec2): the real project names of
    # ``angular.json``, while the config keys carry ``*`` in their place.
    angular_projects: list[str] = field(default_factory=list)
    # Names the module's own code is importable under (``package.json`` ``name``
    # plus npm workspace package names, spec2). Recorded in
    # ``modules[].own_packages`` and handed to source extractors, so spec3 can
    # tell an import of the repo's own code from an external package.
    own_packages: list[str] = field(default_factory=list)
    # The module's effective TypeScript path map (spec2), used by spec3 / spec4.
    path_map: PathMap | None = None


# --- source extractors -----------------------------------------------------


@dataclass(frozen=True)
class SourceContext:
    """One source file. Pure input, so spec9 can cache the result."""

    path: Path
    relative: str  # scan-root-relative, "/" separators
    module: str  # owning module path ("." at the root)
    language: (
        str  # discovery language tag: ts / tsx / js / jsx / mjs / cjs / html / java
    )
    test: bool = False
    data: bytes = b""
    # Own-package names and the tsconfig path map of the owning module (spec2),
    # so an extractor can tell an external import from the repo's own code.
    env: ModuleEnv = field(default_factory=ModuleEnv)


@dataclass
class FileFacts:
    """Per-file output of a source extractor (specs 3–8)."""

    symbols: list[Usage] = field(default_factory=list)
    members: list[Usage] = field(default_factory=list)
    side_effect_imports: list[Usage] = field(default_factory=list)
    wildcard_imports: list[Usage] = field(default_factory=list)
    templates: list[Usage] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    # Own-code imports (relative / paths aliases / workspace packages). Not
    # recorded as facts; spec4 follows them through barrels.
    own_imports: int = 0
    # ``{exported name: (specifier, original name)}`` plus ``*`` re-exports.
    export_map: dict[str, Any] = field(default_factory=dict)


class ManifestReader(Protocol):
    def __call__(self, context: ManifestContext) -> ManifestFacts: ...


class SourceExtractor(Protocol):
    def __call__(self, context: SourceContext) -> FileFacts: ...


class PostPass(Protocol):
    def __call__(self, facts: Any) -> None: ...


# --- registry --------------------------------------------------------------

_MANIFEST_READERS: dict[str, ManifestReader] = {}
_SOURCE_EXTRACTORS: dict[str, SourceExtractor] = {}
_POST_PASSES: list[PostPass] = []


def register_manifest_reader(kind: str, reader: ManifestReader) -> None:
    """Handle one manifest classification (``"package.json"``, ``"pom.xml"``, …).

    Registering one reader for several kinds is how a reader that needs the
    whole manifest family (npm: ``package.json`` + ``package-lock.json`` +
    ``angular.json`` + ``tsconfig*.json``) is called once per module with all of
    them in ``context.files``, instead of once per kind.
    """
    _MANIFEST_READERS[kind] = reader


def register_source_extractor(language: str, extractor: SourceExtractor) -> None:
    """Handle one discovery language tag (``"ts"``, ``"java"``, …)."""
    _SOURCE_EXTRACTORS[language] = extractor


def register_post_pass(post_pass: PostPass) -> None:
    """Run on the merged facts, before the profile is built."""
    _POST_PASSES.append(post_pass)


def manifest_readers() -> Mapping[str, ManifestReader]:
    return dict(_MANIFEST_READERS)


def source_extractors() -> Mapping[str, SourceExtractor]:
    return dict(_SOURCE_EXTRACTORS)


def post_passes() -> Sequence[PostPass]:
    return tuple(_POST_PASSES)


def reset_registry() -> None:
    """Test hook: forget every reader, extractor and post-pass."""
    _MANIFEST_READERS.clear()
    _SOURCE_EXTRACTORS.clear()
    _POST_PASSES.clear()


__all__ = [
    "SCANNER_VERSION",
    "ConfigFact",
    "DependencyFact",
    "Diagnostic",
    "FileFacts",
    "FrameworkFact",
    "Location",
    "ManifestContext",
    "ManifestFacts",
    "ManifestFile",
    "ManifestReader",
    "PostPass",
    "SourceContext",
    "SourceExtractor",
    "Usage",
    "manifest_readers",
    "post_passes",
    "register_manifest_reader",
    "register_post_pass",
    "register_source_extractor",
    "reset_registry",
    "source_extractors",
]
