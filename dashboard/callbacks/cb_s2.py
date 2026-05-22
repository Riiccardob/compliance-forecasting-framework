from pathlib import Path as _Path
import sys as _sys
_sys.path.insert(0, str(_Path(__file__).parent.parent.parent))

import pandas as pd
import plotly.graph_objects as go
from dash import callback, Output, Input, html
from dashboard.core.data_manager import DataManager
from src.utils.config_loader import ConfigLoader

_ROOT_CFG = _Path(__file__).parent.parent.parent
try:
    _cfg = ConfigLoader(
        _ROOT_CFG / "config" / "topology.yaml",
        _ROOT_CFG / "config" / "pipeline_params.yaml",
    )
    _step_h = float(_cfg.load_pipeline_params()
                    .get("forecasting", {})
                    .get("step_duration_hours", 24.0))
except Exception:
    _step_h = 24.0

_SLA_MAP = {
    "H_crit": {"latency_ms": 100.0, "error_rate": 0.05},
    "H_cache": {"latency_ms": 20.0,  "error_rate": 0.10},
}

_MODEL_COLORS = {
    "prophet": "#c4a35a",
    "lstm":    "#8957e5",
    "arima":   "#388bfd",
    "linear":  "#7aaa8f",
}

_MODEL_REASONS = {
    "prophet": "stagionalita/trend",
    "lstm":    "sequenze lunghe",
    "arima":   "stazionarieta",
    "linear":  "correlazione lineare",
}

_DARK_LAYOUT = {
    "paper_bgcolor": "rgba(0,0,0,0)", "plot_bgcolor": "rgba(0,0,0,0)",
    "font": {"color": "#e2ddd5", "size": 11},
    "margin": {"l": 8, "r": 8, "t": 32, "b": 8},
}

def _count_card(label: str, value: str, color: str) -> html.Div:
    return html.Div([
        html.Div(value, className="metric-value",
                 style={"fontSize": "22px", "color": color, "fontWeight": "600"}),
        html.Div(label, style={"fontSize": "11px", "color": "var(--muted)",
                               "marginTop": "4px"}),
    ], style={
        "backgroundColor": "var(--surface)",
        "border": "1px solid var(--border)",
        "padding": "14px 20px",
        "display": "flex",
        "flexDirection": "column",
        "alignItems": "center",
    })


def _empty_fig(title: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(title=title, **_DARK_LAYOUT)
    return fig


def _hex_to_rgb(hex_str: str) -> str:
    h = hex_str.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"{r},{g},{b}"


# ---------------------------------------------------------------------------
# Callback 1 -- conteggi e dropdown al cambio CS
# ---------------------------------------------------------------------------
@callback(
    Output("s2-counts", "children"),
    Output("s2-feature-dd", "options"),
    Output("s2-feature-dd", "value"),
    Output("s2-feature-explanation", "children"),
    Output("s2-intro", "children"),
    Input("s2-cs-select", "value"),
)
def update_cs(cs):
    dm      = DataManager()
    results = dm.load_pipeline_results()

    if results and cs in results.get("compliance_sets", {}):
        features     = results["compliance_sets"][cs].get("features", {})
        node_count   = sum(1 for k in features if k.startswith("node:"))
        edge_count   = sum(1 for k in features if k.startswith("edge:"))
        interf_count = sum(1 for k in features if k.startswith("interf:"))
        total        = len(features)
    else:
        features = {}
        node_count = edge_count = interf_count = total = 0

    cards = [
        _count_card("M_direct nodo", str(node_count),   "#c4a35a"),
        _count_card("M_direct arco", str(edge_count),   "#388bfd"),
        _count_card("M_interf",      str(interf_count), "#8957e5"),
        _count_card("Totale",        str(total),        "#e2ddd5"),
    ]

    opts = (
        [{"label": f"[N] {k.split(':', 1)[1]}", "value": k}
         for k in sorted(k for k in features if k.startswith("node:"))]
        + [{"label": f"[E] {k.split(':', 1)[1]}", "value": k}
           for k in sorted(k for k in features if k.startswith("edge:"))]
        + [{"label": f"[I] {k.split(':', 1)[1]}", "value": k}
           for k in sorted(k for k in features if k.startswith("interf:"))]
    )
    default = opts[0]["value"] if opts else None

    expl = html.Div(
        ("M_direct: metriche di nodo ([N]) e arco ([E]) interni al compliance set. "
         "M_interf: throughput degli archi esterni che portano carico verso nodi "
         "condivisi tra piu compliance set ([I])."),
        style={"fontSize": "11px", "color": "var(--muted)", "marginBottom": "8px"},
    )

    if cs == "H_crit":
        cs_desc = (
            "H_crit — compliance set lineare (5 nodi, 4 archi). "
            "Topologia sequenziale: il percorso critico P_cert attraversa i nodi "
            "in sequenza, quindi il PAS (Path Adherence Score) e applicabile. "
            "Le feature M_interf rappresentano il throughput degli archi esterni "
            "che portano carico verso i nodi condivisi con H_cache."
        )
    else:
        cs_desc = (
            "H_cache — compliance set parallelo (4 nodi, 3 archi). "
            "Topologia ramificata: non esiste un unico percorso critico lineare, "
            "quindi il PAS non e applicabile. "
            "Il framework usa la norma di Frobenius ||W_t - W_gold||_F come fallback "
            "per misurare la deviazione globale dal baseline di distribuzione del traffico."
        )
    intro = html.Div(
        cs_desc,
        style={
            "fontSize": "12px", "color": "var(--muted)",
            "marginBottom": "12px", "lineHeight": "1.6",
            "borderLeft": "2px solid var(--border)", "paddingLeft": "8px",
        },
    )

    return cards, opts, default, expl, intro


# ---------------------------------------------------------------------------
# Callback 2 -- serie temporale della feature selezionata
# ---------------------------------------------------------------------------
@callback(
    Output("s2-series-graph", "figure"),
    Input("s2-feature-dd", "value"),
    Input("s2-cs-select", "value"),
)
def update_series(feature_key, cs):
    if not feature_key:
        return _empty_fig("Seleziona una feature")

    dm      = DataManager()
    results = dm.load_pipeline_results()
    if not results or cs not in results.get("compliance_sets", {}):
        return _empty_fig("Pipeline non eseguita")

    features = results["compliance_sets"][cs].get("features", {})
    if feature_key not in features:
        return _empty_fig(f"{feature_key} non trovata")

    df    = features[feature_key]
    snaps = dm.get_snapshots()
    ts_to_label = {s["timestamp"]: s["label"] for s in snaps}

    x_dt = pd.to_datetime(df.index, unit="us")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x_dt.tolist(), y=df["value"].tolist(),
        mode="lines", name=feature_key,
        line={"color": "#c4a35a", "width": 1.2},
    ))
    for ts in df.index:
        if ts_to_label.get(ts, 0):
            t0 = pd.to_datetime(ts, unit="us")
            t1 = pd.to_datetime(ts + 5_000_000, unit="us")
            fig.add_vrect(x0=t0, x1=t1,
                          fillcolor="#b55e5e", opacity=0.07, line_width=0)
    fig.update_layout(
        title=feature_key, xaxis_title="data/ora (UTC)",
        yaxis_title="valore", **_DARK_LAYOUT,
    )
    return fig


# ---------------------------------------------------------------------------
# Callback 3 -- forecast con banda di confidenza
# ---------------------------------------------------------------------------
@callback(
    Output("s2-forecast-graph", "figure"),
    Output("s2-model-tag", "children"),
    Input("s2-feature-dd", "value"),
    Input("s2-cs-select", "value"),
)
def update_forecast(feature_key, cs):
    if not feature_key:
        return _empty_fig("Seleziona una feature"), ""

    dm      = DataManager()
    results = dm.load_pipeline_results()
    if not results or cs not in results.get("compliance_sets", {}):
        return _empty_fig("Pipeline non eseguita"), ""

    cs_data   = results["compliance_sets"][cs]
    forecasts = cs_data.get("forecasts", {})
    routing   = cs_data.get("routing", {})

    if feature_key not in forecasts:
        note = html.Div(
            ("Previsione non disponibile per questa feature. "
             "Cause possibili: (1) pipeline eseguita in modalita DEMO "
             "su un solo snapshot anomalo — i forecast sono calcolati "
             "solo per le feature del compliance set di quello snapshot; "
             "(2) la feature e di tipo M_interf e non ha abbastanza dati "
             "per il forecasting. Prova la modalita BATCH con piu snapshot."),
            style={"fontSize": "11px", "color": "var(--muted)",
                   "lineHeight": "1.5", "padding": "8px",
                   "backgroundColor": "var(--surface)",
                   "border": "1px solid var(--border)"},
        )
        return _empty_fig("Previsione non disponibile — vedi nota"), note

    df    = forecasts[feature_key]
    model = routing.get(feature_key, "unknown")
    color = _MODEL_COLORS.get(model, "#e2ddd5")
    rgb   = _hex_to_rgb(color)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df.index.tolist(), y=df["yhat_upper"].tolist(),
        mode="lines", line={"width": 0}, showlegend=False, name="upper",
    ))
    fig.add_trace(go.Scatter(
        x=df.index.tolist(), y=df["yhat_lower"].tolist(),
        mode="lines", fill="tonexty",
        fillcolor=f"rgba({rgb},0.12)",
        line={"width": 0}, showlegend=False, name="lower",
    ))
    fig.add_trace(go.Scatter(
        x=df.index.tolist(), y=df["yhat"].tolist(),
        mode="lines", name=model,
        line={"color": color, "width": 1.5},
    ))
    x_labels = []
    for i, _ in enumerate(df.index, start=1):
        h = i * _step_h
        if h < 24:
            x_labels.append(f"+{h:.0f}h")
        elif h % 24 == 0:
            x_labels.append(f"+{int(h/24)}g")
        else:
            x_labels.append(f"+{h/24:.1f}g")

    fig.update_layout(
        title=f"Forecast -- {model}",
        xaxis={"tickvals": df.index.tolist(), "ticktext": x_labels,
               "title": "orizzonte previsionale"},
        yaxis_title="yhat",
        legend={"bgcolor": "rgba(0,0,0,0)"},
        **_DARK_LAYOUT,
    )

    metric_name = feature_key.split(":")[-1]
    sla_val = _SLA_MAP.get(cs, {}).get(metric_name)
    if sla_val is not None:
        fig.add_hline(
            y=sla_val,
            line_dash="dash",
            line_color="#b55e5e",
            line_width=1.5,
            annotation_text=f"SLA max: {sla_val}",
            annotation_font_color="#b55e5e",
            annotation_font_size=9,
            annotation_position="top right",
        )

    reason = _MODEL_REASONS.get(model, "routing automatico")
    tag = html.Div([
        html.Span(model, style={
            "backgroundColor": f"rgba({rgb},0.15)",
            "color": color,
            "padding": "2px 8px",
            "borderRadius": "2px",
            "fontSize": "11px",
            "fontFamily": "JetBrains Mono",
            "marginRight": "8px",
        }),
        html.Span(f"selezionato per: {reason}", style={
            "fontSize": "11px",
            "color": "var(--muted)",
        }),
    ])
    return fig, tag
