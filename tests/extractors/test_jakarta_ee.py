"""Jakarta EE extractor tests."""

from __future__ import annotations

import pytest

from migration_oracle.pipeline.extractors.jakarta_ee import JakartaEEExtractor


@pytest.mark.asyncio
async def test_crosses_ee9_boundary() -> None:
    async with JakartaEEExtractor() as extractor:
        result = await extractor.extract("8.0.0", "9.0.0")
    assert len(result.changes) >= 10
    packages = " ".join(c.statement for c in result.changes)
    assert "javax.servlet" in packages


@pytest.mark.asyncio
async def test_no_boundary_when_both_ge_9() -> None:
    async with JakartaEEExtractor() as extractor:
        result = await extractor.extract("9.0.0", "10.0.0")
    assert result.changes == []


@pytest.mark.asyncio
async def test_no_boundary_below_9() -> None:
    async with JakartaEEExtractor() as extractor:
        result = await extractor.extract("8.0.0", "8.0.0")
    assert result.changes == []
