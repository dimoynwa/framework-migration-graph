# Component Contracts & Boundaries: Pipeline Core

## Module Ownership

- **`_llm.py`** owns: LangChain provider factory, configuring `get_llm()` via `MODEL_PROVIDER`.
- **`_cache.py`** owns: Artifact cache management (`mtime` checks) and `--force` flag bypassing logic.
- **`filters.py`** owns: LLM call 1, prompt assembly, raw MD → filtered MD, filtered MD cache write, stale warning logic.
- **`extractor.py`** owns: LLM call 2, prompt assembly, filtered MD → JSON, JSON cache write, `MigrationEntitiesBatch` validation, structured output fallback path, empty entity list check (exit 1).
- **`populator.py`** owns: all graph writes, `Version` node upsert, artifact path write, `REPLACED_BY` cross-product derivation, `entityClassification` derivation, `SOURCE_SECTION_TO_RULE_TYPE` mapping (superseding legacy substring matching).
- **`pipeline/queries/pipeline.py`** owns: `version_exists`, `upsert_version_artifact_paths`, `list_pipeline_runs`.
- **`cli.py`** owns: CLI argument parsing, force/cache flag logic, extractor registry dispatch, orchestration of filters → extractor → populator.

## Boundary Rules

- **FORBIDDEN**: Any graph write outside `populator.py` and `pipeline/queries/pipeline.py`.
- **FORBIDDEN**: Any direct `os.environ` access outside `config.py`.
- **FORBIDDEN**: Any `neo4j.GraphDatabase.driver()` call outside `graph/driver.py`.
- **READ-ONLY**: `models/entities.py` — pipeline-core imports, never modifies.
