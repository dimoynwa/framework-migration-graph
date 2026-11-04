# Feature Specification: Project-Local Skill Installation

**Feature Branch**: `019-project-local-skill-install`

**Created**: 2026-07-13

**Status**: Draft

**Prerequisite**: `015a-skill-bundle-split` ✅ Complete (bundle layout and install mechanism are stable; this spec changes only the default install destination)

**Input**: User description: "Change `install_migration_skill` so migration harness skill bundles are installed into the current consumer project (`.cursor/skills/` or `.claude/skills/`) instead of the agent's global skills directory (`~/.cursor/skills/` or `~/.claude/skills/`). Keeps per-project migration artifacts (`ps-migration/`) and per-project slash commands co-located in the same repository."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Install Skills Into the Open Project (Priority: P1)

As a migration operator working in a consumer repository, I want `install_migration_skill()` to write harness bundles into that project's `.cursor/skills/` (or `.claude/skills/`) directory by default, so that slash commands travel with the repo and I do not pollute my global agent environment.

**Why this priority**: This is the entire behavioural change — without a project-local default, operators must remember to pass `target_dir` manually on every new project.

**Independent Test**: Open a clean git repository in Cursor, call `install_migration_skill()` with default parameters, and verify bundles appear under `{repo}/.cursor/skills/` (not under `~/.cursor/skills/`).

**Acceptance Scenarios**:

1. **Given** a consumer repository opened as the MCP client's workspace and `target` is `cursor` or `auto`, **When** `install_migration_skill()` is called with no `target_dir`, **Then** skill bundles are written to `{project_root}/.cursor/skills/`.
2. **Given** the same repository and `target` is `claude-code`, **When** `install_migration_skill()` is called with no `target_dir`, **Then** skill bundles are written to `{project_root}/.claude/skills/`.
3. **Given** a successful install, **When** the return payload is inspected, **Then** every path in `installed_paths` is under `{project_root}` and the payload includes the resolved `project_root` and `scope` values.

---

### User Story 2 - Explicit Overrides Preserve Flexibility (Priority: P1)

As an operator with special layout needs (CI scratch dir, monorepo sub-project, or legacy global install), I want to override the install destination explicitly, so that the new project-local default does not remove escape hatches.

**Why this priority**: `target_dir` is already used by tests and advanced operators; removing or weakening it would break existing workflows.

**Independent Test**: Call `install_migration_skill(target_dir="/tmp/skills-test")` and confirm files land only in the override directory regardless of CWD or git root.

**Acceptance Scenarios**:

1. **Given** any workspace, **When** `target_dir` is supplied, **Then** that path is used as the install root and project-root detection is skipped.
2. **Given** a consumer repository, **When** `install_migration_skill(scope="global")` is called, **Then** bundles are written to `~/.cursor/skills/` or `~/.claude/skills/` exactly as before this spec.
3. **Given** `project_dir` is supplied, **When** the MCP server's CWD differs from the consumer repo, **Then** bundles are written relative to the supplied `project_dir`, not the server CWD.

---

### User Story 3 - Coexist With Other Project Skills (Priority: P2)

As a team that already keeps project skills (e.g. SpecKit skills under `.cursor/skills/speckit-*`), I want migration bundles installed alongside them without disturbing unrelated bundles, so that one install call does not break existing project tooling.

**Why this priority**: Many Paysafe and SpecKit repos already commit project-level skills; the installer must remain surgical.

**Independent Test**: Seed a temp project with an unrelated `speckit-plan/SKILL.md`, run `install_migration_skill()`, and verify the unrelated bundle is untouched while migration bundles are present.

**Acceptance Scenarios**:

1. **Given** a project that already contains other bundles under `.cursor/skills/`, **When** `install_migration_skill()` runs, **Then** only migration bundle directories (`framework-migration-*`, `migration-lite`, `openrewrite-runner` per active mode) are created or overwritten.
2. **Given** a re-run of `install_migration_skill()` in the same project, **When** bundles already exist, **Then** migration bundle files are overwritten idempotently with the same semantics as today (no partial install on failure).

---

### Edge Cases

- What happens when the workspace is not inside a git repository? The tool resolves `project_root` to `Path.cwd()` and installs there; no error is raised solely for missing `.git`.
- What happens when the MCP server CWD is not the consumer project root? The operator may pass `project_dir`; if omitted, `cwd` is used as `project_root`.
- What happens when `{project_root}/.cursor/skills/` is not writable? The tool raises `PermissionError` with the resolved path in the message (same as today).
- What happens when the project already has globally installed migration bundles? Global bundles are left untouched; project-local install is independent. Operators who want global behaviour use `scope="global"`.
- What happens in a monorepo opened at a sub-directory? Project root is the nearest ancestor containing `.git`; bundles install at that root's `.cursor/skills/`, consistent with `ps-migration/` living at repo root.

## Requirements *(mandatory)*

### Functional Requirements

#### Install Destination

- **FR-001**: When `target_dir` is omitted, `install_migration_skill` MUST resolve the install root to `{project_root}/.cursor/skills` for `target` in `("auto", "cursor")` and `{project_root}/.claude/skills` for `target="claude-code"`.
- **FR-002**: `project_root` MUST be resolved by walking parent directories from `Path(project_dir or Path.cwd())` until a directory containing `.git` is found; if none is found, `project_root` MUST fall back to `Path(project_dir or Path.cwd())`.
- **FR-003**: A new optional parameter `project_dir: str | None = None` MUST be accepted. When set, it replaces `Path.cwd()` as the starting point for project-root detection. Existing parameters `target` and `target_dir` MUST remain unchanged in name and meaning.
- **FR-004**: A new optional parameter `scope: str = "project"` MUST be accepted with allowed values `"project"` and `"global"`. When `scope="global"`, the install root MUST be `~/.cursor/skills` or `~/.claude/skills` per `target`, preserving pre-019 behaviour. When `target_dir` is set, `scope` is ignored.
- **FR-005**: `target="auto"` MUST continue to default the IDE family to Cursor (same as today). Auto-detection of Cursor vs Claude Code from filesystem markers is out of scope for this spec.

#### Unchanged Install Mechanics

- **FR-006**: `SKILL_BUNDLES`, `MODE_BUNDLES`, staging copy logic (`_install_to_target`), bundle file counts, and `MIGRATION_MODE` gating MUST NOT change.
- **FR-007**: Error semantics MUST remain: missing source file → `FileNotFoundError` with no partial install; non-writable target → `PermissionError` naming the resolved path.
- **FR-008**: The tool's MCP registration, stage-gating exposure, and return-field names (`status`, `target`, `installed_paths`, `message`, `mode`, `installed_skills`) MUST be retained. Two additive return fields are permitted: `project_root` (resolved absolute path string) and `scope` (resolved `"project"` or `"global"`).

#### Documentation

- **FR-009**: `INSTRUCTION.md` MUST change setup guidance from "once per agent environment" to "once per consumer project (or once per repo checkout)".
- **FR-010**: `docs/mcp-tools-skills-prompts.md` and `USAGE.md` MUST document the new default path, `project_dir`, and `scope` parameters.
- **FR-011**: Operator guidance MUST state that project-local bundles may be committed to version control or gitignored — that choice is left to the consumer team; this spec does not mandate either.

#### Tests

- **FR-012**: Unit tests MUST cover: (a) default project-local install under a temp git repo, (b) `scope="global"` preserves `~/.cursor/skills`-style resolution (using `target_dir` or home override in tests — do not write to the developer's real global dir in CI), (c) `target_dir` override still wins, (d) `project_dir` override when CWD differs.
- **FR-013**: Existing tests that pass explicit `target_dir` MUST continue to pass without modification.

### Key Entities

- **Project Root**: The consumer repository root used to anchor `.cursor/skills/` or `.claude/skills/`. Resolved via `.git` walk with `cwd` fallback.
- **Install Scope**: Either `project` (default, new behaviour) or `global` (legacy `~/.cursor/skills` / `~/.claude/skills` behaviour).
- **Install Root**: The parent directory into which bundle subdirectories are written. Equals `{project_root}/.cursor/skills` (or `.claude/skills`) unless overridden by `target_dir` or `scope="global"`.
- **Migration Bundle**: Unchanged from `015a` — e.g. `framework-migration-plan/`, `migration-lite/`, each containing `SKILL.md` and optional `references/`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A default `install_migration_skill()` call in a consumer repo writes all mode-appropriate bundles under that repo's `.cursor/skills/` (or `.claude/skills/`), with zero files written to `~/.cursor/skills/` unless `scope="global"` is explicitly requested.
- **SC-002**: `scope="global"` produces byte-identical bundle layout to the pre-019 installer for the same `MIGRATION_MODE` and `target`.
- **SC-003**: Re-running install in the same project is idempotent — migration bundle files match server source versions; unrelated project skills are not deleted.
- **SC-004**: All existing unit tests that use `target_dir` pass without change; new tests cover project-root resolution and `scope`.
- **SC-005**: Operator docs (`INSTRUCTION.md`, `docs/mcp-tools-skills-prompts.md`) no longer instruct a global one-time install as the only path.

## Assumptions

- Cursor and Claude Code both discover project skills at `.cursor/skills/` and `.claude/skills/` relative to the opened workspace, as documented in Cursor's skill-authoring guidance.
- The MCP server's `Path.cwd()` is usually the workspace root when invoked from Cursor or Claude Code; `project_dir` is the fallback for misaligned CWD.
- Migration bundle names do not collide with common project skills already in use (e.g. `speckit-*`, `changelog-migration-extractor`).
- Consumer teams manage git policy for installed skills themselves; the installer only writes files.
- No new MCP tools, prompts, or skill Markdown content changes are required — only `install.py` and operator documentation.

## Out of Scope

- Changing bundle manifests, skill frontmatter, stage-gating tool lists, or MCP skill resources (`skill://…`).
- Auto-detecting Cursor vs Claude Code from `.cursor/` / `.claude/` markers (may be a future spec).
- Adding installed skills to `.gitignore` automatically or committing them automatically.
- Removing or migrating existing global installs on disk.
- Docker / remote MCP environments where the consumer repo is not on the server's filesystem (operators continue to use `target_dir`).

## Implementation Notes *(informative, not normative)*

Estimated effort: **0.5–1 day**. The change is concentrated in `_resolve_target_dir` (~20–40 lines), a small project-root helper, additive parameters, tests, and doc updates. Copy/staging logic is untouched.

Suggested touch points:

| File | Change |
|------|--------|
| `migration_oracle/mcp/tools/install.py` | Project-root resolution, `scope`, `project_dir`, default path constants |
| `tests/mcp/test_install_skill.py` | New cases for project-local default and `scope` |
| `INSTRUCTION.md` | Setup wording |
| `docs/mcp-tools-skills-prompts.md` | Tool parameter table |
| `USAGE.md` | One-line description update |
