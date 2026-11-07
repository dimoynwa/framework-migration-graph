"""File discovery and module roots (spec 026 FR-2, FR-3).

Discovery answers one question: which files of this repo can the scanner read,
and which module does each belong to?

- Inside a git work tree the file list comes from
  ``git ls-files --cached --others --exclude-standard``, so ``.gitignore`` is
  respected (tracked files are scanned even when they match an ignore rule).
  Otherwise the tree is walked, which ignores ``.gitignore`` by design.
- Skipped directories are pruned in both modes. ``node_modules``,
  ``.angular``, ``.gradle``, ``.git`` and ``.migration`` are skipped at any
  depth. The build-output names ``dist``, ``build``, ``target`` and ``out`` are
  skipped only outside a ``src`` directory: inside ``src/`` they are ordinary
  Java packages or app folders (``src/main/java/com/x/build/``).
- A file over 2 MB, or generated / minified JS, is skipped and counted in
  ``diagnostics`` instead of read.
- Every remaining file is classified as ``manifest:<kind>`` or
  ``source:<lang>``; anything else is ignored, so later specs only register a
  handler for their kind.

A *module root* is a directory holding ``package.json``, ``pom.xml`` or
``build.gradle(.kts)``. Every manifest and source file belongs to its nearest
module root. A file under no module root belongs to ``.``, and ``.`` is a module
whenever any file belongs to it (a root ``tsconfig.json`` or a shared
``config/application.yml`` next to ``svc/pom.xml``), so no manifest is ever
dropped. A repo without any module root still gets one module, ``.``.
"""

from __future__ import annotations

import fnmatch
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from migration_planner.scanner.contract import Diagnostic

# Directory names never entered, at any depth (FR-2). Compared case-insensitively.
ALWAYS_SKIPPED_DIRECTORIES: frozenset[str] = frozenset(
    {"node_modules", ".angular", ".gradle", ".git", ".migration"}
)

# Build-output names, skipped only when no ancestor is ``src`` (FR-2): under
# ``src/`` they are package or folder names, not build output.
BUILD_OUTPUT_DIRECTORIES: frozenset[str] = frozenset({"dist", "build", "target", "out"})

SKIPPED_DIRECTORIES: frozenset[str] = (
    ALWAYS_SKIPPED_DIRECTORIES | BUILD_OUTPUT_DIRECTORIES
)

_SOURCE_TREE_DIRECTORY = "src"

# A source file above this size is not read; it is counted as a diagnostic (FR-2).
MAX_FILE_BYTES = 2 * 1024 * 1024

# Manifests get a higher cap: a real Angular ``package-lock.json`` is often well
# over 2 MB, and dropping it would silently replace installed versions with
# range floors. The cap only guards against pathological files.
MAX_MANIFEST_BYTES = 50 * 1024 * 1024

# A first line longer than this marks generated / minified JS (FR-2).
MAX_JS_FIRST_LINE = 1000

# Manifest classifications. Keys are what manifest readers register for.
MANIFEST_PACKAGE_JSON = "package.json"
MANIFEST_PACKAGE_LOCK = "package-lock.json"
MANIFEST_ANGULAR_JSON = "angular.json"
MANIFEST_TSCONFIG = "tsconfig.json"
MANIFEST_POM = "pom.xml"
MANIFEST_BUILD_GRADLE = "build.gradle"
MANIFEST_BUILD_GRADLE_KTS = "build.gradle.kts"
MANIFEST_SETTINGS_GRADLE = "settings.gradle"
MANIFEST_LIBS_VERSIONS = "libs.versions.toml"
MANIFEST_GRADLE_PROPERTIES = "gradle.properties"
MANIFEST_SPRING_CONFIG = "spring.config"

# A directory with one of these is a module root (FR-3).
MODULE_ROOT_MANIFESTS: frozenset[str] = frozenset(
    {
        MANIFEST_PACKAGE_JSON,
        MANIFEST_POM,
        MANIFEST_BUILD_GRADLE,
        MANIFEST_BUILD_GRADLE_KTS,
    }
)

# Manifest names that make a directory scannable (FR-1 exit code 2). These are
# exactly the names from the Goal diagram, whether or not a reader exists yet.
# ``package-lock.json`` is deliberately absent: it carries versions for a
# ``package.json`` but is not a manifest a repo is scanned for on its own.
SUPPORTED_MANIFESTS: frozenset[str] = frozenset(
    {
        MANIFEST_PACKAGE_JSON,
        MANIFEST_ANGULAR_JSON,
        MANIFEST_TSCONFIG,
        MANIFEST_POM,
        MANIFEST_BUILD_GRADLE,
        MANIFEST_BUILD_GRADLE_KTS,
        MANIFEST_SETTINGS_GRADLE,
        MANIFEST_LIBS_VERSIONS,
        MANIFEST_GRADLE_PROPERTIES,
        MANIFEST_SPRING_CONFIG,
    }
)

# Extension → language tag for source extractors.
SOURCE_LANGUAGES: dict[str, str] = {
    ".ts": "ts",
    ".tsx": "tsx",
    ".js": "js",
    ".jsx": "jsx",
    ".mjs": "mjs",
    ".cjs": "cjs",
    ".html": "html",
    ".java": "java",
}

_JS_LANGUAGES = frozenset({"js", "jsx", "mjs", "cjs"})

# Test file patterns (FR-1: tests are included by default and flagged).
_TEST_FILE_RE = re.compile(r"\.(?:spec|test)\.[cm]?[jt]sx?$")
# ``src/test`` and every Gradle test source set named ``<name>Test`` —
# ``src/integrationTest``, ``src/componentTest``, ``src/acceptanceTest``,
# ``src/apiTest``, ``src/functionalTest``: test code and test config all the
# same. The capital ``T`` keeps ``src/latest/`` out. ``src/it`` is Maven's
# (maven-failsafe / maven-invoker) integration-test directory.
_TEST_DIR_RE = re.compile(
    r"(?:^|/)(?:src/(?:test|it|[a-z][A-Za-z0-9]*Test)|__tests__)/"
)

_SPRING_CONFIG_RE = re.compile(
    r"^(?:application|bootstrap)[\w.-]*\.(?:properties|ya?ml)$"
)
_TSCONFIG_RE = re.compile(r"^tsconfig[\w.-]*\.json$")


@dataclass(frozen=True)
class DiscoveredFile:
    """One file the scanner will read."""

    root: Path
    absolute: Path
    relative: str  # scan-root-relative, "/" separators
    role: str  # "manifest" | "source"
    kind: str  # manifest classification or source language tag
    module: str = "."  # owning module path
    test: bool = False

    @property
    def classification(self) -> str:
        return f"{self.role}:{self.kind}"

    def read_bytes(self) -> bytes | None:
        try:
            return self.absolute.read_bytes()
        except OSError:
            return None

    def read_text(self) -> str | None:
        try:
            return self.absolute.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None


@dataclass(frozen=True)
class Module:
    """One module root (FR-3)."""

    path: str  # "." for the scan root
    absolute: Path
    manifests: tuple[str, ...] = ()  # file names relative to the module root


@dataclass
class DiscoveryResult:
    root: Path
    files: list[DiscoveredFile] = field(default_factory=list)
    modules: list[Module] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    skipped: int = 0
    used_git: bool = False

    @property
    def manifests(self) -> list[DiscoveredFile]:
        return [file for file in self.files if file.role == "manifest"]

    @property
    def sources(self) -> list[DiscoveredFile]:
        return [file for file in self.files if file.role == "source"]

    @property
    def has_supported_manifest(self) -> bool:
        return any(file.kind in SUPPORTED_MANIFESTS for file in self.manifests)

    def module_for(self, path: str) -> Module:
        for module in sorted(
            self.modules, key=lambda item: len(item.path), reverse=True
        ):
            if (
                module.path == "."
                or path == module.path
                or path.startswith(module.path + "/")
            ):
                return module
        return Module(path=".", absolute=self.root)


# --- classification --------------------------------------------------------


def classify_manifest(name: str) -> str | None:
    """Manifest classification of a file *name*, ``None`` when it is not one."""
    if name == "package.json":
        return MANIFEST_PACKAGE_JSON
    if name == "package-lock.json":
        return MANIFEST_PACKAGE_LOCK
    if name == "angular.json":
        return MANIFEST_ANGULAR_JSON
    if name == "pom.xml":
        return MANIFEST_POM
    if name == "build.gradle":
        return MANIFEST_BUILD_GRADLE
    if name == "build.gradle.kts":
        return MANIFEST_BUILD_GRADLE_KTS
    if name in ("settings.gradle", "settings.gradle.kts"):
        return MANIFEST_SETTINGS_GRADLE
    if name == "libs.versions.toml":
        return MANIFEST_LIBS_VERSIONS
    if name == "gradle.properties":
        return MANIFEST_GRADLE_PROPERTIES
    if _SPRING_CONFIG_RE.match(name):
        return MANIFEST_SPRING_CONFIG
    if _TSCONFIG_RE.match(name):
        return MANIFEST_TSCONFIG
    return None


def classify_source(name: str) -> str | None:
    """Language tag of a source *name*, ``None`` when it is not a source."""
    return SOURCE_LANGUAGES.get(PurePosixPath(name).suffix.lower())


def is_test_path(relative: str) -> bool:
    """``*.spec.ts``, ``*.test.ts``, ``src/test/**``, ``src/it/**``, ``src/<name>Test/**`` (FR-1)."""
    return bool(_TEST_FILE_RE.search(relative) or _TEST_DIR_RE.search(relative))


def is_skipped_directory(relative_dir: str) -> bool:
    """Whether the directory ``relative_dir`` (or an ancestor) is skipped (FR-2)."""
    parts = [
        part for part in PurePosixPath(relative_dir).parts if part not in ("", ".")
    ]
    return _skipped_in(parts)


def _skipped_in(directory_parts: list[str] | tuple[str, ...]) -> bool:
    inside_src = False
    for part in directory_parts:
        name = part.lower()
        if name in ALWAYS_SKIPPED_DIRECTORIES:
            return True
        if name in BUILD_OUTPUT_DIRECTORIES and not inside_src:
            return True
        if name == _SOURCE_TREE_DIRECTORY:
            inside_src = True
    return False


def _skipped_parts(relative: str) -> bool:
    return _skipped_in(PurePosixPath(relative).parts[:-1])


# --- file lists ------------------------------------------------------------


@dataclass(frozen=True)
class _IgnoreRule:
    """One ``.gitignore`` pattern, scoped to the directory that holds the file."""

    base: str  # directory of the .gitignore, "" at the scan root
    pattern: str
    negated: bool = False
    dir_only: bool = False

    def matches(self, relative: str) -> bool:
        target = relative
        if self.base:
            if not relative.startswith(self.base + "/"):
                return False
            target = relative[len(self.base) + 1 :]
        pattern = self.pattern.strip("/")
        if not pattern:
            return False
        # A pattern with a slash is anchored to the ignore file's directory; a
        # bare name matches at any depth. Either way, a matching directory also
        # covers everything below it.
        candidates = [target] if "/" in pattern else [target] + target.split("/")
        parts = target.split("/")
        candidates.extend("/".join(parts[:index]) for index in range(1, len(parts)))
        for candidate in candidates:
            if fnmatch.fnmatchcase(candidate, pattern):
                return True
            if "/" not in pattern and fnmatch.fnmatchcase(
                candidate.rsplit("/", 1)[-1], pattern
            ):
                return True
        return False


def _read_gitignore(directory: Path, base: str) -> list[_IgnoreRule]:
    try:
        text = (directory / ".gitignore").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    rules: list[_IgnoreRule] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        negated = line.startswith("!")
        if negated:
            line = line[1:].strip()
        if not line:
            continue
        rules.append(
            _IgnoreRule(
                base=base,
                pattern=line,
                negated=negated,
                dir_only=line.endswith("/"),
            )
        )
    return rules


def _is_ignored(relative: str, rules: list[_IgnoreRule], *, is_dir: bool) -> bool:
    """Last matching rule wins, so ``!keep.ts`` can re-include a file."""
    ignored = False
    for rule in rules:
        if rule.dir_only and not is_dir:
            # ``vendor/`` ignores the directory and therefore its contents.
            if not any(
                rule.matches("/".join(relative.split("/")[:index]))
                for index in range(1, len(relative.split("/")))
            ):
                continue
        if rule.matches(relative):
            ignored = not rule.negated
    return ignored


def _git_worktree_root(root: Path) -> Path | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    top = completed.stdout.strip()
    return Path(top).resolve() if top else None


def _git_files(root: Path) -> list[str] | None:
    """Repo files relative to ``root``, or ``None`` when git cannot help."""
    if _git_worktree_root(root) is None:
        return None
    try:
        completed = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return [name for name in completed.stdout.split("\0") if name]


def _walk_files(root: Path) -> list[str]:
    """Walk the tree, honoring ``.gitignore`` files (AC-1.2: same file set as git).

    Each directory sees the rules of every ``.gitignore`` from the root down to
    itself, so ``a/.gitignore`` also applies to ``a/b/c.ts``.
    """
    found: list[str] = []
    rules_by_dir: dict[str, list[_IgnoreRule]] = {"": _read_gitignore(root, base="")}
    for directory, dirnames, filenames in os.walk(root):
        base = Path(directory)
        relative_dir = base.relative_to(root).as_posix()
        relative_dir = "" if relative_dir == "." else relative_dir
        if relative_dir not in rules_by_dir:
            parent = relative_dir.rsplit("/", 1)[0] if "/" in relative_dir else ""
            rules_by_dir[relative_dir] = rules_by_dir.get(parent, []) + _read_gitignore(
                base, base=relative_dir
            )
        rules = rules_by_dir[relative_dir]
        dirnames[:] = [
            name
            for name in sorted(dirnames)
            if not is_skipped_directory(
                f"{relative_dir}/{name}" if relative_dir else name
            )
            and not _is_ignored(
                f"{relative_dir}/{name}" if relative_dir else name, rules, is_dir=True
            )
        ]
        for name in sorted(filenames):
            relative = f"{relative_dir}/{name}" if relative_dir else name
            if _is_ignored(relative, rules, is_dir=False):
                continue
            found.append(relative)
    return found


def _first_line_is_huge(absolute: Path) -> bool:
    try:
        with absolute.open("rb") as handle:
            return len(handle.readline(MAX_JS_FIRST_LINE + 1)) > MAX_JS_FIRST_LINE
    except OSError:
        return False


# --- modules ---------------------------------------------------------------


def _module_roots(candidates: list[str]) -> dict[str, set[str]]:
    """``{module path: {manifest classification, …}}`` from module-root manifests."""
    roots: dict[str, set[str]] = {}
    for relative in candidates:
        path = PurePosixPath(relative)
        kind = classify_manifest(path.name)
        if kind not in MODULE_ROOT_MANIFESTS:
            continue
        directory = path.parent.as_posix() or "."
        roots.setdefault(directory, set()).add(kind)
    return roots


def _assign_module(relative: str, roots: list[str]) -> str:
    parent = PurePosixPath(relative).parent.as_posix()
    matches = [
        root
        for root in roots
        if root == "." or parent == root or parent.startswith(root + "/")
    ]
    if not matches:
        return "."
    # Longest match wins; "." only when nothing else matches.
    non_root = [root for root in matches if root != "."]
    if non_root:
        return max(non_root, key=len)
    return "."


# --- discovery -------------------------------------------------------------


def discover(
    path: str | Path,
    *,
    include_tests: bool = True,
) -> DiscoveryResult:
    """Discover the files of one repo and group them into modules.

    Never raises for a bad tree: unreadable files become ignored, oversized and
    generated files become diagnostics (FR-2).
    """
    root = Path(path).expanduser().resolve()
    result = DiscoveryResult(root=root)
    if not root.is_dir():
        return result

    listing = _git_files(root)
    if listing is not None:
        result.used_git = True
        names = listing
    else:
        names = _walk_files(root)

    relative_names = sorted(
        {
            name
            for name in names
            if not Path(name).is_absolute() and ".." not in PurePosixPath(name).parts
        }
    )
    existing = [
        name
        for name in relative_names
        if (root / name).is_file() and not _skipped_parts(name)
    ]

    roots = list(_module_roots(existing).keys())

    for relative in existing:
        absolute = root / relative
        name = PurePosixPath(relative).name
        manifest_kind = classify_manifest(name)
        language = classify_source(name)
        if manifest_kind is None and language is None:
            continue
        try:
            size = absolute.stat().st_size
        except OSError:
            continue
        limit = MAX_MANIFEST_BYTES if manifest_kind is not None else MAX_FILE_BYTES
        if size > limit:
            result.skipped += 1
            result.diagnostics.append(
                Diagnostic(
                    kind="file_too_large",
                    file=relative,
                    detail=f"{size} bytes > {limit}",
                )
            )
            continue
        if language in _JS_LANGUAGES and (
            name.endswith(".min.js") or _first_line_is_huge(absolute)
        ):
            result.skipped += 1
            result.diagnostics.append(
                Diagnostic(
                    kind="generated_js", file=relative, detail="minified or generated"
                )
            )
            continue
        is_test = is_test_path(relative)
        if is_test and not include_tests:
            result.skipped += 1
            continue
        result.files.append(
            DiscoveredFile(
                root=root,
                absolute=absolute,
                relative=relative,
                role="manifest" if manifest_kind else "source",
                kind=manifest_kind or str(language),
                module=_assign_module(relative, roots),
                test=is_test,
            )
        )

    result.modules = _build_modules(result.files, roots, root)
    return result


def _build_modules(
    files: list[DiscoveredFile],
    roots: list[str],
    root: Path,
) -> list[Module]:
    """One module per root, plus ``.`` when any file belongs to it (FR-3).

    ``.`` is always present when the tree has no module root at all; otherwise
    it is added only for files under no root, so those manifests still reach a
    reader and appear in ``modules[].manifests``.
    """
    if not roots:
        manifests = tuple(
            sorted(file.relative for file in files if file.role == "manifest")
        )
        return [Module(path=".", absolute=root, manifests=manifests)]
    module_paths = set(roots)
    if any(file.module == "." for file in files):
        module_paths.add(".")
    modules: list[Module] = []
    for module_path in sorted(module_paths):
        manifests = tuple(
            sorted(
                PurePosixPath(file.relative).relative_to(module_path).as_posix()
                if module_path != "."
                else file.relative
                for file in files
                if file.role == "manifest" and file.module == module_path
            )
        )
        absolute = root if module_path == "." else root / module_path
        modules.append(Module(path=module_path, absolute=absolute, manifests=manifests))
    return modules


__all__ = [
    "ALWAYS_SKIPPED_DIRECTORIES",
    "BUILD_OUTPUT_DIRECTORIES",
    "MAX_FILE_BYTES",
    "MAX_MANIFEST_BYTES",
    "MAX_JS_FIRST_LINE",
    "MODULE_ROOT_MANIFESTS",
    "SKIPPED_DIRECTORIES",
    "SOURCE_LANGUAGES",
    "SUPPORTED_MANIFESTS",
    "DiscoveredFile",
    "DiscoveryResult",
    "Module",
    "classify_manifest",
    "classify_source",
    "discover",
    "is_skipped_directory",
    "is_test_path",
]
