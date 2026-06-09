import streamlit as st

from migration_oracle.mcp.tools.context import (
    close_migration_context,
    create_migration_context,
    get_pending_steps,
    update_step_status,
)
from migration_oracle.streamlit_app._constants import FRAMEWORK_DISPLAY_NAMES
from migration_oracle.streamlit_app._helpers import call_tool, clear_on_nav, framework_selectbox

clear_on_nav("04_context_dashboard")

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

.btn-loading {
    display:flex; align-items:center; justify-content:center; gap:8px;
    background:var(--accent-dim) !important;
    border:1px solid var(--accent) !important;
    border-radius:var(--radius);
    padding:7px 14px;
    font-family:var(--font-mono);
    font-size:12px;
    color:var(--accent);
    width:100%;
    cursor:not-allowed;
}
.step-card {
    background:var(--bg-card); border:1px solid var(--border);
    border-radius:var(--radius-lg); padding:0.85rem 1rem;
    margin-bottom:0.6rem; transition:border-color 0.15s;
}
.step-card:hover { border-color:var(--border-bright); }
.step-summary { flex:1; font-size:13.5px; color:var(--text); line-height:1.5; }
.step-meta { display:flex; gap:6px; flex-wrap:wrap; margin-top:4px; }
.pill {
    font-family:var(--font-mono); font-size:10.5px; padding:2px 7px;
    border-radius:5px; border:1px solid var(--border);
    color:var(--text-secondary); background:var(--bg-surface);
    text-transform:uppercase; letter-spacing:0.04em;
}
.pill.effort-mechanical { color:var(--info);    border-color:var(--info);    background:var(--info-dim); }
.pill.effort-substantial{ color:var(--warning); border-color:var(--warning); background:var(--warning-dim); }
.pill.severity-high     { color:var(--danger);  border-color:var(--danger);  background:var(--danger-dim); }
.status-bar {
    background:var(--bg-card); border:1px solid var(--border);
    border-radius:var(--radius); padding:8px 14px;
    font-family:var(--font-mono); font-size:11.5px; color:var(--text-secondary);
    margin-bottom:1.25rem; display:flex; align-items:center; gap:8px;
}
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
.setup-card {
    background:var(--bg-card); border:1px solid var(--border);
    border-radius:var(--radius-lg); padding:1.5rem;
    max-width:560px; margin:2rem auto;
}
</style>
<div style="display:flex;align-items:center;gap:10px;margin-bottom:0.25rem;">
  <span style="font-size:22px;background:var(--accent-dim);border-radius:8px;padding:6px 10px;">📋</span>
  <div>
    <h1 style="border:none;margin:0;padding:0;font-size:22px;">Context Dashboard</h1>
    <p style="color:var(--text-secondary);font-size:12px;margin:0;font-family:var(--font-mono);">
      Track and manage migration contexts
    </p>
  </div>
</div>
<hr style="margin-bottom:1.5rem;" />
""", unsafe_allow_html=True)

    # ── Load / Create context ─────────────────────────────────────────────────
    if "context_id" not in st.session_state:
        st.markdown('<div class="setup-card">', unsafe_allow_html=True)
        st.markdown("#### Load / Create Context")
        project_id = st.text_input("Project ID", placeholder="e.g. my-api-service")
        col_fv, col_tv = st.columns(2)
        with col_fv:
            from_version = st.text_input("From version", placeholder="e.g. 2.7")
        with col_tv:
            to_version = st.text_input("To version", placeholder="e.g. 3.2")
        cli_key = framework_selectbox("Framework", key="cd_fw", include_all=False)

        load_btn = st.button("Load / Create Context", use_container_width=True)

        if load_btn:
            fw_display = FRAMEWORK_DISPLAY_NAMES[cli_key]
            with st.spinner("Creating context…"):
                response = call_tool(
                    create_migration_context,
                    project_id, from_version, to_version, fw_display,
                    scanned_entities=[],
                )
            if response is not None:
                st.session_state["context_id"]              = response["context_id"]
                st.session_state["context_project_id"]      = response.get("project_id", project_id)
                st.session_state["context_from_version"]    = response.get("from_version", from_version)
                st.session_state["context_to_version"]      = response.get("to_version", to_version)
                st.session_state["context_framework"]       = fw_display
                st.session_state["context_status"]          = response.get("migration_status", "in-progress")
                st.session_state["context_completed_count"] = len(response.get("completed_steps", []))
                st.session_state["context_skipped_count"]   = len(response.get("skipped_steps", []))
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
        st.stop()

    # ── Active context view ───────────────────────────────────────────────────
    context_id = st.session_state["context_id"]
    status     = st.session_state["context_status"]
    dot_color  = "var(--accent)" if status == "in-progress" else "var(--muted)"

    st.markdown(f"""
<div class="status-bar">
  <span style="width:7px;height:7px;border-radius:50%;background:{dot_color};
               display:inline-block;animation:pulse 2s infinite;"></span>
  Context&nbsp;<code style='background:transparent;border:none;color:var(--accent);'>{context_id}</code>
  &nbsp;·&nbsp; status: <b style='color:var(--text);'>{status}</b>
  &nbsp;·&nbsp; {st.session_state.get('context_framework','')}
  &nbsp;·&nbsp; {st.session_state.get('context_from_version','')} → {st.session_state.get('context_to_version','')}
</div>
""", unsafe_allow_html=True)

    m1, m2, m3 = st.columns(3)
    m1.metric("Completed", st.session_state["context_completed_count"])
    m2.metric("Skipped",   st.session_state["context_skipped_count"])

    # ── Pending steps ─────────────────────────────────────────────────────────
    with st.spinner("Loading pending steps…"):
        steps_resp = call_tool(get_pending_steps, context_id)
    pending = steps_resp.get("pending_steps", []) if steps_resp else []

    st.markdown("---")

    if not pending:
        st.info("✓ No pending steps remaining — context is clear.")
    else:
        st.markdown(f"""
<div style="font-family:var(--font-mono);font-size:11.5px;color:var(--muted);
            text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.75rem;">
  — {len(pending)} pending step{"s" if len(pending)!=1 else ""}
</div>
""", unsafe_allow_html=True)

        for step in pending:
            step_id        = step.get("step_id", "")
            effort         = step.get("effort", "")
            severity       = step.get("severity", "")
            effort_class   = f"effort-{effort.lower()}" if effort else ""
            severity_class = f"severity-{severity.lower()}" if severity else ""
            completing_key = f"completing_{step_id}"
            skipping_key   = f"skipping_{step_id}"

            with st.container():
                col_info, col_actions = st.columns([5, 2])

                with col_info:
                    st.markdown(f"""
<div class="step-card" style="flex-direction:column;align-items:flex-start;">
  <div class="step-summary">{step.get('summary', '')}</div>
  <div class="step-meta">
    {'<span class="pill '+effort_class+'">'+effort+'</span>' if effort else ''}
    {'<span class="pill '+severity_class+'">'+severity+'</span>' if severity else ''}
    {'<span class="pill">'+step.get('scope','')+'</span>' if step.get('scope') else ''}
    {'<span class="pill">auto</span>' if step.get('automatable') else ''}
  </div>
</div>
""", unsafe_allow_html=True)

                with col_actions:
                    if st.session_state.get(completing_key):
                        st.markdown("""
<div class="btn-loading">
  <div class="dots"><span></span><span></span><span></span></div>
  Saving…
</div>
""", unsafe_allow_html=True)
                        upd = call_tool(update_step_status, context_id, step_id, outcome="completed")
                        if upd is not None:
                            st.session_state["context_completed_count"] = upd.get("completed_count", st.session_state["context_completed_count"])
                            st.session_state["context_skipped_count"]   = upd.get("skipped_count",   st.session_state["context_skipped_count"])
                        del st.session_state[completing_key]
                        st.rerun()
                    elif st.button("✓ Complete", key=f"complete_{step_id}", use_container_width=True):
                        st.session_state[completing_key] = True
                        st.rerun()

                    if st.session_state.get(skipping_key):
                        st.markdown("""
<div class="btn-loading">
  <div class="dots"><span></span><span></span><span></span></div>
  Skipping…
</div>
""", unsafe_allow_html=True)
                        upd = call_tool(update_step_status, context_id, step_id, outcome="skipped")
                        if upd is not None:
                            st.session_state["context_completed_count"] = upd.get("completed_count", st.session_state["context_completed_count"])
                            st.session_state["context_skipped_count"]   = upd.get("skipped_count",   st.session_state["context_skipped_count"])
                        del st.session_state[skipping_key]
                        st.rerun()
                    elif st.button("→ Skip", key=f"skip_{step_id}", use_container_width=True):
                        st.session_state[skipping_key] = True
                        st.rerun()

    # ── Close context ─────────────────────────────────────────────────────────
    if st.session_state.get("context_status") == "in-progress":
        st.markdown("---")
        with st.expander("⊠  Close Context"):
            final_status = st.selectbox("Final status", ["complete", "partial", "abandoned"])
            notes        = st.text_area("Notes", placeholder="Optional closing notes…")
            if st.button("Close Context", use_container_width=True):
                with st.spinner("Closing context…"):
                    resp = call_tool(close_migration_context, context_id, final_status, notes)
                if resp is not None and resp.get("tool_status") == "ok":
                    st.session_state["context_status"] = resp.get("migration_status", final_status)
                    st.rerun()
