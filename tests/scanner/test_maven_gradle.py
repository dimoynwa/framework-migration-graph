"""Maven and Gradle manifests, the Spring Boot version (spec 026.6, FR-3 / FR-8,
AC-6 / AC-7).

Two readers, one question each: *which Spring Boot version does this module
build against* (FR-3) and *what does its build declare* (FR-8). The tests go in
that order — the version first, because that is the one fact a migration plan
cannot work without — and then walk the notations the profile has to understand,
ending with the fixtures and the failure modes a real repo has (a broken pom, a
Gradle form the lexer does not know, a scan with no Maven or Gradle module).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from migration_planner.scanner import builtin, contract
from migration_planner.scanner.discover import discover
from migration_planner.scanner.gradle import read_gradle_manifests
from migration_planner.scanner.maven import read_maven_manifests
from migration_planner.scanner.scan import scan, _manifest_contexts

from .conftest import FIXTURES, read_profile


@pytest.fixture(autouse=True)
def installed_registry():
    """``scan()`` installs nothing; a scan test asks for the shipped readers."""
    contract.reset_registry()
    builtin.install()
    yield
    contract.reset_registry()


@pytest.fixture()
def spring_maven(tmp_path: Path) -> Path:
    """Multi-module Maven tree: parent pom with the Boot BOM, ``app`` and ``lib``."""
    target = tmp_path / "spring-maven"
    shutil.copytree(FIXTURES / "spring-maven", target)
    return target


@pytest.fixture()
def spring_gradle(tmp_path: Path) -> Path:
    """Gradle tree: Kotlin root, Groovy subproject, catalog, ``gradle.properties``."""
    target = tmp_path / "spring-gradle"
    shutil.copytree(FIXTURES / "spring-gradle", target)
    return target


def _scan(repo: Path):
    """Scan and return ``(result, profile, dependencies, config)`` by key."""
    result = scan(repo, out=repo / "profile.json")
    profile = read_profile(repo / "profile.json")
    dependencies = {
        (entry["module"], entry["kind"], entry["key"], entry["scope"]): entry
        for entry in profile["dependencies"]
    }
    config = {
        (entry["module"], entry["key"]): entry for entry in profile["config"]
    }
    return result, profile, dependencies, config


def _read_maven(repo: Path, module: str = "."):
    return read_maven_manifests(_manifest_contexts(discover(repo))[module])


def _read_gradle(repo: Path, module: str = "."):
    return read_gradle_manifests(_manifest_contexts(discover(repo))[module])


def _frameworks(facts) -> list[tuple[str, str]]:
    return [(framework.name, framework.version) for framework in facts.frameworks]


# --- FR-3: the Spring Boot version, from Maven ----------------------------


def test_the_starter_parent_is_the_first_spring_boot_source(make_repo) -> None:
    """FR-3 case 1: a ``spring-boot-starter-parent`` parent wins over everything."""
    repo = make_repo(
        {
            "pom.xml": (
                "<project><modelVersion>4.0.0</modelVersion>"
                "<parent><groupId>org.springframework.boot</groupId>"
                "<artifactId>spring-boot-starter-parent</artifactId>"
                "<version>3.3.4</version><relativePath/></parent>"
                "<groupId>com.acme</groupId><artifactId>svc</artifactId>"
                "<version>1.0.0</version></project>"
            )
        }
    )

    facts = _read_maven(repo)

    assert _frameworks(facts) == [("spring-boot", "3.3.4")]
    assert facts.frameworks[0].raw == "3.3.4"
    assert facts.frameworks[0].source == "pom.xml#parent"


def test_a_spring_boot_bom_import_is_the_second_source(make_repo) -> None:
    """FR-3 case 2: no Boot parent, so the ``spring-boot-dependencies`` BOM."""
    repo = make_repo(
        {
            "pom.xml": (
                "<project><modelVersion>4.0.0</modelVersion>"
                "<groupId>com.acme</groupId><artifactId>svc</artifactId>"
                "<version>1.0.0</version>"
                "<dependencyManagement><dependencies><dependency>"
                "<groupId>org.springframework.boot</groupId>"
                "<artifactId>spring-boot-dependencies</artifactId>"
                "<version>3.2.0</version><type>pom</type>"
                "<scope>import</scope></dependency></dependencies>"
                "</dependencyManagement></project>"
            )
        }
    )

    facts = _read_maven(repo)

    assert _frameworks(facts) == [("spring-boot", "3.2.0")]
    assert facts.frameworks[0].source == "pom.xml#dependencyManagement"


def test_a_non_boot_parent_pom_is_not_a_spring_boot_module(make_repo) -> None:
    repo = make_repo(
        {
            "pom.xml": (
                "<project><parent><groupId>com.acme</groupId>"
                "<artifactId>acme-parent</artifactId><version>1.0.0</version>"
                "<relativePath/></parent>"
                "<artifactId>svc</artifactId></project>"
            )
        }
    )

    assert _frameworks(_read_maven(repo)) == []


def test_a_boot_version_from_a_parent_property_is_resolved(make_repo) -> None:
    """``<version>${spring-boot.version}</version>`` names a real version (AC-6)."""
    repo = make_repo(
        {
            "pom.xml": (
                "<project><groupId>com.acme</groupId><artifactId>svc</artifactId>"
                "<version>1.0.0</version><properties>"
                "<spring-boot.version>3.4.0</spring-boot.version></properties>"
                "<dependencyManagement><dependencies><dependency>"
                "<groupId>org.springframework.boot</groupId>"
                "<artifactId>spring-boot-dependencies</artifactId>"
                "<version>${spring-boot.version}</version><type>pom</type>"
                "<scope>import</scope></dependency></dependencies>"
                "</dependencyManagement></project>"
            )
        }
    )

    assert _frameworks(_read_maven(repo)) == [("spring-boot", "3.4.0")]


def test_a_child_module_inherits_the_parent_boot_version(spring_maven: Path) -> None:
    """The BOM lives in the parent pom; each child is on that version (FR-3)."""
    _, profile, _, _ = _scan(spring_maven)

    frameworks = {module["path"]: module["frameworks"] for module in profile["modules"]}

    assert [entry["version"] for entry in frameworks["app"]] == ["3.3.4"]
    assert [entry["version"] for entry in frameworks["lib"]] == ["3.3.4"]
    # The repo-level framework is the one found in most modules (spec1 FR-3).
    assert profile["framework"]["name"] == "spring-boot"
    assert profile["framework"]["version"] == "3.3.4"


def test_an_external_parent_is_not_read_from_disk(tmp_path: Path) -> None:
    """A parent outside the repo is coordinates only: a scan never leaves the tree."""
    repo = tmp_path / "outside"
    repo.mkdir()
    (repo / "pom.xml").write_text(
        "<project><parent><groupId>org.springframework.boot</groupId>"
        "<artifactId>spring-boot-starter-parent</artifactId>"
        "<version>3.3.4</version></parent>"
        "<artifactId>svc</artifactId></project>"
    )
    # A pom *above* the scan root must not be picked up as the parent.
    (tmp_path / "pom.xml").write_text(
        "<project><groupId>org.springframework.boot</groupId>"
        "<artifactId>spring-boot-starter-parent</artifactId>"
        "<version>9.9.9</version></project>"
    )

    facts = _read_maven(repo)

    assert _frameworks(facts) == [("spring-boot", "3.3.4")]


def test_a_parent_cycle_does_not_hang(make_repo) -> None:
    """A pom whose ``<parent>`` names itself is a cycle, not an infinite chain."""
    repo = make_repo(
        {
            "pom.xml": (
                "<project><parent><groupId>com.acme</groupId>"
                "<artifactId>a</artifactId><version>1</version>"
                "<relativePath>pom.xml</relativePath></parent>"
                "<groupId>com.acme</groupId><artifactId>a</artifactId>"
                "<version>1</version></project>"
            )
        }
    )

    facts = _read_maven(repo)

    assert facts.frameworks == []
    assert [entry.kind for entry in facts.diagnostics] == ["pom_parent_cycle"]


# --- FR-3: the Spring Boot version, from Gradle ---------------------------


def test_the_spring_boot_plugin_is_the_first_gradle_source(make_repo) -> None:
    """FR-3 case 3: ``id 'org.springframework.boot' version 'X'``, either DSL."""
    groovy = make_repo(
        {
            "build.gradle": (
                "plugins {\n"
                "    id 'org.springframework.boot' version '3.3.4'\n"
                "    id 'io.spring.dependency-management' version '1.1.6'\n"
                "}\n"
            )
        },
        name="groovy",
    )
    kotlin = make_repo(
        {
            "build.gradle.kts": (
                "plugins {\n"
                '    id("org.springframework.boot") version "3.4.1"\n'
                "}\n"
            )
        },
        name="kotlin",
    )

    assert _frameworks(_read_gradle(groovy)) == [("spring-boot", "3.3.4")]
    assert _frameworks(_read_gradle(kotlin)) == [("spring-boot", "3.4.1")]


def test_a_catalog_plugin_alias_gives_the_spring_boot_version(make_repo) -> None:
    """FR-3: ``alias(libs.plugins.spring.boot)``, version via ``version.ref``."""
    repo = make_repo(
        {
            "gradle/libs.versions.toml": (
                "[versions]\n"
                'springBoot = "3.5.0"\n\n'
                "[plugins]\n"
                'spring-boot = { id = "org.springframework.boot", version.ref = "springBoot" }\n'
            ),
            "build.gradle.kts": (
                "plugins {\n"
                "    alias(libs.plugins.spring.boot)\n"
                "}\n"
            ),
        }
    )

    facts = _read_gradle(repo)

    assert _frameworks(facts) == [("spring-boot", "3.5.0")]
    assert facts.frameworks[0].source == "build.gradle.kts#catalog"


def test_a_platform_bom_gives_the_spring_boot_version(make_repo) -> None:
    """FR-3 case 4: ``platform("org.springframework.boot:spring-boot-dependencies:X")``."""
    repo = make_repo(
        {
            "build.gradle": (
                "dependencies {\n"
                "    implementation platform("
                "'org.springframework.boot:spring-boot-dependencies:3.2.5')\n"
                "    implementation 'org.springframework.boot:spring-boot-starter-web'\n"
                "}\n"
            )
        }
    )

    facts = _read_gradle(repo)

    assert _frameworks(facts) == [("spring-boot", "3.2.5")]
    assert facts.frameworks[0].source == "build.gradle#platform"


def test_a_subproject_inherits_the_root_plugin_version(spring_gradle: Path) -> None:
    """The root declares ``apply false``; the subproject applies it (FR-3)."""
    facts = _read_gradle(spring_gradle, "service")

    assert _frameworks(facts) == [("spring-boot", "3.4.1")]
    # ``source`` names the script that declares the version, not the one that
    # applies the plugin without one.
    assert facts.frameworks[0].source == "settings.gradle.kts#pluginManagement"


def test_apply_false_does_not_make_the_root_project_spring_boot(
    spring_gradle: Path,
) -> None:
    """``id("org.springframework.boot") version "3.4.1" apply false`` is a version, not a use."""
    _, profile, _, _ = _scan(spring_gradle)

    frameworks = {module["path"]: module["frameworks"] for module in profile["modules"]}

    assert frameworks["."] == []
    assert [entry["version"] for entry in frameworks["service"]] == ["3.4.1"]


def test_plugin_management_supplies_the_version(make_repo) -> None:
    """``pluginManagement`` in ``settings.gradle`` versions an unversioned plugin."""
    repo = make_repo(
        {
            "settings.gradle": (
                "pluginManagement {\n"
                "    plugins {\n"
                "        id 'org.springframework.boot' version '3.1.2'\n"
                "    }\n"
                "}\n"
                "include 'svc'\n"
            ),
            "build.gradle": "// root\n",
            "svc/build.gradle": (
                "plugins {\n    id 'org.springframework.boot'\n}\n"
            ),
        }
    )

    facts = _read_gradle(repo, "svc")

    assert _frameworks(facts) == [("spring-boot", "3.1.2")]


# --- FR-8: Maven manifests -----------------------------------------------


def test_parent_dependencies_boms_and_plugins_are_separate_kinds(
    spring_maven: Path,
) -> None:
    """AC-6: one entry per ``(key, module, scope, kind)``."""
    _, _, dependencies, _ = _scan(spring_maven)

    app = {
        (kind, key): entry
        for (module, kind, key, _), entry in dependencies.items()
        if module == "app"
    }

    assert ("parent", "maven:com.acme:acme-parent") in app
    assert ("plugin", "maven:org.springframework.boot:spring-boot-maven-plugin") in app
    assert (
        "dependency",
        "maven:org.springframework.boot:spring-boot-starter-web",
    ) in app
    assert ("dependency", "maven:org.springframework.boot:spring-boot-starter-actuator") in app
    assert app[("dependency", "maven:org.springframework.boot:spring-boot-starter-actuator")][
        "scope"
    ] == "runtime"


def test_a_bom_import_and_a_dependency_on_it_are_two_entries(make_repo) -> None:
    """AC-1.5: the same artifact as ``bom`` and as ``dependency`` is two facts."""
    repo = make_repo(
        {
            "pom.xml": (
                "<project><groupId>com.acme</groupId><artifactId>svc</artifactId>"
                "<version>1.0.0</version>"
                "<dependencyManagement><dependencies><dependency>"
                "<groupId>org.springframework.boot</groupId>"
                "<artifactId>spring-boot-dependencies</artifactId>"
                "<version>3.3.4</version><type>pom</type><scope>import</scope>"
                "</dependency></dependencies></dependencyManagement>"
                "<dependencies><dependency>"
                "<groupId>org.springframework.boot</groupId>"
                "<artifactId>spring-boot-dependencies</artifactId>"
                "<version>3.3.4</version><type>pom</type>"
                "</dependency></dependencies></project>"
            )
        }
    )

    _, profile, dependencies, _ = _scan(repo)

    kinds = {
        entry["kind"]
        for entry in profile["dependencies"]
        if entry["key"] == "maven:org.springframework.boot:spring-boot-dependencies"
    }
    assert kinds == {"bom", "dependency"}
    assert len(dependencies) == 2


def test_a_parent_property_resolves_in_a_child_pom(spring_maven: Path) -> None:
    """AC-6: ``${jackson.version}`` is declared in the parent (FR-8 interpolation)."""
    _, _, dependencies, _ = _scan(spring_maven)

    entry = next(
        entry
        for (module, kind, key, _), entry in dependencies.items()
        if key == "maven:com.fasterxml.jackson.core:jackson-databind"
    )

    assert entry["version"] == "2.17.2"
    assert entry["range"] == "${jackson.version}"
    assert entry["version_source"] == "declared"


def test_a_property_that_refers_to_the_project_version_resolves(spring_maven: Path) -> None:
    """``<acme.version>${project.version}</acme.version>`` resolves in the child.

    The fixture's child inherits the parent's version, so both read ``2.0.0``;
    ``test_a_parent_project_version_means_the_childs_own_version`` covers a
    child with a version of its own.
    """
    _, _, dependencies, _ = _scan(spring_maven)

    entry = next(
        entry
        for (module, kind, key, _), entry in dependencies.items()
        if key == "maven:com.acme:lib"
    )

    assert entry["version"] == "2.0.0"


def test_an_unresolved_property_keeps_its_raw_text_and_a_diagnostic(
    spring_maven: Path,
) -> None:
    """AC-6: ``${external.bom.version}`` is not a version, and it is reported once."""
    result, profile, dependencies, _ = _scan(spring_maven)

    entry = next(
        entry
        for (module, kind, key, _), entry in dependencies.items()
        if key == "maven:com.example:mystery"
    )

    assert entry["version"] is None
    assert entry["range"] == "${external.bom.version}"
    unresolved = [
        diagnostic
        for diagnostic in profile["diagnostics"]
        if diagnostic["kind"] == "unresolved_variable"
    ]
    assert [diagnostic["detail"] for diagnostic in unresolved] == [
        "${external.bom.version}"
    ]
    assert unresolved[0]["file"] == "app/pom.xml"
    assert unresolved[0]["line"] == 34


def test_properties_become_cfg_keys(spring_maven: Path) -> None:
    """AC-6: ``cfg:pom.xml#properties.java.version`` is what a rule asks for."""
    _, _, _, config = _scan(spring_maven)

    assert config[(".", "cfg:pom.xml#properties.java.version")]["value"] == "17"
    assert config[(".", "cfg:pom.xml#properties.java.version")]["file"] == "pom.xml"
    assert config[(".", "cfg:pom.xml#properties.java.version")]["line"] == 13


def test_a_child_module_records_the_properties_it_inherits(spring_maven: Path) -> None:
    """A rule about ``java.version`` applies to ``lib`` too: it inherits the value."""
    _, _, _, config = _scan(spring_maven)

    assert config[("lib", "cfg:pom.xml#properties.java.version")]["value"] == "17"
    # The file that declares it is named, not the module that inherits it.
    assert config[("lib", "cfg:pom.xml#properties.java.version")]["file"] == "pom.xml"


def test_a_property_using_an_inherited_one_resolves(make_repo) -> None:
    """``<release>${java.version}</release>`` in a child resolves from the parent."""
    repo = make_repo(
        {
            "pom.xml": (
                "<project><groupId>com.acme</groupId><artifactId>parent</artifactId>"
                "<version>1.0</version><packaging>pom</packaging>"
                "<properties><java.version>21</java.version></properties>"
                "<modules><module>child</module></modules></project>"
            ),
            "child/pom.xml": (
                "<project><parent><groupId>com.acme</groupId>"
                "<artifactId>parent</artifactId><version>1.0</version></parent>"
                "<artifactId>child</artifactId><properties>"
                "<maven.compiler.release>${java.version}</maven.compiler.release>"
                "</properties></project>"
            ),
        }
    )

    facts = _read_maven(repo, "child")

    values = {entry.key: entry.value for entry in facts.config}
    assert values["cfg:pom.xml#properties.maven.compiler.release"] == "21"
    assert values["cfg:pom.xml#properties.java.version"] == "21"


def test_a_plugin_without_a_group_id_gets_mavens_default_group(spring_maven: Path) -> None:
    _, _, dependencies, _ = _scan(spring_maven)

    entry = next(
        entry
        for (module, kind, key, _), entry in dependencies.items()
        if key == "maven:org.apache.maven.plugins:maven-surefire-plugin"
    )

    assert entry["kind"] == "plugin"
    assert entry["version"] == "3.2.5"


def test_a_managed_entry_keeps_its_own_scope(make_repo) -> None:
    """A ``<dependencyManagement>`` entry that is not an import is still a fact."""
    repo = make_repo(
        {
            "pom.xml": (
                "<project><groupId>com.acme</groupId><artifactId>svc</artifactId>"
                "<version>1.0</version><dependencyManagement><dependencies>"
                "<dependency><groupId>org.apache.commons</groupId>"
                "<artifactId>commons-lang3</artifactId><version>3.17.0</version>"
                "</dependency></dependencies></dependencyManagement></project>"
            )
        }
    )

    facts = _read_maven(repo)

    assert [
        (entry.key, entry.kind, entry.scope, entry.version)
        for entry in facts.dependencies
    ] == [
        ("maven:org.apache.commons:commons-lang3", "dependency", "dependencyManagement", "3.17.0")
    ]


def test_maven_modules_are_read_as_separate_modules(spring_maven: Path) -> None:
    """AC-6: ``<modules>`` are followed, each with its own poms."""
    _, profile, _, _ = _scan(spring_maven)

    modules = {module["path"]: module["manifests"] for module in profile["modules"]}

    assert set(modules) == {".", "app", "lib"}
    assert modules["app"] == ["pom.xml"]


def test_a_declared_module_with_no_manifest_of_its_own_is_still_listed(
    make_repo,
) -> None:
    """FR-3: a Maven ``<module>`` is a module root, discovery or not."""
    repo = make_repo(
        {
            "pom.xml": (
                "<project><groupId>com.acme</groupId><artifactId>parent</artifactId>"
                "<version>1.0</version><packaging>pom</packaging>"
                "<modules><module>docs-site</module></modules></project>"
            ),
            "docs-site/README.md": "documentation, no pom\n",
        }
    )

    _, profile, _, _ = _scan(repo)

    assert "docs-site" in {module["path"] for module in profile["modules"]}


def test_a_broken_pom_is_a_diagnostic_not_a_crash(make_repo) -> None:
    repo = make_repo({"pom.xml": "<project><dependencies><dependency>"})

    result, profile, _, _ = _scan(repo)

    assert result.path is not None and result.path.is_file()
    assert [entry["kind"] for entry in profile["diagnostics"]] == ["pom_parse_error"]


def test_a_pom_doctype_is_not_expanded(make_repo) -> None:
    """``xml.etree`` never resolves an external entity: a scan reads no extra file."""
    secret = make_repo(
        {"pom.xml": "<project><groupId>&xxe;</groupId></project>", "secret.txt": "top"},
        name="xxe",
    )
    (secret / "xxe.dtd").write_text('<!ENTITY xxe SYSTEM "file:///etc/passwd">')

    facts = _read_maven(secret)

    assert facts.frameworks == []
    assert [entry.kind for entry in facts.diagnostics] == ["pom_parse_error"]


# --- FR-8: Gradle dependencies -------------------------------------------


def test_every_notation_becomes_a_dependency(spring_gradle: Path) -> None:
    """AC-7: string, map, ``platform()``, catalog accessor and ``project()``."""
    _, _, dependencies, _ = _scan(spring_gradle)

    service = {
        (kind, key): entry
        for (module, kind, key, _), entry in dependencies.items()
        if module == "service"
    }

    # String notation, no version (the BOM supplies it).
    assert ("dependency", "maven:org.springframework.boot:spring-boot-starter-web") in service
    # Groovy map notation.
    assert service[
        ("dependency", "maven:com.fasterxml.jackson.core:jackson-core")
    ]["version"] == "2.17.2"
    # ``platform(…)`` is a BOM, not a dependency.
    assert service[("bom", "maven:org.springframework.boot:spring-boot-dependencies")][
        "version"
    ] == "3.4.1"
    # An own project is not an external fact.
    assert not any(key.endswith(":common") for _, key in service)


def test_a_catalog_accessor_resolves_through_version_ref(spring_gradle: Path) -> None:
    """AC-7: ``libs.jackson.databind`` with ``version.ref = "jackson"``."""
    _, _, dependencies, _ = _scan(spring_gradle)

    entry = next(
        entry
        for (module, kind, key, _), entry in dependencies.items()
        if key == "maven:com.fasterxml.jackson.core:jackson-databind"
        and entry["module"] == "service"
    )

    assert entry["version"] == "2.18.2"
    assert entry["scope"] == "implementation"


def test_a_catalog_entry_with_a_literal_version_resolves(spring_gradle: Path) -> None:
    """The string form ``lombok = "org.projectlombok:lombok:1.18.34"``."""
    _, _, dependencies, _ = _scan(spring_gradle)

    entry = next(
        entry
        for (module, kind, key, _), entry in dependencies.items()
        if key == "maven:org.projectlombok:lombok" and entry["scope"] == "implementation"
    )

    assert entry["version"] == "1.18.34"


def test_every_configuration_name_is_a_scope(spring_gradle: Path) -> None:
    """FR-8: ``implementation``, ``compileOnly``, ``testImplementation``, …"""
    _, _, dependencies, _ = _scan(spring_gradle)

    scopes = {
        entry["scope"] for entry in dependencies.values() if entry["module"] == "service"
    }

    assert {"implementation", "compileOnly", "testImplementation"} <= scopes


def test_a_gradle_property_variable_resolves(spring_gradle: Path) -> None:
    """AC-7: ``$springCloudVersion`` comes from ``gradle.properties``."""
    _, _, dependencies, _ = _scan(spring_gradle)

    entry = next(
        entry
        for (module, kind, key, _), entry in dependencies.items()
        if key == "maven:org.springframework.cloud:spring-cloud-starter-config"
    )

    assert entry["version"] == "2024.0.0"


def test_an_ext_variable_resolves(make_repo) -> None:
    """FR-8: ``ext { v = '…' }`` resolves ``$v`` / ``${v}``."""
    repo = make_repo(
        {
            "build.gradle": (
                "ext {\n"
                "    jacksonVersion = '2.17.2'\n"
                "}\n"
                "dependencies {\n"
                "    implementation 'com.fasterxml.jackson.core:jackson-databind:$jacksonVersion'\n"
                "    implementation \"com.fasterxml.jackson.core:jackson-core:${jacksonVersion}\"\n"
                "}\n"
            )
        }
    )

    versions = {
        entry.key: entry.version for entry in _read_gradle(repo).dependencies
    }

    assert versions == {
        "maven:com.fasterxml.jackson.core:jackson-databind": "2.17.2",
        "maven:com.fasterxml.jackson.core:jackson-core": "2.17.2",
    }


def test_an_extra_assignment_resolves(make_repo) -> None:
    repo = make_repo(
        {
            "build.gradle.kts": (
                'extra["springBootVersion"] = "3.4.1"\n'
                "dependencies {\n"
                '    implementation("org.springframework.boot:spring-boot-starter-web:$springBootVersion")\n'
                "}\n"
            )
        }
    )

    facts = _read_gradle(repo)

    assert [entry.version for entry in facts.dependencies] == ["3.4.1"]


def test_an_unresolved_variable_keeps_its_raw_text_and_a_diagnostic(
    spring_gradle: Path,
) -> None:
    """AC-7: ``$externalLibVersion`` is declared nowhere, and that is reported."""
    _, profile, dependencies, _ = _scan(spring_gradle)

    entry = next(
        entry
        for (module, kind, key, _), entry in dependencies.items()
        if key == "maven:com.example:external-lib"
    )

    assert entry["version"] is None
    assert entry["range"] == "$externalLibVersion"
    unresolved = [
        diagnostic
        for diagnostic in profile["diagnostics"]
        if diagnostic["kind"] == "unresolved_variable"
    ]
    assert [diagnostic["detail"] for diagnostic in unresolved] == ["$externalLibVersion"]
    assert unresolved[0]["file"] == "service/build.gradle"


def test_a_dependency_line_the_lexer_cannot_parse_is_reported(make_repo) -> None:
    """FR-8: a dependency-looking line that does not parse is never silent.

    ``add("implementation", "g:a:v")`` is legal Gradle that names its
    configuration in a string, which the lexer's ``configuration coordinate``
    reading cannot follow: the profile says so instead of dropping the artifact.
    """
    repo = make_repo(
        {
            "build.gradle": (
                "dependencies {\n"
                "    implementation 'org.example:known:1.0'\n"
                '    add("implementation", "org.example:thing:1.0")\n'
                "}\n"
            )
        }
    )

    facts = _read_gradle(repo)

    assert [entry.key for entry in facts.dependencies] == [
        "maven:org.example:known"
    ]
    assert [(entry.kind, entry.line) for entry in facts.diagnostics] == [
        ("unparsed_gradle", 3)
    ]


def test_a_call_that_is_not_a_dependency_is_skipped_silently(make_repo) -> None:
    """``project(…)`` and ``files(…)`` are not external coordinates, so no diagnostic."""
    repo = make_repo(
        {
            "build.gradle": (
                "dependencies {\n"
                "    implementation project(':core')\n"
                "    implementation files('libs/local.jar')\n"
                "    implementation gradleApi()\n"
                "}\n"
            )
        }
    )

    facts = _read_gradle(repo)

    assert facts.dependencies == []
    assert facts.diagnostics == []


def test_a_trailing_closure_is_not_a_second_dependency(make_repo) -> None:
    """``implementation('x') { exclude group: 'g' }`` declares one dependency."""
    repo = make_repo(
        {
            "build.gradle": (
                "dependencies {\n"
                "    implementation('org.springframework.boot:spring-boot-starter-web:3.3.4') {\n"
                "        exclude group: 'org.springframework.boot', module: 'spring-boot-starter-tomcat'\n"
                "    }\n"
                "}\n"
            )
        }
    )

    facts = _read_gradle(repo)

    assert [(entry.key, entry.version) for entry in facts.dependencies] == [
        ("maven:org.springframework.boot:spring-boot-starter-web", "3.3.4")
    ]
    assert facts.diagnostics == []


def test_a_comment_is_not_a_declaration(make_repo) -> None:
    repo = make_repo(
        {
            "build.gradle": (
                "// implementation 'org.example:commented:1.0'\n"
                "/* implementation 'org.example:blocked:1.0' */\n"
                "dependencies {\n"
                "    implementation 'org.example:real:1.0'\n"
                "}\n"
            )
        }
    )

    assert [entry.key for entry in _read_gradle(repo).dependencies] == [
        "maven:org.example:real"
    ]


def test_a_classifier_is_not_part_of_the_version(make_repo) -> None:
    repo = make_repo(
        {
            "build.gradle": (
                "dependencies {\n"
                "    implementation 'com.android.tools:aar-lib:1.0.0@aar'\n"
                "}\n"
            )
        }
    )

    assert [entry.version for entry in _read_gradle(repo).dependencies] == ["1.0.0"]


# --- real-world build layouts --------------------------------------------


def test_a_buildscript_ext_block_declares_the_versions(make_repo) -> None:
    """The classic Groovy layout puts ``ext`` in ``buildscript`` and uses it below."""
    repo = make_repo(
        {
            "build.gradle": (
                "buildscript {\n"
                "    ext {\n"
                "        springBootVersion = '2.7.18'\n"
                "    }\n"
                "    dependencies {\n"
                "        classpath \"org.springframework.boot:spring-boot-gradle-plugin:${springBootVersion}\"\n"
                "    }\n"
                "}\n"
                "dependencies {\n"
                "    implementation \"org.springframework.cloud:spring-cloud-starter-config:${springBootVersion}\"\n"
                "}\n"
            )
        }
    )

    facts = _read_gradle(repo)

    assert sorted(
        (entry.key, entry.version) for entry in facts.dependencies
    ) == [
        (
            "maven:org.springframework.boot:spring-boot-gradle-plugin",
            "2.7.18",
        ),
        (
            "maven:org.springframework.cloud:spring-cloud-starter-config",
            "2.7.18",
        ),
    ]
    assert facts.diagnostics == []


def test_a_buildscript_classpath_dependency_is_not_a_compile_dependency(
    make_repo,
) -> None:
    """``buildscript``'s ``classpath`` is the build's own classpath, and says so."""
    repo = make_repo(
        {
            "build.gradle": (
                "buildscript {\n"
                "    dependencies {\n"
                '        classpath "io.spring.gradle:dependency-management-plugin:1.1.4"\n'
                "    }\n"
                "}\n"
            )
        }
    )

    facts = _read_gradle(repo)

    assert [(entry.key, entry.scope) for entry in facts.dependencies] == [
        ("maven:io.spring.gradle:dependency-management-plugin", "buildscript:classpath")
    ]


def test_maven_bom_is_a_bom_not_a_dependency(make_repo) -> None:
    """``dependencyManagement { imports { mavenBom … } }`` (the Spring plugin's syntax)."""
    repo = make_repo(
        {
            "build.gradle": (
                "dependencyManagement {\n"
                "    imports {\n"
                '        mavenBom "org.springframework.cloud:spring-cloud-dependencies:2023.0.5"\n'
                "    }\n"
                "}\n"
            )
        }
    )

    facts = _read_gradle(repo)

    assert [
        (entry.key, entry.kind, entry.version) for entry in facts.dependencies
    ] == [
        (
            "maven:org.springframework.cloud:spring-cloud-dependencies",
            "bom",
            "2023.0.5",
        )
    ]


def test_the_boot_plugin_bom_constant_is_recognized(make_repo) -> None:
    """``mavenBom SpringBootPlugin.BOM_COORDINATES`` names the Boot BOM (no version)."""
    repo = make_repo(
        {
            "build.gradle": (
                "plugins {\n"
                "    id 'org.springframework.boot' version '2.7.18'\n"
                "}\n"
                "dependencyManagement {\n"
                "    imports {\n"
                "        mavenBom org.springframework.boot.gradle.plugin."
                "SpringBootPlugin.BOM_COORDINATES\n"
                "    }\n"
                "}\n"
            )
        }
    )

    facts = _read_gradle(repo)

    assert [
        (entry.key, entry.kind) for entry in facts.dependencies
    ] == [
        ("gradle-plugin:org.springframework.boot", "plugin"),
        ("maven:org.springframework.boot:spring-boot-dependencies", "bom"),
    ]
    # The plugin supplies the version, so FR-3 still finds it.
    assert _frameworks(facts) == [("spring-boot", "2.7.18")]
    assert facts.diagnostics == []


def test_a_kotlin_top_level_val_declares_a_version(make_repo) -> None:
    """``val mockkVersion = "1.13.13"`` then ``$mockkVersion`` (Kotlin DSL)."""
    repo = make_repo(
        {
            "build.gradle.kts": (
                'val mockkVersion = "1.13.13"\n'
                'val computed = someFunction()\n'
                "dependencies {\n"
                '    testImplementation("io.mockk:mockk:$mockkVersion")\n'
                "}\n"
            )
        }
    )

    facts = _read_gradle(repo)

    assert [(entry.key, entry.version) for entry in facts.dependencies] == [
        ("maven:io.mockk:mockk", "1.13.13")
    ]
    assert facts.diagnostics == []


def test_a_dependency_with_a_version_block_is_not_a_failure(make_repo) -> None:
    """``implementation('g:a') { version { strictly '1.0' } }`` does not parse, and says so."""
    repo = make_repo(
        {
            "build.gradle": (
                "dependencies {\n"
                "    implementation('com.google.guava:guava') {\n"
                "        version { strictly '32.1.3-jre' }\n"
                "    }\n"
                "}\n"
            )
        }
    )

    facts = _read_gradle(repo)

    # The artifact is recorded (its coordinates are there); only the version in
    # the closure is beyond a lexer, and the range is empty rather than wrong.
    assert [(entry.key, entry.version) for entry in facts.dependencies] == [
        ("maven:com.google.guava:guava", None)
    ]
    assert facts.diagnostics == []


# --- FR-8: Gradle plugins, module roots, config keys ---------------------


def test_plugins_become_plugin_facts(spring_gradle: Path) -> None:
    """FR-8: ``gradle-plugin:<id>`` with the version the build really uses."""
    _, _, dependencies, _ = _scan(spring_gradle)

    plugins = {
        (module, key): entry
        for (module, kind, key, _), entry in dependencies.items()
        if kind == "plugin"
    }

    assert plugins[("service", "gradle-plugin:io.spring.dependency-management")][
        "version"
    ] == "1.1.6"
    # The subproject's unversioned plugin gets the root's version.
    assert plugins[("service", "gradle-plugin:org.springframework.boot")]["version"] == "3.4.1"


def test_apply_plugin_is_a_plugin_fact(make_repo) -> None:
    repo = make_repo(
        {"build.gradle": "apply plugin: 'java'\napply plugin: 'org.springframework.boot'\n"}
    )

    assert [entry.key for entry in _read_gradle(repo).dependencies] == [
        "gradle-plugin:java",
        "gradle-plugin:org.springframework.boot",
    ]


def test_a_bare_plugin_application_is_a_plugin_fact(make_repo) -> None:
    """``plugins { java }`` — the Kotlin DSL shorthand, with no ``id(…)`` at all."""
    repo = make_repo(
        {
            "build.gradle.kts": (
                "plugins {\n"
                "    java\n"
                "    application\n"
                "}\n"
            )
        }
    )

    assert {entry.key for entry in _read_gradle(repo).dependencies} == {
        "gradle-plugin:application",
        "gradle-plugin:java",
    }
    assert _read_gradle(repo).diagnostics == []


def test_a_toolchain_and_a_compatibility_setting_are_config_keys(make_repo) -> None:
    """FR-8 / AC-7: the JDK a build compiles with, in both spellings."""
    repo = make_repo(
        {
            "build.gradle.kts": (
                "java {\n"
                "    toolchain {\n"
                "        languageVersion = JavaLanguageVersion.of(21)\n"
                "    }\n"
                "}\n"
            ),
            "legacy/build.gradle": "sourceCompatibility = JavaVersion.VERSION_17\n",
        }
    )

    _, _, _, config = _scan(repo)

    assert config[(".", "cfg:build.gradle.kts#java.toolchain.languageVersion")][
        "value"
    ] == "21"
    assert config[("legacy", "cfg:build.gradle#sourceCompatibility")]["value"] == "17"


def test_a_gradle_config_key_uses_the_canonical_file_name(make_repo) -> None:
    """025 FR-2.6: a rule says ``cfg:build.gradle#…``, not the subproject's path."""
    repo = make_repo(
        {
            "svc/build.gradle": "sourceCompatibility = 21\n",
        }
    )

    _, _, _, config = _scan(repo)

    entry = config[("svc", "cfg:build.gradle#sourceCompatibility")]
    # The key is canonical; the real file is still recorded.
    assert entry["file"] == "svc/build.gradle"


def test_settings_include_declares_module_roots(make_repo) -> None:
    """AC-7: ``include(...)`` → module roots, both DSLs and nested paths."""
    repo = make_repo(
        {
            "settings.gradle.kts": (
                'rootProject.name = "demo"\n'
                'include("service", ":platform:common")\n'
            ),
            "build.gradle.kts": "// root\n",
            "service/build.gradle.kts": "// svc\n",
            "platform/common/build.gradle.kts": "// common\n",
            "empty/build.gradle.kts": "// nothing includes this\n",
        }
    )

    facts = _read_gradle(repo)

    assert sorted(facts.module_roots) == ["platform/common", "service"]


def test_an_included_module_without_a_manifest_is_listed(make_repo) -> None:
    repo = make_repo(
        {
            "settings.gradle": "include 'app', 'generated'\n",
            "build.gradle": "// root\n",
            "app/build.gradle": "// app\n",
            "generated/README.md": "code is generated\n",
        }
    )

    _, profile, _, _ = _scan(repo)

    assert "generated" in {module["path"] for module in profile["modules"]}


def test_a_broken_catalog_is_a_diagnostic(make_repo) -> None:
    repo = make_repo(
        {
            "gradle/libs.versions.toml": "[versions\nnot toml",
            "build.gradle.kts": "dependencies {\n    implementation(libs.anything)\n}\n",
        }
    )

    facts = _read_gradle(repo)

    assert [entry.kind for entry in facts.diagnostics] == [
        "version_catalog_parse_error"
    ]


def test_an_unknown_catalog_accessor_is_a_diagnostic(make_repo) -> None:
    repo = make_repo(
        {
            "gradle/libs.versions.toml": "[libraries]\nknown = 'g:a:1.0'\n",
            "build.gradle.kts": (
                "plugins {\n    alias(libs.plugins.missing)\n}\n"
            ),
        }
    )

    facts = _read_gradle(repo)

    assert [entry.kind for entry in facts.diagnostics] == ["unresolved_catalog_entry"]


# --- groupIds for spec7 --------------------------------------------------


def test_declared_group_ids_are_kept_for_spec7(spring_maven: Path) -> None:
    """FR-8 (``groupIds for spec7``): a fully qualified usage needs them.

    The repo's own groupId is not an external one, even though ``app``
    depends on its sibling ``com.acme:lib``: it is ``own_group_ids``.
    """
    facts = _read_maven(spring_maven, "app")

    assert "org.springframework.boot" in facts.group_ids
    assert "com.acme" not in facts.group_ids
    assert facts.own_group_ids == ["com.acme"]


def test_gradle_group_ids_reach_the_module_environment(spring_gradle: Path) -> None:
    """The groupIds a Groovy build declares are kept for spec7 (FR-8)."""
    facts = _read_gradle(spring_gradle, "service")

    assert "org.springframework.boot" in facts.group_ids
    assert "org.springframework.cloud" in facts.group_ids
    assert "com.example" in facts.group_ids


def test_the_scan_passes_group_ids_to_the_module_environment(make_repo) -> None:
    """``ModuleEnv.group_ids`` is what spec7 sees when it parses a ``.java`` file."""
    from migration_planner.scanner.contract import FileFacts

    repo = make_repo(
        {
            "pom.xml": (
                "<project><groupId>com.acme</groupId><artifactId>svc</artifactId>"
                "<version>1.0</version><dependencies><dependency>"
                "<groupId>org.springframework</groupId>"
                "<artifactId>spring-web</artifactId><version>6.1.0</version>"
                "</dependency></dependencies></project>"
            ),
            "src/main/java/A.java": "package com.acme; class A {}\n",
        }
    )
    seen: list[tuple[str, ...]] = []

    def extract(context):
        seen.append(context.env.group_ids)
        return FileFacts()

    contract.register_source_extractor("java", extract)
    scan(repo, out=repo / "p.json")

    assert seen[0] == ("org.springframework",)


# --- the fixtures end to end --------------------------------------------


def test_the_maven_fixture_summary(spring_maven: Path) -> None:
    result = scan(spring_maven, out=spring_maven / "p.json")

    assert result.summary.framework == "spring-boot"
    assert result.summary.framework_version == "3.3.4"
    assert "spring-boot 3.3.4" in result.summary.text()
    assert result.summary.dependencies == len(result.profile.dependencies)


def test_the_gradle_fixture_summary(spring_gradle: Path) -> None:
    result = scan(spring_gradle, out=spring_gradle / "p.json")

    assert result.summary.framework_version == "3.4.1"
    assert "spring-boot 3.4.1" in result.summary.text()


def test_a_scan_of_maven_and_gradle_is_deterministic(spring_maven: Path) -> None:
    first = scan(spring_maven, out=spring_maven / "a.json").profile
    second = scan(spring_maven, out=spring_maven / "b.json").profile

    assert [
        (entry.module, entry.key, entry.kind) for entry in first.dependencies
    ] == [(entry.module, entry.key, entry.kind) for entry in second.dependencies]
    assert first.inputs_hash == second.inputs_hash


def test_a_java_only_repo_gets_no_npm_or_template_facts(spring_maven: Path) -> None:
    """A Maven tree has Java facts (spec7) but no npm symbol and no template."""
    _, profile, _, _ = _scan(spring_maven)

    assert profile["templates"] == []
    assert not any(
        entry["key"].startswith("npm:") for entry in profile["symbols"]
    )
    # Spec7 fills ``symbols[]`` from the fixture's imports.
    assert any(
        entry["key"] == "maven:org.springframework.boot.SpringApplication"
        for entry in profile["symbols"]
    )


@pytest.mark.parametrize(
    "content",
    [
        "",
        "<project>",
        "<project></project>",
        "<project><dependencies/></project>",
        "<project><properties></properties></project>",
    ],
)
def test_a_minimal_or_truncated_pom_never_raises(make_repo, content: str) -> None:
    repo = make_repo({"pom.xml": content})

    result, profile, _, _ = _scan(repo)

    assert result.path is not None and result.path.is_file()
    assert profile["framework"] is None


@pytest.mark.parametrize(
    "content",
    [
        "",
        "dependencies {",
        "dependencies { implementation 'a:b",
        "plugins {",
        "ext {",
        "include(",
        "dependencies { implementation platform(",
        "@",
    ],
)
def test_a_truncated_build_file_never_raises(make_repo, content: str) -> None:
    repo = make_repo({"build.gradle": content})

    result, _, _, _ = _scan(repo)

    assert result.path is not None and result.path.is_file()


def test_both_readers_are_registered_for_their_kinds() -> None:
    assert builtin.MANIFEST_READERS["pom.xml"] is read_maven_manifests
    for kind in (
        "build.gradle",
        "build.gradle.kts",
        "settings.gradle",
        "libs.versions.toml",
        "gradle.properties",
    ):
        assert builtin.MANIFEST_READERS[kind] is read_gradle_manifests


# --- review fixes (026.6) ------------------------------------------------
#
# Each test pins one defect found when spec6 was reviewed: the profile must not
# claim a placeholder as a version, must not read outside the scan root, and
# must not drop or mis-resolve a common real-world form silently.

_POM = '<project xmlns="http://maven.apache.org/POM/4.0.0">'


def test_an_unresolved_boot_parent_version_is_not_a_version(make_repo) -> None:
    """FR-3 / AC-6: ``${boot.version}`` from outside the repo is not claimed."""
    repo = make_repo(
        {
            "pom.xml": _POM
            + "<groupId>com.acme</groupId><artifactId>svc</artifactId><version>1</version>"
            "<parent><groupId>org.springframework.boot</groupId>"
            "<artifactId>spring-boot-starter-parent</artifactId>"
            "<version>${boot.version}</version></parent></project>"
        }
    )

    facts = _read_maven(repo)

    assert [(f.name, f.version, f.raw) for f in facts.frameworks] == [
        ("spring-boot", "", "${boot.version}")
    ]
    assert [d.kind for d in facts.diagnostics] == ["unresolved_variable"]


def test_an_unresolved_boot_parent_falls_through_to_a_resolvable_bom(make_repo) -> None:
    """A later FR-3 source that does resolve wins over one that does not."""
    repo = make_repo(
        {
            "pom.xml": _POM
            + "<groupId>com.acme</groupId><artifactId>svc</artifactId><version>1</version>"
            "<parent><groupId>org.springframework.boot</groupId>"
            "<artifactId>spring-boot-starter-parent</artifactId>"
            "<version>${boot.version}</version></parent>"
            "<dependencyManagement><dependencies><dependency>"
            "<groupId>org.springframework.boot</groupId>"
            "<artifactId>spring-boot-dependencies</artifactId><version>3.3.4</version>"
            "<type>pom</type><scope>import</scope></dependency></dependencies>"
            "</dependencyManagement></project>"
        }
    )

    facts = _read_maven(repo)

    assert _frameworks(facts) == [("spring-boot", "3.3.4")]


def test_a_parent_above_the_scan_root_is_not_read(make_repo) -> None:
    """A scan of ``svc/`` reads ``svc/`` only, even with a default relativePath."""
    repo = make_repo(
        {
            "pom.xml": _POM
            + "<groupId>com.acme</groupId><artifactId>root</artifactId><version>1</version>"
            "<packaging>pom</packaging>"
            "<parent><groupId>org.springframework.boot</groupId>"
            "<artifactId>spring-boot-starter-parent</artifactId><version>3.3.0</version>"
            "</parent><properties><java.version>21</java.version></properties></project>",
            "svc/pom.xml": _POM
            + "<parent><groupId>com.acme</groupId><artifactId>root</artifactId>"
            "<version>1</version></parent><artifactId>svc</artifactId></project>",
        }
    )

    _, profile, _, config = _scan(repo / "svc")

    assert profile["modules"][0]["frameworks"] == []
    assert not any(key.endswith("java.version") for _, key in config)


def test_a_relative_path_to_a_directory_finds_the_parent(make_repo) -> None:
    """``<relativePath>../parent</relativePath>``: Maven appends ``pom.xml``."""
    repo = make_repo(
        {
            "parent/pom.xml": _POM
            + "<groupId>com.acme</groupId><artifactId>par</artifactId><version>1</version>"
            "<packaging>pom</packaging><properties><java.version>21</java.version>"
            "</properties></project>",
            "svc/pom.xml": _POM
            + "<parent><groupId>com.acme</groupId><artifactId>par</artifactId>"
            "<version>1</version><relativePath>../parent</relativePath></parent>"
            "<artifactId>svc</artifactId></project>",
        }
    )

    _, _, _, config = _scan(repo)

    assert config[("svc", "cfg:pom.xml#properties.java.version")]["value"] == "21"


def test_a_project_group_id_placeholder_is_interpolated(make_repo) -> None:
    """``<groupId>${project.groupId}</groupId>`` names a sibling module."""
    repo = make_repo(
        {
            "pom.xml": _POM
            + "<groupId>com.acme</groupId><artifactId>svc</artifactId><version>1</version>"
            "<dependencies><dependency><groupId>${project.groupId}</groupId>"
            "<artifactId>lib</artifactId><version>${project.version}</version>"
            "</dependency><dependency><groupId>${outside.group}</groupId>"
            "<artifactId>x</artifactId></dependency></dependencies></project>"
        }
    )

    facts = _read_maven(repo)

    assert {d.key: d.version for d in facts.dependencies} == {
        "maven:com.acme:lib": "1",
        "maven:${outside.group}:x": None,
    }
    assert [d.detail for d in facts.diagnostics] == ["${outside.group}"]
    assert "${outside.group}" not in facts.group_ids
    assert "${project.groupId}" not in facts.group_ids


def test_a_parent_project_version_means_the_childs_own_version(make_repo) -> None:
    """Maven inherits first, then interpolates: the child's version wins."""
    repo = make_repo(
        {
            "pom.xml": _POM
            + "<groupId>com.acme</groupId><artifactId>root</artifactId><version>1.0</version>"
            "<packaging>pom</packaging><modules><module>app</module></modules>"
            "<properties><lib.version>${project.version}</lib.version></properties>"
            "</project>",
            "app/pom.xml": _POM
            + "<parent><groupId>com.acme</groupId><artifactId>root</artifactId>"
            "<version>1.0</version></parent><artifactId>app</artifactId>"
            "<version>2.0</version><dependencies><dependency><groupId>x</groupId>"
            "<artifactId>y</artifactId><version>${lib.version}</version></dependency>"
            "</dependencies></project>",
        }
    )

    _, _, dependencies, config = _scan(repo)

    assert dependencies[("app", "dependency", "maven:x:y", "compile")]["version"] == "2.0"
    assert config[(".", "cfg:pom.xml#properties.lib.version")]["value"] == "1.0"


def test_an_unresolved_gradle_plugin_version_is_not_a_version(make_repo) -> None:
    """AC-7: ``version "$bootV"`` with no declaration is not claimed anywhere."""
    repo = make_repo(
        {"build.gradle": "plugins {\n    id 'org.springframework.boot' version \"$bootV\"\n}\n"}
    )

    facts = _read_gradle(repo)

    assert [(f.name, f.version, f.raw) for f in facts.frameworks] == [
        ("spring-boot", "", "$bootV")
    ]
    plugin = next(d for d in facts.dependencies if d.kind == "plugin")
    assert (plugin.version, plugin.range) == (None, "$bootV")
    assert [(d.kind, d.line) for d in facts.diagnostics] == [("unresolved_variable", 2)]


def test_an_unresolved_plugin_falls_through_to_a_platform_bom(make_repo) -> None:
    repo = make_repo(
        {
            "build.gradle.kts": (
                "plugins {\n    id(\"org.springframework.boot\") version \"$bootV\"\n}\n"
                "dependencies {\n"
                '    implementation(platform("org.springframework.boot:spring-boot-dependencies:3.3.4"))\n'
                "}\n"
            )
        }
    )

    assert _frameworks(_read_gradle(repo)) == [("spring-boot", "3.3.4")]


def test_a_plugin_applied_with_no_version_anywhere_is_boot_with_no_version(
    make_repo,
) -> None:
    """``apply plugin: 'org.springframework.boot'``: on Boot, version unknown."""
    repo = make_repo(
        {"build.gradle": "apply plugin: 'java'\napply plugin: 'org.springframework.boot'\n"}
    )

    facts = _read_gradle(repo)

    assert [(f.name, f.version, f.source) for f in facts.frameworks] == [
        ("spring-boot", "", "build.gradle#plugins")
    ]


def test_spring_initializr_ext_set_and_dotted_ext_resolve(make_repo) -> None:
    """``ext { set('x', 'v') }`` (Spring Initializr), ``ext.x = 'v'``, ``ext.set(…)``."""
    repo = make_repo(
        {
            "build.gradle": (
                "ext {\n"
                "    set('springCloudVersion', \"2023.0.0\")\n"
                "}\n"
                "ext.jacksonVersion = '2.17.2'\n"
                "project.ext.guavaVersion = '33.0.0-jre'\n"
                "ext.set('lombokVersion', '1.18.30')\n"
                "dependencies {\n"
                "    implementation \"com.fasterxml.jackson.core:jackson-databind:$jacksonVersion\"\n"
                "    implementation \"com.google.guava:guava:${guavaVersion}\"\n"
                "    compileOnly \"org.projectlombok:lombok:$lombokVersion\"\n"
                "}\n"
                "dependencyManagement {\n"
                "    imports {\n"
                "        mavenBom \"org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}\"\n"
                "    }\n"
                "}\n"
            )
        }
    )

    facts = _read_gradle(repo)

    assert {d.key: d.version for d in facts.dependencies} == {
        "maven:com.fasterxml.jackson.core:jackson-databind": "2.17.2",
        "maven:com.google.guava:guava": "33.0.0-jre",
        "maven:org.projectlombok:lombok": "1.18.30",
        "maven:org.springframework.cloud:spring-cloud-dependencies": "2023.0.0",
    }
    assert facts.diagnostics == []


def test_a_subprojects_own_gradle_properties_override_the_roots(make_repo) -> None:
    repo = make_repo(
        {
            "settings.gradle": "include 'svc'\n",
            "build.gradle": "",
            "gradle.properties": "libV=1.0\nrootOnly=9\n",
            "svc/build.gradle": (
                "dependencies {\n"
                '    implementation "a:b:$libV"\n'
                '    implementation "a:c:$rootOnly"\n'
                "}\n"
            ),
            "svc/gradle.properties": "libV=2.0\n",
        }
    )

    facts = _read_gradle(repo, "svc")

    assert {d.key: d.version for d in facts.dependencies} == {
        "maven:a:b": "2.0",
        "maven:a:c": "9",
    }


def test_a_catalog_plugin_in_string_notation_is_id_and_version(make_repo) -> None:
    """``[plugins] boot = "org.springframework.boot:3.3.1"`` is ``id:version``."""
    repo = make_repo(
        {
            "gradle/libs.versions.toml": '[plugins]\nboot = "org.springframework.boot:3.3.1"\n',
            "build.gradle.kts": "plugins {\n    alias(libs.plugins.boot)\n}\n",
        }
    )

    facts = _read_gradle(repo)

    assert [(d.key, d.version) for d in facts.dependencies] == [
        ("gradle-plugin:org.springframework.boot", "3.3.1")
    ]
    assert _frameworks(facts) == [("spring-boot", "3.3.1")]


def test_an_unknown_library_accessor_is_a_diagnostic(make_repo) -> None:
    """FR-8 never-silent: ``implementation(libs.typo)`` is reported, not dropped."""
    repo = make_repo(
        {
            "gradle/libs.versions.toml": "[libraries]\nknown = 'g:a:1.0'\n",
            "build.gradle.kts": (
                "dependencies {\n"
                "    implementation(libs.known)\n"
                "    implementation(libs.typo.lib)\n"
                "}\n"
            ),
        }
    )

    facts = _read_gradle(repo)

    assert [d.key for d in facts.dependencies] == ["maven:g:a"]
    assert [(d.kind, d.line, d.detail) for d in facts.diagnostics] == [
        ("unresolved_catalog_entry", 3, "libs.typo.lib")
    ]


def test_a_catalog_bundle_expands_to_its_libraries(make_repo) -> None:
    repo = make_repo(
        {
            "gradle/libs.versions.toml": (
                "[versions]\njackson = '2.17.2'\n"
                "[libraries]\n"
                "jackson-core = { module = 'com.fasterxml.jackson.core:jackson-core', version.ref = 'jackson' }\n"
                "jackson-databind = { module = 'com.fasterxml.jackson.core:jackson-databind', version.ref = 'jackson' }\n"
                "[bundles]\njackson = ['jackson-core', 'jackson-databind']\n"
            ),
            "build.gradle.kts": (
                "dependencies {\n"
                "    implementation(libs.bundles.jackson)\n"
                "    implementation(libs.bundles.missing)\n"
                "}\n"
            ),
        }
    )

    facts = _read_gradle(repo)

    assert {d.key: d.version for d in facts.dependencies} == {
        "maven:com.fasterxml.jackson.core:jackson-core": "2.17.2",
        "maven:com.fasterxml.jackson.core:jackson-databind": "2.17.2",
    }
    assert [(d.kind, d.detail) for d in facts.diagnostics] == [
        ("unresolved_catalog_entry", "libs.bundles.missing")
    ]


def test_a_missing_version_ref_is_a_diagnostic(make_repo) -> None:
    repo = make_repo(
        {
            "gradle/libs.versions.toml": (
                "[versions]\nx = '1.0'\n"
                "[libraries]\n"
                "bad = { module = 'g:bad', version.ref = 'nope' }\n"
            ),
            "build.gradle.kts": "dependencies {\n    implementation(libs.bad)\n}\n",
        }
    )

    facts = _read_gradle(repo)

    assert [(d.key, d.version) for d in facts.dependencies] == [("maven:g:bad", None)]
    assert [(d.kind, d.file, d.line) for d in facts.diagnostics] == [
        ("unresolved_catalog_entry", "gradle/libs.versions.toml", 4)
    ]


def test_kotlin_module_shorthand_and_groovy_varargs(make_repo) -> None:
    """``kotlin("stdlib")`` and ``implementation 'g:a:1', 'g:b:2'`` are not dropped."""
    repo = make_repo(
        {
            "build.gradle.kts": (
                "dependencies {\n"
                '    implementation(kotlin("stdlib"))\n'
                '    implementation(kotlin("reflect", "2.0.0"))\n'
                "}\n"
            ),
            "lib/build.gradle": (
                "dependencies {\n    implementation 'g:a:1', 'g:b:2'\n}\n"
            ),
        }
    )

    kotlin = _read_gradle(repo)
    groovy = _read_gradle(repo, "lib")

    assert {d.key: d.version for d in kotlin.dependencies} == {
        "maven:org.jetbrains.kotlin:kotlin-stdlib": None,
        "maven:org.jetbrains.kotlin:kotlin-reflect": "2.0.0",
    }
    assert {d.key: d.version for d in groovy.dependencies} == {
        "maven:g:a": "1",
        "maven:g:b": "2",
    }


def test_an_inherited_boot_version_names_the_declaring_script(make_repo) -> None:
    """The fallback source is the real root file, not a made-up ``gradle-root``."""
    repo = make_repo(
        {
            "settings.gradle.kts": (
                "pluginManagement {\n    plugins {\n"
                '        id("org.springframework.boot") version "3.3.4"\n'
                "    }\n}\n"
                'include("svc")\n'
            ),
            "svc/build.gradle.kts": (
                "dependencies {\n"
                '    implementation("org.springframework.boot:spring-boot-starter-web")\n'
                "}\n"
            ),
        }
    )

    facts = _read_gradle(repo, "svc")

    assert [(f.version, f.source) for f in facts.frameworks] == [
        ("3.3.4", "settings.gradle.kts#pluginManagement")
    ]


# --- review decisions (026.6): classpath plugin version, own groupIds ------


def test_a_buildscript_classpath_plugin_gives_the_boot_version(make_repo) -> None:
    """Classic layout: the plugin on the classpath, ``apply plugin:`` without a version."""
    repo = make_repo(
        {
            "build.gradle": (
                "buildscript {\n"
                "    ext { springBootVersion = '2.7.18' }\n"
                "    dependencies {\n"
                '        classpath "org.springframework.boot:spring-boot-gradle-plugin:${springBootVersion}"\n'
                '        classpath "io.spring.gradle:dependency-management-plugin:1.0.15.RELEASE"\n'
                "    }\n"
                "}\n"
                "apply plugin: 'java'\n"
                "apply plugin: 'org.springframework.boot'\n"
                "apply plugin: 'io.spring.dependency-management'\n"
            )
        }
    )

    facts = _read_gradle(repo)

    assert [(f.version, f.raw, f.source) for f in facts.frameworks] == [
        ("2.7.18", "${springBootVersion}", "build.gradle#buildscript")
    ]
    plugins = {d.key: d.version for d in facts.dependencies if d.kind == "plugin"}
    assert plugins["gradle-plugin:org.springframework.boot"] == "2.7.18"
    assert plugins["gradle-plugin:io.spring.dependency-management"] == "1.0.15.RELEASE"
    assert facts.diagnostics == []


def test_a_subproject_inherits_the_root_buildscript_classpath_version(make_repo) -> None:
    """The root's ``buildscript`` and ``ext`` reach a subproject's ``apply plugin:``."""
    repo = make_repo(
        {
            "settings.gradle": "include 'svc'\n",
            "build.gradle": (
                "buildscript {\n"
                "    ext { springBootVersion = '2.7.18' }\n"
                "    dependencies {\n"
                '        classpath "org.springframework.boot:spring-boot-gradle-plugin:${springBootVersion}"\n'
                "    }\n"
                "}\n"
            ),
            "svc/build.gradle": "apply plugin: 'org.springframework.boot'\n",
        }
    )

    root = _read_gradle(repo)
    svc = _read_gradle(repo, "svc")

    assert root.frameworks == []  # on the classpath, but not applied
    assert [(f.version, f.source) for f in svc.frameworks] == [
        ("2.7.18", "build.gradle#buildscript")
    ]
    assert svc.diagnostics == []


def test_a_gradle_module_s_own_group_is_not_an_external_group(make_repo) -> None:
    repo = make_repo(
        {
            "settings.gradle.kts": 'include("app", "lib")\n',
            "build.gradle.kts": 'allprojects {\n    group = "com.acme"\n}\n',
            "app/build.gradle.kts": (
                "dependencies {\n"
                '    implementation("com.acme:lib:1.0")\n'
                '    implementation("org.springframework:spring-web:6.1.0")\n'
                "}\n"
            ),
            "lib/build.gradle.kts": 'group = "com.acme.platform"\n',
        }
    )

    root = _read_gradle(repo)
    lib = _read_gradle(repo, "lib")

    assert root.own_group_ids == ["com.acme"]
    assert lib.own_group_ids == ["com.acme.platform"]
    # The reader of ``app`` cannot see the root's ``group``; the scan can.
    assert "com.acme" in _read_gradle(repo, "app").group_ids


def test_the_scan_removes_every_own_group_id_repo_wide(make_repo) -> None:
    """A sibling's groupId is the repo's own, even when another module declares it."""
    from migration_planner.scanner.contract import FileFacts

    repo = make_repo(
        {
            "pom.xml": (
                _POM + "<groupId>com.acme</groupId><artifactId>root</artifactId>"
                "<version>1</version><packaging>pom</packaging>"
                "<modules><module>app</module><module>lib</module></modules></project>"
            ),
            "app/pom.xml": (
                _POM + "<parent><groupId>com.acme</groupId><artifactId>root</artifactId>"
                "<version>1</version></parent><artifactId>app</artifactId>"
                "<dependencies>"
                "<dependency><groupId>com.acme.platform</groupId><artifactId>lib</artifactId>"
                "<version>1</version></dependency>"
                "<dependency><groupId>org.springframework</groupId>"
                "<artifactId>spring-web</artifactId><version>6.1.0</version></dependency>"
                "</dependencies></project>"
            ),
            "lib/pom.xml": (
                _POM + "<parent><groupId>com.acme</groupId><artifactId>root</artifactId>"
                "<version>1</version></parent><groupId>com.acme.platform</groupId>"
                "<artifactId>lib</artifactId></project>"
            ),
            "app/src/main/java/A.java": "package com.acme.app; class A {}\n",
        }
    )
    seen: list[tuple[str, ...]] = []

    def extract(context):
        seen.append(context.env.group_ids)
        return FileFacts()

    contract.register_source_extractor("java", extract)
    scan(repo, out=repo / "p.json")

    assert seen == [("org.springframework",)]


def test_an_external_parent_group_is_not_owned(make_repo) -> None:
    """A pom with no ``<groupId>`` under the starter parent does not own Spring's."""
    repo = make_repo(
        {
            "pom.xml": (
                _POM + "<parent><groupId>org.springframework.boot</groupId>"
                "<artifactId>spring-boot-starter-parent</artifactId>"
                "<version>3.3.4</version></parent><artifactId>svc</artifactId></project>"
            )
        }
    )

    facts = _read_maven(repo)

    assert facts.own_group_ids == []
    assert facts.group_ids == ["org.springframework.boot"]
