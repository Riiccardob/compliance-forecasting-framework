"""View Panoramica - architettura del framework."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dashboard.state import AppState
from dashboard.style import PALETTE


# ── Diagramma architettura ────────────────────────────────────────────────

def _architecture_diagram() -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="markers",
                             marker=dict(opacity=0), showlegend=False, hoverinfo="skip"))

    blocks = [
        # (x0, y0, x1, y1, fill, border, tag, title, keywords, description)
        (0.01, 0.58, 0.27, 0.96,
         "rgba(88,166,255,0.12)", PALETTE["accent_blue"],
         "Layer 1", "Ipergrafo di Certificazione",
         "H_cert · Shared · A(H_Φi)",
         "Struttura statica design-time. Definisce i compliance sets H_crit e H_cache "
         "come iperarchi del service dependency graph."),

        (0.365, 0.58, 0.635, 0.96,
         "rgba(63,185,80,0.12)", PALETTE["h_cache"],
         "Layer 2", "ATG + PBO",
         "G_t · W_t · W_gold · PAS",
         "Attributed Temporal Graph dinamico + Probabilistic Behavioral Overlay. "
         "Cattura l'evoluzione temporale del sistema e la distribuzione del traffico."),

        (0.73, 0.58, 0.99, 0.96,
         "rgba(137,87,229,0.12)", "#8957E5",
         "Layer 3", "Feature Selection",
         "M_Φi · M_interf · FeatureSelector",
         "Seleziona le feature rilevanti per ogni compliance set, incluse "
         "le feature di interferenza cross-property da M_interf."),

        (0.73, 0.04, 0.99, 0.42,
         "rgba(210,153,34,0.12)", PALETTE["yellow"],
         "Fase I + II", "Forecast + Causal",
         "Prophet · ARIMA · LSTM · Granger",
         "Fase I: forecasting locale con routing automatico per feature. "
         "Fase II: causalità Pearson → Granger → Transfer Entropy."),

        (0.365, 0.04, 0.635, 0.42,
         "rgba(189,86,29,0.12)", PALETTE["orange"],
         "Fase III", "Structural Monitor",
         "Threshold · Z-score · IF · CUSUM",
         "Monitoraggio gerarchico a 4 livelli: threshold/z-score, Isolation Forest, "
         "EWMA/CUSUM, validatore strutturale con Frobenius e PAS."),

        (0.01, 0.04, 0.27, 0.42,
         "rgba(218,54,51,0.12)", PALETTE["red"],
         "Fase IV", "Alert Generator",
         "Lead time t* · Yellow/Orange/Red",
         "Sintesi semantica: aggrega previsioni, segnali strutturali e grafo causale "
         "per produrre alert con criticità e causa radice."),
    ]

    for x0, y0, x1, y1, fill, border, tag, title, keywords, desc in blocks:
        fig.add_shape(type="rect", x0=x0, y0=y0, x1=x1, y1=y1,
                      xref="paper", yref="paper",
                      fillcolor=fill, line=dict(color=border, width=1.5), layer="below")
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        fig.add_annotation(x=cx, y=cy + 0.10, xref="paper", yref="paper",
                           text=f"<b style='font-size:9px;color:{PALETTE['text_secondary']}'>{tag}</b>",
                           showarrow=False, font=dict(size=9, color=PALETTE["text_secondary"]))
        fig.add_annotation(x=cx, y=cy + 0.01, xref="paper", yref="paper",
                           text=f"<b style='font-size:13px'>{title}</b>",
                           showarrow=False, font=dict(size=13, color=PALETTE["text_primary"]))
        fig.add_annotation(x=cx, y=cy - 0.11, xref="paper", yref="paper",
                           text=f"<span style='font-size:9px;color:{border}'>{keywords}</span>",
                           showarrow=False, font=dict(size=9, color=border))

    hover_x = [0.14, 0.50, 0.86, 0.86, 0.50, 0.14]
    hover_y = [0.77, 0.77, 0.77, 0.23, 0.23, 0.23]
    fig.add_trace(go.Scatter(
        x=hover_x, y=hover_y, mode="markers",
        marker=dict(size=60, opacity=0, color="rgba(0,0,0,0)"),
        showlegend=False,
        customdata=[b[9] for b in blocks],
        text=[b[6] + " - " + b[7] for b in blocks],
        hovertemplate="<b>%{text}</b><br><br>%{customdata}<extra></extra>",
    ))

    # Frecce
    arrows = [
        (0.27, 0.77, 0.365, 0.77, PALETTE["border"]),
        (0.635, 0.77, 0.73, 0.77, PALETTE["border"]),
        (0.86, 0.58, 0.86, 0.42, PALETTE["yellow"]),
        (0.73, 0.23, 0.635, 0.23, PALETTE["orange"]),
        (0.365, 0.23, 0.27, 0.23, PALETTE["red"]),
    ]
    for ax, ay, x, y, color in arrows:
        fig.add_annotation(x=x, y=y, ax=ax, ay=ay,
                           xref="paper", yref="paper", axref="paper", ayref="paper",
                           arrowhead=2, arrowwidth=2, arrowcolor=color,
                           showarrow=True, text="")

    fig.update_layout(
        paper_bgcolor=PALETTE["background"], plot_bgcolor=PALETTE["background"],
        font=dict(color=PALETTE["text_primary"]),
        height=320, margin=dict(l=0, r=0, t=0, b=0),
        xaxis=dict(visible=False, range=[0, 1]),
        yaxis=dict(visible=False, range=[0, 1]),
        showlegend=False,
    )
    return fig


# ── Card layer e fasi ─────────────────────────────────────────────────────

def _framework_cards() -> None:
    c1, c2, c3, c4 = st.columns(4)

    cards = [
        (c1, "Layer 1 - Ipergrafo di Certificazione",
         "H_cert = (V, {H_Φ1,…,H_Φm}) - struttura statica che codifica i compliance "
         "sets. Ogni compliance set raggruppa i microservizi rilevanti per una proprietà "
         "non funzionale (latency, reliability, capacity).",
         "H_cert · Shared(H_Φi,H_Φj) · A(H_Φi) · M_interf"),

        (c2, "Layer 2 - ATG + PBO",
         "G_t = (V, E_t, X_V,t, X_E,t) - sequenza temporale di snapshot con feature di "
         "nodo persistenti e feature di arco effimere. Il PBO converte il traffico in "
         "matrice stocastica W_t e definisce il Gold Standard W_gold.",
         "ATG snapshots · W_t · W_gold · PAS · Frobenius"),

        (c3, "Fasi I + II - Forecast + Causal Analysis",
         "Fase I: forecasting locale su M_Φi con routing automatico (Prophet/LSTM/"
         "ARIMA/Linear) per ogni feature dell'arco. Fase II: analisi causale "
         "Pearson → Granger → Transfer Entropy sul grafo topologico.",
         "yhat±CI · grafo causale · intensità causale · lead time"),

        (c4, "Fasi III + IV - Monitor + Alert",
         "Fase III: monitoraggio gerarchico a 4 livelli (threshold, z-score, Isolation "
         "Forest, CUSUM+EWMA, validatore strutturale). Fase IV: aggregazione, stima "
         "lead time τ*, classificazione Yellow/Orange/Red.",
         "alert strutturato · criticità · causa radice"),
    ]

    for col, title, body, footer in cards:
        with col:
            st.markdown(
                f'<div class="card">'
                f'<div style="font-size:0.88rem;font-weight:600;color:{PALETTE["text_primary"]};'
                f'margin-bottom:0.6rem;">{title}</div>'
                f'<div style="font-size:0.8rem;color:{PALETTE["text_secondary"]};'
                f'line-height:1.55;margin-bottom:0.6rem;">{body}</div>'
                f'<div style="font-size:0.75rem;color:{PALETTE["text_secondary"]};'
                f'border-top:1px solid {PALETTE["border"]};padding-top:0.4rem;">{footer}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


# ── Tabella stato moduli ──────────────────────────────────────────────────

def _module_status_table(state: AppState) -> None:
    modules = [
        ("ConfigLoader", state.config),
        ("TopologyBuilder", state.topology_builder),
        ("ATGBuilder", state.atg_builder),
        ("PBOBuilder", state.pbo_builder),
        ("FeatureSelector", state.feature_selector),
        ("StatForecaster", state.stat_forecaster),
        ("CausalAnalyzer", state.causal_analyzer),
        ("StructuralMonitor", state.structural_monitor),
        ("AlertGenerator", state.alert_generator),
    ]

    df = pd.DataFrame([
        {
            "Modulo": name,
            "Stato": "Inizializzato" if obj is not None else "Non inizializzato",
        }
        for name, obj in modules
    ])

    def _style_stato(val: str) -> str:
        if val == "Inizializzato":
            return f"color: {PALETTE['accent']}"
        return f"color: {PALETTE['text_secondary']}"

    styled = df.style.applymap(_style_stato, subset=["Stato"])
    st.dataframe(styled, use_container_width=True, hide_index=True)


# ── Quick start ───────────────────────────────────────────────────────────

def _quick_start(state: AppState) -> None:
    steps = [
        ("Dati", "Seleziona i file CSV da data/converted/ tramite la sezione Dati"),
        ("Topologia", "Esplora il grafo H_cert, i compliance sets e i pesi PBO"),
        ("Pipeline", "Avvia l'analisi completa sulle quattro fasi"),
        ("Alert", "Consulta gli alert generati con classificazione e causa radice"),
    ]

    st.markdown(
        f'<div class="card">'
        f'<div style="font-size:0.78rem;color:{PALETTE["accent_blue"]};'
        f'text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.8rem;">'
        f'Per iniziare</div>'
        + "".join(
            f'<div style="display:flex;gap:0.6rem;margin-bottom:0.5rem;">'
            f'<span style="color:{PALETTE["accent_blue"]};font-weight:700;min-width:1.2rem;">'
            f'{i}.</span>'
            f'<span style="color:{PALETTE["text_secondary"]};font-size:0.85rem;">{desc}</span>'
            f'</div>'
            for i, (_, desc) in enumerate(steps, 1)
        )
        + f'</div>',
        unsafe_allow_html=True,
    )

    cols = st.columns(len(steps))
    for col, (page, _) in zip(cols, steps):
        with col:
            if st.button(page, key=f"qs_{page}", use_container_width=True):
                st.session_state["page"] = page
                state.current_page = page
                st.rerun()


# ── Entry point ───────────────────────────────────────────────────────────

def render() -> None:
    state = AppState.get()

    st.title("Compliance Forecasting Framework")
    st.caption(
        "Monitoraggio predittivo di proprietà non funzionali in sistemi a microservizi "
        "- Dataset: DeathStarBench Social Network · GAMMA"
    )

    col_m1, col_m2, col_m3 = st.columns(3)
    with col_m1:
        st.metric(
            "Snapshot analizzati",
            f"{state.n_snapshots:,}" if state.data_loaded() else "-",
            help="Finestre temporali da 5 secondi",
        )
    with col_m2:
        st.metric("Compliance sets", "2", help="H_crit (linear) e H_cache (parallel)")
    with col_m3:
        st.metric("Nodi nel grafo", "7", help="Microservizi DeathStarBench")

    st.divider()

    st.subheader("Architettura del framework")
    st.caption("Hover sui blocchi per i dettagli di ogni componente")
    try:
        fig = _architecture_diagram()
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    except Exception as exc:
        st.error(f"Errore nel diagramma: {exc}")

    st.divider()

    st.subheader("Layer e fasi")
    try:
        _framework_cards()
    except Exception as exc:
        st.error(f"Errore nelle card: {exc}")

    st.divider()

    st.subheader("Stato dei moduli")
    try:
        _module_status_table(state)
    except Exception as exc:
        st.error(f"Errore nella tabella: {exc}")

    st.divider()

    try:
        _quick_start(state)
    except Exception as exc:
        st.error(f"Errore quick start: {exc}")
