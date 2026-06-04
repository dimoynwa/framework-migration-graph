"""RESTEasy extractor stub."""

from __future__ import annotations

from migration_oracle.pipeline.extractors.base import BaseExtractor
from migration_oracle.pipeline.extractors.stubs import StubExtractor

PIPELINE_DOC = "docs/export-extract-populate-framework-pipeline.md"


class RestEasyExtractor(StubExtractor):
    framework_key = "resteasy"
    display_name = "RESTEasy"
    stub_name = "RESTEasy"
