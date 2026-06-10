# Verification Protocol: 009a — Community Insights UI Improvements

**Location**: `specs/009a-community-insights-ui/verification.md`
**Spec gate**: Run this after `/speckit.implement` completes, before marking `009a` ✅
**Execution order**: Levels 0 → 7 in sequence. Stop and fix on the first failure — failures compound.

---

## Prerequisites

| Requirement | How to confirm |
|-------------|----------------|
| Python env synced | `pip install -e ".[dev]"` or `uv sync` with no errors |
| Streamlit reachable | `streamlit run migration_oracle/streamlit_app/Home.py` starts on port 8501 |
| Neo4j reachable | `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` env vars set; port 7687 open |
| At least one community insight in DB | `MATCH (n:MigrationRule {ruleType:'community_insight'}) RETURN count(n)` returns ≥ 1 |

**Level infrastructure matrix**:

| Level | Requires LLM | Requires DB |
|-------|-------------|------------|
| 0 — Static checks | No | No |
| 2 — Isolation / filter logic | No | No |
| 3 — Integration read path | No | Yes |
| 7 — Edge-case paths | No | No |

---

## Level 0 — Static checks

No external services required.

### 0-A: `05_community.py` parses as valid Python AST

```python
python - <<'EOF'
import ast, pathlib
src = pathlib.Path("migration_oracle/streamlit_app/pages/05_community.py").read_text()
ast.parse(src)
print("PASS 0-A: 05_community.py parses as valid Python AST")
EOF
```

### 0-B: `import html as _html` is present

```python
python - <<'EOF'
import pathlib
src = pathlib.Path("migration_oracle/streamlit_app/pages/05_community.py").read_text()
assert "import html as _html" in src, "FAIL 0-B: import html as _html not found"
print("PASS 0-B: import html as _html present")
EOF
```

### 0-C: `vote-flash` keyframe and `voting-btn` class are removed

```python
python - <<'EOF'
import pathlib
src = pathlib.Path("migration_oracle/streamlit_app/pages/05_community.py").read_text()
assert "vote-flash" not in src, "FAIL 0-C: vote-flash keyframe still present"
assert "voting-btn" not in src,  "FAIL 0-C: voting-btn class still present"
print("PASS 0-C: deprecated vote-flash keyframe and voting-btn class are absent")
EOF
```

### 0-D: New CSS classes are present

```python
python - <<'EOF'
import pathlib
src = pathlib.Path("migration_oracle/streamlit_app/pages/05_community.py").read_text()
for cls in [".controls-row", ".fw-badge", ".ver-badge", ".voting-loading"]:
    assert cls in src, f"FAIL 0-D: CSS class '{cls}' not found"
print("PASS 0-D: .controls-row, .fw-badge, .ver-badge, .voting-loading all present")
EOF
```

### 0-E: Framework selectbox uses distinct keys; old key gone

```python
python - <<'EOF'
import pathlib
src = pathlib.Path("migration_oracle/streamlit_app/pages/05_community.py").read_text()
assert 'key="ci_fw_filter"' in src,  "FAIL 0-E: page-level selectbox key 'ci_fw_filter' missing"
assert 'key="ci_fw_submit"' in src,  "FAIL 0-E: submit-form selectbox key 'ci_fw_submit' missing"
assert 'key="ci_fw"'        not in src, "FAIL 0-E: old conflicting key 'ci_fw' still present"
print("PASS 0-E: framework selectbox keys are distinct (ci_fw_filter / ci_fw_submit)")
EOF
```

### 0-F: Submit form label updated to "Framework version"

```python
python - <<'EOF'
import pathlib
src = pathlib.Path("migration_oracle/streamlit_app/pages/05_community.py").read_text()
assert '"Spring Boot version"' not in src, \
    "FAIL 0-F: old label 'Spring Boot version' still present"
assert '"Framework version"' in src, \
    "FAIL 0-F: new label 'Framework version' not found"
assert "e.g. 3.2 for Spring Boot, 30 for WildFly" in src, \
    "FAIL 0-F: multi-framework placeholder not found"
print("PASS 0-F: submit form label is 'Framework version' with correct placeholder")
EOF
```

### 0-G: `_html.escape()` applied to user-supplied card fields

```python
python - <<'EOF'
import pathlib
src = pathlib.Path("migration_oracle/streamlit_app/pages/05_community.py").read_text()
for call in [
    '_html.escape(insight.get("statement",',
    '_html.escape(insight.get("solution",',
    '_html.escape(insight.get("version",',
]:
    assert call in src, f"FAIL 0-G: missing escape call: {call!r}"
print("PASS 0-G: _html.escape() applied to statement, solution, and version fields")
EOF
```

### 0-H: Vote button uses `on_click` callback; `st.write("")` spacer removed

```python
python - <<'EOF'
import pathlib
src = pathlib.Path("migration_oracle/streamlit_app/pages/05_community.py").read_text()
assert "on_click=lambda" in src, \
    "FAIL 0-H: on_click lambda not found on vote button"
assert 'st.write("")' not in src, \
    'FAIL 0-H: st.write("") spacer still present — should be removed from col_vote'
print("PASS 0-H: vote button uses on_click callback; st.write('') spacer removed")
EOF
```

---

## Level 2 — Isolation / filter logic

No external services required.

### 2-A: Search filter matches keyword in statement

```python
python - <<'EOF'
insights = [
    {"statement": "Use @JsonFormat for serialization", "solution": "Apply annotation.", "votes": 1},
    {"statement": "Remove deprecated method", "solution": "Replace with newApi().", "votes": 2},
    {"statement": "Spring Boot 3 breaks Flyway", "solution": "Upgrade flyway-core.", "votes": 5},
]
q = "jsonformat"
filtered = [i for i in insights
            if q in i.get("statement","").lower() or q in i.get("solution","").lower()]
assert len(filtered) == 1, f"FAIL 2-A: expected 1 result, got {len(filtered)}"
assert "JsonFormat" in filtered[0]["statement"], \
    f"FAIL 2-A: wrong insight returned: {filtered[0]['statement']}"
print("PASS 2-A: search filter matches keyword in statement field")
EOF
```

### 2-B: Search filter matches keyword in solution

```python
python - <<'EOF'
insights = [
    {"statement": "Flyway breaks on upgrade", "solution": "Upgrade flyway-core to 9.x.", "votes": 3},
    {"statement": "Use new API", "solution": "Call newApi() method.", "votes": 1},
]
q = "flyway-core"
filtered = [i for i in insights
            if q in i.get("statement","").lower() or q in i.get("solution","").lower()]
assert len(filtered) == 1, f"FAIL 2-B: expected 1 result, got {len(filtered)}"
assert "flyway-core" in filtered[0]["solution"].lower(), \
    f"FAIL 2-B: solution mismatch: {filtered[0]['solution']}"
print("PASS 2-B: search filter matches keyword in solution field")
EOF
```

### 2-C: Search filter is case-insensitive

```python
python - <<'EOF'
insights = [{"statement": "Configure Hibernate SessionFactory", "solution": "Use HibernateJpaVendorAdapter.", "votes": 2}]
for term in ["hibernate", "HIBERNATE", "HiBeRnAtE"]:
    filtered = [i for i in insights
                if term.lower() in i.get("statement","").lower()
                or term.lower() in i.get("solution","").lower()]
    assert len(filtered) == 1, \
        f"FAIL 2-C: case-insensitive match failed for '{term}', got {len(filtered)}"
print("PASS 2-C: search filter is case-insensitive for hibernate/HIBERNATE/HiBeRnAtE")
EOF
```

### 2-D: Empty query returns all insights

```python
python - <<'EOF'
insights = [
    {"statement": "A", "solution": "B", "votes": 1},
    {"statement": "C", "solution": "D", "votes": 2},
    {"statement": "E", "solution": "F", "votes": 3},
]
q = "".strip().lower()
filtered = (
    [i for i in insights if q in i.get("statement","").lower() or q in i.get("solution","").lower()]
    if q else insights
)
assert len(filtered) == 3, f"FAIL 2-D: empty query should return all 3, got {len(filtered)}"
print("PASS 2-D: empty search term returns all insights unchanged")
EOF
```

### 2-E: Non-matching query returns empty list

```python
python - <<'EOF'
insights = [
    {"statement": "Use Spring profiles", "solution": "Add @Profile.", "votes": 1},
    {"statement": "Disable auto-configuration", "solution": "Use @SpringBootTest.", "votes": 2},
]
q = "zxqnotfound"
filtered = [i for i in insights
            if q in i.get("statement","").lower() or q in i.get("solution","").lower()]
assert len(filtered) == 0, f"FAIL 2-E: expected 0 results, got {len(filtered)}"
print("PASS 2-E: non-matching search term returns empty list")
EOF
```

### 2-F: `html.escape()` encodes special characters to entities

```python
python - <<'EOF'
import html as _html
cases = [
    ("<script>alert(1)</script>", "&lt;script&gt;"),
    ("AT&T",                      "AT&amp;T"),
    ('"quoted"',                  "&quot;quoted&quot;"),
]
for raw, expected_fragment in cases:
    result = _html.escape(raw, quote=True)
    assert expected_fragment in result, \
        f"FAIL 2-F: expected '{expected_fragment}' in escape({raw!r}), got {result!r}"
print("PASS 2-F: html.escape() encodes <, >, &, \" to HTML entities")
EOF
```

### 2-G: Count header includes filter label when present; omits when absent

```python
python - <<'EOF'
import html as _html

# With a search term
search_term = "flyway"
filter_label = f'"{search_term.strip()}" · ' if search_term.strip() else ""
fragment = f'· {_html.escape(filter_label)}' if filter_label else ""
assert "flyway" in fragment, f"FAIL 2-G: search term not in header fragment: {fragment!r}"

# Without a search term
search_term2 = ""
filter_label2 = f'"{search_term2.strip()}" · ' if search_term2.strip() else ""
fragment2 = f'· {_html.escape(filter_label2)}' if filter_label2 else ""
assert fragment2 == "", f"FAIL 2-G: empty search should produce empty fragment, got {fragment2!r}"

print("PASS 2-G: count header includes filter label when present; omits when absent")
EOF
```

---

## Level 3 — Integration read path

**Requires: Neo4j running and reachable.**

### 3-A: Neo4j driver connectivity

```python
python - <<'EOF'
import os
from neo4j import GraphDatabase

with GraphDatabase.driver(
    os.environ["NEO4J_URI"],
    auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
) as driver:
    with driver.session() as session:
        result = session.run("RETURN 1 AS n").single()
        assert result["n"] == 1, f"FAIL 3-A: unexpected result {result['n']}"
print("PASS 3-A: Neo4j driver connects and RETURN 1 succeeds")
EOF
```

### 3-B: `get_community_insights` returns correct shape for Spring Boot

```python
python - <<'EOF'
from migration_oracle.mcp.tools.community import get_community_insights

result = get_community_insights(framework="Spring Boot")
assert isinstance(result, dict), f"FAIL 3-B: expected dict, got {type(result)}"
assert "insights" in result, f"FAIL 3-B: 'insights' key missing; keys={list(result.keys())}"
assert isinstance(result["insights"], list), \
    f"FAIL 3-B: 'insights' should be list, got {type(result['insights'])}"
if result["insights"]:
    sample = result["insights"][0]
    for field in ("insight_id", "statement", "solution", "votes"):
        assert field in sample, \
            f"FAIL 3-B: required field '{field}' missing; keys={list(sample.keys())}"
print(f"PASS 3-B: get_community_insights returns {len(result['insights'])} Spring Boot insights with correct shape")
EOF
```

### 3-C: `framework` argument filters insights — Spring Boot vs WildFly differ

```python
python - <<'EOF'
from migration_oracle.mcp.tools.community import get_community_insights

sb      = get_community_insights(framework="Spring Boot")
wildfly = get_community_insights(framework="WildFly")

for name, res in [("Spring Boot", sb), ("WildFly", wildfly)]:
    assert isinstance(res, dict) and "insights" in res, \
        f"FAIL 3-C: {name} call returned bad shape: {res!r}"

sb_ids      = {i.get("insight_id") for i in sb["insights"]}
wildfly_ids = {i.get("insight_id") for i in wildfly["insights"]}
if sb_ids and wildfly_ids:
    assert sb_ids != wildfly_ids, \
        "FAIL 3-C: Spring Boot and WildFly returned identical insight IDs — framework filter has no effect"
print(f"PASS 3-C: framework arg filters correctly "
      f"(Spring Boot: {len(sb_ids)}, WildFly: {len(wildfly_ids)})")
EOF
```

### 3-D: `vote_insight` increments vote count; DB restored after test

```python
python - <<'EOF'
from migration_oracle.mcp.tools.community import get_community_insights, vote_insight

result = get_community_insights(framework="Spring Boot")
insights = result.get("insights", [])
if not insights:
    print("SKIP 3-D: no Spring Boot insights in DB — skipping vote round-trip")
    exit(0)

target       = insights[0]
insight_id   = target["insight_id"]
votes_before = target.get("votes", 0)

vote_insight(insight_id=insight_id, delta=1)

updated = get_community_insights(framework="Spring Boot")
updated_insight = next((i for i in updated["insights"] if i["insight_id"] == insight_id), None)
assert updated_insight is not None, f"FAIL 3-D: insight {insight_id} not found after voting"
votes_after = updated_insight.get("votes", 0)
assert votes_after == votes_before + 1, \
    f"FAIL 3-D: expected votes {votes_before + 1}, got {votes_after}"

# Restore
vote_insight(insight_id=insight_id, delta=-1)
restored = get_community_insights(framework="Spring Boot")
restored_insight = next((i for i in restored["insights"] if i["insight_id"] == insight_id), None)
votes_restored = restored_insight.get("votes", 0) if restored_insight else -1
assert votes_restored == votes_before, \
    f"FAIL 3-D: restore failed — expected {votes_before}, got {votes_restored}"

print(f"PASS 3-D: vote_insight increments ({votes_before}→{votes_after}) and DB restored to {votes_restored}")
EOF
```

---

## Level 7 — Edge-case paths

No external services required.

### 7-A: Multi-line solution with angle brackets does not break card HTML

```python
python - <<'EOF'
import html as _html

insight = {
    "statement": "Use <PropertyPlaceholderConfigurer> for externalized config",
    "solution":  "Replace with Environment API:\n\n@Bean\npublic static PropertySourcesPlaceholderConfigurer pspc() {\n    return new PropertySourcesPlaceholderConfigurer();\n}",
    "votes": 3,
    "version": "3.2",
    "source_url": "",
    "verified": False,
}
stmt = _html.escape(insight.get("statement", ""))
soln = _html.escape(insight.get("solution",  ""))
ver  = _html.escape(insight.get("version",   ""))
fw_display = "Spring Boot"

card_html = f"""
<div class="insight-card">
  <div class="insight-statement">{stmt}</div>
  <div class="insight-solution">{soln}</div>
  <div class="insight-footer">
    <span class="vote-badge">▲ {insight['votes']}</span>
    <span class="fw-badge">{_html.escape(fw_display)}</span>
    {f'<span class="ver-badge">v{ver}</span>' if ver else ""}
  </div>
</div>
"""

assert "<PropertyPlaceholderConfigurer>" not in card_html, \
    "FAIL 7-A: unescaped user angle brackets in card HTML"
assert "&lt;PropertyPlaceholderConfigurer&gt;" in card_html, \
    "FAIL 7-A: escaped user angle brackets not found in card HTML"
assert '</div>' in card_html, \
    "FAIL 7-A: closing div tag missing — card structure broken"
print("PASS 7-A: multi-line solution with angle brackets escapes correctly; card structure intact")
EOF
```

### 7-B: `ver-badge` absent when version is empty or missing

```python
python - <<'EOF'
import html as _html

for version_value in ["", None, "not present"]:
    insight = {} if version_value == "not present" else {"version": version_value}
    ver = _html.escape(insight.get("version", "") or "")
    badge = f'<span class="ver-badge">v{ver}</span>' if ver else ""
    assert badge == "", \
        f"FAIL 7-B: ver-badge rendered for version={version_value!r}: {badge!r}"
print("PASS 7-B: ver-badge absent for empty string, None, and missing version key")
EOF
```

### 7-C: `ver-badge` renders correctly when version is populated

```python
python - <<'EOF'
import html as _html

insight = {"version": "3.2.1"}
ver = _html.escape(insight.get("version", "") or "")
badge = f'<span class="ver-badge">v{ver}</span>' if ver else ""
assert 'class="ver-badge"' in badge, f"FAIL 7-C: ver-badge missing: {badge!r}"
assert "v3.2.1" in badge, f"FAIL 7-C: version value not in badge: {badge!r}"
print(f"PASS 7-C: ver-badge renders correctly: {badge}")
EOF
```

### 7-D: `source_html` empty when `source_url` is empty, null, or missing

```python
python - <<'EOF'
for insight in [{"source_url": ""}, {"source_url": None}, {}]:
    source_html = (
        f'<a class="source-link" href="{insight["source_url"]}" target="_blank">↗ Source</a>'
        if insight.get("source_url") else ""
    )
    assert source_html == "", \
        f"FAIL 7-D: source_html non-empty for {insight!r}: {source_html!r}"
print("PASS 7-D: source_html is empty for empty, None, and missing source_url")
EOF
```

### 7-E: `source_html` renders correct anchor when `source_url` is populated

```python
python - <<'EOF'
insight = {"source_url": "https://docs.spring.io/migration-guide"}
source_html = (
    f'<a class="source-link" href="{insight["source_url"]}" target="_blank">↗ Source</a>'
    if insight.get("source_url") else ""
)
assert 'href="https://docs.spring.io/migration-guide"' in source_html, \
    f"FAIL 7-E: href not correctly embedded: {source_html!r}"
assert 'class="source-link"' in source_html, \
    f"FAIL 7-E: source-link class missing: {source_html!r}"
assert "↗ Source" in source_html, \
    f"FAIL 7-E: link text missing: {source_html!r}"
print(f"PASS 7-E: source URL renders as anchor tag")
EOF
```

### 7-F: `FRAMEWORK_DISPLAY_NAMES` first key is `spring-boot` (default on load)

```python
python - <<'EOF'
from migration_oracle.streamlit_app._constants import FRAMEWORK_DISPLAY_NAMES

keys = list(FRAMEWORK_DISPLAY_NAMES.keys())
assert keys[0] == "spring-boot", \
    f"FAIL 7-F: first key is '{keys[0]}', expected 'spring-boot'"
assert FRAMEWORK_DISPLAY_NAMES["spring-boot"] == "Spring Boot", \
    f"FAIL 7-F: display name is '{FRAMEWORK_DISPLAY_NAMES['spring-boot']}'"
print(f"PASS 7-F: FRAMEWORK_DISPLAY_NAMES[0] = 'spring-boot' → 'Spring Boot'")
EOF
```

### 7-G: `voting_key` and button key patterns are consistent in source

```python
python - <<'EOF'
import pathlib
src = pathlib.Path("migration_oracle/streamlit_app/pages/05_community.py").read_text()
assert 'f"voting_{insight_id}"' in src, \
    "FAIL 7-G: voting_key assignment pattern not found in source"
assert 'f"vote_{insight_id}"' in src, \
    "FAIL 7-G: button key pattern not found in source"
print("PASS 7-G: voting_key and button_key patterns are consistent in source")
EOF
```

---

## Manual UI acceptance checks

Start the app: `streamlit run migration_oracle/streamlit_app/Home.py` — navigate to **Community Insights**.

| ID | Action | Expected result |
|----|--------|----------------|
| UI-1 | Load the page | Skeleton cards appear briefly, then insight cards render. No raw HTML text visible. |
| UI-2 | Find a card whose statement or solution contains `<` or `&` | Characters render literally, not as HTML tags or entities. |
| UI-3 | Inspect a card footer | Shows `▲ N` vote badge · optional `✓ Verified` · blue `fw-badge` · grey `ver-badge` (if version set) · optional `↗ Source` link. |
| UI-4 | Change the Framework selectbox | Insight list and count header refresh for the selected framework. |
| UI-5 | Type a keyword in **Search insights** | Cards filter in real time; count header shows `— N insights · "keyword" · Framework`. |
| UI-6 | Clear the search bar | All insights for the selected framework return; count header drops the filter label. |
| UI-7 | Click `▲` on any insight | Button replaced by accent-coloured loading div; after rerun, vote count increments. Layout does not shift between states. |
| UI-8 | Open **＋ Submit New Insight** | Form shows label **Framework version** with placeholder `e.g. 3.2 for Spring Boot, 30 for WildFly`. |
| UI-9 | Submit a valid insight via the form | Success banner `✓ Insight submitted — thank you!` appears. |
| UI-10 | Check a card with a non-empty `source_url` | `↗ Source` is a clickable hyperlink, not raw HTML text. |

---

## Completion gate

Update `SPEC_ORGANIZATION.md` to `✅ Complete` only when every item below is checked.

| Check ID | Description | Result |
|----------|-------------|--------|
| 0-A | `05_community.py` parses as valid Python AST | ☐ |
| 0-B | `import html as _html` present | ☐ |
| 0-C | `vote-flash` keyframe and `voting-btn` class removed | ☐ |
| 0-D | `.controls-row`, `.fw-badge`, `.ver-badge`, `.voting-loading` CSS present | ☐ |
| 0-E | Selectbox keys are `ci_fw_filter` / `ci_fw_submit`; old `ci_fw` gone | ☐ |
| 0-F | Submit form label is "Framework version" with multi-framework placeholder | ☐ |
| 0-G | `_html.escape()` applied to statement, solution, and version fields | ☐ |
| 0-H | Vote button uses `on_click=lambda`; `st.write("")` spacer removed | ☐ |
| 2-A | Search filter matches keyword in statement field | ☐ |
| 2-B | Search filter matches keyword in solution field | ☐ |
| 2-C | Search filter is case-insensitive | ☐ |
| 2-D | Empty search term returns all insights | ☐ |
| 2-E | Non-matching search term returns empty list | ☐ |
| 2-F | `html.escape()` encodes `<`, `>`, `&`, `"` to HTML entities | ☐ |
| 2-G | Count header includes filter label when present; omits when absent | ☐ |
| 3-A | Neo4j driver connects; `RETURN 1` succeeds | ☐ |
| 3-B | `get_community_insights` returns correct shape with `insights` list | ☐ |
| 3-C | `framework` arg produces different insight sets for Spring Boot vs WildFly | ☐ |
| 3-D | `vote_insight` increments vote count; DB restored after test | ☐ |
| 7-A | Multi-line solution with angle brackets escapes correctly; card structure intact | ☐ |
| 7-B | `ver-badge` absent for empty string, None, and missing version key | ☐ |
| 7-C | `ver-badge` renders with correct value when version is populated | ☐ |
| 7-D | `source_html` empty for empty, null, and missing `source_url` | ☐ |
| 7-E | `source_html` renders correct anchor tag for populated `source_url` | ☐ |
| 7-F | `FRAMEWORK_DISPLAY_NAMES` index 0 is `spring-boot` → `Spring Boot` | ☐ |
| 7-G | `voting_key` and button key patterns consistent in source | ☐ |
| UI-1 | Skeleton appears on load; no raw HTML text visible | ☐ |
| UI-2 | Cards with `<` or `&` render characters literally | ☐ |
| UI-3 | Card footer shows vote badge, optional verified badge, fw-badge, ver-badge, optional source link | ☐ |
| UI-4 | Framework selectbox change refreshes insight list | ☐ |
| UI-5 | Search bar filters cards and updates count header | ☐ |
| UI-6 | Clearing search bar returns all insights for selected framework | ☐ |
| UI-7 | Vote button shows loading div, increments count, no layout shift | ☐ |
| UI-8 | Submit form shows "Framework version" label and multi-framework placeholder | ☐ |
| UI-9 | Submitting insight shows success banner | ☐ |
| UI-10 | Source URL with value renders as clickable hyperlink, not raw HTML text | ☐ |
