# Feature Specification: Pipeline Core

**Feature Branch**: `002-pipeline-core`

**Created**: 2026-06-03

**Status**: Draft

**Input**: User description: "The pipeline-core module drives the two-LLM-call transformation of raw upstream data into a populated Neo4j/Memgraph graph. It accepts a DocumentedChange list from any registered framework extractor, runs a filter-and-group LLM call to produce a structured Markdown artifact, runs an entity-extraction LLM call to produce a MigrationEntitiesBatch JSON artifact, and optionally writes MigrationRule, MigrationStep, BreakingScope, and typed entity nodes into the graph. It also owns the CLI entry point and the artifact-caching layer."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Process Framework Changes (Priority: P1)

As a downstream tool consumer (MCP server, Streamlit UI), I need clean, typed, graph-queryable migration rules derived from noisy change records so that I can use them reliably without seeing irrelevant changes.

**Why this priority**: Core functionality; downstream systems depend exclusively on this structured output.

**Independent Test**: Can be fully tested by running the pipeline on a known raw markdown report and validating that the output filtered markdown and entities JSON match expected structures.

**Acceptance Scenarios**:

1. **Given** a raw Markdown report containing noisy and relevant changes, **When** the pipeline is run for a version range, **Then** a severity-ordered filtered Markdown document is produced without tests, CI, docs, or non-user-facing refactors.
2. **Given** a filtered Markdown document, **When** the pipeline entity-extraction runs, **Then** a `MigrationEntitiesBatch` JSON document is produced containing ordered `MigrationStep` nodes and typed `AffectedEntity` lists with correct roles.

---

### User Story 2 - Idempotent Graph Population (Priority: P1)

As a graph administrator, I need the pipeline to write extraction outputs to the graph idempotently so that running the pipeline multiple times does not create duplicate nodes or edges.

**Why this priority**: Prevents graph corruption and data duplication.

**Independent Test**: Can be tested by running the graph populator twice with the same entities JSON and verifying node/edge counts remain identical.

**Acceptance Scenarios**:

1. **Given** a generated `MigrationEntitiesBatch`, **When** the graph populator is executed, **Then** nodes (`Version`, `MigrationRule`, `MigrationStep`, `BreakingScope`, `AffectedEntity`) and edges (`REQUIRES`, `HAS_SCOPE`, `AFFECTS_*`, `REPLACED_BY`) are merged/created correctly.
2. **Given** an existing populated graph for a version range, **When** the populator is run again with the same data, **Then** no new duplicate nodes or edges are created.

---

### User Story 3 - Dry Run & Artifact Caching (Priority: P2)

As a developer running the pipeline, I need to be able to dry-run the pipeline to inspect artifacts before modifying the graph, and rely on cached LLM responses when re-running unless explicitly forced.

**Why this priority**: LLM calls are expensive and time-consuming; graph modifications should be verifiable beforehand.

**Independent Test**: Run with `--dry-run` and verify artifacts are created but graph is untouched. Run again without `--force` and verify artifacts are reused.

**Acceptance Scenarios**:

1. **Given** a version range, **When** the pipeline is run with `--dry-run`, **Then** the raw MD, filtered MD, and entities JSON artifacts are produced in the `runs/` directory, but the graph remains untouched.
2. **Given** existing cached artifacts, **When** the pipeline is run without `--force` flags, **Then** the cached files are reused, and file modification times do not change.
3. **Given** existing filtered artifacts, **When** the pipeline is run with `--force-extract` but not `--force-llm`, **Then** a warning is printed to the console and the pipeline continues using the cached filtered artifact (it does NOT abort).

---

### Edge Cases

- What happens when a version range has no upstream data?
- How does the system handle an LLM timeout or malformed JSON response?
- What happens if the `MODEL_PROVIDER` environment variable is missing?
- How does the system handle legacy graphs without `MigrationStep` or `BreakingScope` nodes during backwards-compatible queries?

## Clarifications

### Session 2026-06-03
- Q: Should there be a CLI option to skip a version if raw MD, filtered MD, and graph version already exist? → A: Yes, the CLI must provide an option (e.g., `--skip-existing`) to skip processing a version entirely if the raw MD artifact, filtered MD artifact, and the Version node in the graph already exist.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST accept a `DocumentedChange` list from a framework extractor and execute a filter-and-group LLM call to produce a seven-section severity-ordered Markdown document (`runs/nodes/{framework}-{from}-to-{to}-changes_filtered.md`). The filter prompt MUST include the `{changes_text_markdown_table}` placeholder as the raw MD injection point. The output MUST be stripped of ```markdown fences automatically if the model wraps its response, and the pipeline MUST NOT abort if the model emits a preamble — it strips and proceeds.
- **FR-002**: System MUST execute an entity-extraction LLM call on the filtered Markdown to produce a `MigrationEntitiesBatch` JSON document (`runs/json/{framework}-{from}-to-{to}-entities.json`). The prompt MUST include the placeholders `{framework}` (display name, e.g. "WildFly") and `{changes_text}` (filtered MD).
- **FR-003**: System MUST NOT paraphrase the `Title` column and MUST derive `source_section` from the emoji section header. The system MUST map `source_section` to `ruleType` deterministically using the following mapping: `breaking_change` → `breaking`, `security_fix` → `mandatory_migration`, `component_upgrade` → `mandatory_migration`, `security_config` → `mandatory_migration`, `behavioral` → `behavioral`, `deprecation` → `deprecation`, `new_capability` → `behavioral`. It MUST NOT be re-derived from `change_type` via substring matching.
- **FR-004**: System MUST parse typed `AffectedEntity` lists with correct roles (`removed`, `replacement`, `co-required`, `mentioned`) and derive `REPLACED_BY` edges exactly as follows: for each entity in the `entities[]` list, if an entry has role="removed" and another entry with the same label type has role="replacement" within the same `MigrationEntity`, create a `REPLACED_BY` edge between them. The system MUST NEVER derive `REPLACED_BY` from a string field on the entity.
- **FR-005**: System MUST populate the graph idempotently: `Version` nodes MUST be `MERGE`d on `(framework, version)` and compute/write `sortableVersion` (major×1_000_000 + minor×1_000 + patch) at `MERGE` time. `MigrationRule` keyed on `sourceUrl`, `MigrationStep` keyed on `(ruleId, stepIndex)`, `BreakingScope` keyed on `(scope, severity)`, and `AffectedEntity` keyed on `name`.
- **FR-006**: System MUST skip all graph write operations when the `--dry-run` flag is provided. Independently of `--dry-run`, the populator MUST perform a pre-write check: if a `Version` node for the target framework and version already exists in the graph, the graph write MUST be skipped to guarantee idempotency.
- **FR-007**: System MUST reuse existing artifacts in the `runs/` directory unless overridden by `--force`, `--force-extract`, or `--force-llm` flags.
- **FR-008**: System MUST emit a warning and continue (NOT abort) if `--force-extract` is set but `--force-llm` is not, when a filtered MD or entities JSON artifact already exists.
- **FR-009**: System MUST read all environment variables via `migration_oracle.config` and use `migration_oracle.graph.driver` to acquire graph driver sessions.
- **FR-010**: System MUST provide the CLI entry point `export-extract-populate-framework` requiring `--framework`, `from_version`, and `to_version`. It MUST also support optional path override flags: `--output-md <path>`, `--output-filtered-md <path>`, and `--output-json <path>`.
- **FR-011**: System MUST provide query helpers in `graph/queries/pipeline.py` (`version_exists`, `upsert_version_artifact_paths`, `list_pipeline_runs`) using `OPTIONAL MATCH` where necessary for backwards compatibility. `list_pipeline_runs` MUST query `Version` nodes `WHERE rawMdPath IS NOT NULL`, returning `framework`, `version`, `rawMdPath`, `filteredMdPath`, `entitiesJsonPath`.
- **FR-012**: System MUST abort with a non-zero exit code and a clear error message if the filter LLM call or entity extraction LLM call fails after retries; no partial artifact is written; the run is not recorded in the graph.
- **FR-013**: System MUST retry both LLM calls up to `EXTRACTION_RATE_LIMIT_RETRIES` (default 3) times with exponential backoff on rate-limit errors (HTTP 429 or provider-specific throttle exceptions), and MUST NOT retry other errors.
- **FR-014**: System MUST provide a CLI option (e.g., `--skip-existing`) to skip processing a version entirely. The pipeline MUST evaluate this check *before* any HTTP extraction occurs. The run MUST be skipped if and only if all three conditions are true: (1) the raw MD artifact exists, AND (2) the filtered MD artifact exists, AND (3) the `Version` node exists in the graph. If any condition is false, the pipeline proceeds normally.
- **FR-015**: System MUST derive `entityClassification` internally within `populator.py`. The derivation MUST be: if `len(steps) > 0` then `"actionable"`, else if `len(entities) > 0` then `"incomplete"`, else `"informational"`. The system MUST NEVER read `entityClassification` from the LLM JSON output.
- **FR-016**: System MUST explicitly handle malformed JSON responses from the entity extraction LLM. If the JSON fails `MigrationEntitiesBatch` validation, the pipeline MUST abort with a non-zero exit code and a clear validation error message, and MUST NOT write a partial JSON artifact to disk.
- **FR-017**: On startup, the CLI MUST ensure the `runs/raw/`, `runs/nodes/`, and `runs/json/` subdirectories exist, raising a clear error if the parent path is not writable.
- **FR-018**: System MUST write `AUTOMATED_BY` infrastructure for steps. When a `MigrationStep` has `automatable=true`, the population layer MUST write the step-level `AUTOMATED_BY` edge and related infrastructure required for later recipe mapping.

### Key Entities *(include if feature involves data)*

- **MigrationRule**: Represents a distinct change/migration instruction. Has a `ruleType` derived from the `source_section` mapping. Never stores `actionStep`.
- **MigrationStep**: Represents individual steps. Contains `step_type`, `effort`, `automatable`, `requires[]`, and `verification`. Linked via `REQUIRES` edges.
- **BreakingScope**: Details the impact scope and severity, linked to versions or rules.
- **AffectedEntity**: Typed nodes (`Class`, `Dependency`, `ApplicationProperty`) linked via role-based edges.
- **Version**: A specific framework version, storing the artifact paths (`rawMdPath`, `filteredMdPath`, `entitiesJsonPath`).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of pipeline executions are idempotent during graph population (zero duplicate nodes/edges created on rerun).
- **SC-002**: 100% of pipeline artifacts are successfully cached and reused without modification unless explicit `--force` flags are passed.
- **SC-003**: 100% of graph driver sessions are initialized exclusively via `migration_oracle.graph.driver`.
- **SC-004**: The `--dry-run` flag successfully produces all 3 artifacts without initiating any write transactions on the Neo4j/Memgraph instance.

## Assumptions

- Standard HTTP communication will be performed using `httpx` with `SSL_VERIFY` respected, not `requests`.
- `MigrationEntitiesBatch` and all related subtypes are pre-defined in `migration_oracle.models.entities`.
- The deterministic emoji-to-enum mapping is robust enough for all valid section headers.
- The `MODEL_PROVIDER` will dictate the LangChain provider to be initialized.
