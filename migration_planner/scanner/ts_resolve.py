"""Barrel and alias resolution for TS / JS (spec 026.4 FR-5).

spec3 records the imports of *external* packages and, separately, keeps every
import of the repo's own code (:class:`OwnImport`) together with each file's
export map and the names it declares itself. This module is the post-pass that
turns the second into the first: it follows an own-code import through barrels,
path aliases and workspace packages until an external package is reached, and
records the external key **at the original import site**.

    core/index.ts:  export { inject } from './di'
    di.ts:          export { inject } from '@angular/core'
    a.ts:           import { inject } from '@app/core'

gives ``npm:@angular/core#inject`` at ``a.ts`` — the line a matcher must search,
because that is where the service uses the symbol.

What is followed
----------------

A specifier that names own code resolves to a file: a relative path, a
``compilerOptions.paths`` alias (longest matching pattern, targets in order,
first existing wins), a ``baseUrl`` path, a workspace package name (its
``package.json`` entry, else ``index.*``). Every candidate is probed with the
extensions TypeScript tries — ``.ts``, ``.tsx``, ``.d.ts``, ``.js``, ``.jsx``,
``.mjs``, ``.cjs`` and ``/index.*`` — and a ``.js`` specifier also finds its
``.ts`` source, which is what ``NodeNext`` projects write.

Then the file's export map is followed: ``export { X } from '…'``,
``export { X as Y } from '…'`` (renames applied along the chain),
``export * from '…'`` and ``export * as ns from '…'``. A name that ends in a
local declaration is own code and is dropped silently. A ``export *`` from an
external package cannot be enumerated, so a name that reaches it is attributed
to that package: the star is the chain's end, and that is the only package the
name can come from.

Two kinds of fact come out
--------------------------

**Symbols at the import site** — a named or default own import whose chain ends
at an external package (``import { inject } from '@app/core'``). A namespace
import publishes no symbol of its own, exactly as in spec3.

**Members** — an access through an own-code binding: a member of a named import
(``di.inject(…)``), a decorator option on a namespaced one
(``@core.Component({…})`` → ``npm:@angular/core#Component.selector``), or —
through a namespace import of a barrel — the symbol itself (``core.inject(…)``
→ ``npm:@angular/core#inject``), which is a symbol rather than a member for the
same reason as in spec3.

Best effort, never silent: a cycle gives ``barrel_cycle``, a chain deeper than
:data:`MAX_DEPTH` gives ``barrel_depth``, and an own import whose file cannot be
found gives ``unresolved_import``. A specifier that names an asset rather than a
module (``./x.scss``, ``./data.json``) is not a module we could resolve and is
skipped without a diagnostic.

Results are memoized per ``(file, exported name)``, so a barrel imported by a
thousand files is resolved once.
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass
from typing import Iterator, Mapping

from migration_keys.keys import npm_key
from migration_keys.specifiers import (
    is_node_builtin,
    is_own_code,
    is_relative_specifier,
    join_path,
    own_path_aliases,
    package_of_specifier,
    resolve_path_alias,
    strip_query,
)

from migration_planner.scanner.contract import (
    Diagnostic,
    FileFacts,
    ModuleEnv,
    OwnImport,
    OwnMember,
    OwnPackage,
    PostPassContext,
    Usage,
)

#: A chain longer than this stops resolving (FR-5). The first own file after the
#: importing one is depth 1, so depth 11 is the diagnostic (AC-2.3).
MAX_DEPTH = 10

#: Extensions probed in this order (FR-5, plus ``.jsx`` which discovery parses).
EXTENSIONS: tuple[str, ...] = (".ts", ".tsx", ".d.ts", ".js", ".jsx", ".mjs", ".cjs")

#: Extensions of a specifier that names a module, so a specifier with any other
#: extension (``./x.scss``, ``./data.json``) is not a resolvable module.
MODULE_EXTENSIONS: frozenset[str] = frozenset(EXTENSIONS)

#: Specifier extensions a ``NodeNext`` project uses for a TypeScript source.
_JS_TO_TS: dict[str, tuple[str, ...]] = {
    ".js": (".ts", ".tsx", ".d.ts"),
    ".jsx": (".tsx", ".ts"),
    ".mjs": (".mts", ".ts"),
    ".cjs": (".cts", ".ts"),
}


@dataclass(frozen=True)
class _External:
    """The chain ended at a symbol of an external package."""

    package: str
    symbol: str


@dataclass(frozen=True)
class _ExternalNamespace:
    """``export * as rx from 'rxjs'``: every member is a symbol of ``package``."""

    package: str


@dataclass(frozen=True)
class _Namespace:
    """The name resolves to a namespace — every member lives in ``file``."""

    file: str


class _Dropped:
    """The name is definitively the repo's own code, so nothing is recorded.

    It is different from ``None``, which also means "gave up": a cycle, a chain
    past :data:`MAX_DEPTH`, a file the scanner did not parse. That distinction
    only matters for memoization — a definitive answer holds for every importer,
    while a give-up is a property of one entry point and must not poison a
    shorter chain to the same name.
    """

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "DROPPED"


DROPPED = _Dropped()


class _NotFound:
    """The file does not export the name at all (definitive, memoizable).

    Distinct from :data:`DROPPED` so an ``export *`` search moves on to the next
    star instead of stopping at the first file that lacks the name — the
    standard ``public-api.ts`` with many ``export * from './x'`` lines.
    """

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "NOT_FOUND"


NOT_FOUND = _NotFound()


def resolve_barrels(context: PostPassContext) -> FileFacts:
    """Facts for every own-code import whose chain reaches an external package."""
    return _Resolver(context).run()


class _Resolver:
    """One resolution pass over the collected per-file facts."""

    def __init__(self, context: PostPassContext) -> None:
        self.facts: Mapping[str, FileFacts] = context.files
        self.module_of = context.resolution.module_of
        self.environments = context.resolution.environments
        self.packages: Mapping[str, OwnPackage] = context.resolution.packages
        self.diagnostics: list[Diagnostic] = []
        self.symbols: list[Usage] = []
        self.members: list[Usage] = []
        # ``(file, exported name)`` → what it really is (FR-5 memoization).
        self._exports: dict[tuple[str, str], object] = {}
        # ``(file, specifier)`` → resolved file, so a barrel shared by many
        # importers is probed once.
        self._targets: dict[tuple[str, str], str | None] = {}
        self._reported: set[tuple[str, str, str]] = set()

    def run(self) -> FileFacts:
        for relative in sorted(self.facts):
            facts = self.facts[relative]
            if not facts.own_import_bindings and not facts.own_member_bindings:
                continue
            self._file(relative, facts)
        return FileFacts(
            symbols=self.symbols,
            members=self.members,
            diagnostics=self.diagnostics,
        )

    # -- one file ----------------------------------------------------------

    def _file(self, relative: str, facts: FileFacts) -> None:
        """Resolve this file's own imports, then the members it accesses."""
        # ``{local name: what it is}`` for this file, so a member access does
        # not have to resolve the import again.
        bindings: dict[str, object] = {}
        for own in facts.own_import_bindings:
            for local, imported in sorted(own.named.items()):
                self._bind(relative, own, local, imported, bindings)
            if own.default:
                self._bind(relative, own, own.default, "default", bindings)
            if own.namespace:
                target = self._target_file(relative, own.specifier)
                if target is not None:
                    bindings[own.namespace] = _Namespace(target)
        for member in facts.own_member_bindings:
            self._member(relative, member, bindings)

    def _bind(
        self,
        relative: str,
        own: OwnImport,
        local: str,
        imported: str,
        bindings: dict[str, object],
    ) -> None:
        """Record the external symbol an own-code import binds, if the chain ends there."""
        result = self._resolve_import(relative, own.specifier, imported)
        if result is None or result is NOT_FOUND:
            return
        bindings[local] = result
        if not isinstance(result, _External):
            return  # a namespace publishes no symbol of its own
        self.symbols.append(
            Usage(
                key=npm_key(result.package, result.symbol),
                file=relative,
                line=own.line,
                test=own.test,
                type_only=own.type_only or local in own.type_names,
            )
        )

    def _member(
        self, relative: str, member: OwnMember, bindings: dict[str, object]
    ) -> None:
        """One access on an own-code binding, once the chain reaches a package."""
        bound = bindings.get(member.local)
        if isinstance(bound, _External):
            # ``di.inject(…)`` after ``import { inject as di } from '@app/core'``.
            symbol = member.symbol or bound.symbol
            self._add_member(relative, member, bound.package, symbol, member.member)
            return
        if isinstance(bound, _ExternalNamespace):
            # ``rx.filter()`` after ``import { rx } from '@app/core'`` with
            # ``export * as rx from 'rxjs'``: a symbol of the package, as for a
            # direct ``import * as rx from 'rxjs'`` (spec3 namespace rule).
            if member.symbol:
                self._add_member(
                    relative, member, bound.package, member.symbol, member.member
                )
                return
            self.symbols.append(
                Usage(
                    key=npm_key(bound.package, member.member),
                    file=relative,
                    line=member.line,
                    test=member.test,
                )
            )
            return
        if not isinstance(bound, _Namespace):
            return
        # ``core.inject(…)`` / ``@core.Component({…})``: the first member of a
        # namespace is the package's symbol (spec3's namespace rule).
        name = member.symbol or member.member
        result = self._export(bound.file, name, depth=1, chain=())
        if not isinstance(result, _External):
            return
        if member.symbol:
            self._add_member(
                relative, member, result.package, result.symbol, member.member
            )
            return
        self.symbols.append(
            Usage(
                key=npm_key(result.package, result.symbol),
                file=relative,
                line=member.line,
                test=member.test,
            )
        )

    def _add_member(
        self,
        relative: str,
        member: OwnMember,
        package: str,
        symbol: str,
        name: str,
    ) -> None:
        self.members.append(
            Usage(
                key=npm_key(package, symbol, name),
                file=relative,
                line=member.line,
                test=member.test,
            )
        )

    # -- following a chain -------------------------------------------------

    def _resolve_import(self, relative: str, specifier: str, name: str) -> object:
        """The external symbol ``name`` of ``specifier`` as seen from ``relative``."""
        target = self._target_file(relative, specifier)
        if target is None:
            return None
        return self._export(target, name, depth=1, chain=(relative,))

    def _export(self, file: str, name: str, *, depth: int, chain: tuple[str, ...]):
        """What ``name`` really is in ``file``, following its export map.

        Answers are memoized per ``(file, exported name)`` (FR-5). Only a
        definitive one is stored: a give-up depends on how deep this entry point
        already is, so caching it could deny a shorter chain the same name.
        """
        key = (file, name)
        if key in self._exports:
            return self._exports[key]
        if depth > MAX_DEPTH:
            self._diagnose("barrel_depth", file, " -> ".join(chain + (file,)))
            return None
        if file in chain:
            self._diagnose("barrel_cycle", file, " -> ".join(chain + (file,)))
            return None
        facts = self.facts.get(file)
        if facts is None:
            return None
        result = self._export_in(file, facts, name, depth, chain + (file,))
        if result is not None:
            self._exports[key] = result
        return result

    def _export_in(
        self,
        file: str,
        facts: FileFacts,
        name: str,
        depth: int,
        chain: tuple[str, ...],
    ):
        binding = facts.export_map.get(name)
        if binding is not None:
            if not binding.specifier:
                return DROPPED  # ``export { x }``: declared here, own code
            return self._follow(
                file, binding.specifier, binding.original or name, depth, chain
            )

        namespace_target = facts.namespace_exports.get(name)
        if namespace_target is not None:
            if self._is_builtin(namespace_target, file):
                return DROPPED
            if self._is_external(namespace_target, file):
                # ``export * as rx from 'rxjs'``: members of ``rx`` are symbols
                # of the package.
                package = package_of_specifier(namespace_target)
                return _ExternalNamespace(package) if package else DROPPED
            resolved = self._target_file(file, namespace_target)
            return _Namespace(resolved) if resolved is not None else None

        if name in facts.local_declarations:
            return DROPPED  # a class / function / const of its own: own code
        if name == "default":
            return DROPPED  # ``export *`` never re-exports the default

        stars = [
            specifier
            for specifier in facts.star_exports
            if not self._is_builtin(specifier, file)
        ]
        gave_up = False
        for specifier in stars:
            if self._is_external(specifier, file):
                continue
            resolved = self._target_file(file, specifier)
            if resolved is None:
                continue
            result = self._export(resolved, name, depth=depth + 1, chain=chain)
            if result is None:
                gave_up = True  # a cycle / depth limit on this star: try the next
                continue
            if result is NOT_FOUND:
                continue  # this star does not export the name: try the next
            return result
        # An external ``export *`` cannot be enumerated. With exactly one, it is
        # the only place the name can come from (FR-5). With several, guessing
        # would put a wrong key in the profile (``map`` is ``rxjs``, not
        # ``@angular/core``), so the name is reported, not attributed.
        external = sorted(
            {
                package_of_specifier(specifier)
                for specifier in stars
                if self._is_external(specifier, file)
            }
        )
        if len(external) == 1:
            return _External(external[0], name)
        if len(external) > 1:
            self._diagnose("ambiguous_export", file, f"{name}: " + " | ".join(external))
            return DROPPED
        return None if gave_up else NOT_FOUND

    def _follow(
        self,
        file: str,
        specifier: str,
        name: str,
        depth: int,
        chain: tuple[str, ...],
    ):
        """Continue a re-export at ``specifier``: external now, or one hop on."""
        if self._is_builtin(specifier, file):
            return DROPPED  # ``export { x } from 'node:events'``: no npm package
        if self._is_external(specifier, file):
            package = package_of_specifier(specifier)
            return _External(package, name) if package else DROPPED
        resolved = self._target_file(file, specifier)
        if resolved is None:
            return None  # unresolved: a diagnostic was added, no answer
        return self._export(resolved, name, depth=depth + 1, chain=chain)

    # -- specifier → file --------------------------------------------------

    def _target_file(self, relative: str, specifier: str) -> str | None:
        """The file an own-code specifier names, or ``None`` plus a diagnostic."""
        key = (relative, specifier)
        if key in self._targets:
            return self._targets[key]
        found: str | None = None
        for candidate in self._candidates(relative, strip_query(specifier)):
            found = self._probe(candidate)
            if found is not None:
                break
        if found is None and not _is_asset(specifier):
            self._diagnose("unresolved_import", relative, specifier)
        self._targets[key] = found
        return found

    def _candidates(self, relative: str, specifier: str) -> list[str]:
        """Paths to probe, best first, for one specifier (FR-5).

        TypeScript's own order: ``paths`` first, then ``baseUrl``, then a
        package. A workspace package name is in ``own_packages`` and so is own
        code either way; trying ``baseUrl`` before it keeps a directory that
        shadows a package name honest, which is also what ``is_own_code`` does
        for a declared dependency.
        """
        if specifier.startswith("/"):
            return [specifier.lstrip("/")]
        if is_relative_specifier(specifier):
            return [join_path(posixpath.dirname(relative), specifier)]
        env = self._env(relative)
        candidates: list[str] = []
        path_map = env.path_map
        if path_map is not None and path_map.paths:
            own_aliases = set(own_path_aliases(path_map.paths))
            own_paths = {
                pattern: targets
                for pattern, targets in path_map.paths.items()
                if pattern in own_aliases
            }
            candidates.extend(
                resolve_path_alias(specifier, own_paths, paths_dir=path_map.paths_dir)
            )
        if path_map is not None and path_map.base_url:
            candidates.append(join_path(path_map.base_url, specifier))
        candidates.extend(self._package_candidates(specifier))
        return candidates

    def _package_candidates(self, specifier: str) -> list[str]:
        """Where a workspace package's specifier lands (FR-5).

        The ``package.json`` entries (``main`` / ``module`` / ``types`` /
        ``exports["."]``) in order, then ``index.*`` in the package directory,
        then the subpath as written (``@demo/core/src/x``).
        """
        package, subpath = self._own_package(specifier)
        if package is None:
            return []
        base = package.directory
        if subpath:
            # ``@demo/ui/testing`` → ``exports["./testing"]`` first, then a
            # ``"./*"`` pattern, then the subpath as a directory path.
            candidates: list[str] = []
            wanted = f"./{subpath}"
            for target in package.subpath_exports.get(wanted, ()):
                candidates.append(join_path(base, target))
            for pattern, targets in package.subpath_exports.items():
                star = pattern.find("*")
                if star < 0:
                    continue
                prefix, suffix = pattern[:star], pattern[star + 1 :]
                if not (wanted.startswith(prefix) and wanted.endswith(suffix)):
                    continue
                if len(wanted) < len(prefix) + len(suffix):
                    continue
                capture = wanted[len(prefix) : len(wanted) - len(suffix)]
                for target in targets:
                    candidates.append(join_path(base, target.replace("*", capture)))
            candidates.append(join_path(base, subpath))
            return candidates
        candidates = [join_path(base, entry) for entry in package.entries]
        candidates.append(join_path(base, "index"))
        return candidates

    def _own_package(self, specifier: str) -> tuple[OwnPackage | None, str]:
        """The own package a bare specifier names, plus its subpath."""
        parts = specifier.split("/")
        name = (
            "/".join(parts[:2])
            if specifier.startswith("@") and len(parts) > 1
            else parts[0]
        )
        package = self.packages.get(name)
        if package is None:
            return None, ""
        return package, "/".join(parts[len(name.split("/")) :])

    def _probe(self, candidate: str) -> str | None:
        """The first file of ``candidate`` that the scanner actually parsed."""
        for variant in _variants(candidate):
            if variant in self.facts:
                return variant
        return None

    # -- environment -------------------------------------------------------

    def _env(self, relative: str) -> ModuleEnv:
        module = self.module_of.get(relative, ".")
        env = self.environments.get(module)
        return env if env is not None else ModuleEnv(module=module)

    def _is_own(self, specifier: str, relative: str) -> bool:
        env = self._env(relative)
        path_map = env.path_map
        return is_own_code(
            specifier,
            own_packages=env.own_packages,
            path_aliases=own_path_aliases(path_map.paths)
            if path_map is not None
            else (),
            base_url_roots=env.base_url_roots,
            declared_dependencies=env.declared_dependencies,
        )

    def _is_builtin(self, specifier: str, relative: str) -> bool:
        return is_node_builtin(
            specifier,
            declared_dependencies=self._env(relative).declared_dependencies,
        )

    def _is_external(self, specifier: str, relative: str) -> bool:
        return not self._is_builtin(specifier, relative) and not self._is_own(
            specifier, relative
        )

    def _diagnose(self, kind: str, file: str, detail: str) -> None:
        """Record one diagnostic. A chain is reported once per kind and file.

        The same cycle is found from every file that enters it, with a different
        chain each time; the file is what a reader can act on, so the chains are
        not allowed to multiply the entries. An unresolved specifier is per
        specifier, so there the detail is part of the identity.
        """
        key = (kind, file, "" if kind.startswith("barrel_") else detail)
        if key in self._reported:
            return
        self._reported.add(key)
        self.diagnostics.append(Diagnostic(kind=kind, file=file, detail=detail))


def _variants(candidate: str) -> Iterator[str]:
    """The paths TypeScript tries for one candidate, in its own order (FR-5)."""
    path = candidate.rstrip("/") or "."
    yield path
    extension = posixpath.splitext(path)[1]
    if extension:
        for source in _JS_TO_TS.get(extension, ()):
            yield posixpath.splitext(path)[0] + source
        if extension not in MODULE_EXTENSIONS:
            return  # ``./x.scss`` and friends are not modules
        return
    for suffix in EXTENSIONS:
        yield path + suffix
    for suffix in EXTENSIONS:
        yield f"{path}/index{suffix}"


def _is_asset(specifier: str) -> bool:
    """A specifier with a non-module extension (``./x.scss``, ``./data.json``).

    It names something the scanner does not parse, so "no such module" is not a
    problem worth a diagnostic.
    """
    extension = posixpath.splitext(specifier.split("?", 1)[0])[1]
    return bool(extension) and extension not in MODULE_EXTENSIONS


__all__ = [
    "EXTENSIONS",
    "MAX_DEPTH",
    "MODULE_EXTENSIONS",
    "resolve_barrels",
]
