# Feature Specification: Framework HTTP Extractors

**Feature Branch**: `003-framework-http-extractors`

**Created**: 2026-06-04

**Status**: Draft

**Input**: User description: "Implements all nine framework HTTP extractors that conform to the DocumentedChange output contract defined in 001-pipeline-core. Each extractor, given (from_version, to_version) for one version hop, returns a list of DocumentedChange objects to be consumed by the filter-and-group LLM step. A central registry maps CLI framework keys to extractor classes."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Extract Spring Boot and Angular Changes (Priority: P1)

As a pipeline orchestrator, I need to extract framework changes for Spring Boot and Angular so that I can process them in the downstream steps.

**Why this priority**: These are the most common frameworks and have clear documentation sources.

**Independent Test**: Can be fully tested by running the extraction for spring-boot or angular and verifying the output change objects for a given version range.

**Acceptance Scenarios**:

1. **Given** spring-boot framework and version range, **When** extract is called, **Then** it fetches metadata, releases, and returns an `ExtractionResult` containing `DocumentedChange` objects, attaching the BOM diff to extraction metadata only.
2. **Given** angular framework and version range, **When** extract is called, **Then** it fetches registry data, releases, parses changelogs, and returns an `ExtractionResult` containing `DocumentedChange` objects, storing blog insights in metadata only.

---

### User Story 2 - Extract WildFly, EAP, and Hibernate Changes (Priority: P2)

As a pipeline orchestrator, I need to extract framework changes for WildFly, EAP, and Hibernate so that I can process enterprise framework migrations.

**Why this priority**: These are complex enterprise frameworks with specific documentation and issue tracker enrichment.

**Independent Test**: Can be fully tested by running the extraction for wildfly, eap, or hibernate and verifying the output change objects.

**Acceptance Scenarios**:

1. **Given** wildfly framework and version range, **When** extract is called, **Then** it fetches metadata, releases, migration guides, and enriches with issue tracker data (supporting 3 regex formats and normalizing Jira hosts to redhat.atlassian.net).
2. **Given** eap framework and version range, **When** extract is called, **Then** it fetches enterprise docs using a fixed version table (7.0 through 8.0) and returns an `ExtractionResult`.
3. **Given** hibernate framework and version range, **When** extract is called, **Then** it fetches migration guides or releases and returns an `ExtractionResult`.

---

### User Story 3 - Extract Jakarta EE and Stub Extractors (Priority: P3)

As a pipeline orchestrator, I need to extract framework changes for Jakarta EE and handle stub extractors so that the registry is complete.

**Why this priority**: Jakarta EE is a static mapping, and stub extractors are placeholders for future implementation.

**Independent Test**: Can be fully tested by running the extraction for jakarta-ee or stub extractors and verifying the output change objects or expected errors.

**Acceptance Scenarios**:

1. **Given** jakarta-ee framework and version range crossing the namespace boundary (from < 9.0.0 to >= 9.0.0), **When** extract is called, **Then** it returns an `ExtractionResult` containing `DocumentedChange` objects for the namespace mapping.
2. **Given** resteasy, infinispan, or elytron framework, **When** extract is called, **Then** it raises a `NotImplementedError` with a descriptive message referencing the pipeline doc.

### Edge Cases

- What happens when an unknown framework key is requested? Raises `ValueError` with a list of supported keys.
- What happens when a network request times out on a hop? Extraction raises with a message including framework name, hop range, and URL.
- What happens when Jira unavailability occurs for WildFly? Caught internally, logged at WARNING, enrichment skipped, extraction continues.
- What happens when a version is not found in the metadata? Raises with a clear message (does not return empty list silently).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide an extractor registry mapping 9 framework keys to extractor implementations.
- **FR-002**: System MUST provide an abstract `BaseExtractor` with a shared network client factory and URL-level caching. The `extract(from_version: str, to_version: str)` method MUST be an `async` method and MUST return an `ExtractionResult`. Note: `ExtractionResult` is the new contract, and `filters.py` (from `001-pipeline-core`) MUST be updated to unwrap `ExtractionResult.changes` (cross-spec dependency).
- **FR-003**: System MUST implement Spring Boot extractor fetching metadata and releases. The range-level BOM diff MUST be attached to `ExtractionResult` metadata but does NOT appear as rows in the raw Markdown table. Note: Spring Boot 4.x exists (`v4.0.0`, `v4.1.0`), the Maven metadata URL and `v{version}` tag format are unchanged, and the extractor MUST NOT cap or reject versions above 3.x.
- **FR-004**: System MUST implement Angular extractor fetching registry data and releases. Angular blog insights MUST go into `ExtractionResult` metadata only and are NOT emitted as `DocumentedChange` objects.
- **FR-005**: System MUST implement WildFly extractor with Jira enrichment and stability level detection. The GitHub tag for a per-hop fetch MUST be `{version}.Final` using the full semver (e.g., `39.0.1.Final`), and MUST NOT use the `{major}.0.0.Final` pattern.
  - Jira enrichment MUST support three regex formats: (1) Jira HTML export anchor tags, (2) PR-merge commit style, (3) migration guide bullet style.
  - The set of Jira keys to fetch MUST be the union of keys found in the release-body index scan and keys found anywhere in parsed statement text.
  - The supported Jira key prefixes MUST be exactly: `WFLY`, `WFCORE`, `WFMP`, `JBEAP`, `EAP7`, `UNDERTOW`, `HAL`, `ISPN`, `HHH`.
  - Jira host normalization MUST convert `issues.redhat.com` browse links found in HTML to `redhat.atlassian.net` before any REST call.
  - Stability level detection MUST detect `[experimental]`, `[preview]`, and `[community]` markers, and store the detected level on `DocumentedChange` as a metadata field (not the type field).
- **FR-006**: System MUST implement EAP extractor fetching enterprise docs. It MUST use a fixed version table mapping: 7.0.0→7.0, 7.1.0→7.1, 7.2.0→7.2, 7.3.0→7.3, 7.4.0→7.4, 8.0.0→8.0. It MUST apply CLI hints just like WildFly — any statement containing a `/subsystem=` pattern is promoted to `mandatory_migration` + `confirmed`.
- **FR-007**: System MUST implement Hibernate extractor fetching migration guides or releases. The version-gated strategy MUST be explicit: major ≥ 6 uses AsciiDoc guide first with GitHub releases as fallback; major < 6 uses GitHub releases directly.
- **FR-008**: System MUST implement Jakarta EE extractor with static namespace mapping. "Crossing the EE 9 boundary" is defined precisely as: `fromVersion < 9.0.0 AND toVersion >= 9.0.0`. If both endpoints are >= 9.0.0, or if fromVersion is exactly 9.0.0, it MUST return an empty list.
- **FR-009**: System MUST implement stub extractors for resteasy, infinispan, and elytron. These MUST raise a `NotImplementedError` with a message that names the extractor and references the `export-extract-populate-framework-pipeline.md` documentation.
  - When Infinispan is implemented, tag candidates MUST be tried in the order `{version}` first, then `{version}.Final` for backward compatibility.
  - When Elytron is implemented, its post-processing MUST apply CLI migration hints (same as WildFly).
- **FR-010**: System MUST use asynchronous network requests for all external calls.
- **FR-011**: System MUST be able to parse HTML content for documentation extraction.
- **FR-012**: System MUST be able to parse AsciiDoc content for specific migration guides.
- **FR-013**: System MUST use the `DocumentedChange` object format for all outputs. `DocumentedChange` MUST be imported from `migration_oracle/models/` (or re-exported via `base.py`), and MUST NOT be defined as a second independent type inside `extractors/`.
- **FR-014**: System MUST NOT have side effects on import in the extractor registry.

### Key Entities *(include if feature involves data)*

- **ExtractionResult**: Wraps the extraction output, containing `changes: list[DocumentedChange]` and `metadata: dict`. This type MUST live in `migration_oracle/models/entities.py` alongside `DocumentedChange` to avoid circular dependencies.
- **DocumentedChange**: Represents a single documented change from a framework release or migration guide. Must be imported from `migration_oracle/models/entities.py`. It MUST have an optional `metadata: dict | None = None` field (to store properties like `stability_level`). This is a backward-compatible addition to the type owned by `001-pipeline-core`, and amends `001-pipeline-core`'s data-model.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The registry successfully instantiates all 9 extractors without error.
- **SC-002**: Spring Boot extractor returns an `ExtractionResult` with at least 1 `DocumentedChange` for `extract('3.3.0', '3.4.0')`.
- **SC-003**: WildFly extractor returns an `ExtractionResult` with at least 1 `DocumentedChange` enriched with Jira data for `extract('29.0.0', '30.0.0')`.
- **SC-004**: Pipeline orchestrator can call `extract()` on the base extractor and receive an `ExtractionResult` containing a list of `DocumentedChange` objects.

## Assumptions

- Authentication tokens are optional and used if available.
- Certificate validation can be controlled via configuration.
- Concurrent issue tracker requests are limited by configuration.
- Enterprise docs requests are delayed by configuration to avoid rate limits.
