import pandas as pd
import plotly.graph_objects as go
from dash import callback, clientside_callback, Output, Input, html, ctx
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
# Callback 1 - popola Cytoscape
# ---------------------------------------------------------------------------
@callback(
    Output("s1-cytoscape", "elements"),
    Output("s1-cytoscape", "stylesheet"),
    Input("s1-tabs", "value"),
)
def populate_cytoscape(tab):
    return _CYTO_ELEMENTS, _CYTO_STYLESHEET


# ---------------------------------------------------------------------------
# Callback 2 - dettaglio click nodo/arco
# ---------------------------------------------------------------------------
@callback(
    Output("s1-topo-panel", "children"),
    Input("s1-cytoscape", "tapNodeData"),
    Input("s1-cytoscape", "tapEdgeData"),
)
def show_detail(node_data, edge_data):
    if not ctx.triggered:
        return html.Div("Clicca un nodo o un arco.", style={"color": "var(--muted)"})

    triggered_prop = ctx.triggered[0]["prop_id"]

    # Clic su arco
    if "tapEdgeData" in triggered_prop and edge_data:
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

    # Clic su nodo
    if "tapNodeData" in triggered_prop and node_data:
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
        shared  = "si" if nid in _SHARED else "no"
        rows = [
            ("Appartiene a", ", ".join(belongs) if belongs else "nessuno"),
            ("Shared",       shared),
            ("Metriche",     "cpu_percent, mem_mb, net_rx_mb, net_tx_mb"),
        ]
        return _detail_rows(nid, rows)

    return html.Div("Clicca un nodo o un arco.", style={"color": "var(--muted)"})


# ---------------------------------------------------------------------------
# Callback 3 - inizializza slider ATG
# ---------------------------------------------------------------------------
@callback(
    Output("s1-atg-slider", "max"),
    Output("s1-atg-slider", "marks"),
    Input("s1-tabs", "value"),
)
def init_atg_slider(tab):
    if tab != "atg":
        return 0, {}
    dm    = DataManager()
    snaps = dm.get_snapshots()
    n     = len(snaps)
    if n == 0:
        return 0, {0: "0"}
    marks = {0: "0", n // 2: str(n // 2), n - 1: str(n - 1)}
    return n - 1, marks


# ---------------------------------------------------------------------------
# Callback 4 - heatmap nodi e archi + label snapshot
# ---------------------------------------------------------------------------
@callback(
    Output("s1-atg-node-heatmap", "figure"),
    Output("s1-atg-edge-heatmap", "figure"),
    Output("s1-atg-snap-label", "children"),
    Input("s1-atg-slider", "value"),
)
def update_atg_heatmaps(idx):
    dm    = DataManager()
    snaps = dm.get_snapshots()
    empty = _empty_fig
    empty_label = html.Span("Nessun dato caricato.", style={"color": "var(--muted)"})
    if not snaps or idx is None or idx >= len(snaps):
        return (empty("Node metrics -- nessun dato"),
                empty("Edge metrics -- nessun dato"),
                empty_label)

    snap    = snaps[int(idx)]
    ts_sec  = snap["timestamp"] / 1_000_000
    is_anom = bool(snap["label"])
    label   = "ANOMALO" if is_anom else "nominale"

    if not is_anom:
        snap_label = html.Span(
            f"Snapshot {idx} / {ts_sec:.3f} -- nominale",
            style={"color": "var(--muted)"},
        )
    else:
        import json as _json
        a_type    = snap.get("anomaly_type") or "?"
        _raw_nodes = snap.get("anomaly_node_ids") or "[]"
        try:
            a_nodes = (_json.loads(_raw_nodes)
                       if isinstance(_raw_nodes, str)
                       else (_raw_nodes or []))
        except (ValueError, TypeError):
            a_nodes = []
        nodes_txt = ", ".join(a_nodes) if a_nodes else "N/A"
        snap_label = html.Span([
            html.Span(f"Snapshot {idx} / {ts_sec:.3f} -- ",
                      style={"color": "var(--muted)"}),
            html.Span("ANOMALO", style={"color": "#b55e5e", "fontWeight": "600"}),
            html.Span(f"   tipo: {a_type}   nodi: {nodes_txt}",
                      style={"color": "#e2ddd5"}),
        ])

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

    if is_anom:
        raw = snap.get("anomaly_node_ids") or "[]"
        try:
            anom_nodes = (_json.loads(raw) if isinstance(raw, str)
                          else (raw or []))
        except (ValueError, TypeError):
            anom_nodes = []
        _x_labels = [n.split("-")[-1] for n in _NODE_IDS]
        for anom_node in anom_nodes:
            anom_short = anom_node.split("-")[-1]
            if anom_short not in _x_labels:
                continue
            col_idx = _x_labels.index(anom_short)
            fig_node.add_shape(
                type="rect",
                x0=col_idx - 0.5, x1=col_idx + 0.5,
                y0=-0.5, y1=len(_NODE_METRICS) - 0.5,
                line={"color": "#b55e5e", "width": 2},
                fillcolor="rgba(181,94,94,0.08)",
                layer="above",
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
    return fig_node, fig_edge, snap_label


# ---------------------------------------------------------------------------
# Callback 5 - serie temporale
# ---------------------------------------------------------------------------
@callback(
    Output("s1-atg-ts-graph", "figure"),
    Input("s1-atg-metric-dd", "value"),
    Input("s1-atg-slider",    "value"),
)
def update_atg_ts(metric, slider_idx):
    dm    = DataManager()
    snaps = dm.get_snapshots()
    if not snaps or not metric:
        return _empty_fig("Serie temporale -- nessun dato")

    is_node = metric in _NODE_METRICS
    x_dt, y = [], []
    for snap in snaps:
        x_dt.append(pd.to_datetime(snap["timestamp"], unit="us"))
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
        x=x_dt, y=y, mode="lines",
        line={"color": "#c4a35a", "width": 1.2},
    ))
    for i, snap in enumerate(snaps):
        if snap["label"]:
            t0 = pd.to_datetime(snap["timestamp"],             unit="us")
            t1 = pd.to_datetime(snap["timestamp"] + 5_000_000, unit="us")
            fig.add_vrect(x0=t0, x1=t1,
                          fillcolor="#b55e5e", opacity=0.08, line_width=0)

    if slider_idx is not None and 0 <= int(slider_idx) < len(snaps):
        curr_ts = pd.to_datetime(snaps[int(slider_idx)]["timestamp"], unit="us")
        fig.add_vline(
            x=curr_ts.timestamp() * 1000,
            line_color="#c4a35a",
            line_width=1.5,
            line_dash="dot",
            annotation_text=f"snap {slider_idx}",
            annotation_font_color="#c4a35a",
            annotation_font_size=9,
        )

    fig.update_layout(
        title=f"{metric} — tutti gli snapshot (linea oro = posizione slider)",
        xaxis_title="data/ora (UTC)", yaxis_title=metric,
        **_DARK_LAYOUT,
    )
    return fig


# ---------------------------------------------------------------------------
# Callback 6 - pannello CS e tabella archi topologia
# ---------------------------------------------------------------------------
_CS_COLOR = {"H_crit": "#388bfd", "H_cache": "#3fb950"}
_SHARED_COLOR = "#8957e5"

_CS_STATIC = {
    "H_crit": {
        "topology_type": "linear - PAS applicabile",
        "critical_path": ("nginx-web-server -> nginx-thrift -> "
                          "home-timeline-service -> post-storage-service -> "
                          "post-storage-mongodb"),
        "arcs":    ["e1", "e2", "e4", "e6"],
        "m_interf": [],
        "sla":     {"latency_ms": "<= 100.0 ms", "error_rate": "< 0.05"},
    },
    "H_cache": {
        "topology_type": "parallel - Frobenius come fallback",
        "critical_path": "N/A (parallelo)",
        "arcs":    ["e3", "e4", "e5"],
        "m_interf": ["e2 (nginx-thrift -> home-timeline-service)"],
        "sla":     {"latency_ms": "<= 20.0 ms", "error_rate": "< 0.10"},
    },
}


def _kv(k, v):
    return html.Div([
        html.Span(k, style={"color": "var(--muted)", "minWidth": "110px",
                            "display": "inline-block"}),
        html.Span(v, style={"color": "var(--text)",
                            "fontFamily": "JetBrains Mono, monospace",
                            "fontSize": "11px"}),
    ], style={"padding": "4px 0", "borderBottom": "1px solid var(--border)",
              "display": "flex"})


def _build_cs_card(cs_name):
    cs    = _CS_STATIC[cs_name]
    info  = _CS_INFO[cs_name]
    color = _CS_COLOR[cs_name]

    node_spans = []
    for n in info["nodes"]:
        c = _SHARED_COLOR if n in _SHARED else color
        node_spans.append(html.Span(
            n.split("-")[-1],
            style={"color": c, "fontFamily": "JetBrains Mono, monospace",
                   "fontSize": "10px", "marginRight": "6px"},
        ))

    m_interf_txt = ("; ".join(cs["m_interf"]) if cs["m_interf"]
                    else "nessuno")

    sla_rows = [_kv(f"SLA {k}", v) for k, v in cs["sla"].items()]

    return html.Div(
        style={
            "backgroundColor": "var(--surface)",
            "border": f"1px solid {color}",
            "padding": "16px", "flex": "1", "fontSize": "12px",
        },
        children=[
            html.Div(cs_name, style={
                "color": color, "fontWeight": "600",
                "fontSize": "13px", "marginBottom": "10px",
            }),
            _kv("Tipo",          cs["topology_type"]),
            html.Div([
                html.Span("Nodi", style={"color": "var(--muted)",
                                         "minWidth": "110px",
                                         "display": "inline-block"}),
                html.Span(node_spans),
            ], style={"padding": "4px 0", "borderBottom": "1px solid var(--border)",
                      "display": "flex", "alignItems": "center"}),
            *sla_rows,
            _kv("Cammino critico", cs["critical_path"]),
            _kv(f"A(H_{cs_name.split('_')[1]})",
                f"{len(cs['arcs'])} archi: {', '.join(cs['arcs'])}"),
            _kv("M_interf",      m_interf_txt),
        ],
    )


def _build_edge_table():
    _TH = {"padding": "5px 10px", "color": "var(--muted)",
           "fontSize": "11px", "fontWeight": "600",
           "borderBottom": "1px solid var(--border)",
           "backgroundColor": "var(--surface)"}
    _TD = {"padding": "5px 10px", "fontSize": "11px",
           "borderBottom": "1px solid var(--border)"}

    header = html.Div([
        html.Span("ID",                  style={**_TH, "width": "40px"}),
        html.Span("Source",              style={**_TH, "flex": "1"}),
        html.Span("Target",              style={**_TH, "flex": "1"}),
        html.Span("H_crit",             style={**_TH, "width": "60px"}),
        html.Span("H_cache",            style={**_TH, "width": "60px"}),
        html.Span("M_interf(H_cache)", style={**_TH, "width": "110px"}),
    ], style={"display": "flex"})

    rows = []
    for eid, info in _EDGES.items():
        in_crit  = "H_crit"  in info["cs"]
        in_cache = "H_cache" in info["cs"]
        is_both  = in_crit and in_cache
        is_interf = info["interf"]
        row_color = (_SHARED_COLOR if is_both
                     else "#c4a35a" if is_interf
                     else "var(--text)")
        rows.append(html.Div([
            html.Span(eid,                     style={**_TD, "width": "40px",
                                                       "color": row_color,
                                                       "fontFamily": "JetBrains Mono"}),
            html.Span(info["source"].split("-")[-1], style={**_TD, "flex": "1"}),
            html.Span(info["target"].split("-")[-1], style={**_TD, "flex": "1"}),
            html.Span("v" if in_crit  else "-",  style={**_TD, "width": "60px",
                                                          "color": "#388bfd"}),
            html.Span("v" if in_cache else "-",  style={**_TD, "width": "60px",
                                                          "color": "#3fb950"}),
            html.Span("v" if is_interf else "-", style={**_TD, "width": "110px",
                                                          "color": "#c4a35a"}),
        ], style={"display": "flex",
                  "backgroundColor": "rgba(137,87,229,0.06)" if is_both
                                     else "rgba(196,163,90,0.06)" if is_interf
                                     else "transparent"}))

    return html.Div(
        [header] + rows,
        style={"border": "1px solid var(--border)",
               "backgroundColor": "var(--surface)"},
    )


@callback(
    Output("s1-cs-panel",   "children"),
    Output("s1-edge-table", "children"),
    Input("s1-tabs", "value"),
)
def populate_cs_info(tab):
    if tab != "topology":
        return [], []
    cs_cards = [_build_cs_card("H_crit"), _build_cs_card("H_cache")]
    return cs_cards, _build_edge_table()


# ---------------------------------------------------------------------------
# Callback 6b - inizializza slider PBO
# ---------------------------------------------------------------------------
@callback(
    Output("s1-pbo-slider",     "max"),
    Output("s1-pbo-slider",     "marks"),
    Output("s1-pbo-snap-label", "children"),
    Input("s1-tabs", "value"),
)
def init_pbo_slider(tab):
    if tab != "pbo":
        return 0, {}, ""
    dm = DataManager()
    ws = dm.get_weight_series()
    n  = len(ws) if ws else 0
    if n == 0:
        return 0, {0: "0"}, "Nessun dato"
    marks = {0: "0", n - 1: str(n - 1)}
    return n - 1, marks, f"{n} snapshot disponibili"


# ---------------------------------------------------------------------------
# Callback 7 - grafici PBO (rinumerato da 6)
# ---------------------------------------------------------------------------
_DSB_NOTE = html.Div(
    ("Nota DSB: il dataset DeathStarBench aggrega il throughput a livello di servizio. "
     "PAS_gold = 0.25 e calcolato sulla media delle repliche -- valori superiori "
     "indicano possibile saturazione del cache layer. "
     "La norma di Frobenius e usata come fallback per H_cache (topologia parallela)."),
    style={"fontSize": "11px", "color": "var(--muted)", "marginTop": "10px",
           "fontStyle": "italic", "borderLeft": "2px solid var(--border)",
           "paddingLeft": "8px"},
)


@callback(
    Output("s1-pbo-weight-heatmap", "figure"),
    Output("s1-pbo-pas-frob-chart", "figure"),
    Output("s1-pbo-edge-table", "children"),
    Output("s1-pbo-dsb-note", "children"),
    Input("s1-tabs", "value"),
    Input("s1-pbo-slider", "value"),
)
def update_pbo(tab, slider_val):
    if tab != "pbo":
        return go.Figure(), go.Figure(), [], []

    dm = DataManager()
    ws = dm.get_weight_series()
    wg = dm.get_gold_standard()

    if not ws or not wg:
        msg = html.Div("Pipeline non ancora eseguita.",
                       style={"color": "var(--muted)", "padding": "20px"})
        return _empty_fig("W_t vs W_gold"), _empty_fig("PAS / Frobenius"), msg, _DSB_NOTE

    w_idx  = min(int(slider_val or 0), len(ws) - 1)
    snap_w = ws[w_idx]["weights"]
    z      = [[snap_w.get(e, 0), wg.get(e, 0)] for e in _EDGE_IDS]
    fig_w  = go.Figure(go.Heatmap(
        z=z, x=["W_t", "W_gold"], y=_EDGE_IDS,
        colorscale=[[0, "#1c1c1c"], [1, "#c4a35a"]], showscale=True,
        zmin=0, zmax=1,
    ))
    fig_w.update_layout(title=f"W_t (snap {w_idx}) vs W_gold", **_DARK_LAYOUT)

    fig_pf  = _empty_fig("PAS / Frobenius -- esegui la pipeline")
    results = dm.load_pipeline_results()
    if results and "H_crit" in results.get("compliance_sets", {}):
        mon_crit = results["compliance_sets"]["H_crit"].get("monitor_results", [])
        if mon_crit:
            ts_list   = [m.get("timestamp") for m in mon_crit]
            pas_vals  = [m.get("pas_value") for m in mon_crit]
            frob_vals = [m.get("frobenius_distance") for m in mon_crit]
            snaps     = dm.get_snapshots()
            anom_ts   = {s["timestamp"] for s in snaps if s["label"] == 1}
            fig_pf = go.Figure()
            fig_pf.add_trace(go.Scatter(
                x=ts_list, y=pas_vals, name="PAS (H_crit)",
                line={"color": "#c4a35a", "width": 1.5}, yaxis="y1",
            ))
            fig_pf.add_trace(go.Scatter(
                x=ts_list, y=frob_vals, name="Frobenius",
                line={"color": "#b55e5e", "width": 1.5}, yaxis="y2",
            ))
            for ts in ts_list:
                if ts in anom_ts:
                    fig_pf.add_vrect(
                        x0=ts, x1=ts + 5_000_000,
                        fillcolor="#b55e5e", opacity=0.06,
                        line_width=0, layer="below",
                    )
            fig_pf.add_hline(
                y=0.25,
                line_dash="dash",
                line_color="#5a5a5a",
                annotation_text="PAS_gold = 0.25",
                annotation_font_color="#5a5a5a",
                annotation_font_size=10,
            )
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

    return fig_w, fig_pf, html.Div([header] + rows), _DSB_NOTE


# ---------------------------------------------------------------------------
# Clientside callback - reset viewport Cytoscape S1
# ---------------------------------------------------------------------------
clientside_callback(
    """
    function(n_clicks) {
        if (n_clicks > 0) {
            var cy = document.getElementById('s1-cytoscape');
            if (cy && cy._cy) { cy._cy.fit(); cy._cy.center(); }
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output("s1-cytoscape", "zoom"),
    Input("s1-cyto-reset", "n_clicks"),
    prevent_initial_call=True,
)
