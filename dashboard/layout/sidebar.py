from dash import html

_SECTIONS = [
    ("s0", "Importazione"),
    ("s1", "Struttura"),
    ("s2", "Feature"),
    ("s3", "Analisi Causale"),
    ("s4", "Monitoraggio"),
    ("s5", "Alert"),
]

_NAV_STYLE = {
    "padding": "10px 16px",
    "color": "var(--muted)",
    "cursor": "pointer",
    "fontSize": "13px",
    "borderLeft": "3px solid transparent",
    "transition": "all 0.15s",
    "userSelect": "none",
}


def _build_header() -> html.Div:
    return html.Div(
        style={
            "padding": "20px 16px 16px",
            "borderBottom": "1px solid var(--border)",
        },
        children=[
            html.Div(
                "Compliance",
                style={
                    "fontSize": "11px",
                    "color": "var(--muted)",
                    "letterSpacing": "0.1em",
                    "textTransform": "uppercase",
                },
            ),
            html.Div(
                "Forecasting",
                style={
                    "fontSize": "16px",
                    "fontWeight": 600,
                    "color": "var(--accent)",
                    "marginTop": "2px",
                },
            ),
            html.Div(
                "Monitoraggio predittivo di proprieta non funzionali",
                style={
                    "fontSize": "10px",
                    "color": "var(--muted)",
                    "marginTop": "4px",
                    "lineHeight": "1.4",
                },
            ),
        ],
    )


def _build_footer() -> html.Div:
    return html.Div(
        style={
            "padding": "12px 16px",
            "borderTop": "1px solid var(--border)",
        },
        children=[
            html.Div(
                "DSB / GAMMA",
                style={
                    "fontSize": "10px",
                    "color": "var(--muted)",
                    "textTransform": "uppercase",
                    "letterSpacing": "0.1em",
                },
            ),
            html.Div(id="sidebar-status", children=[]),
        ],
    )


def _build_nav_links() -> list:
    return [
        html.Div(label, id=f"nav-{sid}", n_clicks=0, style=dict(_NAV_STYLE))
        for sid, label in _SECTIONS
    ]


def create_sidebar() -> html.Div:
    return html.Div(
        id="sidebar",
        style={
            "width": "220px",
            "minWidth": "220px",
            "height": "100vh",
            "backgroundColor": "var(--surface)",
            "borderRight": "1px solid var(--border)",
            "display": "flex",
            "flexDirection": "column",
            "padding": "0",
            "overflowY": "auto",
        },
        children=[
            _build_header(),
            html.Div(
                id="nav-links",
                style={"padding": "8px 0", "flex": "1"},
                children=[
                    html.Div([
                        html.Div("Segui questo ordine:", style={
                            "fontSize": "9px", "color": "var(--muted)",
                            "textTransform": "uppercase", "letterSpacing": "0.08em",
                            "marginBottom": "8px",
                        }),
                        html.Div([
                            html.Span(id="sidebar-step1-icon",
                                      children="1",
                                      style={"display": "inline-flex", "alignItems": "center",
                                             "justifyContent": "center", "width": "16px", "height": "16px",
                                             "borderRadius": "50%", "fontSize": "9px", "marginRight": "6px",
                                             "border": "1px solid var(--muted)", "color": "var(--muted)",
                                             "flexShrink": "0"}),
                            html.Span("Carica i CSV e costruisci ATG",
                                      style={"fontSize": "11px", "color": "var(--muted)"}),
                        ], style={"display": "flex", "alignItems": "center", "marginBottom": "4px"}),
                        html.Div([
                            html.Span(id="sidebar-step2-icon",
                                      children="2",
                                      style={"display": "inline-flex", "alignItems": "center",
                                             "justifyContent": "center", "width": "16px", "height": "16px",
                                             "borderRadius": "50%", "fontSize": "9px", "marginRight": "6px",
                                             "border": "1px solid var(--muted)", "color": "var(--muted)",
                                             "flexShrink": "0"}),
                            html.Span("Esegui la pipeline",
                                      style={"fontSize": "11px", "color": "var(--muted)"}),
                        ], style={"display": "flex", "alignItems": "center", "marginBottom": "12px"}),
                    ], style={"padding": "8px 16px 0", "marginBottom": "4px"}),
                    *_build_nav_links(),
                ],
            ),
            _build_footer(),
        ],
    )
