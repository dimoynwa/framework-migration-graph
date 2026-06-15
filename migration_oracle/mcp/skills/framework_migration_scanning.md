# Scanning Reference

Full patterns for extracting entities in the exact formats the knowledge graph expects.

This file feeds Loop I (Context) of the migration harness. Its single job is to produce a
list of codebase entities in the *exact string form the graph stores them as*, so the
entity-matching logic in `analyze_upgrade_path`, `get_pending_steps`, and
`get_steps_for_scope_tier` can do clean equality comparison. Matching is exact-string, not
fuzzy — every rule below exists to align the scan output with the stored form.

---

## Extractor Selection and `extractorPath` (T044, FR-E01, FR-E03)

The scan result always includes an `extractorPath` field:

| Value | Meaning |
|---|---|
| `"python"` | Python canonical extractor ran (primary path) |
| `"grep-gnu"` | GNU grep fast path used (Python unavailable) |
| `"grep-bsd"` | BSD grep fast path used (Python unavailable, macOS) |

**Primary extractor**: Python canonical (uses `pathlib.rglob`, `re`, `xml.etree.ElementTree`, `json`). Available on Python 3.8+. Run after Loop I Step 0 preflight confirms Python 3 is present.

**Optional fast path**: `grep -E` patterns documented below each section. Use only when Python is absent. BSD (macOS) and GNU (Linux) use identical `-E` flag — do **not** use `-P` (PCRE), which is GNU-only and absent on macOS.

---

## Python-Canonical Extractor (FR-E01, T041)

The canonical extractor is a single Python module. It runs all entity-type passes and returns a structured scan result:

```python
"""framework_scanner.py — canonical entity extractor for the migration harness."""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import NamedTuple

ALLOW_LIST = re.compile(
    r'^('
    r'org\.springframework|jakarta\.|javax\.|org\.hibernate|io\.micrometer'
    r'|io\.projectreactor|org\.thymeleaf|com\.fasterxml\.jackson|tools\.jackson'
    r'|org\.springdoc|com\.querydsl|org\.flywaydb|org\.liquibase'
    r'|org\.apache\.tomcat|org\.eclipse\.jetty|io\.undertow'
    r')'
)

IMPORT_RE = re.compile(r'^import\s+(?:static\s+)?([\w.]+)', re.MULTILINE)
ANNOTATION_RE = re.compile(r'@([A-Za-z][\w.]*)')
NOISE_ANNOTATIONS = frozenset([
    'Override', 'Deprecated', 'SuppressWarnings', 'FunctionalInterface',
    'SafeVarargs', 'Data', 'Builder', 'Getter', 'Setter', 'ToString',
    'EqualsAndHashCode', 'NoArgsConstructor', 'AllArgsConstructor',
    'RequiredArgsConstructor', 'Slf4j', 'Value', 'NonNull', 'Nullable',
])
PROP_KEY_RE = re.compile(r'^([\w][\w.-]+)\s*=', re.MULTILINE)
MAVEN_NS = '{http://maven.apache.org/POM/4.0.0}'
MAVEN_KEEP = re.compile(
    r'^(org\.springframework|jakarta\.|javax\.|org\.hibernate|io\.micrometer'
    r'|io\.projectreactor|com\.fasterxml\.jackson|org\.springdoc|com\.querydsl'
    r'|org\.flywaydb|org\.liquibase|org\.apache\.tomcat|org\.eclipse\.jetty'
    r'|io\.undertow)\.'
)
GRADLE_DEP_RE = re.compile(r'["\']([a-zA-Z][\w.-]+:[a-zA-Z][\w.-]+):[^\s"\']+["\']')


class ScanResult(NamedTuple):
    entities: list[str]
    test_entities: list[str]
    extractor_path: str  # always "python"


def _scan_java_imports(root: Path, scope: str = 'main') -> set[str]:
    """Collect FQCNs from Java/Kotlin import lines under src/{scope}."""
    result: set[str] = set()
    base = root / 'src' / scope
    for ext in ('*.java', '*.kt'):
        for f in base.rglob(ext):
            try:
                text = f.read_text(encoding='utf-8', errors='replace')
            except OSError:
                continue
            for m in IMPORT_RE.finditer(text):
                fqcn = m.group(1)
                if ALLOW_LIST.match(fqcn):
                    result.add(fqcn)
    return result


def _scan_annotations(root: Path) -> set[str]:
    """Collect annotation simple names (no @) from src/main."""
    result: set[str] = set()
    for ext in ('*.java', '*.kt'):
        for f in (root / 'src' / 'main').rglob(ext):
            try:
                text = f.read_text(encoding='utf-8', errors='replace')
            except OSError:
                continue
            for m in ANNOTATION_RE.finditer(text):
                raw = m.group(1)
                simple = raw.rsplit('.', 1)[-1]
                if (
                    re.match(r'^[A-Z][A-Za-z0-9]+$', simple)
                    and simple not in NOISE_ANNOTATIONS
                ):
                    result.add(simple)
    return result


def _scan_properties(root: Path) -> set[str]:
    """Collect dotted property keys from .properties and .yml/.yaml files."""
    result: set[str] = set()
    for f in (root / 'src' / 'main' / 'resources').rglob('*.properties'):
        try:
            text = f.read_text(encoding='utf-8', errors='replace')
        except OSError:
            continue
        for m in PROP_KEY_RE.finditer(text):
            result.add(m.group(1))

    # YAML — PyYAML canonical path; degrade path below
    try:
        import yaml as _yaml  # type: ignore[import]
        def _flatten(d: dict, prefix: str = '') -> None:
            for k, v in (d or {}).items():
                key = f'{prefix}.{k}' if prefix else str(k)
                if isinstance(v, dict):
                    _flatten(v, key)
                else:
                    result.add(key)
        for f in (root / 'src' / 'main' / 'resources').rglob('*.y*ml'):
            try:
                data = _yaml.safe_load(f.read_text(encoding='utf-8', errors='replace'))
                if isinstance(data, dict):
                    _flatten(data)
            except Exception:
                pass
    except ImportError:
        # PyYAML absent — YAML property extraction skipped; .properties files parsed only
        pass  # see FR-E02 degrade section below

    return result


def _scan_maven(root: Path) -> set[str]:
    """Collect groupId:artifactId from pom.xml files."""
    result: set[str] = set()
    for pom in root.rglob('pom.xml'):
        if '/target/' in str(pom) or '\\target\\' in str(pom):
            continue
        try:
            tree = ET.parse(str(pom)).getroot()
            for dep in tree.iter(MAVEN_NS + 'dependency'):
                g = dep.find(MAVEN_NS + 'groupId')
                a = dep.find(MAVEN_NS + 'artifactId')
                if g is not None and a is not None:
                    gav = f'{g.text.strip()}:{a.text.strip()}'
                    if MAVEN_KEEP.match(gav):
                        result.add(gav)
        except Exception:
            pass
    return result


def _scan_gradle(root: Path) -> set[str]:
    """Collect groupId:artifactId from build.gradle(.kts) files."""
    result: set[str] = set()
    for f in root.rglob('build.gradle*'):
        if '/.gradle/' in str(f) or '\\.gradle\\' in str(f):
            continue
        try:
            text = f.read_text(encoding='utf-8', errors='replace')
        except OSError:
            continue
        for m in GRADLE_DEP_RE.finditer(text):
            gav = m.group(1)
            if MAVEN_KEEP.match(gav):
                result.add(gav)
    return result


def scan(project_root: str) -> ScanResult:
    root = Path(project_root)
    main_imports = _scan_java_imports(root, 'main')
    test_imports = _scan_java_imports(root, 'test')
    annotations = _scan_annotations(root)
    properties = _scan_properties(root)
    maven_deps = _scan_maven(root)
    gradle_deps = _scan_gradle(root)

    entities = sorted(main_imports | annotations | properties | maven_deps | gradle_deps)
    test_entities = sorted(test_imports)
    return ScanResult(entities=entities, test_entities=test_entities, extractor_path='python')


if __name__ == '__main__':
    project_root = sys.argv[1] if len(sys.argv) > 1 else '.'
    result = scan(project_root)
    print(json.dumps({
        'entities': result.entities,
        'testEntities': result.test_entities,
        'extractorPath': result.extractor_path,
        'count': len(result.entities),
    }, indent=2))
```

---

## PyYAML Degrade Path (FR-E02, T042)

The canonical extractor uses `yaml.safe_load` for `.yml`/`.yaml` property extraction. If PyYAML is absent:

```python
try:
    import yaml
    # ... full YAML flatten as in _scan_properties above
except ImportError:
    # PyYAML absent — YAML property extraction skipped; .properties files parsed only
    pass
```

- Java class/dependency extraction is **unaffected** — it uses `re` + `pathlib` only.
- `.properties` files are still parsed via `re.match`.
- Log: `"PyYAML absent — YAML property extraction skipped; .properties files parsed only"`.
- `extractorPath` remains `"python"` — the degrade affects only one entity type, not the overall extractor choice.
- The agent checks PyYAML availability in Loop I Step 0 preflight and surfaces the warning before scanning starts.

---

## Relevance Filtering — read this first

The graph only contains entities **owned by a tracked framework** (Spring Boot, Angular,
WildFly/JBoss). Anything else — your own application classes, the JDK (`java.*`), test
libraries, Lombok, generic third-party libs — has no node in the graph and can never match a
rule. Emitting it is pure noise.

Two consequences make filtering mandatory, not cosmetic:

1. **Volume.** An unfiltered import scan of a large codebase returns 1000–2000+ classes, the
   vast majority noise, blowing the entity budget and burying the signal.
2. **Correctness.** Noise is *not* inert. Class matching also compares simple names
   (`last(split(e.name, '.'))` against the derived `$scanned_class_simple` bucket). An app
   class `com.acme.Configuration` collides with
   `org.springframework.context.annotation.Configuration` and triggers a **false rule match**.

Therefore: **filter to framework-relevant prefixes at extraction time** (allow-list), do not
rely on a post-hoc trim. Every extractor below pipes through a `grep -E` allow-list. The
allow-list per framework is defined inline and reused by the prioritization step.

> The prefix lists are a manual reflection of each framework's managed dependency set; they
> are **not** auto-synced to upstream. Validate them against `spring-boot-dependencies` (the
> Spring Boot BOM) and the Angular update guide when the prefix set is revised — and treat the
> version-map status fields as advisory, per the staleness caveat in that file.

---

## Entity Format Quick Reference and Scan Result Shape

The scan result returned by the Python canonical extractor (`scan()`) always has the shape:
```json
{
  "entities": ["org.springframework..."],
  "testEntities": ["org.junit..."],
  "extractorPath": "python",
  "count": 42
}
```
`extractorPath` is `"python"`, `"grep-gnu"`, or `"grep-bsd"`. Always present.

### Entity Format Reference

| Entity type | Graph expects | Bash produces |
|---|---|---|
| Java class | `org.springframework.security.config.annotation.web.configuration.WebSecurityConfigurerAdapter` | Full import line, keep as-is |
| Kotlin class | `org.springframework.security.config.annotation.web.configuration.WebSecurityConfigurerAdapter` | Full import line, keep as-is |
| Java annotation | `EnableWebSecurity` | Strip `@`, keep simple name |
| Spring property | `spring.datasource.url` | Full dotted key, no truncation |
| Maven dep | `org.springframework.boot:spring-boot-starter-security` | `groupId:artifactId`, drop version |
| Gradle dep | `org.springframework.boot:spring-boot-starter-security` | `groupId:artifactId`, drop version |
| npm package | `@angular/common` | Exact package name from import/package.json |
| WildFly subsystem config | `subsystem.infinispan.cache-container.*.distributed-cache` | Flattened from `standalone.xml`/`domain.xml`; named instances → `*` (see WildFly section) |
| WildFly extension module | `org.wildfly.extension.picketlink` | From `<extension module="…"/>`; stored as `ApplicationProperty`, **not** `Class` |
| WildFly/JPA property | `hibernate.cache.region.factory_class` | From `persistence.xml` `<property>` keys, as-is |

---

## Spring Boot (Java / Kotlin) — Optional grep Fast Path

> **Use the Python canonical extractor above as the primary path.** These `grep` patterns are the **optional fast path** — use them only when Python 3 is absent (rare). Both GNU and BSD (macOS) support `-E`; do NOT use `-P` (PCRE) as it is GNU-only.

**Allow-list prefixes** (reused by every Spring extractor below). Core set plus managed libs
that carry real migration rules. `javax.` is kept deliberately — it is required for the
`2.x → 3.x` `javax → jakarta` boundary:

```
org.springframework | jakarta. | javax. | org.hibernate | io.micrometer
io.projectreactor | org.thymeleaf | com.fasterxml.jackson | tools.jackson
org.springdoc | com.querydsl | org.flywaydb | org.liquibase
org.apache.tomcat | org.eclipse.jetty | io.undertow
```

> `com.fasterxml.jackson` / `tools.jackson` (Jackson 3) is migration-critical — the Jackson
> 2→3 package rename mirrors the `javax → jakarta` namespace flip. The extended libs (Reactor,
> springdoc, querydsl, Flyway, Liquibase, servlet containers) are well-justified but should be
> confirmed against the BOM when the list is revised.

### Import extraction — Java (produces FQCN, main scope)

```bash
# Keep the FULL dotted path; filter to framework-owned prefixes only.
grep -rh --include="*.java" \
  -oP '(?<=^import )(static )?[\w.]+' \
  "$PROJECT_ROOT/src/main/java" 2>/dev/null \
  | sed 's/^static //' \
  | grep -E '^(org\.springframework|jakarta\.|javax\.|org\.hibernate|io\.micrometer|io\.projectreactor|org\.thymeleaf|com\.fasterxml\.jackson|tools\.jackson|org\.springdoc|com\.querydsl|org\.flywaydb|org\.liquibase|org\.apache\.tomcat|org\.eclipse\.jetty|io\.undertow)\.' \
  | sort -u
# Example output: org.springframework.security.config.annotation.web.configuration.WebSecurityConfigurerAdapter
```

### Import extraction — Java (test scope, tagged separately)

Test-framework imports are noise in the main set and, where relevant at all, belong to Loop
II's tier 4 (`test`, deferred). Scan test scope **separately** and tag the results so the
harness can route them to tier 4 rather than mixing them into the api-surface/runtime tiers.

```bash
# Test scope: framework allow-list PLUS test libraries. Tag output as test-scope.
grep -rh --include="*.java" --include="*.kt" \
  -oP '(?<=^import )(static )?[\w.]+' \
  "$PROJECT_ROOT/src/test" 2>/dev/null \
  | sed 's/^static //' \
  | grep -E '^(org\.springframework|jakarta\.|javax\.|org\.junit|org\.mockito|org\.assertj|io\.rest_assured|org\.testcontainers)\.' \
  | sort -u
# Example output: org.junit.jupiter.api.Test  (→ tier 4, deferred)
```

### Import extraction — Kotlin (produces FQCN, main scope)

```bash
grep -rh --include="*.kt" \
  -oP '(?<=^import )[\w.]+' \
  "$PROJECT_ROOT/src/main" 2>/dev/null \
  | grep -v '\*$' \
  | grep -E '^(org\.springframework|jakarta\.|javax\.|org\.hibernate|io\.micrometer|io\.projectreactor|org\.thymeleaf|com\.fasterxml\.jackson|tools\.jackson|org\.springdoc|com\.querydsl|org\.flywaydb|org\.liquibase|org\.apache\.tomcat|org\.eclipse\.jetty|io\.undertow)\.' \
  | sort -u
# Example output: org.springframework.boot.autoconfigure.SpringBootApplication
```

### Annotation extraction — Java + Kotlin (produces simple name, no @)

The graph indexes annotations by simple name without `@`. The previous pattern
(`[A-Z][A-Za-z]+`) had two bugs and a noise problem: it truncated annotations containing
digits (`@OAuth2Login` → `OAuth`), missed fully-qualified annotations
(`@jakarta.annotation.Resource`), and captured JDK/test/Lombok annotations
(`@Override`, `@Test`, `@Data`). Fixed extractor:

```bash
# Capture the whole annotation token (incl. fully-qualified form), reduce to the simple name,
# allow digits, then strip common JDK / test / Lombok noise annotations.
grep -rh --include="*.java" --include="*.kt" \
  -oP '(?<=@)[A-Za-z][\w.]*' \
  "$PROJECT_ROOT/src/main" 2>/dev/null \
  | sed 's/.*\.//' \
  | grep -E '^[A-Z][A-Za-z0-9]+$' \
  | grep -vE '^(Override|Deprecated|SuppressWarnings|FunctionalInterface|SafeVarargs|Data|Builder|Getter|Setter|ToString|EqualsAndHashCode|NoArgsConstructor|AllArgsConstructor|RequiredArgsConstructor|Slf4j|Value|NonNull|Nullable)$' \
  | sort -u
# Example output: EnableWebSecurity   (NOT @EnableWebSecurity, NOT Override, NOT Test)
```

> Test-only annotations (`Test`, `Mock`, `BeforeEach`, …) are excluded from the main pass; if
> needed they come from the test-scope import pass and route to tier 4.

### Spring application properties (produces full dotted key)

```bash
# .properties files — full key before = sign
grep -rh --include="*.properties" \
  -oP '^[\w][\w.]+(?=\s*=)' \
  "$PROJECT_ROOT/src/main/resources" 2>/dev/null \
  | sort -u
# Example output: spring.datasource.url

# .yml/.yaml — Python for accurate nested key reconstruction
python3 -c "
import yaml, os
def flatten(d, prefix=''):
    for k, v in (d or {}).items():
        key = f'{prefix}.{k}' if prefix else str(k)
        if isinstance(v, dict): flatten(v, key)
        else: print(key)
for root, _, files in os.walk('$PROJECT_ROOT/src/main/resources'):
    for f in files:
        if f.endswith(('.yml', '.yaml')):
            try: flatten(yaml.safe_load(open(os.path.join(root, f))))
            except: pass
" 2>/dev/null | sort -u
# Example output: spring.jpa.hibernate.ddl-auto
```

---

## Spring Boot — Dependencies (Optional grep Fast Path)

**Dependency allow-list** (`groupId:artifactId`, version dropped). Mirrors the import
allow-list; note Jackson's groupId is `com.fasterxml.jackson.*`, which the previous `io.`-only
filter missed:

```
org.springframework | jakarta. | javax. | org.hibernate | io.micrometer
io.projectreactor | com.fasterxml.jackson | org.springdoc | com.querydsl
org.flywaydb | org.liquibase | org.apache.tomcat | org.eclipse.jetty | io.undertow
```

### Maven — pom.xml (produces groupId:artifactId)

```bash
python3 -c "
import xml.etree.ElementTree as ET, glob, re
NS = '{http://maven.apache.org/POM/4.0.0}'
KEEP = re.compile(r'^(org\.springframework|jakarta\.|javax\.|org\.hibernate|io\.micrometer|io\.projectreactor|com\.fasterxml\.jackson|org\.springdoc|com\.querydsl|org\.flywaydb|org\.liquibase|org\.apache\.tomcat|org\.eclipse\.jetty|io\.undertow)\.')
for pom in glob.glob('$PROJECT_ROOT/**/pom.xml', recursive=True):
    if '/target/' in pom: continue
    try:
        root = ET.parse(pom).getroot()
        for dep in root.iter(NS + 'dependency'):
            g = dep.find(NS + 'groupId'); a = dep.find(NS + 'artifactId')
            if g is not None and a is not None:
                gav = f'{g.text.strip()}:{a.text.strip()}'
                if KEEP.match(gav): print(gav)
    except: pass
" 2>/dev/null | sort -u
# Example output: org.springframework.boot:spring-boot-starter-security
```

### Gradle — build.gradle / build.gradle.kts (produces groupId:artifactId)

```bash
grep -rh --include="build.gradle" --include="build.gradle.kts" \
  -oP "(?<=[\"'])[a-zA-Z][\w.-]+:[a-zA-Z][\w.-]+:[^\s\"']+" \
  "$PROJECT_ROOT" 2>/dev/null \
  | awk -F: '{print $1":"$2}' \
  | grep -E '^(org\.springframework|jakarta\.|javax\.|org\.hibernate|io\.micrometer|io\.projectreactor|com\.fasterxml\.jackson|org\.springdoc|com\.querydsl|org\.flywaydb|org\.liquibase|org\.apache\.tomcat|org\.eclipse\.jetty|io\.undertow):' \
  | sort -u
# Example output: org.springframework.boot:spring-boot-starter-data-jpa
```

---

## Angular (TypeScript) — Optional grep/node Fast Path

**Allow-list packages.** `@angular/` and `@ngrx/` alone are too narrow — they drop three
package families that carry real migration rules: `rxjs` (major bumps with breaking
operator/Observable changes track Angular majors), `zone.js` (directly implicated by the
zoneless change-detection shift in Angular 18→19+), and the tooling line
(`@angular-devkit`, `@angular-eslint` for the TSLint→ESLint migration, `@nguniversal` →
`@angular/ssr`, `@nx`/legacy `@nrwl` for monorepos), plus `typescript`/`tslib` as toolchain pins:

```
@angular/ | @ngrx/ | @angular-devkit/ | @angular-eslint/ | @nguniversal/
@nx/ | @nrwl/ | rxjs | zone.js | tslib | typescript
```

### Import extraction (produces exact npm package name)

```bash
grep -rh --include="*.ts" \
  -oP "(?<=from ')[^']+" \
  "$PROJECT_ROOT/src" 2>/dev/null \
  | grep -v '^\.' \
  | sed "s|^\(@[^/]*/[^/]*\)/.*|\1|; s|^\([^@][^/]*\)/.*|\1|" \
  | grep -E '^(@angular/|@ngrx/|@angular-devkit/|@angular-eslint/|@nguniversal/|@nx/|@nrwl/|rxjs$|zone\.js$|tslib$|typescript$)' \
  | sort -u
# Example output: @angular/common, @ngrx/store, rxjs, zone.js
# Handles scoped packages (@angular/common/http → @angular/common)
```

### package.json dependencies (produces exact npm package name)

```bash
node -e "
  const p = require('$PROJECT_ROOT/package.json');
  const all = { ...p.dependencies, ...p.devDependencies, ...p.peerDependencies };
  const keep = /^(@angular\/|@ngrx\/|@angular-devkit\/|@angular-eslint\/|@nguniversal\/|@nx\/|@nrwl\/|rxjs$|zone\.js$|tslib$|typescript$)/;
  console.log(Object.keys(all).filter(k => keep.test(k)).join('\n'));
" 2>/dev/null | sort -u

# Fallback (no node)
python3 -c "
import json, re
p = json.load(open('$PROJECT_ROOT/package.json'))
keep = re.compile(r'^(@angular/|@ngrx/|@angular-devkit/|@angular-eslint/|@nguniversal/|@nx/|@nrwl/|rxjs$|zone\.js$|tslib$|typescript$)')
for k in {**p.get('dependencies',{}), **p.get('devDependencies',{}), **p.get('peerDependencies',{})}:
    if keep.match(k): print(k)
" 2>/dev/null | sort -u
# Example output: @angular/core, @angular/common, rxjs, zone.js
```

### NgModule imports (produces simple class name)

```bash
grep -rh --include="*.ts" \
  -oP '[A-Z][A-Za-z]+Module(?=\b)' \
  "$PROJECT_ROOT/src" 2>/dev/null \
  | sort -u
# Example output: HttpClientModule, RouterModule, FormsModule
```

---

## WildFly / JBoss (Java + server XML) — Python-canonical for XML, optional grep for Java imports

WildFly and JBoss EAP are Jakarta EE application servers. JBoss EAP is the downstream
commercial build of WildFly; the **scanning patterns are identical** — only the version
catalogue and framework string differ (confirm the exact `framework` value stored in the
graph; e.g. `"WildFly"` vs `"JBoss EAP"`).

**Key boundary:** the `javax.* → jakarta.*` namespace flip (WildFly 27 / JBoss EAP 8,
Jakarta EE 10 — *verify against upstream*). It is the same change as Spring Boot's `2.x → 3.x`
boundary but far more pervasive, since the whole programming model lives in `jakarta.*`. Both
`javax.` and `jakarta.` are already in the allow-list below.

**The critical difference from Spring Boot:** almost none of the migration-relevant
configuration is reachable from Java code — it lives in **server XML**. There is no
Spring-style `.properties`/`.yml`. So the WildFly scanner is mostly an XML parser
(`standalone.xml` / `domain.xml` / `persistence.xml`) plus the normal Java import pass.

**Allow-list prefixes (Java imports & deps):**

```
jakarta. | javax. | org.hibernate | io.undertow | org.infinispan | org.jgroups
org.jboss | org.wildfly | org.eclipse.microprofile
```

### Java import extraction (produces FQCN)

```bash
grep -rh --include="*.java" --include="*.kt" \
  -oP '(?<=^import )(static )?[\w.]+' \
  "$PROJECT_ROOT/src/main" 2>/dev/null \
  | sed 's/^static //' \
  | grep -E '^(jakarta\.|javax\.|org\.hibernate|io\.undertow|org\.infinispan|org\.jgroups|org\.jboss|org\.wildfly|org\.eclipse\.microprofile)\.' \
  | sort -u
# Example output: org.jboss.as.clustering.controller.CommonUnaryRequirement  (→ Class node)
```

Annotation extraction reuses the fixed Spring/Kotlin annotation extractor above (Jakarta EE
annotations such as `Stateless`, `Inject`, `Path`, `Entity` are captured by simple name; their
owning `jakarta.*` packages are also captured by the import pass).

### Server config — subsystem keys from `standalone.xml` / `domain.xml`

The graph stores server config on `ApplicationProperty` nodes using a flattened convention:
`subsystem.<name>.<resource-path>`, where **named resource instances are replaced by `*`**
(e.g. `subsystem.infinispan.cache-container.*.distributed-cache.locking.lock-timeout`).

The exact placement of `*` versus a dropped instance name is **not fully determined** by the
current (sparse) graph data — e.g. `cache-container` becomes `*` while a sibling named
resource may be dropped. Because matching is exact-string, a single wrong guess yields silent
zero matches. **Robust approach: emit every `*`/dropped combination at the named-instance
positions** (the powerset). The graph holds only a handful of WildFly keys, so over-emitting
harmless candidates is cheap and guarantees the stored form is hit.

```bash
python3 -c "
import xml.etree.ElementTree as ET, glob, re, itertools
def local(t): return t.split('}', 1)[-1]
def ss_name(t):
    m = re.match(r'\{urn:jboss:domain:([^:}]+)', t)   # subsystem name lives in the xmlns urn
    return m.group(1) if m else None
out = set()
def walk(elem, types, named):
    for child in elem:
        nm = local(child); has_name = child.get('name') is not None
        t2, n2 = types + [nm], named + [has_name]
        idxs = [i for i, was in enumerate(n2) if was]
        for combo in itertools.product(*[['*', None]] * len(idxs)):
            sub = dict(zip(idxs, combo)); parts = []
            for i, seg in enumerate(t2):
                parts.append(seg)
                if sub.get(i) == '*': parts.append('*')
            key = 'subsystem.' + '.'.join(parts)
            out.add(key)
            for a in child.attrib:
                if a != 'name': out.add(key + '.' + a)
        walk(child, t2, n2)
for cfg in glob.glob('$PROJECT_ROOT/**/standalone*.xml', recursive=True) \
         + glob.glob('$PROJECT_ROOT/**/domain*.xml', recursive=True):
    try:
        for ss in ET.parse(cfg).getroot().iter():
            if local(ss) == 'subsystem' and ss_name(ss.tag):
                walk(ss, [ss_name(ss.tag)], [False])
    except: pass
print('\n'.join(sorted(out)))
" 2>/dev/null | sort -u
# Example output: subsystem.infinispan.cache-container.*.distributed-cache
```

> Emitting every attribute inflates the entity count; rely on the prioritization tier
> (below) to keep subsystem keys, and consider skipping attributes whose parent element
> matched nothing. As WildFly graph coverage grows, re-run `MATCH (p:ApplicationProperty)
> WHERE p.name STARTS WITH 'subsystem.' RETURN p.name` — if a clean `*` rule emerges, replace
> the powerset with the canonical form. The real fix is for the graph populator to document
> the `*` placement rule so the scanner need not brute-force it.

### Extension modules from `<extension module="…"/>`

Extension module identifiers look like Java packages but are stored as `ApplicationProperty`,
**not** `Class`. The source file disambiguates the bucket: a string like
`org.wildfly.extension.x` is a *property* when it comes from an `<extension>` element, and a
*Class* only when it comes from a Java `import`. Route by source, never by string shape.

```bash
grep -rhoP '(?<=<extension module=")[^"]+' \
  $(find "$PROJECT_ROOT" -name 'standalone*.xml' -o -name 'domain*.xml') 2>/dev/null \
  | sort -u
# Example output: org.wildfly.extension.picketlink   (→ ApplicationProperty node)
```

### Persistence properties from `persistence.xml`

```bash
grep -rhoP '(?<=<property name=")[^"]+' \
  $(find "$PROJECT_ROOT" -name 'persistence.xml') 2>/dev/null \
  | sort -u
# Example output: hibernate.cache.region.factory_class, wildfly.jpa.bytecodeenhancement
```

> Detection of WildFly/JBoss as the active framework (presence of
> `jboss-deployment-structure.xml`, `standalone.xml`, or an `org.wildfly.bom` import) and the
> WildFly/JBoss version catalogue belong in the version-map file, not here.

---

## Entity Prioritization (enforced cap)

Filtering happens at extraction (above), so the surviving set is already framework-only. This
step is the **enforced cap and ordering** applied to that filtered set — it always runs (it is
not a >200-only trim), and it does **not** pad with noise. There is no "everything else" tier:
if the filtered set is under the cap, keep all of it; sixty high-signal entities beat two
hundred diluted ones.

Pipeline order: union all extractor outputs → assign each entity its highest matching tier →
stable-sort by tier → keep the top `N` (default `N = 200`, configurable) → log the trim.

| Tier | Condition | Frameworks |
|---|---|---|
| 1 | FQCN starts with `org.springframework`, `jakarta.`, `javax.` | Spring, WildFly |
| 2 | FQCN starts with `org.hibernate`, `io.micrometer`, `io.projectreactor`, `com.fasterxml.jackson`, `tools.jackson`, `org.thymeleaf` | Spring |
| 3 | WildFly: `subsystem.*` keys, extension modules, FQCN `org.jboss`/`org.wildfly`/`org.infinispan`/`org.jgroups`, `org.eclipse.microprofile` | WildFly |
| 4 | Framework annotations (simple names that survived the noise filter) | Spring, WildFly |
| 5 | Build deps in the dependency allow-list | all |
| 6 | Angular packages (`@angular/`, `@ngrx/`, `rxjs`, `zone.js`, tooling) | Angular |
| 7 | Spring/JPA properties (`spring.`, `server.`, `management.`, `hibernate.`, `wildfly.jpa.`) | Spring, WildFly |

If even the filtered set exceeds `N`, trim from the lowest occupied tier, alphabetically, and
log: `"Trimmed M entities — kept tiers 1–K (cap N)."` Test-scope entities are tracked in a
separate list (tier 4 / deferred) and do not consume the main cap.

---

## Multi-Module Detection

```bash
# Maven — count sub-modules
find "$PROJECT_ROOT" -name "pom.xml" -not -path "*/target/*" | wc -l

# Gradle — count build files
find "$PROJECT_ROOT" -name "build.gradle*" -not -path "*/.gradle/*" | wc -l
```

If count > 1, scan each module separately using the patterns above, then union all results and
**dedupe once across the union** (`sort -u` on the combined set) before forming
`$ALL_ENTITIES` — per-module `sort -u` does not remove cross-module duplicates, which would
otherwise inflate the count against the cap. Note in the output which modules were scanned and
how many entities each contributed.