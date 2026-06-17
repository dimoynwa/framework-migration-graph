# Framework Migration Skill

End-to-end framework migration workflow for Spring Boot, Angular, and related platforms.

## Phase 2 — Graph Query

### Step 2c — Resolve Paysafe internal dependencies

For each `com.paysafe.*` dependency discovered in Loop I, call:

```
resolve_paysafe_dependency_by_service_name(
  service_name = <dep>
)
```

> The tool returns the latest overall version of the library — compatibility with the target
> framework is not verified. Mark the result as unverified in the dependency table (⚠️) and
> note that the engineer should confirm compatibility after upgrading.

## Phase 4 — Output (Plan Mode and Assistant Mode)

### Dependency upgrade table

| Dependency | Current | Recommended | Notes | Verified |
|---|---|---|---|---|
| `payment-service` | `1.4.2` | `2.0.1` | Latest overall | ⚠️ unverified |

> ⚠️ Paysafe internal dependency versions are the latest available tag, not the latest version
> verified compatible with `<TO_VERSION>`. Confirm compatibility before deploying.
