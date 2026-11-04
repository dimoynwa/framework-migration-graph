#!/usr/bin/env python3
"""Coverage + enrichment audit for RAW artifacts in ``runs/raw/``.

Answers two questions for a version range, without touching the graph or an LLM:

1. Coverage  — does every GA release between --from and --to appear as a hop
   (``## `from` → `to```  section) in some raw file?  Ground truth comes from the
   upstream release list (Maven Central for Spring Boot, npm for Angular).
2. Enrichment — of the rows that carry a GitHub reference (spec 021 input),
   how many actually got a ``Title: … / … / Release: …`` statement?

Usage:
    .venv/bin/python scripts/check_raw_enrichment.py --framework spring-boot \
        --from 3.0.0 --to 3.2.0
    .venv/bin/python scripts/check_raw_enrichment.py --framework angular \
        --from 18.0.0 --to 22.0.0 --per-hop
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

RAW_DIR = Path("runs/raw")

SECTION_RE = re.compile(r"^## `(?P<from>[^`]+)` → `(?P<to>[^`]+)`\s*$")
ROW_RE = re.compile(r"^\|")

SPRING_BOOT_REF_RE = re.compile(
    r"spring-projects/spring-boot/(?:issues|pull)/(\d+)|#(\d{3,})"
)
ANGULAR_REF_RE = re.compile(
    r"angular/angular/(?:commit/[0-9a-f]{7,40}|(?:pull|issues)/\d+)"
)

MAVEN_URL = (
    "https://repo1.maven.org/maven2/org/springframework/boot/"
    "spring-boot/maven-metadata.xml"
)
NPM_URL = "https://registry.npmjs.org/@angular/core"


def version_key(version: str) -> tuple[int, ...]:
    core = version.split("-")[0].split("+")[0]
    return tuple(int(p) if p.isdigit() else 0 for p in core.split("."))


def is_ga(version: str) -> bool:
    return "-" not in version and "+" not in version


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "migration-oracle-audit"})
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 - fixed hosts
        return resp.read()


def released_versions(framework: str, frm: str, to: str) -> list[str]:
    """Upstream GA releases with ``frm < version <= to``."""
    lo, hi = version_key(frm), version_key(to)
    if framework == "spring-boot":
        root = ET.fromstring(_get(MAVEN_URL))
        raw = [el.text.strip() for el in root.iter("version")]
    elif framework == "angular":
        raw = list(json.loads(_get(NPM_URL)).get("versions", {}).keys())
    else:
        raise SystemExit(f"no release listing implemented for {framework!r}")
    return sorted(
        {v for v in raw if is_ga(v) and lo < version_key(v) <= hi}, key=version_key
    )


def parse_raw_files(framework: str) -> dict[str, list[str]]:
    """Return ``{hop_to_version: [statement, …]}`` across every raw file."""
    hops: dict[str, list[str]] = {}
    for path in sorted(RAW_DIR.glob(f"{framework}-*-changes.md")):
        current: list[str] | None = None
        for line in path.read_text(encoding="utf-8").splitlines():
            section = SECTION_RE.match(line)
            if section:
                current = hops.setdefault(section.group("to"), [])
                continue
            if line.startswith("# ") or line.startswith("## "):
                current = None
                continue
            if current is None or not ROW_RE.match(line):
                continue
            cells = [c.strip() for c in line.split("|")]
            if len(cells) < 6:
                continue
            if cells[1] in ("Type", "") or set(cells[1]) <= {"-", ":", " "}:
                continue
            current.append("|".join(cells[4:]).strip())
    return hops


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--framework", required=True, choices=["spring-boot", "angular"])
    ap.add_argument("--from", dest="frm", required=True)
    ap.add_argument("--to", required=True)
    ap.add_argument("--per-hop", action="store_true", help="Print every hop row.")
    args = ap.parse_args()

    expected = released_versions(args.framework, args.frm, args.to)
    hops = parse_raw_files(args.framework)
    ref_re = SPRING_BOOT_REF_RE if args.framework == "spring-boot" else ANGULAR_REF_RE

    missing = [v for v in expected if v not in hops]
    ref_re_stmt = re.compile(r"Title:.*Release:", re.S)

    rows = total_rows = total_ref = total_enr = 0
    unenriched: dict[str, int] = {}
    print(f"\n{'hop':<22}{'rows':>6}{'ref rows':>10}{'enriched':>10}{'  ratio':>8}")
    for version in expected:
        statements = hops.get(version, [])
        if not statements:
            continue
        refs = [s for s in statements if ref_re.search(s)]
        enr = [s for s in refs if ref_re_stmt.search(s)]
        rows += len(statements)
        total_ref += len(refs)
        total_enr += len(enr)
        ratio = (len(enr) / len(refs) * 100) if refs else 100.0
        if len(refs) and ratio < 90:
            unenriched[version] = len(refs) - len(enr)
        if args.per_hop or (len(refs) and ratio < 99.5):
            print(
                f"→ {version:<19}{len(statements):>6}{len(refs):>10}{len(enr):>10}"
                f"{ratio:>7.1f}%"
            )

    print(
        f"\n{args.framework} {args.frm} → {args.to}: "
        f"{len(expected) - len(missing)}/{len(expected)} releases covered, "
        f"{rows} rows, {total_enr}/{total_ref} reference rows enriched "
        f"({(total_enr / total_ref * 100) if total_ref else 0:.1f}%)."
    )
    if missing:
        print(f"MISSING releases (no raw hop found): {', '.join(missing)}")
    stale = [
        v
        for v in expected
        if v in hops and not hops[v]
    ]
    if stale:
        print(f"EMPTY hops (header only, 0 rows): {', '.join(stale)}")
    if unenriched:
        print("Hops with >10% unenriched reference rows:")
        for version, count in sorted(unenriched.items(), key=lambda kv: version_key(kv[0])):
            print(f"  {version}: {count} rows without Title:/Release:")
    return 0 if not missing else 1


if __name__ == "__main__":
    sys.exit(main())
