from dash import html, dcc
import dash_cytoscape as cyto
from dashboard.layout.help_utils import help_icon

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


def create_s3() -> html.Div:
    return html.Div([
        html.Div("Analisi Causale", style=_TITLE_STYLE),

        html.Div(
            ("Il grafo mostra le relazioni causali tra le feature del compliance set "
             "selezionato. Archi lineari (Granger, p<0.05) e non-lineari (Transfer "
             "Entropy normalizzata > 0.1). I filtri sotto limitano gli archi visibili."),
            style={"fontSize": "12px", "color": "var(--muted)", "marginBottom": "12px"},
        ),

        html.Div([
            html.Div([
                html.Div("Compliance set", style=_LABEL_STYLE),
                dcc.RadioItems(
                    id="s3-cs-select",
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
                html.Div("Tipo", style=_LABEL_STYLE),
                dcc.Checklist(
                    id="s3-type-filter",
                    options=[
                        {"label": "linear",    "value": "linear"},
                        {"label": "nonlinear", "value": "nonlinear"},
                    ],
                    value=["linear", "nonlinear"],
                    inline=True,
                    inputStyle={"marginRight": "5px"},
                    labelStyle={
                        "marginRight": "16px",
                        "color": "var(--text)",
                        "fontSize": "13px",
                    },
                ),
            ], style={"marginRight": "32px"}),

            html.Div([
                html.Div("Intensita minima", style=_LABEL_STYLE),
                dcc.Slider(
                    id="s3-intensity-min",
                    min=0.0, max=1.0, step=0.05, value=0.0,
                    marks={0: "0", 0.5: "0.5", 1: "1"},
                    tooltip={"placement": "bottom", "always_visible": False},
                ),
            ], style={"width": "200px"}),

        ], style={
            "display": "flex",
            "alignItems": "flex-end",
            "marginBottom": "16px",
            "flexWrap": "wrap",
            "gap": "8px",
        }),

        html.Div([
            html.Div([
                html.Div([
                    html.Div([
                        html.Div(style={
                            "width": "10px", "height": "10px",
                            "borderRadius": "50%",
                            "backgroundColor": "#388bfd",
                            "flexShrink": "0",
                        }),
                        html.Span("Causalita lineare (Granger)"),
                    ], style={"display": "flex", "alignItems": "center", "gap": "5px"}),
                    html.Div([
                        html.Div(style={
                            "width": "10px", "height": "10px",
                            "borderRadius": "50%",
                            "backgroundColor": "#8957e5",
                            "flexShrink": "0",
                        }),
                        html.Span("Causalita nonlineare (Transfer Entropy)"),
                    ], style={"display": "flex", "alignItems": "center", "gap": "5px"}),
                    html.Span("Spessore arco = intensita causale (0.0 - 1.0)"),
                ], style={
                    "display": "flex", "gap": "16px", "marginBottom": "8px",
                    "fontSize": "11px", "color": "var(--muted)",
                    "alignItems": "center", "flexWrap": "wrap",
                }),
                html.Button(
                    "Reimposta vista",
                    id="s3-cyto-reset",
                    n_clicks=0,
                    style={
                        "fontSize": "11px", "padding": "4px 10px",
                        "backgroundColor": "var(--surface)",
                        "border": "1px solid var(--border)",
                        "color": "var(--muted)", "cursor": "pointer",
                        "marginBottom": "6px", "borderRadius": "2px",
                    },
                ),
                cyto.Cytoscape(
                    id="s3-cytoscape",
                    elements=[],
                    layout={
                        "name": "cose",
                        "animate": False,
                        "nodeRepulsion": 8000,
                        "gravity": 0.1,
                    },
                    style={
                        "height": "480px",
                        "backgroundColor": "var(--surface)",
                        "border": "1px solid var(--border)",
                    },
                    stylesheet=[],
                    boxSelectionEnabled=False,
                    minZoom=0.2,
                    maxZoom=4.0,
                ),
                help_icon(
                    "Grafo delle relazioni causali tra le feature del compliance set. "
                    "Ogni nodo e una feature (CPU di un servizio, latenza di un arco...). "
                    "Una freccia da A a B significa che le variazioni in A precedono "
                    "statisticamente le variazioni in B. "
                    "Archi blu: causalita lineare (test di Granger, p<0.05). "
                    "Archi viola: dipendenza non-lineare (Transfer Entropy > 0.1). "
                    "Lo spessore dell'arco indica l'intensita causale (0=debole, 1=forte). "
                    "Clicca un arco per vedere i dettagli nel pannello destro.", left=True
                ),
            ], style={"flex": "1", "display": "flex", "flexDirection": "column",
                      "position": "relative"}),
            html.Div(
                id="s3-edge-detail",
                style={
                    "width": "260px",
                    "minWidth": "260px",
                    "backgroundColor": "var(--surface)",
                    "border": "1px solid var(--border)",
                    "padding": "14px",
                    "fontSize": "12px",
                    "color": "var(--muted)",
                    "marginLeft": "16px",
                    "overflowY": "auto",
                    "maxHeight": "480px",
                },
                children=html.Div(
                    "Clicca un arco causale per i dettagli.",
                    style={"color": "var(--muted)"},
                ),
            ),
        ], style={"display": "flex"}),

        html.Div([
            html.Div([
                html.Div("Catene cross-property", style={
                    "fontSize": "11px",
                    "color": "var(--muted)",
                    "letterSpacing": "0.05em",
                    "textTransform": "uppercase",
                    "marginBottom": "8px",
                    "marginTop": "20px",
                }),
                html.Span(
                    "?",
                    title=(
                        "Una catena cross-property e una sequenza causale che "
                        "coinvolge piu compliance set: un arco esterno (M_interf) "
                        "porta carico su un nodo condiviso tra H_crit e H_cache, "
                        "che a sua volta influenza un arco interno al set target. "
                        "CONFERMATA = entrambi i test di Granger della catena "
                        "sono significativi."
                    ),
                    style={
                        "display": "inline-flex",
                        "alignItems": "center",
                        "justifyContent": "center",
                        "width": "15px", "height": "15px",
                        "borderRadius": "50%",
                        "border": "1px solid var(--muted)",
                        "color": "var(--muted)",
                        "fontSize": "9px",
                        "cursor": "help",
                        "marginLeft": "6px",
                        "verticalAlign": "middle",
                    },
                ),
            ], style={"display": "flex", "alignItems": "center"}),
            html.Div(id="s3-chains", style={"fontSize": "12px", "color": "var(--muted)"}),
        ]),
    ])
