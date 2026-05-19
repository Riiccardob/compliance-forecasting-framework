import plotly.graph_objects as go
from dash import callback, Output, Input, html
from dashboard.core.data_manager import DataManager

_MODEL_COLORS = {
    "prophet": "#c4a35a",
    "lstm":    "#8957e5",
    "arima":   "#388bfd",
    "linear":  "#7aaa8f",
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

    return cards, opts, default, expl


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

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df.index.tolist(), y=df["value"].tolist(),
        mode="lines", name=feature_key,
        line={"color": "#c4a35a", "width": 1.2},
    ))
    for ts in df.index:
        if ts_to_label.get(ts, 0):
            fig.add_vrect(x0=ts, x1=ts + 5_000_000,
                          fillcolor="#b55e5e", opacity=0.07, line_width=0)
    fig.update_layout(
        title=feature_key, xaxis_title="timestamp (us)",
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
        return _empty_fig("Previsione non disponibile"), ""

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
    fig.update_layout(
        title=f"Forecast -- {model}",
        xaxis_title="step", yaxis_title="yhat",
        legend={"bgcolor": "rgba(0,0,0,0)"},
        **_DARK_LAYOUT,
    )
    tag = html.Span(model, style={
        "backgroundColor": f"rgba({rgb},0.15)",
        "color": color,
        "padding": "2px 8px",
        "borderRadius": "2px",
        "fontSize": "11px",
        "fontFamily": "JetBrains Mono",
    })
    return fig, tag
