"""One scan: discovery → registered readers / extractors → profile (spec 026).

This module owns the loop; the facts come from the extractor contract, so a
spec that adds npm manifests (2), TypeScript sources (3, 4), Angular templates
(5), Maven / Gradle (6), Java sources (7) or Spring config (8) only registers a
module. Until then every fact section stays empty and the scan still produces a
valid profile.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from migration_planner.scanner import contract
from migration_planner.scanner.cache import (
    CACHE_NAME,
    CachedFile,
    ScanCache,
    environment_digest,
    extractor_id,
)
from migration_planner.scanner.contract import (
    Diagnostic,
    FileFacts,
    ManifestContext,
    ManifestFile,
    ModuleEnv,
    OwnPackage,
    PathMap,
    PostPassContext,
    ResolutionEnv,
    SCANNER_VERSION,
    SourceExtractor,
)
from migration_planner.scanner.discover import DiscoveryResult, DiscoveredFile, discover
from migration_planner.scanner.parallel import ParseJob, default_jobs, parse_parallel
from migration_planner.scanner.profile import (
    SCHEMA_VERSION,
    FactAccumulator,
    Generated,
    ModuleEntry,
    Profile,
    Summary,
    choose_framework,
    default_profile_path,
    inputs_hash_from_digests,
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
    #: Source files whose facts came from the cache, and which were parsed (FR-10).
    parsed_files: list[str] = field(default_factory=list)
    cached_files: list[str] = field(default_factory=list)
    cache_path: Path | None = None
    #: Problems of this run that are not facts about the repo (``cache_corrupt``):
    #: reported, never written into the profile.
    run_diagnostics: list[Diagnostic] = field(default_factory=list)


def _manifest_contexts(discovery: DiscoveryResult) -> dict[str, ManifestContext]:
    """One context per module, holding that module's manifest files.

    ``ManifestFile.name`` is relative to the module root, which is what
    ``modules[].manifests`` records (FR-3).
    """
    by_module: dict[str, list[ManifestFile]] = {}
    repo_has_java_build = any(
        file.kind in _JAVA_BUILD_KINDS for file in discovery.manifests
    )
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
            repo_has_java_build=repo_has_java_build,
        )
        for module in discovery.modules
    }


#: Manifest kinds that make a module a Java module (spec6, spec8).
_JAVA_BUILD_KINDS: frozenset[str] = frozenset(
    {"pom.xml", "build.gradle", "build.gradle.kts"}
)


def _registered_readers():
    """Distinct reader functions with the manifest kinds they handle."""
    readers: dict[int, tuple[object, set[str]]] = {}
    for kind, reader in contract.manifest_readers().items():
        entry = readers.setdefault(id(reader), (reader, set()))
        entry[1].add(kind)
    return list(readers.values())


def _stat(file: DiscoveredFile) -> tuple[int, int] | None:
    """``(size, mtime_ns)`` of a discovered file, or ``None`` when it moved away."""
    try:
        status = file.absolute.stat()
    except OSError:
        return None
    return status.st_size, status.st_mtime_ns


@dataclass
class _SourceState:
    """What the scan knows about one source file before parsing it (FR-10)."""

    file: DiscoveredFile
    sha256: str
    size: int = 0
    mtime_ns: int = 0
    #: The extractor that handles the file's language; ``None`` when no reader
    #: is registered, so the file contributes nothing.
    extractor: SourceExtractor | None = None
    #: Module environment and its digest, shared by every file of one module.
    env: ModuleEnv = field(default_factory=ModuleEnv)
    env_digest: str = ""
    #: Facts reused from the cache; ``None`` when the file must be parsed.
    facts: FileFacts | None = None
    #: The bytes, present only when the file has to be parsed.
    data: bytes | None = None


def _read_manifests(
    discovery: DiscoveryResult,
    diagnostics: list[Diagnostic],
) -> dict[str, bytes]:
    """Manifest contents by path. Manifests are always read, cache or not (FR-10):
    there are few of them, and every reader must see the tree as it is now."""
    manifests: dict[str, bytes] = {}
    for file in discovery.manifests:
        data = file.read_bytes()
        if data is None:
            diagnostics.append(
                Diagnostic(
                    kind="unreadable_file", file=file.relative, detail="read failed"
                )
            )
            continue
        manifests[file.relative] = data
    return manifests


def _collect_sources(
    discovery: DiscoveryResult,
    cache: ScanCache,
    environments: Mapping[str, ModuleEnv],
    extractors: Mapping[str, SourceExtractor],
    diagnostics: list[Diagnostic],
) -> list[_SourceState]:
    """Decide, per source file, whether its facts can be reused (FR-10).

    A file is reused when the cache holds its facts, the extractor and module
    environment are the same as when they were recorded, and either its
    ``(size, mtime_ns)`` is unchanged (the file is not even read) or its content
    ``sha256`` is. Everything else is read here and parsed later.

    A file whose language has no extractor is still read and hashed: it
    contributes to ``inputs_hash`` exactly as before the cache existed, it just
    contributes no facts, so it is never cached.
    """
    digests: dict[str, tuple[ModuleEnv, str]] = {}
    states: list[_SourceState] = []
    for file in discovery.sources:
        extractor = extractors.get(file.kind)
        if file.module not in digests:
            env = environments.get(file.module, ModuleEnv(module=file.module))
            digests[file.module] = (env, environment_digest(env))
        env, env_digest = digests[file.module]
        identity = extractor_id(extractor)

        stat = _stat(file)
        if stat is None:
            diagnostics.append(
                Diagnostic(
                    kind="unreadable_file", file=file.relative, detail="stat failed"
                )
            )
            continue
        size, mtime_ns = stat
        cached = cache.get(file.relative) if extractor is not None else None
        if (
            cached is not None
            and cached.matches_stat(size, mtime_ns)
            and not cache.is_racy(mtime_ns)
            and cached.usable(environment=env_digest, extractor=identity)
        ):
            states.append(
                _SourceState(
                    file=file,
                    sha256=cached.sha256,
                    size=size,
                    mtime_ns=mtime_ns,
                    extractor=extractor,
                    env=env,
                    env_digest=env_digest,
                    facts=cached.facts,
                )
            )
            continue

        data = file.read_bytes()
        if data is None:
            diagnostics.append(
                Diagnostic(
                    kind="unreadable_file", file=file.relative, detail="read failed"
                )
            )
            continue
        digest = hashlib.sha256(data).hexdigest()
        state = _SourceState(
            file=file,
            sha256=digest,
            size=size,
            mtime_ns=mtime_ns,
            extractor=extractor,
            env=env,
            env_digest=env_digest,
            data=data,
        )
        if (
            cached is not None
            and cached.sha256 == digest
            and cached.usable(environment=env_digest, extractor=identity)
        ):
            # Same content, new stat: the facts stand, only the signature moves.
            state.facts = cached.facts
            state.data = None
        states.append(state)
    return states


def scan(
    path: str | Path,
    *,
    out: str | Path | None = None,
    include_tests: bool = True,
    max_locations: int = 20,
    no_values: bool = False,
    jobs: int = 0,
    force: bool = False,
    use_cache: bool = True,
    write: bool = True,
) -> ScanResult:
    """Scan one repo and build its profile.

    Raises :class:`NoSupportedManifest` when the tree has no manifest the
    scanner understands (FR-1 exit code 2). Every other problem is recorded in
    ``diagnostics``: one unparsable file never fails a scan.

    ``no_values`` stores no config value at all (spec8 ``--no-values``): the key
    is the fact a matcher compares, the value is what must not reach a CI
    artifact.

    ``jobs`` is the parse parallelism (FR-10): ``0`` means the CPU count, ``1``
    parses in this process. ``force`` ignores the incremental cache, and
    ``use_cache=False`` disables it entirely (a caller that wants a scan to
    leave no trace next to the profile).

    Incremental behavior (FR-10): when ``inputs_hash`` matches the profile's,
    the profile is not rewritten and the summary says ``unchanged``.
    """
    started = time.perf_counter()
    started_ns = time.time_ns()
    root = Path(path).expanduser().resolve()
    discovery = discover(root, include_tests=include_tests)
    if not discovery.has_supported_manifest:
        raise NoSupportedManifest(f"no supported manifest under {root}")

    target = Path(out) if out is not None else default_profile_path(root)
    worker_count = default_jobs() if jobs <= 0 else max(1, jobs)
    accumulator = FactAccumulator(max_locations=max_locations, no_values=no_values)
    diagnostics: list[Diagnostic] = list(discovery.diagnostics)

    # --- the incremental cache (FR-10) ---
    # Problems with the cache are about *this run*, not about the repo, so they
    # never go into the profile: an unchanged profile would otherwise keep a
    # stale ``cache_corrupt`` forever (it is not rewritten when the inputs did
    # not change). They are reported on the result, and the CLI prints them.
    run_diagnostics: list[Diagnostic] = []
    cache_path = cache_path_for(root, target)
    if use_cache and not force:
        cache, cache_diagnostics = ScanCache.load(cache_path, root=root)
        run_diagnostics.extend(cache_diagnostics)
    else:
        cache = ScanCache.empty(cache_path, root=root)

    manifests = _read_manifests(discovery, diagnostics)

    # --- manifests (spec2 npm, spec6 maven/gradle, spec8 spring config) ---
    contexts = _manifest_contexts(discovery)
    environments: dict[str, ModuleEnv] = {}
    angular_projects: dict[str, set[str]] = {}
    own_packages: dict[str, OwnPackage] = {}
    declared_roots: dict[str, ModuleEntry] = {}
    module_group_ids: dict[str, set[str]] = {}
    own_group_ids: set[str] = set()
    spring_config_files: dict[str, set[str]] = {}
    for module_path, context in sorted(contexts.items()):
        present = {manifest.kind for manifest in context.files}
        module_own_packages: set[str] = set()
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
            module_own_packages.update(facts.own_packages)
            for package in facts.own_package_sources:
                # Two modules may declare the same workspace name (a root
                # ``workspaces`` list and the package itself): keep one, so a
                # specifier resolves to one directory.
                own_packages.setdefault(package.name, package)
            if facts.angular_projects:
                angular_projects.setdefault(module_path, set()).update(
                    facts.angular_projects
                )
            if facts.module_roots:
                # Maven ``<modules>`` / Gradle ``include(…)`` (spec6 FR-3, FR-8):
                # a declared module that discovery did not find is still a
                # module root, even with no manifest of its own.
                for declared in facts.module_roots:
                    declared_roots.setdefault(declared, ModuleEntry(path=declared))
            if facts.group_ids:
                module_group_ids.setdefault(module_path, set()).update(
                    facts.group_ids
                )
            own_group_ids.update(facts.own_group_ids)
            if facts.spring_config_files:
                spring_config_files.setdefault(module_path, set()).update(
                    facts.spring_config_files
                )
            if facts.path_map is not None and path_map is None:
                path_map = facts.path_map
        environments[module_path] = ModuleEnv(
            module=module_path,
            own_packages=tuple(sorted(module_own_packages)),
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
            framework_names=tuple(
                sorted(
                    framework.name
                    for framework in accumulator.frameworks.get(module_path, [])
                )
            ),
            path_map=environment.path_map,
            base_url_roots=_base_url_roots(root, environment.path_map),
            declared_dependencies=declared_dependencies,
            group_ids=_repo_group_ids(module_group_ids, own_group_ids),
            own_group_ids=tuple(sorted(own_group_ids)),
        )

    # --- sources (specs3–5 TypeScript / Angular, spec7 Java) ---
    # A file whose facts the cache still holds is not parsed; everything else
    # goes to the pool in one batch, so `--jobs` changes the wall clock only
    # (FR-10). Post-passes below run on the whole collected set either way.
    extractors = contract.source_extractors()
    sources = _collect_sources(
        discovery, cache, environments, extractors, diagnostics
    )
    cache.started_ns = started_ns
    file_facts: dict[str, FileFacts] = {}
    module_of: dict[str, str] = {}
    jobs_to_run: list[tuple[ParseJob, SourceExtractor, ModuleEnv]] = []
    parsed_files: list[str] = []
    cached_files: list[str] = []
    for state in sources:
        if state.extractor is None:
            continue
        module_of[state.file.relative] = state.file.module
        if state.facts is not None:
            file_facts[state.file.relative] = state.facts
            cached_files.append(state.file.relative)
            continue
        parsed_files.append(state.file.relative)
        jobs_to_run.append(
            (
                ParseJob(
                    relative=state.file.relative,
                    path=state.file.absolute,
                    module=state.file.module,
                    language=state.file.kind,
                    test=state.file.test,
                    data=state.data or b"",
                ),
                state.extractor,
                state.env,
            )
        )

    outcome = parse_parallel(
        jobs_to_run,
        jobs=worker_count,
        # Barrel resolution needs every file's facts, so the pool's own order is
        # irrelevant; unordered collection overlaps parsing with IPC.
        asynch=worker_count > 1,
    )
    diagnostics.extend(outcome.failed)
    file_facts.update(outcome.facts)

    # Cache bookkeeping: a parsed file's facts are stored with the stat
    # signature that was current when it was read; a reused one keeps its entry.
    # A file whose extractor failed is not stored, so the next scan retries it.
    # Entries of files that are no longer discovered are pruned.
    for state in sources:
        facts = file_facts.get(state.file.relative)
        if facts is None or state.extractor is None:
            continue
        cache.put(
            state.file.relative,
            CachedFile(
                size=state.size,
                mtime_ns=state.mtime_ns,
                sha256=state.sha256,
                environment=state.env_digest,
                extractor=extractor_id(state.extractor),
                facts=facts,
            ),
        )
    cache.prune(state.file.relative for state in sources if state.extractor is not None)

    # --- post-passes (spec4 barrels, spec7 own-package filtering) ---
    # A post-pass may replace a file's facts to drop some (spec7's own-package
    # filtering needs every package in the repo), so the merge happens after
    # them, not before: otherwise a filtered fact would stay in the profile.
    fragments: list[FileFacts] = []
    if contract.post_passes():
        post_context = PostPassContext(
            root=root,
            files=file_facts,
            resolution=ResolutionEnv(
                module_of=module_of,
                environments=environments,
                packages=own_packages,
            ),
        )
        for post_pass in contract.post_passes():
            try:
                fragment = post_pass(post_context)
            except Exception as exc:
                diagnostics.append(
                    Diagnostic(
                        kind="post_pass_error",
                        detail=f"{getattr(post_pass, '__name__', 'post_pass')}: "
                        f"{type(exc).__name__}: {exc}",
                    )
                )
                continue
            if fragment is not None:
                fragments.append(fragment)
    for facts in file_facts.values():
        accumulator.add_file(facts)
    for fragment in fragments:
        accumulator.add_file(fragment)

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
            spring_config_files=sorted(spring_config_files.get(module.path, ())),
        )
        for module in discovery.modules
    ]
    # A module a build file declares but discovery did not find (a Maven
    # ``<module>`` or Gradle ``include`` with no manifest of its own) is still a
    # module root, so its path is listed (spec6 FR-3, FR-8).
    known_modules = {module.path for module in modules}
    modules.extend(
        entry
        for path, entry in sorted(declared_roots.items())
        if path not in known_modules and (root / path).is_dir()
    )
    modules.sort(key=lambda entry: entry.path)

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    digest = inputs_hash_from_digests(
        _hashed_inputs(sources, manifests),
        options={
            "include_tests": include_tests,
            "max_locations": max_locations,
            "no_values": no_values,
        },
    )
    files_scanned = len(manifests) + len(sources)
    previous = _previous_profile(target)
    # ``--force`` always rewrites: it is how a user regenerates a profile that is
    # stale for a reason ``inputs_hash`` cannot see (a scanner fix without a
    # version bump, a hand-edited file).
    unchanged = (
        write
        and not force
        and previous is not None
        and previous.get("inputs_hash") == digest
        and previous.get("schema") == SCHEMA_VERSION
    )
    profile = Profile(
        generated=Generated(
            at=utc_now(),
            scanner=SCANNER_VERSION,
            root=".",
            files_scanned=files_scanned,
            files_skipped=discovery.skipped,
            duration_ms=elapsed_ms,
        ),
        inputs_hash=digest,
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
        files_scanned=files_scanned,
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
        unchanged=unchanged,
        parsed_files=len(parsed_files),
        cached_files=len(cached_files),
    )
    result = ScanResult(
        profile=profile,
        summary=summary,
        discovery=discovery,
        parsed_files=sorted(parsed_files),
        cached_files=sorted(cached_files),
        cache_path=cache_path if use_cache else None,
        run_diagnostics=run_diagnostics,
    )
    if write:
        if not unchanged:
            result.path = write_profile(profile, target)
            result.written = True
        else:
            # An unchanged tree: the profile on disk already says this, and
            # rewriting it would only move `generated.at` (FR-10).
            result.path = target
        if use_cache:
            cache.save()
    return result


def cache_path_for(root: Path, target: Path) -> Path:
    """Where the cache of a scan of ``root`` writing ``target`` lives (FR-10).

    Next to the profile. Inside the scanned repo that is the spec's
    ``.migration/scan-cache.json``. Outside it (``--out /tmp/x/profile.json``)
    one directory may serve several repos, so the name carries a digest of the
    root and two services never prune each other's cache.
    """
    resolved = target.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        tag = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:12]
        stem, _, suffix = CACHE_NAME.rpartition(".")
        return resolved.parent / f"{stem}-{tag}.{suffix}"
    return resolved.parent / CACHE_NAME


def _hashed_inputs(
    sources: list[_SourceState],
    manifests: dict[str, bytes],
) -> list[tuple[str, str]]:
    """``(path, sha256)`` for every scanned file, sources and manifests (FR-9, FR-10).

    A source file the cache vouched for contributes its stored ``sha256``, so
    ``inputs_hash`` stays exactly what a full scan would compute. Unreadable
    files are absent, as before: the hash is over what was really read.
    """
    rows: list[tuple[str, str]] = [
        (relative, hashlib.sha256(data).hexdigest())
        for relative, data in manifests.items()
    ]
    for state in sources:
        if state.file.relative in manifests:
            continue  # a manifest, hashed above
        rows.append((state.file.relative, state.sha256))
    return rows


def _previous_profile(target: Path) -> dict | None:
    """The profile already at ``target``, or ``None`` when there is none usable."""
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


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


def _repo_group_ids(
    declared: Mapping[str, set[str]], owned: set[str]
) -> tuple[str, ...]:
    """The external groupIds a Java source may use without an import (spec6 → spec7).

    Repo-scoped, like ``own_packages``: a multi-module repo declares its
    dependencies in one place (the parent's ``<dependencyManagement>`` or the
    root ``build.gradle``), and a module without a build file of its own still
    uses them. Every groupId one of the repo's own modules publishes under is
    removed, so ``com.acme.lib.Widget`` in ``app`` is the repo's code, not an
    external package — even though ``app`` depends on ``com.acme:lib``.
    """
    groups: set[str] = set()
    for values in declared.values():
        groups.update(values)
    return tuple(sorted(groups - owned))


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
    """First run in a repo that does not ignore ``.migration/`` (FR-1, not written).

    Only when the profile really lands inside the scanned repo: a scan with
    ``--out /tmp/x/profile.json`` (how the AC-11 runs leave the work tree
    untouched) writes nothing into the tree, so there is nothing to ignore.
    """
    try:
        target.resolve().relative_to(root)
    except ValueError:
        return False
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
