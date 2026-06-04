# Implementation Plan: Pipeline Core

**Branch**: `002-pipeline-core` | **Date**: 2026-06-03 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/002-pipeline-core/spec.md`

## Summary

The pipeline-core module drives the two-LLM-call transformation of raw upstream data into a populated Neo4j/Memgraph graph. It extracts entities, filters changes, produces cached artifacts (Markdown, JSON), and optionally writes typed nodes and edges into the graph in an idempotent manner.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: httpx (with SSL_VERIFY), LangChain
**Storage**: Neo4j/Memgraph graph database (via `migration_oracle.graph.driver`), local file system (`runs/` directory cache)
**Project Type**: CLI tool & pipeline processor
**Constraints**: Idempotent graph writes, deterministic LLM extraction to valid JSON, caching with `--force` override.

## Constitution Check

*GATE: Passed. Complies with project constitution.*
- Standard HTTP communication using `httpx` with `SSL_VERIFY` respected.
- All environment variables read via `migration_oracle.config`.
- Graph driver sessions initialized exclusively via `migration_oracle.graph.driver`.

## Project Structure

### Documentation (this feature)

```text
specs/002-pipeline-core/
├── plan.md              # This file (/speckit-plan command output)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
migration_oracle/
├── cli.py               # CLI entry point
├── config.py            # Environment config
├── graph/
│   ├── driver.py        # Graph driver initialization
│   └── queries/
│       └── pipeline.py  # Pipeline query module
├── models/
│   └── entities.py      # Data models (read-only)
└── pipeline/
    ├── _llm.py          # LangChain provider factory
    ├── _cache.py        # Artifact cache helper
    ├── filters.py       # Filter-and-group LLM call
    ├── extractor.py     # Entity-extraction LLM call
    └── populator.py     # Graph population

runs/                    # Created on startup by CLI
├── raw/
├── nodes/
└── json/
```

**Structure Decision**: A single module pipeline orchestrating LangChain LLM calls, interfacing with read-only entity models, and populating the graph via queries. The `runs/` directory stores artifacts for cache reuse.

## Module Responsibilities & Tech Choices

- **`migration_oracle/pipeline/_llm.py`**: LangChain provider factory. Implements `get_llm()` using the `MODEL_PROVIDER` environment variable, preventing duplicated provider-construction logic in the pipeline. MUST support all six providers: `bedrock`, `openai`, `anthropic`, `ollama`, `litellm`, and `google`.
- **`migration_oracle/pipeline/_cache.py`**: Artifact cache helper. Implements six distinct cache conditions that operate independently per artifact, including: JSON existing with no `--force-llm` skips both LLM calls; filtered MD existing with no `--force-llm` but raw was cached skips the filter call but still runs entity LLM if JSON is missing.
- **`migration_oracle/pipeline/filters.py`**: Filter-and-group LLM call, prompt assembly, raw MD → filtered MD, filtered MD cache write, stale warning logic. Uses `_llm.py` and `_cache.py`.
- **`migration_oracle/pipeline/extractor.py`**: Entity-extraction LLM call, prompt assembly, filtered MD → JSON, JSON cache write, `MigrationEntitiesBatch` validation. Uses `_llm.py` and `_cache.py`.
  - **Structured Output Fallback**: Implements a two-step structured output mechanism: first attempts `with_structured_output(MigrationEntitiesBatch)`; if it fails (validation error or provider incompatibility), falls back to a plain text call, strips code fences, and validates manually.
  - **Empty List Validation**: Must treat an empty entity list in the extraction response as a failure. The response must contain at least one entity; otherwise, the extraction fails with exit code 1 (avoiding silently writing zero-entity artifacts).
- **`migration_oracle/pipeline/populator.py`**: All graph writes, `Version` node upsert, artifact path write, `REPLACED_BY` derivation, `entityClassification` derivation.
  - **`REPLACED_BY` Cross-Product Derivation**: When there are multiple removed and multiple replacement entities of the same kind, all combinations are created (cross-product), not a zip pairing.
  - **`SOURCE_SECTION_TO_RULE_TYPE`**: Defines a module-level dict constant authoritative mapping for `source_section` → `ruleType`. `ruleType` is always read from this mapping. Unrecognized `source_section` raises `ValueError`.
  - **Legacy Mapping Superseded**: The legacy substring mapping from `change_type` → `ruleType` (documented in reference Phase 7) is explicitly superseded by `SOURCE_SECTION_TO_RULE_TYPE` for all new nodes and MUST NOT appear in this code.
- **`migration_oracle/graph/queries/pipeline.py`**: `version_exists`, `upsert_version_artifact_paths`, `list_pipeline_runs`.
- **`migration_oracle/cli.py`**: CLI argument parsing, force/cache flag logic, extractor registry dispatch, orchestration of filters → extractor → populator.
- **`runs/` directory creation on startup**: The CLI ensures `runs/raw/`, `runs/nodes/`, and `runs/json/` directories exist on initialization.
- **Retry & Resilience Constants**: The plan relies on `EXTRACTION_RATE_LIMIT_RETRIES` (default `3`) and an exponential backoff schedule (`2s, 4s, 8s`) used across LLM-calling modules to handle rate limits.
- **Data Models Coverage**: `data-model.md` fully enumerates all intermediate and extraction sub-types (including `AffectedEntity`, `MigrationStep`, `BreakingScopeInput`, `StepType`, `Effort`, `ScopeLevel`, `Severity`) to provide the necessary field names for Cypher population mapping.