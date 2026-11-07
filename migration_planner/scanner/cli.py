"""``migration-scan``: read one service repo, write ``.migration/profile.json``.

Stdout is a single summary line, so an agent never has to read the profile:

```
scanned 4812 files · angular 19.2.0 · 61 deps · 312 symbols · 48 members · \
27 config · 4 template tokens · 3 diagnostics → .migration/profile.json (2.4 s)
```

Counts that are zero are printed too, so the format is stable while the later
026 specs add fact sections. ``--json-summary`` prints the same numbers as one
JSON object.

Exit codes (FR-1): ``0`` profile written, ``1`` usage error, ``2`` no supported
manifest found under ``PATH``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from migration_planner.scanner.contract import SCANNER_VERSION
from migration_planner.scanner.scan import NoSupportedManifest, ScanResult, scan

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_NO_MANIFEST = 2

DEFAULT_MAX_LOCATIONS = 20

_DESCRIPTION = (
    "Scan a service repository and write .migration/profile.json: framework and "
    "version, dependencies, external symbols and members, config keys, template "
    "tokens. No LLM, no network, no graph."
)


class ScanArgumentParser(argparse.ArgumentParser):
    """Argparse would exit ``2`` on a usage error; the spec reserves ``2`` for
    "no supported manifest", so usage errors exit ``1`` (FR-1)."""

    def error(self, message: str) -> None:  # type: ignore[override]
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)


def build_parser() -> argparse.ArgumentParser:
    parser = ScanArgumentParser(
        prog="migration-scan",
        description=_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "exit codes: 0 profile written, 1 usage error, 2 no supported manifest under PATH"
        ),
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        metavar="PATH",
        help="repository to scan (default: the current directory)",
    )
    parser.add_argument(
        "--out",
        metavar="FILE",
        default=None,
        help="profile path (default: PATH/.migration/profile.json)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="ignore the incremental cache (no effect until spec9 lands)",
    )
    parser.add_argument(
        "--max-locations",
        type=int,
        default=DEFAULT_MAX_LOCATIONS,
        metavar="N",
        help=f"locations stored per symbol (default: {DEFAULT_MAX_LOCATIONS}); "
        "count is always exact",
    )
    parser.add_argument(
        "--include-tests",
        dest="include_tests",
        action="store_true",
        default=True,
        help="scan test files too, flagged test: true (default)",
    )
    parser.add_argument(
        "--no-include-tests",
        dest="include_tests",
        action="store_false",
        help="drop test files at discovery",
    )
    parser.add_argument(
        "--json-summary",
        action="store_true",
        help="print the summary as one JSON object",
    )
    parser.add_argument(
        "--no-values",
        dest="no_values",
        action="store_true",
        help="store no config values (value is null in every config entry), so "
        "the profile can be attached to a CI job",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"migration-scan {SCANNER_VERSION}",
    )
    return parser


def _summary_payload(result: ScanResult) -> dict:
    summary = result.summary
    return {
        "files_scanned": summary.files_scanned,
        "files_skipped": summary.files_skipped,
        "framework": summary.framework,
        "framework_version": summary.framework_version,
        "dependencies": summary.dependencies,
        "symbols": summary.symbols,
        "members": summary.members,
        "config": summary.config,
        "template_tokens": summary.template_tokens,
        "diagnostics": summary.diagnostics,
        "out": summary.out,
        "duration_ms": summary.duration_ms,
        "unchanged": summary.unchanged,
        "scanner": SCANNER_VERSION,
    }


def _gitignore_hint(result: ScanResult) -> str:
    summary = result.summary
    if not summary.gitignore_hint:
        return ""
    return (
        "hint: add .migration/ to .gitignore "
        "(the profile is generated output; nothing was written to the file)"
    )


def _usage_error(parser: argparse.ArgumentParser, message: str) -> int:
    """Print a usage error and return ``EXIT_USAGE`` (argparse's ``error`` would exit 2)."""
    parser.print_usage(sys.stderr)
    print(f"{parser.prog}: error: {message}", file=sys.stderr)
    return EXIT_USAGE


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exit_signal:
        # ``--help`` / ``--version`` exit 0 after printing; a usage error was
        # already reported by the parser and must exit 1, not argparse's 2.
        code = exit_signal.code if isinstance(exit_signal.code, int) else EXIT_USAGE
        return EXIT_OK if code == 0 else EXIT_USAGE
    if args.max_locations < 0:
        return _usage_error(parser, "--max-locations must be zero or greater")
    root = Path(args.path).expanduser()
    if not root.exists():
        return _usage_error(parser, f"PATH does not exist: {args.path}")
    if not root.is_dir():
        return _usage_error(parser, f"PATH is not a directory: {args.path}")

    out = Path(args.out).expanduser() if args.out else None
    try:
        result = scan(
            root,
            out=out,
            include_tests=args.include_tests,
            max_locations=args.max_locations,
            no_values=args.no_values,
        )
    except NoSupportedManifest as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_NO_MANIFEST

    if args.json_summary:
        print(json.dumps(_summary_payload(result), ensure_ascii=False, sort_keys=True))
    else:
        print(result.summary.text())
        hint = _gitignore_hint(result)
        if hint:
            print(hint, file=sys.stderr)
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())


__all__ = [
    "DEFAULT_MAX_LOCATIONS",
    "EXIT_NO_MANIFEST",
    "EXIT_OK",
    "EXIT_USAGE",
    "build_parser",
    "main",
]
