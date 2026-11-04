# Research: linear-file-migration-state

**Status**: Resolved

The design for this feature is completely frozen (§7 states no ambiguity remains). All decisions have been settled.

## Resolved Areas

- `get_steps_for_scope_tier` fold: Resolved (deleted, no fold).
- Folder location: Resolved (`$PROJECT_ROOT/ps-migration/{framework}-{from}-to-{to}/`).
- Submission trigger for insights: Resolved (strictly user-initiated).
- Stale-snapshot policy: Resolved (drift rules surface in `tasks.md`, >7 days age triggers warning, no auto-replan).
- Status vocabulary: Resolved (`pending | done | failed | needs-review`).
- Feedback stage deletion: Resolved.
- Deferred/bridge lifecycle: Resolved (`deferred` removed, `BRIDGED_BY` retained as knowledge).
- Needs-review policy: Resolved (explicit sign-off required for verification).
