import pandas as pd
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

_FIELD_LABELS = {
    "base_signal":     ("Anomalia rilevata",
                        "True se almeno Threshold o Z-score hanno segnalato"),
    "if_signal":       ("Isolation Forest",
                        "ML multivariato (attivo solo se anomalia rilevata)"),
    "cusum_signal":    ("CUSUM accumulato",
                        "Degrado comportamentale nel tempo (S_t > 5.0)"),
    "structural_conf": ("Conferma strutturale",
                        "Tutti i livelli attivi + Frobenius > soglia x 3 finestre"),
    "cusum_stat":      ("Valore CUSUM (S_t)",
                        "Accumulatore CUSUM. Su DSB rimane 0 (dataset limit.)"),
    "frobenius":       ("Distanza Frobenius",
                        "||W_t - W_gold||_F. Su DSB = 0 sempre"),
    "pas_value":       ("PAS corrente",
                        "Path Adherence Score sul percorso critico H_crit"),
    "threshold_viol":  ("Soglie SLA violate",
                        "Feature le cui metriche superano la soglia SLA certificata"),
    "zscore_viol":     ("Anomalie z-score",
                        "Feature con |z| > 3.0 rispetto al comportamento nominale"),
}


def _gauge_style(active: bool) -> dict:
    return {
        "position": "absolute",
        "bottom": "0",
        "width": "100%",
        "height": "100%" if active else "20%",
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
    mon        = results["compliance_sets"][cs].get("monitor_results", [])
    snaps      = dm.get_snapshots()
    ts_to_type = {s["timestamp"]: s.get("anomaly_type") for s in snaps}
    opts = []
    for i, m in enumerate(mon):
        m_ts  = m.get("timestamp")
        atype = ts_to_type.get(m_ts, "") if m_ts is not None else ""
        if m.get("base_signal"):
            lbl = "snap " + str(i) + " (AN" + (f" - {atype}" if atype else "") + ")"
        else:
            lbl = f"snap {i} (OK)"
        opts.append({"label": lbl, "value": i})
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
    Output("s4-gauge-threshold_val",  "children"),
    Output("s4-gauge-zscore_val",     "children"),
    Output("s4-gauge-if_val",         "children"),
    Output("s4-gauge-cusum_val",      "children"),
    Input("s4-cs-select", "value"),
    Input("s4-snap-dd",   "value"),
)
def update_monitor_view(cs, snap_idx):
    dm      = DataManager()
    results = dm.load_pipeline_results()
    empty_g = _gauge_style(False)
    empty_f = go.Figure(layout={**_DARK_LAYOUT})

    if results is None or cs not in results.get("compliance_sets", {}):
        return empty_g, empty_g, empty_g, empty_g, empty_f, empty_f, "--", "--", "--", "--"

    mon = results["compliance_sets"][cs].get("monitor_results", [])
    if not mon:
        return empty_g, empty_g, empty_g, empty_g, empty_f, empty_f, "--", "--", "--", "--"

    idx = int(snap_idx) if snap_idx is not None and snap_idx < len(mon) else 0
    m   = mon[idx]
    g_th = _gauge_style(bool(m.get("threshold_violations")))
    g_zs = _gauge_style(bool(m.get("zscore_violations")))
    g_if = _gauge_style(bool(m.get("if_signal")))
    g_cu = _gauge_style(bool(m.get("cusum_signal")))

    v_th = str(len(m.get("threshold_violations", [])))
    v_zs = str(len(m.get("zscore_violations", [])))
    v_if = "SI" if m.get("if_signal") else "no"
    v_cu = f"{m.get('cusum_stat', 0):.3f}"

    # Timeline: 4 righe segnali + 1 riga Ground Truth
    all_snaps   = DataManager().get_snapshots()
    ts_to_label = {s["timestamp"]: s["label"] for s in all_snaps}
    mon_timestamps = [m.get("timestamp") for m in mon]
    mon_ts_dt = [
        pd.to_datetime(ts, unit="us") if ts is not None else None
        for ts in mon_timestamps
    ]

    fig_tl = go.Figure()
    for lv in ["threshold", "zscore", "if", "cusum"]:
        colors = [
            "#b55e5e" if _LEVEL_KEYS[lv](r) else "#2a2a2a"
            for r in mon
        ]
        fig_tl.add_trace(go.Scatter(
            x=mon_ts_dt,
            y=[_LIVELLI_LABELS[lv]] * len(mon),
            mode="markers",
            marker={"symbol": "square", "size": 6, "color": colors},
            name=_LIVELLI_LABELS[lv],
            showlegend=False,
        ))

    gt_colors = [
        "#b55e5e" if ts_to_label.get(ts, 0) else "#7aaa8f"
        for ts in mon_timestamps
    ]
    fig_tl.add_trace(go.Scatter(
        x=mon_ts_dt,
        y=["Ground Truth"] * len(mon),
        mode="markers",
        marker={"symbol": "square", "size": 8, "color": gt_colors},
        name="Ground Truth",
        showlegend=False,
    ))

    fig_tl.update_layout(
        title="Timeline segnali",
        xaxis_title="data/ora (UTC)",
        yaxis={
            "categoryorder": "array",
            "categoryarray": ["CUSUM", "Isol. Forest", "Z-score",
                               "Threshold", "Ground Truth"],
        },
        height=200,
        **_DARK_LAYOUT,
    )

    # Dual-axis PAS + Frobenius
    ts_list   = [r.get("timestamp")          for r in mon]
    pas_vals  = [r.get("pas_value")          for r in mon]
    frob_vals = [r.get("frobenius_distance") for r in mon]
    ts_dt     = [pd.to_datetime(ts, unit="us") if ts is not None else None for ts in ts_list]

    fig_pf = go.Figure()
    if any(v is not None for v in pas_vals):
        fig_pf.add_trace(go.Scatter(
            x=ts_dt, y=pas_vals, name="PAS",
            line={"color": "#c4a35a", "width": 1.5}, yaxis="y1",
        ))
    if any(v is not None for v in frob_vals):
        fig_pf.add_trace(go.Scatter(
            x=ts_dt, y=frob_vals, name="Frobenius",
            line={"color": "#b55e5e", "width": 1.5}, yaxis="y2",
        ))
    fig_pf.update_layout(
        title="PAS e Frobenius nel tempo",
        xaxis_title="data/ora (UTC)",
        yaxis ={"title": "PAS",       "color": "#c4a35a", "side": "left"},
        yaxis2={"title": "Frobenius", "color": "#b55e5e",
                "overlaying": "y", "side": "right"},
        legend={"bgcolor": "rgba(0,0,0,0)"},
        **_DARK_LAYOUT,
    )
    fig_pf.add_annotation(
        text=("PAS=1.0: tutto il traffico sul percorso critico | "
              "PAS=0.0: percorso critico non usato | "
              "Frobenius=0: nessuna deviazione dal baseline"),
        xref="paper", yref="paper",
        x=0, y=-0.22, showarrow=False,
        font={"size": 9, "color": "#5a5a5a"},
        align="left",
    )
    fig_pf.update_layout(margin={"l": 8, "r": 8, "t": 32, "b": 50})
    return g_th, g_zs, g_if, g_cu, fig_tl, fig_pf, v_th, v_zs, v_if, v_cu


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

    thresh_list = m.get("threshold_violations", [])
    zscore_list = m.get("zscore_violations", [])

    def _feat_chips(feat_items):
        if not feat_items:
            return html.Span("nessuna", style={"color": "#7aaa8f",
                                               "fontFamily": "JetBrains Mono",
                                               "fontSize": "10px"})
        chips = []
        for feat in feat_items[:5]:
            if isinstance(feat, (list, tuple)):
                feat_name = str(feat[0])
            else:
                feat_name = str(feat)
            short = ":".join(feat_name.split(":")[-2:]) if ":" in feat_name else feat_name
            chips.append(html.Span(short, style={
                "backgroundColor": "rgba(181,94,94,0.15)",
                "color": "#b55e5e",
                "fontFamily": "JetBrains Mono", "fontSize": "9px",
                "padding": "1px 5px", "marginRight": "3px", "marginBottom": "2px",
                "display": "inline-block",
            }))
        if len(feat_items) > 5:
            chips.append(html.Span(f"+{len(feat_items)-5} altre",
                                   style={"color": "var(--muted)", "fontSize": "9px"}))
        return html.Div(chips, style={"display": "flex", "flexWrap": "wrap",
                                      "alignItems": "center"})

    rows = [
        ("base_signal",     _bool_span(m.get("base_signal"))),
        ("if_signal",       _bool_span(m.get("if_signal"))),
        ("cusum_signal",    _bool_span(m.get("cusum_signal"))),
        ("structural_conf", _bool_span(m.get("structural_confirmed"))),
        ("cusum_stat",      f"{m.get('cusum_stat', 0):.4f}"),
        ("frobenius",       f"{m.get('frobenius_distance') or 0:.4f}"),
        ("pas_value",       str(m.get("pas_value", "N/A"))),
        ("threshold_viol",  None),
        ("zscore_viol",     None),
    ]
    items = []
    for key, value in rows:
        label_text, tooltip_text = _FIELD_LABELS.get(key, (key, ""))
        if key == "threshold_viol":
            val_el = _feat_chips(thresh_list)
        elif key == "zscore_viol":
            val_el = _feat_chips(zscore_list)
        else:
            val_el = value if isinstance(value, html.Span) else html.Span(
                value, style={"color": "var(--text)", "fontFamily": "JetBrains Mono"})
        items.append(html.Div([
            html.Div([
                html.Span(label_text,
                          style={"color": "var(--muted)", "fontSize": "11px"}),
                html.Span(" (?)",
                          title=tooltip_text,
                          style={"color": "var(--border)", "fontSize": "9px",
                                 "cursor": "help", "marginLeft": "3px"}) if tooltip_text else None,
            ], style={"display": "flex", "alignItems": "center"}),
            val_el,
        ], style={"display": "flex", "justifyContent": "space-between",
                  "padding": "4px 0", "borderBottom": "1px solid var(--border)"}))

    header_block = html.Div([
        html.Div(
            f"Snapshot {idx} - " + (
                "ANOMALIA RILEVATA" if m.get("base_signal")
                else "Nessuna anomalia"
            ),
            style={"fontWeight": "600", "color": (
                "#b55e5e" if m.get("base_signal") else "#7aaa8f"
            ), "marginBottom": "6px", "fontSize": "12px"},
        ),
        html.Div(
            "Dettaglio tecnico del risultato di monitoraggio "
            "per lo snapshot selezionato:",
            style={"fontSize": "11px", "color": "var(--muted)",
                   "marginBottom": "10px", "lineHeight": "1.5"},
        ),
    ])
    return html.Div([header_block] + items)
