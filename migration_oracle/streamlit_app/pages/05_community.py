import streamlit as st

from migration_oracle.mcp.tools.community import (
    get_community_insights,
    submit_migration_insight,
    vote_insight,
)
from migration_oracle.streamlit_app._constants import FRAMEWORK_DISPLAY_NAMES
from migration_oracle.streamlit_app._helpers import call_tool, framework_selectbox

st.title("Community Insights")

result = call_tool(get_community_insights)
insights = result.get("insights", []) if result else []

if not insights:
    st.info("No community insights found")
else:
    for insight in insights:
        with st.container():
            insight_id = insight.get("insight_id", "")
            st.markdown(f"**{insight.get('statement', '')}**")
            st.write(insight.get("solution", ""))
            badge = "✓ Verified" if insight.get("verified") else ""
            vote_col, badge_col = st.columns([1, 4])
            vote_col.write(f"Votes: {insight.get('votes', 0)}")
            if badge:
                badge_col.success(badge)
            if insight.get("source_url"):
                st.markdown(f"[Source]({insight['source_url']})")
            if st.button("Vote Up", key=f"vote_{insight_id}"):
                call_tool(vote_insight, insight_id=insight_id, delta=1)
                st.rerun()
            st.divider()

with st.expander("Submit New Insight"):
    with st.form("submit_insight_form"):
        statement = st.text_area("Statement")
        solution = st.text_area("Solution")
        spring_boot_version = st.text_input("Version")
        affected_classes_raw = st.text_input("Affected classes (comma-separated)")
        evidence_url = st.text_input("Evidence URL")
        cli_key = framework_selectbox("Framework", key="ci_fw")
        submit_btn = st.form_submit_button("Submit")

    if submit_btn:
        fw_display = FRAMEWORK_DISPLAY_NAMES[cli_key]
        affected_classes = [c.strip() for c in affected_classes_raw.split(",") if c.strip()]
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
                st.success("Insight submitted")
            elif resp.get("status") == "duplicate":
                st.error("Duplicate detected")
