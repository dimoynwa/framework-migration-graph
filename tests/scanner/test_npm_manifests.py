"""npm manifests, tsconfig and the Angular version (spec 026.2 FR-3, FR-4, AC-8).

Covers the four readers and the pieces the later specs read off them: the
Angular version (lockfile beats range), the four dependency scopes, the
``*``-normalized ``angular.json`` keys, ``tsconfig`` comments / trailing commas /
``extends`` and the effective path map.
"""

from __future__ import annotations

import json

import pytest

from migration_planner.scanner import contract
from migration_planner.scanner.npm_manifests import (
    MAX_CONFIG_VALUE_CHARS,
    normalize_range,
    strip_jsonc,
)
from migration_planner.scanner.scan import scan

from .conftest import read_profile, write


@pytest.fixture(autouse=True)
def clean_registry():
    """The npm reader is installed by the scan itself; no test may leak state."""
    contract.reset_registry()
    yield
    contract.reset_registry()


def _scan(repo):
    """Scan and return ``(profile, by_key)`` for the two sections that matter here."""
    result = scan(repo, out=repo / "profile.json")
    profile = read_profile(repo / "profile.json")
    config = {entry["key"]: entry for entry in profile["config"]}
    dependencies = {entry["key"]: entry for entry in profile["dependencies"]}
    return result, profile, config, dependencies


# --- AC-8: the whole picture on the Angular fixture ------------------------


def test_angular_version_comes_from_the_lockfile(polyglot_repo) -> None:
    _, profile, _, _ = _scan(polyglot_repo)

    # ``package.json`` says ``^19.2.0``; the lockfile says what is installed.
    assert profile["framework"] == {
        "name": "angular",
        "version": "19.2.0",
        "raw": "^19.2.0",
        "source": "package.json",
    }


def test_lockfile_version_beats_the_range(angular_app) -> None:
    result, profile, _, dependencies = _scan(angular_app)

    assert profile["framework"]["version"] == "19.2.4"
    assert profile["framework"]["raw"] == "^19.2.0"
    assert profile["framework"]["source"] == "package-lock.json"
    assert dependencies["npm:@angular/core"]["version"] == "19.2.4"
    assert dependencies["npm:@angular/core"]["range"] == "^19.2.0"
    assert result.summary.framework_version == "19.2.4"


def test_without_a_lockfile_the_range_is_kept_and_normalized(make_repo) -> None:
    repo = make_repo(
        {
            "package.json": json.dumps(
                {"dependencies": {"@angular/core": "^19.2.0", "rxjs": "~7.8.1"}}
            )
        }
    )

    result, profile, _, dependencies = _scan(repo)

    assert profile["framework"] == {
        "name": "angular",
        "version": "19.2.0",
        "raw": "^19.2.0",
        "source": "package.json",
    }
    assert dependencies["npm:rxjs"]["range"] == "~7.8.1"
    assert dependencies["npm:rxjs"]["version"] == "7.8.1"
    assert result.summary.framework_version == "19.2.0"


def test_all_four_dependency_scopes_are_recorded(angular_app) -> None:
    _, _, _, dependencies = _scan(angular_app)

    scopes = {entry["key"]: entry["scope"] for entry in dependencies.values()}
    assert scopes["npm:@angular/core"] == "dependencies"
    assert scopes["npm:typescript"] == "devDependencies"
    assert scopes["npm:zone.js"] == "peerDependencies"
    assert scopes["npm:@esbuild/darwin-arm64"] == "optionalDependencies"
    assert all(entry["kind"] == "dependency" for entry in dependencies.values())


def test_angular_json_project_names_are_normalized_to_a_wildcard(angular_app) -> None:
    _, profile, config, _ = _scan(angular_app)

    # The key is written once and matches every project (FR-4).
    assert (
        config["cfg:angular.json#projects.*.architect.build.builder"]["value"]
        == "@angular-devkit/build-angular:application"
    )
    assert "cfg:angular.json#projects.payments-ui.architect.build.builder" not in config
    # The real names are kept on the module.
    assert profile["modules"][0]["angular_projects"] == [
        "payments-admin",
        "payments-ui",
    ]


def test_builders_are_listed_per_target(angular_app) -> None:
    _, _, config, _ = _scan(angular_app)

    builders = {
        key: entry["value"]
        for key, entry in config.items()
        if key.startswith("cfg:angular.json#projects.*.architect.")
        and key.endswith(".builder")
    }
    assert builders == {
        "cfg:angular.json#projects.*.architect.build.builder": (
            "@angular-devkit/build-angular:application"
        ),
        "cfg:angular.json#projects.*.architect.serve.builder": (
            "@angular-devkit/build-angular:dev-server"
        ),
        "cfg:angular.json#projects.*.architect.test.builder": (
            "@angular-devkit/build-angular:karma"
        ),
    }


def test_every_angular_json_scalar_leaf_gets_a_key(angular_app) -> None:
    _, _, config, _ = _scan(angular_app)

    # Lists keep their index, so two polyfills are two facts.
    assert (
        config["cfg:angular.json#projects.*.architect.build.options.polyfills.0"][
            "value"
        ]
        == "zone.js"
    )
    assert (
        config["cfg:angular.json#projects.*.architect.build.options.budgets.0.type"][
            "value"
        ]
        == "initial"
    )
    assert config["cfg:angular.json#version"]["value"] == "1"
    # An empty string is a value, not "unset".
    assert config["cfg:angular.json#projects.*.root"]["value"] == ""


def test_package_json_config_keys_cover_the_declared_subtrees(angular_app) -> None:
    _, _, config, _ = _scan(angular_app)

    assert config["cfg:package.json#engines.node"]["value"] == ">=18.19.0"
    assert config["cfg:package.json#type"]["value"] == "module"
    assert (
        config["cfg:package.json#browserslist.0"]["value"] == "last 2 Chrome versions"
    )
    assert config["cfg:package.json#overrides.esbuild"]["value"] == "0.25.0"
    assert config["cfg:package.json#resolutions.**/braces"]["value"] == "3.0.3"
    # ``dependencies.*`` is a dependency fact, not a config key.
    assert "cfg:package.json#dependencies.@angular/core" not in config
    assert "cfg:package.json#scripts.build" not in config


def test_config_values_are_truncated_to_200_chars(make_repo) -> None:
    repo = make_repo({"package.json": json.dumps({"browserslist": ["x" * 500]})})

    _, _, config, _ = _scan(repo)

    value = config["cfg:package.json#browserslist.0"]["value"]
    assert len(value) == MAX_CONFIG_VALUE_CHARS


def test_tsconfig_comments_and_trailing_commas_are_accepted(angular_app) -> None:
    _, _, config, _ = _scan(angular_app)

    assert config["cfg:tsconfig.json#compilerOptions.strict"]["value"] == "true"
    assert config["cfg:tsconfig.json#compilerOptions.target"]["value"] == "ES2022"


def test_the_config_that_compiles_the_app_supplies_the_values(angular_app) -> None:
    """``angular.json`` names the app tsconfig, so that is the one that counts."""
    _, _, config, _ = _scan(angular_app)

    # ``tsconfig.json`` says ``./dist/out-tsc``; the app config overrides it.
    assert (
        config["cfg:tsconfig.json#compilerOptions.outDir"]["value"] == "./out-tsc/app"
    )
    assert config["cfg:tsconfig.json#compilerOptions.outDir"]["file"] == (
        "tsconfig.app.json"
    )
    # The app config sets ``types: []``, so the base config's ``types`` is gone:
    # one key, one value, no ambiguity about which compilation it describes.
    assert not [
        key
        for key in config
        if key.startswith("cfg:tsconfig.json#compilerOptions.types")
    ]


def test_a_tsconfig_option_is_emitted_once_per_module(angular_app) -> None:
    _, _, config, _ = _scan(angular_app)

    keys = [entry["key"] for entry in config.values() if "tsconfig" in entry["file"]]
    assert len(keys) == len(set(keys))


def test_the_path_map_comes_from_the_app_tsconfig(angular_app) -> None:
    facts = _read(angular_app)

    assert facts.path_map is not None
    assert facts.path_map.tsconfig == "tsconfig.app.json"
    assert facts.path_map.paths["@app/*"] == ("src/app/*",)
    assert facts.path_map.paths_dir == "."


def test_an_inherited_option_is_attributed_to_the_file_that_declared_it(
    make_repo,
) -> None:
    """A relative ``baseUrl`` means what it means in the file that declares it."""
    repo = make_repo(
        {
            "package.json": json.dumps({"workspaces": ["ui"]}),
            "tsconfig.base.json": json.dumps(
                {"compilerOptions": {"baseUrl": "./", "paths": {"@app/*": ["ui/*"]}}}
            ),
            "ui/package.json": json.dumps({"name": "@demo/ui"}),
            "ui/tsconfig.json": json.dumps(
                {"extends": "../tsconfig.base.json", "compilerOptions": {"outDir": "d"}}
            ),
        }
    )

    result, _, config, _ = _scan(repo)

    # Declared at the repo root, so ``./`` is the repo root even when the
    # config is read through ``ui/tsconfig.json``.
    assert config["cfg:tsconfig.json#compilerOptions.baseUrl"]["file"] == (
        "tsconfig.base.json"
    )
    assert config["cfg:tsconfig.json#compilerOptions.outDir"]["file"] == (
        "ui/tsconfig.json"
    )
    # The module's path map inherits the root-relative interpretation too.
    facts = _read_module(repo, "ui")
    assert facts.path_map is not None
    assert facts.path_map.base_url == "."
    assert facts.path_map.paths == {"@app/*": ("ui/*",)}
    assert result.profile.modules[1].path == "ui"


def test_tsconfig_extends_is_followed_inside_the_repo(make_repo) -> None:
    repo = make_repo(
        {
            "package.json": "{}",
            "tsconfig.base.json": json.dumps(
                {"compilerOptions": {"strict": True, "target": "ES2022"}}
            ),
            "tsconfig.json": json.dumps(
                {
                    "extends": "./tsconfig.base.json",
                    "compilerOptions": {"outDir": "dist"},
                }
            ),
        }
    )

    result, _, config, _ = _scan(repo)

    # A key inherited through ``extends`` and one set locally are both present.
    assert config["cfg:tsconfig.json#compilerOptions.strict"]["value"] == "true"
    assert config["cfg:tsconfig.json#compilerOptions.outDir"]["value"] == "dist"
    assert result.profile.diagnostics == []


def test_a_tsconfig_extends_outside_the_repo_is_a_diagnostic(make_repo) -> None:
    repo = make_repo(
        {
            "package.json": "{}",
            "tsconfig.json": json.dumps({"extends": "@tsconfig/node20/tsconfig.json"}),
        }
    )

    result, profile, _, _ = _scan(repo)

    assert [entry["kind"] for entry in profile["diagnostics"]] == [
        "tsconfig_extends_outside_repo"
    ]
    assert profile["diagnostics"][0]["detail"] == "@tsconfig/node20/tsconfig.json"
    assert result.summary.files_scanned == 2


def test_a_tsconfig_extends_cycle_is_a_diagnostic_not_a_crash(make_repo) -> None:
    repo = make_repo(
        {
            "package.json": "{}",
            "tsconfig.json": json.dumps({"extends": "./tsconfig.other.json"}),
            "tsconfig.other.json": json.dumps({"extends": "./tsconfig.json"}),
        }
    )

    result, profile, _, _ = _scan(repo)

    assert "tsconfig_cycle" in [entry["kind"] for entry in profile["diagnostics"]]
    assert result.profile.schema_version == 1


def test_the_effective_path_map_comes_from_the_config_that_declares_it(
    make_repo,
) -> None:
    repo = make_repo(
        {
            "package.json": "{}",
            "config/base.json": json.dumps(
                {"compilerOptions": {"paths": {"@app/*": ["../src/app/*"]}}}
            ),
            "tsconfig.json": json.dumps({"extends": "./config/base.json"}),
        }
    )

    facts = _read(repo)

    assert facts.path_map is not None
    assert facts.path_map.paths == {"@app/*": ("../src/app/*",)}
    # No ``baseUrl``: targets are relative to the config that declared them.
    assert facts.path_map.paths_dir == "config"


def test_a_relative_base_url_and_paths_come_from_the_effective_config(
    make_repo,
) -> None:
    repo = make_repo(
        {
            "package.json": "{}",
            "tsconfig.json": json.dumps(
                {
                    "compilerOptions": {
                        "baseUrl": "./",
                        "paths": {"@app/*": ["src/app/*"], "@shared": ["src/shared"]},
                    }
                }
            ),
        }
    )

    facts = _read(repo)

    assert facts.path_map is not None
    assert facts.path_map.base_url == "."
    assert facts.path_map.paths_dir == "."
    assert facts.path_map.paths["@shared"] == ("src/shared",)


def test_path_map_survives_a_missing_paths_key(make_repo) -> None:
    """``baseUrl`` alone is still a usable import root for spec3 / spec4."""
    repo = make_repo(
        {
            "package.json": "{}",
            "tsconfig.json": '{"compilerOptions": {"baseUrl": "src"}}',
        }
    )

    facts = _read(repo)

    assert facts.path_map is not None
    assert facts.path_map.base_url == "src"
    assert facts.path_map.paths == {}


# --- AC-8.2 npm workspace --------------------------------------------------


def test_npm_workspace_gives_three_modules(npm_workspace) -> None:
    _, profile, _, dependencies = _scan(npm_workspace)

    assert [module["path"] for module in profile["modules"]] == [
        ".",
        "packages/core",
        "packages/ui",
    ]


def test_workspace_package_names_are_own_packages(npm_workspace) -> None:
    _, profile, _, _ = _scan(npm_workspace)

    own = {module["path"]: module["own_packages"] for module in profile["modules"]}
    # The profile lists each module's own names: the root declares the
    # workspaces, every package its ``name``.
    assert own == {
        ".": ["@demo/core", "@demo/ui", "payments-frontend"],
        "packages/core": ["@demo/core"],
        "packages/ui": ["@demo/ui"],
    }


def test_extractors_get_the_repo_wide_own_packages(npm_workspace) -> None:
    """Any module may import a sibling package, so own-code detection is repo-scoped."""
    seen: dict[str, tuple[str, ...]] = {}

    def spy(context):
        seen[context.module] = context.env.own_packages
        return contract.FileFacts()

    contract.register_source_extractor("ts", spy)
    scan(npm_workspace, out=npm_workspace / "profile.json")

    assert seen["packages/core"] == ("@demo/core", "@demo/ui", "payments-frontend")


def test_each_workspace_module_keeps_its_own_dependencies(npm_workspace) -> None:
    _, _, _, dependencies = _scan(npm_workspace)

    # The installed version comes from the one lockfile at the workspace root.
    assert dependencies["npm:rxjs"]["module"] == "packages/core"
    assert dependencies["npm:rxjs"]["scope"] == "peerDependencies"
    assert dependencies["npm:rxjs"]["version"] == "7.8.1"
    assert dependencies["npm:@angular/core"]["module"] == "packages/ui"
    assert dependencies["npm:typescript"]["module"] == "."


def test_a_workspace_dependency_has_no_registry_version(npm_workspace) -> None:
    """``workspace:*`` is a local package, not a version to compare (FR-4)."""
    result, _, _, dependencies = _scan(npm_workspace)

    assert dependencies["npm:@demo/core"]["range"] == "workspace:*"
    assert dependencies["npm:@demo/core"]["version"] is None
    # Normal, not a diagnostic.
    assert [entry["kind"] for entry in result.profile.diagnostics] == []


def test_angular_is_detected_in_the_workspace_package_that_uses_it(
    npm_workspace,
) -> None:
    _, profile, _, _ = _scan(npm_workspace)

    frameworks = {
        module["path"]: [entry["name"] for entry in module["frameworks"]]
        for module in profile["modules"]
    }
    # Only ``packages/ui`` depends on Angular, and the repo-level framework is
    # still ``angular`` because one module found it (FR-3).
    assert frameworks == {
        ".": [],
        "packages/core": [],
        "packages/ui": ["angular"],
    }
    assert profile["framework"]["name"] == "angular"
    assert profile["framework"]["version"] == "19.2.0"


# --- AC-8.3 a broken manifest ----------------------------------------------


def test_a_broken_package_json_is_a_diagnostic_and_the_scan_continues(
    make_repo,
) -> None:
    repo = make_repo(
        {
            "package.json": '{"name": "demo", "dependencies": {',
            "tsconfig.json": json.dumps({"compilerOptions": {"strict": True}}),
            "src/a.ts": "const a = 1;\n",
        }
    )

    result, profile, config, _ = _scan(repo)

    assert [entry["kind"] for entry in profile["diagnostics"]] == ["invalid_json"]
    assert profile["diagnostics"][0]["file"] == "package.json"
    # Everything else the module declared is still read.
    assert config["cfg:tsconfig.json#compilerOptions.strict"]["value"] == "true"
    assert result.summary.files_scanned == 3


def test_a_broken_package_json_exits_zero(tmp_path) -> None:
    repo = tmp_path / "broken"
    write(repo, "package.json", "{ nope")
    write(repo, "src/a.ts", "const a = 1;\n")

    from .conftest import run_cli

    code, stdout, _ = run_cli(str(repo))

    assert code == 0
    assert "1 diagnostics" in stdout


def test_a_json_array_is_not_a_manifest(make_repo) -> None:
    repo = make_repo({"package.json": "[]", "tsconfig.json": "{}"})

    _, profile, _, _ = _scan(repo)

    assert [entry["kind"] for entry in profile["diagnostics"]] == ["invalid_json"]
    assert profile["diagnostics"][0]["detail"] == "not a JSON object"


# --- ranges ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("^19.2.0", "19.2.0"),
        ("~19.2.0", "19.2.0"),
        ("~1.4", "1.4.0"),
        (">=18", "18.0.0"),
        (">=18.19.0", "18.19.0"),
        ("=19.2.0", "19.2.0"),
        ("19.2.0", "19.2.0"),
        ("v19.2.0", "19.2.0"),
        ("19", "19.0.0"),
        ("19.x", "19.0.0"),
        (">1", "2.0.0"),
        (">1.2", "1.3.0"),
        (">1.2.x", "1.3.0"),
        (">1.2.3", "1.2.4"),
        ("*", None),
        ("", None),
        ("latest", None),
        ("workspace:*", None),
        ("file:../core", None),
        ("not a range", None),
    ],
)
def test_range_normalization(spec: str, expected: str | None) -> None:
    assert normalize_range(spec)[0] == expected


def test_range_normalization_reports_why_it_failed() -> None:
    assert normalize_range("^19.2.0")[1] == ""
    assert normalize_range("*")[1] == "wildcard"
    assert normalize_range("not a range")[1] == "unsupported"


def test_a_caret_range_keeps_the_lowest_allowed_version() -> None:
    """AC-8: the profile answers "which version could this be", so it takes the floor."""
    assert normalize_range("^19.2.0")[0] == "19.2.0"
    assert normalize_range("^19.2.0")[0] != "19.9.9"


def test_an_union_range_takes_the_lowest_alternative() -> None:
    assert normalize_range("^19.2.0 || ^20.0.0")[0] == "19.2.0"
    assert normalize_range("^20.0.0 || ^19.2.0")[0] == "19.2.0"


def test_an_unsupported_range_is_a_diagnostic(make_repo) -> None:
    repo = make_repo(
        {"package.json": json.dumps({"dependencies": {"left-pad": "not a range"}})}
    )

    _, profile, _, dependencies = _scan(repo)

    assert dependencies["npm:left-pad"]["version"] is None
    assert dependencies["npm:left-pad"]["range"] == "not a range"
    assert [entry["kind"] for entry in profile["diagnostics"]] == ["unsupported_range"]


def test_a_non_string_dependency_is_a_diagnostic(make_repo) -> None:
    repo = make_repo(
        {"package.json": json.dumps({"dependencies": {"weird": {"version": "1.0.0"}}})}
    )

    _, profile, _, dependencies = _scan(repo)

    assert dependencies == {}
    assert [entry["kind"] for entry in profile["diagnostics"]] == ["invalid_dependency"]


# --- JSONC -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"a": 1}', '{"a": 1}'),
        ('{"a": 1,}', '{"a": 1}'),
        ('{"a": [1, 2,],}', '{"a": [1, 2]}'),
        ('{\n  // note\n  "a": 1\n}', '{\n  \n  "a": 1\n}'),
        ('{"a": 1, // note\n}', '{"a": 1 \n}'),
        ('{"a": 1 /* note */,}', '{"a": 1 }'),
        # A ``//`` inside a string is data, not a comment.
        ('{"url": "https://example.test"}', '{"url": "https://example.test"}'),
        ('{"glob": "a,}"}', '{"glob": "a,}"}'),
    ],
)
def test_strip_jsonc(text: str, expected: str) -> None:
    assert strip_jsonc(text) == expected


def test_a_tsconfig_with_comments_still_parses(make_repo) -> None:
    repo = make_repo(
        {
            "package.json": "{}",
            "tsconfig.json": (
                "{\n"
                "  // a comment\n"
                '  "compilerOptions": {\n'
                '    "paths": { "@app/*": ["src/app/*"] }, /* trailing */\n'
                "  },\n"
                "}\n"
            ),
        }
    )

    result, _, config, _ = _scan(repo)

    assert config["cfg:tsconfig.json#compilerOptions.paths.@app/*.0"]["value"] == (
        "src/app/*"
    )
    assert [entry["kind"] for entry in result.profile.diagnostics] == []


# --- registration ----------------------------------------------------------


def test_the_npm_reader_handles_every_npm_manifest_kind() -> None:
    from migration_planner.scanner import builtin

    assert set(builtin.MANIFEST_READERS) == {
        "package.json",
        "package-lock.json",
        "angular.json",
        "tsconfig.json",
    }


def test_the_reader_runs_once_per_module_with_all_its_manifests(angular_app) -> None:
    calls: list[tuple[str, int]] = []
    from migration_planner.scanner.npm_manifests import read_npm_manifests

    def counting(context):
        calls.append((context.module, len(context.files)))
        return read_npm_manifests(context)

    for kind in ("package.json", "package-lock.json", "angular.json", "tsconfig.json"):
        contract.register_manifest_reader(kind, counting)
    scan(angular_app, out=angular_app / "profile.json")

    assert calls == [(".", 6)]


def test_a_module_without_any_manifest_gets_no_npm_facts(make_repo) -> None:
    repo = make_repo({"pom.xml": "<project/>", "src/main/java/A.java": "class A {}"})

    _, profile, _, _ = _scan(repo)

    assert profile["dependencies"] == []
    assert profile["config"] == []
    assert profile["framework"] is None


# --- helpers ---------------------------------------------------------------


def _read(repo):
    """Run the npm reader directly, to inspect the parts that never reach the profile."""
    return _read_module(repo, ".")


def _read_module(repo, module: str):
    from migration_planner.scanner.discover import discover
    from migration_planner.scanner.npm_manifests import read_npm_manifests
    from migration_planner.scanner.scan import _manifest_contexts

    contexts = _manifest_contexts(discover(repo))
    return read_npm_manifests(contexts[module])


# --- review fixes -------------------------------------------------------------


def _hoisted_workspace(make_repo, lock_dir: str = ""):
    prefix = f"{lock_dir}/" if lock_dir else ""
    files = {
        f"{prefix}package.json": json.dumps(
            {"name": "root", "private": True, "workspaces": ["packages/*"]}
        ),
        f"{prefix}packages/ui/package.json": json.dumps(
            {"name": "@demo/ui", "dependencies": {"@angular/core": "^19.0.0"}}
        ),
        f"{prefix}packages/server/package.json": json.dumps(
            {"name": "@demo/server", "dependencies": {"express": "^4.0.0"}}
        ),
        f"{prefix}package-lock.json": json.dumps(
            {
                "lockfileVersion": 3,
                "packages": {
                    "node_modules/@angular/core": {"version": "19.2.4"},
                    "node_modules/express": {"version": "4.21.0"},
                },
            }
        ),
    }
    if lock_dir:
        files["backend/pom.xml"] = "<project/>\n"
    return make_repo(files)


def test_a_hoisted_angular_does_not_make_a_sibling_an_angular_module(make_repo) -> None:
    """Only a module that declares ``@angular/core`` is Angular; the lockfile gives the version."""
    repo = _hoisted_workspace(make_repo)

    _, profile, _, _ = _scan(repo)

    frameworks = {
        module["path"]: [
            (entry["name"], entry["version"]) for entry in module["frameworks"]
        ]
        for module in profile["modules"]
    }
    assert frameworks == {
        ".": [],
        "packages/server": [],
        "packages/ui": [("angular", "19.2.4")],
    }


def test_the_lockfile_of_a_nested_workspace_root_is_found(make_repo) -> None:
    """``frontend/package-lock.json`` serves ``frontend/packages/ui``, not only the scan root."""
    repo = _hoisted_workspace(make_repo, lock_dir="frontend")

    _, profile, _, dependencies = _scan(repo)

    ui = next(m for m in profile["modules"] if m["path"] == "frontend/packages/ui")
    assert ui["frameworks"][0]["version"] == "19.2.4"
    assert ui["frameworks"][0]["source"] == "package-lock.json"
    assert dependencies["npm:express"]["version"] == "4.21.0"
    assert dependencies["npm:express"]["version_source"] == "lockfile"
    backend = next(m for m in profile["modules"] if m["path"] == "backend")
    assert backend["own_packages"] == []


def test_a_lockfile_over_two_megabytes_is_still_read(make_repo) -> None:
    packages = {"node_modules/@angular/core": {"version": "19.2.4"}}
    packages.update(
        {
            f"node_modules/pkg{index}": {
                "version": "1.0.0",
                "integrity": "sha512-" + "a" * 200,
            }
            for index in range(12000)
        }
    )
    repo = make_repo(
        {
            "package.json": json.dumps({"dependencies": {"@angular/core": "^19.0.0"}}),
            "package-lock.json": json.dumps(
                {"lockfileVersion": 3, "packages": packages}
            ),
        }
    )
    assert (repo / "package-lock.json").stat().st_size > 2 * 1024 * 1024

    _, profile, _, _ = _scan(repo)

    assert profile["framework"]["version"] == "19.2.4"
    assert not [d for d in profile["diagnostics"] if d["kind"] == "file_too_large"]


def test_version_source_says_lockfile_or_range(make_repo) -> None:
    repo = make_repo(
        {
            "package.json": json.dumps(
                {
                    "dependencies": {
                        "rxjs": "^7.8.0",
                        "zone.js": "~0.15.0",
                        "local": "file:../x",
                    }
                }
            ),
            "package-lock.json": json.dumps(
                {
                    "lockfileVersion": 3,
                    "packages": {"node_modules/rxjs": {"version": "7.8.1"}},
                }
            ),
        }
    )

    _, _, _, dependencies = _scan(repo)

    assert (
        dependencies["npm:rxjs"]["version"],
        dependencies["npm:rxjs"]["version_source"],
    ) == (
        "7.8.1",
        "lockfile",
    )
    assert (
        dependencies["npm:zone.js"]["version"],
        dependencies["npm:zone.js"]["version_source"],
    ) == ("0.15.0", "range")
    assert dependencies["npm:local"]["version"] is None
    assert dependencies["npm:local"]["version_source"] is None


def test_angular_json_targets_pick_the_tsconfig_in_declaration_order(make_repo) -> None:
    """The build target's config wins even when a later target's name sorts first."""
    repo = make_repo(
        {
            "package.json": json.dumps({"dependencies": {"@angular/core": "^19.0.0"}}),
            "angular.json": json.dumps(
                {
                    "projects": {
                        "app": {
                            "architect": {
                                "build": {"options": {"tsConfig": "tsconfig.web.json"}},
                                "test": {"options": {"tsConfig": "tsconfig.e2e.json"}},
                            }
                        }
                    }
                }
            ),
            "tsconfig.json": json.dumps({"compilerOptions": {"target": "ES2020"}}),
            "tsconfig.web.json": json.dumps(
                {"extends": "./tsconfig.json", "compilerOptions": {"strict": True}}
            ),
            "tsconfig.e2e.json": json.dumps(
                {"extends": "./tsconfig.json", "compilerOptions": {"strict": False}}
            ),
        }
    )

    _, _, config, _ = _scan(repo)

    strict = config["cfg:tsconfig.json#compilerOptions.strict"]
    assert (strict["value"], strict["file"]) == ("true", "tsconfig.web.json")
