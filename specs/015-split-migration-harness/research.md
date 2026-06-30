# Research: Split Migration Harness

## Session/Tool-Gating Mechanism

**Decision**: Implement a per-command tool allowlist enforced at the MCP server registration or invocation layer.

**Rationale**: The `preview` stage requires a strict zero-mutation guarantee. To satisfy this, the MCP server must be able to restrict which tools are exposed or executable based on the active session context. A simple and robust approach is to define an allowlist of tools for each of the six commands (`plan`, `gap-check`, `clarify`, `preview`, `execute`, `feedback`). When a session is initialized for a specific command, the MCP server only registers or allows invocation of the tools in that command's allowlist. For `preview`, this list will only contain `get_pending_steps` and `get_migration_contexts`.

**Alternatives considered**:
- *Role-based access control (RBAC)*: Assigning roles to sessions and checking permissions inside each tool. Rejected because it requires modifying every tool's implementation and is more complex than a simple allowlist.
- *Separate MCP server endpoints*: Running different MCP servers for different stages. Rejected because it complicates deployment and client configuration.

## Parallelism and Concurrency

**Decision**: Explicitly forbid parallel execution of `gap-check`, `clarify`, and `preview` reads against a concurrently running `execute` session for the same `context_id`.

**Rationale**: Shared graph writes from `execute` (e.g., updating step outcomes) could race with `clarify`'s exclusion writes or cause `gap-check`/`preview` to read inconsistent state. There is no `[P]` marking across these boundaries for the same `context_id`.

**Alternatives considered**:
- *Graph-level locking*: Using Neo4j locks to manage concurrent access. Rejected because it adds significant complexity and potential for deadlocks, whereas the session boundaries naturally enforce sequential operation for a single migration context.