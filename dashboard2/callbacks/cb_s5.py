import plotly.graph_objects as go
from dash import callback, Output, Input, State, html, ALL
from dash import ctx as dash_ctx
from dashboard.core.data_manager import DataManager

_CRIT_COLOR = {
    "yellow": "#c4a35a",
    "orange": "#c4a35a",
    "red":    "#b55e5e",
}
_CRIT_BG = {
    "yellow": "rgba(196,163,90,0.12)",
    "orange": "rgba(196,163,90,0.22)",
    "red":    "rgba(181,94,94,0.18)",
}
_DARK_LAYOUT = {
    "paper_bgcolor": "rgba(0,0,0,0)", "plot_bgcolor": "rgba(0,0,0,0)",
    "font": {"color": "#e2ddd5", "size": 11},
    "margin": {"l": 8, "r": 8, "t": 32, "b": 8},
}


def _th(width: int) -> dict:
    return {"width": f"{width}px", "minWidth": f"{width}px", "fontWeight": "600"}


def _td(width: int, mono: bool = False, color: str = "var(--text)") -> dict:
    s = {"width": f"{width}px", "minWidth": f"{width}px", "color": color,
         "overflow": "hidden", "textOverflow": "ellipsis", "whiteSpace": "nowrap"}
    if mono:
        s["fontFamily"] = "JetBrains Mono, monospace"
    return s


def _build_gantt(alerts: list) -> go.Figure:
    fig = go.Figure(go.Bar(
        x=[a["timestamp"] for a in alerts],
        y=[a["cs"] for a in alerts],
        marker_color=[_CRIT_COLOR.get(a.get("criticality"), "#5a5a5a") for a in alerts],
        orientation="v",
        width=[5_000_000 for _ in alerts],
    ))
    fig.update_layout(
        barmode="overlay",
        title="Distribuzione criticita",
        xaxis_title="timestamp (us)",
        yaxis={"categoryorder": "array", "categoryarray": ["H_crit", "H_cache"]},
        legend={"bgcolor": "rgba(0,0,0,0)"},
        **_DARK_LAYOUT,
    )
    return fig


# ---------------------------------------------------------------------------
# Callback 1 -- tabella alert + gantt
# ---------------------------------------------------------------------------
@callback(
    Output("s5-table", "children"),
    Output("s5-gantt", "figure"),
    Input("s5-crit-filter", "value"),
    Input("s5-cs-filter",   "value"),
    Input("s5-type-filter", "value"),
)
def update_table(crit_filter, cs_filter, type_filter):
    dm      = DataManager()
    results = dm.load_pipeline_results()
    snaps   = dm.get_snapshots()
    ts_to_type = {s["timestamp"]: s.get("anomaly_type") for s in snaps}

    if not results:
        return (html.Div("Pipeline non eseguita.",
                         style={"color": "var(--muted)", "padding": "20px"}),
                go.Figure(layout={**_DARK_LAYOUT}))

    all_alerts = []
    for cs, cs_data in results.get("compliance_sets", {}).items():
        if cs not in (cs_filter or []):
            continue
        for a in cs_data.get("alerts", []):
            crit = a.get("criticality", "")
            if crit not in (crit_filter or []):
                continue
            anom_type = ts_to_type.get(a.get("timestamp"))
            if anom_type not in (type_filter or []) and anom_type is not None:
                continue
            all_alerts.append({**a, "cs": cs, "anomaly_type": anom_type or "N/A"})

    all_alerts.sort(key=lambda x: x.get("timestamp", 0))

    if not all_alerts:
        empty = html.Div("Nessun alert per i filtri correnti.",
                         style={"color": "var(--muted)", "padding": "20px"})
        return empty, go.Figure(layout={**_DARK_LAYOUT})

    header = html.Div([
        html.Span("Timestamp",    style=_th(120)),
        html.Span("CS",           style=_th(80)),
        html.Span("Criticita",    style=_th(80)),
        html.Span("Proprieta",    style=_th(100)),
        html.Span("Lead (steps)", style=_th(100)),
        html.Span("Root cause",   style=_th(200)),
    ], style={"display": "flex", "padding": "6px 10px",
              "backgroundColor": "var(--surface)",
              "borderBottom": "1px solid var(--border)",
              "fontSize": "11px", "color": "var(--muted)",
              "letterSpacing": "0.04em"})

    rows = []
    for i, a in enumerate(all_alerts):
        crit  = a.get("criticality", "")
        color = _CRIT_COLOR.get(crit, "#e2ddd5")
        bg    = _CRIT_BG.get(crit, "rgba(0,0,0,0)")
        rows.append(html.Div([
            html.Span(str(a.get("timestamp", 0)),          style=_td(120, mono=True)),
            html.Span(a.get("cs", ""),                     style=_td(80)),
            html.Span(crit.upper(),                        style=_td(80, color=color)),
            html.Span(a.get("property_at_risk", ""),       style=_td(100)),
            html.Span(str(a.get("lead_time_steps", "")),   style=_td(100, mono=True)),
            html.Span(str(a.get("root_cause", "N/A"))[:40], style=_td(200, mono=True)),
        ], id={"type": "s5-alert-row", "index": i},
           n_clicks=0,
           style={"display": "flex", "padding": "6px 10px",
                  "borderBottom": "1px solid var(--border)",
                  "cursor": "pointer", "backgroundColor": bg,
                  "transition": "background-color 0.1s"}))

    table = html.Div([header] + rows,
                     style={"backgroundColor": "var(--surface)",
                            "border": "1px solid var(--border)"})
    return table, _build_gantt(all_alerts)


def _row(k: str, v: str) -> html.Div:
    return html.Div([
        html.Span(k, style={"color": "var(--muted)"}),
        html.Span(v, style={"color": "var(--text)", "fontFamily": "JetBrains Mono"}),
    ], style={"display": "flex", "justifyContent": "space-between",
              "padding": "4px 0", "borderBottom": "1px solid var(--border)"})


# ---------------------------------------------------------------------------
# Callback 2a -- salva alert nel Store al click sulla riga
# ---------------------------------------------------------------------------
@callback(
    Output("s5-selected-alert", "data"),
    Input({"type": "s5-alert-row", "index": ALL}, "n_clicks"),
    State("s5-crit-filter", "value"),
    State("s5-cs-filter",   "value"),
    State("s5-type-filter", "value"),
    prevent_initial_call=True,
)
def store_selected_alert(all_n_clicks, crit_f, cs_f, type_f):
    if not any(all_n_clicks):
        return None
    triggered = dash_ctx.triggered_id
    if triggered is None or not isinstance(triggered, dict):
        return None
    idx = triggered["index"]

    dm      = DataManager()
    results = dm.load_pipeline_results()
    snaps   = dm.get_snapshots()
    ts_to_type = {s["timestamp"]: s.get("anomaly_type") for s in snaps}
    if not results:
        return None

    all_alerts = []
    for cs, cs_data in results.get("compliance_sets", {}).items():
        if cs_f and cs not in cs_f:
            continue
        for a in cs_data.get("alerts", []):
            crit = a.get("criticality", "")
            if crit_f and crit not in crit_f:
                continue
            anom_type = ts_to_type.get(a.get("timestamp"))
            if type_f and anom_type not in type_f and anom_type is not None:
                continue
            all_alerts.append({**a, "cs": cs, "anomaly_type": anom_type or "N/A"})
    all_alerts.sort(key=lambda x: x.get("timestamp", 0))

    if idx >= len(all_alerts):
        return None
    return all_alerts[idx]


# ---------------------------------------------------------------------------
# Callback 2b -- aggiorna pannelli dettaglio dallo Store
# ---------------------------------------------------------------------------
@callback(
    Output("s5-detail-panel", "children"),
    Output("s5-gt-panel",     "children"),
    Input("s5-selected-alert", "data"),
)
def show_alert_detail(alert_data):
    if not alert_data:
        return (
            html.Div("Seleziona un alert dalla tabella.", style={"color": "var(--muted)"}),
            html.Div("Ground truth vs previsione.",       style={"color": "var(--muted)"}),
        )
    a = alert_data
    fields = [
        ("CS",           a.get("cs", "")),
        ("Criticita",    a.get("criticality", "").upper()),
        ("Proprieta",    a.get("property_at_risk", "")),
        ("Lead steps",   str(a.get("lead_time_steps", ""))),
        ("Lead hours",   f"{a.get('lead_time_hours', 0):.1f} h"),
        ("SLA thresh.",  str(a.get("sla_threshold", ""))),
        ("SLA bound",    a.get("sla_bound", "")),
        ("Arc critico",  str(a.get("critical_arc", ""))),
        ("Root cause",   str(a.get("root_cause", "N/A"))),
        ("Cross-prop.",  str(a.get("cross_property_interference", "N/A"))),
        ("Uncertainty",  "SI" if a.get("model_uncertainty_flag") else "no"),
    ]
    detail = html.Div(
        [html.Div("Alert",
                  style={"fontWeight": "600", "color": "var(--text)", "marginBottom": "10px"})]
        + [_row(k, v) for k, v in fields]
    )

    dm    = DataManager()
    snaps = dm.get_snapshots()
    ts    = a.get("timestamp", 0)
    snap  = next((s for s in snaps if s["timestamp"] == ts), None)
    gt_rows: list[tuple[str, str]] = []
    if snap:
        gt_rows = [
            ("label GT",     "ANOMALO" if snap["label"] else "nominale"),
            ("anomaly_type", snap.get("anomaly_type", "N/A") or "N/A"),
            ("nodi anomali", ", ".join(snap.get("anomaly_node_ids", []))),
        ]
    sigs = a.get("structural_signals", {})
    sig_rows = [
        ("base_signal",  "SI" if sigs.get("base_signal")         else "no"),
        ("if_signal",    "SI" if sigs.get("if_signal")           else "no"),
        ("cusum_signal", "SI" if sigs.get("cusum_signal")        else "no"),
        ("struct_conf.", "SI" if sigs.get("structural_confirmed") else "no"),
        ("frobenius",    f"{sigs.get('frobenius_distance') or 0:.4f}"),
        ("pas_value",    str(sigs.get("pas_value", "N/A"))),
    ]
    gt_panel = html.Div(
        [html.Div("GT vs Segnali strutturali",
                  style={"fontWeight": "600", "color": "var(--text)", "marginBottom": "10px"})]
        + [_row(k, v) for k, v in (gt_rows + sig_rows)]
    )
    return detail, gt_panel
