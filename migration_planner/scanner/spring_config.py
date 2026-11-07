"""Spring Boot configuration files: canonical config keys (spec 026.8, FR-8a).

Many Spring Boot rules are property renames or default changes
(``spring.data.mongodb.*`` → ``spring.mongodb.*``), so *which properties the
service sets* is a fact the matcher needs. This reader turns every
``application*`` / ``bootstrap*`` file of a Java module into ``config[]`` facts.

What becomes a fact
-------------------

One entry per occurrence of one key in one place::

    { "key": "cfg:application.properties#spring.data.mongodb.authentication-database",
      "value": "admin", "file": "src/main/resources/application-prod.yml",
      "module": ".", "profile": "prod", "kind": "application", "test": false,
      "line": 7, "raw_key": "authenticationDatabase" }

- **Key**: the canonical form (Spring relaxed binding) under the one file name
  rules use, ``cfg:application.properties#…``, whichever file the property is
  really in (025 FR-2.6). ``file`` keeps the real path, so a matcher can still
  say "set only in test".
- **Occurrences are never merged**: the same key in two profiles, modules or
  files is two entries. ``spring.datasource.url`` in ``application-prod.yml``
  and in ``src/test/resources/application.yml`` are different facts.
- **``profile``** comes from the file name (``application-prod.yml`` → ``prod``,
  else ``default``) or, for a multi-document file (YAML ``---``, properties
  ``#---``), from a document's ``spring.config.activate.on-profile`` (or the
  pre-2.4 ``spring.profiles``). ``spring.profiles.active`` activates a profile
  and leaves its document's profile alone.
- **``kind``** is ``application`` or ``bootstrap``. Bootstrap keys are recorded
  like any other — a rule names the property, not the file — and the files
  themselves are listed in ``modules[].spring_config_files``, because "this
  service still has a ``bootstrap.yml``" is a fact of its own (`it needs
  spring-cloud-starter-bootstrap since 2.4`).
- **``test``** is true for anything under ``src/test/`` or a test source set
  such as ``src/integrationTest/`` (the discovery rule, FR-1).

Parsing
-------

``.properties`` is Java's format and gets a small parser here: ``=``, ``:`` and
whitespace separators, ``#`` / ``!`` comments, ``\\`` line continuation and
``\\uXXXX`` escapes. ``.yml`` / ``.yaml`` uses PyYAML's ``compose`` step, so a
key's line number is its real mark in the file and anchors / merge keys are
resolved by the loader rather than re-implemented. A leading BOM, a nested map
flattened to ``a.b.c``, a list to ``key[0].sub`` — all handled.

Secrets never reach the profile
-------------------------------

A value is ``"<redacted>"`` when the key's last segment names a credential
(``password``, ``secret``, ``token``, ``client-secret`` …) or when it contains a
URL with user info (``jdbc:postgresql://user:pass@host/db``). A placeholder such
as ``${DB_PASSWORD}`` is kept exactly as written: it is a reference, not a
secret, and resolving it is not the scanner's job. Values are truncated to 200
characters; lists and maps become keys only. ``--no-values`` stores no value at
all.

Nothing here fails a scan: a file that cannot be parsed is a diagnostic and the
other files of the module are still read.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Iterable, Sequence

from migration_keys.keys import cfg_key
from migration_keys.spring import (
    MAX_VALUE_LENGTH,
    SPRING_CONFIG_FILE,
    canonical_key,
    config_file_for_spring_key,
    is_secret_key,
    redact_value,
)

from migration_planner.scanner.discover import is_test_path
from migration_planner.scanner.contract import (
    ConfigFact,
    Diagnostic,
    ManifestContext,
    ManifestFacts,
)

#: The manifest classification this reader handles.
MANIFEST_KINDS: tuple[str, ...] = ("spring.config",)

#: ``application-prod.yml`` → ``prod``; the index part of the name is the profile.
_PROFILE_RE = re.compile(
    r"^(?P<kind>application|bootstrap)(?:-(?P<profile>[^.]+))?\.(?P<ext>properties|ya?ml)$",
    re.IGNORECASE,
)

#: Canonical keys that make a document profile-specific: Boot 2.4+'s
#: ``spring.config.activate.on-profile`` and the legacy ``spring.profiles``
#: (also as a list, ``spring.profiles[0]``). ``spring.profiles.active`` is *not*
#: one: it activates a profile, and the document setting it is still the
#: default document — reading it as the document's profile would file every
#: production key of ``application.yml`` under ``local``.
_PROFILE_KEYS: tuple[str, ...] = (
    "spring.config.activate.on-profile",
    "spring.profiles",
)

#: ``spring.profiles[0]``: the legacy key written as a list.
_PROFILE_LIST_RE = re.compile(r"^spring\.profiles\[\d+\]$")

#: A ``.properties`` document separator (Spring Boot 2.4+): ``#---`` or
#: ``!---`` on its own line, with no leading whitespace.
_DOCUMENT_SEPARATOR_RE = re.compile(r"^[#!]---\s*$")

#: Manifest kinds that make a module a Java module.
_JAVA_BUILD_KINDS: tuple[str, ...] = ("pom.xml", "build.gradle", "build.gradle.kts")

#: The npm manifest that makes a module a Node package.
_NPM_MANIFEST = "package.json"

#: A document may set several profiles: ``spring.config.activate.on-profile: a,b``.
_PROFILE_SPLIT_RE = re.compile(r"[,;]")

#: Java properties escapes this parser understands (the rest stay literal).
_ESCAPES = {
    "t": "\t",
    "n": "\n",
    "r": "\r",
    "f": "\f",
    "\\": "\\",
}

_UNICODE_RE = re.compile(r"\\u(?P<hex>[0-9a-fA-F]{4})")


@dataclass(frozen=True)
class _RawEntry:
    """One key a file sets, before canonicalization."""

    key: str
    value: str | None
    line: int
    profile: str
    kind: str


def read_spring_config(context: ManifestContext) -> ManifestFacts:
    """Every ``config[]`` fact of one module's Spring config files (FR-8a)."""
    facts = ManifestFacts()
    if not _is_java_module(context):
        return facts
    for manifest in context.by_kind(*MANIFEST_KINDS):
        text = manifest.read_text()
        if text is None:
            facts.diagnostics.append(
                Diagnostic(
                    kind="unreadable_file",
                    file=_relative(context, manifest.name),
                    detail="read failed",
                )
            )
            continue
        path = PurePosixPath(manifest.name)
        match = _PROFILE_RE.match(path.name)
        if match is None:
            continue
        file_kind = match.group("kind").lower()
        file_profile = (match.group("profile") or "default").lower()
        extension = match.group("ext").lower()
        test = _is_test(context.module, manifest.name)
        relative = _relative(context, manifest.name)
        if extension == "properties":
            entries, diagnostics = _properties(
                text, relative, file_profile, file_kind
            )
        else:
            entries, diagnostics = _yaml(text, relative, file_profile, file_kind)
        facts.diagnostics.extend(diagnostics)
        for entry in entries:
            facts.config.append(
                _fact(
                    entry,
                    file=relative,
                    module=context.module,
                    test=test,
                )
            )
        # Every Spring config file of the module is listed, bootstrap ones
        # included: ``modules[].spring_config_files`` is a module-level fact, and
        # a rule about bootstrap (it needs ``spring-cloud-starter-bootstrap``
        # since Spring Boot 2.4) finds its file by name among these.
        facts.spring_config_files.append(relative)
    return facts


def _is_java_module(context: ManifestContext) -> bool:
    """Whether the module's ``application*`` files are Spring config (FR-8a).

    A module with a Maven / Gradle build file is Java. A module without one is
    Java too when the repo has a Java build somewhere and the module is not an
    npm package — a shared ``config/application.yml`` at ``.`` next to
    ``svc/pom.xml``, even when ``.`` also holds a tooling ``package.json``. An
    npm package's ``application.yml`` in a repo that also has Java, or any such
    file in a repo with no Java build at all, is not Spring's.
    """
    if context.by_kind(*_JAVA_BUILD_KINDS):
        return True
    if not context.repo_has_java_build:
        return False
    return context.module == "." or not context.by_kind(_NPM_MANIFEST)


def _fact(
    entry: _RawEntry,
    *,
    file: str,
    module: str,
    test: bool,
) -> ConfigFact:
    """One ``config[]`` entry: canonical key, real file, redacted value.

    ``--no-values`` is applied later, by the accumulator, because it applies to
    every ``config[]`` entry of every reader, not just this one.
    """
    canonical = canonical_key(entry.key)
    value = redact_value(canonical, entry.value)
    return ConfigFact(
        key=cfg_key(config_file_for_spring_key(canonical), canonical),
        value=value,
        file=file,
        module=module,
        line=entry.line,
        raw_key=entry.key if entry.key != canonical else None,
        profile=entry.profile,
        kind=entry.kind,
        test=test,
    )


# --- .properties ----------------------------------------------------------


def _properties(
    text: str, file: str, file_profile: str, kind: str
) -> tuple[list[_RawEntry], list[Diagnostic]]:
    """Java properties: ``=`` / ``:`` / whitespace separators, ``\\`` continuation.

    The format is small but has real corners: a key may be separated by any
    whitespace, ``\\`` at a line end continues the value, ``\\uXXXX`` is an
    escape, and ``#`` / ``!`` at the start of a *logical* line is a comment.
    A line that is not ``key = value`` and not a comment is skipped as a fact
    but reported, because a silently dropped property is a silently dropped rule.
    """
    documents: list[list[tuple[str, str, int]]] = [[]]
    diagnostics: list[Diagnostic] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        start = index
        raw = lines[index]
        index += 1
        line_number = start + 1
        stripped = raw.lstrip()
        if not stripped:
            continue
        if stripped[:1] in ("#", "!"):
            # A comment line never continues, even when it ends in ``\``
            # (Java's rule): the next line is a property of its own.
            if _DOCUMENT_SEPARATOR_RE.match(raw):
                documents.append([])
            continue
        # A physical line ending in an odd number of backslashes continues.
        while _continues(raw) and index < len(lines):
            raw = raw[:-1] + lines[index].lstrip()
            index += 1
        stripped = raw.lstrip()
        key, value = _split_property(stripped)
        if key is None:
            diagnostics.append(
                Diagnostic(
                    kind="unparsed_property",
                    file=file,
                    line=line_number,
                    detail=stripped[:80],
                )
            )
            continue
        documents[-1].append((_unescape(key), _unescape(value), line_number))

    # ``#---`` splits a file into documents (Boot 2.4+), each of which may set
    # its own ``spring.config.activate.on-profile`` — the same rule as YAML.
    entries: list[_RawEntry] = []
    for leaves in documents:
        profile = _document_profile(leaves, file_profile)
        for key, value, line in leaves:
            entries.append(
                _RawEntry(key=key, value=value, line=line, profile=profile, kind=kind)
            )
    return entries, diagnostics


def _continues(raw: str) -> bool:
    """``a=b\\`` continues; ``a=b\\\\`` (an escaped backslash) does not."""
    trailing = len(raw) - len(raw.rstrip("\\"))
    return trailing % 2 == 1 and bool(raw.strip())


def _split_property(text: str) -> tuple[str | None, str]:
    """``key=value`` / ``key: value`` / ``key value`` → ``(key, value)``.

    ``None`` for a line with no key at all (``=value``), which is not a property
    and is reported rather than dropped.
    """
    length = len(text)
    index = 0
    escaped = False
    while index < length:
        character = text[index]
        if escaped:
            escaped = False
        elif character == "\\":
            escaped = True
        elif character in ("=", ":"):
            key = text[:index].strip()
            return (key or None), text[index + 1 :].strip()
        elif character in (" ", "\t", "\f"):
            break
        index += 1
    else:
        key = text.strip()
        return (key or None), ""
    # Whitespace separator: skip it and any ``=`` / ``:`` after it.
    rest = text[index:].lstrip()
    if rest[:1] in ("=", ":"):
        rest = rest[1:]
    key = text[:index].strip()
    return (key or None), rest.strip()


def _unescape(text: str) -> str:
    """``\\u00e9`` and the single-character escapes Java properties defines."""
    if "\\" not in text:
        return text
    text = _UNICODE_RE.sub(lambda match: chr(int(match.group("hex"), 16)), text)
    result: list[str] = []
    index = 0
    while index < len(text):
        character = text[index]
        if character == "\\" and index + 1 < len(text):
            following = text[index + 1]
            replacement = _ESCAPES.get(following)
            if replacement is not None:
                result.append(replacement)
                index += 2
                continue
        result.append(character)
        index += 1
    return "".join(result)


# --- .yml / .yaml ---------------------------------------------------------


def _yaml(
    text: str, file: str, file_profile: str, kind: str
) -> tuple[list[_RawEntry], list[Diagnostic]]:
    """Every leaf key of every document, with its real line number.

    ``yaml.compose_all`` is used rather than ``safe_load_all`` because the marks
    are what the profile needs: ``line`` must be the line the key is written on,
    not the line of the document. Aliases are already shared nodes at compose
    time, and a ``<<`` merge key is applied here, so a merged value appears under
    the key that receives it.
    """
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - pyyaml is a hard dependency
        return [], [
            Diagnostic(
                kind="yaml_unavailable",
                file=file,
                detail=f"{type(exc).__name__}: {exc}",
            )
        ]

    entries: list[_RawEntry] = []
    try:
        documents = list(yaml.compose_all(text, Loader=yaml.SafeLoader))
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None) or getattr(exc, "mark", None)
        return [], [
            Diagnostic(
                kind="yaml_parse_error",
                file=file,
                line=(mark.line + 1) if mark is not None else None,
                detail=_yaml_detail(exc),
            )
        ]

    for document in documents:
        leaves = list(_yaml_leaves(document))
        if not leaves:
            continue
        profile = _document_profile(leaves, file_profile)
        for key, value, line in leaves:
            entries.append(
                _RawEntry(key=key, value=value, line=line, profile=profile, kind=kind)
            )
    return entries, []


def _yaml_detail(exc: Any) -> str:
    """A one-line YAML error: the loader's problem, not its whole traceback."""
    problem = getattr(exc, "problem", None) or str(exc)
    return str(problem).splitlines()[0][:200]


def _document_profile(
    leaves: Sequence[tuple[str, str | None, int]], default: str
) -> str:
    """The profile a document is for, else the file name's profile.

    The key is compared in its canonical form, so relaxed binding applies here
    as everywhere else: ``spring.config.activate.onProfile`` is the same key.
    """
    for key, value, _ in leaves:
        if not value:
            continue
        canonical = canonical_key(key)
        if canonical in _PROFILE_KEYS or _PROFILE_LIST_RE.match(canonical):
            first = _PROFILE_SPLIT_RE.split(value)[0].strip()
            if first:
                return first.lower()
    return default


def _yaml_leaves(
    node: Any, prefix: str = "", seen: frozenset[int] = frozenset()
) -> Iterable[tuple[str, str | None, int]]:
    """``(dotted key, value, line)`` for every leaf under ``node``.

    - A nested map flattens to ``a.b.c``; a list to ``key[0].sub``.
    - An empty map or list is a key with an empty value: the service *sets* it,
      and ``None`` would mean "no value stored" (``--no-values``) instead.
    - An alias is the same node object, so it is walked as written; ``seen`` only
      stops a *recursive* anchor (``&a {x: *a}``), which would otherwise loop.
    """
    if node is None:
        return
    line = node.start_mark.line + 1
    if _is_mapping(node):
        pairs = _merged_pairs(node)
        if not pairs:
            if prefix:
                # An empty map is a key the service sets, with no value: `""`
                # rather than `None`, because `None` means "not stored"
                # (`--no-values`), and a matcher must be able to tell them apart.
                yield prefix, "", line
            return
        identity = id(node)
        for key_node, value_node in pairs:
            key = _scalar_text(key_node)
            if key is None:
                continue
            child = f"{prefix}.{key}" if prefix else key
            yield from _yaml_leaves(value_node, child, seen | {identity})
        return
    if _is_sequence(node):
        items = list(getattr(node, "value", ()) or ())
        if not items:
            if prefix:
                yield prefix, "", line
            return
        identity = id(node)
        for index, item in enumerate(items):
            if id(item) in seen:
                continue
            yield from _yaml_leaves(item, f"{prefix}[{index}]", seen | {identity})
        return
    yield prefix, _scalar_text(node), line


def _merged_pairs(node: Any) -> list[tuple[Any, Any]]:
    """``{key: value}`` pairs of a mapping node, ``<<`` merges applied.

    A merge key takes the pairs of the mapping it points at, and a key written
    in the document itself wins over a merged one — the YAML merge rule. The
    order is the document's own, so a caller can walk it top to bottom.
    """
    own = list(_raw_pairs(node))
    merged: dict[str, tuple[Any, Any]] = {}
    for key_node, value_node in own:
        if _scalar_text(key_node) != "<<":
            continue
        for source in _merge_sources(value_node):
            for merged_key, merged_value in _raw_pairs(source):
                name = _scalar_text(merged_key)
                if name is not None and name != "<<":
                    merged.setdefault(name, (merged_key, merged_value))

    pairs: list[tuple[Any, Any]] = []
    for key_node, value_node in own:
        name = _scalar_text(key_node)
        if name is None or name == "<<":
            continue
        # A key written in the document wins over a merged one of the same name.
        merged.pop(name, None)
        pairs.append((key_node, value_node))
    # A merged pair whose key the document does not set carries the *source's*
    # mark, which is the line the value was really written on.
    pairs.extend(merged.values())
    return pairs


def _merge_sources(value_node: Any) -> list[Any]:
    """The mappings a ``<<`` value refers to: one, or a sequence of them."""
    if _is_sequence(value_node):
        return [item for item in getattr(value_node, "value", ()) if _is_mapping(item)]
    return [value_node] if _is_mapping(value_node) else []


def _raw_pairs(node: Any) -> Iterable[tuple[Any, Any]]:
    """The ``(key node, value node)`` pairs of a mapping node.

    PyYAML's ``MappingNode.value`` is already a list of ``(key, value)`` tuples
    (``SequenceNode.value`` is the flat list of items).
    """
    for entry in getattr(node, "value", ()) or ():
        if isinstance(entry, tuple) and len(entry) == 2:
            yield entry[0], entry[1]


def _is_mapping(node: Any) -> bool:
    return getattr(node, "id", "") == "mapping"


def _is_sequence(node: Any) -> bool:
    return getattr(node, "id", "") == "sequence"


def _scalar_text(node: Any) -> str | None:
    """The text of a scalar node; ``None`` for a map or a sequence."""
    if node is None or _is_mapping(node) or _is_sequence(node):
        return None
    value = getattr(node, "value", None)
    if value is None:
        return None
    if value is True or value is False:
        return "true" if value else "false"
    return str(value)


# --- module helpers -------------------------------------------------------


def _relative(context: ManifestContext, name: str) -> str:
    """The scan-root-relative path of one of the module's files.

    ``ManifestFile.name`` is relative to the module root, so a file of a nested
    module needs the module prefix to be the real path in the repo.
    """
    if context.module == ".":
        return name
    return f"{context.module}/{name}"


def _is_test(module: str, name: str) -> bool:
    """The discovery rule (FR-1): ``src/test/`` or a ``src/<name>Test/`` source set."""
    return is_test_path(f"{module}/{name}" if module != "." else name)


__all__ = [
    "MANIFEST_KINDS",
    "MAX_VALUE_LENGTH",
    "SPRING_CONFIG_FILE",
    "is_secret_key",
    "read_spring_config",
]
