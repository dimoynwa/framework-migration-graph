# Extractor Contracts

This document defines the interface contracts for the framework HTTP extractors.

## Public Interface

- `BaseExtractor.extract(from_version: str, to_version: str) -> ExtractionResult` is the **ONLY** public contract between the orchestrator (`cli.py` / `filters.py`) and the extractor layer.
- `cli.py` and `filters.py` must **ONLY** call `get_extractor(key).extract(from_version, to_version)`.

## Extractor Constraints

- Extractors **MUST NOT** call `filters.py` or `extractor.py` (no circular imports).
- Extractors **MUST NOT** write to the filesystem or to Neo4j.
- The shared HTTP client factory lives in `base.py`; individual extractors must call it rather than instantiating `httpx.AsyncClient` directly.
- `DocumentedChange` and `ExtractionResult` are imported from `migration_oracle.models`; extractors must not define a parallel type.
- Jira enrichment results are available within `extract()` before it returns — the orchestrator **never** calls a separate enrich step.
- Extractor instantiation is stateless at import. Extractors **MUST NOT** make HTTP calls, read files, or read environment variables inside `__init__.py` or at module-level in any extractor file. Configuration reads happen lazily in `BaseExtractor.__init__()` only.
