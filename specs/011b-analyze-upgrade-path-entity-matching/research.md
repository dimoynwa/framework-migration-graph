# Research — Spec 011b: `analyze_upgrade_path` Entity-Matching Gaps

Phase 0 research artifact. Resolves the technical unknowns behind two defects found by the
live probe of `paysafe-wallet-switch` (Spring Boot 3.5.0 → 4.0.0) on 2026-06-11.

---

## Spike 1 — Why critical entity-linked rules are silently excluded

### Decision

`analyze_upgrade_path` requires `user_entities` to contain the **exact entity-type identifiers
the graph stores** — dependency GAV strings and full property key names — not Java class names.
The fix is two-part:

1. **Response layer**: add a `universally_applicable` boolean to each returned rule so callers can
   distinguish "always included" (unlinked) rules from "entity-matched" ones.
2. **Documentation / tool schema**: state explicitly that `user_entities` accepts class names,
   dependency IDs, and property keys, and that the graph matches against graph-node names via
   substring — so callers should include all three identifier types.

### Rationale

**Graph structure confirmed by live probe (2026-06-11):**

```
(Version {version:'4.0.0', framework:'Spring Boot'})
  -[:INCLUDES_RULE]-> (MigrationRule)  [55 total]
    -[:AFFECTS_CLASS]->      (Class            {name: "org.springframework.boot.env.EnvironmentPostProcessor"})
    -[:AFFECTS_PROPERTY]->   (ApplicationProperty {name: "spring.redis.host"})
    -[:AFFECTS_DEPENDENCY]-> (Dependency       {name: "spring-boot-starter-data-redis"})
```

Distribution for Spring Boot 4.0.0:
- **39 rules** have at least one AFFECTS_* link
- **16 rules** have no entity links (universally applicable)

**Filtering logic in `_ANALYZE_UPGRADE_PATH`:**

```cypher
WHERE rule IS NULL
   OR size($user_entities) = 0
   OR size(affected_entities) = 0          -- unlinked rules always pass
   OR ANY(e IN affected_entities WHERE
        ANY(u IN $user_entities WHERE
              toLower(e) CONTAINS toLower(u)))
```

The probe called the tool with
`user_entities=["RestTemplate","WebMvcConfigurer","PathMatchConfigurer","RedisTemplate","CaffeineCache","CacheManager","FeignClient"]`
and received exactly **16 rules** — the 16 unlinked ones. All 39 linked rules were excluded
because none of their entity names contain any of those strings:

```
"org.springframework.boot.env.EnvironmentPostProcessor".contains("resttemplate") → false
"spring.redis.host".contains("redistemplate")                                    → false
"spring-boot-starter-data-redis".contains("redistemplate")                       → false
```

The critical **Redis property-rename rule** (links to `spring.redis.host`,
`spring.redis.port`, `spring.redis.password`, `spring-boot-starter-data-redis`) was
silently excluded. `paysafe-wallet-switch` declares `spring-boot-starter-data-redis`
in `build.gradle` and will hit this rename at runtime — but the tool returned no signal.

**Correct user_entities for this project** (that would surface the Redis rule):

```python
["spring.redis.host", "spring.redis.port", "spring-boot-starter-data-redis",
 "EnvironmentPostProcessor", "spring.codec.log-request-details"]
```

### Why the substring match works for the right identifiers

`"spring-boot-starter-data-redis".contains("spring.redis")` → false (different separator)
`"spring.redis.host".contains("spring.redis.host")` → true (exact / substring)

The substring match is reliable when the caller provides either the exact graph node name or a
distinctive prefix/suffix. Java class names work only if the graph stores them as simple names
(e.g., `Class {name: "RestTemplate"}`). The probe confirmed the graph stores **FQNs**
(`org.springframework.boot.env.EnvironmentPostProcessor`), so passing a short class name
(`"EnvironmentPostProcessor"`) DOES match via contains, but passing `"RedisTemplate"`
does NOT match `"spring-boot-starter-data-redis"` or `"spring.redis.host"`.

### Alternatives Considered

- **Force callers to pass FQNs** — too burdensome; the probe skill and real AI agents scan
  source files and surface short class names. The API should be lenient at the boundary.
- **Add a separate `user_dependencies` param** — splits the concern cleanly but breaks
  backwards compatibility and multiplies the parameter surface area. Rejected.
- **Expand the match to include known aliases** (e.g., map `"RedisTemplate"` → its known
  dependency) — too brittle, requires maintaining a mapping table per framework version.
  Rejected in favour of fixing the documentation and response transparency.

---

## Spike 2 — Why `affected_entities` is always `[]` in the response

### Decision

The `affected_entities: []` in every returned rule is **data-accurate** (the 16 returned rules
genuinely have no entity links). It is **semantically misleading** because callers cannot
distinguish "this rule has no entity links" from "this rule's entity links were stripped from
the response". The fix is to enrich the response with:

- `universally_applicable: true/false` — whether the rule has any AFFECTS_* links in the graph
- `matched_entities: [...]` — the subset of `user_entities` values whose substring matched a
  linked entity name (mirrors `build_recipe_plan`'s existing `matched_entities` field)

### Rationale

**Current query path** (`migration_oracle/mcp/graph/queries/upgrade.py`):

```cypher
-- Step A: collect entity links per rule
OPTIONAL MATCH (rule)-[:AFFECTS_CLASS|AFFECTS_PROPERTY|AFFECTS_DEPENDENCY]->(ruleEntity)
WITH v, raw_lifecycle_events, rule,
     collect(DISTINCT ruleEntity.name) AS affected_entities

-- Step B: filter
WHERE ... OR size(affected_entities) = 0 OR ANY(e IN affected_entities WHERE ...)

-- Step C: collect into rule map
collect(DISTINCT {
    ...
    affected_entities: affected_entities,
    ...
}) AS raw_rules
```

The query is structurally correct — `affected_entities` is projected into the rule map. The
probe confirmed **all 16 returned rules pass via `size(affected_entities) = 0`**, so their
`affected_entities` lists are genuinely empty. The query does not have a Cypher bug; the
data is accurate.

The problem is the **API contract**: `affected_entities: []` means two different things:
1. "This rule applies universally — no specific API is affected" (intended for 16/16 returned
   rules)
2. "The API couldn't determine which entities this rule affects" (what callers infer)

**Comparison with `build_recipe_plan`** (same file, `_BUILD_RECIPE_PLAN` query):

`build_recipe_plan` already computes `matched_entities` and `applicability` in Python
post-processing (lines ~180–210):

```python
matched_entities = [e for e in all_affected if e and e.lower() in user_ents_lower]
applicability = "applicable" if matched_entities else "not_applicable"
```

`analyze_upgrade_path` does not perform this post-processing step. Adding it mirrors the
existing `build_recipe_plan` pattern exactly.

### Correct fix

After fetching the raw query results in `analyze_upgrade_path`, apply the same logic:

```python
user_ents_lower = {u.lower() for u in (user_entities or [])}

for rule in rules:
    raw_affected = rule.get("affected_entities") or []
    matched = [e for e in raw_affected if e and
               any(u in e.lower() for u in user_ents_lower)]
    rule["matched_entities"] = matched
    rule["universally_applicable"] = len(raw_affected) == 0
    rule["applicability"] = (
        "universal"    if len(raw_affected) == 0 else
        "applicable"   if matched else
        "not_applicable"
    )
```

This adds three new fields to each rule object without changing the existing `affected_entities`
field (backward compatible).

### Verification query

After the fix, call the tool with a `user_entities` list that DOES contain graph-linked values:

```python
user_entities=["spring.redis.host", "spring-boot-starter-data-redis"]
```

Expected: rules whose `affected_entities` contains `"spring.redis.host"` are returned with
`applicability="applicable"` and `matched_entities=["spring.redis.host"]`.
Unlinked rules are returned with `universally_applicable=true`, `applicability="universal"`,
`matched_entities=[]`.

```cypher
-- Verify the graph side: rule titles for redis-linked rules
MATCH (v:Version {version:'4.0.0', framework:'Spring Boot'})-[:INCLUDES_RULE]->(mr:MigrationRule)
MATCH (mr)-[:AFFECTS_PROPERTY]->(p:ApplicationProperty)
WHERE p.name STARTS WITH 'spring.redis'
RETURN mr.title, collect(p.name)
```

Expected: ≥ 1 rule titled something about `spring.redis.*` → `spring.data.redis.*` rename.

---

## Spike 3 — What entity types callers must supply for full coverage

### Decision

The `user_entities` parameter must accept and document three identifier types:

| Type | Example graph name | Example caller value |
|---|---|---|
| Java class (FQN or short) | `org.springframework.boot.env.EnvironmentPostProcessor` | `"EnvironmentPostProcessor"` or FQN |
| Property key | `spring.redis.host` | `"spring.redis.host"` |
| Dependency ID | `spring-boot-starter-data-redis` | `"spring-boot-starter-data-redis"` |

### How the probe skill should be updated

Step 0 of the live-probe skill must be updated in two ways:

**1. Replace the class-name allowlist with a broad import scan.** The current probe maintains
a hand-curated grep pattern of migration-relevant types. Any type not on the list is silently
missed — `ObjectMapper` being the critical example: 7+ files in `paysafe-wallet-switch` import
`com.fasterxml.jackson.databind.ObjectMapper` and call `new ObjectMapper()` directly, yet the
allowlist never included it.

The correct fix is to remove the allowlist entirely and let the graph's substring match do the
filtering:

```bash
grep -rh '^import ' src/ --include='*.java' --include='*.kt' \
    | grep -v 'static ' \
    | sed 's/^import //; s/;.*//; s/.*\.//' \
    | sort -u
```

This extracts every simple class name the project imports. Any that substring-match a graph
entity FQN will surface a rule — no human curation required. Had this been in place, `ObjectMapper`
would have been in `SCANNED_ENTITIES` automatically, and the "Jackson 3 now required; Jackson 2
deprecated" rule (linked via `AFFECTS_CLASS → com.fasterxml.jackson.databind.ObjectMapper`)
would have been returned without any pattern change.

**2. Extract additional entity types:**
- **Direct dependency artifact IDs** from `pom.xml`/`build.gradle` (`dependencies {}` block)
- **Leaf-level property keys** from `application.yml` / `application.properties`

For `paysafe-wallet-switch` this produces:
```
# From expanded class grep:
ObjectMapper

# From build.gradle dependencies:
spring-boot-starter-data-redis, spring-boot-starter-jetty,
spring-cloud-starter-openfeign, spring-cloud-starter-netflix-eureka-client

# From config files:
spring.application.name, management.endpoints.web.base-path
```

Together these surface **2 entity-matched rules** on the next probe run: the Redis rename rule
(matched via `spring-boot-starter-data-redis`) and the Jackson 3 upgrade rule (matched via
`ObjectMapper` substring on `com.fasterxml.jackson.databind.ObjectMapper`).

---

## Spike 4 — Dependency name format: GAV vs artifact-only and what the graph stores

### Decision

FR-003 must emit the **artifact-only fragment** (strip the `group:` prefix from GAV
declarations) as the user entity string, not the full `group:artifact` coordinate. The graph
stores Dependency nodes in mixed format (170 GAV, 39 artifact-only), and the substring match
direction in the Cypher query requires the user entity to be a substring of the graph node
name — not the other way around. Passing a full GAV when the graph node is artifact-only
will never match.

### Rationale

Live probe (2026-06-11) confirmed:

```
Dependency node: {name: "spring-boot-starter-data-redis"}   ← artifact-only
```

The CONTAINS check in `_ANALYZE_UPGRADE_PATH`:
```cypher
toLower(e) CONTAINS toLower(u)
-- e = graph entity name, u = user entity string
```

| User entity passed | Graph node name | Match? |
|---|---|---|
| `"spring-boot-starter-data-redis"` | `"spring-boot-starter-data-redis"` | ✅ exact |
| `"org.springframework.boot:spring-boot-starter-data-redis"` | `"spring-boot-starter-data-redis"` | ❌ longer string can't be contained in shorter |
| `"spring-boot-starter-data-redis"` | `"org.springframework.boot:spring-boot-starter-data-redis"` | ✅ artifact fragment is contained in GAV |

FR-003 extraction logic for `build.gradle`:
```bash
# Extract artifact-only fragments from GAV declarations
grep -oE '"org\.[a-z.]+:[a-z-]+"' build.gradle | tr -d '"' | sed 's/.*://'
# Optionally also emit the full GAV for nodes stored in GAV format:
grep -oE '"org\.[a-z.]+:[a-z-]+"' build.gradle | tr -d '"'
```

Both forms should be added to `SCANNED_ENTITIES` — the artifact-only form matches
artifact-only graph nodes, and the full GAV form matches GAV graph nodes.

### Data gap: 7 of 9 `paysafe-wallet-switch` dependencies have no Dependency nodes

The following dependencies declared by the project have no `Dependency` node in the graph
for Spring Boot 4.0.0, meaning no rules can be matched via them regardless of format:

| GAV | Graph node? | Assessment |
|---|---|---|
| `org.springframework.boot:spring-boot-starter-validation` | ❌ | Ingestion gap |
| `org.springframework.cloud:spring-cloud-starter-bootstrap` | ❌ | Ingestion gap |
| `org.springframework.cloud:spring-cloud-starter-openfeign` | ❌ | Ingestion gap |
| `org.springframework.cloud:spring-cloud-starter-netflix-eureka-client` | ❌ | Ingestion gap |
| `org.springframework.hateoas:spring-hateoas` | ❌ | Ingestion gap |
| `org.springframework.cloud:spring-cloud-starter-circuitbreaker-resilience4j` | ❌ | Ingestion gap |
| `org.redisson:redisson-spring-boot-starter` | ✅ node exists | 0 rules linked for 4.0.0 |

This is an **ingestion-layer data gap**, not an API bug. The migration-graph pipeline does
not yet extract breaking-change rules for Spring Cloud, Spring HATEOAS, or Redisson components.
This spec (011b) does not fix ingestion — that is a separate concern. However, including these
artifact IDs in `SCANNED_ENTITIES` is still correct practice: once ingestion is fixed and
the rules are populated, they will automatically be surfaced without any API change.
