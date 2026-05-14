"""View Pipeline — stub."""
import streamlit as st
from dashboard.state import AppState


def render() -> None:
    state = AppState.get()
    st.title("Esegui pipeline")
    st.caption("Esecuzione delle quattro fasi: forecasting · causal · anomaly · alert")
    st.divider()

    if not state.data_loaded():
        st.info("Carica prima i dati nella sezione Dati per abilitare l'esecuzione.")
        return

    st.info("Questa sezione viene implementata nel prossimo step.")
