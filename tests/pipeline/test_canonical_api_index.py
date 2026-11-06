"""API index tests (spec 025 AC-2): parse, cache, resolve, offline fallback."""

from __future__ import annotations

from pathlib import Path


from migration_oracle.models.entities import (
    AffectedEntity,
    EntityKind,
    EntityRole,
    MigrationEntitiesBatch,
)
from migration_oracle.pipeline.canonical import canonicalize_batch, profile_for
from migration_oracle.pipeline.canonical.api_index import (
    HopApiIndex,
    build_hop_index,
    load_hop_index,
    load_version_index,
    package_for_path,
    parse_golden,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "api-index"
# Real excerpts of angular/angular goldens (19.2.0, plus 20.0.0 for
# provideCheckNoChangesConfig and core/primitives/di), API Extractor format.
ENTRY_POINTS = (
    "common/index.api.md",
    "core/index.api.md",
    "core/primitives/di/index.api.md",
    "core/testing/index.api.md",
    "router/index.api.md",
)


class FixtureClient:
    """Reads the golden fixtures instead of GitHub."""

    def __init__(self, offline: bool = False) -> None:
        self.calls = 0
        self._offline = offline

    def entry_point_paths(self) -> list[str]:
        self.calls += 1
        if self._offline:
            raise RuntimeError("GitHub is down")
        return list(ENTRY_POINTS)

    def golden_text(self, path: str) -> str:
        self.calls += 1
        fixture = FIXTURES / path.replace("/", "-")
        return fixture.read_text(encoding="utf-8")


class OfflineClient(FixtureClient):
    def __init__(self) -> None:
        super().__init__(offline=True)


def _occurrence(canonicalized, rule_index: int, occurrence_index: int):
    return canonicalized.rules[rule_index].occurrences[occurrence_index]


def _entity(*entities: AffectedEntity) -> MigrationEntitiesBatch:
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
            for number, group in enumerate(
                [entities[i : i + 1] for i in range(len(entities))]
            )
        ]
    )


def _affected(kind: EntityKind, name: str, role: str = "removed", package: str = "") -> AffectedEntity:
    return AffectedEntity(
        kind=kind, name=name, role=EntityRole(role), package=package
    )


def _index_from_fixtures() -> HopApiIndex:
    """A hop index parsed straight from the golden fixtures (no cache)."""
    version_index: dict[str, dict[str, list[str]]] = {}
    for path in ENTRY_POINTS:
        fixture = FIXTURES / path.replace("/", "-")
        version_index[package_for_path(path)] = parse_golden(fixture.read_text(encoding="utf-8"))
    return build_hop_index(("20.0.0", "20.1.0"), [version_index])


# --- parse (AC-2) ------------------------------------------------------------


def _golden(name: str) -> dict[str, list[str]]:
    return parse_golden(FIXTURES.joinpath(name).read_text(encoding="utf-8"))


def test_parse_golden_symbols_and_members() -> None:
    golden = _golden("core-index.api.md")
    assert set(golden["InjectFlags"]) == {"Default", "Host", "Self", "SkipSelf", "Optional"}
    assert golden["VERSION"] == []  # const without a block
    assert {"bootstrap", "tick", "componentTypes", "isStable"} <= set(golden["ApplicationRef"])
    # abstract class with abstract and getter members
    assert {"setAttribute", "destroy", "createElement"} <= set(golden["Renderer2"])
    assert {"get", "create"} <= set(golden["Injector"])
    assert {"optional", "skipSelf", "self", "host"} <= set(golden["InjectOptions"])
    assert "inject" in golden
    assert "ApplicationConfig" in golden


def test_parse_golden_function_option_fields_union_overloads() -> None:
    """Inline options of every overload are members of the function."""
    golden = _golden("core-index.api.md")
    assert set(golden["provideCheckNoChangesConfig"]) == {"exhaustive", "interval"}


def test_parse_golden_non_exported_declaration_via_export_list() -> None:
    golden = _golden("common-index.api.md")
    assert "NgForOf" in golden and "NgFor" in golden
    assert "ngForOf" in golden["NgForOf"]
    assert golden["NgFor"] == golden["NgForOf"]
    # 19.2.0 still declares DOCUMENT in common (it moved to core in 20)
    assert "DOCUMENT" in golden


def test_parse_golden_const_typed_as_interface_gets_its_members() -> None:
    """`export const TestBed: TestBedStatic;` exposes TestBedStatic's API."""
    golden = _golden("core-testing-index.api.md")
    assert {"get", "inject", "configureTestingModule", "ngModule"} <= set(golden["TestBed"])
    assert "TestBedStatic" in golden


def test_parse_golden_ignores_imports_and_comments() -> None:
    golden = parse_golden(
        "```ts\n\nimport { Observable } from 'rxjs';\n\n// @public (undocumented)\n"
        "export class Foo {\n    // (undocumented)\n    bar(): void;\n    [key: string]: any;\n}\n```\n"
    )
    assert golden == {"Foo": ["bar"]}


def test_parse_golden_alias_with_suffix() -> None:
    golden = parse_golden(
        "class Location_2 implements OnDestroy {\n    back(): void;\n}\n"
        "export { Location_2 as Location }\n"
    )
    assert golden == {"Location": ["back"]}


def test_package_for_path() -> None:
    assert package_for_path("core/index.api.md") == "@angular/core"
    assert package_for_path("core/testing/index.api.md") == "@angular/core/testing"
    assert package_for_path("router/index.api.md") == "@angular/router"
    # goldens before v19 are named index.md
    assert package_for_path("core/testing/index.md") == "@angular/core/testing"


# --- cache (AC-2) -------------------------------------------------------------


def test_load_version_index_writes_and_reuses_cache(tmp_path: Path) -> None:
    client = FixtureClient()
    first = load_version_index("20.0.0", cache_dir=tmp_path, client=client)
    assert set(first) == {
        "@angular/common",
        "@angular/core",
        "@angular/core/primitives/di",
        "@angular/core/testing",
        "@angular/router",
    }
    cache_file = tmp_path / "api-index" / "angular" / "20.0.0.json"
    assert cache_file.exists()
    calls_after_first = client.calls
    second = load_version_index("20.0.0", cache_dir=tmp_path, client=client)
    assert client.calls == calls_after_first  # served from cache
    assert first == second


def test_load_hop_index_unavailable_when_fetch_fails(tmp_path: Path) -> None:
    def client_for(_version: str) -> FixtureClient:
        return OfflineClient()

    index = load_hop_index(
        "20.0.0", "20.1.0", cache_dir=tmp_path, client_for=client_for
    )
    assert index.status == "unavailable"
    assert index.versions == ("20.0.0", "20.1.0")


def test_removed_in_to_symbol_found_via_from(tmp_path: Path) -> None:
    """A symbol that exists only in `from` is still found (spec FR-3)."""
    from_index = {
        "@angular/core": {"OldSymbol": []},
    }
    to_index = {
        "@angular/core": {"NewSymbol": []},
    }
    hop = build_hop_index(("19.0.0", "20.0.0"), [from_index, to_index])
    assert hop.entry_points("OldSymbol") == frozenset({"@angular/core"})
    assert hop.entry_points("NewSymbol") == frozenset({"@angular/core"})
    assert hop.entry_points("Vanished") == frozenset()


# --- resolution (AC-2) --------------------------------------------------------


def test_single_entry_point_fills_package() -> None:
    index = _index_from_fixtures()
    batch = _entity(_affected(EntityKind.CLASS, "InjectFlags"))
    result = canonicalize_batch(
        batch, profile=profile_for("angular"), from_version="20.0.0", to_version="20.1.0", index=index
    )
    entity = _occurrence(result, 0, 0).to_canonical()
    assert entity.package == "@angular/core"
    assert entity.name == "InjectFlags"
    assert entity.key == "npm:@angular/core#InjectFlags"
    assert entity.verified == "true"


def test_multiple_entry_points_without_owner_is_ambiguous() -> None:
    index = _index_from_fixtures()
    batch = _entity(_affected(EntityKind.CLASS, "VERSION"))
    result = canonicalize_batch(
        batch, profile=profile_for("angular"), from_version="20.0.0", to_version="20.1.0", index=index
    )
    entity = _occurrence(result, 0, 0).to_canonical()
    assert entity.package == "?"
    assert entity.key == "npm:?#VERSION"
    assert entity.verified == "ambiguous"


def test_multiple_entry_points_resolved_by_rule_dependency() -> None:
    index = _index_from_fixtures()
    batch = MigrationEntitiesBatch(
        entities=[
            {
                "source_section": "breaking_change",
                "title": "router rule",
                "change_type": "breaking_change",
                "reason": "r",
                "scopes": [{"scope": "api-surface", "severity": "high"}],
                "entities": [
                    _affected(EntityKind.DEPENDENCY, "@angular/router", "mentioned").model_dump(),
                    _affected(EntityKind.CLASS, "VERSION", "removed").model_dump(),
                ],
            }
        ]
    )
    result = canonicalize_batch(
        batch, profile=profile_for("angular"), from_version="20.0.0", to_version="20.1.0", index=index
    )
    entity = _occurrence(result, 0, 1).to_canonical()
    assert entity.package == "@angular/router"
    assert entity.verified == "true"


def test_llm_package_kept_when_in_found_set() -> None:
    index = _index_from_fixtures()
    batch = _entity(_affected(EntityKind.CLASS, "VERSION", package="@angular/router"))
    result = canonicalize_batch(
        batch, profile=profile_for("angular"), from_version="20.0.0", to_version="20.1.0", index=index
    )
    entity = _occurrence(result, 0, 0).to_canonical()
    assert entity.package == "@angular/router"
    assert entity.key == "npm:@angular/router#VERSION"
    assert entity.verified == "true"


def test_llm_package_overridden_when_symbol_is_elsewhere() -> None:
    index = _index_from_fixtures()
    batch = _entity(_affected(EntityKind.CLASS, "InjectFlags", package="@angular/router"))
    result = canonicalize_batch(
        batch, profile=profile_for("angular"), from_version="20.0.0", to_version="20.1.0", index=index
    )
    entity = _occurrence(result, 0, 0).to_canonical()
    assert entity.package == "@angular/core"
    assert entity.verified == "true"


def test_missing_symbol_kept_but_unverified() -> None:
    index = _index_from_fixtures()
    batch = _entity(_affected(EntityKind.CLASS, "NotInIndex"))
    result = canonicalize_batch(
        batch, profile=profile_for("angular"), from_version="20.0.0", to_version="20.1.0", index=index
    )
    entity = _occurrence(result, 0, 0).to_canonical()
    assert entity.name == "NotInIndex"
    assert entity.key == "npm:?#NotInIndex"
    assert entity.verified == "false"


def test_member_verified_when_owner_verified_and_member_in_block() -> None:
    index = _index_from_fixtures()
    batch = _entity(_affected(EntityKind.CLASS, "TestBed.inject"))
    result = canonicalize_batch(
        batch, profile=profile_for("angular"), from_version="20.0.0", to_version="20.1.0", index=index
    )
    entity = _occurrence(result, 0, 0).to_canonical()
    assert entity.kind.value == "member"
    assert entity.package == "@angular/core/testing"
    assert entity.name == "TestBed.inject"
    assert entity.key == "npm:@angular/core/testing#TestBed.inject"
    assert entity.verified == "true"


def test_member_unverified_when_not_in_owners_block() -> None:
    index = _index_from_fixtures()
    batch = _entity(_affected(EntityKind.CLASS, "TestBed.nonexistent"))
    result = canonicalize_batch(
        batch, profile=profile_for("angular"), from_version="20.0.0", to_version="20.1.0", index=index
    )
    entity = _occurrence(result, 0, 0).to_canonical()
    assert entity.package == "@angular/core/testing"
    assert entity.verified == "false"


# --- offline (AC-4, unit half) --------------------------------------------------


def test_unavailable_index_marks_all_npm_entities_unverified() -> None:
    batch = _entity(_affected(EntityKind.CLASS, "InjectFlags"))
    result = canonicalize_batch(
        batch,
        profile=profile_for("angular"),
        from_version="20.0.0",
        to_version="20.1.0",
        index=HopApiIndex.unavailable(("20.0.0", "20.1.0")),
    )
    entity = _occurrence(result, 0, 0).to_canonical()
    assert entity.verified == "false"
    assert entity.key == "npm:?#InjectFlags"
    assert result.api_index_status == "unavailable"

# --- fetch (HttpGoldenClient) ---------------------------------------------------


def _mock_httpx(monkeypatch, handler) -> list[str]:
    import httpx

    from migration_oracle.pipeline.canonical import api_index

    seen: list[str] = []
    real_client = httpx.Client

    def recording(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return handler(request)

    monkeypatch.setattr(
        api_index.httpx,
        "Client",
        lambda **kw: real_client(transport=httpx.MockTransport(recording), **kw),
    )
    return seen


def test_http_client_lists_goldens_with_one_tree_request(monkeypatch) -> None:
    import httpx

    from migration_oracle.pipeline.canonical.api_index import HttpGoldenClient

    tree = {
        "truncated": False,
        "tree": [
            {"path": "core", "type": "tree"},
            {"path": "core/index.api.md", "type": "blob"},
            {"path": "core/testing/index.api.md", "type": "blob"},
            {"path": "core/errors.api.md", "type": "blob"},
            {"path": "router/index.md", "type": "blob"},
            {"path": "manage.js", "type": "blob"},
        ],
    }
    seen = _mock_httpx(monkeypatch, lambda request: httpx.Response(200, json=tree))
    paths = HttpGoldenClient("20.0.0").entry_point_paths()
    assert paths == ["core/index.api.md", "core/testing/index.api.md", "router/index.md"]
    assert len(seen) == 1
    assert "/git/trees/20.0.0:goldens/public-api" in seen[0]
    assert "recursive=1" in seen[0]


def test_http_client_missing_tag_is_unavailable(monkeypatch) -> None:
    import httpx
    import pytest

    from migration_oracle.pipeline.canonical.api_index import (
        ApiIndexUnavailable,
        HttpGoldenClient,
    )

    _mock_httpx(monkeypatch, lambda request: httpx.Response(404, json={"message": "Not Found"}))
    with pytest.raises(ApiIndexUnavailable, match="tag missing"):
        HttpGoldenClient("22.0.0").entry_point_paths()


# --- partial index ----------------------------------------------------------------


def test_load_hop_index_partial_when_one_version_fails(tmp_path: Path) -> None:
    def client_for(version: str) -> FixtureClient:
        return OfflineClient() if version == "22.0.0" else FixtureClient()

    index = load_hop_index("21.0.0", "22.0.0", cache_dir=tmp_path, client_for=client_for)
    assert index.status == "partial"
    assert index.usable
    assert index.missing_versions == ("22.0.0",)
    assert index.entry_points("InjectFlags") == frozenset({"@angular/core"})


def test_partial_index_still_verifies_and_marks_misses(tmp_path: Path) -> None:
    def client_for(version: str) -> FixtureClient:
        return OfflineClient() if version == "22.0.0" else FixtureClient()

    index = load_hop_index("21.0.0", "22.0.0", cache_dir=tmp_path, client_for=client_for)
    batch = _entity(
        _affected(EntityKind.CLASS, "InjectFlags"),
        _affected(EntityKind.CLASS, "BrandNewIn22"),
    )
    result = canonicalize_batch(
        batch, profile=profile_for("angular"), from_version="21.0.0", to_version="22.0.0", index=index
    )
    found = _occurrence(result, 0, 0)
    missing = _occurrence(result, 1, 0)
    assert found.verified == "true"
    assert missing.verified == "false"
    assert "verify:not-in-partial-index" in missing.applied
    assert result.api_index_status == "partial"


def test_cache_from_older_parser_is_rebuilt(tmp_path: Path) -> None:
    import json

    cache_file = tmp_path / "api-index" / "angular" / "20.0.0.json"
    cache_file.parent.mkdir(parents=True)
    cache_file.write_text(json.dumps({"version": "20.0.0", "packages": {"@angular/core": {}}}))
    client = FixtureClient()
    index = load_version_index("20.0.0", cache_dir=tmp_path, client=client)
    assert client.calls > 0
    assert "InjectFlags" in index["@angular/core"]


# --- primary entry point ------------------------------------------------------------


def test_primary_entry_point_wins_over_primitives_and_testing() -> None:
    index = _index_from_fixtures()
    batch = _entity(
        _affected(EntityKind.CLASS, "Injector"),  # core + core/primitives/di
        _affected(EntityKind.CLASS, "Injector.get"),
    )
    result = canonicalize_batch(
        batch, profile=profile_for("angular"), from_version="20.0.0", to_version="20.1.0", index=index
    )
    owner = _occurrence(result, 0, 0)
    member = _occurrence(result, 1, 0)
    assert owner.key == "npm:@angular/core#Injector"
    assert owner.verified == "true"
    assert "verify:primary-entry-point" in owner.applied
    assert member.key == "npm:@angular/core#Injector.get"
    assert member.verified == "true"


def test_function_option_member_verified() -> None:
    index = _index_from_fixtures()
    batch = _entity(_affected(EntityKind.PROPERTY, "provideCheckNoChangesConfig.exhaustive"))
    result = canonicalize_batch(
        batch, profile=profile_for("angular"), from_version="20.0.0", to_version="20.1.0", index=index
    )
    entity = _occurrence(result, 0, 0)
    assert entity.key == "npm:@angular/core#provideCheckNoChangesConfig.exhaustive"
    assert entity.verified == "true"


def test_aliased_export_is_resolved() -> None:
    index = _index_from_fixtures()
    batch = _entity(_affected(EntityKind.CLASS, "NgFor"))
    result = canonicalize_batch(
        batch, profile=profile_for("angular"), from_version="20.0.0", to_version="20.1.0", index=index
    )
    assert _occurrence(result, 0, 0).key == "npm:@angular/common#NgFor"
    assert _occurrence(result, 0, 0).verified == "true"


def test_parse_golden_skips_reexports_of_imported_symbols() -> None:
    golden = parse_golden(
        "import { DOCUMENT } from '@angular/core';\n\n"
        "export { DOCUMENT }\n\n"
        "class NgForOf {\n    ngForOf: any;\n}\n"
        "export { NgForOf }\n"
    )
    assert golden == {"NgForOf": ["ngForOf"]}
