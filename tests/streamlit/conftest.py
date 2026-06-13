import pytest
import streamlit as st


@pytest.fixture(autouse=True)
def clear_st_cache():
    """Clear all @st.cache_data caches before each test.

    Pages use @st.cache_data on functions like _cached_list_runs and _cached_artifact.
    Without clearing, results from one test contaminate the next.
    """
    st.cache_data.clear()
    yield
