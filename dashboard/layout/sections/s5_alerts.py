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


def create_s5() -> html.Div:
    return html.Div([
        html.Div("Alert", style=_TITLE_STYLE),

        html.Div([
            help_icon(
                "Filtri per navigare gli alert generati dalla pipeline. "
                "Criticita: Yellow = lead time > 7 giorni (preavviso lungo). "
                "Orange = 2-7 giorni oppure segnale IF o CUSUM attivo. "
                "Red = lead time < 2 giorni oppure tutti i segnali attivi. "
                "Il lead time e il numero di step previsionali prima della "
                "violazione della soglia SLA.", left=True
            ),
            html.Div([
                html.Div("Criticita", style=_LABEL_STYLE),
                dcc.Checklist(
                    id="s5-crit-filter",
                    options=[
                        {"label": "yellow", "value": "yellow"},
                        {"label": "orange", "value": "orange"},
                        {"label": "red",    "value": "red"},
                    ],
                    value=["yellow", "orange", "red"],
                    inline=True,
                    inputStyle={"marginRight": "5px"},
                    labelStyle={
                        "marginRight": "16px",
                        "fontSize": "13px",
                        "cursor": "pointer",
                        "color": "var(--text)",
                    },
                ),
            ], style={"marginRight": "32px"}),

            html.Div([
                html.Div("Compliance set", style=_LABEL_STYLE),
                dcc.Checklist(
                    id="s5-cs-filter",
                    options=[
                        {"label": "H_crit",  "value": "H_crit"},
                        {"label": "H_cache", "value": "H_cache"},
                    ],
                    value=["H_crit", "H_cache"],
                    inline=True,
                    inputStyle={"marginRight": "5px"},
                    labelStyle={
                        "marginRight": "16px",
                        "fontSize": "13px",
                        "cursor": "pointer",
                        "color": "var(--text)",
                    },
                ),
            ], style={"marginRight": "32px"}),

            html.Div([
                html.Div("Tipo anomalia", style=_LABEL_STYLE),
                dcc.Checklist(
                    id="s5-type-filter",
                    options=[],
                    value=[],
                    inline=True,
                    inputStyle={"marginRight": "5px"},
                    labelStyle={
                        "marginRight": "12px",
                        "fontSize": "13px",
                        "cursor": "pointer",
                        "color": "var(--text)",
                    },
                ),
            ]),
        ], style={
            "display": "flex",
            "alignItems": "flex-end",
            "marginBottom": "16px",
            "flexWrap": "wrap",
            "gap": "8px",
            "backgroundColor": "var(--surface)",
            "border": "1px solid var(--border)",
            "padding": "16px",
            "position": "relative",
        }),

        html.Div(style={"position": "relative"}, children=[
            help_icon(
                "Riepilogo degli alert filtrati. "
                "Ogni alert corrisponde a una previsione di violazione SLA per "
                "un compliance set in uno snapshot specifico. "
                "Clicca una riga della tabella per vedere il dettaglio completo "
                "e il confronto con il ground truth del dataset.", left=True
            ),
            html.Div(id="s5-summary", style={
                "display": "flex", "gap": "12px", "marginBottom": "16px",
            }),
        ]),

        html.Div(id="s5-table", style={"marginBottom": "20px"}),

        html.Div([
            html.Div(
                id="s5-detail-panel",
                style={
                    "flex": "1",
                    "backgroundColor": "var(--surface)",
                    "border": "1px solid var(--border)",
                    "padding": "16px",
                    "fontSize": "12px",
                    "minHeight": "180px",
                },
                children=html.Div(
                    "Seleziona un alert dalla tabella.",
                    style={"color": "var(--muted)"},
                ),
            ),
            html.Div(
                id="s5-gt-panel",
                style={
                    "flex": "1",
                    "marginLeft": "16px",
                    "backgroundColor": "var(--surface)",
                    "border": "1px solid var(--border)",
                    "padding": "16px",
                    "fontSize": "12px",
                    "minHeight": "180px",
                },
                children=html.Div(
                    "Ground truth vs previsione.",
                    style={"color": "var(--muted)"},
                ),
            ),
        ], style={"display": "flex", "marginBottom": "20px"}),

        html.Div([
            help_icon(
                "Distribuzione temporale degli alert. "
                "Asse X: data/ora dell'alert. "
                "Asse Y: compliance set. "
                "Colori: giallo=Yellow, arancione=Orange, rosso=Red. "
                "Ogni punto rappresenta un alert generato per quello snapshot.", left=True
            ),
            html.Div(
                "Distribuzione criticita nel tempo",
                style={
                    "fontSize": "11px",
                    "color": "var(--muted)",
                    "letterSpacing": "0.05em",
                    "textTransform": "uppercase",
                    "marginBottom": "8px",
                },
            ),
            dcc.Graph(
                id="s5-gantt",
                config={"displayModeBar": False},
                style={"height": "200px"},
            ),
        ], style={"position": "relative"}),

        dcc.Store(id="s5-selected-alert", data=None),
    ])
