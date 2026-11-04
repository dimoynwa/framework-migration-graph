# Migration Model

The main model for migrations is a file-backed, skill-driven, six-stage workflow.

Migration progress lives in version-controlled markdown artifacts in the consumer repository, under:

```text
ps-migration/{framework}-{from}-to-{to}/
```

The knowledge graph is the source of migration knowledge. The markdown artifacts are the source of migration state. Neo4j/Memgraph is read-only for per-migration progress.

## State Model

Each migration folder contains:

| File | Role |
|---|---|
| `research.md` | Optional checkpoint of graph and codebase research before planning |
| `plan.md` | Strategy, rule ledger, dependency table, provenance, and drift rules |
| `tasks.md` | Ordered task queue, relevance index, inline task status, and sign-offs |
| `verification.md` | Completion gate and runnable verification levels |

Resume means re-reading this folder and checking `git status`. There is no graph session state to resume.

## Stage Model

The canonical stage sequence is:

```text
/migration-research (optional)
  -> /migration-plan
  -> /migration-gap-check
  -> /migration-clarify (optional)
  -> /migration-preview (optional)
  -> /migration-execute
```

The stages are implemented as installable skill bundles from `migration_oracle/mcp/skills/`. The runtime skill files are the implementation source of truth; this docs area explains their operating model.

## Source-of-Truth Split

| Concern | Source of truth |
|---|---|
| Framework migration facts | Knowledge graph |
| Per-project migration progress | `ps-migration/.../*.md` files |
| Stage behavior | Runtime skills in `migration_oracle/mcp/skills/` |
| Operator workflow | [Operator guide](../04-operator-guides/instruction.md) |
| File schemas | [Migration File-State Design](migration-file-state-design.md) |
| Tool contracts | [MCP Tools, Skills, and Prompts](mcp-tools-skills-prompts.md) |

## Why This Is the Main Model

Earlier graph-session state relied on `MigrationContext`, `STEP_OUTCOME`, and context mutation tools. The current model moved progress out of the graph and into repository-owned markdown files so migrations are reviewable, restartable, diffable, and agent-independent.

The graph remains essential, but it is used as a knowledge base, not a migration progress database.
