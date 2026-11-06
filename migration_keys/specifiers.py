"""Import-specifier rules shared by the scanner (026) and the canonicalizer (025).

A specifier is what an ``import`` statement names: ``'./app/core'``,
``'@app/shared'``, ``'@angular/core/testing'`` or ``'rxjs/internal/operators'``.
Two different questions are answered here, and getting them apart is the whole
point of the module:

- **Which package is this?** For an external specifier, ``@angular/core/testing``
  is its own package (an Angular entry point, 025 FR-1), while ``rxjs/internal/x``
  is a deep file import that the graph does not key on. The answer is the
  *package key*.
- **Is it our own code?** A relative path, a ``tsconfig`` ``paths`` alias and a
  workspace package name are all the service's own code and never become a fact.

Pure string handling: no path probing, no file system. Resolution of own-code
specifiers to real files is the scanner's job (spec4), not this module's.
"""

from __future__ import annotations

from typing import Iterable, Mapping, Sequence

# A specifier that starts like a relative path or an absolute one.
_RELATIVE_PREFIXES: tuple[str, ...] = ("./", "../", ".", "..", "/")

# A Node builtin is not an npm dependency and never has a lockfile version.
NODE_BUILTIN_PREFIXES: tuple[str, ...] = ("node:",)

# Builtins that are also importable without the ``node:`` prefix.
NODE_BUILTINS: frozenset[str] = frozenset(
    {
        "assert",
        "buffer",
        "child_process",
        "cluster",
        "console",
        "constants",
        "crypto",
        "dgram",
        "dns",
        "domain",
        "events",
        "fs",
        "http",
        "http2",
        "https",
        "inspector",
        "module",
        "net",
        "os",
        "path",
        "perf_hooks",
        "process",
        "punycode",
        "querystring",
        "readline",
        "repl",
        "stream",
        "string_decoder",
        "timers",
        "tls",
        "trace_events",
        "tty",
        "url",
        "util",
        "v8",
        "vm",
        "worker_threads",
        "zlib",
    }
)


def is_relative_specifier(specifier: str) -> bool:
    """``./x``, ``../x``, ``.``, ``..`` and absolute paths."""
    return specifier.startswith(_RELATIVE_PREFIXES)


def is_node_builtin(
    specifier: str, *, declared_dependencies: Iterable[str] = ()
) -> bool:
    """``node:fs`` and bare ``fs`` / ``path``. Not an npm dependency.

    A bare name that is also an npm package (``events``, ``buffer``, ``util``,
    ``url``, ``process``, … are common browser polyfills) is a builtin only when
    the repo does not declare it as a dependency. ``node:`` is always a builtin.
    """
    if specifier.startswith(NODE_BUILTIN_PREFIXES):
        return True
    if specifier.startswith("@"):
        return False
    head = specifier.split("/", 1)[0]
    if head not in NODE_BUILTINS:
        return False
    return head not in set(declared_dependencies)


def dependency_name(specifier: str) -> str:
    """The npm dependency a specifier belongs to: ``@scope/name`` or ``name``.

    ``@angular/core/testing`` → ``@angular/core``; ``rxjs/internal/x`` →
    ``rxjs``. For a dependency key (026 FR-4) this is what the lockfile is
    looked up by.
    """
    parts = specifier.split("/")
    if specifier.startswith("@") and len(parts) >= 2:
        return "/".join(parts[:2])
    return parts[0]


def package_of_specifier(specifier: str) -> str:
    """The package key an external specifier belongs to (025 FR-1, 026 FR-5).

    The specifier is the package, **as written** (spec3 FR-5): Angular entry
    points such as ``@angular/core/testing`` are packages in 025, and deep file
    imports (``rxjs/internal/operators``, ``lodash/fp.js``) are kept verbatim so
    a rule about a deep import can match it. The dependency a specifier belongs
    to is :func:`dependency_name`.

    Relative and builtin specifiers are returned unchanged; callers check
    :func:`is_relative_specifier` / :func:`is_node_builtin` first.
    """
    return specifier


def is_own_code(
    specifier: str,
    *,
    own_packages: Iterable[str] = (),
    path_aliases: Iterable[str] = (),
    base_url_roots: Iterable[str] = (),
    declared_dependencies: Iterable[str] = (),
) -> bool:
    """Whether a specifier names the scanned repo's own code (026 FR-5).

    ``own_packages`` are workspace / ``package.json`` names; ``path_aliases``
    are the ``compilerOptions.paths`` keys, which may carry one ``*``.
    ``base_url_roots`` are the entries directly under ``compilerOptions.baseUrl``
    (``app`` for ``src/app/``): with ``baseUrl: "./src"``, ``'app/core/x'`` is
    own code. A declared dependency of the same name wins, because TypeScript
    would then resolve the package. A Node builtin is neither own code nor an
    external package: it is skipped.
    """
    declared = set(declared_dependencies)
    if is_relative_specifier(specifier):
        return True
    if is_node_builtin(specifier, declared_dependencies=declared):
        return True
    for package in own_packages:
        if specifier == package or specifier.startswith(package + "/"):
            return True
    if matches_path_alias(specifier, path_aliases):
        return True
    roots = set(base_url_roots)
    if roots and not specifier.startswith("@"):
        head = specifier.split("/", 1)[0]
        if head in roots and dependency_name(specifier) not in declared:
            return True
    return False


def matches_path_alias(specifier: str, patterns: Iterable[str]) -> bool:
    """Whether a specifier matches one ``compilerOptions.paths`` key.

    ``@app/*`` matches ``@app/core`` and ``@app/core/deep``; an exact key like
    ``@shared`` matches only itself. The longest matching pattern wins in
    TypeScript, but for "is this our own code" any match is enough.
    """
    for pattern in patterns:
        if not pattern:
            continue
        if pattern == specifier:
            return True
        star = pattern.find("*")
        if star < 0:
            continue
        prefix, suffix = pattern[:star], pattern[star + 1 :]
        if (
            len(specifier) >= len(prefix) + len(suffix)
            and specifier.startswith(prefix)
            and specifier.endswith(suffix)
        ):
            return True
    return False


def resolve_path_alias(
    specifier: str,
    paths: Mapping[str, Sequence[str]],
    *,
    paths_dir: str = ".",
) -> list[str]:
    """Candidate repo-relative paths for an aliased specifier, best first (spec4).

    TypeScript picks the pattern with the longest matched prefix; within a
    pattern the targets are tried in order until one exists. ``*`` is
    substituted into each target, so ``@app/*`` + ``src/app/*`` + ``@app/core``
    gives ``src/app/core``. The result is relative to the scan root and still
    needs an extension / ``index`` probe.
    """
    best: tuple[int, Sequence[str], str] | None = None
    for pattern, targets in paths.items():
        star = pattern.find("*")
        if star < 0:
            if pattern != specifier:
                continue
            score = len(pattern)
            capture = ""
        else:
            prefix, suffix = pattern[:star], pattern[star + 1 :]
            if len(specifier) < len(prefix) + len(suffix):
                continue
            if not specifier.startswith(prefix) or not specifier.endswith(suffix):
                continue
            capture = specifier[len(prefix) : len(specifier) - len(suffix)]
            score = len(prefix)
        if best is None or score > best[0]:
            best = (score, targets, capture)
    if best is None:
        return []
    _, targets, capture = best
    results: list[str] = []
    for target in targets:
        if "*" in target:
            substituted = target.replace("*", capture)
        elif capture:
            substituted = f"{target.rstrip('/')}/{capture}"
        else:
            substituted = target
        results.append(join_path(paths_dir, substituted))
    return results


def join_path(base: str, relative: str) -> str:
    """Join and normalize two ``/``-separated repo paths."""
    if not base or base == ".":
        return normalize_path(relative)
    return normalize_path(f"{base}/{relative}")


def normalize_path(path: str) -> str:
    """Resolve ``.`` and ``..`` segments in a ``/``-separated repo path."""
    parts: list[str] = []
    for part in path.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if parts and parts[-1] != "..":
                parts.pop()
            else:
                parts.append("..")
            continue
        parts.append(part)
    return "/".join(parts) or "."


__all__ = [
    "NODE_BUILTINS",
    "NODE_BUILTIN_PREFIXES",
    "dependency_name",
    "is_node_builtin",
    "is_own_code",
    "is_relative_specifier",
    "join_path",
    "matches_path_alias",
    "normalize_path",
    "package_of_specifier",
    "resolve_path_alias",
]
