from __future__ import annotations

from typing import Any, Callable

import streamlit as st

from migration_oracle.streamlit_app._constants import FRAMEWORK_DISPLAY_NAMES


def call_tool(fn: Callable, *args: Any, **kwargs: Any) -> Any | None:
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        st.error(str(exc))
        return None


def framework_selectbox(label: str, key: str, include_all: bool = False) -> str | None:
    options: list[str | None] = list(FRAMEWORK_DISPLAY_NAMES.keys())
    display = list(FRAMEWORK_DISPLAY_NAMES.values())
    if include_all:
        options = [None] + options
        display = ["All"] + display
    idx = st.selectbox(label, range(len(display)), format_func=lambda i: display[i], key=key)
    return options[idx]


def effort_badge(effort: str) -> str:
    return {"mechanical": "🔧 Mechanical", "substantial": "⚡ Substantial"}.get(effort, effort)
