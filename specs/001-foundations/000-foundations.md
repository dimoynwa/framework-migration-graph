# Contracts — 000 Foundations

> Component boundary and delegation rules. Downstream specs must follow these or they
> break the contract and create circular dependencies.

---

## Import rules (strictly enforced)

```
config.py
  imports: stdlib only (os, typing)
  forbidden: anything from migration_oracle.*

models/entities.py
  imports: pydantic, typing, enum, stdlib
  forbidden: migration_oracle.config, migration_oracle.graph.*

models/graph.py
  imports: dataclasses, typing, stdlib
  forbidden: migration_oracle.config, migration_oracle.graph.*, pydantic

graph/driver.py
  imports: neo4j, migration_oracle.config
  forbidden: migration_oracle.models.*, migration_oracle.pipeline.*

graph/indexes.py
  imports: neo4j, logging, migration_oracle.config (for LOG_LEVEL only)
  forbidden: migration_oracle.models.*, migration_oracle.pipeline.*
```

The dependency graph is:
```
config.py  ←────────────────────────────────────────┐
    ↑                                                 │
models/entities.py    models/graph.py        graph/driver.py
        ↑                    ↑                        ↑
        └────────────────────┴────── graph/indexes.py ┘
                                              ↑
                                  (all downstream specs)
```

No module in `000-foundations` imports from `001-pipeline-core` or later specs.

---

## What downstream specs may and may not do

### MUST import from, not reimplement

| Downstream spec | Must import | Must NOT reimplement |
|---|---|---|
| `001-pipeline-core` | `models.entities.MigrationEntitiesBatch` | Pydantic schema |
| `001-pipeline-core` | `models.graph.sortable_version` | `major*1_000_000+...` formula |
| `001-pipeline-core` | `models.entities.SOURCE_SECTION_TO_RULE_TYPE` | `source_section` → `ruleType` map |
| `001-pipeline-core` | `graph.driver.write_session` | Driver singleton |
| `001-pipeline-core` | `config.*` | Any env var reading |
| `004-mcp-server` | `graph.driver.read_session` | Read session management |
| `004-mcp-server` | `graph.indexes.ensure_indexes` | Index startup DDL |
| `005-streamlit-ui` | `graph.driver.read_session` | Driver |
| All specs | `config.SSL_VERIFY` | TLS verification logic |

### Graph write access

`graph/driver.py` is the **only** module that creates `neo4j.Driver` objects. No other
module in any spec may call `neo4j.GraphDatabase.driver()` directly.

### Environment variables

`config.py` is the **only** module that reads `os.environ`. No other module in any spec
may call `os.environ.get()`, `os.getenv()`, or read from `.env` files directly.

### Index DDL

`graph/indexes.py` is the **only** module that issues `CREATE CONSTRAINT` or
`CREATE INDEX` Cypher. Pipeline code and MCP server code must not issue DDL.

---

## Error type ownership

| Error | Defined in | Used by |
|---|---|---|
| `ConfigurationError` | `config.py` | Any module that catches startup config failures |
| `DriverNotInitialisedError` | `graph/driver.py` | Tests; graceful shutdown handlers |

Other specs define their own errors. They must not re-define `ConfigurationError` or
`DriverNotInitialisedError`.

---

## Read vs write access

| Module | Graph access | Justification |
|---|---|---|
| `graph/indexes.py` | Write (DDL only) | One-time startup |
| `pipeline/populator.py` (spec 001) | Write | Pipeline is the only writer |
| `mcp/tools/*.py` (spec 004) | Read only | MCP server is read-only for all query tools |
| `mcp/tools/community.py` (spec 004) | Write | `submit_migration_insight`, `vote_insight`, `verify_insight` write community data |
| `mcp/tools/context.py` (spec 004) | Write | Context management tools write `MigrationContext` nodes |
| `streamlit_app/` (spec 005) | Read only (via MCP tools) | UI never touches the graph directly |
