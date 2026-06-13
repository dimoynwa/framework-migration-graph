#!/usr/bin/env python3
"""Verify every Sortable cell in framework_migration_version_map.md matches MAJOR*1_000_000 + MINOR*1_000 + PATCH."""

import re
import sys
from pathlib import Path

SKILL = Path("migration_oracle/mcp/skills/framework_migration_version_map.md")
SCHEMA = Path("docs/graph-schema.md")

ROW = re.compile(r"^\|\s*(\d+\.\d+\.\d+)\s*\|\s*(\d+)\s*\|")

errors = []
rows_checked = 0

for line in SKILL.read_text().splitlines():
    m = ROW.match(line)
    if not m:
        continue
    version_str, stored_str = m.group(1), m.group(2)
    major, minor, patch = (int(x) for x in version_str.split("."))
    expected = major * 1_000_000 + minor * 1_000 + patch
    stored = int(stored_str)
    status = "OK" if stored == expected else "FAIL"
    print(f"  {status}  {version_str:10s}  stored={stored:10d}  expected={expected:10d}")
    if stored != expected:
        errors.append(f"{version_str}: stored {stored} != expected {expected}")
    rows_checked += 1

print(f"\nRows checked: {rows_checked}")

# Formula property: f(3,10,0) > f(3,9,0)
v3_10_0 = 3 * 1_000_000 + 10 * 1_000 + 0
v3_9_0  = 3 * 1_000_000 +  9 * 1_000 + 0
assert v3_10_0 > v3_9_0, f"Formula property test failed: f(3,10,0)={v3_10_0} not > f(3,9,0)={v3_9_0}"
print(f"Formula property: f(3,10,0)={v3_10_0} > f(3,9,0)={v3_9_0}  OK")

# docs/graph-schema.md unchanged check
schema_text = SCHEMA.read_text()
assert "major * 1_000_000 + minor * 1_000 + patch" in schema_text, \
    "docs/graph-schema.md no longer contains canonical formula text"
print("docs/graph-schema.md formula text: OK")

if errors:
    print(f"\nERRORS ({len(errors)}):")
    for e in errors:
        print(f"  {e}")
    sys.exit(1)

print(f"\nAll {rows_checked} cells correct.")
