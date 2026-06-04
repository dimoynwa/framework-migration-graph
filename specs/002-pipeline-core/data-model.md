# Data Model: Pipeline Core

## Types & Schemas

- **`DocumentedChange`**: Input contract from extractors (defined in 002, consumed here).
- **`FilterResult`**: Intermediate type representing the result of the filter LLM call.
  - `filtered_md`: `str`
  - `artifact_path`: `Path`
- **`ExtractionResult`**: Intermediate type representing the result of the extraction LLM call.
  - `batch`: `MigrationEntitiesBatch`
  - `artifact_path`: `Path`

### Extracted JSON Schema (`MigrationEntitiesBatch`)
- **`MigrationEntitiesBatch`**:
  - `entities`: `list[MigrationEntity]`
- **`MigrationEntity`**:
  - `source_section`: `str`
  - `title`: `str`
  - `entities`: `list[AffectedEntity]`
  - `steps`: `list[MigrationStep]`
  - `scopes`: `list[BreakingScopeInput]`
- **`AffectedEntity`**:
  - `name`: `str`
  - `type`: `str` (`Class`, `Dependency`, `ApplicationProperty`)
  - `role`: `str` (`removed`, `replacement`, `co-required`, `mentioned`)
- **`MigrationStep`**:
  - `step_type`: `StepType`
  - `effort`: `Effort`
  - `automatable`: `bool`
  - `requires`: `list[int]`
  - `verification`: `str`
- **`BreakingScopeInput`**:
  - `scope`: `ScopeLevel`
  - `severity`: `Severity`
- **Enums**:
  - `ScopeLevel` (e.g., `Compile`, `Runtime`, `Configuration`)
  - `Severity` (e.g., `Error`, `Warning`, `Info`)
  - `StepType` (e.g., `Refactor`, `DependencyUpdate`, `ConfigChange`)
  - `Effort` (e.g., `Trivial`, `Low`, `Medium`, `High`)

### Graph Derivations
- **`REPLACED_BY` Derivation (Cross-Product Rule)**: When creating `REPLACED_BY` edges from `AffectedEntity` nodes inside a `MigrationEntity`, all entities with `role="removed"` and all entities with `role="replacement"` of the same type must be paired using a cross-product (many-to-many). For example, if there are 2 removed and 3 replacement entities, 6 `REPLACED_BY` edges are created.
- **`PopulationResult`**: Result of the graph population process.
  - `rules_written`: `int`
  - `steps_written`: `int`
  - `scopes_written`: `int`
  - `entities_written`: `int`
  - `version_created`: `bool`
- **`PipelineRunRecord`**: Represents a pipeline execution run.
  - `framework`: `str`
  - `from_version`: `str`
  - `to_version`: `str`
  - `raw_md_path`: `str`
  - `filtered_md_path`: `str`
  - `entities_json_path`: `str`

## Storage Keys & Constants

- **Artifact key format**: `{framework}-{from_version}-to-{to_version}`
  - Example: `wildfly-29.0.0-to-30.0.0`
- **Directory constants**: `RUNS_RAW`, `RUNS_NODES`, `RUNS_JSON` (from config or hardcoded under project root)
- **Retry & Resilience Constants**:
  - `EXTRACTION_RATE_LIMIT_RETRIES`: `3` (default maximum retries for rate-limit errors on LLM calls)
  - **Backoff schedule**: `2s, 4s, 8s` (exponential backoff sequence)
