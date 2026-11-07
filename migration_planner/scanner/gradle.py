"""Gradle build files: ``build.gradle(.kts)``, ``settings.gradle(.kts)``,
``gradle/libs.versions.toml`` and ``gradle.properties`` (spec 026.6, FR-3 /
FR-8).

**No Gradle execution.** A build script is a Groovy or Kotlin program, and no
lexer can read a program. What the profile needs is not the program but the
declarations a build script almost always makes literally, so this module lexes
the common forms and skips the rest:

=========================================================  ==================
``plugins { id 'x' version 'v' }``, ``id("x") version "v"``  plugin fact
``apply plugin: 'x'``                                        plugin fact
``alias(libs.plugins.x)``                                     plugin fact (catalog)
``implementation 'g:a:v'`` / ``"g:a"``                        dependency fact
``implementation group: 'g', name: 'a', version: 'v'``         dependency fact
``implementation(platform('g:a:v'))`` / ``enforcedPlatform``   ``kind: bom``
``implementation(libs.spring.boot.starter.web)``               catalog accessor
``ext { v = '…' }``, ``extra["v"] = …``, ``gradle.properties``  variables
=========================================================  ==================

A construct the lexer does not understand is skipped. A *dependency-looking*
statement it cannot parse becomes an ``unparsed_gradle`` diagnostic, so a form
this lexer misses shows up in the profile instead of silently disappearing
(FR-8). A variable no file declares keeps its raw ``$name`` text and becomes an
``unresolved_variable`` diagnostic: the profile never invents a version.

Spring Boot (FR-3) comes from the plugin — its version taken from the module's
own ``plugins`` block, an ``alias(libs.plugins.…)``, the Gradle root project's
``plugins`` / ``pluginManagement`` block when the module applies it without a
version, else from a ``platform("org.springframework.boot:spring-boot-dependencies:X")``
dependency.

``settings.gradle`` ``include(…)`` declares module roots, which the scan folds
into ``modules[]``; ``sourceCompatibility`` / ``targetCompatibility`` /
``java.toolchain.languageVersion`` become ``cfg:build.gradle#…`` keys, because
the JDK a build compiles with is what most Spring Boot migration rules ask
about.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Sequence

from migration_keys.keys import cfg_key, maven_key

from migration_planner.scanner.contract import (
    ConfigFact,
    DependencyFact,
    Diagnostic,
    FrameworkFact,
    ManifestContext,
    ManifestFacts,
    ManifestFile,
)

#: The manifest classifications this reader handles. One function, one call per
#: module, whichever subset of these the module has (spec1 extractor contract).
MANIFEST_KINDS: tuple[str, ...] = (
    "build.gradle",
    "build.gradle.kts",
    "settings.gradle",
    "libs.versions.toml",
    "gradle.properties",
)

SPRING_BOOT_PLUGIN = "org.springframework.boot"
SPRING_BOOT_GROUP = "org.springframework.boot"
SPRING_BOOT_BOM = "spring-boot-dependencies"
SPRING_BOOT_BOM_KEY = f"{SPRING_BOOT_GROUP}:{SPRING_BOOT_BOM}"

PLUGIN_SCOPE = "plugins"

#: ``kind`` of a ``platform(…)`` / ``enforcedPlatform(…)`` dependency.
BOM_KIND = "bom"

#: Kotlin's ``kotlin("jvm")`` shorthand: the argument is a plugin-id suffix.
_KOTLIN_PLUGIN_ALIASES: dict[str, str] = {
    "jvm": "org.jetbrains.kotlin.jvm",
    "js": "org.jetbrains.kotlin.js",
    "android": "org.jetbrains.kotlin.android",
    "kapt": "org.jetbrains.kotlin.kapt",
    "multiplatform": "org.jetbrains.kotlin.multiplatform",
    "plugin.serialization": "org.jetbrains.kotlin.plugin.serialization",
    "plugin.spring": "org.jetbrains.kotlin.plugin.spring",
    "plugin.jpa": "org.jetbrains.kotlin.plugin.jpa",
}

#: ``mavenBom SpringBootPlugin.BOM_COORDINATES`` — the Boot plugin's own constant
#: for ``org.springframework.boot:spring-boot-dependencies``. It carries no
#: version: the plugin in use supplies it. The constant is usually written fully
#: qualified (``org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES``),
#: so it is matched by suffix.
_BOM_COORDINATE_CONSTANTS: tuple[tuple[str, str], ...] = (
    ("SpringBootPlugin.BOM_COORDINATES", SPRING_BOOT_BOM_KEY),
    ("DependencyManagementPlugin.BOM_COORDINATES", SPRING_BOOT_BOM_KEY),
)

#: ``buildscript { dependencies { classpath "g:a:v" } }`` artifacts that *are* a
#: plugin: the classic (pre-``plugins {}``) layout puts the plugin on the build
#: classpath and then writes ``apply plugin: 'id'`` with no version, so the
#: classpath entry is where the plugin's version is (FR-3).
_CLASSPATH_PLUGINS: dict[str, str] = {
    "org.springframework.boot:spring-boot-gradle-plugin": SPRING_BOOT_PLUGIN,
    "io.spring.gradle:dependency-management-plugin": "io.spring.dependency-management",
}

#: Wrappers around a dependency coordinate that change what it means.
_PLATFORM_WRAPPERS: tuple[str, ...] = ("enforcedPlatform", "platform")

#: Calls inside ``dependencies { }`` that are not configuration names.
_NOT_A_CONFIGURATION: frozenset[str] = frozenset(
    {
        "platform",
        "enforcedPlatform",
        "project",
        "files",
        "fileTree",
        "gradleApi",
        "gradleTestKit",
        "localGroovy",
        "testFixtures",
        "libs",
        "if",
        "else",
        "for",
        "return",
        "def",
        "val",
        "var",
        "constraints",
    }
)

#: Blocks inside ``dependencies { }`` that hold more dependencies.
_NESTED_DEPENDENCY_BLOCKS: frozenset[str] = frozenset({"constraints"})

#: Dependencies that are not facts of the module's own build.
_NOT_A_DEPENDENCY_CALL: tuple[str, ...] = (
    "project",
    "files",
    "fileTree",
    "gradleApi",
    "gradleTestKit",
    "localGroovy",
    "testFixtures",
)

_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*")
_NAMED_ARGUMENT_RE = re.compile(
    r"(?P<key>group|name|module|version)\s*(?::|=)\s*", re.MULTILINE
)
_STRING_ESCAPES = {
    "n": "\n",
    "t": "\t",
    "r": "\r",
    "b": "\b",
    "f": "\f",
    "\\": "\\",
    "'": "'",
    '"': '"',
    "$": "$",
}
_VARIABLE_RE = re.compile(r"\$\{([A-Za-z_][\w.\-]*)\}|\$([A-Za-z_][\w.\-]*)")
_JAVA_LANGUAGE_VERSION_RE = re.compile(
    r"JavaLanguageVersion\.of\s*\(\s*['\"]?(\d+)['\"]?"
)
_JAVA_VERSION_RE = re.compile(r"JavaVersion\.VERSION_(\d+|1_\d+)")
_JVM_TOOLCHAIN_RE = re.compile(r"jvmToolchain\s*\(\s*(\d+)\s*\)")
_BARE_JAVA_VERSION_RE = re.compile(r"['\"]?(\d+(?:\.\d+)?)['\"]?")


# --- records ---------------------------------------------------------------


@dataclass(frozen=True)
class _String:
    """One string literal of a build file, with where it starts."""

    value: str
    index: int


@dataclass(frozen=True)
class _Statement:
    """One statement of a block body: ``name(args)``, ``name { … }`` or both."""

    name: str
    args: tuple[int, int] | None = None
    block: tuple[int, int] | None = None
    index: int = 0


@dataclass(frozen=True)
class _Plugin:
    """One declared plugin: its id, the version as written and where it is.

    ``applied`` is ``False`` for ``id 'x' version 'v' apply false`` — a root
    project often declares a plugin's version without using it, so the version
    is a fact for the subprojects but the root project is not on the framework.
    """

    plugin_id: str
    raw_version: str = ""
    index: int = 0
    applied: bool = True


@dataclass(frozen=True)
class _Dependency:
    """One parsed dependency coordinate, before it becomes a fact."""

    group: str = ""
    artifact: str = ""
    version: str = ""
    raw_version: str = ""
    kind: str = "dependency"

    @property
    def name(self) -> str:
        return f"{self.group}:{self.artifact}" if self.artifact else ""


@dataclass(frozen=True)
class _CatalogEntry:
    """One ``[libraries]`` / ``[plugins]`` entry of the version catalog."""

    name: str
    module: str = ""
    version: str = ""
    plugin_id: str = ""


@dataclass
class _Catalog:
    """A parsed ``gradle/libs.versions.toml``."""

    versions: dict[str, str] = field(default_factory=dict)
    libraries: dict[str, _CatalogEntry] = field(default_factory=dict)
    plugins: dict[str, _CatalogEntry] = field(default_factory=dict)
    #: ``[bundles]``: accessor → the dotted library aliases it groups.
    bundles: dict[str, tuple[str, ...]] = field(default_factory=dict)
    file: str = ""
    #: The catalog exists but did not parse: its ``version_catalog_parse_error``
    #: already explains every accessor that then fails to resolve.
    broken: bool = False

    def plugin(self, dotted: str) -> _CatalogEntry | None:
        return self.plugins.get(dotted)

    def library(self, dotted: str) -> _CatalogEntry | None:
        return self.libraries.get(dotted)


@dataclass(frozen=True)
class _BuildFile:
    """One build / settings script, masked and ready to scan."""

    file: str
    text: str
    masked: str

    def line(self, index: int) -> int:
        return self.text.count("\n", 0, index) + 1

    def statements(self, span: tuple[int, int] | None = None) -> list[_Statement]:
        start, end = span if span is not None else (0, len(self.masked))
        return list(_statements(self.masked, start, end))

    def blocks(self, name: str) -> list[tuple[int, int]]:
        """Bodies of every top-level ``name { … }`` block."""
        return [
            statement.block
            for statement in self.statements()
            if statement.name == name and statement.block is not None
        ]


@dataclass
class _Declarations:
    """What one build / settings script declares, before it becomes facts."""

    plugins: list[_Plugin] = field(default_factory=list)
    plugin_aliases: list[tuple[str, int]] = field(default_factory=list)
    #: ``(configuration, argument span, statement index)``.
    dependencies: list[tuple[str, tuple[int, int], int]] = field(default_factory=list)
    #: ``mavenBom 'g:a:v'`` argument spans (``io.spring.dependency-management``).
    boms: list[tuple[tuple[int, int], int]] = field(default_factory=list)
    config: dict[str, tuple[str, int]] = field(default_factory=dict)
    variables: dict[str, str] = field(default_factory=dict)
    includes: list[str] = field(default_factory=list)
    #: ``(plugin id, raw version)`` from a ``buildscript`` ``classpath`` entry.
    classpath_plugins: list[tuple[str, str]] = field(default_factory=list)
    #: ``group = 'com.acme'`` — the groupId this build publishes under, at the
    #: top level or in ``allprojects`` / ``subprojects``.
    own_groups: list[str] = field(default_factory=list)


# --- lexing ----------------------------------------------------------------


def _mask(text: str) -> str:
    """``text`` with comments and string contents blanked, newlines kept.

    The result has the same length and line structure as ``text``, so an index
    in the mask is an index in the source: brackets are matched on the mask and
    values are read from the source.
    """
    out = list(text)
    index, length = 0, len(text)
    while index < length:
        char = text[index]
        if char == "/" and index + 1 < length and text[index + 1] == "/":
            while index < length and text[index] != "\n":
                out[index] = " "
                index += 1
            continue
        if char == "/" and index + 1 < length and text[index + 1] == "*":
            out[index] = out[index + 1] = " "
            index += 2
            while index < length:
                if text[index] == "*" and index + 1 < length and text[index + 1] == "/":
                    out[index] = out[index + 1] = " "
                    index += 2
                    break
                if text[index] != "\n":
                    out[index] = " "
                index += 1
            continue
        if char in ('"', "'"):
            quote = text[index : index + 3]
            if quote not in ('"""', "'''"):
                quote = char
            index += len(quote)
            while index < length:
                if text[index] == "\\" and len(quote) == 1:
                    index += 2
                    continue
                if text.startswith(quote, index):
                    index += len(quote)
                    break
                if text[index] != "\n":
                    out[index] = " "
                index += 1
            continue
        index += 1
    return "".join(out)


def _skip_whitespace(text: str, index: int, end: int) -> int:
    while index < end and text[index].isspace():
        index += 1
    return index


def _match_close(text: str, open_index: int, end: int) -> int:
    """Index of the bracket that closes the one at ``open_index``."""
    pairs = {"(": ")", "{": "}", "[": "]"}
    stack = [pairs[text[open_index]]]
    index = open_index + 1
    while index < end:
        char = text[index]
        if char in pairs:
            stack.append(pairs[char])
        elif stack and char == stack[-1]:
            stack.pop()
            if not stack:
                return index
        index += 1
    return end


def _statements(masked: str, start: int, end: int) -> Iterator[_Statement]:
    """Statements of one block body, in source order.

    A statement is an identifier followed by ``( … )``, or by ``{ … }`` for a
    nested block, or — Groovy's optional parentheses — by the rest of its line.
    A trailing closure belongs to the call and is skipped.
    """
    index = start
    while index < end:
        if masked[index].isspace():
            index += 1
            continue
        match = _IDENT_RE.match(masked, index)
        if match is None:
            index += 1
            continue
        name = match.group(0)
        cursor = match.end()
        probe = cursor
        while probe < end and masked[probe] in " \t":
            probe += 1
        args: tuple[int, int] | None = None
        block: tuple[int, int] | None = None
        if probe < end and masked[probe] == "(":
            close = _match_close(masked, probe, end)
            args = (probe + 1, close)
            cursor = close + 1
            # A trailing closure — ``tasks.withType(JavaCompile) { … }``,
            # ``implementation('x') { exclude … }`` — belongs to the call: it is
            # its block, so a caller that wants the body can have it.
            closure = _skip_whitespace(masked, cursor, end)
            if closure < end and masked[closure] == "{":
                close_block = _match_close(masked, closure, end)
                block = (closure + 1, close_block)
                cursor = close_block + 1
        elif probe < end and masked[probe] == "{":
            close = _match_close(masked, probe, end)
            block = (probe + 1, close)
            cursor = close + 1
        else:
            args = _rest_of_statement(masked, probe, end)
            cursor = args[1]
        yield _Statement(name=name, args=args, block=block, index=index)
        index = cursor


def _rest_of_statement(masked: str, start: int, end: int) -> tuple[int, int]:
    """The argument span of a statement written without parentheses."""
    cursor = start
    depth = 0
    while cursor < end:
        char = masked[cursor]
        if char == "\n" and depth == 0:
            current = masked[start:cursor].rstrip()
            if current.endswith((",", ":", "+", "(", "=")):
                cursor += 1
                continue
            break
        if char in "([{":
            depth += 1
        elif char in ")]}":
            if depth == 0:
                break
            depth -= 1
        cursor += 1
    return start, cursor


def _strings(text: str, start: int, end: int) -> list[_String]:
    """String literals of ``text[start:end]``, comments skipped."""
    found: list[_String] = []
    index = start
    limit = min(end, len(text))
    while index < limit:
        char = text[index]
        if char == "/" and index + 1 < limit and text[index + 1] == "/":
            newline = text.find("\n", index, limit)
            index = limit if newline < 0 else newline + 1
            continue
        if char == "/" and index + 1 < limit and text[index + 1] == "*":
            close = text.find("*/", index + 2, limit)
            index = limit if close < 0 else close + 2
            continue
        if char not in ('"', "'"):
            index += 1
            continue
        quote = text[index : index + 3]
        if quote not in ('"""', "'''"):
            quote = char
        cursor = index + len(quote)
        buffer: list[str] = []
        while cursor < limit:
            if text.startswith(quote, cursor):
                break
            current = text[cursor]
            if current == "\\" and len(quote) == 1 and cursor + 1 < limit:
                following = text[cursor + 1]
                buffer.append(_STRING_ESCAPES.get(following, "\\" + following))
                cursor += 2
                continue
            buffer.append(current)
            cursor += 1
        found.append(_String(value="".join(buffer), index=index))
        index = cursor + len(quote)
    return found


# --- variables -------------------------------------------------------------


class _Variables:
    """``ext`` / ``extra`` / ``gradle.properties`` values, and their resolution."""

    #: ``${a}`` whose value is ``${b}`` is resolved through, but not forever.
    MAX_DEPTH = 10

    def __init__(self, values: dict[str, str], diagnostics: list[Diagnostic]) -> None:
        self.values = values
        self.diagnostics = diagnostics
        self._reported: set[str] = set()

    def resolve(
        self, text: str, *, file: str = "", line: int | None = None
    ) -> str:
        """Replace ``$name`` / ``${name}``; an unknown name stays as written."""
        if "$" not in text:
            return text
        return self._resolve(text, file=file, line=line, depth=0)

    def _resolve(self, text: str, *, file: str, line: int | None, depth: int) -> str:
        unresolved: list[str] = []

        def replace(match: re.Match[str]) -> str:
            name = match.group(1) or match.group(2)
            value = self.values.get(name)
            if value is None:
                unresolved.append(name)
                return match.group(0)
            if "$" not in value:
                return value
            # ``springCloudVersion = "$springCloudVersion"`` in ``ext`` is how a
            # build file re-exports a ``gradle.properties`` value; a value that
            # only refers to itself would otherwise stay unresolved silently.
            if depth >= self.MAX_DEPTH or value.strip() == match.group(0):
                unresolved.append(name)
                return match.group(0)
            return self._resolve(value, file=file, line=line, depth=depth + 1)

        resolved = _VARIABLE_RE.sub(replace, text)
        for name in unresolved:
            self.report(name, file=file, line=line)
        return resolved

    def report(self, name: str, *, file: str = "", line: int | None = None) -> None:
        """One diagnostic per unresolved name per file: a name repeats often."""
        identity = f"{file}\0{name}"
        if identity in self._reported:
            return
        self._reported.add(identity)
        self.diagnostics.append(
            Diagnostic(
                kind="unresolved_variable", file=file, line=line, detail=f"${name}"
            )
        )


def _read_gradle_properties(
    files: Sequence[ManifestFile], facts: ManifestFacts
) -> dict[str, str]:
    """``gradle.properties``: ``key=value`` / ``key: value``, ``#`` / ``!`` comments."""
    values: dict[str, str] = {}
    for file in files:
        text = file.read_text()
        if text is None:
            facts.diagnostics.append(
                Diagnostic(kind="unreadable_file", file=file.name, detail="read failed")
            )
            continue
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line[0] in "#!":
                continue
            for separator in ("=", ":"):
                if separator in line:
                    key, _, value = line.partition(separator)
                    values[key.strip()] = value.strip()
                    break
            else:
                parts = line.split(None, 1)
                if len(parts) == 2:
                    values[parts[0]] = parts[1].strip()
    return values


def _ext_assignments(build: _BuildFile) -> dict[str, str]:
    """``ext { name = 'v' }``, ``ext { set('name', 'v') }``, ``ext.name = 'v'``,
    ``ext.set('name', 'v')``, ``extra["name"] = 'v'`` and ``val name = "v"``.

    ``ext { set('springCloudVersion', "2023.0.0") }`` is what Spring Initializr
    writes for a Groovy build, so it is as common as the plain assignment.

    ``ext`` is read wherever it is written, including inside a ``buildscript``
    block — the classic Groovy layout declares the versions there and uses them
    in both ``buildscript`` and ``dependencies``. A Kotlin script's top-level
    ``val mockkVersion = "1.13.13"`` is the same thing written differently, so
    it is read too.
    """
    values: dict[str, str] = {}
    for statement in _all_statements(build, (0, len(build.masked))):
        if statement.name in ("ext", "extra", "project.ext"):
            if statement.block is not None:
                for inner in build.statements(statement.block):
                    if inner.args is None:
                        continue
                    if inner.name == "set":
                        values.update(_set_call(build, inner))
                    else:
                        values.update(_assignment(build, inner))
            elif statement.args is not None:
                values.update(_assignment(build, statement))
            continue
        prefix = next(
            (
                prefix
                for prefix in ("project.ext.", "ext.", "extra.")
                if statement.name.startswith(prefix)
            ),
            None,
        )
        if prefix is not None and statement.args is not None:
            name = statement.name[len(prefix) :]
            if name == "set":
                values.update(_set_call(build, statement))
            elif name and "." not in name:
                values.update(
                    _assignment(
                        build,
                        _Statement(
                            name=name, args=statement.args, index=statement.index
                        ),
                    )
                )
            continue
        if statement.name in ("val", "var", "def") and statement.args is not None:
            values.update(_declaration(build, statement))
    masked = build.masked
    for match in re.finditer(r"extra\s*\[\s*", masked):
        closing = masked.find("]", match.end())
        if closing < 0:
            continue
        names = _strings(build.text, match.end(), closing)
        if not names:
            continue
        rest = _skip_whitespace(masked, closing + 1, len(masked))
        if rest >= len(masked) or masked[rest] != "=":
            continue
        literals = _strings(build.text, rest, _line_end(masked, rest))
        if literals:
            values[names[0].value] = literals[0].value
    return values


def _set_call(build: _BuildFile, statement: _Statement) -> dict[str, str]:
    """``set('name', 'value')`` inside ``ext`` (or ``ext.set(…)``)."""
    if statement.args is None:
        return {}
    literals = _strings(build.text, statement.args[0], statement.args[1])
    if len(literals) != 2:
        return {}
    name, value = literals[0].value, literals[1].value
    if value.strip() in (f"${name}", "${" + name + "}"):
        return {}
    return {name: value}


def _declaration(build: _BuildFile, statement: _Statement) -> dict[str, str]:
    """``val name = "value"`` (Kotlin) / ``def name = "value"`` (Groovy)."""
    if statement.args is None:
        return {}
    match = re.match(
        r"\s*([A-Za-z_][\w]*)\s*(?::\s*[\w.<>?]+\s*)?=", 
        build.text[statement.args[0] : statement.args[1]],
    )
    if match is None:
        return {}
    literals = _strings(
        build.text, statement.args[0] + match.end(), statement.args[1]
    )
    if len(literals) != 1:
        # ``val x = compute(…)`` is not a literal, and a string that holds more
        # than one literal is an expression: neither declares a version.
        return {}
    return {match.group(1): literals[0].value}


def _assignment(build: _BuildFile, statement: _Statement) -> dict[str, str]:
    """``name = 'value'`` for one statement inside an ``ext`` body.

    The lexer gives the statement its name and the span of what follows it, so
    the value is read past the ``=`` — ``springCloudVersion = '2024.0.0'``
    arrives as name ``springCloudVersion`` and span ``= '2024.0.0'``.

    ``springCloudVersion = "$springCloudVersion"`` re-exports a
    ``gradle.properties`` value and adds nothing: it is skipped, because taking
    it would replace the real value with its own placeholder.
    """
    if statement.args is None:
        return {}
    fragment = build.text[statement.args[0] : statement.args[1]]
    match = re.match(r"\s*=?\s*", fragment)
    start = statement.args[0] + (match.end() if match else 0)
    literals = _strings(build.text, start, statement.args[1])
    if not literals:
        return {}
    value = literals[0].value
    if value.strip() in (f"${statement.name}", "$" + "{" + statement.name + "}"):
        return {}
    return {statement.name: value}


def _line_end(masked: str, index: int) -> int:
    newline = masked.find("\n", index)
    return len(masked) if newline < 0 else newline


# --- version catalog -------------------------------------------------------


def _load_catalog(file: ManifestFile | None, diagnostics: list[Diagnostic]) -> _Catalog:
    """``gradle/libs.versions.toml`` with ``version.ref`` resolution (FR-8)."""
    catalog = _Catalog()
    if file is None:
        return catalog
    catalog.file = file.name
    data = file.read_bytes()
    if data is None:
        diagnostics.append(
            Diagnostic(kind="unreadable_file", file=file.name, detail="read failed")
        )
        return catalog
    text = data.decode("utf-8", errors="replace")
    try:
        parsed = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, ValueError) as exc:
        catalog.broken = True
        diagnostics.append(
            Diagnostic(
                kind="version_catalog_parse_error", file=file.name, detail=str(exc)
            )
        )
        return catalog

    versions = parsed.get("versions")
    if isinstance(versions, dict):
        catalog.versions = {
            str(name): str(value)
            for name, value in versions.items()
            if isinstance(value, (str, int, float))
        }
    for section, found in (("libraries", catalog.libraries), ("plugins", catalog.plugins)):
        block = parsed.get(section)
        if not isinstance(block, dict):
            continue
        for name, value in block.items():
            entry = _catalog_entry(
                str(name), value, catalog.versions, plugin=section == "plugins"
            )
            if entry is None:
                continue
            found[_dotted(str(name))] = entry
            missing = _missing_version_ref(value, catalog.versions)
            if missing:
                # ``version.ref = "nope"``: the entry is real, its version is
                # not declared anywhere — reported, never guessed (FR-8).
                diagnostics.append(
                    Diagnostic(
                        kind="unresolved_catalog_entry",
                        file=file.name,
                        line=_toml_key_line(text, str(name)),
                        detail=f"{section}.{name}: version.ref = {missing}",
                    )
                )
    bundles = parsed.get("bundles")
    if isinstance(bundles, dict):
        for name, members in bundles.items():
            if isinstance(members, list):
                catalog.bundles[_dotted(str(name))] = tuple(
                    _dotted(str(member)) for member in members if isinstance(member, str)
                )
    return catalog


def _toml_key_line(text: str, name: str) -> int | None:
    """The line a catalog entry is written on (``name = …``), for a diagnostic."""
    match = re.search(
        r"^[ \t]*[\"']?" + re.escape(name) + r"[\"']?[ \t]*=", text, re.MULTILINE
    )
    return text.count("\n", 0, match.start()) + 1 if match else None


def _missing_version_ref(value: object, versions: dict[str, str]) -> str:
    """The ``version.ref`` name of an entry when ``[versions]`` lacks it."""
    if not isinstance(value, dict):
        return ""
    reference = value.get("version")
    name = reference.get("ref") if isinstance(reference, dict) else None
    if isinstance(name, str) and name not in versions:
        return name
    return ""


def _dotted(name: str) -> str:
    """A catalog name as its accessor reads it: ``spring-boot-web`` → ``spring.boot.web``."""
    return name.replace("-", ".").replace("_", ".")


def _unresolved_free(version: str) -> str:
    """A version, or ``""`` when it still holds an unresolved ``$var`` / ``${var}``.

    An unresolved placeholder is not a version: keeping it would make the
    profile claim the build uses ``$externalLibVersion``. It stays in ``range``
    as written, and the ``unresolved_variable`` diagnostic says why (AC-7).
    """
    return "" if "$" in version else version


def _catalog_entry(
    name: str, value: object, versions: dict[str, str], *, plugin: bool = False
) -> _CatalogEntry | None:
    if isinstance(value, str) and plugin:
        # ``[plugins]`` string notation is ``"<plugin id>:<version>"``, not a
        # Maven coordinate: ``boot = "org.springframework.boot:3.3.1"``.
        plugin_id, _, version = value.partition(":")
        return _CatalogEntry(name=name, plugin_id=plugin_id.strip(), version=version.strip())
    if isinstance(value, str):
        if ":" in value:
            group, _, rest = value.partition(":")
            artifact, _, version = rest.partition(":")
            return _CatalogEntry(
                name=name, module=f"{group}:{artifact}", version=version
            )
        # A version-less alias names another entry: ``x = "some-lib"``.
        return None
    if not isinstance(value, dict):
        return None
    module = str(value.get("module") or "")
    if not module:
        group = str(value.get("group") or "")
        artifact = str(value.get("name") or "")
        module = f"{group}:{artifact}" if group and artifact else ""
    plugin_id = str(value.get("id") or "")
    if not module and not plugin_id:
        return None
    return _CatalogEntry(
        name=name,
        module=module,
        version=_catalog_version(value, versions),
        plugin_id=plugin_id,
    )


def _catalog_version(value: dict, versions: dict[str, str]) -> str:
    reference = value.get("version")
    if isinstance(reference, str):
        return reference
    if isinstance(reference, dict):
        name = reference.get("ref")
        return versions.get(name, "") if isinstance(name, str) else ""
    # ``version.ref = "x"`` is one dotted TOML key, so it arrives here.
    name = value.get("version.ref")
    return versions.get(name, "") if isinstance(name, str) else ""


# --- dependency coordinates ------------------------------------------------


class _CoordinateParser:
    """Turns one dependency argument list into coordinates (FR-8 notation)."""

    def __init__(self, build: _BuildFile, catalog: _Catalog, variables: _Variables) -> None:
        self.build = build
        self.catalog = catalog
        self.variables = variables
        #: ``libs.…`` accessors the catalog does not declare, with their index —
        #: the caller reports them, because a dropped accessor is a lost fact.
        self.unknown_accessors: list[tuple[str, int]] = []

    def parse(self, span: tuple[int, int], *, kind: str = "dependency") -> list[_Dependency]:
        """Every coordinate one argument list declares (usually one).

        More than one when the argument is a ``libs.bundles.…`` accessor or a
        Groovy vararg list (``implementation 'g:a:1', 'g:b:2'``); none when it
        is not an external coordinate at all.
        """
        start, end = span
        masked = self.build.masked
        cursor = _skip_whitespace(masked, start, end)
        if cursor >= end:
            return []
        for wrapper in _PLATFORM_WRAPPERS:
            if not masked.startswith(wrapper, cursor):
                continue
            probe = _skip_whitespace(masked, cursor + len(wrapper), end)
            if probe < end and masked[probe] == "(":
                close = _match_close(masked, probe, end)
                return self._value((probe + 1, close), BOM_KIND)
            break
        constant = self._coordinate_constant(cursor, end)
        if constant is not None:
            return [constant]
        return self._value((cursor, end), kind)

    def _coordinate_constant(self, cursor: int, end: int) -> _Dependency | None:
        """``mavenBom SpringBootPlugin.BOM_COORDINATES`` → the BOM it names.

        The constant is a reference, not a coordinate, but it is the standard way
        the Boot plugin's own BOM is imported. Its version belongs to the plugin,
        so the coordinates are recorded without one and FR-3 reads the version
        from the plugin instead.
        """
        match = re.match(r"[A-Za-z_][\w.]*", self.build.masked[cursor:end])
        if match is None:
            return None
        written = match.group(0)
        name = next(
            (
                coordinate
                for suffix, coordinate in _BOM_COORDINATE_CONSTANTS
                if written.endswith(suffix)
            ),
            None,
        )
        if name is None:
            return None
        group, _, artifact = name.partition(":")
        return _Dependency(group=group, artifact=artifact, kind=BOM_KIND)

    def _value(self, span: tuple[int, int], kind: str) -> list[_Dependency]:
        start, end = span
        masked = self.build.masked
        cursor = _skip_whitespace(masked, start, end)
        if cursor >= end:
            return []
        # An own-project dependency or a file collection is not an external fact.
        for prefix in _NOT_A_DEPENDENCY_CALL:
            if masked.startswith(prefix + "(", cursor):
                return []
        if masked.startswith("libs.", cursor):
            return self._accessor(cursor, end, kind)
        if masked.startswith("kotlin", cursor):
            kotlin = self._kotlin_module(cursor, end, kind)
            if kotlin is not None:
                return [kotlin]
        named = self._named_arguments((start, end))
        if named is not None:
            group, artifact, raw, index = named
            return [self._coordinate(group, artifact, raw, index, kind)]
        literals = _strings(self.build.text, start, end)
        if not literals:
            return []
        if len(literals) >= 3 and ":" not in literals[0].value:
            # Kotlin DSL's positional form: ``implementation("g", "a", "v")``.
            return [
                self._coordinate(
                    literals[0].value,
                    literals[1].value,
                    literals[2].value,
                    literals[0].index,
                    kind,
                )
            ]
        # ``'g:a:v'`` — or several of them, Groovy's vararg form
        # ``implementation 'g:a:1', 'g:b:2'``. Only when *every* literal is a
        # coordinate: ``add("implementation", "g:a:v")`` is not a list of
        # coordinates, and it stays an ``unparsed_gradle`` statement.
        coordinates = [
            (literal, literal.value.split(":"))
            for literal in (literals if all(":" in item.value for item in literals) else literals[:1])
        ]
        found: list[_Dependency] = []
        for literal, pieces in coordinates:
            if len(pieces) < 2:
                continue
            raw = pieces[2] if len(pieces) > 2 else ""
            found.append(
                self._coordinate(pieces[0], pieces[1], raw, literal.index, kind)
            )
        return found

    def _coordinate(
        self, group: str, artifact: str, raw: str, index: int, kind: str
    ) -> _Dependency:
        # ``g:a:1.0@aar`` / ``g:a:1.0!!``: the classifier is not the version.
        raw = raw.split("@", 1)[0].rstrip("!").strip()
        version = self.variables.resolve(
            raw, file=self.build.file, line=self.build.line(index)
        )
        return _Dependency(
            group=group.strip(),
            artifact=artifact.strip(),
            version=_unresolved_free(version),
            raw_version=raw,
            kind=kind,
        )

    def _kotlin_module(self, cursor: int, end: int, kind: str) -> _Dependency | None:
        """``kotlin("stdlib")`` / ``kotlin("reflect", "2.0.0")`` → ``org.jetbrains.kotlin:kotlin-…``."""
        probe = _skip_whitespace(self.build.masked, cursor + len("kotlin"), end)
        if probe >= end or self.build.masked[probe] != "(":
            return None
        close = _match_close(self.build.masked, probe, end)
        literals = _strings(self.build.text, probe + 1, close)
        if not literals or ":" in literals[0].value:
            return None
        raw = literals[1].value if len(literals) > 1 else ""
        return self._coordinate(
            "org.jetbrains.kotlin",
            f"kotlin-{literals[0].value.strip()}",
            raw,
            literals[0].index,
            kind,
        )

    def _accessor(self, cursor: int, end: int, kind: str) -> list[_Dependency]:
        """``libs.spring.boot.starter.web`` → the catalog's ``spring-boot-starter-web``.

        ``libs.bundles.web`` → every library of the bundle. An accessor the
        catalog does not declare is remembered, so the caller reports it.
        """
        match = _IDENT_RE.match(self.build.masked, cursor)
        accessor = match.group(0) if match else ""
        bundle = _catalog_bundle(self.catalog, accessor)
        if bundle is not None:
            entries = bundle
            if not entries:
                self.unknown_accessors.append((accessor, cursor))
        else:
            entry = _catalog_accessor(self.catalog, accessor)
            if entry is None:
                self.unknown_accessors.append((accessor, cursor))
                return []
            entries = [entry]
        found: list[_Dependency] = []
        for entry in entries:
            group, _, artifact = entry.module.partition(":")
            found.append(
                _Dependency(
                    group=group,
                    artifact=artifact,
                    version=_unresolved_free(
                        self.variables.resolve(
                            entry.version,
                            file=self.build.file,
                            line=self.build.line(cursor),
                        )
                    ),
                    raw_version=entry.version,
                    kind=kind,
                )
            )
        return found

    def _named_arguments(
        self, span: tuple[int, int]
    ) -> tuple[str, str, str, int] | None:
        """Map notation: ``group: 'g', name: 'a', version: 'v'`` (Groovy / Kotlin)."""
        start, end = span
        masked = self.build.masked
        values: dict[str, tuple[str, int]] = {}
        for match in _NAMED_ARGUMENT_RE.finditer(masked, start, end):
            key = match.group("key")
            if key in values:
                continue
            cursor = _skip_whitespace(masked, match.end(), end)
            if cursor >= end:
                continue
            if masked.startswith("libs.", cursor):
                accessor = _IDENT_RE.match(masked, cursor)
                entry = _catalog_accessor(
                    self.catalog, accessor.group(0) if accessor else ""
                )
                if entry is None:
                    continue
                if key == "version":
                    values[key] = (entry.version, cursor)
                else:
                    group, _, artifact = entry.module.partition(":")
                    values["group"] = (group, cursor)
                    values["name"] = (artifact, cursor)
                continue
            literals = _strings(self.build.text, cursor, min(_line_end(masked, cursor), end))
            if not literals:
                continue
            if key == "module":
                group, _, artifact = literals[0].value.partition(":")
                values["group"] = (group, literals[0].index)
                values["name"] = (artifact, literals[0].index)
            else:
                values[key] = (literals[0].value, literals[0].index)
        if "name" not in values:
            return None
        group = values.get("group", ("", start))
        artifact = values["name"]
        raw, index = values.get("version", ("", start))
        return group[0], artifact[0], raw, index


def _catalog_accessor(catalog: _Catalog, accessor: str) -> _CatalogEntry | None:
    """``libs.spring.boot.starter.web`` → the catalog's ``spring-boot-starter-web``.

    The accessor is the catalog name with ``-`` / ``_`` read as ``.``, plus three
    reserved prefixes: ``libs.plugins.``, ``libs.bundles.`` and
    ``libs.versions.``. Everything else names a library.
    """
    if not accessor.startswith("libs."):
        return None
    parts = accessor[len("libs.") :].split(".")
    if not parts or not parts[0]:
        return None
    if parts[0] == "plugins":
        return catalog.plugin(".".join(parts[1:]))
    if parts[0] == "versions":
        return None
    if parts[0] == "bundles":
        return None  # a bundle is several libraries: see ``_catalog_bundle``
    return catalog.library(".".join(parts))


def _catalog_bundle(catalog: _Catalog, accessor: str) -> list[_CatalogEntry] | None:
    """``libs.bundles.web`` → its libraries; ``None`` when it is not a bundle.

    A member that names no library is skipped here; the bundle itself is what
    the build file wrote, and an unknown bundle is reported by the caller.
    """
    prefix = "libs.bundles."
    if not accessor.startswith(prefix):
        return None
    members = catalog.bundles.get(accessor[len(prefix) :])
    if members is None:
        return []
    return [entry for member in members if (entry := catalog.library(member)) is not None]


# --- build file ------------------------------------------------------------


def _read_declarations(build: _BuildFile) -> _Declarations:
    """Walk one build / settings script for the declarations FR-8 asks for."""
    declarations = _Declarations()
    _collect_plugins(build, declarations)
    _collect_dependencies(build, declarations)
    _collect_java_config(build, declarations)
    declarations.variables.update(_ext_assignments(build))
    for statement in build.statements():
        if statement.name == "include" and statement.args is not None:
            declarations.includes.extend(_include_paths(build, statement.args))
    declarations.classpath_plugins.extend(_classpath_plugins(build, declarations))
    declarations.own_groups.extend(_own_groups(build))
    return declarations


def _classpath_plugins(
    build: _BuildFile, declarations: _Declarations
) -> Iterator[tuple[str, str]]:
    """``classpath "org.springframework.boot:spring-boot-gradle-plugin:$v"`` → the plugin's version.

    The raw version is kept as written; it is resolved later, against the
    variables of the module that applies the plugin.
    """
    for configuration, span, _ in declarations.dependencies:
        if configuration != "buildscript:classpath":
            continue
        for literal in _strings(build.text, span[0], span[1]):
            pieces = literal.value.split(":")
            if len(pieces) < 3:
                continue
            plugin_id = _CLASSPATH_PLUGINS.get(f"{pieces[0].strip()}:{pieces[1].strip()}")
            if plugin_id:
                yield plugin_id, pieces[2].split("@", 1)[0].strip()


def _own_groups(build: _BuildFile) -> list[str]:
    """``group = 'com.acme'`` at the top level or in ``allprojects`` / ``subprojects``."""
    spans = [(0, len(build.masked))]
    spans.extend(build.blocks("allprojects"))
    spans.extend(build.blocks("subprojects"))
    groups: list[str] = []
    for span in spans:
        for statement in build.statements(span):
            if statement.name not in ("group", "project.group") or statement.args is None:
                continue
            fragment = build.masked[statement.args[0] : statement.args[1]]
            if not fragment.lstrip().startswith("="):
                continue  # ``group 'x'`` is not an assignment we can trust
            literals = _strings(build.text, statement.args[0], statement.args[1])
            if len(literals) == 1 and "$" not in literals[0].value:
                groups.append(literals[0].value.strip())
    return groups


def _collect_plugins(build: _BuildFile, declarations: _Declarations) -> None:
    """``plugins { … }``, ``pluginManagement { plugins { … } }`` and ``apply plugin:``."""
    spans = build.blocks("plugins")
    for outer in build.blocks("pluginManagement"):
        spans.extend(
            statement.block
            for statement in build.statements(outer)
            if statement.name == "plugins" and statement.block is not None
        )
    for span in spans:
        pending: str = ""
        for statement in build.statements(span):
            if statement.name == "version" and statement.args is not None and pending:
                literals = _strings(build.text, statement.args[0], statement.args[1])
                if literals:
                    declarations.plugins.append(
                        _Plugin(pending, literals[0].value, statement.index)
                    )
                    pending = ""
                continue
            if _is_bare_statement(statement, build):
                # Kotlin DSL's shorthand: ``plugins { java }`` applies the plugin.
                declarations.plugins.append(_Plugin(statement.name, "", statement.index))
                pending = ""
                continue
            if statement.args is None:
                continue
            if statement.name == "alias":
                accessor = _accessor_text(build, statement.args, "libs.plugins.")
                if accessor:
                    declarations.plugin_aliases.append((accessor, statement.index))
                pending = ""
                continue
            if statement.name == "id":
                literals = _strings(build.text, statement.args[0], statement.args[1])
                if not literals:
                    continue
                raw_version = literals[1].value if len(literals) > 1 else ""
                if not raw_version:
                    # ``id("x").version("v")`` in Kotlin DSL.
                    raw_version = _version_call(build, statement) or ""
                applied = not re.search(
                    r"apply\s+false",
                    build.text[statement.index : _line_end(build.masked, statement.index)],
                )
                declarations.plugins.append(
                    _Plugin(literals[0].value, raw_version, statement.index, applied)
                )
                pending = ""
                continue
            if statement.name == "kotlin":
                literals = _strings(build.text, statement.args[0], statement.args[1])
                plugin_id = _KOTLIN_PLUGIN_ALIASES.get(
                    literals[0].value if literals else ""
                )
                if plugin_id:
                    pending = plugin_id
                    declarations.plugins.append(_Plugin(plugin_id, "", statement.index))
                continue
            pending = ""

    for statement in build.statements():
        if statement.name != "apply" or statement.args is None:
            continue
        fragment = build.text[statement.args[0] : statement.args[1]]
        found = re.search(r"plugin\s*[:=]\s*['\"]([^'\"]+)['\"]", fragment)
        if found:
            declarations.plugins.append(_Plugin(found.group(1), "", statement.index))


def _is_bare_statement(statement: _Statement, build: _BuildFile) -> bool:
    """Whether the statement is a lone identifier on its line (``plugins { java }``).

    Without parentheses the lexer reads the rest of the line as the arguments,
    so a shorthand plugin application arrives with an empty argument span.
    """
    if statement.args is None or statement.block is not None:
        return False
    return not build.masked[statement.args[0] : statement.args[1]].strip()


def _accessor_text(
    build: _BuildFile, span: tuple[int, int], prefix: str
) -> str:
    """The ``libs.…`` accessor written inside an argument list."""
    match = re.search(
        r"libs\." + re.escape(prefix[len("libs.") :]) + r"[\w.]*",
        build.text[span[0] : span[1]],
    )
    return f"libs.{match.group(0)[len('libs.'):]}" if match else ""


def _version_call(build: _BuildFile, statement: _Statement) -> str | None:
    """``id("x").version("v")``: the version written after the ``id`` call."""
    if statement.args is None:
        return None
    end = min(_line_end(build.masked, statement.args[1]), len(build.masked))
    literals = _strings(build.text, statement.args[1], end)
    return literals[0].value if literals else None


def _collect_dependencies(build: _BuildFile, declarations: _Declarations) -> None:
    """``dependencies { … }`` at the top level, and inside ``allprojects`` / ``subprojects``.

    A build that configures its modules centrally is still a build that declares
    those dependencies, so both shapes are read. ``constraints`` (a real block
    inside ``dependencies``) and ``dependencyManagement { dependencies { … } }``
    hold dependencies too.
    """
    for span in build.blocks("dependencies"):
        _collect_dependency_block(build, span, declarations)
    for wrapper in ("allprojects", "subprojects", "buildscript"):
        for outer in build.blocks(wrapper):
            for span in (
                statement.block
                for statement in build.statements(outer)
                if statement.name == "dependencies" and statement.block is not None
            ):
                _collect_dependency_block(
                    build,
                    span,
                    declarations,
                    prefix="buildscript:" if wrapper == "buildscript" else "",
                )
    for management in build.blocks("dependencyManagement"):
        for span in _nested_blocks(build, management, "imports"):
            _collect_bom_block(build, span, declarations)


def _nested_blocks(
    build: _BuildFile, span: tuple[int, int], *names: str
) -> list[tuple[int, int]]:
    return [
        statement.block
        for statement in build.statements(span)
        if statement.name in names and statement.block is not None
    ]


def _collect_bom_block(
    build: _BuildFile, span: tuple[int, int], declarations: _Declarations
) -> None:
    """``dependencyManagement { imports { mavenBom 'g:a:v' } }``: a BOM, not a dependency.

    The ``io.spring.dependency-management`` plugin's syntax. Its sibling
    ``dependencies { … }`` block is ordinary managed entries.
    """
    for statement in build.statements(span):
        if statement.args is None:
            continue
        if statement.name == "mavenBom":
            declarations.boms.append((statement.args, statement.index))
        elif not statement.name.startswith(("if", "else")):
            declarations.dependencies.append(
                (statement.name, statement.args, statement.index)
            )


def _collect_dependency_block(
    build: _BuildFile,
    span: tuple[int, int],
    declarations: _Declarations,
    *,
    prefix: str = "",
) -> None:
    """Configurations of one ``dependencies { … }`` block.

    ``prefix`` marks a block whose configurations are the build's own classpath
    (``buildscript``), so a ``classpath`` entry is recorded as such rather than
    as a compile dependency of the module.
    """
    for statement in build.statements(span):
        if statement.args is None and statement.block is not None:
            if statement.name in _NESTED_DEPENDENCY_BLOCKS:
                _collect_dependency_block(build, statement.block, declarations, prefix=prefix)
            continue
        if statement.args is None or statement.name in _NOT_A_CONFIGURATION:
            continue
        declarations.dependencies.append(
            (f"{prefix}{statement.name}", statement.args, statement.index)
        )


def _collect_java_config(build: _BuildFile, declarations: _Declarations) -> None:
    """``java { toolchain { languageVersion = … } }`` and ``sourceCompatibility``.

    The two keys a Spring Boot migration asks about: the toolchain language
    version (the JDK the build compiles with) and the source / target
    compatibility that older builds set instead.
    """
    for span in build.blocks("java"):
        for statement in build.statements(span):
            if statement.name == "toolchain" and statement.block is not None:
                _toolchain(build, statement.block, declarations)
            elif statement.name in ("sourceCompatibility", "targetCompatibility"):
                _java_compatibility(build, statement, declarations)
    for statement in _all_statements(build, (0, len(build.masked))):
        if statement.name in ("sourceCompatibility", "targetCompatibility"):
            _java_compatibility(build, statement, declarations)
    for match in _JVM_TOOLCHAIN_RE.finditer(build.masked):
        declarations.config.setdefault(
            "java.toolchain.languageVersion", (match.group(1), match.start())
        )


def _all_statements(
    build: _BuildFile, span: tuple[int, int], depth: int = 0
) -> Iterator[_Statement]:
    """Every statement at any depth, so a compatibility set in a nested closure counts.

    ``tasks.withType(JavaCompile) { sourceCompatibility = '21' }`` and
    ``sourceCompatibility = JavaVersion.VERSION_17`` say the same thing about
    the build, so both are read. Depth is bounded: a pathological script cannot
    turn one scan into a deep recursion.
    """
    if depth > 8:
        return
    for statement in build.statements(span):
        yield statement
        if statement.block is not None:
            yield from _all_statements(build, statement.block, depth + 1)


def _java_compatibility(
    build: _BuildFile, statement: _Statement, declarations: _Declarations
) -> None:
    span = statement.args
    if span is None:
        equals = build.masked.find("=", statement.index, _line_end(build.masked, statement.index))
        if equals < 0:
            return
        span = (equals + 1, _line_end(build.masked, equals))
    value = _java_version(build.text[span[0] : span[1]])
    if value:
        declarations.config.setdefault(statement.name, (value, statement.index))


def _toolchain(
    build: _BuildFile, span: tuple[int, int], declarations: _Declarations
) -> None:
    for statement in build.statements(span):
        if statement.name != "languageVersion":
            continue
        cursor = statement.args[0] if statement.args else statement.index
        window = build.text[cursor : cursor + 200]
        match = _JAVA_LANGUAGE_VERSION_RE.search(window)
        if match:
            declarations.config.setdefault(
                "java.toolchain.languageVersion", (match.group(1), cursor)
            )
            continue
        literals = _strings(build.text, cursor, _line_end(build.masked, cursor))
        value = _java_version(literals[0].value) if literals else ""
        if value:
            declarations.config.setdefault(
                "java.toolchain.languageVersion", (value, cursor)
            )


def _java_version(text: str) -> str:
    """``JavaVersion.VERSION_17`` / ``1_8`` / ``'17'`` / ``1.8`` → ``17`` / ``1.8``."""
    match = _JAVA_VERSION_RE.search(text)
    if match:
        raw = match.group(1)
        return f"1.{raw[2:]}" if raw.startswith("1_") else raw
    literal = _BARE_JAVA_VERSION_RE.search(text)
    return literal.group(1) if literal else ""


def _include_paths(build: _BuildFile, span: tuple[int, int]) -> list[str]:
    """``include 'a', ':b:c'`` → module paths (``a``, ``b/c``)."""
    paths: list[str] = []
    for literal in _strings(build.text, span[0], span[1]):
        name = literal.value.strip()
        if not name or "$" in name or "://" in name:
            continue
        name = name.strip(":").replace(":", "/")
        if name:
            paths.append(name)
    return paths


# --- file access -----------------------------------------------------------


def _build_file(path: Path, relative: str) -> _BuildFile | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return _BuildFile(file=relative, text=text, masked=_mask(text))


def _scan_relative(context: ManifestContext, path: Path) -> str:
    """A build file as a scan-root-relative path, for diagnostics and ``config[].file``."""
    root = (context.scan_root or context.root).resolve()
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.name


def _module_manifest(context: ManifestContext, *names: str) -> ManifestFile | None:
    """The module's own build / settings script, else none.

    ``ManifestFile.name`` is relative to the module root, but a reader also has
    to reach a *parent* project's file (the Gradle root's build file supplies a
    subproject's inherited plugin version); the caller passes a path for that.
    """
    for name in names:
        found = context.named(name)
        if found is not None:
            return found
    for name in names:
        for manifest in context.files:
            if manifest.name.endswith("/" + name):
                return manifest
    return None


def _gradle_property_files(context: ManifestContext) -> list[ManifestFile]:
    """The repo root's ``gradle.properties``, then the module's own.

    A subproject inherits the root project's ``gradle.properties`` values, which
    is how ``$versions`` in a subproject build file normally resolves, and its
    own file overrides them. The files are read in this order and a later value
    wins, so the module's own file comes last.
    """
    files: list[ManifestFile] = []
    own = context.named("gradle.properties")
    root = context.scan_root
    if root is not None:
        root_file = root / "gradle.properties"
        if root_file.is_file() and (own is None or root_file.resolve() != own.path.resolve()):
            files.append(
                ManifestFile(
                    name="gradle.properties", kind="gradle.properties", path=root_file
                )
            )
    if own is not None:
        files.append(own)
    return files


def _root_project_directory(context: ManifestContext) -> Path:
    """The Gradle root project: the nearest ancestor with a settings script."""
    scan_root = (context.scan_root or context.root).resolve()
    directory = context.root.resolve()
    for candidate in (directory, *directory.parents):
        try:
            candidate.relative_to(scan_root)
        except ValueError:
            break
        if any(
            (candidate / name).is_file()
            for name in ("settings.gradle", "settings.gradle.kts")
        ):
            return candidate
    return scan_root


def _inherited_from_root(
    context: ManifestContext,
) -> tuple[dict[str, tuple[str, str]], dict[str, str]]:
    """Plugin versions a subproject inherits from its Gradle root project.

    Two places declare them: ``pluginManagement { plugins { … } }`` in the root's
    settings script, and the root's own ``plugins`` block (often ``apply false``,
    so the root does not use the plugin itself). Both are read without running
    Gradle, and a subproject's own declaration wins. A third is the classic
    layout: the plugin on the root's ``buildscript`` classpath, applied in the
    subproject with ``apply plugin:``.

    Returns ``({plugin id: (raw version, where)}, root ext variables)``.
    ``where`` is the declaring script and block
    (``settings.gradle.kts#pluginManagement``), so a framework fact built from
    it names its real source. The root's ``ext`` values are visible in every
    subproject (Gradle looks a property up through the parent projects), and
    the classic layout writes ``springBootVersion`` exactly there.
    """
    root = _root_project_directory(context)
    versions: dict[str, tuple[str, str]] = {}
    variables: dict[str, str] = {}
    for name in ("settings.gradle", "settings.gradle.kts", "build.gradle", "build.gradle.kts"):
        path = root / name
        if not path.is_file():
            continue
        build = _build_file(path, _scan_relative(context, path))
        if build is None:
            continue
        block = "pluginManagement" if name.startswith("settings") else "plugins"
        declared = _read_declarations(build)
        for plugin in declared.plugins:
            if plugin.raw_version:
                versions.setdefault(
                    plugin.plugin_id, (plugin.raw_version, f"{build.file}#{block}")
                )
        for plugin_id, raw in declared.classpath_plugins:
            versions.setdefault(plugin_id, (raw, f"{build.file}#buildscript"))
        for variable, value in declared.variables.items():
            variables.setdefault(variable, value)
    return versions, variables


# --- reader ----------------------------------------------------------------


def read_gradle_manifests(context: ManifestContext) -> ManifestFacts:
    """Every Gradle fact of one module (FR-3 Spring Boot, FR-8 manifests)."""
    facts = ManifestFacts()

    catalog = _load_catalog(_catalog_file(context), facts.diagnostics)
    build_file = _module_manifest(context, "build.gradle", "build.gradle.kts")
    settings_file = _module_manifest(context, "settings.gradle", "settings.gradle.kts")
    properties = _gradle_property_files(context)
    if (
        build_file is None
        and settings_file is None
        and catalog.file == ""
        and not properties
    ):
        return facts

    build = (
        _build_file(build_file.path, _scan_relative(context, build_file.path))
        if build_file is not None
        else None
    )
    if build is None and build_file is not None:
        facts.diagnostics.append(
            Diagnostic(
                kind="unreadable_file",
                file=_scan_relative(context, build_file.path),
                detail="read failed",
            )
        )
    settings = (
        _build_file(settings_file.path, _scan_relative(context, settings_file.path))
        if settings_file is not None
        else None
    )

    variables = _read_gradle_properties(properties, facts)
    declarations = _read_declarations(build) if build is not None else _Declarations()
    settings_declarations = (
        _read_declarations(settings) if settings is not None else _Declarations()
    )
    variables.update(settings_declarations.variables)
    variables.update(declarations.variables)
    # A plugin declared without a version takes it from the module's own
    # ``buildscript`` classpath first, then ``pluginManagement``, then the root.
    plugin_sources: dict[str, str] = {}
    for plugin_id, raw in declarations.classpath_plugins:
        if build is not None and f"plugin.{plugin_id}" not in variables:
            variables[f"plugin.{plugin_id}"] = raw
            plugin_sources[plugin_id] = f"{build.file}#buildscript"
    for plugin in settings_declarations.plugins:
        if plugin.raw_version:
            variables.setdefault(f"plugin.{plugin.plugin_id}", plugin.raw_version)
            plugin_sources.setdefault(
                plugin.plugin_id, f"{settings.file}#pluginManagement" if settings else ""
            )

    inherited, root_variables = _inherited_from_root(context)
    for plugin_id, (raw, where) in inherited.items():
        variables.setdefault(f"plugin.{plugin_id}", raw)
        plugin_sources.setdefault(plugin_id, where)
    for variable, value in root_variables.items():
        variables.setdefault(variable, value)

    resolver = _Variables(variables, facts.diagnostics)

    if build is not None:
        _record_plugins(facts, context, build, declarations, catalog, resolver)
    dependencies = (
        _record_dependencies(facts, context, build, declarations, catalog, resolver)
        if build is not None
        else []
    )
    if build is not None:
        _record_config(facts, context, build, declarations.config, resolver)
        _record_module_roots(facts, context, declarations.includes)
    if settings is not None:
        _record_module_roots(facts, context, settings_declarations.includes)
        _record_plugin_management(facts, context, settings, settings_declarations, resolver)

    _detect_spring_boot(
        facts,
        context,
        build,
        declarations,
        plugin_sources,
        catalog,
        dependencies,
        resolver,
    )
    own_groups = {*declarations.own_groups, *settings_declarations.own_groups}
    facts.own_group_ids.extend(sorted(own_groups))
    facts.group_ids.extend(
        sorted(
            {
                dependency.group
                for dependency in dependencies
                if dependency.group and dependency.group not in own_groups
            }
        )
    )
    return facts


def _catalog_file(context: ManifestContext) -> ManifestFile | None:
    """The version catalog this module resolves ``libs.…`` against.

    A subproject rarely holds ``gradle/libs.versions.toml`` itself: the catalog
    belongs to the Gradle root project and every subproject reads it through
    ``libs``. The module's own catalog wins, then the root's.
    """
    manifests = context.by_kind("libs.versions.toml")
    if manifests:
        return manifests[0]
    root = _root_project_directory(context)
    for relative in ("gradle/libs.versions.toml", "libs.versions.toml"):
        path = root / relative
        if path.is_file():
            return ManifestFile(name=relative, kind="libs.versions.toml", path=path)
    return None


def _record_plugins(
    facts: ManifestFacts,
    context: ManifestContext,
    build: _BuildFile,
    declarations: _Declarations,
    catalog: _Catalog,
    resolver: _Variables,
) -> None:
    """``plugins`` / ``apply plugin`` / ``alias(libs.plugins.x)`` (FR-8).

    A plugin applied without a version still gets one when the Gradle root
    project or the catalog declares it — that is how a subproject's ``plugins``
    block is written — so the fact carries the version the build really uses.
    """
    declared: set[str] = set()
    for plugin in declarations.plugins:
        declared.add(plugin.plugin_id)
        raw = plugin.raw_version or resolver.values.get(
            f"plugin.{plugin.plugin_id}", ""
        )
        facts.dependencies.append(
            _plugin_fact(
                context,
                build.file,
                plugin.plugin_id,
                raw,
                resolver,
                build.line(plugin.index),
                source="declared" if plugin.raw_version else "inherited",
            )
        )
    for accessor, index in declarations.plugin_aliases:
        entry = _catalog_accessor(catalog, accessor)
        plugin_id = (entry.plugin_id or entry.module) if entry is not None else ""
        if entry is None or not plugin_id:
            if catalog.broken:
                continue
            facts.diagnostics.append(
                Diagnostic(
                    kind="unresolved_catalog_entry",
                    file=build.file,
                    line=build.line(index),
                    detail=accessor,
                )
            )
            continue
        if plugin_id in declared:
            # ``id 'x'`` and ``alias(libs.plugins.x)`` name one plugin: one fact.
            continue
        declared.add(plugin_id)
        facts.dependencies.append(
            _plugin_fact(
                context,
                build.file,
                plugin_id,
                entry.version,
                resolver,
                build.line(index),
                source="catalog",
            )
        )


def _record_plugin_management(
    facts: ManifestFacts,
    context: ManifestContext,
    settings: _BuildFile,
    declarations: _Declarations,
    resolver: _Variables,
) -> None:
    """``pluginManagement`` versions are the project's, recorded once per module."""
    recorded = {
        dependency.key
        for dependency in facts.dependencies
        if dependency.kind == "plugin"
    }
    for plugin in declarations.plugins:
        # The module's own ``plugins`` block already recorded this one, with the
        # version it applies; ``pluginManagement`` is the fallback.
        if not plugin.raw_version or f"gradle-plugin:{plugin.plugin_id}" in recorded:
            continue
        recorded.add(f"gradle-plugin:{plugin.plugin_id}")
        facts.dependencies.append(
            _plugin_fact(
                context,
                settings.file,
                plugin.plugin_id,
                plugin.raw_version,
                resolver,
                settings.line(plugin.index),
                source="pluginManagement",
            )
        )


def _plugin_fact(
    context: ManifestContext,
    file: str,
    plugin_id: str,
    raw_version: str,
    resolver: _Variables,
    line: int,
    *,
    source: str,
) -> DependencyFact:
    version = (
        _unresolved_free(resolver.resolve(raw_version, file=file, line=line))
        if raw_version
        else ""
    )
    return DependencyFact(
        key=f"gradle-plugin:{plugin_id}",
        name=plugin_id,
        range=raw_version,
        version=version or None,
        scope=PLUGIN_SCOPE,
        module=context.module,
        kind="plugin",
        version_source=source if version else None,
    )


def _record_dependencies(
    facts: ManifestFacts,
    context: ManifestContext,
    build: _BuildFile,
    declarations: _Declarations,
    catalog: _Catalog,
    resolver: _Variables,
) -> list[_Dependency]:
    """Every declared dependency in any configuration (FR-8 notation)."""
    parser = _CoordinateParser(build, catalog, resolver)
    parsed: list[_Dependency] = []
    for configuration, span, index in declarations.dependencies:
        unknown_before = len(parser.unknown_accessors)
        found = parser.parse(span)
        for coordinates in found:
            if not coordinates.group or not coordinates.artifact:
                facts.diagnostics.append(
                    Diagnostic(
                        kind="invalid_dependency",
                        file=build.file,
                        line=build.line(index),
                        detail=f"{configuration} {coordinates.name}".strip(),
                    )
                )
                continue
            parsed.append(coordinates)
            facts.dependencies.append(
                _dependency_fact(context, coordinates, configuration)
            )
        if found or len(parser.unknown_accessors) > unknown_before:
            continue
        if _dependency_shaped(build, span):
            facts.diagnostics.append(
                Diagnostic(
                    kind="unparsed_gradle",
                    file=build.file,
                    line=build.line(index),
                    detail=build.text[span[0] : span[1]].strip()[:120],
                )
            )
    for span, index in declarations.boms:
        unknown_before = len(parser.unknown_accessors)
        found = [entry for entry in parser.parse(span, kind=BOM_KIND) if entry.artifact]
        if not found:
            if len(parser.unknown_accessors) == unknown_before:
                facts.diagnostics.append(
                    Diagnostic(
                        kind="unparsed_gradle",
                        file=build.file,
                        line=build.line(index),
                        detail=build.text[span[0] : span[1]].strip()[:120],
                    )
                )
            continue
        for coordinates in found:
            parsed.append(coordinates)
            facts.dependencies.append(
                _dependency_fact(context, coordinates, "dependencyManagement")
            )
    for accessor, index in parser.unknown_accessors:
        # ``implementation(libs.typo)``: the catalog has no such entry, so the
        # dependency is unknown — reported, never dropped silently (FR-8).
        # A broken catalog is already one diagnostic; one per accessor would
        # only repeat it.
        if catalog.broken:
            continue
        facts.diagnostics.append(
            Diagnostic(
                kind="unresolved_catalog_entry",
                file=build.file,
                line=build.line(index),
                detail=accessor,
            )
        )
    return parsed


def _dependency_fact(
    context: ManifestContext, coordinates: _Dependency, scope: str
) -> DependencyFact:
    return DependencyFact(
        key=maven_key(coordinates.name),
        name=coordinates.name,
        range=coordinates.raw_version,
        version=coordinates.version or None,
        scope=scope,
        module=context.module,
        kind=coordinates.kind,
        version_source="declared" if coordinates.version else None,
    )


def _dependency_shaped(build: _BuildFile, span: tuple[int, int]) -> bool:
    """Whether a statement the lexer could not parse plainly declares a dependency.

    ``implementation(project(":core"))`` and ``implementation(files("libs/x.jar"))``
    are not failures — they are not external coordinates at all. A string
    literal that carries a group and an artifact is.
    """
    fragment = build.text[span[0] : span[1]]
    if any(f"{call}(" in fragment for call in _NOT_A_DEPENDENCY_CALL):
        return False
    return any(":" in literal.value for literal in _strings(build.text, span[0], span[1]))


def _record_config(
    facts: ManifestFacts,
    context: ManifestContext,
    build: _BuildFile,
    config: dict[str, tuple[str, int]],
    resolver: _Variables,
) -> None:
    key_file = _config_key_file(build.file)
    for key, (raw, index) in sorted(config.items()):
        facts.config.append(
            ConfigFact(
                key=cfg_key(key_file, key),
                value=resolver.resolve(
                    raw, file=build.file, line=build.line(index)
                ),
                file=build.file,
                module=context.module,
                line=build.line(index),
            )
        )


def _config_key_file(file: str) -> str:
    """The canonical file name of a Gradle config key (025 FR-2.6).

    A rule says ``cfg:build.gradle#java.toolchain.languageVersion``, not the
    name of the subproject's script, so every Groovy script canonicalizes to
    ``build.gradle`` and every Kotlin one to ``build.gradle.kts`` — the two
    evidence keys 027 / 025 know about. The real file stays in ``config[].file``.
    """
    return "build.gradle.kts" if file.endswith(".gradle.kts") else "build.gradle"


def _record_module_roots(
    facts: ManifestFacts, context: ManifestContext, includes: Sequence[str]
) -> None:
    """``settings.gradle`` ``include(…)`` → module roots (FR-8, FR-3)."""
    scan_root = (context.scan_root or context.root).resolve()
    base = context.root.resolve()
    for name in includes:
        candidate = (base / name).resolve()
        try:
            relative = candidate.relative_to(scan_root).as_posix()
        except ValueError:
            continue
        if relative and relative not in facts.module_roots:
            facts.module_roots.append(relative)


def _detect_spring_boot(
    facts: ManifestFacts,
    context: ManifestContext,
    build: _BuildFile | None,
    declarations: _Declarations,
    plugin_sources: dict[str, str],
    catalog: _Catalog,
    dependencies: Sequence[_Dependency],
    resolver: _Variables,
) -> None:
    """FR-3 for Gradle: the plugin first, then a Boot BOM on ``platform(…)``.

    A subproject that applies the plugin without a version inherits the root
    project's, which is exactly what ``pluginManagement`` is for; a subproject
    that declares neither, but depends on Spring Boot libraries, is on the root
    project's version too.

    A source whose version does not resolve (``version "$bootVersion"`` with no
    declaration, or a plugin applied with no version anywhere) does not stop
    the search. When no source gives a version, a module that applies the
    plugin is still on Spring Boot: the fact has an empty ``version`` and the
    text as written in ``raw`` — the shape spec2 gives an Angular range it
    cannot normalize — and the ``unresolved_variable`` diagnostic says why.
    """
    del context
    file = build.file if build is not None else ""
    unresolved: FrameworkFact | None = None

    if build is not None:
        for raw, source, index in _plugin_declarations(
            build, declarations, catalog, resolver, plugin_sources
        ):
            version = (
                _unresolved_free(
                    resolver.resolve(raw, file=file, line=build.line(index))
                )
                if raw
                else ""
            )
            fact = FrameworkFact(
                name="spring-boot", version=version, raw=raw, source=source
            )
            if version:
                facts.frameworks.append(fact)
                return
            unresolved = unresolved or fact

    bom = next(
        (
            dependency
            for dependency in dependencies
            if dependency.kind == BOM_KIND
            and dependency.name == SPRING_BOOT_BOM_KEY
            and dependency.version
        ),
        None,
    )
    if bom is not None:
        facts.frameworks.append(
            FrameworkFact(
                name="spring-boot",
                version=bom.version,
                raw=bom.raw_version,
                source=f"{file}#platform" if build is not None else "#platform",
            )
        )
        return

    if unresolved is not None:
        facts.frameworks.append(unresolved)
        return

    inherited = resolver.values.get(f"plugin.{SPRING_BOOT_PLUGIN}", "")
    if inherited and _uses_spring(dependencies):
        facts.frameworks.append(
            FrameworkFact(
                name="spring-boot",
                version=_unresolved_free(resolver.resolve(inherited, file=file)),
                raw=inherited,
                source=plugin_sources.get(SPRING_BOOT_PLUGIN, "gradle-root#plugins"),
            )
        )


def _plugin_declarations(
    build: _BuildFile,
    declarations: _Declarations,
    catalog: _Catalog,
    resolver: _Variables,
    plugin_sources: dict[str, str],
) -> Iterator[tuple[str, str, int]]:
    """``(raw version, source, index)`` of this module's Spring Boot plugin wiring.

    ``source`` is where the version comes from: the module's ``plugins`` block,
    the catalog, or — for a plugin applied without a version — the script that
    supplies it (``build.gradle#buildscript``, ``settings.gradle#pluginManagement``).

    ``apply false`` declares a version without using the plugin, which is how a
    root project publishes its version to its subprojects: the module itself is
    then *not* on Spring Boot, and the version stays available to subprojects.
    """
    for plugin in declarations.plugins:
        if plugin.plugin_id != SPRING_BOOT_PLUGIN or not plugin.applied:
            continue
        if plugin.raw_version:
            yield plugin.raw_version, f"{build.file}#plugins", plugin.index
            continue
        inherited = resolver.values.get(f"plugin.{SPRING_BOOT_PLUGIN}", "")
        # Applied with no version anywhere in the repo: on Boot, version unknown.
        source = plugin_sources.get(SPRING_BOOT_PLUGIN) if inherited else None
        yield inherited, source or f"{build.file}#plugins", plugin.index
    for accessor, index in declarations.plugin_aliases:
        entry = _catalog_accessor(catalog, accessor)
        if entry is None or (entry.plugin_id or entry.module) != SPRING_BOOT_PLUGIN:
            continue
        yield entry.version, f"{build.file}#catalog", index


def _uses_spring(dependencies: Sequence[_Dependency]) -> bool:
    """Whether the module depends on a Spring Boot library.

    The Boot Gradle plugin on a ``buildscript`` classpath is the build's
    tooling, not a library of the module: it does not count.
    """
    return any(
        dependency.kind == "dependency"
        and dependency.group == SPRING_BOOT_GROUP
        and dependency.name not in _CLASSPATH_PLUGINS
        for dependency in dependencies
    )


__all__ = [
    "MANIFEST_KINDS",
    "SPRING_BOOT_BOM_KEY",
    "SPRING_BOOT_PLUGIN",
    "read_gradle_manifests",
]
