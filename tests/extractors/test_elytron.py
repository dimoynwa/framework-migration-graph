"""Elytron stub tests."""

from __future__ import annotations

import pytest

from migration_oracle.pipeline.extractors.elytron import ElytronExtractor


@pytest.mark.asyncio
async def test_elytron_not_implemented() -> None:
    async with ElytronExtractor() as extractor:
        with pytest.raises(NotImplementedError, match="WildFly Elytron"):
            await extractor.extract("2.0.0", "3.0.0")
