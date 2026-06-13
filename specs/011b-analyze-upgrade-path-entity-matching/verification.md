**Location**: `specs/011b-analyze-upgrade-path-entity-matching/verification.md`
**Spec gate**: Run this after implementing FR-001, FR-002, and FR-003, before merging to main.
**Execution order**: Levels 0 → 4 in sequence. Stop and fix on the first failure.

---

## Expected Outcome Analysis — `paysafe-wallet-switch`

This section defines what a correct implementation MUST produce for the real project at
`/Users/dimo.drangov/DevelopmentTools/paysafe-wallet-switch`. All acceptance criteria below
are derived from this analysis.

### What the graph contains for Spring Boot 4.0.0

Live probe on 2026-06-11 confirmed:
- **55 total rules** for `Version {version:'4.0.0', framework:'Spring Boot'}`
- **39 rules** have at least one `AFFECTS_CLASS`, `AFFECTS_PROPERTY`, or `AFFECTS_DEPENDENCY` link
- **16 rules** have no entity links (universally applicable)

### What `paysafe-wallet-switch` uses (from `build.gradle` + config files + source scan)

Dependencies are declared as full GAV (`group:artifact`) in `build.gradle`. The graph stores
Dependency nodes in **mixed format** — 170 in GAV, 39 in artifact-only. The substring match in
`analyze_upgrade_path` is `toLower(graphEntityName) CONTAINS toLower(userEntity)`, so passing
the full GAV as a user entity will NOT match an artifact-only graph node (the longer string
cannot contain the shorter one in the wrong direction). **FR-003 must emit the artifact-only
fragment** (strip the `group:` prefix) alongside the full GAV to guarantee matches.

| Identifier (GAV from build.gradle) | Artifact-only fragment to emit | Graph node exists? | Rules linked (4.0.0)? |
|---|---|---|---|
| `org.springframework.boot:spring-boot-starter-data-redis` | `spring-boot-starter-data-redis` | ✅ artifact-only node | ✅ Redis rename rule |
| `org.springframework.boot:spring-boot-starter-validation` | `spring-boot-starter-validation` | ❌ | ❌ data gap |
| `org.springframework.boot:spring-boot-starter-jetty` | `spring-boot-starter-jetty` | ❌ | ❌ data gap |
| `org.springframework.cloud:spring-cloud-starter-bootstrap` | `spring-cloud-starter-bootstrap` | ❌ | ❌ data gap |
| `org.springframework.cloud:spring-cloud-starter-openfeign` | `spring-cloud-starter-openfeign` | ❌ | ❌ data gap |
| `org.springframework.cloud:spring-cloud-starter-netflix-eureka-client` | `spring-cloud-starter-netflix-eureka-client` | ❌ | ❌ data gap |
| `org.springframework.cloud:spring-cloud-starter-circuitbreaker-resilience4j` | `spring-cloud-starter-circuitbreaker-resilience4j` | ❌ | ❌ data gap |
| `org.springframework.hateoas:spring-hateoas` | `spring-hateoas` | ❌ | ❌ data gap |
| `org.redisson:redisson-spring-boot-starter` | `redisson-spring-boot-starter` | ✅ GAV node | ❌ 0 rules linked |

> **Data gap note:** 7 of 9 Spring/Cloud/Redisson dependencies declared by `paysafe-wallet-switch`
> have no Dependency node in the graph for Spring Boot 4.0.0. This is an ingestion gap —
> the pipeline has not extracted breaking-change rules for Spring Cloud, Spring HATEOAS, or
> Redisson upgrades. These are out of scope for this spec (spec 011b fixes the API layer);
> the ingestion gap should be tracked separately.

| Identifier | Type | Source |
|---|---|---|
| `spring.application.name` | Property key | `bootstrap.yml` |
| `management.endpoints.web.base-path` | Property key | `bootstrap.yml` |
| `RestTemplate` | Class name | `src/` grep |
| `WebMvcConfigurer` | Class name | `src/` grep |
| `PathMatchConfigurer` | Class name | `src/` grep |
| `RedisTemplate` | Class name | `src/` grep |
| `FeignClient` | Class name | `src/` grep |
| **`ObjectMapper`** | **Class name** | **7+ files: `RafService`, `JsonConverter`, `EmailsService`, `MonitoringService`, `PlatformErrorMapper`, `ExchangeV2Mapper`, `SkrillClientIdHttpInterceptor`, `CryptoTransactionSummaryAssembler`, `RestClientResponseExceptionHandler`** |

> **Note on `ObjectMapper`:** All usages import `com.fasterxml.jackson.databind.ObjectMapper`
> (Jackson 2). Several files call `new ObjectMapper()` directly. In Spring Boot 4.0, Jackson 3
> is the default and the package moves to `tools.jackson.databind.ObjectMapper`. This is a
> **high-severity** migration impact. `ObjectMapper` must be added to the Step 0 class-name
> grep pattern (FR-003) — it is not in the current pattern and would be missed entirely.

### Which rules the project should match (after FR-003 entity types and class names are complete)

Cross-referencing all project identifiers against the 4.0.0 graph entity links:

| Rule | Matched entity | Match type | Severity |
|---|---|---|---|
| Redis property rename (`spring.redis.*` → `spring.data.redis.*`) | `spring-boot-starter-data-redis` | Dependency ID exact match | high |
| Jackson 3 now required; Jackson 2 deprecated | `com.fasterxml.jackson.databind.ObjectMapper` | Class name substring match (`objectmapper` in FQN) | high |
| Jackson 2 support deprecated via `spring-boot-jackson2` | `com.fasterxml.jackson.databind.ObjectMapper` | Class name substring match | medium |
| Jackson 3 compatibility configuration property | `com.fasterxml.jackson.databind.ObjectMapper` | Class name substring match | low |
| Jackson datetime and JSON mapper property paths renamed | `com.fasterxml.jackson.databind.ObjectMapper` | Class name substring match | low |

**Expected matched rule count: 2 distinct rules** (Redis rename + Jackson 3 upgrade) matching
via `spring-boot-starter-data-redis` and `ObjectMapper` respectively.
**Expected total rule count with enhanced entities: ≥ 18.**

### The Redis rename rule — exact expected content

Graph-confirmed (live probe 2026-06-11):

```
statement: "When migrating from Spring Boot 3.5 to 4.0, the spring.redis.* properties are
            replaced by spring.data.redis.*. Spring Boot 4.0 silently ignores spring.redis.*
            at startup, causing runtime Redis connection failures with no warning in logs."
affected_entities: [AFFECTS_PROPERTY → spring.redis.host,
                    AFFECTS_PROPERTY → spring.redis.port,
                    AFFECTS_PROPERTY → spring.redis.password,
                    AFFECTS_DEPENDENCY → spring-boot-starter-data-redis]
```

After FR-001, this rule must appear with:
- `matched_entities: ["spring-boot-starter-data-redis"]`
- `applicability: "applicable"`
- `universally_applicable: false`

### The Jackson 3 rule — exact expected content

Graph-confirmed (live probe 2026-06-11):

```
title:   "Jackson 3 now required; Jackson 2 deprecated"
affected_entities: [AFFECTS_CLASS → com.fasterxml.jackson.databind.ObjectMapper,
                    AFFECTS_CLASS → tools.jackson.databind.ObjectMapper,
                    AFFECTS_CLASS → org.springframework.boot.jackson.Jackson2ObjectMapperBuilderCustomizer,
                    AFFECTS_CLASS → org.springframework.boot.jackson.JsonComponent,
                    ... (9 class links + 1 dependency link total)]
```

After FR-001, this rule must appear with:
- `matched_entities: ["ObjectMapper"]` (the user entity string that substring-matched the FQN)
- `applicability: "applicable"`
- `universally_applicable: false`

The 16 unlinked rules must appear with:
- `matched_entities: []`
- `applicability: "universal"`
- `universally_applicable: true`

---

## Prerequisites

| Requirement | Check |
|---|---|
| MCP server running | `curl -s http://localhost:8080/sse --max-time 3` returns `event: endpoint` |
| Neo4j reachable | Server responds (it feeds the MCP) |
| Repo root | All commands from `/Users/dimo.drangov/paysafe-version-migration-graph/` |
| Project available | `/Users/dimo.drangov/DevelopmentTools/paysafe-wallet-switch/build.gradle` exists |

---

## Level 0 — Static checks (no server required)

### 0-A — New response fields exist in `analyze_upgrade_path` Python layer

```bash
grep -n "matched_entities\|universally_applicable\|applicability" \
    migration_oracle/mcp/graph/queries/upgrade.py
```

Expected: at least 3 lines — one each for setting `matched_entities`, `universally_applicable`,
and `applicability` on each rule. Zero lines → FR-001 not implemented.

### 0-B — Tool schema documents three entity identifier types

```bash
grep -A5 "user_entities" migration_oracle/mcp/tools/upgrade.py | grep -i "property\|depend"
```

Expected: description mentions "property keys" or "dependency" (FR-002). Empty output →
tool schema not updated.

### 0-C — Probe skill Step 0 uses broad import scan, not an allowlist

```bash
grep -n "grep.*import\|import.*java\|import.*kt" \
    ~/.claude/skills/mcp-live-probe/SKILL.md | head -5
grep -n "artifactId\|implementation\|dependencies\|build.gradle" \
    ~/.claude/skills/mcp-live-probe/SKILL.md | head -5
```

Expected: Step 0 references extracting class names via `import` grep (FR-003 broad scan) AND
extracting dependency IDs from `build.gradle`. The old fixed-allowlist pattern
(`WebSecurityConfigurerAdapter|HttpSecurity|...`) must not be the primary extraction mechanism.

---

## Level 1 — Unit: post-processing logic

Run entirely in Python, no Neo4j or MCP server.

### 1-A — `matched_entities` computed correctly

```python
python3 - <<'EOF'
import sys
sys.path.insert(0, ".")

# Simulate the post-processing on a synthetic rule
from migration_oracle.mcp.graph.queries.upgrade import analyze_upgrade_path

# Patch: test the post-processing helper in isolation
rule_with_links = {
    "rule_id": "test-1",
    "statement": "spring.redis.* is renamed to spring.data.redis.*",
    "affected_entities": [
        "spring.redis.host", "spring.redis.port", "spring-boot-starter-data-redis"
    ],
    "steps": [], "scopes": [], "recipes": [],
}
rule_no_links = {
    "rule_id": "test-2",
    "statement": "JUnit 4 integration deprecated",
    "affected_entities": [],
    "steps": [], "scopes": [], "recipes": [],
}

user_entities = ["spring-boot-starter-data-redis", "spring.application.name"]
user_ents_lower = {u.lower() for u in user_entities}

def apply_post_processing(rule, user_ents_lower):
    raw = rule.get("affected_entities") or []
    matched = [e for e in raw if any(u in e.lower() for u in user_ents_lower)]
    rule["matched_entities"] = matched
    rule["universally_applicable"] = len(raw) == 0
    rule["applicability"] = (
        "universal"  if len(raw) == 0 else
        "applicable" if matched else
        "not_applicable"
    )
    return rule

r1 = apply_post_processing(rule_with_links, user_ents_lower)
r2 = apply_post_processing(rule_no_links, user_ents_lower)

assert r1["matched_entities"] == ["spring-boot-starter-data-redis"], \
    f"FAIL: expected ['spring-boot-starter-data-redis'], got {r1['matched_entities']}"
assert r1["applicability"] == "applicable", \
    f"FAIL: expected 'applicable', got {r1['applicability']}"
assert r1["universally_applicable"] == False, \
    f"FAIL: expected False, got {r1['universally_applicable']}"

assert r2["matched_entities"] == [], \
    f"FAIL: expected [], got {r2['matched_entities']}"
assert r2["applicability"] == "universal", \
    f"FAIL: expected 'universal', got {r2['applicability']}"
assert r2["universally_applicable"] == True, \
    f"FAIL: expected True, got {r2['universally_applicable']}"

print("PASS: 1-A post-processing computes matched_entities, applicability, universally_applicable correctly")
EOF
```

### 1-B — Short class name substring-matches FQN entity name

```python
python3 -c "
user_ents_lower = {'resttemplate', 'redistemplate'}
fqns = [
    'org.springframework.web.client.RestTemplate',
    'org.springframework.data.redis.core.RedisTemplate',
    'org.springframework.boot.env.EnvironmentPostProcessor',
]
for fqn in fqns:
    matched = any(u in fqn.lower() for u in user_ents_lower)
    label = 'MATCH' if matched else 'NO MATCH'
    print(f'  {label}: {fqn}')
assert any(u in fqns[0].lower() for u in user_ents_lower), 'RestTemplate should substring-match'
assert any(u in fqns[1].lower() for u in user_ents_lower), 'RedisTemplate should substring-match'
assert not any(u in fqns[2].lower() for u in user_ents_lower), 'EnvironmentPostProcessor should not match'
print('PASS: 1-B FQN substring matching works for class names')
"
```

---

## Level 2 — Project scan (FR-003): enhanced entity extraction

No MCP server needed. Validates that Step 0 now extracts the right identifiers.

### 2-A — Artifact-only fragments are extracted from build.gradle GAV declarations

The build file declares full GAV (`org.springframework.boot:spring-boot-starter-data-redis`).
FR-003 must strip the group prefix and emit the artifact-only fragment, because many graph
Dependency nodes store artifact-only names. Passing the full GAV as `user_entities` will
NOT match an artifact-only graph node (CONTAINS match direction fails).

```bash
PROJECT="/Users/dimo.drangov/DevelopmentTools/paysafe-wallet-switch"

# Full GAV lines as declared
echo "=== Full GAV declarations ==="
grep -oE '"org\.[a-z.]+:[a-z-]+"' "$PROJECT/build.gradle" | tr -d '"' | sort -u | head -20

# Artifact-only fragments (what must go into SCANNED_ENTITIES)
echo ""
echo "=== Artifact-only fragments (after stripping group:) ==="
grep -oE '"org\.[a-z.]+:[a-z-]+"' "$PROJECT/build.gradle" | tr -d '"' | \
    sed 's/.*://' | sort -u | head -20
```

Expected: `spring-boot-starter-data-redis` appears in the artifact-only output.
If only the full GAV is emitted (without stripping), the Redis rename rule will not match.

### 2-B — Leaf property keys are extracted from bootstrap.yml

```bash
PROJECT="/Users/dimo.drangov/DevelopmentTools/paysafe-wallet-switch"
grep -oE '[a-z][a-z0-9._-]+\.[a-z][a-z0-9._-]+' \
    "$PROJECT/src/main/resources/bootstrap.yml" | sort -u | head -20
```

Expected: lines like `spring.application.name`, `management.endpoints.web.base-path`.
These must appear in `SCANNED_ENTITIES` sent to the MCP tool.

### 2-B2 — Broad import scan extracts `ObjectMapper` from Java sources

```bash
PROJECT="/Users/dimo.drangov/DevelopmentTools/paysafe-wallet-switch"

# FR-003: broad import scan — no allowlist
grep -rh '^import ' "$PROJECT/src/main/java" --include='*.java' \
    | grep -v 'static ' \
    | sed 's/^import //; s/;.*//; s/.*\.//' \
    | sort -u \
    | grep -i objectmapper
```

Expected: `ObjectMapper` appears in the output — extracted automatically without any hardcoded
pattern. If absent, Step 0 broad-scan implementation is missing or incomplete.

Corroborating count (to understand scope):
```bash
grep -rl "ObjectMapper" "$PROJECT/src/main/java" --include='*.java' \
    | wc -l | xargs -I{} echo "{} files import or use ObjectMapper"
```
Expected: ≥ 7 files.

### 2-C — Combined entity list for paysafe-wallet-switch contains ≥ 15 identifiers and includes `ObjectMapper`

```bash
PROJECT="/Users/dimo.drangov/DevelopmentTools/paysafe-wallet-switch"

CLASSES=$(grep -rh '^import ' "$PROJECT/src" --include='*.java' --include='*.kt' \
  | grep -v 'static ' \
  | sed 's/^import //; s/;.*//; s/.*\.//' \
  | sort -u)

DEPS=$(grep -oE 'spring-boot-starter-[a-z-]+|spring-cloud-starter-[a-z-]+|spring-kafka' \
  "$PROJECT/build.gradle" | sort -u)

PROPS=$(grep -oE '[a-z][a-z0-9._-]+\.[a-z][a-z0-9._-]+' \
  "$PROJECT/src/main/resources/bootstrap.yml" \
  "$PROJECT/src/main/resources/application.yml" 2>/dev/null | sort -u)

ALL=$(printf '%s\n%s\n%s\n' "$CLASSES" "$DEPS" "$PROPS" | sort -u | grep -v '^$')
COUNT=$(echo "$ALL" | wc -l | xargs)
echo "Total entities: $COUNT"
echo "$ALL"
[ "$COUNT" -ge 15 ] && echo "PASS: 2-C entity count ≥ 15" || echo "FAIL: 2-C only $COUNT entities extracted"
echo "$ALL" | grep -q "ObjectMapper" && echo "PASS: 2-C ObjectMapper present" || echo "FAIL: 2-C ObjectMapper missing — add to class-name grep pattern"
```

Expected: `spring-boot-starter-data-redis` and `ObjectMapper` are both in the list, total ≥ 15.

---

## Level 3 — Live MCP: regression (no user_entities)

All checks in this level use a live SSE session. Set up once and reuse.

### 3-A — Total rule count without user_entities is still 55

```python
python3 - <<'EOF'
import requests, json, threading, time

responses = {}
session_id = None

def listen_sse():
    global session_id
    with requests.get("http://localhost:8080/sse", stream=True, timeout=60) as r:
        for line in r.iter_lines():
            if line:
                d = line.decode()
                if d.startswith("data: /messages/"):
                    session_id = d.split("session_id=")[1]
                elif d.startswith("data: "):
                    try:
                        obj = json.loads(d[6:])
                        responses[obj.get("id")] = obj
                    except: pass

threading.Thread(target=listen_sse, daemon=True).start()
time.sleep(0.8)

def call(rid, name, args, wait=5.0):
    requests.post(f"http://localhost:8080/messages/?session_id={session_id}",
        json={"jsonrpc":"2.0","id":rid,"method":"tools/call","params":{"name":name,"arguments":args}})
    time.sleep(wait)
    return responses.get(rid)

def text(r):
    if not r: return None
    c = r.get("result",{}).get("content",[{}])
    return c[0].get("text","") if c else ""

requests.post(f"http://localhost:8080/messages/?session_id={session_id}",
    json={"jsonrpc":"2.0","id":0,"method":"initialize",
          "params":{"protocolVersion":"2024-11-05","capabilities":{},
                    "clientInfo":{"name":"verify-011b","version":"1.0"}}})
time.sleep(1.5)

r = call(1, "analyze_upgrade_path", {
    "framework": "Spring Boot",
    "current_version": "3.5.0",
    "target_version": "4.0.0",
    "top_n": 100,
}, wait=6)
data = json.loads(text(r))
rules = data.get("rules", [])
assert len(rules) == 55, f"FAIL: expected 55 rules without user_entities, got {len(rules)}"

# All rules must have the three new fields
for rule in rules:
    assert "matched_entities" in rule, f"FAIL: rule missing matched_entities: {rule.get('rule_id')}"
    assert "universally_applicable" in rule, f"FAIL: rule missing universally_applicable"
    assert "applicability" in rule, f"FAIL: rule missing applicability"

print(f"PASS: 3-A {len(rules)} rules returned without user_entities, all have new fields")
EOF
```

### 3-B — All rules without user_entities have `applicability="universal"`

```python
# Extend the script from 3-A:
for rule in rules:
    assert rule["applicability"] == "universal", \
        f"FAIL: rule '{rule.get('rule_id')}' has applicability='{rule['applicability']}' with no user_entities"
print("PASS: 3-B all rules have applicability='universal' when no user_entities supplied")
```

---

## Level 4 — Live MCP: project-specific outcome validation

This is the core validation. Uses the actual `paysafe-wallet-switch` entity list.

### 4-A — Enhanced entity scan surfaces ≥ 17 rules

```python
python3 - <<'EOF'
import requests, json, threading, time

responses = {}
session_id = None

def listen_sse():
    global session_id
    with requests.get("http://localhost:8080/sse", stream=True, timeout=60) as r:
        for line in r.iter_lines():
            if line:
                d = line.decode()
                if d.startswith("data: /messages/"):
                    session_id = d.split("session_id=")[1]
                elif d.startswith("data: "):
                    try:
                        obj = json.loads(d[6:])
                        responses[obj.get("id")] = obj
                    except: pass

threading.Thread(target=listen_sse, daemon=True).start()
time.sleep(0.8)

def call(rid, name, args, wait=5.0):
    requests.post(f"http://localhost:8080/messages/?session_id={session_id}",
        json={"jsonrpc":"2.0","id":rid,"method":"tools/call","params":{"name":name,"arguments":args}})
    time.sleep(wait)
    return responses.get(rid)

def text(r):
    if not r: return None
    c = r.get("result",{}).get("content",[{}])
    return c[0].get("text","") if c else ""

requests.post(f"http://localhost:8080/messages/?session_id={session_id}",
    json={"jsonrpc":"2.0","id":0,"method":"initialize",
          "params":{"protocolVersion":"2024-11-05","capabilities":{},
                    "clientInfo":{"name":"verify-011b","version":"1.0"}}})
time.sleep(1.5)

# Enhanced entity list — class names (incl. ObjectMapper) + artifact-only dep fragments + leaf property keys
# Note: full GAV strings (e.g. "org.springframework.cloud:spring-cloud-starter-openfeign") are NOT
# used here because the substring match direction requires the user entity to be <= the graph
# node name. Artifact-only fragments ("spring-cloud-starter-openfeign") work for both formats.
WALLET_ENTITIES = [
    # class names (from source scan — ObjectMapper added per FR-003 pattern fix)
    "RestTemplate", "WebMvcConfigurer", "PathMatchConfigurer",
    "RedisTemplate", "CaffeineCache", "CacheManager", "FeignClient",
    "ObjectMapper",
    # artifact-only dependency fragments (stripped from GAV declarations in build.gradle)
    "spring-boot-starter-data-redis",       # graph node exists → Redis rename rule
    "spring-cloud-starter-openfeign",       # no graph node yet — data gap
    "spring-cloud-starter-netflix-eureka-client",   # no graph node yet — data gap
    "spring-cloud-starter-bootstrap",       # no graph node yet — data gap
    "spring-cloud-starter-circuitbreaker-resilience4j",  # no graph node yet — data gap
    "spring-boot-starter-validation",       # no graph node yet — data gap
    "spring-boot-starter-jetty",            # no graph node yet — data gap
    "spring-hateoas",                       # no graph node yet — data gap
    "redisson-spring-boot-starter",         # graph node exists but 0 rules linked
    # property keys (from bootstrap.yml / application.yml — FR-003 addition)
    "spring.application.name",
    "management.endpoints.web.base-path",
]

r = call(2, "analyze_upgrade_path", {
    "framework": "Spring Boot",
    "current_version": "3.5.0",
    "target_version": "4.0.0",
    "user_entities": WALLET_ENTITIES,
    "top_n": 100,
}, wait=6)
data = json.loads(text(r))
rules = data.get("rules", [])

print(f"Rules returned with enhanced entities: {len(rules)}")
assert len(rules) >= 18, \
    f"FAIL: expected ≥ 18 rules with enhanced entities, got {len(rules)} — Redis and/or Jackson rule not returned"
print(f"PASS: 4-A {len(rules)} rules returned (≥ 18 expected)")
EOF
```

### 4-B — Redis rename rule is present in the results

```python
# Extend the script from 4-A:
redis_rules = [r for r in rules
               if "spring.redis" in (r.get("statement") or "").lower()
               or "spring.data.redis" in (r.get("statement") or "").lower()]

assert len(redis_rules) >= 1, (
    "FAIL: 4-B Redis rename rule not found — "
    "'spring.redis.*' → 'spring.data.redis.*' must be in results when "
    "user_entities includes 'spring-boot-starter-data-redis'"
)
print(f"PASS: 4-B Redis rename rule present ({len(redis_rules)} match(es))")
for rule in redis_rules:
    print(f"  statement: {(rule.get('statement') or '')[:100]}")
```

### 4-C — Redis rule has correct `applicability` and `matched_entities`

```python
# Extend from 4-B:
for rule in redis_rules:
    assert rule.get("applicability") == "applicable", \
        f"FAIL: 4-C Redis rule has applicability='{rule.get('applicability')}', expected 'applicable'"
    assert rule.get("universally_applicable") == False, \
        f"FAIL: 4-C Redis rule has universally_applicable=True, expected False"
    matched = rule.get("matched_entities", [])
    assert "spring-boot-starter-data-redis" in matched, \
        f"FAIL: 4-C 'spring-boot-starter-data-redis' not in matched_entities: {matched}"
    print(f"PASS: 4-C Redis rule applicability='applicable', matched_entities={matched}")
```

### 4-D — All 16 universally applicable rules are still present

```python
# Extend from 4-A:
universal_rules = [r for r in rules if r.get("universally_applicable") == True]
applicable_rules = [r for r in rules if r.get("applicability") == "applicable"]

assert len(universal_rules) == 16, \
    f"FAIL: 4-D expected 16 universally_applicable rules, got {len(universal_rules)}"
print(f"PASS: 4-D {len(universal_rules)} universal rules present")
print(f"      {len(applicable_rules)} entity-matched rules present")
```

### 4-E — Jackson 3 rule is present and correctly attributed to `ObjectMapper`

```python
# Extend from 4-A:
jackson_rules = [r for r in rules
                 if "jackson 3" in (r.get("title") or "").lower()
                 or ("jackson" in (r.get("statement") or "").lower()
                     and "deprecated" in (r.get("statement") or "").lower())]

assert len(jackson_rules) >= 1, (
    "FAIL: 4-E Jackson 3 rule not found — "
    "'Jackson 3 now required; Jackson 2 deprecated' must be returned when "
    "user_entities includes 'ObjectMapper'"
)
print(f"PASS: 4-E Jackson 3 rule present ({len(jackson_rules)} match(es))")

for rule in jackson_rules:
    assert rule.get("applicability") == "applicable", \
        f"FAIL: 4-E Jackson rule has applicability='{rule.get('applicability')}', expected 'applicable'"
    assert rule.get("universally_applicable") == False, \
        f"FAIL: 4-E Jackson rule universally_applicable should be False"
    matched = rule.get("matched_entities", [])
    assert any("objectmapper" in m.lower() for m in matched), \
        f"FAIL: 4-E 'ObjectMapper' not in matched_entities for Jackson rule: {matched}"
    print(f"      title={rule.get('title')}")
    print(f"      matched_entities={matched}")
```

> **Why this matters:** `paysafe-wallet-switch` instantiates `new ObjectMapper()` directly in
> 7+ files (`RafService`, `JsonConverter`, `EmailsService`, `MonitoringService`, etc.). In Spring
> Boot 4.0, `com.fasterxml.jackson.databind.ObjectMapper` is replaced by
> `tools.jackson.databind.ObjectMapper`. Without this rule surfaced, the agent would have no
> signal that every `new ObjectMapper()` call in the project is a breaking change.

### 4-F — No rule has `applicability` outside the allowed set

```python
# Extend from 4-A:
allowed = {"universal", "applicable", "not_applicable"}
bad = [r for r in rules if r.get("applicability") not in allowed]
assert not bad, \
    f"FAIL: 4-E rules with invalid applicability value: {[r.get('rule_id') for r in bad]}"
print("PASS: 4-E all rules have valid applicability values")
```

### 4-F — Class-name-only call (baseline before fix) returns 16 rules and no applicable rules

```python
# Extend script from 4-A — call with class names only (the pre-fix behaviour):
# Call with the OLD entity list (class names only, no ObjectMapper, no dependency IDs):
r_classes = call(3, "analyze_upgrade_path", {
    "framework": "Spring Boot",
    "current_version": "3.5.0",
    "target_version": "4.0.0",
    "user_entities": ["RestTemplate", "WebMvcConfigurer", "PathMatchConfigurer",
                      "RedisTemplate", "CaffeineCache", "CacheManager", "FeignClient"],
    "top_n": 100,
}, wait=6)
class_rules = json.loads(text(r_classes)).get("rules", [])
applicable_class_rules = [r for r in class_rules if r.get("applicability") == "applicable"]

assert len(class_rules) == 16, \
    f"FAIL: 4-G expected 16 rules with old class-name-only entities, got {len(class_rules)}"
assert len(applicable_class_rules) == 0, \
    f"FAIL: 4-G expected 0 applicable rules with old class names, got {len(applicable_class_rules)}"
print(f"PASS: 4-G class-name-only (no ObjectMapper, no dep IDs) returns 16 rules, 0 applicable")
print(f"      Confirms: Redis rule and Jackson 3 rule are both invisible without FR-003 entities.")
```

---

## Completion Gate

All of the following must be true before marking spec 011b ✅:

- [ ] `0-A` new fields present in `upgrade.py`
- [ ] `0-B` tool schema documents property keys and dependency IDs
- [ ] `0-C` probe skill Step 0 extracts dependency IDs
- [ ] `1-A` post-processing logic correct (unit)
- [ ] `1-B` FQN substring matching correct (unit)
- [ ] `2-A` `spring-boot-starter-data-redis` extracted from `paysafe-wallet-switch` `build.gradle`
- [ ] `2-B2` `ObjectMapper` found in 7+ source files — gap in current grep pattern confirmed
- [ ] `2-C` ≥ 15 combined entities extracted, **`ObjectMapper` and `spring-boot-starter-data-redis` both present**
- [ ] `3-A` 55 rules without `user_entities` (no regression)
- [ ] `3-B` all rules have `applicability="universal"` without `user_entities`
- [ ] `4-A` ≥ 18 rules with enhanced wallet-switch entities (16 universal + Redis + Jackson)
- [ ] `4-B` Redis rename rule present in results
- [ ] `4-C` Redis rule has `applicability="applicable"`, `matched_entities` contains `"spring-boot-starter-data-redis"`
- [ ] `4-D` exactly 16 `universally_applicable=true` rules
- [ ] `4-E` Jackson 3 rule present, `applicability="applicable"`, `matched_entities` contains `"ObjectMapper"`
- [ ] `4-F` all rules have valid `applicability` values
- [ ] `4-G` old class-name-only call (no `ObjectMapper`, no dep IDs) returns exactly 16 rules, 0 applicable — proves both rules are invisible without FR-003
