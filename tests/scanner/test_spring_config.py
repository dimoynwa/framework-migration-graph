"""Spring configuration files: canonical keys, profiles, secrets (spec 026.8).

Five groups, in the order the spec states them:

1. **Parsing**: the Java properties format (``=`` / ``:`` / whitespace, comments,
   continuation lines, ``\\uXXXX``) and YAML (nested maps, lists, multi-document,
   anchors, merge keys) — with a real line number for every key.
2. **Canonical keys**: relaxed binding, and the map-valued prefixes that must
   *not* be canonicalized.
3. **Profiles, kinds and tests**: from the file name, from
   ``spring.config.activate.on-profile``, ``application`` / ``bootstrap``, and
   ``test: true`` under ``src/test/``.
4. **Secrets**: a credential or a URL with user info is redacted, a placeholder
   is kept as written, and ``--no-values`` stores nothing.
5. **The fixture end to end**, plus the failure modes (an unparsable YAML is a
   diagnostic, never a lost scan).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from migration_keys.spring import (
    REDACTED,
    canonical_key,
    has_userinfo_url,
    is_secret_key,
    redact_value,
)
from migration_planner.scanner import builtin, contract
from migration_planner.scanner.discover import discover
from migration_planner.scanner.scan import _manifest_contexts, scan
from migration_planner.scanner.spring_config import (
    MANIFEST_KINDS,
    read_spring_config,
)

from .conftest import FIXTURES, read_profile, run_cli


@pytest.fixture(autouse=True)
def installed_registry():
    """``scan()`` installs nothing; a scan test asks for the shipped readers."""
    contract.reset_registry()
    builtin.install()
    yield
    contract.reset_registry()


@pytest.fixture()
def spring_config_repo(tmp_path: Path) -> Path:
    """The Spring config fixture: properties, YAML profiles, bootstrap, a broken file."""
    target = tmp_path / "spring-config"
    shutil.copytree(FIXTURES / "spring-config", target)
    return target


SPRING = "spring-boot-starter-parent"


def _pom(group: str = "com.acme", artifact: str = "svc") -> str:
    return (
        f"<project><groupId>{group}</groupId><artifactId>{artifact}</artifactId>"
        "<version>1.0.0</version></project>"
    )


def _read(repo: Path, module: str = "."):
    return read_spring_config(_manifest_contexts(discover(repo))[module])


def _entries(facts) -> dict[str, str | None]:
    """``{canonical key: value}`` of one reader run."""
    return {entry.key: entry.value for entry in facts.config}


def _all(facts) -> dict[tuple[str, str], dict]:
    """Every ``config[]`` entry keyed by ``(key, profile)``, for per-occurrence checks."""
    return {(entry.key, entry.profile or ""): entry.__dict__ for entry in facts.config}


def _scan(repo: Path, **kwargs):
    result = scan(repo, out=repo / "profile.json", **kwargs)
    return result, read_profile(repo / "profile.json")


# --- 1. parsing: .properties ---------------------------------------------


def test_the_equals_colon_and_whitespace_separators(make_repo) -> None:
    repo = make_repo(
        {
            "pom.xml": _pom(),
            "src/main/resources/application.properties": (
                "a.equals=1\n"
                "b.colon: 2\n"
                "c.space 3\n"
                "d.tab\t4\n"
                "e.bare\n"
            ),
        }
    )

    values = _entries(_read(repo))

    assert {key.split("#", 1)[1]: value for key, value in values.items()} == {
        "a.equals": "1",
        "b.colon": "2",
        "c.space": "3",
        "d.tab": "4",
        "e.bare": "",
    }


def test_comments_continuation_lines_and_unicode_escapes(make_repo) -> None:
    """FR-8a: ``#`` / ``!`` comments, ``\\`` continuation, ``\\uXXXX``."""
    repo = make_repo(
        {
            "pom.xml": _pom(),
            "src/main/resources/application.properties": (
                "# a comment\n"
                "! also a comment\n"
                "\n"
                "app.continued=one \\\n"
                "    two\n"
                "app.unicode=caf\\u00e9\n"
                "app.escaped=tab\\there\n"
            ),
        }
    )

    facts = _read(repo)
    values = {entry.key.split("#", 1)[1]: entry.value for entry in facts.config}

    # Java's rule: a continuation's leading whitespace on the next line is kept
    # as written, and `\ ` (escaped space) would be needed to join the words.
    assert values["app.continued"] == "one two"
    assert values["app.unicode"] == "café"
    assert values["app.escaped"] == "tab\there"


def test_a_continuation_line_is_one_entry_with_the_first_lines_number(
    make_repo,
) -> None:
    repo = make_repo(
        {
            "pom.xml": _pom(),
            "src/main/resources/application.properties": (
                "first=1\n"
                "app.long=a \\\n"
                "  b \\\n"
                "  c\n"
                "last=2\n"
            ),
        }
    )

    facts = _read(repo)
    entries = {entry.key.split("#", 1)[1]: entry for entry in facts.config}

    assert entries["app.long"].value == "a b c"
    assert entries["app.long"].line == 2
    assert entries["last"].line == 5


def test_a_comment_inside_a_continued_value_is_not_a_comment(make_repo) -> None:
    """A logical line's continuation is value text, whatever it starts with."""
    repo = make_repo(
        {
            "pom.xml": _pom(),
            "src/main/resources/application.properties": "app.x=a\\\n#notacomment\n",
        }
    )

    values = _entries(_read(repo))

    assert values["cfg:application.properties#app.x"] == "a#notacomment"


def test_a_comment_ending_in_a_backslash_does_not_swallow_the_next_line(
    make_repo,
) -> None:
    """Java's rule: a comment line never continues."""
    repo = make_repo(
        {
            "pom.xml": _pom(),
            "src/main/resources/application.properties": (
                "# a comment ending with a backslash \\\n"
                "server.servlet.context-path=/x\n"
                "! another \\\n"
                "server.port=8080\n"
            ),
        }
    )

    facts = _read(repo)

    assert {entry.key: entry.line for entry in facts.config} == {
        "cfg:application.properties#server.servlet.context-path": 2,
        "cfg:application.properties#server.port": 4,
    }
    assert facts.diagnostics == []


def test_a_multi_document_properties_file_is_split_by_profile(make_repo) -> None:
    """``#---`` (Boot 2.4+) splits a ``.properties`` file like ``---`` splits YAML."""
    repo = make_repo(
        {
            "pom.xml": _pom(),
            "src/main/resources/application.properties": (
                "server.port=8080\n"
                "#---\n"
                "spring.config.activate.on-profile=dev\n"
                "server.port=8081\n"
                "!---\n"
                "spring.config.activate.on-profile=prod\n"
                "server.port=9090\n"
            ),
        }
    )

    ports = sorted(
        (entry.profile, entry.value, entry.line)
        for entry in _read(repo).config
        if entry.key.endswith("#server.port")
    )

    assert ports == [("default", "8080", 1), ("dev", "8081", 4), ("prod", "9090", 7)]


def test_an_indented_separator_is_only_a_comment(make_repo) -> None:
    repo = make_repo(
        {
            "pom.xml": _pom(),
            "src/main/resources/application.properties": (
                "a.b=1\n  #---\nspring.config.activate.on-profile=dev\n"
            ),
        }
    )

    assert {entry.profile for entry in _read(repo).config} == {"dev"}


def test_a_line_that_is_not_a_property_is_a_diagnostic(make_repo) -> None:
    """Never silent: a dropped property is a dropped rule."""
    repo = make_repo(
        {
            "pom.xml": _pom(),
            "src/main/resources/application.properties": "=no-key\nkey=value\n",
        }
    )

    facts = _read(repo)

    assert [entry.value for entry in facts.config] == ["value"]
    assert [(entry.kind, entry.line) for entry in facts.diagnostics] == [
        ("unparsed_property", 1)
    ]


# --- 1. parsing: .yml / .yaml --------------------------------------------


def test_nested_yaml_maps_become_dotted_keys_with_real_lines(make_repo) -> None:
    repo = make_repo(
        {
            "pom.xml": _pom(),
            "src/main/resources/application.yml": (
                "spring:\n"
                "  datasource:\n"
                "    url: jdbc:h2:mem:x\n"
                "    hikari:\n"
                "      maximum-pool-size: 20\n"
                "server:\n"
                "  port: 9090\n"
            ),
        }
    )

    facts = _read(repo)
    entries = {entry.key.split("#", 1)[1]: entry for entry in facts.config}

    assert entries["spring.datasource.url"].value == "jdbc:h2:mem:x"
    assert entries["spring.datasource.url"].line == 3
    assert entries["spring.datasource.hikari.maximum-pool-size"].value == "20"
    assert entries["server.port"].line == 7


def test_yaml_lists_use_index_segments(make_repo) -> None:
    repo = make_repo(
        {
            "pom.xml": _pom(),
            "src/main/resources/application.yml": (
                "app:\n"
                "  features:\n"
                "    - checkout\n"
                "    - search\n"
                "  servers:\n"
                "    - name: one\n"
                "      port: 8080\n"
            ),
        }
    )

    values = {
        entry.key.split("#", 1)[1]: entry.value for entry in _read(repo).config
    }

    assert values["app.features[0]"] == "checkout"
    assert values["app.features[1]"] == "search"
    assert values["app.servers[0].name"] == "one"
    assert values["app.servers[0].port"] == "8080"


def test_an_empty_map_or_list_is_a_key_with_no_value(make_repo) -> None:
    """A rule asking "is this set" must not have to know the children."""
    repo = make_repo(
        {
            "pom.xml": _pom(),
            "src/main/resources/application.yml": "app:\n  features: []\n  extra:\n",
        }
    )

    values = {
        entry.key.split("#", 1)[1]: entry.value for entry in _read(repo).config
    }

    assert values["app.features"] == ""
    assert values["app.extra"] == ""


def test_an_anchor_and_a_merge_key_are_resolved(make_repo) -> None:
    """``<<: *base`` gives the merged keys, and a key written wins over it."""
    repo = make_repo(
        {
            "pom.xml": _pom(),
            "src/main/resources/application.yml": (
                "base: &base\n"
                "  pool: 10\n"
                "  timeout: 3000\n"
                "spring:\n"
                "  datasource:\n"
                "    <<: *base\n"
                "    timeout: 5000\n"
            ),
        }
    )

    values = {
        entry.key.split("#", 1)[1]: entry.value for entry in _read(repo).config
    }

    assert values["spring.datasource.pool"] == "10"
    assert values["spring.datasource.timeout"] == "5000"


def test_a_multi_document_yaml_is_split_by_profile(make_repo) -> None:
    repo = make_repo(
        {
            "pom.xml": _pom(),
            "src/main/resources/application.yml": (
                "server:\n"
                "  port: 8080\n"
                "---\n"
                "spring:\n"
                "  config:\n"
                "    activate:\n"
                "      on-profile: prod\n"
                "server:\n"
                "  port: 9090\n"
            ),
        }
    )

    facts = _read(repo)
    ports = {
        entry.profile: entry.value
        for entry in facts.config
        if entry.key == "cfg:application.properties#server.port"
    }

    assert ports == {"default": "8080", "prod": "9090"}


def test_the_legacy_spring_profiles_key_also_sets_the_profile(make_repo) -> None:
    repo = make_repo(
        {
            "pom.xml": _pom(),
            "src/main/resources/application.yml": (
                "spring:\n  profiles: legacy\napp:\n  name: x\n"
            ),
        }
    )

    profiles = {entry.profile for entry in _read(repo).config}

    assert profiles == {"legacy"}


def test_the_legacy_spring_profiles_list_sets_the_profile(make_repo) -> None:
    repo = make_repo(
        {
            "pom.xml": _pom(),
            "src/main/resources/application.yml": (
                "spring:\n  profiles:\n    - eu\n    - prod\napp:\n  name: x\n"
            ),
        }
    )

    assert {entry.profile for entry in _read(repo).config} == {"eu"}


def test_spring_profiles_active_does_not_make_the_document_a_profile(make_repo) -> None:
    """``spring.profiles.active`` activates a profile; its document is still ``default``."""
    repo = make_repo(
        {
            "pom.xml": _pom(),
            "src/main/resources/application.yml": (
                "spring:\n  profiles:\n    active: local\n"
                "  datasource:\n    url: jdbc:h2:mem\n"
            ),
            "src/main/resources/application.properties": (
                "spring.profiles.active=local\nserver.port=8080\n"
            ),
        }
    )

    assert {entry.profile for entry in _read(repo).config} == {"default"}


def test_the_on_profile_key_is_matched_under_relaxed_binding(make_repo) -> None:
    """``onProfile`` is ``on-profile``: the document is ``prod``."""
    repo = make_repo(
        {
            "pom.xml": _pom(),
            "src/main/resources/application.yml": (
                "server:\n  port: 8080\n---\n"
                "spring:\n  config:\n    activate:\n      onProfile: prod\n"
                "server:\n  port: 9090\n"
            ),
        }
    )

    ports = sorted(
        (entry.profile, entry.value)
        for entry in _read(repo).config
        if entry.key.endswith("#server.port")
    )

    assert ports == [("default", "8080"), ("prod", "9090")]


def test_an_unparsable_yaml_is_one_diagnostic(make_repo) -> None:
    repo = make_repo(
        {
            "pom.xml": _pom(),
            "src/main/resources/application.yml": "spring:\n  url: [unclosed\n",
        }
    )

    facts = _read(repo)

    assert facts.config == []
    assert [(entry.kind, entry.file) for entry in facts.diagnostics] == [
        ("yaml_parse_error", "src/main/resources/application.yml")
    ]
    assert facts.diagnostics[0].line == 3


def test_an_unparsable_file_does_not_lose_the_others(make_repo) -> None:
    repo = make_repo(
        {
            "pom.xml": _pom(),
            "src/main/resources/application.yml": "broken: [\n",
            "src/main/resources/application.properties": "server.port=8080\n",
        }
    )

    result, profile = _scan(repo)

    assert result.path is not None and result.path.is_file()
    assert [entry["value"] for entry in profile["config"]] == ["8080"]
    assert [entry["kind"] for entry in profile["diagnostics"]] == ["yaml_parse_error"]


# --- 2. canonical keys ----------------------------------------------------


def test_camel_case_becomes_kebab_case() -> None:
    """AC-8a: ``authenticationDatabase`` → ``authentication-database``."""
    assert (
        canonical_key("spring.data.mongodb.authenticationDatabase")
        == "spring.data.mongodb.authentication-database"
    )
    assert canonical_key("server.SERVER_PORT") == "server.server-port"
    assert canonical_key("a.b.snake_case") == "a.b.snake-case"


def test_a_map_valued_prefix_keeps_the_case_of_its_keys() -> None:
    """AC-8a: ``logging.level.com.Foo.BarService`` is a logger name, not a property."""
    assert (
        canonical_key("logging.level.com.Foo.BarService")
        == "logging.level.com.Foo.BarService"
    )
    assert (
        canonical_key("spring.jpa.properties.hibernate.dialect")
        == "spring.jpa.properties.hibernate.dialect"
    )
    assert (
        canonical_key("management.metrics.tags.Application")
        == "management.metrics.tags.Application"
    )


def test_a_gateway_route_metadata_key_keeps_its_case() -> None:
    assert (
        canonical_key("spring.cloud.gateway.routes[0].metadata.Connect-Timeout")
        == "spring.cloud.gateway.routes[0].metadata.Connect-Timeout"
    )


def test_the_raw_key_is_kept_when_it_differs(make_repo) -> None:
    """``raw_key`` is the written form, so a matcher can explain a mismatch."""
    repo = make_repo(
        {
            "pom.xml": _pom(),
            "src/main/resources/application.properties": (
                "spring.data.mongodb.authenticationDatabase=admin\n"
                "server.port=8080\n"
            ),
        }
    )

    facts = _read(repo)
    entries = {entry.key.split("#", 1)[1]: entry for entry in facts.config}

    assert entries["spring.data.mongodb.authentication-database"].raw_key == (
        "spring.data.mongodb.authenticationDatabase"
    )
    # A key already canonical has no raw form to keep.
    assert entries["server.port"].raw_key is None


def test_the_key_names_the_one_canonical_spring_file(make_repo) -> None:
    """025 FR-2.6: a rule says ``cfg:application.properties#…``, not the real path."""
    repo = make_repo(
        {
            "pom.xml": _pom(),
            "src/main/resources/application-prod.yml": "server:\n  port: 8443\n",
        }
    )

    facts = _read(repo)
    entry = facts.config[0]

    assert entry.key == "cfg:application.properties#server.port"
    # The real file is still recorded.
    assert entry.file == "src/main/resources/application-prod.yml"


# --- 3. profiles, kinds, tests --------------------------------------------


def test_the_profile_comes_from_the_file_name(make_repo) -> None:
    """AC-8a: ``application-prod.yml`` gives ``prod``; ``application.yml`` ``default``."""
    repo = make_repo(
        {
            "pom.xml": _pom(),
            "src/main/resources/application.yml": "a: 1\n",
            "src/main/resources/application-prod.yml": "a: 2\n",
            "src/main/resources/application-dev.properties": "a=3\n",
        }
    )

    profiles = sorted(entry.profile for entry in _read(repo).config)

    assert profiles == ["default", "dev", "prod"]


def test_bootstrap_keys_are_recorded_and_the_file_is_listed(make_repo) -> None:
    """AC-8a: ``kind: bootstrap`` and ``modules[].spring_config_files``."""
    repo = make_repo(
        {
            "pom.xml": _pom(),
            "src/main/resources/bootstrap.yml": (
                "spring:\n  application:\n    name: shop\n"
            ),
        }
    )

    _, profile = _scan(repo)
    entry = profile["config"][0]

    assert entry["kind"] == "bootstrap"
    assert entry["key"] == "cfg:application.properties#spring.application.name"
    assert entry["value"] == "shop"
    assert profile["modules"][0]["spring_config_files"] == [
        "src/main/resources/bootstrap.yml"
    ]


def test_an_application_file_is_listed_too(make_repo) -> None:
    repo = make_repo(
        {
            "pom.xml": _pom(),
            "src/main/resources/application.yml": "a: 1\n",
            "config/application-prod.properties": "b=2\n",
        }
    )

    _, profile = _scan(repo)

    assert profile["modules"][0]["spring_config_files"] == [
        "config/application-prod.properties",
        "src/main/resources/application.yml",
    ]


def test_a_file_under_src_test_is_a_test_fact(make_repo) -> None:
    """AC-8a: ``src/test/resources`` → ``test: true``."""
    repo = make_repo(
        {
            "pom.xml": _pom(),
            "src/main/resources/application.properties": "app.mode=prod\n",
            "src/test/resources/application.properties": "app.mode=test\n",
        }
    )

    facts = _read(repo)
    flags = sorted(
        (entry.test, entry.value) for entry in facts.config if entry.value in ("prod", "test")
    )

    assert flags == [(False, "prod"), (True, "test")]


@pytest.mark.parametrize(
    "source_set", ["integrationTest", "componentTest", "acceptanceTest", "apiTest", "it"]
)
def test_a_file_under_a_gradle_test_source_set_is_a_test_fact(
    make_repo, source_set: str
) -> None:
    """``src/integrationTest/resources`` is test config, like ``src/test/resources``."""
    repo = make_repo(
        {
            "pom.xml": _pom(),
            "src/main/resources/application.properties": "app.mode=prod\n",
            f"src/{source_set}/resources/application.properties": "app.mode=test\n",
        }
    )

    flags = sorted((entry.test, entry.value) for entry in _read(repo).config)

    assert flags == [(False, "prod"), (True, "test")]


def test_no_include_tests_drops_a_test_source_set(make_repo) -> None:
    repo = make_repo(
        {
            "pom.xml": _pom(),
            "src/main/resources/application.properties": "app.mode=prod\n",
            "src/integrationTest/resources/application.properties": "app.mode=test\n",
            "src/integrationTest/java/com/acme/AIT.java": (
                "package com.acme;\nimport org.junit.jupiter.api.Test;\nclass AIT {}\n"
            ),
        }
    )

    _, profile = _scan(repo, include_tests=False)

    assert [entry["value"] for entry in profile["config"]] == ["prod"]
    assert profile["modules"][0]["spring_config_files"] == [
        "src/main/resources/application.properties"
    ]


def test_the_same_key_in_two_profiles_is_two_entries(make_repo) -> None:
    """FR-8a: never merged by key alone, so "only in prod" stays visible."""
    repo = make_repo(
        {
            "pom.xml": _pom(),
            "src/main/resources/application.properties": "app.mode=default\n",
            "src/main/resources/application-prod.properties": "app.mode=prod\n",
        }
    )

    _, profile = _scan(repo)
    entries = [
        entry for entry in profile["config"] if entry["key"].endswith("#app.mode")
    ]

    assert sorted((entry["profile"], entry["value"]) for entry in entries) == [
        ("default", "default"),
        ("prod", "prod"),
    ]


def test_a_module_gets_its_own_config_files(make_repo) -> None:
    """A multi-module repo keeps each service's config under its own module."""
    repo = make_repo(
        {
            "pom.xml": (
                "<project><groupId>com.acme</groupId><artifactId>parent</artifactId>"
                "<version>1</version><packaging>pom</packaging>"
                "<modules><module>api</module></modules></project>"
            ),
            "api/pom.xml": _pom("com.acme", "api"),
            "api/src/main/resources/application.yml": "server:\n  port: 8081\n",
        }
    )

    _, profile = _scan(repo)
    by_path = {module["path"]: module for module in profile["modules"]}

    assert by_path["api"]["spring_config_files"] == [
        "api/src/main/resources/application.yml"
    ]
    entry = profile["config"][0]
    assert entry["module"] == "api"
    assert entry["file"] == "api/src/main/resources/application.yml"


def test_an_npm_module_in_a_java_repo_has_no_spring_config(make_repo) -> None:
    """``web/application.yml`` of an Angular module is not Spring's."""
    repo = make_repo(
        {
            "pom.xml": _pom(),
            "src/main/resources/application.yml": "server:\n  port: 8080\n",
            "web/package.json": '{"name": "web", "dependencies": {"@angular/core": "19.0.0"}}',
            "web/application.yml": "foo: bar\n",
        }
    )

    _, profile = _scan(repo)
    by_path = {module["path"]: module for module in profile["modules"]}

    assert by_path["web"]["spring_config_files"] == []
    assert [entry["key"] for entry in profile["config"] if entry["module"] == "web"] == []
    assert "cfg:application.properties#server.port" in {
        entry["key"] for entry in profile["config"]
    }


def test_a_repo_with_no_java_build_has_no_spring_config(make_repo) -> None:
    repo = make_repo(
        {
            "package.json": '{"name": "web", "dependencies": {"@angular/core": "19.0.0"}}',
            "application.yml": "foo: bar\n",
            "config/application.properties": "a.b=1\n",
        }
    )

    _, profile = _scan(repo)

    assert not any(entry["key"].startswith("cfg:application.properties#") for entry in profile["config"])
    assert all(module["spring_config_files"] == [] for module in profile["modules"])


def test_shared_root_config_next_to_a_tooling_package_json_is_read(make_repo) -> None:
    """``.`` with a commitlint ``package.json`` and ``svc/pom.xml``: ``config/`` is Spring's."""
    repo = make_repo(
        {
            "package.json": '{"name": "tooling", "devDependencies": {"husky": "9.0.0"}}',
            "svc/pom.xml": _pom(),
            "config/application.yml": "server:\n  port: 8080\n",
        }
    )

    _, profile = _scan(repo)

    entry = next(
        entry for entry in profile["config"]
        if entry["key"] == "cfg:application.properties#server.port"
    )
    assert entry["module"] == "."
    assert entry["file"] == "config/application.yml"


def test_a_repo_without_spring_config_has_no_config_facts(make_repo) -> None:
    repo = make_repo({"pom.xml": _pom(), "src/main/java/A.java": "class A {}\n"})

    _, profile = _scan(repo)

    assert profile["config"] == []
    assert profile["modules"][0]["spring_config_files"] == []


# --- 4. secrets and values ----------------------------------------------


def test_a_password_is_redacted(make_repo) -> None:
    """AC-8a: ``spring.datasource.password=s3cret`` → ``<redacted>``."""
    repo = make_repo(
        {
            "pom.xml": _pom(),
            "src/main/resources/application.properties": "spring.datasource.password=s3cret\n",
        }
    )

    entry = _read(repo).config[0]

    assert entry.value == REDACTED
    assert "s3cret" not in json.dumps(
        {"value": entry.value, "raw_key": entry.raw_key}
    )


def test_client_secret_and_a_userinfo_url_are_redacted() -> None:
    """AC-8a: a ``client-secret`` key and a ``scheme://u:p@`` value."""
    assert redact_value("security.oauth2.client.client-secret", "abc") == REDACTED
    assert (
        redact_value("spring.datasource.url", "jdbc:postgresql://u:p@host/db")
        == REDACTED
    )
    assert has_userinfo_url("jdbc:postgresql://u:p@host/db") is True
    assert has_userinfo_url("jdbc:postgresql://host/db") is False


@pytest.mark.parametrize(
    "key",
    [
        "spring.datasource.password",
        "spring.datasource.passwd",
        "app.client-secret",
        "app.api-key",
        "app.apikey",
        "app.private-key",
        "app.credential",
        "auth.token",
        "app.hmac-secret-key",
        "app.hmacSecretKey",
        "spring.cloud.vault.token",
        "server.ssl.key-store-password",
        "app.refresh-token",
    ],
)
def test_every_secret_key_is_recognized(key: str) -> None:
    assert is_secret_key(key) is True
    assert redact_value(key, "hunter2") == REDACTED


@pytest.mark.parametrize(
    "key",
    [
        "spring.datasource.url",
        "server.port",
        "app.tokens-per-second",
        "app.secrets-count",
        "spring.security.oauth2.client.provider.idp.token-uri",
        "app.jwt.access-token-validity-seconds",
        "app.jwt.secret-header-name",
    ],
)
def test_a_key_without_a_secret_word_is_not_redacted(key: str) -> None:
    """A word must be a whole token: ``tokens-per-second`` is not a token."""
    assert redact_value(key, "value") == "value"


def test_a_placeholder_is_kept_as_written() -> None:
    """AC-8a: ``${DB_PASSWORD}`` is a reference, never resolved."""
    assert redact_value("spring.datasource.password", "${DB_PASSWORD}") == (
        "${DB_PASSWORD}"
    )
    assert redact_value("server.port", "${PORT:8080}") == "${PORT:8080}"


def test_yaml_secrets_are_redacted_too(make_repo) -> None:
    repo = make_repo(
        {
            "pom.xml": _pom(),
            "src/main/resources/application.yml": (
                "spring:\n"
                "  security:\n"
                "    oauth2:\n"
                "      client:\n"
                "        registration:\n"
                "          acme:\n"
                "            client-secret: topsecret\n"
            ),
        }
    )

    entry = _read(repo).config[0]

    assert entry.key.endswith("registration.acme.client-secret")
    assert entry.value == REDACTED


def test_a_long_value_is_truncated_to_200_characters() -> None:
    long_value = "x" * 500

    assert len(redact_value("app.banner", long_value) or "") == 200


def test_no_values_stores_no_value_at_all(make_repo) -> None:
    """AC-8a: ``--no-values`` → ``value`` is ``null`` in every ``config[]`` entry."""
    repo = make_repo(
        {
            "pom.xml": _pom(),
            "package.json": '{"name": "demo", "engines": {"node": ">=18"}}',
            "src/main/resources/application.properties": "server.port=8080\n",
        }
    )

    _, profile = _scan(repo, no_values=True)

    # Every entry, not only the Spring ones: the Maven and npm readers' too.
    assert profile["config"]
    assert [entry["value"] for entry in profile["config"]] == [None] * len(
        profile["config"]
    )


def test_no_values_changes_the_inputs_hash() -> None:
    """FR-9: an output-changing option is part of ``inputs_hash``."""
    from migration_planner.scanner.profile import inputs_hash

    with_values = inputs_hash([("a", b"x")], options={"no_values": False})
    without_values = inputs_hash([("a", b"x")], options={"no_values": True})

    assert with_values != without_values


def test_the_scan_puts_no_values_in_the_inputs_hash(make_repo) -> None:
    """The option really travels into the hash ``scan()`` computes."""
    repo = make_repo(
        {
            "pom.xml": _pom(),
            "src/main/resources/application.properties": "server.port=8080\n",
        }
    )

    with_values, _ = _scan(repo)
    without_values = scan(repo, out=repo / "other.json", no_values=True)

    assert with_values.profile.inputs_hash != without_values.profile.inputs_hash


def test_the_cli_flag_reaches_the_profile(make_repo) -> None:
    repo = make_repo(
        {
            "pom.xml": _pom(),
            "src/main/resources/application.properties": "server.port=8080\n",
        }
    )

    code, _, _ = run_cli(str(repo), "--no-values")

    assert code == 0
    profile = read_profile(repo / ".migration" / "profile.json")
    assert [entry["value"] for entry in profile["config"]] == [None]


def test_the_cli_documents_no_values() -> None:
    code, stdout, _ = run_cli("--help")

    assert code == 0
    assert "--no-values" in stdout


# --- 5. the fixture end to end ------------------------------------------


def test_the_fixture_profile(spring_config_repo: Path) -> None:
    result, profile = _scan(spring_config_repo)
    by_key = {(entry["key"], entry["profile"]): entry for entry in profile["config"]}

    key = "cfg:application.properties#"

    def only(
        name: str,
        profile_name: str = "default",
        kind: str = "application",
        test: bool = False,
    ) -> dict:
        """The one entry for this key, profile, file kind and test flag.

        A key legitimately repeats — a profile file, a bootstrap file and a
        ``src/test`` file each set ``spring.application.name`` — so a lookup has
        to name which occurrence it means.
        """
        found = [
            entry
            for entry in profile["config"]
            if entry["key"] == key + name
            and entry["profile"] == profile_name
            and (entry["kind"] or "application") == kind
            and entry["test"] is test
        ]
        assert len(found) == 1, (name, profile_name, kind, test, found)
        return found[0]

    # .properties
    assert only("spring.application.name")["value"] == "config-svc"
    assert only("server.port")["value"] == "8080"
    # relaxed binding, and the map-valued prefix
    assert (key + "spring.data.mongodb.authentication-database", "default") in by_key
    assert (
        key + "logging.level.com.acme.shop.web.CatalogController", "default"
    ) in by_key
    # secrets: the main file's password and URL, the test file's empty password
    assert only("spring.datasource.password")["value"] == REDACTED
    assert only("spring.datasource.url")["value"] == REDACTED
    assert only("spring.datasource.username")["value"] == "${DB_USER}"
    # YAML, both documents of the profile file
    assert only("spring.datasource.hikari.maximum-pool-size", "prod")["value"] == "40"
    assert only("server.port", "prod")["value"] == "8443"
    assert only("app.debug", "staging")["value"] == "true"
    # bootstrap
    assert only("spring.cloud.config.uri", kind="bootstrap")["kind"] == "bootstrap"
    assert only("spring.cloud.config.password", kind="bootstrap")["value"] == (
        "${CONFIG_PASSWORD}"
    )
    # src/test: the same key in a second place, flagged
    test_entries = [entry for entry in profile["config"] if entry["test"]]
    assert test_entries and all(
        entry["file"].startswith("src/test/") for entry in test_entries
    )
    assert only("spring.datasource.url")["test"] is False
    assert only("spring.datasource.url")["file"] == (
        "src/main/resources/application.properties"
    )
    # the broken file is one diagnostic, not a lost scan
    assert [(entry["kind"], entry["file"]) for entry in profile["diagnostics"]] == [
        ("yaml_parse_error", "config/application-broken.yml")
    ]
    assert result.summary.framework == "spring-boot"


def test_the_fixture_lists_every_config_file(spring_config_repo: Path) -> None:
    _, profile = _scan(spring_config_repo)

    assert profile["modules"][0]["spring_config_files"] == [
        "config/application-broken.yml",
        "src/main/resources/application-prod.yml",
        "src/main/resources/application.properties",
        "src/main/resources/bootstrap.yml",
        "src/test/resources/application.yml",
    ]


def test_the_summary_counts_config_entries(spring_config_repo: Path) -> None:
    result = scan(spring_config_repo, out=spring_config_repo / "p.json")

    assert result.summary.config == len(result.profile.config)
    assert result.summary.config > 0


def test_no_secret_of_the_fixture_reaches_the_profile(spring_config_repo: Path) -> None:
    """AC-8a: ``grep`` of the profile for a known secret finds none."""
    scan(spring_config_repo, out=spring_config_repo / "p.json")
    text = (spring_config_repo / "p.json").read_text()
    source = (
        FIXTURES / "spring-config" / "src/main/resources/application.properties"
    ).read_text()

    assert "s3cret" not in text
    for line in source.splitlines():
        if "password=" in line and "${" not in line:
            secret = line.split("=", 1)[1]
            assert secret not in text


def test_a_scan_of_spring_config_is_deterministic(spring_config_repo: Path) -> None:
    first = scan(spring_config_repo, out=spring_config_repo / "a.json").profile
    second = scan(spring_config_repo, out=spring_config_repo / "b.json").profile

    assert [(entry.key, entry.value, entry.profile) for entry in first.config] == [
        (entry.key, entry.value, entry.profile) for entry in second.config
    ]
    assert first.inputs_hash == second.inputs_hash


def test_the_reader_is_registered_for_the_spring_config_kind() -> None:
    assert builtin.MANIFEST_READERS["spring.config"] is read_spring_config
    assert set(MANIFEST_KINDS) == {"spring.config"}
