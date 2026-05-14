"""View Risultati — stub."""
import streamlit as st
from dashboard.state import AppState


def render() -> None:
    state = AppState.get()
    st.title("Analisi risultati")
    st.caption("Previsioni, root cause e segnali strutturali per compliance set")
    st.divider()

    if not state.pipeline_done():
        st.info("Esegui prima la pipeline nella sezione Pipeline.")
        return

    st.info("Questa sezione viene implementata nel prossimo step.")
