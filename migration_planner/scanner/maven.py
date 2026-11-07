"""Maven manifests: ``pom.xml`` (spec 026.6, FR-3 / FR-8).

One reader answers the two questions the profile asks about a Maven module:

- **which Spring Boot version** the module builds against (FR-3): its own
  ``<parent>`` ``org.springframework.boot:spring-boot-starter-parent``, else a
  ``spring-boot-dependencies`` BOM imported in ``<dependencyManagement>``,
  inherited through the in-repo parent chain;
- **what it declares** (FR-8): ``<parent>``, ``<dependencies>``,
  ``<dependencyManagement>`` (BOM imports and managed entries) and
  ``<build><plugins>`` / ``<build><pluginManagement>`` as
  ``maven:<groupId>:<artifactId>`` facts with a ``kind``;
- **its properties** (``<properties>`` of the pom and its in-repo parents) as
  ``cfg:pom.xml#properties.<name>``, because rules such as "``java.version``
  must be at least 21" are written against exactly that key.

Interpolation
-------------

``${prop}`` is resolved from the effective property map — the pom's own
``<properties>`` over its in-repo parents' — plus Maven's implicit properties
(``project.version``, ``project.parent.version``, ``project.groupId``, …).
A value that cannot be resolved keeps its raw text and produces an
``unresolved_variable`` diagnostic: the profile never invents a version.

Parents are found the way Maven finds them, but never outside the repo: the
``<parent><relativePath>`` (default ``../pom.xml``), else the nearest ancestor
pom with the same ``groupId``/``artifactId`` (and ``version``, when it is
declared). An external parent such as ``spring-boot-starter-parent`` is *not*
followed — only its coordinates are recorded — so a scan never needs the
network or a local ``~/.m2``.

Nothing here fails a scan: a broken pom is a ``pom_parse_error`` diagnostic and
the other manifests of the module are still read.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from migration_keys.keys import cfg_key, maven_key

from migration_planner.scanner.contract import (
    ConfigFact,
    DependencyFact,
    Diagnostic,
    FrameworkFact,
    ManifestContext,
    ManifestFacts,
)

#: The manifest classification this reader handles.
MANIFEST_KINDS: tuple[str, ...] = ("pom.xml",)

SPRING_BOOT_GROUP = "org.springframework.boot"
SPRING_BOOT_PARENT = "spring-boot-starter-parent"
SPRING_BOOT_BOM = "spring-boot-dependencies"

#: ``scope`` of a fact, so the four roles of one artifact never collapse into
#: one entry (FR-8: one entry per ``(key, module, scope, kind)``).
PARENT_SCOPE = "parent"
IMPORT_SCOPE = "import"
MANAGED_SCOPE = "dependencyManagement"
PLUGIN_SCOPE = "build"
DEFAULT_SCOPE = "compile"

#: Where ``version`` came from. Maven has no lockfile: the version in the pom
#: (or an in-repo parent, through inheritance) is what the build uses.
VERSION_SOURCE = "declared"

#: How deep a parent chain / a property chain may go before it is a cycle.
MAX_DEPTH = 10

_PROPERTY_RE = re.compile(r"\$\{([^}]+)\}")


# --- records ---------------------------------------------------------------


@dataclass(frozen=True)
class _Gav:
    """One ``<groupId>:<artifactId>:<version>`` with the extras Maven allows."""

    group_id: str = ""
    artifact_id: str = ""
    version: str = ""
    scope: str = ""
    type: str = ""


@dataclass
class _Pom:
    """One parsed ``pom.xml``, with the coordinates the reader needs."""

    path: Path
    relative: str  # scan-root-relative
    text: str
    group_id: str = ""
    artifact_id: str = ""
    version: str = ""
    packaging: str = ""
    parent: _Gav | None = None
    #: ``<parent><relativePath>`` as written; ``None`` means "not set" (Maven's
    #: default ``../pom.xml``) and ``""`` means "do not look locally".
    parent_relative_path: str | None = None
    properties: dict[str, str] = field(default_factory=dict)
    dependencies: list[_Gav] = field(default_factory=list)
    managed: list[_Gav] = field(default_factory=list)
    plugins: list[_Gav] = field(default_factory=list)
    modules: list[str] = field(default_factory=list)


# --- XML -------------------------------------------------------------------


def _parse_xml(text: str) -> ET.Element | None:
    """The document with namespaces stripped, ``None`` when it does not parse.

    ``xml.etree`` never resolves external entities, so a pom with a DOCTYPE
    cannot make the scanner read a file or open a socket.
    """
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return None
    for node in root.iter():
        if isinstance(node.tag, str) and "}" in node.tag:
            node.tag = node.tag.rsplit("}", 1)[1]
    return root


def _text(element: ET.Element | None, tag: str) -> str:
    if element is None:
        return ""
    node = element.find(tag)
    if node is None or node.text is None:
        return ""
    return node.text.strip()


def _section(element: ET.Element | None, tag: str) -> list[ET.Element]:
    """Children of ``<tag>`` (``<dependencies>`` → its ``<dependency>`` list)."""
    if element is None:
        return []
    node = element.find(tag)
    return list(node) if node is not None else []


def _gav(element: ET.Element, *, default_scope: str = "") -> _Gav:
    return _Gav(
        group_id=_text(element, "groupId"),
        artifact_id=_text(element, "artifactId"),
        version=_text(element, "version"),
        scope=_text(element, "scope") or default_scope,
        type=_text(element, "type"),
    )


def _load_pom(path: Path, relative: str) -> tuple[_Pom | None, str | None]:
    """Read and parse one pom; ``(pom, error)``."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return None, f"read failed: {exc}"
    root = _parse_xml(text)
    if root is None:
        return None, "not well-formed XML"

    pom = _Pom(path=path, relative=relative, text=text)
    pom.group_id = _text(root, "groupId")
    pom.artifact_id = _text(root, "artifactId")
    pom.version = _text(root, "version")
    pom.packaging = _text(root, "packaging") or "jar"

    parent = root.find("parent")
    if parent is not None:
        pom.parent = _gav(parent)
        relative_node = parent.find("relativePath")
        if relative_node is not None:
            pom.parent_relative_path = (relative_node.text or "").strip()

    properties = root.find("properties")
    if properties is not None:
        for node in properties:
            if isinstance(node.tag, str):
                pom.properties[node.tag] = (node.text or "").strip()

    pom.dependencies = [
        _gav(node) for node in _section(root, "dependencies") if node.tag == "dependency"
    ]
    management = root.find("dependencyManagement")
    if management is not None:
        pom.managed = [
            _gav(node)
            for node in _section(management, "dependencies")
            if node.tag == "dependency"
        ]

    build = root.find("build")
    if build is not None:
        pom.plugins = [
            _gav(node) for node in _section(build, "plugins") if node.tag == "plugin"
        ]
        plugin_management = build.find("pluginManagement")
        if plugin_management is not None:
            pom.plugins.extend(
                _gav(node)
                for node in _section(plugin_management, "plugins")
                if node.tag == "plugin"
            )

    pom.modules = [
        (node.text or "").strip()
        for node in _section(root, "modules")
        if node.tag == "module" and (node.text or "").strip()
    ]
    return pom, None


# --- parent chain ----------------------------------------------------------


def _parent_candidates(pom: _Pom, scan_root: Path) -> Iterable[Path]:
    """Where the parent pom may be: ``<relativePath>`` first, then ancestors.

    Only files inside the scan root are ever a candidate: a scan reads the tree
    it was pointed at and nothing above it, so a parent pom in a containing
    checkout is never mistaken for the parent.
    """
    if pom.parent_relative_path == "":
        return  # ``<relativePath/>``: Maven resolves it from the repository only
    declared = pom.parent_relative_path or "../pom.xml"
    candidate = (pom.path.parent / declared).resolve()
    if candidate.is_dir():
        # ``<relativePath>../parent</relativePath>``: Maven appends ``pom.xml``.
        candidate = candidate / "pom.xml"
    if candidate.is_file() and _inside(candidate, scan_root):
        yield candidate
        return
    # A wrong ``relativePath`` falls back to the nearest matching ancestor pom,
    # which is what Maven does before it looks in the local repository.
    for directory in pom.path.resolve().parent.parents:
        if not _inside(directory, scan_root):
            return  # outside the scanned tree: stop, do not look further up
        candidate = directory / "pom.xml"
        if candidate.is_file():
            yield candidate


def _inside(path: Path, scan_root: Path) -> bool:
    """Whether ``path`` is the scan root or below it."""
    try:
        path.relative_to(scan_root)
    except ValueError:
        return False
    return True


def _matches(pom: _Pom, wanted: _Gav) -> bool:
    if pom.group_id and wanted.group_id and pom.group_id != wanted.group_id:
        return False
    if pom.artifact_id and wanted.artifact_id and pom.artifact_id != wanted.artifact_id:
        return False
    if pom.version and wanted.version and pom.version != wanted.version:
        return False
    return True


def _parent_chain(
    pom: _Pom,
    scan_root: Path,
    diagnostics: list[Diagnostic],
) -> list[_Pom]:
    """``[own pom, parent, grandparent, …]`` — in-repo parents only."""
    chain = [pom]
    seen = {pom.path.resolve()}
    current = pom
    while current.parent is not None and len(chain) <= MAX_DEPTH:
        found: _Pom | None = None
        for candidate in _parent_candidates(current, scan_root):
            if candidate in seen:
                diagnostics.append(
                    Diagnostic(
                        kind="pom_parent_cycle",
                        file=current.relative,
                        detail=candidate.name,
                    )
                )
                return chain
            try:
                relative = candidate.relative_to(scan_root).as_posix()
            except ValueError:
                relative = candidate.name
            loaded, _ = _load_pom(candidate, relative)
            if loaded is None:
                continue
            if not _matches(loaded, current.parent):
                continue
            found = loaded
            break
        if found is None:
            # The parent lives outside the repo (a release parent, the Boot
            # starter parent): its coordinates are a fact, its content is not
            # needed. Nothing to resolve against it.
            break
        chain.append(found)
        seen.add(found.path.resolve())
        current = found
    return chain


# --- interpolation ---------------------------------------------------------


def _implicit(pom: _Pom) -> dict[str, str]:
    """Maven's own properties for one pom (``project.version`` and friends).

    The values are raw: they may themselves be ``${...}`` and are interpolated
    when a value that uses them is resolved.
    """
    parent = pom.parent
    version = pom.version or (parent.version if parent else "")
    group_id = pom.group_id or (parent.group_id if parent else "")
    values = {
        "project.version": version,
        "pom.version": version,
        "version": version,
        "project.groupId": group_id,
        "pom.groupId": group_id,
        "groupId": group_id,
        "project.artifactId": pom.artifact_id,
        "pom.artifactId": pom.artifact_id,
        "artifactId": pom.artifact_id,
        "project.packaging": pom.packaging,
        "pom.packaging": pom.packaging,
    }
    if parent is not None:
        values.update(
            {
                "project.parent.version": parent.version,
                "parent.version": parent.version,
                "project.parent.groupId": parent.group_id,
                "parent.groupId": parent.group_id,
                "project.parent.artifactId": parent.artifact_id,
                "parent.artifactId": parent.artifact_id,
            }
        )
    return values


def _effective_properties(chain: Sequence[_Pom]) -> dict[str, str]:
    """Properties visible to the nearest pom: ancestors first, own last (FR-8).

    Maven assembles the inherited model first and interpolates the result, so a
    ``${project.version}`` written in a parent's ``<properties>`` means the
    version of the module being built — the child's, when the child declares
    one. The nearest pom's implicit coordinates therefore win, like its
    explicit properties do.
    """
    values: dict[str, str] = {}
    for pom in reversed(chain):
        values.update(_implicit(pom))
        values.update(pom.properties)
    return values


def _interpolate(
    text: str,
    values: dict[str, str],
    unresolved: list[str],
    depth: int = 0,
) -> str:
    if "$" not in text or depth > MAX_DEPTH:
        return text

    def replace(match: re.Match[str]) -> str:
        name = match.group(1).strip()
        value = values.get(name)
        if value is None:
            unresolved.append(name)
            return match.group(0)
        return _interpolate(value, values, unresolved, depth + 1)

    return _PROPERTY_RE.sub(replace, text)


def _line_of(text: str, needle: str) -> int | None:
    index = text.find(needle)
    if index < 0:
        return None
    return text.count("\n", 0, index) + 1


class _Resolver:
    """Interpolates values against one module's effective properties (FR-8)."""

    def __init__(
        self,
        values: dict[str, str],
        chain: Sequence[_Pom],
        diagnostics: list[Diagnostic],
    ) -> None:
        self.values = values
        self.chain = chain
        self.diagnostics = diagnostics
        self.reported: set[str] = set()

    def __call__(self, text: str, *, file: str = "") -> str:
        if not text or "$" not in text:
            return text
        unresolved: list[str] = []
        resolved = _interpolate(text, self.values, unresolved)
        for name in unresolved:
            self.report(name, file)
        return resolved

    def report(self, name: str, file: str = "") -> None:
        """One diagnostic per unresolved name, at the line that mentions it."""
        if name in self.reported:
            return
        self.reported.add(name)
        needle = "${" + name + "}"
        line: int | None = None
        source = file
        for pom in self.chain:
            found = _line_of(pom.text, needle)
            if found is not None:
                line, source = found, pom.relative
                break
        self.diagnostics.append(
            Diagnostic(
                kind="unresolved_variable",
                file=source or (self.chain[0].relative if self.chain else ""),
                line=line,
                detail=needle,
            )
        )


# --- reader ----------------------------------------------------------------


def read_maven_manifests(context: ManifestContext) -> ManifestFacts:
    """Every Maven fact of one module (FR-3 Spring Boot, FR-8 manifests)."""
    facts = ManifestFacts()
    pom_file = context.named("pom.xml")
    if pom_file is None:
        return facts

    scan_root = (context.scan_root or context.root).resolve()
    own, error = _load_pom(pom_file.path, _scan_relative(context, pom_file.path))
    if own is None:
        facts.diagnostics.append(
            Diagnostic(
                kind="pom_parse_error",
                file=_scan_relative(context, pom_file.path),
                detail=error or "unreadable",
            )
        )
        return facts

    chain = _parent_chain(own, scan_root, facts.diagnostics)
    resolve = _Resolver(_effective_properties(chain), chain, facts.diagnostics)

    _record_parent(facts, context, own, resolve)
    _record_dependencies(facts, context, own, resolve)
    _record_managed(facts, context, own, resolve)
    _record_plugins(facts, context, own, resolve)
    _record_properties(facts, context, chain, resolve)
    _detect_spring_boot(facts, own, chain, resolve)
    _record_module_roots(facts, own, scan_root)
    _record_group_ids(facts, own, chain, resolve)
    return facts


def _scan_relative(context: ManifestContext, path: Path) -> str:
    """A pom as a scan-root-relative path, for diagnostics and ``config[].file``."""
    root = (context.scan_root or context.root).resolve()
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.name


def _dependency(
    facts: ManifestFacts,
    context: ManifestContext,
    coordinates: _Gav,
    *,
    kind: str,
    scope: str,
    resolve: _Resolver,
    file: str,
) -> None:
    """Turn one ``<dependency>``/``<plugin>`` into a profile fact (FR-8).

    ``<groupId>${project.groupId}</groupId>`` is how a sibling module is
    usually written, so the coordinates are interpolated like the version. An
    unresolved one keeps its raw text (and its diagnostic) rather than vanish.
    """
    coordinates = _Gav(
        group_id=resolve(coordinates.group_id, file=file),
        artifact_id=resolve(coordinates.artifact_id, file=file),
        version=coordinates.version,
        scope=coordinates.scope,
        type=coordinates.type,
    )
    if not coordinates.group_id or not coordinates.artifact_id:
        facts.diagnostics.append(
            Diagnostic(
                kind="invalid_dependency",
                file=file,
                detail=f"{coordinates.group_id}:{coordinates.artifact_id}".strip(":"),
            )
        )
        return
    name = f"{coordinates.group_id}:{coordinates.artifact_id}"
    raw = coordinates.version
    version = _unresolved_free(resolve(raw, file=file)) if raw else ""
    facts.dependencies.append(
        DependencyFact(
            key=maven_key(name),
            name=name,
            range=raw,
            version=version or None,
            scope=scope,
            module=context.module,
            kind=kind,
            version_source=VERSION_SOURCE if version else None,
        )
    )


def _unresolved_free(version: str) -> str:
    """A version, or ``""`` when it still holds a ``${…}`` placeholder.

    An unresolved placeholder is *not* a version: keeping it in ``version``
    would make the profile claim the service builds with
    ``${external.bom.version}``. It stays in ``range`` as written, and the
    ``unresolved_variable`` diagnostic says why (AC-6).
    """
    return "" if "${" in version else version


def _record_parent(
    facts: ManifestFacts,
    context: ManifestContext,
    pom: _Pom,
    resolve: _Resolver,
) -> None:
    if pom.parent is None or not pom.parent.artifact_id:
        return
    _dependency(
        facts,
        context,
        pom.parent,
        kind="parent",
        scope=PARENT_SCOPE,
        resolve=resolve,
        file=pom.relative,
    )


def _record_dependencies(
    facts: ManifestFacts,
    context: ManifestContext,
    pom: _Pom,
    resolve: _Resolver,
) -> None:
    for coordinates in pom.dependencies:
        _dependency(
            facts,
            context,
            coordinates,
            kind="dependency",
            scope=coordinates.scope or DEFAULT_SCOPE,
            resolve=resolve,
            file=pom.relative,
        )


def _record_managed(
    facts: ManifestFacts,
    context: ManifestContext,
    pom: _Pom,
    resolve: _Resolver,
) -> None:
    """``<dependencyManagement>``: an imported BOM is ``kind: bom``.

    A managed entry that is not an import still pins a version, and the profile
    keeps it — with its own scope, so it never collapses into the ``compile``
    dependency of the same artifact (FR-8).
    """
    for coordinates in pom.managed:
        if coordinates.scope == IMPORT_SCOPE:
            _dependency(
                facts,
                context,
                coordinates,
                kind="bom",
                scope=IMPORT_SCOPE,
                resolve=resolve,
                file=pom.relative,
            )
            continue
        _dependency(
            facts,
            context,
            coordinates,
            kind="dependency",
            scope=coordinates.scope or MANAGED_SCOPE,
            resolve=resolve,
            file=pom.relative,
        )


def _record_plugins(
    facts: ManifestFacts,
    context: ManifestContext,
    pom: _Pom,
    resolve: _Resolver,
) -> None:
    for coordinates in pom.plugins:
        if not coordinates.group_id:
            # Maven's default plugin group: ``<plugin><artifactId>…`` alone.
            coordinates = _Gav(
                group_id="org.apache.maven.plugins",
                artifact_id=coordinates.artifact_id,
                version=coordinates.version,
            )
        _dependency(
            facts,
            context,
            coordinates,
            kind="plugin",
            scope=PLUGIN_SCOPE,
            resolve=resolve,
            file=pom.relative,
        )


def _record_properties(
    facts: ManifestFacts,
    context: ManifestContext,
    chain: Sequence[_Pom],
    resolve: _Resolver,
) -> None:
    """``<properties>`` of the pom and its in-repo parents (FR-8).

    The effective set is recorded for every module that sees it: a rule about
    ``cfg:pom.xml#properties.java.version`` applies to a child module that
    inherits the value as much as to the parent that writes it. ``file`` says
    which pom declares the value.
    """
    for pom in reversed(chain):
        for name, raw in pom.properties.items():
            facts.config.append(
                ConfigFact(
                    key=cfg_key("pom.xml", f"properties.{name}"),
                    value=resolve(raw, file=pom.relative),
                    file=pom.relative,
                    module=context.module,
                    line=_line_of(pom.text, f"<{name}>"),
                )
            )


def _detect_spring_boot(
    facts: ManifestFacts,
    own: _Pom,
    chain: Sequence[_Pom],
    resolve: _Resolver,
) -> None:
    """FR-3: the parent first, then a ``spring-boot-dependencies`` BOM import.

    The chain is walked rather than only the own pom, because a child inherits
    its in-repo parent's ``<parent>`` effect and its imported BOMs. ``source``
    names the pom that actually declares it, so a reader can tell an inherited
    version from a declared one.

    A declaration whose version does not resolve (``${boot.version}`` set
    outside the repo) does not stop the search: a later source may still know
    the version. When none does, the module is still on Spring Boot, and the
    fact says so with an empty ``version`` and the text as written in ``raw``
    — the same shape an Angular range that cannot be normalized has (spec2).
    The ``unresolved_variable`` diagnostic says why.
    """
    unresolved: FrameworkFact | None = None
    for pom, raw, section in _spring_boot_declarations(chain):
        version = _unresolved_free(resolve(raw, file=pom.relative))
        fact = FrameworkFact(
            name="spring-boot",
            version=version,
            raw=raw,
            source=f"{pom.relative}#{section}",
        )
        if version:
            facts.frameworks.append(fact)
            return
        unresolved = unresolved or fact
    if unresolved is not None:
        facts.frameworks.append(unresolved)


def _spring_boot_declarations(
    chain: Sequence[_Pom],
) -> Iterable[tuple[_Pom, str, str]]:
    """``(pom, raw version, section)`` of every FR-3 source, in FR-3 order."""
    for pom in chain:
        parent = pom.parent
        if (
            parent is not None
            and parent.group_id == SPRING_BOOT_GROUP
            and parent.artifact_id == SPRING_BOOT_PARENT
            and parent.version
        ):
            yield pom, parent.version, "parent"
    for pom in chain:
        for coordinates in pom.managed:
            if (
                coordinates.group_id == SPRING_BOOT_GROUP
                and coordinates.artifact_id == SPRING_BOOT_BOM
                and coordinates.version
            ):
                yield pom, coordinates.version, "dependencyManagement"


def _record_module_roots(facts: ManifestFacts, pom: _Pom, scan_root: Path) -> None:
    """``<modules>`` are module roots too (FR-3, AC-6 multi-module).

    Discovery already treats every directory with a ``pom.xml`` as a module
    root, so this only matters for a module the discovery rules skipped. The
    scan adds those to ``modules[]``; a path outside the repo is not followed.
    """
    for declared in pom.modules:
        candidate = (pom.path.parent / declared).resolve()
        try:
            relative = candidate.relative_to(scan_root).as_posix()
        except ValueError:
            continue
        if candidate.is_dir():
            facts.module_roots.append(relative)


def _record_group_ids(
    facts: ManifestFacts,
    own: _Pom,
    chain: Sequence[_Pom],
    resolve: _Resolver,
) -> None:
    """External groupIds, so spec7 recognizes a fully qualified usage (FR-7).

    The groupIds the repo itself publishes under — this pom's and its in-repo
    parents' — go to ``own_group_ids`` instead: ``com.acme.app.Foo`` is the
    service's own code, not a dependency, even when the module also depends
    on a sibling ``com.acme:lib``. ``scan()`` subtracts every module's own
    groupIds repo-wide, which covers a sibling with a groupId of its own.

    Interpolated like the coordinates they come from; a groupId that still
    holds ``${…}`` names nothing a source file could use, so it is left out.
    """
    owned = {_own_group_id(pom, index, chain) for index, pom in enumerate(chain)}
    owned = {resolve(group) for group in owned if group}
    owned = {group for group in owned if "${" not in group}

    written: set[str] = set()
    for pom in chain:
        if pom.parent is not None and pom.parent.group_id:
            written.add(pom.parent.group_id)
        for coordinates in (*pom.dependencies, *pom.managed, *pom.plugins):
            if coordinates.group_id:
                written.add(coordinates.group_id)
    groups = {resolve(group) for group in written}
    facts.own_group_ids.extend(sorted(owned))
    facts.group_ids.extend(
        sorted(group for group in groups if "${" not in group and group not in owned)
    )


def _own_group_id(pom: _Pom, index: int, chain: Sequence[_Pom]) -> str:
    """The groupId ``pom`` publishes under, when that groupId is the repo's own.

    A pom with no ``<groupId>`` inherits its parent's — but only an *in-repo*
    parent makes that groupId the repo's: a service that inherits
    ``org.springframework.boot`` from the starter parent does not own Spring's
    groupId.
    """
    if pom.group_id:
        return pom.group_id
    if index + 1 < len(chain) and pom.parent is not None:
        return pom.parent.group_id
    return ""


__all__ = [
    "DEFAULT_SCOPE",
    "MANIFEST_KINDS",
    "SPRING_BOOT_BOM",
    "SPRING_BOOT_GROUP",
    "SPRING_BOOT_PARENT",
    "read_maven_manifests",
]
