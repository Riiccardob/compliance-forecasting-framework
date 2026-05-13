from dash import html, dcc
import dash_mantine_components as dmc

_UPLOAD_STYLE = {
    "border": "1px dashed var(--border)",
    "borderRadius": "4px",
    "padding": "10px",
    "textAlign": "center",
    "cursor": "pointer",
    "color": "var(--muted)",
    "fontSize": "12px",
    "backgroundColor": "var(--bg)",
}
_FB = {"fontSize": "11px", "color": "var(--muted)", "marginTop": "4px"}
_LBL = {"fontSize": "11px", "color": "var(--muted)", "marginBottom": "4px",
        "textTransform": "uppercase", "letterSpacing": "0.05em"}
_BTN_BASE = {"border": "none", "borderRadius": "4px", "padding": "8px 16px",
             "cursor": "pointer", "fontSize": "13px", "fontWeight": 600, "width": "100%"}


def _upload_block(label: str, uid: str, fid: str) -> html.Div:
    return html.Div(
        style={"marginBottom": "14px"},
        children=[
            html.Div(label, style=_LBL),
            dcc.Upload(id=uid, children=html.Div("Trascina o clicca"),
                       style=_UPLOAD_STYLE, multiple=False),
            html.Div("Nessun file selezionato", id=fid, style=_FB),
        ],
    )


def _card(title: str, children: list) -> html.Div:
    return html.Div(
        style={
            "backgroundColor": "var(--surface)",
            "border": "1px solid var(--border)",
            "borderRadius": "4px",
            "padding": "20px",
            "flex": "1",
        },
        children=[
            html.Div(title, style={
                "fontSize": "13px", "fontWeight": 600, "color": "var(--text)",
                "marginBottom": "16px", "paddingBottom": "8px",
                "borderBottom": "1px solid var(--border)",
            }),
            *children,
        ],
    )


def create_s0() -> html.Div:
    left = _card("File CSV canonici", [
        _upload_block("Node Metrics", "s0-upload-node", "s0-feedback-node"),
        _upload_block("Edge Metrics", "s0-upload-edge", "s0-feedback-edge"),
        _upload_block("Ground Truth", "s0-upload-gt",   "s0-feedback-gt"),
        html.Button("Carica dati", id="s0-btn-load", disabled=True,
                    style={**_BTN_BASE, "backgroundColor": "var(--accent)",
                           "color": "var(--bg)", "marginTop": "4px"}),
    ])

    right = _card("Pipeline", [
        html.Div(id="s0-load-status",
                 style={"fontSize": "12px", "color": "var(--muted)", "marginBottom": "8px"}),
        dmc.Progress(id="s0-build-progress", value=0,
                     style={"display": "none", "marginBottom": "4px"}),
        html.Div("Nessun file selezionato", id="s0-build-label",
                 style={**_FB, "marginBottom": "12px"}),
        html.Div("Modalità", style=_LBL),
        dcc.RadioItems(
            id="s0-mode",
            options=[{"label": " Campione", "value": "sample"},
                     {"label": " Full dataset", "value": "full"}],
            value="sample",
            labelStyle={"display": "block", "marginBottom": "4px",
                        "fontSize": "13px", "color": "var(--text)"},
        ),
        html.Div("Attenzione: full dataset richiede diversi minuti.",
                 id="s0-full-warning",
                 style={"fontSize": "11px", "color": "var(--danger)",
                        "marginTop": "4px", "display": "none"}),
        html.Div("Finestre da processare", style={**_LBL, "marginTop": "12px"}),
        dcc.Slider(id="s0-n-snapshots", min=100, max=1000, step=100, value=500,
                   marks={i: str(i) for i in [100, 400, 700, 1000]}),
        html.Button("Esegui pipeline", id="s0-btn-run",
                    style={**_BTN_BASE, "backgroundColor": "var(--crit)",
                           "color": "#fff", "marginTop": "16px"}),
        dmc.Progress(id="s0-progress", value=0, style={"marginTop": "12px"}),
        html.Div(id="s0-progress-label", style={**_FB, "marginTop": "4px"}),
        html.Pre(id="s0-run-log", style={
            "backgroundColor": "var(--bg)", "border": "1px solid var(--border)",
            "borderRadius": "4px", "padding": "8px", "fontSize": "11px",
            "color": "var(--muted)", "marginTop": "10px", "maxHeight": "160px",
            "overflowY": "auto", "fontFamily": '"JetBrains Mono", monospace',
        }),
        html.Div(id="s0-snapshot-table", style={"marginTop": "12px"}),
    ])

    return html.Div(
        children=[html.Div(style={"display": "flex", "gap": "16px"},
                           children=[left, right])]
    )
