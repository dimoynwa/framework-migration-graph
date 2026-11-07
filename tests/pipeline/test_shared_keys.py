"""025 reads the shared key builders and Angular data (spec 026 AC-1.4).

The move to :mod:`migration_keys` must not change a single key or token: these
are the assertions that catch drift between ingestion and the scanner.
"""

from __future__ import annotations

from migration_keys import (
    ANGULAR_CONFIG_PREFIXES,
    ANGULAR_PACKAGES,
    ANGULAR_SYNTAX_TOKENS,
    cfg_key,
    maven_key,
    npm_key,
)
from migration_oracle.models.entities import (
    AffectedEntity,
    EntityKind,
    EntityRole,
    MigrationEntitiesBatch,
)
from migration_oracle.pipeline.canonical import canonicalize_batch, profile_for
from migration_oracle.pipeline.canonical.api_index import HopApiIndex
from migration_oracle.pipeline.canonical.profiles import ANGULAR_PROFILE


def _occurrences(*entities: AffectedEntity, framework: str = "angular"):
    batch = MigrationEntitiesBatch(
        entities=[
            {
                "source_section": "breaking_change",
                "title": "rule",
                "change_type": "breaking_change",
                "reason": "r",
                "scopes": [{"scope": "api-surface", "severity": "high"}],
                "entities": [entity.model_dump() for entity in entities],
            }
        ]
    )
    result = canonicalize_batch(
        batch,
        profile=profile_for(framework),
        from_version="19.2.0",
        to_version="20.0.0",
        index=HopApiIndex.unavailable(("19.2.0", "20.0.0")),
    )
    return result.rules[0].occurrences


# --- the data lives in one place ------------------------------------------


def test_angular_profile_reads_the_shared_tuples() -> None:
    assert ANGULAR_PROFILE.known_packages == frozenset(ANGULAR_PACKAGES)
    assert ANGULAR_PROFILE.syntax_tokens == frozenset(ANGULAR_SYNTAX_TOKENS)
    assert dict(ANGULAR_PROFILE.config_prefixes) == ANGULAR_CONFIG_PREFIXES


def test_config_file_lookup_is_unchanged_by_the_move() -> None:
    profile = profile_for("angular")

    assert profile.file_for_key("engines.node") == "package.json"
    assert profile.file_for_key("dependencies.rxjs") == "package.json"
    assert profile.file_for_key("compilerOptions.strict") == "tsconfig.json"
    assert profile.file_for_key("angularCompilerOptions.strictTemplates") == "tsconfig.json"
    assert profile.file_for_key("projects.*.architect.build.builder") == "angular.json"
    assert profile.file_for_key("schematics.*.collection") == "angular.json"
    assert profile.file_for_key("unknown.key") == ""


def test_spring_boot_profile_keeps_its_config_file() -> None:
    profile = profile_for("spring-boot")

    assert profile.is_npm is False
    assert profile.config_file == "application.properties"
    assert profile.file_for_key("anything") == ""


# --- the keys 025 writes are the shared ones ------------------------------


def test_npm_class_and_member_keys_match_the_shared_builders() -> None:
    occurrences = _occurrences(
        AffectedEntity(
            kind=EntityKind.MEMBER,
            name="TestBed.get",
            role=EntityRole.REMOVED,
            package="@angular/core/testing",
        ),
        AffectedEntity(
            kind=EntityKind.CLASS,
            name="InjectFlags",
            role=EntityRole.REMOVED,
            package="@angular/core",
        ),
    )

    keys = {occurrence.key for occurrence in occurrences}
    assert npm_key("@angular/core/testing", "TestBed", "get") in keys
    assert npm_key("@angular/core", "InjectFlags") in keys


def test_config_keys_match_the_shared_cfg_builder() -> None:
    occurrences = _occurrences(
        AffectedEntity(
            kind=EntityKind.PROPERTY,
            name="engines.node",
            role=EntityRole.REMOVED,
        )
    )

    assert occurrences[0].key == cfg_key("package.json", "engines.node")


def test_spring_boot_property_key_uses_application_properties() -> None:
    occurrences = _occurrences(
        AffectedEntity(
            kind=EntityKind.PROPERTY,
            name="spring.data.mongodb.uri",
            role=EntityRole.REMOVED,
        ),
        framework="spring-boot",
    )

    occurrence = occurrences[0]
    assert occurrence.key == cfg_key("application.properties", "spring.data.mongodb.uri")
    # 025 FR-2.7: the name stays byte-for-byte as written.
    assert occurrence.name == "spring.data.mongodb.uri"
    assert occurrence.verified == "unchecked"


def test_syntax_token_key_uses_the_shared_syntax_builder() -> None:
    occurrences = _occurrences(
        AffectedEntity(kind=EntityKind.CLASS, name="@defer", role=EntityRole.REMOVED)
    )

    assert occurrences[0].key == "syntax:angular-template#@defer"
    assert occurrences[0].kind == EntityKind.SYNTAX


def test_wildfly_maven_keys_still_come_from_the_shared_builder() -> None:
    """WildFly (maven) keys moved to ``migration_keys`` too, without changing."""
    occurrences = _occurrences(
        AffectedEntity(
            kind=EntityKind.CLASS,
            name="org.jboss.Foo",
            role=EntityRole.REMOVED,
        ),
        framework="wildfly",
    )

    assert occurrences[0].key == maven_key("org.jboss.Foo")


def test_a_spring_boot_property_key_is_in_canonical_form() -> None:
    """The rule's key is the one the 026 scanner writes; the name stays as written."""
    from migration_keys.spring import canonical_key

    occurrences = _occurrences(
        AffectedEntity(
            kind=EntityKind.PROPERTY,
            name="spring.data.mongodb.authenticationDatabase",
            role=EntityRole.REMOVED,
        ),
        AffectedEntity(
            kind=EntityKind.PROPERTY,
            name="logging.level.com.Foo.BarService",
            role=EntityRole.REMOVED,
        ),
        framework="spring-boot",
    )

    assert [occurrence.key for occurrence in occurrences] == [
        "cfg:application.properties#spring.data.mongodb.authentication-database",
        "cfg:application.properties#logging.level.com.Foo.BarService",
    ]
    assert occurrences[0].name == "spring.data.mongodb.authenticationDatabase"
    assert canonical_key(occurrences[0].name) == (
        occurrences[0].key.split("#", 1)[1]
    )
