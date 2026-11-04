"""Migration progress dashboard — re-scope pending (017-linear-file-migration-state).

The previous version depended on removed MigrationContext graph nodes and session-state
MCP tools. Progress now lives in consumer-repo ps-migration/ markdown files.
See ISSUES.md BACKLOG-017-001.
"""

import streamlit as st

from migration_oracle.streamlit_app._helpers import clear_on_nav

clear_on_nav("04_context_dashboard")

st.title("Migration Progress")
st.warning(
    "This page requires re-scoping. Graph session state (MigrationContext) was removed "
    "in 017-linear-file-migration-state. Migration progress is now tracked in "
    "`ps-migration/{framework}-{from}-to-{to}/` markdown files (plan.md, tasks.md, "
    "verification.md) in the consumer repository.",
    icon="⚠️",
)
st.markdown(
    "Track progress by opening the consumer repo's `ps-migration/` folder, or see "
    "`INSTRUCTION.md` at the migration-oracle repo root for the five-stage workflow."
)
