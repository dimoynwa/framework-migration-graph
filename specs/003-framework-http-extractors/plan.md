# Implementation Plan: Framework HTTP Extractors

**Branch**: `003-framework-http-extractors` | **Date**: 2026-06-04 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/003-framework-http-extractors/spec.md`

## Summary

Implements all nine framework HTTP extractors that conform to the `ExtractionResult` output contract. Each extractor, given `(from_version, to_version)` for one version hop, returns an `ExtractionResult` containing a list of `DocumentedChange` objects to be consumed by the filter-and-group LLM step. A central registry maps CLI framework keys to extractor classes.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: `httpx`, `beautifulsoup4`, `anyio` (or `asyncio`)

**Storage**: N/A (Extractors do not write to storage)

**Testing**: `pytest`, `pytest-asyncio`, HTTP mocking (`respx` or `pytest-httpx`)

**Target Platform**: CLI / Pipeline Orchestrator

**Project Type**: Library module within `migration_oracle`

**Performance Goals**: Efficient concurrent fetching for Jira enrichment (up to `JIRA_MAX_CONCURRENT`)

**Constraints**: Extractors must not call `filters.py` or `extractor.py` (no circular imports). All HTTP must be async.

**Scale/Scope**: 9 framework extractors, supporting various documentation sources (GitHub, Maven, npm, Red Hat docs, AsciiDoc).

## Constitution Check

*GATE: Passed.*

## Project Structure

### Documentation (this feature)

```text
specs/003-framework-http-extractors/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output (to be generated)
```

### Source Code (repository root)

```text
migration_oracle/pipeline/extractors/
├── __init__.py
├── base.py
├── spring_boot.py
├── angular.py
├── wildfly.py
├── eap.py
├── hibernate.py
├── resteasy.py
├── infinispan.py
├── elytron.py
└── jakarta_ee.py

tests/extractors/
├── test_spring_boot.py
├── test_angular.py
├── test_wildfly.py
├── test_wildfly_jira.py
├── test_eap.py
├── test_hibernate.py
├── test_jakarta_ee.py
└── test_registry.py
```

**Structure Decision**: Extractors are placed in `migration_oracle/pipeline/extractors/` with a dedicated module for each framework. Tests are organized in `tests/extractors/` mirroring the implementation modules.

## Technical Decisions

- **ExtractionResult vs list[DocumentedChange]**: `cli.py` (or the orchestrator) unwraps `ExtractionResult.changes` before passing to `filters.py`. `filters.py` is not modified — it continues to receive `list[DocumentedChange]`.
- All HTTP is async via `httpx.AsyncClient`. The shared HTTP client is instantiated once per extractor instance (in `__init__`) and reused across hops.
- WildFly Jira enrichment uses `anyio.create_task_group` (or `asyncio.gather`) for up to `JIRA_MAX_CONCURRENT` concurrent fetches (imported from `migration_oracle.config`).
- Maven metadata XML parsing uses the standard library `xml.etree.ElementTree`. To handle namespace-qualified XML from Maven Central mirrors robustly, implementations must strip or ignore namespaces when searching for the `<version>` elements within `<versioning><versions>`.
- **Tag Candidate Ordering**: Tag candidates are tried in a defined order, and the first 200-series response wins. This order is framework-specific:
  - **Infinispan**: `{version}` first, then `{version}.Final` (16.x dropped `.Final`).
  - **Hibernate**: `{version}` first; `{version}.Final` is a safety fallback that never resolves.
  - **WildFly**: `{version}.Final` only — there is no bare `{version}` fallback.
  - **Other GitHub extractors**: Most specific first (e.g., `v{version}` then `{version}`).
- **AsciiDoc Parsing**: Hibernate ORM ≥ 6 AsciiDoc migration guides are parsed using a custom pure-Python regex-based approach (string parsing), as no `asciidoc` CLI is available and third-party libraries add unnecessary bloat.
- **HTML Parsing**: HTML parsing uses BeautifulSoup with the `html.parser` backend (stdlib, no extra dependency). `lxml` is explicitly excluded.
- **DocumentedChange Amendment**: `DocumentedChange` in `migration_oracle/models/entities.py` (spec 001-pipeline-core) gains `metadata: dict | None = None` as a backward-compatible addition. This edit must be the first implementation task — it is a prerequisite for all extractors that set stability level.
- URL-level cache is a `dict[str, str | bytes]` on the shared client instance, not a decorator or middleware.
- EAP uses a module-level tuple of `EAPVersionEntry` objects, not a config file.
- Jakarta EE namespace mappings are a module-level list of `JakartaEENamespaceMapping`, not fetched or computed at runtime.
- WildFly version normalization (`30.0.1.Final` → `30.0.1`) is a pure string operation applied at version discovery time, before any hop computation.
- Jira key regex is compiled once at module level; not recompiled per statement.

## Extractor Contracts

The `contracts/003-framework-http-extractors.md` file defines the following boundary rules:
1. `BaseExtractor.extract()` is the ONLY public contract between the orchestrator (`cli.py` / `filters.py`) and the extractor layer.
2. `cli.py` and `filters.py` must ONLY call `get_extractor(key).extract(from_version, to_version)`.
3. Extractors MUST NOT call `filters.py` or `extractor.py` (no circular imports).
4. Extractors MUST NOT write to the filesystem or to Neo4j.
5. The shared HTTP client factory lives in `base.py`; individual extractors must call it rather than instantiating `httpx.AsyncClient` directly.
6. `DocumentedChange` and `ExtractionResult` are imported from `migration_oracle.models`; extractors must not define a parallel type.

## Implementation Order & Parallelism

1. **Sequential Prerequisites**: `base.py` and the registry skeleton (`__init__.py`) must be implemented first.
2. **Parallel Implementation**: Once the base is established, the following full extractors are independent and their implementation tasks can run in parallel (marked with `[P]` in `tasks.md`):
   - `spring_boot.py`
   - `angular.py`
   - `wildfly.py`
   - `eap.py`
   - `hibernate.py`
   - `jakarta_ee.py`
   - `resteasy.py` (stub implementation, but must be added to complete registry)
   - `infinispan.py` (stub implementation, but must be added to complete registry)
   - `elytron.py` (stub implementation, but must be added to complete registry)
