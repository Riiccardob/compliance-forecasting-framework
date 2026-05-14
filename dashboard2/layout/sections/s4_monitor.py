from dash import html, dcc
import dash_mantine_components as dmc  # noqa: F401

_TITLE_STYLE = {
    "fontSize": "18px",
    "fontWeight": "600",
    "color": "var(--text)",
    "marginBottom": "20px",
}

_LABEL_STYLE = {
    "fontSize": "11px",
    "color": "var(--muted)",
    "letterSpacing": "0.05em",
    "textTransform": "uppercase",
    "marginBottom": "6px",
}


def _gauge(label: str, component_id: str) -> html.Div:
    return html.Div([
        html.Div(
            id=component_id + "_bar",
            style={
                "width": "32px",
                "height": "100px",
                "backgroundColor": "var(--surface)",
                "border": "1px solid var(--border)",
                "position": "relative",
                "overflow": "hidden",
            },
            children=html.Div(
                id=component_id + "_fill",
                style={
                    "position": "absolute",
                    "bottom": "0",
                    "width": "100%",
                    "height": "0%",
                    "backgroundColor": "var(--success)",
                    "transition": "height 0.4s,background-color 0.4s",
                },
            ),
        ),
        html.Div(label, style={
            "fontSize": "10px",
            "color": "var(--muted)",
            "textAlign": "center",
            "maxWidth": "60px",
        }),
    ], style={
        "display": "flex",
        "flexDirection": "column",
        "alignItems": "center",
        "gap": "6px",
    })


def create_s4() -> html.Div:
    return html.Div([
        html.Div("Monitoraggio Strutturale", style=_TITLE_STYLE),

        html.Div([
            html.Div([
                html.Div("Compliance set", style=_LABEL_STYLE),
                dcc.RadioItems(
                    id="s4-cs-select",
                    options=[
                        {"label": "H_crit",  "value": "H_crit"},
                        {"label": "H_cache", "value": "H_cache"},
                    ],
                    value="H_crit",
                    inline=True,
                    inputStyle={"marginRight": "6px"},
                    labelStyle={
                        "marginRight": "20px",
                        "color": "var(--text)",
                        "fontSize": "13px",
                    },
                ),
            ], style={"marginRight": "32px"}),

            html.Div([
                html.Div("Snapshot", style=_LABEL_STYLE),
                dcc.Dropdown(
                    id="s4-snap-dd",
                    options=[],
                    value=None,
                    placeholder="Seleziona snapshot...",
                    style={
                        "width": "200px",
                        "backgroundColor": "var(--surface)",
                        "color": "var(--text)",
                    },
                ),
            ]),
        ], style={
            "display": "flex",
            "alignItems": "flex-end",
            "marginBottom": "20px",
            "gap": "8px",
        }),

        html.Div([
            _gauge("Threshold",   "s4-gauge-threshold"),
            _gauge("Z-score",     "s4-gauge-zscore"),
            _gauge("Isolation F", "s4-gauge-if"),
            _gauge("CUSUM",       "s4-gauge-cusum"),
        ], style={
            "display": "flex",
            "gap": "16px",
            "marginBottom": "20px",
            "justifyContent": "flex-start",
        }),

        html.Div([
            html.Div(
                "Timeline segnali",
                style={
                    "fontSize": "11px",
                    "color": "var(--muted)",
                    "letterSpacing": "0.05em",
                    "textTransform": "uppercase",
                    "marginBottom": "8px",
                },
            ),
            dcc.Graph(
                id="s4-timeline",
                config={"displayModeBar": False},
                style={"height": "160px"},
            ),
        ], style={"marginBottom": "20px"}),

        html.Div([
            html.Div(
                dcc.Graph(
                    id="s4-frob-pas-chart",
                    config={"displayModeBar": False},
                ),
                style={"flex": "1"},
            ),
            html.Div(
                id="s4-result-card",
                style={
                    "width": "280px",
                    "minWidth": "280px",
                    "marginLeft": "16px",
                    "backgroundColor": "var(--surface)",
                    "border": "1px solid var(--border)",
                    "padding": "16px",
                    "fontSize": "12px",
                    "overflowY": "auto",
                    "maxHeight": "320px",
                },
                children=html.Div(
                    "Seleziona uno snapshot.",
                    style={"color": "var(--muted)"},
                ),
            ),
        ], style={"display": "flex"}),
    ])
