"""Import specifiers: external package keys vs the repo's own code (026 FR-5).

These rules decide what the scanner records, and 025 uses the same package split
for canonical keys, so the two are tested together and without the pipeline.
"""

from __future__ import annotations

import pytest

from migration_keys.specifiers import (
    dependency_name,
    is_node_builtin,
    is_own_code,
    is_relative_specifier,
    matches_path_alias,
    package_of_specifier,
    resolve_path_alias,
)


@pytest.mark.parametrize(
    ("specifier", "expected"),
    [
        ("@angular/core", "@angular/core"),
        # An Angular entry point is its own package (025 FR-1).
        ("@angular/core/testing", "@angular/core/testing"),
        ("@angular/core/rxjs-interop", "@angular/core/rxjs-interop"),
        # An unscoped deep import is kept as written.
        ("rxjs/internal/operators/map", "rxjs/internal/operators/map"),
        ("rxjs", "rxjs"),
        # A deep file import is kept as written too (spec3 FR-5).
        ("lodash/fp.js", "lodash/fp.js"),
        ("some-pkg/dist/index.mjs", "some-pkg/dist/index.mjs"),
    ],
)
def test_package_of_specifier(specifier: str, expected: str) -> None:
    assert package_of_specifier(specifier) == expected


@pytest.mark.parametrize(
    ("specifier", "expected"),
    [
        ("@angular/core/testing", "@angular/core"),
        ("@angular/core", "@angular/core"),
        ("rxjs/internal/x", "rxjs"),
        ("single", "single"),
    ],
)
def test_dependency_name_is_the_installable_package(
    specifier: str, expected: str
) -> None:
    assert dependency_name(specifier) == expected


@pytest.mark.parametrize(
    "specifier", ["./x", "../y", ".", "..", "/abs/path", "./deep/thing.ts"]
)
def test_relative_specifiers(specifier: str) -> None:
    assert is_relative_specifier(specifier) is True


@pytest.mark.parametrize("specifier", ["pkg", "@scope/pkg", "@app/x"])
def test_non_relative_specifiers(specifier: str) -> None:
    assert is_relative_specifier(specifier) is False


@pytest.mark.parametrize("specifier", ["node:fs", "node:crypto", "fs", "path", "os"])
def test_node_builtins(specifier: str) -> None:
    assert is_node_builtin(specifier) is True


@pytest.mark.parametrize("specifier", ["fs-extra", "@types/node", "path-to-regexp"])
def test_packages_that_look_like_builtins(specifier: str) -> None:
    assert is_node_builtin(specifier) is False


def test_own_code_covers_relative_aliases_and_workspace_packages() -> None:
    assert is_own_code("./x") is True
    assert is_own_code("@app/core", path_aliases=["@app/*"]) is True
    assert is_own_code("@demo/ui", own_packages=["@demo/ui"]) is True
    assert (
        is_own_code("@angular/core", path_aliases=["@app/*"], own_packages=["@demo"])
        is False
    )


def test_a_node_builtin_is_not_own_code_but_is_also_not_external() -> None:
    """It is a third thing: the caller skips it without counting an own import."""
    assert is_own_code("fs") is True
    assert is_own_code("node:fs") is True


def test_path_alias_matching() -> None:
    assert matches_path_alias("@app/core", ["@app/*"]) is True
    assert matches_path_alias("@app/core/deep/x", ["@app/*"]) is True
    assert matches_path_alias("@shared", ["@shared"]) is True
    # An exact key does not match a child path.
    assert matches_path_alias("@shared/child", ["@shared"]) is False
    assert matches_path_alias("@app", ["@app/*"]) is False
    assert matches_path_alias("@other/x", ["@app/*"]) is False


def test_specificity_is_not_confused_by_a_shorter_pattern() -> None:
    assert matches_path_alias("@app/core/x", ["@app/*", "@app/core/*"]) is True


def test_resolve_path_alias_substitutes_the_star() -> None:
    assert resolve_path_alias("@app/core", {"@app/*": ["src/app/*"]}) == [
        "src/app/core"
    ]


def test_resolve_path_alias_prefers_the_longest_pattern() -> None:
    assert resolve_path_alias(
        "@app/core/x",
        {"@app/*": ["src/app/*"], "@app/core/*": ["src/core/*"]},
    ) == ["src/core/x"]


def test_resolve_path_alias_keeps_the_target_order() -> None:
    """TypeScript tries the targets in order and takes the first that exists."""
    assert resolve_path_alias(
        "@app/core", {"@app/*": ["generated/*", "src/app/*"]}
    ) == ["generated/core", "src/app/core"]


def test_resolve_path_alias_honours_paths_dir() -> None:
    assert resolve_path_alias("@app/core", {"@app/*": ["app/*"]}, paths_dir="src") == [
        "src/app/core"
    ]


def test_resolve_path_alias_returns_nothing_for_an_unknown_specifier() -> None:
    assert resolve_path_alias("@nope/x", {"@app/*": ["src/app/*"]}) == []


def test_resolve_path_alias_normalizes_dot_segments() -> None:
    # ``..`` with nothing above it stays, so a target outside the scan root is
    # visible rather than silently clamped.
    assert resolve_path_alias("../x", {"../*": ["../shared/*"]}, paths_dir=".") == [
        "../shared/x"
    ]
    assert resolve_path_alias(
        "@app/core", {"@app/*": ["src/./app/../app/*"]}, paths_dir="."
    ) == ["src/app/core"]


def test_a_declared_dependency_is_not_a_builtin() -> None:
    assert is_node_builtin("events") is True
    assert is_node_builtin("events", declared_dependencies=["events"]) is False
    assert is_node_builtin("node:events", declared_dependencies=["events"]) is True


def test_base_url_roots_make_own_code() -> None:
    assert is_own_code("app/core/x", base_url_roots=["app"]) is True
    assert is_own_code("rxjs", base_url_roots=["app"]) is False
    assert (
        is_own_code("app", base_url_roots=["app"], declared_dependencies=["app"])
        is False
    )
