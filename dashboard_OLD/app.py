"""Entry point della dashboard: streamlit run dashboard/app.py"""
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

st.set_page_config(
    page_title="Compliance Forecasting Framework",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)

from dashboard.style import apply_style, PALETTE
from dashboard.state import AppState
import dashboard.views.overview as _ov
import dashboard.views.data as _da
import dashboard.views.topology as _to
import dashboard.views.pipeline as _pi
import dashboard.views.results as _re
import dashboard.views.alerts as _al

apply_style()

# ── Pagine disponibili ────────────────────────────────────────────────────
PAGES: dict[str, object] = {
    "Panoramica": _ov,
    "Dati": _da,
    "Topologia": _to,
    "Pipeline": _pi,
    "Risultati": _re,
    "Alert": _al,
}

state = AppState.get()

# Inizializza pagina corrente se non già in sessione
if "page" not in st.session_state:
    st.session_state["page"] = "Panoramica"
# Sincronizza AppState
state.current_page = st.session_state["page"]

# ── Sidebar ───────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        "<p style='font-size:11px; color:#8B949E; text-transform:uppercase; "
        "letter-spacing:1px; margin-bottom:4px; margin-top:8px;'>FRAMEWORK</p>"
        "<p style='font-size:16px; font-weight:600; color:#E6EDF3; margin-bottom:0;'>"
        "Compliance Forecasting</p>",
        unsafe_allow_html=True,
    )
    st.divider()

    # Navigazione
    current_page = st.session_state["page"]
    for label in PAGES:
        is_active = current_page == label
        if st.button(
            label,
            key=f"nav_{label}",
            use_container_width=True,
            type="primary" if is_active else "secondary",
        ):
            st.session_state["page"] = label
            state.current_page = label
            st.rerun()

    st.divider()

    # Stato sistema — compatto, nessuna icona
    dataset_status = (
        f"{state.n_snapshots:,} snapshot"
        if state.data_loaded()
        else "Nessun dataset caricato"
    )
    pipeline_status = (
        "Completata" if state.pipeline_phase == "done"
        else "In esecuzione" if state.pipeline_running
        else "Inattiva"
    )
    st.markdown(
        f"<p style='font-size:12px; color:#8B949E; line-height:1.7; margin:0;'>"
        f"Dataset: <span style='color:#E6EDF3;'>{dataset_status}</span><br>"
        f"Pipeline: <span style='color:#E6EDF3;'>{pipeline_status}</span>"
        f"</p>",
        unsafe_allow_html=True,
    )

    st.markdown(
        "<p style='font-size:11px; color:#30363D; margin-top:16px; margin-bottom:0;'>"
        "v1.0 — DSB · graph_2</p>",
        unsafe_allow_html=True,
    )

# ── Routing e Navigazione Fondo Pagina ────────────────────────────────────
page_module = PAGES.get(st.session_state["page"], _ov)
page_module.render()

st.divider()

page_names = list(PAGES.keys())
current_idx = page_names.index(st.session_state["page"])

col1, col2, col3 = st.columns([1, 2, 1])

with col1:
    if current_idx > 0:
        prev_page = page_names[current_idx - 1]
        if st.button(f"⬅️ {prev_page}", use_container_width=True):
            st.session_state["page"] = prev_page
            state.current_page = prev_page
            st.rerun()

with col3:
    if current_idx < len(page_names) - 1:
        next_page = page_names[current_idx + 1]
        if st.button(f"{next_page} ➡️", use_container_width=True):
            st.session_state["page"] = next_page
            state.current_page = next_page
            st.rerun()
