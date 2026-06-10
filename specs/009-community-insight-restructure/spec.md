# Feature Specification: Community Insight Restructure

**Feature Branch**: `009-community-insight-restructure`

**Created**: 2026-06-09

**Status**: Draft

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Submit a Community Insight (Priority: P1)

A developer discovers an undocumented migration edge case while upgrading from Spring Boot 2.7 to 3.0. They submit the workaround via the `submit_migration_insight` MCP tool so the knowledge is captured for future upgraders.

**Why this priority**: This is the primary write path for community knowledge. All other community tools depend on data written by this tool. Getting the write correct — including the node type, relationships, and properties — is the foundation of the whole feature.

**Independent Test**: Call `submit_migration_insight` with a valid insight and confirm the response contains `{status, insight_id, duplicate_of, message}`. Then query the graph to verify a `MigrationRule` node with `ruleType='community_insight'` exists, linked to the correct `Version` via `INCLUDES_RULE`, with a `MigrationStep` child via `REQUIRES_STEP`.

**Acceptance Scenarios**:

1. **Given** no existing insight matches the statement, **When** `submit_migration_insight` is called with a valid statement, solution, and version, **Then** a `MigrationRule` node with `ruleType='community_insight'` is created, a `MigrationStep` child is created with `stepType='manual'` and `instruction` equal to the solution, community provenance properties (`communitySubmittedBy`, `communityCreatedAt`, `communityConfidence`, `communityVotes=0`, `communityVerified=false`) are set on the rule, and the response has `status='success'` with a valid `insight_id`.
2. **Given** an existing insight with an identical statement already exists, **When** `submit_migration_insight` is called with the same statement, **Then** no new node is created and the response returns `duplicate_of` pointing to the existing rule's element ID.
3. **Given** embeddings are disabled (`POPULATE_MIGRATION_EMBEDDINGS=false`), **When** `submit_migration_insight` is called, **Then** the node is written without an `embedding` property, duplicate detection uses exact BM25 match only, and the tool does not raise an exception.
4. **Given** affected classes, properties, or dependencies are supplied, **When** the insight is written, **Then** `AFFECTS_CLASS`, `AFFECTS_PROPERTY`, and `AFFECTS_DEPENDENCY` relationships are created from the `MigrationRule` node to the corresponding entity nodes.

---

### User Story 2 - Retrieve Community Insights (Priority: P2)

A developer querying migration guidance for a Spring Boot upgrade expects to see community-contributed insights alongside official changelog rules, without having to set any special flag.

**Why this priority**: This is the primary read path. It validates that restructured nodes are queryable with the correct filters and that the external response shape is unchanged.

**Independent Test**: After submitting at least one insight for a known version range, call `get_community_insights` for that range and confirm the response contains the insight with all expected fields in the correct shape.

**Acceptance Scenarios**:

1. **Given** community insights exist for a version range, **When** `get_community_insights` is called with matching `from_version` and `to_version`, **Then** each insight in the response contains `{insight_id, statement, solution, source_url, submitted_by, created_at, confidence, votes, verified, version}` with `solution` drawn from the first `MigrationStep.instruction`.
2. **Given** `verified_only=True` is passed, **When** `get_community_insights` is called, **Then** only insights with `communityVerified=true` on the `MigrationRule` node are returned.
3. **Given** community insights exist as `MigrationRule` nodes, **When** `search_migration_knowledge` is called without any `include_community_insights` flag, **Then** community insights are returned automatically as part of the standard `MigrationRule` search results.

---

### User Story 3 - Vote and Verify Insights (Priority: P3)

Community moderators and developers can upvote useful insights and mark them as verified, improving trust signals for future consumers.

**Why this priority**: Voting and verification are quality-of-life features on top of the core read/write path. They operate on already-written nodes.

**Independent Test**: Submit an insight, note its `insight_id`, call `vote_insight` with `delta=1`, confirm `new_vote_count=1`. Then call `verify_insight`, confirm `verified=true`.

**Acceptance Scenarios**:

1. **Given** a community insight exists, **When** `vote_insight` is called with `delta=1`, **Then** `communityVotes` on the `MigrationRule` node increments by 1 and the response contains `{status, insight_id, new_vote_count}` with the updated count.
2. **Given** a community insight exists, **When** `vote_insight` is called with `delta=-1`, **Then** `communityVotes` decrements by 1.
3. **Given** a community insight exists, **When** `verify_insight` is called, **Then** `communityVerified` is set to `true` on the `MigrationRule` node and the response contains `{status, insight_id, verified: true}`.

---

### User Story 4 - Streamlit Community Page Renders Correctly (Priority: P4)

The Streamlit community page continues to work without modification after the tool rewrites, because its call signatures and return shapes are unchanged.

**Why this priority**: This is a regression guard. The page must not break, but since it calls tool functions by import, no structural page changes are expected.

**Independent Test**: Launch the Streamlit app, navigate to the Community page, submit a test insight, retrieve insights for a version range, and vote/verify — all interactions should succeed without errors.

**Acceptance Scenarios**:

1. **Given** the Streamlit app is running, **When** the Community page is loaded, **Then** it renders without errors and displays the submission form and insight list.
2. **Given** a community insight exists in the graph, **When** the community page fetches insights for a version range, **Then** the insight is displayed with all expected fields.

---

### Edge Cases

- What happens when a vector similarity check runs but the `migration_knowledge_vector_mr` index does not yet contain any community entries? (First submission must not error.)
- What happens when `submit_migration_insight` is called with `confidence` outside the expected range?
- What happens when `vote_insight` is called with an `insight_id` that does not exist in the graph?
- What happens if the `Version` node for the given `spring_boot_version` and `framework` does not exist?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST store community insights as `MigrationRule` nodes with `ruleType='community_insight'` — no node with the `CommunityInsight` label may be created or queried anywhere in the codebase after this spec.
- **FR-002**: Each community insight `MigrationRule` node MUST be linked to a `Version` node via `(v:Version)-[:INCLUDES_RULE]->(r:MigrationRule)`.
- **FR-003**: Each community insight `MigrationRule` node MUST have at least one `MigrationStep` child linked via `REQUIRES_STEP`, with `stepType='manual'`, `effort='moderate'`, `automatable=false`, and both `summary` and `instruction` set from the submitted `solution`.
- **FR-004**: Community provenance metadata MUST be stored on the `MigrationRule` node using prefixed property names: `communitySubmittedBy`, `communityCreatedAt`, `communityConfidence`, `communityVotes` (initial value: `0`), `communityVerified` (initial value: `false`).
- **FR-005**: The `submit_migration_insight` tool MUST perform near-duplicate detection before writing: first an exact statement BM25 match, then a vector cosine similarity check (threshold ≥ 0.92) against the `migration_knowledge_vector_mr` index when embeddings are enabled.
- **FR-006**: When `POPULATE_MIGRATION_EMBEDDINGS=false`, the `embedding` property MUST be omitted from the written node and duplicate detection MUST fall back to exact BM25 match only without raising an exception.
- **FR-007**: When embeddings are enabled, the embedding vector MUST be stored on the `MigrationRule` node (not on `MigrationStep`) so vector search results hydrate correctly.
- **FR-008**: The `submit_migration_insight` tool MUST create `AFFECTS_CLASS`, `AFFECTS_PROPERTY`, and `AFFECTS_DEPENDENCY` relationships from the `MigrationRule` node to entity nodes when the corresponding affected entities are provided.
- **FR-009**: The `get_community_insights` tool MUST query `MigrationRule` nodes filtered by `ruleType='community_insight'` and return each insight with the field mapping: `solution` retrieved by traversing `OPTIONAL MATCH (r)-[:REQUIRES_STEP]->(s:MigrationStep)` and taking the first result's `s.instruction`; `submitted_by`, `created_at`, `confidence`, `votes`, `verified` from the `community`-prefixed properties on the rule node. A rule with no step child returns `solution` as `null` rather than erroring.
- **FR-010**: The `get_community_insights` tool MUST support `verified_only=True` to filter results to `communityVerified=true` nodes only.
- **FR-011**: The `vote_insight` tool MUST match the target node by element ID against the `MigrationRule` label (not `CommunityInsight`), increment or decrement `communityVotes`, and return `{status, insight_id, new_vote_count}`.
- **FR-012**: The `verify_insight` tool MUST match the target node by element ID against the `MigrationRule` label (not `CommunityInsight`), set `communityVerified=true`, and return `{status, insight_id, verified}`.
- **FR-013**: The `include_community_insights` parameter MUST be removed from all three locations where it currently exists:
  - (a) the `search_migration_knowledge` tool function signature in `migration_oracle/mcp/graph/queries/search.py`;
  - (b) the `_build_hits` internal helper function signature in `migration_oracle/mcp/graph/queries/search.py`;
  - (c) the `hydrate_nodes` Cypher filter branch in `migration_oracle/mcp/graph/queries/search.py` — the `$include_community_insights` conditional in the Cypher string is deleted entirely.
  - (d) the `hydrate_nodes` Cypher projection in `migration_oracle/mcp/graph/queries/search.py` that currently reads `n.solution AS solution` MUST be updated to also traverse `OPTIONAL MATCH (n)-[:REQUIRES_STEP]->(s:MigrationStep)` for `ruleType='community_insight'` nodes so that `solution` is populated from `s.instruction`; without this change, community insight results return `solution=null` via the search path.
  Community insights are returned automatically via the existing `MigrationRule` search path once the filter branch is removed. Any call site that previously passed `include_community_insights=False` MUST also be cleaned up.
- **FR-014**: All four community tool function signatures (`submit_migration_insight`, `get_community_insights`, `vote_insight`, `verify_insight`) MUST remain byte-for-byte identical to their pre-spec versions (parameter names, types, defaults, and order). No `@mcp.tool()` decorators may be altered. Docstrings are explicitly excluded from this constraint — they are not part of the MCP tool signature — and are covered by FR-016.
- **FR-015**: The `migration_oracle/streamlit_app/pages/05_community.py` page MUST render and function correctly after the tool rewrites without any structural changes to the page itself.
- **FR-016**: All Cypher query strings inside `migration_oracle/mcp/graph/queries/community.py` that currently match `(ci:CommunityInsight)` MUST be rewritten to match `(r:MigrationRule)` (or a label-agnostic element ID lookup). Specifically:
  - `_FIND_EXACT_STATEMENT`: change `MATCH (ci:CommunityInsight)` → `MATCH (r:MigrationRule)`
  - `_FETCH_EMBEDDING`: change `MATCH (ci:CommunityInsight)` → `MATCH (r:MigrationRule)` and project `r.embedding`
  - `_VOTE_INSIGHT`: change `MATCH (ci:CommunityInsight)` → `MATCH (r:MigrationRule)` and reference `communityVotes` (not `votes`)
  - `_VERIFY_INSIGHT`: change `MATCH (ci:CommunityInsight)` → `MATCH (r:MigrationRule)` and set `communityVerified=true` (not `verified`)
  Any docstring in the tool layer that references `CommunityInsight` (e.g., "Writes a CommunityInsight node") MUST be updated to reference `MigrationRule` with `ruleType='community_insight'`.
- **FR-017**: The BM25 duplicate-detection call in `community.py` (`_best_bm25_duplicate`) currently uses `index="migration_text"`. After the restructure it MUST switch to `index="rule_statement"` (which covers `MigrationRule.statement`). The `migration_text` index definition in `migration_oracle/graph/indexes.py:27` MUST be updated to remove `CommunityInsight` from the label list, leaving only `MigrationRule`.
- **FR-018**: The `RuntimeError` message in `submit_insight()` that currently reads `"Failed to create CommunityInsight"` MUST be updated to `"Failed to create community insight MigrationRule"`. When the `Version` node for the given `framework` and `spring_boot_version` does not exist, the tool MUST return a structured `{status: "error", message: "Version not found: <framework> <version>"}` response rather than propagating a bare `RuntimeError` to the MCP caller.

### Key Entities

- **MigrationRule (community_insight)**: A `MigrationRule` node with `ruleType='community_insight'`. Carries all standard `MigrationRule` properties plus the `community`-prefixed provenance properties. Linked to a `Version` via `INCLUDES_RULE` and to at least one `MigrationStep` via `REQUIRES_STEP`.
- **MigrationStep**: Child of the community insight rule. Holds `stepType='manual'`, `effort='moderate'`, `automatable=false`, and the developer's `solution` text in both `summary` and `instruction`.
- **Version**: The target framework version the insight applies to. Identified by `spring_boot_version` and `framework` parameters.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All four community MCP tools return responses with identical field shapes to their pre-spec versions — no caller-visible contract change occurs.
- **SC-002**: A submitted community insight is retrievable via `get_community_insights` within the same session, with all fields correctly mapped from the underlying `MigrationRule` and `MigrationStep` nodes.
- **SC-003**: `search_migration_knowledge` returns community insights automatically without any `include_community_insights` flag, and no code path in the project references the removed parameter.
- **SC-004**: No code path in the project creates or queries a node with the `CommunityInsight` label — verified by grep across the entire codebase.
- **SC-005**: Near-duplicate detection prevents re-submission of an identical insight statement, returning a `duplicate_of` reference instead of creating a second node.
- **SC-006**: The Streamlit Community page loads and all community interactions (submit, list, vote, verify) complete without errors after the tool rewrites.
- **SC-007**: When embeddings are disabled, insight submission succeeds without exceptions and the written node carries no `embedding` property.
- **SC-008**: `search_migration_knowledge` results for community insight rules include a non-null `solution` value drawn from the first `MigrationStep.instruction` — not from a non-existent `solution` property on the rule node.
- **SC-009**: Submitting an insight for a framework/version combination that does not exist in the graph returns a structured error response (`status: "error"`) rather than an unhandled exception propagating to the MCP caller.

## Assumptions

- The `migration_knowledge_vector_mr` vector index already covers `MigrationRule.embedding`; no new index DDL is required.
- The `rule_statement` fulltext index on `MigrationRule.statement` already covers community insight statements; no new fulltext index is required.
- The old `migration_knowledge_vector_ci` vector index (if present in the live database) is obsolete and can be dropped manually; after this spec no code references it.
- `migration_oracle/graph/indexes.py` currently references `CommunityInsight` in the `migration_text` fulltext index definition (`indexes.py:27`); that label must be removed as part of this spec (see FR-017). The file otherwise requires no other changes.
- The `import` path `migration_oracle.mcp.graph.queries.community` is unchanged; only the Cypher strings and helper logic inside that module change.
- The Streamlit community page calls tool functions by Python import and does not issue direct Cypher queries, so it requires no structural changes.
- Existing `MigrationRule` nodes for official changelog rules are unaffected; only nodes with `ruleType='community_insight'` carry the `community`-prefixed properties.
