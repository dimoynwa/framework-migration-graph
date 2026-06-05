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
structured JSON array of entities. Each entity represents a distinct change that an upgrading user
must understand, act on, or verify.

---

## Inputs

- **Document**: A structured changelog (Markdown table, Jira-export, plain text release notes,
  or similar). Attached as a file or pasted inline.
- **Framework / Platform name** (optional): e.g. `WildFly`, `Spring Boot`, `Quarkus`. Infer from
  the document if not stated.

If the user hasn't attached a file and hasn't pasted content, ask once: "Please attach or paste
the changelog document you'd like me to analyze."

---

## Output

Return **only** a valid JSON object. No markdown fences, no prose before or after, no trailing
commas, double quotes everywhere:

```json
{
  "entities": [
    {
      "change_type": "string",
      "reason_type": "string",
      "reason": "string",
      "action_step": "string",
      "affected_properties": ["string"],
      "replacement_property": "string",
      "affected_classes": ["string"],
      "replacement_class": "string",
      "affected_dependencies": ["string"],
      "replacement_dependency": "string",
      "cli_operation": "string",
      "subsystem": "string"
    }
  ]
}
```

---

## Field Reference

### `change_type` (REQUIRED)
One of:
- `breaking_change` — removes or fundamentally alters an API, config, or behavior
- `mandatory_migration` — confirmed required action for upgrade
- `dependency_upgrade` — library/component version bump with potential user impact
- `deprecation` — feature or API marked for future removal
- `behavior_change` — same API/config but different runtime behavior
- `configuration_change` — subsystem or property rename/restructure
- `namespace_migration` — package/namespace rename (e.g. javax → jakarta)
- `informational` — notable but no action required
- `other`

Map source labels: `"breaking"` → `breaking_change`, `"mandatory_migration"` → `mandatory_migration`,
`"behavioral"` → `behavior_change`, `"dependency_upgrade"` → `dependency_upgrade`.

### `reason_type` (OPTIONAL)
Infer from context. One of: `security`, `performance`, `spec_compliance`, `dependency_alignment`,
`bugfix`, `other`, or `""` if unclear.

### `reason` (REQUIRED)
1–3 sentences covering: what changed, why it matters for upgraders, and what migration risk or
compatibility impact it may introduce.

### `action_step` (IMPORTANT)
Concrete, specific migration steps. Must state:
- **What** to change (property name, class, dependency, config block)
- **How** to change it (rename to X, update version to Y, remove Z)
- **Why** the change is needed (what break or risk it addresses)
- **How to validate** — always specific: "run X and confirm Y", never just "validate compatibility"

If no clear action is stated in the source, provide the best-effort step grounded in the change.
Use `""` only if truly no actionable step can be inferred.

**Good examples:**
- "Replace `javax.*` imports with `jakarta.*`, update Maven dependencies to Jakarta-compatible
  versions, and recompile to surface unresolved API usage."
- "Update `io.vertx:vertx-core` to 4.5.24 in your dependency management. Run reactive messaging
  integration tests and confirm no `CVE-2026-1002`-related errors appear."
- "Set `maximum-failed-authentications` on affected Elytron realms. Run auth tests with multiple
  bad-password scenarios and confirm legitimate users are not locked out."

**Bad examples (do not write these):**
- "Review your configuration."
- "Validate compatibility."
- "Check if this affects you."

### `affected_dependencies`
Use Maven coordinates (`groupId:artifactId`) when possible, otherwise clear component names.

### `replacement_dependency`
Include version if specified. Example: `"org.infinispan:infinispan-core:14.0.17.Final"`.

### `affected_properties` / `affected_classes` / `subsystem`
Populate only when explicitly implied by the change. Use empty arrays `[]` or `""` otherwise.

### `cli_operation`
Include only if exact CLI commands appear in the source text.

---

## Extraction Strategy

### 1. Prioritize high-signal changes
Focus on:
- Breaking changes and mandatory migrations first
- Removals (dependency removed, feature dropped, namespace gone)
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

**Exception:** If a test fix reveals a previously hidden behavioral bug that affected production
(e.g. session manager invoked outside ControlPoint), include it as a `behavior_change`.

### 4. Self-contained entities
Each entity must be understandable without external context. Spell out component names, JIRA IDs
are not needed in output fields (they may inform the reason but should not be the reason itself).

### 5. Prefer fewer, high-value entities
Aim for signal over noise. A well-written entity covering a grouped set of related Vert.x
dependency bumps is more useful than five near-identical entries.

---

## Quality Checklist (apply before outputting)

- [ ] Every entity has a non-empty `change_type` and `reason`
- [ ] `action_step` is specific — no vague "review" or "validate" without follow-up detail
- [ ] Security CVEs are `mandatory_migration` with `reason_type: security`
- [ ] Removed dependencies have `replacement_dependency: ""` and a clear action_step explaining
      what to do instead
- [ ] No test-only, CI-only, or doc-only entries unless they carry production impact
- [ ] JSON is valid — no trailing commas, all strings double-quoted, arrays properly closed
- [ ] Output is ONLY the JSON object — no surrounding markdown, no explanations

---

## Example Trigger Phrases

- "Here's the WildFly changelog, extract migration entities"
- "Analyze this release notes file and give me the breaking changes"
- "I'm upgrading from version X to Y, what do I need to change?" (with doc attached)
- "Turn this changelog into structured migration JSON"
- "What changed between these two versions?" (with diff/changelog attached)
