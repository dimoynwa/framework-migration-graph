# Implementation Instructions: Migration Skill Install Remediation

You are implementing the remediation described by this folder. This is intentionally not a full SpecKit cycle.

## Required Reading

Read these files before editing:

1. `specs/020-migration-skill-install-remediation/spec.md`
2. `specs/020-migration-skill-install-remediation/research.md`
3. `docs/03-mcp-and-agent-harness/migration-model.md`
4. `docs/04-operator-guides/instruction.md`
5. `migration_oracle/mcp/tools/install.py`
6. `migration_oracle/mcp/server.py`
7. `migration_oracle/mcp/stage_gating.py`
8. `migration_oracle/mcp/skills/framework-migration/research.md`
9. `migration_oracle/mcp/skills/framework-migration/scanning.md`

## Objective

Fix runtime and documentation drift in migration skill installation:

- Full mode installs the complete six-stage bundle set, including research.
- The server can route and serve the research stage.
- Stage gating accepts `MCP_ACTIVE_STAGE=research`.
- Installed scanner instructions point to files copied into installed bundles.
- Active docs describe the split-bundle, file-state workflow.
- Invalid `install_migration_skill(target=...)` values fail clearly.

## Required Code Changes

### 1. Installer Bundle Set

Edit `migration_oracle/mcp/tools/install.py`.

Required behavior:

- Add `framework-migration-research` to `SKILL_BUNDLES`.
- Copy `framework-migration/research.md` to `framework-migration-research/SKILL.md`.
- Ensure research-stage references resolve after full-mode install. Either:
  - copy `scanning.md`, `version-map.md`, and `framework_scanner.py` into `framework-migration-research/references/`, or
  - keep research pointing to `../framework-migration-plan/references/...` and assert the sibling plan bundle is always installed in full mode.
- Add `framework-migration-research` as the first entry in `MODE_BUNDLES["full"]`.
- Copy `framework-migration/framework_scanner.py` into an installed `references/` path used by `scanning.md`.
- Validate `target` against `{"auto", "cursor", "claude-code"}` before resolving install paths or copying files. Invalid values must raise `ValueError`.

Do not change:

- Lite-mode bundle names or semantics.
- Project-local install defaults from spec `019-project-local-skill-install`.
- Staging/no-partial-install behavior.

### 2. Scanner Reference Paths

Edit `migration_oracle/mcp/skills/framework-migration/scanning.md`.

Required behavior:

- The primary command for installed skills must use an installed relative path such as:

```bash
python3 references/framework_scanner.py /path/to/project
```

- Do not tell consumer-repo operators to run `migration_oracle/mcp/skills/framework-migration/framework_scanner.py` as the primary command.
- It is acceptable to mention the source-tree path only as a development-source location, not as the installed command.

If research keeps sibling references to the plan bundle, check `migration_oracle/mcp/skills/framework-migration/research.md` and make its wording unambiguous that it uses installed sibling references.

### 3. Server Resources and Prompts

Edit `migration_oracle/mcp/server.py`.

Required behavior:

- Add `"research": "framework-migration-research"` to `_STAGE_BUNDLES`.
- Register `skill://framework-migration-research/main` and return `framework-migration/research.md`.
- Update prompt docstrings and rendered text so valid stages include research.
- `start_migration(..., stage="research")` must load `skill://framework-migration-research/main`.
- `resume_migration(..., stage="research")` should also route to research rather than falling back to execute.
- `migration_workflow_prompt` must describe the six-stage sequence with optional research.

### 4. Stage Gating

Edit `migration_oracle/mcp/stage_gating.py`.

Required behavior:

- Add `research` to `_VALID_STAGES`.
- Add `STAGE_TOOL_ALLOWLIST["research"]`.
- The allowlist must match the `compatibility.tools` list in `framework-migration/research.md`.
- Keep file-only stages restricted as they are unless the spec explicitly requires otherwise.

### 5. Documentation

Update active docs, at minimum:

- `docs/03-mcp-and-agent-harness/mcp-tools-skills-prompts.md`
- `docs/04-operator-guides/usage.md`

Required behavior:

- Full-mode install docs list six top-level bundles.
- Skill resource docs include `skill://framework-migration-research/main`.
- Prompt docs describe file-state stages and `ps-migration/` artifacts.
- Active docs do not instruct the current harness to use:
  - `skill://framework-migration/main`
  - `skill://framework-migration/plan-format`
  - `create_migration_context`
  - `get_pending_steps`
  - `update_step_status`
  - `close_migration_context`

Historical or archived docs may keep those terms only if the surrounding text clearly marks them as historical.

## Required Test Updates

Update or add tests in:

- `tests/mcp/test_install_skill.py`
- `tests/mcp/test_install_bundles.py`
- `tests/mcp/test_prompts.py`
- `tests/mcp/test_feature_flag.py`
- `tests/mcp/test_server.py`

Required coverage:

- Full mode installs six bundles, including `framework-migration-research`.
- Installed paths include scanner reference files required by `scanning.md`.
- Frontmatter tools for research match stage-gating allowlist.
- Server resources include `skill://framework-migration-research/main`.
- `start_migration(..., stage="research")` routes to the research URI.
- `MCP_ACTIVE_STAGE=research` exposes the research-stage tool set.
- Invalid installer target raises `ValueError` before files are written.
- Lite-mode install tests still pass unchanged in behavior.

## Verification

Run:

```bash
.venv/bin/python -m pytest tests/mcp/test_install_skill.py tests/mcp/test_install_bundles.py tests/mcp/test_prompts.py tests/mcp/test_feature_flag.py tests/mcp/test_server.py
```

Then run:

```bash
rg -n "skill://framework-migration/main|skill://framework-migration/plan-format|Run the four-loop|create_migration_context|update_step_status|close_migration_context|get_pending_steps" docs/03-mcp-and-agent-harness docs/04-operator-guides migration_oracle/mcp/skills tests
```

Review any matches. Active docs and skills must not instruct the current workflow to use old resources or removed tools.

## Completion Criteria

The implementation is complete when:

- All required focused tests pass.
- The stale-reference grep has no active-doc or runtime-skill violations.
- `install_migration_skill(target="cursor", target_dir=<tmp>)` in full mode produces a coherent installed bundle tree that an agent can follow from `SKILL.md` files alone.
- The final response lists changed files and any residual risks.
