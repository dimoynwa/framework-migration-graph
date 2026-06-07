# Plan Format Reference
 
This file defines the exact schema and agent instructions for plan-mode output.
 
---
 
## File to create: `MIGRATION_PLAN.md`
 
Place at `$PROJECT_ROOT/MIGRATION_PLAN.md`.
 
---
 
## Schema
 
### Header block
 
```markdown
# Migration Plan: <FRAMEWORK> <FROM_VERSION> → <TO_VERSION>
<!-- meta: do not edit this block manually -->
Generated: <ISO date>
Project: <absolute PROJECT_ROOT path>
Framework: <FRAMEWORK>
From: <FROM_VERSION>
To: <TO_VERSION>
Total tasks: <N>
HIGH: <count> · MEDIUM: <count> · LOW: <count>
```
 
### Prerequisites block
 
```markdown
## Prerequisites
 
> Complete ALL prerequisites before starting any tasks.
 
- [ ] All changes committed or stashed (`git status` is clean)
- [ ] Test suite passes on current version: `<test command>`
- [ ] Runtime requirement: <e.g. "Java 17+ required for Spring Boot 3.x">
- [ ] Backup or branch: `git checkout -b migration/<FROM>-to-<TO>`
```
 
### Task block (one per change)
 
```markdown
### TASK-<NNN> · <RISK> · <CONCERN>
 
**Summary:** <one-line description of what changes>
**File pattern:** `<glob or specific path>`
**Effort:** <XS=<15min | S=15-30min | M=30-90min | L=>90min>
 
#### Instructions
 
<Numbered, precise steps. Each step must be independently verifiable.
Avoid vague language ("update the code"). Be specific about method names,
annotation names, import paths, config keys.>
 
1. Find all occurrences: `grep -r "<pattern>" src/`
2. <Specific transformation step>
3. <Specific transformation step>
...
 
#### Before / After Reference
 
> Use these as templates, not copy-paste targets — adapt to your actual code.
 
**Before:**
```<lang>
<representative snippet of old code>
```
 
**After:**
```<lang>
<representative snippet of new code>
```
 
#### Verification
 
```bash
# Confirm the change is complete
<one-liner bash check that returns exit 0 on success>
```
 
Expected: <what "success" looks like — e.g. "no output" or "returns 0">
 
---
```
 
### Dependency table block
 
```markdown
## Dependency Updates
 
Apply these version changes to your `pom.xml` / `build.gradle` / `package.json`
before running any code tasks.
 
| Dependency | Current version | Target version | Paysafe service | Notes |
|---|---|---|---|---|
| `spring-boot-starter-parent` | 2.7.x | 3.2.4 | — | Update parent POM first |
| `my-paysafe-service` | 1.3.0 | 2.1.0 | payment-gateway | Compatible with SB 3.x |
```
 
### Verification checklist block
 
```markdown
## Final Verification Checklist
 
Run after all tasks are complete.
 
- [ ] Clean build: `<build command>`
- [ ] Unit tests pass: `<test command>`
- [ ] Integration tests pass: `<integration test command>`
- [ ] Application starts: `<run command>`
- [ ] No remaining deprecated API usages: `<lint/analyze command>`
- [ ] Delete this file: `rm MIGRATION_PLAN.md && git add -A`
```
 
---
 
## Risk Labels
 
| Label | Markdown | When to use |
|---|---|---|
| HIGH | `· HIGH ·` | Entity removed in TO_VERSION; requires architectural change; no 1:1 replacement |
| MEDIUM | `· MEDIUM ·` | Deprecated; mechanical rename; replacement exists |
| LOW | `· LOW ·` | Config key rename; trivial annotation change; tooling can automate |
 
---
 
## Task Ordering Rules
 
Order tasks so that each task's output compiles before the next task runs:
 
1. **Build file changes first** (pom.xml, build.gradle, package.json) — TASK-001 to TASK-00N
2. **Removed dependencies** — remove before adding replacements
3. **Foundational API changes** — base classes, core annotations, config classes
4. **Derived changes** — anything that extends or imports from step 3
5. **Property/config changes** — application.properties/yml
6. **Test changes** — test-scope changes last
Within each group, HIGH before MEDIUM before LOW.
 
---
 
## Agent Instructions Preamble
 
Include this block verbatim at the top of the task list section:
 
```markdown
## Instructions for Code Agent
 
You are executing a structured migration plan. Follow these rules:
 
1. **Work sequentially.** Complete TASK-001 fully before starting TASK-002.
   Each task is designed to leave the codebase in a compilable state.
2. **Verify after each task.** Run the verification command in each task block.
   Do not proceed if verification fails — diagnose and fix first.
3. **Do not invent solutions.** If the Before/After reference does not match
   your actual code, do not guess — output a comment `# NEEDS MANUAL REVIEW`
   and move to the next task.
4. **When stuck, search before skipping.** If a task's Before/After reference
   does not match your code, or if the migration path is unclear, call
   `search_migration_knowledge(query = "<entity or error>", framework = "<FRAMEWORK>")`
   before marking it `# NEEDS MANUAL REVIEW`. Only escalate to manual review
   if the search returns no actionable result.
5. **Preserve behaviour.** Migration changes should be functionally equivalent.
   Do not refactor, rename, or restructure beyond what the task requires.
6. **Track progress.** Check off each `- [ ]` checkbox as you complete it.
7. When all tasks are done, run the Final Verification Checklist.
```
 
---
 
## Effort Estimation Guide
 
| Change type | Effort |
|---|---|
| Single property rename | XS |
| Import swap, no logic change | XS |
| Annotation replacement, same semantics | S |
| Method signature change with adapter | S |
| Replace base class, same behaviour | M |
| Refactor to new pattern (e.g. SecurityFilterChain) | M–L |
| Replace removed module with new dependency | M |
| Architectural change (e.g. WebClient → HttpInterface) | L |
 
---
 
## Assistant Template (4B — Human-Readable Mode)
 
```markdown
## Migration Guide: <FRAMEWORK> <FROM> → <TO>
 
### Overview
<2-3 sentences: total breaking changes found, how many affect this codebase,
estimated effort: 0 HIGH=S · 1-3=M · 4-9=L · 10+=XL>
 
### Recommended Order of Attack
<Numbered list of concerns in execution order, one line each>
 
---
 
### 🔴 High-Risk Changes (<N>)
 
#### 1. <Statement>
**Affects:** <entity list>
**Deprecated in:** <version> · **Removed in:** <version>
**Replace with:** <replacement>
**How:** <3-7 concrete bullet steps>
**Risk if skipped:** <one sentence>
 
---
 
### 🟡 Medium-Risk Changes (<N>)
...same structure...
 
### 🟢 Low-Risk Changes (<N>)
...same structure...
 
### 📦 Dependency Updates
 
| Dependency | Current | Recommended | Notes |
|---|---|---|---|
 
### ✅ Next Steps
1. ...
```
 