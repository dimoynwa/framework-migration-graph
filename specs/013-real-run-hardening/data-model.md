# Data Model: Real-Run Hardening (013)

**Spec**: [spec.md](spec.md) | **Date**: 2026-06-14

---

## 1. sortableVersion Formula

No change from round-1.

```
sortableVersion = MAJOR × 1_000_000 + MINOR × 1_000 + PATCH
```

Examples: `3.5.12 → 3_005_012`, `4.0.6 → 4_000_006`, `4.1.0 → 4_001_000`.

Implementation: `migration_oracle/models/graph.py::sortable_version(version: str) -> int`.

---

## 2. resolve_version — Shared Resolution Routine

`resolve_version` is the **only** path that maps a `(framework, version)` string to a graph `Version` node. No tool may inline a separate resolution query.

### 2.1 Signature

```python
def resolve_version(
    framework: str,       # canonical framework slug (e.g. "Spring Boot")
    version: str,         # caller-supplied string (e.g. "3.5.12", "4.0", "4.0.6")
    mode: Literal["exact", "floor", "ceil"],
    *,
    allow_stub_create: bool = False,
) -> VersionResolutionResult | VersionResolutionFailure
```

### 2.2 Patch Preservation Rule

Before any graph query, the routine parses the version string:
- If a patch component is present (`3.5.12`) → it is preserved exactly throughout.
- If the patch is absent (`4.0`) → it is filled to `.0` (`4.0.0`) for graph query purposes. The caller's original string is stored as-is in the `requestedVersion` field of the result.
- The routine **never** truncates a caller-supplied patch.

### 2.3 Resolution Order by Mode

| Mode | Graph query | Behaviour |
|---|---|---|
| `exact` | `MATCH (v:Version {framework, version})` (exact normalised string) | Returns the matching node or `NO_CANDIDATE`. No rounding. |
| `floor` | `WHERE v.sortableVersion <= sortableVersion(requested) ORDER BY v.sortableVersion DESC LIMIT 1` scoped to `framework` | Returns highest catalogued node at or below request. `rounded=true` when the node version differs from the requested version. |
| `ceil` | `WHERE v.sortableVersion >= sortableVersion(requested) ORDER BY v.sortableVersion ASC LIMIT 1` scoped to `framework` | Returns lowest catalogued node at or above request. `rounded=true` when the node version differs. `aheadOfCatalogue=true` when no node at or above exists (clamped to highest). |

**Ahead-of-catalogue handling (ceil)**: when no Version node satisfies `≥ sortableVersion(requested)` for the given framework, the routine queries `ORDER BY v.sortableVersion DESC LIMIT 1` (highest available), sets `aheadOfCatalogue=true`, `rounded=true`, and returns that node — **never a rejection**.

**No minor-line match (any mode)**: when no Version node with the given `framework` exists at all, returns `VersionResolutionFailure` with `status: "NO_CANDIDATE"`. This is a distinct code from `aheadOfCatalogue`.

### 2.4 Output — Success

```python
@dataclass
class VersionResolutionResult:
    resolvedVersion: str        # the catalogued version string (e.g. "3.5.0")
    resolvedSortable: int       # sortableVersion of the resolved node
    nodeId: str                 # Neo4j elementId of the resolved Version node
    requestedVersion: str       # the original caller-supplied string
    rounded: bool               # True when resolvedVersion != requestedVersion
    aheadOfCatalogue: bool      # True when clamped to highest (ceil mode)
    stubCreated: bool           # True when allow_stub_create created a new node
    direction: Literal["floor", "ceil", "exact"]
```

### 2.5 Output — Failure

```python
@dataclass
class VersionResolutionFailure:
    status: Literal["NO_CANDIDATE"]
    framework: str
    requestedVersion: str
    candidatesConsidered: list[str]   # up to 5 nearest nodes examined
```

### 2.6 Gated Stub-MERGE Exception

When `allow_stub_create=True` **and** the mode is `ceil` **and** the framework is known (at least one Version node exists for it) **and** the requested version is ahead-of-catalogue: the routine MERGEs a minimal stub Version node (`framework`, `version`, `sortableVersion`, `status: "stub-pending"`) and sets `stubCreated=True`. Callers are warned that a stub node lacks full rule coverage and carries an orphan-node risk if the catalogue is later updated without reconciliation.

Default is `allow_stub_create=False`. This exception must not be triggered on `floor` or `exact` modes.

### 2.7 Tool Delegation

The following tools **must** call `resolve_version` and **must not** re-implement resolution:

| Tool | Mode used | Note |
|---|---|---|
| `check_version_availability` | `floor` (current) or `ceil` (target) based on caller hint | Replaces `_CHECK_VERSION_IN_GRAPH` exact-match |
| `submit_migration_insight` | `floor` for `fromVersion` | Called before cosine-similarity dedup |
| `create_migration_context` | `floor` for `fromVersion`, `ceil` for `toVersion` | Replaces `to_minor_zero` normalisation; resolved nodes → UPGRADES_FROM/UPGRADES_TO |
| `analyze_upgrade_path` | `floor` + `ceil` for range bounds | Replaces inline `sortable_version(to_minor_zero(...))` |
| `build_recipe_plan` | Same as `analyze_upgrade_path` | |

---

## 3. Bridge Model

**Chosen representation**: `(:MigrationRule)-[:BRIDGED_BY]->(:Dependency)`

### 3.1 Rationale

The `Dependency` label and its `name` uniqueness constraint already exist. Linking `BRIDGED_BY` to an existing `Dependency` node requires one `MERGE` with no schema additions. The edge is multi-valued by nature (a rule may have multiple eligible bridge dependencies).

### 3.2 Edge Properties

```cypher
(r:MigrationRule)-[:BRIDGED_BY {
  removalCondition: String,       # e.g. "when jackson-databind:3.x migration is complete"
  bridgeReason: String,           # human-readable explanation of why this bridge exists
  applicableRuleTypes: List[String]  # real ruleType values; bridges only apply when the rule's ruleType is in this list
                                  # e.g. ["breaking", "mandatory_migration"]
}]->(d:Dependency)
```

**PLAN-06 note**: the former field `requiredClassification: "required"` used a value (`"required"`) that does not exist in the graph schema. MigrationRule nodes carry `ruleType` (values: `"breaking"`, `"mandatory_migration"`, `"recommended"`, `"informational"`) and `entityClassification` (values: `"actionable"`, `"incomplete"`, `"informational"`). The replacement edge property `applicableRuleTypes` stores a list of real `ruleType` values. A bridge is only accepted when `r.ruleType IN edge.applicableRuleTypes`. For the standard bridge use case, this is `["breaking", "mandatory_migration"]` — informational rules are never bridgeable.

- **Cardinality**: `MigrationRule → Dependency` is 0..N. A rule with no `BRIDGED_BY` edges has no eligible bridge; attempting a `deferred` outcome for it is rejected (FR-C11).
- **`removalCondition`**: the human-readable condition under which the bridge is removed and the real change becomes mandatory.
- **`applicableRuleTypes`**: bridges apply only when the rule's `ruleType` is in this list. Informational or optional rules (`ruleType="informational"` or `ruleType="recommended"`) have no bridge concept.

### 3.3 Discoverability Check (FR-C11)

Before recording a `deferred` outcome, the harness must verify:

```cypher
MATCH (r:MigrationRule {ruleId: $rule_id})-[:BRIDGED_BY]->(b:Dependency)
RETURN b.name AS bridgeName LIMIT 1
```

If this query returns no rows, the `deferred` outcome is rejected.

---

## 4. MigrationContext — Field Handling on Create vs Match

### 4.1 Properties

| Property | Type | Create | Match (ON MATCH SET) | Notes |
|---|---|---|---|---|
| `projectId` | String | MERGE key | ← key, not written | Identity |
| `fromVersion` | String | MERGE key (exact requested string) | ← key, not written | Identity; patch preserved |
| `toVersion` | String | MERGE key (exact requested string) | ← key, not written | Identity; patch preserved |
| `framework` | String | SET | — | Not overwritten on match |
| `status` | String | `'in-progress'` | — | Not reset on match |
| `createdAt` | datetime | `datetime()` | — | Set once |
| `updatedAt` | datetime | `datetime()` | `datetime()` | **New** — set on every state-changing write |
| `completedAt` | datetime? | `null` | — | Set by `close_migration_context` |
| `notes` | String | `''` | — | Set by `close_migration_context` |
| `completedSteps` | String[] | `[]` | — | Appended by `update_step_status` |
| `skippedSteps` | String[] | `[]` | — | Appended by `update_step_status` |
| `failedSteps` | String[] | `[]` | — | Appended by `update_step_status` |
| `deferredSteps` | String[] | `[]` | — | **New** — appended by `update_step_status(outcome="deferred")` |
| `scannedEntities` | String[] | SET | `ON MATCH SET` (refreshed) | Legacy flat list |
| `scannedClasses` | String[] | SET | `ON MATCH SET` (refreshed) | Typed bucket |
| `scannedClassSimple` | String[] | SET | `ON MATCH SET` (refreshed) | Typed bucket |
| `scannedDepsGa` | String[] | SET | `ON MATCH SET` (refreshed) | Typed bucket |
| `scannedDepArtifacts` | String[] | SET | `ON MATCH SET` (refreshed) | Typed bucket |
| `scannedProps` | String[] | SET | `ON MATCH SET` (refreshed) | Typed bucket |
| `queriedEntities` | String (JSON) | `'{}'` | — | Not reset on match; cache preserved |
| `_was_created` | Boolean | `true` | `false` | Internal flag, not returned to callers |

**Allow-list enforcement**: all six scanned-entity buckets are server-filtered before write on both create and match paths. `droppedCount` = (input entity count) − (post-filter entity count).

### 4.2 queriedEntities Schema (unchanged from round-1)

```json
{
  "entity_name": "summary_string_max_500_chars"
}
```

JSON-serialised string stored as a Neo4j `String` property. `update_queried_entity` deserialises, upserts the key, re-serialises, and writes back. The skip guard in Loop II reads this field before each entity query.

### 4.3 STEP_OUTCOME Relationship

```cypher
(ctx:MigrationContext)-[:STEP_OUTCOME {
  status:    String,   # completed | skipped | failed | deferred  ← deferred is new
  reason:    String,   # for deferred: JSON string with bridgeName, bridgeReason, requiredChange (step elementId)
  updatedAt: datetime
}]->(step:MigrationStep)
```

**PLAN-05 contract**: `_RECORD_STEP_OUTCOME` always writes the STEP_OUTCOME edge first (`SET so.status = $outcome, so.reason = $reason, so.updatedAt = datetime()`), then the array-append CASE expressions (`completedSteps`, `deferredSteps`, etc.) are part of the SAME SET clause. For `outcome="deferred"`, the STEP_OUTCOME edge `status` is set to `"deferred"` AND `ctx.deferredSteps` is appended in the same operation — not in separate calls. A test must assert that after `update_step_status(outcome="deferred")`, both the edge status and the array agree.

**PLAN-03b — `requiredChange` is a step elementId**: for `deferred` outcomes, the `reason` JSON contains `requiredChange` set to the **Neo4j elementId of the real-change MigrationStep** (not a free-text description). This enables the auto-resolve check in `update_step_status`: when a step is marked `completed`, any deferred step whose stored `reason.requiredChange` matches the completed step's elementId is automatically resolved (moved from `deferredSteps` to `completedSteps`, STEP_OUTCOME edge `status` updated to `"bridgeResolved"`).

`deferred` is an additive extension. The existing three values and the relationship shape are unchanged.

### 4.4 Graph Relationships

```
(ctx)-[:UPGRADES_FROM]->(vf:Version)   # resolved floor node; NOT the identity string
(ctx)-[:UPGRADES_TO]->(vt:Version)     # resolved ceil node; NOT the identity string
(ctx)-[:STEP_OUTCOME]->(s:MigrationStep)
(r:MigrationRule)-[:BRIDGED_BY]->(d:Dependency)  # new
```

### 4.5 Indexes (no changes to existing)

The `context_project` range index (`FOR (mc:MigrationContext) ON (mc.projectId)`) is used by the new `get_migration_contexts` tool — no new index required.

---

## 5. VersionResolutionResult — Key Entities (summary)

| Entity | Fields |
|---|---|
| `VersionResolutionResult` | `resolvedVersion`, `resolvedSortable`, `nodeId`, `requestedVersion`, `rounded`, `aheadOfCatalogue`, `stubCreated`, `direction` |
| `VersionResolutionFailure` | `status: "NO_CANDIDATE"`, `framework`, `requestedVersion`, `candidatesConsidered` |
| `ExecutorRoute` | `stepId`, `track` (openrewrite/prompted-auto/agent-codemod/human-review), `rationale`, `blastRadiusFiles`, `executorInputs` |
| `DeferredOutcome` | `stepId`, `status: "deferred"`, `bridgeName`, `bridgeReason`, `requiredChange` (elementId of the real-change MigrationStep — not free text) |
| `ResolutionFailure` | `status: "RESOLUTION_FAILED"`, `subStatus` (auth_error/transport_error/NO_CANDIDATE), `failureReason`, `remediationSteps`, `unresolvedDependencies`, `fallbackInstructions?` |
| `ScanResult` | `entities` (filtered), `droppedCount`, `extractorPath`, `warnings` |
