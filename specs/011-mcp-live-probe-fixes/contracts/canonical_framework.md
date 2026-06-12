# Contract: canonical_framework Helper

**Spec**: 011-mcp-live-probe-fixes | **FR**: FR-005–FR-008

## Purpose

Provides a single authoritative entry point for resolving any user-supplied framework string to the
canonical `display` form used in graph queries and the canonical `slug` form used in Maven
coordinate lookups. Prevents every tool from implementing its own inline normalisation logic,
which historically produced divergent behaviour across tools.

---

## Owner Module

`migration_oracle/mcp/tools/upgrade.py` — module-level function and lookup table. No new file is
introduced. The helper MUST NOT be copied into any other module; other modules MUST import it from
`upgrade.py` if they need it.

---

## API

```python
from typing import NamedTuple

class _CanonicalFramework(NamedTuple):
    display: str   # "Spring Boot"  — graph query filter value
    slug: str      # "spring-boot"  — Maven coordinate table key

def canonical_framework(framework: str) -> _CanonicalFramework | dict:
    """
    Resolve a framework string to the canonical record.

    Returns:
      _CanonicalFramework on success.
      A structured error dict with error_code="unsupported_framework" on failure.
      Call sites MUST check the return type before using .display/.slug.
    """
```

---

## Accepted Inputs

The helper normalises the input before lookup by stripping all hyphens, underscores, and whitespace
and lowercasing. The following are ALL equivalent:

| Input | Normalised key | Resolves to |
|-------|----------------|-------------|
| `"Spring Boot"` | `springboot` | `_CanonicalFramework(display="Spring Boot", slug="spring-boot")` |
| `"spring boot"` | `springboot` | same |
| `"spring-boot"` | `springboot` | same |
| `"springboot"`  | `springboot` | same |
| `"SPRING-BOOT"` | `springboot` | same |

Any input that does not map to a known entry returns the `unsupported_framework` error dict.

---

## Usage Rules

### `.display` — for graph queries

Any Cypher query that filters on `Version.framework`, `MigrationRule.framework`, or any other
node property that stores the display-form framework name MUST use `.display`.

```python
cf = canonical_framework(framework)
if isinstance(cf, dict): return cf   # propagate error
session.run(QUERY, framework=cf.display, ...)
```

### `.slug` — for Maven coordinate lookup

The `_MAVEN_COORDS` table in `upgrade.py` is keyed by slug. All Maven Central / Artifactory
lookups MUST use `.slug`.

```python
coords = _MAVEN_COORDS.get(cf.slug)
```

### Error propagation

When `canonical_framework` returns a dict (the error sentinel), the call site MUST return that
dict directly without making any network calls or graph reads. This is the no-network-call guarantee
required by FR-008.

---

## Scope for Spec 011

Only `check_version_availability` is REQUIRED to adopt this helper in spec 011. The other
framework-accepting tools (`analyze_upgrade_path`, `build_recipe_plan`, `resolve_deprecation`,
`entity_evolution`) already accept the `"Spring Boot"` display form and pass it unchanged to the
graph — which is correct. They DO NOT need to be modified in this spec.

Future specs that add new frameworks or tools MUST use `canonical_framework` for input resolution
and MUST NOT add inline normalisation.

---

## Prohibition

Inline framework normalisation (e.g. `framework.lower().replace(" ", "-")`) MUST NOT appear in
any tool function body. All normalisation passes through `canonical_framework`.

---

## Lookup Table Extension

New frameworks are added by inserting into `_FRAMEWORK_ALIASES` in `upgrade.py` and into
`_MAVEN_COORDS` when Maven coordinates are known. No other files require changes.

```python
_FRAMEWORK_ALIASES: dict[str, _CanonicalFramework] = {
    "springboot": _CanonicalFramework(display="Spring Boot", slug="spring-boot"),
    # "angular":  _CanonicalFramework(display="Angular",     slug="angular"),  ← future
}
```
