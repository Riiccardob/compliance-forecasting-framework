"""View Dati — carica dataset canonico."""
from __future__ import annotations

import io
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

_CONFIG_TOPOLOGY = _ROOT / "config" / "topology.yaml"
_CONFIG_PIPELINE = _ROOT / "config" / "pipeline_params.yaml"


# ── Inizializzazione moduli ───────────────────────────────────────────────

def _init_modules(
    state: AppState,
    node_df: pd.DataFrame,
    edge_df: pd.DataFrame,
    gt_df: pd.DataFrame,
) -> dict[str, str | None]:
    results: dict[str, str | None] = {}

    try:
        from src.utils.config_loader import ConfigLoader
        config = ConfigLoader(_CONFIG_TOPOLOGY, _CONFIG_PIPELINE)
        config.load_topology()
        config.load_pipeline_params()
        state.config = config
        results["ConfigLoader"] = None
    except Exception as exc:
        state.config = None
        results["ConfigLoader"] = str(exc)
        return results

    config = state.config

    try:
        from src.layer1.topology_builder import TopologyBuilder
        tb = TopologyBuilder(config)
        tb.build()
        state.topology_builder = tb
        results["TopologyBuilder"] = None
    except Exception as exc:
        results["TopologyBuilder"] = str(exc)

    try:
        from src.layer2.atg_builder import ATGBuilder
        topo = config.load_topology()
        dp = topo["data_paths"]
        atg = ATGBuilder(
            config,
            _ROOT / dp["node_metrics_csv"],
            _ROOT / dp["edge_metrics_csv"],
            _ROOT / dp["ground_truth_csv"],
        )
        state.atg_builder = atg
        results["ATGBuilder"] = None
    except Exception as exc:
        results["ATGBuilder"] = str(exc)

    try:
        from src.layer2.pbo_builder import PBOBuilder
        pbo = PBOBuilder(config, state.topology_builder)
        state.pbo_builder = pbo
        results["PBOBuilder"] = None
    except Exception as exc:
        results["PBOBuilder"] = str(exc)

    try:
        from src.layer3.feature_selector import FeatureSelector
        fs = FeatureSelector(config, state.topology_builder)
        state.feature_selector = fs
        results["FeatureSelector"] = None
    except Exception as exc:
        results["FeatureSelector"] = str(exc)

    return results


def _load_snapshots(
    state: AppState,
    node_df: pd.DataFrame,
    edge_df: pd.DataFrame,
    gt_df: pd.DataFrame,
) -> str | None:
    try:
        atg = state.atg_builder
        snapshots = atg.build(node_df=node_df, edge_df=edge_df, gt_df=gt_df)
        from src.layer2.atg_builder import ATGBuilder
        nominal = ATGBuilder.get_nominal_snapshots(snapshots)
        anomalous = ATGBuilder.get_anomalous_snapshots(snapshots)
        state.snapshots = snapshots
        state.nominal_snapshots = nominal
        state.anomalous_snapshots = anomalous
        state.n_snapshots = len(snapshots)
        state.n_nominal = len(nominal)
        state.n_anomalous = len(anomalous)
        state.node_df = node_df
        state.edge_df = edge_df
        state.gt_df = gt_df
        return None
    except Exception as exc:
        return str(exc)


# ── Grafici ───────────────────────────────────────────────────────────────

def _timeline_chart(gt_df: pd.DataFrame) -> go.Figure:
    gt = gt_df.copy()
    gt["dt"] = pd.to_datetime(gt["timestamp"], unit="us", utc=True)
    gt["dt_str"] = gt["dt"].dt.strftime("%Y-%m-%d %H:%M:%S")
    nominal = gt[gt["label_trace"] == 0]
    anomalous = gt[gt["label_trace"] == 1]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=nominal["dt"], y=[0] * len(nominal),
        mode="markers", name="Nominale",
        marker=dict(color=PALETTE["nominal"], size=4, opacity=0.6),
        customdata=nominal[["dt_str", "fault_type", "anomaly_node_ids"]].fillna("—").values,
        hovertemplate="<b>Nominale</b><br>Timestamp: %{customdata[0]}<br><extra></extra>",
    ))
    if len(anomalous) > 0:
        fig.add_trace(go.Scatter(
            x=anomalous["dt"], y=[1] * len(anomalous),
            mode="markers", name="Anomalo",
            marker=dict(color=PALETTE["anomaly"], size=5, opacity=0.8, symbol="diamond"),
            customdata=anomalous[["dt_str", "fault_type", "anomaly_node_ids"]].fillna("—").values,
            hovertemplate=(
                "<b>Anomalo</b><br>"
                "Timestamp: %{customdata[0]}<br>"
                "Tipo: %{customdata[1]}<br>"
                "Nodi: %{customdata[2]}<br>"
                "<extra></extra>"
            ),
        ))
    fig.update_layout(
        title=dict(text="Distribuzione temporale degli snapshot",
                   font=dict(color=PALETTE["text_primary"], size=14)),
        plot_bgcolor=PALETTE["surface"], paper_bgcolor=PALETTE["surface"],
        font=dict(color=PALETTE["text_secondary"]),
        xaxis=dict(title="Timestamp", gridcolor=PALETTE["border"],
                   showgrid=True, color=PALETTE["text_secondary"]),
        yaxis=dict(title="Tipo", tickvals=[0, 1], ticktext=["Nominale", "Anomalo"],
                   gridcolor=PALETTE["border"], color=PALETTE["text_secondary"]),
        legend=dict(font=dict(color=PALETTE["text_secondary"]),
                    bgcolor=PALETTE["surface_alt"], bordercolor=PALETTE["border"]),
        margin=dict(l=60, r=20, t=50, b=50), height=280,
    )
    return fig


def _anomaly_pie(gt_df: pd.DataFrame) -> go.Figure | None:
    anomalous = gt_df[gt_df["label_trace"] == 1].copy()
    if anomalous.empty:
        return None
    counts = anomalous["fault_type"].fillna("unknown").value_counts()
    colors = [
        PALETTE["red"], PALETTE["orange"], PALETTE["yellow"],
        PALETTE["accent_blue"], PALETTE["h_cache"], PALETTE["text_secondary"],
    ]
    fig = go.Figure(go.Pie(
        labels=counts.index.tolist(),
        values=counts.values.tolist(),
        hole=0.45,
        marker=dict(colors=colors[: len(counts)],
                    line=dict(color=PALETTE["border"], width=1)),
        textfont=dict(color=PALETTE["text_primary"]),
        hovertemplate="%{label}<br>%{value} snapshot (%{percent})<extra></extra>",
    ))
    fig.update_layout(
        title=dict(text="Tipi di anomalia",
                   font=dict(color=PALETTE["text_primary"], size=13)),
        plot_bgcolor=PALETTE["surface"], paper_bgcolor=PALETTE["surface"],
        font=dict(color=PALETTE["text_secondary"]),
        legend=dict(font=dict(color=PALETTE["text_secondary"]),
                    bgcolor=PALETTE["surface_alt"]),
        margin=dict(l=10, r=10, t=50, b=10), height=280,
    )
    return fig


# ── Sezioni ───────────────────────────────────────────────────────────────

def _section_a(
    state: AppState,
) -> tuple[pd.DataFrame | None, pd.DataFrame | None, pd.DataFrame | None]:
    st.subheader("Selezione file")

    tab_auto, tab_manual = st.tabs(["Usa dati convertiti", "Carica file manualmente"])
    node_df = edge_df = gt_df = None

    with tab_auto:
        try:
            from src.utils.config_loader import ConfigLoader
            cfg = ConfigLoader(_CONFIG_TOPOLOGY, _CONFIG_PIPELINE)
            topo = cfg.load_topology()
            dp = topo["data_paths"]
            node_path = _ROOT / dp["node_metrics_csv"]
            edge_path = _ROOT / dp["edge_metrics_csv"]
            gt_path = _ROOT / dp["ground_truth_csv"]
        except Exception as exc:
            st.error(f"Errore lettura topology.yaml: {exc}")
            return None, None, None

        converted_dir = node_path.parent
        files_ok = node_path.exists() and edge_path.exists() and gt_path.exists()

        if not converted_dir.exists():
            st.warning(
                f"Directory `{converted_dir.relative_to(_ROOT)}` non trovata.\n\n"
                "Esegui prima il converter:\n```\npython run_etl.py\n```"
            )
        elif not files_ok:
            missing = [p.name for p in [node_path, edge_path, gt_path] if not p.exists()]
            st.warning(
                f"File mancanti in `{converted_dir.relative_to(_ROOT)}`: "
                f"{', '.join(missing)}\n\nEsegui il converter per generarli."
            )
        else:
            st.markdown(
                f'<div class="card">'
                f'<div style="font-size:0.8rem;color:{PALETTE["text_secondary"]};">'
                f'File disponibili in '
                f'<code style="color:{PALETTE["text_primary"]};">'
                f'{converted_dir.relative_to(_ROOT)}/</code></div>'
                f'<div style="margin-top:0.4rem;font-size:0.82rem;'
                f'color:{PALETTE["accent"]};">'
                f'{node_path.name} &nbsp; {edge_path.name} &nbsp; {gt_path.name}'
                f'</div></div>',
                unsafe_allow_html=True,
            )
            if st.button("Carica da data/converted/", key="btn_load_auto"):
                with st.spinner("Caricamento in corso..."):
                    _node_df = pd.read_csv(node_path)
                    _edge_df = pd.read_csv(edge_path)
                    _gt_df = pd.read_csv(gt_path)
                return _node_df, _edge_df, _gt_df

        if state.data_loaded():
            return state.node_df, state.edge_df, state.gt_df

    with tab_manual:
        st.caption("Carica i tre CSV prodotti dal DSBConverter nel formato canonico.")
        up_node = st.file_uploader(
            "node_metrics.csv — Feature di nodo per ogni timestamp",
            type="csv", key="up_node",
        )
        up_edge = st.file_uploader(
            "edge_metrics.csv — Feature di arco per ogni timestamp",
            type="csv", key="up_edge",
        )
        up_gt = st.file_uploader(
            "ground_truth.csv — Label temporali e metadati anomalia",
            type="csv", key="up_gt",
        )
        all_uploaded = up_node is not None and up_edge is not None and up_gt is not None
        if st.button("Carica", disabled=not all_uploaded, key="btn_load_manual"):
            with st.spinner("Caricamento in corso..."):
                _node_df = pd.read_csv(io.BytesIO(up_node.read()))
                _edge_df = pd.read_csv(io.BytesIO(up_edge.read()))
                _gt_df = pd.read_csv(io.BytesIO(up_gt.read()))
            return _node_df, _edge_df, _gt_df
        if not all_uploaded:
            st.caption("Seleziona tutti e tre i file per abilitare il caricamento.")

    return None, None, None


def _section_b(state: AppState) -> None:
    if not state.data_loaded():
        return

    st.subheader("Preview dati")

    n_types = len({
        s["anomaly_type"]
        for s in (state.anomalous_snapshots or [])
        if s.get("anomaly_type")
    })

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Snapshot totali", f"{state.n_snapshots:,}",
                  help="Finestre temporali da 5 secondi")
    with c2:
        pct_nom = state.n_nominal / state.n_snapshots * 100 if state.n_snapshots else 0
        st.metric("Nominali", f"{state.n_nominal:,}",
                  delta=f"{pct_nom:.1f}% del totale")
    with c3:
        pct_anom = state.n_anomalous / state.n_snapshots * 100 if state.n_snapshots else 0
        st.metric("Anomali", f"{state.n_anomalous:,}",
                  delta=f"{pct_anom:.1f}% del totale")
    with c4:
        st.metric("Tipi anomalia", str(n_types), help="Fault type distinti")

    col_l, col_r = st.columns(2)
    with col_l:
        st.caption("node_metrics — prime 10 righe")
        if state.node_df is not None:
            st.dataframe(state.node_df.head(10), use_container_width=True, hide_index=True)
    with col_r:
        st.caption("edge_metrics — prime 10 righe")
        if state.edge_df is not None:
            st.dataframe(state.edge_df.head(10), use_container_width=True, hide_index=True)

    if state.gt_df is not None:
        st.caption("ground_truth — prime 20 righe")
        gt_preview = state.gt_df.head(20).copy()

        def _row_color(row):
            cols = gt_preview.columns.tolist()
            if row["label_trace"] == 0:
                return [f"color: {PALETTE['nominal']}" if c == "label_trace" else "" for c in cols]
            return [f"color: {PALETTE['anomaly']}" if c == "label_trace" else "" for c in cols]

        styled = gt_preview.style.apply(_row_color, axis=1)
        st.dataframe(styled, use_container_width=True, hide_index=True)


def _section_c(state: AppState) -> None:
    if not state.data_loaded() or state.gt_df is None:
        return
    st.subheader("Distribuzione temporale")
    fig = _timeline_chart(state.gt_df)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def _section_d(state: AppState) -> None:
    if not state.data_loaded() or state.gt_df is None:
        return
    anomalous_gt = state.gt_df[state.gt_df["label_trace"] == 1]
    if anomalous_gt.empty:
        return

    st.subheader("Statistiche anomalie")
    col_table, col_pie = st.columns([3, 2])
    with col_table:
        counts = (
            anomalous_gt["fault_type"].fillna("unknown")
            .value_counts().reset_index()
        )
        counts.columns = ["anomaly_type", "conteggio"]
        counts["% del totale"] = (
            counts["conteggio"] / state.n_snapshots * 100
        ).map("{:.2f}%".format)
        counts["% degli anomali"] = (
            counts["conteggio"] / state.n_anomalous * 100
        ).map("{:.1f}%".format)
        st.dataframe(counts, use_container_width=True, hide_index=True)
    with col_pie:
        fig = _anomaly_pie(state.gt_df)
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def _section_e(
    state: AppState, module_results: dict[str, str | None] | None
) -> None:
    if not state.data_loaded() or module_results is None:
        return

    with st.expander("Moduli framework inizializzati", expanded=True):
        all_ok = all(v is None for v in module_results.values())
        for name, err in module_results.items():
            if err is None:
                st.markdown(
                    f'<div style="color:{PALETTE["accent"]};font-size:0.9rem;">'
                    f'OK &nbsp; {name}</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div style="color:{PALETTE["red"]};font-size:0.9rem;">'
                    f'ERR &nbsp; {name}</div>',
                    unsafe_allow_html=True,
                )
                st.error(f"{name}: {err}")
        if all_ok:
            st.success("Tutti i moduli inizializzati correttamente.")


# ── Entry point ───────────────────────────────────────────────────────────

def render() -> None:
    state = AppState.get()

    st.title("Carica Dataset")
    st.caption("Seleziona i file CSV canonici prodotti dal DSBConverter")
    st.divider()

    node_df, edge_df, gt_df = _section_a(state)

    module_results: dict[str, str | None] | None = None

    if node_df is not None and edge_df is not None and gt_df is not None:
        with st.spinner("Inizializzazione moduli e costruzione snapshot..."):
            module_results = _init_modules(state, node_df, edge_df, gt_df)
            if state.atg_builder is not None:
                err = _load_snapshots(state, node_df, edge_df, gt_df)
                if err:
                    st.error(f"Errore nella costruzione degli snapshot: {err}")
            else:
                st.error("ATGBuilder non inizializzato — impossibile costruire gli snapshot.")
        if state.data_loaded():
            st.success(
                f"Dataset caricato: {state.n_snapshots:,} snapshot "
                f"({state.n_nominal:,} nominali, {state.n_anomalous:,} anomali)"
            )

    st.divider()
    _section_b(state)

    if state.data_loaded():
        st.divider()
    _section_c(state)

    if state.data_loaded():
        st.divider()
    _section_d(state)

    if state.data_loaded():
        st.divider()
    _section_e(state, module_results)
