# SpecKit Runbook — `009-community-insight-restructure`

> **How to use this file:** Paste each prompt block verbatim into Claude Code in the order shown.
> Do not skip the gap-review steps — they catch the most common drift before it compounds.
> Complete all items in a gap review before advancing to the next command.

---

## Prerequisites

Before starting this spec:

- `005-mcp-server` ✅ — `MigrationRule`, `MigrationStep`, and `Version` nodes with
  `INCLUDES_RULE` and `REQUIRES_STEP` relationships must be live in the graph
- `006a-streamlit-ui-redesign` ✅ — `migration_oracle/streamlit_app/pages/05_community.py`
  is the redesigned card-based community page; it calls `get_community_insights`,
  `submit_migration_insight`, `vote_insight` from `migration_oracle.mcp.tools.community`
  and reads `votes`, `verified`, `solution`, `source_url` from the response dict
- There are **zero** `CommunityInsight` nodes in the database — confirmed before starting;
  if any exist, they must be migrated or dropped before this spec runs
- Reference files to keep open during gap reviews:
  - `migration_oracle/mcp/tools/community.py` — all four tool signatures (`submit_migration_insight`,
    `get_community_insights`, `vote_insight`, `verify_insight`)
  - `migration_oracle/mcp/graph/queries/community.py` — Cypher queries, `find_near_duplicate`,
    `submit_insight`, `query_insights`; note vector index name `migration_knowledge_vector_ci`
    used in `find_near_duplicate` — this must change to `migration_knowledge_vector_mr`
  - `migration_oracle/mcp/tools/search.py` — `search_migration_knowledge` signature and
    `_build_hits`; note `include_community_insights` param on both
  - `migration_oracle/mcp/graph/queries/search.py` — `hydrate_nodes` Cypher; note the
    `$include_community_insights OR 'MigrationRule' IN labels(n)` filter that must be removed
  - `migration_oracle/streamlit_app/pages/05_community.py` — no structural changes needed;
    verify it still works after the underlying tool rewrites

---

## Command 1 — `/speckit.specify`

Paste this entire block:

```
/speckit.specify

WHAT it does:
This spec restructures how community-sourced migration knowledge is stored in the graph.
Community insights — developer-contributed workarounds and edge-case findings — are no
longer stored as a separate `CommunityInsight` node label. They are stored as
`MigrationRule` nodes (with `ruleType = 'community_insight'`) linked to `Version` via
`INCLUDES_RULE`, each with at least one `MigrationStep` child via `REQUIRES_STEP`.
The four community MCP tools (`submit_migration_insight`, `get_community_insights`,
`vote_insight`, `verify_insight`) retain their external signatures and return shapes.
The `search_migration_knowledge` tool no longer needs an `include_community_insights`
flag — community insights are returned automatically by the existing MigrationRule
search path.

WHY it exists:
The `CommunityInsight` node label creates a parallel graph path that duplicates the
MigrationRule → MigrationStep traversal pattern. This forces every consumer
(search, plan builder, Streamlit UI) to special-case a second node type. Flattening
community insights into the MigrationRule schema gives them `effort`, `automatable`,
and `stepType` properties — making them first-class inputs to recipe plan building
and migration context tracking, without any caller-visible contract change.

COMMUNITY TOOLS and what they do:
  submit_migration_insight(statement, spring_boot_version, solution, affected_properties,
    affected_classes, affected_dependencies, evidence_url, confidence, framework)
    - Near-duplicate detection runs before write (exact statement match, then vector
      similarity ≥ 0.92 against the MigrationRule vector index)
    - On a novel insight: creates a `MigrationRule` node with `ruleType='community_insight'`
      linked via `INCLUDES_RULE` to the matching `Version` node; creates one `MigrationStep`
      child via `REQUIRES_STEP` with `stepType='manual'`, `summary` and `instruction` both
      set from `solution`, `effort='moderate'`, `automatable=false`; community provenance
      properties stored on the `MigrationRule` node using prefixed names to distinguish them
      from official rule fields: `communitySubmittedBy`, `communityCreatedAt`,
      `communityConfidence`, `communityVotes=0`, `communityVerified=false`; embedding stored
      on the `MigrationRule` node
    - If embeddings are disabled (`POPULATE_MIGRATION_EMBEDDINGS=false`), the embedding
      parameter is `None`; near-duplicate detection falls back to exact-statement BM25 match
      only and the node is written with no `embedding` property — this mirrors the fix
      introduced in spec 008 bug fix #3
    - Returns: `{status, insight_id, duplicate_of, message}` — identical shape to today
    - `AFFECTS_CLASS`, `AFFECTS_PROPERTY`, `AFFECTS_DEPENDENCY` relationships from the
      `MigrationRule` node to entity nodes are preserved

  get_community_insights(from_version, to_version, entity_name, entity_type, verified_only,
    framework)
    - Queries `MigrationRule` nodes WHERE `ruleType = 'community_insight'` linked via
      `INCLUDES_RULE` to `Version` nodes matching the given framework and version range
    - Returns: `{status, insights, total}` where each insight record contains:
      `{insight_id, statement, solution, source_url, submitted_by, created_at, confidence,
      votes, verified, version}` — identical external shape to today
    - Internal mapping: `solution` ← first `MigrationStep.instruction` via `REQUIRES_STEP`;
      `submitted_by` ← `r.communitySubmittedBy`; `created_at` ← `r.communityCreatedAt`;
      `confidence` ← `r.communityConfidence`; `votes` ← `r.communityVotes`;
      `verified` ← `r.communityVerified`
    - `verified_only=True` filters on `r.communityVerified = true`

  vote_insight(insight_id, delta)
    - Increments or decrements `communityVotes` on the `MigrationRule` node with the given
      element ID
    - Returns: `{status, insight_id, new_vote_count}` — identical shape to today;
      `new_vote_count` is read from `communityVotes` after the update

  verify_insight(insight_id)
    - Sets `communityVerified=true` on the `MigrationRule` node with the given element ID
    - Returns: `{status, insight_id, verified}` — identical shape to today;
      `verified` is read from `communityVerified`

SEARCH TOOL change:
  search_migration_knowledge — the `include_community_insights` parameter is removed.
  Community insights (stored as `MigrationRule` nodes) are returned automatically by
  the existing MigrationRule search path. The `hydrate_nodes` Cypher in
  `migration_oracle/mcp/graph/queries/search.py` removes the
  `$include_community_insights` filter branch entirely.

STREAMLIT PAGE:
  `migration_oracle/streamlit_app/pages/05_community.py` calls the community tool
  functions by import — it does NOT query the graph directly. Because the tool
  signatures and return shapes are unchanged, the page requires no structural
  changes. Only verify it still renders correctly after the tool rewrites.

KEY BEHAVIORS:
SAME_TOOL_SIGNATURES — All four community tool function signatures are byte-for-byte
  identical to their pre-spec versions. No caller needs to update call sites.
SAME_RETURN_SHAPES — `get_community_insights` returns the same `insights` list shape;
  `submit_migration_insight` returns the same `{status, insight_id, duplicate_of, message}`;
  `vote_insight` returns the same `{status, insight_id, new_vote_count}`;
  `verify_insight` returns the same `{status, insight_id, verified}`.
COMMUNITY_PROPERTIES_PREFIXED — On the `MigrationRule` node, all community-specific
  metadata uses the `community` prefix: `communityVotes`, `communityVerified`,
  `communitySubmittedBy`, `communityCreatedAt`, `communityConfidence`. The external
  tool response maps these back to the unprefixed names (`votes`, `verified`, etc.) so
  the Streamlit page and MCP callers see no change. This avoids polluting the MigrationRule
  property namespace with semantics that do not apply to official changelog rules.
EMBEDDING_OPTIONAL — When `POPULATE_MIGRATION_EMBEDDINGS=false`, `embedding` is `None`;
  the write proceeds without the `embedding` property and duplicate detection uses
  BM25 exact-match only. The tool must not raise when embedding is None.
EMBEDDING_ON_RULE — The embedding vector is stored on the `MigrationRule` node, not on
  the `MigrationStep` node, so that vector search hits continue to return `MigrationRule`
  element IDs and hydrate correctly.
DUPLICATE_DETECTION_USES_MR_INDEX — Near-duplicate detection in `find_near_duplicate`
  uses the vector index `migration_knowledge_vector_mr` (not the removed
  `migration_knowledge_vector_ci`) for cosine similarity checks.
NO_COMMUNITY_INSIGHT_LABEL — No code anywhere in the project creates or queries nodes
  with the `CommunityInsight` label after this spec. No compatibility shim, no re-export.
STEP_CREATED_PER_SUBMIT — Every `submit_migration_insight` call that writes a new
  `MigrationRule` also writes at least one `MigrationStep` child. A rule with no steps
  is not a valid outcome of this tool.
INCLUDE_CI_FLAG_REMOVED — The `include_community_insights` parameter is removed from
  `search_migration_knowledge` and from `_build_hits`/`hydrate_nodes`. Code that
  previously passed `include_community_insights=False` to `search_openrewrite_recipes`
  is cleaned up.

INTEGRATION CONSTRAINTS:
- MigrationRule nodes written by this tool must carry `ruleType = 'community_insight'`;
  this is the sole discriminator used by `get_community_insights` to filter results
- Relationship direction: `(v:Version)-[:INCLUDES_RULE]->(r:MigrationRule)` — the
  Version node is the source, consistent with all other MigrationRule writes
- The fulltext index `rule_statement` on `MigrationRule.statement` already covers
  community insight statements — no new index DDL is required
- The vector index `migration_knowledge_vector_mr` already covers `MigrationRule.embedding` —
  no new vector index DDL is required; the old `migration_knowledge_vector_ci` index
  (if it exists in the live DB) can be dropped manually but is not referenced by any code
- `migration_oracle/graph/indexes.py` requires no changes — it no longer references
  `CommunityInsight` (verified on main branch post-spec-008 merge)
- Import path for community queries: `migration_oracle.mcp.graph.queries.community` —
  unchanged; only the Cypher strings and helper functions inside change
- Do NOT change the `@mcp.tool()` decorator on any community tool — tool registration
  is managed by the FastMCP instance and must not be disrupted
```

---

## Gap Review — Post-Specify

After Claude Code generates `specs/009-community-insight-restructure/spec.md`, check these items
before running `/speckit.plan`:

```
Review the generated spec.md for 009-community-insight-restructure and verify these items
before we proceed to planning:

GAP-001: Embedding placement is unambiguous
  The spec must state that the embedding vector is stored on the MigrationRule node, not on
  the MigrationStep node. Vector search indexes MigrationRule.embedding — if the embedding
  lands on the step, search results will not hydrate correctly.
  If the spec is vague about which node carries the embedding, make it explicit.

GAP-002: Duplicate detection vector index named correctly
  The spec must state that find_near_duplicate uses vector index `migration_knowledge_vector_mr`
  after the change. The old index `migration_knowledge_vector_ci` is specific to the
  CommunityInsight label being removed. If the spec says "the existing vector index" without
  naming it, correct it to name migration_knowledge_vector_mr explicitly.

GAP-003: solution field sourced from MigrationStep
  get_community_insights returns a `solution` field in each insight record. After the change,
  there is no `solution` property on the MigrationRule node — solution is stored as
  MigrationStep.instruction. The spec must state that the Cypher for get_community_insights
  retrieves solution via OPTIONAL MATCH on the REQUIRES_STEP child step.
  If this is absent or vague, add it.

GAP-004: INCLUDES_RULE relationship direction stated
  The spec must state the relationship direction explicitly:
  (v:Version)-[:INCLUDES_RULE]->(r:MigrationRule), i.e., Version is the source node.
  If the spec omits the direction or implies the reverse, correct it — an incorrect
  direction means zero rows returned from all community queries.

GAP-005: include_community_insights removal scope
  The spec must cover all three locations where include_community_insights appears today:
  (a) search_migration_knowledge tool signature in search.py
  (b) _build_hits helper signature in search.py
  (c) hydrate_nodes Cypher filter in mcp/graph/queries/search.py
  If any location is omitted, add it — a partial removal will leave unreachable dead code.

GAP-006: vote_insight and verify_insight use MigrationRule label
  The spec must state that vote_insight and verify_insight match nodes by elementId against
  MigrationRule (or label-agnostic MATCH), not CommunityInsight. If these tools are not
  mentioned in the restructure, add a clause confirming their Cypher is updated.

GAP-007: Streamlit page no-change contract stated
  The spec must explicitly state that 05_community.py requires no structural changes —
  tool signatures and return shapes are identical. A vague "frontend is updated" statement
  is not acceptable because it will cause the implementer to make unnecessary changes.
  The page only needs a live smoke-test to confirm it still renders correctly.

GAP-008: MigrationStep minimum content defined
  The spec must state the minimum field values for the MigrationStep written by submit:
  stepType='manual', summary=solution, instruction=solution, effort='moderate',
  automatable=false. If only "at least one MigrationStep is created" is stated without
  field values, add the specifics — the implementer will otherwise guess.

GAP-009: Community property prefix applied consistently
  The spec must state that community-specific metadata on the MigrationRule node uses
  prefixed property names: communityVotes, communityVerified, communitySubmittedBy,
  communityCreatedAt, communityConfidence. If any of these appear as unprefixed names
  (votes, verified, submittedBy, etc.) on the node schema, correct them — unprefixed
  names would collide with or confuse official MigrationRule properties in future readers.
  The external tool response still returns the unprefixed names; the mapping happens
  in the Python query wrapper, not in the Cypher property names.

GAP-010: Embedding-disabled path handled
  The spec must state that when embedding is None (POPULATE_MIGRATION_EMBEDDINGS=false),
  submit_migration_insight still writes the MigrationRule + MigrationStep successfully;
  the embedding property is simply omitted from the node; and duplicate detection falls
  back to BM25 exact-match only. This was fixed in spec 008 bug fix #3 and must be
  preserved in the new implementation.

Fix all gaps before running /speckit.plan.
```

---

## Command 2 — `/speckit.plan`

Paste this entire block:

```
/speckit.plan


Read specs/009-community-insight-restructure/spec.md and produce the full planning
artifacts for this spec.

Required artifacts to produce in specs/009-community-insight-restructure/:

1. plan.md — File-by-file change plan covering:
   - Python 3.11+ as the runtime constraint; no new dependencies required
   - migration_oracle/mcp/graph/queries/community.py: full rewrite of all Cypher strings
     and helper functions (_FIND_EXACT_STATEMENT, _FETCH_EMBEDDING, _SUBMIT_INSIGHT,
     _QUERY_INSIGHTS, _VOTE_INSIGHT, _VERIFY_INSIGHT, find_near_duplicate, submit_insight,
     query_insights, vote_insight, verify_insight); note that _FETCH_EMBEDDING must now
     fetch from MigrationRule, not CommunityInsight; _SUBMIT_INSIGHT must write a
     MigrationRule + MigrationStep + INCLUDES_RULE + REQUIRES_STEP + optional AFFECTS_*
   - migration_oracle/mcp/tools/community.py: docstring updates only — no signature
     or return-shape changes; note that 'Writes a CommunityInsight node' must become
     'Writes a MigrationRule node with ruleType=community_insight'
   - migration_oracle/mcp/tools/search.py: remove include_community_insights parameter
     from search_migration_knowledge and _build_hits; update call site in
     search_openrewrite_recipes that passes include_community_insights=False
   - migration_oracle/mcp/graph/queries/search.py: remove $include_community_insights
     parameter and filter condition from hydrate_nodes; update Python wrapper to not
     pass the parameter
   - migration_oracle/graph/indexes.py: no changes needed (confirmed already clean)
   - migration_oracle/streamlit_app/pages/05_community.py: no changes needed;
     add to plan as explicit no-op with reason stated

2. data-model.md — All types, Cypher shapes, and node property sets:
   - MigrationRule (community_insight variant): all properties written by submit_insight
     {statement, ruleType='community_insight', sourceUrl,
     communitySubmittedBy, communityCreatedAt, communityConfidence,
     communityVotes=0, communityVerified=false, embedding (omitted when None)}
   - MigrationStep (community_insight variant): properties written per submission
     {stepType='manual', summary, instruction, effort='moderate', automatable=false}
   - CommunityInsightRecord: the external dict shape returned by get_community_insights
     per record — note the property mapping from node names to response names:
     {insight_id,
      statement        ← r.statement,
      solution         ← coalesce(s.instruction, '') via REQUIRES_STEP,
      source_url       ← r.sourceUrl,
      submitted_by     ← r.communitySubmittedBy,
      created_at       ← r.communityCreatedAt,
      confidence       ← r.communityConfidence,
      votes            ← r.communityVotes,
      verified         ← r.communityVerified,
      version          ← v.version}
   - SubmitInsightResult: {status, insight_id, duplicate_of, message}
   - VoteInsightResult: {status, insight_id, new_vote_count}   — new_vote_count ← communityVotes
   - VerifyInsightResult: {status, insight_id, verified}       — verified ← communityVerified

3. contracts/009-community-insight-restructure.md — Boundary rules:
   - submit_migration_insight MUST create a MigrationRule AND at least one MigrationStep
     in the same write transaction; partial writes (rule without step) are not valid
   - The embedding MUST be stored on MigrationRule.embedding, not MigrationStep.embedding;
     when embedding is None the property is omitted — the write MUST NOT raise
   - find_near_duplicate MUST use vector index `migration_knowledge_vector_mr` for
     vector similarity; the index `migration_knowledge_vector_ci` MUST NOT be referenced
   - get_community_insights MUST filter by ruleType='community_insight'; returning all
     MigrationRule nodes regardless of ruleType is incorrect
   - Community metadata MUST use prefixed property names on the node:
     communityVotes, communityVerified, communitySubmittedBy, communityCreatedAt,
     communityConfidence — the query layer maps these to the unprefixed external response
   - The `solution` field in the response MUST be sourced from MigrationStep.instruction
     via OPTIONAL MATCH on REQUIRES_STEP, not from a non-existent MigrationRule.solution
   - No code in the codebase may reference the CommunityInsight node label after this spec
   - The Streamlit page 05_community.py MUST NOT be structurally changed

4. research.md — Answer these questions:
   - Is the Cypher FOREACH pattern for creating optional AFFECTS_* relationships on the
     new MigrationRule node safe when the FOREACH list is empty? (yes — FOREACH over []
     is a no-op in Neo4j/Memgraph; confirm this is also true for the MigrationStep creation
     in the same query)
   - Does hydrate_nodes need a fallback for MigrationRule nodes that have no
     REQUIRES_STEP child? Some pre-existing MigrationRule nodes may not have steps.
     The $include_community_insights removal must not cause those nodes to be filtered out.
   - Does removing include_community_insights from search_migration_knowledge constitute
     a breaking change for any registered MCP client? (No — it is a boolean defaulting
     to True, meaning current callers that omit it already get all results; removing it
     changes nothing about the result set.)
Do not generate tasks.md — that comes from /speckit.tasks separately.
```

---

## Gap Review — Post-Plan

After Claude Code generates the plan artifacts, check these items before running `/speckit.tasks`:

```
Review the generated plan.md, data-model.md, contracts/, and research.md for
009-community-insight-restructure and verify these items before running /speckit.tasks:

PLAN-GAP-001: _SUBMIT_INSIGHT Cypher writes both rule and step atomically
  plan.md must state that the MigrationRule and MigrationStep are created in a single
  Cypher query (one write transaction). If the plan describes two separate queries
  (one for the rule, one for the step), correct it — a partial write must not be possible.

PLAN-GAP-002: INCLUDES_RULE direction in Cypher
  The _SUBMIT_INSIGHT Cypher pattern in plan.md must show:
    MATCH (v:Version {framework: $framework, version: $version})
    CREATE (v)-[:INCLUDES_RULE]->(r:MigrationRule {...})
  If the direction is reversed or omitted, correct it before tasks are generated.

PLAN-GAP-003: _QUERY_INSIGHTS Cypher retrieves solution from MigrationStep
  plan.md must show that _QUERY_INSIGHTS does:
    OPTIONAL MATCH (r)-[:REQUIRES_STEP]->(s:MigrationStep)
    WITH r, v, s ORDER BY s.stepIndex ASC LIMIT 1
  and returns s.instruction as `solution`. If solution is read from a rule property
  that won't exist, the get_community_insights tool will return empty solution strings.

PLAN-GAP-004: find_near_duplicate vector index name is explicit
  plan.md must state that find_near_duplicate calls vector_search with
  index='migration_knowledge_vector_mr'. If the plan says 'update the vector index name'
  without stating the new name, correct it to name migration_knowledge_vector_mr.

PLAN-GAP-005: hydrate_nodes change is scoped correctly
  plan.md must state exactly which line(s) in hydrate_nodes change:
  remove the `$include_community_insights` parameter from the Cypher string and the
  Python function signature. The rest of the MATCH and filter logic is unchanged.
  If plan.md describes a broader rewrite of hydrate_nodes, narrow the scope.

PLAN-GAP-006: 05_community.py is listed as explicit no-op
  plan.md must include an entry for migration_oracle/streamlit_app/pages/05_community.py
  marked as "no changes required" with the reason stated. If it is absent from the plan,
  add it — its absence will cause the implementer to either skip it or unnecessarily modify it.

PLAN-GAP-007: data-model.md solution field provenance
  data-model.md CommunityInsightRecord must annotate the `solution` field with its source:
  "read from first MigrationStep.instruction via REQUIRES_STEP". If it says
  "from MigrationRule.solution" or leaves the source unstated, correct it.

PLAN-GAP-009: data-model.md uses prefixed community property names
  data-model.md must list MigrationRule community_insight properties as communityVotes,
  communityVerified, communitySubmittedBy, communityCreatedAt, communityConfidence —
  NOT as votes, verified, submittedBy, createdAt, confidence. If unprefixed names appear
  in the node schema (as opposed to the CommunityInsightRecord response shape), correct them.

PLAN-GAP-010: research.md answers the embedding-disabled path
  research.md must confirm how submit_insight behaves when embedding=None. It must state
  that: (a) the MigrationRule is written without an embedding property, (b) find_near_duplicate
  skips vector search and uses exact-statement BM25 only, (c) no exception is raised.
  This preserves the spec 008 fix. If research.md is silent on this, add the answer.

PLAN-GAP-008: research.md answers the hydrate_nodes fallback question
  research.md must confirm whether nodes without REQUIRES_STEP children are correctly
  returned by hydrate_nodes after the include_community_insights filter is removed.
  If the answer is not present, add it — removing the wrong condition could silently
  filter all pre-existing official MigrationRule nodes.

Fix all gaps before running /speckit.tasks.
```

---

## Command 3 — `/speckit.tasks`

Paste this block:

```
/speckit.tasks

Read specs/009-community-insight-restructure/spec.md, plan.md, data-model.md, and
contracts/ and generate tasks.md for the 009-community-insight-restructure spec.

Task ordering requirements:
1. Rewrite migration_oracle/mcp/graph/queries/community.py (all Cypher + helpers) — first,
   because all tool and search changes depend on the new Cypher being correct
2. Update migration_oracle/mcp/tools/community.py docstrings — second, after queries are done
3. Remove include_community_insights from migration_oracle/mcp/tools/search.py and
   migration_oracle/mcp/graph/queries/search.py — can be done in parallel [P] with task 2
4. Unit tests for the rewritten community.py queries — verify submit writes rule+step,
   query returns solution from step, vote and verify match MigrationRule
5. Integration smoke-test: call submit_migration_insight, then get_community_insights,
   confirm the submitted insight appears; call vote_insight and verify_insight, confirm
   the response shapes match the pre-spec contracts
6. Streamlit page smoke-test: start the Streamlit app and navigate to 05_community.py;
   verify the page loads, the insight list renders (or shows empty state), and the submit
   form accepts input without traceback — this must be the last task

Mark tasks [P] where changes to separate files are independent (queries rewrite vs
docstring update vs search.py cleanup).

Include an explicit no-op task for 05_community.py confirming it needs no code changes.
```

---

## Gap Review — Post-Tasks

After Claude Code generates `specs/009-community-insight-restructure/tasks.md`, check these items
before running `/speckit.implement`:

```
Review the generated tasks.md for 009-community-insight-restructure and verify these items
before running /speckit.implement:

TASK-GAP-001: queries.community rewrite is the first task
  The task for rewriting migration_oracle/mcp/graph/queries/community.py must come before
  all other tasks. If any tool or search file task appears first, reorder.

TASK-GAP-002: unit test covers submit → rule+step atomicity
  There must be a unit/integration test task that verifies submit_migration_insight creates
  BOTH a MigrationRule AND a MigrationStep. A test that only checks the MigrationRule was
  created is insufficient — the step creation is a spec invariant.

TASK-GAP-003: unit test covers solution field sourcing
  There must be a test task that verifies get_community_insights returns the correct
  `solution` value by reading it from MigrationStep.instruction. If only the status
  and insight_id are asserted, add the solution field assertion.

TASK-GAP-004: unit test covers duplicate detection with mr vector index
  There must be a test task that confirms find_near_duplicate uses
  migration_knowledge_vector_mr, not migration_knowledge_vector_ci. A test that only
  checks the return value without checking which index is queried may miss this.

TASK-GAP-005: [P] markers on independent file tasks
  The docstring update task (community.py tools) and the search.py cleanup task are
  independent of each other and of the test tasks. Verify both are marked [P].

TASK-GAP-006: explicit no-op task for 05_community.py
  There must be a task entry for 05_community.py stating "no code changes required;
  verify page renders correctly via smoke-test". If this task is absent, add it.

TASK-GAP-007: Streamlit smoke-test is the final task
  The last task must be: start Streamlit, navigate to 05_community.py, verify the page
  loads and the submit form works end-to-end. If this is absent or placed before code tasks,
  reorder.

TASK-GAP-009: community property prefix tested
  There must be a test task that queries the raw MigrationRule node after submit and asserts
  that the node has communityVotes, communityVerified, communitySubmittedBy — NOT the
  unprefixed forms. A test that only checks the tool response dict (which uses unprefixed
  names after mapping) will not catch a missing prefix in the Cypher write.

TASK-GAP-010: embedding-None path tested
  There must be a test task that calls submit_migration_insight with embeddings disabled
  (mock or set embedding=None) and asserts the write succeeds without exception and the
  returned status is "ok". This guards the spec 008 fix from regressing.

TASK-GAP-008: file paths are fully nested
  All file paths must use the full nested form:
  migration_oracle/mcp/graph/queries/community.py — not just community.py or queries/community.py.
  Verify all file references in tasks.md.

Fix all gaps before running /speckit.implement.
```

---

## Command 4 — `/speckit.implement`

Paste this block:

```
/speckit.implement

Read specs/009-community-insight-restructure/tasks.md and implement all tasks in order,
respecting [P] parallelism markers. Follow these constraints exactly:

1. migration_oracle/mcp/graph/queries/community.py:
   - _SUBMIT_INSIGHT must CREATE a MigrationRule node (NOT CommunityInsight) with
     ruleType='community_insight' and prefixed community provenance properties
     (communitySubmittedBy, communityCreatedAt, communityConfidence,
     communityVotes=0, communityVerified=false) plus embedding when not None —
     then in the same query CREATE a MigrationStep child via REQUIRES_STEP with
     stepType='manual', summary=$solution, instruction=$solution,
     effort='moderate', automatable=false.
   - When embedding is None (POPULATE_MIGRATION_EMBEDDINGS=false), omit the embedding
     property from the CREATE clause entirely — use coalesce or conditional Cypher;
     the write must succeed without raising.
   - Relationship direction: (v:Version)-[:INCLUDES_RULE]->(r:MigrationRule).
   - _QUERY_INSIGHTS must MATCH (v:Version)-[:INCLUDES_RULE]->(r:MigrationRule) WHERE
     r.ruleType='community_insight', then OPTIONAL MATCH (r)-[:REQUIRES_STEP]->(s:MigrationStep)
     to retrieve solution from s.instruction.
   - find_near_duplicate must call vector_search with index='migration_knowledge_vector_mr',
     not 'migration_knowledge_vector_ci'.
   - _FETCH_EMBEDDING must match on MigrationRule, not CommunityInsight.
   - _VOTE_INSIGHT must SET ci.communityVotes = coalesce(ci.communityVotes, 0) + $delta
     and RETURN communityVotes as votes.
   - _VERIFY_INSIGHT must SET ci.communityVerified = true and RETURN communityVerified
     as verified.
   - Both must match on MigrationRule (or elementId-only MATCH with no label filter).

2. migration_oracle/mcp/tools/community.py:
   - Update docstrings only. Do not change any function signature, parameter name,
     parameter type, default value, or return shape.

3. migration_oracle/mcp/tools/search.py:
   - Remove the include_community_insights parameter from search_migration_knowledge
     and from _build_hits. Remove the call-site argument in search_openrewrite_recipes.
   - Do not change any other parameter or return shape.

4. migration_oracle/mcp/graph/queries/search.py:
   - Remove the $include_community_insights parameter and filter condition from
     hydrate_nodes. The line:
       AND ($include_community_insights OR 'MigrationRule' IN labels(n))
     becomes simply nothing — the filter is dropped entirely, not replaced.
   - Update the Python hydrate_nodes function signature to remove include_community_insights.

5. migration_oracle/streamlit_app/pages/05_community.py:
   - Make NO changes to this file. It calls tool functions by import; the tool signatures
     and return shapes are unchanged; the page will continue to work as-is.

6. migration_oracle/graph/indexes.py:
   - Make NO changes. It is already correct on the main branch.

After implementing each task, confirm the file exists at the correct path and that
no import of the CommunityInsight label string remains anywhere in the codebase.
```

---

## Recovery Prompts

Use these verbatim if implementation drifts:

### RECOVERY-01: CommunityInsight label still used in Cypher

```
The CommunityInsight node label must not appear in any Cypher string after this spec.
Every occurrence of MATCH (ci:CommunityInsight) or CREATE (ci:CommunityInsight {}) must
be replaced with MATCH (ci:MigrationRule) or CREATE (r:MigrationRule {...}) respectively.
Run: grep -r "CommunityInsight" migration_oracle/ to find all remaining occurrences and
remove them. Do not create a compatibility alias or shim.
```

### RECOVERY-02: Embedding stored on MigrationStep instead of MigrationRule

```
The embedding vector must be stored on the MigrationRule node, not on the MigrationStep node.
The vector search index migration_knowledge_vector_mr indexes MigrationRule.embedding.
If embedding is written to the step, search results will return step element IDs that
hydrate_nodes cannot resolve — all search hits will be silently dropped.
Move the embedding property to the MigrationRule node in the _SUBMIT_INSIGHT Cypher.
```

### RECOVERY-03: find_near_duplicate still references migration_knowledge_vector_ci

```
The vector index migration_knowledge_vector_ci was specific to the CommunityInsight label
being removed. After this spec it no longer exists or is populated.
In migration_oracle/mcp/graph/queries/community.py, find_near_duplicate must call:
  vector_search(embedding=embedding, index='migration_knowledge_vector_mr', ...)
Replace every occurrence of 'migration_knowledge_vector_ci' with 'migration_knowledge_vector_mr'.
```

### RECOVERY-04: get_community_insights returns empty solution strings

```
After the restructure, there is no MigrationRule.solution property. The solution field in
the CommunityInsightRecord is read from the first MigrationStep's instruction property.
The _QUERY_INSIGHTS Cypher must include:
  OPTIONAL MATCH (r)-[:REQUIRES_STEP]->(s:MigrationStep)
  WITH r, v, s ORDER BY s.stepIndex ASC LIMIT 1
and the RETURN clause must include: coalesce(s.instruction, '') AS solution
If solution is returned as '' for all records despite valid submissions, this is the cause.
```

### RECOVERY-05: 05_community.py unnecessarily modified

```
Do not modify migration_oracle/streamlit_app/pages/05_community.py.
The page calls get_community_insights, submit_migration_insight, and vote_insight by import.
All three tool functions retain their original signatures and return shapes after this spec.
The page does not query the graph directly and does not reference the CommunityInsight label.
Revert any changes to this file and re-run the Streamlit smoke-test to confirm it still works.
```

### RECOVERY-07: Community properties written without prefix

```
Community-specific metadata on MigrationRule must use prefixed property names:
communityVotes, communityVerified, communitySubmittedBy, communityCreatedAt, communityConfidence.
If the Cypher writes votes, verified, submittedBy, createdAt, or confidence directly onto
the MigrationRule node, those names collide with the property namespace of official rules
and will cause confusion for any future reader or query that scans all MigrationRule nodes.
Update the _SUBMIT_INSIGHT, _VOTE_INSIGHT, and _VERIFY_INSIGHT Cypher strings to use the
prefixed names. Update the Python query_insights wrapper to map communityVotes → votes,
communityVerified → verified, etc. in the returned dict.
```

### RECOVERY-08: submit raises when embedding is None

```
When POPULATE_MIGRATION_EMBEDDINGS=false, get_embedding_model().encode() is not called
and embedding is None. The _SUBMIT_INSIGHT Cypher must not include embedding in the
CREATE clause unconditionally — passing embedding=None as a Cypher parameter writes a
null property, which is fine, but any code that does `.tolist()` on a None value raises.
The fix (from spec 008 bug fix #3) is to guard the encode call:
  embedding = get_embedding_model().encode(statement).tolist() if embedding_enabled else None
and pass it directly; the Cypher CREATE uses: embedding: $embedding (null is stored as absent).
Do not re-introduce the unguarded encode call.
```

### RECOVERY-06: include_community_insights removed from the wrong location only

```
The include_community_insights parameter must be removed from all three locations:
  (a) search_migration_knowledge function signature in migration_oracle/mcp/tools/search.py
  (b) _build_hits helper signature in migration_oracle/mcp/tools/search.py
  (c) hydrate_nodes function signature and Cypher filter in
      migration_oracle/mcp/graph/queries/search.py
Run: grep -n "include_community_insights" migration_oracle/ -r
Any remaining occurrence is a bug. Each one must be removed or cleaned up.
```

---

## What Success Looks Like

After implementation, verify this sequence manually:

1. `grep -r "CommunityInsight" migration_oracle/` — **zero results** (no label references remain)
2. `grep -n "include_community_insights" migration_oracle/` — **zero results**
3. Call `submit_migration_insight(statement="Test insight", spring_boot_version="3.2", solution="Apply fix X")` via the MCP server or direct Python import — returns `{status: "ok", insight_id: <id>, ...}`
4. Query Neo4j directly: `MATCH (r:MigrationRule {ruleType:'community_insight'})-[:REQUIRES_STEP]->(s:MigrationStep) RETURN r.statement, r.communityVotes, r.communityVerified, s.instruction LIMIT 1` — returns one row; `communityVotes=0`, `communityVerified=false`, `s.instruction` matches the solution submitted
5. Call `get_community_insights(framework="Spring Boot")` — returns `{status: "ok", insights: [{statement: "Test insight", solution: "Apply fix X", ...}], total: 1}`
6. Call `vote_insight(insight_id=<id>, delta=1)` — returns `{status: "ok", new_vote_count: 1}`
7. Call `search_migration_knowledge(query="Test insight")` — returns the community insight in hits with `rule_type: "community_insight"`
8. Start Streamlit: `streamlit run migration_oracle/streamlit_app/app.py` — navigate to Community page — insight card renders with statement, solution, vote count; submit form accepts input and shows `st.success("Insight submitted")`

No `CommunityInsight` node label should appear in any Neo4j query, log line, or code path after step 1 passes.
