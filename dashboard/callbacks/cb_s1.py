import pandas as pd
import plotly.graph_objects as go
from dash import callback, clientside_callback, Output, Input, html, ctx, Patch
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
    {"data": {"id": "nginx-web-server",     "label": "nginx-web-server",     "parent": "H_crit_group",
              "title": "nginx-web-server\nCS: H_crit\nMetriche: cpu, mem, net_rx, net_tx"}},
    {"data": {"id": "nginx-thrift",         "label": "nginx-thrift",         "parent": "H_crit_group",
              "title": "nginx-thrift\nCS: H_crit\nMetriche: cpu, mem, net_rx, net_tx\nM_interf: arco e2 verso home-timeline-service"}},
    {"data": {"id": "post-storage-mongodb", "label": "post-storage-mongodb", "parent": "H_crit_group",
              "title": "post-storage-mongodb\nCS: H_crit\nMetriche: cpu, mem, net_rx, net_tx"}},
    {"data": {"id": "home-timeline-redis",    "label": "home-timeline-redis",    "parent": "H_cache_group",
              "title": "home-timeline-redis\nCS: H_cache\nMetriche: cpu, mem, net_rx, net_tx"}},
    {"data": {"id": "post-storage-memcached", "label": "post-storage-memcached", "parent": "H_cache_group",
              "title": "post-storage-memcached\nCS: H_cache\nMetriche: cpu, mem, net_rx, net_tx"}},
    {"data": {"id": "home-timeline-service", "label": "home-timeline-service",
              "title": "home-timeline-service\nCS: H_crit + H_cache (condiviso)\nPunto di interferenza strutturale\nMetriche: cpu, mem, net_rx, net_tx"}, "classes": "shared"},
    {"data": {"id": "post-storage-service",  "label": "post-storage-service",
              "title": "post-storage-service\nCS: H_crit + H_cache (condiviso)\nPunto di interferenza strutturale\nMetriche: cpu, mem, net_rx, net_tx"},  "classes": "shared"},
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
        "text-tooltip": "data(title)",
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

_EDGE_SLA = {
    "latency_ms": 100.0,
    "error_rate": 0.05,
}


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
    t_start = pd.to_datetime(snaps[0]["timestamp"],    unit="us").strftime("%d/%m/%y")
    t_mid   = pd.to_datetime(snaps[n // 2]["timestamp"], unit="us").strftime("%d/%m/%y")
    t_end   = pd.to_datetime(snaps[-1]["timestamp"],   unit="us").strftime("%d/%m/%y")
    marks = {
        0:      {"label": f"0 ({t_start})",     "style": {"fontSize": "9px", "color": "var(--muted)"}},
        n // 2: {"label": f"{n//2} ({t_mid})",  "style": {"fontSize": "9px", "color": "var(--muted)"}},
        n - 1:  {"label": f"{n-1} ({t_end})",   "style": {"fontSize": "9px", "color": "var(--muted)"}},
    }
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
    is_anom = bool(snap["label"])
    label   = "ANOMALO" if is_anom else "nominale"
    dt_snap = pd.to_datetime(snap["timestamp"], unit="us")
    dt_str  = dt_snap.strftime("%Y-%m-%d %H:%M:%S")

    if not is_anom:
        snap_label = html.Span(
            f"Snapshot {idx}  {dt_str}  nominale",
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
            html.Span(f"Snapshot {idx}  {dt_str}  ",
                      style={"color": "var(--muted)"}),
            html.Span("ANOMALO", style={"color": "#b55e5e", "fontWeight": "600"}),
            html.Span(f"  tipo: {a_type}   nodi: {nodes_txt}",
                      style={"color": "#e2ddd5"}),
        ])

    z_node   = [[snap["nodes"].get(n, {}).get(m) for n in _NODE_IDS]
                for m in _NODE_METRICS]
    z_text_n = [[f"{v:.2g}" if v is not None else "N/A" for v in row]
                for row in z_node]
    cs_n     = [[0, "#1c1c1c"], [1, "#b55e5e"]] if is_anom \
               else [[0, "#1c1c1c"], [1, "#c4a35a"]]
    fig_node = go.Figure(go.Heatmap(
        z=z_node, x=[n.split("-")[-1] for n in _NODE_IDS], y=_NODE_METRICS,
        colorscale=cs_n, showscale=True,
        text=z_text_n, texttemplate="%{text}", textfont={"size": 9},
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

    z_edge   = [[snap["edges"].get(e, {}).get(m) for e in _EDGE_IDS]
                for m in _EDGE_METRICS]
    z_text_e = [[f"{v:.2g}" if v is not None else "N/A" for v in row]
                for row in z_edge]
    cs_e     = [[0, "#1c1c1c"], [1, "#b55e5e"]] if is_anom \
               else [[0, "#1c1c1c"], [1, "#388bfd"]]
    fig_edge = go.Figure(go.Heatmap(
        z=z_edge, x=_EDGE_IDS, y=_EDGE_METRICS,
        colorscale=cs_e, showscale=True,
        text=z_text_e, texttemplate="%{text}", textfont={"size": 9},
    ))
    fig_edge.update_layout(
        title=f"Archi -- snap {idx} ({label})", **_DARK_LAYOUT,
        yaxis={"tickfont": {"size": 9}}, xaxis={"tickfont": {"size": 9}},
    )
    for row_idx, metric in enumerate(_EDGE_METRICS):
        sla_val = _EDGE_SLA.get(metric)
        if sla_val is None:
            continue
        for col_idx, eid in enumerate(_EDGE_IDS):
            val = snap["edges"].get(eid, {}).get(metric)
            if val is not None and float(val) > sla_val:
                fig_edge.add_shape(
                    type="rect",
                    x0=col_idx - 0.5, x1=col_idx + 0.5,
                    y0=row_idx - 0.5, y1=row_idx + 0.5,
                    line={"color": "#b55e5e", "width": 2},
                    fillcolor="rgba(0,0,0,0)",
                    layer="above",
                )
    return fig_node, fig_edge, snap_label


# ---------------------------------------------------------------------------
# Callback 5 - serie temporale
# ---------------------------------------------------------------------------
def _build_ts_shapes(snaps: list) -> tuple[list, list]:
    """Return (x_dt_sub, anomaly_bands) for the subsampled snapshot list."""
    _MAX_PTS = 1500
    x_dt_all = [pd.to_datetime(s["timestamp"], unit="us") for s in snaps]
    if len(x_dt_all) > _MAX_PTS:
        step     = len(x_dt_all) // _MAX_PTS
        x_dt_sub = x_dt_all[::step]
        snaps_sub = snaps[::step]
    else:
        x_dt_sub  = x_dt_all
        snaps_sub = snaps

    bands, in_band, band_start = [], False, None
    for i, snap in enumerate(snaps_sub):
        if snap["label"] and not in_band:
            band_start = x_dt_sub[i]
            in_band = True
        elif not snap["label"] and in_band:
            bands.append((band_start, x_dt_sub[i - 1]))
            in_band = False
    if in_band and band_start is not None:
        bands.append((band_start, x_dt_sub[-1]))
    return x_dt_sub, bands


def _vline_shape(x_iso: str) -> dict:
    return {
        "type": "line", "x0": x_iso, "x1": x_iso,
        "y0": 0, "y1": 1, "xref": "x", "yref": "paper",
        "line": {"color": "#c4a35a", "width": 1.5, "dash": "dot"},
    }


def _vline_annotation(x_iso: str, label: str) -> dict:
    return {
        "x": x_iso, "y": 1, "xref": "x", "yref": "paper",
        "text": label, "showarrow": False,
        "font": {"color": "#c4a35a", "size": 9}, "yshift": 5,
    }


@callback(
    Output("s1-atg-ts-graph", "figure"),
    Input("s1-atg-metric-dd",   "value"),
    Input("s1-atg-slider",      "value"),
    Input("s1-atg-entity-type", "value"),
    Input("s1-atg-entity-dd",   "value"),
)
def update_atg_ts(metric, slider_idx, entity_type, entity_id):
    dm    = DataManager()
    snaps = dm.get_snapshots()

    # ── Slider-only trigger: rebuild only shapes/annotations via Patch ──────
    # Avoids recomputing the full series (up to 41k snapshots).
    if ctx.triggered_id == "s1-atg-slider" and snaps:
        if slider_idx is None or not (0 <= int(slider_idx) < len(snaps)):
            return Patch()

        _, bands = _build_ts_shapes(snaps)
        curr_ts  = pd.to_datetime(snaps[int(slider_idx)]["timestamp"], unit="us")
        x_iso    = curr_ts.isoformat()

        shapes = [
            {
                "type": "rect", "xref": "x", "yref": "paper",
                "x0": t0.isoformat(), "x1": t1.isoformat(),
                "y0": 0, "y1": 1,
                "fillcolor": "#b55e5e", "opacity": 0.08,
                "line": {"width": 0}, "layer": "below",
            }
            for t0, t1 in bands
        ] + [_vline_shape(x_iso)]

        patched = Patch()
        patched["layout"]["shapes"]      = shapes
        patched["layout"]["annotations"] = [_vline_annotation(x_iso, f"snap {slider_idx}")]
        return patched

    # ── Full render: metric/entity changed or initial call ───────────────────
    if not snaps or not metric:
        return _empty_fig("Serie temporale -- nessun dato")

    if entity_type == "node" and entity_id:
        x_dt, y = [], []
        for snap in snaps:
            x_dt.append(pd.to_datetime(snap["timestamp"], unit="us"))
            val = snap["nodes"].get(entity_id, {}).get(metric)
            y.append(float(val) if val is not None else None)
    elif entity_type == "edge" and entity_id:
        x_dt, y = [], []
        for snap in snaps:
            x_dt.append(pd.to_datetime(snap["timestamp"], unit="us"))
            val = snap["edges"].get(entity_id, {}).get(metric)
            y.append(float(val) if val is not None else None)
    else:
        # entity_type == "all": average over all elements
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

    _MAX_PTS = 1500
    if len(x_dt) > _MAX_PTS:
        step       = len(x_dt) // _MAX_PTS
        x_dt       = x_dt[::step]
        y          = y[::step]
        snaps_sub  = snaps[::step]
        subsampled = True
    else:
        snaps_sub  = snaps
        subsampled = False

    bands = []
    in_band, band_start = False, None
    for i, snap in enumerate(snaps_sub):
        if snap["label"] and not in_band:
            band_start = x_dt[i]
            in_band = True
        elif not snap["label"] and in_band:
            bands.append((band_start, x_dt[i - 1]))
            in_band = False
    if in_band and band_start is not None:
        bands.append((band_start, x_dt[-1]))

    fig = go.Figure(go.Scatter(
        x=x_dt, y=y, mode="lines",
        line={"color": "#c4a35a", "width": 1.2},
    ))
    for t0, t1 in bands:
        fig.add_vrect(x0=t0, x1=t1, fillcolor="#b55e5e", opacity=0.08, line_width=0)

    # Vline — always added last so Patch can target shapes[-1] / annotations[0]
    if slider_idx is not None and 0 <= int(slider_idx) < len(snaps):
        curr_ts      = pd.to_datetime(snaps[int(slider_idx)]["timestamp"], unit="us")
        x_iso        = curr_ts.isoformat()
        vline_opacity = 1.0
        anno_text    = f"snap {slider_idx}"
    else:
        x_iso        = x_dt[0].isoformat() if x_dt else "1970-01-01"
        vline_opacity = 0.0
        anno_text    = ""

    fig.add_shape(**{**_vline_shape(x_iso), "opacity": vline_opacity})
    fig.update_layout(annotations=[{**_vline_annotation(x_iso, anno_text),
                                    "opacity": vline_opacity}])

    title_suffix = f" (campione 1/{step})" if subsampled else ""
    if entity_type in ("node", "edge") and entity_id:
        title_base = f"{entity_id} : {metric}"
    else:
        title_base = f"{metric} (media su tutti gli elementi)"
    fig.update_layout(
        title=f"{title_base}{title_suffix}",
        xaxis_title="data/ora (UTC)", yaxis_title=metric,
        **_DARK_LAYOUT,
    )
    return fig


# ---------------------------------------------------------------------------
# Callback 5b - mostra/nasconde e popola il dropdown elemento
# ---------------------------------------------------------------------------
@callback(
    Output("s1-atg-entity-dd-wrap", "style"),
    Output("s1-atg-entity-dd",      "options"),
    Output("s1-atg-entity-dd",      "value"),
    Input("s1-atg-entity-type",     "value"),
)
def update_entity_dd(entity_type):
    if entity_type == "node":
        opts = [{"label": nid, "value": nid} for nid in _NODE_IDS]
        return {"display": "block"}, opts, _NODE_IDS[0]
    if entity_type == "edge":
        opts = [{"label": eid, "value": eid} for eid in _EDGE_IDS]
        return {"display": "block"}, opts, _EDGE_IDS[0]
    return {"display": "none"}, [], None


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


_NODE_POS = {
    "nginx-web-server":       (0.0, 0.5),
    "nginx-thrift":           (0.2, 0.5),
    "home-timeline-service":  (0.4, 0.5),
    "home-timeline-redis":    (0.6, 0.8),
    "post-storage-service":   (0.6, 0.2),
    "post-storage-memcached": (0.8, 0.4),
    "post-storage-mongodb":   (0.8, 0.0),
}
_EDGE_ENDPOINTS = {
    "e1": ("nginx-web-server",       "nginx-thrift"),
    "e2": ("nginx-thrift",            "home-timeline-service"),
    "e3": ("home-timeline-service",   "home-timeline-redis"),
    "e4": ("home-timeline-service",   "post-storage-service"),
    "e5": ("post-storage-service",    "post-storage-memcached"),
    "e6": ("post-storage-service",    "post-storage-mongodb"),
}


@callback(
    Output("s1-pbo-wgold-fig",      "figure"),
    Output("s1-pbo-weight-heatmap", "figure"),
    Output("s1-pbo-pas-frob-chart", "figure"),
    Output("s1-pbo-edge-table",     "children"),
    Output("s1-pbo-dsb-note",       "children"),
    Input("s1-tabs", "value"),
    Input("s1-pbo-slider", "value"),
)
def update_pbo(tab, slider_val):
    if tab != "pbo":
        return go.Figure(), go.Figure(), go.Figure(), [], []

    dm = DataManager()
    ws = dm.get_weight_series()
    wg = dm.get_gold_standard()

    if not ws or not wg:
        msg = html.Div("Pipeline non ancora eseguita.",
                       style={"color": "var(--muted)", "padding": "20px"})
        return (go.Figure(), _empty_fig("W_t vs W_gold"),
                _empty_fig("PAS / Frobenius"), msg, _DSB_NOTE)

    # ── Grafo W_gold ──────────────────────────────────────────────────────────
    fig_wg = go.Figure()
    for eid, (src, tgt) in _EDGE_ENDPOINTS.items():
        x0, y0 = _NODE_POS[src]
        x1, y1 = _NODE_POS[tgt]
        w     = wg.get(eid, 0.0)
        width = max(1.0, w * 12)
        fig_wg.add_trace(go.Scatter(
            x=[x0, x1], y=[y0, y1],
            mode="lines",
            line={"color": "#c4a35a", "width": width},
            hovertemplate=f"{eid}: w_gold={w:.4f}<extra></extra>",
            showlegend=False,
        ))
        fig_wg.add_annotation(
            x=(x0 + x1) / 2, y=(y0 + y1) / 2,
            text=f"w={w:.3f}", showarrow=False,
            font={"size": 9, "color": "#e2ddd5"},
            bgcolor="rgba(28,28,28,0.8)",
        )
    for eid, (src, tgt) in _EDGE_ENDPOINTS.items():
        x0, y0 = _NODE_POS[src]
        x1, y1 = _NODE_POS[tgt]
        w = wg.get(eid, 0.0)
        ax    = x0 + (x1 - x0) * 0.3
        ay    = y0 + (y1 - y0) * 0.3
        x_arr = x0 + (x1 - x0) * 0.7
        y_arr = y0 + (y1 - y0) * 0.7
        fig_wg.add_annotation(
            x=x_arr, y=y_arr, ax=ax, ay=ay,
            xref="x", yref="y", axref="x", ayref="y",
            arrowhead=2, arrowwidth=max(1, int(w * 4)),
            arrowcolor="#c4a35a",
            showarrow=True, text="",
        )
    for nid, (x, y) in _NODE_POS.items():
        node_color = "#8957e5" if nid in _SHARED else "#e2ddd5"
        fig_wg.add_trace(go.Scatter(
            x=[x], y=[y], mode="markers+text",
            marker={"size": 16, "color": "#1c1c1c",
                    "line": {"color": node_color, "width": 2}},
            text=[nid.split("-")[-1]],
            textposition="top center",
            textfont={"size": 9, "color": "#e2ddd5"},
            showlegend=False,
            hovertemplate=f"<b>{nid}</b><extra></extra>",
        ))
    fig_wg.update_layout(
        xaxis={"visible": False, "range": [-0.05, 0.95]},
        yaxis={"visible": False, "range": [-0.1, 1.0]},
        height=280, margin={"l": 10, "r": 10, "t": 10, "b": 10},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )

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
            ts_dt     = [pd.to_datetime(ts, unit="us") if ts is not None else None
                         for ts in ts_list]
            fig_pf = go.Figure()
            fig_pf.add_trace(go.Scatter(
                x=ts_dt, y=pas_vals, name="PAS (H_crit)",
                line={"color": "#c4a35a", "width": 1.5}, yaxis="y1",
            ))
            fig_pf.add_trace(go.Scatter(
                x=ts_dt, y=frob_vals, name="Frobenius",
                line={"color": "#b55e5e", "width": 1.5}, yaxis="y2",
            ))
            _anom_ts_list = [ts for ts in ts_list if ts in anom_ts][:200]
            for ts in _anom_ts_list:
                t0 = pd.to_datetime(ts, unit="us")
                t1 = pd.to_datetime(ts + 5_000_000, unit="us")
                fig_pf.add_vrect(
                    x0=t0, x1=t1,
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
                xaxis_title="data/ora (UTC)",
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

    return fig_wg, fig_w, fig_pf, html.Div([header] + rows), _DSB_NOTE


# ---------------------------------------------------------------------------
# Clientside callback - reset viewport Cytoscape S1
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
        var wrapper = document.getElementById('s1-cytoscape');
        var cy = findCy(wrapper);
        if (cy) { cy.fit(); cy.center(); }
        return window.dash_clientside.no_update;
    }
    """,
    Output("s1-cytoscape", "zoom"),
    Input("s1-cyto-reset", "n_clicks"),
    prevent_initial_call=True,
)
