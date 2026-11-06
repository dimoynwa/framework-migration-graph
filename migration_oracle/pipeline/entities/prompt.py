"""Entity prompt for one change cluster. Derived from the document extraction prompt.

The field rules are the same. The document and research-appendix wording is not:
every row in the request is one change, and the only evidence is those rows.
"""

from __future__ import annotations

DOSSIER_ENTITY_PROMPT_VERSION = 3

DOSSIER_ENTITY_PROMPT = """You are extracting a migration entity for {framework} from the rows of a single change.

All rows below are one change. Produce at most one entity.

Use only identifiers that appear in the rows or their research. Prefer `**Before/after:**` \
snippets for `instruction`.

When the research says `**Action:** none` and the row text does not require action, return \
{"entities": []}.

When a row has no Research section: No research is available; use only the row text; leave steps \
empty unless the row names the exact identifiers to change.

---

## FIELD RULES

### source_section
One of: breaking_change | security_fix | component_upgrade | security_config | behavioral | \
deprecation | new_capability.

Default from the triage Category. Override the default when the research contradicts it:
  breaking                        → "breaking_change"
  security                        → "security_fix"
  dependency_upgrade              → "component_upgrade"
  config_change or behavior_change → "behavioral"
  deprecation                     → "deprecation"
  new_optional_feature            → "new_capability"

Use "security_config" when the change is to authentication, authorization, or security \
subsystem settings rather than a vulnerability fix. When the rows disagree, pick the section \
the research supports.

### title
A short title of at most 15 words. Use the row title when the statement has one. Do not invent.

### jira_keys
Leave []. The pipeline fills this from the rows.

### source_url
Leave "". The pipeline fills this from the rows.

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
One of: security | performance | spec_compliance | dependency_alignment | bugfix | other | "".

### reason
1–3 sentences: what changed, why it matters for upgraders, and what migration risk it introduces.
Use only information present in the rows and their research. Do not invent.

### scopes
At least one { "scope": ..., "severity": ... } entry when you return an entity. Omit the entity \
instead of inventing a scope the rows do not support.

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

### entities
One entry per class, member, property, or dependency named in the rows or their research. Do not invent names.

  kind: "class" | "member" | "property" | "dependency" | "syntax" | "diagnostic"
  name: FQCN, dotted key, bare exported symbol, or groupId:artifactId
  package: import path / entry point for npm symbols; "" for everything else
  role: "removed" | "replacement" | "co-required" | "mentioned"

Role rules:
  removed     — the source says this is removed, deleted, or no longer available
  replacement — the source says to use this instead
  co-required — must also be configured, injected, or added alongside the replacement
  mentioned   — named but none of the above

#### naming rules
{naming_rules}

### steps
Ordered, atomic migration actions, or [] when the rows do not name a concrete action.

Fields per step:
  index        — 0-based position in this entity's sequence
  step_type    — "remove" | "rename" | "replace" | "configure" | "verify" | "namespace"
  summary      — ≤10 words naming the specific API, property, or artifact
  instruction  — The concrete action. Prefer a `**Before/after:**` snippet. Name only identifiers \
that appear in the rows or their research.
  effort       — "mechanical" | "moderate" | "architectural"
  automatable  — true only for rename/namespace/configure steps that are purely mechanical
  requires     — prerequisite step indices within this entity. [] if none.
  verification — an observable signal. Must not be vague.
  cli_operation — {cli_rule}

Do not invent steps the rows and their research do not support. When research says \
`**Action:** none` and the row text does not require action, return {"entities": []} rather \
than an entity with empty steps.

### subsystem
{subsystem_rule}

---

## OUTPUT

Return ONLY a JSON object, no markdown and no explanation:

{"entities": []}

or one entity:

{"entities": [{
  "source_section": "breaking_change",
  "title": "...",
  "jira_keys": [],
  "source_url": "",
  "change_type": "breaking_change",
  "reason_type": "",
  "reason": "...",
  "scopes": [{"scope": "api-surface", "severity": "high"}],
  "entities": [],
  "steps": [],
  "subsystem": ""
}]}

More than one entity is invalid. {subsystem_check}.

---

{changes_text}
"""

_WILDCARD_DEFAULTS = {
    "{subsystem_rule}": 'Always the empty string "" for this framework.',
    "{cli_rule}": "Always the empty string for this framework.",
    "{subsystem_check}": "subsystem and cli_operation are empty strings for this framework",
    "{naming_rules}": (
        "Entities use the exact FQCN, dotted config key, or groupId:artifactId "
        'the rows name. `package` stays "".'
    ),
}

_WILDFLY_RULES = {
    "{subsystem_rule}": (
        'The WildFly subsystem the change belongs to, as named in the management model '
        '(e.g. "undertow", "elytron", "messaging-activemq", "datasources"). '
        'Empty string "" when the change is not specific to one subsystem.'
    ),
    "{cli_rule}": (
        "A jboss-cli.sh operation that performs this step when one exists "
        '(e.g. "/subsystem=undertow/server=default-server:write-attribute(name=..., value=...)"). '
        "Empty string when the step is not a management-model change."
    ),
    "{subsystem_check}": (
        "subsystem names the WildFly subsystem when the change belongs to one; "
        "cli_operation is set for management-model steps"
    ),
}

_ANGULAR_RULES = {
    "{subsystem_rule}": 'Always the empty string "" for this framework.',
    "{cli_rule}": "Always the empty string for this framework.",
    "{subsystem_check}": "subsystem and cli_operation are empty strings for this framework",
    "{naming_rules}": (
        "Angular has no FQCN, so:\n"
        '  - `name` is the bare exported symbol (for example "InjectFlags", "Router");\n'
        '  - put the import path or entry point in `package` (for example "@angular/core", '
        '"@angular/core/testing", "@angular/router"); use "" when the rows do not name it;\n'
        '  - methods, fields, and options of a symbol are kind "member" with name '
        '"Owner.member" (for example "TestBed.inject");\n'
        '  - template operators and block keywords (for example "in", "void", "let", '
        '"@if", "@for", "@defer", "@let") are kind "syntax";\n'
        '  - compiler diagnostics like "NG8115" are kind "diagnostic";\n'
        '  - config keys are full dotted paths (for example "engines.node", '
        '"angularCompilerOptions.extendedDiagnostics.checks. ...") and stay kind "property";\n'
        "  - never put a package inside `name`."
    ),
}


def _rules_for(framework: str) -> dict[str, str]:
    lowered = framework.lower()
    if "angular" in lowered:
        return _ANGULAR_RULES
    rules = dict(_WILDCARD_DEFAULTS)
    if "wildfly" in lowered:
        rules.update(_WILDFLY_RULES)
    return rules


def render_prompt(framework: str, changes_text: str) -> str:
    """Plain substitution. The cluster text is inserted last so its braces stay literal."""
    rules = _rules_for(framework)
    prompt = DOSSIER_ENTITY_PROMPT
    for placeholder, text in rules.items():
        prompt = prompt.replace(placeholder, text)
    prompt = prompt.replace("{framework}", framework)
    return prompt.replace("{changes_text}", changes_text)


def render_cluster_input(cluster, framework: str, hop: tuple[str, str]) -> str:
    """The user text for one cluster: member rows and their dossiers."""
    lines = [f"Framework: {framework} · Hop: {hop[0]} → {hop[1]}"]
    for number, member in enumerate(cluster.members, start=1):
        category = member.category or "—"
        impact = member.impact_score or "—"
        lines.extend(
            [
                "",
                f"## Row {number}",
                f"Triage: {category}, impact {impact}",
                f"{member.row_type} | {member.source} | {member.statement}",
            ]
        )
        if member.evidence == "row_only" or member.dossier is None or member.dossier.status != "ok":
            continue
        lines.append("Research:")
        lines.append(member.dossier.text.strip())
        lines.append("Fetched sources:")
        if member.dossier.sources:
            lines.extend(f"- {url}" for url in member.dossier.sources)
        else:
            lines.append("-")
    return "\n".join(lines) + "\n"
