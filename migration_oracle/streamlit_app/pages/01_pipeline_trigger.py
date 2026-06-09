import subprocess
import sys

import streamlit as st

from migration_oracle.streamlit_app._constants import FRAMEWORK_DISPLAY_NAMES
from migration_oracle.streamlit_app._helpers import clear_on_nav

clear_on_nav("01_pipeline_trigger")

keys   = list(FRAMEWORK_DISPLAY_NAMES.keys())
labels = list(FRAMEWORK_DISPLAY_NAMES.values())

_page = st.empty()

with _page.container():
    st.markdown("""
<style>
.page-header {
    display: flex; align-items: center; gap: 10px;
    margin-bottom: 0.25rem;
}
.page-header .icon {
    font-size: 22px;
    background: var(--accent-dim);
    border-radius: 8px;
    padding: 6px 10px;
}
.flag-pill {
    display: flex; align-items: center; gap: 6px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 6px 10px;
    font-size: 12.5px;
    font-family: var(--font-mono);
    color: var(--text-secondary);
}

/* ── spinner dot row ── */
@keyframes blink { 0%,80%,100%{opacity:0.15} 40%{opacity:1} }
.dots span {
    display: inline-block;
    width: 6px; height: 6px;
    border-radius: 50%;
    background: var(--accent);
    margin: 0 2px;
    animation: blink 1.2s infinite;
}
.dots span:nth-child(2){ animation-delay: 0.2s; }
.dots span:nth-child(3){ animation-delay: 0.4s; }
.running-banner {
    display: flex; align-items: center; gap: 10px;
    background: var(--accent-dim);
    border: 1px solid var(--accent);
    border-radius: var(--radius);
    padding: 9px 14px;
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--accent);
    margin-bottom: 1rem;
}
</style>
<div class="page-header">
  <span class="icon">🚀</span>
  <div>
    <h1 style="border:none;margin:0;padding:0;font-size:22px;">Pipeline Trigger</h1>
    <p style="color:var(--text-secondary);font-size:12px;margin:0;font-family:var(--font-mono);">
      Kick off a framework migration pipeline run
    </p>
  </div>
</div>
<hr style="margin-bottom:1.5rem;" />
""", unsafe_allow_html=True)

    left, right = st.columns([3, 2], gap="large")

    with left:
        st.markdown("#### Configure Run")
        with st.form("pipeline_form"):
            fw_idx = st.selectbox("Framework", range(len(labels)), format_func=lambda i: labels[i])
            col_from, col_to = st.columns(2)
            with col_from:
                from_version = st.text_input("From version", placeholder="e.g. 2.7.x")
            with col_to:
                to_version = st.text_input("To version", placeholder="e.g. 3.2")

            st.markdown("**Run flags**")
            c1, c2 = st.columns(2)
            with c1:
                dry_run = st.checkbox("--dry-run", help="Simulate without writing output")
                force   = st.checkbox("--force",   help="Overwrite existing results")
            with c2:
                force_extract = st.checkbox("--force-extract", help="Re-run extraction step")
                force_llm     = st.checkbox("--force-llm",     help="Re-run LLM generation step")

            submitted = st.form_submit_button("▶ Run Pipeline", use_container_width=True)

    with right:
        st.markdown("#### About this page")
        st.markdown("""
<div style="
  background:var(--bg-card);
  border:1px solid var(--border);
  border-left: 3px solid var(--accent);
  border-radius:var(--radius);
  padding:1rem 1.25rem;
  font-size:13px;
  color:var(--text-secondary);
  line-height:1.7;
">
Triggers the <code style='background:transparent;border:none;color:var(--accent);'>migration_oracle.cli</code>
CLI process for the selected framework and version range.
Output streams live below as the pipeline runs.
<br/><br/>
Use <b style='color:var(--text);'>--dry-run</b> to preview without persisting, and
<b style='color:var(--text);'>--force</b> flags to re-execute specific pipeline steps.
</div>
""", unsafe_allow_html=True)

        selected_flags = []
        if dry_run:          selected_flags.append("--dry-run")
        if force:            selected_flags.append("--force")
        if force_extract:    selected_flags.append("--force-extract")
        if force_llm:        selected_flags.append("--force-llm")

        if selected_flags:
            st.markdown("**Active flags**")
            for f in selected_flags:
                st.markdown(f'<div class="flag-pill">⚑ {f}</div>', unsafe_allow_html=True)

    if submitted:
        if not from_version.strip() or not to_version.strip():
            st.warning("⚠️ Both `from_version` and `to_version` are required.")
            st.stop()

        cli_key = keys[fw_idx]
        flag_args: list[str] = []
        if dry_run:       flag_args.append("--dry-run")
        if force:         flag_args.append("--force")
        if force_extract: flag_args.append("--force-extract")
        if force_llm:     flag_args.append("--force-llm")

        cmd = [
            sys.executable, "-m", "migration_oracle.cli",
            "--framework", cli_key,
            from_version.strip(),
            to_version.strip(),
        ] + flag_args

        st.markdown("---")
        st.markdown(f"""
<div style="
  display:flex; align-items:center; gap:10px;
  background:var(--bg-card);
  border:1px solid var(--border-bright);
  border-radius:var(--radius);
  padding:10px 14px;
  margin-bottom:1rem;
  font-family:var(--font-mono);
  font-size:12px;
  color:var(--text-secondary);
">
  <span style="color:var(--accent);">$</span>
  <span>{' '.join(cmd)}</span>
</div>
""", unsafe_allow_html=True)

        banner = st.empty()
        banner.markdown("""
<div class="running-banner">
  <div class="dots"><span></span><span></span><span></span></div>
  Pipeline running…
</div>
""", unsafe_allow_html=True)

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        output_area = st.empty()
        lines: list[str] = []
        for line in proc.stdout:
            lines.append(line.rstrip())
            output_area.code("\n".join(lines), language="bash")
        proc.wait()
        stderr_lines = proc.stderr.read().splitlines()

        banner.empty()

        if proc.returncode == 0:
            st.success("✓ Pipeline completed — Exit 0")
        else:
            last = stderr_lines[-1] if stderr_lines else "see output above"
            st.error(f"✗ Exit {proc.returncode}: {last}")
