# Research Findings: Migration Skill Install Remediation

## Source Review Summary

This research summarizes a focused review of `install_migration_skill`, the split migration skill bundles, server skill-resource routing, stage gating, and operator documentation.

## Finding 1: Research Stage Source Exists but Runtime Does Not Expose It

Evidence:

- `migration_oracle/mcp/skills/framework-migration/research.md` exists and defines `name: framework-migration-research`.
- `docs/04-operator-guides/instruction.md` describes a six-stage workflow and lists `framework-migration-research` as a full-mode install bundle.
- `migration_oracle/mcp/tools/install.py` full-mode `MODE_BUNDLES` currently lists only five bundles: plan, gap-check, clarify, preview, execute.
- `migration_oracle/mcp/server.py` `_STAGE_BUNDLES` currently lists only plan, gap-check, clarify, preview, execute.
- `migration_oracle/mcp/stage_gating.py` `_VALID_STAGES` currently lists only plan, gap-check, clarify, preview, execute.

Decision:

- Treat the missing research bundle/resource/stage as a runtime drift bug from `018-migration-research-stage`.
- Add research as the first full-mode bundle and first optional stage.

Rejected alternative:

- Remove the research stage from docs and source. Rejected because `018-migration-research-stage` already established research as the canonical optional checkpoint stage and the operator guide now depends on it.

## Finding 2: Installed Scanner Instructions Point to a Source-Tree Path

Evidence:

- `migration_oracle/mcp/skills/framework-migration/scanning.md` says the canonical extractor lives at `migration_oracle/mcp/skills/framework-migration/framework_scanner.py` and tells operators to run `python3 migration_oracle/mcp/skills/framework-migration/framework_scanner.py /path/to/project`.
- `install.py` copies `scanning.md` into `framework-migration-plan/references/scanning.md`, but does not copy `framework_scanner.py`.
- Consumer repositories that receive project-local skills do not necessarily contain the Migration Oracle source tree, so the command is not portable.

Decision:

- Copy `framework_scanner.py` into the installed plan bundle references directory.
- Update scanner documentation so the primary installed command uses `references/framework_scanner.py`.
- Ensure research-stage scanning instructions point to installed material. Either copy the same references into `framework-migration-research/references/` or explicitly point to the installed sibling path `../framework-migration-plan/references/...` and test that full-mode install always includes both bundles.

Preferred implementation:

- Keep one installed scanner copy under `framework-migration-plan/references/framework_scanner.py`.
- For research, keep sibling references to `../framework-migration-plan/references/scanning.md` and `../framework-migration-plan/references/version-map.md` only if tests assert the sibling bundle is installed in full mode. If standalone robustness is preferred, duplicate scanner/version-map references into research as well.

## Finding 3: Docs Still Describe Removed Four-Loop Resources and Context Tools

Evidence:

- `docs/04-operator-guides/usage.md` says there are four static skill resources and lists `skill://framework-migration/main`, `skill://framework-migration/scanning`, `skill://framework-migration/plan-format`, and `skill://framework-migration/version-map`.
- The same guide shows a rendered prompt loading `skill://framework-migration/main` and running a four-loop harness using `create_migration_context`, `update_step_status`, and `close_migration_context`.
- Current server resources are split URIs such as `skill://framework-migration-plan/main` and `skill://framework-migration-execute/rollback`.
- The current file-state model removed graph session state for migration progress.

Decision:

- Update active operator and MCP docs to match the split-bundle, file-state harness.
- Historical docs may keep old references only if clearly marked obsolete or archival.

Rejected alternative:

- Leave docs stale because root `USAGE.md` is only a redirect. Rejected because the redirect target is the active operator guide.

## Finding 4: Tests Protect the Stale Five-Bundle Layout

Evidence:

- `tests/mcp/test_install_skill.py::test_full_mode_installs_six_bundles` is named for six bundles but asserts only five installed skills and eight installed paths.
- `tests/mcp/test_install_bundles.py` has `FULL_BUNDLES` hardcoded to five bundles.
- Server resource tests currently expect eight split resources without research.

Decision:

- Update tests first or alongside implementation so the test suite asserts the intended six-stage runtime contract.
- Include negative coverage for invalid install targets.

## Finding 5: Invalid Install Target Silently Resolves to Claude Code

Evidence:

- `install_migration_skill` documents `target` as `auto`, `cursor`, or `claude-code`.
- Runtime resolution uses `resolved = "cursor" if target in ("auto", "cursor") else "claude-code"`, so typos such as `curser` silently install into Claude paths.

Decision:

- Add explicit target validation before path resolution and file copy.
- Mirror existing `scope` validation style.

## Implementation Risk

- The full-mode installed path count will change when adding research and scanner references. Tests should assert expected files by path rather than only count where possible.
- If `research.md` relies on sibling bundle references, installing a single research bundle manually would be incomplete. Current installer installs full mode as a bundle set, so this is acceptable only if documented and tested.
- Hatch packaging may need verification for non-Python package data under `migration_oracle/mcp/skills/`. The implementation should run an installed-source or wheel-like test if packaging is part of release criteria.

## Recommended Verification Commands

Run focused tests first:

```bash
.venv/bin/python -m pytest tests/mcp/test_install_skill.py tests/mcp/test_install_bundles.py tests/mcp/test_prompts.py tests/mcp/test_feature_flag.py tests/mcp/test_server.py
```

Then run a grep-based stale reference check:

```bash
rg -n "skill://framework-migration/main|skill://framework-migration/plan-format|Run the four-loop|create_migration_context|update_step_status|close_migration_context|get_pending_steps" docs/03-mcp-and-agent-harness docs/04-operator-guides migration_oracle/mcp/skills tests
```

Expected result: active docs and skills do not instruct use of old resources or removed tools. Historical documents may match only when explicitly marked historical or obsolete.
