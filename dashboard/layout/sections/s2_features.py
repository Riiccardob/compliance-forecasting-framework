from dash import html, dcc
import dash_mantine_components as dmc

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

_CARD = {
    "backgroundColor": "var(--surface)",
    "border": "1px solid var(--border)",
    "borderRadius": "4px",
    "padding": "16px",
}

_GRAPH_LAYOUT = {
    "paper_bgcolor": "rgba(0,0,0,0)",
    "plot_bgcolor": "rgba(0,0,0,0)",
    "font": {"color": "#e2ddd5", "size": 11},
    "margin": {"l": 50, "r": 10, "t": 32, "b": 40},
    "xaxis": {"gridcolor": "#2a2a2a"},
    "yaxis": {"gridcolor": "#2a2a2a"},
}


def create_s2() -> html.Div:
    return html.Div([
        html.Div("Feature Selection", style=_TITLE_STYLE),

        html.Div([
            html.Div("Compliance set", style=_LABEL_STYLE),
            dcc.RadioItems(
                id="s2-cs-select",
                options=[
                    {"label": "H_crit",  "value": "H_crit"},
                    {"label": "H_cache", "value": "H_cache"},
                ],
                value="H_crit",
                inline=True,
                inputStyle={"marginRight": "6px"},
                labelStyle={
                    "marginRight": "24px",
                    "color": "var(--text)",
                    "fontSize": "13px",
                    "cursor": "pointer",
                },
            ),
        ], style={"marginBottom": "16px"}),

        html.Div(id="s2-intro"),

        html.Div(id="s2-counts", style={
            "display": "flex",
            "gap": "12px",
            "marginBottom": "12px",
        }),

        html.Div(id="s2-feature-explanation"),

        html.Div([
            html.Div([
                html.Div([
                    html.Div("Feature", style=_LABEL_STYLE),
                    dcc.Dropdown(
                        id="s2-feature-dd",
                        options=[],
                        value=None,
                        placeholder="Seleziona una feature...",
                        clearable=False,
                        style={
                            "backgroundColor": "var(--surface)",
                            "color": "var(--text)",
                        },
                    ),
                ], style={"marginBottom": "10px"}),
                dcc.Graph(
                    id="s2-series-graph",
                    config={"displayModeBar": False},
                    figure={"data": [], "layout": _GRAPH_LAYOUT},
                ),
            ], style={"flex": "1"}),

            html.Div([
                html.Div("Previsione StatForecaster", style=_LABEL_STYLE),
                html.Div(
                    id="s2-model-tag",
                    style={
                        "marginBottom": "8px",
                        "fontSize": "11px",
                        "color": "var(--muted)",
                    },
                ),
                dcc.Graph(
                    id="s2-forecast-graph",
                    config={"displayModeBar": False},
                    figure={"data": [], "layout": _GRAPH_LAYOUT},
                ),
            ], style={"flex": "1", "marginLeft": "16px"}),
        ], style={"display": "flex"}),
    ])
