import plotly.graph_objects as go  # noqa: F401
from dash import callback, clientside_callback, Output, Input, html
from dashboard.core.data_manager import DataManager

_CAUSAL_STYLESHEET = [
    {"selector": "node", "style": {
        "background-color": "#1c1c1c", "border-color": "#2a2a2a",
        "border-width": 1, "color": "#e2ddd5", "font-size": "9px",
        "text-valign": "center", "label": "data(label)",
        "shape": "rectangle", "width": "label", "height": "22px",
        "padding": "5px", "text-wrap": "wrap", "text-max-width": "120px",
    }},
    {"selector": "edge", "style": {
        "width": "mapData(intensity,0,1,1,4)",
        "target-arrow-shape": "triangle", "curve-style": "bezier",
        "font-size": "8px", "label": "data(label)",
        "text-rotation": "autorotate",
    }},
    {"selector": ".linear", "style": {
        "line-color": "#388bfd", "target-arrow-color": "#388bfd",
        "color": "#388bfd",
    }},
    {"selector": ".nonlinear", "style": {
        "line-color": "#8957e5", "target-arrow-color": "#8957e5",
        "color": "#8957e5",
    }},
    {"selector": ".cross-property", "style": {
        "line-color": "#c4a35a", "target-arrow-color": "#c4a35a",
        "line-style": "dashed",
    }},
    {"selector": ":selected", "style": {
        "border-color": "#c4a35a", "line-color": "#c4a35a",
        "target-arrow-color": "#c4a35a",
    }},
]


def _render_chains(chains: list) -> html.Div:
    if not chains:
        return html.Div("Nessuna catena cross-property trovata.",
                        style={"color": "var(--muted)", "fontSize": "12px"})
    items = []
    for ch in chains:
        confirmed_str = "CONFERMATA" if ch.get("confirmed") else "non confermata"
        color         = "#7aaa8f"   if ch.get("confirmed") else "#5a5a5a"
        chain_str     = " -> ".join(ch.get("chain", []))
        cross         = f'{ch.get("source_cs", "")} -> {ch.get("target_cs", "")}'
        items.append(html.Div([
            html.Span(confirmed_str,
                      style={"color": color, "fontFamily": "JetBrains Mono",
                             "fontSize": "10px", "marginRight": "10px"}),
            html.Span(cross,     style={"color": "var(--accent)", "fontSize": "11px",
                                        "marginRight": "8px"}),
            html.Span(chain_str, style={"color": "var(--text)", "fontSize": "11px",
                                        "fontFamily": "JetBrains Mono"}),
        ], style={"padding": "4px 0", "borderBottom": "1px solid var(--border)"}))
    return html.Div(items)


def _detail_panel(title: str, rows: list) -> html.Div:
    return html.Div([
        html.Div(title, style={"fontWeight": "600", "color": "var(--text)",
                               "marginBottom": "10px", "fontSize": "12px"}),
    ] + [
        html.Div([
            html.Span(k, style={"color": "var(--muted)"}),
            html.Span(v, style={"color": "var(--text)",
                                "fontFamily": "JetBrains Mono"}),
        ], style={"display": "flex", "justifyContent": "space-between",
                  "padding": "4px 0", "borderBottom": "1px solid var(--border)"})
        for k, v in rows
    ])


@callback(
    Output("s3-cytoscape", "elements"),
    Output("s3-cytoscape", "stylesheet"),
    Output("s3-chains", "children"),
    Input("s3-cs-select", "value"),
    Input("s3-type-filter", "value"),
    Input("s3-intensity-min", "value"),
)
def update_causal_graph(cs, types, min_intensity):
    dm      = DataManager()
    results = dm.load_pipeline_results()

    if not results or cs not in results.get("compliance_sets", {}):
        msg = html.Div(
            "Pipeline non eseguita - vai su S0 e avvia la pipeline "
            "prima di usare questa sezione.",
            style={"color": "var(--muted)", "padding": "20px", "fontSize": "13px"},
        )
        return [], _CAUSAL_STYLESHEET, msg

    cg     = results["compliance_sets"][cs].get("causal_graph", {})
    edges  = cg.get("edges", [])
    chains = cg.get("cross_property_chains", [])

    min_i  = min_intensity or 0.0
    types  = types or ["linear", "nonlinear"]

    filtered = [
        e for e in edges
        if e.get("type") in types
        and (e.get("intensity") or 0) >= min_i
    ]

    node_ids = set()
    for e in filtered:
        node_ids.add(e["source"])
        node_ids.add(e["target"])

    elements = []
    for nid in node_ids:
        parts = nid.split(":")
        label = ":".join(parts[-2:]) if len(parts) >= 2 else nid
        elements.append({"data": {"id": nid, "label": label}})

    chain_pairs: set = set()
    for ch in chains:
        if ch.get("confirmed"):
            chain = ch.get("chain", [])
            for i in range(len(chain) - 1):
                chain_pairs.add((chain[i], chain[i + 1]))

    for e in filtered:
        cls = e.get("type", "")
        if (e["source"], e["target"]) in chain_pairs:
            cls += " cross-property"
        lbl = f"{e.get('intensity', 0):.2f}"
        lag = e.get("lag")
        if lag is not None:
            lbl += f" L{lag}"
        elements.append({"data": {
            "id":        f"{e['source']}->{e['target']}",
            "source":    e["source"],
            "target":    e["target"],
            "label":     lbl,
            "intensity": float(e.get("intensity") or 0),
        }, "classes": cls.strip()})

    edges_in_graph = filtered

    if not edges_in_graph:
        empty_msg = html.Div([
            html.Div("Nessuna relazione causale trovata.", style={
                "color": "var(--muted)", "fontSize": "13px", "fontWeight": "600",
                "marginBottom": "8px",
            }),
            html.Div(
                "Le possibili cause sono: (1) pipeline eseguita in modalita "
                "DEMO su un solo snapshot, che fornisce serie troppo corte "
                "per i test statistici (Granger richiede almeno max_lag+2 = 7 "
                "campioni per compliance set); (2) le serie temporali delle "
                "feature sono costanti (es. error_rate=0 su tutto il dataset "
                "nominale); (3) nessuna coppia supera la soglia Pearson |r|>0.7. "
                "Per ottenere risultati causali, eseguire la pipeline in modalita "
                "BATCH con almeno 30-50 snapshot.",
                style={"color": "var(--muted)", "fontSize": "11px", "lineHeight": "1.6"},
            ),
        ], style={
            "backgroundColor": "var(--surface)",
            "border": "1px solid var(--border)",
            "borderLeft": "2px solid var(--border)",
            "padding": "12px 16px",
            "marginTop": "12px",
        })
        return [], _CAUSAL_STYLESHEET, empty_msg

    return elements, _CAUSAL_STYLESHEET, html.Div(_render_chains(chains))


_ROW  = {"display": "flex", "justifyContent": "space-between",
         "padding": "4px 0", "borderBottom": "1px solid var(--border)"}
_K    = {"color": "var(--muted)"}
_V    = {"color": "var(--text)", "fontFamily": "JetBrains Mono", "fontSize": "11px"}

_EXPL = {
    "linear":    ("Causalita lineare: variazioni in source precedono "
                  "variazioni in target (test di Granger)"),
    "nonlinear": ("Dipendenza nonlineare: informazione da source riduce "
                  "incertezza su target (Transfer Entropy)"),
}
_TYPE_COLOR = {"linear": "#388bfd", "nonlinear": "#8957e5"}


@callback(
    Output("s3-edge-detail", "children"),
    Input("s3-cytoscape", "tapEdgeData"),
)
def show_edge_detail(edge_data):
    if not edge_data:
        return html.Div("Clicca un arco causale per i dettagli.",
                        style={"color": "var(--muted)"})
    dm      = DataManager()
    results = dm.load_pipeline_results()
    if not results:
        return html.Div("Nessun dato.", style={"color": "var(--muted)"})

    edge_id = edge_data.get("id", "")
    for cs, cs_data in results.get("compliance_sets", {}).items():
        for e in cs_data.get("causal_graph", {}).get("edges", []):
            eid = f"{e['source']}->{e['target']}"
            if eid != edge_id:
                continue

            src   = e["source"].split(":")[-1][:20]
            tgt   = e["target"].split(":")[-1][:20]
            etype = e.get("type", "")
            color = _TYPE_COLOR.get(etype, "var(--text)")
            lag   = e.get("lag")

            return html.Div([
                html.Div(f"{src} -> {tgt}", style={
                    "fontWeight": "600", "color": "var(--text)",
                    "marginBottom": "10px", "fontSize": "12px",
                }),
                html.Div([
                    html.Span("Tipo", style=_K),
                    html.Span(etype, style={**_V, "color": color, "fontWeight": "600"}),
                ], style=_ROW),
                html.Div([
                    html.Span("Intensita", style=_K),
                    html.Span(f"{e.get('intensity', 0):.4f}", style=_V),
                ], style=_ROW),
                html.Div([
                    html.Span("Metodo", style=_K),
                    html.Span(e.get("method", ""), style=_V),
                ], style=_ROW),
                html.Div([
                    html.Span("Lag", style=_K),
                    html.Span(str(lag) if lag is not None else "N/A", style=_V),
                ], style=_ROW),
                html.Div([
                    html.Span("CS", style=_K),
                    html.Span(cs, style=_V),
                ], style=_ROW),
                html.Div(
                    _EXPL.get(etype, ""),
                    style={"marginTop": "10px", "fontSize": "11px",
                           "color": color, "fontStyle": "italic",
                           "lineHeight": "1.5"},
                ),
            ])
    return html.Div("Dettaglio non trovato.", style={"color": "var(--muted)"})


# ---------------------------------------------------------------------------
# Clientside callback - reset viewport Cytoscape S3
# ---------------------------------------------------------------------------
clientside_callback(
    """
    function(n_clicks) {
        if (!n_clicks || n_clicks < 1) {
            return window.dash_clientside.no_update;
        }
        function findCy(el) {
            if (!el) return null;
            if (el._cy) return el._cy;
            for (var i = 0; i < el.children.length; i++) {
                var found = findCy(el.children[i]);
                if (found) return found;
            }
            return null;
        }
        var wrapper = document.getElementById('s3-cytoscape');
        var cy = findCy(wrapper);
        if (cy) { cy.fit(); cy.center(); }
        return window.dash_clientside.no_update;
    }
    """,
    Output("s3-cytoscape", "zoom"),
    Input("s3-cyto-reset", "n_clicks"),
    prevent_initial_call=True,
)
