import pandas as pd
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


def _mini_card(label: str, value: int, color: str) -> html.Div:
    return html.Div([
        html.Div(str(value), style={
            "fontSize": "18px", "color": color,
            "fontFamily": "JetBrains Mono, monospace", "fontWeight": "600",
        }),
        html.Div(label, style={
            "fontSize": "11px", "color": "var(--muted)", "marginTop": "2px",
        }),
    ], style={
        "backgroundColor": "var(--surface)",
        "border": "1px solid var(--border)",
        "padding": "8px 12px",
        "flex": "1",
    })


def _fmt_ts(ts_us: int) -> str:
    if not ts_us:
        return "N/A"
    try:
        return pd.to_datetime(ts_us, unit="us").strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts_us)


_GANTT_COLORS = {
    "yellow": "#c4a35a",
    "orange": "#e07b39",
    "red":    "#b55e5e",
}

def _build_gantt(alerts: list) -> go.Figure:
    by_crit: dict = {}
    for a in alerts:
        crit = a.get("criticality", "other")
        by_crit.setdefault(crit, []).append(a)

    fig = go.Figure()
    for crit, items in by_crit.items():
        xs = [pd.to_datetime(a["timestamp"], unit="us", utc=True) for a in items]
        ys = [a["cs"] for a in items]
        color = _GANTT_COLORS.get(crit, "#5a5a5a")
        fig.add_trace(go.Scatter(
            x=xs, y=ys,
            mode="markers",
            marker={"symbol": "square", "size": 10, "color": color},
            name=crit.capitalize(),
            showlegend=True,
        ))

    fig.update_layout(
        title="Distribuzione temporale alert",
        xaxis_title="data/ora (UTC)",
        yaxis={
            "categoryorder": "array",
            "categoryarray": ["H_cache", "H_crit"],
        },
        legend={
            "bgcolor": "rgba(0,0,0,0)",
            "orientation": "h",
            "yanchor": "bottom", "y": 1.02,
            "xanchor": "left",   "x": 0,
        },
        height=180,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": "#e2ddd5", "size": 11},
        margin={"l": 50, "r": 10, "t": 32, "b": 40},
    )
    return fig


# ---------------------------------------------------------------------------
# Callback 1 -- riepilogo + tabella alert + gantt
# ---------------------------------------------------------------------------
_EMPTY_SUMMARY = [
    _mini_card("Alert totali", 0, "#e2ddd5"),
    _mini_card("Yellow",       0, "#c4a35a"),
    _mini_card("Orange",       0, "#e07b39"),
    _mini_card("Red",          0, "#b55e5e"),
]


@callback(
    Output("s5-summary", "children"),
    Output("s5-table",   "children"),
    Output("s5-gantt",   "figure"),
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
        return (_EMPTY_SUMMARY,
                html.Div("Pipeline non eseguita.",
                         style={"color": "var(--muted)", "padding": "20px"}),
                go.Figure(layout={**_DARK_LAYOUT}))

    all_alerts = []
    for cs, cs_data in results.get("compliance_sets", {}).items():
        if cs_filter and cs not in cs_filter:
            continue
        for a in cs_data.get("alerts", []):
            crit = a.get("criticality", "")
            if crit_filter and crit not in crit_filter:
                continue
            anom_type = ts_to_type.get(a.get("timestamp"))
            if type_filter and anom_type is not None and anom_type not in type_filter:
                continue
            all_alerts.append({**a, "cs": cs, "anomaly_type": anom_type or "N/A"})

    all_alerts.sort(key=lambda x: x.get("timestamp", 0))

    n_yellow = sum(1 for a in all_alerts if a.get("criticality") == "yellow")
    n_orange = sum(1 for a in all_alerts if a.get("criticality") == "orange")
    n_red    = sum(1 for a in all_alerts if a.get("criticality") == "red")
    summary_cards = [
        _mini_card("Alert totali", len(all_alerts), "#e2ddd5"),
        _mini_card("Yellow",       n_yellow,        "#c4a35a"),
        _mini_card("Orange",       n_orange,        "#e07b39"),
        _mini_card("Red",          n_red,           "#b55e5e"),
    ]

    if not all_alerts:
        empty = html.Div("Nessun alert per i filtri correnti.",
                         style={"color": "var(--muted)", "padding": "20px"})
        return summary_cards, empty, go.Figure(layout={**_DARK_LAYOUT})

    header = html.Div([
        html.Span("Timestamp",    style=_th(160)),
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
            html.Span(_fmt_ts(a.get("timestamp", 0)),        style=_td(160, mono=True)),
            html.Span(a.get("cs", ""),                      style=_td(80)),
            html.Span(crit.upper(),                         style=_td(80, color=color)),
            html.Span(a.get("property_at_risk", ""),        style=_td(100)),
            html.Span(str(a.get("lead_time_steps", "")),    style=_td(100, mono=True)),
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
    return summary_cards, table, _build_gantt(all_alerts)


# ---------------------------------------------------------------------------
# Callback 1b -- opzioni tipo anomalia dinamiche
# ---------------------------------------------------------------------------
@callback(
    Output("s5-type-filter", "options"),
    Output("s5-type-filter", "value"),
    Input("active-section", "data"),
)
def update_type_filter_options(section):
    if section != "s5":
        return [], []
    dm    = DataManager()
    snaps = dm.get_snapshots()
    types = sorted({s.get("anomaly_type") for s in snaps if s.get("anomaly_type")})
    opts  = [{"label": t, "value": t} for t in types]
    return opts, types


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

    _SEP = html.Div(style={"borderTop": "1px solid var(--border)", "margin": "10px 0"})
    _SEC = lambda t: html.Div(t, style={  # noqa: E731
        "fontWeight": "600", "color": "var(--text)",
        "marginBottom": "6px", "fontSize": "12px",
    })
    _COLORED_ROW = lambda k, v, c: html.Div([  # noqa: E731
        html.Span(k, style={"color": "var(--muted)"}),
        html.Span(v, style={"color": c, "fontFamily": "JetBrains Mono, monospace",
                            "fontSize": "11px", "fontWeight": "600"}),
    ], style={"display": "flex", "justifyContent": "space-between",
              "padding": "4px 0", "borderBottom": "1px solid var(--border)"})

    # -- Ground Truth section --
    if snap:
        label_text  = "ANOMALO" if snap["label"] else "nominale"
        label_color = "#b55e5e" if snap["label"] else "#7aaa8f"
        import json as _json
        raw_nodes = snap.get("anomaly_node_ids") or "[]"
        try:
            nodes_list = (_json.loads(raw_nodes)
                          if isinstance(raw_nodes, str)
                          else (raw_nodes or []))
        except (ValueError, TypeError):
            nodes_list = []
        nodes_txt = ", ".join(nodes_list) if nodes_list else "N/A"
        gt_section  = [
            _row("Tipo fault:",   snap.get("anomaly_type", "N/A") or "N/A"),
            _COLORED_ROW("Label reale:", label_text, label_color),
            _row("Nodi anomali:", nodes_txt),
        ]
    else:
        gt_section = [_row("Snapshot", "N/A")]

    # -- Framework prediction section --
    crit       = a.get("criticality", "")
    crit_color = {"yellow": "#c4a35a", "orange": "#e07b39",
                  "red": "#b55e5e"}.get(crit, "#e2ddd5")
    steps      = a.get("lead_time_steps", 0) or 0
    hours      = a.get("lead_time_hours",  0) or 0
    root_cause = str(a.get("root_cause", "") or "N/A")
    if len(root_cause) > 40:
        root_cause = root_cause[:37] + "..."

    pred_section = [
        _COLORED_ROW("Criticita:", crit.upper() if crit else "N/A", crit_color),
        _row("Lead time:",           f"{steps} step ({hours:.0f}h)"),
        _row("Proprieta a rischio:", a.get("property_at_risk", "N/A") or "N/A"),
        _row("Causa radice:",        root_cause),
        _row("Flag incertezza:",     "SI" if a.get("model_uncertainty_flag") else "no"),
    ]

    gt_panel = html.Div([
        _SEC("Ground Truth"),
        *gt_section,
        _SEP,
        _SEC("Previsione framework"),
        *pred_section,
    ])
    return detail, gt_panel
