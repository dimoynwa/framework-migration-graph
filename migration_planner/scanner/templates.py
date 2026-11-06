"""Angular template syntax tokens (spec 026.5, FR-6).

A template lives in two places: a ``*.html`` file, and the inline ``template``
property of an ``@Component`` decorator (``template: '…'`` or a template
literal). The second one is found by the spec3 decorator pass, which is the only
place that knows the string *and* its line in the ``.ts`` file; it calls
:func:`template_usages` with the string's starting line, which is how an inline
template token gets the line of the ``.ts`` file rather than a line inside the
string.

The lexer is deliberately small — no HTML parser dependency. It walks the text
once and counts a token only where the surrounding syntax makes it an Angular
construct:

- **Block keywords** (``@if``, ``@for``, ``@switch``, ``@defer``, ``@let``,
  ``@else``, ``@else if``, ``@empty``, ``@case``, ``@placeholder``, ``@error``,
  ``@loading``) only at the **start of a block**: after ``{``, after ``}``,
  after a tag, or at the start of the template. ``@if`` in the middle of a word
  or of a paragraph is text, not a block.
- **Expression tokens** (``in``, ``void``, ``typeof``, ``as``, ``let``) only
  inside a **binding**: ``{{ … }}``, ``[prop]="…"``, ``(event)="…"``,
  ``[(prop)]="…"``, ``*dir="…"`` and the condition of a block keyword. Text
  between tags is never an expression, so "in" in a sentence is not a token.
- **Structural directives** (``*ngFor``, ``*ngIf``, ``*ngSwitchCase``, …) as
  ``syntax:angular-template#*ngFor``, whatever the attribute name is.
- **Pipes** used in a binding (``… | async``, ``… | date:'short'``) as
  ``syntax:angular-template#pipe:date``. ``a || b`` is not a pipe.

Tokens are matched against the Angular token list in :mod:`migration_keys.angular`,
so a rule entity and a scanner fact land on the same key. String literals inside
a binding are masked before matching, so ``[title]="'in'"`` does not count
``in``, and an HTML comment is skipped whole (FR-6).

``*.html`` files are only scanned when the owning module is Angular: an
``index.html`` next to a Node service is not a template.
"""

from __future__ import annotations

import re
from bisect import bisect_left
from typing import Callable

from migration_keys.angular import ANGULAR_SYNTAX_TOKENS
from migration_keys.keys import syntax_key

from migration_planner.scanner.contract import FileFacts, SourceContext, Usage

#: ``@if``, ``@else if``, … — the tokens that open or continue a block.
BLOCK_TOKENS: tuple[str, ...] = tuple(
    token for token in ANGULAR_SYNTAX_TOKENS if token.startswith("@")
)

#: ``in``, ``void``, ``typeof``, ``as``, ``let`` — counted inside a binding only.
EXPRESSION_TOKENS: tuple[str, ...] = tuple(
    token for token in ANGULAR_SYNTAX_TOKENS if not token.startswith("@")
)

#: The framework whose template keys the scanner builds.
FRAMEWORK = "angular"

#: One site of a fact: ``(token, index in the text)``.
_Emit = Callable[[str, int], None]


def _block_pattern(tokens: tuple[str, ...]) -> re.Pattern[str]:
    """``@(else\\s+if|if|for|…)``: longest name first, so ``@else if`` wins."""
    names = sorted((token[1:] for token in tokens), key=len, reverse=True)
    alternatives = "|".join(
        re.escape(name).replace(r"\ ", r"\s+") for name in names
    )
    return re.compile(r"@" + "(?:" + alternatives + r")\b")


_BLOCK_RE = _block_pattern(BLOCK_TOKENS)

#: An expression token — not part of a longer identifier and not a property
#: access (``x.in`` is a member, ``index`` is a name).
_EXPRESSION_RE = re.compile(
    r"(?<![\w$.])("
    + "|".join(
        sorted(
            (re.escape(token) for token in EXPRESSION_TOKENS), key=len, reverse=True
        )
    )
    + r")(?![\w$])"
)

#: A pipe inside a binding. Neither bar of ``||`` may start one: that is a
#: logical or, not a pipe.
_PIPE_RE = re.compile(r"(?<!\|)\|(?!\|)\s*([A-Za-z_$][\w$]*)")

#: ``<`` that starts a tag: ``<div``, ``</div>``, ``<!--``, ``<!doctype``, ``<?xml``.
_TAG_START_RE = re.compile(r"<[A-Za-z!/?]")

#: Characters a tag or attribute name may hold (``my-component``, ``svg:path``).
_NAME_CHARS = frozenset("-_:.")

#: Prefixes that make an attribute value an expression (``bind-title``, …).
_BINDING_PREFIXES: tuple[str, ...] = ("bind-", "on-", "bindon-")


def template_usages(
    text: str,
    *,
    file: str,
    test: bool = False,
    start_line: int = 1,
    escapes: bool = False,
) -> list[Usage]:
    """Every template token of ``text``, one usage per ``(key, line)`` site.

    ``start_line`` is the 1-based line of ``text[0]`` in ``file``: ``1`` for an
    HTML file, the line of the opening quote for an inline template.
    ``escapes`` marks a JavaScript string body, where ``\\`` escapes the next
    character (``\\n`` separates statements but stays one file line).
    """
    usages: list[Usage] = []
    seen: set[tuple[str, int]] = set()
    newlines = [index for index, char in enumerate(text) if char == "\n"]

    def add(token: str, index: int) -> None:
        line = start_line + bisect_left(newlines, index)
        site = (token, line)
        if site in seen:
            return
        seen.add(site)
        usages.append(
            Usage(
                key=syntax_key(FRAMEWORK, token),
                file=file,
                line=line,
                test=test,
            )
        )

    source = _mask_escapes(text) if escapes else text
    length = len(source)
    index = 0
    while index < length:
        if source.startswith("<!--", index):
            end = source.find("-->", index + 4)
            index = length if end < 0 else end + 3
            continue
        if source.startswith("{{", index):
            end = source.find("}}", index + 2)
            stop = length if end < 0 else end
            _add_expression(source, index + 2, stop, add)
            index = length if end < 0 else end + 2
            continue
        char = source[index]
        if char == "<" and _TAG_START_RE.match(source, index):
            index = _tag(source, index, add)
            continue
        if char == "@":
            block = _BLOCK_RE.match(source, index)
            if block is not None and _starts_block(source, index, block.end()):
                token = re.sub(r"\s+", " ", block.group(0))
                add(token, index)
                _add_block_expression(source, block.end(), token, add)
                index = block.end()
                continue
        index += 1
    return usages


def extract_html_template(context: SourceContext) -> FileFacts:
    """Template tokens of one ``*.html`` file (FR-6).

    A file whose module has no Angular framework is not a template and yields
    nothing, so the ``index.html`` of a static site never becomes Angular facts.
    """
    if context.language != "html" or not is_angular(context):
        return FileFacts()
    text = context.data.decode("utf-8", "replace")
    return FileFacts(
        templates=template_usages(text, file=context.relative, test=context.test)
    )


def is_angular(context: SourceContext) -> bool:
    """Whether the file's module is an Angular module (FR-6 gating)."""
    return FRAMEWORK in context.env.framework_names


# --- escapes ---------------------------------------------------------------


def _mask_escapes(text: str) -> str:
    """Blank every ``\\x`` pair, keeping the length and the real newlines.

    Inside a JavaScript string ``\\n`` is a rendered newline, so a token after it
    starts a block even though the file itself has no newline there. A backslash
    before a real newline is a line continuation: only the backslash goes, so
    line numbers stay right.
    """
    if "\\" not in text:
        return text
    masked = list(text)
    index = 0
    length = len(text)
    while index < length:
        if text[index] == "\\" and index + 1 < length:
            masked[index] = " "
            if text[index + 1] == "\n":
                index += 1  # keep the newline: it is a real line break
            else:
                masked[index + 1] = " "
                index += 2
            continue
        index += 1
    return "".join(masked)


# --- block keywords --------------------------------------------------------


def _starts_block(text: str, index: int, after: int) -> bool:
    """Whether an ``@keyword`` at ``index`` (ending at ``after``) is a block.

    Two things make a keyword a block keyword: it is not inside a word
    (``a@if.example``, ``a@if`` in prose), and it carries block syntax — a
    parenthesized condition (``@if (a)``, ``@for (…; track …)``), a body
    (``@else {``, ``@empty {``, ``@placeholder {``) or, for ``@let``, a name and
    an ``=``. That is what "block keywords at the start of a block" means:
    ``@defer`` in a sentence is text even though it looks like a token.
    """
    previous = index - 1
    while previous >= 0 and text[previous] in " \t\r":
        previous -= 1
    if previous >= 0 and (text[previous].isalnum() or text[previous] in "_$@."):
        return False
    cursor = after
    while cursor < len(text) and text[cursor] in " \t\r":
        cursor += 1
    if cursor >= len(text):
        return False
    if text[cursor] == "(":
        return True  # ``@if (a)``, ``@for (…; track …)``, ``@case (x)``
    rest = text[cursor:]
    if text.startswith("@let", index):
        return _let_syntax(rest)
    return rest[0] == "{"  # ``@else {``, ``@empty {``, ``@defer {``


def _let_syntax(rest: str) -> bool:
    """``@let name = expr;`` — a name, then an ``=``."""
    head = rest.split("=", 1)
    if len(head) != 2:
        return False
    return bool(head[0].strip())


def _add_block_expression(text: str, after: int, token: str, add: _Emit) -> None:
    """The expression a block keyword carries: its ``( … )``, or ``@let``'s value."""
    if token == "@let":
        _add_expression(text, after, _statement_end(text, after), add)
        return
    bounds = _parenthesized(text, after)
    if bounds is not None:
        _add_expression(text, bounds[0], bounds[1], add)


def _parenthesized(text: str, after: int) -> tuple[int, int] | None:
    """``(start, end)`` inside the parenthesized group right after ``after``."""
    length = len(text)
    start = after
    while start < length and text[start].isspace():
        start += 1
    if start >= length or text[start] != "(":
        return None
    depth = 0
    quote = ""
    index = start
    while index < length:
        char = text[index]
        if quote:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = ""
            index += 1
            continue
        if char in "'\"`":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return start + 1, index
        index += 1
    return start + 1, length


def _statement_end(text: str, after: int) -> int:
    """End of a ``@let`` statement: its ``;`` or the end of its line."""
    index = after
    length = len(text)
    quote = ""
    while index < length:
        char = text[index]
        if quote:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = ""
            index += 1
            continue
        if char in "'\"`":
            quote = char
        elif char in ";\n":
            return index
        index += 1
    return length


# --- tags and attributes ---------------------------------------------------


def _tag(text: str, start: int, add: _Emit) -> int:
    """Read one tag, counting its attribute facts; return the index after it."""
    length = len(text)
    index = start + 1
    if index < length and text[index] in "!?":
        # ``<!doctype html>``, ``<!--`` (handled earlier), ``<?xml``: no bindings.
        end = text.find(">", index)
        return length if end < 0 else end + 1
    if index < length and text[index] == "/":
        end = text.find(">", index)
        return length if end < 0 else end + 1
    while index < length and (text[index].isalnum() or text[index] in _NAME_CHARS):
        index += 1
    while index < length:
        while index < length and text[index].isspace():
            index += 1
        if index >= length:
            return length
        if text[index] == ">":
            return index + 1
        if text.startswith("/>", index):
            return index + 2
        name_start = index
        while index < length and not text[index].isspace() and text[index] not in "=>":
            index += 1
        name = text[name_start:index]
        value, value_start, index = _attribute_value(text, index)
        if name:
            _attribute(name, name_start, value, value_start, add)
        else:
            index += 1  # never stall on a character no rule consumes
    return length


def _attribute_value(text: str, index: int) -> tuple[str, int, int]:
    """``(value, value start, index after)`` of ``name="…"``, else empty."""
    length = len(text)
    cursor = index
    while cursor < length and text[cursor].isspace():
        cursor += 1
    if cursor >= length or text[cursor] != "=":
        return "", cursor, index
    cursor += 1
    while cursor < length and text[cursor].isspace():
        cursor += 1
    if cursor >= length:
        return "", cursor, length
    if text[cursor] in "\"'":
        quote = text[cursor]
        end = text.find(quote, cursor + 1)
        if end < 0:
            return text[cursor + 1 :], cursor + 1, length
        return text[cursor + 1 : end], cursor + 1, end + 1
    start = cursor
    while cursor < length and not text[cursor].isspace() and text[cursor] != ">":
        cursor += 1
    return text[start:cursor], start, cursor


def _attribute(
    name: str, name_start: int, value: str, value_start: int, add: _Emit
) -> None:
    """One attribute: a structural directive is a fact, a binding is an expression."""
    if name.startswith("*"):
        # ``*ngFor="let item of items"``: the directive is the fact, and its
        # microsyntax is a binding (``let``, ``as``, … are tokens there).
        add(name, name_start)
        if value:
            _add_expression(value, 0, len(value), add, offset=value_start)
        return
    if is_binding(name):
        if value:
            _add_expression(value, 0, len(value), add, offset=value_start)
        return
    # ``title="{{ x | async }}"``: an interpolation is a binding wherever it is.
    _add_interpolations(value, value_start, add)


def is_binding(name: str) -> bool:
    """Whether an attribute's value is an Angular expression (FR-6)."""
    if name.startswith("["):
        return name.endswith("]")  # ``[prop]`` and ``[(prop)]``
    if name.startswith("("):
        return name.endswith(")")  # ``(event)``
    return name.startswith(_BINDING_PREFIXES)


def _add_interpolations(value: str, offset: int, add: _Emit) -> None:
    """The ``{{ … }}`` groups of an attribute value."""
    index = 0
    length = len(value)
    while index < length:
        start = value.find("{{", index)
        if start < 0:
            return
        end = value.find("}}", start + 2)
        stop = length if end < 0 else end
        _add_expression(value, start + 2, stop, add, offset=offset)
        index = length if end < 0 else end + 2


# --- expressions -----------------------------------------------------------


def _add_expression(
    text: str, start: int, end: int, add: _Emit, *, offset: int = 0
) -> None:
    """Expression tokens and pipes of ``text[start:end]``.

    ``offset`` maps an index of ``text`` to its place in the template; it is
    non-zero when ``text`` is an attribute value sliced out of the template.
    """
    expression = text[start:end]
    masked = _mask_strings(expression)
    for match in _EXPRESSION_RE.finditer(masked):
        add(match.group(1), offset + start + match.start())
    for match in _PIPE_RE.finditer(masked):
        add(f"pipe:{match.group(1)}", offset + start + match.start())


def _mask_strings(expression: str) -> str:
    """Replace string literals with spaces, keeping every index.

    A token inside ``[title]="'a in b'"`` is text, not the ``in`` operator, and a
    ``|`` inside a string is not a pipe.
    """
    masked = list(expression)
    quote = ""
    index = 0
    length = len(expression)
    while index < length:
        char = expression[index]
        if quote:
            if char == "\\" and index + 1 < length:
                masked[index] = " "
                masked[index + 1] = expression[index + 1] if expression[index + 1] == "\n" else " "
                index += 2
                continue
            if char == quote:
                quote = ""
                masked[index] = " "
                index += 1
                continue
            masked[index] = char if char == "\n" else " "
            index += 1
            continue
        if char in "'\"`":
            quote = char
            masked[index] = " "
        index += 1
    return "".join(masked)


__all__ = [
    "BLOCK_TOKENS",
    "EXPRESSION_TOKENS",
    "extract_html_template",
    "is_angular",
    "is_binding",
    "template_usages",
]
