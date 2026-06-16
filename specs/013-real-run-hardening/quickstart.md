# Quickstart: Replaying the 3.5.12 → 4.0.6 Migration Scenario

This guide gets you to a running Oracle that can replay the first real migration run (`paysafe-wallet-switch`, Spring Boot 3.5.12 → 4.0.6) against the hardened 013 codebase.

**Prerequisites**: Docker, Docker Compose, Python 3.12+, `uv`

---

## Step 1: Clone and install

```bash
git clone <repo-url> paysafe-version-migration-graph
cd paysafe-version-migration-graph
uv sync
```

---

## Step 2: Configure environment

```bash
cp .env.example .env   # or create manually
```

Minimum required variables:

```bash
# .env
NEO4J_PASSWORD=yourpassword

# Optional — needed only for Paysafe dep resolution
FINDIT_AUTH_TOKEN=<token>
GITLAB_API_KEY=<token>

# Optional — needed only for AI-assisted features
ANTHROPIC_API_KEY=<key>
```

---

## Step 3: Start Neo4j and the Oracle

```bash
docker compose up -d neo4j
# Wait for Neo4j to be healthy (about 30 seconds)
docker compose ps neo4j   # confirm "healthy"

docker compose up -d oracle
```

Verify the Oracle is reachable:

```bash
curl -s http://localhost:8080/health | python3 -m json.tool
```

---

## Step 4: Seed the version catalogue

The graph needs Spring Boot Version nodes covering the 3.5.x and 4.0.x minor lines. Run the seeder:

```bash
# From repo root, activate venv
source .venv/bin/activate

# Seed Spring Boot nodes: 3.5.0, 3.5.12, 4.0.0, 4.0.6
python3 -c "
from migration_oracle.graph.driver import write_session
from migration_oracle.models.graph import sortable_version

versions = [
    ('Spring Boot', '3.5.0'),
    ('Spring Boot', '3.5.12'),
    ('Spring Boot', '4.0.0'),
    ('Spring Boot', '4.0.6'),
]

with write_session() as s:
    for fw, ver in versions:
        s.run('''
            MERGE (v:Version {framework: \$fw, version: \$ver})
            ON CREATE SET v.sortableVersion = \$sv, v.status = 'active'
        ''', fw=fw, ver=ver, sv=sortable_version(ver))
    print('Seeded', len(versions), 'Version nodes')
"
```

Verify:

```bash
python3 -c "
from migration_oracle.graph.driver import read_session
with read_session() as s:
    rows = list(s.run('MATCH (v:Version) WHERE v.framework = \\'Spring Boot\\' RETURN v.version ORDER BY v.sortableVersion'))
    for r in rows: print(r['v.version'])
"
```

---

## Step 5: Verify resolve_version behaviour (the round-1 contradiction fix)

With the Oracle running, test that version resolution is now consistent:

```bash
# check_version_availability — floor resolution for 3.5.12
curl -s -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "check_version_availability",
    "args": {"framework": "Spring Boot", "version": "3.5.12"}
  }' | python3 -m json.tool
# Expected: exists_in_graph: true, resolved node: 3.5.12
```

---

## Step 6: Create a migration context

```bash
# Replace PROJECT_ROOT with the path to paysafe-wallet-switch (or any Spring Boot 3.5.x project)
PROJECT_ROOT="/path/to/paysafe-wallet-switch"

# Run Loop I scan (BSD/GNU portable)
ENTITIES=$(
  grep -rh --include="*.java" \
    -E '^import (static )?[a-z]' \
    "$PROJECT_ROOT/src/main/java" 2>/dev/null \
  | sed 's/^import (static )?//' \
  | sed 's/import static //' \
  | sed 's/import //' \
  | grep -E '^(org\.springframework|jakarta\.|javax\.|org\.hibernate|io\.micrometer|io\.projectreactor|org\.thymeleaf|com\.fasterxml\.jackson|tools\.jackson|org\.springdoc|com\.querydsl|org\.flywaydb|org\.liquibase|org\.apache\.tomcat|org\.eclipse\.jetty|io\.undertow)\.' \
  | sort -u \
  | python3 -c "import sys,json; print(json.dumps([l.rstrip(';').strip() for l in sys.stdin]))"
)

# Create context
curl -s -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d "{
    \"tool\": \"create_migration_context\",
    \"args\": {
      \"project_id\": \"paysafe-wallet-switch\",
      \"from_version\": \"3.5.12\",
      \"to_version\": \"4.0.6\",
      \"framework\": \"Spring Boot\",
      \"scanned_entities\": $ENTITIES
    }
  }" | python3 -m json.tool
```

Expected response includes:
- `created: true`
- `from_version: "3.5.12"` (patch preserved — not `"3.5.0"`)
- `to_version: "4.0.6"` (patch preserved — not `"4.0.0"`)
- `upgrades_to_version: "4.0.6"` with `rounded: false`
- `droppedCount: 0` (if all entities pass the allow-list)

---

## Step 7: List contexts (new in 013)

```bash
curl -s -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "get_migration_contexts",
    "args": {"project_id": "paysafe-wallet-switch"}
  }' | python3 -m json.tool
# Expected: count: 1, contexts array with outcome_counts
```

---

## Step 8: Query upgrade path

```bash
CONTEXT_ID="<id from step 6>"

curl -s -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d "{
    \"tool\": \"get_steps_for_scope_tier\",
    \"args\": {
      \"context_id\": \"$CONTEXT_ID\",
      \"scope\": \"api-surface\",
      \"severity_threshold\": \"high\"
    }
  }" | python3 -m json.tool
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `exists_in_graph: false` for 3.5.12 | Run Step 4 to seed the Version nodes |
| `version_not_in_graph` on `create_migration_context` | Neo4j healthcheck failed; wait for `docker compose ps neo4j` to show healthy |
| `auth_error` from Paysafe resolver | Set `FINDIT_AUTH_TOKEN` and `GITLAB_API_KEY` in `.env`; re-run `docker compose up -d oracle` |
| `grep -P` errors on macOS | Normal — the portable scan command in Step 6 uses `-E` (BSD-compatible); the Oracle's Python fallback scanner handles this automatically |
| `droppedCount > 0` after scan | Application-class entities were filtered by the allow-list — this is correct behaviour, not an error |

---

## Clean-up

```bash
docker compose down -v   # removes volumes (deletes graph data)
```
