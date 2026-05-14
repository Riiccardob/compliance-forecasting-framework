import dash
from dash import callback, Output, Input, State, html
from dashboard.layout.sections.s0_import import create_s0

SECTIONS = ["s0", "s1", "s2", "s3", "s4", "s5"]

SECTION_LABELS = {
    "s0": "Importazione", "s1": "Struttura",
    "s2": "Feature", "s3": "Analisi Causale",
    "s4": "Monitoraggio", "s5": "Alert",
}


def _load_section(section_id: str) -> html.Div:
    try:
        if section_id == "s0":
            return create_s0()
        elif section_id == "s1":
            from dashboard.layout.sections.s1_structure import create_s1
            return create_s1()
        elif section_id == "s2":
            from dashboard.layout.sections.s2_features import create_s2
            return create_s2()
        elif section_id == "s3":
            from dashboard.layout.sections.s3_causal import create_s3
            return create_s3()
        elif section_id == "s4":
            from dashboard.layout.sections.s4_monitor import create_s4
            return create_s4()
        elif section_id == "s5":
            from dashboard.layout.sections.s5_alerts import create_s5
            return create_s5()
    except ImportError:
        pass
    return html.Div(
        f"Sezione {section_id.upper()} — in sviluppo",
        style={"color": "var(--muted)", "padding": "40px", "fontSize": "16px"},
    )


@callback(
    Output("section-content", "children"),
    Output("active-section", "data"),
    [Input(f"nav-{s}", "n_clicks") for s in SECTIONS],
    State("active-section", "data"),
    prevent_initial_call=False,
)
def navigate(*args):
    current = args[-1] or "s0"
    ctx = dash.callback_context

    if not ctx.triggered or ctx.triggered[0]["value"] is None:
        return _load_section("s0"), "s0"

    triggered_id = ctx.triggered[0]["prop_id"].split(".")[0]
    new_section = triggered_id.replace("nav-", "")
    if new_section not in SECTIONS:
        new_section = current

    return _load_section(new_section), new_section


@callback(
    [Output(f"nav-{s}", "style") for s in SECTIONS],
    Input("active-section", "data"),
)
def update_nav_styles(active: str) -> list[dict]:
    active = active or "s0"
    styles = []
    for s in SECTIONS:
        if s == active:
            styles.append({
                "padding": "10px 16px",
                "color": "var(--text)",
                "cursor": "pointer",
                "fontSize": "13px",
                "borderLeft": "3px solid var(--accent)",
                "transition": "all 0.15s",
                "userSelect": "none",
                "backgroundColor": "rgba(196,163,90,0.06)",
            })
        else:
            styles.append({
                "padding": "10px 16px",
                "color": "var(--muted)",
                "cursor": "pointer",
                "fontSize": "13px",
                "borderLeft": "3px solid transparent",
                "transition": "all 0.15s",
                "userSelect": "none",
            })
    return styles
