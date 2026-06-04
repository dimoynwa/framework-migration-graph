#!/usr/bin/env python3
"""Split a multi-hop WildFly raw MD file into major-version-range files."""

from __future__ import annotations

import re
import sys
from datetime import UTC, datetime
from pathlib import Path

SOURCE = Path("runs/raw/wildfly-28.0.0-to-40.0.0-changes.md")
OUT_DIR = Path("runs/raw")


def parse_hops(text: str) -> list[tuple[str, str, str]]:
    """Return (from_ver, to_ver, section_body) for each hop."""
    pattern = re.compile(r"^## `([^`]+)` → `([^`]+)`\s*$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    hops: list[tuple[str, str, str]] = []
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        hops.append((match.group(1), match.group(2), text[start:end]))
    return hops


def group_hops(hops: list[tuple[str, str, str]]) -> dict[tuple[str, str], list]:
    """Group hops into X.0.0 → (X+1).0.0 slices by hop_from major."""
    groups: dict[tuple[str, str], list] = {}
    for hop_from, hop_to, body in hops:
        major = int(hop_from.split(".")[0])
        key = (f"{major}.0.0", f"{major + 1}.0.0")
        groups.setdefault(key, []).append((hop_from, hop_to, body))
    return groups


def render_file(
    *,
    range_from: str,
    range_to: str,
    hop_sections: list[tuple[str, str, str]],
    generated_utc: str,
) -> str:
    lines = [
        "# WildFly — documented changes (extract-only)",
        "",
        "- **Framework key:** `wildfly`",
        f"- **Resolved range:** `{range_from}` → `{range_to}`",
        f"- **Generated (UTC):** {generated_utc}",
        f"- **Split from:** `{SOURCE.name}`",
        "",
        "---",
        "",
    ]
    for hop_from, hop_to, body in hop_sections:
        lines.append(f"## `{hop_from}` → `{hop_to}`")
        lines.extend(body.strip().splitlines())
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    if not SOURCE.exists():
        print(f"Missing source: {SOURCE}", file=sys.stderr)
        return 1

    text = SOURCE.read_text(encoding="utf-8")
    ts_match = re.search(r"\*\*Generated \(UTC\):\*\* (.+)", text)
    generated = ts_match.group(1).strip() if ts_match else datetime.now(UTC).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    hops = parse_hops(text)
    groups = group_hops(hops)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for (range_from, range_to), sections in sorted(groups.items(), key=lambda x: x[0]):
        out_path = OUT_DIR / f"wildfly-{range_from}-to-{range_to}-changes.md"
        out_path.write_text(
            render_file(
                range_from=range_from,
                range_to=range_to,
                hop_sections=sections,
                generated_utc=generated,
            ),
            encoding="utf-8",
        )
        hop_count = len(sections)
        rows = sum(
            1
            for _, _, body in sections
            for ln in body.splitlines()
            if ln.startswith("| ")
            and not ln.startswith("| Type")
            and not ln.startswith("|------")
        )
        print(f"Wrote {out_path.name}: {hop_count} hops, {rows} rows")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
