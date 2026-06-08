# Quickstart: Streamlit Operator UI (006-streamlit-ui)

**Date**: 2026-06-08

---

## Prerequisites

### Environment Variables

The following must be set in the shell before starting the app:

```bash
export NEO4J_URI=bolt://localhost:7687      # required
export NEO4J_USERNAME=neo4j                 # required (default: "neo4j")
export NEO4J_PASSWORD=yourpassword          # required
```

> **Neo4j unreachable at startup**: `app.py` imports nothing from `migration_oracle`, so the app
> starts successfully even if Neo4j is down. Tool function imports are deferred to individual page
> scripts, which Streamlit loads lazily on first navigation. When an operator visits a page and the
> first tool call fails (e.g. `ServiceUnavailable`), the page's `try/except` shows `st.error(...)`.
> There is no startup health check — fix Neo4j connectivity and reload the page.

Optional (for vector search and embedding features):

```bash
export SENTENCE_TRANSFORMERS_MODEL=all-MiniLM-L6-v2   # defaults to this if unset
export POPULATE_MIGRATION_EMBEDDINGS=true              # set to enable vector search
```

### Python Environment

`streamlit>=1.35` is already listed in `[project.dependencies]` — no manual install needed.

```bash
# Install all dependencies (including streamlit):
uv sync

# Or with pip:
pip install -e .
```

---

## Running the App

```bash
streamlit run migration_oracle/streamlit_app/app.py
```

Streamlit will print a local URL (default: http://localhost:8501). Open it in a browser.

---

## Verifying Each Page

### Page 1 — Pipeline Trigger

1. Select a framework from the dropdown (populated from `FRAMEWORK_DISPLAY_NAMES`).
2. Enter any version strings (e.g. `2.7.x` → `3.2`).
3. Check `--dry-run`.
4. Click Submit.
5. Verify: output lines stream into the output area; exit code shown green (0) or red (non-zero).

### Page 2 — Run Browser

1. Navigate to "Run Browser".
2. Verify: if runs exist, a selectbox appears labelled `"framework → to_version"`.
3. Select a run and click each tab (Raw MD, Filtered MD, Entities JSON).
4. Verify: content renders in each tab, or an inline error message appears in tabs where the artifact is missing.
5. If no runs exist: verify `st.info("No pipeline runs found")` is shown.

### Page 3 — Rule Explorer

1. Navigate to "Rule Explorer".
2. Type a query (e.g. `"removed API"`).
3. Click Search.
4. Verify: result cards appear showing statement excerpt, `rule_type` badge, `source_url` link, and `action_step`.
5. Try a query with no matches: verify `st.info("No rules found for this query")`.

### Page 4 — Context Dashboard

1. Navigate to "Context Dashboard".
2. Fill in a project ID, from/to versions, and framework.
3. Click "Load / Create".
4. Verify: context status badge, completed count, and skipped count appear.
5. If pending steps exist: verify the table renders with summary, effort, automatable, scope, severity columns.
6. Click "Mark Complete" on a step: verify the step disappears from the table after refresh.
7. Navigate away and back: verify the context is still shown without re-entering the form.

### Page 5 — Community

1. Navigate to "Community".
2. Verify: insight cards render with statement, solution, votes, verified badge.
3. Click "Vote Up" on an insight: verify the vote count increments.
4. Open "Submit New Insight", fill all fields, submit: verify success confirmation appears.
5. Submit the same insight again: verify `st.error("Duplicate detected")` appears.

---

## Triggering a Dry-Run Pipeline from the UI

1. Open "Pipeline Trigger".
2. Select `Spring Boot` from the framework dropdown.
3. Enter `2.7.x` as the from-version and `3.2` as the to-version.
4. Check the `--dry-run` checkbox.
5. Click Submit.
6. Expected: the pipeline subprocess runs with `--dry-run`, output streams line-by-line, exit code 0 shown in green when complete.

The underlying command executed is:
```
sys.executable -m migration_oracle.cli --framework spring-boot 2.7.x 3.2 --dry-run
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ServiceUnavailable` on any page | Neo4j not running or wrong URI | Start Neo4j; verify `NEO4J_URI` |
| `ModuleNotFoundError: migration_oracle` | Package not installed | Run `uv sync` or `pip install -e .` |
| Rule Explorer returns 0 results | Embeddings not populated | Set `POPULATE_MIGRATION_EMBEDDINGS=true` and re-run pipeline |
| Pipeline Trigger shows no frameworks | `FRAMEWORK_DISPLAY_NAMES` import failed | Check `migration_oracle.pipeline.extractors` is importable |
| Vote count does not update | `delta` param mismatch | Verify call uses `delta=1`, not `direction="up"` |
