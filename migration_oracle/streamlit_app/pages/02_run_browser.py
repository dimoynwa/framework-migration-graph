import json
import streamlit as st

from migration_oracle.mcp.tools.artifacts import get_artifact_content, list_pipeline_runs
from migration_oracle.streamlit_app._helpers import call_tool, clear_on_nav

clear_on_nav("02_run_browser")


@st.cache_data(ttl=60)
def _cached_list_runs() -> dict:
    return list_pipeline_runs()


@st.cache_data(ttl=300)
def _cached_artifact(framework: str, from_version: str, to_version: str, artifact_type: str) -> dict:
    return get_artifact_content(framework, from_version, to_version, artifact_type)


# Wrap everything in a single replaceable container so Streamlit swaps one
# element on navigation instead of diffing every rendered markdown node.
_page = st.empty()

with _page.container():
    st.markdown("""
<div style="display:flex;align-items:center;gap:10px;margin-bottom:0.25rem;">
  <span style="font-size:22px;background:var(--accent-dim);border-radius:8px;padding:6px 10px;">📂</span>
  <div>
    <h1 style="border:none;margin:0;padding:0;font-size:22px;">Run Browser</h1>
    <p style="color:var(--text-secondary);font-size:12px;margin:0;font-family:var(--font-mono);">
      Browse past pipeline runs and inspect artifacts
    </p>
  </div>
</div>
<hr style="margin-bottom:1.5rem;" />
""", unsafe_allow_html=True)

    with st.spinner("Loading pipeline runs…"):
        result = call_tool(_cached_list_runs)

    if result is None or result.get("runs", []) == []:
        st.info("No pipeline runs found.")
        st.stop()

    runs = result["runs"]

    st.markdown("#### Select Run")
    labels = [f"{r['framework']}  →  {r['to_version']}" for r in runs]
    idx = st.selectbox(
        "Pipeline run",
        range(len(labels)),
        format_func=lambda i: labels[i],
        label_visibility="collapsed",
    )
    selected     = runs[idx]
    framework    = selected["framework"]
    from_version = selected["from_version"]
    to_version   = selected["to_version"]

    st.markdown(f"""
<div style="display:flex;gap:8px;flex-wrap:wrap;margin:0.75rem 0 1.25rem;">
  <span style="background:var(--bg-card);border:1px solid var(--border);border-radius:6px;
               padding:4px 10px;font-family:var(--font-mono);font-size:11.5px;color:var(--text-secondary);">
    ⚙ {framework}
  </span>
  <span style="background:var(--bg-card);border:1px solid var(--border);border-radius:6px;
               padding:4px 10px;font-family:var(--font-mono);font-size:11.5px;color:var(--text-secondary);">
    from {from_version}
  </span>
  <span style="background:var(--accent-dim);border:1px solid var(--accent);border-radius:6px;
               padding:4px 10px;font-family:var(--font-mono);font-size:11.5px;color:var(--accent);">
    → {to_version}
  </span>
</div>
""", unsafe_allow_html=True)

    with st.spinner("Loading artifacts…"):
        raw_resp      = call_tool(_cached_artifact, framework, from_version, to_version, "raw_md")
        filtered_resp = call_tool(_cached_artifact, framework, from_version, to_version, "filtered_md")
        entities_resp = call_tool(_cached_artifact, framework, from_version, to_version, "entities_json")

    raw_tab, filtered_tab, entities_tab = st.tabs(["📄 Raw MD", "✂️ Filtered MD", "🗂 Entities JSON"])

    with raw_tab:
        if raw_resp is None or raw_resp.get("status") != "ok":
            st.error("Artifact not found")
        else:
            st.markdown(raw_resp["content"])

    with filtered_tab:
        if filtered_resp is None or filtered_resp.get("status") != "ok":
            st.error("Artifact not found")
        else:
            st.markdown(filtered_resp["content"])

    with entities_tab:
        if entities_resp is None or entities_resp.get("status") != "ok":
            st.error("Artifact not found")
        else:
            try:
                st.json(json.loads(entities_resp["content"]), expanded=1)
            except Exception as exc:
                st.error(str(exc))
