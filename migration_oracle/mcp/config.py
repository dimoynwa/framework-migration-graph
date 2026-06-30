"""MCP server mode configuration loaded once at import time."""

from __future__ import annotations

import os

_VALID_MODES = frozenset({"full", "lite"})
_raw = os.getenv("MIGRATION_MODE", "lite").strip().lower()

if _raw not in _VALID_MODES:
    raise ValueError(
        f"Invalid MIGRATION_MODE={_raw!r}; valid options are: full, lite"
    )

MIGRATION_MODE: str = _raw

# Optional harness stage for per-session tool gating (015-split-migration-harness).
# When unset, all tools for the active MIGRATION_MODE are registered.
MCP_ACTIVE_STAGE: str | None = os.getenv("MCP_ACTIVE_STAGE", "").strip().lower() or None

VALID_ACTIVE_STAGES: frozenset[str] = frozenset({
    "plan",
    "gap-check",
    "clarify",
    "preview",
    "execute",
    "feedback",
})
