"""Angular template tokens (spec 026.5, FR-6 / AC-4).

The lexer is a pure function of the text, so the AC-4 rows are asserted directly
on :func:`template_usages`; the profile-level tests then prove the wiring: which
files count as templates, the inline ``@Component`` pass, the ``test`` flag, the
``--max-locations`` bound and determinism.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from migration_planner.scanner import builtin, contract
from migration_planner.scanner.contract import ModuleEnv, SourceContext
from migration_planner.scanner.scan import scan
from migration_planner.scanner.templates import (
    BLOCK_TOKENS,
    EXPRESSION_TOKENS,
    extract_html_template,
    template_usages,
)
from migration_planner.scanner.ts import extract_ts

from .conftest import FIXTURES, read_profile


@pytest.fixture(autouse=True)
def installed_registry():
    """``scan()`` does not install; a scan test needs the shipped extractors."""
    contract.reset_registry()
    builtin.install()
    yield
    contract.reset_registry()


def _tokens(text: str, **kwargs) -> list[tuple[str, int]]:
    """``(token without its prefix, line)`` for each token of ``text``."""
    return [
        (usage.key.split("#", 1)[1], usage.line)
        for usage in template_usages(text, file="t.html", **kwargs)
    ]


def _keys(text: str) -> list[str]:
    return [token for token, _ in _tokens(text)]


# --- FR-6: the token list ------------------------------------------------


def test_the_token_lists_come_from_the_shared_angular_module() -> None:
    """A rule entity and a scanner fact must land on the same key (025 FR-1)."""
    assert "@if" in BLOCK_TOKENS and "@defer" in BLOCK_TOKENS
    assert "in" in EXPRESSION_TOKENS and "no" not in EXPRESSION_TOKENS
    assert not set(BLOCK_TOKENS) & set(EXPRESSION_TOKENS)


def test_a_block_keyword_is_a_key_with_the_canonical_prefix() -> None:
    usage = template_usages("@defer (on viewport) { <x /> }", file="t.html")[0]

    assert usage.key == "syntax:angular-template#@defer"


# --- AC-4: block keywords, directives, bindings ---------------------------


def test_block_keywords_at_the_start_of_a_block() -> None:
    text = (
        "@if (a) {\n"
        "  <p>x</p>\n"
        "} @else if (b) {\n"
        "  <p>y</p>\n"
        "} @else {\n"
        "  <p>z</p>\n"
        "}\n"
    )

    assert _tokens(text) == [("@if", 1), ("@else if", 3), ("@else", 5)]


def test_a_keyword_inside_a_word_or_a_sentence_is_not_a_block() -> None:
    """``@if`` mid-sentence (an email address, prose) opens no block."""
    assert _keys("mail me at a@if.example for details") == []
    assert _keys("<p>the @defer block is new</p>") == []


def test_a_structural_directive_is_its_own_key() -> None:
    text = (
        '<ul *ngFor="let item of items">\n'
        '  <li *ngSwitchCase="1">{{ item.name }}</li>\n'
        "</ul>\n"
        '<div *ngIf="shown"></div>\n'
    )

    keys = _keys(text)
    assert "*ngFor" in keys
    assert "*ngSwitchCase" in keys
    assert "*ngIf" in keys


def test_a_structural_directive_microsyntax_is_a_binding() -> None:
    """``let item of items; track item.id``: ``let`` is a token there."""
    assert ("let", 1) in _tokens('<div *ngFor="let item of items"></div>')


def test_expression_tokens_are_counted_only_inside_bindings() -> None:
    text = (
        "<p>Text saying in and as and void is not a binding.</p>\n"
        "<p>{{ a in b }}</p>\n"
        '<p [title]="c as d"></p>\n'
        '<p (click)="typeof e"></p>\n'
    )

    assert _tokens(text) == [("in", 2), ("as", 3), ("typeof", 4)]


def test_a_binding_inside_a_block_condition_is_counted() -> None:
    assert _keys("@if (item in cache) { <p>x</p> }") == ["@if", "in"]


def test_a_pipe_in_a_binding_is_a_key_and_a_logical_or_is_not() -> None:
    text = '<p>{{ created | date:"short" }}</p>\n<p [title]="a || b"></p>\n'

    assert _tokens(text) == [("pipe:date", 1)]


def test_a_token_inside_a_string_literal_is_not_a_token() -> None:
    text = """<p [title]="'a in b'"></p>\n<p [label]="'x | date'"></p>\n"""

    assert _keys(text) == []


def test_an_interpolation_in_a_plain_attribute_is_a_binding() -> None:
    assert _tokens('<p title="{{ x | uppercase }}"></p>') == [("pipe:uppercase", 1)]


def test_an_event_and_a_two_way_binding_are_bindings() -> None:
    text = (
        '<input (input)="onInput($event)" />\n'
        '<input [(ngModel)]="value as string" />\n'
    )

    assert _keys(text) == ["as"]


def test_an_html_comment_is_ignored() -> None:
    text = "<!-- @defer *ngFor in void -->\n<p>{{ x }}</p>\n<p>@if</p>\n"

    assert _keys(text) == []


def test_a_let_declaration_carries_its_expression() -> None:
    assert _keys("@let total = items.length;\n<p>{{ total }}</p>") == ["@let"]


def test_only_the_first_use_of_a_token_on_a_line_is_one_site() -> None:
    """A location has no column (spec1 FR-1), so one line is one site."""
    keys = [usage.key for usage in template_usages("<p>{{ a in b }} {{ c in d }}</p>", file="t.html")]

    assert keys == ["syntax:angular-template#in"]

    usages = template_usages("<p>{{ a in b }} {{ c as d }}</p>", file="t.html")
    assert [(usage.key, usage.line) for usage in usages] == [
        ("syntax:angular-template#in", 1),
        ("syntax:angular-template#as", 1),
    ]


def test_lines_are_counted_from_the_start_of_the_file() -> None:
    text = "<div>\n\n  @if (a) {\n    <p>{{ b in c }}</p>\n  }\n</div>\n"

    assert _tokens(text) == [("@if", 3), ("in", 4)]


def test_a_directive_attribute_records_its_line() -> None:
    text = "<div>\n  <span\n    *ngIf=\"x\"\n  ></span>\n</div>\n"

    assert _tokens(text) == [("*ngIf", 3)]


def test_a_doctype_and_a_closing_tag_are_not_bindings() -> None:
    text = "<!doctype html>\n</div>\n<p>{{ a }}</p>\n"

    assert _keys(text) == []


def test_a_binding_spanning_several_lines_records_its_own_line() -> None:
    """An attribute value can wrap; each token keeps its line in the file."""
    text = '<div\n  [title]="a in b"\n  (click)="c as d"\n>\n</div>\n'

    assert _tokens(text) == [("in", 2), ("as", 3)]


def test_a_switch_case_parens_is_a_block() -> None:
    text = '@switch (mode) {\n  @case ("a") { <p>a</p> }\n}'

    assert _tokens(text) == [("@switch", 1), ("@case", 2)]


def test_a_for_body_is_not_a_binding() -> None:
    """``of items`` is the ``@for`` microsyntax; prose in the body is not an expression."""
    assert _keys("@for (item of items) { <p>in the list</p> }") == ["@for"]


def test_nested_blocks_are_counted_at_their_own_lines() -> None:
    text = (
        "@if (a) {\n"
        "  @for (x of xs) {\n"
        "    @defer {\n"
        "      <p>{{ n | number }}</p>\n"
        "    }\n"
        "  }\n"
        "}\n"
    )

    assert _tokens(text) == [
        ("@if", 1),
        ("@for", 2),
        ("@defer", 3),
        ("pipe:number", 4),
    ]


def test_a_block_keyword_inside_an_attribute_value_is_text() -> None:
    assert _keys('<p title="@if (a)"></p>') == []


# --- FR-6: an inline @Component template ---------------------------------


def _ts_facts(source: str, *, relative: str = "src/a.ts", test: bool = False):
    return extract_ts(
        SourceContext(
            path=Path(relative),
            relative=relative,
            module=".",
            language="ts",
            test=test,
            data=source.encode("utf-8"),
            env=ModuleEnv(),
        )
    )


def test_an_inline_template_literal_is_scanned() -> None:
    source = (
        "import { Component } from '@angular/core';\n"
        "@Component({\n"
        "  selector: 'x',\n"
        "  template: `\n"
        "    @if (a) {\n"
        '      <div *ngFor="let row of rows">{{ row.value | async }}</div>\n'
        "    }\n"
        "  `,\n"
        "})\n"
        "export class C {}\n"
    )

    facts = _ts_facts(source)

    assert [(usage.key, usage.line) for usage in facts.templates] == [
        ("syntax:angular-template#@if", 5),
        ("syntax:angular-template#*ngFor", 6),
        ("syntax:angular-template#let", 6),
        ("syntax:angular-template#pipe:async", 6),
    ]


def test_an_inline_template_on_one_line_uses_the_ts_line() -> None:
    """AC-4: an inline template's location is the right line in the ``.ts`` file."""
    source = (
        "import { Component } from '@angular/core';\n"
        "@Component({\n"
        "  template: '<p *ngIf=\"shown\">{{ shown | date }}</p>',\n"
        "})\n"
        "export class C {}\n"
    )

    assert [(usage.key, usage.line) for usage in _ts_facts(source).templates] == [
        ("syntax:angular-template#*ngIf", 3),
        ("syntax:angular-template#pipe:date", 3),
    ]


def test_a_quoted_inline_template_is_scanned_the_same_way() -> None:
    source = (
        "import { Component } from '@angular/core';\n"
        "@Component({ template: '<p>@defer { <x /> }</p>' })\n"
        "export class C {}\n"
    )

    assert _keys_of_inline(_ts_facts(source)) == ["@defer"]


def test_an_inline_template_with_substitutions_is_not_scanned() -> None:
    """A ``${…}`` template is not static: its tokens would be a guess."""
    source = (
        "import { Component } from '@angular/core';\n"
        "const suffix = 'x';\n"
        "@Component({ template: `<p>@if (a) {${suffix}}</p>` })\n"
        "export class C {}\n"
    )

    assert _ts_facts(source).templates == []


def test_only_component_templates_are_scanned() -> None:
    """``@Directive`` has no ``template``; a random ``template`` option is no template."""
    source = (
        "import { Directive, Component } from '@angular/core';\n"
        "@Directive({ selector: 'x', template: '<p>@defer</p>' })\n"
        "export class D {}\n"
        "@Component({ selector: 'y', templateUrl: './y.html' })\n"
        "export class C {}\n"
    )

    facts = _ts_facts(source)

    assert facts.templates == []
    # ``templateUrl`` is a separate option name, not the inline template.
    assert "npm:@angular/core#Component.templateUrl" in {m.key for m in facts.members}


def test_a_template_property_of_an_own_decorator_is_not_scanned() -> None:
    source = (
        "import { Local } from './local';\n"
        "@Local({ template: '<p>@defer { <x /> }</p>' })\n"
        "export class C {}\n"
    )

    assert _ts_facts(source).templates == []


def test_a_template_through_a_barrel_import_is_scanned() -> None:
    """``Component`` from the service's own barrel is the Angular one (spec4)."""
    source = (
        "import { Component } from '@app/core';\n"
        "@Component({ template: '<p>@defer { <x /> }</p>' })\n"
        "export class C {}\n"
    )

    assert _keys_of_inline(_ts_facts(source)) == ["@defer"]


def test_a_local_class_named_component_is_not_the_angular_one() -> None:
    source = (
        "class Component {}\n"
        "@Component({ template: '<p>@defer { <x /> }</p>' })\n"
        "export class C {}\n"
    )

    assert _ts_facts(source).templates == []


def test_escaped_newlines_inside_a_template_keep_the_ts_line() -> None:
    """``\\n`` renders a newline, so a block may start after it on the same line."""
    source = (
        "import { Component } from '@angular/core';\n"
        "@Component({ template: '<p>a</p>\\n@if (b) { <x /> }' })\n"
        "export class C {}\n"
    )

    assert [(usage.key, usage.line) for usage in _ts_facts(source).templates] == [
        ("syntax:angular-template#@if", 2)
    ]


def test_the_template_flag_travels_to_an_inline_token() -> None:
    source = (
        "import { Component } from '@angular/core';\n"
        "@Component({ template: '<p>@defer { <x /> }</p>' })\n"
        "export class C {}\n"
    )

    facts = _ts_facts(source, relative="src/c.spec.ts", test=True)

    assert facts.templates[0].test is True


def test_a_backtick_template_keeps_the_selector_members() -> None:
    """The template pass must not disturb the decorator member facts (spec3)."""
    source = (
        "import { Component } from '@angular/core';\n"
        "@Component({ selector: 'x', standalone: true, template: '<p>@defer</p>' })\n"
        "export class C {}\n"
    )

    keys = {member.key for member in _ts_facts(source).members}

    assert keys == {
        "npm:@angular/core#Component.selector",
        "npm:@angular/core#Component.standalone",
        "npm:@angular/core#Component.template",
    }


def _keys_of_inline(facts) -> list[str]:
    return [usage.key.split("#", 1)[1] for usage in facts.templates]


# --- FR-6: which .html files are templates -------------------------------


def test_an_html_file_of_a_non_angular_module_is_not_a_template() -> None:
    facts = extract_html_template(
        SourceContext(
            path=Path("index.html"),
            relative="public/index.html",
            module=".",
            language="html",
            data=b"<div *ngFor=\"let x of xs\">@defer</div>",
            env=ModuleEnv(framework_names=()),
        )
    )

    assert facts.templates == []


def test_an_html_file_of_an_angular_module_is_a_template() -> None:
    facts = extract_html_template(
        SourceContext(
            path=Path("a.html"),
            relative="src/app/a.component.html",
            module=".",
            language="html",
            data=b"<div *ngFor=\"let x of xs\">@defer { <y /> }</div>",
            env=ModuleEnv(framework_names=("angular",)),
        )
    )

    assert _keys_of_inline(facts) == ["*ngFor", "let", "@defer"]


def test_the_html_extractor_is_registered_beside_the_ts_one() -> None:
    assert set(builtin.EXTRA_SOURCE_EXTRACTORS) == {"html"}
    assert "html" in contract.source_extractors()
    assert set(builtin.SOURCE_EXTRACTORS) == {
        "ts",
        "tsx",
        "js",
        "jsx",
        "mjs",
        "cjs",
    }


# --- AC-4 through a real scan --------------------------------------------


@pytest.fixture()
def templates_repo(tmp_path: Path) -> Path:
    import shutil

    target = tmp_path / "angular-templates"
    shutil.copytree(FIXTURES / "angular-templates", target)
    return target


def test_the_fixture_gives_the_expected_keys(templates_repo: Path) -> None:
    payload = read_profile(scan(templates_repo, out=templates_repo / "p.json").path)

    by_key = {entry["key"]: entry["count"] for entry in payload["templates"]}

    assert by_key == {
        "syntax:angular-template#*ngFor": 2,
        "syntax:angular-template#*ngIf": 1,
        "syntax:angular-template#@case": 1,
        "syntax:angular-template#@defer": 1,
        "syntax:angular-template#@else if": 1,
        "syntax:angular-template#@empty": 1,
        "syntax:angular-template#@error": 1,
        "syntax:angular-template#@if": 2,
        "syntax:angular-template#@let": 1,
        "syntax:angular-template#@loading": 1,
        "syntax:angular-template#@placeholder": 1,
        "syntax:angular-template#@switch": 1,
        "syntax:angular-template#in": 1,
        "syntax:angular-template#let": 2,
        "syntax:angular-template#pipe:async": 1,
        "syntax:angular-template#pipe:date": 1,
    }


def test_a_token_in_an_html_comment_is_not_counted(templates_repo: Path) -> None:
    """AC-4: the fixture's comment holds ``@defer *ngFor in void @switch``."""
    payload = read_profile(scan(templates_repo, out=templates_repo / "p.json").path)

    by_key = {entry["key"]: entry for entry in payload["templates"]}

    # One ``@defer`` (line 19) — the comment at the top has the other one, and
    # ``@switch`` appears once (the inline component), not twice.
    assert by_key["syntax:angular-template#@defer"]["count"] == 1
    assert by_key["syntax:angular-template#@switch"]["count"] == 1


def test_in_plain_text_is_not_counted_but_in_a_binding_is(templates_repo: Path) -> None:
    payload = read_profile(scan(templates_repo, out=templates_repo / "p.json").path)

    entry = next(
        entry
        for entry in payload["templates"]
        if entry["key"] == "syntax:angular-template#in"
    )

    # ``{{ item in cache }}`` line 9; the plain text on line 10 is not a binding.
    assert entry["count"] == 1
    assert entry["locations"] == [
        {"file": "src/app/app.component.html", "line": 9, "test": False}
    ]


def test_a_logical_or_is_not_a_pipe(templates_repo: Path) -> None:
    payload = read_profile(scan(templates_repo, out=templates_repo / "p.json").path)

    pipes = {
        entry["key"]
        for entry in payload["templates"]
        if "pipe:" in entry["key"]
    }

    assert pipes == {
        "syntax:angular-template#pipe:async",
        "syntax:angular-template#pipe:date",
    }


def test_an_inline_template_location_is_a_ts_file(templates_repo: Path) -> None:
    payload = read_profile(scan(templates_repo, out=templates_repo / "p.json").path)

    entry = next(
        entry
        for entry in payload["templates"]
        if entry["key"] == "syntax:angular-template#@switch"
    )

    assert entry["locations"] == [
        {"file": "src/app/inline.component.ts", "line": 10, "test": False}
    ]


def test_a_non_angular_html_file_is_not_scanned(make_repo) -> None:
    repo = make_repo(
        {
            "package.json": json.dumps({"dependencies": {"express": "^4.19.0"}}),
            "public/index.html": '<div *ngFor="let x of xs">@defer {{ x in y }}</div>',
        }
    )

    payload = read_profile(scan(repo, out=repo / "p.json").path)

    assert payload["templates"] == []


def test_an_angular_module_scans_its_html_and_a_sibling_does_not(make_repo) -> None:
    repo = make_repo(
        {
            "package.json": json.dumps({"name": "root"}),
            "ui/package.json": json.dumps(
                {"name": "ui", "dependencies": {"@angular/core": "^19.2.0"}}
            ),
            "ui/src/app/a.component.html": '<p *ngIf="x"></p>',
            "site/index.html": '<p *ngFor="let x of xs"></p>',
        }
    )

    payload = read_profile(scan(repo, out=repo / "p.json").path)

    assert [entry["key"] for entry in payload["templates"]] == [
        "syntax:angular-template#*ngIf"
    ]
    assert payload["templates"][0]["locations"][0]["file"] == (
        "ui/src/app/a.component.html"
    )


def test_a_test_template_is_flagged(make_repo) -> None:
    repo = make_repo(
        {
            "package.json": json.dumps({"dependencies": {"@angular/core": "^19.2.0"}}),
            "src/app/x.component.spec.html": "<p></p>",
            "src/test/template.spec.ts": (
                "import { Component } from '@angular/core';\n"
                "@Component({ template: '<p>@defer { <x /> }</p>' })\n"
                "export class C {}\n"
            ),
        }
    )

    payload = read_profile(scan(repo, out=repo / "p.json").path)

    assert payload["templates"][0]["locations"][0]["test"] is True


def test_max_locations_bounds_template_tokens(make_repo) -> None:
    files = {"package.json": json.dumps({"dependencies": {"@angular/core": "^19"}})}
    for index in range(12):
        files[f"src/t{index:02d}.component.html"] = "<p>@defer { <x /> }</p>"

    repo = make_repo(files)
    profile = scan(repo, out=repo / "p.json", max_locations=4).profile

    entry = profile.templates[0]
    assert entry.count == 12
    assert entry.files == 12
    assert len(entry.locations) == 4
    assert entry.truncated is True


def test_the_summary_counts_template_tokens(templates_repo: Path) -> None:
    result = scan(templates_repo, out=templates_repo / "p.json")

    assert result.summary.template_tokens == len(result.profile.templates)
    assert "16 template tokens" in result.summary.text()


def test_a_scan_is_still_deterministic(templates_repo: Path) -> None:
    first = scan(templates_repo, out=templates_repo / "a.json").profile
    second = scan(templates_repo, out=templates_repo / "b.json").profile

    assert [entry.key for entry in first.templates] == [
        entry.key for entry in second.templates
    ]
    assert first.inputs_hash == second.inputs_hash


def test_a_broken_template_does_not_fail_the_scan(make_repo) -> None:
    repo = make_repo(
        {
            "package.json": json.dumps({"dependencies": {"@angular/core": "^19"}}),
            "src/a.component.html": '<p>{{ unclosed',
        }
    )

    result = scan(repo, out=repo / "p.json")

    assert result.path is not None and result.path.is_file()
    assert result.profile.diagnostics == []


@pytest.mark.parametrize(
    "text",
    ["", "<", "<!--", "{{", "<div", "<div a=", '<div [x]="', "@", "@if", "<>", "{{ | }}"],
)
def test_a_truncated_template_never_hangs_or_raises(text: str) -> None:
    """A half-written file is what an editor saves; the lexer must survive it."""
    # The point is that the call returns at all, with no exception and nothing
    # invented: a broken fragment has no complete token in it.
    assert template_usages(text, file="t.html") == []
