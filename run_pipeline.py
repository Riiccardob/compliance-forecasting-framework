#!/usr/bin/env python3
"""
Standalone runner per il framework Hybrid Hypergraph-ATG.

Esegue la pipeline completa (Layer 1-2-3, Fasi I-IV) direttamente sui CSV
canonici, senza dipendenze dalla dashboard o dal DataManager.

Architettura di forecasting:
  - Training: una sola sessione, esclusivamente su snapshot nominali (label=0).
  - Inference: forecast unico calcolato post-fit, riusato per ogni finestra
    anomala (training fisso, no rolling window). Questa e la stessa architettura
    del runner della dashboard e produce i risultati documentati nel Capitolo 5.

Motivo del no-rolling-window:
  - Rolling window sul training: violerebbe l'invariante fondamentale
    (i modelli devono apprendere la distribuzione nominale, non quella anomala).
  - Rolling window sull'inference (predict() per ogni snapshot): non modifica
    i risultati su DSB perche la previsione nominale viola gia la soglia SLA
    (latenza nominale ~202 ms > soglia 100 ms), producendo lead_time=1 in ogni
    caso. Il costo computazionale sarebbe proibitivo (~9.913 chiamate Prophet).

Utilizzo:
  python run_pipeline.py [--output risultati.json] [--log-level WARNING]
  python run_pipeline.py --fault-type cpu    # solo fault CPU
  python run_pipeline.py --limit 500         # primi N snapshot anomali
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.utils.config_loader import ConfigLoader
from src.utils.logging_setup import LoggingSetup
from src.layer1.topology_builder import TopologyBuilder
from src.layer2.atg_builder import ATGBuilder
from src.layer2.pbo_builder import PBOBuilder
from src.layer3.feature_selector import FeatureSelector
from src.phase1.stat_forecaster import StatForecaster
from src.phase2.causal_analyzer import CausalAnalyzer
from src.phase3.structural_monitor import StructuralMonitor
from src.phase4.alert_generator import AlertGenerator

runner_logger = LoggingSetup.configure("pipeline.runner", "INFO")

_LINE = "=" * 72
_DASH = "-" * 72


def _data_path(data_paths: dict[str, str], canonical_key: str, legacy_key: str) -> str:
    """Legge un path dataset accettando anche la vecchia chiave config."""
    if canonical_key in data_paths:
        return data_paths[canonical_key]
    if legacy_key in data_paths:
        return data_paths[legacy_key]
    raise KeyError(
        f"data_paths deve contenere '{canonical_key}' "
        f"(oppure legacy '{legacy_key}')"
    )


# ---------------------------------------------------------------------------
# Helpers di output
# ---------------------------------------------------------------------------

def _sec(title: str) -> None:
    print(f"\n{_LINE}\n  {title}\n{_LINE}")


def _sub(title: str) -> None:
    print(f"\n{_DASH}\n  {title}\n{_DASH}")


def _pct(num: int, den: int, decimals: int = 1) -> str:
    if den == 0:
        return "0/0 (N/A)"
    return f"{num}/{den} ({num / den * 100:.{decimals}f}%)"


def _safe(v: Any) -> Any:
    """Converte tipi numpy/float non JSON-serializzabili in tipi Python base."""
    if v is None:
        return None
    try:
        if math.isnan(float(v)):
            return None
        return float(v) if not isinstance(v, int) else int(v)
    except (TypeError, ValueError):
        return str(v)


# ---------------------------------------------------------------------------
# Statistiche aggregate
# ---------------------------------------------------------------------------

def _monitor_stats(results: list[dict]) -> dict:
    n = len(results)
    if n == 0:
        return {}
    base = sum(1 for r in results if r.get("base_signal", False))
    ifr  = sum(1 for r in results if r.get("if_signal", False))
    cusum = sum(1 for r in results if r.get("cusum_signal", False))
    conf  = sum(1 for r in results if r.get("structural_confirmed", False))
    pas_vals   = [r["pas_value"]          for r in results if r.get("pas_value")          is not None]
    frob_vals  = [r["frobenius_distance"] for r in results if r.get("frobenius_distance") is not None]
    cusum_vals = [r.get("cusum_stat", 0.0) for r in results]
    return {
        "n": n,
        "base_signal_rate":          base / n,
        "if_signal_rate":            ifr  / n,
        "cusum_signal_rate":         cusum / n,
        "structural_confirmed_rate": conf  / n,
        "pas_values":   pas_vals,
        "frob_values":  frob_vals,
        "cusum_stats":  cusum_vals,
    }


def _alert_stats(alerts: list[dict], n_total_anomalous: int) -> dict:
    n = len(alerts)
    if n == 0:
        return {"count": 0, "recall": 0.0}
    criticality = Counter(a["criticality"] for a in alerts)
    lt_steps    = [a["lead_time_steps"] for a in alerts if a.get("lead_time_steps")]
    rc_defined  = sum(1 for a in alerts if a.get("root_cause") is not None)
    cp_defined  = sum(1 for a in alerts if a.get("cross_property_interference") is not None)
    unc_true    = sum(1 for a in alerts if a.get("model_uncertainty_flag", False))
    lt_dist     = Counter(lt_steps)
    root_causes = Counter(a.get("root_cause") for a in alerts if a.get("root_cause"))
    arcs_crit   = Counter(a.get("critical_arc") for a in alerts if a.get("critical_arc"))
    return {
        "count":                n,
        "recall":               n / n_total_anomalous,
        "criticality":          dict(criticality),
        "lead_time_steps_mean": sum(lt_steps) / len(lt_steps) if lt_steps else None,
        "lead_time_dist":       dict(sorted(lt_dist.items())),
        "root_cause_rate":      rc_defined / n,
        "cross_property_rate":  cp_defined / n,
        "uncertainty_flag_rate": unc_true / n,
        "root_cause_top5":      dict(root_causes.most_common(5)),
        "critical_arc_top5":    dict(arcs_crit.most_common(5)),
    }


# ---------------------------------------------------------------------------
# Runner principale
# ---------------------------------------------------------------------------

def run_pipeline(
    output_path: str | None = None,
    fault_type_filter: str | None = None,
    limit: int | None = None,
) -> dict:
    """
    Esegue la pipeline e restituisce un dizionario con tutti i risultati.

    Parameters
    ----------
    output_path:
        Percorso JSON per il salvataggio dei risultati grezzi.
    fault_type_filter:
        Se specificato, esegue l'inference solo sulle finestre con questo
        tipo di fault (es. "cpu", "mem", "net", "cpu_mem").
    limit:
        Numero massimo di snapshot anomali su cui eseguire l'inference.
        Utile per test rapidi. None = tutti.
    """
    t_global = time.time()

    # -----------------------------------------------------------------------
    # 0. Configurazione
    # -----------------------------------------------------------------------
    _sec("INIZIALIZZAZIONE")

    config = ConfigLoader(
        ROOT / "config" / "topology.yaml",
        ROOT / "config" / "pipeline_params.yaml",
    )
    topo_cfg     = config.load_topology()
    pipeline_cfg = config.load_pipeline_params()
    cs_names     = list(topo_cfg["compliance_sets"].keys())
    horizon      = pipeline_cfg["forecasting"]["horizon_steps"]
    step_h       = pipeline_cfg["forecasting"].get("step_duration_hours", 24.0)

    print(f"Compliance set:   {cs_names}")
    print(f"Orizzonte:        {horizon} step x {step_h:.0f} h = {horizon * step_h:.0f} h")
    print(f"SLA per CS:")
    for cs in cs_names:
        sla = topo_cfg["compliance_sets"][cs].get("sla", {})
        ttype = topo_cfg["compliance_sets"][cs].get("topology_type", "?")
        print(f"  {cs} ({ttype}): {sla}")

    if fault_type_filter:
        print(f"Filtro fault type: {fault_type_filter}")
    if limit:
        print(f"Limite inference: {limit} snapshot anomali")

    # -----------------------------------------------------------------------
    # LAYER 1 - TopologyBuilder
    # -----------------------------------------------------------------------
    _sec("LAYER 1 - IPERGRAFO DI CERTIFICAZIONE")

    topology = TopologyBuilder(config)
    topology.build()

    for cs in cs_names:
        nodes  = topology.get_compliance_set_nodes(cs)
        edges  = topology.get_edges_for_compliance_set(cs)
        ttype  = topo_cfg["compliance_sets"][cs].get("topology_type", "?")
        path   = topology.get_critical_path(cs)
        print(f"\n{cs} ({ttype})")
        print(f"  Nodi ({len(nodes)}): {sorted(nodes)}")
        print(f"  Archi A(H) ({len(edges)}): {[f'{u}->{v}' for u,v in edges]}")
        if path:
            print(f"  Critical path: {' -> '.join(path)}")

    if len(cs_names) >= 2:
        shared = topology.get_shared_nodes(cs_names[0], cs_names[1])
        print(f"\nShared({cs_names[0]}, {cs_names[1]}): {sorted(shared)}")
        interf_01 = topology.get_interference_edges(cs_names[0], cs_names[1])
        interf_10 = topology.get_interference_edges(cs_names[1], cs_names[0])
        print(f"M_interf({cs_names[0]}, {cs_names[1]}): "
              f"{[f'{u}->{v}' for u,v in interf_01] or 'vuoto'}")
        print(f"M_interf({cs_names[1]}, {cs_names[0]}): "
              f"{[f'{u}->{v}' for u,v in interf_10] or 'vuoto'}")

    # -----------------------------------------------------------------------
    # LAYER 2 - ATGBuilder: caricamento CSV
    # -----------------------------------------------------------------------
    _sec("LAYER 2 - ATG: CARICAMENTO DATASET")

    data_paths = topo_cfg["data_paths"]
    atg = ATGBuilder(
        config,
        node_metrics_path=ROOT / _data_path(
            data_paths, "node_metrics_csv", "node_metrics"
        ),
        edge_metrics_path=ROOT / _data_path(
            data_paths, "edge_metrics_csv", "edge_metrics"
        ),
        ground_truth_path=ROOT / _data_path(
            data_paths, "ground_truth_csv", "ground_truth"
        ),
    )

    print("Lettura CSV canonici in corso...")
    t0 = time.time()
    all_snapshots = atg.build()
    print(f"Build ATG: {time.time() - t0:.1f}s")

    nominal   = ATGBuilder.get_nominal_snapshots(all_snapshots)
    anomalous = ATGBuilder.get_anomalous_snapshots(all_snapshots)

    if fault_type_filter:
        anomalous = ATGBuilder.get_anomalous_snapshots(
            all_snapshots, anomaly_type=fault_type_filter
        )

    if limit:
        anomalous = anomalous[:limit]

    n_total_anomalous_unfiltered = len(ATGBuilder.get_anomalous_snapshots(all_snapshots))
    atype_dist = Counter(
        s["anomaly_type"]
        for s in ATGBuilder.get_anomalous_snapshots(all_snapshots)
        if s["anomaly_type"]
    )

    print(f"\nSnapshot totali allineati: {len(all_snapshots)}")
    print(f"  Nominali  (label=0): {len(nominal)} "
          f"({len(nominal)/len(all_snapshots)*100:.1f}%)")
    print(f"  Anomali   (label=1): {n_total_anomalous_unfiltered} "
          f"({n_total_anomalous_unfiltered/len(all_snapshots)*100:.1f}%)")
    print(f"  Distribuzione fault type: {dict(atype_dist)}")
    print(f"\nSnapshot su cui verra eseguita l'inference: {len(anomalous)}")

    dataset_stats = {
        "total_snapshots":           len(all_snapshots),
        "nominal_count":             len(nominal),
        "anomalous_count_total":     n_total_anomalous_unfiltered,
        "anomalous_count_inference": len(anomalous),
        "fault_type_distribution":   dict(atype_dist),
        "fault_type_filter":         fault_type_filter,
        "limit":                     limit,
    }

    # -----------------------------------------------------------------------
    # LAYER 2 - PBOBuilder: matrice stocastica e gold standard
    # -----------------------------------------------------------------------
    _sec("LAYER 2 - PBO: MATRICE DI TRANSIZIONE E GOLD STANDARD")

    pbo = PBOBuilder(config, topology)

    t0 = time.time()
    weight_nominal = pbo.compute_transition_weights(nominal)
    gold           = pbo.compute_gold_standard(weight_nominal, nominal)
    print(f"Gold standard calcolato su {len(nominal)} nominali ({time.time()-t0:.1f}s)")

    print(f"\nW_gold per arco:")
    for eid in sorted(gold.keys()):
        print(f"  {eid}: {gold[eid]:.6f}")

    # Diagnosi PAS/Frobenius su un campione di finestre anomale
    sample_anom = anomalous[:min(100, len(anomalous))]
    w_sample    = pbo.compute_transition_weights(sample_anom)

    pbo_diagnostics: dict[str, Any] = {}
    print(f"\nDiagnosi PBO su campione di {len(sample_anom)} finestre anomale:")
    for cs in cs_names:
        ttype = topo_cfg["compliance_sets"][cs].get("topology_type", "")
        if ttype == "linear":
            try:
                pas_series = pbo.compute_path_adherence(w_sample, cs)
                pas_vals   = [e["pas"] for e in pas_series]
                is_const   = (max(pas_vals) - min(pas_vals)) < 1e-9
                pbo_diagnostics[cs] = {
                    "type": "PAS",
                    "min": min(pas_vals), "max": max(pas_vals),
                    "mean": sum(pas_vals) / len(pas_vals),
                    "constant": is_const,
                }
                print(f"  PAS {cs}: min={min(pas_vals):.6f}  max={max(pas_vals):.6f}  "
                      f"costante={'SI' if is_const else 'NO'}")
                if is_const:
                    print(f"    Atteso (limitazione DSB): CUSUM inattivo su questo CS.")
            except Exception as exc:
                print(f"  PAS {cs}: errore - {exc}")
        else:
            try:
                frob_series = pbo.compute_frobenius_distance(w_sample, gold)
                frob_vals   = [e["frobenius"] for e in frob_series]
                is_zero     = max(frob_vals) < 1e-9
                pbo_diagnostics[cs] = {
                    "type": "Frobenius",
                    "min": min(frob_vals), "max": max(frob_vals),
                    "mean": sum(frob_vals) / len(frob_vals),
                    "zero": is_zero,
                }
                print(f"  Frobenius {cs}: min={min(frob_vals):.6f}  "
                      f"max={max(frob_vals):.6f}  "
                      f"identicamente_zero={'SI' if is_zero else 'NO'}")
                if is_zero:
                    print(f"    Atteso (limitazione DSB): CUSUM inattivo su questo CS.")
            except Exception as exc:
                print(f"  Frobenius {cs}: errore - {exc}")

    # -----------------------------------------------------------------------
    # PIPELINE PER COMPLIANCE SET
    # -----------------------------------------------------------------------
    results_cs: dict[str, Any] = {}

    for cs in cs_names:
        _sec(f"COMPLIANCE SET: {cs}")
        t_cs = time.time()

        cs_cfg = topo_cfg["compliance_sets"][cs]
        ttype  = cs_cfg.get("topology_type", "")
        sla    = cs_cfg.get("sla", {})

        print(f"Tipo topologia: {ttype}")
        print(f"SLA:            {sla}")

        # ----------------------------------------------------------------
        # Feature Selection su nominali
        # ----------------------------------------------------------------
        _sub("Feature Selection (M_direct union M_interf)")

        fs        = FeatureSelector(config, topology)
        feats_nom = fs.select_features(cs, nominal)
        feat_info = fs.get_feature_names(cs)

        n_node  = len([k for k in feats_nom if k.startswith("node:")])
        n_edge  = len([k for k in feats_nom if k.startswith("edge:")])
        n_interf = len([k for k in feats_nom if k.startswith("interf:")])

        print(f"Feature totali: {len(feats_nom)}  "
              f"(node={n_node}, edge={n_edge}, interf={n_interf})")
        if n_interf > 0:
            interf_keys = [k for k in feats_nom if k.startswith("interf:")]
            print(f"Feature interferenza: {interf_keys}")
            print(f"  Queste feature bypassano il filtro Pearson in Fase II.")
        else:
            print(f"M_interf({cs}) = vuoto (proprieta strutturale della topologia DSB).")

        # ----------------------------------------------------------------
        # Fase I - StatForecaster: training su nominali
        # ----------------------------------------------------------------
        _sub(f"Fase I - StatForecaster (training su {len(nominal)} nominali)")

        t0 = time.time()
        fc = StatForecaster(config)
        fc.fit(feats_nom, nominal_snapshots=nominal)
        routing       = fc.get_model_routing()
        elapsed_fit   = time.time() - t0

        routing_counts = Counter(routing.values())
        print(f"Tempo fit: {elapsed_fit:.1f}s")
        print(f"Routing:   {dict(routing_counts)}")
        for model_name in sorted(routing_counts):
            sample_keys = [k for k, m in routing.items() if m == model_name]
            print(f"  {model_name} ({routing_counts[model_name]} feature):")
            for k in sample_keys[:4]:
                print(f"    {k}")
            if len(sample_keys) > 4:
                print(f"    ... e altri {len(sample_keys) - 4}")

        # Forecast globale unico - riusato per OGNI finestra anomala
        print(f"\nGenerazione forecast globale (no rolling window)...")
        t0 = time.time()
        fcast_global  = fc.predict()
        elapsed_pred  = time.time() - t0
        print(f"Tempo predict: {elapsed_pred:.1f}s  |  Feature previste: {len(fcast_global)}")
        print(f"Nota: questo forecast viene riusato identico su tutte le {len(anomalous)} "
              f"finestre anomale. Il training fisso sui nominali e la scelta architettuale "
              f"che produce lead_time=1 su DSB (latenza nominale > soglia SLA).")

        # ----------------------------------------------------------------
        # Fase II - CausalAnalyzer
        # ----------------------------------------------------------------
        _sub("Fase II - CausalAnalyzer (analisi causale su nominali)")

        t0 = time.time()
        ca           = CausalAnalyzer(config, topology)
        causal_graph = ca.analyze(cs, feats_nom)
        elapsed_ca   = time.time() - t0

        edges_c  = causal_graph.get("edges", [])
        chains_c = causal_graph.get("cross_property_chains", [])
        confirmed_c = [c for c in chains_c if c.get("confirmed")]

        print(f"Tempo analisi: {elapsed_ca:.1f}s")
        print(f"Link causali identificati: {len(edges_c)}")
        if edges_c:
            linear_c    = [e for e in edges_c if e["type"] == "linear"]
            nonlinear_c = [e for e in edges_c if e["type"] == "nonlinear"]
            print(f"  linear (Granger):     {len(linear_c)}")
            print(f"  nonlinear (TE):       {len(nonlinear_c)}")
            for e in edges_c[:6]:
                print(f"  [{e['type']:<10}] {e['source']:<55} -> {e['target']}")
                print(f"              intensita={e['intensity']:.4f}  "
                      f"lag={e.get('lag', 'N/A')}")
            if len(edges_c) > 6:
                print(f"  ... e altri {len(edges_c) - 6} link")

        print(f"\nCatene cross-property: {len(chains_c)} totali, {len(confirmed_c)} confirmed")
        for chain in confirmed_c[:5]:
            print(f"  [{chain['source_cs']} -> {cs}]  "
                  f"{' -> '.join(chain['chain'])}")
        if len(confirmed_c) > 5:
            print(f"  ... e altre {len(confirmed_c) - 5}")

        # ----------------------------------------------------------------
        # Fase III - StructuralMonitor: training su nominali
        # ----------------------------------------------------------------
        _sub(f"Fase III - StructuralMonitor (training su {len(nominal)} nominali)")

        t0  = time.time()
        mon = StructuralMonitor(config, topology, pbo)
        mon.fit(cs, feats_nom, nominal, weight_nominal, gold)
        print(f"Tempo fit monitor: {time.time() - t0:.1f}s")

        ag = AlertGenerator(config, topology)

        # ----------------------------------------------------------------
        # Inference su snapshot anomali
        # ----------------------------------------------------------------
        _sub(f"Inference su {len(anomalous)} finestre anomale")

        alerts: list[dict]          = []
        monitor_results: list[dict] = []
        report_every = max(1, len(anomalous) // 10)
        t_inf = time.time()

        for idx, snap in enumerate(anomalous):
            if idx % report_every == 0:
                print(f"  [{idx:>6}/{len(anomalous)}]  "
                      f"ts={snap['timestamp']}  "
                      f"fault={snap.get('anomaly_type','?')}  "
                      f"elapsed={time.time()-t_inf:.0f}s")

            # Feature per il singolo snapshot corrente (usate da monitor)
            feats_snap = fs.select_features(cs, [snap])

            # Pesi PBO del singolo snapshot corrente
            w_curr = pbo.compute_transition_weights([snap])

            # Fase III: monitoraggio (accumula stato CUSUM tra finestre)
            m_res = mon.monitor(cs, feats_snap, w_curr, snap["timestamp"])
            m_res["timestamp"]    = snap["timestamp"]
            m_res["anomaly_type"] = snap.get("anomaly_type")
            monitor_results.append(m_res)

            # Fase IV: generazione alert (forecast globale fisso)
            alert = ag.generate(
                cs, fcast_global, causal_graph, m_res, snap["timestamp"]
            )
            if alert is not None:
                alert["anomaly_type"] = snap.get("anomaly_type")
                alerts.append(alert)

        mon.reset_cusum()
        elapsed_inf = time.time() - t_inf
        print(f"  [{len(anomalous)}/{len(anomalous)}]  Completato in {elapsed_inf:.0f}s")

        # ----------------------------------------------------------------
        # Riepilogo per CS
        # ----------------------------------------------------------------
        _sub(f"Riepilogo - {cs}")

        mst = _monitor_stats(monitor_results)
        ast = _alert_stats(alerts, len(anomalous))
        n   = len(anomalous)

        print(f"Segnali Fase III su {n} finestre anomale:")
        print(f"  base_signal (threshold+zscore): {_pct(round(mst['base_signal_rate']*n), n)}")
        print(f"  if_signal   (Isolation Forest): {_pct(round(mst['if_signal_rate']*n), n)}")
        print(f"  cusum_signal (EWMA+CUSUM):      {_pct(round(mst['cusum_signal_rate']*n), n)}")
        print(f"  structural_confirmed:            {_pct(round(mst['structural_confirmed_rate']*n), n)}")

        if mst.get("pas_values"):
            pv = mst["pas_values"]
            print(f"  PAS: min={min(pv):.6f}  max={max(pv):.6f}  "
                  f"costante={'SI' if max(pv)-min(pv)<1e-9 else 'NO'}")
        if mst.get("frob_values"):
            fv = mst["frob_values"]
            print(f"  Frobenius: min={min(fv):.6f}  max={max(fv):.6f}  "
                  f"zero={'SI' if max(fv)<1e-9 else 'NO'}")

        cs_cusum_max = max(mst["cusum_stats"]) if mst.get("cusum_stats") else 0.0
        print(f"  cusum_stat max raggiunto: {cs_cusum_max:.6f}  "
              f"(soglia alert: {config.load_pipeline_params()['anomaly_detection']['cusum']['alert_threshold']})")

        print(f"\nAlert Fase IV su {n} finestre anomale:")
        print(f"  Generati (recall):       {_pct(ast['count'], n)}")
        for level in ("red", "orange", "yellow"):
            cnt = ast["criticality"].get(level, 0)
            if cnt > 0 or ast["count"] > 0:
                print(f"  {level.upper():8s}:             {_pct(cnt, ast['count'])}")

        lt_mean = ast.get("lead_time_steps_mean")
        if lt_mean is not None:
            print(f"  Lead time medio:         {lt_mean:.2f} step "
                  f"= {lt_mean * step_h:.1f} ore (semantica classificazione)")
            print(f"  Distribuzione lead time: {ast['lead_time_dist']}")

        print(f"  Root cause rate:         {_pct(round(ast['root_cause_rate']*ast['count']), ast['count'])}")
        print(f"  Cross-property rate:     {_pct(round(ast['cross_property_rate']*ast['count']), ast['count'])}")
        print(f"  Uncertainty flag rate:   {_pct(round(ast['uncertainty_flag_rate']*ast['count']), ast['count'])}")

        if ast["root_cause_top5"]:
            print(f"\nRoot cause (top 5):")
            for rc, cnt in ast["root_cause_top5"].items():
                print(f"  {rc}: {cnt} ({cnt/ast['count']*100:.1f}%)")

        if ast["critical_arc_top5"]:
            print(f"Critical arc (top 5):")
            for arc, cnt in ast["critical_arc_top5"].items():
                print(f"  {arc}: {cnt} ({cnt/ast['count']*100:.1f}%)")

        # Cross-property: esempio prima catena confermata
        first_cp = next((a for a in alerts if a.get("cross_property_interference")), None)
        if first_cp:
            print(f"\nEsempio cross-property interference:")
            print(f"  Provenienza: {first_cp['cross_property_interference']}")
            print(f"  Catena:      {first_cp.get('causal_chain', [])}")

        # Esempio alert completo (primo della lista)
        if alerts:
            _sub("Esempio alert strutturato (primo)")
            a = alerts[0]
            for field in ("compliance_set", "property_at_risk", "criticality",
                          "lead_time_steps", "lead_time_hours", "sla_threshold",
                          "sla_bound", "critical_arc", "root_cause",
                          "cross_property_interference", "causal_chain",
                          "model_uncertainty_flag", "anomaly_type"):
                print(f"  {field:<35}: {a.get(field)}")
            ss = a.get("structural_signals", {})
            print(f"  structural_signals:")
            for sk, sv in ss.items():
                print(f"    {sk:<30}: {sv}")
            agg = a.get("aggregated_forecast", [])
            if agg:
                print(f"  aggregated_forecast (primi 6): "
                      f"{[round(v, 3) for v in agg[:6]]}")

        elapsed_cs = time.time() - t_cs
        print(f"\nTempo totale {cs}: {elapsed_cs:.0f}s")

        results_cs[cs] = {
            "feature_count":     len(feats_nom),
            "feature_breakdown": {"node": n_node, "edge": n_edge, "interf": n_interf},
            "model_routing":     dict(routing_counts),
            "causal_graph_summary": {
                "edges":            len(edges_c),
                "cross_property":   len(chains_c),
                "confirmed":        len(confirmed_c),
            },
            "monitor_stats": {k: v for k, v in mst.items()
                              if k not in ("pas_values", "frob_values", "cusum_stats")},
            "alert_stats":   ast,
            "alerts":        alerts,
            "monitor_results": [
                {k: _safe(v) for k, v in m.items()
                 if not isinstance(v, list) or k in ("threshold_violations", "zscore_violations")}
                for m in monitor_results
            ],
        }

    # -----------------------------------------------------------------------
    # RIEPILOGO FINALE
    # -----------------------------------------------------------------------
    _sec("RIEPILOGO FINALE")

    elapsed_total = time.time() - t_global
    print(f"Dataset: {len(all_snapshots)} snapshot totali  "
          f"({len(nominal)} nominali, {n_total_anomalous_unfiltered} anomali)")
    print(f"Inference eseguita su: {len(anomalous)} snapshot anomali\n")

    for cs, res in results_cs.items():
        ast = res["alert_stats"]
        mst = res["monitor_stats"]
        crit = ast.get("criticality", {})
        print(f"{'='*40}")
        print(f"{cs}")
        print(f"  Alert:    {ast['count']}/{len(anomalous)} ({ast['count']/len(anomalous)*100:.1f}%)")
        for level in ("red", "orange", "yellow"):
            cnt = crit.get(level, 0)
            if cnt > 0:
                print(f"  {level.upper():8s}: {cnt} ({cnt/max(ast['count'],1)*100:.1f}%)")
        lt = ast.get("lead_time_steps_mean")
        if lt:
            print(f"  Lead time medio: {lt:.2f} step")
        print(f"  base_signal:    {mst['base_signal_rate']*100:.1f}%  "
              f"if_signal: {mst['if_signal_rate']*100:.1f}%  "
              f"cusum: {mst['cusum_signal_rate']*100:.1f}%  "
              f"confirmed: {mst['structural_confirmed_rate']*100:.1f}%")
        print(f"  root_cause:     {ast['root_cause_rate']*100:.1f}%  "
              f"cross_prop: {ast['cross_property_rate']*100:.1f}%  "
              f"uncertainty: {ast['uncertainty_flag_rate']*100:.1f}%")

    print(f"\nTempo di esecuzione totale: {elapsed_total:.0f}s")

    # -----------------------------------------------------------------------
    # Salvataggio JSON
    # -----------------------------------------------------------------------
    output_data = {
        "dataset_stats":   dataset_stats,
        "pbo_diagnostics": {k: {kk: _safe(vv) for kk, vv in v.items()}
                            for k, v in pbo_diagnostics.items()},
        "compliance_sets": results_cs,
        "elapsed_seconds": _safe(elapsed_total),
    }

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as fh:
            json.dump(output_data, fh, indent=2, default=str)
        print(f"\nRisultati salvati in: {out.resolve()}")

    return output_data


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Standalone pipeline runner - Hybrid Hypergraph-ATG",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--output",
        default="results/pipeline_results.json",
        help="Percorso output JSON (default: results/pipeline_results.json)",
    )
    parser.add_argument(
        "--fault-type",
        dest="fault_type",
        choices=["cpu", "mem", "net", "cpu_mem"],
        default=None,
        help="Esegue inference solo su questo tipo di fault.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Numero massimo di snapshot anomali su cui eseguire l'inference.",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="WARNING",
        help="Livello logging dei moduli interni (default: WARNING).",
    )
    args = parser.parse_args()

    # Sopprime i logger dei moduli interni per non inquinare l'output del runner
    logging.getLogger("src").setLevel(getattr(logging, args.log_level))
    logging.getLogger("prophet").setLevel(logging.ERROR)
    logging.getLogger("cmdstanpy").setLevel(logging.ERROR)
    logging.getLogger("numexpr").setLevel(logging.ERROR)

    run_pipeline(
        output_path=args.output,
        fault_type_filter=args.fault_type,
        limit=args.limit,
    )
