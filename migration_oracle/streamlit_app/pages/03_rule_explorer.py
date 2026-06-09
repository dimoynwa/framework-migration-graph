import asyncio
import concurrent.futures
import os

os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")

import streamlit as st

from migration_oracle.mcp.tools.search import search_migration_knowledge
from migration_oracle.streamlit_app._constants import FRAMEWORK_DISPLAY_NAMES
from migration_oracle.streamlit_app._helpers import call_tool, clear_on_nav

clear_on_nav("03_rule_explorer")

_page = st.empty()

with _page.container():
    st.markdown("""
<style>
@keyframes sweep {
    0%   { background-position: -200% center; }
    100% { background-position:  200% center; }
}
.search-loading {
    background: linear-gradient(
        90deg,
        var(--bg-card) 25%,
        var(--bg-hover) 50%,
        var(--bg-card) 75%
    );
    background-size: 200% 100%;
    animation: sweep 1.4s ease infinite;
    border-radius: var(--radius-lg);
    height: 72px;
    margin-bottom: 0.75rem;
}
.rule-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 1rem 1.25rem;
    margin-bottom: 0.75rem;
    transition: border-color 0.15s;
}
.rule-card:hover { border-color: var(--border-bright); }
.rule-type-badge {
    display: inline-block;
    background: var(--info-dim);
    color: var(--info);
    border-radius: 5px;
    padding: 2px 8px;
    font-size: 11px;
    font-family: var(--font-mono);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.6rem;
}
.rule-statement {
    font-size: 14.5px;
    font-weight: 500;
    color: var(--text);
    line-height: 1.5;
    margin-bottom: 0.5rem;
}
.rule-action {
    font-size: 13px;
    color: var(--text-secondary);
    line-height: 1.6;
}
.rule-source { margin-top: 0.5rem; font-size: 11.5px; font-family: var(--font-mono); }
.rule-source a { color: var(--accent); text-decoration: none; }
.rule-source a:hover { text-decoration: underline; }
.results-header {
    font-family: var(--font-mono);
    font-size: 11.5px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin: 1.25rem 0 0.75rem;
}
</style>
<div style="display:flex;align-items:center;gap:10px;margin-bottom:0.25rem;">
  <span style="font-size:22px;background:var(--accent-dim);border-radius:8px;padding:6px 10px;">🔍</span>
  <div>
    <h1 style="border:none;margin:0;padding:0;font-size:22px;">Rule Explorer</h1>
    <p style="color:var(--text-secondary);font-size:12px;margin:0;font-family:var(--font-mono);">
      Search the migration knowledge base
    </p>
  </div>
</div>
<hr style="margin-bottom:1.5rem;" />
""", unsafe_allow_html=True)

    col_q, col_fw, col_btn = st.columns([4, 2, 1], gap="small")

    with col_q:
        query = st.text_input(
            "Search query",
            placeholder="e.g. javax.persistence to jakarta.persistence",
            key="re_query",
            label_visibility="collapsed",
        )
    with col_fw:
        display_names = ["All frameworks"] + list(FRAMEWORK_DISPLAY_NAMES.values())
        choice = st.selectbox("Framework filter", display_names, key="re_fw", label_visibility="collapsed")
        fw: str | None = None if choice == "All frameworks" else choice

    with col_btn:
        search_clicked = st.button("Search", use_container_width=True)

    if search_clicked:
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

        skeleton_area = st.empty()
        skeleton_area.markdown(
            "".join(['<div class="search-loading"></div>'] * 4),
            unsafe_allow_html=True,
        )

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            result = call_tool(pool.submit(_run_in_new_loop).result)

        skeleton_area.empty()

        if result is None:
            st.stop()

        hits = result.get("hits", [])
        if not hits:
            st.info("No rules found for this query.")
        else:
            st.markdown(
                f'<div class="results-header">— {len(hits)} result{"s" if len(hits) != 1 else ""} found</div>',
                unsafe_allow_html=True,
            )
            for hit in hits:
                rule_type_badge = (
                    f'<div class="rule-type-badge">{hit["rule_type"]}</div>'
                    if hit.get("rule_type") else ""
                )
                source_link = (
                    f'<div class="rule-source"><a href="{hit["source_url"]}" target="_blank">↗ View source</a></div>'
                    if hit.get("source_url") else ""
                )
                action = (
                    f'<div class="rule-action">{hit["action_step"]}</div>'
                    if hit.get("action_step") else ""
                )
                st.markdown(f"""
<div class="rule-card">
  {rule_type_badge}
  <div class="rule-statement">{hit['statement']}</div>
  {action}
  {source_link}
</div>
""", unsafe_allow_html=True)
