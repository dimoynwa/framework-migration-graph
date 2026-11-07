"""Parallel parsing (spec 026 FR-10, second part).

Source extractors are pure functions of a file's content plus its module
environment, and the spec's own words are "output is identical for any
``--jobs`` value". The design follows from that:

- The **parent** process discovers files, reads manifests, hashes contents and
  decides what is fresh — a warm scan with no change parses nothing at all and
  never starts a pool (a process pool costs more than the whole warm scan).
- A **worker** only runs the extractors on files the parent handed it, in
  ``chunksize`` batches, and returns encoded facts (JSON-ready lists, not
  pickled objects, so the cache and the pool share one encoding).
- Order never matters: the parent keys results by path and merges them in
  discovery order, and the post-passes sort their own output. That is why
  ``--jobs 1`` (in-process) and ``--jobs 8`` are byte-identical.

One thing a pool cannot see is the extractor registry, so the worker gets the
registry's *contents* — the extractor functions themselves plus the
:class:`ModuleEnv` of each module. Both pickle when they are module-level
functions (every shipped extractor is); a caller that registered a closure
keeps working, because a batch that cannot be sent to a worker is parsed in
this process, which yields exactly the facts a ``--jobs 1`` scan would.

A worker that **dies** (a native crash in a grammar) never hangs the scan: the
batches it took down are re-parsed one file per process, and the file that
kills its worker again is an ``extractor_crash`` diagnostic (FR-1: one file
never fails a scan). A file that loops forever is not guarded against.
"""

from __future__ import annotations

import multiprocessing
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass
from multiprocessing.context import BaseContext
from pathlib import Path
from typing import Iterable, Sequence

from migration_planner.scanner.cache import decode_facts, encode_facts
from migration_planner.scanner.contract import (
    Diagnostic,
    FileFacts,
    ModuleEnv,
    SourceContext,
    SourceExtractor,
)

#: Files per unit of work. Small enough that one slow file cannot stall a pool,
#: large enough that IPC does not dominate on many small files.
CHUNK_SIZE = 16

#: Below this many files a pool costs more than it saves: a process has to
#: start, import the grammars and hand back results, which is tens of ms each.
#: A small repo (and every fixture) therefore parses in-process even with the
#: default ``--jobs``, and the output is the same either way.
MIN_FILES_FOR_POOL = 32


def default_jobs() -> int:
    """``--jobs`` default: the CPUs this process may use (at least one).

    ``os.cpu_count()`` is the host's count, which in a container with a CPU
    limit or under ``taskset`` starts more workers than there are CPUs. The
    usable count is ``os.process_cpu_count()`` (3.13+), else the affinity mask.
    """
    counter = getattr(os, "process_cpu_count", None)
    if counter is not None:
        count = counter()
    elif hasattr(os, "sched_getaffinity"):
        count = len(os.sched_getaffinity(0))
    else:
        count = os.cpu_count()
    return max(1, count or 1)


@dataclass(frozen=True)
class ParseJob:
    """One file to parse: everything the worker needs, and nothing else.

    ``data`` is the file's bytes, which the parent already read to hash it, so a
    worker never re-reads the file (and cannot see a different version).
    """

    relative: str
    path: Path
    module: str
    language: str
    test: bool
    data: bytes

    def context(self, env: ModuleEnv) -> SourceContext:
        return SourceContext(
            path=self.path,
            relative=self.relative,
            module=self.module,
            language=self.language,
            test=self.test,
            data=self.data,
            env=env,
        )


@dataclass
class ParseOutcome:
    """What parsing produced: usable facts per file, plus what failed.

    ``failed`` files are the ones whose extractor raised. They are **not** in
    ``facts``: the caller writes the diagnostic and leaves the file out of the
    cache, so the next scan tries it again.
    """

    facts: dict[str, FileFacts]
    failed: list[Diagnostic]


def parse_file(
    job: ParseJob,
    extractor: SourceExtractor,
    env: ModuleEnv,
) -> tuple[str, dict | None, list]:
    """Run one extractor. Never raises: an exception is a diagnostic (FR-1).

    Returns JSON-ready data so the result crosses a process boundary without
    pickling pydantic models, and so the parent can put it straight into the
    cache.
    """
    try:
        facts = extractor(job.context(env))
    except Exception as exc:  # one unparsable file never fails the scan
        return (
            job.relative,
            None,
            [["extractor_error", job.relative, None, f"{type(exc).__name__}: {exc}"]],
        )
    return job.relative, encode_facts(facts), []


def _worker(
    batch: Sequence[tuple[ParseJob, SourceExtractor, ModuleEnv]],
) -> list[tuple[str, dict | None, list]]:
    """Pool entry point: one batch of files, in this process."""
    return [parse_file(*item) for item in batch]


def _batches(
    items: Sequence[tuple[ParseJob, SourceExtractor, ModuleEnv]],
    chunk_size: int,
) -> list[list[tuple[ParseJob, SourceExtractor, ModuleEnv]]]:
    size = max(1, chunk_size)
    return [list(items[index : index + size]) for index in range(0, len(items), size)]


def parse_parallel(
    items: Sequence[tuple[ParseJob, SourceExtractor, ModuleEnv]],
    *,
    jobs: int = 1,
    chunk_size: int = CHUNK_SIZE,
    asynch: bool = False,
) -> ParseOutcome:
    """Parse ``items`` with ``jobs`` processes (``1`` stays in this process).

    ``items`` is ``(job, extractor, env)`` per file; the caller has already
    decided that each one has to be parsed (a cached file is not here at all).
    """
    outcome = ParseOutcome(facts={}, failed=[])
    results: Iterable[tuple[str, dict | None, list]]
    if jobs <= 1 or len(items) < MIN_FILES_FOR_POOL:
        results = [parse_file(*item) for item in items]
    else:
        results = _map_in_pool(
            items, jobs=min(jobs, len(items)), chunk_size=chunk_size, asynch=asynch
        )

    return _collect(results, outcome)


def _map_in_pool(
    items: Sequence[tuple[ParseJob, SourceExtractor, ModuleEnv]],
    *,
    jobs: int,
    chunk_size: int,
    asynch: bool,
) -> list[tuple[str, dict | None, list]]:
    """Run the batches in a process pool; never hang, never lose a file.

    ``concurrent.futures`` rather than ``multiprocessing.Pool``: a worker that
    dies (a native segfault in a grammar, ``os._exit``) makes every pending
    future raise :class:`BrokenProcessPool`, where ``Pool`` would wait for the
    lost task forever. The batches that did not come back are then parsed
    **one file per process** (:func:`_isolate`), so the file that kills its
    worker is found, reported as ``extractor_crash`` and left out, and every
    other file still gets its facts.

    A batch that fails for any other reason — the extractor or its environment
    does not pickle (a closure a caller registered) — is parsed in this
    process, which yields exactly the facts a ``--jobs 1`` scan would. Order
    is irrelevant either way (``asynch`` is accepted for callers, not needed):
    results are keyed by path.
    """
    del asynch
    batches = _batches(items, chunk_size)
    results: list[tuple[str, dict | None, list]] = []
    broken: list[tuple[ParseJob, SourceExtractor, ModuleEnv]] = []
    try:
        executor = ProcessPoolExecutor(max_workers=jobs, mp_context=_pool_context())
    except (OSError, ValueError, NotImplementedError):
        # No process pool in this environment (a sandbox): a slower scan.
        return [row for batch in batches for row in _worker(batch)]
    with executor:
        try:
            futures = {executor.submit(_worker, batch): batch for batch in batches}
        except BrokenProcessPool:
            futures = {}
            broken.extend(item for batch in batches for item in batch)
        for future in as_completed(futures):
            batch = futures[future]
            try:
                results.extend(future.result())
            except BrokenProcessPool:
                broken.extend(batch)
            except Exception:  # does not pickle, or the worker cannot import it
                results.extend(_worker(batch))
    if broken:
        results.extend(_isolate(broken))
    return results


def _isolate(
    items: Sequence[tuple[ParseJob, SourceExtractor, ModuleEnv]],
) -> list[tuple[str, dict | None, list]]:
    """Parse each file in a one-worker pool, replacing the worker when it dies.

    Only reached after a worker crashed, so the cost (serial parsing of the
    batches that were in flight) is paid on a broken scan only. A file whose
    worker dies again is the culprit: an ``extractor_crash`` diagnostic, no
    facts, not cached — the next scan tries it again.
    """
    results: list[tuple[str, dict | None, list]] = []
    executor: ProcessPoolExecutor | None = None
    try:
        for item in items:
            if executor is None:
                executor = ProcessPoolExecutor(max_workers=1, mp_context=_pool_context())
            try:
                results.extend(executor.submit(_worker, [item]).result())
            except BrokenProcessPool:
                job = item[0]
                results.append(
                    (
                        job.relative,
                        None,
                        [
                            [
                                "extractor_crash",
                                job.relative,
                                None,
                                "the parser process died on this file",
                            ]
                        ],
                    )
                )
                executor.shutdown(wait=False, cancel_futures=True)
                executor = None
            except Exception:
                results.extend(_worker([item]))
    finally:
        if executor is not None:
            executor.shutdown(wait=True)
    return results


def _pool_context() -> BaseContext:
    """``fork`` on Linux only; ``spawn`` everywhere else.

    ``fork`` is nearly free and safe on Linux. On macOS it is offered but
    unsafe once the parent has threads (system frameworks may hold locks in
    the child; CPython warns and has defaulted to ``spawn`` there since 3.8),
    and Windows has only ``spawn``. ``spawn`` imports this package in each
    worker, which works because every shipped extractor is a module-level
    function.
    """
    if sys.platform.startswith("linux") and "fork" in multiprocessing.get_all_start_methods():
        return multiprocessing.get_context("fork")
    return multiprocessing.get_context("spawn")


def _collect(
    results: Iterable[tuple[str, dict | None, list]],
    outcome: ParseOutcome,
) -> ParseOutcome:
    for relative, payload, diagnostics in results:
        for kind, file, line, detail in diagnostics:
            outcome.failed.append(
                Diagnostic(kind=kind, file=file, line=line, detail=detail)
            )
        if payload is None:
            continue
        try:
            outcome.facts[relative] = decode_facts(payload, relative)
        except (KeyError, TypeError, ValueError) as exc:
            outcome.failed.append(
                Diagnostic(
                    kind="extractor_error",
                    file=relative,
                    detail=f"undecodable facts: {type(exc).__name__}: {exc}",
                )
            )
    return outcome


__all__ = [
    "CHUNK_SIZE",
    "MIN_FILES_FOR_POOL",
    "ParseJob",
    "ParseOutcome",
    "default_jobs",
    "parse_file",
    "parse_parallel",
]
