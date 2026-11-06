"""Normalizer tests (spec 025 AC-1): the real Angular cases, deterministic."""

from __future__ import annotations

from migration_oracle.models.entities import (
    AffectedEntity,
    EntityKind,
    EntityRole,
    MigrationEntitiesBatch,
)
from migration_oracle.pipeline.canonical import canonicalize_batch, profile_for
from migration_oracle.pipeline.canonical.api_index import HopApiIndex, build_hop_index


def _batch(*groups: list[AffectedEntity]) -> MigrationEntitiesBatch:
    return MigrationEntitiesBatch(
        entities=[
            {
                "source_section": "breaking_change",
                "title": f"rule {number}",
                "change_type": "breaking_change",
                "reason": "r",
                "scopes": [{"scope": "api-surface", "severity": "high"}],
                "entities": [e.model_dump() for e in group],
            }
            for number, group in enumerate(groups)
        ]
    )


def _affected(kind: str, name: str, role: str = "removed", package: str = "") -> AffectedEntity:
    return AffectedEntity(kind=EntityKind(kind), name=name, role=EntityRole(role), package=package)


def _canonical(batch: MigrationEntitiesBatch, index: HopApiIndex | None = None):
    return canonicalize_batch(
        batch,
        profile=profile_for("angular"),
        from_version="19.2.0",
        to_version="20.0.0",
        index=index
        if index is not None
        else HopApiIndex.unavailable(("19.2.0", "20.0.0")),
    )


def _one(index: HopApiIndex | None = None, **kwargs):
    batch = _batch([_affected(**kwargs)])
    result = _canonical(batch, index)
    return result.rules[0].occurrences[0].to_canonical()


def _fixture_index() -> HopApiIndex:
    return build_hop_index(
        ("19.2.0", "20.0.0"),
        [
            {
                "@angular/core": {
                    "InjectFlags": ["Static", "Optional"],
                    "Attribute": [],
                },
                "@angular/core/rxjs-interop": {"RxResourceOptions": []},
                "@angular/core/testing": {"TestBed": ["get", "inject"]},
                "@angular/router": {"Router": []},
            }
        ],
    )


# --- AC-1: package spellings ---------------------------------------------------


def test_three_package_spellings_split_to_package_and_bare_symbol() -> None:
    index = _fixture_index()
    a = _one(index, kind="class", name="@angular/core InjectFlags")
    b = _one(index, kind="class", name="@angular/router:Router")
    c = _one(index, kind="class", name="@angular/core/rxjs-interop RxResourceOptions")
    assert (a.package, a.symbol, a.name) == ("@angular/core", "InjectFlags", "InjectFlags")
    assert a.key == "npm:@angular/core#InjectFlags"
    assert (b.package, b.symbol, b.name) == ("@angular/router", "Router", "Router")
    assert b.key == "npm:@angular/router#Router"
    assert (c.package, c.symbol, c.name) == (
        "@angular/core/rxjs-interop",
        "RxResourceOptions",
        "RxResourceOptions",
    )
    assert c.key == "npm:@angular/core/rxjs-interop#RxResourceOptions"


def test_duplicate_symbols_collapse_into_one_key() -> None:
    index = _fixture_index()
    batch = _batch(
        [_affected(kind="class", name="InjectFlags")],
        [_affected(kind="class", name="@angular/core InjectFlags")],
    )
    result = _canonical(batch, index)
    keys = {o.to_canonical().key for r in result.rules for o in r.occurrences}
    assert keys == {"npm:@angular/core#InjectFlags"}


# --- AC-1: member split -----------------------------------------------------------


def test_testbed_get_as_class_and_property_gets_one_member_key() -> None:
    index = _fixture_index()
    batch = _batch(
        [
            _affected(kind="class", name="TestBed.get", role="removed"),
            _affected(kind="property", name="TestBed.get", role="mentioned"),
        ]
    )
    result = _canonical(batch, index)
    kinds = {o.to_canonical().kind.value for o in result.rules[0].occurrences}
    keys = {o.to_canonical().key for o in result.rules[0].occurrences}
    assert kinds == {"member"}
    assert keys == {"npm:@angular/core/testing#TestBed.get"}


def test_bare_option_gets_owner_from_replacement_symbol() -> None:
    index = build_hop_index(
        ("19.2.0", "20.0.0"),
        [{"@angular/core": {"provideCheckNoChangesConfig": ["exhaustive", "interval"]}}],
    )
    batch = _batch(
        [
            _affected(kind="property", name="exhaustive", role="removed"),
            _affected(kind="class", name="provideCheckNoChangesConfig", role="replacement"),
        ]
    )
    result = _canonical(batch, index)
    entity = result.rules[0].occurrences[0].to_canonical()
    assert entity.kind.value == "member"
    assert entity.name == "provideCheckNoChangesConfig.exhaustive"
    assert entity.key == "npm:@angular/core#provideCheckNoChangesConfig.exhaustive"
    assert entity.verified == "true"


def test_bare_option_without_single_owner_stays_bare_and_unverified() -> None:
    entity = _one(kind="property", name="exhaustive")
    assert entity.kind.value == "property"
    assert entity.name == "exhaustive"
    assert entity.key == "cfg:exhaustive"
    assert entity.verified == "false"


# --- AC-1: syntax and diagnostics ---------------------------------------------------


def test_template_operators_become_syntax() -> None:
    for token in ("in", "void", "@if", "@for", "@defer"):
        entity = _one(kind="property", name=token, role="mentioned")
        assert entity.kind.value == "syntax", token
        assert entity.name == token
        assert entity.key == f"syntax:angular-template#{token}"
        assert entity.verified == "true"


def test_ng_diagnostic_code_becomes_diagnostic() -> None:
    entity = _one(kind="property", name="NG8115", role="mentioned")
    assert entity.kind.value == "diagnostic"
    assert entity.key == "diag:NG8115"
    assert entity.verified == "true"


# --- AC-1: config keys ------------------------------------------------------------


def test_engines_node_gets_package_json() -> None:
    entity = _one(kind="property", name="engines.node", role="mentioned")
    assert entity.kind.value == "property"
    assert entity.file == "package.json"
    assert entity.key == "cfg:package.json#engines.node"
    assert entity.verified == "true"


def test_unknown_config_prefix_is_unverified() -> None:
    entity = _one(kind="property", name="someUnknown.section.key", role="mentioned")
    assert entity.file == ""
    assert entity.key == "cfg:someUnknown.section.key"
    assert entity.verified == "false"


# --- AC-1: cleaning --------------------------------------------------------------


def test_decorator_at_sign_stripped() -> None:
    index = _fixture_index()
    entity = _one(index, kind="class", name="@Attribute")
    assert entity.name == "Attribute"
    assert entity.key == "npm:@angular/core#Attribute"


def test_backticks_quotes_and_trailing_parens_are_cleaned() -> None:
    index = _fixture_index()
    entity = _one(index, kind="class", name="`InjectFlags`")
    assert entity.name == "InjectFlags"
    entity = _one(index, kind="member", name="TestBed.inject()")
    assert entity.name == "TestBed.inject"


# --- dependencies -------------------------------------------------------------------


def test_npm_dependency_key() -> None:
    entity = _one(kind="dependency", name="@angular/router", role="mentioned")
    assert entity.kind.value == "dependency"
    assert entity.name == "@angular/router"
    assert entity.key == "npm:@angular/router"
    assert entity.verified == "true"


# --- AC-5: Spring Boot / WildFly no-op ------------------------------------------------


def _maven_batch() -> MigrationEntitiesBatch:
    return MigrationEntitiesBatch(
        entities=[
            {
                "source_section": "breaking_change",
                "title": "spring rule",
                "change_type": "breaking_change",
                "reason": "r",
                "scopes": [{"scope": "api-surface", "severity": "high"}],
                "entities": [
                    _affected(
                        kind="class",
                        name="org.springframework.security.config.annotation.web.configuration.WebSecurityConfigurerAdapter",
                    ).model_dump(),
                    _affected(kind="property", name="spring.datasource.url").model_dump(),
                    _affected(kind="dependency", name="io.vertx:vertx-core").model_dump(),
                ],
            }
        ]
    )


def test_spring_boot_names_byte_for_byte_and_keys_are_maven_or_cfg() -> None:
    raw = _maven_batch()
    result = canonicalize_batch(
        raw, profile=profile_for("spring-boot"), from_version="3.4.0", to_version="3.5.0"
    )
    occurrences = result.rules[0].occurrences
    fqcn = "org.springframework.security.config.annotation.web.configuration.WebSecurityConfigurerAdapter"
    assert occurrences[0].name == fqcn
    assert occurrences[0].key == f"maven:{fqcn}"
    assert occurrences[1].name == "spring.datasource.url"
    assert occurrences[1].key == "cfg:application.properties#spring.datasource.url"
    assert occurrences[2].name == "io.vertx:vertx-core"
    assert occurrences[2].key == "maven:io.vertx:vertx-core"
    for occurrence in occurrences:
        # no maven API index yet: honest "unchecked", never "true"
        assert occurrence.verified == "unchecked"
        assert occurrence.name == occurrence.raw_name  # byte-for-byte


def test_wildfly_property_key_without_file() -> None:
    batch = MigrationEntitiesBatch(
        entities=[
            {
                "source_section": "breaking_change",
                "title": "wildfly rule",
                "change_type": "breaking_change",
                "reason": "r",
                "scopes": [{"scope": "config", "severity": "medium"}],
                "entities": [
                    _affected(kind="property", name="messaging-activemq").model_dump()
                ],
            }
        ]
    )
    result = canonicalize_batch(
        batch, profile=profile_for("wildfly"), from_version="35.0.0", to_version="36.0.0"
    )
    entity = result.rules[0].occurrences[0]
    assert entity.key == "cfg:messaging-activemq"
    assert entity.name == "messaging-activemq"


def test_unknown_framework_defaults_to_maven_noop() -> None:
    batch = _maven_batch()
    result = canonicalize_batch(
        batch, profile=profile_for("stub_framework"), from_version="1.0.0", to_version="2.0.0"
    )
    for occurrence in result.rules[0].occurrences:
        assert occurrence.name == occurrence.raw_name

# --- review fixes (2026-11-06) ----------------------------------------------------


def test_hash_package_separator_is_split() -> None:
    entity = _one(_fixture_index(), kind="class", name="@angular/core#InjectFlags")
    assert entity.package == "@angular/core"
    assert entity.name == "InjectFlags"
    assert entity.key == "npm:@angular/core#InjectFlags"
    assert entity.verified == "true"


def test_llm_declared_syntax_kind_is_kept_for_unlisted_token() -> None:
    entity = _one(kind="syntax", name="track")
    assert entity.kind == EntityKind.SYNTAX
    assert entity.key == "syntax:angular-template#track"


def test_llm_declared_diagnostic_kind_is_kept() -> None:
    entity = _one(kind="diagnostic", name="NG0911")
    assert entity.kind == EntityKind.DIAGNOSTIC
    assert entity.key == "diag:NG0911"


def test_non_identifier_bare_property_gets_no_owner() -> None:
    batch = _batch(
        [
            _affected("class", "provideNgReflectAttributes", "replacement"),
            _affected("property", "ng-reflect-*", "removed"),
        ]
    )
    result = _canonical(batch, _fixture_index())
    entity = result.rules[0].occurrences[1].to_canonical()
    assert entity.kind == EntityKind.PROPERTY
    assert entity.name == "ng-reflect-*"
    assert entity.key == "cfg:ng-reflect-*"
    assert entity.verified == "false"
    assert "owner-skipped:not-identifier" in result.rules[0].occurrences[1].applied


def test_bare_option_owner_taken_from_index_over_replacement() -> None:
    """`useNgZoneOnStable` belongs to the removed function, not its replacement."""
    index = build_hop_index(
        ("19.2.0", "20.0.0"),
        [
            {
                "@angular/core": {
                    "provideExperimentalCheckNoChangesForDebug": ["interval", "useNgZoneOnStable"],
                    "provideCheckNoChangesConfig": ["exhaustive", "interval"],
                }
            }
        ],
    )
    batch = _batch(
        [
            _affected("class", "provideExperimentalCheckNoChangesForDebug", "removed"),
            _affected("class", "provideCheckNoChangesConfig", "replacement"),
            _affected("property", "useNgZoneOnStable", "removed"),
            _affected("property", "exhaustive", "co-required"),
        ]
    )
    result = _canonical(batch, index)
    ng_zone = result.rules[0].occurrences[2]
    exhaustive = result.rules[0].occurrences[3]
    assert ng_zone.key == "npm:@angular/core#provideExperimentalCheckNoChangesForDebug.useNgZoneOnStable"
    assert ng_zone.verified == "true"
    assert "owner-from-index" in ng_zone.applied
    assert exhaustive.key == "npm:@angular/core#provideCheckNoChangesConfig.exhaustive"
    assert exhaustive.verified == "true"
