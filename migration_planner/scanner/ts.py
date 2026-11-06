"""TypeScript / JavaScript extraction: imports, members, decorators (spec 026.3).

One pure function of the file's bytes, so spec9 can cache it and run it in a
process pool: :func:`extract_ts`.

What becomes a fact
-------------------

**Imports of an external package.** ``import { A } from 'pkg'`` records
``npm:pkg#A`` at the import's line; the local name is kept so ``A.b`` later in
the same file becomes ``npm:pkg#A.b``. Every row of the FR-5 table is handled:
named, aliased, default (``#default``), namespace, side-effect, ``import type``
and inline ``{ type T }`` (``type_only``), ``export … from`` and ``export *
from``, the ``import('pkg')`` / ``require('pkg')`` calls and TypeScript's
``import x = require('pkg')``.

``symbols[]`` locations are **import sites** (spec1 FR-9). Only a side-effect
``import 'pkg'`` goes to ``side_effect_imports``; a package-level use without a
symbol (``import('pkg')``, ``require('pkg')``, ``export * from 'pkg'``) is the
symbol ``npm:pkg`` in ``symbols``.

**Own code is not a fact.** A relative specifier, a ``compilerOptions.paths``
alias, a specifier under ``baseUrl`` or a workspace package name is counted in
``own_imports`` and stored as an :class:`OwnImport`, which is what spec4 needs to
follow the import through its barrel to a real external package. A Node builtin
is skipped without a count: it is neither — unless the repo declares an npm
package of that name (``events``, ``buffer``), which is then external.

**Members.** ``Local.member`` for every identifier bound to an external import,
first segment only (``A.b.c`` → ``A.b``). A local declaration of the same name
inside a scope stops tracking in that scope, so a parameter that shadows an
import is not mistaken for the import.

**Decorators.** The literal keys of a decorator's first object argument are
members (``npm:@angular/core#Component.standalone``), shorthand keys
(``{ selector }``) and namespaced decorators (``@core.Component({…})``)
included, because most Angular rules are about decorator options. The
decorator itself adds no symbol location: its import site is already one.

Parsing
-------

tree-sitter with the grammar the file extension asks for: ``.ts`` → typescript,
``.tsx`` → tsx, ``.js`` / ``.jsx`` / ``.mjs`` / ``.cjs`` → javascript. A tree
whose root has an error covering the whole file is a ``parse_error`` diagnostic;
a partial parse still yields whatever imports did parse, because one bad file
must never lose the rest of its facts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterator

from migration_keys.keys import npm_key
from migration_keys.specifiers import (
    is_node_builtin,
    is_own_code,
    own_path_aliases,
    package_of_specifier,
)

from migration_planner.scanner.contract import (
    Diagnostic,
    ExportBinding,
    FileFacts,
    OwnImport,
    OwnMember,
    SourceContext,
    Usage,
)
from migration_planner.scanner.templates import template_usages

# Discovery language tag → tree-sitter grammar. ``jsx`` shares the javascript
# grammar, which parses JSX; ``tsx`` needs its own because ``<X>`` is a cast in
# plain TypeScript.
GRAMMARS: tuple[str, ...] = ("ts", "tsx", "js", "jsx", "mjs", "cjs")

#: The decorator whose inline template is also a template (spec5 FR-6).
_COMPONENT = "Component"

#: The decorator option that holds an inline template.
_TEMPLATE_OPTION = "template"

#: Node types whose body is a scope for shadowing checks.
_SHADOWING_SCOPES: frozenset[str] = frozenset(
    {
        "arrow_function",
        "catch_clause",
        "class_declaration",
        "function_declaration",
        "function_expression",
        "generator_function",
        "generator_function_declaration",
        "lexical_declaration",
        "method_definition",
        "variable_declaration",
    }
)

#: Node types that hold block-scoped declarations covering the whole block.
_BLOCK_SCOPES: frozenset[str] = frozenset(
    {"statement_block", "class_body", "program", "switch_body"}
)

_FUNCTION_SCOPES: frozenset[str] = frozenset(
    {
        "arrow_function",
        "function_declaration",
        "function_expression",
        "generator_function",
        "generator_function_declaration",
        "method_definition",
    }
)

# A string literal's content, without the quotes.
_STRING_QUOTE_RE = re.compile(r"^['\"]|['\"]$")


@dataclass
class _Binding:
    """One identifier bound to an external symbol, for member tracking.

    An **own-code** binding (``import { di } from '@app/core'``) carries no
    package yet: spec4 decides whether the barrel chain reaches one, so its
    member accesses are kept as :class:`OwnMember` instead of a fact.
    """

    package: str
    symbol: str  # the imported name, ``default``, or ``*`` for a namespace
    own: bool = False

    def key(self, member: str = "") -> str:
        # A namespace import has no symbol of its own: ``core.inject`` is the
        # symbol ``inject`` of the package, not a member of ``*``.
        if self.symbol == "*":
            return npm_key(self.package, member)
        return npm_key(self.package, self.symbol, member)


class _Extractor:
    """Walks one parsed tree and accumulates that file's facts."""

    def __init__(self, context: SourceContext, root: Any) -> None:
        self.context = context
        self.root = root
        self.facts = FileFacts()
        self._bindings: dict[str, _Binding] = {}
        self._seen_symbols: set[tuple[str, int, bool]] = set()
        self._seen_members: set[tuple[str, int]] = set()
        self._seen_own_members: set[tuple[str, str, int, str]] = set()
        # ``(start, end)`` byte spans of declarators that *created* a binding
        # (``const m = require('pkg')``). They declare the binding rather than
        # shadow it, so the shadow check must skip them.
        self._binding_declarations: set[tuple[int, int]] = set()
        path_map = context.env.path_map
        # Only aliases into the repo's own code: one that redirects into
        # ``node_modules`` keeps its imports external (FR-5).
        self._path_aliases = (
            own_path_aliases(path_map.paths) if path_map is not None else ()
        )
        # ``{local name: (specifier, imported name)}`` for every static import,
        # so ``import { X } from 'pkg'; export { X }`` re-exports ``pkg#X``.
        self._imports: dict[str, tuple[str, str]] = {}

    def run(self) -> FileFacts:
        for node in _walk(self.root):
            if node.type == "import_statement":
                self._import_statement(node)
            elif node.type == "export_statement":
                self._export_statement(node)
            elif node.type == "call_expression":
                self._call_expression(node)
            elif node.type == "decorator":
                self._decorator(node)
            elif node.type in ("lexical_declaration", "variable_declaration"):
                self._declaration(node)
            elif node.type in (
                "class_declaration",
                "function_declaration",
                "interface_declaration",
                "enum_declaration",
                "type_alias_declaration",
            ):
                self._named_declaration(node)
        self._collect_members()
        self._link_local_exports()
        return self.facts

    def _link_local_exports(self) -> None:
        """``import { X } from 'p'; export { X }``: the export is a re-export of ``p``.

        spec4 must follow it to ``p`` instead of treating ``X`` as declared here.
        A re-exported namespace import (``import * as ns``) becomes a namespace
        export.
        """
        for published, binding in list(self.facts.export_map.items()):
            if binding.specifier or binding.original not in self._imports:
                continue
            specifier, imported = self._imports[binding.original]
            self.facts.local_declarations.discard(binding.original)
            if imported == "*":
                del self.facts.export_map[published]
                self.facts.namespace_exports[published] = specifier
                continue
            self.facts.export_map[published] = ExportBinding(
                specifier=specifier, original=imported
            )

    # -- imports ----------------------------------------------------------

    def _import_statement(self, node: Any) -> None:
        require_clause = _first_child(node, "import_require_clause")
        if require_clause is not None:
            # TypeScript ``import fs = require('fs-extra')``: a ``require`` bound
            # to one name, i.e. a package-level use plus member tracking.
            source = _first_child(require_clause, "string")
            identifier = _first_child(require_clause, "identifier")
            specifier = _string_value(source)
            if specifier is None:
                return
            self._record_import(
                node,
                specifier=specifier,
                namespace=_text(identifier) if identifier is not None else "",
                package_level=True,
            )
            return
        specifier = _string_value(node.child_by_field_name("source"))
        if specifier is None:
            return
        type_only = _has_child(node, "type")
        named: dict[str, str] = {}
        type_names: set[str] = set()
        default = ""
        namespace = ""
        clause = _first_child(node, "import_clause")
        if clause is not None:
            for child in clause.named_children:
                if child.type == "identifier":
                    default = _text(child)
                elif child.type == "namespace_import":
                    identifier = _first_child(child, "identifier")
                    namespace = _text(identifier) if identifier is not None else ""
                elif child.type == "named_imports":
                    for specifier_node in _children_of_type(child, "import_specifier"):
                        name = specifier_node.child_by_field_name("name")
                        alias = specifier_node.child_by_field_name("alias")
                        imported = _text(name)
                        if imported:
                            local = _text(alias) or imported
                            named[local] = imported
                            if _has_child(specifier_node, "type"):
                                # ``import { type Signal, inject }``
                                type_names.add(local)

        if named and not default and not namespace and set(named) == type_names:
            type_only = True  # every specifier is ``type``: a type-only import
        self._record_import(
            node,
            specifier=specifier,
            named=named,
            default=default,
            namespace=namespace,
            type_only=type_only,
            type_names=type_names,
            side_effect=clause is None,
        )

    def _export_statement(self, node: Any) -> None:
        clause = _first_child(node, "export_clause")
        specifier = _string_value(node.child_by_field_name("source"))
        if specifier is None:
            # ``export { a, b }`` / ``export class X {}``: the file itself
            # publishes these names, which spec4 reads to know where a name ends.
            if clause is not None:
                for entry in _children_of_type(clause, "export_specifier"):
                    published = _export_name(entry)
                    original = _export_original(entry)
                    if published:
                        if original not in self._imports:
                            self.facts.local_declarations.add(original)
                        self.facts.export_map[published] = ExportBinding(
                            specifier="", original=original
                        )
            return

        if any(child.type == "*" for child in node.children):
            self.facts.star_exports.append(specifier)
        named: dict[str, str] = {}
        namespace_local = ""
        namespace = _first_child(node, "namespace_export")
        if namespace is not None:
            identifier = _first_child(namespace, "identifier")
            if identifier is not None:
                namespace_local = _text(identifier)
                self.facts.namespace_exports[namespace_local] = specifier
        if clause is not None:
            for entry in _children_of_type(clause, "export_specifier"):
                published = _export_name(entry)
                original = _export_original(entry)
                if published:
                    self.facts.export_map[published] = ExportBinding(
                        specifier=specifier, original=original
                    )
                    named[published] = original

        # A re-export of an external package is also a use of the names it
        # publishes (FR-5). ``export *`` publishes names we cannot enumerate, so
        # it stays a spec4 input and records no fact of its own.
        if named or namespace_local:
            self._record_import(
                node, specifier=specifier, named=named, namespace=namespace_local
            )
        elif specifier in self.facts.star_exports and self._is_external(specifier):
            # ``export * from '@angular/cdk/a11y'``: the names cannot be
            # enumerated, but the package is used — a package-level symbol.
            self._record_import(node, specifier=specifier, package_level=True)

    def _call_expression(self, node: Any) -> None:
        """``import('pkg')``, ``require('pkg')`` and destructured ``require``."""
        function = node.child_by_field_name("function")
        if function is None:
            return
        is_dynamic = function.type == "import"
        is_require = function.type == "identifier" and _text(function) == "require"
        if not (is_dynamic or is_require):
            return
        arguments = node.child_by_field_name("arguments")
        specifier = _first_string_argument(arguments)
        if specifier is None:
            return

        named: dict[str, str] = {}
        namespace = ""
        declarator = _enclosing_declarator(node)
        if declarator is not None:
            pattern = declarator.child_by_field_name("name")
            if pattern is not None and pattern.type == "object_pattern":
                named = _pattern_names(pattern)
            elif pattern is not None and pattern.type == "identifier" and is_dynamic:
                # ``const mod = await import('pkg')``: a namespace-like binding
                # only when it is awaited; otherwise it is an opaque promise.
                if _is_awaited(node):
                    namespace = _text(pattern)
            elif pattern is not None and pattern.type == "identifier" and is_require:
                namespace = _text(pattern)
        self._record_import(
            node,
            specifier=specifier,
            named=named,
            namespace=namespace,
            package_level=not named,
            declarator=declarator,
        )

    def _record_import(
        self,
        node: Any,
        *,
        specifier: str,
        named: dict[str, str] | None = None,
        default: str = "",
        namespace: str = "",
        type_only: bool = False,
        type_names: set[str] | None = None,
        package_level: bool = False,
        side_effect: bool = False,
        declarator: Any | None = None,
    ) -> None:
        """One import of ``specifier``: an external fact, or own code for spec4.

        ``package_level`` records ``npm:<pkg>`` itself rather than a symbol. It
        is what ``import('pkg')`` and ``require('pkg')`` without destructuring
        are: a use of the package, whose symbols are not statically known
        (FR-5's "+ destructured names when present").
        """
        named = named or {}
        type_names = type_names or set()
        line = node.start_point.row + 1
        if self._is_builtin(specifier):
            return
        if node.type == "import_statement":
            for local, imported in named.items():
                self._imports.setdefault(local, (specifier, imported))
            if default:
                self._imports.setdefault(default, (specifier, "default"))
            if namespace:
                self._imports.setdefault(namespace, (specifier, "*"))
        if self._is_own(specifier):
            self.facts.own_imports += 1
            self.facts.own_import_bindings.append(
                OwnImport(
                    relative=self.context.relative,
                    line=line,
                    test=self.context.test,
                    specifier=specifier,
                    is_relative=specifier.startswith((".", "/")),
                    named=dict(named),
                    default=default,
                    namespace=namespace,
                    type_only=type_only,
                    type_names=frozenset(type_names),
                )
            )
            # Own code still binds: ``core.inject(…)`` on a barrel has to reach
            # the external package it re-exports (spec4), so the local names are
            # tracked here and resolved in the post-pass.
            for local, imported in named.items():
                self._bind(local, _Binding(package="", symbol=imported, own=True))
            if default:
                self._bind(default, _Binding(package="", symbol="default", own=True))
            if namespace:
                self._bind(namespace, _Binding(package="", symbol="*", own=True))
            return

        package = package_of_specifier(specifier)
        if not package:
            return
        if not (named or default or namespace):
            # ``import 'zone.js'`` is a side effect; ``require('legacy')`` /
            # ``import('pkg')`` / ``export * from 'pkg'`` use the package itself.
            self._add_symbol(package, "", line, side_effect=side_effect)
            return
        if package_level:
            # A dynamic import or a ``require`` bound to one name: the package
            # is used, and the binding still tracks members (``mod.thing()``).
            self._add_symbol(package, "", line)
            if namespace:
                self._bind(namespace, _Binding(package=package, symbol="*"))

        for local, imported in named.items():
            self._add_symbol(package, imported, line, type_only or local in type_names)
            self._bind(local, _Binding(package=package, symbol=imported))
        if default:
            self._add_symbol(package, "default", line, type_only)
            self._bind(default, _Binding(package=package, symbol="default"))
        if namespace and not package_level:
            # A static ``import * as ns``: the package is used through members,
            # each of which becomes its own symbol, so no package fact here.
            self._bind(namespace, _Binding(package=package, symbol="*"))
        if declarator is not None:
            # ``const m = require('pkg')`` declares ``m``; the shadow check must
            # not then read that declaration as shadowing the binding it made.
            self._binding_declarations.add((declarator.start_byte, declarator.end_byte))

    def _is_builtin(self, specifier: str) -> bool:
        return is_node_builtin(
            specifier, declared_dependencies=self.context.env.declared_dependencies
        )

    def _is_own(self, specifier: str) -> bool:
        env = self.context.env
        return is_own_code(
            specifier,
            own_packages=env.own_packages,
            path_aliases=self._path_aliases,
            base_url_roots=env.base_url_roots,
            declared_dependencies=env.declared_dependencies,
        )

    def _is_external(self, specifier: str) -> bool:
        return not self._is_builtin(specifier) and not self._is_own(specifier)

    def _bind(self, local: str, binding: _Binding) -> None:
        if local and local not in self._bindings:
            self._bindings[local] = binding

    def _add_symbol(
        self,
        package: str,
        symbol: str,
        line: int,
        type_only: bool = False,
        *,
        side_effect: bool = False,
    ) -> None:
        """One import site. ``side_effect`` only for ``import 'pkg'`` (FR-5)."""
        key = npm_key(package, symbol) if symbol else npm_key(package)
        site = (key, line, side_effect)
        if site in self._seen_symbols:
            return
        self._seen_symbols.add(site)
        usage = Usage(
            key=key,
            file=self.context.relative,
            line=line,
            test=self.context.test,
            type_only=type_only,
        )
        if side_effect and not symbol:
            self.facts.side_effect_imports.append(usage)
        else:
            self.facts.symbols.append(usage)

    # -- declarations (for spec4 and shadowing) ---------------------------

    def _declaration(self, node: Any) -> None:
        if not _is_top_level(node):
            return  # a ``const`` inside a function is not a module export
        for declarator in _children_of_type(node, "variable_declarator"):
            pattern = declarator.child_by_field_name("name")
            if pattern is not None:
                self.facts.local_declarations.update(_declared_names(pattern))

    def _named_declaration(self, node: Any) -> None:
        if not _is_top_level(node):
            return
        name = node.child_by_field_name("name")
        if name is not None:
            self.facts.local_declarations.add(_text(name))

    # -- decorators -------------------------------------------------------

    def _decorator(self, node: Any) -> None:
        """``@Component({…})``: the literal option keys become members.

        The decorator adds no symbol location: ``symbols[].locations`` are import
        sites (spec1 FR-9), and the import is already one. ``@core.Component``
        on a namespace import resolves to ``npm:<pkg>#Component`` (its option
        keys are members of that symbol); the symbol use itself is recorded by
        the member pass.
        """
        call = next(
            (child for child in node.named_children if child.type == "call_expression"),
            None,
        )
        if call is None:
            return  # ``@Input`` without a call: no options to record
        function = call.child_by_field_name("function")
        decorated = self._decorator_binding(function)
        if decorated is None:
            return
        binding, local, symbol = decorated
        arguments = call.child_by_field_name("arguments")
        if arguments is None:
            return
        component = (symbol or binding.symbol) == _COMPONENT
        for argument in arguments.named_children:
            if argument.type != "object":
                continue
            for entry in argument.named_children:
                option = ""
                value = None
                if entry.type == "pair":
                    key = entry.child_by_field_name("key")
                    if key is not None and key.type in (
                        "property_identifier",
                        "string",
                    ):
                        option = _string_value(key) or _text(key)
                    value = entry.child_by_field_name("value")
                elif entry.type == "shorthand_property_identifier":
                    option = _text(entry)  # ``@Component({ selector })``
                elif entry.type == "method_definition":
                    name = entry.child_by_field_name("name")
                    option = _text(name) if name is not None else ""
                if option:
                    self._add_member(
                        binding, local, option, entry.start_point.row + 1, symbol
                    )
                if component and option == _TEMPLATE_OPTION and value is not None:
                    self._inline_template(value)
            break  # only the first object argument carries the options

    def _inline_template(self, value: Any) -> None:
        """``@Component({ template: '…' })``: the spec5 template tokens (FR-6).

        The tokens are located in the ``.ts`` file, not in the string: the line of
        a token is its line in the file, which is why the string's own start line
        is handed to the template lexer.
        """
        content, start_line = _string_content(value)
        if content is None:
            return
        self.facts.templates.extend(
            template_usages(
                content,
                file=self.context.relative,
                test=self.context.test,
                start_line=start_line,
                escapes=True,
            )
        )

    def _decorator_binding(
        self, function: Any | None
    ) -> tuple[_Binding, str, str] | None:
        """The import a decorator's callee names: ``(binding, local, symbol)``."""
        if function is None:
            return None
        if function.type == "identifier":
            local = _text(function)
            binding = self._bindings.get(local)
            if binding is None or binding.symbol == "*":
                return None
            return binding, local, ""
        if function.type == "member_expression":
            object_node = function.child_by_field_name("object")
            property_node = function.child_by_field_name("property")
            if object_node is None or property_node is None:
                return None
            if object_node.type != "identifier":
                return None
            local = _text(object_node)
            namespace = self._bindings.get(local)
            if namespace is None or namespace.symbol != "*":
                return None
            return namespace, local, _text(property_node)
        return None

    # -- members ----------------------------------------------------------

    def _collect_members(self) -> None:
        for node in _walk(self.root):
            if node.type != "member_expression":
                continue
            object_node = node.child_by_field_name("object")
            property_node = node.child_by_field_name("property")
            if object_node is None or property_node is None:
                continue
            if object_node.type != "identifier":
                continue  # only the first segment: ``A.b.c`` reports ``A.b``
            local = _text(object_node)
            binding = self._bindings.get(local)
            if binding is None or self._is_shadowed(local, node):
                continue
            member = _text(property_node)
            if member:
                self._add_member(binding, local, member, node.start_point.row + 1)

    def _is_shadowed(self, local: str, node: Any) -> bool:
        """Whether an inner declaration of ``local`` encloses ``node``.

        A ``const`` / ``let`` shadows from where it is declared to the end of its
        enclosing block, so the check looks at the block a declaration sits in,
        not only at the declaration node itself.
        """
        current = node.parent
        while current is not None:
            if current.type in _SHADOWING_SCOPES and _declares(current, local):
                return True
            if current.type in _BLOCK_SCOPES and _block_declares(
                current, local, owners=self._binding_declarations
            ):
                return True
            current = current.parent
        return False

    def _add_member(
        self,
        binding: _Binding,
        local: str,
        member: str,
        line: int,
        symbol: str = "",
    ) -> None:
        """One member access — a fact, or (for own code) input to spec4.

        ``symbol`` is set only through a namespace local (``@core.Component``),
        where the symbol sits between the namespace and the option key, so it
        replaces the namespace's ``*`` rather than being appended to it.
        """
        if binding.own:
            self._add_own_member(local, member, line, symbol)
            return
        key = (
            npm_key(binding.package, symbol, member) if symbol else binding.key(member)
        )
        site = (key, line)
        if site in self._seen_members:
            return
        self._seen_members.add(site)
        if binding.symbol == "*" and not symbol:
            # ``core.inject(…)`` resolves to the package's symbol, not a member.
            self.facts.symbols.append(
                Usage(
                    key=key,
                    file=self.context.relative,
                    line=line,
                    test=self.context.test,
                )
            )
            return
        self.facts.members.append(
            Usage(
                key=key, file=self.context.relative, line=line, test=self.context.test
            )
        )

    def _add_own_member(
        self, local: str, member: str, line: int, symbol: str = ""
    ) -> None:
        """Keep an own-code access for spec4, once per ``(local, member, line)``."""
        site = (local, member, line, symbol)
        if site in self._seen_own_members:
            return
        self._seen_own_members.add(site)
        self.facts.own_member_bindings.append(
            OwnMember(
                relative=self.context.relative,
                line=line,
                test=self.context.test,
                local=local,
                member=member,
                symbol=symbol,
            )
        )


# --- tree helpers ----------------------------------------------------------


def _is_top_level(node: Any) -> bool:
    """A module-scope declaration: directly in ``program`` or ``export``-ed there.

    Only those can shadow an ``export *`` name; a ``const map`` inside a
    function body is not part of the module's exports (spec4 FR-5).
    """
    parent = node.parent
    if parent is None:
        return False
    if parent.type == "program":
        return True
    return parent.type == "export_statement" and (
        parent.parent is not None and parent.parent.type == "program"
    )


def _walk(node: Any) -> Iterator[Any]:
    """Every node in the subtree, the root first."""
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.children))


def _text(node: Any) -> str:
    return node.text.decode("utf-8", "replace") if node is not None else ""


def _children_of_type(node: Any, kind: str) -> list[Any]:
    return [child for child in node.children if child.type == kind]


def _first_child(node: Any, kind: str) -> Any | None:
    return next((child for child in node.children if child.type == kind), None)


def _has_child(node: Any, kind: str) -> bool:
    return any(child.type == kind for child in node.children)


def _string_value(node: Any | None) -> str | None:
    """The content of a ``string`` node, ``None`` for anything else."""
    if node is None or node.type != "string":
        return None
    return _STRING_QUOTE_RE.sub("", _text(node))


#: Node types that hold a string whose content can be a template.
_STRING_NODE_TYPES: frozenset[str] = frozenset({"string", "template_string"})


def _string_content(node: Any) -> tuple[str | None, int]:
    """``(content, start line)`` of a string or a template literal.

    An inline template is either ``template: '<div>…</div>'`` or a template
    literal. A literal with substitutions (``${…}``) is not a static template:
    its tokens would be a guess, so it is skipped. The start line is the line of
    the opening quote — the first content character may sit a line further down,
    which is why the content keeps its own leading newline.
    """
    if node is None or node.type not in _STRING_NODE_TYPES:
        return None, 0
    if node.type == "template_string" and _has_child(node, "template_substitution"):
        return None, 0
    text = _text(node)
    if len(text) < 2:
        return None, 0
    return text[1:-1], node.start_point.row + 1


def _export_name(node: Any) -> str:
    """The name the exporting file publishes: ``export { X as Y }`` → ``Y``."""
    alias = node.child_by_field_name("alias")
    if alias is not None:
        return _text(alias)
    name = node.child_by_field_name("name")
    return _text(name) if name is not None else _text(node)


def _export_original(node: Any) -> str:
    """The name in the source module: ``export { X as Y }`` → ``X``."""
    name = node.child_by_field_name("name")
    return _text(name) if name is not None else _text(node)


def _first_string_argument(arguments: Any | None) -> str | None:
    """The specifier of a call, only when its first argument is a string literal."""
    if arguments is None:
        return None
    first = next(iter(arguments.named_children), None)
    return _string_value(first)


def _enclosing_declarator(node: Any) -> Any | None:
    """The ``variable_declarator`` a call is the value of, if any.

    The value may be wrapped: ``const m = await import('x')`` puts an
    ``await_expression`` (and possibly parentheses) between the call and the
    declarator, so those are stepped through rather than treated as a stop.
    """
    current = node.parent
    while current is not None:
        if current.type == "variable_declarator":
            return current
        if current.type not in (
            "await_expression",
            "parenthesized_expression",
            "as_expression",
            "non_null_expression",
            "satisfies_expression",
        ):
            return None
        current = current.parent
    return None


def _is_awaited(node: Any) -> bool:
    return any(
        ancestor is not None and ancestor.type == "await_expression"
        for ancestor in _ancestors(node, limit=3)
    )


def _ancestors(node: Any, *, limit: int = 10) -> Iterator[Any]:
    current = node.parent
    count = 0
    while current is not None and count < limit:
        yield current
        current = current.parent
        count += 1


def _pattern_names(pattern: Any) -> dict[str, str]:
    """``{ a, b: c }`` → ``{"a": "a", "c": "b"}`` (local name → imported name)."""
    if pattern.type != "object_pattern":
        return {}
    names: dict[str, str] = {}
    for child in pattern.named_children:
        if child.type == "shorthand_property_identifier_pattern":
            names[_text(child)] = _text(child)
        elif child.type == "pair_pattern":
            key = child.child_by_field_name("key")
            value = child.child_by_field_name("value")
            if key is not None and value is not None and value.type == "identifier":
                names[_text(value)] = _text(key)
    return names


def _declared_names(node: Any) -> set[str]:
    """The identifiers an ``object_pattern`` / ``array_pattern`` / name binds."""
    if node is None:
        return set()
    if node.type in ("identifier", "shorthand_property_identifier_pattern"):
        return {_text(node)}
    if node.type == "pair_pattern":
        return _declared_names(node.child_by_field_name("value"))
    if node.type in ("object_pattern", "array_pattern"):
        names: set[str] = set()
        for child in node.named_children:
            names.update(_declared_names(child))
        return names
    if node.type == "assignment_pattern":
        return _declared_names(node.child_by_field_name("left"))
    if node.type == "rest_pattern":
        inner = next(iter(node.named_children), None)
        return _declared_names(inner)
    return set()


def _declares(scope: Any, local: str) -> bool:
    """Whether ``scope`` declares ``local`` (parameter, variable, catch, class)."""
    if scope.type in _FUNCTION_SCOPES:
        parameters = scope.child_by_field_name("parameters")
        if parameters is not None:
            for parameter in parameters.named_children:
                target = (
                    parameter.child_by_field_name("pattern")
                    or parameter.child_by_field_name("name")
                    or parameter
                )
                if local in _declared_names(target):
                    return True
    if scope.type in ("lexical_declaration", "variable_declaration"):
        for declarator in _children_of_type(scope, "variable_declarator"):
            if local in _declared_names(declarator.child_by_field_name("name")):
                return True
    if scope.type == "catch_clause":
        parameter = scope.child_by_field_name("parameter")
        if local in _declared_names(parameter):
            return True
    if scope.type == "class_declaration":
        name = scope.child_by_field_name("name")
        if name is not None and _text(name) == local:
            return True
    return False


def _block_declares(
    block: Any, local: str, *, owners: set[tuple[int, int]] = frozenset()
) -> bool:
    """Whether a block declares ``local`` with ``const`` / ``let`` / ``class``.

    A block-scoped declaration covers the whole block, so this is checked per
    block rather than per node. ``owners`` are declaration spans that *created*
    an import binding (``const m = require('pkg')``): those declare the binding
    instead of shadowing it, so they are skipped.
    """
    for statement in block.named_children:
        target = statement
        if statement.type == "export_statement":
            target = statement.child_by_field_name("declaration")
            if target is None:
                continue
        if target.type in ("lexical_declaration", "variable_declaration"):
            for declarator in _children_of_type(target, "variable_declarator"):
                if (declarator.start_byte, declarator.end_byte) in owners:
                    continue
                if local in _declared_names(declarator.child_by_field_name("name")):
                    return True
        elif target.type in (
            "class_declaration",
            "function_declaration",
            "enum_declaration",
        ):
            name = target.child_by_field_name("name")
            if name is not None and _text(name) == local:
                return True
    return False


# --- grammar / parser ------------------------------------------------------


def _language(language: str) -> Any:
    """The tree-sitter language for a discovery language tag."""
    from tree_sitter import Language
    import tree_sitter_javascript
    import tree_sitter_typescript

    if language == "tsx":
        return Language(tree_sitter_typescript.language_tsx())
    if language == "ts":
        return Language(tree_sitter_typescript.language_typescript())
    return Language(tree_sitter_javascript.language())


_PARSERS: dict[str, Any] = {}


def _parser(language: str) -> Any:
    """One parser per grammar, reused: building a language is not free."""
    if language not in _PARSERS:
        from tree_sitter import Parser

        _PARSERS[language] = Parser(_language(language))
    return _PARSERS[language]


def extract_ts(context: SourceContext) -> FileFacts:
    """Every TS / JS fact of one file (spec 026 FR-5, members, decorators)."""
    if context.language not in GRAMMARS:
        return FileFacts()
    try:
        tree = _parser(context.language).parse(context.data)
    except Exception as exc:  # a grammar failure is a diagnostic, never a crash
        return FileFacts(
            diagnostics=[
                Diagnostic(
                    kind="parse_error",
                    file=context.relative,
                    detail=f"{type(exc).__name__}: {exc}",
                )
            ]
        )

    root = tree.root_node
    if root.has_error and _nothing_parsed(root):
        return FileFacts(
            diagnostics=[
                Diagnostic(
                    kind="parse_error",
                    file=context.relative,
                    detail="the file could not be parsed",
                )
            ]
        )

    facts = _Extractor(context, root).run()
    if root.has_error:
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
    error = _first_error(root)
    if error is None:
        return False
    return error.start_byte == root.start_byte and error.end_byte >= root.end_byte


__all__ = [
    "GRAMMARS",
    "extract_ts",
]
