"""The service profile: model, merge, deterministic writer (spec 026 FR-9).

``.migration/profile.json`` records facts about one service, never decisions:
which framework and version, which dependencies, which external symbols and
members the code uses, which config keys it sets, which template tokens it
uses. Sections whose spec has not landed yet stay empty lists, so the schema is
stable while specs 2–9 add extractors.

Determinism: the JSON is written with sorted keys and every list is sorted, so
two scans of an unchanged tree differ only in ``generated.at``.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field

from migration_planner.scanner.contract import (
    ConfigFact,
    DependencyFact,
    Diagnostic,
    FileFacts,
    FrameworkFact,
    SCANNER_VERSION,
    Usage,
)

SCHEMA_VERSION = 1


# --- model -----------------------------------------------------------------


class Generated(BaseModel):
    """Who scanned what, when, and how long it took."""

    model_config = ConfigDict(populate_by_name=True)

    at: datetime
    scanner: str = SCANNER_VERSION
    root: str = "."
    files_scanned: int = 0
    files_skipped: int = 0
    duration_ms: int = 0


class FrameworkInfo(BaseModel):
    """One detected framework version."""

    name: str
    version: str = ""
    raw: str = ""
    source: str = ""


class ModuleEntry(BaseModel):
    """One module root and what the scanner knows about it."""

    path: str = "."
    manifests: list[str] = Field(default_factory=list)
    frameworks: list[FrameworkInfo] = Field(default_factory=list)
    # Filled by spec2 (angular.json), spec8 (Spring config files).
    angular_projects: list[str] = Field(default_factory=list)
    spring_config_files: list[str] = Field(default_factory=list)


class DependencyEntry(BaseModel):
    key: str
    name: str = ""
    range: str = ""
    version: str | None = None
    scope: str = "dependencies"
    module: str = "."
    kind: str = "dependency"  # dependency | bom | parent | plugin (spec6)


class LocationEntry(BaseModel):
    """One import site (or member access / template token) of a fact."""

    file: str
    line: int
    test: bool = False


class SymbolEntry(BaseModel):
    key: str
    count: int = 0
    files: int = 0
    type_only: bool = False
    locations: list[LocationEntry] = Field(default_factory=list)
    truncated: bool = False


class MemberEntry(BaseModel):
    key: str
    count: int = 0
    files: int = 0
    locations: list[LocationEntry] = Field(default_factory=list)
    truncated: bool = False


class UsageEntry(BaseModel):
    """A key used once per site with no member: side effect and wildcard imports."""

    key: str
    count: int = 0
    files: int = 0
    locations: list[LocationEntry] = Field(default_factory=list)
    truncated: bool = False


class ConfigEntry(BaseModel):
    """One occurrence of a config key (one entry per file / module / profile / line)."""

    key: str
    value: str | None = ""
    file: str = ""
    module: str = "."
    line: int | None = None
    raw_key: str | None = None
    profile: str | None = None
    kind: str | None = None
    test: bool = False


class TemplateEntry(BaseModel):
    key: str
    count: int = 0
    files: int = 0
    locations: list[LocationEntry] = Field(default_factory=list)
    truncated: bool = False


class DiagnosticEntry(BaseModel):
    kind: str
    file: str = ""
    line: int | None = None
    detail: str = ""


class Profile(BaseModel):
    """The whole profile file."""

    model_config = ConfigDict(populate_by_name=True)

    schema_version: int = Field(
        default=SCHEMA_VERSION,
        validation_alias="schema",
        serialization_alias="schema",
    )
    generated: Generated
    inputs_hash: str = ""
    framework: FrameworkInfo | None = None
    modules: list[ModuleEntry] = Field(default_factory=list)
    dependencies: list[DependencyEntry] = Field(default_factory=list)
    symbols: list[SymbolEntry] = Field(default_factory=list)
    members: list[MemberEntry] = Field(default_factory=list)
    side_effect_imports: list[UsageEntry] = Field(default_factory=list)
    wildcard_imports: list[UsageEntry] = Field(default_factory=list)
    config: list[ConfigEntry] = Field(default_factory=list)
    templates: list[TemplateEntry] = Field(default_factory=list)
    diagnostics: list[DiagnosticEntry] = Field(default_factory=list)

    def to_json(self) -> str:
        """Deterministic UTF-8 JSON: sorted keys, sorted lists, trailing newline."""
        payload = self.model_dump(mode="json", by_alias=True)
        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


# --- merge -----------------------------------------------------------------


def _sorted_locations(locations: Iterable[LocationEntry]) -> list[LocationEntry]:
    unique: dict[tuple[str, int], LocationEntry] = {}
    for location in locations:
        unique.setdefault((location.file, location.line), location)
    return [unique[key] for key in sorted(unique)]


def _files_of(locations: Iterable[LocationEntry]) -> int:
    return len({location.file for location in locations})


def _unique_usages(usages: Iterable[Usage]) -> list[Usage]:
    """One usage per ``(file, line)`` site; ``type_only`` is kept when any says so."""
    merged: dict[tuple[str, int], Usage] = {}
    for usage in usages:
        site = (usage.file, usage.line)
        previous = merged.get(site)
        if previous is None:
            merged[site] = usage
        elif not usage.type_only and previous.type_only:
            merged[site] = usage
    return [merged[site] for site in sorted(merged)]


class FactAccumulator:
    """Collects per-file and per-module fragments, then merges them (FR-9).

    Counting happens here, before ``--max-locations`` is applied, so ``count``
    is always exact and ``truncated`` says whether locations were dropped.
    """

    def __init__(self, *, max_locations: int = 20) -> None:
        self.max_locations = max(0, max_locations)
        self.dependencies: list[DependencyEntry] = []
        self.config: list[ConfigEntry] = []
        self.diagnostics: list[DiagnosticEntry] = []
        self.frameworks: dict[str, list[FrameworkInfo]] = {}
        self._symbols: dict[str, list[Usage]] = {}
        self._members: dict[str, list[Usage]] = {}
        self._side_effect: dict[str, list[Usage]] = {}
        self._wildcard: dict[str, list[Usage]] = {}
        self._templates: dict[str, list[Usage]] = {}

    # -- input ------------------------------------------------------------

    def add_file(self, facts: FileFacts) -> None:
        self._collect(self._symbols, facts.symbols)
        self._collect(self._members, facts.members)
        self._collect(self._side_effect, facts.side_effect_imports)
        self._collect(self._wildcard, facts.wildcard_imports)
        self._collect(self._templates, facts.templates)
        for diagnostic in facts.diagnostics:
            self.add_diagnostic(diagnostic)

    def add_dependency(self, dependency: DependencyFact) -> None:
        self.dependencies.append(
            DependencyEntry(
                key=dependency.key,
                name=dependency.name,
                range=dependency.range,
                version=dependency.version,
                scope=dependency.scope,
                module=dependency.module,
                kind=dependency.kind,
            )
        )

    def add_config(self, config: ConfigFact) -> None:
        self.config.append(
            ConfigEntry(
                key=config.key,
                value=config.value,
                file=config.file,
                module=config.module,
                line=config.line,
                raw_key=config.raw_key,
                profile=config.profile,
                kind=config.kind,
                test=config.test,
            )
        )

    def add_framework(self, module: str, framework: FrameworkFact) -> None:
        self.frameworks.setdefault(module, []).append(
            FrameworkInfo(
                name=framework.name,
                version=framework.version,
                raw=framework.raw,
                source=framework.source,
            )
        )

    def add_diagnostic(self, diagnostic: Diagnostic) -> None:
        self.diagnostics.append(
            DiagnosticEntry(
                kind=diagnostic.kind,
                file=diagnostic.file,
                line=diagnostic.line,
                detail=diagnostic.detail,
            )
        )

    @staticmethod
    def _collect(target: dict[str, list[Usage]], usages: Iterable[Usage]) -> None:
        for usage in usages:
            target.setdefault(usage.key, []).append(usage)

    # -- output -----------------------------------------------------------

    def symbol_entries(self) -> list[SymbolEntry]:
        return [
            SymbolEntry(
                key=key,
                count=count,
                files=files,
                type_only=type_only,
                locations=locations,
                truncated=count > len(locations),
            )
            for key, count, files, locations, type_only in self._entries(self._symbols)
        ]

    def member_entries(self) -> list[MemberEntry]:
        return [
            MemberEntry(
                key=key,
                count=count,
                files=files,
                locations=locations,
                truncated=count > len(locations),
            )
            for key, count, files, locations, _ in self._entries(self._members)
        ]

    def side_effect_entries(self) -> list[UsageEntry]:
        return self._usage_entries(self._side_effect)

    def wildcard_entries(self) -> list[UsageEntry]:
        return self._usage_entries(self._wildcard)

    def template_entries(self) -> list[TemplateEntry]:
        return [
            TemplateEntry(
                key=key,
                count=count,
                files=files,
                locations=locations,
                truncated=count > len(locations),
            )
            for key, count, files, locations, _ in self._entries(self._templates)
        ]

    def _usage_entries(self, target: dict[str, list[Usage]]) -> list[UsageEntry]:
        return [
            UsageEntry(
                key=key,
                count=count,
                files=files,
                locations=locations,
                truncated=count > len(locations),
            )
            for key, count, files, locations, _ in self._entries(target)
        ]

    def _entries(
        self, target: dict[str, list[Usage]]
    ) -> list[tuple[str, int, int, list[LocationEntry], bool]]:
        """``(key, count, files, capped locations, type_only)`` per key.

        ``count`` is the number of distinct sites, measured before
        ``--max-locations`` caps the stored ones, so a profile can say "this is
        everywhere, look at these few places" (FR-1, FR-9). Two identical
        usages on one line are one site, not two.
        """
        merged: list[tuple[str, int, int, list[LocationEntry], bool]] = []
        for key in sorted(target):
            usages = _unique_usages(target[key])
            locations = _sorted_locations(
                LocationEntry(file=usage.file, line=usage.line, test=usage.test)
                for usage in usages
            )
            type_only = all(usage.type_only for usage in usages)
            merged.append(
                (
                    key,
                    len(usages),
                    _files_of(locations),
                    locations[: self.max_locations],
                    type_only,
                )
            )
        return merged

    def dependency_entries(self) -> list[DependencyEntry]:
        """One entry per ``(key, module, scope, kind)``: a BOM import and a plain
        dependency on the same artifact are two facts (spec6)."""
        unique: dict[tuple[str, str, str, str], DependencyEntry] = {}
        for dependency in self.dependencies:
            unique.setdefault(
                (dependency.key, dependency.module, dependency.scope, dependency.kind),
                dependency,
            )
        return [unique[key] for key in sorted(unique)]

    def config_entries(self) -> list[ConfigEntry]:
        """One entry per occurrence ``(key, module, file, profile, line)``.

        Only exact repeats of one occurrence collapse; the same key in two
        modules, files or Spring profiles stays two entries (FR-8a).
        """
        unique: dict[tuple[str, str, str, str, int], ConfigEntry] = {}
        for entry in self.config:
            unique.setdefault(
                (
                    entry.key,
                    entry.module,
                    entry.file,
                    entry.profile or "",
                    entry.line or 0,
                ),
                entry,
            )
        return [unique[key] for key in sorted(unique)]

    def diagnostic_entries(self) -> list[DiagnosticEntry]:
        unique: dict[tuple[str, str, int | None, str], DiagnosticEntry] = {}
        for entry in self.diagnostics:
            unique.setdefault((entry.kind, entry.file, entry.line, entry.detail), entry)
        return [
            unique[key]
            for key in sorted(
                unique, key=lambda item: (item[1], item[2] or 0, item[0], item[3])
            )
        ]


# --- framework choice ------------------------------------------------------


def choose_framework(
    frameworks_by_module: dict[str, list[FrameworkInfo]],
) -> tuple[FrameworkInfo | None, list[Diagnostic]]:
    """The repo-level framework: the one found in most modules (FR-3).

    Ties are listed in ``diagnostics`` and broken by name, so the choice stays
    deterministic.
    """
    counts: dict[str, list[FrameworkInfo]] = {}
    for module in sorted(frameworks_by_module):
        seen: set[str] = set()
        for framework in frameworks_by_module[module]:
            if framework.name in seen:
                continue
            seen.add(framework.name)
            counts.setdefault(framework.name, []).append(framework)
    if not counts:
        return None, []
    best = max(len(found) for found in counts.values())
    winners = sorted(name for name, found in counts.items() if len(found) == best)
    diagnostics: list[Diagnostic] = []
    if len(winners) > 1:
        diagnostics.append(
            Diagnostic(
                kind="framework_tie",
                detail=", ".join(
                    f"{name} ({len(counts[name])} modules)" for name in winners
                ),
            )
        )
    winner = winners[0]
    return counts[winner][0], diagnostics


# --- inputs hash -----------------------------------------------------------


def inputs_hash(
    entries: Iterable[tuple[str, bytes]],
    scanner_version: str = SCANNER_VERSION,
    options: dict[str, object] | None = None,
) -> str:
    """``sha256:…`` over sorted ``(path, sha256(content))``, the scanner version
    and the scan options that change the output (``--max-locations``,
    ``--include-tests``, …), so a re-scan with other options is never
    reported ``unchanged`` (spec9)."""
    digest = hashlib.sha256()
    rows = sorted(
        (path, hashlib.sha256(content).hexdigest()) for path, content in entries
    )
    for path, content_digest in rows:
        digest.update(f"{path}\0{content_digest}\n".encode("utf-8"))
    digest.update(f"scanner\0{scanner_version}\n".encode("utf-8"))
    for name in sorted(options or {}):
        digest.update(f"option\0{name}={(options or {})[name]!r}\n".encode("utf-8"))
    return f"sha256:{digest.hexdigest()}"


# --- writer ----------------------------------------------------------------


def default_profile_path(root: str | Path) -> Path:
    """``<root>/.migration/profile.json`` (FR-1)."""
    return Path(root) / ".migration" / "profile.json"


def write_profile(profile: Profile, path: str | Path) -> Path:
    """Write atomically: a crashed scan never leaves a half-written profile."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = profile.to_json()
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
        delete=False,
    )
    try:
        with handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, target)
    except BaseException:
        try:
            os.unlink(handle.name)
        except OSError:
            pass
        raise
    return target


def utc_now() -> datetime:
    """The one timestamp in the profile, second precision (deterministic writes)."""
    return datetime.now(timezone.utc).replace(microsecond=0)


# --- summary ---------------------------------------------------------------


class Summary(BaseModel):
    """The one stdout line (FR-1), also available as JSON with ``--json-summary``."""

    files_scanned: int = 0
    files_skipped: int = 0
    framework: str | None = None
    framework_version: str = ""
    dependencies: int = 0
    symbols: int = 0
    members: int = 0
    config: int = 0
    template_tokens: int = 0
    diagnostics: int = 0
    out: str = ""
    duration_ms: int = 0
    unchanged: bool = False
    gitignore_hint: bool = False

    def text(self) -> str:
        """``scanned 4812 files · angular 19.2.0 · 61 deps · … (2.4 s)``."""
        framework = (
            f"{self.framework} {self.framework_version}".strip()
            if self.framework
            else "no framework"
        )
        parts = [
            f"scanned {self.files_scanned} files",
            framework,
            f"{self.dependencies} deps",
            f"{self.symbols} symbols",
            f"{self.members} members",
            f"{self.config} config",
            f"{self.template_tokens} template tokens",
            f"{self.diagnostics} diagnostics",
        ]
        line = " · ".join(parts)
        suffix = "unchanged" if self.unchanged else f"({self.duration_ms / 1000:.1f} s)"
        return f"{line} → {self.out} {suffix}".rstrip()


__all__ = [
    "SCHEMA_VERSION",
    "ConfigEntry",
    "DependencyEntry",
    "DiagnosticEntry",
    "FactAccumulator",
    "FrameworkInfo",
    "Generated",
    "LocationEntry",
    "MemberEntry",
    "ModuleEntry",
    "Profile",
    "Summary",
    "SymbolEntry",
    "TemplateEntry",
    "UsageEntry",
    "choose_framework",
    "default_profile_path",
    "inputs_hash",
    "utc_now",
    "write_profile",
]
