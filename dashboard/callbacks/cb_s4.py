import plotly.graph_objects as go
from dash import callback, Output, Input, html
from dashboard.core.data_manager import DataManager

_DARK_LAYOUT = {
    "paper_bgcolor": "rgba(0,0,0,0)", "plot_bgcolor": "rgba(0,0,0,0)",
    "font": {"color": "#e2ddd5", "size": 11},
    "margin": {"l": 8, "r": 8, "t": 32, "b": 8},
}

_LIVELLI_LABELS = {
    "threshold": "Threshold",
    "zscore":    "Z-score",
    "if":        "Isol. Forest",
    "cusum":     "CUSUM",
}

_LEVEL_KEYS = {
    "threshold": lambda r: bool(r.get("threshold_violations")),
    "zscore":    lambda r: bool(r.get("zscore_violations")),
    "if":        lambda r: bool(r.get("if_signal")),
    "cusum":     lambda r: bool(r.get("cusum_signal")),
}


def _gauge_style(active: bool) -> dict:
    return {
        "position": "absolute",
        "bottom": "0",
        "width": "100%",
        "height": "100%" if active else "0%",
        "backgroundColor": "#b55e5e" if active else "#7aaa8f",
        "transition": "height 0.4s, background-color 0.4s",
    }


# ---------------------------------------------------------------------------
# Callback 1 -- popola dropdown snapshot
# ---------------------------------------------------------------------------
@callback(
    Output("s4-snap-dd", "options"),
    Output("s4-snap-dd", "value"),
    Input("s4-cs-select", "value"),
)
def populate_snap_dd(cs):
    dm      = DataManager()
    results = dm.load_pipeline_results()
    if not results or cs not in results.get("compliance_sets", {}):
        return [], None
    mon  = results["compliance_sets"][cs].get("monitor_results", [])
    opts = [
        {"label": f"snap {i} ({'AN' if m.get('base_signal') else 'OK'})",
         "value": i}
        for i, m in enumerate(mon)
    ]
    return opts, 0 if opts else None


# ---------------------------------------------------------------------------
# Callback 2 -- gauge + timeline + chart PAS/Frobenius
# ---------------------------------------------------------------------------
@callback(
    Output("s4-gauge-threshold_fill", "style"),
    Output("s4-gauge-zscore_fill",    "style"),
    Output("s4-gauge-if_fill",        "style"),
    Output("s4-gauge-cusum_fill",     "style"),
    Output("s4-timeline",             "figure"),
    Output("s4-frob-pas-chart",       "figure"),
    Input("s4-cs-select", "value"),
    Input("s4-snap-dd",   "value"),
)
def update_monitor_view(cs, snap_idx):
    dm      = DataManager()
    results = dm.load_pipeline_results()
    empty_g = _gauge_style(False)
    empty_f = go.Figure(layout={**_DARK_LAYOUT})

    if results is None or cs not in results.get("compliance_sets", {}):
        return empty_g, empty_g, empty_g, empty_g, empty_f, empty_f

    mon = results["compliance_sets"][cs].get("monitor_results", [])
    if not mon:
        return empty_g, empty_g, empty_g, empty_g, empty_f, empty_f

    idx = int(snap_idx) if snap_idx is not None and snap_idx < len(mon) else 0
    m   = mon[idx]
    g_th = _gauge_style(bool(m.get("threshold_violations")))
    g_zs = _gauge_style(bool(m.get("zscore_violations")))
    g_if = _gauge_style(bool(m.get("if_signal")))
    g_cu = _gauge_style(bool(m.get("cusum_signal")))

    # Timeline: 4 righe di marker quadrati (rosso=attivo, grigio=inattivo)
    fig_tl = go.Figure()
    for lv in ["threshold", "zscore", "if", "cusum"]:
        colors = [
            "#b55e5e" if _LEVEL_KEYS[lv](r) else "#2a2a2a"
            for r in mon
        ]
        fig_tl.add_trace(go.Scatter(
            x=[r["timestamp"] for r in mon],
            y=[_LIVELLI_LABELS[lv]] * len(mon),
            mode="markers",
            marker={"symbol": "square", "size": 6, "color": colors},
            name=_LIVELLI_LABELS[lv],
            showlegend=False,
        ))
    fig_tl.update_layout(
        title="Timeline segnali",
        xaxis_title="timestamp (us)",
        yaxis={
            "categoryorder": "array",
            "categoryarray": ["CUSUM", "Isol. Forest", "Z-score", "Threshold"],
        },
        height=160,
        **_DARK_LAYOUT,
    )

    # Dual-axis PAS + Frobenius
    ts_list   = [r["timestamp"]              for r in mon]
    pas_vals  = [r.get("pas_value")          for r in mon]
    frob_vals = [r.get("frobenius_distance") for r in mon]

    fig_pf = go.Figure()
    if any(v is not None for v in pas_vals):
        fig_pf.add_trace(go.Scatter(
            x=ts_list, y=pas_vals, name="PAS",
            line={"color": "#c4a35a", "width": 1.5}, yaxis="y1",
        ))
    if any(v is not None for v in frob_vals):
        fig_pf.add_trace(go.Scatter(
            x=ts_list, y=frob_vals, name="Frobenius",
            line={"color": "#b55e5e", "width": 1.5}, yaxis="y2",
        ))
    fig_pf.update_layout(
        title="PAS e Frobenius nel tempo",
        yaxis ={"title": "PAS",       "color": "#c4a35a", "side": "left"},
        yaxis2={"title": "Frobenius", "color": "#b55e5e",
                "overlaying": "y", "side": "right"},
        legend={"bgcolor": "rgba(0,0,0,0)"},
        **_DARK_LAYOUT,
    )
    return g_th, g_zs, g_if, g_cu, fig_tl, fig_pf


# ---------------------------------------------------------------------------
# Callback 3 -- card dettaglio MonitorResult
# ---------------------------------------------------------------------------
@callback(
    Output("s4-result-card", "children"),
    Input("s4-cs-select", "value"),
    Input("s4-snap-dd",   "value"),
)
def update_result_card(cs, snap_idx):
    dm      = DataManager()
    results = dm.load_pipeline_results()
    if not results or cs not in results.get("compliance_sets", {}):
        return html.Div("Pipeline non eseguita.", style={"color": "var(--muted)"})
    mon = results["compliance_sets"][cs].get("monitor_results", [])
    if not mon or snap_idx is None:
        return html.Div("Seleziona uno snapshot.", style={"color": "var(--muted)"})
    idx = int(snap_idx)
    if idx >= len(mon):
        return html.Div("Indice fuori range.", style={"color": "var(--muted)"})
    m = mon[idx]

    def _bool_span(v):
        color = "#b55e5e" if v else "#7aaa8f"
        return html.Span("SI" if v else "no",
                         style={"color": color, "fontFamily": "JetBrains Mono"})

    rows = [
        ("base_signal",      _bool_span(m.get("base_signal"))),
        ("if_signal",        _bool_span(m.get("if_signal"))),
        ("cusum_signal",     _bool_span(m.get("cusum_signal"))),
        ("structural_conf.", _bool_span(m.get("structural_confirmed"))),
        ("cusum_stat",       f"{m.get('cusum_stat', 0):.4f}"),
        ("frobenius",        f"{m.get('frobenius_distance') or 0:.4f}"),
        ("pas_value",        str(m.get("pas_value", "N/A"))),
        ("threshold_viol.",  str(len(m.get("threshold_violations", [])))),
        ("zscore_viol.",     str(len(m.get("zscore_violations", [])))),
    ]
    items = []
    for label, value in rows:
        val_el = value if isinstance(value, html.Span) else html.Span(
            value, style={"color": "var(--text)", "fontFamily": "JetBrains Mono"})
        items.append(html.Div([
            html.Span(label, style={"color": "var(--muted)"}),
            val_el,
        ], style={
            "display": "flex", "justifyContent": "space-between",
            "padding": "4px 0", "borderBottom": "1px solid var(--border)",
        }))

    title = html.Div(
        f"MonitorResult -- snap {idx}",
        style={"fontWeight": "600", "color": "var(--text)",
               "marginBottom": "10px", "fontSize": "12px"},
    )
    return html.Div([title] + items)
