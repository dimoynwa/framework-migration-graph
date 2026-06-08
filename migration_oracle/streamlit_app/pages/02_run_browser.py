import json

import streamlit as st

from migration_oracle.mcp.tools.artifacts import get_artifact_content, list_pipeline_runs
from migration_oracle.streamlit_app._helpers import call_tool


st.title("Run Browser")


@st.cache_data(ttl=60)
def _cached_list_runs() -> dict:
    return list_pipeline_runs()


result = call_tool(_cached_list_runs)

if result is None or result.get("runs", []) == []:
    st.info("No pipeline runs found")
    st.stop()

runs = result["runs"]
labels = [f"{r['framework']} → {r['to_version']}" for r in runs]
idx = st.selectbox("Select run", range(len(labels)), format_func=lambda i: labels[i])
selected = runs[idx]
framework = selected["framework"]
from_version = selected["from_version"]
to_version = selected["to_version"]

raw_tab, filtered_tab, entities_tab = st.tabs(["Raw MD", "Filtered MD", "Entities JSON"])

with raw_tab:
    resp = call_tool(get_artifact_content, framework, from_version, to_version, "raw_md")
    if resp is None or resp.get("status") != "ok":
        st.error("Artifact not found")
    else:
        st.markdown(resp["content"])

with filtered_tab:
    resp = call_tool(get_artifact_content, framework, from_version, to_version, "filtered_md")
    if resp is None or resp.get("status") != "ok":
        st.error("Artifact not found")
    else:
        st.markdown(resp["content"])

with entities_tab:
    resp = call_tool(get_artifact_content, framework, from_version, to_version, "entities_json")
    if resp is None or resp.get("status") != "ok":
        st.error("Artifact not found")
    else:
        try:
            st.json(json.loads(resp["content"]), expanded=1)
        except Exception as exc:
            st.error(str(exc))
