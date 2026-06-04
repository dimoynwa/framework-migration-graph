# Framework HTTP Extractor Contracts

Boundary rules for `migration_oracle/pipeline/extractors/`.

1. **`extract()` is the only public interface** — `BaseExtractor.extract(from_version, to_version) -> ExtractionResult` (async). Range orchestration uses `extract_range()` on the same class.
2. **`cli.py` / orchestrator** call only `get_extractor(key)` then `await extractor.extract_range(from_version, to_version)` (or `extract()` for single-hop tooling).
3. **No circular imports** — extractors MUST NOT import `migration_oracle.pipeline.filters` or `migration_oracle.pipeline.extractor`.
4. **No side-effect I/O** — extractors MUST NOT write to the filesystem or Neo4j.
5. **HTTP client** — `httpx.AsyncClient` is created only in `base.py`; extractors use `self.fetch()` / `self.fetch_json()`.
6. **Shared types** — `DocumentedChange` and `ExtractionResult` are imported from `migration_oracle.models.entities`; extractors MUST NOT redefine them.
