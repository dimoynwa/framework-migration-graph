"""Unit tests for the Python-canonical Spring Boot scanner (T045).

Validates:
- Python canonical extractor produces the correct entity list from a Java fixture directory
- allow-list filters non-matching imports
- PyYAML absent does not abort the scan (extractorPath="python" still returned)
- PyYAML auto-install is attempted when import fails
- scanner output is identical on macOS-BSD and GNU-Linux paths (fixture-based, not platform-conditional)
"""
from __future__ import annotations

import textwrap
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _write_java(tmp_path: Path, filename: str, content: str) -> None:
    dest = tmp_path / "src" / "main" / "java"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / filename).write_text(textwrap.dedent(content))


def _write_test_java(tmp_path: Path, filename: str, content: str) -> None:
    dest = tmp_path / "src" / "test" / "java"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / filename).write_text(textwrap.dedent(content))


def _write_resources(tmp_path: Path, filename: str, content: str) -> None:
    dest = tmp_path / "src" / "main" / "resources"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / filename).write_text(textwrap.dedent(content))


def _write_pom(tmp_path: Path, content: str) -> None:
    (tmp_path / "pom.xml").write_text(textwrap.dedent(content))


def _load_scanner() -> ModuleType:
    """Import the framework_scanner module from the skills directory."""
    skills_dir = (
        Path(__file__).parent.parent.parent
        / "migration_oracle"
        / "mcp"
        / "skills"
    )
    skill_file = skills_dir / "framework_scanner.py"
    import importlib.util

    spec = importlib.util.spec_from_file_location("framework_scanner", skill_file)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _scan(project_root: str) -> dict:
    mod = _load_scanner()
    result = mod.scan(project_root)
    return {
        "entities": result.entities,
        "testEntities": result.test_entities,
        "extractorPath": result.extractor_path,
        "warnings": result.warnings,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestJavaImportExtraction:
    def test_spring_import_included(self, tmp_path):
        _write_java(tmp_path, "App.java", """\
            import org.springframework.boot.autoconfigure.SpringBootApplication;
            public class App {}
        """)
        result = _scan(str(tmp_path))
        assert 'org.springframework.boot.autoconfigure.SpringBootApplication' in result['entities']
        assert result['extractorPath'] == 'python'

    def test_non_framework_import_excluded(self, tmp_path):
        _write_java(tmp_path, "Svc.java", """\
            import com.acme.internal.MyService;
            import java.util.List;
            import org.springframework.stereotype.Service;
        """)
        result = _scan(str(tmp_path))
        entities = result['entities']
        assert 'com.acme.internal.MyService' not in entities
        assert 'java.util.List' not in entities
        assert 'org.springframework.stereotype.Service' in entities

    def test_static_import_stripped(self, tmp_path):
        _write_java(tmp_path, "Util.java", """\
            import static org.springframework.test.web.servlet.MockMvcBuilders.standaloneSetup;
        """)
        result = _scan(str(tmp_path))
        assert 'org.springframework.test.web.servlet.MockMvcBuilders.standaloneSetup' in result['entities']

    def test_test_scope_separated(self, tmp_path):
        _write_test_java(tmp_path, "AppTest.java", """\
            import org.springframework.boot.test.context.SpringBootTest;
            import org.junit.jupiter.api.Test;
        """)
        result = _scan(str(tmp_path))
        assert 'org.springframework.boot.test.context.SpringBootTest' in result['testEntities']
        assert 'org.springframework.boot.test.context.SpringBootTest' not in result['entities']


class TestAnnotationExtraction:
    def test_annotation_simple_name_no_at(self, tmp_path):
        _write_java(tmp_path, "Ctrl.java", """\
            @RestController
            @RequestMapping("/api")
            public class Ctrl {}
        """)
        result = _scan(str(tmp_path))
        assert 'RestController' in result['entities']
        assert 'RequestMapping' in result['entities']

    def test_noise_annotations_excluded(self, tmp_path):
        _write_java(tmp_path, "Bean.java", """\
            @Override
            @Data
            @Slf4j
            public class Bean {}
        """)
        result = _scan(str(tmp_path))
        assert 'Override' not in result['entities']
        assert 'Data' not in result['entities']
        assert 'Slf4j' not in result['entities']


class TestMavenDependencyExtraction:
    def test_spring_dep_included(self, tmp_path):
        _write_pom(tmp_path, """\
            <project xmlns="http://maven.apache.org/POM/4.0.0">
              <dependencies>
                <dependency>
                  <groupId>org.springframework.boot</groupId>
                  <artifactId>spring-boot-starter-security</artifactId>
                  <version>3.3.0</version>
                </dependency>
                <dependency>
                  <groupId>com.example</groupId>
                  <artifactId>not-tracked</artifactId>
                </dependency>
              </dependencies>
            </project>
        """)
        result = _scan(str(tmp_path))
        assert 'org.springframework.boot:spring-boot-starter-security' in result['entities']
        assert 'com.example:not-tracked' not in result['entities']

    def test_target_dir_poms_skipped(self, tmp_path):
        target = tmp_path / "target"
        target.mkdir()
        (target / "pom.xml").write_text("""\
            <project xmlns="http://maven.apache.org/POM/4.0.0">
              <dependencies>
                <dependency>
                  <groupId>org.springframework.boot</groupId>
                  <artifactId>spring-boot-autoconfigure</artifactId>
                </dependency>
              </dependencies>
            </project>
        """)
        result = _scan(str(tmp_path))
        assert 'org.springframework.boot:spring-boot-autoconfigure' not in result['entities']


class TestPyYamlDegrade:
    def test_scan_succeeds_when_pyyaml_unavailable(self, tmp_path):
        """PyYAML unavailable does not abort the scan; extractorPath='python' still returned."""
        _write_java(tmp_path, "App.java", """\
            import org.springframework.stereotype.Component;
        """)
        _write_resources(tmp_path, "application.yml", "spring:\n  datasource:\n    url: jdbc:h2\n")

        mod = _load_scanner()
        with patch.object(mod, "_ensure_pyyaml", return_value=None):
            result = mod.scan(str(tmp_path))

        assert result.extractor_path == "python"
        assert "org.springframework.stereotype.Component" in result.entities
        assert any("PyYAML unavailable" in w for w in result.warnings)

    def test_ensure_pyyaml_installs_when_import_fails(self):
        mod = _load_scanner()
        mock_yaml = MagicMock()
        yaml_calls = 0
        original_import = __import__

        def fake_import(name, *args, **kwargs):
            nonlocal yaml_calls
            if name == "yaml":
                yaml_calls += 1
                if yaml_calls == 1:
                    raise ImportError("No module named 'yaml'")
                return mock_yaml
            return original_import(name, *args, **kwargs)

        with patch("subprocess.check_call") as pip_install:
            with patch("builtins.__import__", side_effect=fake_import):
                got = mod._ensure_pyyaml()

        pip_install.assert_called_once()
        assert got is mock_yaml

    def test_yaml_keys_extracted_when_pyyaml_present(self, tmp_path):
        _write_resources(tmp_path, "application.yml", "spring:\n  datasource:\n    url: jdbc:h2\n")
        result = _scan(str(tmp_path))
        assert "spring.datasource.url" in result["entities"]

    def test_properties_file_parsed_without_pyyaml(self, tmp_path):
        """Even without PyYAML, .properties keys are extracted."""
        _write_resources(tmp_path, "application.properties",
                         "spring.datasource.url=jdbc:h2\nspring.jpa.hibernate.ddl-auto=update\n")
        result = _scan(str(tmp_path))
        assert 'spring.datasource.url' in result['entities']
        assert 'spring.jpa.hibernate.ddl-auto' in result['entities']


class TestExtractorPathField:
    def test_extractor_path_always_present(self, tmp_path):
        result = _scan(str(tmp_path))
        assert 'extractorPath' in result
        assert result['extractorPath'] == 'python'

    def test_extractor_path_on_empty_project(self, tmp_path):
        result = _scan(str(tmp_path))
        assert result['extractorPath'] == 'python'
        assert result['entities'] == []


class TestFixtureBasedCrossplatform:
    """Verify scanner output is identical across macOS-BSD and GNU-Linux paths.

    These tests use pure Python fixture files — no platform-conditional logic.
    The same result is expected regardless of the underlying OS.
    """

    def test_same_output_regardless_of_platform(self, tmp_path):
        _write_java(tmp_path, "App.java", """\
            import org.springframework.boot.autoconfigure.SpringBootApplication;
            @SpringBootApplication
            public class App {}
        """)
        _write_pom(tmp_path, """\
            <project xmlns="http://maven.apache.org/POM/4.0.0">
              <dependencies>
                <dependency>
                  <groupId>org.springframework.boot</groupId>
                  <artifactId>spring-boot-starter-web</artifactId>
                  <version>3.4.2</version>
                </dependency>
              </dependencies>
            </project>
        """)
        result = _scan(str(tmp_path))
        assert result['extractorPath'] == 'python'
        assert 'org.springframework.boot.autoconfigure.SpringBootApplication' in result['entities']
        assert 'org.springframework.boot:spring-boot-starter-web' in result['entities']
        assert 'SpringBootApplication' in result['entities']
        # Entities list is sorted (deterministic order on all platforms)
        assert result['entities'] == sorted(result['entities'])
