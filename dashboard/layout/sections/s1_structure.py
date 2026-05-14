from dash import html, dcc
import dash_mantine_components as dmc
import dash_cytoscape as cyto

_CARD = {
    "backgroundColor": "var(--surface)",
    "border": "1px solid var(--border)",
    "borderRadius": "4px",
    "padding": "16px",
    "marginBottom": "12px",
}

_LABEL = {
    "fontSize": "11px",
    "color": "var(--muted)",
    "marginBottom": "4px",
    "textTransform": "uppercase",
    "letterSpacing": "0.05em",
}


def _topology_panel() -> html.Div:
    cyto_stylesheet = [
        {
            "selector": "node",
            "style": {
                "label": "data(label)",
                "color": "var(--text)",
                "font-size": "10px",
                "background-color": "var(--surface)",
                "border-color": "var(--border)",
                "border-width": "1px",
                "width": "32px",
                "height": "32px",
                "text-valign": "bottom",
                "text-margin-y": "4px",
            },
        },
        {
            "selector": "node.crit",
            "style": {"border-color": "var(--crit)", "border-width": "2px"},
        },
        {
            "selector": "node.cache",
            "style": {"border-color": "var(--cache)", "border-width": "2px"},
        },
        {
            "selector": "node.shared",
            "style": {
                "border-color": "var(--shared)",
                "border-width": "2px",
            },
        },
        {
            "selector": "edge",
            "style": {
                "line-color": "var(--border)",
                "target-arrow-color": "var(--border)",
                "target-arrow-shape": "triangle",
                "curve-style": "bezier",
                "width": 1.5,
                "font-size": "9px",
                "color": "var(--muted)",
            },
        },
        {
            "selector": "edge:selected",
            "style": {"line-color": "var(--accent)", "width": 2.5},
        },
        {
            "selector": "node:selected",
            "style": {"border-color": "var(--accent)", "border-width": "3px"},
        },
    ]

    return html.Div(
        style={"display": "flex", "gap": "12px"},
        children=[
            html.Div(
                style={**_CARD, "flex": "1", "minHeight": "420px", "padding": "0"},
                children=cyto.Cytoscape(
                    id="s1-cytoscape",
                    layout={"name": "cose-bilkent"},
                    elements=[],
                    stylesheet=cyto_stylesheet,
                    style={"width": "100%", "height": "420px"},
                    responsive=True,
                ),
            ),
            html.Div(
                id="s1-topo-panel",
                style={**_CARD, "width": "220px", "minHeight": "420px",
                       "fontSize": "12px", "color": "var(--muted)"},
                children="Seleziona un nodo o arco per i dettagli.",
            ),
        ],
    )


def _atg_panel() -> html.Div:
    metric_options = [
        {"label": "CPU %", "value": "cpu_percent"},
        {"label": "Memoria (MB)", "value": "mem_mb"},
        {"label": "Net RX (MB)", "value": "net_rx_mb"},
        {"label": "Net TX (MB)", "value": "net_tx_mb"},
        {"label": "Latenza (ms)", "value": "latency_ms"},
        {"label": "Error Rate", "value": "error_rate"},
        {"label": "Throughput (rps)", "value": "throughput_rps"},
    ]

    return html.Div(
        children=[
            html.Div(
                style=_CARD,
                children=[
                    html.Div("Snapshot", style=_LABEL),
                    dcc.Slider(
                        id="s1-atg-slider",
                        min=0,
                        max=0,
                        step=1,
                        value=0,
                        marks=None,
                        tooltip={"placement": "bottom", "always_visible": False},
                        updatemode="drag",
                    ),
                    html.Div(
                        id="s1-atg-snap-label",
                        style={"fontSize": "11px", "color": "var(--muted)",
                               "marginTop": "6px"},
                        children="Nessun dato caricato.",
                    ),
                ],
            ),
            html.Div(
                style={"display": "flex", "gap": "12px", "marginBottom": "12px"},
                children=[
                    html.Div(
                        style={**_CARD, "flex": "1", "marginBottom": "0"},
                        children=[
                            html.Div("Feature nodo (heatmap)", style=_LABEL),
                            dcc.Graph(
                                id="s1-atg-node-heatmap",
                                config={"displayModeBar": False},
                                style={"height": "220px"},
                                figure={"data": [], "layout": {
                                    "paper_bgcolor": "var(--surface)",
                                    "plot_bgcolor": "var(--surface)",
                                    "margin": {"l": 60, "r": 10, "t": 10, "b": 40},
                                    "font": {"color": "var(--text)", "size": 10},
                                }},
                            ),
                        ],
                    ),
                    html.Div(
                        style={**_CARD, "flex": "1", "marginBottom": "0"},
                        children=[
                            html.Div("Feature arco (heatmap)", style=_LABEL),
                            dcc.Graph(
                                id="s1-atg-edge-heatmap",
                                config={"displayModeBar": False},
                                style={"height": "220px"},
                                figure={"data": [], "layout": {
                                    "paper_bgcolor": "var(--surface)",
                                    "plot_bgcolor": "var(--surface)",
                                    "margin": {"l": 60, "r": 10, "t": 10, "b": 40},
                                    "font": {"color": "var(--text)", "size": 10},
                                }},
                            ),
                        ],
                    ),
                ],
            ),
            html.Div(
                style=_CARD,
                children=[
                    html.Div(
                        style={"display": "flex", "alignItems": "center",
                               "gap": "12px", "marginBottom": "8px"},
                        children=[
                            html.Div("Serie temporale", style={**_LABEL, "marginBottom": "0"}),
                            dcc.Dropdown(
                                id="s1-atg-metric-dd",
                                options=metric_options,
                                value="cpu_percent",
                                clearable=False,
                                style={
                                    "flex": "1",
                                    "backgroundColor": "var(--bg)",
                                    "border": "1px solid var(--border)",
                                    "borderRadius": "2px",
                                    "color": "var(--text)",
                                    "fontSize": "12px",
                                },
                            ),
                        ],
                    ),
                    dcc.Graph(
                        id="s1-atg-ts-graph",
                        config={"displayModeBar": False},
                        style={"height": "200px"},
                        figure={"data": [], "layout": {
                            "paper_bgcolor": "var(--surface)",
                            "plot_bgcolor": "var(--surface)",
                            "margin": {"l": 50, "r": 10, "t": 10, "b": 40},
                            "font": {"color": "var(--text)", "size": 10},
                            "xaxis": {"gridcolor": "var(--border)"},
                            "yaxis": {"gridcolor": "var(--border)"},
                        }},
                    ),
                ],
            ),
        ]
    )


def _pbo_panel() -> html.Div:
    return html.Div(
        children=[
            html.Div(
                style={"display": "flex", "gap": "12px", "marginBottom": "12px"},
                children=[
                    html.Div(
                        style={**_CARD, "flex": "1", "marginBottom": "0"},
                        children=[
                            html.Div("Matrice W_t (heatmap)", style=_LABEL),
                            dcc.Graph(
                                id="s1-pbo-weight-heatmap",
                                config={"displayModeBar": False},
                                style={"height": "260px"},
                                figure={"data": [], "layout": {
                                    "paper_bgcolor": "var(--surface)",
                                    "plot_bgcolor": "var(--surface)",
                                    "margin": {"l": 70, "r": 10, "t": 10, "b": 60},
                                    "font": {"color": "var(--text)", "size": 10},
                                }},
                            ),
                        ],
                    ),
                    html.Div(
                        style={**_CARD, "flex": "1", "marginBottom": "0"},
                        children=[
                            html.Div("PAS / Norma Frobenius", style=_LABEL),
                            dcc.Graph(
                                id="s1-pbo-pas-frob-chart",
                                config={"displayModeBar": False},
                                style={"height": "260px"},
                                figure={"data": [], "layout": {
                                    "paper_bgcolor": "var(--surface)",
                                    "plot_bgcolor": "var(--surface)",
                                    "margin": {"l": 50, "r": 10, "t": 10, "b": 40},
                                    "font": {"color": "var(--text)", "size": 10},
                                    "xaxis": {"gridcolor": "var(--border)"},
                                    "yaxis": {"gridcolor": "var(--border)"},
                                }},
                            ),
                        ],
                    ),
                ],
            ),
            html.Div(
                style=_CARD,
                children=[
                    html.Div("Pesi per arco", style=_LABEL),
                    html.Div(
                        id="s1-pbo-edge-table",
                        style={"fontSize": "12px", "color": "var(--muted)"},
                        children="Nessun dato disponibile.",
                    ),
                ],
            ),
        ]
    )


def create_s1() -> html.Div:
    return html.Div(
        children=[
            html.Div(
                "Struttura",
                style={
                    "fontSize": "15px",
                    "fontWeight": "600",
                    "color": "var(--text)",
                    "marginBottom": "16px",
                    "letterSpacing": "0.02em",
                },
            ),
            dmc.Tabs(
                id="s1-tabs",
                value="topology",
                children=[
                    dmc.TabsList(
                        children=[
                            dmc.Tab("Topologia", value="topology"),
                            dmc.Tab("ATG Temporale", value="atg"),
                            dmc.Tab("PBO", value="pbo"),
                        ],
                    ),
                    dmc.TabsPanel(
                        value="topology",
                        children=html.Div(_topology_panel(), style={"marginTop": "12px"}),
                    ),
                    dmc.TabsPanel(
                        value="atg",
                        children=html.Div(_atg_panel(), style={"marginTop": "12px"}),
                    ),
                    dmc.TabsPanel(
                        value="pbo",
                        children=html.Div(_pbo_panel(), style={"marginTop": "12px"}),
                    ),
                ],
            ),
        ]
    )
