"""framework_scanner.py — canonical entity extractor for the migration harness."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, NamedTuple

ALLOW_LIST = re.compile(
    r"^("
    r"org\.springframework|jakarta\.|javax\.|org\.hibernate|io\.micrometer"
    r"|io\.projectreactor|org\.thymeleaf|com\.fasterxml\.jackson|tools\.jackson"
    r"|org\.springdoc|com\.querydsl|org\.flywaydb|org\.liquibase"
    r"|org\.apache\.tomcat|org\.eclipse\.jetty|io\.undertow"
    r")"
)

IMPORT_RE = re.compile(r"^import\s+(?:static\s+)?([\w.]+)", re.MULTILINE)
ANNOTATION_RE = re.compile(r"@([A-Za-z][\w.]*)")
NOISE_ANNOTATIONS = frozenset(
    [
        "Override",
        "Deprecated",
        "SuppressWarnings",
        "FunctionalInterface",
        "SafeVarargs",
        "Data",
        "Builder",
        "Getter",
        "Setter",
        "ToString",
        "EqualsAndHashCode",
        "NoArgsConstructor",
        "AllArgsConstructor",
        "RequiredArgsConstructor",
        "Slf4j",
        "Value",
        "NonNull",
        "Nullable",
    ]
)
PROP_KEY_RE = re.compile(r"^([\w][\w.-]+)\s*=", re.MULTILINE)
MAVEN_NS = "{http://maven.apache.org/POM/4.0.0}"
MAVEN_KEEP = re.compile(
    r"^(org\.springframework|jakarta\.|javax\.|org\.hibernate|io\.micrometer"
    r"|io\.projectreactor|com\.fasterxml\.jackson|org\.springdoc|com\.querydsl"
    r"|org\.flywaydb|org\.liquibase|org\.apache\.tomcat|org\.eclipse\.jetty"
    r"|io\.undertow)\."
)
GRADLE_DEP_RE = re.compile(r"['\"]([a-zA-Z][\w.-]+:[a-zA-Z][\w.-]+):[^\s\"']+['\"]")


class ScanResult(NamedTuple):
    entities: list[str]
    test_entities: list[str]
    extractor_path: str  # always "python"
    warnings: list[str]


def _ensure_pyyaml() -> Any | None:
    """Return the yaml module, installing PyYAML into the current interpreter if needed."""
    try:
        import yaml  # type: ignore[import-untyped]

        return yaml
    except ImportError:
        pass

    print(
        "PyYAML absent — installing pyyaml into the current Python environment...",
        file=sys.stderr,
    )
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet", "pyyaml"],
            timeout=120,
        )
        import yaml  # type: ignore[import-untyped]

        print("PyYAML installed successfully.", file=sys.stderr)
        return yaml
    except (subprocess.SubprocessError, OSError, ImportError) as exc:
        print(
            f"PyYAML install failed ({exc}) — YAML property extraction skipped; "
            ".properties files parsed only",
            file=sys.stderr,
        )
        return None


def _scan_java_imports(root: Path, scope: str = "main") -> set[str]:
    """Collect FQCNs from Java/Kotlin import lines under src/{scope}."""
    result: set[str] = set()
    base = root / "src" / scope
    for ext in ("*.java", "*.kt"):
        for f in base.rglob(ext):
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for m in IMPORT_RE.finditer(text):
                fqcn = m.group(1)
                if ALLOW_LIST.match(fqcn):
                    result.add(fqcn)
    return result


def _scan_annotations(root: Path) -> set[str]:
    """Collect annotation simple names (no @) from src/main."""
    result: set[str] = set()
    for ext in ("*.java", "*.kt"):
        for f in (root / "src" / "main").rglob(ext):
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for m in ANNOTATION_RE.finditer(text):
                raw = m.group(1)
                simple = raw.rsplit(".", 1)[-1]
                if (
                    re.match(r"^[A-Z][A-Za-z0-9]+$", simple)
                    and simple not in NOISE_ANNOTATIONS
                ):
                    result.add(simple)
    return result


def _flatten_yaml_keys(d: dict, prefix: str, result: set[str]) -> None:
    for k, v in (d or {}).items():
        key = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict):
            _flatten_yaml_keys(v, key, result)
        else:
            result.add(key)


def _scan_properties(root: Path, warnings: list[str]) -> set[str]:
    """Collect dotted property keys from .properties and .yml/.yaml files."""
    result: set[str] = set()
    resources = root / "src" / "main" / "resources"
    for f in resources.rglob("*.properties"):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in PROP_KEY_RE.finditer(text):
            result.add(m.group(1))

    yaml_mod = _ensure_pyyaml()
    if yaml_mod is None:
        warnings.append(
            "PyYAML unavailable — YAML property extraction skipped; .properties files only"
        )
    else:
        for f in resources.rglob("*.y*ml"):
            try:
                data = yaml_mod.safe_load(f.read_text(encoding="utf-8", errors="replace"))
                if isinstance(data, dict):
                    _flatten_yaml_keys(data, "", result)
            except Exception:
                pass

    return result


def _scan_maven(root: Path) -> set[str]:
    """Collect groupId:artifactId from pom.xml files."""
    result: set[str] = set()
    for pom in root.rglob("pom.xml"):
        if "/target/" in str(pom) or "\\target\\" in str(pom):
            continue
        try:
            tree = ET.parse(str(pom)).getroot()
            for dep in tree.iter(MAVEN_NS + "dependency"):
                g = dep.find(MAVEN_NS + "groupId")
                a = dep.find(MAVEN_NS + "artifactId")
                if g is not None and a is not None:
                    gav = f"{g.text.strip()}:{a.text.strip()}"
                    if MAVEN_KEEP.match(gav):
                        result.add(gav)
        except Exception:
            pass
    return result


def _scan_gradle(root: Path) -> set[str]:
    """Collect groupId:artifactId from build.gradle(.kts) files."""
    result: set[str] = set()
    for f in root.rglob("build.gradle*"):
        if "/.gradle/" in str(f) or "\\.gradle\\" in str(f):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in GRADLE_DEP_RE.finditer(text):
            gav = m.group(1)
            if MAVEN_KEEP.match(gav):
                result.add(gav)
    return result


def scan(project_root: str) -> ScanResult:
    root = Path(project_root)
    warnings: list[str] = []
    main_imports = _scan_java_imports(root, "main")
    test_imports = _scan_java_imports(root, "test")
    annotations = _scan_annotations(root)
    properties = _scan_properties(root, warnings)
    maven_deps = _scan_maven(root)
    gradle_deps = _scan_gradle(root)

    entities = sorted(main_imports | annotations | properties | maven_deps | gradle_deps)
    test_entities = sorted(test_imports)
    return ScanResult(
        entities=entities,
        test_entities=test_entities,
        extractor_path="python",
        warnings=warnings,
    )


if __name__ == "__main__":
    project_root = sys.argv[1] if len(sys.argv) > 1 else "."
    result = scan(project_root)
    print(
        json.dumps(
            {
                "entities": result.entities,
                "testEntities": result.test_entities,
                "extractorPath": result.extractor_path,
                "warnings": result.warnings,
                "count": len(result.entities),
            },
            indent=2,
        )
    )
