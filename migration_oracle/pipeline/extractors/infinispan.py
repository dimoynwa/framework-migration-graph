"""Infinispan extractor stub."""

from __future__ import annotations

from migration_oracle.pipeline.extractors.stubs import StubExtractor

# Planned tag candidates (version first, then .Final for pre-16.x compatibility):
# TAG_CANDIDATES = ["{version}", "{version}.Final"]


class InfinispanExtractor(StubExtractor):
    framework_key = "infinispan"
    display_name = "Infinispan"
    stub_name = "Infinispan"
