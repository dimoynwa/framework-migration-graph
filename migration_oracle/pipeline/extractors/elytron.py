"""WildFly Elytron extractor stub."""

from __future__ import annotations

from migration_oracle.pipeline.extractors.stubs import StubExtractor

# TODO: apply is_jboss_ga_version filter in version discovery
# (same pattern as hibernate.py: filter when config.JBOSS_SKIP_PRERELEASE)


class ElytronExtractor(StubExtractor):
    framework_key = "elytron"
    display_name = "WildFly Elytron"
    stub_name = "WildFly Elytron"
