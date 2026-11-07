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
  own-package filtering in spec7). They get a :class:`PostPassContext` — every
  file's facts plus how the repo resolves imports — and write through a
  :class:`FactSink`, so they add facts without owning the merge.

A spec that is not implemented yet registers nothing, and its profile section
stays an empty list.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Protocol, Sequence

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
    # Frameworks detected in this module (``angular``, spec2). A ``*.html`` file
    # is only a template when its module is Angular (spec5 FR-6).
    framework_names: tuple[str, ...] = ()
    path_map: PathMap | None = None
    # Entry names directly under ``compilerOptions.baseUrl`` (directories, and
    # files without their extension): ``'app/core/x'`` with ``baseUrl: "./src"``
    # is own code when ``app`` is one of them (spec3 FR-5). Computed by the scan
    # so the extractor stays a pure function of the file.
    base_url_roots: tuple[str, ...] = ()
    # npm dependency names declared anywhere in the repo. A declared ``events``
    # or ``buffer`` is an npm package, not a Node builtin; a declared name also
    # wins over a ``baseUrl`` entry of the same name.
    declared_dependencies: tuple[str, ...] = ()
    # External groupIds the repo's builds declare (spec6 → spec7). Spec7 records
    # a fully qualified usage such as ``org.springframework.X.y()`` that has no
    # import, and the groupId is how it tells an external package from the
    # service's own ``com.acme.…`` code — so the groupIds of the repo's own
    # modules are never in it, even when a module depends on a sibling.
    group_ids: tuple[str, ...] = ()

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
    # Where each of those names lives and which files its ``package.json``
    # nominates as entry points (spec4): how a bare specifier becomes a file.
    own_package_sources: list[OwnPackage] = field(default_factory=list)
    # The module's effective TypeScript path map (spec2), used by spec3 / spec4.
    path_map: PathMap | None = None
    # Directories a build file declares as modules: Maven ``<modules>`` and
    # Gradle ``include(…)`` (spec6 FR-3, FR-8). Discovery already treats every
    # directory holding a module-root manifest as one, so these matter only for
    # a declared module that has none of its own. Scan-root relative.
    module_roots: list[str] = field(default_factory=list)
    # Every *external* groupId this module's build declares (spec6 FR-8). Spec7
    # needs them to recognize a fully qualified usage (``org.x.Y.z()``) with no
    # import. The repo's own groupIds are not in it: see ``own_group_ids``.
    group_ids: list[str] = field(default_factory=list)
    # The groupIds this module and its in-repo parents publish under (Maven
    # ``<groupId>``, Gradle ``group = …``). ``scan()`` subtracts them repo-wide
    # from ``ModuleEnv.group_ids``, so a dependency on a sibling module
    # (``com.acme:lib``) never makes the service's own code look external.
    own_group_ids: list[str] = field(default_factory=list)


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


@dataclass(frozen=True)
class ExportBinding:
    """Where a file's exported name really comes from (spec3 → spec4).

    ``specifier`` is the module the name is re-exported from — ``""`` when the
    file declares the name itself. ``original`` is the name it has there, so a
    rename chain (``export { inject as di } from '@angular/core'``) can be
    followed to the original key.
    """

    specifier: str = ""
    original: str = ""


@dataclass(frozen=True)
class OwnImport:
    """One import of the repo's own code (spec3) — spec4's resolution input.

    Own-code imports are not recorded as facts: they become facts only when a
    barrel chain ends at an external package. Until then the import site, the
    local names it binds and the specifier are all kept, because the external
    key must be recorded at this file and line (spec4 FR-5).
    """

    #: Where the import happened: ``relative`` and ``line`` are the import site.
    relative: str
    line: int
    test: bool = False
    #: The specifier as written (``./app.component``, ``@app/core``).
    specifier: str = ""
    #: A relative specifier (``./x``, ``../y``) rather than an alias / package.
    is_relative: bool = True
    #: ``{local name: imported name}``; ``*`` is the namespace import, and an
    #: empty imported name means a side-effect import.
    named: dict[str, str] = field(default_factory=dict)
    #: Local name of a default import, if any.
    default: str = ""
    #: Local name of a ``import * as ns``, if any.
    namespace: str = ""
    #: True when the import is ``import type`` (or every specifier is ``type``).
    type_only: bool = False
    #: Local names imported with an inline ``type`` (``import { type T, v }``).
    type_names: frozenset[str] = frozenset()


@dataclass(frozen=True)
class OwnMember:
    """A member access on a name bound to own code (spec3 → spec4).

    ``core.inject(…)`` and ``A.b`` are recorded for own-code bindings too, so
    spec4 can report them once the barrel chain reaches an external package:
    the local name is resolved to its original external symbol, which gives
    ``npm:<pkg>#<symbol>.<member>`` (or ``npm:<pkg>#<member>`` through a
    namespace). A decorator's option keys arrive the same way, with ``symbol``
    set for ``@core.Component({…})``.
    """

    relative: str
    line: int
    test: bool = False
    #: The local identifier as written in this file (``di``, ``core``).
    local: str = ""
    #: The first member segment (``inject``, ``selector``).
    member: str = ""
    #: The symbol after a namespace local (``Component`` in ``@core.Component``).
    symbol: str = ""


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
    # ``{exported name: ExportBinding}`` plus ``export *`` specifiers: the
    # file's export map, which spec4 walks to reach an external package.
    export_map: dict[str, "ExportBinding"] = field(default_factory=dict)
    # ``export * from '<specifier>'`` targets, in source order.
    star_exports: list[str] = field(default_factory=list)
    # ``export * as ns from '<specifier>'``: namespaced re-exports.
    namespace_exports: dict[str, str] = field(default_factory=dict)
    # Local names the file declares itself (class / function / const). Spec4
    # drops a barrel name that ends in one of these: that is own code.
    local_declarations: set[str] = field(default_factory=set)
    # The own-code imports this file makes, with their bound local names.
    own_import_bindings: list[OwnImport] = field(default_factory=list)
    # Member accesses (and decorator option keys) on own-code bindings, which
    # spec4 attributes once the chain reaches an external package.
    own_member_bindings: list[OwnMember] = field(default_factory=list)


@dataclass(frozen=True)
class OwnPackage:
    """An own package name and where its sources live (spec2 → spec4).

    A workspace package is imported under its ``package.json`` ``name`` but its
    files live in a directory; ``entries`` are that manifest's ``main`` /
    ``module`` / ``types`` and ``exports["."]`` values as written, which is what
    spec4 tries before falling back to ``index.*`` in ``directory``. Both paths
    are scan-root-relative, so resolution never depends on where the repo sits.
    """

    name: str
    directory: str = "."
    entries: tuple[str, ...] = ()
    #: ``exports`` subpaths other than ``"."``, as written:
    #: ``{"./testing": ("./src/testing.ts",), "./*": ("./src/*.ts",)}``.
    subpath_exports: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class ResolutionEnv:
    """How the repo's own imports resolve to files (spec4).

    ``module_of`` says which module owns each source file and
    ``environments`` carries that module's effective path map, ``baseUrl``
    entries, own packages and declared dependencies (spec2 → spec3).
    ``packages`` maps an own package name to where its sources live. The set of
    resolvable files is ``PostPassContext.files``: a target the scanner did not
    parse is not resolvable. Path-map directories are scan-relative, so nothing
    here depends on the absolute location of the repo.
    """

    module_of: Mapping[str, str] = field(default_factory=dict)
    environments: Mapping[str, ModuleEnv] = field(default_factory=dict)
    packages: Mapping[str, "OwnPackage"] = field(default_factory=dict)


@dataclass(frozen=True)
class PostPassContext:
    """What a post-pass sees: the per-file facts plus how imports resolve.

    ``files`` keeps every file's :class:`FileFacts` by scan-relative path, which
    is the export map spec4 follows. A post-pass returns a :class:`FileFacts`
    fragment (facts at the *original* import site) and the scan merges it like
    any extractor's output.
    """

    root: Path
    files: Mapping[str, "FileFacts"] = field(default_factory=dict)
    resolution: ResolutionEnv = field(default_factory=ResolutionEnv)


class ManifestReader(Protocol):
    def __call__(self, context: ManifestContext) -> ManifestFacts: ...


class SourceExtractor(Protocol):
    def __call__(self, context: SourceContext) -> FileFacts: ...


class PostPass(Protocol):
    def __call__(self, context: PostPassContext) -> FileFacts | None: ...


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
    "ExportBinding",
    "FileFacts",
    "FrameworkFact",
    "Location",
    "ManifestContext",
    "ManifestFacts",
    "ManifestFile",
    "ManifestReader",
    "ModuleEnv",
    "OwnImport",
    "OwnMember",
    "OwnPackage",
    "PathMap",
    "PostPass",
    "PostPassContext",
    "ResolutionEnv",
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
