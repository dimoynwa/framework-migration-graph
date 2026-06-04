"""RESTEasy stub tests."""

from __future__ import annotations

import pytest

from migration_oracle.pipeline.extractors.resteasy import RestEasyExtractor


@pytest.mark.asyncio
async def test_resteasy_not_implemented() -> None:
    async with RestEasyExtractor() as extractor:
        with pytest.raises(NotImplementedError, match="RESTEasy"):
            await extractor.extract("6.0.0", "7.0.0")
