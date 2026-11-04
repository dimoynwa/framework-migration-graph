# Verification Protocol: Migration Skill Install Remediation

**Location**: `specs/020-migration-skill-install-remediation/verification.md`
**Spec gate**: Run this after `/speckit.implement` completes, before marking `020` complete
**Execution order**: Levels 0 -> 2, then Level 7. Stop and fix on the first failure -- failures compound.

This protocol verifies the remediation described in `spec.md`, using `instructions.md` as the implementation-task source because this lightweight package intentionally has no `tasks.md` or `plan.md`.

## Prerequisites

| Requirement | Needed for | Check |
|---|---|---|
| Python environment synced | All levels | `.venv/bin/python -m pytest --version` succeeds |
| Database reachability | Not required | This spec does not touch graph read/write behavior |
| LLM credentials | Not required | This spec does not run extraction or generation |
| Writable temp directory | Levels 1, 2, 7 | Python `tempfile.TemporaryDirectory()` can create files |

Infrastructure summary:

- Levels 0, 1, 2, and 7 require no DB and no LLM.
- Levels 3, 4, 5, and 6 are omitted because this remediation has no graph read path, graph write path, dry-run pipeline, or graph idempotency behavior.

## Level 0 — Static Skill Install Structure

Infrastructure: no DB, no LLM.

### 0-A — Public modules import

```bash
.venv/bin/python - <<'PY'
import importlib

modules = [
    "migration_oracle.mcp.tools.install",
    "migration_oracle.mcp.server",
    "migration_oracle.mcp.stage_gating",
]

for name in modules:
    mod = importlib.import_module(name)
    assert mod is not None, f"Import returned None for {name}"

print("PASS: 0-A public install/server/stage-gating modules import")
PY
```

### 0-B — Full-mode bundle set is exactly six bundles in stage order

```bash
.venv/bin/python - <<'PY'
from migration_oracle.mcp.tools.install import MODE_BUNDLES, SKILL_BUNDLES

expected = [
    "framework-migration-research",
    "framework-migration-plan",
    "framework-migration-gap-check",
    "framework-migration-clarify",
    "framework-migration-preview",
    "framework-migration-execute",
]

actual = MODE_BUNDLES.get("full")
assert actual == expected, f"Full bundles mismatch. Got: {actual!r}"

missing = [name for name in expected if name not in SKILL_BUNDLES]
assert not missing, f"Missing SKILL_BUNDLES entries: {missing!r}"

print("PASS: 0-B full-mode bundle set is exactly six bundles in stage order")
PY
```

### 0-C — Research bundle source and destination are defined

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
from migration_oracle.mcp.tools.install import SKILL_BUNDLES

pairs = SKILL_BUNDLES["framework-migration-research"]
expected_pair = ("framework-migration/research.md", "framework-migration-research/SKILL.md")
assert expected_pair in pairs, f"Research bundle missing pair {expected_pair!r}. Got: {pairs!r}"

skills_dir = Path("migration_oracle/mcp/skills")
for src, _ in pairs:
    path = skills_dir / src
    assert path.is_file(), f"Research bundle source missing: {path}"

print("PASS: 0-C research bundle source and destination are defined")
PY
```

### 0-D — Plan bundle installs scanner script used by scanning reference

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
from migration_oracle.mcp.tools.install import SKILL_BUNDLES

pairs = SKILL_BUNDLES["framework-migration-plan"]
destinations = {dest for _, dest in pairs}
sources = {src for src, _ in pairs}

assert "framework-migration-plan/references/framework_scanner.py" in destinations, (
    f"Plan bundle does not install framework_scanner.py. Destinations: {sorted(destinations)!r}"
)
assert "framework-migration/framework_scanner.py" in sources, (
    f"Plan bundle does not copy scanner source. Sources: {sorted(sources)!r}"
)

scanner = Path("migration_oracle/mcp/skills/framework-migration/framework_scanner.py")
assert scanner.is_file(), f"Scanner source missing: {scanner}"

print("PASS: 0-D plan bundle installs scanner script used by scanning reference")
PY
```

### 0-E — Research stage is registered in server routing

```bash
.venv/bin/python - <<'PY'
from migration_oracle.mcp.server import bundle_to_skill_uri
import migration_oracle.mcp.server as server

stage_bundles = getattr(server, "_STAGE_BUNDLES")
actual = stage_bundles.get("research")
assert actual == "framework-migration-research", f"Research stage route mismatch. Got: {actual!r}"

uri = bundle_to_skill_uri(actual)
assert uri == "skill://framework-migration-research/main", f"Research URI mismatch. Got: {uri!r}"

print("PASS: 0-E research stage is registered in server routing")
PY
```

### 0-F — Stage-gating research allowlist matches research frontmatter

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
import re
import yaml

from migration_oracle.mcp.stage_gating import STAGE_TOOL_ALLOWLIST

text = Path("migration_oracle/mcp/skills/framework-migration/research.md").read_text(encoding="utf-8")
match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
assert match, "Research skill has no YAML frontmatter"
frontmatter = yaml.safe_load(match.group(1))
frontmatter_tools = set(frontmatter["compatibility"]["tools"])

allowlist = set(STAGE_TOOL_ALLOWLIST.get("research", set()))
assert allowlist == frontmatter_tools, (
    f"Research allowlist/frontmatter mismatch. Allowlist={sorted(allowlist)!r}, "
    f"frontmatter={sorted(frontmatter_tools)!r}"
)

print("PASS: 0-F stage-gating research allowlist matches research frontmatter")
PY
```

### 0-G — Server exposes the research skill resource

```bash
.venv/bin/python - <<'PY'
import asyncio
from migration_oracle.mcp.server import mcp

async def main():
    resources = await mcp.list_resources()
    uris = {str(resource.uri) for resource in resources}
    expected = "skill://framework-migration-research/main"
    assert expected in uris, f"Missing research resource {expected}. Got: {sorted(uris)!r}"
    print("PASS: 0-G server exposes the research skill resource")

asyncio.run(main())
PY
```

## Level 1 — Interface Structure

Infrastructure: no DB, no LLM.

### 1-A — Prompt API accepts research stage without fallback

```bash
.venv/bin/python - <<'PY'
from migration_oracle.mcp.server import start_migration, resume_migration

start_text = start_migration(
    framework="Spring Boot",
    current_version="3.3.0",
    target_version="3.4.0",
    project_id="verify-020",
    stage="research",
)
assert "skill://framework-migration-research/main" in start_text, f"start_migration text: {start_text}"
assert "Active stage: research" in start_text, f"start_migration did not mark active research stage: {start_text}"
assert "skill://framework-migration-plan/main" not in start_text, f"start_migration fell back to plan: {start_text}"

resume_text = resume_migration(
    migration_folder="ps-migration/spring-boot-3.3.0-to-3.4.0",
    stage="research",
)
assert "skill://framework-migration-research/main" in resume_text, f"resume_migration text: {resume_text}"
assert "skill://framework-migration-execute/main" not in resume_text, f"resume_migration fell back to execute: {resume_text}"

print("PASS: 1-A prompt API accepts research stage without fallback")
PY
```

### 1-B — Workflow prompt describes six-stage file-state workflow

```bash
.venv/bin/python - <<'PY'
from migration_oracle.mcp.server import migration_workflow_prompt

text = migration_workflow_prompt()
required = [
    "skill://framework-migration-research/main",
    "skill://framework-migration-plan/main",
    "research",
    "plan",
    "gap-check",
    "clarify",
    "preview",
    "execute",
    "ps-migration",
]
missing = [item for item in required if item not in text]
assert not missing, f"Workflow prompt missing {missing!r}. Text: {text}"

for forbidden in ["four-loop", "create_migration_context", "close_migration_context"]:
    assert forbidden not in text, f"Workflow prompt contains stale term {forbidden!r}: {text}"

print("PASS: 1-B workflow prompt describes six-stage file-state workflow")
PY
```

### 1-C — Invalid install target raises clear ValueError before writing files

```bash
.venv/bin/python - <<'PY'
import os
import sys
import tempfile
from pathlib import Path

os.environ["MIGRATION_MODE"] = "full"
for name in ("migration_oracle.mcp.tools.install", "migration_oracle.mcp.config"):
    sys.modules.pop(name, None)

import migration_oracle.mcp.tools.install as inst

with tempfile.TemporaryDirectory() as tmp:
    target_root = Path(tmp)
    try:
        inst.install_migration_skill(target="curser", target_dir=str(target_root))
    except ValueError as exc:
        message = str(exc)
        assert "target" in message and "cursor" in message and "claude-code" in message, (
            f"Invalid target ValueError message is not clear. Got: {message!r}"
        )
    else:
        raise AssertionError("install_migration_skill accepted invalid target 'curser'")

    remaining = list(target_root.iterdir())
    assert remaining == [], f"Invalid target wrote files: {[str(p) for p in remaining]!r}"

print("PASS: 1-C invalid install target raises clear ValueError before writing files")
PY
```

### 1-D — Valid install targets still resolve correctly

```bash
.venv/bin/python - <<'PY'
import os
import sys
import tempfile

os.environ["MIGRATION_MODE"] = "lite"
for name in ("migration_oracle.mcp.tools.install", "migration_oracle.mcp.config"):
    sys.modules.pop(name, None)

import migration_oracle.mcp.tools.install as inst

for target, expected in [("auto", "cursor"), ("cursor", "cursor"), ("claude-code", "claude-code")]:
    with tempfile.TemporaryDirectory() as tmp:
        result = inst.install_migration_skill(target=target, target_dir=tmp)
        assert result["target"] == expected, f"Target {target!r} resolved to {result['target']!r}"
        assert result["status"] == "ok", f"Install failed for target {target!r}: {result!r}"

print("PASS: 1-D valid install targets still resolve correctly")
PY
```

## Level 2 — Isolated Install and Documentation Behavior

Infrastructure: no DB, no LLM. These checks exercise filesystem install behavior in temporary directories and static documentation checks.

### 2-A — Full-mode install writes coherent six-bundle tree

```bash
.venv/bin/python - <<'PY'
import os
import sys
import tempfile
from pathlib import Path

os.environ["MIGRATION_MODE"] = "full"
for name in ("migration_oracle.mcp.tools.install", "migration_oracle.mcp.config"):
    sys.modules.pop(name, None)

import migration_oracle.mcp.tools.install as inst

expected_bundles = [
    "framework-migration-research",
    "framework-migration-plan",
    "framework-migration-gap-check",
    "framework-migration-clarify",
    "framework-migration-preview",
    "framework-migration-execute",
]

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    result = inst.install_migration_skill(target="cursor", target_dir=str(root))
    assert result["installed_skills"] == expected_bundles, (
        f"Installed skill order mismatch. Got: {result['installed_skills']!r}"
    )

    for bundle in expected_bundles:
        skill = root / bundle / "SKILL.md"
        assert skill.is_file(), f"Missing installed skill file: {skill}"

    scanner = root / "framework-migration-plan" / "references" / "framework_scanner.py"
    assert scanner.is_file(), f"Missing installed scanner reference: {scanner}"

    scanning_ref = root / "framework-migration-plan" / "references" / "scanning.md"
    assert scanning_ref.is_file(), f"Missing installed scanning reference: {scanning_ref}"
    text = scanning_ref.read_text(encoding="utf-8")
    assert "references/framework_scanner.py" in text, f"Scanning ref lacks installed scanner command: {text[:500]}"
    assert "python3 migration_oracle/mcp/skills/framework-migration/framework_scanner.py" not in text, (
        "Scanning ref still uses source-tree command"
    )

print("PASS: 2-A full-mode install writes coherent six-bundle tree")
PY
```

### 2-B — Research installed references resolve

```bash
.venv/bin/python - <<'PY'
import os
import sys
import tempfile
from pathlib import Path

os.environ["MIGRATION_MODE"] = "full"
for name in ("migration_oracle.mcp.tools.install", "migration_oracle.mcp.config"):
    sys.modules.pop(name, None)

import migration_oracle.mcp.tools.install as inst

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    inst.install_migration_skill(target="cursor", target_dir=str(root))
    research_skill = root / "framework-migration-research" / "SKILL.md"
    assert research_skill.is_file(), f"Missing research skill: {research_skill}"

    text = research_skill.read_text(encoding="utf-8")
    candidate_paths = [
        root / "framework-migration-research" / "references" / "scanning.md",
        root / "framework-migration-plan" / "references" / "scanning.md",
    ]
    assert any(path.is_file() for path in candidate_paths), (
        f"No installed scanning reference reachable for research. Checked: {[str(p) for p in candidate_paths]!r}"
    )

    candidate_version_maps = [
        root / "framework-migration-research" / "references" / "version-map.md",
        root / "framework-migration-plan" / "references" / "version-map.md",
    ]
    assert any(path.is_file() for path in candidate_version_maps), (
        f"No installed version-map reference reachable for research. Checked: {[str(p) for p in candidate_version_maps]!r}"
    )

    assert "migration_oracle/mcp/skills/framework-migration/framework_scanner.py" not in text, (
        "Research skill points operators at source-tree scanner path"
    )

print("PASS: 2-B research installed references resolve")
PY
```

### 2-C — Lite-mode install remains unchanged in behavior

```bash
.venv/bin/python - <<'PY'
import os
import sys
import tempfile
from pathlib import Path

os.environ["MIGRATION_MODE"] = "lite"
for name in ("migration_oracle.mcp.tools.install", "migration_oracle.mcp.config"):
    sys.modules.pop(name, None)

import migration_oracle.mcp.tools.install as inst

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    result = inst.install_migration_skill(target="cursor", target_dir=str(root))
    expected = ["migration-lite", "openrewrite-runner"]
    assert result["installed_skills"] == expected, f"Lite installed skills changed. Got: {result['installed_skills']!r}"

    expected_files = [
        "migration-lite/SKILL.md",
        "migration-lite/references/version-map.md",
        "openrewrite-runner/SKILL.md",
        "openrewrite-runner/references/recipe-catalog.md",
        "openrewrite-runner/references/examples.md",
    ]
    for rel in expected_files:
        path = root / rel
        assert path.is_file(), f"Missing lite install file: {path}"

    unexpected = root / "framework-migration-research"
    assert not unexpected.exists(), f"Lite install unexpectedly wrote full-mode bundle: {unexpected}"

print("PASS: 2-C lite-mode install remains unchanged in behavior")
PY
```

### 2-D — Focused pytest suite passes

```bash
.venv/bin/python -m pytest \
  tests/mcp/test_install_skill.py \
  tests/mcp/test_install_bundles.py \
  tests/mcp/test_prompts.py \
  tests/mcp/test_feature_flag.py \
  tests/mcp/test_server.py
```

Expected: exit code 0.

### 2-E — Active docs and runtime skills do not instruct stale workflow

```bash
.venv/bin/python - <<'PY'
from pathlib import Path

paths = [
    Path("docs/03-mcp-and-agent-harness/mcp-tools-skills-prompts.md"),
    Path("docs/04-operator-guides/usage.md"),
    Path("docs/04-operator-guides/instruction.md"),
    Path("migration_oracle/mcp/skills/framework-migration/research.md"),
    Path("migration_oracle/mcp/skills/framework-migration/plan.md"),
    Path("migration_oracle/mcp/skills/framework-migration/gap-check.md"),
    Path("migration_oracle/mcp/skills/framework-migration/clarify.md"),
    Path("migration_oracle/mcp/skills/framework-migration/preview.md"),
    Path("migration_oracle/mcp/skills/framework-migration/execute.md"),
    Path("migration_oracle/mcp/server.py"),
]

forbidden = [
    "Load skill://framework-migration/main",
    "skill://framework-migration/plan-format",
    "Run the four-loop",
    "call create_migration_context",
    "call update_step_status",
    "call close_migration_context",
    "get_pending_steps",
]

violations = []
for path in paths:
    text = path.read_text(encoding="utf-8")
    for term in forbidden:
        if term in text:
            violations.append(f"{path}: {term}")

assert not violations, "Stale active workflow references found: " + repr(violations)
print("PASS: 2-E active docs and runtime skills do not instruct stale workflow")
PY
```

### 2-F — Documentation lists registered split skill resources including research

```bash
.venv/bin/python - <<'PY'
from pathlib import Path

doc = Path("docs/03-mcp-and-agent-harness/mcp-tools-skills-prompts.md").read_text(encoding="utf-8")
required = [
    "skill://framework-migration-research/main",
    "skill://framework-migration-plan/main",
    "skill://framework-migration-gap-check/main",
    "skill://framework-migration-clarify/main",
    "skill://framework-migration-preview/main",
    "skill://framework-migration-execute/main",
    "skill://framework-migration-plan/scanning",
    "skill://framework-migration-plan/version-map",
    "skill://framework-migration-execute/rollback",
]
missing = [item for item in required if item not in doc]
assert not missing, f"MCP docs missing split skill resources: {missing!r}"

assert "Full mode bundles" in doc, "MCP docs missing full mode bundle section"
assert "framework-migration-research" in doc, "MCP docs missing research bundle name"
assert "five top-level directories" not in doc, "MCP docs still claim five full-mode top-level directories"

print("PASS: 2-F documentation lists registered split skill resources including research")
PY
```

## Level 7 — Edge-Case Paths

Infrastructure: no DB, no LLM.

### 7-A — Target validation guard rejects multiple invalid values before install

```bash
.venv/bin/python - <<'PY'
import os
import sys
import tempfile
from pathlib import Path

os.environ["MIGRATION_MODE"] = "full"
for name in ("migration_oracle.mcp.tools.install", "migration_oracle.mcp.config"):
    sys.modules.pop(name, None)

import migration_oracle.mcp.tools.install as inst

invalid_targets = ["", "CurSor", "claude", "cursor-code", "curser"]

for invalid in invalid_targets:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        try:
            inst.install_migration_skill(target=invalid, target_dir=str(root))
        except ValueError as exc:
            assert "target" in str(exc), f"ValueError for {invalid!r} does not mention target: {exc}"
        else:
            raise AssertionError(f"Invalid target {invalid!r} was accepted")
        assert list(root.iterdir()) == [], f"Invalid target {invalid!r} wrote files into {root}"

print("PASS: 7-A target validation guard rejects multiple invalid values before install")
PY
```

### 7-B — Stage-gating rejects unknown stage but accepts research

```bash
.venv/bin/python - <<'PY'
import os
import sys

def fresh_stage_gating(stage):
    os.environ["MCP_ACTIVE_STAGE"] = stage
    sys.modules.pop("migration_oracle.mcp.stage_gating", None)
    import migration_oracle.mcp.stage_gating as sg
    return sg

sg = fresh_stage_gating("research")
assert sg.get_active_stage() == "research", f"research stage was not accepted; got {sg.get_active_stage()!r}"
assert "research" in sg.STAGE_TOOL_ALLOWLIST, f"research missing from allowlist keys: {sorted(sg.STAGE_TOOL_ALLOWLIST)!r}"

try:
    fresh_stage_gating("analysis")
except ValueError as exc:
    assert "research" in str(exc), f"Invalid-stage error does not list research as valid: {exc}"
else:
    raise AssertionError("Unknown MCP_ACTIVE_STAGE='analysis' was accepted")

print("PASS: 7-B stage-gating rejects unknown stage but accepts research")
PY
```

### 7-C — Re-running full install is idempotent for installed skill files

```bash
.venv/bin/python - <<'PY'
import hashlib
import os
import sys
import tempfile
from pathlib import Path

os.environ["MIGRATION_MODE"] = "full"
for name in ("migration_oracle.mcp.tools.install", "migration_oracle.mcp.config"):
    sys.modules.pop(name, None)

import migration_oracle.mcp.tools.install as inst

def digest_tree(root: Path) -> dict[str, str]:
    result = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        result[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    first = inst.install_migration_skill(target="cursor", target_dir=str(root))
    before = digest_tree(root)
    second = inst.install_migration_skill(target="cursor", target_dir=str(root))
    after = digest_tree(root)

    assert first["installed_skills"] == second["installed_skills"], (
        f"Installed skill list changed across rerun. First={first['installed_skills']!r}, "
        f"second={second['installed_skills']!r}"
    )
    assert before == after, f"Installed file digests changed across idempotent rerun. Before={before!r}, after={after!r}"

print("PASS: 7-C re-running full install is idempotent for installed skill files")
PY
```

### 7-D — Scanner reference mtime updates on reinstall when source changes

This check verifies the installer overwrites managed migration files on rerun. It uses a seeded installed file and checks mtime with the required cross-platform stat form.

```bash
.venv/bin/python - <<'PY'
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ["MIGRATION_MODE"] = "full"
for name in ("migration_oracle.mcp.tools.install", "migration_oracle.mcp.config"):
    sys.modules.pop(name, None)

import migration_oracle.mcp.tools.install as inst

def stat_mtime(path: Path) -> int:
    cmd = f"stat -c %Y {path} 2>/dev/null || stat -f %m {path}"
    out = subprocess.check_output(cmd, shell=True, text=True).strip()
    return int(out)

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    inst.install_migration_skill(target="cursor", target_dir=str(root))
    scanner = root / "framework-migration-plan" / "references" / "framework_scanner.py"
    assert scanner.is_file(), f"Missing installed scanner: {scanner}"

    scanner.write_text("# stale local edit\n", encoding="utf-8")
    before = stat_mtime(scanner)
    time.sleep(1.1)
    inst.install_migration_skill(target="cursor", target_dir=str(root))
    after = stat_mtime(scanner)

    content = scanner.read_text(encoding="utf-8")
    assert "# stale local edit" not in content, "Installer did not overwrite managed scanner reference"
    assert after >= before, f"Scanner mtime did not update or remain valid. Before={before}, after={after}"

print("PASS: 7-D scanner reference mtime updates on reinstall when source changes")
PY
```

## Completion Gate

Update `SPEC_ORGANIZATION.md` to `✅ Complete` only when every item below is checked.

| Check ID | Description | Result |
|---|---|---|
| 0-A | Public install/server/stage-gating modules import | |
| 0-B | Full-mode bundle set is exactly six bundles in stage order | |
| 0-C | Research bundle source and destination are defined | |
| 0-D | Plan bundle installs scanner script used by scanning reference | |
| 0-E | Research stage is registered in server routing | |
| 0-F | Stage-gating research allowlist matches research frontmatter | |
| 0-G | Server exposes the research skill resource | |
| 1-A | Prompt API accepts research stage without fallback | |
| 1-B | Workflow prompt describes six-stage file-state workflow | |
| 1-C | Invalid install target raises clear ValueError before writing files | |
| 1-D | Valid install targets still resolve correctly | |
| 2-A | Full-mode install writes coherent six-bundle tree | |
| 2-B | Research installed references resolve | |
| 2-C | Lite-mode install remains unchanged in behavior | |
| 2-D | Focused pytest suite passes | |
| 2-E | Active docs and runtime skills do not instruct stale workflow | |
| 2-F | Documentation lists registered split skill resources including research | |
| 7-A | Target validation guard rejects multiple invalid values before install | |
| 7-B | Stage-gating rejects unknown stage but accepts research | |
| 7-C | Re-running full install is idempotent for installed skill files | |
| 7-D | Scanner reference mtime updates on reinstall when source changes | |
