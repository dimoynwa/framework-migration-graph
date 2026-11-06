"""npm manifests: ``package.json``, ``package-lock.json``, ``angular.json``,
``tsconfig*.json`` (spec 026.2).

One reader handles all four kinds, because they answer one question together:
what does this npm module declare, install and compile with? It is registered
once and therefore called once per module with every npm manifest of that
module (spec1 extractor contract).

What it records
---------------

``package.json``
    ``dependencies`` / ``devDependencies`` / ``peerDependencies`` /
    ``optionalDependencies`` as :class:`DependencyFact` with the range as
    written and the **installed** version from ``package-lock.json`` when the
    lockfile knows it. Config keys of ``engines``, ``type``, ``browserslist``,
    ``overrides``, ``resolutions`` and ``workspaces`` become
    ``cfg:package.json#<dotted path>``. The package's own ``name`` and its
    workspace package names are collected as **own packages**, so spec3 can
    tell "import of our own code" from "import of an external package".

``package-lock.json``
    Only versions are read: ``packages["node_modules/<name>"].version``,
    preferring the module's own ``node_modules`` over the hoisted one. The
    lockfile is the module's own, else the nearest one in a parent directory
    (an npm workspace root). Lockfile v1 ``dependencies`` is a fallback.
    ``dependencies[].version_source`` says ``lockfile`` or ``range``.

``angular.json``
    Every scalar leaf becomes ``cfg:angular.json#<dotted path>`` with the
    project name replaced by ``*``, so one key describes every project:
    ``cfg:angular.json#projects.*.architect.build.builder``. The real project
    names land in ``modules[].angular_projects``.

``tsconfig*.json``
    JSON with comments and trailing commas is accepted. ``extends`` is followed
    inside the repo (into ``node_modules`` or outside the repo is a diagnostic,
    not followed), giving the **effective** config: scalar leaves of
    ``compilerOptions`` / ``angularCompilerOptions`` become
    ``cfg:tsconfig.json#<dotted path>`` — one file name, because that is the
    key 025 canonicalizes rules to — and ``paths`` / ``baseUrl`` are stored on
    the module as the effective path map for import resolution (spec3, spec4).

    A module usually has several configs (``tsconfig.json``, ``.app``, ``.spec``)
    and they all map to that one key, so each option is emitted once. The config
    ``angular.json`` names as the build's ``tsConfig`` supplies the value: that
    is the compilation the application actually has, not the test one. Values
    inherited through ``extends`` keep the ``file`` that declared them, which is
    also the base a relative ``baseUrl`` resolves against.

Nothing here fails a scan: a broken manifest is a diagnostic and the other
manifests of the module are still read.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Iterator

from migration_keys.keys import cfg_key, npm_key

from migration_planner.scanner.contract import (
    ConfigFact,
    DependencyFact,
    Diagnostic,
    FrameworkFact,
    ManifestContext,
    ManifestFacts,
    ManifestFile,
    OwnPackage,
    PathMap,
)

# The manifest classifications this reader handles. One function, one call per
# module, whichever subset of these the module has.
MANIFEST_KINDS: tuple[str, ...] = (
    "package.json",
    "package-lock.json",
    "angular.json",
    "tsconfig.json",
)

DEPENDENCY_SCOPES: tuple[str, ...] = (
    "dependencies",
    "devDependencies",
    "peerDependencies",
    "optionalDependencies",
)

# The ``package.json`` subtrees worth a config key (FR-4). ``dependencies.*``
# is not here: it is a dependency fact, not a config key.
PACKAGE_CONFIG_ROOTS: tuple[str, ...] = (
    "engines",
    "type",
    "browserslist",
    "overrides",
    "resolutions",
    "workspaces",
)

ANGULAR_PACKAGE = "@angular/core"
ANGULAR_PROJECT_WILDCARD = "*"

# Config values are for matching, not for reading: a long browser list or a
# lockfile excerpt would only bloat the profile (FR-4).
MAX_CONFIG_VALUE_CHARS = 200

# Every tsconfig variant canonicalizes to one file name (025 FR-2.6): a rule
# says ``cfg:tsconfig.json#compilerOptions.strict``, not the app config's name.
TSCONFIG_KEY_FILE = "tsconfig.json"

# --- version ranges --------------------------------------------------------

# ``^19.2.0``, ``~19``, ``v19.2.0``, ``19.2.0-rc.1``: an optional prefix, up to
# three numeric parts, an optional prerelease / build suffix.
_VERSION_RE = re.compile(
    r"^[v=\s]*(\d+|[xX*])(?:\.(\d+|[xX*]))?(?:\.(\d+|[xX*]))?"
    r"(?:([-+][0-9A-Za-z.\-+]+))?$"
)

# A range that names no floor at all: any installed version satisfies it, so
# there is nothing to normalize (and nothing to report).
_WILDCARD_RANGES: frozenset[str] = frozenset({"", "*", "x", "X", "latest", "next", "-"})

# Local / alias / VCS specifiers are not registry ranges (``workspace:*`` in a
# monorepo, ``file:../core``, an npm alias): the resolved version is genuinely
# unknown, and that is normal, not a diagnostic.
_LOCAL_SPECIFIER_PREFIXES: tuple[str, ...] = (
    "file:",
    "link:",
    "portal:",
    "workspace:",
    "npm:",
    "git:",
    "git+",
    "github:",
    "bitbucket:",
    "gitlab:",
    "http:",
    "https:",
)

_UNSUPPORTED = "unsupported"
_WILDCARD = "wildcard"


def normalize_range(spec: str) -> tuple[str | None, str]:
    """``(lowest version satisfying the range, reason)``; FR-4 / AC-8.

    The normalized version is the **lowest** version the range allows, because
    the profile answers "which version could this service be on" — a service
    with ``^19.2.0`` may be on any 19.x. ``reason`` is ``""`` when a version was
    produced, ``"wildcard"`` when the range has no floor (``*``,
    ``workspace:*``) and ``"unsupported"`` when the scanner does not understand
    the range, which the caller turns into a diagnostic.

    >>> normalize_range("^19.2.0")
    ('19.2.0', '')
    >>> normalize_range("~1.4")
    ('1.4.0', '')
    >>> normalize_range(">=18")
    ('18.0.0', '')
    >>> normalize_range("19.x")
    ('19.0.0', '')
    >>> normalize_range("workspace:*")
    (None, 'wildcard')
    >>> normalize_range("not a range")
    (None, 'unsupported')
    """
    text = (spec or "").strip()
    if text in _WILDCARD_RANGES or text.lower() in _WILDCARD_RANGES:
        return None, _WILDCARD
    if text.lower().startswith(_LOCAL_SPECIFIER_PREFIXES):
        return None, _WILDCARD

    bounds: list[str] = []
    for alternative in text.split("||"):
        bound, reason = _alternative_lower_bound(alternative)
        if reason == _UNSUPPORTED:
            return None, _UNSUPPORTED
        if bound is not None:
            bounds.append(bound)
    if not bounds:
        return None, _WILDCARD
    return _lowest(bounds), ""


def _alternative_lower_bound(alternative: str) -> tuple[str | None, str]:
    """The lowest version one ``||`` alternative allows, ``(None, reason)`` if unbounded."""
    text = alternative.strip()
    if not text:
        return None, _WILDCARD
    # Hyphen range ``1.2.3 - 2.0.0``: the lower end is the floor.
    if " - " in text:
        return _alternative_lower_bound(text.split(" - ", 1)[0])

    tokens = text.split()
    if len(tokens) > 1:  # comparator set, e.g. ``>=1.2.3 <2``
        bounds: list[str] = []
        for token in tokens:
            bound, reason = _comparator_bound(token)
            if reason == _UNSUPPORTED:
                return None, _UNSUPPORTED
            if bound is not None:
                bounds.append(bound)
        return (max(bounds, key=_version_key), "") if bounds else (None, _WILDCARD)
    return _comparator_bound(tokens[0])


def _comparator_bound(token: str) -> tuple[str | None, str]:
    """The floor of one comparator: ``^1.2``, ``~1.2``, ``>=1``, ``<2``, ``1.2.3``."""
    text = token.strip()
    if text in _WILDCARD_RANGES:
        return None, _WILDCARD
    # Longest operator first, so ``>=`` beats ``>`` and ``~>`` beats ``~``.
    for prefix in (">=", "<=", "~>", ">", "<", "=", "^", "~"):
        if text.startswith(prefix):
            return _prefixed_bound(prefix, text[len(prefix) :].strip())
    parsed = _parse_version(text)
    if parsed is None:
        return None, _UNSUPPORTED
    return parsed, ""


def _prefixed_bound(prefix: str, text: str) -> tuple[str | None, str]:
    parsed = _parse_version(text)
    if parsed is None:
        return None, _UNSUPPORTED
    if prefix in ("<", "<="):
        # No floor: any version below the cap satisfies it.
        return None, _WILDCARD
    if prefix == ">":
        # npm semantics: ``>1`` is ``>=2.0.0``, ``>1.2`` is ``>=1.3.0`` and only a
        # full ``>1.2.3`` moves to the next patch.
        major, minor, patch, suffix = _split(parsed)
        if suffix:
            return parsed, ""
        given = _given_parts(text)
        if given == 1:
            return f"{major + 1}.0.0", ""
        if given == 2:
            return f"{major}.{minor + 1}.0", ""
        return f"{major}.{minor}.{patch + 1}", ""
    # ``^``, ``~``, ``~>``, ``>=`` and ``=`` all start at the written version:
    # the profile wants the lowest version the range allows, not its ceiling.
    return parsed, ""


def _parse_version(text: str) -> str | None:
    """``19`` / ``19.2`` / ``19.2.0`` / ``19.x`` → padded ``19.2.0``, else ``None``."""
    match = _VERSION_RE.match(text.strip())
    if match is None:
        return None
    major, minor, patch, suffix = match.groups()
    parts = [_numeric(part) for part in (major, minor, patch)]
    if parts[0] is None:
        return None
    resolved = [part if part is not None else 0 for part in parts]
    return ".".join(str(part) for part in resolved) + (suffix or "")


def _given_parts(text: str) -> int:
    """How many leading numeric parts a version names (``1.2.x`` → 2, ``1`` → 1)."""
    match = _VERSION_RE.match(text.strip())
    if match is None:
        return 3
    count = 0
    for part in match.groups()[:3]:
        if part is None or not part.isdigit():
            break
        count += 1
    return count


def _numeric(part: str | None) -> int | None:
    if part is None or part in ("x", "X", "*"):
        return 0
    return int(part)


def _split(version: str) -> tuple[int, int, int, str]:
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)(.*)$", version)
    assert match is not None, version
    return int(match.group(1)), int(match.group(2)), int(match.group(3)), match.group(4)


def _version_key(version: str) -> tuple[int, int, int, str]:
    """Sort key for versions: the numeric parts, then any prerelease suffix."""
    major, minor, patch, suffix = _split(version)
    return major, minor, patch, suffix


def _lowest(bounds: list[str]) -> str:
    return min(bounds, key=_version_key)


# --- entry point -----------------------------------------------------------


def read_npm_manifests(context: ManifestContext) -> ManifestFacts:
    """Every npm fact of one module: dependencies, config, angular, path map."""
    facts = ManifestFacts()

    package_file = context.named("package.json")
    package = (
        _load_json(package_file, context, facts, jsonc=False)
        if package_file is not None
        else None
    )
    lock_file, lock_data = _load_lockfile(context, facts)
    versions = _Versions(lock_data, lock_file, context)

    declared: dict[str, str] = {}
    if package is not None and package_file is not None:
        _read_package_json(context, package, package_file, versions, facts, declared)
    preferred_tsconfigs = _read_angular_json(context, facts)
    _read_tsconfigs(context, facts, preferred_tsconfigs)
    return facts


# --- package.json ----------------------------------------------------------


def _read_package_json(
    context: ManifestContext,
    package: dict[str, Any],
    package_file: ManifestFile,
    versions: "_Versions",
    facts: ManifestFacts,
    declared: dict[str, str],
) -> None:
    file = _scan_relative(context, package_file.name)

    name = package.get("name")
    if isinstance(name, str) and name.strip():
        facts.own_packages.append(name.strip())
        facts.own_package_sources.append(
            OwnPackage(
                name=name.strip(),
                directory=_scan_path(context, context.root),
                entries=_package_entries(package),
                subpath_exports=_subpath_exports(package),
            )
        )
    for workspace in _workspace_packages(package, context):
        facts.own_packages.append(workspace.name)
        facts.own_package_sources.append(workspace)

    for scope in DEPENDENCY_SCOPES:
        block = package.get(scope)
        if not isinstance(block, dict):
            continue
        for dependency_name, spec in block.items():
            if not isinstance(dependency_name, str) or not isinstance(spec, str):
                facts.diagnostics.append(
                    Diagnostic(
                        kind="invalid_dependency",
                        file=file,
                        detail=f"{scope}.{dependency_name}",
                    )
                )
                continue
            declared.setdefault(dependency_name, spec)
            version = versions.version(dependency_name)
            version_source: str | None = "lockfile" if version is not None else None
            if version is None:
                version, reason = normalize_range(spec)
                version_source = "range" if version is not None else None
                if reason == _UNSUPPORTED:
                    facts.diagnostics.append(
                        Diagnostic(
                            kind="unsupported_range",
                            file=file,
                            detail=f"{scope}.{dependency_name} = {spec}",
                        )
                    )
            facts.dependencies.append(
                DependencyFact(
                    key=npm_key(dependency_name),
                    name=dependency_name,
                    range=spec,
                    version=version,
                    scope=scope,
                    module=context.module,
                    kind="dependency",
                    version_source=version_source,
                )
            )

    for root_key in PACKAGE_CONFIG_ROOTS:
        if root_key not in package:
            continue
        for dotted, value in _scalar_leaves(package[root_key], (root_key,)):
            facts.config.append(
                ConfigFact(
                    key=cfg_key("package.json", dotted),
                    value=_truncate(value),
                    file=file,
                    module=context.module,
                )
            )

    _detect_angular(context, declared, versions, facts)


def _detect_angular(
    context: ManifestContext,
    declared: dict[str, str],
    versions: "_Versions",
    facts: ManifestFacts,
) -> None:
    """Angular version: the lockfile's installed version, else the declared range.

    The lockfile wins because that is what the build actually uses — a
    ``package.json`` range is a wish, ``npm ls @angular/core`` is the answer
    (FR-3, AC-8). With no lockfile the range is kept as written in ``raw`` and
    normalized to the lowest version it allows.

    Only a module whose ``package.json`` declares ``@angular/core`` (any scope)
    is an Angular module. A hoisted ``node_modules/@angular/core`` in a shared
    workspace lockfile says nothing about a sibling ``server`` package that
    never imports Angular, so the lockfile only supplies the exact version.
    """
    raw = declared.get(ANGULAR_PACKAGE, "")
    if not raw:
        return  # not an Angular module
    installed = versions.version(ANGULAR_PACKAGE)
    if installed is not None:
        facts.frameworks.append(
            FrameworkFact(
                name="angular",
                version=installed,
                raw=raw,
                source="package-lock.json",
            )
        )
        return
    version, reason = normalize_range(raw)
    if version is None and reason == _UNSUPPORTED:
        facts.diagnostics.append(
            Diagnostic(
                kind="unsupported_range",
                file=_scan_relative(context, "package.json"),
                detail=f"{ANGULAR_PACKAGE} = {raw}",
            )
        )
    facts.frameworks.append(
        FrameworkFact(
            name="angular",
            version=version or "",
            raw=raw,
            source="package.json",
        )
    )


def _workspace_packages(
    package: dict[str, Any], context: ManifestContext
) -> list[OwnPackage]:
    """The npm workspaces declared here, as importable packages (FR-4, AC-8.2).

    Resolved by globbing the workspace patterns against the module root and
    reading each matched ``package.json`` — the point of the list is the
    importable name (``@demo/ui``), not the directory. ``directory`` and
    ``entries`` are what spec4 needs to resolve ``@demo/ui`` to a real file.
    """
    workspaces = package.get("workspaces")
    patterns: list[str] = []
    if isinstance(workspaces, list):
        patterns = [item for item in workspaces if isinstance(item, str)]
    elif isinstance(workspaces, dict):
        listed = workspaces.get("packages")
        if isinstance(listed, list):
            patterns = [item for item in listed if isinstance(item, str)]

    found: list[OwnPackage] = []
    for pattern in patterns:
        if not pattern or pattern.startswith("!") or pattern.startswith("/"):
            continue
        if ".." in PurePosixPath(pattern).parts:
            continue
        for directory in sorted(context.root.glob(pattern)):
            if not directory.is_dir():
                continue
            data = _package_json(directory / "package.json")
            name = data.get("name") if data is not None else None
            if not isinstance(name, str) or not name.strip():
                continue
            found.append(
                OwnPackage(
                    name=name.strip(),
                    directory=_scan_path(context, directory),
                    entries=_package_entries(data),
                    subpath_exports=_subpath_exports(data),
                )
            )
    return found


def _package_entries(package: dict[str, Any]) -> tuple[str, ...]:
    """The files a ``package.json`` nominates for ``import '<name>'`` (spec4 FR-5).

    In Node / TypeScript order: ``exports["."]`` first (the modern, authoritative
    field), then ``types``, ``module`` and ``main``. ``exports["."]`` may be a
    string or a condition object; a condition object's string values are all
    kept, ``types`` / ``require`` / ``import`` / ``default`` before the rest, so
    a ``.d.ts`` and the runtime file are both probed.
    """
    entries: list[str] = []
    exports = package.get("exports")
    if isinstance(exports, str):
        entries.append(exports)
    elif isinstance(exports, dict):
        root = exports.get(".")
        entries.extend(_export_targets(root))
    for field_name in ("types", "typings", "module", "main"):
        value = package.get(field_name)
        if isinstance(value, str) and value.strip():
            entries.append(value.strip())
    return tuple(dict.fromkeys(entries))


def _subpath_exports(package: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    """``exports`` subpaths other than ``"."`` (``"./testing"``, ``"./*"``), spec4 FR-5."""
    exports = package.get("exports")
    if not isinstance(exports, dict):
        return {}
    found: dict[str, tuple[str, ...]] = {}
    for key, value in exports.items():
        if not isinstance(key, str) or key == "." or not key.startswith("./"):
            continue
        targets = tuple(dict.fromkeys(_export_targets(value)))
        if targets:
            found[key] = targets
    return found


_CONDITION_ORDER: tuple[str, ...] = ("types", "import", "node", "require", "default")


def _package_json(path: Path) -> dict[str, Any] | None:
    """A workspace package's ``package.json``, best effort (spec4 follows it)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _export_targets(value: Any) -> list[str]:
    """String targets of an ``exports["."]`` entry, likely conditions first."""
    if isinstance(value, str):
        return [value]
    if not isinstance(value, dict):
        return []
    targets: list[str] = []
    for condition in _CONDITION_ORDER:
        if condition in value:
            targets.extend(_export_targets(value[condition]))
    for condition, inner in value.items():
        if condition not in _CONDITION_ORDER:
            targets.extend(_export_targets(inner))
    return targets


# --- package-lock.json -----------------------------------------------------


def _load_lockfile(
    context: ManifestContext, facts: ManifestFacts
) -> tuple[ManifestFile | None, dict[str, Any] | None]:
    """The module's own lockfile, else the nearest one in a parent directory.

    An npm workspace keeps one lockfile at the workspace root, which need not
    be the scan root (``frontend/package-lock.json`` for
    ``frontend/packages/ui``), so the search walks up from the module to the
    scan root and takes the first lockfile it meets. ``ManifestFile.name`` is
    the file's scan-relative path, so a diagnostic points at the file that is
    actually broken.
    """
    own = context.named("package-lock.json")
    if own is not None:
        return own, _load_json(own, context, facts, jsonc=False)
    if context.scan_root is None or context.module == ".":
        return None, None
    scan_root = context.scan_root.resolve()
    parts = PurePosixPath(context.module).parts
    for depth in range(len(parts) - 1, -1, -1):
        directory = scan_root.joinpath(*parts[:depth])
        candidate = directory / "package-lock.json"
        if not candidate.is_file():
            continue
        relative = candidate.relative_to(scan_root).as_posix()
        manifest = ManifestFile(name=relative, kind="package-lock.json", path=candidate)
        return manifest, _load_json(manifest, context, facts, jsonc=False)
    return None, None


class _Versions:
    """Installed npm versions of one module, from one lockfile.

    ``packages`` is looked up by ``node_modules`` path, so the module's own
    install wins over a hoisted one at the repo root: a workspace package may
    depend on a different ``rxjs`` than the root.
    """

    def __init__(
        self,
        data: dict[str, Any] | None,
        lock_file: ManifestFile | None,
        context: ManifestContext,
    ) -> None:
        packages = (data or {}).get("packages")
        self._packages: dict[str, Any] = packages if isinstance(packages, dict) else {}
        dependencies = (data or {}).get("dependencies")
        self._dependencies: dict[str, Any] = (
            dependencies if isinstance(dependencies, dict) else {}
        )
        self._prefix = _lock_prefix(lock_file, context)

    def version(self, name: str) -> str | None:
        prefixes = [self._prefix]
        if self._prefix:
            prefixes.append("")  # hoisted to the repo root
        for prefix in prefixes:
            entry = self._packages.get(f"{prefix}node_modules/{name}")
            if isinstance(entry, dict) and isinstance(entry.get("version"), str):
                return str(entry["version"])
        entry = self._dependencies.get(name)
        if isinstance(entry, dict) and isinstance(entry.get("version"), str):
            return str(entry["version"])  # lockfileVersion 1
        return None


def _lock_prefix(lock_file: ManifestFile | None, context: ManifestContext) -> str:
    """Module directory relative to the lockfile's directory, with a trailing ``/``."""
    if lock_file is None:
        return ""
    lock_dir = lock_file.path.parent.resolve()
    module_dir = context.scan_root or context.root
    module_dir = (module_dir / context.module).resolve()
    try:
        relative = module_dir.relative_to(lock_dir).as_posix()
    except ValueError:
        return ""
    return "" if relative == "." else relative + "/"


# --- angular.json ----------------------------------------------------------


def _read_angular_json(context: ManifestContext, facts: ManifestFacts) -> list[str]:
    """``angular.json`` config keys, plus the tsconfigs its projects compile with.

    The returned names are module-relative (``tsconfig.app.json``) and come from
    ``…architect.<target>.options.tsConfig``: those are the configs that decide
    what the built application sees, so their options get the plain
    ``tsconfig.json`` config keys and their path map is the module's (FR-4).
    """
    angular_file = context.named("angular.json")
    if angular_file is None:
        return []
    data = _load_json(angular_file, context, facts, jsonc=True)
    if data is None:
        return []
    file = _scan_relative(context, angular_file.name)

    preferred: list[str] = []
    projects = data.get("projects")
    if isinstance(projects, dict):
        facts.angular_projects.extend(
            sorted(name for name in projects if isinstance(name, str))
        )
        for project in projects.values():
            if not isinstance(project, dict):
                continue
            architect = project.get("architect")
            if not isinstance(architect, dict):
                continue
            for target in architect.values():
                if not isinstance(target, dict):
                    continue
                options = target.get("options")
                name = options.get("tsConfig") if isinstance(options, dict) else None
                if isinstance(name, str) and name not in preferred:
                    preferred.append(name)

    for dotted, value in _scalar_leaves(data):
        parts = dotted.split(".")
        if parts[0] == "projects" and len(parts) > 1:
            # One key describes every project, so a rule written once matches a
            # repo with any number of them (FR-4).
            parts[1] = ANGULAR_PROJECT_WILDCARD
        facts.config.append(
            ConfigFact(
                key=cfg_key("angular.json", ".".join(parts)),
                value=_truncate(value),
                file=file,
                module=context.module,
            )
        )
    return preferred


# --- tsconfig*.json --------------------------------------------------------


@dataclass
class _EffectiveConfig:
    """A tsconfig after ``extends``, plus which file set each value.

    ``origins`` maps ``"<group>.<option>"`` to the file that declared it, so a
    config key can say where its value really came from. TypeScript resolves
    ``baseUrl`` and ``paths`` against that file, not against the leaf config.
    """

    data: dict[str, Any] = field(default_factory=dict)
    origins: dict[str, Path] = field(default_factory=dict)


def _read_tsconfigs(
    context: ManifestContext,
    facts: ManifestFacts,
    preferred: list[str] | None = None,
) -> None:
    """One effective tsconfig per module: config keys and the import path map."""
    candidates = sorted(
        context.by_kind("tsconfig.json"),
        key=lambda manifest: (
            # angular.json targets in declaration order (build before test),
            # then the plain tsconfig.json, then the rest by name.
            (preferred or []).index(manifest.name)
            if manifest.name in (preferred or ())
            else len(preferred or ()),
            manifest.name != "tsconfig.json",
            manifest.name,
        ),
    )
    if not candidates:
        return

    resolved: list[tuple[ManifestFile, _EffectiveConfig]] = []
    for manifest in candidates:
        effective = _effective_config(manifest, context, facts, seen=frozenset())
        if effective is not None:
            resolved.append((manifest, effective))
    if not resolved:
        return

    # The reference config carries the import map the built application uses:
    # the one ``angular.json`` names, else the one that declares ``paths``, else
    # plain ``tsconfig.json`` — every other config extends it.
    best_file, best = resolved[0]
    for manifest, effective in resolved[1:]:
        if _tsconfig_score(effective) > _tsconfig_score(best):
            best_file, best = manifest, effective

    _emit_config_keys(context, facts, resolved)

    path_map = _path_map(best, best_file, context)
    if path_map is not None:
        facts.path_map = path_map


def _emit_config_keys(
    context: ManifestContext,
    facts: ManifestFacts,
    resolved: list[tuple[ManifestFile, _EffectiveConfig]],
) -> None:
    """One entry per option of the module's compilation config (FR-4).

    A module usually has ``tsconfig.json`` plus ``tsconfig.app.json`` and
    ``tsconfig.spec.json``, and every one of them canonicalizes to the same key
    file — a rule says ``cfg:tsconfig.json#compilerOptions.strict``. Emitting per
    variant would give one key several values with no way to tell which
    compilation it belongs to, so each option is emitted once: the first config
    that sets it wins, and ``resolved`` lists the config that compiles the app
    first. Suppression is by option name, so an override that sets ``types: []``
    also suppresses the ``types.0`` inherited from the base config. ``file`` says
    which config the value came from.
    """
    seen_options: set[tuple[str, str]] = set()
    seen_leaves: set[str] = set()
    for manifest, effective in resolved:
        fallback = _scan_relative(context, manifest.name)
        for group in ("compilerOptions", "angularCompilerOptions"):
            block = effective.data.get(group)
            if not isinstance(block, dict):
                continue
            for option in block:
                if not isinstance(option, str):
                    continue
                if (group, option) in seen_options:
                    continue
                seen_options.add((group, option))
                origin = effective.origins.get(f"{group}.{option}")
                file = _scan_path(context, origin) if origin is not None else fallback
                for dotted, value in _scalar_leaves(block[option], (group, option)):
                    if dotted in seen_leaves:
                        continue
                    seen_leaves.add(dotted)
                    facts.config.append(
                        ConfigFact(
                            key=cfg_key(TSCONFIG_KEY_FILE, dotted),
                            value=_truncate(value),
                            file=file,
                            module=context.module,
                        )
                    )


def _tsconfig_score(effective: _EffectiveConfig) -> tuple[int, int]:
    options = effective.data.get("compilerOptions")
    options = options if isinstance(options, dict) else {}
    return (1 if options.get("paths") else 0, 1 if options.get("baseUrl") else 0)


def _path_map(
    effective: _EffectiveConfig, manifest: ManifestFile, context: ManifestContext
) -> PathMap | None:
    root = (context.scan_root or context.root).resolve()
    options = effective.data.get("compilerOptions")
    options = options if isinstance(options, dict) else {}

    base_url = options.get("baseUrl")
    base_dir = ""
    if isinstance(base_url, str) and base_url.strip():
        origin = effective.origins.get("compilerOptions.baseUrl", manifest.path)
        base_dir = _posix_rel(origin.parent / base_url.strip(), root)

    raw_paths = options.get("paths")
    paths: dict[str, tuple[str, ...]] = {}
    if isinstance(raw_paths, dict):
        for pattern, targets in raw_paths.items():
            if not isinstance(pattern, str):
                continue
            if isinstance(targets, str):
                paths[pattern] = (targets,)
            elif isinstance(targets, list):
                kept = tuple(item for item in targets if isinstance(item, str))
                if kept:
                    paths[pattern] = kept

    if not base_dir and not paths:
        return None
    if base_dir:
        paths_dir = base_dir
    else:
        origin = effective.origins.get("compilerOptions.paths", manifest.path)
        paths_dir = _posix_rel(origin.parent, root)
    return PathMap(
        base_url=base_dir,
        paths=paths,
        paths_dir=paths_dir,
        tsconfig=manifest.name,
    )


def _effective_config(
    manifest: ManifestFile,
    context: ManifestContext,
    facts: ManifestFacts,
    seen: frozenset[Path],
) -> _EffectiveConfig | None:
    """The config after following ``extends`` inside the repo (FR-4).

    TypeScript resolves ``baseUrl`` and ``paths`` against the file that declares
    them, not against the leaf config, so both remember their declaring file.
    """
    resolved_path = manifest.path.resolve()
    if resolved_path in seen:
        facts.diagnostics.append(
            Diagnostic(
                kind="tsconfig_cycle",
                file=_scan_relative(context, manifest.name),
                detail=str(manifest.name),
            )
        )
        return None

    data = _load_json(manifest, context, facts, jsonc=True)
    if data is None:
        return None

    merged = _EffectiveConfig()
    for reference in _extends_list(data.get("extends")):
        parent_path = _resolve_extends(reference, manifest, context, facts)
        if parent_path is None:
            continue
        parent = _effective_config(
            ManifestFile(
                name=_module_relative(context, parent_path),
                kind="tsconfig.json",
                path=parent_path,
            ),
            context,
            facts,
            seen | {resolved_path},
        )
        if parent is not None:
            # A later ``extends`` entry wins over an earlier one, as in TypeScript.
            merged = _merge(merged, parent)

    own = _EffectiveConfig(
        data={key: value for key, value in data.items() if key != "extends"}
    )
    return _merge(merged, own, origin=manifest.path)


def _merge(
    parent: _EffectiveConfig, child: _EffectiveConfig, origin: Path | None = None
) -> _EffectiveConfig:
    """One config over another: top-level groups shallow-merge, the rest replaces.

    ``origin`` is the file ``child``'s data came from. When it is ``None`` the
    child is already resolved (a config followed through ``extends``) and brings
    its own per-option origins, which are kept.
    """
    data = dict(parent.data)
    origins = dict(parent.origins)
    for key, value in child.data.items():
        if isinstance(value, dict) and isinstance(data.get(key), dict):
            group = dict(data[key])
            group.update(value)
            data[key] = group
        else:
            data[key] = value

        if origin is not None:
            if isinstance(value, dict):
                for option in value:
                    if isinstance(option, str):
                        origins[f"{key}.{option}"] = origin
            else:
                origins[key] = origin
            continue
        # Already resolved: adopt the child's own attribution for what it sets.
        if isinstance(value, dict):
            for option in value:
                if isinstance(option, str):
                    child_origin = child.origins.get(f"{key}.{option}")
                    if child_origin is not None:
                        origins[f"{key}.{option}"] = child_origin
        else:
            child_origin = child.origins.get(key)
            if child_origin is not None:
                origins[key] = child_origin
    return _EffectiveConfig(data=data, origins=origins)


def _extends_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def _resolve_extends(
    reference: str,
    manifest: ManifestFile,
    context: ManifestContext,
    facts: ManifestFacts,
) -> Path | None:
    """``extends`` target inside the repo, else a diagnostic and ``None`` (FR-4)."""
    file = _scan_relative(context, manifest.name)
    if not reference.startswith("."):
        # A bare specifier resolves through node_modules or the package's own
        # resolution rules: not followed, not guessed at.
        facts.diagnostics.append(
            Diagnostic(
                kind="tsconfig_extends_outside_repo", file=file, detail=reference
            )
        )
        return None

    root = (context.scan_root or context.root).resolve()
    base = (manifest.path.parent / reference).resolve()
    try:
        base.relative_to(root)
    except ValueError:
        facts.diagnostics.append(
            Diagnostic(
                kind="tsconfig_extends_outside_repo", file=file, detail=reference
            )
        )
        return None

    for candidate in (base, Path(f"{base}.json"), base / "tsconfig.json"):
        if candidate.is_file() and candidate.suffix == ".json":
            return candidate
    facts.diagnostics.append(
        Diagnostic(kind="tsconfig_extends_missing", file=file, detail=reference)
    )
    return None


# --- JSON / JSONC ----------------------------------------------------------


def strip_jsonc(text: str) -> str:
    """Drop ``//`` and ``/* */`` comments and trailing commas, keeping strings and numbers.

    A one-pass scan, not a global regex: a ``//`` inside a string
    (``"https://host"``) must survive, and a trailing comma may sit before a
    comment (``"a": 1, // note`` then ``}``).
    """
    out: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char == '"':
            end = index + 1
            while end < length:
                if text[end] == "\\":
                    end += 2
                    continue
                if text[end] == '"':
                    end += 1
                    break
                end += 1
            out.append(text[index:end])
            index = end
            continue
        if text.startswith("//", index):
            newline = text.find("\n", index)
            index = length if newline < 0 else newline
            continue
        if text.startswith("/*", index):
            closing = text.find("*/", index + 2)
            index = length if closing < 0 else closing + 2
            continue
        if char == "," and _closes_container(text, index + 1):
            index += 1  # trailing comma: drop it, keep the closer
            continue
        out.append(char)
        index += 1
    return "".join(out)


def _closes_container(text: str, start: int) -> bool:
    """Whether only whitespace and comments separate ``start`` from ``}`` / ``]``."""
    index, length = start, len(text)
    while index < length:
        char = text[index]
        if char in " \t\r\n":
            index += 1
        elif text.startswith("//", index):
            newline = text.find("\n", index)
            index = length if newline < 0 else newline
        elif text.startswith("/*", index):
            closing = text.find("*/", index + 2)
            index = length if closing < 0 else closing + 2
        else:
            return char in "}]"
    return False


def _load_json(
    manifest: ManifestFile,
    context: ManifestContext,
    facts: ManifestFacts,
    *,
    jsonc: bool,
) -> dict[str, Any] | None:
    text = manifest.read_text()
    if text is None:
        facts.diagnostics.append(
            Diagnostic(
                kind="unreadable_file",
                file=_scan_relative(context, manifest.name),
                detail="read failed",
            )
        )
        return None
    if text.startswith("\ufeff"):
        text = text[1:]
    if jsonc:
        text = strip_jsonc(text)
    try:
        data = json.loads(text)
    except ValueError as exc:
        facts.diagnostics.append(
            Diagnostic(
                kind="invalid_json",
                file=_scan_relative(context, manifest.name),
                detail=str(exc),
            )
        )
        return None
    if not isinstance(data, dict):
        facts.diagnostics.append(
            Diagnostic(
                kind="invalid_json",
                file=_scan_relative(context, manifest.name),
                detail="not a JSON object",
            )
        )
        return None
    return data


# --- helpers ---------------------------------------------------------------


def _scalar_leaves(value: Any, path: tuple[str, ...] = ()) -> Iterator[tuple[str, str]]:
    """Every scalar leaf of a JSON value as ``(dotted path, text)``."""
    if isinstance(value, dict):
        for key in value:
            if isinstance(key, str):
                yield from _scalar_leaves(value[key], path + (key,))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _scalar_leaves(child, path + (str(index),))
    elif isinstance(value, bool):
        yield ".".join(path), "true" if value else "false"
    elif isinstance(value, (str, int, float)):
        yield ".".join(path), str(value)
    # ``None`` is "not set": no key.


def _truncate(value: str) -> str:
    return value[:MAX_CONFIG_VALUE_CHARS]


def _scan_relative(context: ManifestContext, name: str) -> str:
    """A manifest name as a scan-root-relative path, for diagnostics and ``config[].file`` (FR-9).

    ``ManifestFile.name`` is relative to the module root, so it needs the module
    prefix. A file a reader resolved elsewhere in the repo (the npm workspace
    lockfile at the root) already carries its scan-relative path; the tree says
    which of the two it is, so both cases get one rule.
    """
    if context.module == "." or name.startswith(context.module + "/"):
        return name
    root = context.scan_root or context.root
    if (root / name).is_file() and not (root / context.module / name).is_file():
        return name
    return f"{context.module}/{name}"


def _module_relative(context: ManifestContext, path: Path) -> str:
    root = (context.scan_root or context.root).resolve()
    try:
        relative = path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.name
    prefix = "" if context.module == "." else context.module + "/"
    if relative.startswith(prefix):
        return relative[len(prefix) :]
    return relative


def _scan_path(context: ManifestContext, path: Path) -> str:
    """A resolved file as a scan-root-relative path, for ``config[].file`` (FR-9)."""
    root = (context.scan_root or context.root).resolve()
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.name


def _posix_rel(path: Path, root: Path) -> str:
    try:
        relative = Path(os.path.normpath(path)).resolve().relative_to(root).as_posix()
    except ValueError:
        return "."
    return relative or "."


__all__ = [
    "DEPENDENCY_SCOPES",
    "MANIFEST_KINDS",
    "MAX_CONFIG_VALUE_CHARS",
    "PACKAGE_CONFIG_ROOTS",
    "normalize_range",
    "read_npm_manifests",
    "strip_jsonc",
]
