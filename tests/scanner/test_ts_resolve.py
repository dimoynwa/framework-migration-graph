"""Barrel and alias resolution (spec 026.4 AC-2, AC-2.2, AC-2.3).

The resolver is a post-pass, so the tests go through :func:`scan` or call
:func:`resolve_barrels` with hand-built per-file facts. Both paths matter: the
first proves the wiring (the external key lands at the *import site*), the
second pins the chain rules without a file tree.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from migration_planner.scanner import builtin, contract
from migration_planner.scanner.contract import (
    FileFacts,
    ModuleEnv,
    OwnImport,
    OwnMember,
    OwnPackage,
    PathMap,
    PostPassContext,
    ResolutionEnv,
    Usage,
)
from migration_planner.scanner.scan import scan
from migration_planner.scanner.ts import GRAMMARS, extract_ts
from migration_planner.scanner.ts_resolve import MAX_DEPTH, resolve_barrels

from .conftest import read_profile


@pytest.fixture(autouse=True)
def installed_registry():
    """``scan()`` does not install; a scan test needs the shipped readers."""
    contract.reset_registry()
    builtin.install()
    yield
    contract.reset_registry()


@pytest.fixture()
def barrel_repo(tmp_path: Path) -> Path:
    """Copy of the ts-barrels fixture: barrels, aliases, a workspace package."""
    import shutil

    from .conftest import FIXTURES

    target = tmp_path / "ts-barrels"
    shutil.copytree(FIXTURES / "ts-barrels", target)
    return target


# --- a tiny in-memory repo ------------------------------------------------


def _facts(source: str, relative: str, env: ModuleEnv | None = None) -> FileFacts:
    """The facts spec3 would produce for a file, without touching the disk."""
    return extract_ts(
        contract.SourceContext(
            path=Path(relative),
            relative=relative,
            module=env.module if env is not None else ".",
            language="ts",
            data=source.encode("utf-8"),
            env=env if env is not None else _env(),
        )
    )


def _env(**kwargs) -> ModuleEnv:
    """The module environment the fixture tree pretends to have."""
    defaults = dict(
        module=".",
        path_map=PathMap(paths={"@app/*": ("src/app/*",)}, paths_dir="."),
    )
    defaults.update(kwargs)
    return ModuleEnv(**defaults)


def _resolve(
    files: dict[str, str],
    *,
    env: ModuleEnv | None = None,
    packages: dict[str, OwnPackage] | None = None,
):
    """Run the barrel pass over ``{path: source}`` and return its fragment."""
    known = tuple(sorted((packages or {}).keys()))
    if env is None:
        environment = _env(own_packages=known)
    elif known:
        environment = _env(
            path_map=env.path_map,
            base_url_roots=env.base_url_roots,
            declared_dependencies=env.declared_dependencies,
            own_packages=known,
        )
    else:
        environment = env
    facts = {
        relative: _facts(source, relative, environment)
        for relative, source in files.items()
    }
    context = PostPassContext(
        root=Path("."),
        files=facts,
        resolution=ResolutionEnv(
            module_of={relative: "." for relative in files},
            environments={".": environment},
            packages=packages or {},
        ),
    )
    return resolve_barrels(context)


def _keys(usages) -> list[tuple[str, str, int]]:
    return sorted((usage.key, usage.file, usage.line) for usage in usages)


# --- AC-2: the key lands at the import site -------------------------------


def test_a_barrel_chain_records_the_key_at_the_original_import_site() -> None:
    """AC-2: ``a.ts`` → ``@app/core`` → ``./di`` → ``@angular/core``."""
    fragment = _resolve(
        {
            "src/app/a.ts": "import { inject } from '@app/core';\n",
            "src/app/core/index.ts": "export { inject } from './di';\n",
            "src/app/core/di.ts": "export { inject } from '@angular/core';\n",
        }
    )

    # The importing file — the site a matcher must search — is in the profile.
    assert ("npm:@angular/core#inject", "src/app/a.ts", 1) in _keys(fragment.symbols)
    # No other symbol, and every location is an import site (spec1 FR-9): the
    # importing file and the barrel's own re-export, never a call.
    assert {usage.key for usage in fragment.symbols} == {"npm:@angular/core#inject"}
    assert {usage.file for usage in fragment.symbols} == {
        "src/app/a.ts",
        "src/app/core/index.ts",
    }
    assert fragment.diagnostics == []


def test_a_relative_import_of_a_file_that_re_exports_is_resolved() -> None:
    fragment = _resolve(
        {
            "src/app/a.ts": "import { Component } from './comp';\n",
            "src/app/comp.ts": "export { Component } from '@angular/core';\n",
        }
    )

    assert _keys(fragment.symbols) == [
        ("npm:@angular/core#Component", "src/app/a.ts", 1)
    ]


def test_a_barrel_cycle_is_a_diagnostic_and_records_nothing() -> None:
    """AC-2: a cycle gives ``barrel_cycle`` and no crash."""
    fragment = _resolve(
        {
            "src/app/a.ts": "import { x } from './cycle-a';\n",
            "src/app/cycle-a.ts": "export * from './cycle-b';\n",
            "src/app/cycle-b.ts": "export * from './cycle-a';\n",
        }
    )

    assert fragment.symbols == []
    assert [entry.kind for entry in fragment.diagnostics] == ["barrel_cycle"]


def test_a_self_reexporting_file_is_a_cycle() -> None:
    fragment = _resolve(
        {
            "src/app/a.ts": "import { x } from './self';\n",
            "src/app/self.ts": "export { x } from './self';\n",
        }
    )

    assert fragment.symbols == []
    assert [entry.kind for entry in fragment.diagnostics] == ["barrel_cycle"]


# --- AC-2.2: the shapes a chain can take ----------------------------------


def test_an_export_star_chain_is_followed() -> None:
    fragment = _resolve(
        {
            "src/app/a.ts": "import { signal } from '@app/core';\n",
            "src/app/core/index.ts": "export * from './signals';\n",
            "src/app/core/signals.ts": "export { signal } from '@angular/core';\n",
        }
    )

    assert _keys(fragment.symbols) == [("npm:@angular/core#signal", "src/app/a.ts", 1)]


def test_an_export_star_of_a_package_ends_the_chain_at_that_package() -> None:
    """``export * from '@angular/cdk/a11y'`` cannot be enumerated, so a name that
    reaches it belongs to that package (that is where FR-5 follows it to)."""
    fragment = _resolve(
        {
            "src/app/a.ts": "import { LiveAnnouncer } from '@app/core';\n",
            "src/app/core/index.ts": "export * from '@angular/cdk/a11y';\n",
        }
    )

    assert _keys(fragment.symbols) == [
        ("npm:@angular/cdk/a11y#LiveAnnouncer", "src/app/a.ts", 1)
    ]


def test_a_rename_chain_reaches_the_original_name() -> None:
    """AC-2: ``export { inject as di }`` + ``import { di }`` → ``#inject``."""
    fragment = _resolve(
        {
            "src/app/a.ts": "import { di } from '@app/core';\ndi.call(TOKEN);\n",
            "src/app/core/index.ts": "export { inject as di } from '@angular/core';\n",
        }
    )

    assert ("npm:@angular/core#inject", "src/app/a.ts", 1) in _keys(fragment.symbols)
    # The local name follows the chain too (``…#inject.call``).
    assert _keys(fragment.members) == [
        ("npm:@angular/core#inject.call", "src/app/a.ts", 2)
    ]


def test_a_rename_is_applied_through_several_barrels() -> None:
    fragment = _resolve(
        {
            "src/app/a.ts": "import { renamed } from './one';\n",
            "src/app/one.ts": "export { other as renamed } from './two';\n",
            "src/app/two.ts": "export { inner as other } from '@angular/core';\n",
        }
    )

    assert ("npm:@angular/core#inner", "src/app/a.ts", 1) in _keys(fragment.symbols)
    assert {usage.key for usage in fragment.symbols} == {"npm:@angular/core#inner"}


def test_a_namespace_import_of_a_barrel_resolves_per_member() -> None:
    """AC-2.2: ``core.inject(…)`` → ``npm:@angular/core#inject``."""
    fragment = _resolve(
        {
            "src/app/a.ts": (
                "import * as core from '@app/core';\ncore.inject(TOKEN);\n"
            ),
            "src/app/core/index.ts": "export { inject } from '@angular/core';\n",
        }
    )

    assert _keys(fragment.symbols) == [("npm:@angular/core#inject", "src/app/a.ts", 2)]
    # A namespace publishes no symbol of its own, exactly as for an external one.
    assert all(usage.line != 1 for usage in fragment.symbols)


def test_a_namespaced_decorator_keeps_its_symbol_and_options() -> None:
    fragment = _resolve(
        {
            "src/app/a.ts": (
                "import * as core from '@app/core';\n"
                "@core.Component({ selector: 'x', standalone: true })\n"
                "class C {}\n"
            ),
            "src/app/core/index.ts": "export { Component } from '@angular/core';\n",
        }
    )

    assert "npm:@angular/core#Component" in [usage.key for usage in fragment.symbols]
    assert [usage.key for usage in fragment.members] == [
        "npm:@angular/core#Component.selector",
        "npm:@angular/core#Component.standalone",
    ]


def test_a_member_of_a_renamed_barrel_import_is_a_member_of_the_real_symbol() -> None:
    fragment = _resolve(
        {
            "src/app/a.ts": "import { TB } from '@app/test';\nTB.get(X);\n",
            "src/app/test.ts": "export { TestBed as TB } from '@angular/core/testing';\n",
        }
    )

    assert (
        "npm:@angular/core/testing#TestBed",
        "src/app/a.ts",
        1,
    ) in _keys(fragment.symbols)
    assert _keys(fragment.members) == [
        ("npm:@angular/core/testing#TestBed.get", "src/app/a.ts", 2)
    ]


def test_a_paths_alias_with_a_star_resolves_to_its_target() -> None:
    fragment = _resolve(
        {
            "src/app/a.ts": "import { effect } from '@app/signals';\n",
            "src/app/signals.ts": "export { effect } from '@angular/core';\n",
        }
    )

    assert _keys(fragment.symbols) == [("npm:@angular/core#effect", "src/app/a.ts", 1)]


def test_the_first_existing_paths_target_wins() -> None:
    """AC-2.2: multiple targets are tried in order; the first that exists wins."""
    env = _env(
        path_map=PathMap(
            paths={"@shared/*": ("generated/shared/*", "src/shared/*")},
            paths_dir=".",
        )
    )
    fragment = _resolve(
        {
            "src/app/a.ts": "import { effect } from '@shared/x';\n",
            "src/shared/x.ts": "export { effect } from './from-real';\n",
            "generated/shared/from-real.ts": "export { effect } from '@other/pkg';\n",
            "src/shared/from-real.ts": "export { effect } from '@angular/core';\n",
        },
        env=env,
    )

    # The generated target exists too; the first one in the list still wins.
    assert ("npm:@angular/core#effect", "src/app/a.ts", 1) in _keys(fragment.symbols)
    assert not [usage.key for usage in fragment.symbols if "pkg" in usage.key]


def test_a_base_url_import_resolves() -> None:
    env = _env(
        path_map=PathMap(base_url="src", paths_dir="src"),
        base_url_roots=("app",),
    )
    fragment = _resolve(
        {
            "src/app/a.ts": "import { inject } from 'app/core/x';\n",
            "src/app/core/x.ts": "export { inject } from '@angular/core';\n",
        },
        env=env,
    )

    assert ("npm:@angular/core#inject", "src/app/a.ts", 1) in _keys(fragment.symbols)


def test_a_workspace_package_entry_point_resolves() -> None:
    """AC-2.2: an own package name resolves through its ``package.json`` entry."""
    fragment = _resolve(
        {
            "src/app/a.ts": "import { Button } from '@demo/ui';\n",
            "packages/ui/src/index.ts": "export { Button } from './button';\n",
            "packages/ui/src/button.ts": "export { Button } from '@angular/core';\n",
        },
        packages={
            "@demo/ui": OwnPackage(
                name="@demo/ui",
                directory="packages/ui",
                entries=("./src/index.ts",),
            )
        },
    )

    assert ("npm:@angular/core#Button", "src/app/a.ts", 1) in _keys(fragment.symbols)
    assert {usage.key for usage in fragment.symbols} == {"npm:@angular/core#Button"}


def test_a_workspace_package_falls_back_to_its_index() -> None:
    fragment = _resolve(
        {
            "src/app/a.ts": "import { thing } from '@demo/ui';\n",
            "packages/ui/index.ts": "export { thing } from '@angular/core';\n",
        },
        packages={"@demo/ui": OwnPackage(name="@demo/ui", directory="packages/ui")},
    )

    assert ("npm:@angular/core#thing", "src/app/a.ts", 1) in _keys(fragment.symbols)


def test_a_workspace_subpath_resolves_under_the_package_directory() -> None:
    fragment = _resolve(
        {
            "src/app/a.ts": "import { thing } from '@demo/ui/deep/thing';\n",
            "packages/ui/deep/thing.ts": "export { thing } from '@angular/core';\n",
        },
        packages={"@demo/ui": OwnPackage(name="@demo/ui", directory="packages/ui")},
    )

    assert ("npm:@angular/core#thing", "src/app/a.ts", 1) in _keys(fragment.symbols)


def test_a_namespaced_reexport_is_resolved_to_its_barrel() -> None:
    """``export * as ns from './x'`` publishes a namespace, not a symbol."""
    fragment = _resolve(
        {
            "src/app/a.ts": "import { ns } from '@app/core';\nns.inject(TOKEN);\n",
            "src/app/core/index.ts": "export * as ns from './inner';\n",
            "src/app/core/inner.ts": "export { inject } from '@angular/core';\n",
        }
    )

    assert _keys(fragment.symbols) == [("npm:@angular/core#inject", "src/app/a.ts", 2)]


# --- extension probing ---------------------------------------------------


@pytest.mark.parametrize(
    ("target", "specifier"),
    [
        ("src/app/x.ts", "./x"),
        ("src/app/x.tsx", "./x"),
        ("src/app/x.d.ts", "./x"),
        ("src/app/x.js", "./x"),
        ("src/app/x.mjs", "./x"),
        ("src/app/x.cjs", "./x"),
        ("src/app/x/index.ts", "./x"),
    ],
)
def test_every_extension_is_probed(target: str, specifier: str) -> None:
    fragment = _resolve(
        {
            "src/app/a.ts": f"import {{ inject }} from '{specifier}';\n",
            target: "export { inject } from '@angular/core';\n",
        }
    )

    assert _keys(fragment.symbols) == [("npm:@angular/core#inject", "src/app/a.ts", 1)]


def test_a_js_specifier_finds_its_typescript_source() -> None:
    """``NodeNext`` writes ``./x.js`` for ``x.ts``."""
    fragment = _resolve(
        {
            "src/app/a.ts": "import { inject } from './x.js';\n",
            "src/app/x.ts": "export { inject } from '@angular/core';\n",
        }
    )

    assert _keys(fragment.symbols) == [("npm:@angular/core#inject", "src/app/a.ts", 1)]


def test_a_dot_slash_index_specifier_is_probed() -> None:
    fragment = _resolve(
        {
            "src/app/a.ts": "import { inject } from './core';\n",
            "src/app/core/index.ts": "export { inject } from '@angular/core';\n",
        }
    )

    assert _keys(fragment.symbols) == [("npm:@angular/core#inject", "src/app/a.ts", 1)]


# --- AC-2.3: names that end in own code, and depth -----------------------


def test_a_name_that_ends_in_a_local_declaration_is_dropped() -> None:
    """AC-2.3: a class the barrel declares itself is own code."""
    fragment = _resolve(
        {
            "src/app/a.ts": (
                "import { LocalHelper, inject } from '@app/core';\nLocalHelper.q();\n"
            ),
            "src/app/core/index.ts": (
                "export class LocalHelper {}\nexport { inject } from '@angular/core';\n"
            ),
        }
    )

    assert [usage.key for usage in fragment.symbols] == ["npm:@angular/core#inject"]
    assert fragment.members == []


def test_a_declaration_wins_over_an_export_star() -> None:
    """A name the file declares is own code even when a star could supply it."""
    fragment = _resolve(
        {
            "src/app/a.ts": "import { Local } from '@app/core';\n",
            "src/app/core/index.ts": (
                "export class Local {}\nexport * from './other';\n"
            ),
            "src/app/core/other.ts": "export { Local } from '@angular/core';\n",
        }
    )

    assert fragment.symbols == []


def test_a_default_export_that_is_declared_here_is_dropped() -> None:
    fragment = _resolve(
        {
            "src/app/a.ts": "import Def from '@app/core';\n",
            "src/app/core/index.ts": "export default class Foo {}\n",
        }
    )

    assert fragment.symbols == []


def test_a_chain_of_exactly_max_depth_resolves_and_one_more_does_not() -> None:
    """AC-2.3: depth 11 → a ``barrel_depth`` diagnostic and no fact."""
    files = {
        "src/app/a.ts": "import { ok, tooDeep } from './ok0';\nimport { x } from './deep0';\n"
    }
    for index in range(MAX_DEPTH - 1):
        files[f"src/app/ok{index}.ts"] = f"export * from './ok{index + 1}';\n"
    files[f"src/app/ok{MAX_DEPTH - 1}.ts"] = "export { ok } from '@angular/core';\n"
    for index in range(MAX_DEPTH):
        files[f"src/app/deep{index}.ts"] = f"export * from './deep{index + 1}';\n"
    files[f"src/app/deep{MAX_DEPTH}.ts"] = "export { x } from '@angular/core';\n"

    fragment = _resolve(files)

    assert _keys(fragment.symbols) == [("npm:@angular/core#ok", "src/app/a.ts", 1)]
    depth_entries = [
        entry for entry in fragment.diagnostics if entry.kind == "barrel_depth"
    ]
    assert len(depth_entries) == 1
    assert depth_entries[0].file == f"src/app/deep{MAX_DEPTH}.ts"


def test_a_short_chain_still_resolves_after_a_deep_one_gave_up() -> None:
    """A give-up is per entry point, so it must not poison the memo (FR-5).

    ``x`` is reachable in one hop from ``near.ts`` and only past the depth limit
    from ``deep0.ts``. The deep file is visited first, and the near one must
    still resolve.
    """
    files = {
        "src/app/a.ts": "import { x } from './deep0';\nimport { x as y } from './near';\n",
        "src/app/near.ts": "export { x } from '@angular/core';\n",
    }
    for index in range(MAX_DEPTH):
        files[f"src/app/deep{index}.ts"] = f"export * from './deep{index + 1}';\n"
    files[f"src/app/deep{MAX_DEPTH}.ts"] = "export { x } from '@angular/core';\n"

    fragment = _resolve(files)

    assert ("npm:@angular/core#x", "src/app/a.ts", 2) in _keys(fragment.symbols)
    assert [entry.kind for entry in fragment.diagnostics] == ["barrel_depth"]


def test_an_unresolvable_import_is_a_diagnostic() -> None:
    fragment = _resolve({"src/app/a.ts": "import { x } from './missing';\n"})

    assert fragment.symbols == []
    assert [
        (entry.kind, entry.file, entry.detail) for entry in fragment.diagnostics
    ] == [("unresolved_import", "src/app/a.ts", "./missing")]


@pytest.mark.parametrize("specifier", ["./styles.scss", "./data.json", "./icon.svg"])
def test_an_asset_import_is_not_a_diagnostic(specifier: str) -> None:
    """It names something the scanner does not parse, so there is nothing to report."""
    fragment = _resolve({"src/app/a.ts": f"import '{specifier}';\n"})

    assert fragment.symbols == []
    assert fragment.diagnostics == []


def test_a_builtin_behind_a_barrel_is_skipped() -> None:
    fragment = _resolve(
        {
            "src/app/a.ts": "import { EventEmitter } from '@app/core';\n",
            "src/app/core/index.ts": "export { EventEmitter } from 'node:events';\n",
        }
    )

    assert fragment.symbols == []
    assert fragment.diagnostics == []


def test_type_only_travels_along_the_chain() -> None:
    fragment = _resolve(
        {
            "src/app/a.ts": "import type { Model } from '@app/core';\n",
            "src/app/core/index.ts": "export { Model } from '@app/models';\n",
            "src/app/models.ts": "export { Model } from '@angular/core';\n",
        }
    )

    # At the importing file the whole chain is type-only.
    types = {
        (usage.key, usage.type_only)
        for usage in fragment.symbols
        if usage.file == "src/app/a.ts"
    }
    assert types == {("npm:@angular/core#Model", True)}


def test_resolution_is_memoized_per_file_and_name() -> None:
    """A barrel imported by many files is resolved once (FR-5 "Execution")."""
    files = {
        "src/app/core/index.ts": "export { inject } from '@angular/core';\n",
    }
    for index in range(20):
        files[f"src/app/f{index}.ts"] = "import { inject } from '@app/core';\n"

    fragment = _resolve(files)

    # Every importer gets the key at its own line, and the barrel is visited once.
    assert len(fragment.symbols) == 20
    assert {usage.file for usage in fragment.symbols} == {
        f"src/app/f{index}.ts" for index in range(20)
    }


# --- the post-pass is registered and does nothing when there is no barrel --


def test_the_barrel_pass_is_registered() -> None:
    assert resolve_barrels in builtin.POST_PASSES
    assert resolve_barrels in contract.post_passes()


def test_extractors_still_get_the_same_grammars() -> None:
    assert set(GRAMMARS) <= set(builtin.SOURCE_EXTRACTORS)
    assert all(builtin.SOURCE_EXTRACTORS[language] is extract_ts for language in GRAMMARS)


# --- AC-2 / AC-2.2 / AC-2.3 through a real scan ---------------------------


def test_scan_resolves_a_barrel_at_the_import_site(barrel_repo: Path) -> None:
    payload = read_profile(scan(barrel_repo, out=barrel_repo / "p.json").path)

    symbols = {entry["key"]: entry for entry in payload["symbols"]}
    inject = symbols["npm:@angular/core#inject"]
    files = {location["file"] for location in inject["locations"]}
    # ``feature.ts`` imports ``inject`` from ``@app/core``; the key is there.
    assert "src/app/feature.ts" in files
    # ``LocalHelper`` is declared by the barrel: own code, not a fact.
    assert not [key for key in symbols if "LocalHelper" in key]
    # ``utilFn`` is declared by the barrel: own code, not a fact.
    assert not [key for key in symbols if "utilFn" in key]


def test_scan_of_the_barrel_fixture_has_no_unresolved_diagnostics(
    barrel_repo: Path,
) -> None:
    payload = read_profile(scan(barrel_repo, out=barrel_repo / "p.json").path)

    kinds = {entry["kind"] for entry in payload["diagnostics"]}
    assert kinds <= {"barrel_cycle", "barrel_depth"}


def test_scan_reports_the_barrel_cycle_and_depth(barrel_repo: Path) -> None:
    payload = read_profile(scan(barrel_repo, out=barrel_repo / "p.json").path)

    by_kind = {entry["kind"]: entry for entry in payload["diagnostics"]}
    assert by_kind["barrel_cycle"]["file"] == "src/app/cycle-a.ts"
    assert by_kind["barrel_depth"]["file"].startswith("src/deep/deep")


def test_scan_stops_a_too_deep_chain_at_the_import_site(barrel_repo: Path) -> None:
    """AC-2.3 through the real wiring: depth 10 resolves, depth 11 does not.

    The depth-11 name is still a fact of the file that imports Angular directly
    (spec3 records an external re-export at its own line); what the limit stops
    is attributing it to ``src/app/deep-import.ts``, the file at the far end.
    """
    payload = read_profile(scan(barrel_repo, out=barrel_repo / "p.json").path)

    symbols = {entry["key"]: entry for entry in payload["symbols"]}
    allowed = {
        location["file"]
        for location in symbols["npm:@angular/core#deepAllowed"]["locations"]
    }
    too_far = {
        location["file"]
        for location in symbols["npm:@angular/core#deepTooFar"]["locations"]
    }
    assert "src/app/deep-import.ts" in allowed
    assert "src/app/deep-import.ts" not in too_far


def test_scan_resolves_a_workspace_package_and_a_paths_alias(
    barrel_repo: Path,
) -> None:
    """AC-2.2 through the real wiring, including the package entry point."""
    payload = read_profile(scan(barrel_repo, out=barrel_repo / "p.json").path)

    symbols = {entry["key"]: entry for entry in payload["symbols"]}
    announce = symbols["npm:@angular/cdk/a11y#announce"]
    assert "src/app/feature-imports.ts" in {
        location["file"] for location in announce["locations"]
    }
    track = symbols["npm:@angular/platform-browser#track"]
    assert "src/app/feature-imports.ts" in {
        location["file"] for location in track["locations"]
    }


def test_a_barrel_import_raises_the_symbol_count(make_repo) -> None:
    """The spec4 headline: symbols that spec3 missed are now present."""
    common = {
        "package.json": '{"name": "demo", "dependencies": {"@angular/core": "^19.2.0"}}',
        "tsconfig.json": json.dumps(
            {"compilerOptions": {"paths": {"@app/*": ["src/app/*"]}}}
        ),
    }
    without_barrel = make_repo(
        {**common, "src/app/a.ts": "import { inject } from '@angular/core';\n"},
        name="direct",
    )
    with_barrel = make_repo(
        {
            **common,
            "src/app/a.ts": "import { inject } from '@app/core';\n",
            "src/app/core/index.ts": "export { inject } from './di';\n",
            "src/app/core/di.ts": "export { inject } from '@angular/core';\n",
        },
        name="barrel",
    )

    direct = scan(without_barrel, out=without_barrel / "p.json").profile
    through = scan(with_barrel, out=with_barrel / "p.json").profile

    assert {entry.key for entry in direct.symbols} == {"npm:@angular/core#inject"}
    assert {entry.key for entry in through.symbols} == {"npm:@angular/core#inject"}
    # ... and the barrel version has more sites, the import one among them.
    direct_locations = direct.symbols[0].count
    barrel_locations = through.symbols[0].count
    assert barrel_locations > direct_locations


def test_the_spec3_extractor_keeps_own_members_for_the_post_pass() -> None:
    """The seam between the two specs: own members are input, not facts (FR-5)."""
    facts = _facts(
        "import { Component } from '@app/core';\n"
        "@Component({ selector: 'x' })\n"
        "class C {}\n",
        "src/app/a.ts",
    )

    assert facts.symbols == []
    assert facts.members == []
    assert facts.own_member_bindings == [
        OwnMember(
            relative="src/app/a.ts",
            line=2,
            test=False,
            local="Component",
            member="selector",
            symbol="",
        )
    ]


def test_a_shadowed_own_import_records_no_member() -> None:
    fragment = _resolve(
        {
            "src/app/a.ts": (
                "import { inject } from '@app/core';\n"
                "function f(inject) {\n  inject.call();\n}\n"
                "inject(TOKEN);\n"
            ),
            "src/app/core/index.ts": "export { inject } from '@angular/core';\n",
        }
    )

    assert _keys(fragment.members) == []
    assert [usage.line for usage in fragment.symbols] == [1]


def test_an_own_import_binding_of_a_barrel_is_kept_by_the_extractor() -> None:
    facts = _facts("import { inject } from '@app/core';\n", "src/app/a.ts")

    assert facts.own_import_bindings == [
        OwnImport(
            relative="src/app/a.ts",
            line=1,
            test=False,
            specifier="@app/core",
            is_relative=False,
            named={"inject": "inject"},
            default="",
            namespace="",
            type_only=False,
        )
    ]


def test_the_resolver_only_reports_symbols_and_members() -> None:
    fragment = _resolve(
        {
            "src/app/a.ts": (
                "import { inject } from '@app/core';\nimport 'zone.js';\n"
            ),
            "src/app/core/index.ts": "export { inject } from '@angular/core';\n",
        }
    )

    # ``usage`` is a fact of the extractor, never of the post-pass.
    assert all(isinstance(usage, Usage) for usage in fragment.symbols)
    assert fragment.side_effect_imports == []
    assert fragment.own_import_bindings == []


# --- review fixes (2026-11-06) ----------------------------------------------


def _scan_tree(tmp_path: Path, files: dict[str, str]) -> dict:
    repo = tmp_path / "repo"
    for relative, content in files.items():
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return read_profile(scan(repo, out=repo / "p.json").path)


def _sites(payload: dict, file: str) -> set[tuple[str, int]]:
    return {
        (entry["key"], location["line"])
        for entry in payload["symbols"]
        for location in entry["locations"]
        if location["file"] == file
    }


_PACKAGE = json.dumps(
    {"name": "ui", "dependencies": {"@angular/core": "^19", "rxjs": "^7"}}
)
_TSCONFIG = json.dumps(
    {"compilerOptions": {"baseUrl": ".", "paths": {"@app/*": ["src/app/*"]}}}
)


def test_every_own_star_is_searched_not_only_the_first(tmp_path: Path) -> None:
    """``public-api.ts`` with many ``export * from './x'``: the name may be in any of them."""
    payload = _scan_tree(
        tmp_path,
        {
            "package.json": _PACKAGE,
            "tsconfig.json": _TSCONFIG,
            "src/app/core/index.ts": "export * from './a';\nexport * from './b';\n",
            "src/app/core/a.ts": "export const onlyA = 1;\n",
            "src/app/core/b.ts": "export { inject } from '@angular/core';\n",
            "src/app/x.ts": "import { inject } from '@app/core';\n",
        },
    )

    assert ("npm:@angular/core#inject", 1) in _sites(payload, "src/app/x.ts")


def test_an_imported_then_exported_name_is_a_re_export(tmp_path: Path) -> None:
    payload = _scan_tree(
        tmp_path,
        {
            "package.json": _PACKAGE,
            "tsconfig.json": _TSCONFIG,
            "src/app/core/index.ts": (
                "import { Injectable } from '@angular/core';\n"
                "import * as rxjs from 'rxjs';\n"
                "export { Injectable, rxjs };\n"
            ),
            "src/app/x.ts": "import { Injectable, rxjs } from '@app/core';\nrxjs.of(1);\n",
        },
    )

    sites = _sites(payload, "src/app/x.ts")
    assert ("npm:@angular/core#Injectable", 1) in sites
    assert ("npm:rxjs#of", 2) in sites


def test_a_paths_alias_into_node_modules_stays_external(tmp_path: Path) -> None:
    """``"@angular/*": ["./node_modules/@angular/*"]`` is a redirect, not own code."""
    tsconfig = json.dumps(
        {
            "compilerOptions": {
                "baseUrl": ".",
                "paths": {
                    "@app/*": ["src/app/*"],
                    "@angular/*": ["./node_modules/@angular/*"],
                },
            }
        }
    )
    payload = _scan_tree(
        tmp_path,
        {
            "package.json": _PACKAGE,
            "tsconfig.json": tsconfig,
            "src/app/x.ts": "import { Component } from '@angular/core';\n",
        },
    )

    assert ("npm:@angular/core#Component", 1) in _sites(payload, "src/app/x.ts")
    assert not [d for d in payload["diagnostics"] if d["kind"] == "unresolved_import"]


def test_several_external_stars_are_reported_not_guessed(tmp_path: Path) -> None:
    payload = _scan_tree(
        tmp_path,
        {
            "package.json": _PACKAGE,
            "tsconfig.json": _TSCONFIG,
            "src/app/core/index.ts": "export * from '@angular/core';\nexport * from 'rxjs';\n",
            "src/app/x.ts": "import { map } from '@app/core';\n",
        },
    )

    assert not [
        key for key, _ in _sites(payload, "src/app/x.ts") if key.endswith("#map")
    ]
    ambiguous = [d for d in payload["diagnostics"] if d["kind"] == "ambiguous_export"]
    assert [d["detail"] for d in ambiguous] == ["map: @angular/core | rxjs"]


def test_a_single_external_star_still_attributes_the_name(tmp_path: Path) -> None:
    payload = _scan_tree(
        tmp_path,
        {
            "package.json": _PACKAGE,
            "tsconfig.json": _TSCONFIG,
            "src/app/util/index.ts": (
                "export * from 'rxjs';\n"
                "export function helper() { const map = new Map(); return map; }\n"
            ),
            "src/app/x.ts": "import { map } from '@app/util';\n",
        },
    )

    # The ``const map`` inside ``helper`` is not a module export.
    assert ("npm:rxjs#map", 1) in _sites(payload, "src/app/x.ts")


def test_inline_type_through_a_barrel_is_type_only_per_name() -> None:
    """The import site keeps the per-name ``type`` flag (the profile then ANDs
    it with the barrel's own value re-export, spec1 FR-9)."""
    fragment = _resolve(
        {
            "src/app/core/index.ts": "export { Signal, inject } from '@angular/core';\n",
            "src/app/x.ts": "import { type Signal, inject } from '@app/core';\n",
        }
    )

    flags = {
        usage.key: usage.type_only
        for usage in fragment.symbols
        if usage.file == "src/app/x.ts"
    }
    assert flags == {
        "npm:@angular/core#Signal": True,
        "npm:@angular/core#inject": False,
    }


def test_a_workspace_subpath_export_resolves(tmp_path: Path) -> None:
    payload = _scan_tree(
        tmp_path,
        {
            "package.json": json.dumps(
                {
                    "name": "app",
                    "workspaces": ["packages/*"],
                    "dependencies": {"@angular/core": "^19"},
                }
            ),
            "packages/ui/package.json": json.dumps(
                {
                    "name": "@demo/ui",
                    "exports": {".": "./src/index.ts", "./testing": "./src/testing.ts"},
                }
            ),
            "packages/ui/src/index.ts": "export const x = 1;\n",
            "packages/ui/src/testing.ts": "export { TestBed } from '@angular/core/testing';\n",
            "src/x.ts": "import { TestBed } from '@demo/ui/testing';\n",
        },
    )

    assert ("npm:@angular/core/testing#TestBed", 1) in _sites(payload, "src/x.ts")
    assert not [d for d in payload["diagnostics"] if d["kind"] == "unresolved_import"]


def test_an_external_namespace_re_export_gives_member_symbols(tmp_path: Path) -> None:
    payload = _scan_tree(
        tmp_path,
        {
            "package.json": _PACKAGE,
            "tsconfig.json": _TSCONFIG,
            "src/app/core/index.ts": "export * as rx from 'rxjs';\n",
            "src/app/x.ts": "import { rx } from '@app/core';\nrx.filter();\n",
        },
    )

    assert ("npm:rxjs#filter", 2) in _sites(payload, "src/app/x.ts")


def test_a_bundler_query_is_not_an_unresolved_import(tmp_path: Path) -> None:
    payload = _scan_tree(
        tmp_path,
        {
            "package.json": _PACKAGE,
            "src/worker.ts": "export default 1;\n",
            "src/x.ts": "import W from './worker?worker';\n",
        },
    )

    assert not [d for d in payload["diagnostics"] if d["kind"] == "unresolved_import"]
