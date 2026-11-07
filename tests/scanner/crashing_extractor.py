"""A Java extractor that kills its worker process on one file (spec9 test helper).

Module-level, so it pickles under ``spawn`` too. It only crashes in a *worker*:
``SCANNER_TEST_PARENT_PID`` is the test process, which never dies, so the
in-process fallback paths stay testable.
"""

from __future__ import annotations

import os

from migration_planner.scanner.java import extract_java

#: The file name that brings its worker down.
CRASHING_FILE = "Crash.java"


def crashing_extract_java(context):
    parent = os.environ.get("SCANNER_TEST_PARENT_PID", "")
    if context.relative.endswith(CRASHING_FILE) and str(os.getpid()) != parent:
        os._exit(139)  # what a native segfault looks like to the parent
    return extract_java(context)
