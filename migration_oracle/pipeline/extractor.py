"""Entity-extraction LLM call: filtered Markdown → MigrationEntitiesBatch JSON."""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from migration_oracle.models.entities import MigrationEntitiesBatch
from migration_oracle.pipeline._cache import CacheFlags
from migration_oracle.pipeline._llm import (
    LLMInvocationError,
    get_llm,
    invoke_with_retry,
    strip_markdown_fences,
)

EXTRACTION_PROMPT = """You are reading a structured migration changelog (pre-filtered Migration Oracle \
Markdown) for {framework}. It has already been deduplicated and categorised by a prior step. \
Your job is to decompose each table row into a typed, machine-readable entity for graph population.

---

## INTERNET RESEARCH (mandatory)

Before writing steps[].instruction and steps[].verification, search the internet for authoritative \
migration guidance whenever the source text is thin, ambiguous, or references an API without \
explaining how to migrate it. Do not skip this even when a change looks obvious.

Search targets (priority order):
1. Official framework migration guide for this version range
2. Official Javadoc / TypeDoc for removed and replacement types
3. GitHub issues, release notes, or PR descriptions linked from the JIRA key
4. Stack Overflow accepted/highly-voted answers for the specific API change

Use search findings to confirm the exact replacement API, fill in method signatures or config \
structure omitted by the source text, identify co-required changes, and write a verification \
signal that is observable without ambiguity. If findings extend or correct the source text, use \
the richer information (you may add a parenthetical such as "per {framework} migration guide").

---

## FIELD RULES

### source_section
Read the section heading emoji and map it exactly:
  🔴                        → "breaking_change"
  🟠 Security & CVE         → "security_fix"
  🟠 Major Component        → "component_upgrade"
  🟠 Security Configuration → "security_config"
  🟡 Behavioral             → "behavioral"
  🟡 Deprecations           → "deprecation"
  🔵 New Capabilities       → "new_capability"

### title
Copy the Title column verbatim. Do not paraphrase. Maximum 15 words.

### jira_keys
Copy the JIRA column. Split on comma. Strip whitespace. "N/A" → [].

### source_url
URL of the source document or GitHub release page. Empty string if not available.

### change_type
One of: breaking_change | mandatory_migration | dependency_upgrade | deprecation |
        behavior_change | configuration_change | namespace_migration | informational | other

Use source_section as the primary signal:
  breaking_change                    → "breaking_change"
  security_fix or security_config    → "mandatory_migration"
  component_upgrade                  → "dependency_upgrade" (or "mandatory_migration" if steps required)
  deprecation                        → "deprecation"
  behavioral or new_capability       → "behavior_change" or "informational"

### reason_type
Infer from context. One of: security | performance | spec_compliance |
dependency_alignment | bugfix | other | "" (if unclear).

### reason
1–3 sentences: what changed, why it matters for upgraders, and what migration risk it introduces.
Use only information present in the source text. Do not invent.

### scopes
At least one { "scope": ..., "severity": ... } entry.

scope values:
  api-surface — public API or class removed/changed
  runtime     — default behaviour or lifecycle changed; no API change
  config      — application.yml / application.properties keys only
  build       — pom.xml, build.gradle, dependency coordinates, or plugin config
  test        — test code or test configuration only

severity values:
  critical — will definitely cause compilation or startup failure without migration
  high     — likely causes failure in most configurations
  medium   — may cause failure in some configurations
  low      — unlikely to cause failure but requires attention

A single change may have multiple scope entries (e.g. api-surface/critical + build/high).

### entities
One entry per class, property, or dependency named in the source text. Do not invent names.

  kind: "class" | "property" | "dependency"
  name: FQCN (e.g. org.springframework.security.config.annotation.web.configuration.WebSecurityConfigurerAdapter)
        dotted key (e.g. spring.datasource.url)
        groupId:artifactId (e.g. io.vertx:vertx-core)
  role: "removed" | "replacement" | "co-required" | "mentioned"

Role rules:
  removed     — source says this entity is removed, deleted, or no longer available
  replacement — source says to use this instead
  co-required — must also be configured, injected, or added alongside the replacement
  mentioned   — named but none of the above; use sparingly

"removed" entities should have a corresponding "replacement" entry when the source names one.

### steps
Ordered, atomic migration actions. One step = one atomic action verifiable independently.

Fields per step:
  index        — 0-based position in this entity's sequence
  step_type    — "remove" | "rename" | "replace" | "configure" | "verify" | "namespace"
  summary      — ≤10 words naming the specific API, property, or artifact (not a generic label)
  instruction  — Full concrete action enriched by internet research. Name the exact class,
                 method signature, property key, or dependency coordinate to change; the exact
                 replacement; and any co-required changes. Must not be vague.
  effort       — "mechanical" | "moderate" | "architectural"
                   mechanical    — purely mechanical; safe for OpenRewrite auto-apply
                   moderate      — developer must review and apply, but action is well-defined
                   architectural — a design decision is required
  automatable  — true only for rename/namespace/configure steps that are purely mechanical
  requires     — list of prerequisite step indices within this entity. [] if none.
  verification — observable signal that confirms success. Must not be vague.
  cli_operation — WildFly CLI fragment only. Empty string for {framework}.

Step decomposition:
  Two sequential actions (remove X then add Y) → two steps; second has requires: [0]
  Two parallel actions → two steps; both with requires: []
  Do not invent steps not supported by the source text.

GOOD instruction examples:
  "Rename `spring.datasource.url` to `spring.datasource.jdbc-url` in all application*.yml and \
application*.properties files. If you configure DataSourceProperties manually, update the setter \
to setJdbcUrl(). Per Spring Boot 3.2 migration guide."
  "Remove the class extending WebSecurityConfigurerAdapter. Create a @Configuration class with a \
@Bean SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception method. Port \
security rules from configure(HttpSecurity) into http.authorizeHttpRequests(...). Add \
@EnableWebSecurity if it was on the removed adapter. Per Spring Security 6.0 migration guide."

BAD instructions (never write these):
  "Review your configuration."
  "Validate compatibility."
  "Update the security configuration." (too vague — name the class and exact change)

GOOD verification examples:
  "Compilation succeeds and no import of WebSecurityConfigurerAdapter remains in the codebase."
  "Application starts without NoSuchBeanDefinitionException. GET /actuator/health returns 200."

BAD verifications (never write these):
  "Test the application."
  "Validate the change."

### subsystem
Empty string "" for {framework}. (WildFly subsystem names only.)

---

## EXTRACTION STRATEGY

1. Prioritise breaking changes and security fixes first.
2. Group repetitive dependency bumps of the same component into one entity (highest/final version).
   Multiple CVE-driven upgrades of unrelated components → one entity each.
3. Skip entries that are exclusively about internal test fixes, CI/CD, docs, or quickstart samples
   (exception: test fix that reveals a hidden production-affecting bug → include as "behavioral").
4. Each entity must be understandable without external context. Spell out component names.

---

## QUALITY CHECKLIST (apply before outputting)

- Every entity has non-empty source_section, title, change_type, and reason
- source_section is one of the seven valid literals
- Every entity has at least one scopes entry with valid scope and severity
- Internet research performed for every step where source text was thin or omitted exact API names
- steps[].summary names the specific API, property, or artifact — not a generic label
- steps[].instruction names exact class names, method signatures, property keys, coordinates
- steps[].verification is observable
- Security CVEs → source_section: "security_fix", change_type: "mandatory_migration", reason_type: "security"
- entities[].name uses FQCN / dotted key / groupId:artifactId
- role: "removed" entities have a corresponding role: "replacement" when a replacement is named
- No test-only, CI-only, or doc-only entries unless they carry production impact
- subsystem is empty string for {framework}
- JSON is valid — no trailing commas, all strings double-quoted, arrays properly closed
- Output is ONLY the JSON object — no surrounding markdown, no explanations

---

{changes_text}
"""

_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}")


@dataclass(frozen=True)
class ExtractionResult:
    batch: MigrationEntitiesBatch
    artifact_path: Path


def _parse_json_response(text: str) -> MigrationEntitiesBatch:
    cleaned = strip_markdown_fences(text.strip())
    try:
        return MigrationEntitiesBatch.model_validate_json(cleaned)
    except ValidationError:
        match = _JSON_BLOCK_RE.search(cleaned)
        if not match:
            raise
        return MigrationEntitiesBatch.model_validate_json(match.group(0))


def _invoke_structured(filtered_md: str, framework: str) -> MigrationEntitiesBatch:
    llm = get_llm()
    prompt = EXTRACTION_PROMPT.format(framework=framework, changes_text=filtered_md)
    try:
        structured = llm.with_structured_output(MigrationEntitiesBatch)
        result = structured.invoke(prompt)
        if isinstance(result, MigrationEntitiesBatch):
            return result
        if isinstance(result, dict):
            return MigrationEntitiesBatch.model_validate(result)
        return MigrationEntitiesBatch.model_validate(result)
    except Exception:
        raw = invoke_with_retry(llm, prompt)
        return _parse_json_response(raw)


def run_extraction(
    filtered_md: str,
    *,
    framework_display: str,
    output_path: Path,
    flags: CacheFlags,
) -> ExtractionResult:
    if flags.skip_entity_llm and output_path.exists():
        try:
            batch = MigrationEntitiesBatch.model_validate_json(
                output_path.read_text(encoding="utf-8")
            )
        except ValidationError as exc:
            print(
                f"Cached entities JSON failed validation: {exc}. "
                "Re-run with --force-llm.",
                file=sys.stderr,
            )
            raise SystemExit(1) from exc
        if not batch.entities:
            print(
                "Cached entities JSON contains zero entities. Re-run with --force-llm.",
                file=sys.stderr,
            )
            raise SystemExit(1)
        return ExtractionResult(batch=batch, artifact_path=output_path)

    try:
        batch = _invoke_structured(filtered_md, framework_display)
    except ValidationError as exc:
        print(f"Entity extraction JSON validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except LLMInvocationError as exc:
        print(f"Entity extraction LLM call failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except Exception as exc:
        print(f"Entity extraction failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if not batch.entities:
        print("Entity extraction returned zero entities.", file=sys.stderr)
        raise SystemExit(1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(batch.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return ExtractionResult(batch=batch, artifact_path=output_path)
