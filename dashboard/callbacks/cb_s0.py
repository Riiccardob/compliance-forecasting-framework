import base64
import threading
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from dash import callback, Output, Input, State, html, dcc, ctx

from dashboard.core.data_manager import DataManager

# ── Stato globale condiviso tra Flask thread e worker thread ──────────────

_S = {
    "atg_running": False,
    "atg_done":    False,
    "atg_error":   "",
    "atg_pct":     0,
    "atg_msg":     "",
}


# ── Worker ATG ────────────────────────────────────────────────────────────

def _worker_atg(node_path: str, edge_path: str, gt_path: str) -> None:
    _S["atg_running"] = True
    _S["atg_error"]   = ""
    _S["atg_pct"]     = 5
    _S["atg_msg"]     = "Verifica file..."
    try:
        for label, path in [("node_metrics", node_path),
                             ("edge_metrics", edge_path),
                             ("ground_truth", gt_path)]:
            if not Path(path).exists():
                raise FileNotFoundError(
                    f"File non trovato: {path}"
                )
        _S["atg_pct"] = 20
        _S["atg_msg"] = "Caricamento CSV in DataManager..."
        dm = DataManager()
        dm.load_csvs(Path(node_path), Path(edge_path), Path(gt_path))
        _S["atg_pct"] = 40
        _S["atg_msg"] = "Costruzione snapshot ATG (puo richiedere 1-2 min)..."
        dm.build_snapshots()
        _S["atg_pct"] = 100
        _S["atg_msg"] = (
            f"Completato: {len(dm.get_snapshots())} snapshot, "
            f"{len(dm.get_nominal_snapshots())} nominali, "
            f"{len(dm.get_anomalous_snapshots())} anomali"
        )
        _S["atg_done"] = True
    except Exception as exc:
        _S["atg_error"] = str(exc)
        _S["atg_pct"]   = 0
        _S["atg_msg"]   = f"Errore: {exc}"
    finally:
        _S["atg_running"] = False


# ── Callback: aggiorna path quando si carica un file alternativo ──────────

def _save_upload(contents, filename, rel_name):
    if not contents or not filename:
        return None
    cache = Path(__file__).parent.parent / "cache" / "uploads"
    cache.mkdir(parents=True, exist_ok=True)
    _, data = contents.split(",", 1)
    out = cache / rel_name
    out.write_bytes(base64.b64decode(data))
    return str(out)


@callback(
    Output("s0-upload-paths", "data"),
    Output("s0-path-node", "children"),
    Output("s0-path-edge", "children"),
    Output("s0-path-gt",   "children"),
    Input("s0-upload-node", "contents"),
    Input("s0-upload-edge", "contents"),
    Input("s0-upload-gt",   "contents"),
    State("s0-upload-node", "filename"),
    State("s0-upload-edge", "filename"),
    State("s0-upload-gt",   "filename"),
    State("s0-upload-paths", "data"),
    prevent_initial_call=True,
)
def handle_uploads(cn, ce, cg, fn, fe, fg, paths):
    p = dict(paths)
    triggered = ctx.triggered_id
    if triggered == "s0-upload-node" and cn:
        saved = _save_upload(cn, fn, "node_metrics.csv")
        if saved:
            p["node"] = saved
    elif triggered == "s0-upload-edge" and ce:
        saved = _save_upload(ce, fe, "edge_metrics.csv")
        if saved:
            p["edge"] = saved
    elif triggered == "s0-upload-gt" and cg:
        saved = _save_upload(cg, fg, "ground_truth.csv")
        if saved:
            p["gt"] = saved
    return p, p["node"], p["edge"], p["gt"]


# ── Callback: click Carica dati ───────────────────────────────────────────

@callback(
    Output("s0-btn-load", "children"),
    Input("s0-btn-load",  "n_clicks"),
    State("s0-upload-paths", "data"),
    prevent_initial_call=True,
)
def start_atg_build(n_clicks, paths):
    if not n_clicks:
        return "Carica e costruisci ATG"
    if _S["atg_running"]:
        return "Costruzione in corso..."
    _S["atg_done"] = False
    t = threading.Thread(
        target=_worker_atg,
        args=(paths["node"], paths["edge"], paths["gt"]),
        daemon=True,
    )
    t.start()
    return "Costruzione avviata..."


# ── Callback: polling ogni secondo ────────────────────────────────────────

@callback(
    Output("s0-build-progress", "value"),
    Output("s0-build-label",    "children"),
    Output("s0-load-status",    "children"),
    Output("s0-load-status",    "style"),
    Output("s0-btn-load",       "disabled"),
    Output("s0-btn-load",       "style"),
    Output("s0-snapshot-table", "children"),
    Output("s0-btn-run",          "disabled"),
    Output("s0-btn-run",          "style"),
    Output("s0-dataset-preview",  "children"),
    Output("s0-dataset-preview",  "style"),
    Input("s0-poll", "n_intervals"),
    State("s0-pipeline-config", "data"),
    State("s0-mode",            "value"),
    State("s0-n-snapshots",     "value"),
)
def poll(n, pipeline_config, current_mode, current_n):
    _BTN_BASE = {
        "border": "none", "padding": "10px 20px",
        "cursor": "pointer", "fontSize": "13px",
        "fontWeight": "600", "borderRadius": "2px", "width": "100%",
        "transition": "opacity 0.15s",
    }
    btn_load_active  = {**_BTN_BASE, "backgroundColor": "var(--accent)",
                        "color": "#0e0e0e", "marginTop": "8px", "opacity": "1"}
    btn_load_running = {**_BTN_BASE, "backgroundColor": "var(--border)",
                        "color": "var(--muted)", "marginTop": "8px",
                        "opacity": "0.6", "cursor": "not-allowed"}

    atg_pct   = _S["atg_pct"]
    atg_msg   = _S["atg_msg"]
    atg_error = _S["atg_error"]

    if atg_error:
        load_status = html.Div(
            atg_error,
            style={"color": "var(--danger)",
                   "fontFamily": "JetBrains Mono, monospace",
                   "fontSize": "11px"},
        )
        load_style        = {}
        btn_load_disabled = False
        btn_load_style    = btn_load_active
    elif _S["atg_done"]:
        dm = DataManager()
        ns = len(dm.get_snapshots())
        nn = len(dm.get_nominal_snapshots())
        na = len(dm.get_anomalous_snapshots())
        load_status = html.Div([
            html.Div("ATG caricato",
                     style={"color": "var(--success)",
                            "fontWeight": "600", "marginBottom": "4px"}),
            html.Div(
                f"{ns} snapshot   {nn} nominali   {na} anomali",
                style={"fontFamily": "JetBrains Mono, monospace",
                       "fontSize": "11px", "color": "var(--text)"},
            ),
        ])
        load_style        = {}
        btn_load_disabled = False
        btn_load_style    = btn_load_active
    elif _S["atg_running"]:
        load_status       = html.Div("")
        load_style        = {}
        btn_load_disabled = True
        btn_load_style    = btn_load_running
    else:
        load_status       = html.Div("")
        load_style        = {}
        btn_load_disabled = False
        btn_load_style    = btn_load_active

    if _S["atg_done"]:
        from collections import Counter
        dm    = DataManager()
        snaps = dm.get_snapshots()
        anom  = dm.get_anomalous_snapshots()
        types = Counter(s.get("anomaly_type") or "unknown" for s in anom)
        pills = [
            html.Span(f"{t}: {c}", style={
                "backgroundColor": "rgba(181,94,94,0.2)",
                "color": "var(--danger)", "padding": "2px 8px",
                "borderRadius": "2px", "marginRight": "6px",
                "fontSize": "11px",
            })
            for t, c in types.most_common()
        ]
        snap_table = html.Div(pills) if pills else html.Div("")

        # ── Dataset preview ──────────────────────────────────────────────────
        nominal_ts   = [pd.to_datetime(s["timestamp"], unit="us")
                        for s in snaps if s["label"] == 0]
        anomalous_ts = [pd.to_datetime(s["timestamp"], unit="us")
                        for s in snaps if s["label"] == 1]
        anomalous_ft = [s.get("anomaly_type") or "" for s in snaps if s["label"] == 1]

        fig_tl = go.Figure()
        if nominal_ts:
            fig_tl.add_trace(go.Scatter(
                x=nominal_ts, y=[0] * len(nominal_ts),
                mode="markers", name="Nominale",
                marker={"color": "#7aaa8f", "size": 3, "opacity": 0.5},
                hovertemplate="Nominale<br>%{x}<extra></extra>",
            ))
        if anomalous_ts:
            fig_tl.add_trace(go.Scatter(
                x=anomalous_ts, y=[1] * len(anomalous_ts),
                mode="markers", name="Anomalo",
                marker={"color": "#b55e5e", "size": 5,
                        "symbol": "diamond", "opacity": 0.7},
                customdata=[[ft] for ft in anomalous_ft],
                hovertemplate="Anomalo<br>%{x}<br>tipo: %{customdata[0]}<extra></extra>",
            ))
        fig_tl.update_layout(
            title="Distribuzione temporale degli snapshot",
            yaxis={"tickvals": [0, 1], "ticktext": ["Nominale", "Anomalo"],
                   "gridcolor": "#2a2a2a"},
            xaxis={"title": "data/ora (UTC)", "gridcolor": "#2a2a2a"},
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font={"color": "#e2ddd5", "size": 11},
            height=200, margin={"l": 60, "r": 10, "t": 36, "b": 40},
            legend={"bgcolor": "rgba(0,0,0,0)"},
        )

        _PIE_COLORS = ["#b55e5e", "#e07b39", "#c4a35a",
                       "#388bfd", "#3fb950", "#888888"]
        fig_pie = go.Figure(go.Pie(
            labels=list(types.keys()), values=list(types.values()), hole=0.45,
            marker={"colors": _PIE_COLORS[:len(types)],
                    "line": {"color": "#2a2a2a", "width": 1}},
            textfont={"color": "#e2ddd5"},
            hovertemplate="%{label}<br>%{value} snapshot (%{percent})<extra></extra>",
        ))
        fig_pie.update_layout(
            title="Tipi di anomalia",
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font={"color": "#e2ddd5", "size": 11},
            height=220, margin={"l": 10, "r": 10, "t": 36, "b": 10},
            legend={"bgcolor": "rgba(0,0,0,0)"},
        )

        n_tot  = len(snaps)
        n_anom = len(anom)
        table_rows = []
        for ft, count in types.most_common():
            pct_tot  = count / n_tot  * 100 if n_tot  else 0
            pct_anom = count / n_anom * 100 if n_anom else 0
            table_rows.append(html.Div([
                html.Span(ft, style={"flex": "1", "color": "var(--text)",
                                     "fontSize": "12px"}),
                html.Span(str(count), style={"width": "60px", "textAlign": "right",
                                             "fontFamily": "JetBrains Mono",
                                             "fontSize": "11px", "color": "#e2ddd5"}),
                html.Span(f"{pct_tot:.1f}%", style={"width": "70px", "textAlign": "right",
                                                     "fontFamily": "JetBrains Mono",
                                                     "fontSize": "11px",
                                                     "color": "var(--muted)"}),
                html.Span(f"{pct_anom:.1f}%", style={"width": "80px", "textAlign": "right",
                                                      "fontFamily": "JetBrains Mono",
                                                      "fontSize": "11px",
                                                      "color": "#b55e5e"}),
            ], style={"display": "flex", "padding": "4px 8px",
                      "borderBottom": "1px solid var(--border)"}))

        tbl_hdr = html.Div([
            html.Span("Tipo",      style={"flex": "1", "fontSize": "10px",
                                           "color": "var(--muted)"}),
            html.Span("N",         style={"width": "60px", "textAlign": "right",
                                           "fontSize": "10px", "color": "var(--muted)"}),
            html.Span("% tot",     style={"width": "70px", "textAlign": "right",
                                           "fontSize": "10px", "color": "var(--muted)"}),
            html.Span("% anomali", style={"width": "80px", "textAlign": "right",
                                           "fontSize": "10px", "color": "var(--muted)"}),
        ], style={"display": "flex", "padding": "4px 8px",
                  "backgroundColor": "var(--bg)",
                  "borderBottom": "1px solid var(--border)"})

        fault_table = html.Div(
            [tbl_hdr] + table_rows,
            style={"border": "1px solid var(--border)",
                   "backgroundColor": "var(--surface)"},
        )

        preview_children = html.Div([
            html.Div("Distribuzione del dataset", style={
                "fontSize": "12px", "fontWeight": "600", "color": "var(--text)",
                "marginBottom": "12px", "marginTop": "20px",
                "borderTop": "1px solid var(--border)", "paddingTop": "12px",
            }),
            dcc.Graph(figure=fig_tl, config={"displayModeBar": False}),
            html.Div([
                html.Div([
                    dcc.Graph(figure=fig_pie, config={"displayModeBar": False}),
                ], style={"flex": "1"}),
                html.Div([fault_table], style={"flex": "1", "marginLeft": "16px"}),
            ], style={"display": "flex", "marginTop": "12px"}),
        ])
        preview_style = {"display": "block"}
    else:
        snap_table       = html.Div("")
        preview_children = []
        preview_style    = {"display": "none"}

    atg_ready = _S["atg_done"] or DataManager().is_data_loaded()
    config_changed = (
        pipeline_config is None
        or pipeline_config.get("mode") != current_mode
        or (current_mode == "batch"
            and pipeline_config.get("n_snapshots") != int(current_n or 50))
    )
    btn_disabled = not atg_ready or not config_changed
    btn_opacity  = "1" if (atg_ready and config_changed) else "0.4"
    btn_cursor   = "pointer" if (atg_ready and config_changed) else "not-allowed"
    btn_run_style = {
        "border": "none",
        "padding": "10px 20px",
        "fontSize": "13px",
        "fontWeight": "600",
        "borderRadius": "2px",
        "width": "100%",
        "backgroundColor": "var(--crit)",
        "color": "#ffffff",
        "marginTop": "16px",
        "opacity": btn_opacity,
        "cursor": btn_cursor,
    }
    return (
        atg_pct, atg_msg,
        load_status, load_style,
        btn_load_disabled, btn_load_style,
        snap_table,
        btn_disabled,
        btn_run_style,
        preview_children,
        preview_style,
    )


# ── Callback: disabilita poll fuori da S0 ────────────────────────────────

@callback(
    Output("s0-poll", "disabled"),
    Input("active-section", "data"),
)
def toggle_poll(section):
    return section != "s0"


# ── Callback: toggle batch controls / full warning ───────────────────────

@callback(
    Output("s0-batch-controls", "style"),
    Output("s0-full-warning",   "style"),
    Input("s0-mode", "value"),
)
def toggle_mode_controls(mode):
    batch_style = {"display": "block"} if mode == "batch" else {"display": "none"}
    full_style  = (
        {"fontSize": "11px", "color": "var(--danger)",
         "marginTop": "4px", "display": "block"}
        if mode == "full" else {"display": "none"}
    )
    return batch_style, full_style
