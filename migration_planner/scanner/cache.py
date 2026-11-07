"""Incremental scan cache (spec 026 FR-10).

A warm scan must not re-parse a codebase that did not change, and its profile
must be the one a `--force` scan writes. The cache is what makes that possible:
`.migration/scan-cache.json` stores, per source file, the file's stat signature
(`size`, `mtime_ns`), the content `sha256` and the extractor's per-file facts.

Why the whole :class:`~migration_planner.scanner.contract.FileFacts` is stored,
not a digest of it: post-passes (barrels, own packages) run on the collected
facts every scan, so a reused file must contribute exactly what a re-parse
would.

Invalidation, in the order the scan checks it:

- **scanner version** — a parser or merge change bumps
  :data:`~migration_planner.scanner.contract.SCANNER_VERSION`; a cache written
  by another version is dropped whole.
- **module environment** — an extractor's output also depends on what the
  manifest readers learned *about the module* (own package names, the tsconfig
  path map, declared groupIds). Editing a `package.json` must not leave stale
  facts behind, so each entry records a digest of its module's `ModuleEnv`
  and a changed digest forces a re-parse.
- **extractor identity** — one language tag can be handled by a different
  extractor (a caller registering its own, a later spec swapping the parser), so
  the entry names the extractor that produced the facts.
- **stat signature** — a file whose `(size, mtime_ns)` is unchanged is not even
  read: its stored `sha256` feeds `inputs_hash`.
- **content hash** — a file whose stat moved (a `touch`, a rewrite with the same
  length) is read and hashed; an unchanged hash reuses the facts.

The cache lives next to the profile, not always under the scan root: a scan with
`--out /tmp/x/profile.json` must leave the service's work tree untouched, which
is how the AC-11 runs were made. With the default `--out` that is
`<root>/.migration/scan-cache.json`, as the spec says; outside the repo the name
carries a digest of the root (``scan.cache_path_for``), and the cache records
its root, so one output directory can serve several services.

A file whose mtime is within :data:`RACY_WINDOW_NS` of the caching scan's start
is not trusted by its stat alone (:meth:`ScanCache.is_racy`).

Writes are atomic (temp file + rename), like the profile writer, and a broken
cache is one `cache_corrupt` *run* diagnostic plus a full scan — never a failed
scan, and never a fact in the profile.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from migration_planner.scanner.contract import (
    Diagnostic,
    ExportBinding,
    FileFacts,
    ModuleEnv,
    OwnImport,
    OwnMember,
    SCANNER_VERSION,
    Usage,
)
from migration_planner.scanner.profile import atomic_write_text

#: File name of the cache, inside the profile's directory (FR-10).
CACHE_NAME = "scan-cache.json"

#: Shape of one entry's encoded facts. Bumped with SCANNER_VERSION when the
#: encoding changes; a mismatch is a full scan, never a wrong profile.
#: 2: the cache records its root and the time its scan started.
CACHE_SCHEMA = 2

#: How close to the cache's scan a file's mtime may be before its stat is no
#: longer trusted. A file rewritten with the same size within the filesystem's
#: timestamp granularity of the scan that cached it would otherwise keep its
#: old facts (git's "racily clean" case); 2 s covers FAT, 1 s ext3 / HFS+.
RACY_WINDOW_NS = 2_000_000_000


# --- environment digest ----------------------------------------------------


def _jsonable(value: Any) -> Any:
    """A ``ModuleEnv`` field as order-stable JSON data (dataclasses recursively)."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _jsonable(getattr(value, item.name))
            for item in dataclasses.fields(value)
        }
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (set, frozenset)):
        return sorted(_jsonable(item) for item in value)
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def environment_digest(env: ModuleEnv) -> str:
    """``sha256:…`` over **every** field of ``ModuleEnv``.

    A different digest means the same file bytes may extract differently (a
    new own-package name, a new path alias, another declared groupId), so its
    cached facts are not reused. The fields are taken from the dataclass, not
    listed here, so a field a later spec adds to ``ModuleEnv`` invalidates the
    cache by itself instead of silently being ignored.
    """
    encoded = json.dumps(_jsonable(env), sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def extractor_id(extractor: object | None) -> str:
    """A stable name for the extractor that produced an entry's facts."""
    if extractor is None:
        return ""
    module = getattr(extractor, "__module__", "") or ""
    name = getattr(extractor, "__qualname__", None) or repr(extractor)
    return f"{module}.{name}" if module else str(name)


# --- facts encoding --------------------------------------------------------
#
# Facts travel through JSON, so every record becomes a small list. The encoding
# is positional to keep the cache small (a thousand-file service stores tens of
# thousands of usages); CACHE_SCHEMA guards the shape.
#
# A fact's ``file`` is not stored: every fact in one :class:`FileFacts` belongs
# to the file it is cached under (an extractor only reports facts about the file
# it was given), so it is restored from the key on load. That alone halves the
# cache on a Java service, where each usage would otherwise repeat a long path.


def _encode_usage(usage: Usage) -> list[Any]:
    return [
        usage.key,
        usage.line,
        int(usage.test),
        int(usage.type_only),
        list(usage.names),
    ]


def _decode_usage(row: Sequence[Any], relative: str) -> Usage:
    key, line, test, type_only, names = row
    return Usage(
        key=str(key),
        file=relative,
        line=int(line),
        test=bool(test),
        type_only=bool(type_only),
        names=tuple(str(name) for name in names),
    )


def _encode_diagnostic(diagnostic: Diagnostic) -> list[Any]:
    return [diagnostic.kind, diagnostic.line, diagnostic.detail]


def _decode_diagnostic(row: Sequence[Any], relative: str) -> Diagnostic:
    kind, line, detail = row
    return Diagnostic(
        kind=str(kind),
        file=relative,
        line=None if line is None else int(line),
        detail=str(detail),
    )


def _encode_binding(binding: ExportBinding) -> list[Any]:
    return [binding.specifier, binding.original]


def _decode_binding(row: Sequence[Any]) -> ExportBinding:
    specifier, original = row
    return ExportBinding(specifier=str(specifier), original=str(original))


def _encode_own_import(own: OwnImport) -> list[Any]:
    return [
        own.relative,
        own.line,
        int(own.test),
        own.specifier,
        int(own.is_relative),
        dict(own.named),
        own.default,
        own.namespace,
        int(own.type_only),
        sorted(own.type_names),
    ]


def _decode_own_import(row: Sequence[Any]) -> OwnImport:
    (
        relative,
        line,
        test,
        specifier,
        is_relative,
        named,
        default,
        namespace,
        type_only,
        type_names,
    ) = row
    return OwnImport(
        relative=str(relative),
        line=int(line),
        test=bool(test),
        specifier=str(specifier),
        is_relative=bool(is_relative),
        named={str(key): str(value) for key, value in dict(named).items()},
        default=str(default),
        namespace=str(namespace),
        type_only=bool(type_only),
        type_names=frozenset(str(name) for name in type_names),
    )


def _encode_own_member(member: OwnMember) -> list[Any]:
    return [
        member.relative,
        member.line,
        int(member.test),
        member.local,
        member.member,
        member.symbol,
    ]


def _decode_own_member(row: Sequence[Any]) -> OwnMember:
    relative, line, test, local, member, symbol = row
    return OwnMember(
        relative=str(relative),
        line=int(line),
        test=bool(test),
        local=str(local),
        member=str(member),
        symbol=str(symbol),
    )


def encode_facts(facts: FileFacts) -> dict[str, Any]:
    """One :class:`FileFacts` as JSON-ready data (used by the cache and the pool)."""
    return {
        "symbols": [_encode_usage(usage) for usage in facts.symbols],
        "members": [_encode_usage(usage) for usage in facts.members],
        "side_effect_imports": [
            _encode_usage(usage) for usage in facts.side_effect_imports
        ],
        "wildcard_imports": [
            _encode_usage(usage) for usage in facts.wildcard_imports
        ],
        "templates": [_encode_usage(usage) for usage in facts.templates],
        "diagnostics": [
            _encode_diagnostic(diagnostic) for diagnostic in facts.diagnostics
        ],
        "own_imports": facts.own_imports,
        "export_map": {
            name: _encode_binding(binding)
            for name, binding in facts.export_map.items()
        },
        "star_exports": list(facts.star_exports),
        "namespace_exports": dict(facts.namespace_exports),
        "local_declarations": sorted(facts.local_declarations),
        "package_name": facts.package_name,
        "own_import_bindings": [
            _encode_own_import(own) for own in facts.own_import_bindings
        ],
        "own_member_bindings": [
            _encode_own_member(member) for member in facts.own_member_bindings
        ],
    }


def decode_facts(payload: Mapping[str, Any], relative: str) -> FileFacts:
    """The inverse of :func:`encode_facts`; raises ``KeyError`` / ``TypeError``
    / ``ValueError`` on a payload that does not match :data:`CACHE_SCHEMA`.

    ``relative`` is the path the facts were cached under: an extractor only
    reports facts about the file it was given, so the file is not stored per
    fact and is restored here.
    """
    return FileFacts(
        symbols=[_decode_usage(row, relative) for row in payload["symbols"]],
        members=[_decode_usage(row, relative) for row in payload["members"]],
        side_effect_imports=[
            _decode_usage(row, relative) for row in payload["side_effect_imports"]
        ],
        wildcard_imports=[
            _decode_usage(row, relative) for row in payload["wildcard_imports"]
        ],
        templates=[_decode_usage(row, relative) for row in payload["templates"]],
        diagnostics=[
            _decode_diagnostic(row, relative) for row in payload["diagnostics"]
        ],
        own_imports=int(payload["own_imports"]),
        export_map={
            str(name): _decode_binding(row)
            for name, row in dict(payload["export_map"]).items()
        },
        star_exports=[str(item) for item in payload["star_exports"]],
        namespace_exports={
            str(name): str(target)
            for name, target in dict(payload["namespace_exports"]).items()
        },
        local_declarations={
            str(name) for name in payload["local_declarations"]
        },
        package_name=(
            None if payload["package_name"] is None else str(payload["package_name"])
        ),
        own_import_bindings=[
            _decode_own_import(row) for row in payload["own_import_bindings"]
        ],
        own_member_bindings=[
            _decode_own_member(row) for row in payload["own_member_bindings"]
        ],
    )


# --- one entry -------------------------------------------------------------


@dataclass(frozen=True)
class CachedFile:
    """The cache's knowledge of one source file (FR-10)."""

    size: int
    mtime_ns: int
    sha256: str
    environment: str = ""
    extractor: str = ""
    facts: FileFacts = field(default_factory=FileFacts)

    def matches_stat(self, size: int, mtime_ns: int) -> bool:
        """Whether the file can be trusted without reading it."""
        return self.size == size and self.mtime_ns == mtime_ns

    def usable(self, *, environment: str, extractor: str) -> bool:
        """Whether these facts were produced under the current environment."""
        return self.environment == environment and self.extractor == extractor

    def to_payload(self) -> dict[str, Any]:
        return {
            "size": self.size,
            "mtime_ns": self.mtime_ns,
            "sha256": self.sha256,
            "env": self.environment,
            "extractor": self.extractor,
            "facts": encode_facts(self.facts),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any], relative: str) -> "CachedFile":
        return cls(
            size=int(payload["size"]),
            mtime_ns=int(payload["mtime_ns"]),
            sha256=str(payload["sha256"]),
            environment=str(payload.get("env", "")),
            extractor=str(payload.get("extractor", "")),
            facts=decode_facts(dict(payload["facts"]), relative),
        )


# --- the cache -------------------------------------------------------------


class ScanCache:
    """Per-file facts of one repo, as loaded from / written to disk (FR-10).

    ``dirty`` says whether anything changed, so a warm scan that parsed nothing
    does not rewrite a multi-megabyte file for no reason.
    """

    def __init__(
        self,
        path: Path,
        entries: Mapping[str, CachedFile] | None = None,
        *,
        dirty: bool = False,
        root: Path | str | None = None,
        started_ns: int = 0,
    ) -> None:
        self.path = path
        self.entries: dict[str, CachedFile] = dict(entries or {})
        self.dirty = dirty
        #: The scanned repo, so a cache is never used for another one.
        self.root = "" if root is None else str(root)
        #: When the scan that wrote the cache started (see :meth:`is_racy`).
        self.started_ns = started_ns

    # -- loading ----------------------------------------------------------

    @classmethod
    def empty(cls, path: Path, *, root: Path | str | None = None) -> "ScanCache":
        # A new (or replaced) cache must be written even if no entry changes.
        return cls(path, root=root, dirty=True)

    @classmethod
    def load(
        cls, path: Path, *, root: Path | str | None = None
    ) -> tuple["ScanCache", list[Diagnostic]]:
        """Read the cache at ``path``.

        A missing file is simply an empty cache (the first scan). A file that
        cannot be read or does not parse is ``cache_corrupt`` — one diagnostic
        and a full scan (FR-10), because a wrong cache is worse than none.
        """
        empty = cls.empty(path, root=root)
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return empty, []
        except OSError as exc:
            return empty, [_corrupt(path, f"{type(exc).__name__}: {exc}")]
        try:
            payload = json.loads(text)
            return cls._from_payload(path, payload, root=root), []
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            return empty, [_corrupt(path, f"{type(exc).__name__}: {exc}")]

    @classmethod
    def _from_payload(
        cls, path: Path, payload: Any, *, root: Path | str | None = None
    ) -> "ScanCache":
        if not isinstance(payload, dict):
            raise TypeError("cache root is not an object")
        if payload.get("scanner") != SCANNER_VERSION:
            # Another version wrote it: drop it whole, silently (FR-10).
            return cls.empty(path, root=root)
        if payload.get("schema") != CACHE_SCHEMA:
            return cls.empty(path, root=root)
        if root is not None and payload.get("root") != str(root):
            # Another repo's cache (a shared `--out` directory): not ours to use.
            return cls.empty(path, root=root)
        raw_entries = payload.get("files")
        if not isinstance(raw_entries, dict):
            raise TypeError("cache entries are not an object")
        entries = {
            str(relative): CachedFile.from_payload(entry, str(relative))
            for relative, entry in raw_entries.items()
        }
        return cls(
            path,
            entries,
            root=payload.get("root", ""),
            started_ns=int(payload.get("started_ns", 0)),
        )

    # -- reading ----------------------------------------------------------

    def is_racy(self, mtime_ns: int) -> bool:
        """Whether a file's stat is too close to the caching scan to trust.

        A file modified within :data:`RACY_WINDOW_NS` of the start of the scan
        that cached it (or after it) may have changed again in the same
        timestamp tick, keeping its size and mtime. Such a file is read and
        hashed instead; an unchanged hash still reuses its facts, so the cost
        is one read, never a re-parse.
        """
        return mtime_ns >= self.started_ns - RACY_WINDOW_NS

    def get(self, relative: str) -> CachedFile | None:
        return self.entries.get(relative)

    def __len__(self) -> int:
        return len(self.entries)

    # -- writing ----------------------------------------------------------

    def put(self, relative: str, entry: CachedFile) -> None:
        if self.entries.get(relative) != entry:
            self.entries[relative] = entry
            self.dirty = True

    def prune(self, keep: Iterable[str]) -> None:
        """Forget files that are no longer discovered (deleted, or now ignored)."""
        wanted = set(keep)
        stale = [relative for relative in self.entries if relative not in wanted]
        for relative in stale:
            del self.entries[relative]
        if stale:
            self.dirty = True

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema": CACHE_SCHEMA,
            "scanner": SCANNER_VERSION,
            "root": self.root,
            "started_ns": self.started_ns,
            "files": {
                relative: entry.to_payload()
                for relative, entry in self.entries.items()
            },
        }

    def save(self) -> Path | None:
        """Write atomically when something changed; ``None`` when nothing was written."""
        if not self.dirty:
            return None
        payload = json.dumps(
            self.to_payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        written = atomic_write_text(self.path, payload + "\n")
        self.dirty = False
        return written


def _corrupt(path: Path, detail: str) -> Diagnostic:
    return Diagnostic(kind="cache_corrupt", file=path.name, detail=detail)


__all__ = [
    "CACHE_NAME",
    "CACHE_SCHEMA",
    "CachedFile",
    "ScanCache",
    "decode_facts",
    "encode_facts",
    "environment_digest",
    "extractor_id",
]
