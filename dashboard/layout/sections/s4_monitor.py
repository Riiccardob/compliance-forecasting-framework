from dash import html, dcc
import dash_mantine_components as dmc  # noqa: F401
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


def _gauge(label: str, component_id: str,
           tooltip_text: str = "") -> html.Div:
    return html.Div([
        html.Div(
            "?",
            title=tooltip_text,
            style={
                "fontSize": "10px", "color": "var(--muted)",
                "cursor": "help", "textAlign": "center",
                "marginBottom": "2px",
                "textDecoration": "underline dotted",
            },
        ) if tooltip_text else html.Div(),
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
        html.Div(
            id=component_id + "_val",
            style={
                "fontSize": "10px",
                "fontFamily": "JetBrains Mono, monospace",
                "color": "var(--text)",
                "textAlign": "center",
                "marginTop": "4px",
            },
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

        html.Div(
            ("Il monitoraggio strutturale verifica in tempo reale se il "
             "sistema rispetta i vincoli di conformita certificati. "
             "Opera su 4 livelli gerarchici: Threshold (violazione diretta "
             "delle soglie SLA), Z-score (anomalia statistica rispetto al "
             "comportamento nominale), Isolation Forest (anomalia multivariata "
             "rilevata da ML), CUSUM (accumulo di degrado comportamentale nel "
             "tempo). I gauge mostrano lo stato di ogni livello per lo snapshot "
             "selezionato: verde = nessuna anomalia, rosso = attivo. "
             "Il valore numerico indica l'intensita del segnale."),
            style={
                "fontSize": "12px", "color": "var(--muted)",
                "marginBottom": "16px", "lineHeight": "1.6",
                "borderLeft": "2px solid var(--border)", "paddingLeft": "8px",
            },
        ),

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
            help_icon(
                "I gauge mostrano l'attivazione dei 4 livelli del monitoraggio "
                "gerarchico per lo snapshot selezionato. "
                "Verde basso = livello non attivo (nominale). "
                "Rosso pieno = livello attivo (anomalia rilevata). "
                "Il valore numerico sotto indica l'intensita del segnale. "
                "I livelli si attivano in cascata: IF si attiva solo se "
                "Threshold o Z-score e gia attivo. "
                "Structural Validator si attiva solo se IF e CUSUM sono entrambi attivi."
            ),
            _gauge("Threshold", "s4-gauge-threshold",
                   "Livello 1a: verifica se una metrica supera direttamente "
                   "la soglia SLA definita nel certificato (es. latency > 100ms). "
                   "E il livello piu semplice e immediato."),
            _gauge("Z-score", "s4-gauge-zscore",
                   "Livello 1b: z = (valore - media_nominale) / std_nominale. "
                   "Attivo se |z| > 3.0. Rileva deviazioni statistiche rispetto "
                   "al comportamento nominale storico, anche senza violare la SLA."),
            _gauge("Isolation F", "s4-gauge-if",
                   "Livello 2: Isolation Forest addestrato sui soli snapshot "
                   "nominali. Attivo solo se Threshold o Z-score e gia attivo. "
                   "Rileva anomalie multidimensionali che i test univariati "
                   "potrebbero perdere."),
            _gauge("CUSUM", "s4-gauge-cusum",
                   "Livello 3: CUSUM accumula le deviazioni del PAS (per H_crit) "
                   "o Frobenius (per H_cache) nel tempo. Attivo se S_t > 5.0. "
                   "Su DSB rimane sempre a 0 perche il throughput e aggregato "
                   "e W_t = W_gold sempre (limitazione del dataset)."),
        ], style={
            "display": "flex",
            "gap": "16px",
            "marginBottom": "12px",
            "justifyContent": "flex-start",
            "position": "relative",
        }),

        html.Div(
            ("Nota: su GAMMA/DeathStarBench il throughput e aggregato a livello "
             "di finestra temporale -- tutti gli archi hanno throughput identico. "
             "Di conseguenza W(t) = W_gold per ogni finestra, Frobenius = 0 sempre "
             "e il CUSUM non accumula mai segnale. "
             "Il gauge CUSUM rimane in stato nominale per limitazione del dataset, "
             "non per assenza di anomalie."),
            style={
                "fontSize": "11px",
                "color": "var(--muted)",
                "marginBottom": "16px",
                "borderLeft": "2px solid var(--border)",
                "paddingLeft": "8px",
                "lineHeight": "1.6",
            },
        ),

        html.Div([
            help_icon(
                "Timeline che mostra l'attivazione dei segnali nel tempo "
                "per tutti gli snapshot processati dalla pipeline. "
                "Ogni riga = un livello di monitoraggio. "
                "Ogni quadratino = uno snapshot. "
                "Rosso = segnale attivo. Grigio scuro = nessun segnale. "
                "La riga Ground Truth usa i label reali del dataset per confronto: "
                "verde = snapshot nominale, rosso = anomalia reale (fault injection).", left=True
            ),
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
            html.Div([
                html.Div([
                    html.Div(style={"width": "12px", "height": "12px",
                                    "backgroundColor": "#b55e5e", "flexShrink": "0"}),
                    html.Span("Segnale attivo"),
                ], style={"display": "flex", "alignItems": "center", "gap": "5px"}),
                html.Div([
                    html.Div(style={"width": "12px", "height": "12px",
                                    "backgroundColor": "#2a2a2a", "flexShrink": "0"}),
                    html.Span("Nessun segnale"),
                ], style={"display": "flex", "alignItems": "center", "gap": "5px"}),
                html.Div([
                    html.Div(style={"width": "12px", "height": "12px",
                                    "backgroundColor": "#7aaa8f", "flexShrink": "0"}),
                    html.Span("Ground Truth nominale"),
                ], style={"display": "flex", "alignItems": "center", "gap": "5px"}),
                html.Div([
                    html.Div(style={"width": "12px", "height": "12px",
                                    "backgroundColor": "#b55e5e", "flexShrink": "0"}),
                    html.Span("Ground Truth anomalo"),
                ], style={"display": "flex", "alignItems": "center", "gap": "5px"}),
            ], style={"display": "flex", "gap": "16px", "fontSize": "11px",
                      "color": "var(--muted)", "marginBottom": "6px",
                      "flexWrap": "wrap"}),
            dcc.Graph(
                id="s4-timeline",
                config={"displayModeBar": False},
                style={"height": "200px"},
            ),
        ], style={"marginBottom": "20px", "position": "relative"}),

        html.Div([
            help_icon(
                "PAS (Path Adherence Score, asse sinistro oro): misura quanto il "
                "traffico segue il percorso critico nominale. Range 0-1. "
                "Frobenius (asse destro rosso): deviazione della distribuzione "
                "traffico dal baseline nominale. Range 0-inf. "
                "Su DeathStarBench entrambi sono costanti (PAS=0.25, Frobenius=0) "
                "per limitazione del dataset (throughput aggregato per finestra).", left=True
            ),
            html.Div(
                dcc.Graph(
                    id="s4-frob-pas-chart",
                    config={"displayModeBar": False},
                ),
                style={"flex": "1"},
            ),
            html.Div(
                style={
                    "width": "280px",
                    "minWidth": "280px",
                    "marginLeft": "16px",
                    "position": "relative",
                },
                children=[
                    help_icon(
                        "Dettaglio tecnico del risultato di monitoraggio per lo snapshot. "
                        "base_signal: True se Threshold o Z-score ha rilevato anomalia. "
                        "if_signal: True se Isolation Forest conferma (attivo solo se base_signal). "
                        "cusum_signal: True se CUSUM > 5.0. "
                        "structural_confirmed: True solo se IF e CUSUM sono entrambi attivi "
                        "e Frobenius > soglia per 3 finestre consecutive. "
                        "Su DSB structural_confirmed e sempre False per limitazione dataset."
                    ),
                    html.Div(
                        id="s4-result-card",
                        style={
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
                ],
            ),
        ], style={"display": "flex", "position": "relative"}),
    ])
