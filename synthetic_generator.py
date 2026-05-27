#!/usr/bin/env python3
"""
Generatore del dataset sintetico v2 — Framework Hybrid Hypergraph-ATG.
Scenario SaaS Monitoring Platform.

Differenze rispetto alla v1:
  - Nessun plateau piatto nella fase anomala.
    Il fault causa degradazione CONTINUA (rampa che accelera), non uno step
    verso un valore fisso. Elimina il problema "plateau < SLA".
  - ramp_rate scala solo la pendenza della rampa, non la sua ampiezza.
    La rampa e sempre cappata a RAMP_CAP_FRAC x SLA nei nominali.
    Elimina il problema "ramp > SLA".
  - La variazione di lead_time tra esperimenti emerge dal meccanismo EWMA:
    ramp piu ripida -> EWMA piu alto a inizio fase anomala -> lead_time minore.
  - Il riepilogo mostra il CS del scenario (H_ingest o H_analysis).

Schema CSV invariato:
  node_metrics.csv:  timestamp, window_id, node_id, cpu_percent, mem_mb, net_rx_mb, net_tx_mb
  edge_metrics.csv:  timestamp, window_id, edge_id, source, target, latency_ms, error_rate, throughput_rps
  ground_truth.csv:  timestamp, window_id, fault_type, anomaly_node_ids, label_trace

Utilizzo:
  python synthetic_generator_v2.py
  python synthetic_generator_v2.py --n-nominal 60 --n-ramp 25 --n-anomalous 30 --seed 42
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


N_NOMINAL   = 60
N_RAMP      = 25
N_ANOMALOUS = 30
WINDOW_S    = 30
SEED        = 42

RAMP_RATES  = [0.7, 1.0, 1.4]

RAMP_TARGET_FRAC = 0.90
RAMP_CAP_FRAC    = 0.93
FAULT_SPEED_MULT = 2.0

SLA_H_INGEST   = 70.0
SLA_H_ANALYSIS = 120.0

NODES = [
    "api-gateway", "metrics-ingestor", "data-enricher", "stream-processor",
    "storage-writer", "analysis-engine", "alert-dispatcher", "report-generator",
]

EDGES = {
    "e1": ("api-gateway",       "metrics-ingestor"),
    "e2": ("metrics-ingestor",  "data-enricher"),
    "e3": ("data-enricher",     "stream-processor"),
    "e4": ("stream-processor",  "storage-writer"),
    "e5": ("api-gateway",       "stream-processor"),
    "e6": ("stream-processor",  "analysis-engine"),
    "e7": ("stream-processor",  "alert-dispatcher"),
    "e8": ("stream-processor",  "report-generator"),
}

LATENCY_NOMINAL_MS = {
    "e1": 3.0, "e2": 8.0, "e3": 5.0, "e4": 18.0,
    "e5": 4.0, "e6": 45.0, "e7": 8.0, "e8": 15.0,
}
LATENCY_STD_MS = {k: max(0.1, v * 0.05) for k, v in LATENCY_NOMINAL_MS.items()}

THROUGHPUT_NOMINAL_RPS = {
    "e1": 100.0, "e2": 100.0, "e3": 100.0, "e4": 95.0,
    "e5": 50.0,  "e6": 50.0,  "e7": 50.0,  "e8": 50.0,
}
THROUGHPUT_STD_RPS = {k: max(0.1, v * 0.05) for k, v in THROUGHPUT_NOMINAL_RPS.items()}

ERROR_RATE_NOMINAL = 0.001
ERROR_RATE_STD     = 0.0002

NODE_METRICS_NOMINAL = {
    "api-gateway":       (8.0,  192.0, 10.0, 10.0),
    "metrics-ingestor":  (2.0,  128.0,  5.0,  2.0),
    "data-enricher":     (3.5,  160.0,  4.0,  2.5),
    "stream-processor":  (15.0, 256.0,  3.0,  3.0),
    "storage-writer":    (5.0,  512.0,  1.0,  0.5),
    "analysis-engine":   (20.0, 384.0,  0.5,  0.5),
    "alert-dispatcher":  (1.0,   64.0,  0.2,  0.2),
    "report-generator":  (3.0,  128.0,  0.3,  0.3),
}
NODE_METRICS_STD = {
    k: (max(0.1, v[0]*0.05), max(1.0, v[1]*0.05),
        max(0.01, v[2]*0.10), max(0.01, v[3]*0.10))
    for k, v in NODE_METRICS_NOMINAL.items()
}

H_INGEST_ARCS   = ["e1", "e2", "e3", "e4"]
H_ANALYSIS_ARCS = ["e5", "e6", "e7", "e8"]

FAULT_SCENARIOS = [
    {
        "name":            "metrics_ingestor_memory_leak",
        "fault_type":      "memory_leak",
        "target_node":     "metrics-ingestor",
        "affected_arcs":   ["e2"],
        "target_cs":       "H_ingest",
        "side_effect_node": "stream-processor",
        "mem_factor":      4.0,
        "routing_drift":   {"e4": -0.08, "e6": +0.08, "e7": 0.0, "e8": 0.0},
    },
    {
        "name":            "data_enricher_memory_leak",
        "fault_type":      "memory_leak",
        "target_node":     "data-enricher",
        "affected_arcs":   ["e3"],
        "target_cs":       "H_ingest",
        "side_effect_node": "stream-processor",
        "mem_factor":      4.5,
        "routing_drift":   {"e4": -0.06, "e6": +0.04, "e7": +0.01, "e8": +0.01},
    },
    {
        "name":            "stream_processor_cpu_saturation",
        "fault_type":      "cpu_hog",
        "target_node":     "stream-processor",
        "affected_arcs":   ["e4", "e6", "e7", "e8"],
        "target_cs":       "H_ingest",
        "side_effect_node": None,
        "mem_factor":      1.2,
        "routing_drift":   {"e4": -0.10, "e6": +0.06, "e7": +0.02, "e8": +0.02},
    },
    {
        "name":            "analysis_engine_memory_leak",
        "fault_type":      "memory_leak",
        "target_node":     "analysis-engine",
        "affected_arcs":   ["e6"],
        "target_cs":       "H_analysis",
        "side_effect_node": None,
        "mem_factor":      5.0,
        "routing_drift":   {},
    },
]


def compute_arc_slopes(scenario: dict, n_ramp: int) -> dict[str, float]:
    """
    Calcola la pendenza nominale (a ramp_rate=1.0) per ogni arco affected.

    Per scenari con affected_arcs che attraversano più compliance set
    (es. stream_processor con e4 in H_ingest ed e6/e7/e8 in H_analysis),
    ogni arco viene calibrato rispetto al proprio CS di riferimento.
    """
    if n_ramp == 0:
        return {e: 0.0 for e in scenario["affected_arcs"]}

    affected = scenario["affected_arcs"]
    slopes: dict[str, float] = {}

    for arc in affected:
        if arc in H_INGEST_ARCS:
            arc_cs = "H_ingest"
        elif arc in H_ANALYSIS_ARCS:
            arc_cs = "H_analysis"
        else:
            slopes[arc] = 0.0
            continue

        if arc_cs == "H_ingest":
            sla_target = SLA_H_INGEST * RAMP_TARGET_FRAC
            nominal_sum = sum(LATENCY_NOMINAL_MS[e] for e in H_INGEST_ARCS)
            in_cs_count = sum(1 for e in affected if e in H_INGEST_ARCS)
            if in_cs_count == 0:
                slopes[arc] = 0.0
            else:
                delta = sla_target - nominal_sum
                slopes[arc] = delta / (n_ramp * in_cs_count)

        elif arc_cs == "H_analysis":
            # Ramo critico H_analysis: e5 + e6 (latenza massima).
            # Archi paralleli (e6, e7, e8): ciascuno porta il proprio
            # ramo critico al 90% di SLA.
            sla_target = SLA_H_ANALYSIS * RAMP_TARGET_FRAC
            e5_nom = LATENCY_NOMINAL_MS["e5"]
            e_nom = LATENCY_NOMINAL_MS[arc]
            delta = sla_target - e5_nom - e_nom
            slopes[arc] = delta / n_ramp if delta > 0 else 0.0

    return slopes


def compute_arc_caps(scenario: dict) -> dict[str, float]:
    """
    Calcola il valore massimo assoluto per ogni arco affected durante la rampa.
    """
    affected = scenario["affected_arcs"]
    caps: dict[str, float] = {}

    for arc in affected:
        if arc in H_INGEST_ARCS:
            sla_cap = SLA_H_INGEST * RAMP_CAP_FRAC
            nominal_sum = sum(LATENCY_NOMINAL_MS[e] for e in H_INGEST_ARCS)
            in_cs = [e for e in affected if e in H_INGEST_ARCS]
            if not in_cs:
                caps[arc] = float("inf")
            else:
                max_each = (sla_cap - nominal_sum) / len(in_cs)
                caps[arc] = LATENCY_NOMINAL_MS[arc] + max_each

        elif arc in H_ANALYSIS_ARCS:
            sla_cap = SLA_H_ANALYSIS * RAMP_CAP_FRAC
            e5_nom = LATENCY_NOMINAL_MS["e5"]
            caps[arc] = sla_cap - e5_nom  # cap sul singolo arco parallelo

        else:
            caps[arc] = float("inf")

    return caps


def generate_experiment(
    scenario: dict,
    ramp_rate: float,
    rng: np.random.Generator,
    base_timestamp_us: int,
    n_nominal: int,
    n_ramp: int,
    n_anomalous: int,
    window_s: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    total      = n_nominal + n_anomalous
    ramp_start = n_nominal - n_ramp

    slopes = compute_arc_slopes(scenario, n_ramp)
    caps   = compute_arc_caps(scenario)

    last_ramp_val: dict[str, float] = {
        arc: LATENCY_NOMINAL_MS[arc] for arc in scenario["affected_arcs"]
    }

    node_rows: list[dict] = []
    edge_rows: list[dict] = []
    gt_rows:   list[dict] = []

    for t_idx in range(total):
        ts        = base_timestamp_us + t_idx * window_s * 1_000_000
        is_anomal = t_idx >= n_nominal
        label     = 1 if is_anomal else 0

        ramp_step   = (t_idx - ramp_start + 1) if (not is_anomal and t_idx >= ramp_start) else 0
        anomal_step = (t_idx - n_nominal + 1)   if is_anomal else 0

        for node_id in NODES:
            nom = NODE_METRICS_NOMINAL[node_id]
            std = NODE_METRICS_STD[node_id]

            cpu    = float(rng.normal(nom[0], std[0]))
            mem    = float(rng.normal(nom[1], std[1]))
            net_rx = float(rng.normal(nom[2], std[2]))
            net_tx = float(rng.normal(nom[3], std[3]))

            if node_id == scenario["target_node"] and is_anomal:
                m = 1.0 + (anomal_step / n_anomalous) * (scenario["mem_factor"] - 1.0)
                mem *= m
                cpu *= (1.0 + (anomal_step / n_anomalous) * 0.4)

            sn = scenario.get("side_effect_node")
            if sn and node_id == sn and is_anomal:
                cpu *= (1.0 + (anomal_step / n_anomalous) * 0.35)

            node_rows.append({
                "timestamp":   ts, "window_id": t_idx, "node_id": node_id,
                "cpu_percent": max(0.01, cpu), "mem_mb": max(1.0, mem),
                "net_rx_mb":   max(0.0, net_rx), "net_tx_mb": max(0.0, net_tx),
            })

        for edge_id, (source, target) in EDGES.items():
            lat_nom = LATENCY_NOMINAL_MS[edge_id]
            std_lat = LATENCY_STD_MS[edge_id]
            thr_nom = THROUGHPUT_NOMINAL_RPS[edge_id]
            std_thr = THROUGHPUT_STD_RPS[edge_id]

            latency    = float(rng.normal(lat_nom, std_lat))
            throughput = float(rng.normal(thr_nom, std_thr))
            error_rate = float(rng.normal(ERROR_RATE_NOMINAL, ERROR_RATE_STD))

            if edge_id in scenario["affected_arcs"]:
                slope = slopes.get(edge_id, 0.0)
                cap   = caps.get(edge_id, float("inf"))

                if ramp_step > 0:
                    ramp_val = min(lat_nom + slope * ramp_rate * ramp_step, cap)
                    last_ramp_val[edge_id] = ramp_val
                    noise = std_lat * (1.0 + ramp_step / n_ramp)
                    latency = float(rng.normal(ramp_val, noise))

                elif is_anomal:
                    fault_slope = slope * ramp_rate * FAULT_SPEED_MULT
                    fault_val   = last_ramp_val[edge_id] + fault_slope * anomal_step
                    nf = 1.0 + 2.0 * max(0.0, fault_val - lat_nom) / (lat_nom + 1.0)
                    latency = float(rng.normal(fault_val, std_lat * max(1.0, nf)))
                    if anomal_step > n_anomalous // 2:
                        frac = (anomal_step - n_anomalous // 2) / max(1, n_anomalous // 2)
                        error_rate = float(rng.normal(
                            ERROR_RATE_NOMINAL + frac * 0.04, ERROR_RATE_STD * 5.0
                        ))

            drift = scenario.get("routing_drift", {}).get(edge_id, 0.0)
            if is_anomal and abs(drift) > 0.0:
                w_gold = {"e4": 0.388, "e6": 0.204, "e7": 0.204, "e8": 0.204}
                if edge_id in w_gold:
                    total_out = sum(THROUGHPUT_NOMINAL_RPS[e] for e in w_gold)
                    df = min(1.0, anomal_step / n_anomalous)
                    w_new = max(0.05, min(0.80, w_gold[edge_id] + drift * df))
                    throughput = float(rng.normal(total_out * w_new, std_thr * (1.0 + df)))

            edge_rows.append({
                "timestamp": ts, "window_id": t_idx, "edge_id": edge_id,
                "source": source, "target": target,
                "latency_ms":     max(0.1, latency),
                "error_rate":     max(0.0, min(1.0, error_rate)),
                "throughput_rps": max(0.1, throughput),
            })

        gt_rows.append({
            "timestamp":        ts, "window_id": t_idx,
            "fault_type":       scenario["fault_type"] if is_anomal else "nominal",
            "anomaly_node_ids": json.dumps([scenario["target_node"]] if is_anomal else []),
            "label_trace":      label,
        })

    return pd.DataFrame(node_rows), pd.DataFrame(edge_rows), pd.DataFrame(gt_rows)


def _hingest_agg(edf: pd.DataFrame, wids: list[int]) -> float:
    r = edf[edf["window_id"].isin(wids)]
    return sum(r.loc[r["edge_id"] == e, "latency_ms"].mean() for e in H_INGEST_ARCS)


def _hanalysis_agg(edf: pd.DataFrame, wids: list[int]) -> float:
    r = edf[edf["window_id"].isin(wids)]
    e5 = r.loc[r["edge_id"] == "e5", "latency_ms"].mean()
    return max(e5 + r.loc[r["edge_id"] == e, "latency_ms"].mean() for e in ["e6", "e7", "e8"])


def generate_all(
    output_base: Path,
    n_nominal=N_NOMINAL, n_ramp=N_RAMP, n_anomalous=N_ANOMALOUS,
    window_s=WINDOW_S, seed=SEED,
) -> None:
    rng = np.random.default_rng(seed)
    base = int(1_700_000_000_000_000)
    exp_n = 0
    summary = []

    for scenario in FAULT_SCENARIOS:
        for rep_idx, ramp_rate in enumerate(RAMP_RATES):
            exp_name = f"{scenario['name']}_rep{rep_idx + 1}"
            out_dir  = output_base / scenario["name"] / str(rep_idx + 1)
            out_dir.mkdir(parents=True, exist_ok=True)

            exp_start = base + exp_n * (n_nominal + n_anomalous) * window_s * 1_000_000
            ndf, edf, gdf = generate_experiment(
                scenario, ramp_rate, rng, exp_start,
                n_nominal, n_ramp, n_anomalous, window_s,
            )

            ndf.to_csv(out_dir / "node_metrics.csv",  index=False)
            edf.to_csv(out_dir / "edge_metrics.csv",  index=False)
            gdf.to_csv(out_dir / "ground_truth.csv",  index=False)

            json.dump(
                {"scenario": scenario["name"], "fault_type": scenario["fault_type"],
                 "target_node": scenario["target_node"], "target_cs": scenario["target_cs"],
                 "ramp_rate": ramp_rate, "rep": rep_idx+1, "n_nominal": n_nominal,
                 "n_ramp": n_ramp, "n_anomalous": n_anomalous, "window_s": window_s,
                 "affected_arcs": scenario["affected_arcs"]},
                open(out_dir / "experiment_meta.json", "w"), indent=2,
            )

            exp_n += 1

            cs = scenario["target_cs"]
            sla = SLA_H_INGEST if cs == "H_ingest" else SLA_H_ANALYSIS
            agg = _hingest_agg if cs == "H_ingest" else _hanalysis_agg

            nom_agg  = agg(edf, list(range(n_nominal - n_ramp)))
            ramp_agg = agg(edf, [n_nominal - 1])
            last_agg = agg(edf, [n_nominal + n_anomalous - 1])

            ok_r = bool(ramp_agg < sla)
            ok_a = bool(last_agg > sla)

            print(
                f"  {exp_name:52s} {cs}  "
                f"nom={nom_agg:5.1f}  ramp={ramp_agg:6.1f}[{'OK  ' if ok_r else 'WARN'}]  "
                f"last={last_agg:6.1f}[{'OK  ' if ok_a else 'WARN'}]  SLA={sla:.0f}ms"
            )

            summary.append({
                "exp": exp_name, "target_cs": cs, "ramp_rate": ramp_rate,
                "nom_ms": round(nom_agg, 1), "ramp_end_ms": round(ramp_agg, 1),
                "last_anomal_ms": round(last_agg, 1), "sla_ms": sla,
                "ramp_ok": ok_r, "anomal_ok": ok_a,
            })

    out_s = output_base / "generation_summary_v2.json"
    json.dump(summary, open(out_s, "w"), indent=2)

    nwr = sum(1 for r in summary if not r["ramp_ok"])
    nwa = sum(1 for r in summary if not r["anomal_ok"])
    print(f"\nGenerati {exp_n} esperimenti. WARN ramp: {nwr}  WARN anomal: {nwa}  (atteso: 0 entrambi)")
    if nwr == 0 and nwa == 0:
        print("Dataset calibrato correttamente. Nessun WARN.")
    print(f"Summary: {out_s}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output",      default="data/synthetic")
    p.add_argument("--n-nominal",   type=int, default=N_NOMINAL)
    p.add_argument("--n-ramp",      type=int, default=N_RAMP)
    p.add_argument("--n-anomalous", type=int, default=N_ANOMALOUS)
    p.add_argument("--window-s",    type=int, default=WINDOW_S)
    p.add_argument("--seed",        type=int, default=SEED)
    a = p.parse_args()

    assert a.n_ramp < a.n_nominal, f"n_ramp ({a.n_ramp}) deve essere < n_nominal ({a.n_nominal})"
    print(f"n_nominal={a.n_nominal}, n_ramp={a.n_ramp}, n_anomalous={a.n_anomalous}\n")
    generate_all(Path(a.output), a.n_nominal, a.n_ramp, a.n_anomalous, a.window_s, a.seed)