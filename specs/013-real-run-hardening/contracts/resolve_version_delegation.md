# Contract: resolve_version Delegation Rule

**Spec anchor**: FR-A01, FR-A02, FR-A03, FR-A04, FR-A05, FR-A06, FR-A07  
**New in**: 013-real-run-hardening

---

## Rule

`resolve_version` is the **single version-resolution path**. Every tool that maps a `(framework, version)` string to a graph `Version` node **must** call `resolve_version`. No tool may inline a separate graph query or normalisation that determines which Version node to use.

---

## Delegating Tools

| Tool | Where it calls resolve_version | Mode(s) |
|---|---|---|
| `check_version_availability` | Top of handler, before Maven probe | `floor` **by default**. Accepts an optional `direction: Literal["floor", "ceil"] = "floor"` parameter. Use `ceil` only when the caller explicitly signals a target/upper-bound check. **SC-001 / US1 guarantee**: when called for the same (framework, version) as `submit_migration_insight` without an explicit direction, both tools use `floor` and MUST return the same resolved `nodeId`. |
| `submit_migration_insight` | Before cosine-similarity dedup | `floor` for `fromVersion`. On `VersionResolutionFailure`, dedup is **skipped** and the failure is returned directly — `submit_migration_insight` must not silently no-op. |
| `create_migration_context` | Before the MERGE | `floor` for `fromVersion`, `ceil` for `toVersion`. Resolved nodes are written to `UPGRADES_FROM` / `UPGRADES_TO` relationships. The identity MERGE key stores the **exact requested strings** (not the resolved versions). |
| `analyze_upgrade_path` | Before the range query | `floor` for `currentVersion`, `ceil` for `targetVersion`. Returns resolved `sortableVersion` bounds to the Cypher. |
| `build_recipe_plan` | Same as `analyze_upgrade_path` | Same modes |

---

## What Tools Must NOT Do

- Call `to_minor_zero()` as a version normalisation step before writing to the context identity — this silently overwrites caller-supplied patch numbers and causes ISSUE-017.
- Use `_CHECK_VERSION_IN_GRAPH` (exact match on `.0`) directly in any tool other than `resolve_version` itself.
- Inline `sortable_version(to_minor_zero(version))` to compute range bounds — this is the responsibility of `resolve_version(mode="floor"|"ceil")`.

---

## Failure Propagation

When `resolve_version` returns a `VersionResolutionFailure`:
- The calling tool **must** return an explicit error response.
- The error response must include the `status: "NO_CANDIDATE"` code, the `framework`, the `requestedVersion`, and the `candidatesConsidered` list.
- The calling tool **must not** silently no-op or return an empty result.

---

## Non-Goals

`resolve_version` is read-only by default. The `allow_stub_create` flag is opt-in and scoped to `create_migration_context` only (when the user explicitly requests that a just-released version be seeded into the catalogue).
