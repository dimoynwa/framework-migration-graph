# Verification Protocol: Community Insight Restructure

**Location**: `specs/009-community-insight-restructure/verification.md`
**Spec gate**: Run this after `/speckit.implement` completes, before marking `009` ✅
**Execution order**: Levels 0 → 7 in sequence. Stop and fix on the first failure — failures compound.

---

## Prerequisites

| Requirement | How to satisfy |
|-------------|---------------|
| Python env | `source .venv/bin/activate` (or equivalent) |
| DB reachable | `NEO4J_URI`, `NEO4J_PASSWORD` set in environment |
| Embedding model | `SENTENCE_TRANSFORMERS_MODEL` set (or accept default `all-mpnet-base-v2`) |
| Writable temp | `/tmp` writable for cleanup scripts |

## Infrastructure requirements by level

| Level | Name | DB | LLM/Embeddings |
|-------|------|----|----------------|
| 0 | Static checks | ✗ | ✗ |
| 1 | Interface structure | ✗ | ✗ |
| 2 | Isolation behaviour | ✗ | ✗ |
| 3 | Integration — read path | ✓ | ✗ |
| 5 | Integration — write path | ✓ | Optional |
| 6 | Idempotency | ✓ | Optional |
| 7 | Edge-case paths | ✓ (some) | ✗ |

> Level 4 (dry-run) is omitted — this spec has no dry-run mode.

---

## Level 0 — Static checks

**No external services required.**

### 0-A: Module imports

```python
python - <<'EOF'
import importlib

modules = [
    "migration_oracle.mcp.graph.queries.community",
    "migration_oracle.mcp.tools.community",
    "migration_oracle.mcp.graph.queries.search",
    "migration_oracle.mcp.tools.search",
    "migration_oracle.graph.indexes",
]
for m in modules:
    importlib.import_module(m)
    print(f"PASS: {m} imports without error")
EOF
```

### 0-B: `CommunityInsight` label absent from all source files

```bash
result=$(grep -r 'CommunityInsight' migration_oracle/ --include="*.py")
if [ -z "$result" ]; then
    echo "PASS: no CommunityInsight label in migration_oracle/"
else
    echo "FAIL: CommunityInsight still present:"
    echo "$result"
fi
```

### 0-C: `include_community_insights` absent from all source files

```bash
result=$(grep -r 'include_community_insights' migration_oracle/ --include="*.py")
if [ -z "$result" ]; then
    echo "PASS: include_community_insights fully removed from migration_oracle/"
else
    echo "FAIL: include_community_insights still present:"
    echo "$result"
fi
```

### 0-D: `_SUBMIT_INSIGHT` Cypher uses `MigrationRule` and creates `MigrationStep`

```python
python - <<'EOF'
import migration_oracle.mcp.graph.queries.community as cq

cypher = cq._SUBMIT_INSIGHT
required = [
    ("CREATE (r:MigrationRule",          "MigrationRule CREATE present"),
    ("ruleType:              'community_insight'", "ruleType hardcoded"),
    ("communityVotes:        0",          "communityVotes initialised to 0"),
    ("communityVerified:     false",      "communityVerified initialised to false"),
    ("communitySubmittedBy:",             "communitySubmittedBy property present"),
    ("communityCreatedAt:",               "communityCreatedAt property present"),
    ("communityConfidence:",              "communityConfidence property present"),
    ("CREATE (s:MigrationStep",           "MigrationStep CREATE present"),
    ("stepType:    'manual'",             "stepType='manual'"),
    ("effort:      'moderate'",           "effort='moderate'"),
    ("automatable: false",                "automatable=false"),
    ("(v)-[:INCLUDES_RULE]->(r)",         "INCLUDES_RULE direction correct"),
    ("(r)-[:REQUIRES_STEP]->(s)",         "REQUIRES_STEP present"),
    ("AFFECTS_CLASS",                     "AFFECTS_CLASS FOREACH present"),
    ("AFFECTS_PROPERTY",                  "AFFECTS_PROPERTY FOREACH present"),
    ("AFFECTS_DEPENDENCY",                "AFFECTS_DEPENDENCY FOREACH present"),
]
for fragment, label in required:
    assert fragment in cypher, f"FAIL: '{fragment}' not found in _SUBMIT_INSIGHT — {label}"
    print(f"PASS: {label}")

forbidden = ["CommunityInsight", "DISCOVERED_IN", ":MigrationRule {solution:", "votes:"]
for fragment in forbidden:
    assert fragment not in cypher, f"FAIL: forbidden pattern '{fragment}' found in _SUBMIT_INSIGHT"
print("PASS: no forbidden patterns in _SUBMIT_INSIGHT")
EOF
```

### 0-E: `_QUERY_INSIGHTS` traverses MigrationStep for solution

```python
python - <<'EOF'
import migration_oracle.mcp.graph.queries.community as cq

cypher = cq._QUERY_INSIGHTS
required = [
    ("ruleType = 'community_insight'",       "ruleType filter present"),
    ("OPTIONAL MATCH (r)-[:REQUIRES_STEP]->(s:MigrationStep)", "REQUIRES_STEP traversal"),
    ("coalesce(first_step.instruction",      "solution from MigrationStep.instruction"),
    ("communityVotes",                       "communityVotes read"),
    ("communityVerified",                    "communityVerified read"),
    ("communitySubmittedBy",                 "communitySubmittedBy read"),
    ("communityCreatedAt",                   "communityCreatedAt read"),
    ("communityConfidence",                  "communityConfidence read"),
    ("$verified_only",                       "verified_only filter parameter present"),
]
for fragment, label in required:
    assert fragment in cypher, f"FAIL: '{fragment}' missing from _QUERY_INSIGHTS — {label}"
    print(f"PASS: {label}")

forbidden = ["CommunityInsight", "ci.solution", "ci.votes", "ci.verified"]
for fragment in forbidden:
    assert fragment not in cypher, f"FAIL: forbidden pattern '{fragment}' found in _QUERY_INSIGHTS"
print("PASS: no forbidden patterns in _QUERY_INSIGHTS")
EOF
```

### 0-F: Vote and verify Cypher target `MigrationRule` with community-prefixed properties

```python
python - <<'EOF'
import migration_oracle.mcp.graph.queries.community as cq

vote = cq._VOTE_INSIGHT
verify = cq._VERIFY_INSIGHT

assert "MATCH (r:MigrationRule)" in vote, "FAIL: _VOTE_INSIGHT does not target MigrationRule"
assert "communityVotes" in vote, "FAIL: _VOTE_INSIGHT does not write communityVotes"
assert "r.communityVotes AS votes" in vote, "FAIL: _VOTE_INSIGHT alias 'votes' missing"
assert "CommunityInsight" not in vote, "FAIL: CommunityInsight still in _VOTE_INSIGHT"
print("PASS: _VOTE_INSIGHT targets MigrationRule with communityVotes")

assert "MATCH (r:MigrationRule)" in verify, "FAIL: _VERIFY_INSIGHT does not target MigrationRule"
assert "communityVerified = true" in verify, "FAIL: _VERIFY_INSIGHT does not set communityVerified"
assert "r.communityVerified AS verified" in verify, "FAIL: _VERIFY_INSIGHT alias 'verified' missing"
assert "CommunityInsight" not in verify, "FAIL: CommunityInsight still in _VERIFY_INSIGHT"
print("PASS: _VERIFY_INSIGHT targets MigrationRule with communityVerified")
EOF
```

### 0-G: Duplicate-detection index names updated

```python
python - <<'EOF'
import inspect
import migration_oracle.mcp.graph.queries.community as cq

source = inspect.getsource(cq)

assert "migration_knowledge_vector_mr" in source, \
    "FAIL: migration_knowledge_vector_mr not found in community.py"
assert "migration_knowledge_vector_ci" not in source, \
    "FAIL: migration_knowledge_vector_ci still present in community.py"
print("PASS: vector index name updated to migration_knowledge_vector_mr")

assert 'index="rule_statement"' in source, \
    "FAIL: rule_statement BM25 index not found in community.py"
# migration_text may still be referenced in _best_bm25_duplicate — check it's gone
import re
bm25_calls = re.findall(r'bm25_search\([^)]+\)', source)
for call in bm25_calls:
    assert "migration_text" not in call, \
        f"FAIL: migration_text still used in bm25_search call: {call}"
print("PASS: BM25 duplicate detection uses rule_statement, not migration_text")
EOF
```

### 0-H: `indexes.py` no longer references `CommunityInsight` in `migration_text` DDL

```python
python - <<'EOF'
import migration_oracle.graph.indexes as idx

migration_text_ddl = next(
    (s for s in idx._INDEXES if "migration_text" in s),
    None
)
assert migration_text_ddl is not None, "FAIL: migration_text DDL not found in _INDEXES"
assert "CommunityInsight" not in migration_text_ddl, \
    f"FAIL: CommunityInsight still in migration_text DDL:\n  {migration_text_ddl}"
assert "MigrationRule" in migration_text_ddl, \
    "FAIL: MigrationRule missing from migration_text DDL"
print(f"PASS: migration_text DDL covers only MigrationRule: {migration_text_ddl!r}")
EOF
```

### 0-I: `hydrate_nodes` in `search.py` has solution coalesce and no `include_community_insights`

```python
python - <<'EOF'
import inspect
import migration_oracle.mcp.graph.queries.search as sq

source = inspect.getsource(sq.hydrate_nodes)

assert "include_community_insights" not in source, \
    "FAIL: include_community_insights still present in hydrate_nodes"
assert "OPTIONAL MATCH (n)-[:REQUIRES_STEP]->(s:MigrationStep)" in source, \
    "FAIL: REQUIRES_STEP traversal missing from hydrate_nodes"
assert "coalesce(n.solution, first_step.instruction)" in source, \
    "FAIL: coalesce solution projection missing from hydrate_nodes"
assert "$include_community_insights" not in source, \
    "FAIL: $include_community_insights Cypher param still in hydrate_nodes"
print("PASS: hydrate_nodes has solution traversal and no include_community_insights")
EOF
```

### 0-J: Tool layer `search_migration_knowledge` and `_build_hits` signatures cleaned

```python
python - <<'EOF'
import inspect
import migration_oracle.mcp.tools.search as st

smk_sig = inspect.signature(st.search_migration_knowledge)
assert "include_community_insights" not in smk_sig.parameters, \
    f"FAIL: include_community_insights still in search_migration_knowledge signature"
print("PASS: search_migration_knowledge signature has no include_community_insights")

build_hits_sig = inspect.signature(st._build_hits)
assert "include_community_insights" not in build_hits_sig.parameters, \
    f"FAIL: include_community_insights still in _build_hits signature"
print("PASS: _build_hits signature has no include_community_insights")
EOF
```

### 0-K: Community tool signatures preserved byte-for-byte

```python
python - <<'EOF'
import inspect
from migration_oracle.mcp.tools.community import (
    submit_migration_insight,
    get_community_insights,
    vote_insight,
    verify_insight,
)

smi = inspect.signature(submit_migration_insight)
expected_smi = ["statement", "spring_boot_version", "solution", "affected_properties",
                "affected_classes", "affected_dependencies", "evidence_url",
                "confidence", "framework"]
actual_smi = list(smi.parameters.keys())
assert actual_smi == expected_smi, f"FAIL: submit_migration_insight signature changed.\n  Expected: {expected_smi}\n  Got: {actual_smi}"
print("PASS: submit_migration_insight signature unchanged")

gci = inspect.signature(get_community_insights)
expected_gci = ["from_version", "to_version", "entity_name", "entity_type", "verified_only", "framework"]
actual_gci = list(gci.parameters.keys())
assert actual_gci == expected_gci, f"FAIL: get_community_insights signature changed.\n  Expected: {expected_gci}\n  Got: {actual_gci}"
print("PASS: get_community_insights signature unchanged")

vi = inspect.signature(vote_insight)
assert list(vi.parameters.keys()) == ["insight_id", "delta"], \
    f"FAIL: vote_insight signature changed. Got: {list(vi.parameters.keys())}"
print("PASS: vote_insight signature unchanged")

vei = inspect.signature(verify_insight)
assert list(vei.parameters.keys()) == ["insight_id"], \
    f"FAIL: verify_insight signature changed. Got: {list(vei.parameters.keys())}"
print("PASS: verify_insight signature unchanged")
EOF
```

---

## Level 1 — Interface structure

**No external services required.**

### 1-A: `submit_migration_insight` docstring no longer references `CommunityInsight`

```python
python - <<'EOF'
from migration_oracle.mcp.tools.community import (
    submit_migration_insight,
    get_community_insights,
)

smi_doc = submit_migration_insight.__doc__ or ""
assert "CommunityInsight" not in smi_doc, \
    f"FAIL: submit_migration_insight docstring still references CommunityInsight:\n  {smi_doc}"
assert "MigrationRule" in smi_doc or "ruleType" in smi_doc, \
    "FAIL: submit_migration_insight docstring does not mention MigrationRule or ruleType"
print(f"PASS: submit_migration_insight docstring updated: {smi_doc[:80]!r}...")

gci_doc = get_community_insights.__doc__ or ""
assert "CommunityInsight" not in gci_doc, \
    f"FAIL: get_community_insights docstring still references CommunityInsight:\n  {gci_doc}"
print("PASS: get_community_insights docstring updated")
EOF
```

### 1-B: `search_migration_knowledge` docstring no longer references `include_community_insights`

```python
python - <<'EOF'
from migration_oracle.mcp.tools.search import search_migration_knowledge

doc = search_migration_knowledge.__doc__ or ""
assert "include_community_insights" not in doc, \
    f"FAIL: search_migration_knowledge docstring still references include_community_insights"
print("PASS: search_migration_knowledge docstring cleaned")
EOF
```

### 1-C: Missing required env vars raise `ConfigurationError`, not `ImportError`

```bash
# Run in a subprocess with NEO4J_URI unset to confirm fail-fast behaviour
python - <<'EOF'
import subprocess, sys, os
env = {k: v for k, v in os.environ.items() if k not in ("NEO4J_URI", "NEO4J_PASSWORD")}
env["NEO4J_URI"] = ""
result = subprocess.run(
    [sys.executable, "-c", "import migration_oracle.config"],
    capture_output=True, text=True, env=env
)
assert result.returncode != 0, "FAIL: expected non-zero exit when NEO4J_URI is empty"
assert "ConfigurationError" in result.stderr or "NEO4J_URI" in result.stderr, \
    f"FAIL: expected ConfigurationError message, got:\n{result.stderr}"
print("PASS: missing NEO4J_URI raises ConfigurationError at import")
EOF
```

---

## Level 2 — Isolation behaviour

**No external services required.**

### 2-A: `find_near_duplicate` with `embedding=None` short-circuits before vector/BM25 calls

```python
python - <<'EOF'
from unittest.mock import patch, MagicMock
import migration_oracle.mcp.graph.queries.community as cq

vector_mock = MagicMock(return_value=[])
bm25_mock   = MagicMock(return_value=[])
exact_mock  = MagicMock(return_value=None)  # no exact match

with patch.object(cq, '_find_exact_statement', exact_mock), \
     patch('migration_oracle.mcp.graph.queries.community.vector_search', vector_mock), \
     patch('migration_oracle.mcp.graph.queries.community.bm25_search',   bm25_mock):
    result = cq.find_near_duplicate(statement="any statement", embedding=None)

assert result is None, f"FAIL: expected None, got {result!r}"
vector_mock.assert_not_called(), "FAIL: vector_search was called despite embedding=None"
bm25_mock.assert_not_called(),   "FAIL: bm25_search was called despite embedding=None"
print("PASS: find_near_duplicate short-circuits when embedding=None")
EOF
```

### 2-B: `submit_insight` raises `ValueError` on Version-not-found (record is None)

```python
python - <<'EOF'
from unittest.mock import patch, MagicMock
import migration_oracle.mcp.graph.queries.community as cq

mock_session = MagicMock()
mock_session.__enter__ = lambda s: s
mock_session.__exit__ = MagicMock(return_value=False)
mock_session.run.return_value.single.return_value = None  # Version not found

with patch('migration_oracle.mcp.graph.queries.community.find_near_duplicate', return_value=None), \
     patch('migration_oracle.mcp.graph.queries.community.write_session', return_value=mock_session):
    try:
        cq.submit_insight(
            statement="test", framework="Spring Boot", version="99.99.0"
        )
        print("FAIL: expected ValueError, none raised")
    except ValueError as e:
        assert "Version not found" in str(e), \
            f"FAIL: ValueError message does not mention 'Version not found': {e}"
        assert "Spring Boot" in str(e), \
            f"FAIL: ValueError message does not include framework: {e}"
        print(f"PASS: submit_insight raises ValueError for missing Version: {e}")
    except RuntimeError as e:
        print(f"FAIL: old RuntimeError('Failed to create CommunityInsight') still raised: {e}")
EOF
```

### 2-C: `submit_migration_insight` tool returns structured error on `ValueError`

```python
python - <<'EOF'
from unittest.mock import patch, MagicMock
from migration_oracle.mcp.tools.community import submit_migration_insight

mock_model = MagicMock()
mock_model.encode.return_value = MagicMock(tolist=lambda: [0.1])

with patch('migration_oracle.mcp.tools.community.get_embedding_model', return_value=mock_model), \
     patch('migration_oracle.mcp.tools.community.community_queries.submit_insight',
           side_effect=ValueError("Version not found: Spring Boot 99.99.0")):
    result = submit_migration_insight(statement="test", spring_boot_version="99.99")

assert result["status"] == "error",        f"FAIL: status={result['status']!r}, expected 'error'"
assert result["insight_id"] == "",         f"FAIL: insight_id={result['insight_id']!r}, expected ''"
assert result["duplicate_of"] == "",       f"FAIL: duplicate_of={result['duplicate_of']!r}, expected ''"
assert "Version not found" in result["message"], \
    f"FAIL: message={result['message']!r} does not contain 'Version not found'"
print(f"PASS: submit_migration_insight returns structured error response: {result}")
EOF
```

### 2-D: `hydrate_nodes` does not accept `include_community_insights` kwarg

```python
python - <<'EOF'
from migration_oracle.mcp.graph.queries.search import hydrate_nodes
import inspect

sig = inspect.signature(hydrate_nodes)
assert "include_community_insights" not in sig.parameters, \
    "FAIL: hydrate_nodes still accepts include_community_insights parameter"
print("PASS: hydrate_nodes signature: " + str(sig))
EOF
```

### 2-E: `_FIND_EXACT_STATEMENT` filters by `ruleType` to avoid false positives from official rules

```python
python - <<'EOF'
import migration_oracle.mcp.graph.queries.community as cq

cypher = cq._FIND_EXACT_STATEMENT
assert "ruleType = 'community_insight'" in cypher, \
    f"FAIL: _FIND_EXACT_STATEMENT does not filter by ruleType:\n{cypher}"
assert "MigrationRule" in cypher, \
    "FAIL: _FIND_EXACT_STATEMENT does not target MigrationRule"
assert "CommunityInsight" not in cypher, \
    "FAIL: _FIND_EXACT_STATEMENT still targets CommunityInsight"
print("PASS: _FIND_EXACT_STATEMENT filters by MigrationRule and ruleType='community_insight'")
EOF
```

---

## Level 3 — Integration: read path

**DB required. No LLM.**

Run the cleanup block at the end of this level even if earlier checks fail.

### 3-A: Database connection

```python
python - <<'EOF'
from migration_oracle.graph.driver import get_driver

driver = get_driver()
with driver.session() as session:
    result = session.run("RETURN 1 AS n").single()
assert result["n"] == 1, f"FAIL: expected 1, got {result['n']}"
print("PASS: database connection OK")
EOF
```

### 3-B: `query_insights` returns empty list for a version range with no community insights

```python
python - <<'EOF'
from migration_oracle.mcp.graph.queries.community import query_insights
from migration_oracle.models.graph import sortable_version

results = query_insights(
    framework="Spring Boot",
    from_sortable=sortable_version("999.0.0"),
    to_sortable=sortable_version("999.9.9"),
    verified_only=False,
)
assert results == [], f"FAIL: expected empty list, got {results!r}"
print("PASS: query_insights returns [] for version range with no community insights")
EOF
```

### 3-C: `find_near_duplicate` returns `None` for an absent statement (no exact match)

```python
python - <<'EOF'
from migration_oracle.mcp.graph.queries.community import find_near_duplicate

result = find_near_duplicate(
    statement="__verification_probe_absent_statement_xyz_009__",
    embedding=None,
)
assert result is None, f"FAIL: expected None for absent statement, got {result!r}"
print("PASS: find_near_duplicate returns None for absent statement")
EOF
```

### 3-D: Write a community insight, read it back, verify all properties, then delete

```python
python - <<'EOF'
from migration_oracle.graph.driver import read_session, write_session

# Prerequisites: need a Version node to attach to
FRAMEWORK = "Spring Boot"
VERSION   = "999.0.0"

with write_session() as s:
    s.run(
        "MERGE (v:Version {framework: $fw, version: $v}) SET v.sortableVersion = 999000000",
        fw=FRAMEWORK, v=VERSION
    )
print("Setup: Version 999.0.0 created")

# Write via the query module
from migration_oracle.mcp.graph.queries.community import submit_insight

insight_id, is_dup = submit_insight(
    statement="Verification check: test insight for 009",
    framework=FRAMEWORK,
    version=VERSION,
    solution="Test solution text",
    embedding=None,
)
assert not is_dup, f"FAIL: unexpected duplicate for fresh statement"
print(f"Setup: insight written, insight_id={insight_id}")

# Read back and verify node properties
with read_session() as s:
    rec = s.run(
        """
        MATCH (r:MigrationRule) WHERE elementId(r) = $id
        RETURN r.ruleType AS ruleType,
               r.statement AS statement,
               r.communityVotes AS votes,
               r.communityVerified AS verified,
               r.communitySubmittedBy AS submittedBy,
               r.communityCreatedAt AS createdAt,
               r.communityConfidence AS confidence,
               r.sourceUrl AS sourceUrl
        """,
        id=insight_id
    ).single()

assert rec is not None, "FAIL: MigrationRule node not found after submit_insight"
assert rec["ruleType"] == "community_insight", \
    f"FAIL: ruleType={rec['ruleType']!r}, expected 'community_insight'"
assert rec["statement"] == "Verification check: test insight for 009", \
    f"FAIL: statement mismatch: {rec['statement']!r}"
assert rec["votes"] == 0,      f"FAIL: communityVotes={rec['votes']}, expected 0"
assert rec["verified"] == False, f"FAIL: communityVerified={rec['verified']}, expected false"
assert rec["submittedBy"] == "mcp-agent", \
    f"FAIL: communitySubmittedBy={rec['submittedBy']!r}, expected 'mcp-agent'"
assert rec["createdAt"] is not None, "FAIL: communityCreatedAt is None"
assert rec["confidence"] == 0.5, f"FAIL: communityConfidence={rec['confidence']}, expected 0.5"
print("PASS: MigrationRule node has all required community-prefixed properties")

# Verify no 'solution' property on the rule node
with read_session() as s:
    sol_rec = s.run(
        "MATCH (r:MigrationRule) WHERE elementId(r) = $id RETURN r.solution AS solution",
        id=insight_id
    ).single()
assert sol_rec["solution"] is None, \
    f"FAIL: MigrationRule has solution property directly: {sol_rec['solution']!r} — must be on MigrationStep"
print("PASS: MigrationRule has no direct 'solution' property")

# Verify MigrationStep child
with read_session() as s:
    step_rec = s.run(
        """
        MATCH (r:MigrationRule)-[:REQUIRES_STEP]->(s:MigrationStep)
        WHERE elementId(r) = $id
        RETURN s.stepType AS stepType, s.instruction AS instruction,
               s.summary AS summary, s.effort AS effort, s.automatable AS automatable
        """,
        id=insight_id
    ).single()

assert step_rec is not None, "FAIL: no MigrationStep child found via REQUIRES_STEP"
assert step_rec["stepType"] == "manual",   f"FAIL: stepType={step_rec['stepType']!r}"
assert step_rec["effort"] == "moderate",   f"FAIL: effort={step_rec['effort']!r}"
assert step_rec["automatable"] == False,   f"FAIL: automatable={step_rec['automatable']!r}"
assert step_rec["instruction"] == "Test solution text", \
    f"FAIL: instruction={step_rec['instruction']!r}"
assert step_rec["summary"] == "Test solution text", \
    f"FAIL: summary={step_rec['summary']!r}"
print("PASS: MigrationStep child has correct properties")

# Verify INCLUDES_RULE direction: (Version)-[:INCLUDES_RULE]->(MigrationRule)
with read_session() as s:
    rel_rec = s.run(
        """
        MATCH (v:Version {framework: $fw, version: $ver})-[:INCLUDES_RULE]->(r:MigrationRule)
        WHERE elementId(r) = $id
        RETURN count(r) AS cnt
        """,
        fw=FRAMEWORK, ver=VERSION, id=insight_id
    ).single()
assert rel_rec["cnt"] == 1, \
    f"FAIL: INCLUDES_RULE from Version to MigrationRule not found (count={rel_rec['cnt']})"
print("PASS: INCLUDES_RULE (Version)→(MigrationRule) relationship exists")

# Verify query_insights returns the insight with solution from step
from migration_oracle.mcp.graph.queries.community import query_insights
from migration_oracle.models.graph import sortable_version

rows = query_insights(
    framework=FRAMEWORK,
    from_sortable=sortable_version("999.0.0"),
    to_sortable=sortable_version("999.0.0"),
)
assert len(rows) >= 1, f"FAIL: query_insights returned no rows for 999.0.0"
row = next((r for r in rows if r["insight_id"] == insight_id), None)
assert row is not None, f"FAIL: submitted insight not found in query_insights results"
assert row["solution"] == "Test solution text", \
    f"FAIL: solution={row['solution']!r}, expected 'Test solution text' (from MigrationStep)"
assert row["submitted_by"] == "mcp-agent", \
    f"FAIL: submitted_by={row['submitted_by']!r}"
assert row["verified"] == False, f"FAIL: verified={row['verified']!r}"
print("PASS: query_insights returns insight with solution from MigrationStep.instruction")

print(f"\nCleanup token: insight_id={insight_id}")
EOF
```

### 3-E: Cleanup — delete test nodes

```python
python - <<'EOF'
# Replace <insight_id> with the value printed by 3-D
INSIGHT_ID = "<insight_id>"   # ← paste from 3-D output
FRAMEWORK  = "Spring Boot"
VERSION    = "999.0.0"

from migration_oracle.graph.driver import write_session

with write_session() as s:
    s.run(
        """
        MATCH (r:MigrationRule) WHERE elementId(r) = $id
        OPTIONAL MATCH (r)-[:REQUIRES_STEP]->(s:MigrationStep)
        DETACH DELETE r, s
        """,
        id=INSIGHT_ID
    )
    s.run(
        "MATCH (v:Version {framework: $fw, version: $ver}) DETACH DELETE v",
        fw=FRAMEWORK, ver=VERSION
    )
print("PASS: Level 3 test nodes deleted")
EOF
```

---

## Level 5 — Integration: full write path

**DB required. Embedding model optional (tested both ways).**

This level validates the complete tool-layer call path, relationship counts, and SC-* gates.

### Setup: seed a test Version node

```python
python - <<'EOF'
from migration_oracle.graph.driver import write_session

with write_session() as s:
    s.run(
        "MERGE (v:Version {framework: 'Spring Boot', version: '999.1.0'}) SET v.sortableVersion = 999001000"
    )
print("Setup: Version 999.1.0 created")
EOF
```

### 5-A: Full submit via tool layer — success path

```python
python - <<'EOF'
from unittest.mock import patch, MagicMock
from migration_oracle.mcp.tools.community import submit_migration_insight

# Mock embedding model to avoid loading sentence-transformers during verification
mock_model = MagicMock()
mock_model.encode.return_value = MagicMock(tolist=lambda: [0.1] * 768)

with patch('migration_oracle.mcp.tools.community.get_embedding_model', return_value=mock_model):
    result = submit_migration_insight(
        statement="Level 5 verification: DataSourceAutoConfiguration must be excluded",
        spring_boot_version="999.1.0",
        solution="Add @SpringBootApplication(exclude = {DataSourceAutoConfiguration.class})",
        affected_classes=["DataSourceAutoConfiguration"],
        framework="Spring Boot",
    )

assert result["status"] == "ok", f"FAIL: status={result['status']!r}"
assert result["insight_id"] != "", f"FAIL: insight_id is empty"
assert result["duplicate_of"] == "", f"FAIL: duplicate_of={result['duplicate_of']!r}"
assert result["message"] == "Insight submitted", f"FAIL: message={result['message']!r}"

INSIGHT_ID = result["insight_id"]
print(f"PASS: submit_migration_insight succeeded. insight_id={INSIGHT_ID}")
print(f"Capture: INSIGHT_ID={INSIGHT_ID}")
EOF
```

### 5-B: Verify MigrationRule node properties and absence of legacy fields

```python
python - <<'EOF'
# Replace <insight_id> with value from 5-A
INSIGHT_ID = "<insight_id>"

from migration_oracle.graph.driver import read_session

with read_session() as s:
    rec = s.run(
        """
        MATCH (r:MigrationRule) WHERE elementId(r) = $id
        RETURN labels(r) AS node_labels,
               r.ruleType AS ruleType,
               r.communityVotes AS votes,
               r.communityVerified AS verified,
               r.communitySubmittedBy AS submittedBy,
               r.communityCreatedAt AS createdAt,
               r.communityConfidence AS confidence,
               r.solution AS directSolution,
               r.votes AS oldVotes,
               r.verified AS oldVerified
        """,
        id=INSIGHT_ID
    ).single()

assert rec is not None, "FAIL: MigrationRule node not found"
assert "MigrationRule" in rec["node_labels"], \
    f"FAIL: node_labels={rec['node_labels']!r} — MigrationRule label missing"
assert "CommunityInsight" not in rec["node_labels"], \
    f"FAIL: CommunityInsight label present on node: {rec['node_labels']!r}"
assert rec["ruleType"] == "community_insight", \
    f"FAIL: ruleType={rec['ruleType']!r}"
assert rec["votes"] == 0,   f"FAIL: communityVotes={rec['votes']}"
assert rec["verified"] == False, f"FAIL: communityVerified={rec['verified']}"

# Confirm no legacy flat properties
assert rec["directSolution"] is None, \
    f"FAIL: MigrationRule.solution={rec['directSolution']!r} — should not exist"
assert rec["oldVotes"] is None, \
    f"FAIL: MigrationRule.votes={rec['oldVotes']!r} — unprefixed 'votes' must not exist"
assert rec["oldVerified"] is None, \
    f"FAIL: MigrationRule.verified={rec['oldVerified']!r} — unprefixed 'verified' must not exist"

print("PASS: MigrationRule has correct community-prefixed properties; no legacy flat properties")
EOF
```

### 5-C: Verify MigrationStep child and AFFECTS_CLASS relationship

```python
python - <<'EOF'
INSIGHT_ID = "<insight_id>"

from migration_oracle.graph.driver import read_session

with read_session() as s:
    step = s.run(
        """
        MATCH (r:MigrationRule)-[:REQUIRES_STEP]->(s:MigrationStep)
        WHERE elementId(r) = $id
        RETURN s.stepType AS stepType, s.instruction AS instruction,
               s.effort AS effort, s.automatable AS automatable
        """,
        id=INSIGHT_ID
    ).single()

assert step is not None, "FAIL: no MigrationStep via REQUIRES_STEP"
assert step["stepType"] == "manual",  f"FAIL: stepType={step['stepType']!r}"
assert step["effort"] == "moderate",  f"FAIL: effort={step['effort']!r}"
assert step["automatable"] == False,  f"FAIL: automatable={step['automatable']!r}"
assert "DataSourceAutoConfiguration" in step["instruction"], \
    f"FAIL: instruction does not contain submitted solution text: {step['instruction']!r}"
print("PASS: MigrationStep has correct properties")

with read_session() as s:
    affects = s.run(
        """
        MATCH (r:MigrationRule)-[:AFFECTS_CLASS]->(c:Class)
        WHERE elementId(r) = $id
        RETURN c.name AS name
        """,
        id=INSIGHT_ID
    ).data()

class_names = [row["name"] for row in affects]
assert "DataSourceAutoConfiguration" in class_names, \
    f"FAIL: AFFECTS_CLASS to DataSourceAutoConfiguration not found. Got: {class_names}"
print("PASS: AFFECTS_CLASS relationship created for affected_classes")
EOF
```

### 5-D: `get_community_insights` returns insight with solution from MigrationStep

```python
python - <<'EOF'
INSIGHT_ID = "<insight_id>"

from migration_oracle.mcp.tools.community import get_community_insights

result = get_community_insights(
    from_version="999.1.0",
    to_version="999.1.0",
    framework="Spring Boot",
)

assert result["status"] == "ok",   f"FAIL: status={result['status']!r}"
assert result["total"] >= 1,       f"FAIL: total={result['total']}, expected >= 1"

insight = next((i for i in result["insights"] if i["insight_id"] == INSIGHT_ID), None)
assert insight is not None, f"FAIL: submitted insight not found in get_community_insights results"

required_fields = ["insight_id", "statement", "solution", "source_url",
                   "submitted_by", "created_at", "confidence", "votes", "verified", "version"]
for field in required_fields:
    assert field in insight, f"FAIL: field '{field}' missing from insight record"

assert "DataSourceAutoConfiguration" in insight["solution"], \
    f"FAIL: solution={insight['solution']!r} — does not contain submitted text"
assert insight["votes"] == 0,        f"FAIL: votes={insight['votes']}"
assert insight["verified"] == False, f"FAIL: verified={insight['verified']}"
assert insight["version"] == "999.1.0", f"FAIL: version={insight['version']!r}"

print(f"PASS: get_community_insights returns insight with all required fields")
print(f"      solution={insight['solution']!r}")
EOF
```

### 5-E: `vote_insight` increments `communityVotes` on the MigrationRule node

```python
python - <<'EOF'
INSIGHT_ID = "<insight_id>"

from migration_oracle.mcp.tools.community import vote_insight

result = vote_insight(insight_id=INSIGHT_ID, delta=1)
assert result["status"] == "ok",        f"FAIL: status={result['status']!r}"
assert result["insight_id"] == INSIGHT_ID, f"FAIL: insight_id mismatch"
assert result["new_vote_count"] == 1,   f"FAIL: new_vote_count={result['new_vote_count']}, expected 1"
print("PASS: vote_insight increments communityVotes to 1")

# Verify on the node directly
from migration_oracle.graph.driver import read_session
with read_session() as s:
    votes = s.run(
        "MATCH (r:MigrationRule) WHERE elementId(r) = $id RETURN r.communityVotes AS v",
        id=INSIGHT_ID
    ).single()["v"]
assert votes == 1, f"FAIL: communityVotes on node={votes}, expected 1"
print("PASS: communityVotes=1 confirmed on MigrationRule node")
EOF
```

### 5-F: `verify_insight` sets `communityVerified=true` on the MigrationRule node

```python
python - <<'EOF'
INSIGHT_ID = "<insight_id>"

from migration_oracle.mcp.tools.community import verify_insight

result = verify_insight(insight_id=INSIGHT_ID)
assert result["status"] == "ok",          f"FAIL: status={result['status']!r}"
assert result["insight_id"] == INSIGHT_ID, f"FAIL: insight_id mismatch"
assert result["verified"] == True,        f"FAIL: verified={result['verified']!r}"
print("PASS: verify_insight sets communityVerified=true")

from migration_oracle.graph.driver import read_session
with read_session() as s:
    verified = s.run(
        "MATCH (r:MigrationRule) WHERE elementId(r) = $id RETURN r.communityVerified AS v",
        id=INSIGHT_ID
    ).single()["v"]
assert verified == True, f"FAIL: communityVerified on node={verified!r}"
print("PASS: communityVerified=true confirmed on MigrationRule node")
EOF
```

### 5-G: SC-004 — no `CommunityInsight` nodes exist in the graph

```python
python - <<'EOF'
from migration_oracle.graph.driver import read_session

with read_session() as s:
    count = s.run("MATCH (n:CommunityInsight) RETURN count(n) AS cnt").single()["cnt"]
assert count == 0, f"FAIL: {count} CommunityInsight node(s) still exist in the graph"
print(f"PASS: SC-004 — zero CommunityInsight nodes in graph")
EOF
```

### 5-H: `search_migration_knowledge` returns community insight without any flag

```python
python - <<'EOF'
INSIGHT_ID = "<insight_id>"

# Use an async call via asyncio.run
import asyncio
from unittest.mock import patch, MagicMock
from migration_oracle.mcp.tools.search import search_migration_knowledge

mock_model = MagicMock()
mock_model.encode.return_value = MagicMock(tolist=lambda: [0.1] * 768)

with patch('migration_oracle.mcp.tools.search.get_embedding_model', return_value=mock_model):
    result = asyncio.run(search_migration_knowledge(
        query="DataSourceAutoConfiguration exclude",
        framework="Spring Boot",
        max_results=10,
    ))

assert result["status"] == "ok", f"FAIL: status={result['status']!r}"
# Verify the community insight appears in hits (may not be top-ranked if vector disabled)
hit_ids = [h.get("node_id") for h in result.get("hits", [])]
print(f"INFO: search returned {len(hit_ids)} hits: {hit_ids}")
# SC-003: the call must not fail due to an unexpected parameter
print("PASS: search_migration_knowledge called successfully without include_community_insights")
EOF
```

### Level 5 cleanup

```python
python - <<'EOF'
INSIGHT_ID = "<insight_id>"

from migration_oracle.graph.driver import write_session

with write_session() as s:
    # Delete the MigrationRule, its MigrationStep, and any AFFECTS_* targets if orphaned
    s.run(
        """
        MATCH (r:MigrationRule) WHERE elementId(r) = $id
        OPTIONAL MATCH (r)-[:REQUIRES_STEP]->(s:MigrationStep)
        DETACH DELETE r, s
        """,
        id=INSIGHT_ID
    )
    s.run(
        "MATCH (v:Version {framework: 'Spring Boot', version: '999.1.0'}) DETACH DELETE v"
    )
print("PASS: Level 5 test nodes deleted")
EOF
```

---

## Level 6 — Idempotency

**DB required.**

### Setup

```python
python - <<'EOF'
from migration_oracle.graph.driver import write_session

with write_session() as s:
    s.run(
        "MERGE (v:Version {framework: 'Spring Boot', version: '999.2.0'}) SET v.sortableVersion = 999002000"
    )
print("Setup: Version 999.2.0 created")
EOF
```

### 6-A: Second submit of identical statement returns duplicate, no new node

```python
python - <<'EOF'
from unittest.mock import patch, MagicMock
from migration_oracle.mcp.tools.community import submit_migration_insight

mock_model = MagicMock()
mock_model.encode.return_value = MagicMock(tolist=lambda: [0.1] * 768)

with patch('migration_oracle.mcp.tools.community.get_embedding_model', return_value=mock_model):
    r1 = submit_migration_insight(
        statement="Idempotency test: identical statement for 009 verification",
        spring_boot_version="999.2.0",
        solution="Some fix",
        framework="Spring Boot",
    )

assert r1["status"] == "ok", f"FAIL (first submit): {r1}"
INSIGHT_ID = r1["insight_id"]
print(f"First submit: {r1}")

with patch('migration_oracle.mcp.tools.community.get_embedding_model', return_value=mock_model):
    r2 = submit_migration_insight(
        statement="Idempotency test: identical statement for 009 verification",
        spring_boot_version="999.2.0",
        solution="Some fix",
        framework="Spring Boot",
    )

assert r2["status"] == "duplicate", \
    f"FAIL (second submit): expected status='duplicate', got {r2['status']!r}"
assert r2["duplicate_of"] == INSIGHT_ID, \
    f"FAIL: duplicate_of={r2['duplicate_of']!r}, expected {INSIGHT_ID!r}"
print(f"PASS: second submit correctly returns duplicate: {r2}")
print(f"Capture: INSIGHT_ID={INSIGHT_ID}")
EOF
```

### 6-B: Node and edge counts are identical after the duplicate submit

```python
python - <<'EOF'
INSIGHT_ID = "<insight_id>"   # from 6-A

from migration_oracle.graph.driver import read_session

def get_counts(insight_id: str) -> dict:
    with read_session() as s:
        rule_count = s.run(
            "MATCH (r:MigrationRule) WHERE elementId(r) = $id RETURN count(r) AS cnt",
            id=insight_id
        ).single()["cnt"]
        step_count = s.run(
            "MATCH (r:MigrationRule)-[:REQUIRES_STEP]->(s:MigrationStep) WHERE elementId(r) = $id RETURN count(s) AS cnt",
            id=insight_id
        ).single()["cnt"]
        includes_count = s.run(
            "MATCH ()-[:INCLUDES_RULE]->(r:MigrationRule) WHERE elementId(r) = $id RETURN count(r) AS cnt",
            id=insight_id
        ).single()["cnt"]
    return {"rule": rule_count, "step": step_count, "includes_rule": includes_count}

counts = get_counts(INSIGHT_ID)
assert counts["rule"] == 1, \
    f"FAIL: expected 1 MigrationRule, found {counts['rule']} — duplicate node created"
assert counts["step"] == 1, \
    f"FAIL: expected 1 MigrationStep, found {counts['step']} — duplicate step created"
assert counts["includes_rule"] == 1, \
    f"FAIL: expected 1 INCLUDES_RULE edge, found {counts['includes_rule']} — duplicate edge created"

print(f"PASS: node and edge counts unchanged after duplicate submit: {counts}")
EOF
```

### 6-C: `verify_insight` called twice leaves `communityVerified=true` (idempotent)

```python
python - <<'EOF'
INSIGHT_ID = "<insight_id>"

from migration_oracle.mcp.tools.community import verify_insight

r1 = verify_insight(insight_id=INSIGHT_ID)
r2 = verify_insight(insight_id=INSIGHT_ID)
assert r2["verified"] == True, f"FAIL: verified={r2['verified']!r} after second verify"
assert r2["status"] == "ok",   f"FAIL: status={r2['status']!r} on second verify"
print("PASS: verify_insight is idempotent — second call still returns verified=true")
EOF
```

### Level 6 cleanup

```python
python - <<'EOF'
INSIGHT_ID = "<insight_id>"

from migration_oracle.graph.driver import write_session

with write_session() as s:
    s.run(
        """
        MATCH (r:MigrationRule) WHERE elementId(r) = $id
        OPTIONAL MATCH (r)-[:REQUIRES_STEP]->(s:MigrationStep)
        DETACH DELETE r, s
        """,
        id=INSIGHT_ID
    )
    s.run(
        "MATCH (v:Version {framework: 'Spring Boot', version: '999.2.0'}) DETACH DELETE v"
    )
print("PASS: Level 6 test nodes deleted")
EOF
```

---

## Level 7 — Edge-case paths

### 7-A: Version-not-found returns structured error (no matching Version node)

```python
python - <<'EOF'
from unittest.mock import patch, MagicMock
from migration_oracle.mcp.tools.community import submit_migration_insight

mock_model = MagicMock()
mock_model.encode.return_value = MagicMock(tolist=lambda: [0.1] * 768)

with patch('migration_oracle.mcp.tools.community.get_embedding_model', return_value=mock_model):
    result = submit_migration_insight(
        statement="Edge case: version that cannot possibly exist",
        spring_boot_version="888.888.888",
        solution="Irrelevant",
        framework="Spring Boot",
    )

assert result["status"] == "error", \
    f"FAIL: expected status='error', got {result['status']!r}"
assert result["insight_id"] == "",  f"FAIL: insight_id={result['insight_id']!r}"
assert "Version not found" in result["message"] or "888" in result["message"], \
    f"FAIL: message={result['message']!r} — missing version info"
print(f"PASS: Version-not-found returns structured error: {result}")
EOF
```

### 7-B: `verified_only=True` filters out unverified insights

```python
python - <<'EOF'
from migration_oracle.graph.driver import write_session, read_session

# Seed two insights: one verified, one not
with write_session() as s:
    s.run("MERGE (v:Version {framework: 'Spring Boot', version: '999.3.0'}) SET v.sortableVersion = 999003000")
    r1 = s.run(
        """
        MATCH (v:Version {framework: 'Spring Boot', version: '999.3.0'})
        CREATE (r:MigrationRule {statement: 'verified insight', ruleType: 'community_insight',
          communityVotes: 0, communityVerified: true, communitySubmittedBy: 'test',
          communityCreatedAt: toString(datetime()), communityConfidence: 0.9, sourceUrl: ''})
        CREATE (v)-[:INCLUDES_RULE]->(r)
        CREATE (s:MigrationStep {stepType: 'manual', instruction: 'do it', summary: 'do it',
          effort: 'moderate', automatable: false})
        CREATE (r)-[:REQUIRES_STEP]->(s)
        RETURN elementId(r) AS id
        """
    ).single()
    id_verified = r1["id"]

    r2 = s.run(
        """
        MATCH (v:Version {framework: 'Spring Boot', version: '999.3.0'})
        CREATE (r:MigrationRule {statement: 'unverified insight', ruleType: 'community_insight',
          communityVotes: 0, communityVerified: false, communitySubmittedBy: 'test',
          communityCreatedAt: toString(datetime()), communityConfidence: 0.5, sourceUrl: ''})
        CREATE (v)-[:INCLUDES_RULE]->(r)
        CREATE (s:MigrationStep {stepType: 'manual', instruction: 'maybe', summary: 'maybe',
          effort: 'moderate', automatable: false})
        CREATE (r)-[:REQUIRES_STEP]->(s)
        RETURN elementId(r) AS id
        """
    ).single()
    id_unverified = r2["id"]

print(f"Setup: verified={id_verified}, unverified={id_unverified}")

from migration_oracle.mcp.tools.community import get_community_insights

# verified_only=False — both returned
all_results = get_community_insights(
    from_version="999.3.0", to_version="999.3.0", framework="Spring Boot", verified_only=False
)
all_ids = {i["insight_id"] for i in all_results["insights"]}
assert id_verified in all_ids,   f"FAIL: verified insight missing from verified_only=False results"
assert id_unverified in all_ids, f"FAIL: unverified insight missing from verified_only=False results"
print("PASS: verified_only=False returns both insights")

# verified_only=True — only verified returned
verified_results = get_community_insights(
    from_version="999.3.0", to_version="999.3.0", framework="Spring Boot", verified_only=True
)
verified_ids = {i["insight_id"] for i in verified_results["insights"]}
assert id_verified in verified_ids, \
    f"FAIL: verified insight not in verified_only=True results"
assert id_unverified not in verified_ids, \
    f"FAIL: unverified insight appears in verified_only=True results"
print("PASS: verified_only=True returns only the verified insight")

# Cleanup
with write_session() as s:
    s.run(
        """
        MATCH (r:MigrationRule) WHERE elementId(r) IN $ids
        OPTIONAL MATCH (r)-[:REQUIRES_STEP]->(step)
        DETACH DELETE r, step
        """,
        ids=[id_verified, id_unverified]
    )
    s.run("MATCH (v:Version {framework: 'Spring Boot', version: '999.3.0'}) DETACH DELETE v")
print("Cleanup: 7-B nodes deleted")
EOF
```

### 7-C: `embedding=None` — node written without `embedding` property

```python
python - <<'EOF'
from unittest.mock import patch, MagicMock
from migration_oracle.graph.driver import write_session, read_session

with write_session() as s:
    s.run("MERGE (v:Version {framework: 'Spring Boot', version: '999.4.0'}) SET v.sortableVersion = 999004000")

from migration_oracle.mcp.tools.community import submit_migration_insight

# Force embedding to None by making get_embedding_model raise
with patch('migration_oracle.mcp.tools.community.get_embedding_model',
           side_effect=RuntimeError("embeddings disabled")):
    result = submit_migration_insight(
        statement="7-C: embedding-disabled insight",
        spring_boot_version="999.4.0",
        solution="No embedding needed",
        framework="Spring Boot",
    )

assert result["status"] == "ok", f"FAIL: expected ok, got {result['status']!r} — exception must not propagate"
INSIGHT_ID = result["insight_id"]

with read_session() as s:
    rec = s.run(
        "MATCH (r:MigrationRule) WHERE elementId(r) = $id RETURN r.embedding AS emb",
        id=INSIGHT_ID
    ).single()
assert rec["emb"] is None, \
    f"FAIL: embedding property present on node: {rec['emb']!r} — should be absent when disabled"
print("PASS: embedding=None → node written without embedding property, no exception raised")

with write_session() as s:
    s.run(
        "MATCH (r:MigrationRule) WHERE elementId(r) = $id OPTIONAL MATCH (r)-[:REQUIRES_STEP]->(s) DETACH DELETE r, s",
        id=INSIGHT_ID
    )
    s.run("MATCH (v:Version {framework: 'Spring Boot', version: '999.4.0'}) DETACH DELETE v")
print("Cleanup: 7-C nodes deleted")
EOF
```

### 7-D: `vote_insight` with non-existent `insight_id` raises `ValueError`

```python
python - <<'EOF'
from migration_oracle.mcp.graph.queries.community import vote_insight

try:
    vote_insight(insight_id="nonexistent-element-id-00000", delta=1)
    print("FAIL: expected ValueError for non-existent insight_id, none raised")
except ValueError as e:
    print(f"PASS: vote_insight raises ValueError for non-existent id: {e}")
except Exception as e:
    print(f"FAIL: unexpected exception type {type(e).__name__}: {e}")
EOF
```

### 7-E: `migration_knowledge_vector_ci` index name is completely absent from codebase

```bash
result=$(grep -r 'migration_knowledge_vector_ci' migration_oracle/ --include="*.py")
if [ -z "$result" ]; then
    echo "PASS: migration_knowledge_vector_ci not referenced anywhere in migration_oracle/"
else
    echo "FAIL: migration_knowledge_vector_ci still referenced:"
    echo "$result"
fi
```

---

## Completion Gate

Update `SPEC_ORGANIZATION.md` (or equivalent tracking) to `✅ Complete` only when every item below is checked.

| Check ID | Description | Result |
|----------|-------------|--------|
| 0-A | All 5 modules import without error | ☐ |
| 0-B | `CommunityInsight` absent from all `.py` source files | ☐ |
| 0-C | `include_community_insights` absent from all `.py` source files | ☐ |
| 0-D | `_SUBMIT_INSIGHT` Cypher: all 17 required fragments present, all forbidden patterns absent | ☐ |
| 0-E | `_QUERY_INSIGHTS` Cypher: REQUIRES_STEP traversal, coalesce solution, community-prefixed properties | ☐ |
| 0-F | `_VOTE_INSIGHT` and `_VERIFY_INSIGHT` target MigrationRule with community-prefixed properties | ☐ |
| 0-G | Vector index `migration_knowledge_vector_mr`; BM25 index `rule_statement` in community.py | ☐ |
| 0-H | `migration_text` DDL covers only `MigrationRule` (no `CommunityInsight`) | ☐ |
| 0-I | `hydrate_nodes`: no `include_community_insights`, REQUIRES_STEP traversal, coalesce solution | ☐ |
| 0-J | `search_migration_knowledge` and `_build_hits` signatures have no `include_community_insights` | ☐ |
| 0-K | All four community tool signatures byte-for-byte identical to pre-spec versions | ☐ |
| 1-A | `submit_migration_insight` and `get_community_insights` docstrings updated; no `CommunityInsight` | ☐ |
| 1-B | `search_migration_knowledge` docstring has no `include_community_insights` reference | ☐ |
| 1-C | Missing `NEO4J_URI` raises `ConfigurationError` at import | ☐ |
| 2-A | `find_near_duplicate(embedding=None)` short-circuits; `vector_search` and `bm25_search` not called | ☐ |
| 2-B | `submit_insight` raises `ValueError("Version not found: …")` when record is None | ☐ |
| 2-C | `submit_migration_insight` tool returns `{status: "error", …}` on ValueError | ☐ |
| 2-D | `hydrate_nodes` does not accept `include_community_insights` kwarg | ☐ |
| 2-E | `_FIND_EXACT_STATEMENT` filters by `ruleType='community_insight'` | ☐ |
| 3-A | Database driver connects; `RETURN 1` succeeds | ☐ |
| 3-B | `query_insights` returns `[]` for unreachable version range | ☐ |
| 3-C | `find_near_duplicate` returns `None` for absent statement | ☐ |
| 3-D | Submit via `submit_insight`, read back: ruleType, communityVotes=0, communityVerified=false, MigrationStep child, INCLUDES_RULE direction | ☐ |
| 3-D | `query_insights` returns insight with `solution` from MigrationStep.instruction | ☐ |
| 3-D | MigrationRule has no direct `solution` property | ☐ |
| 3-E | Level 3 cleanup: test nodes deleted | ☐ |
| 5-A | `submit_migration_insight` returns `{status: "ok", insight_id: <id>, duplicate_of: ""}` | ☐ |
| 5-B | MigrationRule: `CommunityInsight` label absent; no legacy `votes`/`verified`/`solution` flat properties | ☐ |
| 5-C | MigrationStep: `stepType='manual'`, `effort='moderate'`, `automatable=false`, instruction=submitted text | ☐ |
| 5-C | AFFECTS_CLASS relationship created for `affected_classes` parameter | ☐ |
| 5-D | `get_community_insights` returns all required fields; `solution` from MigrationStep | ☐ |
| 5-E | `vote_insight(delta=1)` → `new_vote_count=1`; `communityVotes=1` on node | ☐ |
| 5-F | `verify_insight` → `verified=true`; `communityVerified=true` on node | ☐ |
| 5-G | SC-004: zero `CommunityInsight` nodes in graph | ☐ |
| 5-H | `search_migration_knowledge` called successfully without `include_community_insights` flag | ☐ |
| 5-cleanup | Level 5 test nodes deleted | ☐ |
| 6-A | Second submit of identical statement returns `status='duplicate'` with correct `duplicate_of` | ☐ |
| 6-B | Node count: 1 MigrationRule, 1 MigrationStep, 1 INCLUDES_RULE edge after duplicate submit | ☐ |
| 6-C | `verify_insight` called twice: second call still returns `verified=true` | ☐ |
| 6-cleanup | Level 6 test nodes deleted | ☐ |
| 7-A | Version-not-found returns `{status: "error", insight_id: "", message: "Version not found: …"}` | ☐ |
| 7-B | `verified_only=False` returns both; `verified_only=True` returns only verified insight | ☐ |
| 7-C | `embedding=None`: no exception; MigrationRule has no `embedding` property | ☐ |
| 7-D | `vote_insight` with non-existent ID raises `ValueError` | ☐ |
| 7-E | `migration_knowledge_vector_ci` not referenced anywhere in `migration_oracle/` | ☐ |
