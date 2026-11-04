# Skill Bundle Architecture

Runtime migration skills live under `migration_oracle/mcp/skills/`.

This docs area explains the skill model; it is not the runtime source of truth. The installable skill files shipped by the MCP server remain canonical for stage behavior.

```text
migration_oracle/mcp/skills/
├── framework-migration/
├── migration-lite/
├── openrewrite/
└── templates/
```

The migration model itself is documented in [Migration Model](../03-mcp-and-agent-harness/migration-model.md).
