"""Tool-call tracing for dev/test sessions.

Activated by setting MCP_TRACE_FILE to a path (e.g. runs/traces/session.jsonl).
Each tool invocation appends one JSON line:

    {"ts": "...", "tool": "...", "args": {...}, "reasoning": "...", "elapsed_ms": 42.1, "result": [...]}

The LLM can include a special "_reasoning" key in any tool's arguments to record
its thinking alongside the call.  The key is stripped before the tool sees it.
"""

from __future__ import annotations

import json
import os
import time
import types
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

_REASONING_KEY = "_reasoning"


def _trace_path() -> Path | None:
    val = os.environ.get("MCP_TRACE_FILE", "").strip()
    return Path(val) if val else None


def _serialise_result(result: Any) -> Any:
    """Convert MCP ContentBlock sequence or plain dict to JSON-safe form."""
    if isinstance(result, dict):
        return result
    if isinstance(result, (list, tuple)):
        out = []
        for item in result:
            if hasattr(item, "model_dump"):
                out.append(item.model_dump())
            elif hasattr(item, "__dict__"):
                out.append(vars(item))
            else:
                out.append(str(item))
        return out
    return str(result)


def _append_record(record: dict) -> None:
    path = _trace_path()
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")


def install_tracing(mcp_instance: Any) -> None:
    """Wrap mcp_instance.call_tool to log every invocation to MCP_TRACE_FILE."""
    original = mcp_instance.__class__.call_tool

    async def _traced(self: Any, name: str, arguments: dict[str, Any]) -> Sequence[Any] | dict[str, Any]:
        reasoning = arguments.pop(_REASONING_KEY, None)
        t0 = time.monotonic()
        result = await original(self, name, arguments)
        elapsed_ms = round((time.monotonic() - t0) * 1000, 1)
        _append_record(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "tool": name,
                "args": arguments,
                "reasoning": reasoning,
                "elapsed_ms": elapsed_ms,
                "result": _serialise_result(result),
            }
        )
        return result

    mcp_instance.call_tool = types.MethodType(_traced, mcp_instance)
