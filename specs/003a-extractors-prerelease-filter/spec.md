# Spec: Pre-release Version Filtering for Maven-based Extractors

**Amendment to**: `003-framework-http-extractors`
**Branch**: `003a-extractors-prerelease-filter`
**Created**: 2026-06-04
**Status**: Ready for implementation

---

## Problem

Four Maven-based extractors — Hibernate ORM, RESTEasy, Infinispan, and WildFly Elytron — fetch their available version list from Maven Central `maven-metadata.xml` but apply **no filter** to exclude pre-release versions. Maven Central for all four frameworks contains Alpha, Beta, CR (Candidate Release), and Dev builds alongside GA releases:

| Framework | Example pre-release versions on Maven Central |
|---|---|
| Hibernate ORM | `6.0.0.Alpha1`–`Alpha9`, `6.0.0.Beta1`–`Beta3`, `6.0.0.CR1`–`CR2`, `7.2.0.CR1`, `7.3.0.CR1` |
| RESTEasy | `7.0.0.Beta1`–`Beta5`, `6.2.14.Beta1` |
| Infinispan | `16.2.0.Dev01`, `16.2.0.Dev02` (16.x); non-`.Final` on 15.x and older |
| WildFly Elytron | `2.9.0.CR1`, `2.9.0.CR2` |

Spring Boot is also affected: starting with `4.0.0-M1`, milestones and release candidates (`4.1.0-M4`, `4.1.0-RC1`) are now published to Maven Central. The `^\d+\.\d+\.\d+$` stable filter is absent from the Spring Boot extractor.

WildFly and Angular are **not** affected: WildFly already filters to `.Final` only via `JBOSS_SKIP_PRERELEASE`, and Angular's npm filter `\d+\.\d+\.\d+` already excludes all pre-release tags.

**Without this fix**, when a user requests a range like `hibernate 6.4.0 7.0.0`:
1. Version discovery returns `[..., 7.0.0.Alpha1, 7.0.0.Alpha2, ..., 7.0.0.CR1, 7.0.0.Final, ...]`
2. The phase-1 chunker produces hops through every Alpha, Beta, and CR version
3. Each pre-release hop tries to fetch an AsciiDoc migration guide or GitHub release — both of which either 404 or return a stub with no real changelog content
4. The filter LLM receives dozens of empty hop sections, producing garbage or an empty entities JSON
5. No error is raised — the pipeline silently produces a useless artifact

---

## What needs to change

### 1. `migration_oracle/pipeline/extractors/base.py` — add two shared filter functions

```python
import re

# Matches GA releases for the JBoss/Red Hat Maven ecosystem: X.Y.Z.Final
_JBOSS_GA_PATTERN = re.compile(r'^\d+\.\d+\.\d+\.Final$')

# Matches GA releases for Spring Boot: plain X.Y.Z with no suffix
_SPRING_GA_PATTERN = re.compile(r'^\d+\.\d+\.\d+$')


def is_jboss_ga_version(version: str) -> bool:
    """Return True only for JBoss-ecosystem GA releases (X.Y.Z.Final).

    Rejects: Alpha, Beta, CR, SP (service pack is kept — see NOTE below).
    Used by: WildFly (already filtered), Hibernate ORM, RESTEasy, WildFly Elytron.

    NOTE: Service pack versions like X.Y.Z.SP1 are also excluded by this filter.
    SP releases are rare and do not have standalone GitHub release pages. If a
    user needs to include an SP version in their range they must use
    JBOSS_SKIP_PRERELEASE=1 to disable the filter entirely.
    """
    return bool(_JBOSS_GA_PATTERN.match(version))


def is_infinispan_ga_version(version: str) -> bool:
    """Return True for GA Infinispan releases.

    Infinispan changed version conventions at 16.x:
    - 15.x and older: GA releases end in .Final (e.g. 15.0.20.Final)
    - 16.x and newer: GA releases are plain X.Y.Z (e.g. 16.2.0)

    Rejects: X.Y.Z.Dev01, X.Y.Z.Dev02, X.Y.Z.Beta1, X.Y.Z.CR1, etc.
    """
    # Plain X.Y.Z — current (16.x+) GA style
    if _SPRING_GA_PATTERN.match(version):
        return True
    # X.Y.Z.Final — legacy (15.x and older) GA style
    if _JBOSS_GA_PATTERN.match(version):
        return True
    return False


def is_spring_boot_ga_version(version: str) -> bool:
    """Return True only for Spring Boot GA releases (plain X.Y.Z, no suffix).

    Rejects: 4.1.0-M4, 4.1.0-RC1, 4.0.0-SNAPSHOT, 3.3.0-M2, etc.
    Required because as of Spring Boot 4.0.0-M1, milestone and RC builds
    are published to Maven Central alongside GA releases.
    """
    return bool(_SPRING_GA_PATTERN.match(version))
```

---

### 2. `migration_oracle/config.py` — confirm `JBOSS_SKIP_PRERELEASE` covers all four JBoss extractors

`JBOSS_SKIP_PRERELEASE` already exists and is used by WildFly. The same env var must be read by Hibernate ORM, RESTEasy, and WildFly Elytron. No new env var is needed. No change to `config.py` is required unless WildFly reads it directly rather than from the base class. Verify at implementation time.

A new env var `SPRING_INCLUDE_PRERELEASE` is introduced for Spring Boot (opt-in to include M/RC versions):

```python
# config.py addition
SPRING_INCLUDE_PRERELEASE: bool = os.getenv("SPRING_INCLUDE_PRERELEASE", "").lower() in ("1", "true", "yes")
```

---

### 3. `migration_oracle/pipeline/extractors/spring_boot.py` — apply `is_spring_boot_ga_version`

In the version discovery method, after parsing `maven-metadata.xml` into a list of version strings, add:

```python
from migration_oracle.pipeline.extractors.base import is_spring_boot_ga_version
from migration_oracle import config

versions = [v for v in raw_versions if is_spring_boot_ga_version(v)]
# opt-in: if SPRING_INCLUDE_PRERELEASE is set, use raw_versions unfiltered
if config.SPRING_INCLUDE_PRERELEASE:
    versions = raw_versions
```

---

### 4. `migration_oracle/pipeline/extractors/hibernate.py` — apply `is_jboss_ga_version`

In the version discovery method, after parsing `maven-metadata.xml`:

```python
from migration_oracle.pipeline.extractors.base import is_jboss_ga_version
from migration_oracle import config

versions = [v for v in raw_versions if is_jboss_ga_version(v)]
if config.JBOSS_SKIP_PRERELEASE:
    versions = raw_versions
```

---

### 5. `migration_oracle/pipeline/extractors/resteasy.py` — apply `is_jboss_ga_version`

Same pattern as Hibernate. RESTEasy is currently a stub (`NotImplementedError`) — the filter must be applied in the version discovery method when the stub is replaced with a real implementation. Add it to the stub now as a comment/TODO so it is not forgotten:

```python
# TODO: apply is_jboss_ga_version filter in version discovery
# (same pattern as hibernate.py)
```

---

### 6. `migration_oracle/pipeline/extractors/infinispan.py` — apply `is_infinispan_ga_version`

Same pattern but using the Infinispan-specific function:

```python
from migration_oracle.pipeline.extractors.base import is_infinispan_ga_version
from migration_oracle import config

versions = [v for v in raw_versions if is_infinispan_ga_version(v)]
if config.JBOSS_SKIP_PRERELEASE:
    versions = raw_versions
```

---

### 7. `migration_oracle/pipeline/extractors/elytron.py` — apply `is_jboss_ga_version`

Same pattern as Hibernate. Elytron is currently a stub — add the same TODO comment as RESTEasy.

---

### 8. `migration_oracle/pipeline/extractors/wildfly.py` — no change

WildFly already filters to `.Final` versions. The existing filter must call `is_jboss_ga_version` from `base.py` rather than duplicating the logic inline. If it is already using `is_jboss_ga_version`, no change. If it uses an inline check (e.g. `v.endswith('.Final')`), replace it with the shared function for consistency. Logic is identical — this is a code-quality change only.

---

## Files changed

| File | Change type | Notes |
|---|---|---|
| `migration_oracle/pipeline/extractors/base.py` | Addition | Three new pure functions, no side effects |
| `migration_oracle/config.py` | Addition | One new env var `SPRING_INCLUDE_PRERELEASE` |
| `migration_oracle/pipeline/extractors/spring_boot.py` | Modification | Apply `is_spring_boot_ga_version` in version discovery |
| `migration_oracle/pipeline/extractors/hibernate.py` | Modification | Apply `is_jboss_ga_version` in version discovery |
| `migration_oracle/pipeline/extractors/resteasy.py` | Modification | Add TODO comment (stub — no behaviour change yet) |
| `migration_oracle/pipeline/extractors/infinispan.py` | Modification | Apply `is_infinispan_ga_version` in version discovery |
| `migration_oracle/pipeline/extractors/elytron.py` | Modification | Add TODO comment (stub — no behaviour change yet) |
| `migration_oracle/pipeline/extractors/wildfly.py` | Modification | Replace inline `.endswith('.Final')` with `is_jboss_ga_version` (if needed) |

**No other files change.** `models/entities.py`, `filters.py`, `extractor.py`, `populator.py`, `cli.py`, and all MCP/graph modules are untouched.

---

## Constraints

- The three filter functions must live in `base.py` — not in `config.py` and not duplicated per extractor. They are pure string functions with no I/O.
- `JBOSS_SKIP_PRERELEASE` and `SPRING_INCLUDE_PRERELEASE` are the only escape hatches. No per-extractor opt-in flags.
- The filter is applied **after** XML parsing and **before** version range computation. It must not be applied to the user-supplied `from_version`/`to_version` CLI arguments — only to the discovered version list.
- If `JBOSS_SKIP_PRERELEASE` or `SPRING_INCLUDE_PRERELEASE` disables filtering, the full raw list from Maven Central is used, including pre-release versions. The pipeline must not crash on these — it must attempt to fetch them and fail per the normal per-hop error policy if no release content is found.
- The filter functions must be importable with no side effects (no HTTP, no env var reads).

---

## Out of scope

- WildFly and Angular: already handled, no change.
- EAP and Jakarta EE: use fixed/static version lists, no Maven metadata fetch, no filter needed.
- Changing hop-level error behaviour when a pre-release sneaks through (e.g. via `JBOSS_SKIP_PRERELEASE`): existing per-hop error policy (`extract()` raises with descriptive message) is sufficient.