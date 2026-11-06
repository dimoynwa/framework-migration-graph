"""Signal request shape (AC-1) and the contract guard / floors (AC-2, AC-3).

Everything here uses the fake System-1 client: no HTTP, no graph.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from migration_oracle.models.entities import (
    AffectedEntity,
    EntityKind,
    EntityRole,
    MigrationEntitiesBatch,
    StepType,
)
from migration_oracle.pipeline.canonical import canonicalize_batch, profile_for
from migration_oracle.pipeline.canonical.api_index import build_hop_index
from migration_oracle.pipeline.signals import (
    SIGNAL_QUESTIONS_VERSION,
    SIGNAL_CRITERIA,
    cache_key,
    classify_signals,
    features_for,
    signal_questions,
)
from migration_oracle.pipeline.signals.contract import (
    apply_contract,
    chosen_features,
    rule_shortcut,
    shortcut_result,
    signal_keys,
)
from migration_oracle.pipeline.signals.settings import SignalSettings, load_settings
from migration_oracle.pipeline.triage.client import FakeTriageClient
from migration_oracle.pipeline.triage.settings import TriageSettings

HOP = ("19.2.0", "20.0.0")


# --- fixtures ---------------------------------------------------------------


def _settings(**overrides: object) -> SignalSettings:
    base = load_settings()
    client = TriageSettings(
        base_url=str(overrides.get("base_url", "http://triage.example")),
        endpoint_path="/v1/systemone",
        model=str(overrides.get("model", "nimble")),
        api_key="",
        timeout_sec=30.0,
        max_concurrent=2,
        state_max_chars=6000,
        drop_max_action_prob=0.2,
        drop_min_category_prob=0.8,
        drop_max_impact_score=1.0,
        filter_max_input_tokens=60000,
        cache_dir=base.cache_dir,
    )
    return SignalSettings(
        client=client,
        state_max_chars=int(overrides.get("state_max_chars", base.state_max_chars)),
        searchable_min_prob=float(
            overrides.get("searchable_min_prob", base.searchable_min_prob)
        ),
        universal_min_prob=float(
            overrides.get("universal_min_prob", base.universal_min_prob)
        ),
        feature_min_prob=float(overrides.get("feature_min_prob", base.feature_min_prob)),
        cache_dir=Path(str(overrides.get("cache_dir", base.cache_dir))),
    )


def _entity(
    *,
    title: str = "TestBed.get removed",
    change_type: str = "breaking_change",
    source_section: str = "breaking_change",
    entities: list[AffectedEntity] | None = None,
    steps: int = 0,
) -> dict:
    return {
        "source_section": source_section,
        "title": title,
        "change_type": change_type,
        "reason": "r",
        "scopes": [{"scope": "api-surface", "severity": "high"}],
        "entities": [entity.model_dump() for entity in entities or []],
        "steps": [
            {
                "index": index,
                "step_type": StepType.VERIFY.value,
                "summary": f"verify {index}",
                "instruction": "i",
                "effort": "moderate",
                "automatable": False,
                "verification": "v",
            }
            for index in range(steps)
        ],
    }


def _affected(kind: str, name: str, role: str = "mentioned", package: str = "") -> AffectedEntity:
    return AffectedEntity(
        kind=EntityKind(kind), name=name, role=EntityRole(role), package=package
    )


def _batch(*entities: dict) -> MigrationEntitiesBatch:
    return MigrationEntitiesBatch.model_validate({"entities": list(entities)})


def _index():
    return build_hop_index(
        HOP,
        [
            {
                "@angular/core": {"DestroyRef": ["onDestroy"]},
                "@angular/common/http": {
                    "HttpClientModule": [],
                    "provideHttpClient": [],
                },
                "@angular/core/testing": {"TestBed": ["get", "inject", "configureTestingModule"]},
                "@angular/animations": {},
            }
        ],
    )


def _canonical(batch: MigrationEntitiesBatch, index=None):
    return canonicalize_batch(
        batch,
        profile=profile_for("angular"),
        from_version=HOP[0],
        to_version=HOP[1],
        index=index if index is not None else _index(),
    )


def _answers(signal: str = "symbol", probability: float = 0.9, **features: float) -> dict:
    probabilities = {
        "symbol": 0.0,
        "config": 0.0,
        "dependency": 0.0,
        "syntax": 0.0,
        "behavioral": 0.0,
        "universal": 0.0,
    }
    probabilities[signal] = probability
    answers: dict = {
        "signal": {
            "type": "choice",
            "choice": signal,
            "probabilities": probabilities,
            "confidence": 0.5,
        }
    }
    for feature_id, value in features.items():
        answers[f"feature.{feature_id}"] = {"type": "noul", "noul": value}
    return answers


# --- AC-1: request shape ----------------------------------------------------


def test_ac1_one_request_per_rule_with_signal_and_every_feature(tmp_path: Path) -> None:
    batch = _batch(
        _entity(
            title="TestBed.get removed",
            entities=[_affected("class", "TestBed.get", role="removed")],
        ),
        _entity(
            title="InjectFlags removed",
            entities=[_affected("class", "InjectFlags", role="removed")],
        ),
    )
    canonicalized = _canonical(batch)
    client = FakeTriageClient(_answers(feature_probability=0.0))

    classify_signals(
        batch=batch,
        canonicalized=canonicalized,
        framework_key="angular",
        framework_display="Angular",
        hop=HOP,
        client=client,
        settings=_settings(cache_dir=tmp_path),
        jsonl_path=tmp_path / "signals.jsonl",
        summary_path=tmp_path / "summary.json",
    )

    # One request per rule, state sent with it, all questions in one body.
    assert len(client.calls) == 2
    state, questions = client.calls[0]
    assert questions["signal"]["type"] == "choice"
    assert set(questions["signal"]["criteria"]) == set(SIGNAL_CRITERIA)
    feature_ids = [feature.id for feature in features_for("angular")]
    assert [key for key in questions if key.startswith("feature.")] == [
        f"feature.{feature_id}" for feature_id in feature_ids
    ]
    for feature_id in feature_ids:
        assert questions[f"feature.{feature_id}"]["type"] == "noul"
    # The state names the rule and its canonical keys.
    assert "TestBed.get removed" in state
    assert "npm:@angular/core/testing#TestBed.get" in state


def test_ac1_state_is_capped(tmp_path: Path) -> None:
    batch = _batch(
        _entity(
            title="A rule with a very long reason",
            entities=[_affected("class", "DestroyRef", role="mentioned")],
            steps=8,
        )
    )
    canonicalized = _canonical(batch)
    client = FakeTriageClient(_answers())
    settings = _settings(cache_dir=tmp_path, state_max_chars=120)

    classify_signals(
        batch=batch,
        canonicalized=canonicalized,
        framework_key="angular",
        framework_display="Angular",
        hop=HOP,
        client=client,
        settings=settings,
        jsonl_path=tmp_path / "signals.jsonl",
        summary_path=tmp_path / "summary.json",
    )
    assert len(client.calls[0][0]) <= 120


def test_ac1_question_version_covers_the_vocabulary() -> None:
    assert SIGNAL_QUESTIONS_VERSION >= 1
    questions = signal_questions(features_for("spring-boot"))
    assert "signal" in questions
    assert "feature.security" in questions


# --- AC-2: the guard --------------------------------------------------------


def test_ac2_removed_key_wins_over_the_replacement(tmp_path: Path) -> None:
    batch = _batch(
        _entity(
            title="Use provideHttpClient instead of HttpClientModule",
            entities=[
                _affected("class", "HttpClientModule", role="removed"),
                _affected("class", "provideHttpClient", role="replacement"),
            ],
        )
    )
    canonicalized = _canonical(batch)
    client = FakeTriageClient(_answers("symbol", 0.95, feature_probability=0.0))
    result = classify_signals(
        batch=batch,
        canonicalized=canonicalized,
        framework_key="angular",
        framework_display="Angular",
        hop=HOP,
        client=client,
        settings=_settings(cache_dir=tmp_path),
        jsonl_path=tmp_path / "signals.jsonl",
        summary_path=tmp_path / "summary.json",
    )
    record = result.records[0]
    assert record.signal == "symbol"
    assert record.signal_source == "model"
    # The removed key is the search key; the replacement key never is.
    assert record.signal_keys == ["npm:@angular/common/http#HttpClientModule"]
    assert all("provideHttpClient" not in key for key in record.signal_keys)


def test_ac2_guard_when_the_only_entities_are_replacements(tmp_path: Path) -> None:
    """A rule that names only its replacement cannot be searched for at all."""
    batch = _batch(
        _entity(
            title="Use the new API instead",
            entities=[_affected("class", "provideHttpClient", role="replacement")],
        )
    )
    canonicalized = _canonical(batch)
    client = FakeTriageClient(_answers("symbol", 0.95))
    result = classify_signals(
        batch=batch,
        canonicalized=canonicalized,
        framework_key="angular",
        framework_display="Angular",
        hop=HOP,
        client=client,
        settings=_settings(cache_dir=tmp_path),
        jsonl_path=tmp_path / "signals.jsonl",
        summary_path=tmp_path / "summary.json",
    )
    assert result.records[0].signal == "behavioral"
    assert result.records[0].signal_source == "guard"
    assert result.records[0].signal_keys == []


def test_ac2_config_without_a_property_entity_falls_back(tmp_path: Path) -> None:
    batch = _batch(
        _entity(
            title="strictStandalone default changed",
            entities=[_affected("class", "DestroyRef", role="mentioned")],
        )
    )
    canonicalized = _canonical(batch)
    client = FakeTriageClient(_answers("config", 0.95))
    result = classify_signals(
        batch=batch,
        canonicalized=canonicalized,
        framework_key="angular",
        framework_display="Angular",
        hop=HOP,
        client=client,
        settings=_settings(cache_dir=tmp_path),
        jsonl_path=tmp_path / "signals.jsonl",
        summary_path=tmp_path / "summary.json",
    )
    assert result.records[0].signal == "behavioral"
    assert result.records[0].signal_source == "guard"


def test_ac2_config_key_without_a_known_file_is_not_searchable() -> None:
    from migration_oracle.pipeline.canonical.normalize import NormalizedEntity

    unknown_file = NormalizedEntity(
        role="mentioned",
        raw_kind="property",
        raw_name="someKey",
        llm_package="",
        kind=EntityKind.PROPERTY,
        ecosystem="npm",
        symbol="someKey",
        name="someKey",
        key="cfg:someKey",
        verified="false",
    )
    assert signal_keys([unknown_file], "config") == ([], [], [])


def test_ac2_removed_member_key_stays_symbol() -> None:
    batch = _batch(
        _entity(
            title="TestBed.get removed",
            entities=[
                _affected("class", "TestBed.get", role="removed"),
                _affected("class", "TestBed.inject", role="replacement"),
            ],
        )
    )
    canonicalized = _canonical(batch)
    result = apply_contract(
        answer=_answers("symbol", 0.9),
        occurrences=canonicalized.rules[0].occurrences,
        settings=_settings(),
    )
    assert result.signal == "symbol"
    assert result.source == "model"
    assert result.keys == ["npm:@angular/core/testing#TestBed.get"]
    assert result.confidence == pytest.approx(0.9)


# --- AC-3: the floors -------------------------------------------------------


def test_ac3_symbol_below_the_searchable_floor_falls_back() -> None:
    batch = _batch(
        _entity(entities=[_affected("class", "DestroyRef", role="removed")])
    )
    canonicalized = _canonical(batch)
    result = apply_contract(
        answer=_answers("symbol", 0.65),
        occurrences=canonicalized.rules[0].occurrences,
        settings=_settings(searchable_min_prob=0.70),
    )
    assert result.signal == "behavioral"
    assert result.source == "low_confidence"
    # The keys are kept for review, but the planner will not search for them.
    assert result.keys == ["npm:@angular/core#DestroyRef"]


def test_ac3_universal_at_065_stays_universal() -> None:
    batch = _batch(_entity(entities=[]))
    canonicalized = _canonical(batch)
    result = apply_contract(
        answer=_answers("universal", 0.65),
        occurrences=canonicalized.rules[0].occurrences,
        settings=_settings(universal_min_prob=0.60),
    )
    assert result.signal == "universal"
    assert result.source == "model"


def test_ac3_universal_below_its_floor_falls_back() -> None:
    result = apply_contract(
        answer=_answers("universal", 0.55),
        occurrences=[],
        settings=_settings(universal_min_prob=0.60),
    )
    assert result.signal == "behavioral"
    assert result.source == "low_confidence"


def test_ac3_feature_floor_is_inclusive() -> None:
    settings = _settings(feature_min_prob=0.50)
    chosen, probabilities = chosen_features(
        _answers(ssr=0.49, testbed=0.51), ["ssr", "testbed", "zoneless"], settings
    )
    assert chosen == ["testbed"]
    assert probabilities == {"ssr": 0.49, "testbed": 0.51}


def test_unknown_signal_label_is_guarded() -> None:
    result = apply_contract(
        answer=_answers("nonsense", 0.99),
        occurrences=[],
        settings=_settings(),
    )
    assert result.signal == "behavioral"
    assert result.source == "guard"


# --- FR-4.5: the deterministic shortcut ------------------------------------


def test_ac4_all_dependency_component_upgrade_is_dependency_by_rule() -> None:
    batch = _batch(
        _entity(
            title="Angular package bump",
            change_type="component_upgrade",
            source_section="component_upgrade",
            entities=[_affected("dependency", "@angular/core", role="mentioned")],
        )
    )
    canonicalized = _canonical(batch)
    shortcut = shortcut_result(canonicalized.rules[0].occurrences)
    assert shortcut.signal == "dependency"
    assert shortcut.source == "rule"
    assert shortcut.keys == ["npm:@angular/core"]


def test_ac4_shortcut_needs_every_entity_to_be_a_dependency() -> None:
    batch = _batch(
        _entity(
            change_type="component_upgrade",
            source_section="component_upgrade",
            entities=[
                _affected("dependency", "@angular/core", role="mentioned"),
                _affected("class", "DestroyRef", role="mentioned"),
            ],
        )
    )
    canonicalized = _canonical(batch)
    assert (
        rule_shortcut(
            occurrences=canonicalized.rules[0].occurrences,
            change_type="component_upgrade",
            source_section="component_upgrade",
        )
        is False
    )


def test_ac4_shortcut_still_asks_for_features(tmp_path: Path) -> None:
    batch = _batch(
        _entity(
            title="Angular package bump",
            change_type="component_upgrade",
            source_section="component_upgrade",
            entities=[_affected("dependency", "@angular/core", role="mentioned")],
        )
    )
    canonicalized = _canonical(batch)
    # The model's signal answer says symbol; the rule must win.
    client = FakeTriageClient(_answers("symbol", 0.95, testbed=0.9))
    result = classify_signals(
        batch=batch,
        canonicalized=canonicalized,
        framework_key="angular",
        framework_display="Angular",
        hop=HOP,
        client=client,
        settings=_settings(cache_dir=tmp_path),
        jsonl_path=tmp_path / "signals.jsonl",
        summary_path=tmp_path / "summary.json",
    )
    assert len(client.calls) == 1
    questions = client.calls[0][1]
    assert "feature.testbed" in questions
    record = result.records[0]
    assert record.signal == "dependency"
    assert record.signal_source == "rule"
    assert record.features == ["testbed"]


# --- AC-6: Nimble unavailable ----------------------------------------------


def test_ac6_nimble_disabled_writes_no_properties(tmp_path: Path) -> None:
    batch = _batch(
        _entity(entities=[_affected("class", "DestroyRef", role="removed")])
    )
    canonicalized = _canonical(batch)
    client = FakeTriageClient(_answers())
    result = classify_signals(
        batch=batch,
        canonicalized=canonicalized,
        framework_key="angular",
        framework_display="Angular",
        hop=HOP,
        client=client,
        settings=_settings(cache_dir=tmp_path, base_url=""),
        jsonl_path=tmp_path / "signals.jsonl",
        summary_path=tmp_path / "summary.json",
    )
    assert result.status == "disabled"
    assert result.applied is False
    assert result.properties_by_rule_id() == {}
    assert client.calls == []


def test_ac6_nimble_unreachable_writes_no_properties(tmp_path: Path) -> None:
    from migration_oracle.pipeline.triage.client import TriageUnavailable

    batch = _batch(
        _entity(entities=[_affected("class", "DestroyRef", role="removed")])
    )
    canonicalized = _canonical(batch)
    result = classify_signals(
        batch=batch,
        canonicalized=canonicalized,
        framework_key="angular",
        framework_display="Angular",
        hop=HOP,
        client=FakeTriageClient(TriageUnavailable("connection refused")),
        settings=_settings(cache_dir=tmp_path),
        jsonl_path=tmp_path / "signals.jsonl",
        summary_path=tmp_path / "summary.json",
    )
    assert result.status == "unavailable"
    assert result.properties_by_rule_id() == {}


# --- AC-5: the cache --------------------------------------------------------


def _run(batch, canonicalized, *, client, settings, tmp_path):
    return classify_signals(
        batch=batch,
        canonicalized=canonicalized,
        framework_key="angular",
        framework_display="Angular",
        hop=HOP,
        client=client,
        settings=settings,
        jsonl_path=tmp_path / "signals.jsonl",
        summary_path=tmp_path / "summary.json",
    )


def test_ac5_second_run_makes_no_calls(tmp_path: Path) -> None:
    batch = _batch(
        _entity(
            title="TestBed.get removed",
            entities=[_affected("class", "TestBed.get", role="removed")],
        ),
        _entity(
            title="InjectFlags removed",
            entities=[_affected("class", "InjectFlags", role="removed")],
        ),
    )
    canonicalized = _canonical(batch)
    settings = _settings(cache_dir=tmp_path)
    client = FakeTriageClient(_answers("symbol", 0.9, testbed=0.8))

    first = _run(batch, canonicalized, client=client, settings=settings, tmp_path=tmp_path)
    assert len(client.calls) == 2
    assert first.calls == 2 and first.cache_hits == 0

    second = _run(batch, canonicalized, client=client, settings=settings, tmp_path=tmp_path)
    assert len(client.calls) == 2
    assert second.calls == 0
    assert second.cache_hits == 2
    assert [record.signal for record in second.records] == [
        record.signal for record in first.records
    ]


def test_ac5_changed_canonical_key_re_asks_only_that_rule(tmp_path: Path) -> None:
    first_batch = _batch(
        _entity(
            title="TestBed.get removed",
            entities=[_affected("class", "TestBed.get", role="removed")],
        ),
        _entity(
            title="InjectFlags removed",
            entities=[_affected("class", "InjectFlags", role="removed")],
        ),
    )
    settings = _settings(cache_dir=tmp_path)
    client = FakeTriageClient(_answers("symbol", 0.9))
    _run(
        first_batch,
        _canonical(first_batch),
        client=client,
        settings=settings,
        tmp_path=tmp_path,
    )
    assert len(client.calls) == 2

    # Same titles, one different entity: only that rule's state changes.
    second_batch = _batch(
        _entity(
            title="TestBed.get removed",
            entities=[_affected("class", "TestBed.get", role="removed")],
        ),
        _entity(
            title="InjectFlags removed",
            entities=[_affected("class", "VERSION", role="removed")],
        ),
    )
    second = _run(
        second_batch,
        _canonical(second_batch),
        client=client,
        settings=settings,
        tmp_path=tmp_path,
    )
    assert len(client.calls) == 3
    assert second.calls == 1
    assert second.cache_hits == 1


def test_ac5_version_bump_re_asks_everything(monkeypatch, tmp_path: Path) -> None:
    from migration_oracle.pipeline.signals import run as run_module

    batch = _batch(
        _entity(
            title="TestBed.get removed",
            entities=[_affected("class", "TestBed.get", role="removed")],
        )
    )
    canonicalized = _canonical(batch)
    settings = _settings(cache_dir=tmp_path)
    client = FakeTriageClient(_answers("symbol", 0.9))
    _run(batch, canonicalized, client=client, settings=settings, tmp_path=tmp_path)
    assert len(client.calls) == 1

    monkeypatch.setattr(run_module.questions_module, "SIGNAL_QUESTIONS_VERSION", 2)
    _run(batch, canonicalized, client=client, settings=settings, tmp_path=tmp_path)
    assert len(client.calls) == 2


def test_cache_key_is_scoped_by_framework() -> None:
    assert cache_key(1, "nimble", "angular", "state") != cache_key(
        1, "nimble", "spring-boot", "state"
    )


# --- artifacts (FR-7) -------------------------------------------------------


def test_artifacts_record_every_probability_and_the_decision(tmp_path: Path) -> None:
    batch = _batch(
        _entity(
            title="TestBed.get removed",
            entities=[_affected("class", "TestBed.get", role="removed")],
        )
    )
    canonicalized = _canonical(batch)
    settings = _settings(cache_dir=tmp_path)
    client = FakeTriageClient(_answers("symbol", 0.9, testbed=0.81, ssr=0.12))
    classify_signals(
        batch=batch,
        canonicalized=canonicalized,
        framework_key="angular",
        framework_display="Angular",
        hop=HOP,
        client=client,
        settings=settings,
        jsonl_path=tmp_path / "signals.jsonl",
        summary_path=tmp_path / "summary.json",
    )
    line = json.loads((tmp_path / "signals.jsonl").read_text(encoding="utf-8"))
    assert line["ruleId"] == "pipeline://Angular/20.0.0/TestBed.get removed"
    assert line["signal"] == "symbol"
    assert line["signalSource"] == "model"
    assert line["signalKeys"] == ["npm:@angular/core/testing#TestBed.get"]
    assert line["features"] == ["testbed"]
    assert line["featureProbabilities"] == {"testbed": 0.81, "ssr": 0.12}
    assert line["answers"]["feature.testbed"]["noul"] == 0.81
    assert line["cacheHit"] is False

    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["nimble"] == "ok"
    assert summary["by_signal"] == {"symbol": 1}
    assert summary["by_source"] == {"model": 1}
    assert summary["by_feature"] == {"testbed": 1}
    assert summary["questions_version"] == SIGNAL_QUESTIONS_VERSION


# --- review 2026-11-06: behavioral rules carry locator keys --------------------


def _occ(kind, key, role, file=""):
    from migration_oracle.models.entities import EntityKind
    from migration_oracle.pipeline.canonical.normalize import NormalizedEntity

    return NormalizedEntity(
        role=role, raw_kind=kind, raw_name=key, llm_package="", kind=EntityKind(kind),
        ecosystem="npm", key=key, file=file, verified="true",
    )


def _answer(choice, prob, behavioral=0.1):
    return {"signal": {"type": "choice", "choice": choice,
                       "probabilities": {choice: prob, "behavioral": behavioral}}}


def test_model_behavioral_keeps_locator_keys_of_any_kind() -> None:
    from migration_oracle.pipeline.signals.contract import apply_contract
    from migration_oracle.pipeline.signals.settings import load_settings

    occurrences = [
        _occ("class", "npm:@angular/platform-browser#BootstrapContext", "replacement"),
        _occ("class", "npm:@angular/core#PlatformRef", "mentioned"),
        _occ("dependency", "npm:@angular/platform-server", "mentioned"),
    ]
    result = apply_contract(answer=_answer("behavioral", 0.8), occurrences=occurrences,
                            settings=load_settings())
    assert result.signal == "behavioral"
    assert result.keys == ["npm:@angular/core#PlatformRef", "npm:@angular/platform-server"]


def test_guard_and_floor_fall_back_with_locator_keys() -> None:
    from migration_oracle.pipeline.signals.contract import apply_contract
    from migration_oracle.pipeline.signals.settings import load_settings

    # `syntax` chosen but the rule only names a class: guard → behavioral + locator
    occurrences = [_occ("class", "npm:@angular/common#NgClass", "removed")]
    guarded = apply_contract(answer=_answer("syntax", 0.9), occurrences=occurrences,
                             settings=load_settings())
    assert (guarded.signal, guarded.source) == ("behavioral", "guard")
    assert guarded.keys == ["npm:@angular/common#NgClass"]

    # `universal` below its floor → behavioral, still with the locator keys
    floored = apply_contract(answer=_answer("universal", 0.4), occurrences=occurrences,
                             settings=load_settings())
    assert (floored.signal, floored.source) == ("behavioral", "low_confidence")
    assert floored.keys == ["npm:@angular/common#NgClass"]
