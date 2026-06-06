---
name: changelog-migration-extractor
description: >
  Analyzes structured changelog or release-notes documents (attached as files or pasted as text) for
  software platforms and frameworks (e.g. WildFly, Spring Boot, Quarkus, Keycloak, Infinispan) and
  extracts ALL migration-impacting changes as a structured JSON array of entities. Use this skill
  whenever a user attaches or pastes a changelog, release notes, or Jira-derived diff document and
  asks to extract migration changes, breaking changes, upgrade steps, or produce a structured
  migration report. Also trigger when the user says things like "analyze this changelog", "extract
  migration changes", "what do I need to change to upgrade", or "turn this into migration entities".
  Always use this skill when both a document (file upload or pasted text) and a framework/platform
  name are present together, even if the user's wording is casual.
---

# Changelog Migration Extractor

Extracts migration-impacting changes from changelog or release-note documents and outputs a
structured JSON object matching the `MigrationEntitiesBatch` schema used by the Migration Oracle
graph population pipeline. Each entity represents a distinct change that an upgrading developer
must understand, act on, or verify.

---

## Internet research

Before writing `steps[].instruction` and `steps[].summary`, search the internet for authoritative
migration guidance whenever the source text is thin, ambiguous, or references an API without
explaining how to migrate it. Do not skip this step because a change "looks obvious".

**Search targets (in priority order):**
1. Official framework migration guides (e.g. Spring Boot 3.x Migration Guide, Angular Update
   Guide, WildFly Migration Guide, Hibernate ORM Migration Guide)
2. Official API Javadoc or TypeDoc for the removed and replacement types
3. GitHub issues, release notes, or PR descriptions linked from the JIRA key or source URL
4. Stack Overflow accepted answers or highly-voted answers for the specific API change

**Use search findings to:**
- Confirm the exact replacement API, class name, or configuration key
- Fill in any method signatures, annotation parameters, or config block structure that the
  source text omits
- Identify co-required changes not mentioned in the source (e.g. a class replacement that
  also requires a new Maven dependency)
- Write a `verification` signal that is observable without ambiguity

If search results confirm the source text, proceed. If search results contradict or meaningfully
extend the source text, use the richer information but note it came from external research
(you may include a parenthetical in `instruction`, e.g. "per Spring Boot 3.2 migration guide").

Do not invent information that cannot be found in either the source document or search results.

---

## Inputs

- **Document**: A structured changelog (Markdown table, Jira-export, plain text release notes,
  pre-filtered Migration Oracle Markdown, or similar). Attached as a file or pasted inline.
- **Framework / Platform name** (optional): e.g. `WildFly`, `Spring Boot`, `Quarkus`. Infer from
  the document if not stated.

Two input forms are accepted:

**Form A — Pre-filtered Migration Oracle Markdown** (output of Phase 5 filter-and-group call):
Sections are headed with emoji (`## 🔴 Breaking Changes`, `## 🟠 Mandatory Migrations`, etc.) and
each section contains a Markdown table with `# | JIRA | Title | Impact` columns. Read
`source_section` directly from the emoji heading.

**Form B — Raw changelog** (GitHub release notes, Jira export, plain prose, Red Hat docs):
No emoji section structure. Infer `source_section`, `title`, and `jira_keys` from the content
itself. Classify severity using the impact of the change as described below.

If the user hasn't attached a file and hasn't pasted content, ask once: "Please attach or paste
the changelog document you'd like me to analyze."

---

## Output

Return **only** a valid JSON object matching `MigrationEntitiesBatch`. No markdown fences, no
prose before or after, no trailing commas, double quotes everywhere:

```json
{
  "entities": [
    {
      "source_section": "breaking_change",
      "title": "string",
      "jira_keys": ["string"],
      "source_url": "string",
      "change_type": "string",
      "reason_type": "string",
      "reason": "string",
      "scopes": [
        { "scope": "api-surface", "severity": "critical" }
      ],
      "entities": [
        { "kind": "class", "name": "string", "role": "removed" }
      ],
      "steps": [
        {
          "index": 0,
          "step_type": "remove",
          "summary": "string",
          "instruction": "string",
          "effort": "moderate",
          "automatable": false,
          "requires": [],
          "verification": "string",
          "cli_operation": ""
        }
      ],
      "subsystem": ""
    }
  ]
}
```

---

## Field Reference

### `source_section` (REQUIRED)

Exactly one of the following string literals:

| Value | Meaning |
|---|---|
| `breaking_change` | Public API, class, or fundamental behaviour removed or incompatibly altered |
| `security_fix` | CVE fix or security vulnerability resolved |
| `component_upgrade` | Major component / dependency version bump with migration impact |
| `security_config` | Security configuration change required to upgrade |
| `behavioral` | Same API but different runtime behaviour; or notable new capability |
| `deprecation` | Feature or API marked for future removal |
| `new_capability` | New feature with no breaking impact (informational) |

**For Form A inputs:** Copy from the section emoji heading using this map:
`🔴` → `breaking_change` | `🟠 Security & CVE` → `security_fix` |
`🟠 Major Component` → `component_upgrade` | `🟠 Security Configuration` → `security_config` |
`🟡 Behavioral` → `behavioral` | `🟡 Deprecations` → `deprecation` |
`🔵 New Capabilities` → `new_capability`

**For Form B inputs:** Assign based on the change's impact:
- Removal of a public class, method, or API → `breaking_change`
- CVE number present → `security_fix`
- Configuration key renamed or removed → `breaking_change` (if required) or `behavioral`
- Feature marked deprecated → `deprecation`
- Default behaviour changed → `behavioral`
- New optional feature → `new_capability`

### `title` (REQUIRED)

For Form A: Copy the `Title` column verbatim. Do not paraphrase. Maximum 15 words.
For Form B: Write a concise label for the change. Maximum 15 words.

### `jira_keys` (REQUIRED, may be empty list)

For Form A: Copy the `JIRA` column. Split on comma. Strip whitespace. `"N/A"` → `[]`.
For Form B: Extract any Jira-style issue keys (e.g. `WFLY-12345`, `SPR-18552`) found in the
text. Empty list if none present.

### `source_url` (REQUIRED, may be empty string)

URL of the source document, release page, or GitHub tag. Empty string if not available.

### `change_type` (REQUIRED)

One of: `breaking_change`, `mandatory_migration`, `dependency_upgrade`, `deprecation`,
`behavior_change`, `configuration_change`, `namespace_migration`, `informational`, `other`.

Use `source_section` as the primary signal — do not contradict it. Mapping:
- `breaking_change` → `breaking_change`
- `security_fix` or `security_config` → `mandatory_migration`
- `component_upgrade` → `dependency_upgrade` (or `mandatory_migration` if migration steps are required)
- `deprecation` → `deprecation`
- `behavioral` or `new_capability` → `behavior_change` or `informational`

### `reason_type` (OPTIONAL)

Infer from context. One of: `security`, `performance`, `spec_compliance`,
`dependency_alignment`, `bugfix`, `other`, or `""` if unclear.

### `reason` (REQUIRED)

1–3 sentences: what changed, why it matters for upgraders, and what migration risk or
compatibility impact it may introduce. Do not invent. Use only information present in the
source text.

### `scopes` (REQUIRED, at least one entry)

Array of `{ "scope": string, "severity": string }` objects assessing the blast radius.

`scope` values:
- `api-surface` — public API or class removed/changed; callers of this code are affected
- `runtime` — default behaviour or lifecycle changed; no API change
- `config` — `application.yml` / `application.properties` keys only; no compiled code change
- `build` — `pom.xml`, `build.gradle`, dependency coordinates, or plugin configuration
- `test` — test code or test configuration only

`severity` values:
- `critical` — will definitely cause compilation or startup failure without migration
- `high` — likely causes failure in most configurations
- `medium` — may cause failure in some configurations
- `low` — unlikely to cause failure but requires attention

A single change may have multiple scope entries (e.g. a class removal that also requires a
`pom.xml` update would have both `api-surface/critical` and `build/high`).

### `entities` (array, may be empty)

One entry per class, property, or dependency named in the source text. Do not invent names
not present in the text.

| Field | Type | Values | Description |
|---|---|---|---|
| `kind` | string | `class` \| `property` \| `dependency` | Type of artifact |
| `name` | string | FQCN / dotted key / `groupId:artifactId` | Exact name of the artifact |
| `role` | string | `removed` \| `replacement` \| `co-required` \| `mentioned` | Role in this change |

**Role assignment rules:**
- `removed` — the source says this entity is removed, deleted, eliminated, or no longer available
- `replacement` — the source says to use this instead, or this replaces the removed entity
- `co-required` — the source says this must also be configured, injected, or added alongside the replacement
- `mentioned` — the entity is named but none of the above apply; use sparingly, omit if it adds no information

Use FQCNs for classes (e.g. `org.springframework.security.config.annotation.web.configuration.WebSecurityConfigurerAdapter`).
Use dotted keys for properties (e.g. `spring.datasource.url`).
Use `groupId:artifactId` for dependencies (e.g. `io.vertx:vertx-core`).

### `steps` (array, may be empty — but populate whenever actionable steps exist)

Ordered, atomic migration actions. One step = one atomic action that can be verified
independently.

| Field | Type | Required | Description |
|---|---|---|---|
| `index` | integer | Yes | 0-based position in this entity's step sequence |
| `step_type` | string | Yes | `remove` \| `rename` \| `replace` \| `configure` \| `verify` \| `namespace` |
| `summary` | string | Yes | Ten words or fewer — what this step does. Use the specific API or property name, not a generic label. |
| `instruction` | string | Yes | Full concrete action enriched by internet research. State the exact class name, method signature, property key, or dependency coordinate to change; the exact replacement; and any co-required changes. Must not be vague. |
| `effort` | string | Yes | `mechanical` \| `moderate` \| `architectural` |
| `automatable` | boolean | Yes | True only if a tool can apply this step without any human judgement |
| `requires` | integer[] | Yes | Indices of prerequisite steps within this entity. Empty list if none. |
| `verification` | string | Yes | Observable signal that confirms this step succeeded. Must not be vague. |
| `cli_operation` | string | No | WildFly CLI fragment only. Empty string for Spring Boot and Angular. |

**Effort levels:**
- `mechanical` — a tool can apply this without human judgement. A property rename, a package
  import update, a single-line config change. Safe to auto-apply via OpenRewrite.
- `moderate` — a developer must review and apply the change, but the action is well-defined.
  A method refactor, a multi-file class restructure, a security config pattern update.
- `architectural` — a design decision is required. Replacing a security model, restructuring a
  persistence layer, migrating an API surface.

**Step decomposition guidance:**
- If the source describes two sequential actions (remove X, then add Y) → two steps, second has `requires: [0]`
- If the source describes parallel actions → two steps, both with `requires: []`
- Do not invent steps not supported by the source text
- Mark `automatable: true` only for steps of type `rename`, `namespace`, or `configure` where the change is purely mechanical

**Good instruction examples:**
- "Rename `spring.datasource.url` to `spring.datasource.jdbc-url` in all `application*.yml` and `application*.properties` files. If you use Spring Boot's auto-configured `DataSource`, no Java code change is needed — only the key rename. If you configure `DataSourceProperties` manually, update the setter call to `setJdbcUrl()`. Per Spring Boot 3.2 migration guide."
- "Remove the class that extends `WebSecurityConfigurerAdapter`. Copy the body of `configure(HttpSecurity http)` — it will move into a new `@Bean` method. Create a `@Configuration` class with a `@Bean SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception` method. Port security rules from the removed `configure()` body into `http.authorizeHttpRequests(...)`. Add `@EnableWebSecurity` to the configuration class if it was on the removed adapter class. Per Spring Security 6.0 migration guide."
- "Add `org.springframework.boot:spring-boot-starter-actuator` to your `pom.xml` or `build.gradle` if not already present. Set `management.endpoints.web.exposure.include=health,info` in `application.properties`. The `/actuator/health` endpoint now returns a 200 with `{ \"status\": \"UP\" }` without authentication by default — verify that your security config does not restrict it."

**Bad instruction examples (do not write these):**
- "Review your configuration."
- "Validate compatibility."
- "Check if this affects you."
- "Update the security configuration." (too vague — name the class and the exact change)

**Good verification examples:**
- "Compilation succeeds and no import of `WebSecurityConfigurerAdapter` remains in the codebase."
- "Application starts without `NoSuchBeanDefinitionException`. GET /actuator/health returns 200."
- "No `javax.*` imports remain. All tests pass."

**Bad verification examples (do not write these):**
- "Test the application."
- "Validate the change."

### `subsystem` (REQUIRED, empty string for non-WildFly)

WildFly subsystem name (`undertow`, `elytron`, `messaging`, `datasources`, etc.).
Empty string `""` for Spring Boot and Angular.

---

## Extraction Strategy

### 1. Prioritize high-signal changes
Focus on:
- Breaking changes and mandatory migrations first
- Removals (class removed, dependency removed, feature dropped, namespace gone)
- Security fixes (CVEs) — always `mandatory_migration` + `reason_type: security`
- Core platform / persistence / messaging / networking / serialization upgrades

### 2. Group repetitive dependency bumps
Multiple upgrades of the same component → single entity with the highest/final version.
Multiple CVE-driven upgrades of unrelated components → one entity each (security is always
individual).

### 3. Ignore noise
Skip entries that are exclusively about:
- Internal test fixes with no user-facing impact
- CI/CD pipeline changes
- Documentation-only updates
- Quickstart/sample app changes

**Exception:** If a test fix reveals a previously hidden behavioral bug that affected production,
include it as `behavioral`.

### 4. Self-contained entities
Each entity must be understandable without external context. Spell out component names. JIRA IDs
may inform the `reason` text but must not be the reason itself.

### 5. Prefer fewer, high-value entities
Aim for signal over noise. A well-written entity covering a grouped set of related Vert.x
dependency bumps is more useful than five near-identical entries.

---

## Quality Checklist (apply before outputting)

- [ ] Every entity has a non-empty `source_section`, `title`, `change_type`, and `reason`
- [ ] `source_section` is one of the seven valid literals — never invented
- [ ] Every entity has at least one `scopes` entry with valid `scope` and `severity` values
- [ ] Internet research was performed for every step where the source text was thin or omitted exact API names
- [ ] `steps[].summary` names the specific API, property, or artifact — not a generic label like "Update configuration"
- [ ] `steps[].instruction` names exact class names, method signatures, property keys, and coordinates — no vague "review" or "update" without the specific target
- [ ] `steps[].verification` is observable — something a test or the developer can confirm
- [ ] Security CVEs → `source_section: "security_fix"`, `change_type: "mandatory_migration"`, `reason_type: "security"`
- [ ] `entities[].name` uses FQCN / dotted key / `groupId:artifactId` — no short names where full names are available
- [ ] `role: "removed"` entities have a corresponding `role: "replacement"` entity when a replacement is named in the source
- [ ] No test-only, CI-only, or doc-only entries unless they carry production impact
- [ ] `subsystem` is empty string for Spring Boot and Angular
- [ ] JSON is valid — no trailing commas, all strings double-quoted, arrays properly closed
- [ ] Output is ONLY the JSON object — no surrounding markdown, no explanations

---

## Example Trigger Phrases

- "Here's the WildFly changelog, extract migration entities"
- "Analyze this release notes file and give me the breaking changes"
- "I'm upgrading from version X to Y, what do I need to change?" (with doc attached)
- "Turn this changelog into structured migration JSON"
- "What changed between these two versions?" (with diff/changelog attached)
- "Run the extractor on this pre-filtered Migration Oracle Markdown"
