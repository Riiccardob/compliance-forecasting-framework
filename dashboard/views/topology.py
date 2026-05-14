"""View Topologia — Layer 1 (ipergrafo), Layer 2 (ATG), PBO."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import networkx as nx
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dashboard.state import AppState
from dashboard.style import PALETTE

_CONFIG_TOPOLOGY = _ROOT / "config" / "topology.yaml"
_CONFIG_PIPELINE = _ROOT / "config" / "pipeline_params.yaml"

_SHARED_COLOR = "#8957E5"
_INTERF_COLOR = PALETTE["orange"]


# ── Layout grafo ──────────────────────────────────────────────────────────

def _get_graph_layout(state: AppState, G: nx.DiGraph) -> dict[str, tuple[float, float]]:
    if state.graph_layout is not None:
        return state.graph_layout

    raw = nx.spring_layout(G, seed=42, k=2.5, iterations=100)
    xs = [v[0] for v in raw.values()]
    ys = [v[1] for v in raw.values()]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    x_range = x_max - x_min or 1.0
    y_range = y_max - y_min or 1.0
    layout = {
        node: (
            0.05 + 0.90 * (raw[node][0] - x_min) / x_range,
            0.05 + 0.90 * (raw[node][1] - y_min) / y_range,
        )
        for node in raw
    }
    state.graph_layout = layout
    return layout


def _node_color(node: str, h_crit_nodes: set, h_cache_nodes: set) -> str:
    in_crit = node in h_crit_nodes
    in_cache = node in h_cache_nodes
    if in_crit and in_cache:
        return _SHARED_COLOR
    if in_crit:
        return PALETTE["h_crit"]
    if in_cache:
        return PALETTE["h_cache"]
    return PALETTE["text_secondary"]


def _edge_color(hyperedges: list[str], is_interf_cache: bool) -> tuple[str, str]:
    in_crit = "H_crit" in hyperedges
    in_cache = "H_cache" in hyperedges
    if in_crit and in_cache:
        return _SHARED_COLOR, "dash"
    if is_interf_cache:
        return _INTERF_COLOR, "dot"
    if in_crit:
        return PALETTE["h_crit"], "solid"
    if in_cache:
        return PALETTE["h_cache"], "solid"
    return PALETTE["text_secondary"], "solid"


# ── Grafo Plotly ──────────────────────────────────────────────────────────

def _topology_plotly(
    G: nx.DiGraph,
    pos: dict[str, tuple[float, float]],
    h_crit_nodes: set,
    h_cache_nodes: set,
    shared_nodes: set,
    a_crit_edges: set,
    a_cache_edges: set,
    interf_cache: set,
    topo: dict,
) -> go.Figure:
    fig = go.Figure()

    edge_id_map: dict[tuple[str, str], str] = {
        (e["source"], e["target"]): e["id"]
        for e in topo["edges"]
    }

    for u, v, data in G.edges(data=True):
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        hyperedges: list[str] = data.get("hyperedges", [])
        edge_id = data.get("id", edge_id_map.get((u, v), "?"))
        is_interf = (u, v) in interf_cache

        color, dash = _edge_color(hyperedges, is_interf)

        membership_parts = []
        if "H_crit" in hyperedges:
            membership_parts.append("H_crit")
        if "H_cache" in hyperedges:
            membership_parts.append("H_cache")
        membership = " · ".join(membership_parts) if membership_parts else "—"

        interf_note = ""
        if is_interf:
            interf_note = "<br><i>Arco di interferenza: porta carico esterno su nodo condiviso</i>"

        hover = (
            f"<b>{edge_id}</b>: {u} → {v}<br>"
            f"Compliance sets: {membership}"
            f"{interf_note}"
        )

        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        dx, dy = x1 - x0, y1 - y0
        length = math.sqrt(dx ** 2 + dy ** 2) or 1.0
        offset = 0.04
        x_tip = x1 - offset * dx / length
        y_tip = y1 - offset * dy / length

        line_width = 3 if is_interf else 2
        fig.add_annotation(
            x=x_tip, y=y_tip, ax=x0, ay=y0,
            xref="x", yref="y", axref="x", ayref="y",
            arrowhead=2, arrowwidth=line_width, arrowcolor=color,
            showarrow=True, text="",
        )
        fig.add_annotation(
            x=mx, y=my, xref="x", yref="y",
            text=f"<b style='font-size:9px'>{edge_id}</b>",
            showarrow=False, font=dict(size=9, color=color),
            bgcolor=PALETTE["background"], borderpad=1,
        )
        fig.add_trace(go.Scatter(
            x=[mx], y=[my], mode="markers",
            marker=dict(size=20, opacity=0),
            showlegend=False,
            hovertemplate=hover + "<extra></extra>",
            name=edge_id,
        ))

    node_metrics: list[str] = topo.get("node_metrics", [])
    for node in G.nodes():
        x, y = pos[node]
        color = _node_color(node, h_crit_nodes, h_cache_nodes)
        is_shared = node in shared_nodes
        size = 22 if is_shared else 16

        cs_list = []
        if node in h_crit_nodes:
            cs_list.append("H_crit")
        if node in h_cache_nodes:
            cs_list.append("H_cache")
        cs_str = " · ".join(cs_list) if cs_list else "—"

        shared_note = ""
        if is_shared:
            shared_note = "<br><b>Nodo condiviso — punto di interferenza cross-property</b>"

        hover = (
            f"<b>{node}</b><br>"
            f"Compliance sets: {cs_str}<br>"
            f"Metriche: {', '.join(node_metrics)}"
            f"{shared_note}"
        )

        fig.add_trace(go.Scatter(
            x=[x], y=[y], mode="markers+text",
            marker=dict(size=size, color=color,
                        line=dict(color=PALETTE["border"], width=1.5),
                        symbol="circle"),
            text=[node.replace("-", "-<br>")],
            textposition="top center",
            textfont=dict(size=9, color=PALETTE["text_primary"]),
            showlegend=False,
            hovertemplate=hover + "<extra></extra>",
            name=node,
        ))

    legend_items = [
        ("H_crit only", PALETTE["h_crit"], "circle"),
        ("H_cache only", PALETTE["h_cache"], "circle"),
        ("Shared (H_crit ∩ H_cache)", _SHARED_COLOR, "circle"),
        ("A(H_crit)", PALETTE["h_crit"], "line-ew"),
        ("A(H_cache)", PALETTE["h_cache"], "line-ew"),
        ("Arco condiviso e4", _SHARED_COLOR, "line-ew-open"),
        ("M_interf (interferenza)", _INTERF_COLOR, "line-ew"),
    ]
    for label, color, symbol in legend_items:
        fig.add_trace(go.Scatter(
            x=[None], y=[None], mode="markers",
            marker=dict(size=10, color=color, symbol=symbol),
            name=label, showlegend=True,
        ))

    fig.update_layout(
        paper_bgcolor=PALETTE["background"], plot_bgcolor=PALETTE["surface"],
        font=dict(color=PALETTE["text_primary"]),
        height=500, margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(visible=False, range=[-0.05, 1.05], showgrid=False, zeroline=False),
        yaxis=dict(visible=False, range=[-0.05, 1.05], showgrid=False, zeroline=False),
        legend=dict(font=dict(color=PALETTE["text_secondary"], size=11),
                    bgcolor=PALETTE["surface_alt"], bordercolor=PALETTE["border"],
                    x=1.01, y=0.99, xanchor="left"),
        hoverlabel=dict(bgcolor=PALETTE["surface_alt"], bordercolor=PALETTE["border"],
                        font=dict(color=PALETTE["text_primary"])),
    )
    return fig


# ── Pannello compliance sets ──────────────────────────────────────────────

def _cs_panel(topo: dict, tb) -> None:
    col_l, col_r = st.columns(2)
    cs_data = topo["compliance_sets"]

    def _render_cs(col, cs_name: str, color: str):
        cs = cs_data[cs_name]
        ttype = cs.get("topology_type", "—")
        nodes_list: list[str] = cs.get("nodes", [])
        sla: dict = cs.get("sla", {})

        with col:
            badge_cls = "blue" if cs_name == "H_crit" else "green"
            st.markdown(
                f'<div class="badge badge-{badge_cls}" '
                f'style="font-size:1rem;padding:0.3em 0.8em;margin-bottom:0.5rem;">'
                f'{cs_name}</div> '
                f'<span style="font-size:0.8rem;color:{PALETTE["text_secondary"]};">'
                f'topology_type: <b>{ttype}</b></span>',
                unsafe_allow_html=True,
            )

            st.markdown(
                f'<div style="font-size:0.75rem;color:{PALETTE["text_secondary"]};'
                f'margin-top:0.6rem;margin-bottom:0.3rem;">Nodi</div>',
                unsafe_allow_html=True,
            )
            chips = " ".join(f'<span class="node-chip">{n}</span>' for n in nodes_list)
            st.markdown(chips, unsafe_allow_html=True)

            try:
                edges = tb.get_edges_for_compliance_set(cs_name)
                edge_lookup = {(e["source"], e["target"]): e["id"] for e in topo["edges"]}
                st.markdown(
                    f'<div style="font-size:0.75rem;color:{PALETTE["text_secondary"]};'
                    f'margin-top:0.6rem;margin-bottom:0.3rem;">A({cs_name}) — archi interni</div>',
                    unsafe_allow_html=True,
                )
                for u, v in edges:
                    eid = edge_lookup.get((u, v), "?")
                    st.markdown(
                        f'<span class="node-chip" style="color:{color};">'
                        f'{eid}: {u} → {v}</span>',
                        unsafe_allow_html=True,
                    )
            except Exception as exc:
                st.error(f"A({cs_name}): {exc}")

            other = "H_cache" if cs_name == "H_crit" else "H_crit"
            try:
                shared = tb.get_shared_nodes(cs_name, other)
                if shared:
                    st.markdown(
                        f'<div style="font-size:0.75rem;color:{PALETTE["text_secondary"]};'
                        f'margin-top:0.6rem;margin-bottom:0.3rem;">'
                        f'Shared({cs_name}, {other})</div>',
                        unsafe_allow_html=True,
                    )
                    for n in sorted(shared):
                        st.markdown(
                            f'<span class="node-chip" style="color:{_SHARED_COLOR};">{n}</span>',
                            unsafe_allow_html=True,
                        )
            except Exception:
                pass

            try:
                interf = tb.get_interference_edges(cs_name, other)
                if interf:
                    eid_lkp = {(e["source"], e["target"]): e["id"] for e in topo["edges"]}
                    st.markdown(
                        f'<div style="font-size:0.75rem;color:{_INTERF_COLOR};'
                        f'margin-top:0.6rem;margin-bottom:0.3rem;">'
                        f'M_interf({cs_name}) — archi di interferenza</div>',
                        unsafe_allow_html=True,
                    )
                    for u, v in interf:
                        eid = eid_lkp.get((u, v), "?")
                        st.markdown(
                            f'<span class="node-chip" style="color:{_INTERF_COLOR};">'
                            f'{eid}: {u} → {v}</span>',
                            unsafe_allow_html=True,
                        )
                else:
                    st.markdown(
                        f'<div style="font-size:0.78rem;color:{PALETTE["text_secondary"]};'
                        f'margin-top:0.6rem;">M_interf({cs_name}) = ∅</div>',
                        unsafe_allow_html=True,
                    )
            except Exception:
                pass

            if sla:
                st.markdown(
                    f'<div style="font-size:0.75rem;color:{PALETTE["text_secondary"]};'
                    f'margin-top:0.6rem;margin-bottom:0.3rem;">SLA</div>',
                    unsafe_allow_html=True,
                )
                rows = ""
                for metric, spec in sla.items():
                    rows += (
                        f'<tr>'
                        f'<td style="padding:0.2rem 0.5rem;font-family:monospace;'
                        f'font-size:0.8rem;">{metric}</td>'
                        f'<td style="padding:0.2rem 0.5rem;font-size:0.8rem;">'
                        f'{spec.get("bound","")}</td>'
                        f'<td style="padding:0.2rem 0.5rem;font-size:0.8rem;'
                        f'color:{color};font-weight:600;">{spec.get("threshold","")}</td>'
                        f'</tr>'
                    )
                st.markdown(
                    f'<table style="border-collapse:collapse;width:100%;'
                    f'background:{PALETTE["surface_alt"]};border-radius:6px;">'
                    f'<thead><tr>'
                    f'<th style="padding:0.25rem 0.5rem;text-align:left;font-size:0.72rem;'
                    f'color:{PALETTE["text_secondary"]};">Metrica</th>'
                    f'<th style="padding:0.25rem 0.5rem;text-align:left;font-size:0.72rem;'
                    f'color:{PALETTE["text_secondary"]};">Bound</th>'
                    f'<th style="padding:0.25rem 0.5rem;text-align:left;font-size:0.72rem;'
                    f'color:{PALETTE["text_secondary"]};">Threshold</th>'
                    f'</tr></thead><tbody>{rows}</tbody></table>',
                    unsafe_allow_html=True,
                )

    _render_cs(col_l, "H_crit", PALETTE["h_crit"])
    _render_cs(col_r, "H_cache", PALETTE["h_cache"])


# ── Tabella archi ─────────────────────────────────────────────────────────

def _edge_table(topo: dict, tb) -> None:
    try:
        a_crit = set(tb.get_edges_for_compliance_set("H_crit"))
        a_cache = set(tb.get_edges_for_compliance_set("H_cache"))
        interf_crit = set(tb.get_interference_edges("H_crit", "H_cache"))
        interf_cache = set(tb.get_interference_edges("H_cache", "H_crit"))
    except Exception as exc:
        st.error(f"Errore tabella archi: {exc}")
        return

    rows = []
    for e in topo["edges"]:
        uv = (e["source"], e["target"])
        rows.append({
            "edge_id": e["id"],
            "source": e["source"],
            "target": e["target"],
            "H_crit": "si" if uv in a_crit else "—",
            "H_cache": "si" if uv in a_cache else "—",
            "M_interf(H_crit)": "si" if uv in interf_crit else "—",
            "M_interf(H_cache)": "si" if uv in interf_cache else "—",
        })

    df = pd.DataFrame(rows)

    def _highlight(row):
        in_both = row["H_crit"] == "si" and row["H_cache"] == "si"
        is_interf = row["M_interf(H_cache)"] == "si"
        if in_both:
            return [f"color:{_SHARED_COLOR};font-weight:600"] * len(row)
        if is_interf:
            return [f"color:{_INTERF_COLOR}"] * len(row)
        return [""] * len(row)

    styled = df.style.apply(_highlight, axis=1)
    st.dataframe(styled, use_container_width=True, hide_index=True)


# ── Tab 2: ATG nel tempo ──────────────────────────────────────────────────

def _snapshot_heatmap(
    snapshot: dict,
    node_ids: list[str],
    metrics: list[str],
    label: int,
    title: str,
    metric_suffix: str = "node",
) -> go.Figure:
    entity_key = "nodes" if metric_suffix == "node" else "edges"
    entities = snapshot.get(entity_key, {})

    z_raw: list[list[float]] = []
    z_text: list[list[str]] = []

    for eid in node_ids:
        row_raw: list[float] = []
        row_text: list[str] = []
        feat = entities.get(eid, {})
        for m in metrics:
            val = feat.get(m, float("nan"))
            try:
                row_raw.append(float(val))
                row_text.append(f"{float(val):.3g}")
            except (TypeError, ValueError):
                row_raw.append(float("nan"))
                row_text.append("NaN")
        z_raw.append(row_raw)
        z_text.append(row_text)

    z_norm: list[list[float]] = [row[:] for row in z_raw]
    n_metrics = len(metrics)
    for col_idx in range(n_metrics):
        col_vals = [
            z_raw[row_idx][col_idx]
            for row_idx in range(len(node_ids))
            if not math.isnan(z_raw[row_idx][col_idx])
        ]
        if col_vals:
            mn, mx = min(col_vals), max(col_vals)
            rng = mx - mn if mx != mn else 1.0
            for row_idx in range(len(node_ids)):
                v = z_raw[row_idx][col_idx]
                if not math.isnan(v):
                    z_norm[row_idx][col_idx] = (v - mn) / rng

    colorscale = "Reds" if label == 1 else "Viridis"
    fig = go.Figure(go.Heatmap(
        z=z_norm, x=metrics, y=node_ids,
        colorscale=colorscale,
        text=z_text, texttemplate="%{text}",
        textfont=dict(size=10),
        hovertemplate="%{y} — %{x}<br>Valore: %{text}<extra></extra>",
        showscale=False,
    ))
    fig.update_layout(
        title=dict(text=title, font=dict(color=PALETTE["text_primary"], size=13)),
        paper_bgcolor=PALETTE["surface"], plot_bgcolor=PALETTE["surface"],
        font=dict(color=PALETTE["text_secondary"]),
        margin=dict(l=10, r=10, t=45, b=10), height=280,
        xaxis=dict(color=PALETTE["text_secondary"]),
        yaxis=dict(color=PALETTE["text_secondary"]),
    )
    return fig


def _timeseries_chart(
    state: AppState,
    entity_type: str,
    entity_id: str,
    metric: str,
    current_idx: int,
) -> go.Figure:
    try:
        if entity_type == "node" and state.node_df is not None:
            df = state.node_df
            subset = df[df["node_id"] == entity_id][["timestamp", metric]].dropna()
        elif entity_type == "edge" and state.edge_df is not None:
            df = state.edge_df
            subset = df[df["edge_id"] == entity_id][["timestamp", metric]].dropna()
        else:
            return go.Figure()

        subset = subset.sort_values("timestamp")
        ts = pd.to_datetime(subset["timestamp"], unit="us", utc=True)
        fig = go.Figure()

        if state.gt_df is not None:
            gt = state.gt_df
            anomalous_ts = gt[gt["label_trace"] == 1]["timestamp"].values
            anomalous_set = set(anomalous_ts)
            anom_timestamps_sorted = sorted(
                t for t in subset["timestamp"] if t in anomalous_set
            )
            if anom_timestamps_sorted:
                step = (
                    subset["timestamp"].iloc[1] - subset["timestamp"].iloc[0]
                    if len(subset) > 1 else 5_000_000
                )
                groups: list[list[int]] = []
                grp: list[int] = [anom_timestamps_sorted[0]]
                for t in anom_timestamps_sorted[1:]:
                    if t - grp[-1] <= step * 2:
                        grp.append(t)
                    else:
                        groups.append(grp)
                        grp = [t]
                groups.append(grp)
                for grp in groups:
                    t0 = pd.to_datetime(grp[0], unit="us", utc=True)
                    t1 = pd.to_datetime(grp[-1], unit="us", utc=True)
                    fig.add_vrect(
                        x0=t0, x1=t1,
                        fillcolor=PALETTE["anomaly"], opacity=0.12,
                        layer="below", line_width=0,
                    )

        fig.add_trace(go.Scatter(
            x=ts, y=subset[metric], mode="lines", name=metric,
            line=dict(color=PALETTE["accent_blue"], width=1.5),
            hovertemplate="%{x|%H:%M:%S}<br>%{y:.4g}<extra></extra>",
        ))

        if state.snapshots and 0 <= current_idx < len(state.snapshots):
            ts_curr = state.snapshots[current_idx]["timestamp"]
            dt_curr = pd.to_datetime(ts_curr, unit="us", utc=True)
            fig.add_vline(x=dt_curr,
                          line=dict(color=PALETTE["yellow"], width=2, dash="dash"))

        title_str = f"{entity_type}:{entity_id}:{metric} nel tempo"
        fig.update_layout(
            title=dict(text=title_str, font=dict(color=PALETTE["text_primary"], size=13)),
            paper_bgcolor=PALETTE["surface"], plot_bgcolor=PALETTE["surface"],
            font=dict(color=PALETTE["text_secondary"]),
            xaxis=dict(title="Timestamp", color=PALETTE["text_secondary"],
                       gridcolor=PALETTE["border"]),
            yaxis=dict(title=metric, color=PALETTE["text_secondary"],
                       gridcolor=PALETTE["border"]),
            margin=dict(l=50, r=20, t=50, b=50), height=320,
            showlegend=False,
        )
        return fig
    except Exception as exc:
        fig = go.Figure()
        fig.add_annotation(text=f"Errore: {exc}", x=0.5, y=0.5, showarrow=False)
        return fig


# ── Tab 3: PBO ────────────────────────────────────────────────────────────

def _ensure_pbo_computed(state: AppState) -> bool:
    if (
        state.weight_series is not None
        and state.gold_standard is not None
        and state.pas_series is not None
        and state.frobenius_series is not None
    ):
        return True

    if not state.data_loaded() or state.pbo_builder is None:
        return False

    pbo = state.pbo_builder
    snapshots = state.snapshots

    try:
        with st.spinner("Calcolo PBO (weight_series, W_gold, PAS, Frobenius)..."):
            ws = pbo.compute_transition_weights(snapshots)
            state.weight_series = ws
            gs = pbo.compute_gold_standard(ws, snapshots)
            state.gold_standard = gs
            try:
                pas = pbo.compute_path_adherence(ws, "H_crit")
                state.pas_series = pas
            except Exception:
                state.pas_series = []
            frob = pbo.compute_frobenius_distance(ws, gs)
            state.frobenius_series = frob
        return True
    except Exception as exc:
        st.error(f"Errore nel calcolo PBO: {exc}")
        return False


def _topology_graph_with_weights(
    pos: dict[str, tuple[float, float]],
    topo: dict,
    weights: dict[str, float],
    gold: dict[str, float] | None,
    title: str,
) -> go.Figure:
    fig = go.Figure()
    max_weight = max(weights.values()) if weights else 1.0

    for edge in topo["edges"]:
        eid = edge["id"]
        u, v = edge["source"], edge["target"]
        x0, y0 = pos.get(u, (0, 0))
        x1, y1 = pos.get(v, (0, 0))
        w = weights.get(eid, 0.0)
        width = max(1.0, 8.0 * w / max_weight)

        fig.add_annotation(
            x=x1, y=y1, ax=x0, ay=y0,
            xref="x", yref="y", axref="x", ayref="y",
            arrowhead=2, arrowwidth=width,
            arrowcolor=PALETTE["accent_blue"],
            showarrow=True, text="",
        )
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        w_gold_val = (gold or {}).get(eid, 0.0)
        delta = w - w_gold_val
        delta_color = PALETTE["accent"] if delta >= 0 else PALETTE["red"]
        ab_color = PALETTE["accent_blue"]
        delta_note = f"<br><span style='color:{delta_color}'>delta{delta:+.3f}</span>" if gold else ""
        fig.add_annotation(
            x=mx, y=my, xref="x", yref="y",
            text=(
                f"<b style='font-size:9px'>{eid}</b><br>"
                f"<span style='color:{ab_color}'>{w:.3f}</span>"
                + delta_note
            ),
            showarrow=False,
            font=dict(size=9, color=PALETTE["text_primary"]),
            bgcolor=PALETTE["background"], borderpad=1,
        )

    for node in topo["nodes"]:
        nid = node["id"]
        x, y = pos.get(nid, (0.5, 0.5))
        fig.add_trace(go.Scatter(
            x=[x], y=[y], mode="markers+text",
            marker=dict(size=16, color=PALETTE["surface_alt"],
                        line=dict(color=PALETTE["accent_blue"], width=2)),
            text=[nid.split("-")[-1]],
            textposition="top center",
            textfont=dict(size=9, color=PALETTE["text_primary"]),
            showlegend=False,
            hovertemplate=f"<b>{nid}</b><extra></extra>",
        ))

    fig.update_layout(
        title=dict(text=title, font=dict(color=PALETTE["text_primary"], size=13)),
        paper_bgcolor=PALETTE["surface"], plot_bgcolor=PALETTE["surface"],
        font=dict(color=PALETTE["text_secondary"]),
        height=380, margin=dict(l=10, r=10, t=50, b=10),
        xaxis=dict(visible=False, range=[-0.05, 1.05]),
        yaxis=dict(visible=False, range=[-0.05, 1.05]),
        showlegend=False,
    )
    return fig


def _pas_frobenius_chart(state: AppState) -> go.Figure:
    fig = go.Figure()

    gt_df = state.gt_df
    anomalous_ts_set: set = set()
    if gt_df is not None:
        anomalous_ts_set = set(gt_df[gt_df["label_trace"] == 1]["timestamp"].values)

    pas_series = state.pas_series or []
    if pas_series:
        ts_pas = pd.to_datetime([e["timestamp"] for e in pas_series], unit="us", utc=True)
        vals_pas = [e["pas"] for e in pas_series]

        anom_ts = sorted(e["timestamp"] for e in pas_series
                         if e["timestamp"] in anomalous_ts_set)
        if anom_ts:
            step = (
                pas_series[1]["timestamp"] - pas_series[0]["timestamp"]
                if len(pas_series) > 1 else 5_000_000
            )
            groups: list[list[int]] = []
            grp = [anom_ts[0]]
            for t in anom_ts[1:]:
                if t - grp[-1] <= step * 2:
                    grp.append(t)
                else:
                    groups.append(grp)
                    grp = [t]
            groups.append(grp)
            for grp in groups:
                fig.add_vrect(
                    x0=pd.to_datetime(grp[0], unit="us", utc=True),
                    x1=pd.to_datetime(grp[-1], unit="us", utc=True),
                    fillcolor=PALETTE["anomaly"], opacity=0.1,
                    layer="below", line_width=0,
                )

        fig.add_trace(go.Scatter(
            x=ts_pas, y=vals_pas, mode="lines", name="PAS H_crit",
            line=dict(color=PALETTE["h_crit"], width=1.5),
            yaxis="y",
            hovertemplate="PAS: %{y:.4f}<extra></extra>",
        ))

        if state.gold_standard and state.pbo_builder:
            try:
                pbo = state.pbo_builder
                gs = state.gold_standard
                pas_gold_res = pbo.compute_path_adherence(
                    [{"timestamp": 0, "weights": gs}], "H_crit"
                )
                pas_gold = pas_gold_res[0]["pas"]
                fig.add_hline(
                    y=pas_gold, yref="y",
                    line=dict(color=PALETTE["h_crit"], dash="dash", width=1),
                    annotation_text=f"PAS_gold={pas_gold:.4f}",
                    annotation_font=dict(color=PALETTE["h_crit"], size=10),
                )
            except Exception:
                pass

    frob_series = state.frobenius_series or []
    if frob_series:
        ts_frob = pd.to_datetime([e["timestamp"] for e in frob_series], unit="us", utc=True)
        vals_frob = [e["frobenius"] for e in frob_series]
        fig.add_trace(go.Scatter(
            x=ts_frob, y=vals_frob, mode="lines", name="Frobenius H_cache",
            line=dict(color=PALETTE["h_cache"], width=1.5),
            yaxis="y2",
            hovertemplate="Frobenius: %{y:.4f}<extra></extra>",
        ))

    fig.update_layout(
        title=dict(text="Aderenza comportamentale nel tempo",
                   font=dict(color=PALETTE["text_primary"], size=13)),
        paper_bgcolor=PALETTE["surface"], plot_bgcolor=PALETTE["surface"],
        font=dict(color=PALETTE["text_secondary"]),
        xaxis=dict(title="Timestamp", color=PALETTE["text_secondary"],
                   gridcolor=PALETTE["border"]),
        yaxis=dict(title="PAS (H_crit)", color=PALETTE["h_crit"],
                   side="left", showgrid=True, gridcolor=PALETTE["border"]),
        yaxis2=dict(title="Frobenius (H_cache)", color=PALETTE["h_cache"],
                    side="right", overlaying="y", showgrid=False),
        legend=dict(font=dict(color=PALETTE["text_secondary"]),
                    bgcolor=PALETTE["surface_alt"], bordercolor=PALETTE["border"]),
        margin=dict(l=60, r=60, t=50, b=50), height=360,
    )
    return fig


# ── Entry point ───────────────────────────────────────────────────────────

def render() -> None:
    state = AppState.get()

    st.title("Topologia")
    st.caption(
        "Layer 1 — Ipergrafo H_cert  |  "
        "Layer 2 — ATG nel tempo  |  PBO — Pesi di transizione"
    )

    try:
        from src.utils.config_loader import ConfigLoader
        from src.layer1.topology_builder import TopologyBuilder

        _cfg = state.config if state.config is not None else ConfigLoader(
            _CONFIG_TOPOLOGY, _CONFIG_PIPELINE
        )
        if state.config is None:
            _cfg.load_topology()

        _tb = state.topology_builder if state.topology_builder is not None else TopologyBuilder(_cfg)
        topo = _cfg.load_topology()
    except Exception as exc:
        st.error(f"Impossibile caricare la topologia: {exc}")
        return

    try:
        G = _tb.build()
        h_crit_nodes = _tb.get_compliance_set_nodes("H_crit")
        h_cache_nodes = _tb.get_compliance_set_nodes("H_cache")
        shared_nodes = _tb.get_shared_nodes("H_crit", "H_cache")
        a_crit = set(_tb.get_edges_for_compliance_set("H_crit"))
        a_cache = set(_tb.get_edges_for_compliance_set("H_cache"))
        interf_cache = set(_tb.get_interference_edges("H_cache", "H_crit"))
        pos = _get_graph_layout(state, G)
    except Exception as exc:
        st.error(f"Errore nella costruzione del grafo: {exc}")
        return

    tab1, tab2, tab3 = st.tabs([
        "Layer 1 — Ipergrafo",
        "Layer 2 — ATG nel tempo",
        "PBO — Pesi di transizione",
    ])

    # ── Tab 1 — Layer 1 ──────────────────────────────────────────────────
    with tab1:
        st.caption("Grafo interattivo H_cert — hover su nodi e archi per dettagli")
        try:
            fig_topo = _topology_plotly(
                G, pos, h_crit_nodes, h_cache_nodes, shared_nodes,
                a_crit, a_cache, interf_cache, topo,
            )
            st.plotly_chart(fig_topo, use_container_width=True,
                            config={"displayModeBar": False})
        except Exception as exc:
            st.error(f"Errore nel grafo topologico: {exc}")

        st.divider()
        st.caption("Compliance sets")
        try:
            _cs_panel(topo, _tb)
        except Exception as exc:
            st.error(f"Errore pannello compliance sets: {exc}")

        st.divider()
        st.caption("Tabella archi — appartenenza a compliance sets e archi di interferenza")
        try:
            _edge_table(topo, _tb)
        except Exception as exc:
            st.error(f"Errore tabella archi: {exc}")

    # ── Tab 2 — ATG nel tempo ─────────────────────────────────────────────
    with tab2:
        if not state.data_loaded():
            st.info("Carica prima i dati nella sezione Dati per visualizzare l'ATG nel tempo.")
        else:
            node_ids_sorted = sorted(topo["nodes"], key=lambda n: n["id"])
            node_ids = [n["id"] for n in node_ids_sorted]
            node_metrics: list[str] = topo.get("node_metrics", [])
            edge_ids = [e["id"] for e in topo["edges"]]
            edge_metrics: list[str] = topo.get("edge_metrics", [])

            st.caption("Snapshot selezionato")
            n = state.n_snapshots
            idx = st.slider(
                "Snapshot index",
                min_value=0, max_value=n - 1,
                value=state.current_snapshot_idx,
                key="snap_slider_tab2",
                label_visibility="collapsed",
            )
            state.current_snapshot_idx = idx

            snap = state.snapshots[idx]
            ts_us = snap["timestamp"]
            dt_snap = pd.to_datetime(ts_us, unit="us", utc=True)
            label = snap.get("label", -1)
            anomaly_type = snap.get("anomaly_type")
            anomaly_nodes = snap.get("anomaly_node_ids", [])

            col_ts, col_lbl, col_anom = st.columns([3, 2, 4])
            with col_ts:
                st.markdown(
                    f'<div style="font-size:0.85rem;color:{PALETTE["text_secondary"]};">'
                    f'Timestamp</div>'
                    f'<div style="font-family:monospace;font-size:0.9rem;">'
                    f'{dt_snap.strftime("%Y-%m-%d %H:%M:%S UTC")}</div>',
                    unsafe_allow_html=True,
                )
            with col_lbl:
                if label == 0:
                    lbl_html = '<span class="badge badge-green">Nominale</span>'
                else:
                    atype = anomaly_type or "anomalo"
                    lbl_html = (
                        f'<span style="background:rgba(218,54,51,0.2);'
                        f'color:{PALETTE["red"]};border:1px solid {PALETTE["red"]};'
                        f'border-radius:12px;padding:0.2em 0.7em;font-size:0.8rem;'
                        f'font-weight:600;">Anomalo: {atype}</span>'
                    )
                st.markdown(lbl_html, unsafe_allow_html=True)
            with col_anom:
                if anomaly_nodes:
                    chips = " ".join(
                        f'<span class="node-chip" style="color:{PALETTE["red"]};">{n}</span>'
                        for n in anomaly_nodes
                    )
                    st.markdown(chips, unsafe_allow_html=True)

            col_b, col_c = st.columns(2)
            with col_b:
                try:
                    fig_nh = _snapshot_heatmap(
                        snap, node_ids, node_metrics, label, "Feature di nodo", "node",
                    )
                    st.plotly_chart(fig_nh, use_container_width=True,
                                    config={"displayModeBar": False})
                except Exception as exc:
                    st.error(f"Heatmap nodi: {exc}")
            with col_c:
                try:
                    fig_eh = _snapshot_heatmap(
                        snap, edge_ids, edge_metrics, label, "Feature di arco", "edge",
                    )
                    st.plotly_chart(fig_eh, use_container_width=True,
                                    config={"displayModeBar": False})
                except Exception as exc:
                    st.error(f"Heatmap archi: {exc}")

            st.divider()
            st.caption("Andamento temporale di una feature")
            sel_col1, sel_col2, sel_col3 = st.columns(3)
            with sel_col1:
                entity_type = st.selectbox("Tipo", ["Nodo", "Arco"], key="ts_type")
            with sel_col2:
                if entity_type == "Nodo":
                    feature = st.selectbox("Feature", node_metrics, key="ts_feat")
                    entity_list = node_ids
                    etype_key = "node"
                else:
                    feature = st.selectbox("Feature", edge_metrics, key="ts_feat")
                    entity_list = edge_ids
                    etype_key = "edge"
            with sel_col3:
                entity_id = st.selectbox("Elemento", entity_list, key="ts_entity")

            try:
                fig_ts = _timeseries_chart(state, etype_key, entity_id, feature, idx)
                st.plotly_chart(fig_ts, use_container_width=True,
                                config={"displayModeBar": False})
            except Exception as exc:
                st.error(f"Serie temporale: {exc}")

    # ── Tab 3 — PBO ───────────────────────────────────────────────────────
    with tab3:
        if not state.data_loaded():
            st.info("Carica prima i dati nella sezione Dati.")
        else:
            pbo_ok = _ensure_pbo_computed(state)
            if not pbo_ok:
                st.warning("PBO non disponibile — inizializza prima i moduli dalla pagina Dati.")
            else:
                gold = state.gold_standard or {}

                st.caption("W_gold — Gold Standard calibrato sulle finestre nominali")
                col_wg_graph, col_wg_table = st.columns([3, 2])
                with col_wg_graph:
                    try:
                        fig_wg = _topology_graph_with_weights(
                            pos, topo, gold, None,
                            "W_gold — spessore archi proporzionale al peso"
                        )
                        st.plotly_chart(fig_wg, use_container_width=True,
                                        config={"displayModeBar": False})
                    except Exception as exc:
                        st.error(f"Grafo W_gold: {exc}")
                with col_wg_table:
                    rows = []
                    for e in topo["edges"]:
                        eid = e["id"]
                        rows.append({
                            "edge_id": eid,
                            "source": e["source"],
                            "target": e["target"],
                            "w_gold": round(gold.get(eid, 0.0), 4),
                        })
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

                st.divider()
                st.caption("W_t — Pesi di transizione allo snapshot corrente")
                n = state.n_snapshots
                idx_pbo = st.slider(
                    "Snapshot (PBO)",
                    min_value=0, max_value=n - 1,
                    value=state.current_snapshot_idx,
                    key="snap_slider_pbo",
                    label_visibility="collapsed",
                )
                state.current_snapshot_idx = idx_pbo

                ws_all = state.weight_series or []
                curr_weights = ws_all[idx_pbo]["weights"] if idx_pbo < len(ws_all) else {}

                col_wt_graph, col_wt_bars = st.columns([3, 2])
                with col_wt_graph:
                    try:
                        fig_wt = _topology_graph_with_weights(
                            pos, topo, curr_weights, gold,
                            f"W(t) — snapshot {idx_pbo} | delta = w(t) - w_gold"
                        )
                        st.plotly_chart(fig_wt, use_container_width=True,
                                        config={"displayModeBar": False})
                    except Exception as exc:
                        st.error(f"Grafo W_t: {exc}")
                with col_wt_bars:
                    for e in topo["edges"]:
                        eid = e["id"]
                        wt = curr_weights.get(eid, 0.0)
                        wg = gold.get(eid, 0.0)
                        delta = wt - wg
                        delta_color = PALETTE["accent"] if delta >= 0 else PALETTE["red"]
                        st.markdown(
                            f'<div style="margin-bottom:0.5rem;">'
                            f'<div style="font-size:0.78rem;margin-bottom:0.1rem;">'
                            f'<b style="color:{PALETTE["accent_blue"]}">{eid}</b> '
                            f'<span style="color:{PALETTE["text_secondary"]}">'
                            f'{e["source"].split("-")[-1]} → {e["target"].split("-")[-1]}'
                            f'</span></div>'
                            f'<div style="display:flex;align-items:center;gap:0.5rem;">'
                            f'<div style="flex:1;background:{PALETTE["border"]};'
                            f'border-radius:3px;height:8px;">'
                            f'<div style="width:{min(100, wt * 100):.1f}%;'
                            f'background:{PALETTE["accent_blue"]};'
                            f'height:100%;border-radius:3px;"></div></div>'
                            f'<span style="font-size:0.78rem;min-width:3rem;'
                            f'color:{PALETTE["text_primary"]}">{wt:.3f}</span>'
                            f'<span style="font-size:0.75rem;color:{delta_color}">'
                            f'{delta:+.3f}</span>'
                            f'</div></div>',
                            unsafe_allow_html=True,
                        )

                st.divider()
                st.caption("Aderenza comportamentale nel tempo")
                try:
                    fig_pf = _pas_frobenius_chart(state)
                    st.plotly_chart(fig_pf, use_container_width=True,
                                    config={"displayModeBar": False})
                except Exception as exc:
                    st.error(f"Grafico PAS/Frobenius: {exc}")
