"""MCP server lifespan hook for Paysafe resolver cache population."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from migration_oracle.paysafe import findit

logger = logging.getLogger(__name__)


@contextlib.asynccontextmanager
async def paysafe_cache_lifespan(_server):
    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, findit.populate_cache)
    except Exception as exc:
        logger.error("Failed to populate Paysafe resolver cache: %s", exc)
        raise
    yield
