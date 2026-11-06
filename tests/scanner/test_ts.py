"""TS / JS extraction: imports, members, decorators (spec 026.3 AC-1, AC-3).

The extractor is a pure function of ``(path, bytes, module env)``, so most tests
call :func:`extract_ts` directly with a source string and assert on the facts.
The last group goes through :func:`scan` to prove the wiring: test flags, the
``--max-locations`` bound and a real profile.
"""

from __future__ import annotations

from pathlib import Path

import json

import pytest

from migration_planner.scanner import builtin, contract
from migration_planner.scanner.contract import ModuleEnv, PathMap, SourceContext
from migration_planner.scanner.scan import scan
from migration_planner.scanner.ts import GRAMMARS, extract_ts

from .conftest import read_profile


@pytest.fixture(autouse=True)
def installed_registry():
    """``scan()`` does not install; a scan test needs the shipped readers."""
    contract.reset_registry()
    builtin.install()
    yield
    contract.reset_registry()


def _extract(
    source: str,
    *,
    language: str = "ts",
    relative: str = "src/a.ts",
    own_packages: tuple[str, ...] = (),
    path_alias: dict[str, tuple[str, ...]] | None = None,
    test: bool = False,
):
    """Facts for one source string, with the env a real module would supply."""
    env = ModuleEnv(
        module=".",
        own_packages=own_packages,
        path_map=(
            PathMap(paths=dict(path_alias), paths_dir=".") if path_alias else None
        ),
    )
    return extract_ts(
        SourceContext(
            path=Path(relative),
            relative=relative,
            module=".",
            language=language,
            test=test,
            data=source.encode("utf-8"),
            env=env,
        )
    )


def _keys(usages) -> list[tuple[str, int]]:
    return [(usage.key, usage.line) for usage in usages]


# --- AC-1: the FR-5 import table -------------------------------------------


def test_named_and_aliased_imports() -> None:
    facts = _extract("import { A, B as C } from 'pkg';\n")

    # The local alias ``C`` still maps to the imported name ``B`` (FR-5).
    assert _keys(facts.symbols) == [("npm:pkg#A", 1), ("npm:pkg#B", 1)]


def test_default_import_is_the_default_symbol() -> None:
    facts = _extract("import D from 'pkg';\n")

    assert _keys(facts.symbols) == [("npm:pkg#default", 1)]


def test_named_default_import_is_the_default_symbol() -> None:
    """``import { default as E }`` is the same fact as ``import E from``."""
    facts = _extract("import { default as E } from 'pkg';\n")

    assert _keys(facts.symbols) == [("npm:pkg#default", 1)]


def test_namespace_import_records_members_not_a_symbol() -> None:
    facts = _extract("import * as ns from 'pkg';\nns.inject(X);\nns.other();\n")

    # A namespace import has no symbol of its own: each use is the package's
    # symbol, at the use site.
    assert _keys(facts.symbols) == [("npm:pkg#inject", 2), ("npm:pkg#other", 3)]
    assert facts.members == []


def test_side_effect_import_records_the_package() -> None:
    facts = _extract("import 'zone.js';\n")

    assert facts.symbols == []
    assert _keys(facts.side_effect_imports) == [("npm:zone.js", 1)]


def test_type_only_import_is_flagged() -> None:
    facts = _extract("import type { T } from 'pkg';\n")

    assert _keys(facts.symbols) == [("npm:pkg#T", 1)]
    assert facts.symbols[0].type_only is True


def test_an_inline_type_specifier_is_type_only_per_name() -> None:
    """``{ type U, V }``: ``U`` is type-only, ``V`` is a value use."""
    facts = _extract("import { type U, V } from 'pkg';\n")

    by_key = {usage.key: usage.type_only for usage in facts.symbols}
    assert by_key == {"npm:pkg#U": True, "npm:pkg#V": False}


def test_all_inline_type_specifiers_make_a_type_only_import() -> None:
    facts = _extract("import { type U, type W } from 'pkg';\n")

    assert all(usage.type_only for usage in facts.symbols)


def test_reexport_of_an_external_package_is_a_usage() -> None:
    facts = _extract("export { A } from 'pkg';\n")

    assert _keys(facts.symbols) == [("npm:pkg#A", 1)]
    assert facts.export_map["A"].specifier == "pkg"
    assert facts.export_map["A"].original == "A"


def test_star_reexport_of_an_external_package_is_a_package_level_symbol() -> None:
    """Names behind ``export *`` are unknown here (spec4 resolves them), but the
    package is used: ``npm:pkg`` in ``symbols``."""
    facts = _extract("export * from 'pkg';\n")

    assert facts.star_exports == ["pkg"]
    assert _keys(facts.symbols) == [("npm:pkg", 1)]
    assert facts.side_effect_imports == []


def test_star_reexport_of_own_code_records_no_fact() -> None:
    facts = _extract("export * from './local';\n")

    assert facts.star_exports == ["./local"]
    assert facts.symbols == []


def test_dynamic_import_and_require_are_recorded() -> None:
    facts = _extract(
        "const d = await import('pkg-dyn');\n"
        "const l = require('pkg-legacy');\n"
        "import('pkg-fire-and-forget');\n"
    )

    # A package-level use is a symbol; only ``import 'pkg'`` is a side effect.
    assert sorted(_keys(facts.symbols)) == [
        ("npm:pkg-dyn", 1),
        ("npm:pkg-fire-and-forget", 3),
        ("npm:pkg-legacy", 2),
    ]
    assert facts.side_effect_imports == []


def test_destructured_require_records_the_names() -> None:
    facts = _extract("const { a, b: c } = require('pkg');\n")

    assert _keys(facts.symbols) == [("npm:pkg#a", 1), ("npm:pkg#b", 1)]


def test_a_non_literal_specifier_is_not_resolved() -> None:
    facts = _extract(
        "const name = 'pkg';\nconst m = require(name);\nimport(`pkg/${x}`);\n"
    )

    assert facts.symbols == []
    assert facts.side_effect_imports == []


def test_angular_entry_point_is_its_own_package() -> None:
    facts = _extract("import { TestBed } from '@angular/core/testing';\n")

    assert _keys(facts.symbols) == [("npm:@angular/core/testing#TestBed", 1)]


def test_a_deep_unscoped_import_is_kept_as_written() -> None:
    facts = _extract("import { map } from 'rxjs/internal/operators/map';\n")

    assert _keys(facts.symbols) == [("npm:rxjs/internal/operators/map#map", 1)]


def test_a_deep_file_import_falls_back_to_its_dependency() -> None:
    """A path to a real file is not a public entry point."""
    facts = _extract("import x from 'lodash/fp.js';\n")

    assert _keys(facts.symbols) == [("npm:lodash/fp.js#default", 1)]


def test_a_node_builtin_is_neither_a_fact_nor_own_code() -> None:
    facts = _extract("import { readFile } from 'node:fs';\nimport path from 'path';\n")

    assert facts.symbols == []
    assert facts.own_imports == 0


# --- AC-1: own code is not recorded ----------------------------------------


def test_relative_imports_are_own_code() -> None:
    facts = _extract("import { x } from './local';\nimport { y } from '../up';\n")

    assert facts.symbols == []
    assert facts.own_imports == 2
    assert [binding.specifier for binding in facts.own_import_bindings] == [
        "./local",
        "../up",
    ]


def test_a_paths_alias_is_own_code() -> None:
    facts = _extract(
        "import { shared } from '@app/shared';\n",
        path_alias={"@app/*": ("src/app/*",)},
    )

    assert facts.symbols == []
    assert facts.own_imports == 1
    assert facts.own_import_bindings[0].specifier == "@app/shared"


def test_a_workspace_package_is_own_code() -> None:
    facts = _extract("import { widget } from '@demo/ui';\n", own_packages=("@demo/ui",))

    assert facts.symbols == []
    assert facts.own_imports == 1


def test_own_import_bindings_keep_the_local_names_for_spec4() -> None:
    facts = _extract(
        "import Def, { x as y } from './barrel';\nimport * as all from '#alias';\n",
        path_alias={"#alias": ("src/alias.ts",)},
    )

    first, second = facts.own_import_bindings
    assert first.named == {"y": "x"}
    assert first.default == "Def"
    assert first.is_relative is True
    assert second.namespace == "all"
    assert second.is_relative is False


def test_local_declarations_are_collected_for_spec4() -> None:
    facts = _extract(
        "export class Own {}\n"
        "export function ownFn() {}\n"
        "export const ownConst = 1;\n"
        "const { a, b: c } = obj;\n"
    )

    assert {"Own", "ownFn", "ownConst", "a", "c"} <= facts.local_declarations


# --- AC-3: members ---------------------------------------------------------


def test_member_access_on_a_named_import() -> None:
    facts = _extract(
        "import { TestBed } from '@angular/core/testing';\n\nTestBed.get(Foo);\n"
    )

    assert ("npm:@angular/core/testing#TestBed.get", 3) in _keys(facts.members)


def test_member_access_through_an_alias() -> None:
    facts = _extract(
        "import { TestBed as TB } from '@angular/core/testing';\nTB.get(Foo);\n"
    )

    assert _keys(facts.members) == [("npm:@angular/core/testing#TestBed.get", 2)]


def test_member_access_through_a_namespace_becomes_a_symbol() -> None:
    facts = _extract("import * as core from '@angular/core';\ncore.inject(X);\n")

    assert _keys(facts.symbols) == [("npm:@angular/core#inject", 2)]


def test_only_the_first_member_segment_is_recorded() -> None:
    facts = _extract("import D from 'pkg';\nD.b.c;\n")

    assert _keys(facts.members) == [("npm:pkg#default.b", 2)]


def test_a_member_without_a_call_is_recorded() -> None:
    """A rule can be about reading a property, not only calling it."""
    facts = _extract(
        "import { Injector } from '@angular/core';\nconst x = Injector.NULL;\n"
    )

    assert _keys(facts.members) == [("npm:@angular/core#Injector.NULL", 2)]


def test_a_shadowing_parameter_stops_member_tracking_in_its_scope() -> None:
    source = (
        "import { TestBed } from '@angular/core/testing';\n"
        "TestBed.get(Outside);\n"
        "function f(TestBed) {\n"
        "  TestBed.get(Inside);\n"
        "}\n"
        "TestBed.get(OutsideAgain);\n"
    )
    facts = _extract(source)

    # The two outer uses count; the shadowing parameter is an own local, so the
    # inner use is not the import (line 4 is the only one missing).
    assert _keys(facts.members) == [
        ("npm:@angular/core/testing#TestBed.get", 2),
        ("npm:@angular/core/testing#TestBed.get", 6),
    ]


def test_a_shadowing_local_variable_stops_tracking() -> None:
    source = (
        "import { TestBed } from '@angular/core/testing';\n"
        "function f() {\n"
        "  const TestBed = local();\n"
        "  TestBed.get(Inside);\n"
        "}\n"
    )

    assert facts_keys(_extract(source).members) == []


def facts_keys(usages) -> list[str]:
    return [usage.key for usage in usages]


def test_member_tracking_is_per_file() -> None:
    """A binding in one file says nothing about an identifier in another."""
    facts = _extract("TestBed.get(X);\n", relative="src/other.ts")

    assert facts.members == []


# --- AC-3: decorators ------------------------------------------------------


def test_decorator_keys_are_members_and_the_symbol_stays_at_its_import_site() -> None:
    source = (
        "import { Component } from '@angular/core';\n"
        "\n"
        "@Component({ selector: 'x', standalone: true, changeDetection: 1 })\n"
        "export class C {}\n"
    )
    facts = _extract(source)

    # symbols[].locations are import sites (spec1 FR-9), not decorator sites.
    assert _keys(facts.symbols) == [("npm:@angular/core#Component", 1)]
    assert _keys(facts.members) == [
        ("npm:@angular/core#Component.selector", 3),
        ("npm:@angular/core#Component.standalone", 3),
        ("npm:@angular/core#Component.changeDetection", 3),
    ]


def test_a_decorator_adds_no_symbol_location() -> None:
    """``@Input()`` twice: ``Input`` keeps one location, its import site."""
    facts = _extract(
        "import { Input } from '@angular/core';\n"
        "class C {\n  @Input() x;\n  @Input() y;\n}\n"
    )

    assert _keys(facts.symbols) == [("npm:@angular/core#Input", 1)]


def test_shorthand_and_method_decorator_options_are_members() -> None:
    facts = _extract(
        "import { Component } from '@angular/core';\n"
        "const selector = 'x';\n"
        "@Component({ selector, standalone: true })\n"
        "class C {}\n"
    )

    assert _keys(facts.members) == [
        ("npm:@angular/core#Component.selector", 3),
        ("npm:@angular/core#Component.standalone", 3),
    ]


def test_a_namespaced_decorator_records_its_options() -> None:
    facts = _extract(
        "import * as core from '@angular/core';\n"
        "@core.Component({ selector: 'x' })\n"
        "class C {}\n"
    )

    assert ("npm:@angular/core#Component", 2) in _keys(facts.symbols)
    assert _keys(facts.members) == [("npm:@angular/core#Component.selector", 2)]


def test_typescript_import_equals_require() -> None:
    facts = _extract("import fs = require('fs-extra');\nfs.copy(a, b);\n")

    assert ("npm:fs-extra", 1) in _keys(facts.symbols)
    assert ("npm:fs-extra#copy", 2) in _keys(facts.symbols)


def test_a_decorator_on_an_own_class_is_not_a_fact() -> None:
    facts = _extract("@Local({ a: 1 })\nclass C {}\n")

    assert facts.symbols == []
    assert facts.members == []


def test_non_literal_decorator_keys_are_not_members() -> None:
    source = (
        "import { Component } from '@angular/core';\n"
        "@Component({ [key]: 1, 'literal-key': 2 })\n"
        "class C {}\n"
    )
    facts = _extract(source)

    # A computed key has no static name; a string key does.
    assert _keys(facts.members) == [("npm:@angular/core#Component.literal-key", 2)]


# --- AC-3.2: every grammar ------------------------------------------------


@pytest.mark.parametrize("language", GRAMMARS)
def test_each_language_parses_its_own_syntax(language: str) -> None:
    """``.tsx`` needs its own grammar; jsx shares javascript; cjs is javascript."""
    facts = _extract("import { A } from 'pkg';\nA.x();\n", language=language)

    assert _keys(facts.symbols) == [("npm:pkg#A", 1)]
    assert _keys(facts.members) == [("npm:pkg#A.x", 2)]


def test_tsx_jsx_syntax_parses() -> None:
    facts = _extract(
        "import { Component } from 'react';\n"
        "export const App = () => <div className='x'>{1}</div>;\n"
        "Component.memo(App);\n",
        language="tsx",
    )

    assert ("npm:react#Component", 1) in _keys(facts.symbols)
    assert ("npm:react#Component.memo", 3) in _keys(facts.members)


def test_javascript_jsx_syntax_parses() -> None:
    facts = _extract(
        "import React from 'react';\nexport const A = () => <div />;\nReact.memo(A);\n",
        language="jsx",
    )

    assert ("npm:react#default.memo", 3) in _keys(facts.members)


@pytest.mark.parametrize("language", ["js", "mjs", "cjs"])
def test_plain_javascript_languages_parse(language: str) -> None:
    facts = _extract("const x = require('pkg');\nx.thing();\n", language=language)

    assert ("npm:pkg", 1) in _keys(facts.symbols)
    assert ("npm:pkg#thing", 2) in _keys(facts.symbols)


def test_an_unsupported_language_returns_nothing() -> None:
    facts = _extract("import { A } from 'pkg';\n", language="java")

    assert facts.symbols == []
    assert facts.diagnostics == []


# --- parse errors ---------------------------------------------------------


def test_an_unparsable_file_is_a_diagnostic() -> None:
    facts = _extract("import { from 'pkg';\n)((((")

    assert [entry.kind for entry in facts.diagnostics] == ["parse_error"]
    assert facts.diagnostics[0].file == "src/a.ts"


def test_a_partial_parse_still_yields_the_imports_that_parsed() -> None:
    facts = _extract("import { A } from 'pkg';\nconst x = {{{ ;;;\n")

    assert ("npm:pkg#A", 1) in _keys(facts.symbols)
    assert [entry.kind for entry in facts.diagnostics] == ["partial_parse_error"]


def test_an_empty_file_is_not_an_error() -> None:
    facts = _extract("")

    assert facts.symbols == []
    assert facts.diagnostics == []


# --- AC-3.3: bounds and test flags through a real scan ---------------------


def test_the_extractor_is_registered_for_every_language() -> None:
    assert set(builtin.SOURCE_EXTRACTORS) == set(GRAMMARS)


def test_a_scan_records_symbols_and_members_with_test_flags(make_repo) -> None:
    repo = make_repo(
        {
            "package.json": '{"name": "demo", "dependencies": {"@angular/core": "^19.2.0"}}',
            "src/app.ts": (
                "import { Component } from '@angular/core';\n"
                "@Component({ standalone: true })\n"
                "export class App {}\n"
            ),
            "src/app.spec.ts": (
                "import { TestBed } from '@angular/core/testing';\n"
                "TestBed.configureTestingModule({});\n"
            ),
        }
    )

    result = scan(repo, out=repo / "profile.json")
    payload = read_profile(repo / "profile.json")

    symbols = {entry["key"]: entry for entry in payload["symbols"]}
    members = {entry["key"]: entry for entry in payload["members"]}

    assert "npm:@angular/core#Component" in symbols
    assert "npm:@angular/core/testing#TestBed" in symbols
    # The ``test`` flag travels from the file to the location (FR-1).
    assert symbols["npm:@angular/core/testing#TestBed"]["locations"][0]["test"] is True
    assert symbols["npm:@angular/core#Component"]["locations"][0]["test"] is False
    assert "npm:@angular/core#Component.standalone" in members
    assert "npm:@angular/core/testing#TestBed.configureTestingModule" in members
    assert result.summary.symbols == len(symbols)
    assert result.summary.members == len(members)


def test_no_include_tests_drops_the_spec_file(make_repo) -> None:
    repo = make_repo(
        {
            "package.json": '{"name": "demo"}',
            "src/app.ts": "import { Component } from '@angular/core';\n",
            "src/app.spec.ts": "import { TestBed } from '@angular/core/testing';\n",
        }
    )

    with_tests = scan(repo, out=repo / "a.json").profile
    without = scan(repo, out=repo / "b.json", include_tests=False).profile

    assert {entry.key for entry in with_tests.symbols} == {
        "npm:@angular/core#Component",
        "npm:@angular/core/testing#TestBed",
    }
    assert {entry.key for entry in without.symbols} == {"npm:@angular/core#Component"}


def test_max_locations_bounds_a_symbol_used_in_thirty_files(make_repo) -> None:
    """AC-3.3: ``count`` stays exact while only five locations are stored."""
    files = {"package.json": '{"name": "demo"}'}
    for index in range(30):
        files[f"src/f{index:02d}.ts"] = (
            "import { TestBed } from '@angular/core/testing';\nTestBed.get(X);\n"
        )
    repo = make_repo(files)

    profile = scan(repo, out=repo / "p.json", max_locations=5).profile
    entry = next(
        entry
        for entry in profile.symbols
        if entry.key == "@angular/core/testing#TestBed"
        or entry.key == "npm:@angular/core/testing#TestBed"
    )

    assert entry.count == 30
    assert entry.files == 30
    assert len(entry.locations) == 5
    assert entry.truncated is True


# --- a fixture that mixes every form --------------------------------------


def test_the_mixed_fixture_produces_exactly_the_expected_keys(ts_imports_repo) -> None:
    payload = read_profile(scan(ts_imports_repo, out=ts_imports_repo / "p.json").path)

    symbols = {entry["key"] for entry in payload["symbols"]}
    assert symbols == {
        "npm:@angular/core/testing#TestBed",
        "npm:pkg-default#default",
        "npm:pkg-destructured#a",
        "npm:pkg-destructured#b",
        "npm:pkg-named#A",
        "npm:pkg-named#B",
        "npm:pkg-reexport#Reexported",
        "npm:pkg-types#T",
        "npm:rxjs/internal/operators/deep#deep",
        # Package-level uses: ``import('pkg')``, ``require('pkg')``, ``export *``.
        "npm:pkg-dynamic",
        "npm:pkg-legacy",
        "npm:pkg-star",
    }
    assert {entry["key"] for entry in payload["side_effect_imports"]} == {
        "npm:pkg-side-effect",
    }
    # Own code (relative, paths alias, workspace package) never becomes a fact.
    assert not [key for key in symbols if key.startswith("npm:@demo")]
    assert not [key for key in symbols if key.startswith("npm:ts-imports")]
    assert payload["diagnostics"] == []


def test_the_type_only_flag_survives_into_the_profile(ts_imports_repo) -> None:
    payload = read_profile(scan(ts_imports_repo, out=ts_imports_repo / "p.json").path)

    entries = {entry["key"]: entry for entry in payload["symbols"]}
    assert entries["npm:pkg-types#T"]["type_only"] is True
    assert entries["npm:pkg-named#A"]["type_only"] is False


# --- review fixes: baseUrl, builtins ----------------------------------------


def test_a_base_url_import_is_own_code(make_repo) -> None:
    """``baseUrl: "./src"`` makes ``'app/core/x'`` the repo's own code (FR-5)."""
    repo = make_repo(
        {
            "package.json": json.dumps(
                {"name": "payments-ui", "dependencies": {"@angular/core": "^19.0.0"}}
            ),
            "tsconfig.json": json.dumps({"compilerOptions": {"baseUrl": "./src"}}),
            "src/app/core/core.service.ts": "export class CoreService {}\n",
            "src/main.ts": "export const x = 1;\n",
            "src/app/a.ts": (
                "import { CoreService } from 'app/core/core.service';\n"
                "import { x } from 'main';\n"
                "import { inject } from '@angular/core';\n"
            ),
        }
    )

    payload = read_profile(scan(repo, out=repo / "p.json").path)

    assert {entry["key"] for entry in payload["symbols"]} == {
        "npm:@angular/core#inject"
    }


def test_a_declared_dependency_beats_a_base_url_entry_of_the_same_name(
    make_repo,
) -> None:
    repo = make_repo(
        {
            "package.json": json.dumps({"dependencies": {"lodash": "^4.0.0"}}),
            "tsconfig.json": json.dumps({"compilerOptions": {"baseUrl": "."}}),
            "lodash/index.ts": "export const local = 1;\n",
            "src/a.ts": "import { map } from 'lodash';\n",
        }
    )

    payload = read_profile(scan(repo, out=repo / "p.json").path)

    assert "npm:lodash#map" in {entry["key"] for entry in payload["symbols"]}


def test_a_declared_npm_package_named_like_a_builtin_is_external(make_repo) -> None:
    """``events`` / ``buffer`` polyfills are npm packages when declared."""
    repo = make_repo(
        {
            "package.json": json.dumps(
                {"dependencies": {"events": "^3.3.0", "buffer": "^6.0.0"}}
            ),
            "src/a.ts": (
                "import { EventEmitter } from 'events';\n"
                "import { Buffer } from 'buffer';\n"
                "import { readFile } from 'fs';\n"
                "import { join } from 'node:path';\n"
            ),
        }
    )

    payload = read_profile(scan(repo, out=repo / "p.json").path)

    assert {entry["key"] for entry in payload["symbols"]} == {
        "npm:buffer#Buffer",
        "npm:events#EventEmitter",
    }
