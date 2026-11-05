"""Score System-1 triage against entity silver labels already in ``runs/``.

A raw row is relevant when an entity from the paired ``runs/json`` file points
back at it via source URL, Jira key, GitHub issue number, or commit SHA.
Rows whose entity ``change_type`` is a breaking change, deprecation, or
mandatory migration are the critical subset.

Thresholds (AC-7), reported per preset range:

- critical recall >= 98%
- overall relevant recall >= 95%
- drop rate >= 50% of raw rows

Exit 0 when every preset that has triaged rows meets the thresholds.
Exit 1 when a triaged preset misses a threshold.
Exit 2 when no triaged raw file is available to score.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from migration_oracle.pipeline.triage.markdown import parse_raw_markdown

CRITICAL_RECALL = 0.98
RELEVANT_RECALL = 0.95
MIN_DROP_RATE = 0.50

PRESETS = (
    ("angular", (18, 0, 0), (22, 0, 0)),
    ("spring-boot", (3, 3, 0), (4, 1, 0)),
    ("wildfly", (28, 0, 0), (30, 0, 0)),
)

_JIRA_RE = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")
_ISSUE_RE = re.compile(r"/(?:issues|pull)/(\d+)\b|#(\d+)\b")
_SHA_RE = re.compile(r"/commit/([0-9a-f]{7,40})\b", re.IGNORECASE)
_FILE_RE = re.compile(r"^(?P<framework>.+)-(?P<from>\d.*)-to-(?P<to>\d.*)-changes\.md$")


@dataclass
class Score:
    framework: str
    rows: int = 0
    dropped: int = 0
    relevant: int = 0
    relevant_kept: int = 0
    critical: int = 0
    critical_kept: int = 0
    misses: list[str] = field(default_factory=list)
    untriaged_files: list[str] = field(default_factory=list)

    @property
    def drop_rate(self) -> float:
        return self.dropped / self.rows if self.rows else 0.0

    @property
    def recall(self) -> float:
        return self.relevant_kept / self.relevant if self.relevant else 1.0

    @property
    def critical_recall(self) -> float:
        return self.critical_kept / self.critical if self.critical else 1.0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runs",
        type=Path,
        default=Path("runs"),
        help="Directory that contains raw/ and json/",
    )
    parser.add_argument(
        "--raw",
        type=Path,
        action="append",
        default=[],
        help="Score this raw file against the sibling entities JSON. Repeatable.",
    )
    args = parser.parse_args(argv)
    if args.raw:
        scores = [_score_files(args.raw, label="custom")]
    else:
        scores = [
            _score_preset(args.runs, framework, start, end)
            for framework, start, end in PRESETS
        ]
    scored = [score for score in scores if score.rows]
    for score in scores:
        _print_score(score)
    if not scored:
        print(
            "No triaged raw rows found. Run export-extract-populate-framework "
            "with TRIAGE_BASE_URL and TRIAGE_MODEL set, then re-run this script."
        )
        return 2
    failed = [score for score in scored if not _passes(score)]
    return 1 if failed else 0


def _score_preset(
    runs: Path, framework: str, start: tuple[int, int, int], end: tuple[int, int, int]
) -> Score:
    raw_dir = runs / "raw"
    files = []
    if raw_dir.exists():
        for path in sorted(raw_dir.glob(f"{framework}-*-changes.md")):
            parsed = _parse_filename(path.name)
            if parsed is None or parsed[0] != framework:
                continue
            _fw, hop_from, hop_to = parsed
            if _version_tuple(hop_from) >= start and _version_tuple(hop_to) <= end:
                files.append(path)
    return _score_files(files, label=framework)


def _score_files(raw_paths: list[Path], *, label: str) -> Score:
    score = Score(framework=label)
    for raw_path in raw_paths:
        text = raw_path.read_text(encoding="utf-8")
        parsed = parse_raw_markdown(text)
        if not parsed.triaged:
            score.untriaged_files.append(str(raw_path))
            continue
        entities_path = _entities_path(raw_path)
        entities = _load_entities(entities_path)
        entity_keys = [(entity, _entity_keys(entity)) for entity in entities]
        for row in parsed.rows:
            score.rows += 1
            kept = row.triage_decision != "drop"
            if row.triage_decision == "drop":
                score.dropped += 1
            row_keys = _text_keys(row.source_url, row.statement)
            matched = [
                entity
                for entity, keys in entity_keys
                if keys and (keys & row_keys or _urls_match(entity, row.source_url))
            ]
            if not matched:
                continue
            critical = any(_is_critical(str(entity.get("change_type") or "")) for entity in matched)
            score.relevant += 1
            if kept:
                score.relevant_kept += 1
            if critical:
                score.critical += 1
                if kept:
                    score.critical_kept += 1
                elif len(score.misses) < 40:
                    score.misses.append(
                        f"CRITICAL drop {row.source_url} :: {row.statement[:160]}"
                    )
            elif not kept and len(score.misses) < 40:
                score.misses.append(
                    f"drop {row.source_url} :: {row.statement[:160]}"
                )
    return score


def _passes(score: Score) -> bool:
    return (
        score.critical_recall >= CRITICAL_RECALL
        and score.recall >= RELEVANT_RECALL
        and score.drop_rate >= MIN_DROP_RATE
    )


def _print_score(score: Score) -> None:
    print(f"\n{score.framework}")
    if score.untriaged_files:
        print(f"  untriaged files skipped: {len(score.untriaged_files)}")
    if not score.rows:
        print("  no triaged rows")
        return
    status = "PASS" if _passes(score) else "FAIL"
    print(
        f"  {status}  rows={score.rows}  drop_rate={score.drop_rate:.1%}  "
        f"relevant={score.relevant_kept}/{score.relevant} ({score.recall:.1%})  "
        f"critical={score.critical_kept}/{score.critical} ({score.critical_recall:.1%})"
    )
    for miss in score.misses:
        print(f"  MISS {miss}")


def _entities_path(raw_path: Path) -> Path:
    stem = raw_path.name.removesuffix("-changes.md")
    return raw_path.parent.parent / "json" / f"{stem}-entities.json"


def _load_entities(path: Path) -> list[dict]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    entities = payload.get("entities") if isinstance(payload, dict) else None
    if not isinstance(entities, list):
        return []
    return [entity for entity in entities if isinstance(entity, dict)]


def _entity_keys(entity: dict) -> set[str]:
    parts = [
        str(entity.get("source_url") or ""),
        str(entity.get("title") or ""),
        str(entity.get("reason") or ""),
    ]
    jira = entity.get("jira_keys") or []
    if isinstance(jira, list):
        parts.extend(str(key) for key in jira)
    return _text_keys(*parts)


def _text_keys(*parts: str) -> set[str]:
    text = "\n".join(parts)
    keys: set[str] = set()
    keys.update(_JIRA_RE.findall(text))
    for match in _ISSUE_RE.finditer(text):
        number = match.group(1) or match.group(2)
        if number:
            keys.add(f"issue:{number}")
    for match in _SHA_RE.finditer(text):
        sha = match.group(1).lower()
        keys.add(f"sha:{sha}")
        keys.add(f"sha:{sha[:7]}")
        keys.add(f"sha:{sha[:10]}")
    return keys


def _urls_match(entity: dict, source_url: str) -> bool:
    left = str(entity.get("source_url") or "").rstrip("/")
    right = (source_url or "").rstrip("/")
    return bool(left and right and left == right)


def _is_critical(change_type: str) -> bool:
    text = change_type.lower().replace("-", " ").replace("_", " ")
    return "breaking" in text or "deprecat" in text or "mandatory" in text


def _parse_filename(name: str) -> tuple[str, str, str] | None:
    match = _FILE_RE.match(name)
    if match is None:
        return None
    return match.group("framework"), match.group("from"), match.group("to")


def _version_tuple(version: str) -> tuple[int, int, int]:
    numbers = [int(piece) for piece in re.findall(r"\d+", version)[:3]]
    while len(numbers) < 3:
        numbers.append(0)
    return numbers[0], numbers[1], numbers[2]


if __name__ == "__main__":
    sys.exit(main())
