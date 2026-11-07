"""Native-parser stability guard (spec 026 AC-11, review 2026-11-06).

py-tree-sitter 0.26.0 segfaults inside the TS extractor on ordinary, larger
test files: the AC-11 run on a real Angular service (``paysafe-wac-web-login-fe``)
crashed on 22 of 631 files, and the synthetic spec file below — nested
``describe`` / ``it`` blocks with many member accesses on one imported
binding — reproduces it at ~800 lines. 0.24 and 0.25 are fine, so
``pyproject.toml`` pins ``tree-sitter>=0.25,<0.26``.

A segfault kills the interpreter, so the extractor runs in a subprocess: the
test then fails with the exit code instead of taking pytest down with it.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap


def _synthetic_spec_file() -> str:
    lines = ["import { Helpers } from './helpers';", "describe('Helpers', () => {"]
    for group in range(30):
        lines.append(f"  describe('group{group}', () => {{")
        lines.append(
            f"    const fixture{group} = [{{ title: 'a' }}, {{ title: 'b' }}];"
        )
        for case in range(6):
            lines.append(f"    it('case {group}-{case}', () => {{")
            lines.append(
                f"      const result = Helpers.check{case}(fixture{group}, 'title');"
            )
            lines.append(
                f"      expect(Helpers.other{case}(result))"
                f".toEqual(Helpers.expected(() => {{ /* x */ }}));"
            )
            lines.append("    });")
        lines.append("  });")
    lines.append("});")
    return "\n".join(lines) + "\n"


_RUNNER = textwrap.dedent(
    """
    import sys
    from pathlib import Path
    from migration_planner.scanner.contract import SourceContext
    from migration_planner.scanner.ts import extract_ts

    data = sys.stdin.buffer.read()
    facts = extract_ts(
        SourceContext(path=Path("a.spec.ts"), relative="a.spec.ts", module=".",
                      language="ts", data=data)
    )
    print(len(facts.own_member_bindings))
    """
)


def test_the_installed_tree_sitter_is_below_0_26() -> None:
    from importlib.metadata import version

    major, minor = (int(part) for part in version("tree-sitter").split(".")[:2])
    assert (major, minor) < (0, 26), (
        "py-tree-sitter 0.26.0 segfaults; see module docstring"
    )


def test_a_large_spec_file_does_not_crash_the_extractor() -> None:
    completed = subprocess.run(
        [sys.executable, "-c", _RUNNER],
        input=_synthetic_spec_file().encode("utf-8"),
        capture_output=True,
        timeout=120,
        check=False,
    )

    assert completed.returncode == 0, (
        f"extractor exited {completed.returncode} (139 / -11 = segfault): "
        f"{completed.stderr.decode('utf-8', 'replace')[-500:]}"
    )
    # Every ``Helpers.x`` access on the own-code binding is kept for spec4.
    assert int(completed.stdout.decode().strip()) > 300
