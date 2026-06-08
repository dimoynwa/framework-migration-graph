import asyncio
import concurrent.futures
import os

os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")

import streamlit as st

from migration_oracle.mcp.tools.search import search_migration_knowledge
from migration_oracle.streamlit_app._constants import FRAMEWORK_DISPLAY_NAMES
from migration_oracle.streamlit_app._helpers import call_tool

st.title("Rule Explorer")

query = st.text_input("Search query", key="re_query")

display_names = ["All"] + list(FRAMEWORK_DISPLAY_NAMES.values())
choice = st.selectbox("Framework filter", display_names, key="re_fw")
fw: str | None = None if choice == "All" else choice

if st.button("Search"):
    if not query.strip():
        st.info("Enter a query to search.")
        st.stop()

    def _run_in_new_loop() -> dict:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                search_migration_knowledge(query=query.strip(), framework=fw, max_results=20)
            )
        finally:
            loop.close()
            asyncio.set_event_loop(None)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        result = call_tool(pool.submit(_run_in_new_loop).result)

    if result is None:
        st.stop()

    hits = result.get("hits", [])
    if not hits:
        st.info("No rules found for this query")
    else:
        for hit in hits:
            with st.expander(hit["statement"][:80]):
                if hit.get("rule_type"):
                    st.caption(hit["rule_type"])
                if hit.get("source_url"):
                    st.markdown(f"[Source]({hit['source_url']})")
                if hit.get("action_step"):
                    st.write(hit["action_step"])
