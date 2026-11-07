"""Java sources: external imports and their usages (spec 026.7 FR-7).

One pure function of the file's bytes, so spec9 can cache it and run it in a
process pool: :func:`extract_java`. One post-pass, :func:`filter_own_packages`,
runs once on the collected facts because the set of the repo's own packages is
only known after every source has been read.

What becomes a fact
-------------------

**Imports.** Every import declaration is a fact at its own line — a symbol for
a class (``import a.b.C``), a member for a static import
(``import static a.b.C.m`` → ``maven:a.b.C.m``), a wildcard entry for
``import a.b.*`` / ``import static a.b.C.*``. A nested type keeps its dots
(``import a.b.C.Inner`` → ``maven:a.b.C.Inner``).

A wildcard import cannot name the class it supplies, so the entry also carries
the simple names the file uses that nothing else explains (``names``); a matcher
tests ``a.b.X`` against them (AC-5.2). A name the file declares itself, or that
another import already binds, is not listed, and the own-package post-pass drops
a name the file's own package declares, because that needs no import at all.

**Usages**, all recorded where they happen and keyed by FQCN:

- a type in any position — field, parameter, ``extends``, ``implements``,
  generic argument, ``new C(…)``, cast, ``instanceof``, ``throws``, ``C.class``,
  ``C::new`` — is a **symbol** (``maven:a.b.C``);
- an annotation ``@C`` / ``@C(…)`` is a symbol at its own line, and each
  attribute is a **member** (``maven:a.b.C.method``); the single-value form
  ``@C("x")`` is the attribute ``value``;
- a static call or field read on an imported class — ``C.m(…)``, ``C.FIELD`` —
  is a **member** (``maven:a.b.C.m``), taking the first segment after the class
  exactly as the TypeScript extractor does, so ``RequestMethod.GET.name()`` is
  ``RequestMethod.GET`` and not a method of the enum constant;
- a statically imported name used bare — ``assertEquals(…)``, ``MAX`` — is a
  member of the class it was imported from; a statically imported nested type
  (``import static java.util.Map.Entry``) is a symbol instead, at the import and
  at every use;
- an annotation only a class wildcard can supply (``@RequestMapping(method = …)``
  under ``import …annotation.*``) has no FQCN, so its attributes are members
  under every class wildcard of the file — the policy ``names`` follows.

A call on a variable (``entity.getName()``) is not resolved (Non-Goals, spec1),
and ``this`` / ``super`` are not owners.

A **fully qualified usage without import** — ``org.x.Y.z()``, ``@org.x.Ann``,
``org.x.Y`` as a type — is recorded the same way when its name starts with a
groupId the repo's builds declare (spec6 → ``ModuleEnv.group_ids``) or with its
parent groupId (:func:`_qualified_prefixes`: a starter-only service still names
``org.springframework.util``). That set is how the scanner tells an external
package from the service's own ``com.acme.…`` code, so no import is needed for a
rule about it.

**Own packages are not facts.** Every ``package x.y;`` declared in the scanned
sources is an own package, so an import of one — or of anything under one — is
the repo's own code in another module, not an external library. The extractor
records it like any other import; :func:`filter_own_packages` removes it once
the whole set is known. That is a post-pass by the spec1 extractor contract,
because one file cannot know its siblings' packages.

The rule is the spec's "equals or starts with", so a repo whose sources are in
``com.acme`` treats a dependency on an external ``com.acme.platform`` as its own
code as well — the same trade-off spec6's ``own_group_ids`` makes, and the same
one the TypeScript own-package rule makes for a workspace name.

Parsing
-------

tree-sitter-java. A file where nothing parses is one ``parse_error``
diagnostic and a partial parse a ``partial_parse_error`` at the first error;
either way the imports and usages that did parse are recorded (AC-5.4),
because one bad file must never lose the facts around it.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any, Iterator

from migration_keys.keys import maven_key

from migration_planner.scanner.contract import (
    Diagnostic,
    FileFacts,
    PostPassContext,
    SourceContext,
    Usage,
)

#: Discovery language tag this module handles.
GRAMMARS: tuple[str, ...] = ("java",)

#: Node types that declare a type name (the names a wildcard need not supply).
_TYPE_DECLARATIONS: frozenset[str] = frozenset(
    {
        "annotation_type_declaration",
        "class_declaration",
        "enum_declaration",
        "interface_declaration",
        "record_declaration",
    }
)

#: Node types that bind a name in their ``name`` field. A bare name bound here
#: is a declaration, never a use of a static import. A lambda's parameter has no
#: ``name`` field and is handled separately (``_declarations``).
_DECLARING_NODES: frozenset[str] = _TYPE_DECLARATIONS | {
    "annotation_type_element_declaration",
    "catch_formal_parameter",
    "constructor_declaration",
    "enhanced_for_statement",
    "enum_constant",
    "formal_parameter",
    "method_declaration",
    "record_pattern_component",
    "resource",  # try-with-resources: ``resource (Type name = …)``
    "spread_parameter",
    "type_parameter",
    "variable_declarator",
}

#: Parents in which an ``identifier`` belongs to a name or a member access that
#: another rule already handles, so it is not a bare reference. An identifier in
#: an annotation's argument list or an ``element_value_pair`` value *is* a
#: reference (``@RequestMapping(method = GET)`` with ``GET`` statically
#: imported), which is why those parents are absent.
_NOT_A_REFERENCE: frozenset[str] = frozenset(
    {
        "annotation",
        "field_access",
        "import_declaration",
        "marker_annotation",
        "method_invocation",
        "method_reference",
        "package_declaration",
        "scoped_identifier",
        "scoped_type_identifier",
    }
)

#: ``var`` is a type node in a declaration, not a type name (Java 10+).
_NOT_A_TYPE_NAME: frozenset[str] = frozenset({"var"})

#: Types every compilation unit imports implicitly. A name in this set needs no
#: import at all, so it is never a simple name a wildcard import supplied (a
#: ``java.util.*`` entry must not claim to supply ``String``). Curated to what
#: real service code uses; a missing JDK type only means one extra name in a
#: wildcard entry, never a missing fact.
_JAVA_LANG: frozenset[str] = frozenset(
    {
        "Appendable", "ArithmeticException", "ArrayIndexOutOfBoundsException",
        "ArrayStoreException", "AssertionError", "AutoCloseable", "Boolean",
        "BootstrapMethodError", "Byte", "CharSequence", "Character", "Class",
        "ClassCastException", "ClassLoader", "ClassNotFoundException",
        "ClassValue", "CloneNotSupportedException", "Cloneable", "Comparable",
        "Compiler", "Deprecated", "Double", "Enum", "EnumConstantNotPresentException",
        "Error", "Exception", "ExceptionInInitializerError", "Float",
        "FunctionalInterface", "IllegalAccessException", "IllegalArgumentException",
        "IllegalCallerException", "IllegalMonitorStateException",
        "IllegalStateException", "IllegalThreadStateException",
        "IncompatibleClassChangeError", "IndexOutOfBoundsException",
        "InstantiationException", "Integer", "InternalError", "InterruptedException",
        "Iterable", "LayerInstantiationException", "LinkageError", "Long", "Math",
        "Module", "ModuleLayer", "NegativeArraySizeException", "NoClassDefFoundError",
        "NoSuchFieldError", "NoSuchFieldException", "NoSuchMethodError",
        "NoSuchMethodException", "NullPointerException", "Number",
        "NumberFormatException", "Object", "OutOfMemoryError", "Override", "Package",
        "Process", "ProcessBuilder", "ProcessHandle", "Readable", "Record",
        "ReflectiveOperationException", "Runnable", "Runtime", "RuntimeException",
        "SafeVarargs", "ScopedValue", "SecurityException", "SecurityManager",
        "Short", "StackOverflowError", "StackTraceElement", "StackWalker",
        "StrictMath", "String", "StringBuffer", "StringBuilder",
        "StringIndexOutOfBoundsException", "SuppressWarnings", "System", "Thread",
        "ThreadDeath", "ThreadGroup", "ThreadLocal", "Throwable",
        "TypeNotPresentException", "UnknownError", "UnsatisfiedLinkError",
        "UnsupportedClassVersionError", "UnsupportedOperationException",
        "VerifyError", "VirtualMachineError", "Void",
    }
)


class _Extractor:
    """Walks one parsed tree and accumulates that file's facts."""

    def __init__(self, context: SourceContext, root: Any) -> None:
        self.context = context
        self.root = root
        self.facts = FileFacts(package_name="")
        self.package = ""
        # ``{simple name: FQCN}`` for ``import a.b.C`` and ``a.b.C.Inner``.
        self._classes: dict[str, str] = {}
        # ``{simple name: dotted owner name}`` for ``import static a.b.C.m``.
        self._statics: dict[str, str] = {}
        # ``(package or owner, line)`` of every wildcard import.
        self._class_wildcards: list[tuple[str, int]] = []
        self._static_wildcards: list[tuple[str, int]] = []
        # Names this file declares: a wildcard supplies neither.
        self._declared_types: set[str] = set()
        self._declared: set[str] = set()
        # Simple names in a type position that no import explains: what a class
        # wildcard import could have supplied (AC-5.2).
        self._unbound_types: set[str] = set()
        # Simple names called or read bare that no import explains: what a
        # static wildcard import could have supplied.
        self._unbound_members: set[str] = set()
        self._seen: set[tuple[str, str, int]] = set()
        self._group_ids = _qualified_prefixes(
            context.env.group_ids, context.env.own_group_ids
        )

    def run(self) -> FileFacts:
        self._package()
        self._declarations()
        self._imports()
        for node in _walk(self.root):
            kind = node.type
            if kind == "type_identifier":
                self._type_identifier(node)
            elif kind == "scoped_type_identifier":
                self._scoped_type(node)
            elif kind in ("annotation", "marker_annotation"):
                self._annotation(node)
            elif kind == "method_invocation":
                self._method_invocation(node)
            elif kind == "field_access":
                self._field_access(node)
            elif kind == "method_reference":
                self._method_reference(node)
            elif kind == "identifier":
                self._bare_identifier(node)
        self._wildcard_imports()
        self.facts.local_declarations = set(self._declared_types)
        return self.facts

    # -- declarations ------------------------------------------------------

    def _package(self) -> None:
        """``package x.y;``: own-package filtering needs it (post-pass)."""
        for node in self.root.named_children:
            if node.type != "package_declaration":
                continue
            self.package = _compact(_without_keyword(_text(node), "package"))
            break
        self.facts.package_name = self.package

    def _declarations(self) -> None:
        for node in _walk(self.root):
            kind = node.type
            if kind == "lambda_expression":
                # ``x -> …`` declares ``x`` (no ``name`` field) and
                # ``(x) -> …`` wraps it in ``inferred_parameters``.
                first = next(iter(node.named_children), None)
                if first is None:
                    continue
                if first.type == "identifier":
                    self._declared.add(_text(first))
                elif first.type == "inferred_parameters":
                    self._declared.update(
                        _text(child)
                        for child in first.named_children
                        if child.type == "identifier"
                    )
                continue
            if kind not in _DECLARING_NODES:
                continue
            name = _declared_name(node)
            if not name:
                continue
            self._declared.add(name)
            if kind in _TYPE_DECLARATIONS:
                self._declared_types.add(name)

    # -- imports -----------------------------------------------------------

    def _imports(self) -> None:
        for node in self.root.named_children:
            if node.type != "import_declaration":
                continue
            # The ``static`` keyword is its own token: a text prefix test would
            # read ``import statics.Foo`` as a static import.
            is_static = any(child.type == "static" for child in node.children)
            body = _compact(
                "".join(
                    _text(child)
                    for child in node.children
                    if child.type not in ("import", "static", ";")
                )
            )
            if not body:
                continue
            line = node.start_point.row + 1
            if body.endswith(".*"):
                owner = body[:-2]
                if is_static:
                    self._static_wildcards.append((owner, line))
                else:
                    self._class_wildcards.append((owner, line))
                continue
            simple = body.rsplit(".", 1)[-1]
            if is_static:
                self._statics[simple] = body
                if _looks_like_nested_type(simple):
                    # ``import static java.util.Map.Entry`` binds a type, so it
                    # is a symbol here as well as at every use.
                    self._symbol(maven_key(body), line)
                else:
                    self._member(maven_key(body), line)
            else:
                self._classes[simple] = body
                self._symbol(maven_key(body), line)

    def _wildcard_imports(self) -> None:
        """One entry per wildcard import, with the simple names it could supply.

        Every class wildcard in a file lists every unexplained simple name, and
        every static wildcard lists every unexplained bare name. Without a
        classpath the scanner cannot tell *which* of two wildcard packages
        really declares ``Map``, so it lists the name under each of them: a
        matcher that misses a name would drop a rule that does apply, while a
        matcher that sees one extra name only has a rule to verify — and the
        entry's ``locations`` already name the files to look at. A file with one
        wildcard import (the common case) is exact.
        """
        for owner, line in self._class_wildcards:
            self._wildcard(
                maven_key(f"{owner}.*"), line, tuple(sorted(self._unbound_types))
            )
        for owner, line in self._static_wildcards:
            self._wildcard(
                maven_key(f"{owner}.*"), line, tuple(sorted(self._unbound_members))
            )

    # -- usages ------------------------------------------------------------

    def _type_identifier(self, node: Any) -> None:
        parent = node.parent
        if parent is not None and parent.type in (
            "scoped_type_identifier",
            "type_parameter",
        ):
            # ``Outer.Inner`` is one name (the scoped node has it), and the
            # ``T`` of ``class C<T>`` declares a type parameter.
            return
        name = _text(node)
        if name in _NOT_A_TYPE_NAME:
            return
        line = node.start_point.row + 1
        key = self._key_for_type(name)
        if key is not None:
            self._symbol(key, line)

    def _scoped_type(self, node: Any) -> None:
        if node.parent is not None and node.parent.type == "scoped_type_identifier":
            return  # the outermost node holds the whole name
        text = _compact(_text(node))
        line = node.start_point.row + 1
        simple = text.split(".", 1)[0]
        if simple in self._classes:
            # ``Outer.Inner`` where ``Outer`` came from an import.
            self._symbol(maven_key(self._classes[simple] + text[len(simple) :]), line)
        elif self._is_external(text):
            self._symbol(maven_key(text), line)
        else:
            self._candidate(simple)

    def _annotation(self, node: Any) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        text = _compact(_text(name_node))
        line = node.start_point.row + 1
        key = self._key_for_type(text)
        if key is None:
            # ``@RequestMapping(method = …)`` under ``import a.b.*``: the class
            # has no FQCN, but its attributes are still the facts a rule names,
            # so they are recorded under every class wildcard that could supply
            # it — the policy ``names`` already follows. The own-package
            # post-pass drops the ones an own package supplies.
            for owner in self._wildcard_owners(text):
                self._annotation_attributes(maven_key(f"{owner}.{text}"), node)
            return
        self._symbol(key, line)
        self._annotation_attributes(key, node)

    def _annotation_attributes(self, key: str, node: Any) -> None:
        """``@C(attr = …)`` → a member per attribute; ``@C("x")`` → ``value``."""
        arguments = node.child_by_field_name("arguments")
        if arguments is None:
            return
        pairs = [
            child
            for child in arguments.named_children
            if child.type == "element_value_pair"
        ]
        if pairs:
            for pair in pairs:
                attribute = pair.child_by_field_name("key")
                if attribute is None:
                    continue
                self._member(f"{key}.{_text(attribute)}", pair.start_point.row + 1)
        elif arguments.named_children:
            # The single-value shorthand: ``@C("x")`` sets ``value``.
            self._member(f"{key}.value", node.start_point.row + 1)

    def _method_invocation(self, node: Any) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _text(name_node)
        line = node.start_point.row + 1
        receiver = node.child_by_field_name("object")
        if receiver is None:
            self._bare_use(name, line)
            return
        if receiver.type in ("this", "super"):
            return
        segments = _dotted_chain(receiver)
        if segments is None:
            return
        self._qualified_use(segments, name, line)

    def _field_access(self, node: Any) -> None:
        parent = node.parent
        if (
            parent is not None
            and parent.type in ("field_access", "method_invocation")
            and parent.child_by_field_name("object") == node
        ):
            return  # the outer node sees the whole chain
        receiver = node.child_by_field_name("object")
        field = node.child_by_field_name("field")
        if receiver is None or field is None or receiver.type in ("this", "super"):
            return
        segments = _dotted_chain(receiver)
        if segments is None:
            return
        self._qualified_use(segments, _text(field), node.start_point.row + 1)

    def _method_reference(self, node: Any) -> None:
        named = node.named_children
        if not named:
            return
        receiver = named[0]
        member = named[1] if len(named) > 1 else None
        name = _text(member) if member is not None else "new"
        if name in _NOT_A_TYPE_NAME:
            return
        segments = _dotted_chain(receiver)
        if segments is None:
            return
        line = node.start_point.row + 1
        if name == "new":
            key = self._key_for_type(".".join(segments))
            if key is not None:
                self._symbol(key, line)
            else:
                self._candidate(segments[0])
            return
        self._qualified_use(segments, name, line)

    def _bare_identifier(self, node: Any) -> None:
        """A statically imported name used bare: ``MAX``, ``assertEquals``."""
        name = _text(node)
        if name not in self._statics or name in self._declared:
            return
        parent = node.parent
        if parent is None or parent.type in _NOT_A_REFERENCE:
            return
        if _is_binding_name(node, parent):
            return
        if parent.type == "element_value_pair" and (
            parent.child_by_field_name("key") == node
        ):
            return  # the attribute name, not a value
        self._member(maven_key(self._statics[name]), node.start_point.row + 1)

    def _bare_use(self, name: str, line: int) -> None:
        """A name called with no receiver: a static import, or a wildcard case."""
        if name in self._declared:
            return  # the file's own method shadows any static import of that name
        if name in self._statics:
            self._member(maven_key(self._statics[name]), line)
        else:
            self._unbound_members.add(name)

    def _qualified_use(self, segments: list[str], name: str, line: int) -> None:
        """``C.m`` / ``org.x.Y.m``: a member of the class the chain starts at."""
        owner = self._owner_of(segments)
        if owner is None:
            # ``entity.getName()``, ``list.add(x)``: a call on a value, which the
            # scanner does not resolve (spec1 Non-Goals). Only a capitalized
            # root can be a class a wildcard import supplied — the Java
            # convention is the only signal there is — so a variable name never
            # lands in a wildcard entry.
            if _looks_like_type(segments[0]):
                self._candidate(segments[0])
            return
        class_name, nested, from_import = owner
        if not from_import:
            # A fully qualified usage names its class nowhere else, so the class
            # itself is a symbol here as well as the member (FR-7).
            self._symbol(maven_key(class_name), line)
        member = nested[0] if nested else name
        self._member(maven_key(f"{class_name}.{member}"), line)

    # -- name resolution ---------------------------------------------------

    def _key_for_type(self, text: str) -> str | None:
        """The maven key a type (or annotation) name resolves to, if it does."""
        simple = text.split(".", 1)[0]
        if text in self._classes:
            return maven_key(self._classes[text])
        if simple in self._classes:
            return maven_key(self._classes[simple] + text[len(simple) :])
        if text in self._statics:
            return maven_key(self._statics[text])
        if text in self._declared_types:
            return None
        if self._is_external(text):
            return maven_key(text)
        self._candidate(simple)
        return None

    def _candidate(self, name: str) -> None:
        """Record a simple name no import explains: a wildcard may supply it.

        A name the file declares itself (its own type, method, field or
        parameter) is not a candidate: nothing is imported to supply it
        (AC-5.2). Neither is a ``java.lang`` type (imported implicitly), a
        statically imported name, or a name that does not look like a type —
        ``list.add(x)`` is a call on a variable, and the Java convention of a
        capitalized type name is what tells them apart.
        """
        if not _looks_like_type(name):
            return
        if name in self._declared or name in self._statics or name in _JAVA_LANG:
            return
        self._unbound_types.add(name)

    def _wildcard_owners(self, text: str) -> list[str]:
        """The class-wildcard packages that could supply an unresolved type name."""
        simple = text.split(".", 1)[0]
        if not _looks_like_type(simple):
            return []
        if (
            simple in self._declared
            or simple in self._statics
            or simple in self._classes
            or simple in _JAVA_LANG
        ):
            return []
        return [owner for owner, _ in self._class_wildcards]

    def _owner_of(
        self, segments: list[str]
    ) -> tuple[str, list[str], bool] | None:
        """``(class FQCN, segments after the class, came from an import)``.

        ``['List', 'of']`` with ``import java.util.List`` gives
        ``('java.util.List', [], True)``; ``['HttpStatus', 'OK']`` the same way
        gives ``('…HttpStatus', ['OK'], True)``; ``['org', 'springframework',
        'util', 'Assert']`` with no import gives itself with ``False``, so the
        caller also records the class as a symbol. ``['entity', 'getName']`` is
        a call on a variable and resolves to nothing.
        """
        root = segments[0]
        if root in self._classes:
            return self._classes[root], segments[1:], True
        if root in self._statics:
            # A statically imported member is not a class: ``m.foo()`` is a call
            # on a value, and the scanner does not resolve those.
            return None
        if len(segments) < 2:
            return None
        joined = ".".join(segments)
        if not self._is_external(joined):
            return None
        split = _split_class(segments)
        return ".".join(segments[:split]), segments[split:], False

    def _is_external(self, name: str) -> bool:
        """Whether a name starts with a declared groupId or its parent (spec6).

        See :func:`_qualified_prefixes` for why the parent counts.
        """
        return any(
            name == group or name.startswith(group + ".") for group in self._group_ids
        )

    # -- output ------------------------------------------------------------

    def _symbol(self, key: str, line: int) -> None:
        self._add("symbols", self.facts.symbols, key, line)

    def _member(self, key: str, line: int) -> None:
        self._add("members", self.facts.members, key, line)

    def _wildcard(self, key: str, line: int, names: tuple[str, ...]) -> None:
        self._add("wildcard", self.facts.wildcard_imports, key, line, names)

    def _add(
        self,
        section: str,
        target: list[Usage],
        key: str,
        line: int,
        names: tuple[str, ...] = (),
    ) -> None:
        marker = (section, key, line)
        if marker in self._seen:
            return
        self._seen.add(marker)
        target.append(
            Usage(
                key=key,
                file=self.context.relative,
                line=line,
                test=self.context.test,
                names=names,
            )
        )


# --- post-pass: the repo's own packages -----------------------------------


def filter_own_packages(context: PostPassContext) -> None:
    """Drop facts about the repo's own packages, repo-wide (spec7 FR-7).

    ``com.acme.shop.web`` importing ``com.acme.shop.service.Order`` is the
    repo's own code in another module, not an external library, so it is not a
    fact — the Java counterpart of spec3's rule for relative imports. One file
    cannot decide this (a sibling module's package is unknown to it), which is
    why it is a post-pass over every source's facts.

    A wildcard entry keeps only the simple names its package could really
    supply: a name the file's own package declares needs no import at all. The
    replaced facts are written back to ``context.files``, and ``scan()`` merges
    them after the post-passes, so the profile has the filtered entries.
    """
    java = {
        relative: facts
        for relative, facts in context.files.items()
        if facts.package_name is not None
    }
    if not java:
        return
    packages = {facts.package_name for facts in java.values() if facts.package_name}
    declared: dict[str, set[str]] = {}
    for facts in java.values():
        declared.setdefault(facts.package_name or "", set()).update(
            facts.local_declarations
        )
    for relative, facts in java.items():
        # The names the file gets without an external import: its own package's
        # types, and the types of every own package it imports with a wildcard
        # (``import com.acme.shop.service.*``). Neither is a name an external
        # wildcard supplies.
        own_names = set(declared.get(facts.package_name or "", set()))
        external_wildcards: list[str] = []
        for usage in facts.wildcard_imports:
            owner = _wildcard_owner(usage.key)
            if owner in packages:
                own_names.update(declared.get(owner, set()))
            elif not _is_own(usage.key, packages):
                external_wildcards.append(owner)
        imported = {usage.key for usage in facts.symbols}
        context.files[relative] = replace(
            facts,
            symbols=[
                usage for usage in facts.symbols if not _is_own(usage.key, packages)
            ],
            members=[
                usage
                for usage in facts.members
                if not _is_own(usage.key, packages)
                and not _is_own_wildcard_member(
                    usage.key, external_wildcards, own_names, imported
                )
            ],
            wildcard_imports=[
                _without_own_names(usage, own_names)
                for usage in facts.wildcard_imports
                if not _is_own(usage.key, packages)
            ],
        )


def _wildcard_owner(key: str) -> str:
    """``maven:a.b.*`` → ``a.b``."""
    if key.startswith("maven:"):
        key = key[len("maven:") :]
    return key[:-2] if key.endswith(".*") else key


def _is_own_wildcard_member(
    key: str, wildcards: list[str], own_names: set[str], imported: set[str]
) -> bool:
    """An annotation attribute recorded under an external wildcard for an own type.

    ``@Audited(level = …)`` with ``Audited`` in an own package is recorded as
    ``maven:<wildcard>.Audited.level`` by the extractor, which cannot know the
    sibling packages. A class that is also imported explicitly
    (``maven:<wildcard>.Audited`` is a symbol) is the external one, so it stays.
    """
    bare = key[len("maven:") :] if key.startswith("maven:") else key
    for owner in wildcards:
        if not bare.startswith(owner + "."):
            continue
        rest = bare[len(owner) + 1 :]
        name, dot, _ = rest.partition(".")
        if dot and name in own_names and maven_key(f"{owner}.{name}") not in imported:
            return True
    return False


def _without_own_names(usage: Usage, own_names: set[str]) -> Usage:
    """A wildcard entry without the simple names the file's own package declares."""
    if not usage.names:
        return usage
    kept = tuple(name for name in usage.names if name not in own_names)
    return usage if kept == usage.names else replace(usage, names=kept)


def _is_own(key: str, packages: set[str]) -> bool:
    """Whether a fact's key names a package this repo declares.

    The key is compared segment by segment, so an own package ``com.acme.shop``
    claims ``com.acme.shop.web.Order`` but not a (hypothetical) external
    ``com.acme.shopping.Cart``.
    """
    if key.startswith("maven:"):
        key = key[len("maven:") :]
    if key.endswith(".*"):
        key = key[:-2]
    prefix = ""
    for segment in key.split("."):
        prefix = f"{prefix}.{segment}" if prefix else segment
        if prefix in packages:
            return True
    return False


# --- parsing --------------------------------------------------------------

_PARSERS: dict[str, Any] = {}


def _parser() -> Any:
    """One parser for the Java grammar, reused: building a language is not free."""
    if "java" not in _PARSERS:
        from tree_sitter import Language, Parser

        import tree_sitter_java

        _PARSERS["java"] = Parser(Language(tree_sitter_java.language()))
    return _PARSERS["java"]


def extract_java(context: SourceContext) -> FileFacts:
    """Every external import, usage and wildcard of one ``.java`` file (FR-7)."""
    if context.language not in GRAMMARS:
        return FileFacts()
    try:
        tree = _parser().parse(context.data)
    except Exception as exc:  # a grammar failure is a diagnostic, never a crash
        return FileFacts(
            package_name="",
            diagnostics=[
                Diagnostic(
                    kind="parse_error",
                    file=context.relative,
                    detail=f"{type(exc).__name__}: {exc}",
                )
            ],
        )

    root = tree.root_node
    if root.has_error and _nothing_parsed(root):
        return FileFacts(
            package_name="",
            diagnostics=[
                Diagnostic(
                    kind="parse_error",
                    file=context.relative,
                    detail="the file could not be parsed",
                )
            ],
        )

    facts = _Extractor(context, root).run()
    if root.has_error:
        # AC-5.4: what parsed is recorded, the rest is reported, never silent.
        error = _first_error(root)
        facts.diagnostics.append(
            Diagnostic(
                kind="partial_parse_error",
                file=context.relative,
                line=(error.start_point.row + 1) if error is not None else None,
                detail="some of the file could not be parsed",
            )
        )
    return facts


def _first_error(root: Any) -> Any | None:
    return next((node for node in _walk(root) if node.is_error), None)


def _nothing_parsed(root: Any) -> bool:
    """``True`` when the parse produced no usable statement at all."""
    if not root.named_children:
        return True
    if all(child.is_error for child in root.named_children):
        # ``}}} garbage`` parses as one error node and nothing else. (The error
        # need not reach the last byte: a trailing newline is outside it.)
        return True
    error = _first_error(root)
    if error is None:
        return False
    return error.start_byte == root.start_byte and error.end_byte >= root.end_byte


# --- tree helpers ---------------------------------------------------------


def _walk(node: Any) -> Iterator[Any]:
    """Every node in the subtree, the root first."""
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.children))


def _text(node: Any) -> str:
    return node.text.decode("utf-8", "replace") if node is not None else ""


def _without_keyword(text: str, keyword: str) -> str:
    """``import static a.b.C;`` → ``a.b.C`` (keyword and ``;`` dropped)."""
    body = text.strip()
    if body.startswith(keyword):
        body = body[len(keyword) :]
    return body.strip().rstrip(";").strip()


_COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.DOTALL)


def _compact(text: str) -> str:
    """A Java name without the comments and whitespace Java allows around its dots."""
    return "".join(_COMMENT.sub(" ", text).split())


def _dotted_chain(node: Any) -> list[str] | None:
    """``a.b.C`` as ``['a', 'b', 'C']``; ``None`` when it is not a plain chain."""
    if node.type == "identifier":
        return [_text(node)]
    if node.type == "field_access":
        receiver = node.child_by_field_name("object")
        field = node.child_by_field_name("field")
        if receiver is None or field is None:
            return None
        head = _dotted_chain(receiver)
        return None if head is None else head + [_text(field)]
    if node.type == "scoped_identifier":
        return _compact(_text(node)).split(".")
    return None


def _looks_like_nested_type(name: str) -> bool:
    """``Entry`` is a type, ``APPLICATION_JSON`` / ``MAX`` a constant, ``of`` a method.

    A statically imported name is a nested type when it follows the type naming
    convention: a capital first letter and at least one lower-case letter.
    """
    return _looks_like_type(name) and any(char.islower() for char in name)


def _qualified_prefixes(
    group_ids: tuple[str, ...] | list[str], own_group_ids: tuple[str, ...] | list[str]
) -> tuple[str, ...]:
    """The prefixes a fully qualified name without an import is external under.

    Every declared groupId, plus its parent groupId: a Spring Boot service
    declares only ``org.springframework.boot`` starters, yet its code names
    ``org.springframework.util.Assert`` (``spring-core``, a transitive
    dependency) — the same project family under the parent groupId. A parent
    needs at least two segments (``org`` or ``io`` names everyone), and a parent
    that is, contains or lies under one of the repo's own groupIds is left out,
    so ``com.acme.platform`` never makes the repo's ``com.acme.shop`` external.
    """
    prefixes = set(group_ids)
    for group in group_ids:
        parent = group.rpartition(".")[0]
        if parent.count(".") < 1:
            continue
        if any(
            own == parent
            or own.startswith(parent + ".")
            or parent.startswith(own + ".")
            for own in own_group_ids
        ):
            continue
        prefixes.add(parent)
    return tuple(sorted(prefixes))


def _looks_like_type(name: str) -> bool:
    """Java's convention: a type name starts with a capital, a variable does not.

    The only signal a scanner has without a classpath, and the reason a wildcard
    entry lists ``Widget`` but never ``entity`` (spec7 AC-5.2).
    """
    return bool(name) and name[0].isupper()


def _split_class(segments: list[str]) -> int:
    """Index one past the class name of a fully qualified chain.

    Java's convention (package segments are lower case, type names are not) is
    the only signal a scanner has without a classpath: ``org.springframework.
    http.HttpStatus.OK`` splits after ``HttpStatus``. A chain with no type-like
    segment keeps its whole length, so the last segment is the owner.
    """
    for index, segment in enumerate(segments):
        if segment[:1].isupper():
            return index + 1
    return len(segments)


def _declared_name(node: Any) -> str:
    name = node.child_by_field_name("name")
    if name is None:
        # ``type_parameter``, ``enhanced_for_statement`` and ``lambda_expression``
        # declare their name as the first named child.
        name = next(iter(node.named_children), None)
    return _text(name)


def _is_binding_name(node: Any, parent: Any) -> bool:
    """Whether ``node`` is the declared name of ``parent``, not a use of it."""
    name = parent.child_by_field_name("name")
    if name is not None:
        return name == node
    return parent.type in _DECLARING_NODES


__all__ = [
    "GRAMMARS",
    "extract_java",
    "filter_own_packages",
]
