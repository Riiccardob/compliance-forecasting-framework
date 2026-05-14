from pathlib import Path
from dash import html, dcc
import dash_mantine_components as dmc

_ROOT = Path(__file__).parent.parent.parent

_DEFAULT_NODE = str((_ROOT.parent / "data" / "converted" / "node_metrics.csv").resolve())
_DEFAULT_EDGE = str((_ROOT.parent / "data" / "converted" / "edge_metrics.csv").resolve())
_DEFAULT_GT   = str((_ROOT.parent / "data" / "converted" / "ground_truth.csv").resolve())

_BTN = {
    "border": "none",
    "padding": "10px 20px",
    "cursor": "pointer",
    "fontSize": "13px",
    "fontWeight": "600",
    "borderRadius": "2px",
    "width": "100%",
    "transition": "opacity 0.15s",
}

_CARD = {
    "backgroundColor": "var(--surface)",
    "border": "1px solid var(--border)",
    "padding": "20px",
    "flex": "1",
}

_LBL = {
    "fontSize": "11px",
    "color": "var(--muted)",
    "textTransform": "uppercase",
    "letterSpacing": "0.05em",
    "marginBottom": "5px",
}

_PATH_STYLE = {
    "fontFamily": "JetBrains Mono, monospace",
    "fontSize": "11px",
    "color": "var(--text)",
    "backgroundColor": "var(--bg)",
    "border": "1px solid var(--border)",
    "padding": "6px 10px",
    "marginBottom": "10px",
    "wordBreak": "break-all",
}


def _file_row(label, path_id, default_path, upload_id):
    return html.Div([
        html.Div(label, style=_LBL),
        html.Div(default_path, id=path_id, style=_PATH_STYLE),
        dcc.Upload(
            id=upload_id,
            children=html.Div(
                "Sostituisci con altro file",
                style={"fontSize": "11px", "color": "var(--muted)",
                       "cursor": "pointer",
                       "textDecoration": "underline"},
            ),
            multiple=False,
        ),
    ], style={"marginBottom": "14px"})


def create_s0():
    left = html.Div(style=_CARD, children=[
        html.Div("File CSV", style={
            "fontSize": "13px", "fontWeight": "600",
            "color": "var(--text)", "marginBottom": "16px",
            "paddingBottom": "8px",
            "borderBottom": "1px solid var(--border)",
        }),
        _file_row("Node Metrics", "s0-path-node",
                  _DEFAULT_NODE, "s0-upload-node"),
        _file_row("Edge Metrics", "s0-path-edge",
                  _DEFAULT_EDGE, "s0-upload-edge"),
        _file_row("Ground Truth", "s0-path-gt",
                  _DEFAULT_GT,   "s0-upload-gt"),
        html.Button(
            "Carica e costruisci ATG",
            id="s0-btn-load",
            n_clicks=0,
            style={**_BTN,
                   "backgroundColor": "var(--accent)",
                   "color": "#0e0e0e",
                   "marginTop": "8px"},
        ),
        html.Div(id="s0-build-progress-wrap", style={"marginTop": "12px"},
                 children=[
            dmc.Progress(id="s0-build-progress", value=0,
                         style={"marginBottom": "4px"}),
            html.Div(id="s0-build-label",
                     style={"fontSize": "11px",
                            "color": "var(--muted)",
                            "fontFamily": "JetBrains Mono, monospace"}),
        ]),
        html.Div(id="s0-load-status", style={"marginTop": "10px",
                                              "fontSize": "12px"}),
    ])

    right = html.Div(style=_CARD, children=[
        html.Div("Pipeline", style={
            "fontSize": "13px", "fontWeight": "600",
            "color": "var(--text)", "marginBottom": "16px",
            "paddingBottom": "8px",
            "borderBottom": "1px solid var(--border)",
        }),
        html.Div("Modalita", style=_LBL),
        dcc.RadioItems(
            id="s0-mode",
            options=[
                {"label": " Campione (1 snapshot anomalo)",
                 "value": "sample"},
                {"label": " Full dataset",
                 "value": "full"},
            ],
            value="sample",
            labelStyle={"display": "block", "marginBottom": "6px",
                        "color": "var(--text)", "fontSize": "13px",
                        "cursor": "pointer"},
        ),
        html.Div(
            "Full dataset: puo richiedere ore.",
            id="s0-full-warning",
            style={"fontSize": "11px", "color": "var(--danger)",
                   "marginTop": "4px", "display": "none"},
        ),
        html.Button(
            "Esegui pipeline",
            id="s0-btn-run",
            n_clicks=0,
            disabled=True,
            style={**_BTN,
                   "backgroundColor": "var(--crit)",
                   "color": "#ffffff",
                   "marginTop": "16px",
                   "opacity": "0.4"},
        ),
        html.Div(id="s0-pipe-progress-wrap", style={"marginTop": "12px"},
                 children=[
            dmc.Progress(id="s0-progress", value=0,
                         style={"marginBottom": "4px"}),
            html.Div(id="s0-progress-label",
                     style={"fontSize": "11px",
                            "color": "var(--muted)",
                            "fontFamily": "JetBrains Mono, monospace"}),
        ]),
        html.Pre(
            id="s0-run-log",
            style={
                "backgroundColor": "var(--bg)",
                "border": "1px solid var(--border)",
                "padding": "8px", "fontSize": "11px",
                "color": "var(--muted)", "marginTop": "10px",
                "maxHeight": "140px", "overflowY": "auto",
                "fontFamily": "JetBrains Mono, monospace",
                "whiteSpace": "pre-wrap",
            },
        ),
        html.Div(id="s0-snapshot-table", style={"marginTop": "12px"}),
    ])

    return html.Div([
        html.Div("Importazione dati", style={
            "fontSize": "18px", "fontWeight": "600",
            "color": "var(--text)", "marginBottom": "20px",
        }),
        html.Div(style={"display": "flex", "gap": "16px"},
                 children=[left, right]),
        dcc.Store(id="s0-upload-paths", data={
            "node": _DEFAULT_NODE,
            "edge": _DEFAULT_EDGE,
            "gt":   _DEFAULT_GT,
        }),
        dcc.Interval(id="s0-poll", interval=1000, n_intervals=0),
    ])
