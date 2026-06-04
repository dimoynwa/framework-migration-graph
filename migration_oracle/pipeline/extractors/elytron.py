"""WildFly Elytron extractor stub."""

from __future__ import annotations

from migration_oracle.pipeline.extractors.stubs import StubExtractor


class ElytronExtractor(StubExtractor):
    framework_key = "elytron"
    display_name = "WildFly Elytron"
    stub_name = "WildFly Elytron"
