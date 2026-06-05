"""RESTEasy extractor stub."""

from __future__ import annotations

from migration_oracle.pipeline.extractors.stubs import StubExtractor

PIPELINE_DOC = "docs/export-extract-populate-framework-pipeline.md"

# TODO: apply is_jboss_ga_version filter in version discovery
# (same pattern as hibernate.py: filter when config.JBOSS_SKIP_PRERELEASE)


class RestEasyExtractor(StubExtractor):
    framework_key = "resteasy"
    display_name = "RESTEasy"
    stub_name = "RESTEasy"
