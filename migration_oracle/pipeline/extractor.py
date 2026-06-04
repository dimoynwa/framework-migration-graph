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

EXTRACTION_PROMPT = """You are reading a structured migration changelog that has already been filtered,
deduplicated, and categorised by a prior analysis step. Your job is to decompose
each table row into a typed, machine-readable entity for graph population.

Framework: {framework}

For each row in each table:

1. SOURCE SECTION: Read the section heading emoji.
   🔴 → "breaking_change"
   🟠 Security & CVE → "security_fix"
   🟠 Major Component → "component_upgrade"
   🟠 Security Configuration → "security_config"
   🟡 Behavioral → "behavioral"
   🟡 Deprecations → "deprecation"
   🔵 New Capabilities → "new_capability"

2. TITLE: Copy the Title column value verbatim. Do not paraphrase.

3. JIRA KEYS: Copy the JIRA column value. Split on comma. If the value is
   "N/A", produce an empty list.

4. REASON: Write 1-3 sentences from the Impact text — what changed, why it
   matters for upgraders. Do not invent. Use only information in the Impact text.

5. SCOPES: Assess the blast radius of the Impact text. Produce at least one
   scope entry.

6. ENTITIES: List every class, property, or dependency named in the Impact text.
   Assign a role to each: removed, replacement, co-required, or mentioned.

7. STEPS: Decompose the Impact into ordered, atomic actions with step_type,
   summary, instruction, effort, automatable, requires[], and verification.

Do not invent entities, steps, or scope entries not supported by the Impact text.
Return only JSON matching the MigrationEntitiesBatch schema.

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
