"""One scan: discovery → registered readers / extractors → profile (spec 026).

This module owns the loop; the facts come from the extractor contract, so a
spec that adds npm manifests (2), TypeScript sources (3, 4), Angular templates
(5), Maven / Gradle (6), Java sources (7) or Spring config (8) only registers a
module. Until then every fact section stays empty and the scan still produces a
valid profile.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from migration_planner.scanner import contract
from migration_planner.scanner.contract import (
    Diagnostic,
    ManifestContext,
    ManifestFile,
    ModuleEnv,
    PathMap,
    SCANNER_VERSION,
    SourceContext,
)
from migration_planner.scanner.discover import DiscoveryResult, DiscoveredFile, discover
from migration_planner.scanner.profile import (
    FactAccumulator,
    Generated,
    ModuleEntry,
    Profile,
    Summary,
    choose_framework,
    default_profile_path,
    inputs_hash,
    utc_now,
    write_profile,
)


class NoSupportedManifest(Exception):
    """No manifest file name from the Goal diagram exists under ``PATH`` (FR-1)."""


@dataclass
class ScanResult:
    profile: Profile
    summary: Summary
    discovery: DiscoveryResult
    written: bool = False
    path: Path | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)


def _manifest_contexts(discovery: DiscoveryResult) -> dict[str, ManifestContext]:
    """One context per module, holding that module's manifest files.

    ``ManifestFile.name`` is relative to the module root, which is what
    ``modules[].manifests`` records (FR-3).
    """
    by_module: dict[str, list[ManifestFile]] = {}
    for module in discovery.modules:
        by_module[module.path] = []
    for file in discovery.manifests:
        name = file.relative
        if file.module != ".":
            prefix = file.module + "/"
            if name.startswith(prefix):
                name = name[len(prefix) :]
        by_module.setdefault(file.module, []).append(
            ManifestFile(name=name, kind=file.kind, path=file.absolute)
        )
    return {
        module.path: ManifestContext(
            root=module.absolute,
            module=module.path,
            files=tuple(
                sorted(by_module.get(module.path, []), key=lambda item: item.name)
            ),
            scan_root=discovery.root,
        )
        for module in discovery.modules
    }


def _registered_readers():
    """Distinct reader functions with the manifest kinds they handle."""
    readers: dict[int, tuple[object, set[str]]] = {}
    for kind, reader in contract.manifest_readers().items():
        entry = readers.setdefault(id(reader), (reader, set()))
        entry[1].add(kind)
    return list(readers.values())


def _read_bytes(
    files: Iterable[DiscoveredFile],
) -> tuple[dict[str, bytes], list[Diagnostic]]:
    """File contents by scan-relative path; unreadable files become diagnostics."""
    contents: dict[str, bytes] = {}
    diagnostics: list[Diagnostic] = []
    for file in files:
        data = file.read_bytes()
        if data is None:
            diagnostics.append(
                Diagnostic(
                    kind="unreadable_file", file=file.relative, detail="read failed"
                )
            )
            continue
        contents[file.relative] = data
    return contents, diagnostics


def scan(
    path: str | Path,
    *,
    out: str | Path | None = None,
    include_tests: bool = True,
    max_locations: int = 20,
    write: bool = True,
) -> ScanResult:
    """Scan one repo and build its profile.

    Raises :class:`NoSupportedManifest` when the tree has no manifest the
    scanner understands (FR-1 exit code 2). Every other problem is recorded in
    ``diagnostics``: one unparsable file never fails a scan.
    """
    started = time.perf_counter()
    root = Path(path).expanduser().resolve()
    discovery = discover(root, include_tests=include_tests)
    if not discovery.has_supported_manifest:
        raise NoSupportedManifest(f"no supported manifest under {root}")

    target = Path(out) if out is not None else default_profile_path(root)
    accumulator = FactAccumulator(max_locations=max_locations)
    diagnostics: list[Diagnostic] = list(discovery.diagnostics)

    contents, read_diagnostics = _read_bytes(discovery.files)
    diagnostics.extend(read_diagnostics)

    # --- manifests (spec2 npm, spec6 maven/gradle, spec8 spring config) ---
    contexts = _manifest_contexts(discovery)
    environments: dict[str, ModuleEnv] = {}
    angular_projects: dict[str, set[str]] = {}
    for module_path, context in sorted(contexts.items()):
        present = {manifest.kind for manifest in context.files}
        own_packages: set[str] = set()
        path_map: PathMap | None = None
        for reader, kinds in _registered_readers():
            if not present & kinds:
                continue
            try:
                facts = reader(context)  # type: ignore[operator]
            except Exception as exc:  # a broken manifest is a diagnostic, not a crash
                diagnostics.append(
                    Diagnostic(
                        kind="reader_error",
                        file=_module_label(module_path),
                        detail=f"{type(exc).__name__}: {exc}",
                    )
                )
                continue
            for dependency in facts.dependencies:
                accumulator.add_dependency(dependency)
            for config in facts.config:
                accumulator.add_config(config)
            for framework in facts.frameworks:
                accumulator.add_framework(module_path, framework)
            for diagnostic in facts.diagnostics:
                diagnostics.append(diagnostic)
            own_packages.update(facts.own_packages)
            if facts.angular_projects:
                angular_projects.setdefault(module_path, set()).update(
                    facts.angular_projects
                )
            if facts.path_map is not None and path_map is None:
                path_map = facts.path_map
        environments[module_path] = ModuleEnv(
            module=module_path,
            own_packages=tuple(sorted(own_packages)),
            path_map=path_map,
        )

    # Own-code detection is repo-scoped, not module-scoped: an import of
    # ``@demo/ui`` inside ``packages/core`` is still the repo's own code, and a
    # package is importable under its name from any module (AC-8.2).
    repo_packages = tuple(
        sorted(
            {
                package
                for environment in environments.values()
                for package in environment.own_packages
            }
        )
    )
    # The profile records each module's own names; extractors get the repo-wide
    # set (above), since any module may import any sibling package.
    module_packages = {
        module_path: environment.own_packages
        for module_path, environment in environments.items()
    }
    declared_dependencies = tuple(
        sorted(
            {
                dependency.name
                for dependency in accumulator.dependencies
                if dependency.key.startswith("npm:") and dependency.name
            }
        )
    )
    for module_path, environment in environments.items():
        environments[module_path] = ModuleEnv(
            module=module_path,
            own_packages=repo_packages,
            path_map=environment.path_map,
            base_url_roots=_base_url_roots(root, environment.path_map),
            declared_dependencies=declared_dependencies,
        )

    # --- sources (specs3–5 TypeScript / Angular, spec7 Java) ---
    extractors = contract.source_extractors()
    for file in discovery.sources:
        extractor = extractors.get(file.kind)
        if extractor is None:
            continue
        data = contents.get(file.relative, b"")
        try:
            facts = extractor(
                SourceContext(
                    path=file.absolute,
                    relative=file.relative,
                    module=file.module,
                    language=file.kind,
                    test=file.test,
                    data=data,
                    env=environments.get(file.module, ModuleEnv(module=file.module)),
                )
            )
        except Exception as exc:  # one unparsable file never fails the scan
            diagnostics.append(
                Diagnostic(
                    kind="extractor_error",
                    file=file.relative,
                    detail=f"{type(exc).__name__}: {exc}",
                )
            )
            continue
        accumulator.add_file(facts)

    for post_pass in contract.post_passes():
        try:
            post_pass(accumulator)
        except Exception as exc:
            diagnostics.append(
                Diagnostic(
                    kind="post_pass_error",
                    detail=f"{getattr(post_pass, '__name__', 'post_pass')}: "
                    f"{type(exc).__name__}: {exc}",
                )
            )

    framework, framework_diagnostics = choose_framework(accumulator.frameworks)
    diagnostics.extend(framework_diagnostics)
    for diagnostic in diagnostics:
        accumulator.add_diagnostic(diagnostic)

    modules = [
        ModuleEntry(
            path=module.path,
            manifests=list(module.manifests),
            frameworks=sorted(
                accumulator.frameworks.get(module.path, []),
                key=lambda item: (item.name, item.version),
            ),
            angular_projects=sorted(angular_projects.get(module.path, ())),
            own_packages=list(module_packages.get(module.path, ())),
        )
        for module in discovery.modules
    ]

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    profile = Profile(
        generated=Generated(
            at=utc_now(),
            scanner=SCANNER_VERSION,
            root=".",
            files_scanned=len(contents),
            files_skipped=discovery.skipped,
            duration_ms=elapsed_ms,
        ),
        inputs_hash=inputs_hash(
            ((relative, data) for relative, data in contents.items()),
            options={"include_tests": include_tests, "max_locations": max_locations},
        ),
        framework=framework,
        modules=modules,
        dependencies=accumulator.dependency_entries(),
        symbols=accumulator.symbol_entries(),
        members=accumulator.member_entries(),
        side_effect_imports=accumulator.side_effect_entries(),
        wildcard_imports=accumulator.wildcard_entries(),
        config=accumulator.config_entries(),
        templates=accumulator.template_entries(),
        diagnostics=accumulator.diagnostic_entries(),
    )
    summary = Summary(
        files_scanned=len(contents),
        files_skipped=discovery.skipped,
        framework=framework.name if framework else None,
        framework_version=framework.version if framework else "",
        dependencies=len(profile.dependencies),
        symbols=len(profile.symbols),
        members=len(profile.members),
        config=len(profile.config),
        template_tokens=len(profile.templates),
        diagnostics=len(profile.diagnostics),
        out=_display_path(target, root),
        duration_ms=elapsed_ms,
        gitignore_hint=_needs_gitignore(root, target),
    )
    result = ScanResult(profile=profile, summary=summary, discovery=discovery)
    if write:
        result.path = write_profile(profile, target)
        result.written = True
    return result


# Source extensions stripped from a ``baseUrl`` entry: ``main.ts`` is importable
# as ``'main'``. Longest first, so ``.d.ts`` wins over ``.ts``.
_BASE_URL_EXTENSIONS: tuple[str, ...] = (
    ".d.ts",
    ".tsx",
    ".ts",
    ".jsx",
    ".mjs",
    ".cjs",
    ".js",
)


def _base_url_roots(root: Path, path_map: PathMap | None) -> tuple[str, ...]:
    """Entry names directly under the module's ``baseUrl`` (spec3 FR-5).

    Only ``baseUrl`` itself is listed, not the tree below it: a non-relative
    specifier resolves under ``baseUrl`` only through its first segment.
    """
    if path_map is None or not path_map.base_url:
        return ()
    directory = (root / path_map.base_url).resolve()
    try:
        directory.relative_to(root)
    except ValueError:
        return ()
    if not directory.is_dir():
        return ()
    names: set[str] = set()
    try:
        entries = list(directory.iterdir())
    except OSError:
        return ()
    for entry in entries:
        name = entry.name
        if name.startswith(".") or name == "node_modules":
            continue
        if entry.is_dir():
            names.add(name)
            continue
        for extension in _BASE_URL_EXTENSIONS:
            if name.endswith(extension):
                names.add(name[: -len(extension)])
                break
    return tuple(sorted(names))


def _display_path(target: Path, root: Path) -> str:
    """Profile path as printed: relative to the scan root when it is inside it."""
    try:
        return target.resolve().relative_to(root).as_posix()
    except ValueError:
        return target.as_posix()


def _module_label(module_path: str) -> str:
    """A diagnostic ``file`` for a module-level problem."""
    return "." if module_path == "." else module_path


def _needs_gitignore(root: Path, target: Path) -> bool:
    """First run in a repo that does not ignore ``.migration/`` (FR-1, not written)."""
    if target.exists():
        return False
    ignore_file = root / ".gitignore"
    try:
        text = ignore_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return True
    return not any(
        line.strip().rstrip("/") in (".migration", "/.migration", ".migration/")
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    )


__all__ = ["NoSupportedManifest", "ScanResult", "scan"]
