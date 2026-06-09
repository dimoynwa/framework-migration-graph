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

/* vote button pulsing state */
@keyframes vote-flash {
    0%   { background:var(--accent-dim); border-color:var(--accent); color:var(--accent); }
    50%  { background:var(--accent);     border-color:var(--accent); color:var(--accent-text); }
    100% { background:var(--accent-dim); border-color:var(--accent); color:var(--accent); }
}
.voting-btn {
    animation: vote-flash 0.6s ease;
    border-radius: var(--radius);
    border: 1px solid var(--accent);
    padding: 4px 10px;
    font-size: 13px;
    font-family: var(--font-ui);
    cursor: not-allowed;
    width: 100%;
}

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

    skel = st.empty()
    skel.markdown(
        "".join(['<div class="skeleton-card"></div>'] * 3),
        unsafe_allow_html=True,
    )
    result = call_tool(get_community_insights)
    skel.empty()

    insights = result.get("insights", []) if result else []

    if not insights:
        st.info("No community insights found yet — be the first to contribute!")
    else:
        st.markdown(f"""
<div style="font-family:var(--font-mono);font-size:11.5px;color:var(--muted);
            text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.75rem;">
  — {len(insights)} insight{"s" if len(insights)!=1 else ""}
</div>
""", unsafe_allow_html=True)

        for insight in insights:
            insight_id  = insight.get("insight_id", "")
            verified    = insight.get("verified", False)
            card_class  = "insight-card verified" if verified else "insight-card"
            voting_key  = f"voting_{insight_id}"

            source_html = (
                f'<a class="source-link" href="{insight["source_url"]}" target="_blank">↗ Source</a>'
                if insight.get("source_url") else ""
            )
            verified_html = (
                '<span class="verified-badge">✓ Verified</span>' if verified else ""
            )

            col_card, col_vote = st.columns([8, 1], gap="small")

            with col_card:
                st.markdown(f"""
<div class="{card_class}">
  <div class="insight-statement">{insight.get('statement', '')}</div>
  <div class="insight-solution">{insight.get('solution', '')}</div>
  <div class="insight-footer">
    <span class="vote-badge">▲ {insight.get('votes', 0)}</span>
    {verified_html}
    {source_html}
  </div>
</div>
""", unsafe_allow_html=True)

            with col_vote:
                st.write("")
                if st.session_state.get(voting_key):
                    st.markdown('<div class="voting-btn">▲</div>', unsafe_allow_html=True)
                    call_tool(vote_insight, insight_id=insight_id, delta=1)
                    del st.session_state[voting_key]
                    st.rerun()
                elif st.button("▲", key=f"vote_{insight_id}", help="Vote up this insight"):
                    st.session_state[voting_key] = True
                    st.rerun()

    st.markdown("---")
    with st.expander("＋ Submit New Insight"):
        with st.form("submit_insight_form"):
            statement = st.text_area("Statement", placeholder="Describe the migration issue…")
            solution  = st.text_area("Solution",  placeholder="How to fix or work around it…")

            col_ver, col_ev = st.columns(2)
            with col_ver:
                spring_boot_version = st.text_input("Spring Boot version", placeholder="e.g. 3.2.0")
            with col_ev:
                evidence_url = st.text_input("Evidence URL", placeholder="https://…")

            affected_classes_raw = st.text_input(
                "Affected classes",
                placeholder="com.example.Foo, org.bar.Baz (comma-separated)",
            )
            cli_key    = framework_selectbox("Framework", key="ci_fw")
            submit_btn = st.form_submit_button("Submit Insight", use_container_width=True)

        if submit_btn:
            fw_display       = FRAMEWORK_DISPLAY_NAMES[cli_key]
            affected_classes = [c.strip() for c in affected_classes_raw.split(",") if c.strip()]
            with st.spinner("Submitting insight…"):
                resp = call_tool(
                    submit_migration_insight,
                    statement=statement,
                    solution=solution,
                    spring_boot_version=spring_boot_version,
                    affected_classes=affected_classes,
                    evidence_url=evidence_url,
                    framework=fw_display,
                )
            if resp is not None:
                if resp.get("status") == "ok":
                    st.success("✓ Insight submitted — thank you!")
                elif resp.get("status") == "duplicate":
                    st.warning("⚠️ This insight appears to be a duplicate.")
