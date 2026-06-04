# Quickstart: Pipeline Core

This guide explains how to run the pipeline-core module locally end-to-end.

## Environment Variables

Ensure the following environment variables are set:
- `NEO4J_URI`: Connection string for Neo4j/Memgraph.
- `MODEL_PROVIDER`: Defines the LangChain provider to initialize (e.g., `openai`, `anthropic`).
- `MODEL_ID` (or Bedrock equivalent): The specific model to use for the LLM calls.
- `GITHUB_TOKEN` (Optional): Required if the extractor needs to fetch data from GitHub.

## Running a Dry-Run

To verify the artifact output without modifying the graph, run the pipeline with the `--dry-run` flag using a stub extractor:

```bash
export-extract-populate-framework --framework stub_framework 1.0.0 2.0.0 --dry-run
```

Expected output artifacts in `runs/`:
- `runs/raw/stub_framework-1.0.0-to-2.0.0-changes.md`
- `runs/nodes/stub_framework-1.0.0-to-2.0.0-changes_filtered.md`
- `runs/json/stub_framework-1.0.0-to-2.0.0-entities.json`

## Verifying Graph Population

After running without `--dry-run`, verify the `Version` node in your graph database:

```cypher
MATCH (v:Version {framework: "stub_framework", version: "2.0.0"})
RETURN v.rawMdPath, v.filteredMdPath, v.entitiesJsonPath
```

Ensure the three path properties are populated correctly.

## Re-running LLM Steps

To bypass the artifact cache and force the LLM steps to re-run:

```bash
export-extract-populate-framework --framework stub_framework 1.0.0 2.0.0 --force-llm
```

This ensures the filter and extraction LLM calls are executed again and overwrites existing artifacts.
