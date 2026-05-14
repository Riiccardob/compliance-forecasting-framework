"""View Alert — stub."""
import streamlit as st
from dashboard.state import AppState


def render() -> None:
    state = AppState.get()
    st.title("Alert e criticità")
    st.caption("Alert strutturati con lead time, classificazione e causa radice")
    st.divider()

    if not state.pipeline_done():
        st.info("Esegui prima la pipeline nella sezione Pipeline.")
        return

    st.info("Questa sezione viene implementata nel prossimo step.")
