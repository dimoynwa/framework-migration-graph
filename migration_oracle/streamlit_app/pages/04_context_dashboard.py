import streamlit as st

from migration_oracle.mcp.tools.context import (
    close_migration_context,
    create_migration_context,
    get_pending_steps,
    update_step_status,
)
from migration_oracle.streamlit_app._constants import FRAMEWORK_DISPLAY_NAMES
from migration_oracle.streamlit_app._helpers import call_tool, framework_selectbox

st.title("Context Dashboard")

if "context_id" not in st.session_state:
    st.subheader("Load / Create Context")
    project_id = st.text_input("Project ID")
    from_version = st.text_input("From version")
    to_version = st.text_input("To version")
    cli_key = framework_selectbox("Framework", key="cd_fw", include_all=False)

    if st.button("Load / Create"):
        fw_display = FRAMEWORK_DISPLAY_NAMES[cli_key]
        response = call_tool(
            create_migration_context,
            project_id,
            from_version,
            to_version,
            fw_display,
            scanned_entities=[],
        )
        if response is not None:
            st.session_state["context_id"] = response["context_id"]
            st.session_state["context_project_id"] = response.get("project_id", project_id)
            st.session_state["context_from_version"] = response.get("from_version", from_version)
            st.session_state["context_to_version"] = response.get("to_version", to_version)
            st.session_state["context_framework"] = fw_display
            st.session_state["context_status"] = response.get("migration_status", "in-progress")
            st.session_state["context_completed_count"] = len(response.get("completed_steps", []))
            st.session_state["context_skipped_count"] = len(response.get("skipped_steps", []))
            st.rerun()
    st.stop()

context_id = st.session_state["context_id"]
st.caption(f"Status: {st.session_state['context_status']}")
col1, col2 = st.columns(2)
col1.metric("Completed", st.session_state["context_completed_count"])
col2.metric("Skipped", st.session_state["context_skipped_count"])

steps_resp = call_tool(get_pending_steps, context_id)
pending = steps_resp.get("pending_steps", []) if steps_resp else []

if not pending:
    st.info("No pending steps remaining")
else:
    st.subheader("Pending Steps")
    for step in pending:
        step_id = step.get("step_id", "")
        cols = st.columns([3, 1, 1, 1, 1, 1, 1])
        cols[0].write(step.get("summary", ""))
        cols[1].write(step.get("effort", ""))
        cols[2].write(str(step.get("automatable", "")))
        cols[3].write(step.get("scope", ""))
        cols[4].write(step.get("severity", ""))

        if cols[5].button("Mark Complete", key=f"complete_{step_id}"):
            upd = call_tool(update_step_status, context_id, step_id, outcome="completed")
            if upd is not None:
                st.session_state["context_completed_count"] = upd.get("completed_count", st.session_state["context_completed_count"])
                st.session_state["context_skipped_count"] = upd.get("skipped_count", st.session_state["context_skipped_count"])
                st.rerun()

        if cols[6].button("Skip", key=f"skip_{step_id}"):
            reason = st.text_input(f"Reason for skipping {step_id}", key=f"skip_reason_{step_id}")
            if reason:
                upd = call_tool(update_step_status, context_id, step_id, outcome="skipped", reason=reason)
                if upd is not None:
                    st.session_state["context_completed_count"] = upd.get("completed_count", st.session_state["context_completed_count"])
                    st.session_state["context_skipped_count"] = upd.get("skipped_count", st.session_state["context_skipped_count"])
                    st.rerun()

if st.session_state.get("context_status") == "in-progress":
    st.subheader("Close Context")
    final_status = st.selectbox("Final status", ["complete", "partial", "abandoned"])
    notes = st.text_area("Notes")
    if st.button("Close Context"):
        resp = call_tool(close_migration_context, context_id, final_status, notes)
        if resp is not None and resp.get("tool_status") == "ok":
            st.session_state["context_status"] = resp.get("migration_status", final_status)
            st.rerun()
