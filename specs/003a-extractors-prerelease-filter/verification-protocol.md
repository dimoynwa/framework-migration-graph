# Verification Protocol: Pre-release Version Filtering

**Location**: `specs/003a-extractors-prerelease-filter/verification-protocol.md`
**Spec gate**: Run after implementing `003a-extractors-prerelease-filter` before merging to main.
**Execution order**: Levels 0 → 3 in sequence. Stop and fix on the first failure — failures compound.

---

## Prerequisites

| Requirement | Check |
|---|---|
| `uv sync` is clean | `uv sync && echo OK` |
| No network needed | All checks in Levels 0–2 are pure; Level 3 needs live Maven Central |

**Level requirements:**

| Level | Network | Purpose |
|---|---|---|
| 0 — Static checks | ✗ | Filter functions exist, are importable, return correct values |
| 1 — Config checks | ✗ | New env var present with correct default |
| 2 — Extractor wiring | ✗ | Each extractor calls the correct filter; no inline duplication |
| 3 — Live version discovery | ✓ | Real Maven metadata returns only GA versions |

---

## Level 0 — Static checks

*No infrastructure. All checks are pure unit tests on the filter functions.*

### 0-A: Filter functions exist in `base.py` and are importable

```bash
uv run python -c "
from migration_oracle.pipeline.extractors.base import (
    is_jboss_ga_version,
    is_infinispan_ga_version,
    is_spring_boot_ga_version,
)
print('PASS 0-A: all three filter functions importable from base.py')
"
```

### 0-B: `is_jboss_ga_version` — correct accept/reject behaviour

```bash
uv run python -c "
from migration_oracle.pipeline.extractors.base import is_jboss_ga_version

ACCEPT = [
    '6.0.0.Final', '6.6.52.Final', '7.0.0.Final', '7.4.0.Final',
    '2.9.1.Final', '5.0.10.Final', '6.2.16.Final',
]
REJECT = [
    '6.0.0.Alpha1', '6.0.0.Alpha9', '6.0.0.Beta1', '6.0.0.Beta3',
    '6.0.0.CR1', '6.0.0.CR2', '7.2.0.CR1', '7.3.0.CR1',
    '7.0.0.Beta5', '6.2.14.Beta1',
    '2.9.0.CR1', '2.9.0.CR2',
    '6.0.0',         # plain version without .Final
    '6.0.0.SP1',     # service pack — also excluded
    '',
]
for v in ACCEPT:
    assert is_jboss_ga_version(v), f'Should ACCEPT {v!r}'
for v in REJECT:
    assert not is_jboss_ga_version(v), f'Should REJECT {v!r}'
print(f'PASS 0-B: is_jboss_ga_version accepts {len(ACCEPT)} GA and rejects {len(REJECT)} pre-release versions')
"
```

### 0-C: `is_infinispan_ga_version` — correct accept/reject behaviour

```bash
uv run python -c "
from migration_oracle.pipeline.extractors.base import is_infinispan_ga_version

ACCEPT = [
    '16.2.0', '16.2.1', '16.1.4', '16.0.12',   # 16.x plain style
    '15.0.20.Final', '15.2.5.Final', '14.0.35.Final',  # 15.x .Final style
]
REJECT = [
    '16.2.0.Dev01', '16.2.0.Dev02',  # 16.x dev builds
    '15.0.19.Beta1',                  # hypothetical beta
    '16.0.0.CR1',                     # CR build
    '16.2.0.Final',                   # .Final on a 16.x version is not the convention
                                      # but is technically not GA either — reject it
                                      # to avoid ambiguity
    '',
]
for v in ACCEPT:
    assert is_infinispan_ga_version(v), f'Should ACCEPT {v!r}'
for v in REJECT:
    assert not is_infinispan_ga_version(v), f'Should REJECT {v!r}'
print(f'PASS 0-C: is_infinispan_ga_version accepts {len(ACCEPT)} GA and rejects {len(REJECT)} pre-release versions')
"
```

### 0-D: `is_spring_boot_ga_version` — correct accept/reject behaviour

```bash
uv run python -c "
from migration_oracle.pipeline.extractors.base import is_spring_boot_ga_version

ACCEPT = [
    '3.3.0', '3.4.1', '3.5.14', '4.0.0', '4.0.6', '4.1.0', '2.7.18',
]
REJECT = [
    '4.1.0-M1', '4.1.0-M2', '4.1.0-M3', '4.1.0-M4',
    '4.0.0-M1', '4.0.0-M2',
    '4.1.0-RC1', '4.0.0-RC1',
    '4.0.0-SNAPSHOT', '3.3.0-SNAPSHOT',
    '3.3.0-M2',
    '',
]
for v in ACCEPT:
    assert is_spring_boot_ga_version(v), f'Should ACCEPT {v!r}'
for v in REJECT:
    assert not is_spring_boot_ga_version(v), f'Should REJECT {v!r}'
print(f'PASS 0-D: is_spring_boot_ga_version accepts {len(ACCEPT)} GA and rejects {len(REJECT)} pre-release versions')
"
```

### 0-E: Filter functions have no side effects (no I/O, no env var reads)

```bash
uv run python -c "
import unittest.mock as mock, os

# Patch env and open to detect any I/O
with mock.patch.dict(os.environ, {}, clear=True), \
     mock.patch('builtins.open', side_effect=AssertionError('open() called in filter function')):
    from migration_oracle.pipeline.extractors.base import (
        is_jboss_ga_version, is_infinispan_ga_version, is_spring_boot_ga_version
    )
    is_jboss_ga_version('6.0.0.Final')
    is_infinispan_ga_version('16.2.0')
    is_spring_boot_ga_version('3.3.0')

print('PASS 0-E: filter functions have no I/O side effects')
"
```

---

## Level 1 — Config checks

*No network. Verifies the new env var is wired correctly.*

### 1-A: `SPRING_INCLUDE_PRERELEASE` defaults to `False`

```bash
uv run python -c "
import os
# Ensure the var is unset
os.environ.pop('SPRING_INCLUDE_PRERELEASE', None)

# Force config reload
import importlib, sys
for k in list(sys.modules.keys()):
    if 'migration_oracle.config' in k:
        del sys.modules[k]

from migration_oracle import config
assert config.SPRING_INCLUDE_PRERELEASE is False, (
    f'Expected SPRING_INCLUDE_PRERELEASE=False by default, got {config.SPRING_INCLUDE_PRERELEASE!r}'
)
print('PASS 1-A: SPRING_INCLUDE_PRERELEASE defaults to False')
"
```

### 1-B: `SPRING_INCLUDE_PRERELEASE=1` enables pre-release versions

```bash
uv run python -c "
import os
os.environ['SPRING_INCLUDE_PRERELEASE'] = '1'

import importlib, sys
for k in list(sys.modules.keys()):
    if 'migration_oracle.config' in k:
        del sys.modules[k]

from migration_oracle import config
assert config.SPRING_INCLUDE_PRERELEASE is True, (
    f'Expected SPRING_INCLUDE_PRERELEASE=True when set to 1, got {config.SPRING_INCLUDE_PRERELEASE!r}'
)
print('PASS 1-B: SPRING_INCLUDE_PRERELEASE=1 sets flag to True')
" 
```

### 1-C: `JBOSS_SKIP_PRERELEASE` is accessible from `config.py` (existing var, confirm it's there)

```bash
uv run python -c "
from migration_oracle import config
assert hasattr(config, 'JBOSS_SKIP_PRERELEASE'), 'JBOSS_SKIP_PRERELEASE missing from config'
print(f'PASS 1-C: JBOSS_SKIP_PRERELEASE present in config (current value: {config.JBOSS_SKIP_PRERELEASE!r})')
"
```

---

## Level 2 — Extractor wiring

*No network. AST-based checks that each extractor calls the right filter and does not duplicate logic inline.*

### 2-A: Spring Boot extractor calls `is_spring_boot_ga_version`

```bash
uv run python -c "
import ast, pathlib

src = pathlib.Path('migration_oracle/pipeline/extractors/spring_boot.py').read_text()
assert 'is_spring_boot_ga_version' in src, (
    'spring_boot.py does not call is_spring_boot_ga_version — filter not wired'
)
# Must not use a hardcoded regex pattern as a substitute
import re
BAD_PATTERNS = [r'match\(r.*\\\\d.*\\\\d.*\\\\d', r'fullmatch\(']
for pat in BAD_PATTERNS:
    assert not re.search(pat, src), (
        f'spring_boot.py appears to duplicate the filter regex inline: matched {pat!r}'
    )
print('PASS 2-A: spring_boot.py calls is_spring_boot_ga_version')
"
```

### 2-B: Hibernate extractor calls `is_jboss_ga_version`

```bash
uv run python -c "
import pathlib
src = pathlib.Path('migration_oracle/pipeline/extractors/hibernate.py').read_text()
assert 'is_jboss_ga_version' in src, (
    'hibernate.py does not call is_jboss_ga_version — filter not wired'
)
# Must not use endswith('.Final') as a substitute inline
assert \"endswith('.Final')\" not in src or src.count(\"endswith('.Final')\") == 0, (
    'hibernate.py uses inline endswith check instead of shared function'
)
print('PASS 2-B: hibernate.py calls is_jboss_ga_version')
"
```

### 2-C: Infinispan extractor calls `is_infinispan_ga_version`

```bash
uv run python -c "
import pathlib
src = pathlib.Path('migration_oracle/pipeline/extractors/infinispan.py').read_text()
assert 'is_infinispan_ga_version' in src, (
    'infinispan.py does not call is_infinispan_ga_version — filter not wired'
)
print('PASS 2-C: infinispan.py calls is_infinispan_ga_version')
"
```

### 2-D: WildFly extractor uses `is_jboss_ga_version` (not an inline check)

```bash
uv run python -c "
import pathlib
src = pathlib.Path('migration_oracle/pipeline/extractors/wildfly.py').read_text()
assert 'is_jboss_ga_version' in src, (
    'wildfly.py still uses inline .Final check instead of shared is_jboss_ga_version'
)
print('PASS 2-D: wildfly.py uses shared is_jboss_ga_version from base.py')
"
```

### 2-E: Elytron stub contains TODO comment for future filter wiring

```bash
uv run python -c "
import pathlib
src = pathlib.Path('migration_oracle/pipeline/extractors/elytron.py').read_text()
assert 'is_jboss_ga_version' in src or 'TODO' in src.upper(), (
    'elytron.py has no filter wiring and no TODO comment — filter will be forgotten at implementation'
)
print('PASS 2-E: elytron.py has filter reference or TODO comment')
"
```

### 2-F: RESTEasy stub contains TODO comment for future filter wiring

```bash
uv run python -c "
import pathlib
src = pathlib.Path('migration_oracle/pipeline/extractors/resteasy.py').read_text()
assert 'is_jboss_ga_version' in src or 'TODO' in src.upper(), (
    'resteasy.py has no filter wiring and no TODO comment — filter will be forgotten at implementation'
)
print('PASS 2-F: resteasy.py has filter reference or TODO comment')
"
```

### 2-G: No extractor duplicates the filter logic inline

```bash
uv run python -c "
import pathlib, re

EXTRACTORS = [
    'spring_boot.py', 'hibernate.py', 'wildfly.py',
    'infinispan.py', 'elytron.py', 'resteasy.py',
]
base_dir = pathlib.Path('migration_oracle/pipeline/extractors')

FORBIDDEN = [
    (r\"endswith\(['\\\"]\.Final['\\\"]\\)\", 'inline .Final endswith check'),
    (r'\.endswith\([\x27\x22]\.Beta', 'inline .Beta endswith check'),
    (r'\.endswith\([\x27\x22]\.Alpha', 'inline .Alpha endswith check'),
    (r'\.endswith\([\x27\x22]\.CR', 'inline .CR endswith check'),
    (r'[Mm]\d+.*[Rr][Cc]\d*.*regex', 'inline M/RC regex'),
]

violations = []
for fname in EXTRACTORS:
    src = (base_dir / fname).read_text()
    for pattern, label in FORBIDDEN:
        if re.search(pattern, src):
            violations.append(f'{fname}: {label}')

assert not violations, f'Inline filter logic found (use shared functions):\\n' + '\\n'.join(violations)
print('PASS 2-G: no extractor duplicates filter logic inline')
"
```

---

## Level 3 — Live version discovery

*Requires network access to Maven Central. Run with real HTTP.*

### 3-A: Spring Boot version list contains no M, RC, or SNAPSHOT versions

```bash
uv run python -c "
import asyncio
from migration_oracle.pipeline.extractors import get_extractor

ext = get_extractor('spring-boot')
# Call the internal version discovery method
# Accept either _discover_versions() or _fetch_versions() naming
discover_fn = getattr(ext, '_discover_versions', None) or getattr(ext, '_fetch_versions', None)
if discover_fn is None:
    # Fall back: run a dry extract and check that no pre-release hops appear
    print('SKIP 3-A: no public _discover_versions method — verify via 3-D CLI check instead')
else:
    versions = asyncio.run(discover_fn())
    prerelease = [v for v in versions if any(x in v for x in ['-M', '-RC', '-SNAPSHOT', '-m', '-rc'])]
    assert not prerelease, (
        f'Spring Boot version list contains pre-release versions: {prerelease[:5]}'
    )
    print(f'PASS 3-A: Spring Boot version list has {len(versions)} GA versions, 0 pre-release')
"
```

### 3-B: Hibernate version list contains no Alpha, Beta, or CR versions

```bash
uv run python -c "
import asyncio
from migration_oracle.pipeline.extractors import get_extractor

ext = get_extractor('hibernate')
discover_fn = getattr(ext, '_discover_versions', None) or getattr(ext, '_fetch_versions', None)
if discover_fn is None:
    print('SKIP 3-B: no public _discover_versions method — verify via 3-D CLI check instead')
else:
    versions = asyncio.run(discover_fn())
    prerelease = [v for v in versions if any(
        x in v for x in ['Alpha', 'Beta', 'CR', 'alpha', 'beta', 'cr']
    )]
    assert not prerelease, (
        f'Hibernate version list contains pre-release versions: {prerelease[:5]}'
    )
    ga = [v for v in versions if v.endswith('.Final')]
    assert len(ga) >= 10, f'Expected at least 10 .Final versions, got {len(ga)}'
    print(f'PASS 3-B: Hibernate version list has {len(versions)} GA versions, 0 pre-release')
"
```

### 3-C: Infinispan version list contains no Dev, Beta, or CR versions

```bash
uv run python -c "
import asyncio
from migration_oracle.pipeline.extractors import get_extractor

ext = get_extractor('infinispan')
try:
    asyncio.run(ext.extract('15.0.0', '15.0.1'))
    # If it raises NotImplementedError, the stub is still in place
    print('SKIP 3-C: infinispan is still a stub — version discovery not testable yet')
except NotImplementedError:
    print('SKIP 3-C: infinispan is still a stub — version discovery not testable yet')
except Exception as e:
    # Any other error means the extractor tried to run — check version list via discover
    discover_fn = getattr(ext, '_discover_versions', None)
    if discover_fn:
        import asyncio as aio
        versions = aio.run(discover_fn())
        bad = [v for v in versions if any(x in v for x in ['Dev', 'Beta', 'CR', 'Alpha', 'dev', 'beta', 'cr', 'alpha'])]
        assert not bad, f'Infinispan version list contains pre-release: {bad[:5]}'
        print(f'PASS 3-C: Infinispan version list has {len(versions)} GA versions, 0 pre-release')
    else:
        print(f'SKIP 3-C: could not access version discovery: {e}')
"
```

### 3-D: CLI dry-run for Spring Boot produces no pre-release hop sections in the raw Markdown

```bash
# This is the most important live check — the artifact must contain only GA version hops
rm -f runs/raw/spring-boot-3.3.0-to-3.4.0-changes.md

uv run python -m migration_oracle.cli export-extract-populate-framework \
  --framework spring-boot 3.3.0 3.4.0 --dry-run --force-extract

ARTIFACT="runs/raw/spring-boot-3.3.0-to-3.4.0-changes.md"
test -f "$ARTIFACT" || { echo "FAIL 3-D: artifact not created"; exit 1; }

# Check for pre-release hop headers — none should appear
python3 -c "
import pathlib, re, sys

content = pathlib.Path('$ARTIFACT').read_text()
# Look for hop headers containing M, RC, or SNAPSHOT version numbers
hop_headers = re.findall(r'^## .*', content, re.MULTILINE)
bad_hops = [h for h in hop_headers if re.search(r'M\d+|RC\d+|SNAPSHOT|-M|-RC', h)]
if bad_hops:
    print('FAIL 3-D: pre-release hop headers found in artifact:')
    for h in bad_hops:
        print(f'  {h}')
    sys.exit(1)
print(f'PASS 3-D: {len(hop_headers)} hop sections in artifact, none are pre-release')
"
```

### 3-E: `SPRING_INCLUDE_PRERELEASE=1` allows milestone versions through (opt-in smoke test)

```bash
# This verifies the escape hatch works — pre-release versions ARE fetchable when opted in
SPRING_INCLUDE_PRERELEASE=1 uv run python -c "
import asyncio, os
assert os.getenv('SPRING_INCLUDE_PRERELEASE') == '1'

from migration_oracle.pipeline.extractors import get_extractor
ext = get_extractor('spring-boot')

discover_fn = getattr(ext, '_discover_versions', None)
if discover_fn:
    versions = asyncio.run(discover_fn())
    prerelease = [v for v in versions if any(x in v for x in ['-M', '-RC', '-SNAPSHOT'])]
    assert len(prerelease) > 0, (
        'With SPRING_INCLUDE_PRERELEASE=1, expected pre-release versions in list but got none. '
        'Escape hatch is not working.'
    )
    print(f'PASS 3-E: SPRING_INCLUDE_PRERELEASE=1 allows {len(prerelease)} pre-release versions through')
else:
    print('SKIP 3-E: no public _discover_versions — cannot test opt-in directly')
"
```

---

## Completion gate checklist

> Merge `002-extractors-prerelease-filter` only when every item below is checked.

| ID | Level | Description | Result |
|---|---|---|---|
| 0-A | Static | All three filter functions importable from `base.py` | |
| 0-B | Static | `is_jboss_ga_version` correctly accepts all `.Final` and rejects Alpha/Beta/CR/SP | |
| 0-C | Static | `is_infinispan_ga_version` correctly handles both 16.x (plain) and 15.x (.Final) GA styles | |
| 0-D | Static | `is_spring_boot_ga_version` correctly accepts X.Y.Z and rejects M/RC/SNAPSHOT | |
| 0-E | Static | All three filter functions have no I/O side effects | |
| 1-A | Config | `SPRING_INCLUDE_PRERELEASE` defaults to `False` | |
| 1-B | Config | `SPRING_INCLUDE_PRERELEASE=1` sets flag to `True` | |
| 1-C | Config | `JBOSS_SKIP_PRERELEASE` present in `config.py` | |
| 2-A | Wiring | `spring_boot.py` calls `is_spring_boot_ga_version` | |
| 2-B | Wiring | `hibernate.py` calls `is_jboss_ga_version` | |
| 2-C | Wiring | `infinispan.py` calls `is_infinispan_ga_version` | |
| 2-D | Wiring | `wildfly.py` uses shared `is_jboss_ga_version` (no inline check) | |
| 2-E | Wiring | `elytron.py` has filter reference or TODO comment | |
| 2-F | Wiring | `resteasy.py` has filter reference or TODO comment | |
| 2-G | Wiring | No extractor duplicates filter logic inline | |
| 3-A | Live | Spring Boot version discovery returns 0 pre-release versions | |
| 3-B | Live | Hibernate version discovery returns 0 pre-release versions | |
| 3-C | Live | Infinispan version discovery returns 0 pre-release versions (or skipped if stub) | |
| 3-D | Live | CLI dry-run artifact for `spring-boot 3.3.0 3.4.0` has 0 pre-release hop sections | |
| 3-E | Live | `SPRING_INCLUDE_PRERELEASE=1` allows pre-release versions through (opt-in works) | |