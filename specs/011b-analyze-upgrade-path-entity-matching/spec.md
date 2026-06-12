# Feature Specification: `analyze_upgrade_path` Entity-Matching Gaps

**Feature Branch**: `011b-analyze-upgrade-path-entity-matching`

**Created**: 2026-06-11

**Status**: Draft

**Source**: Live probe of `http://localhost:8080/sse` on 2026-06-11 using real project
`paysafe-wallet-switch` (Spring Boot 3.5.0 → 4.0.0). Two defects found during Step 4 of the
probe that silently degrade the migration orchestration loop.

---

## Overview

`analyze_upgrade_path` returns the wrong subset of rules when `user_entities` is provided, and
gives the caller no signal to detect or diagnose the omission.

**Root cause A — Entity-type mismatch (Issue 1):** The graph stores rule–entity links via
`AFFECTS_CLASS`, `AFFECTS_PROPERTY`, and `AFFECTS_DEPENDENCY` relationships, targeting node
names that are Java FQNs, property keys, and Maven dependency IDs respectively. Callers
(including the live-probe skill and real AI agents) scan project sources and pass short Java class
names. These never substring-match dependency IDs or property keys, so all 39 entity-linked rules
for Spring Boot 4.0.0 were silently excluded when the probe called the tool with class names. The
only rules returned were the 16 that have no entity links at all (universally applicable rules).

**Root cause B — Opaque response (Issue 2):** Every returned rule carries `affected_entities: []`.
This is data-accurate (the 16 returned rules genuinely have no links), but callers cannot
distinguish "universally applicable, no entity links" from "entity-matched but entities not
shown". The response provides no signal that 39 other rules were excluded and no indication of
which entity matched which rule. `build_recipe_plan` already solves this with `matched_entities`
and `applicability` fields; `analyze_upgrade_path` does not.

**Impact on `paysafe-wallet-switch`:** Two high-severity rules were silently excluded:

- **Redis property rename** (`spring.redis.*` → `spring.data.redis.*`) — a silent runtime failure
  with no log warning. Matched via `spring-boot-starter-data-redis` (dependency ID), which is not
  a class name and therefore not in the probe's entity list.
- **Jackson 3 required** — `com.fasterxml.jackson.databind.ObjectMapper` (Jackson 2) is used in
  7+ source files via `new ObjectMapper()`. In Spring Boot 4.0 the package moves to
  `tools.jackson.databind.ObjectMapper`. This rule was missed because `ObjectMapper` was absent
  from the Step 0 class-name grep pattern.

No caller passing only the class names currently extracted by the probe would ever receive either rule.

---

## Functional Requirements

### FR-001 — Add `matched_entities` and `applicability` to each rule in the response

Each rule object returned by `analyze_upgrade_path` must include:

- `matched_entities: list[str]` — the values from `user_entities` that substring-matched at
  least one of the rule's linked entity names. Empty list if none matched.
- `applicability: "universal" | "applicable" | "not_applicable"` — derived as:
  - `"universal"` — the rule has no AFFECTS_* links in the graph (linked to no specific entity)
  - `"applicable"` — the rule has entity links AND at least one matched the caller's
    `user_entities`
  - `"not_applicable"` — the rule has entity links but none matched `user_entities`
    *(note: rules in this state are currently filtered out and never returned; this value is
    reserved for a future opt-in mode that returns all rules regardless of match)*
- `universally_applicable: bool` — `true` when the rule has no AFFECTS_* links (convenience
  alias for `applicability == "universal"`).

These fields mirror the existing `matched_entities` and `applicability` fields already present
in `build_recipe_plan` responses (same file, `upgrade.py`).

**Implementation:** post-processing in the Python layer of `analyze_upgrade_path`, after the
Cypher query returns. No Cypher change required.

```python
user_ents_lower = {u.lower() for u in (user_entities or [])}
for rule in rules:
    raw_affected = rule.get("affected_entities") or []
    matched = [e for e in raw_affected
               if any(u in e.lower() for u in user_ents_lower)]
    rule["matched_entities"] = matched
    rule["universally_applicable"] = len(raw_affected) == 0
    rule["applicability"] = (
        "universal"  if len(raw_affected) == 0 else
        "applicable" if matched else
        "not_applicable"
    )
```

---

### FR-002 — Document accepted entity identifier types in the tool schema

The `user_entities` parameter description in the MCP tool schema must state:

> Accepts three identifier types: (1) Java class names — short form (e.g. `ObjectMapper`) or
> fully-qualified (e.g. `com.fasterxml.jackson.databind.ObjectMapper`); (2) Spring property
> keys as they appear in config files (e.g. `spring.redis.host`); (3) Maven dependency
> artifact IDs in **artifact-only form** (e.g. `spring-boot-starter-data-redis`) — do NOT
> pass the full `group:artifact` coordinate, as the graph stores some dependency nodes in
> artifact-only format and the substring match will fail. Matching is substring-based:
> `graphNodeName.contains(userEntity)`.

---

### FR-003 — Update the live-probe skill entity-scan step to include all three identifier types

The live-probe SKILL.md Step 0 entity scan must be extended in three ways:

1. **Replace the class-name allowlist with a broad import scan.** Do not maintain a
   hand-curated list of migration-relevant types. Instead, extract all simple class names from
   `import` statements across Java/Kotlin source files and let the graph's substring match
   (`toLower(graphEntityName) CONTAINS toLower(userEntity)`) do the filtering:
   ```bash
   grep -rh '^import ' src/ --include='*.java' --include='*.kt' \
       | grep -v 'static ' \
       | sed 's/^import //; s/;.*//; s/.*\.//' \
       | sort -u
   ```
   This is self-maintaining: any class the project imports is automatically included.
   The old allowlist silently missed `ObjectMapper` even though 7+ files in
   `paysafe-wallet-switch` import `com.fasterxml.jackson.databind.ObjectMapper` — a
   high-severity Jackson 3 migration issue that a broad scan would have caught automatically.

2. **Extract dependency artifact-only fragments** from `build.gradle` / `pom.xml` — the
   artifact ID part only (strip `group:`). For Gradle, parse lines inside `dependencies {}`
   that contain `implementation`, `runtimeOnly`, or `api` and extract the artifact ID portion:
   ```bash
   grep -oE '"org\.[a-z.]+:[a-z-]+"' build.gradle | tr -d '"' | sed 's/.*://'
   ```
   Do **not** pass the full `group:artifact` coordinate — the graph stores some Dependency nodes
   in artifact-only format, and passing the full GAV breaks the substring match against them.

3. **Extract leaf-level property keys** from `application.yml` / `application.properties` — full
   dot-separated paths (e.g. `spring.redis.host`), not just the top-level namespace prefix.

All three sets must be combined into `SCANNED_ENTITIES` before calling `analyze_upgrade_path`.

**Rationale:** Without dependency IDs and leaf property keys, entity-linked rules are
systematically excluded. Without the expanded class-name pattern, high-severity class-level
rules (e.g. Jackson 3 upgrade) are also silently missed. Together these gaps cause the probe
to report false confidence: "no issues" when critical breaking changes exist.

---

## User Scenarios & Testing

### User Story 1 — Agent discovers Redis rename rule (Priority: P1) — FR-001, FR-002, FR-003

A developer runs the live probe against `paysafe-wallet-switch`. After the FR-003 scan
enhancement, `SCANNED_ENTITIES` includes `"spring-boot-starter-data-redis"` (extracted from
`build.gradle` dependencies). The tool returns the Redis property-rename rule with
`applicability="applicable"` and `matched_entities=["spring-boot-starter-data-redis"]`. The
agent surfaces it as a high-priority migration step.

Note: `paysafe-wallet-switch` does not declare `spring.redis.host` explicitly in its config
files — the match happens via the dependency ID, not a property key.

**Acceptance criteria:**
- `analyze_upgrade_path` with `user_entities=["spring-boot-starter-data-redis"]`
  returns ≥ 1 rule containing `spring.redis` in its statement.
- That rule has `applicability="applicable"` and `matched_entities` containing
  `"spring-boot-starter-data-redis"`.
- Unlinked rules in the same response have `universally_applicable=true`.

### User Story 2 — Agent can explain rule relevance (Priority: P2) — FR-001

An AI agent presents migration rules to the developer. For each rule it can now state:
"This applies to your project because you use `spring.redis.host`." Previously it could only
say "This rule applies" with no entity context.

**Acceptance criteria:**
- Every rule in the response has a `matched_entities` field (list, may be empty).
- Every rule has an `applicability` field with one of the three allowed values.
- Rules with `universally_applicable=true` have `matched_entities=[]`.

### User Story 2b — Agent discovers Jackson 3 breaking change (Priority: P1) — FR-001, FR-003

A developer runs the live probe against `paysafe-wallet-switch`. After the FR-003 grep
pattern expansion, `SCANNED_ENTITIES` includes `"ObjectMapper"`. The tool returns the
"Jackson 3 now required; Jackson 2 deprecated" rule with `applicability="applicable"` and
`matched_entities=["ObjectMapper"]`. The agent flags all 7+ files instantiating
`new ObjectMapper()` as requiring migration to `tools.jackson.databind.ObjectMapper`.

**Acceptance criteria:**
- `analyze_upgrade_path` with `user_entities=["ObjectMapper"]` returns ≥ 1 rule whose title
  or statement references Jackson 3 / Jackson 2 deprecation.
- That rule has `applicability="applicable"` and `matched_entities` containing `"ObjectMapper"`.
- The rule's `affected_entities` contains `"com.fasterxml.jackson.databind.ObjectMapper"` (the
  FQN that `"ObjectMapper"` substring-matched against).

### User Story 3 — No regression for calls without `user_entities` (Priority: P1) — FR-001

When `user_entities` is empty or absent, all 55 rules are returned and every rule has
`applicability="universal"` (since no user context was provided, the concept of match doesn't
apply).

**Acceptance criteria:**
- `analyze_upgrade_path` without `user_entities` returns the same rule count as before.
- All rules have `applicability="universal"` and `universally_applicable=true`.

---

## Non-Goals

- This spec does **not** change the filtering logic — rules whose entity links don't match
  `user_entities` continue to be excluded. A future "show all rules" mode is out of scope.
- This spec does **not** change how entity nodes are stored in the graph.
- This spec does **not** change `build_recipe_plan` (it already handles this correctly).
- This spec does **not** address the **ingestion data gap** for Spring Cloud, Spring HATEOAS,
  and Redisson: 7 of 9 dependencies declared by `paysafe-wallet-switch` have no Dependency
  nodes in the graph for Spring Boot 4.0.0 (`spring-cloud-starter-openfeign`,
  `spring-cloud-starter-netflix-eureka-client`, `spring-cloud-starter-bootstrap`,
  `spring-cloud-starter-circuitbreaker-resilience4j`, `spring-boot-starter-validation`,
  `spring-boot-starter-jetty`, `spring-hateoas`). Fixing this requires ingestion pipeline
  changes and is a separate concern. Including these artifact IDs in `SCANNED_ENTITIES` is
  still correct — they will match automatically once ingestion is fixed.

---

## Affected Files

| File | Change |
|---|---|
| `migration_oracle/mcp/graph/queries/upgrade.py` | Add post-processing loop in `analyze_upgrade_path` to set `matched_entities`, `applicability`, `universally_applicable` on each rule |
| `migration_oracle/mcp/tools/upgrade.py` | Update tool schema: extend `user_entities` parameter description per FR-002 |
| `~/.claude/skills/mcp-live-probe/SKILL.md` | Extend Step 0 entity scan per FR-003 (extract dependency IDs and leaf property keys) |

---

## Open Questions

| # | Question | Impact |
|---|---|---|
| 1 | Should `applicability="not_applicable"` rules ever be returned (e.g. via an `include_all=true` flag)? | Scope: could be useful for "show me all rules even if they don't match my project" |
| 2 | Should `universally_applicable` rules be labelled differently in the UI / agent output to distinguish them from truly matched rules? | UX only |
| 3 | Should the API normalise both GAV and artifact-only formats internally, so callers can safely pass either? The graph's mixed format (170 GAV, 39 artifact-only nodes) is the root inconsistency — an API-level normaliser would insulate callers from it. | Scope: would require maintaining a group→artifact mapping or a normalisation query; currently out of scope for this spec |
