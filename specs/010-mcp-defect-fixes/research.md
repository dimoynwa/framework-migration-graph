# Research — Spec 010: MCP Defect Fixes (Migration Session Hardening)

Phase 0 research artifact. Resolves four spike questions that gate implementation decisions for FR-005, FR-008, FR-009, and FR-017.

---

## Spike 1 — Maven Central REST Endpoint for GA Availability Check

### Decision

Use the Maven Central SolrSearch REST API:

```
GET https://search.maven.org/solrsearch/select?q=g:{groupId}+AND+a:{artifactId}+AND+v:{version}&rows=1&wt=json
```

No authentication is required. The API is publicly accessible for anonymous reads.

### Rationale

The official Maven Central REST API is a stable, documented, JSON-returning endpoint that requires no scraping or HTML parsing. It directly answers two questions: (1) whether a specific version is present in GA, and (2) what the latest released version of an artifact is.

### Alternatives Considered

- **Maven Central HTML pages / badge URLs** — fragile, subject to layout changes, not machine-readable by design. Rejected.
- **Maven Central `/artifact/` path redirects** — returns HTML, not JSON. Rejected.

### Implementation Notes

**GA availability check** — `numFound >= 1` in the response body indicates the version is present:

```
Response: {"response": {"numFound": N, "docs": [...]}}
```

**Latest patch query** — omit the `v:` filter and sort descending by version; the first doc's `v` field is the latest released version:

```
GET https://search.maven.org/solrsearch/select?q=g:{groupId}+AND+a:{artifactId}&rows=1&wt=json&sort=version+desc
```

Caller pattern: `requests.get(url, timeout=10)` — parse `response.json()["response"]["numFound"]` for availability, and `response.json()["response"]["docs"][0]["v"]` for latest version.

---

## Spike 2 — Neo4j Map Property Update Pattern for stepNotes

### Decision

Use **Python-side map-merge with full SET**. The pattern is:

1. Read the current `ctx.stepNotes` map in the same Cypher transaction (or a preliminary `RETURN`).
2. In Python: `merged = {**(current_map or {}), step_id: reason}`
3. Write back: `SET ctx.stepNotes = $merged_map`

### Rationale

APOC is not available in this project's Neo4j deployment (see Spike 3). Python-side merge is therefore the only viable pattern. It requires no plugins, is portable across Community and Enterprise editions, and is straightforward to test in unit tests by mocking the read/write Cypher calls independently.

### Alternatives Considered

- **APOC `apoc.map.setKey`** — would allow a single-Cypher update without a read-then-write round trip. Rejected because APOC is not installed; calling it would raise `Unknown function 'apoc.map.setKey'` at runtime.
- **Cypher `map + {key: value}` merge operator** — available in Neo4j 5.x. Viable as a future optimisation but not used here to keep the implementation consistent with the existing Python-side data-manipulation style in this codebase.

### Implementation Notes

The read and write should occur in the same logical operation to minimise the race window. Because the MCP server is single-threaded (FastMCP / asyncio), a true concurrent write race is unlikely, but the read-then-write should still be kept in the same function call without awaiting unrelated coroutines between them.

Null guard is required: `ctx.stepNotes` may be `null` on a freshly created `MigrationSession` node; the `or {}` default handles this.

---

## Spike 3 — APOC Availability

### Decision

**APOC is NOT available** in this project's Neo4j instance.

### Rationale

The `docker-compose.yml` uses `image: neo4j:5` (Community Edition). No `NEO4J_PLUGINS` environment variable is set, and no APOC JAR is volume-mounted. Community Edition does not bundle APOC. The plugin is therefore absent at runtime.

### Alternatives Considered

- **Enable APOC by adding `NEO4J_PLUGINS: '["apoc"]'` to docker-compose.yml** — technically possible but out of scope for this spec. Any function that currently uses or plans to use APOC must be implemented without it. Rejected for this spec.

### Implementation Notes

This finding directly confirms the Spike 2 decision: all map-property updates must use Python-side merge. Spec FR-005 already specifies the correct fallback path consistent with this constraint. No changes to `docker-compose.yml` are required.

---

## Spike 4 — Artifactory `/api/search/latestVersion` Format and Anonymous Access

### Decision

Use the standard Artifactory REST endpoint:

```
GET {ARTIFACTORY_BASE_URL}/api/search/latestVersion?g={groupId}&a={artifactId}&repos={repo}
```

No `Authorization` header. Anonymous read access is enabled by default in Artifactory OSS/Pro for non-sensitive repositories.

### Rationale

This is the documented Artifactory 7.x REST API for latest-version lookup. It returns a plain-text version string, which is trivial to parse. Anonymous read satisfies FR-008 ("no additional env vars for Artifactory credentials") and avoids introducing a credential-management concern into the MCP server.

### Alternatives Considered

- **Artifactory AQL (Artifactory Query Language)** — more flexible and supports complex filters, but requires an authenticated session. Rejected because authentication would violate the FR-008/FR-009 constraint.
- **Artifactory `/api/search/gavc`** — returns JSON with full artifact metadata. More verbose than necessary for a version string; anonymous access rules are the same. Rejected in favour of the simpler `latestVersion` endpoint.

### Implementation Notes

Response format: plain-text version string (e.g., `2.3.1`) or empty body / HTTP 404 on miss.

Caller pattern:

```python
response = requests.get(url, timeout=10)
if response.ok and response.text.strip():
    latest = response.text.strip()
else:
    latest = None
```

`ARTIFACTORY_BASE_URL` is treated as an optional environment variable (per FR-009). When absent, the Artifactory resolver must be skipped gracefully rather than raising an exception. The variable is absent from the current `docker-compose.yml` environment block and must be added there when deploying against an internal Artifactory instance.

---

## Framework to Maven Coordinate Lookup Table

Required by FR-017. Maps logical framework identifiers (as used in `MigrationSession.framework` and MCP tool arguments) to Maven Central `groupId`/`artifactId` coordinates.

| Framework Key  | groupId                    | artifactId   |
|----------------|----------------------------|--------------|
| `spring-boot`  | `org.springframework.boot` | `spring-boot` |

Additional entries can be added to this table without requiring a spec amendment. The table is the authoritative source consumed by the version-availability resolver when constructing Maven Central and Artifactory queries.
