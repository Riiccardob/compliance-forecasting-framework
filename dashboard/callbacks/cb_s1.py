import plotly.graph_objects as go
from dash import callback, Output, Input, html
from dashboard.core.data_manager import DataManager

_CS_INFO = {
    "H_crit": {
        "label":        "H_crit -- Real-time Dependability",
        "nodes":        ["nginx-web-server", "nginx-thrift",
                         "home-timeline-service", "post-storage-service",
                         "post-storage-mongodb"],
        "arcs":         ["e1", "e2", "e4", "e6"],
        "m_interf":     [],
        "sla":          {"latency_ms": "< 100 ms", "error_rate": "< 0.05"},
        "topology_type": "linear",
    },
    "H_cache": {
        "label":        "H_cache -- Cache Efficiency",
        "nodes":        ["home-timeline-service", "home-timeline-redis",
                         "post-storage-service", "post-storage-memcached"],
        "arcs":         ["e3", "e4", "e5"],
        "m_interf":     ["e2 (nginx-thrift -> home-timeline-service)"],
        "sla":          {"latency_ms": "< 20 ms", "error_rate": "< 0.10"},
        "topology_type": "parallel",
    },
}

_SHARED = {"home-timeline-service", "post-storage-service"}

_EDGES = {
    "e1": {"source": "nginx-web-server",       "target": "nginx-thrift",            "cs": ["H_crit"],           "interf": False},
    "e2": {"source": "nginx-thrift",            "target": "home-timeline-service",   "cs": ["H_crit"],           "interf": True},
    "e3": {"source": "home-timeline-service",   "target": "home-timeline-redis",     "cs": ["H_cache"],          "interf": False},
    "e4": {"source": "home-timeline-service",   "target": "post-storage-service",    "cs": ["H_crit", "H_cache"], "interf": False},
    "e5": {"source": "post-storage-service",    "target": "post-storage-memcached",  "cs": ["H_cache"],          "interf": False},
    "e6": {"source": "post-storage-service",    "target": "post-storage-mongodb",    "cs": ["H_crit"],           "interf": False},
}

_CYTO_ELEMENTS = [
    {"data": {"id": "H_crit_group",  "label": "H_crit"}},
    {"data": {"id": "H_cache_group", "label": "H_cache"}},
    {"data": {"id": "nginx-web-server",     "label": "nginx-web-server",     "parent": "H_crit_group"}},
    {"data": {"id": "nginx-thrift",         "label": "nginx-thrift",         "parent": "H_crit_group"}},
    {"data": {"id": "post-storage-mongodb", "label": "post-storage-mongodb", "parent": "H_crit_group"}},
    {"data": {"id": "home-timeline-redis",    "label": "home-timeline-redis",    "parent": "H_cache_group"}},
    {"data": {"id": "post-storage-memcached", "label": "post-storage-memcached", "parent": "H_cache_group"}},
    {"data": {"id": "home-timeline-service", "label": "home-timeline-service"}, "classes": "shared"},
    {"data": {"id": "post-storage-service",  "label": "post-storage-service"},  "classes": "shared"},
    {"data": {"id": "e1", "source": "nginx-web-server",     "target": "nginx-thrift",           "label": "e1"}},
    {"data": {"id": "e2", "source": "nginx-thrift",          "target": "home-timeline-service",  "label": "e2"}, "classes": "interference"},
    {"data": {"id": "e3", "source": "home-timeline-service", "target": "home-timeline-redis",    "label": "e3"}},
    {"data": {"id": "e4", "source": "home-timeline-service", "target": "post-storage-service",   "label": "e4"}},
    {"data": {"id": "e5", "source": "post-storage-service",  "target": "post-storage-memcached", "label": "e5"}},
    {"data": {"id": "e6", "source": "post-storage-service",  "target": "post-storage-mongodb",   "label": "e6"}},
]

_CYTO_STYLESHEET = [
    {"selector": "node", "style": {
        "background-color": "#1c1c1c", "border-color": "#2a2a2a", "border-width": 1,
        "color": "#e2ddd5", "font-size": "10px", "text-valign": "center",
        "text-halign": "center", "label": "data(label)", "shape": "rectangle",
        "width": "label", "height": "28px", "padding": "6px",
        "text-max-width": "130px", "text-wrap": "wrap",
    }},
    {"selector": "node:parent", "style": {
        "border-width": 2, "padding": "24px", "font-size": "11px",
        "text-valign": "top", "font-weight": "600", "background-opacity": 0.07,
        "shape": "rectangle",
    }},
    {"selector": "#H_crit_group", "style": {
        "background-color": "#388bfd", "border-color": "#388bfd", "color": "#388bfd",
    }},
    {"selector": "#H_cache_group", "style": {
        "background-color": "#3fb950", "border-color": "#3fb950", "color": "#3fb950",
    }},
    {"selector": ".shared", "style": {
        "border-color": "#8957e5",
        "border-width": 3,
        "border-style": "double",
    }},
    {"selector": "edge", "style": {
        "width": 1.5, "line-color": "#5a5a5a",
        "target-arrow-color": "#5a5a5a", "target-arrow-shape": "triangle",
        "curve-style": "bezier", "font-size": "9px", "color": "#5a5a5a",
        "label": "data(label)", "text-rotation": "autorotate",
    }},
    {"selector": ".interference", "style": {
        "line-style": "dashed", "line-color": "#c4a35a",
        "target-arrow-color": "#c4a35a", "line-dash-pattern": [6, 3],
    }},
    {"selector": ":selected", "style": {
        "border-color": "#c4a35a", "border-width": 2,
        "line-color": "#c4a35a", "target-arrow-color": "#c4a35a",
    }},
]

_DARK_LAYOUT = {
    "paper_bgcolor": "rgba(0,0,0,0)", "plot_bgcolor": "rgba(0,0,0,0)",
    "font": {"color": "#e2ddd5", "size": 11},
    "margin": {"l": 8, "r": 8, "t": 32, "b": 8},
}

_NODE_METRICS = ["cpu_percent", "mem_mb", "net_rx_mb", "net_tx_mb"]
_EDGE_METRICS = ["latency_ms", "error_rate", "throughput_rps"]
_NODE_IDS = ["nginx-web-server", "nginx-thrift", "home-timeline-service",
             "home-timeline-redis", "post-storage-service",
             "post-storage-memcached", "post-storage-mongodb"]
_EDGE_IDS = ["e1", "e2", "e3", "e4", "e5", "e6"]


def _detail_rows(title: str, rows: list[tuple[str, str]]) -> html.Div:
    return html.Div([
        html.Div(title, style={"fontWeight": "600", "color": "var(--text)",
                               "marginBottom": "12px"}),
        *[html.Div([
            html.Span(label, style={"color": "var(--muted)"}),
            html.Span(value, className="metric-value",
                      style={"color": "var(--text)", "fontFamily": "JetBrains Mono, monospace"}),
        ], style={"display": "flex", "justifyContent": "space-between",
                  "marginBottom": "6px"})
          for label, value in rows],
    ])


def _empty_fig(title: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(title=title, **_DARK_LAYOUT)
    return fig


# ---------------------------------------------------------------------------
# Callback 1 — popola Cytoscape
# ---------------------------------------------------------------------------
@callback(
    Output("s1-cytoscape", "elements"),
    Output("s1-cytoscape", "stylesheet"),
    Input("s1-tabs", "value"),
)
def populate_cytoscape(tab):
    return _CYTO_ELEMENTS, _CYTO_STYLESHEET


# ---------------------------------------------------------------------------
# Callback 2 — dettaglio click nodo/arco
# ---------------------------------------------------------------------------
@callback(
    Output("s1-topo-panel", "children"),
    Input("s1-cytoscape", "tapNodeData"),
    Input("s1-cytoscape", "tapEdgeData"),
)
def show_detail(node_data, edge_data):
    if not node_data and not edge_data:
        return html.Div("Clicca un nodo o un arco.", style={"color": "var(--muted)"})

    if edge_data:
        eid  = edge_data.get("id", "")
        info = _EDGES.get(eid, {})
        rows = [
            ("ID",       eid),
            ("Sorgente", info.get("source", "")),
            ("Target",   info.get("target", "")),
            ("CS",       ", ".join(info.get("cs", []))),
            ("M_interf", "si" if info.get("interf") else "no"),
        ]
        return _detail_rows("Arco " + eid, rows)

    nid = node_data.get("id", "")
    if nid in _CS_INFO:
        cs   = _CS_INFO[nid]
        rows = [
            ("Tipo",     cs["topology_type"]),
            ("Nodi",     str(len(cs["nodes"]))),
            ("A(H)",     ", ".join(cs["arcs"])),
            ("M_interf", "; ".join(cs["m_interf"]) or "nessuno"),
        ] + [(k, v) for k, v in cs["sla"].items()]
        return _detail_rows(cs["label"], rows)

    belongs = [k for k, v in _CS_INFO.items() if nid in v["nodes"]]
    rows = [
        ("Appartiene a", ", ".join(belongs) if belongs else "nessuno"),
        ("Shared",       "si" if nid in _SHARED else "no"),
    ]
    return _detail_rows(nid, rows)


# ---------------------------------------------------------------------------
# Callback 3 — inizializza slider ATG
# ---------------------------------------------------------------------------
@callback(
    Output("s1-atg-slider", "max"),
    Output("s1-atg-slider", "marks"),
    Output("s1-atg-snap-label", "children"),
    Input("s1-tabs", "value"),
)
def init_atg_slider(tab):
    if tab != "atg":
        return 0, {}, ""
    dm    = DataManager()
    snaps = dm.get_snapshots()
    n     = len(snaps)
    if n == 0:
        return 0, {0: "0"}, "Nessun dato caricato"
    marks = {0: "0", n // 2: str(n // 2), n - 1: str(n - 1)}
    label = (f"{n} snapshot -- nominali: {len(dm.get_nominal_snapshots())}"
             f" / anomali: {len(dm.get_anomalous_snapshots())}")
    return n - 1, marks, label


# ---------------------------------------------------------------------------
# Callback 4 — heatmap nodi e archi
# ---------------------------------------------------------------------------
@callback(
    Output("s1-atg-node-heatmap", "figure"),
    Output("s1-atg-edge-heatmap", "figure"),
    Input("s1-atg-slider", "value"),
)
def update_atg_heatmaps(idx):
    dm    = DataManager()
    snaps = dm.get_snapshots()
    empty = _empty_fig
    if not snaps or idx is None or idx >= len(snaps):
        return empty("Node metrics -- nessun dato"), empty("Edge metrics -- nessun dato")

    snap  = snaps[int(idx)]
    label = "ANOMALO" if snap["label"] else "nominale"

    z_node = [[snap["nodes"].get(n, {}).get(m) for n in _NODE_IDS]
               for m in _NODE_METRICS]
    fig_node = go.Figure(go.Heatmap(
        z=z_node, x=[n.split("-")[-1] for n in _NODE_IDS], y=_NODE_METRICS,
        colorscale=[[0, "#1c1c1c"], [1, "#c4a35a"]], showscale=True,
    ))
    fig_node.update_layout(
        title=f"Nodi -- snap {idx} ({label})", **_DARK_LAYOUT,
        yaxis={"tickfont": {"size": 9}}, xaxis={"tickfont": {"size": 9}},
    )

    z_edge = [[snap["edges"].get(e, {}).get(m) for e in _EDGE_IDS]
               for m in _EDGE_METRICS]
    fig_edge = go.Figure(go.Heatmap(
        z=z_edge, x=_EDGE_IDS, y=_EDGE_METRICS,
        colorscale=[[0, "#1c1c1c"], [1, "#388bfd"]], showscale=True,
    ))
    fig_edge.update_layout(
        title=f"Archi -- snap {idx} ({label})", **_DARK_LAYOUT,
        yaxis={"tickfont": {"size": 9}}, xaxis={"tickfont": {"size": 9}},
    )
    return fig_node, fig_edge


# ---------------------------------------------------------------------------
# Callback 5 — serie temporale
# ---------------------------------------------------------------------------
@callback(
    Output("s1-atg-ts-graph", "figure"),
    Input("s1-atg-metric-dd", "value"),
)
def update_atg_ts(metric):
    dm    = DataManager()
    snaps = dm.get_snapshots()
    if not snaps or not metric:
        return _empty_fig("Serie temporale -- nessun dato")

    is_node = metric in _NODE_METRICS
    x, y = [], []
    for snap in snaps:
        x.append(snap["timestamp"])
        if is_node:
            vals = [snap["nodes"].get(n, {}).get(metric)
                    for n in _NODE_IDS
                    if snap["nodes"].get(n, {}).get(metric) is not None]
        else:
            vals = [snap["edges"].get(e, {}).get(metric)
                    for e in _EDGE_IDS
                    if snap["edges"].get(e, {}).get(metric) is not None]
        y.append(sum(vals) / len(vals) if vals else None)

    fig = go.Figure(go.Scatter(
        x=x, y=y, mode="lines",
        line={"color": "#c4a35a", "width": 1.2},
    ))
    for snap in snaps:
        if snap["label"]:
            ts = snap["timestamp"]
            fig.add_vrect(x0=ts, x1=ts + 5_000_000,
                          fillcolor="#b55e5e", opacity=0.08, line_width=0)
    fig.update_layout(
        title=f"{metric} (media su tutti i nodi/archi)",
        xaxis_title="timestamp (us)", yaxis_title=metric,
        **_DARK_LAYOUT,
    )
    return fig


# ---------------------------------------------------------------------------
# Callback 6 — grafici PBO
# ---------------------------------------------------------------------------
@callback(
    Output("s1-pbo-weight-heatmap", "figure"),
    Output("s1-pbo-pas-frob-chart", "figure"),
    Output("s1-pbo-edge-table", "children"),
    Input("s1-tabs", "value"),
)
def update_pbo(tab):
    if tab != "pbo":
        return go.Figure(), go.Figure(), []

    dm = DataManager()
    ws = dm.get_weight_series()
    wg = dm.get_gold_standard()

    if not ws or not wg:
        msg = html.Div("Pipeline non ancora eseguita.",
                       style={"color": "var(--muted)", "padding": "20px"})
        return _empty_fig("W_t vs W_gold"), _empty_fig("PAS / Frobenius"), msg

    last_w = ws[-1]["weights"]
    z      = [[last_w.get(e, 0), wg.get(e, 0)] for e in _EDGE_IDS]
    fig_w  = go.Figure(go.Heatmap(
        z=z, x=["W_t", "W_gold"], y=_EDGE_IDS,
        colorscale=[[0, "#1c1c1c"], [1, "#c4a35a"]], showscale=True,
        zmin=0, zmax=1,
    ))
    fig_w.update_layout(title="W_t (ultimo snap) vs W_gold", **_DARK_LAYOUT)

    fig_pf  = _empty_fig("PAS / Frobenius -- esegui la pipeline")
    results = dm.load_pipeline_results()
    if results and "H_crit" in results.get("compliance_sets", {}):
        mon_crit = results["compliance_sets"]["H_crit"].get("monitor_results", [])
        if mon_crit:
            ts_list   = [m["timestamp"] for m in mon_crit]
            pas_vals  = [m.get("pas_value") for m in mon_crit]
            frob_vals = [m.get("frobenius_distance") for m in mon_crit]
            fig_pf = go.Figure()
            fig_pf.add_trace(go.Scatter(
                x=ts_list, y=pas_vals, name="PAS (H_crit)",
                line={"color": "#c4a35a", "width": 1.5}, yaxis="y1",
            ))
            fig_pf.add_trace(go.Scatter(
                x=ts_list, y=frob_vals, name="Frobenius",
                line={"color": "#b55e5e", "width": 1.5}, yaxis="y2",
            ))
            fig_pf.update_layout(
                title="PAS e Frobenius nel tempo",
                yaxis={"title": "PAS", "color": "#c4a35a", "side": "left"},
                yaxis2={"title": "Frobenius", "color": "#b55e5e",
                        "overlaying": "y", "side": "right"},
                legend={"bgcolor": "rgba(0,0,0,0)"},
                **_DARK_LAYOUT,
            )

    header = html.Div(
        "W_gold per arco",
        style={"fontSize": "11px", "color": "var(--muted)",
               "letterSpacing": "0.05em", "textTransform": "uppercase",
               "marginBottom": "8px"},
    )
    rows = []
    for eid in _EDGE_IDS:
        info = _EDGES[eid]
        rows.append(html.Div([
            html.Span(eid, style={"color": "var(--accent)", "width": "40px",
                                  "display": "inline-block",
                                  "fontFamily": "JetBrains Mono"}),
            html.Span(f"{info['source']} -> {info['target']}",
                      style={"color": "var(--muted)", "flex": "1", "margin": "0 12px"}),
            html.Span(f"{wg.get(eid, 0):.4f}",
                      style={"color": "var(--text)", "fontFamily": "JetBrains Mono"}),
        ], style={"display": "flex", "alignItems": "center",
                  "padding": "5px 0", "borderBottom": "1px solid var(--border)"}))

    return fig_w, fig_pf, html.Div([header] + rows)
