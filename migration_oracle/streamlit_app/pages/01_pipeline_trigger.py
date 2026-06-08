import subprocess
import sys

import streamlit as st

from migration_oracle.streamlit_app._constants import FRAMEWORK_DISPLAY_NAMES

st.title("Pipeline Trigger")

keys = list(FRAMEWORK_DISPLAY_NAMES.keys())
labels = list(FRAMEWORK_DISPLAY_NAMES.values())

with st.form("pipeline_form"):
    fw_idx = st.selectbox("Framework", range(len(labels)), format_func=lambda i: labels[i])
    from_version = st.text_input("From version", placeholder="e.g. 2.7.x")
    to_version = st.text_input("To version", placeholder="e.g. 3.2")
    dry_run = st.checkbox("--dry-run")
    force = st.checkbox("--force")
    force_extract = st.checkbox("--force-extract")
    force_llm = st.checkbox("--force-llm")
    submitted = st.form_submit_button("Submit")

if submitted:
    if not from_version.strip() or not to_version.strip():
        st.warning("Both from_version and to_version are required.")
        st.stop()

    cli_key = keys[fw_idx]
    flag_args: list[str] = []
    if dry_run:
        flag_args.append("--dry-run")
    if force:
        flag_args.append("--force")
    if force_extract:
        flag_args.append("--force-extract")
    if force_llm:
        flag_args.append("--force-llm")

    cmd = [
        sys.executable, "-m", "migration_oracle.cli",
        "--framework", cli_key,
        from_version.strip(),
        to_version.strip(),
    ] + flag_args

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    output_area = st.empty()
    lines: list[str] = []
    for line in proc.stdout:
        lines.append(line.rstrip())
        output_area.code("\n".join(lines))
    proc.wait()
    stderr_lines = proc.stderr.read().splitlines()

    if proc.returncode == 0:
        st.success("Exit 0")
    else:
        last = stderr_lines[-1] if stderr_lines else "see output above"
        st.error(f"Exit {proc.returncode}: {last}")
