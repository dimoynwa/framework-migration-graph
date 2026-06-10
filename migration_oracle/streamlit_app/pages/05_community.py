import html as _html

import streamlit as st

from migration_oracle.mcp.tools.community import (
    get_community_insights,
    submit_migration_insight,
    vote_insight,
)
from migration_oracle.streamlit_app._constants import FRAMEWORK_DISPLAY_NAMES
from migration_oracle.streamlit_app._helpers import call_tool, clear_on_nav, framework_selectbox

clear_on_nav("05_community")

_page = st.empty()

with _page.container():
    st.markdown("""
<style>
@keyframes blink { 0%,80%,100%{opacity:0.15} 40%{opacity:1} }
.dots span {
    display:inline-block; width:6px; height:6px;
    border-radius:50%; background:var(--accent);
    margin:0 2px; animation:blink 1.2s infinite;
}
.dots span:nth-child(2){ animation-delay:0.2s; }
.dots span:nth-child(3){ animation-delay:0.4s; }

@keyframes sweep {
    0%   { background-position: -200% center; }
    100% { background-position:  200% center; }
}
.skeleton-card {
    background: linear-gradient(
        90deg,
        var(--bg-card) 25%,
        var(--bg-hover) 50%,
        var(--bg-card) 75%
    );
    background-size: 200% 100%;
    animation: sweep 1.4s ease infinite;
    border-radius: var(--radius-lg);
    height: 110px;
    margin-bottom: 0.75rem;
}

.insight-card {
    background:var(--bg-card); border:1px solid var(--border);
    border-radius:var(--radius-lg); padding:1.1rem 1.25rem;
    margin-bottom:0.75rem;
    transition:border-color 0.15s, transform 0.15s;
    position:relative;
}
.insight-card:hover { border-color:var(--border-bright); transform:translateY(-1px); }
.insight-card.verified { border-left:3px solid var(--accent); }
.insight-statement { font-size:14.5px; font-weight:600; color:var(--text); margin-bottom:0.5rem; line-height:1.5; }
.insight-solution  { font-size:13px; color:var(--text-secondary); line-height:1.65; margin-bottom:0.75rem; }
.insight-footer    { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
.vote-badge {
    display:inline-flex; align-items:center; gap:5px;
    font-family:var(--font-mono); font-size:11.5px; color:var(--text-secondary);
    background:var(--bg-surface); border:1px solid var(--border);
    border-radius:6px; padding:3px 8px;
}
.verified-badge {
    display:inline-flex; align-items:center; gap:4px;
    font-size:11.5px; font-family:var(--font-mono);
    color:var(--accent); background:var(--accent-dim);
    border:1px solid var(--accent); border-radius:6px; padding:3px 8px;
    text-transform:uppercase; letter-spacing:0.05em;
}
.source-link { font-size:11.5px; font-family:var(--font-mono); color:var(--info); text-decoration:none; }
.source-link:hover { text-decoration:underline; }

/* Controls row (search + framework selector) */
.controls-row {
    display: flex;
    align-items: flex-end;
    gap: 10px;
    margin-bottom: 1rem;
}

/* Framework badge on each card */
.fw-badge {
    display: inline-flex;
    align-items: center;
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--info);
    background: var(--info-dim);
    border: 1px solid var(--info);
    border-radius: 5px;
    padding: 2px 7px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}

/* Version badge on each card */
.ver-badge {
    display: inline-flex;
    align-items: center;
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--muted);
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: 5px;
    padding: 2px 7px;
}

/* Vote loading div — static accent state during API call */
.voting-loading {
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--accent-dim);
    border: 1px solid var(--accent);
    border-radius: var(--radius);
    color: var(--accent);
    font-size: 13px;
    font-family: var(--font-ui);
    cursor: not-allowed;
    width: 100%;
    min-height: 38px;
    margin-top: 28px;
}
</style>
<div style="display:flex;align-items:center;gap:10px;margin-bottom:0.25rem;">
  <span style="font-size:22px;background:var(--accent-dim);border-radius:8px;padding:6px 10px;">💬</span>
  <div>
    <h1 style="border:none;margin:0;padding:0;font-size:22px;">Community Insights</h1>
    <p style="color:var(--text-secondary);font-size:12px;margin:0;font-family:var(--font-mono);">
      Shared migration knowledge from the community
    </p>
  </div>
</div>
<hr style="margin-bottom:1.5rem;" />
""", unsafe_allow_html=True)

    col_search, col_fw = st.columns([3, 2], gap="small")
    with col_fw:
        cli_key = framework_selectbox("Framework", key="ci_fw_filter")
        fw_display = FRAMEWORK_DISPLAY_NAMES[cli_key]
    with col_search:
        search_term = st.text_input(
            "Search insights",
            placeholder="Filter by keyword…",
            key="community_search",
            label_visibility="visible",
        )

    # Cache fetched insights per framework in session state so that typing
    # in the search box does not trigger a fresh API call on every keystroke.
    cache_key = f"community_insights_{fw_display}"
    if cache_key not in st.session_state:
        skel = st.empty()
        skel.markdown(
            "".join(['<div class="skeleton-card"></div>'] * 3),
            unsafe_allow_html=True,
        )
        result = call_tool(get_community_insights, framework=fw_display)
        skel.empty()
        st.session_state[cache_key] = result.get("insights", []) if result else []

    all_insights = st.session_state[cache_key]

    # Filter in-memory; no API call needed when the search term changes.
    q = search_term.strip().lower()
    if q:
        insights = [
            i for i in all_insights
            if q in i.get("statement", "").lower()
            or q in i.get("solution", "").lower()
        ]
    else:
        insights = all_insights

    if not insights:
        st.info("No community insights found yet — be the first to contribute!")
    else:
        filter_label = f'"{search_term.strip()}" · ' if search_term.strip() else ""
        st.markdown(f"""
<div style="font-family:var(--font-mono);font-size:11.5px;color:var(--muted);
            text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.75rem;">
  — {len(insights)} insight{"s" if len(insights)!=1 else ""}
  {f'· {_html.escape(filter_label)}' if filter_label else ""}
  · {_html.escape(fw_display)}
</div>
""", unsafe_allow_html=True)

        for insight in insights:
            insight_id  = insight.get("insight_id", "")
            verified    = insight.get("verified", False)
            card_class  = "insight-card verified" if verified else "insight-card"
            voting_key  = f"voting_{insight_id}"

            # Fix: source_url was built but never inserted into the card HTML.
            source_url = insight.get("source_url", "")
            source_html = (
                f'<a class="source-link" href="{_html.escape(source_url)}" target="_blank">↗ Source</a>'
                if source_url else ""
            )
            verified_html = (
                '<span class="verified-badge">✓ Verified</span>' if verified else ""
            )

            col_card, col_vote = st.columns([8, 1], gap="small")

            with col_card:
                stmt      = _html.escape(insight.get("statement", ""))
                soln      = _html.escape(insight.get("solution",  ""))
                ver       = _html.escape(insight.get("version",   ""))
                votes     = insight.get("votes", 0)
                fw_badge  = f'<span class="fw-badge">{_html.escape(fw_display)}</span>'
                ver_badge = f'<span class="ver-badge">v{ver}</span>' if ver else ""
                card_html = (
                    f'<div class="{card_class}">'
                    f'<div class="insight-statement">{stmt}</div>'
                    f'<div class="insight-solution">{soln}</div>'
                    f'<div class="insight-footer">'
                    f'<span class="vote-badge">&#9650; {votes}</span>'
                    f'{verified_html}'
                    f'{fw_badge}'
                    f'{ver_badge}'
                    f'{source_html}'
                    f'</div>'
                    f'</div>'
                )
                st.markdown(card_html, unsafe_allow_html=True)

            with col_vote:
                if st.session_state.get(voting_key):
                    st.markdown('<div class="voting-loading">▲</div>', unsafe_allow_html=True)
                    call_tool(vote_insight, insight_id=insight_id, delta=1)
                    del st.session_state[voting_key]
                    # Invalidate the cache so the updated vote count is fetched
                    # on the next rerun rather than showing a stale value.
                    st.session_state.pop(cache_key, None)
                    st.rerun()
                else:
                    st.button("▲", key=f"vote_{insight_id}", help="Vote up this insight",
                              on_click=lambda _k=voting_key: st.session_state.update({_k: True}))

    st.markdown("---")
    with st.expander("＋ Submit New Insight"):
        with st.form("submit_insight_form"):
            statement = st.text_area("Statement", placeholder="Describe the migration issue…")
            solution  = st.text_area("Solution",  placeholder="How to fix or work around it…")

            col_ver, col_ev = st.columns(2)
            with col_ver:
                spring_boot_version = st.text_input(
                    "Framework version",
                    placeholder="e.g. 3.2 for Spring Boot, 30 for WildFly",
                )
            with col_ev:
                evidence_url = st.text_input("Evidence URL", placeholder="https://…")

            affected_classes_raw = st.text_input(
                "Affected classes",
                placeholder="com.example.Foo, org.bar.Baz (comma-separated)",
            )
            affected_dependencies_raw = st.text_input(
                "Affected dependencies",
                placeholder="org.springframework:spring-web, com.example:lib (comma-separated)",
            )
            submit_cli_key    = framework_selectbox("Framework", key="ci_fw_submit")
            submit_btn = st.form_submit_button("Submit Insight", use_container_width=True)

        if submit_btn:
            submit_fw_display     = FRAMEWORK_DISPLAY_NAMES[submit_cli_key]
            affected_classes      = [c.strip() for c in affected_classes_raw.split(",") if c.strip()]
            affected_dependencies = [d.strip() for d in affected_dependencies_raw.split(",") if d.strip()]
            with st.spinner("Submitting insight…"):
                resp = call_tool(
                    submit_migration_insight,
                    statement=statement,
                    solution=solution,
                    spring_boot_version=spring_boot_version,
                    affected_classes=affected_classes,
                    affected_dependencies=affected_dependencies,
                    evidence_url=evidence_url,
                    framework=submit_fw_display,
                )
            if resp is not None:
                if resp.get("status") == "ok":
                    # Invalidate cache so the newly submitted insight appears.
                    st.session_state.pop(f"community_insights_{submit_fw_display}", None)
                    st.success("✓ Insight submitted — thank you!")
                elif resp.get("status") == "duplicate":
                    st.warning("⚠️ This insight appears to be a duplicate.")