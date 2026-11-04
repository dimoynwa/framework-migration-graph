# Feature Specification: Migration Skill Install Remediation

**Feature Branch**: `020-migration-skill-install-remediation`

**Created**: 2026-07-27

**Status**: Draft

**Input**: Review findings from `install_migration_skill`: the installer, server prompts, stage gating, and docs drifted after the optional research stage and split skill bundles were added. Full-mode installs omit the research skill, installed scanner instructions point to source-tree paths that are absent in consumer repos, docs still point to removed skill resources and tools, tests protect the stale five-bundle layout, and invalid install targets silently resolve to Claude Code.

## User Scenarios & Testing

### User Story 1 - Install the Complete Full Migration Harness (Priority: P1)

As a migration operator using full mode, I want `install_migration_skill()` to install every stage bundle in the documented six-stage workflow so that `/migration-research` is available alongside plan, gap-check, clarify, preview, and execute.

**Why this priority**: The canonical migration model and operator guide now describe `/migration-research` as an optional first stage. If it is not installed, operators cannot run the documented workflow.

**Independent Test**: Set `MIGRATION_MODE=full`, call `install_migration_skill(target="cursor", target_dir=<tmp>)`, and verify six top-level bundles exist, including `framework-migration-research/SKILL.md`.

**Acceptance Scenarios**:

1. **Given** full mode, **When** the installer runs, **Then** `installed_skills` contains `framework-migration-research`, `framework-migration-plan`, `framework-migration-gap-check`, `framework-migration-clarify`, `framework-migration-preview`, and `framework-migration-execute`.
2. **Given** full mode, **When** server resources are listed, **Then** `skill://framework-migration-research/main` is registered and resolves to `migration_oracle/mcp/skills/framework-migration/research.md`.
3. **Given** `start_migration(..., stage="research")`, **When** the prompt is rendered, **Then** it instructs the agent to load `skill://framework-migration-research/main` and identifies research as the active stage.
4. **Given** `MCP_ACTIVE_STAGE=research`, **When** stage gating is applied, **Then** the same knowledge-read tools required by `research.md` frontmatter remain available.

---

### User Story 2 - Installed Scanner Reference Works in Consumer Repos (Priority: P1)

As a migration operator in a consumer repository, I want the installed scan instructions to point to files that were actually installed so that the plan and research stages can run the canonical extractor without depending on the Migration Oracle source checkout layout.

**Why this priority**: `framework-migration-plan/references/scanning.md` currently tells agents to run `migration_oracle/mcp/skills/framework-migration/framework_scanner.py`, but that file is not copied into installed skill bundles. This breaks the primary scanner path outside the source repo.

**Independent Test**: Install full-mode bundles into a temp skills directory and verify the scanner script exists under an installed bundle reference path. Then assert `references/scanning.md` contains the installed relative command, not the source-tree command.

**Acceptance Scenarios**:

1. **Given** the plan bundle is installed, **When** its `references/` folder is inspected, **Then** it contains `framework_scanner.py`.
2. **Given** the research bundle is installed, **When** it needs scanning instructions, **Then** it either has its own installed scanner reference files or points to an installed sibling bundle path that exists after full-mode install.
3. **Given** an installed `references/scanning.md`, **When** an agent follows the Python canonical extractor instructions, **Then** the command uses an installed relative path such as `references/framework_scanner.py`, not `migration_oracle/mcp/skills/...`.
4. **Given** lite mode is installed, **When** installed references are inspected, **Then** no full-mode scanner dependency is introduced unless the lite skill explicitly uses it.

---

### User Story 3 - Public Documentation Matches Runtime Skill Resources (Priority: P2)

As an operator reading the docs, I want all installation, prompt, and skill resource references to match the current split-bundle, file-state harness so that I am not sent to removed four-loop resources or deleted context tools.

**Why this priority**: Stale docs are actively misleading: `docs/04-operator-guides/usage.md` still mentions `skill://framework-migration/main`, four resources, four loops, and removed context tools.

**Independent Test**: Search the canonical docs for removed resource URIs and removed graph-session tools. No active operator guide or MCP contract doc should instruct use of deleted resources/tools.

**Acceptance Scenarios**:

1. **Given** the operator usage guide, **When** the skill resources section is read, **Then** it lists the split resources actually registered by the server, including research.
2. **Given** prompt documentation, **When** `start_migration` and `resume_migration` are described, **Then** they describe the file-state stage workflow and `ps-migration/` folder state, not `MigrationContext`.
3. **Given** install documentation, **When** full-mode bundles are listed, **Then** the list has six top-level bundles and matches `MODE_BUNDLES["full"]`.
4. **Given** docs mention removed context tools such as `create_migration_context`, `get_pending_steps`, `update_step_status`, or `close_migration_context`, **Then** those mentions are historical-only or explicitly marked obsolete; active instructions must not require them.

---

### User Story 4 - Installer Rejects Invalid Targets (Priority: P3)

As a caller of `install_migration_skill`, I want invalid `target` values to fail clearly so that typos do not silently install Claude Code bundles.

**Why this priority**: Current behavior maps any target other than `auto` or `cursor` to `claude-code`, hiding mistakes.

**Independent Test**: Call `install_migration_skill(target="curser", target_dir=<tmp>)` and assert it raises `ValueError` and writes no files.

**Acceptance Scenarios**:

1. **Given** `target` is one of `auto`, `cursor`, or `claude-code`, **When** the installer runs, **Then** behavior remains unchanged except for the remediations above.
2. **Given** any other `target`, **When** the installer is called, **Then** it raises `ValueError` naming the valid values and does not write partial files.

## Requirements

### Functional Requirements

- **FR-001**: Full-mode `MODE_BUNDLES` MUST include `framework-migration-research` as the first bundle in stage order.
- **FR-002**: `SKILL_BUNDLES` MUST define `framework-migration-research` and copy `framework-migration/research.md` to `framework-migration-research/SKILL.md`.
- **FR-003**: Research-stage installed references MUST be sufficient for the instructions in `research.md` to resolve after installation. At minimum, references to scanning and version-map material must point to installed files.
- **FR-004**: The plan bundle MUST include `framework_scanner.py` in its installed `references/` directory when `scanning.md` instructs users to run it.
- **FR-005**: `scanning.md` MUST document an installed-bundle command for the canonical extractor and MUST NOT present the Migration Oracle source-tree path as the command operators should run from consumer repos.
- **FR-006**: The server MUST register `skill://framework-migration-research/main`.
- **FR-007**: `start_migration` and `resume_migration` MUST accept `stage="research"` and map it to `skill://framework-migration-research/main`.
- **FR-008**: `migration_workflow_prompt` and prompt docs MUST describe the six-stage sequence with optional research.
- **FR-009**: `MCP_ACTIVE_STAGE=research` MUST be valid and expose the tool allowlist required by `framework-migration-research` frontmatter.
- **FR-010**: The frontmatter tool list for `framework-migration-research` MUST match its stage allowlist.
- **FR-011**: Full-mode installer tests MUST expect six top-level bundles and fail if the research bundle is omitted.
- **FR-012**: Installer/reference relocation tests MUST assert the installed scanner script and scanner instructions are coherent.
- **FR-013**: Prompt/server resource tests MUST assert the research stage URI is registered and routable.
- **FR-014**: Stage-gating tests MUST cover `MCP_ACTIVE_STAGE=research`.
- **FR-015**: `install_migration_skill` MUST validate `target` against `{"auto", "cursor", "claude-code"}` before resolving install paths.
- **FR-016**: Invalid-target validation MUST occur before file copy and MUST leave no partial install output.
- **FR-017**: Canonical docs under `docs/03-mcp-and-agent-harness/` and `docs/04-operator-guides/` MUST match the split-bundle, six-stage runtime behavior.
- **FR-018**: Active docs MUST NOT instruct use of removed four-loop context tools except in explicitly historical sections.
- **FR-019**: Root redirect docs (`INSTRUCTION.md`, `USAGE.md`) may remain redirects, but their targets MUST be current.
- **FR-020**: Lite-mode bundle behavior MUST remain unchanged unless tests prove a shared helper needs a harmless validation update.

### Non-Functional Requirements

- **NFR-001**: The fix MUST be narrowly scoped to installation, skill-resource routing, scanner reference relocation, docs, and tests.
- **NFR-002**: The fix MUST NOT change knowledge-query tool contracts, graph schema, migration artifact schemas, or the behavior of plan/render classification.
- **NFR-003**: The fix MUST preserve project-local install behavior introduced by `019-project-local-skill-install`.
- **NFR-004**: Installed skill files should remain readable standalone in a consumer repo.

## Key Entities

- **Full-Mode Bundle Set**: The ordered list of installable full harness skill bundles. It must be six bundles: research, plan, gap-check, clarify, preview, execute.
- **Installed Reference File**: A file copied under a bundle `references/` directory and referenced by installed `SKILL.md` prose.
- **Research Stage Resource**: The MCP resource URI `skill://framework-migration-research/main`.
- **Target IDE**: The validated destination family for installation: `auto`, `cursor`, or `claude-code`.

## Success Criteria

- **SC-001**: Full-mode install writes all six expected bundles and returns all six bundle names.
- **SC-002**: An installed full-mode plan bundle contains a runnable scanner script reference under `framework-migration-plan/references/`.
- **SC-003**: `start_migration(..., stage="research")` and `MCP_ACTIVE_STAGE=research` both work without falling back to plan.
- **SC-004**: Docs no longer present active four-loop or `MigrationContext` instructions for the current harness.
- **SC-005**: `install_migration_skill(target="invalid", target_dir=<tmp>)` fails with `ValueError` and writes no files.
- **SC-006**: Existing lite-mode install tests continue to pass.

## Out of Scope

- Running a full SpecKit cycle for this remediation.
- Redesigning the migration research artifact schema.
- Changing MCP knowledge tool parameters or return shapes.
- Adding new graph nodes, relationships, or persisted session state.
- Reintroducing deleted context tools.
