"""Infinispan stub tests."""

from __future__ import annotations

import pytest

from migration_oracle.pipeline.extractors.infinispan import InfinispanExtractor


@pytest.mark.asyncio
async def test_infinispan_not_implemented() -> None:
    async with InfinispanExtractor() as extractor:
        with pytest.raises(NotImplementedError, match="Infinispan"):
            await extractor.extract("15.0.0", "16.0.0")
