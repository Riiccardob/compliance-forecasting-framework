from dash import html, dcc
import dash_mantine_components as dmc
import dash_cytoscape as cyto
from dashboard.layout.help_utils import help_icon

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

    def _sq(color, double=False):
        style = {
            "width": "12px", "height": "12px",
            "borderRadius": "0",
            "backgroundColor": color,
            "flexShrink": "0",
        }
        if double:
            style["backgroundColor"] = "transparent"
            style["border"] = f"3px double {color}"
        return html.Div(style=style)

    def _line(color, dashed=False):
        return html.Div(style={
            "width": "20px", "height": "2px",
            "borderTop": f"2px {'dashed' if dashed else 'solid'} {color}",
            "flexShrink": "0",
        })

    def _badge(symbol, label):
        return html.Div([symbol, html.Span(label)],
                        style={"display": "flex", "alignItems": "center",
                               "gap": "5px"})

    legend = html.Div([
        _badge(_sq("#388bfd"),          "H_crit"),
        _badge(_sq("#3fb950"),          "H_cache"),
        _badge(_sq("#8957e5", double=True), "Shared"),
        _badge(_line("#c4a35a", dashed=True), "M_interf (interferenza)"),
        _badge(_line("#5a5a5a"),        "Arco interno"),
    ], style={
        "display": "flex", "gap": "16px", "marginBottom": "12px",
        "fontSize": "11px", "color": "var(--muted)",
        "alignItems": "center", "flexWrap": "wrap",
    })

    return html.Div([
        legend,
        html.Button(
            "Reimposta vista",
            id="s1-cyto-reset",
            n_clicks=0,
            style={
                "fontSize": "11px", "padding": "4px 10px",
                "backgroundColor": "var(--surface)",
                "border": "1px solid var(--border)",
                "color": "var(--muted)", "cursor": "pointer",
                "marginBottom": "6px", "borderRadius": "2px",
            },
        ),
        html.Div(
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
                        minZoom=0.3,
                        maxZoom=3.0,
                    ),
                ),
                html.Div(
                    id="s1-topo-panel",
                    style={**_CARD, "width": "220px", "minHeight": "420px",
                           "fontSize": "12px", "color": "var(--muted)"},
                    children="Seleziona un nodo o arco per i dettagli.",
                ),
            ],
        ),
        html.Div(id="s1-edge-table", style={"marginTop": "16px"}),
        html.Div(id="s1-cs-panel",
                 style={"display": "flex", "gap": "16px", "marginTop": "16px"},
                 children=[]),
    ])


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
                style={**_CARD, "position": "relative"},
                children=[
                    help_icon(
                        "Uno snapshot e una finestra temporale di 5 secondi del "
                        "sistema. Contiene le metriche di tutti i 7 microservizi "
                        "(CPU, memoria, rete) e dei 6 archi (latenza, error rate, "
                        "throughput). Il label indica se il sistema era in stato "
                        "nominale (nessun fault) o anomalo (fault injection attiva). "
                        "Lo slider seleziona quale snapshot visualizzare nelle heatmap."
                    ),
                    html.Div("Snapshot", style=_LABEL),
                    dcc.Slider(
                        id="s1-atg-slider",
                        min=0,
                        max=0,
                        step=1,
                        value=0,
                        marks=None,
                        tooltip={"placement": "bottom", "always_visible": False},
                        updatemode="mouseup",
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
                        style={**_CARD, "flex": "1", "marginBottom": "0",
                               "position": "relative"},
                        children=[
                            help_icon(
                                "Heatmap delle metriche di risorse per ogni microservizio "
                                "nello snapshot selezionato. Righe = metriche (CPU, memoria, "
                                "rete RX, rete TX). Colonne = microservizi. "
                                "Colori piu chiari = valori piu alti. "
                                "Il bordo rosso evidenzia il nodo riportato come anomalo "
                                "nel ground truth del dataset.", left=True
                            ),
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
                        style={**_CARD, "flex": "1", "marginBottom": "0",
                               "position": "relative"},
                        children=[
                            help_icon(
                                "Heatmap delle metriche di comunicazione per ogni arco "
                                "(connessione tra microservizi) nello snapshot. "
                                "Righe = metriche (latenza ms, error rate, throughput rps). "
                                "Colonne = archi (e1..e6). "
                                "Colori piu chiari = valori piu alti. "
                                "La latenza misura il ritardo di risposta, l'error rate "
                                "la percentuale di richieste fallite."
                            ),
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
                style={**_CARD, "position": "relative"},
                children=[
                    help_icon(
                        "Andamento della metrica selezionata nel tempo, mediata su "
                        "tutti i nodi o archi del sistema. "
                        "La linea dorata verticale indica la posizione dello snapshot "
                        "corrente (selezionato con lo slider sopra). "
                        "Le zone rosse trasparenti indicano finestre anomale secondo "
                        "il ground truth del dataset GAMMA/DSB. "
                        "Con molti snapshot il grafico usa un campione rappresentativo."
                    ),
                    html.Div([
                        html.Div([
                            html.Div("Tipo elemento",
                                     style={**_LABEL, "marginBottom": "2px"}),
                            dcc.RadioItems(
                                id="s1-atg-entity-type",
                                options=[
                                    {"label": "Media tutti",    "value": "all"},
                                    {"label": "Nodo specifico", "value": "node"},
                                    {"label": "Arco specifico", "value": "edge"},
                                ],
                                value="all",
                                inline=True,
                                inputStyle={"marginRight": "4px"},
                                labelStyle={"marginRight": "14px",
                                            "color": "var(--muted)",
                                            "fontSize": "11px",
                                            "cursor": "pointer"},
                            ),
                        ], style={"flex": "1"}),
                    ], style={"display": "flex", "alignItems": "flex-start",
                              "marginBottom": "8px", "gap": "12px"}),
                    html.Div(
                        id="s1-atg-entity-dd-wrap",
                        style={"display": "none", "marginBottom": "8px"},
                        children=[
                            dcc.Dropdown(
                                id="s1-atg-entity-dd",
                                options=[],
                                value=None,
                                clearable=False,
                                placeholder="Seleziona elemento...",
                                style={
                                    "backgroundColor": "var(--surface)",
                                    "color": "var(--text)",
                                },
                            ),
                        ],
                    ),
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
                "Il Probabilistic Behavioral Overlay (PBO) rappresenta come il "
                "traffico si distribuisce tra i percorsi del sistema. "
                "W_t e la matrice dei pesi di transizione al tempo t: "
                "w(u->v,t) = throughput(u->v,t) / somma throughput da u. "
                "W_gold e la media di W_t sui soli snapshot nominali (baseline). "
                "PAS (Path Adherence Score) misura quanto il percorso critico "
                "H_crit segue il comportamento nominale: PAS = prod(w lungo il percorso). "
                "Frobenius = ||W_t - W_gold||_F misura la deviazione globale dal baseline.",
                style={
                    "fontSize": "12px", "color": "var(--muted)",
                    "marginBottom": "12px", "lineHeight": "1.6",
                    "borderLeft": "2px solid var(--border)", "paddingLeft": "8px",
                },
            ),
            html.Div(
                id="s1-pbo-wgold-graph",
                style={**_CARD, "marginBottom": "12px"},
                children=[
                    html.Div("Distribuzione traffico W_gold (baseline nominale)",
                             style=_LABEL),
                    dcc.Graph(
                        id="s1-pbo-wgold-fig",
                        config={"displayModeBar": False},
                        style={"height": "280px"},
                    ),
                    html.Div(
                        "Spessore arco proporzionale al peso W_gold (media sulle finestre "
                        "nominali). Su DSB tutti i pesi sono ~0.5 per i nodi con 2 uscite "
                        "(throughput aggregato).",
                        style={"fontSize": "11px", "color": "var(--muted)",
                               "marginTop": "4px"},
                    ),
                ],
            ),
            html.Div(
                style={"display": "flex", "gap": "12px", "marginBottom": "12px"},
                children=[
                    html.Div(
                        style={**_CARD, "flex": "1", "marginBottom": "0",
                               "position": "relative"},
                        children=[
                            help_icon(
                                "W_t e la matrice dei pesi di transizione del traffico al "
                                "tempo t: ogni cella w(e) indica la frazione del traffico "
                                "totale dal nodo sorgente che passa per l'arco e. "
                                "W_gold e la media di W_t sui soli snapshot nominali "
                                "(baseline del comportamento atteso). "
                                "Su DeathStarBench le due colonne sono identiche perche il "
                                "throughput e aggregato a livello di finestra -- non disaggregato "
                                "per singolo arco. Questo e un limite del dataset, non del framework."
                            ),
                            html.Div("Matrice W_t (heatmap)", style=_LABEL),
                            html.Div([
                                html.Div("Snapshot W_t", style=_LABEL),
                                dcc.Slider(
                                    id="s1-pbo-slider",
                                    min=0, max=0, step=1, value=0,
                                    marks=None,
                                    tooltip={"placement": "bottom",
                                             "always_visible": False},
                                    updatemode="mouseup",
                                ),
                                html.Div(
                                    id="s1-pbo-snap-label",
                                    style={"fontSize": "11px",
                                           "color": "var(--muted)",
                                           "marginTop": "4px"},
                                ),
                            ]),
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
                            html.Div(
                                ("Su GAMMA/DSB: W_t = W_gold per ogni snapshot perche il "
                                 "throughput e aggregato a livello di finestra (non per singolo arco). "
                                 "Le due colonne della heatmap sono quindi sempre identiche. "
                                 "Questo e una limitazione del dataset, non del framework."),
                                style={
                                    "fontSize": "11px", "color": "var(--muted)",
                                    "marginTop": "6px", "fontStyle": "italic",
                                },
                            ),
                        ],
                    ),
                    html.Div(
                        style={**_CARD, "flex": "1", "marginBottom": "0",
                               "position": "relative"},
                        children=[
                            help_icon(
                                "PAS (Path Adherence Score): prodotto dei pesi lungo il percorso "
                                "critico di H_crit. PAS=1.0 significa tutto il traffico sul "
                                "percorso principale; PAS=0.0 nessun traffico. "
                                "Frobenius: norma ||W_t - W_gold||_F, misura quanto la distribuzione "
                                "del traffico si discosta dal baseline nominale. "
                                "Su DSB entrambi sono costanti (PAS=0.25, Frobenius=0) per la "
                                "limitazione del dataset descritta sopra."
                            ),
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
            html.Div(id="s1-pbo-dsb-note"),
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
                            dmc.TabsTab("Topologia — ipergrafo H_cert", value="topology"),
                            dmc.TabsTab("ATG — metriche nel tempo", value="atg"),
                            dmc.TabsTab("PBO — distribuzione traffico", value="pbo"),
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
