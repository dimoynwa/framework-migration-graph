"""One-off: rewrite stale artifact paths in the graph to match the current layout.

Old layout (stored in graph):
  runs/md/{key}.md
  runs/filtered/{key}.md
  runs/json/{key}-entities.json   ← already correct

Current layout (on disk):
  runs/raw/{key}-changes.md
  runs/nodes/{key}-changes_filtered.md
  runs/json/{key}-entities.json
"""

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from migration_oracle.graph.driver import read_session, write_session

_LIST = """
MATCH (v:Version)
WHERE v.rawMdPath IS NOT NULL
RETURN v.framework AS framework,
       v.version   AS version,
       v.rawMdPath AS raw_md_path,
       v.filteredMdPath AS filtered_md_path,
       v.entitiesJsonPath AS entities_json_path
"""

_KEY_RE = re.compile(r"[^/]+/[^/]+/(.+?)(?:\.md|-entities\.json)$")

_UPDATE = """
MATCH (v:Version {framework: $framework, version: $version})
SET v.rawMdPath        = $raw_md_path,
    v.filteredMdPath   = $filtered_md_path,
    v.entitiesJsonPath = $entities_json_path
"""


def extract_key(path: str) -> str | None:
    m = _KEY_RE.search(path)
    return m.group(1) if m else None


def main() -> None:
    with read_session() as s:
        rows = [dict(r) for r in s.run(_LIST)]

    print(f"Found {len(rows)} Version nodes with artifact paths.\n")
    updates = []

    for row in rows:
        old_raw = row["raw_md_path"] or ""
        key = extract_key(old_raw)
        if not key:
            print(f"  SKIP {row['framework']} {row['version']}: can't parse key from '{old_raw}'")
            continue

        new_raw      = f"runs/raw/{key}-changes.md"
        new_filtered = f"runs/nodes/{key}-changes_filtered.md"
        new_json     = f"runs/json/{key}-entities.json"

        # Verify at least the raw file exists before committing
        raw_on_disk = PROJECT_ROOT / new_raw
        if not raw_on_disk.exists():
            print(f"  WARN {key}: raw file not found at {raw_on_disk} — skipping")
            continue

        print(f"  {row['framework']} {row['version']}")
        print(f"    raw:      {old_raw!r}  →  {new_raw!r}")
        print(f"    filtered: {row['filtered_md_path']!r}  →  {new_filtered!r}")
        print(f"    json:     {row['entities_json_path']!r}  →  {new_json!r}")
        updates.append({
            "framework": row["framework"],
            "version": row["version"],
            "raw_md_path": new_raw,
            "filtered_md_path": new_filtered,
            "entities_json_path": new_json,
        })

    if not updates:
        print("Nothing to update.")
        return

    print(f"\nApplying {len(updates)} updates...")
    with write_session() as s:
        for u in updates:
            s.run(_UPDATE, **u)

    print("Done.")


if __name__ == "__main__":
    main()
