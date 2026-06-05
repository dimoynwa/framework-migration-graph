"""Shared pre-release version filters for Maven-based extractors."""

from __future__ import annotations

import os

from migration_oracle import config
from migration_oracle.pipeline.extractors.base import (
    is_infinispan_ga_version,
    is_jboss_ga_version,
)

__all__ = [
    "is_jboss_ga_version",
    "is_infinispan_ga_version",
    "_skip_prerelease",
]


def _skip_prerelease() -> bool:
    """Return True when pre-release versions should be filtered out."""
    val = os.environ.get("JBOSS_SKIP_PRERELEASE")
    if val is None:
        return config.JBOSS_SKIP_PRERELEASE
    return val.strip().lower() not in ("0", "false", "no")
