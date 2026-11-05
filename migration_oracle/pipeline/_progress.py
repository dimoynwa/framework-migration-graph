"""Progress bars for the long per-row loops (triage, research).

Bars go to stderr and only render on a terminal (``disable=None``), so logs,
CI, and tests stay clean. ``TQDM_DISABLE=1`` turns them off everywhere.
"""

from __future__ import annotations

import sys

from tqdm.auto import tqdm


def progress_bar(total: int, desc: str, *, initial: int = 0, unit: str = "row") -> tqdm:
    return tqdm(
        total=total,
        initial=initial,
        desc=desc,
        unit=unit,
        file=sys.stderr,
        disable=None,
        dynamic_ncols=True,
        leave=True,
    )
