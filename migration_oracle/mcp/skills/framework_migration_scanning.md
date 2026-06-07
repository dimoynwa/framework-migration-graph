# Scanning Reference
 
Full patterns for extracting entities in the exact formats the knowledge graph expects.
 
## Entity Format Quick Reference
 
| Entity type | Graph expects | Bash produces |
|---|---|---|
| Java class | `org.springframework.security.config.annotation.web.configuration.WebSecurityConfigurerAdapter` | Full import line, keep as-is |
| Kotlin class | `org.springframework.security.config.annotation.web.configuration.WebSecurityConfigurerAdapter` | Full import line, keep as-is |
| Java annotation | `EnableWebSecurity` | Strip `@`, keep simple name |
| Spring property | `spring.datasource.url` | Full dotted key, no truncation |
| Maven dep | `org.springframework.boot:spring-boot-starter-security` | `groupId:artifactId`, drop version |
| Gradle dep | `org.springframework.boot:spring-boot-starter-security` | `groupId:artifactId`, drop version |
| npm package | `@angular/common` | Exact package name from import/package.json |
 
---
 
## Spring Boot (Java / Kotlin)
 
### Import extraction — Java (produces FQCN)
```bash
# Keep the FULL dotted path — do NOT strip to simple name
grep -rh --include="*.java" \
  -oP '(?<=^import )(static )?[\w.]+' \
  "$PROJECT_ROOT/src/main/java" "$PROJECT_ROOT/src/test/java" 2>/dev/null \
  | sed 's/^static //' \
  | grep '\.' \
  | sort -u
# Example output: org.springframework.security.config.annotation.web.configuration.WebSecurityConfigurerAdapter
```
 
### Import extraction — Kotlin (produces FQCN)
```bash
grep -rh --include="*.kt" \
  -oP '(?<=^import )[\w.]+' \
  "$PROJECT_ROOT/src" 2>/dev/null \
  | grep '\.' \
  | grep -v '\*$' \
  | sort -u
# Example output: org.springframework.boot.autoconfigure.SpringBootApplication
```
 
### Annotation extraction — Java + Kotlin (produces simple name, no @)
```bash
# Graph indexes annotations by simple name without @ prefix
grep -rh --include="*.java" --include="*.kt" \
  -oP '(?<=@)[A-Z][A-Za-z]+' \
  "$PROJECT_ROOT/src" 2>/dev/null \
  | sort -u
# Example output: EnableWebSecurity
# NOT: @EnableWebSecurity
```
 
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
 
## Spring Boot — Dependencies
 
### Maven — pom.xml (produces groupId:artifactId)
 
```bash
# Pair groupId and artifactId lines — they alternate in <dependency> blocks
python3 -c "
import xml.etree.ElementTree as ET, glob
ns = {'m': 'http://maven.apache.org/POM/4.0.0'}
for pom in glob.glob('$PROJECT_ROOT/**/pom.xml', recursive=True):
    if '/target/' in pom: continue
    try:
        root = ET.parse(pom).getroot()
        for dep in root.iter('{http://maven.apache.org/POM/4.0.0}dependency'):
            g = dep.find('{http://maven.apache.org/POM/4.0.0}groupId')
            a = dep.find('{http://maven.apache.org/POM/4.0.0}artifactId')
            if g is not None and a is not None:
                print(f'{g.text.strip()}:{a.text.strip()}')
    except: pass
" 2>/dev/null | sort -u
# Example output: org.springframework.boot:spring-boot-starter-security
 
# Bash fallback (less reliable for multi-module, but works for single pom.xml)
paste -d: \
  <(grep -oP '(?<=<groupId>)[^<]+' "$PROJECT_ROOT/pom.xml") \
  <(grep -oP '(?<=<artifactId>)[^<]+' "$PROJECT_ROOT/pom.xml") \
  2>/dev/null | grep '\.' | sort -u
```
 
### Gradle — build.gradle / build.gradle.kts (produces groupId:artifactId)
 
```bash
# Extract groupId:artifactId:version, then drop the version segment
grep -rh --include="build.gradle" --include="build.gradle.kts" \
  -oP "(?<=[\"'])[a-zA-Z][\w.-]+:[a-zA-Z][\w.-]+:[^\s\"']+" \
  "$PROJECT_ROOT" 2>/dev/null \
  | awk -F: '{print $1":"$2}' \
  | grep '\.' \
  | sort -u
# Example output: org.springframework.boot:spring-boot-starter-data-jpa
# NOT: spring-boot-starter-data-jpa
```
 
---
 
## Angular (TypeScript)
 
### Import extraction (produces exact npm package name)
 
```bash
grep -rh --include="*.ts" \
  -oP "(?<=from ')[^']+" \
  "$PROJECT_ROOT/src" 2>/dev/null \
  | grep -v '^\.' \
  | sed "s|^\(@[^/]*/[^/]*\)/.*|\1|; s|^\([^@][^/]*\)/.*|\1|" \
  | sort -u
# Example output: @angular/common, rxjs, @ngrx/store
# Handles scoped packages (@angular/common/http → @angular/common)
```
 
### package.json dependencies (produces exact npm package name)
 
```bash
node -e "
  const p = require('$PROJECT_ROOT/package.json');
  const all = { ...p.dependencies, ...p.devDependencies, ...p.peerDependencies };
  console.log(Object.keys(all).join('\n'));
" 2>/dev/null | sort -u
 
# Fallback (no node)
python3 -c "
import json
p = json.load(open('$PROJECT_ROOT/package.json'))
for key in {**p.get('dependencies',{}), **p.get('devDependencies',{}), **p.get('peerDependencies',{})}.keys():
    print(key)
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
 
## Entity Prioritization (when > 200 entities)
 
Rank descending — keep higher tiers first:
 
| Tier | Condition | Keep? |
|---|---|---|
| 1 | FQCN starts with `org.springframework`, `jakarta.`, `javax.` | Always |
| 2 | FQCN starts with `org.hibernate`, `io.micrometer`, `org.thymeleaf` | Always |
| 3 | Annotation: `EnableWebSecurity`, `SpringBootApplication`, `Transactional` etc. | Always |
| 4 | Maven/Gradle dep starts with `org.springframework`, `jakarta.`, `io.` | Always |
| 5 | Angular pkg starts with `@angular/`, `@ngrx/` | Always |
| 6 | Spring property starts with `spring.`, `server.`, `management.` | Always |
| 7 | Everything else | Fill to 200 alphabetically |
 
Apply this ranking, keep top 200, log: "Trimmed N entities — kept tiers 1-N."
 
---
 
## Multi-Module Detection
 
```bash
# Maven — count sub-modules
find "$PROJECT_ROOT" -name "pom.xml" -not -path "*/target/*" | wc -l
 
# Gradle — count build files
find "$PROJECT_ROOT" -name "build.gradle*" -not -path "*/.gradle/*" | wc -l
```
 
If count > 1, scan each module separately using the patterns above, then union
all results before combining into `$ALL_ENTITIES`. Note in the output which
modules were scanned and how many entities each contributed.