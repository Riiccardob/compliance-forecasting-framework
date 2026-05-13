import base64
import threading
from pathlib import Path

from dash import callback, Output, Input, State, html, ctx

from dashboard.core.data_manager import DataManager

#  Stato globale condiviso tra Flask thread e worker thread 

_S = {
    "atg_running": False,
    "atg_done":    False,
    "atg_error":   "",
    "atg_pct":     0,
    "atg_msg":     "",
}


#  Worker ATG 

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


#  Callback: aggiorna path quando si carica un file alternativo 

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


#  Callback: click Carica dati 

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


#  Callback: polling ogni secondo 

@callback(
    Output("s0-build-progress", "value"),
    Output("s0-build-label",    "children"),
    Output("s0-load-status",    "children"),
    Output("s0-load-status",    "style"),
    Output("s0-btn-load",       "disabled"),
    Output("s0-btn-load",       "style"),
    Output("s0-snapshot-table", "children"),
    Input("s0-poll", "n_intervals"),
)
def poll(n):
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
    else:
        snap_table = html.Div("")

    return (
        atg_pct, atg_msg,
        load_status, load_style,
        btn_load_disabled, btn_load_style,
        snap_table,
    )


#  Callback: toggle batch controls / full warning 

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
