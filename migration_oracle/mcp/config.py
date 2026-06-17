"""MCP server mode configuration loaded once at import time."""

from __future__ import annotations

import os

_VALID_MODES = frozenset({"full", "lite"})
_raw = os.getenv("MIGRATION_MODE", "full").strip().lower()

if _raw not in _VALID_MODES:
    raise ValueError(
        f"Invalid MIGRATION_MODE={_raw!r}; valid options are: full, lite"
    )

MIGRATION_MODE: str = _raw
