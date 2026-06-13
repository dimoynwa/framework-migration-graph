# Spec — Scanning & Applicability Pipeline Fix

**Component:** Paysafe Migration Oracle MCP
**Area:** Codebase scanning → entity matching → migration plan generation
**Status:** Proposed
**Problem owner:** MCP server team

---

## 1. Problem Statement

Generated migration plans are incomplete: rules that genuinely apply to a customer's
codebase are silently omitted. Investigation shows the cause is **not** primarily the
extraction step — it is the *contract* between what the scanner produces and how the
query tools consume it, plus a substring-based matching predicate that fails
asymmetrically.

Five compounding defects were identified:

1. **Substring matching.** `analyze_upgrade_path` and `build_recipe_plan` match with
   `toLower(graphEntity) CONTAINS toLower(userEntity)`. This drops applicable rules
   whenever the scanned form is longer or differently formatted than the stored form
   (e.g. a Maven coordinate carrying a version, a relaxed-binding property variant),
   and produces false positives for short tokens.
2. **Input-side trimming.** The scanning skill trims extracted entities to a "top 200"
   ranking *before* matching. Genuinely-affected entities ranked 201+ never reach the
   graph.
3. **Grep extraction + declared-only dependencies.** Regex extraction misses star
   imports, inline FQNs, reflection, profile-specific and code-set properties; parsing
   declared `pom.xml`/`build.gradle` entries misses transitive artifacts pulled via
   BOMs and starters, which many high-severity rules target.
4. **Broken scan contract.** `scannedEntities` is persisted on `MigrationContext` but
   the query tools do not read it; they take a separate `user_entities` parameter.
   `get_pending_steps` applies **no entity filter at all**. The plan the user reviews
   (entity-filtered, under-inclusive) and the steps they execute (`get_pending_steps`,
   unfiltered) come from different rule sets.
5. **Breaking changes can be filtered out.** The entity filter treats a `critical`
   `api-surface` removal identically to a trivial rename — no entity match means
   dropped, with no error.

A false negative on a breaking change is far costlier than a false positive. The fix
prioritises completeness and visibility over noise reduction.

---

## 2. Goals / Non-Goals

### Goals
- One applicability model, applied consistently across `analyze_upgrade_path`,
  `build_recipe_plan`, and `get_pending_steps`.
- Normalized, per-kind exact matching that does not depend on substring coincidence.
- No silent omission of `high`/`critical` rules.
- Per-query coverage diagnostics so incompleteness becomes a visible signal.
- Transitive dependency coverage via resolved dependency trees.

### Non-Goals
- AST-grade extraction (JavaParser / tree-sitter) — tracked as a follow-up; the
  matching and contract fixes recover correctly-extracted entities that are dropped
  today regardless of extraction quality.
- Inter-dependency version-conflict detection (not modelled in the graph schema).

---

## 3. Normalization Contract

The scanner MUST emit canonical, kind-separated entity lists. The application layer
normalizes the scanned side before any query; graph `name` values are assumed canonical
(see §3.4 for the one-time backfill if that assumption does not hold).

### 3.1 Classes
- Primary: fully-qualified class name (FQCN), exact, into `scanned_classes`.
- Fallback for star imports / unresolved references: simple name into
  `scanned_class_simple`. Simple names match **only** on the last dotted segment of a
  stored FQCN, never as a substring.

### 3.2 Dependencies (use the resolved tree, not declared entries)
- Run `mvn dependency:tree` / `gradle dependencies`; route `com.paysafe.*` through the
  existing `resolve_paysafe_dependency_by_service_name` tool.
- Strip the version. Emit `groupId:artifactId` into `scanned_deps_ga`.
- Emit bare `artifactId` into `scanned_dep_artifacts` as a lower-confidence fallback.

### 3.3 Properties
- Flatten YAML to dotted keys. Canonicalize relaxed binding (camelCase, kebab-case,
  UPPER_UNDERSCORE → canonical lower-kebab dotted form). Emit into `scanned_props`.
- Scan all profile files (`application-*.yml/.properties`), not just defaults.

### 3.4 Graph-side canonicalization (one-time)
If `ApplicationProperty.name` values are not guaranteed canonical, run a one-time
normalization migration to canonical lower-kebab dotted form before enabling exact
property matching. Validate with a count of distinct canonical collisions first.

### 3.5 Parameter shape passed to all query tools
```json
{
  "scanned_classes":      ["org.springframework.web.servlet.config.annotation.WebMvcConfigurerAdapter"],
  "scanned_class_simple": ["WebMvcConfigurerAdapter"],
  "scanned_deps_ga":      ["org.springframework.boot:spring-boot-starter-web"],
  "scanned_dep_artifacts":["spring-boot-starter-web"],
  "scanned_props":        ["spring.datasource.url"]
}
```

---

## 4. Matching Semantics

Per-kind, exact (equality/`IN`) matching with explicit confidence tiers. No `CONTAINS`.

| Kind | Tier `strong` | Tier `weak` |
|---|---|---|
| Class | `e.name IN scanned_classes` | `last(split(e.name,'.')) IN scanned_class_simple` |
| Dependency | `(g+':'+a) IN scanned_deps_ga` | `a IN scanned_dep_artifacts` |
| Property | `e.name IN scanned_props` | — |

A rule is **applicable** if any affected entity matches at `strong` or `weak` tier.

### Breaking-change safety net
A rule with `BreakingScope.severity IN ['high','critical']` is **always included**,
even with no entity match, flagged `applicability = "uncertain"`. This guarantees no
breaking change is silently dropped.

### Applicability values returned per rule
- `matched` — at least one `strong`/`weak` entity match.
- `uncertain` — no match but high/critical severity (surfaced via safety net).
- `informational` — rule has no affected entities at all.

---

## 5. Required Tool Changes

### 5.1 Consume `scannedEntities` from the context
Context-aware tools (`get_pending_steps`, `get_steps_for_scope_tier`,
`update_step_status` path validation) MUST read the normalized entity sets from the
`MigrationContext` rather than relying on the agent to re-pass them. Store the
normalized sets on the context at `create_migration_context` time.

### 5.2 Apply one applicability model everywhere
`get_pending_steps` currently applies **no** entity filter. It MUST apply the §4
model so the executed step queue matches the reviewed plan.

### 5.3 Trim outputs, not inputs
Remove the "top 200" input cap from the scanning skill. Send the full normalized entity
set; rank and cap the *resulting rules* (e.g. by severity then match tier).

### 5.4 Emit coverage diagnostics
Every query that filters by entities returns a `diagnostics` block:
```json
{
  "scanned_total": 412,
  "matched_entities": ["...names that hit >=1 rule..."],
  "unmatched_entities": ["...names that hit nothing..."],
  "rules_included": 37,
  "rules_excluded_by_entity_filter": 121,
  "rules_via_safety_net": 4
}
```

---

## 6. Rewritten Cypher

### 6.1 `analyze_upgrade_path` (matching + safety net + diagnostics)

```cypher
// Params: $framework, $current_version_sortable, $target_version_sortable,
//         $scanned_classes, $scanned_class_simple,
//         $scanned_deps_ga, $scanned_dep_artifacts, $scanned_props,
//         $classification (list), $min_severity_rank (int|null)
MATCH (v:Version {framework: $framework})
WHERE v.sortableVersion >  $current_version_sortable
  AND v.sortableVersion <= $target_version_sortable
MATCH (v)-[:INCLUDES_RULE]->(rule:MigrationRule)
WHERE size($classification) = 0
   OR rule.entityClassification IS NULL
   OR rule.entityClassification IN $classification

// --- per-rule severity (max severity across its scopes) ---
OPTIONAL MATCH (rule)-[:HAS_SCOPE]->(bs:BreakingScope)
WITH v, rule,
     min(CASE bs.severity
           WHEN 'critical' THEN 0 WHEN 'high' THEN 1
           WHEN 'medium'   THEN 2 WHEN 'low'  THEN 3 ELSE 4 END) AS sev_rank,
     collect(DISTINCT {scope: bs.scope, severity: bs.severity}) AS scopes

// --- per-entity, kind-aware match ---
OPTIONAL MATCH (rule)-[:AFFECTS_CLASS|AFFECTS_PROPERTY|AFFECTS_DEPENDENCY]->(e)
WITH v, rule, sev_rank, scopes, e,
     CASE
       WHEN e:Class THEN
            e.name IN $scanned_classes
         OR last(split(e.name, '.')) IN $scanned_class_simple
       WHEN e:ApplicationProperty THEN
            e.name IN $scanned_props
       WHEN e:Dependency THEN
            (size(split(e.name, ':')) >= 2
               AND (split(e.name, ':')[0] + ':' + split(e.name, ':')[1]) IN $scanned_deps_ga)
         OR last(split(e.name, ':')) IN $scanned_dep_artifacts
       ELSE false
     END AS entity_match
WITH v, rule, sev_rank, scopes,
     collect(DISTINCT e.name)                                   AS affected_entities,
     count(e)                                                   AS affected_count,
     sum(CASE WHEN entity_match THEN 1 ELSE 0 END)              AS match_count

// --- applicability decision ---
WITH v, rule, sev_rank, scopes, affected_entities, affected_count, match_count,
     CASE
       WHEN affected_count = 0          THEN 'informational'
       WHEN match_count   > 0           THEN 'matched'
       WHEN sev_rank      <= 1          THEN 'uncertain'   // high/critical safety net
       ELSE 'excluded'
     END AS applicability
WHERE applicability <> 'excluded'
  AND ($min_severity_rank IS NULL OR sev_rank <= $min_severity_rank)

// --- hydrate steps & recipes ---
OPTIONAL MATCH (rule)-[:REQUIRES_STEP]->(s:MigrationStep)
OPTIONAL MATCH (s)-[ab:AUTOMATED_BY]->(rec:OpenRewriteRecipe)
WITH v, rule, scopes, affected_entities, applicability, match_count, s,
     collect(DISTINCT {
       recipe_id: rec.recipeId,
       display_name: rec.displayName,
       auto: ab.auto,
       fully_automatable: (ab.auto = true AND coalesce(ab.missingRequiredParams, []) = []),
       missing_required_params: coalesce(ab.missingRequiredParams, [])
     }) AS recipes
WITH v, rule, scopes, affected_entities, applicability, match_count,
     collect(DISTINCT CASE WHEN s IS NULL THEN null ELSE {
       step_id: elementId(s), step_type: s.stepType, summary: s.summary,
       instruction: s.instruction, effort: s.effort, automatable: s.automatable,
       verification_hint: s.verificationHint, cli_operation: s.cliOperation,
       step_index: s.stepIndex
     } END) AS steps_raw, recipes

RETURN v.version AS release_version,
       v.sortableVersion AS release_sortable,
       collect(DISTINCT {
         rule_id: elementId(rule),
         statement: rule.statement,
         rule_type: rule.ruleType,
         title: rule.title,
         action_step: rule.actionStep,
         source_url: rule.sourceUrl,
         entity_classification: rule.entityClassification,
         applicability: applicability,
         match_count: match_count,
         affected_entities: affected_entities,
         scopes: [x IN scopes WHERE x.scope IS NOT NULL],
         steps: [x IN steps_raw WHERE x IS NOT NULL],
         recipes: [x IN recipes WHERE x.recipe_id IS NOT NULL]
       }) AS rules
ORDER BY v.sortableVersion ASC
```

> Lifecycle alerts (`HAS_LIFECYCLE_ALERT`) and lifecycle events
> (`DEPRECATED_IN`/`REMOVED_IN`/`INTRODUCED_IN`) should be fetched in a **separate**
> query keyed on the same version range, not folded into the rule aggregation. Folding
> them in was a source of grouping fragility in the original.

### 6.2 `build_recipe_plan` (two-track, same matching)

```cypher
// Same params as 6.1
MATCH (v:Version {framework: $framework})
WHERE v.sortableVersion >  $current_version_sortable
  AND v.sortableVersion <= $target_version_sortable
MATCH (v)-[:INCLUDES_RULE]->(rule:MigrationRule)
WHERE size($classification) = 0
   OR rule.entityClassification IS NULL
   OR rule.entityClassification IN $classification

OPTIONAL MATCH (rule)-[:HAS_SCOPE]->(bs:BreakingScope)
WITH v, rule,
     min(CASE bs.severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1
           WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4 END) AS sev_rank,
     head(collect(DISTINCT bs.scope))     AS scope,
     head(collect(DISTINCT bs.severity))  AS severity

OPTIONAL MATCH (rule)-[:AFFECTS_CLASS|AFFECTS_PROPERTY|AFFECTS_DEPENDENCY]->(e)
WITH v, rule, sev_rank, scope, severity, e,
     CASE
       WHEN e:Class THEN
            e.name IN $scanned_classes OR last(split(e.name,'.')) IN $scanned_class_simple
       WHEN e:ApplicationProperty THEN e.name IN $scanned_props
       WHEN e:Dependency THEN
            (size(split(e.name,':')) >= 2
               AND (split(e.name,':')[0]+':'+split(e.name,':')[1]) IN $scanned_deps_ga)
         OR last(split(e.name,':')) IN $scanned_dep_artifacts
       ELSE false
     END AS entity_match
WITH v, rule, sev_rank, scope, severity,
     collect(DISTINCT e.name) AS affected_entities,
     count(e) AS affected_count,
     sum(CASE WHEN entity_match THEN 1 ELSE 0 END) AS match_count
WITH v, rule, sev_rank, scope, severity, affected_entities, match_count,
     CASE WHEN affected_count = 0 THEN 'informational'
          WHEN match_count > 0    THEN 'matched'
          WHEN sev_rank <= 1      THEN 'uncertain'
          ELSE 'excluded' END AS applicability
WHERE applicability <> 'excluded'

MATCH (rule)-[:REQUIRES_STEP]->(s:MigrationStep)
OPTIONAL MATCH (s)-[ab:AUTOMATED_BY]->(rec:OpenRewriteRecipe)
WITH v, rule, scope, severity, affected_entities, applicability, match_count, s, ab, rec,
     (s.automatable = true
        AND s.effort = 'mechanical'
        AND ab.auto = true
        AND coalesce(ab.missingRequiredParams, []) = []) AS is_auto
RETURN
     CASE WHEN is_auto THEN 'auto' ELSE 'manual' END AS track,
     elementId(rule) AS rule_id,
     elementId(s)    AS step_id,
     rule.statement  AS statement,
     s.summary       AS summary,
     s.instruction   AS instruction,
     s.effort        AS effort,
     s.verificationHint AS verification_hint,
     scope, severity,
     applicability,
     match_count,
     affected_entities,
     rec.recipeId    AS recipe_id,
     coalesce(ab.missingRequiredParams, []) AS missing_required_params,
     v.version       AS version,
     s.stepIndex     AS step_index
ORDER BY v.sortableVersion ASC, s.stepIndex ASC
```

### 6.3 `get_pending_steps` (add the entity filter, read from context)

Insert the same kind-aware match and applicability gate before returning steps, sourcing
the `scanned_*` lists from the context node. Steps belonging to `excluded` rules are
dropped; `uncertain` (safety-net) steps are returned with a flag so the executor can
surface them for confirmation rather than auto-applying.

```cypher
MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $context_id
MATCH (ctx)-[:UPGRADES_FROM]->(from_v:Version)
MATCH (ctx)-[:UPGRADES_TO]->(to_v:Version)
MATCH (v:Version)
WHERE v.sortableVersion >  from_v.sortableVersion
  AND v.sortableVersion <= to_v.sortableVersion
MATCH (v)-[:INCLUDES_RULE]->(r:MigrationRule)-[:REQUIRES_STEP]->(s:MigrationStep)
WHERE NOT elementId(s) IN ctx.completedSteps
  AND NOT elementId(s) IN ctx.skippedSteps
  AND NOT elementId(s) IN coalesce(ctx.failedSteps, [])
  AND (size($effort_filter) = 0 OR s.effort IN $effort_filter)

OPTIONAL MATCH (r)-[:HAS_SCOPE]->(bs:BreakingScope)
WITH ctx, r, s,
     min(CASE bs.severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1
           WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4 END) AS sev_rank,
     head(collect(DISTINCT bs.scope))    AS scope,
     head(collect(DISTINCT bs.severity)) AS severity
WHERE size($scope_filter) = 0 OR scope IN $scope_filter

OPTIONAL MATCH (r)-[:AFFECTS_CLASS|AFFECTS_PROPERTY|AFFECTS_DEPENDENCY]->(e)
WITH ctx, r, s, sev_rank, scope, severity, e,
     CASE
       WHEN e:Class THEN e.name IN ctx.scannedClasses
            OR last(split(e.name,'.')) IN ctx.scannedClassSimple
       WHEN e:ApplicationProperty THEN e.name IN ctx.scannedProps
       WHEN e:Dependency THEN
            (size(split(e.name,':')) >= 2
               AND (split(e.name,':')[0]+':'+split(e.name,':')[1]) IN ctx.scannedDepsGa)
         OR last(split(e.name,':')) IN ctx.scannedDepArtifacts
       ELSE false
     END AS entity_match
WITH ctx, r, s, sev_rank, scope, severity,
     count(e) AS affected_count,
     sum(CASE WHEN entity_match THEN 1 ELSE 0 END) AS match_count
WITH r, s, sev_rank, scope, severity,
     CASE WHEN affected_count = 0 THEN 'informational'
          WHEN match_count > 0    THEN 'matched'
          WHEN sev_rank <= 1      THEN 'uncertain'
          ELSE 'excluded' END AS applicability
WHERE applicability <> 'excluded'

OPTIONAL MATCH (s)-[ab:AUTOMATED_BY]->(rec:OpenRewriteRecipe)
  WHERE ab.auto = true AND coalesce(ab.missingRequiredParams, []) = []
OPTIONAL MATCH (s)-[:REQUIRES]->(prereq:MigrationStep)
RETURN elementId(s) AS step_id, s.stepType AS step_type, elementId(r) AS rule_id,
       s.summary AS summary, s.instruction AS instruction,
       s.verificationHint AS verification_hint, s.effort AS effort,
       s.automatable AS automatable, scope, severity, applicability,
       rec.recipeId AS recipe_id, s.stepIndex AS _step_index,
       sev_rank AS _severity_rank,
       collect(DISTINCT elementId(prereq)) AS requires
ORDER BY _severity_rank ASC, _step_index ASC
```

---

## 7. Out-of-Scope Bug Fixes (recommended, adjacent)

- **`update_step_status` STEP_OUTCOME write** sets `rel.status = $status` while the
  tool parameter is `outcome`. Bind the outcome value to the relationship `status`, or
  every recorded outcome lands `null`.
- **`search_migration_knowledge` hydrate** traverses `DISCOVERED_IN`, which is not in
  the schema (insights attach via `INCLUDES_RULE`). Remove the dead branch.
- **`search_openrewrite_recipes`** documents `only_composite` / `require_no_params` as
  not enforced while the hydrate query references them — reconcile.

---

## 8. Rollout

1. Land §3 normalization + §4 matching behind a feature flag; store normalized
   `scanned*` lists on `MigrationContext` at creation.
2. Run §3.4 property backfill in staging; validate collision count is zero.
3. Switch `analyze_upgrade_path` / `build_recipe_plan` / `get_pending_steps` to the
   §6 queries behind the flag.
4. Shadow-compare: run old vs new on a corpus of real projects; expect rule count to
   **increase**. Inspect any decrease.
5. Remove the top-200 input cap (§5.3) once output ranking is in place.
6. Enable transitive dependency resolution (§3.2).

---

## 9. Acceptance Criteria

- A rule whose affected `Dependency` is a transitive artifact (BOM/starter-pulled)
  appears in the plan.
- A scanned simple class name matches its stored FQCN; a scanned GAV-with-version
  matches the stored `groupId:artifactId`; a relaxed-binding property variant matches
  the canonical key.
- No `high`/`critical` rule is ever omitted; when unmatched it appears with
  `applicability = "uncertain"`.
- `analyze_upgrade_path`, `build_recipe_plan`, and `get_pending_steps` return the same
  applicable rule set for identical inputs.
- Each entity-filtered response includes the §5.4 diagnostics block.
- Shadow comparison shows rule completeness increases relative to the substring
  implementation, with no unexplained regressions.