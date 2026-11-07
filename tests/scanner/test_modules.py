"""Modules and framework choice (spec 026 AC-1.3, FR-3)."""

from __future__ import annotations

from migration_planner.scanner.discover import discover
from migration_planner.scanner.profile import FrameworkInfo, choose_framework


def test_three_modules_from_three_manifest_families(polyglot_repo) -> None:
    result = discover(polyglot_repo)

    assert [module.path for module in result.modules] == [".", "backend", "tools"]
    manifests = {module.path: list(module.manifests) for module in result.modules}
    assert manifests["."] == ["package.json", "tsconfig.json"]
    # Every manifest of the module is listed, relative to the module root (FR-3).
    assert manifests["backend"] == ["pom.xml", "src/main/resources/application.yml"]
    assert manifests["tools"] == ["build.gradle.kts"]


def test_each_source_file_belongs_to_its_nearest_module_root(polyglot_repo) -> None:
    result = discover(polyglot_repo)
    by_module: dict[str, list[str]] = {}
    for file in result.files:
        by_module.setdefault(file.module, []).append(file.relative)

    assert sorted(by_module["."]) == [
        "package.json",
        "src/app/app.component.spec.ts",
        "src/app/app.component.ts",
        "tsconfig.json",
    ]
    assert "backend/src/main/java/com/example/BackendApp.java" in by_module["backend"]
    assert "backend/src/main/resources/application.yml" in by_module["backend"]
    assert "tools/src/main/java/com/example/tools/ToolMain.java" in by_module["tools"]


def test_a_repo_without_a_module_root_still_gets_one_module(make_repo) -> None:
    repo = make_repo({"tsconfig.json": "{}\n", "src/a.ts": "const a = 1;\n"})

    result = discover(repo)

    assert [module.path for module in result.modules] == ["."]


def test_nested_module_roots_pick_the_deepest(make_repo) -> None:
    repo = make_repo(
        {
            "package.json": "{}\n",
            "packages/ui/package.json": "{}\n",
            "packages/ui/src/button.ts": "const b = 1;\n",
            "packages/ui/nested/package.json": "{}\n",
            "packages/ui/nested/src/deep.ts": "const d = 1;\n",
            "docs/example.ts": "const e = 1;\n",
        }
    )

    result = discover(repo)
    owners = {file.relative: file.module for file in result.files}

    assert [module.path for module in result.modules] == [
        ".",
        "packages/ui",
        "packages/ui/nested",
    ]
    assert owners["packages/ui/src/button.ts"] == "packages/ui"
    assert owners["packages/ui/nested/src/deep.ts"] == "packages/ui/nested"
    assert owners["docs/example.ts"] == "."


def test_module_for_falls_back_to_the_root(polyglot_repo) -> None:
    result = discover(polyglot_repo)

    assert result.module_for("src/app/app.component.ts").path == "."


def test_manifest_names_in_modules_are_relative_to_the_module(polyglot_repo) -> None:
    result = discover(polyglot_repo)
    backend = next(module for module in result.modules if module.path == "backend")

    assert backend.manifests == ("pom.xml", "src/main/resources/application.yml")
    assert backend.absolute == polyglot_repo / "backend"


def test_framework_is_the_one_found_in_most_modules() -> None:
    angular = FrameworkInfo(name="angular", version="19.2.0")
    spring = FrameworkInfo(name="spring-boot", version="3.5.0")

    chosen, diagnostics = choose_framework(
        {".": [angular], "backend": [spring], "tools": [spring]}
    )

    assert chosen == spring
    assert diagnostics == []


def test_framework_tie_is_listed_in_diagnostics() -> None:
    angular = FrameworkInfo(name="angular", version="19.2.0")
    spring = FrameworkInfo(name="spring-boot", version="3.5.0")

    chosen, diagnostics = choose_framework({".": [angular], "backend": [spring]})

    # Deterministic tie-break by name; the ambiguity is reported, not hidden.
    assert chosen == angular
    assert [diagnostic.kind for diagnostic in diagnostics] == ["framework_tie"]
    assert "angular" in diagnostics[0].detail
    assert "spring-boot" in diagnostics[0].detail


def test_a_module_with_two_detections_of_one_framework_counts_once() -> None:
    one = FrameworkInfo(name="angular", version="19.2.0")
    two = FrameworkInfo(name="angular", version="19.2.0", source="package.json")

    chosen, diagnostics = choose_framework({".": [one, two], "ui": [one]})

    assert chosen == one
    assert diagnostics == []


def test_no_framework_at_all() -> None:
    chosen, diagnostics = choose_framework({".": []})

    assert chosen is None
    assert diagnostics == []


def test_files_under_no_module_root_get_a_root_module(make_repo) -> None:
    """A root ``tsconfig.json`` / shared ``config/application.properties`` is never dropped."""
    from migration_planner.scanner.discover import discover

    repo = make_repo(
        {
            "svc/pom.xml": "<project/>\n",
            "svc/src/main/java/com/x/A.java": "package com.x; class A {}\n",
            "config/application.properties": "spring.x=1\n",
            "tsconfig.json": "{}\n",
        }
    )

    result = discover(repo)

    modules = {module.path: module.manifests for module in result.modules}
    assert set(modules) == {".", "svc"}
    assert modules["."] == ("config/application.properties", "tsconfig.json")
    assert modules["svc"] == ("pom.xml",)


def test_no_root_module_when_every_file_has_a_root(make_repo) -> None:
    from migration_planner.scanner.discover import discover

    repo = make_repo(
        {
            "README.md": "not scanned\n",
            "svc/pom.xml": "<project/>\n",
            "svc/src/main/java/com/x/A.java": "package com.x; class A {}\n",
        }
    )

    assert [module.path for module in discover(repo).modules] == ["svc"]
