"""Discovery (spec 026 AC-1.2, FR-2) and test-file handling (FR-1)."""

from __future__ import annotations

from pathlib import Path

from migration_planner.scanner.discover import (
    MAX_FILE_BYTES,
    MAX_JS_FIRST_LINE,
    classify_manifest,
    classify_source,
    discover,
    is_test_path,
)

from .conftest import write


def _relatives(result) -> list[str]:
    return [file.relative for file in result.files]


def test_git_mode_respects_gitignore(git_repo) -> None:
    repo = git_repo(
        {
            "package.json": "{}\n",
            "src/app.ts": "const a = 1;\n",
            "ignored.ts": "const b = 2;\n",
        }
    )

    result = discover(repo)

    assert result.used_git is True
    assert "src/app.ts" in _relatives(result)
    assert "ignored.ts" not in _relatives(result)


def test_git_mode_scans_tracked_files_that_match_gitignore(git_repo) -> None:
    """``git ls-files --cached`` lists committed files even when ignored later."""
    from .conftest import git

    repo = git_repo({"package.json": "{}\n", "src/app.ts": "const a = 1;\n"})
    write(repo, ".gitignore", ".migration/\n")
    write(repo, "src/committed.ts", "const c = 3;\n")
    git(repo, "add", "-f", "src/committed.ts")
    write(repo, ".gitignore", ".migration/\nsrc/committed.ts\n")

    assert "src/committed.ts" in _relatives(discover(repo))


def test_walk_mode_gives_the_same_file_set_as_git(git_repo, tmp_path: Path) -> None:
    files = {
        "package.json": "{}\n",
        "tsconfig.json": "{}\n",
        "src/app.ts": "const a = 1;\n",
        "src/app.html": "<div></div>\n",
        "ignored.ts": "const b = 2;\n",
        "scratch.log": "noise\n",
    }
    repo = git_repo(files)
    # The same tree outside a work tree: copy without .git.
    plain = tmp_path / "plain"
    for relative in files:
        write(plain, relative, files[relative])
    write(plain, ".gitignore", "ignored.ts\nnode_modules/\n")

    git_files = _relatives(discover(repo))
    walk_files = _relatives(discover(plain))

    assert discover(plain).used_git is False
    assert walk_files == git_files


def test_skipped_directories_are_never_entered(make_repo) -> None:
    repo = make_repo(
        {
            "package.json": "{}\n",
            "src/app.ts": "const a = 1;\n",
            "node_modules/left-pad/index.js": "module.exports = 1;\n",
            "dist/bundle.js": "console.log(1);\n",
            "build/out.js": "console.log(1);\n",
            "target/generated.ts": "const t = 1;\n",
            "out/generated.ts": "const t = 1;\n",
            ".angular/cache.js": "var x = 1;\n",
            ".gradle/file.ts": "const g = 1;\n",
            ".migration/profile.json": "{}",
            "sub/node_modules/nested.js": "module.exports = 2;\n",
        }
    )

    relatives = _relatives(discover(repo))

    assert relatives == ["package.json", "src/app.ts"]


def test_oversized_file_is_skipped_and_counted(make_repo) -> None:
    repo = make_repo({"package.json": "{}\n"})
    write(repo, "src/huge.ts", b"x" * (MAX_FILE_BYTES + 1))

    result = discover(repo)

    assert "src/huge.ts" not in _relatives(result)
    assert result.skipped == 1
    assert [
        (diagnostic.kind, diagnostic.file) for diagnostic in result.diagnostics
    ] == [("file_too_large", "src/huge.ts")]


def test_minified_and_generated_js_are_skipped_and_counted(make_repo) -> None:
    repo = make_repo(
        {
            "package.json": "{}\n",
            "src/app.min.js": "var a=1;\n",
            "src/generated.js": "var " + "x" * MAX_JS_FIRST_LINE + " = 1;\n",
            "src/normal.js": "const a = 1;\n",
        }
    )

    result = discover(repo)

    relatives = _relatives(result)
    assert "src/app.min.js" not in relatives
    assert "src/generated.js" not in relatives
    assert "src/normal.js" in relatives
    assert result.skipped == 2
    assert {diagnostic.kind for diagnostic in result.diagnostics} == {"generated_js"}


def test_no_include_tests_drops_test_files(make_repo) -> None:
    repo = make_repo(
        {
            "package.json": "{}\n",
            "src/app.ts": "const a = 1;\n",
            "src/app.spec.ts": "describe('x', () => {});\n",
            "src/app.test.ts": "it('x', () => {});\n",
            "src/test/java/com/example/AppTest.java": "class AppTest {}\n",
            "src/test/setup.ts": "export {};\n",
        }
    )

    with_tests = discover(repo)
    without_tests = discover(repo, include_tests=False)

    assert "src/app.spec.ts" in _relatives(with_tests)
    assert "src/test/java/com/example/AppTest.java" in _relatives(with_tests)
    assert _relatives(without_tests) == ["package.json", "src/app.ts"]
    # Tests are included by default and flagged, not silently merged (FR-1).
    flag = {file.relative: file.test for file in with_tests.files}
    assert flag["src/app.spec.ts"] is True
    assert flag["src/app.ts"] is False


def test_files_are_classified_as_manifest_or_source(make_repo) -> None:
    repo = make_repo(
        {
            "package.json": "{}\n",
            "package-lock.json": "{}\n",
            "angular.json": "{}\n",
            "tsconfig.app.json": "{}\n",
            "pom.xml": "<project/>\n",
            "build.gradle": "\n",
            "build.gradle.kts": "\n",
            "settings.gradle": "\n",
            "gradle/libs.versions.toml": "\n",
            "gradle.properties": "\n",
            "application.properties": "\n",
            "bootstrap.yml": "\n",
            "src/app.ts": "\n",
            "src/app.tsx": "\n",
            "src/app.js": "\n",
            "src/app.jsx": "\n",
            "src/app.mjs": "\n",
            "src/app.cjs": "\n",
            "src/app.html": "\n",
            "src/App.java": "\n",
            "README.md": "# no\n",
            "src/styles.css": "\n",
        }
    )

    result = discover(repo)
    classified = {file.relative: file.classification for file in result.files}

    assert classified["package.json"] == "manifest:package.json"
    assert classified["package-lock.json"] == "manifest:package-lock.json"
    assert classified["angular.json"] == "manifest:angular.json"
    assert classified["tsconfig.app.json"] == "manifest:tsconfig.json"
    assert classified["pom.xml"] == "manifest:pom.xml"
    assert classified["build.gradle.kts"] == "manifest:build.gradle.kts"
    assert classified["application.properties"] == "manifest:spring.config"
    assert classified["src/app.tsx"] == "source:tsx"
    assert classified["src/app.mjs"] == "source:mjs"
    assert classified["src/app.html"] == "source:html"
    assert classified["src/App.java"] == "source:java"
    # Anything else is ignored, so later specs only register their own kind.
    assert "README.md" not in classified
    assert "src/styles.css" not in classified


def test_classifiers_directly() -> None:
    assert classify_manifest("tsconfig.spec.json") == "tsconfig.json"
    assert classify_manifest("application-prod.yml") == "spring.config"
    assert classify_manifest("bootstrap.yaml") == "spring.config"
    assert classify_manifest("settings.gradle.kts") == "settings.gradle"
    assert classify_manifest("notes.md") is None
    assert classify_source("a.TS") == "ts"
    assert classify_source("a.md") is None
    assert is_test_path("src/a.spec.ts") is True
    assert is_test_path("src/a.test.tsx") is True
    assert is_test_path("src/test/java/A.java") is True
    assert is_test_path("src/main/java/A.java") is False


def test_unreadable_file_becomes_a_diagnostic(make_repo) -> None:
    repo = make_repo({"package.json": "{}\n", "src/app.ts": "const a = 1;\n"})
    (repo / "src" / "app.ts").chmod(0o000)

    from migration_planner.scanner.scan import scan

    result = scan(repo)
    (repo / "src" / "app.ts").chmod(0o644)

    kinds = [entry.kind for entry in result.profile.diagnostics]
    assert "unreadable_file" in kinds


def test_scan_of_a_missing_path_discovers_nothing(tmp_path: Path) -> None:
    result = discover(tmp_path / "nope")

    assert result.files == []
    assert result.has_supported_manifest is False


def test_build_output_names_inside_src_are_not_skipped(make_repo) -> None:
    """``build`` / ``out`` / ``target`` / ``dist`` under ``src/`` are packages, not output."""
    repo = make_repo(
        {
            "pom.xml": "<project/>\n",
            "src/main/java/com/x/build/A.java": "package com.x.build; class A {}\n",
            "src/main/java/com/x/target/B.java": "package com.x.target; class B {}\n",
            "src/app/out/c.ts": "const c = 1;\n",
            "src/app/dist/d.ts": "const d = 1;\n",
            "target/classes/Gen.java": "class Gen {}\n",
            "src/node_modules/x.js": "module.exports = 1;\n",
        }
    )

    relatives = _relatives(discover(repo))

    assert "src/main/java/com/x/build/A.java" in relatives
    assert "src/main/java/com/x/target/B.java" in relatives
    assert "src/app/out/c.ts" in relatives
    assert "src/app/dist/d.ts" in relatives
    assert "target/classes/Gen.java" not in relatives
    assert "src/node_modules/x.js" not in relatives


def test_build_output_inside_src_is_kept_in_git_mode_too(git_repo) -> None:
    repo = git_repo(
        {
            "pom.xml": "<project/>\n",
            "src/main/java/com/x/build/A.java": "package com.x.build; class A {}\n",
        }
    )

    assert "src/main/java/com/x/build/A.java" in _relatives(discover(repo))


def test_walk_mode_applies_every_ancestor_gitignore(make_repo) -> None:
    """``a/.gitignore`` also ignores matching files in ``a/b/`` (walk mode, no git)."""
    repo = make_repo(
        {
            "package.json": "{}\n",
            "a/.gitignore": "*.gen.ts\n",
            "a/b/x.gen.ts": "const x = 1;\n",
            "a/b/y.ts": "const y = 1;\n",
            "c/z.gen.ts": "const z = 1;\n",
        }
    )

    result = discover(repo)

    assert result.used_git is False
    relatives = _relatives(result)
    assert "a/b/x.gen.ts" not in relatives
    assert "a/b/y.ts" in relatives
    assert "c/z.gen.ts" in relatives


def test_a_manifest_over_two_megabytes_is_not_skipped(make_repo) -> None:
    """Lockfiles are routinely > 2 MB; only sources get the 2 MB cap (FR-2)."""
    repo = make_repo(
        {
            "package.json": "{}\n",
            "package-lock.json": b"{" + b" " * (MAX_FILE_BYTES + 1) + b"}",
        }
    )

    result = discover(repo)

    assert "package-lock.json" in _relatives(result)
    assert not [d for d in result.diagnostics if d.kind == "file_too_large"]
