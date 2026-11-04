<!-- OKF DOCS START -->
# Documentation navigation

Project documentation follows the OKF knowledge-bundle layout under `docs/`.

Before searching scattered Markdown files, start with:

- `docs/index.md` - top-level OKF index and knowledge-area map.
- `docs/03-mcp-and-agent-harness/migration-model.md` - canonical migration model: file-backed, skill-driven, graph-informed.
- `docs/03-mcp-and-agent-harness/index.md` - MCP tools, migration harness, file-state design, and rendering behavior.
- `docs/07-agent-skills/index.md` - skill-bundle documentation and project-local skill references.
- `docs/04-operator-guides/index.md` - setup, usage, and operator workflow.
- `docs/06-speckit-runbooks/index.md` - historical SpecKit runbook snapshots.

Search guidance:

- For "how migrations work", "main model", "state", "workflow", or "SKILLS approach", read `docs/03-mcp-and-agent-harness/migration-model.md` first.
- For runtime skill behavior, treat `migration_oracle/mcp/skills/` as implementation source of truth and `docs/07-agent-skills/` as explanatory documentation.
- For graph schema questions, read `docs/01-foundation/graph-schema.md`.
- For MCP tool contracts, read `docs/03-mcp-and-agent-harness/mcp-tools-skills-prompts.md`.
- For extraction/pipeline questions, read `docs/02-extraction-pipeline/index.md`.
- Old root-level or flat docs paths may be redirect stubs after the OKF refactor; follow their links to the canonical location before drawing conclusions.
<!-- OKF DOCS END -->

<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan
at specs/018-migration-research-stage/plan.md
<!-- SPECKIT END -->
