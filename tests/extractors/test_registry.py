"""Extractor registry tests."""

from __future__ import annotations

import pytest

from migration_oracle.pipeline.extractors import get_extractor, supported_framework_keys
from migration_oracle.pipeline.extractors.stubs import StubExtractor


@pytest.mark.parametrize(
    "key",
    [
        "spring-boot",
        "angular",
        "wildfly",
        "eap",
        "hibernate",
        "resteasy",
        "infinispan",
        "elytron",
        "jakarta-ee",
    ],
)
def test_registry_instantiates_all_nine_keys(key: str) -> None:
    extractor = get_extractor(key)
    assert extractor.framework_key == key or extractor.display_name


def test_unknown_framework_raises() -> None:
    with pytest.raises(ValueError, match="Supported"):
        get_extractor("unknown-framework")


def test_stub_extractors_raise_not_implemented() -> None:
    for key in ("resteasy", "elytron"):
        extractor = get_extractor(key)
        assert isinstance(extractor, StubExtractor)
        with pytest.raises(NotImplementedError, match="export-extract-populate-framework"):
            import asyncio

            asyncio.run(extractor.extract("1.0.0", "2.0.0"))


def test_supported_keys_count() -> None:
    keys = supported_framework_keys()
    assert len(keys) >= 9
    assert "spring-boot" in keys
    assert "jakarta-ee" in keys
