import base64, io  # noqa: F401
from pathlib import Path
import pandas as pd  # noqa: F401
import dash
from dash import callback, Output, Input, State, html, dcc
import dash_mantine_components as dmc
from dashboard.app import app, background_callback_manager

_FB_OK  = {"fontSize": "11px", "color": "var(--success)", "marginTop": "4px"}
_FB_ERR = {"fontSize": "11px", "color": "var(--danger)",  "marginTop": "4px"}
_FB_DEF = {"fontSize": "11px", "color": "var(--muted)",   "marginTop": "4px"}
_UPLOAD_DIR = Path(__file__).parent.parent / "cache" / "uploads"


def _handle_upload(contents, filename, dest_name):
    if contents is None:
        return "Nessun file selezionato", _FB_DEF
    if filename and not filename.endswith(".csv"):
        return f"Errore: {filename} non è un CSV", _FB_ERR
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    _, content_string = contents.split(",", 1)
    decoded = base64.b64decode(content_string)
    (_UPLOAD_DIR / dest_name).write_bytes(decoded)
    n_rows = len(decoded.decode("utf-8", errors="replace").splitlines()) - 1
    return f"{filename} ({n_rows} righe)", _FB_OK


@callback(
    Output("s0-feedback-node", "children"), Output("s0-feedback-node", "style"),
    Input("s0-upload-node", "contents"), State("s0-upload-node", "filename"),
    prevent_initial_call=True,
)
def handle_upload_node(contents, filename):
    return _handle_upload(contents, filename, "node_metrics.csv")


@callback(
    Output("s0-feedback-edge", "children"), Output("s0-feedback-edge", "style"),
    Input("s0-upload-edge", "contents"), State("s0-upload-edge", "filename"),
    prevent_initial_call=True,
)
def handle_upload_edge(contents, filename):
    return _handle_upload(contents, filename, "edge_metrics.csv")


@callback(
    Output("s0-feedback-gt", "children"), Output("s0-feedback-gt", "style"),
    Input("s0-upload-gt", "contents"), State("s0-upload-gt", "filename"),
    prevent_initial_call=True,
)
def handle_upload_gt(contents, filename):
    return _handle_upload(contents, filename, "ground_truth.csv")


@callback(
    Output("s0-btn-load", "disabled"),
    Input("s0-feedback-node", "children"),
    Input("s0-feedback-edge", "children"),
    Input("s0-feedback-gt", "children"),
)
def enable_load_btn(fn, fe, fg):
    ok = lambda txt: txt and "Nessun" not in txt and "Errore" not in txt
    return not (ok(fn) and ok(fe) and ok(fg))


@app.callback(
    output=[
        Output("s0-load-status", "children"),
        Output("s0-btn-run", "disabled"),
        Output("s0-snapshot-table", "children"),
    ],
    inputs=Input("s0-btn-load", "n_clicks"),
    background=True,
    manager=background_callback_manager,
    running=[
        (Output("s0-btn-load", "disabled"), True, False),
        (Output("s0-build-progress", "style"),
         {"display": "block"}, {"display": "none"}),
    ],
    progress=[
        Output("s0-build-progress", "value"),
        Output("s0-build-label", "children"),
    ],
    prevent_initial_call=True,
)
def build_atg(set_progress, n_clicks):
    import sys
    from pathlib import Path as _Path
    sys.path.insert(0, str(_Path(__file__).parent.parent.parent))
    from dashboard.core.data_manager import DataManager

    set_progress(10, "Caricamento CSV...")
    dm = DataManager()
    cache_dir = _Path(__file__).parent.parent / "cache" / "uploads"
    dm.load_csvs(
        cache_dir / "node_metrics.csv",
        cache_dir / "edge_metrics.csv",
        cache_dir / "ground_truth.csv",
    )
    set_progress(40, "Costruzione ATG...")
    try:
        dm.build_snapshots()
    except Exception as e:
        return f"Errore: {e}", True, html.Div(
            str(e), style={"color": "var(--danger)", "fontSize": "12px"}
        )
    set_progress(100, "Completato")
    snaps     = dm.get_snapshots()
    nominal   = dm.get_nominal_snapshots()
    anomalous = dm.get_anomalous_snapshots()
    from collections import Counter
    types = Counter(s.get("anomaly_type") or "unknown" for s in anomalous)
    table = _build_snapshot_table(len(snaps), len(nominal), len(anomalous), types)
    return f"ATG costruito: {len(snaps)} snapshot", False, table


def _build_snapshot_table(total, nominal, anomalous, types) -> html.Div:
    summary = [
        html.Div(["Totale ",   html.Span(str(total),     className="metric-value")]),
        html.Div(["Nominali ", html.Span(str(nominal),   className="metric-value")]),
        html.Div(["Anomali ",  html.Span(str(anomalous), className="metric-value")]),
    ]
    pills = [
        html.Span(f"{t}: {c}", style={
            "backgroundColor": "rgba(181,94,94,0.2)",
            "color": "var(--danger)", "padding": "2px 8px",
            "borderRadius": "2px", "marginRight": "6px", "fontSize": "11px",
        })
        for t, c in types.most_common()
    ]
    return html.Div([
        html.Div(summary, style={"display": "flex", "gap": "24px",
                                 "marginBottom": "12px", "flexWrap": "wrap"}),
        html.Div(pills),
    ])


@callback(
    Output("s0-n-snapshots", "style"),
    Output("s0-full-warning", "style"),
    Input("s0-mode", "value"),
)
def toggle_mode_ui(mode):
    slider_on = {"display": "block", "marginTop": "8px"}
    hidden    = {"display": "none"}
    warning   = {"display": "block", "color": "var(--danger)",
                 "fontSize": "12px", "marginTop": "8px"}
    if mode == "sample":
        return slider_on, hidden
    if mode == "full":
        return hidden, warning
    return hidden, hidden
