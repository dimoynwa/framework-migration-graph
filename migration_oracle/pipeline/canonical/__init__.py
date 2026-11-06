"""Entity canonicalization (spec 025): one canonical identity per entity.

Public entry points:

- :func:`canonicalize_batch` — normalize + verify one ``MigrationEntitiesBatch``
- :func:`write_canonical_audit` — the ``runs/canonical/`` artifacts (FR-5)
- :func:`profile_for` — the per-framework profile
"""

from migration_oracle.models.entities import CanonicalEntity
from migration_oracle.pipeline.canonical.api_index import HopApiIndex
from migration_oracle.pipeline.canonical.normalize import NormalizedEntity, normalize_rule
from migration_oracle.pipeline.canonical.profiles import FrameworkProfile, profile_for
from migration_oracle.pipeline.canonical.run import (
    CanonicalRule,
    CanonicalizedBatch,
    canonicalize_batch,
    write_canonical_audit,
)

__all__ = [
    "CanonicalEntity",
    "CanonicalRule",
    "CanonicalizedBatch",
    "FrameworkProfile",
    "HopApiIndex",
    "NormalizedEntity",
    "canonicalize_batch",
    "normalize_rule",
    "profile_for",
    "write_canonical_audit",
]