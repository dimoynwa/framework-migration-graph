from __future__ import annotations

from typing import Any, Callable

import streamlit as st

from migration_oracle.streamlit_app._constants import FRAMEWORK_DISPLAY_NAMES


def clear_on_nav(page_id: str) -> None:
    """Guarantee a clean slate when the user navigates to this page.

    On the first run after a navigation event st.session_state still holds the
    previous page's __page_id__.  We detect the change, update the sentinel,
    and call st.rerun() *before* any elements are rendered.  Streamlit then
    sends empty deltas to the frontend which unmounts every stale element from
    the old page.  The second (immediate) run renders the real content.
    """
    if st.session_state.get("__page_id__") != page_id:
        st.session_state["__page_id__"] = page_id
        st.rerun()


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
