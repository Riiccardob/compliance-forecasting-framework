#!/usr/bin/env python3
"""
Runner per il corpus GAMMA augmentato con iniezione ramp.

Architettura:
  - Training GLOBALE: una sola sessione Prophet su tutti gli snapshot nominali
    (label=0) dell'intero corpus non escluso. I modelli imparano la distribuzione
    nominale globale, non quella di un singolo esperimento.
  - Buffer EWMA: resettato per ogni source_file → ciascun esperimento parte
    con CUSUM pulito e buffer pre-riscaldato sulle proprie ultime finestre nominali.

Differenza da run_pipeline_synthetic.py:
  Ogni esperimento è un source_file nel CSV globale, non una directory separata.
  Il training Prophet è unico e globale; il buffer EWMA è per-source_file.

Differenza da run_pipeline.py:
  run_pipeline.py usa predict() fisso (forecast nominale riusato). Qui si usa
  predict_adaptive() per ogni finestra anomala, con buffer EWMA resettato tra
  source_file (evita che lo stato CUSUM di un esperimento contamini il successivo).

Utilizzo:
  python run_pipeline_gamma_aug.py
  python run_pipeline_gamma_aug.py --log-level INFO
  python run_pipeline_gamma_aug.py --fault-type mem
  python run_pipeline_gamma_aug.py --output results/gamma_aug/summary.json
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

import pandas as pd

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

logger = LoggingSetup.configure("pipeline.gamma_aug", "INFO")

# ---------------------------------------------------------------------------
# Costanti
# ---------------------------------------------------------------------------

TOPOLOGY_PATH  = ROOT / "config" / "topology_gamma_aug.yaml"
PIPELINE_PATH  = ROOT / "config" / "pipeline_params.yaml"
RESULTS_DIR    = ROOT / "results" / "gamma_aug"
EXCLUDE_PREFIX = "cpu_aug12_25min_200_"
LOOKBACK       = 8   # finestre per il buffer EWMA di predict_adaptive

_LINE = "=" * 72
_DASH = "-" * 72


# ---------------------------------------------------------------------------
# Helpers di output
# ---------------------------------------------------------------------------

def _sec(title: str) -> None:
    print(f"\n{_LINE}\n  {title}\n{_LINE}")


def _sub(title: str) -> None:
    print(f"\n{_DASH}\n  {title}\n{_DASH}")


def _pct(num: int | float, den: int | float, decimals: int = 1) -> str:
    if den == 0:
        return "0/0 (N/A)"
    return f"{num}/{den} ({num / den * 100:.{decimals}f}%)"


def _safe(v: Any) -> Any:
    if v is None:
        return None
    try:
        if math.isnan(float(v)):
            return None
        return float(v) if not isinstance(v, int) else int(v)
    except (TypeError, ValueError):
        return str(v)


# ---------------------------------------------------------------------------
# Buffer EWMA
# ---------------------------------------------------------------------------

def _update_buffer(
    buf: dict[str, pd.DataFrame],
    feats: dict[str, pd.DataFrame],
    max_lookback: int = LOOKBACK,
) -> None:
    """Aggiunge l'osservazione corrente al buffer di lookback per predict_adaptive.

    Parameters
    ----------
    buf:
        Buffer del compliance set corrente: {feat_key: DataFrame con col "value"}.
    feats:
        Output di FeatureSelector.select_features() per un singolo snapshot.
    max_lookback:
        Numero massimo di osservazioni da conservare (tail).
    """
    for key, feat_df in feats.items():
        if len(feat_df) == 0:
            continue
        val = float(feat_df["value"].mean())
        new_row = pd.DataFrame({"value": [val]})
        if key not in buf:
            buf[key] = new_row
        else:
            buf[key] = pd.concat([buf[key], new_row], ignore_index=True).tail(max_lookback)


# ---------------------------------------------------------------------------
# Costruzione JSON per source_file / compliance set
# ---------------------------------------------------------------------------

def _build_cs_result(
    cs: str,
    alerts: list[dict],
    mon_results: list[dict],
    n_anomalous: int,
    topology_type: str,
) -> dict:
    """Costruisce il dizionario di risultati per un compliance set e source_file."""
    n_alerts = len(alerts)
    lt_dist: dict[str, int] = {}
    crit_dist: dict[str, int] = {}
    rc_counter: Counter = Counter()
    cross_counter: Counter = Counter()
    unc_count = 0

    for a in alerts:
        lt = str(a.get("lead_time_steps", 0))
        lt_dist[lt] = lt_dist.get(lt, 0) + 1
        crit = str(a.get("criticality", "unknown")).upper()
        crit_dist[crit] = crit_dist.get(crit, 0) + 1
        rc = a.get("root_cause")
        if rc is not None:
            rc_counter[str(rc)] += 1
        cp = a.get("cross_property_interference")
        if cp is not None:
            cross_counter[str(cp)] += 1
        if a.get("model_uncertainty_flag", False):
            unc_count += 1

    n_mon = len(mon_results)
    cusum_signals = sum(1 for r in mon_results if r.get("cusum_signal", False))
    if_signals    = sum(1 for r in mon_results if r.get("if_signal", False))

    # Valori strutturali: PAS per topologia linear, Frobenius per parallel
    if topology_type == "linear":
        struct_vals = [
            _safe(r.get("pas_value"))
            for r in mon_results
            if r.get("pas_value") is not None
        ]
    else:
        struct_vals = [
            _safe(r.get("frobenius_distance"))
            for r in mon_results
            if r.get("frobenius_distance") is not None
        ]

    cross_property = cross_counter.most_common(1)[0][0] if cross_counter else None

    return {
        "alert_count":                  n_alerts,
        "total_anomalous_windows":      n_anomalous,
        "lead_time_distribution":       lt_dist,
        "criticality_distribution":     crit_dist,
        "cusum_signal_rate":            cusum_signals / max(n_mon, 1),
        "if_signal_rate":               if_signals    / max(n_mon, 1),
        "frobenius_values":             struct_vals,
        "root_cause_top3":              rc_counter.most_common(3),
        "cross_property_interference":  cross_property,
        "model_uncertainty_flag_rate":  unc_count / max(n_alerts, 1),
    }


# ---------------------------------------------------------------------------
# Runner principale
# ---------------------------------------------------------------------------

def run(
    output_path: str | None = None,
    fault_type_filter: str | None = None,
    log_level: str = "WARNING",
) -> None:
    """Esegue la pipeline GAMMA-augmented con training globale e buffer per-source_file."""
    t_global = time.time()

    # -----------------------------------------------------------------------
    # FASE 1 - Caricamento dati globali
    # -----------------------------------------------------------------------
    _sec("FASE 1 - CONFIGURAZIONE E CARICAMENTO DATI")

    config = ConfigLoader(TOPOLOGY_PATH, PIPELINE_PATH)
    topo_cfg     = config.load_topology()
    pipeline_cfg = config.load_pipeline_params()
    cs_names     = list(topo_cfg["compliance_sets"].keys())
    data_paths   = topo_cfg["data_paths"]

    print(f"Topology:         {TOPOLOGY_PATH.name}")
    print(f"Compliance set:   {cs_names}")

    topology = TopologyBuilder(config)
    topology.build()

    node_csv = ROOT / data_paths["node_metrics_csv"]
    edge_csv = ROOT / data_paths["edge_metrics_csv"]
    gt_csv   = ROOT / data_paths["ground_truth_csv"]

    logger.info("Lettura CSV: %s | %s | %s", node_csv, edge_csv, gt_csv)
    t0 = time.time()
    node_df_all = pd.read_csv(node_csv)
    edge_df_all = pd.read_csv(edge_csv)
    gt_df_all   = pd.read_csv(gt_csv)
    print(f"CSV caricati in {time.time() - t0:.1f}s  "
          f"(node={len(node_df_all)}, edge={len(edge_df_all)}, gt={len(gt_df_all)} righe)")

    # Mappa source_file → fault_type (prima occorrenza)
    sf_to_fault: dict[str, str] = (
        gt_df_all.groupby("source_file")["fault_type"].first().to_dict()
    )

    all_sfs  = sorted(gt_df_all["source_file"].unique())
    proc_sfs = sorted(
        [sf for sf in all_sfs if not sf.startswith(EXCLUDE_PREFIX)],
        key=lambda sf: (sf_to_fault.get(sf, ""), sf),
    )
    excl_sfs = [sf for sf in all_sfs if sf.startswith(EXCLUDE_PREFIX)]

    if fault_type_filter:
        proc_sfs = [
            sf for sf in proc_sfs
            if sf_to_fault.get(sf, "") == fault_type_filter
        ]
        print(f"Filtro fault_type={fault_type_filter!r}: "
              f"{len(proc_sfs)} source_file selezionati")

    print(f"\nSource file totali: {len(all_sfs)}")
    print(f"  Esclusi ({EXCLUDE_PREFIX!r}): {len(excl_sfs)}")
    print(f"  Da processare:                {len(proc_sfs)}")

    # -----------------------------------------------------------------------
    # Build snapshot per source_file + raccolta nominali globali
    # -----------------------------------------------------------------------
    _sub("Build ATG per source_file")

    atg = ATGBuilder(
        config,
        node_metrics_path=node_csv,
        edge_metrics_path=edge_csv,
        ground_truth_path=gt_csv,
    )

    sf_snapshots: dict[str, list[dict]] = {}
    all_nominal: list[dict] = []
    seen_ts_nominal: set[int] = set()  # deduplication per training

    t0 = time.time()
    for sf in proc_sfs:
        sf_node = node_df_all[node_df_all["source_file"] == sf].copy()
        sf_edge = edge_df_all[edge_df_all["source_file"] == sf].copy()
        sf_gt   = gt_df_all[gt_df_all["source_file"] == sf].copy()

        snaps = atg.build(node_df=sf_node, edge_df=sf_edge, gt_df=sf_gt)
        sf_snapshots[sf] = snaps

        # Colleziona nominali senza timestamp duplicati tra source_file diversi
        # (replications dello stesso giorno condividono timestamp µs)
        for s in snaps:
            if s["label"] == 0 and s["timestamp"] not in seen_ts_nominal:
                seen_ts_nominal.add(s["timestamp"])
                all_nominal.append(s)

    print(f"Build ATG completato in {time.time() - t0:.1f}s")
    print(f"Snapshot nominali globali (deduplicated per timestamp): {len(all_nominal)}")

    n_nom_total = sum(
        len(ATGBuilder.get_nominal_snapshots(sf_snapshots[sf]))
        for sf in proc_sfs
    )
    n_anom_total = sum(
        len(ATGBuilder.get_anomalous_snapshots(sf_snapshots[sf]))
        for sf in proc_sfs
    )
    print(f"Corpus processato: {n_nom_total} nominali, {n_anom_total} anomali "
          f"(su {len(proc_sfs)} source_file)")

    # -----------------------------------------------------------------------
    # FASE 2 - Training GLOBALE (una sola volta)
    # -----------------------------------------------------------------------
    _sec("FASE 2 - TRAINING GLOBALE SU NOMINALI")

    pbo = PBOBuilder(config, topology)
    t0 = time.time()
    weight_nominal = pbo.compute_transition_weights(all_nominal)
    gold           = pbo.compute_gold_standard(weight_nominal, all_nominal)
    print(f"PBO gold standard calcolato su {len(all_nominal)} nominali ({time.time()-t0:.1f}s)")

    fs = FeatureSelector(config, topology)

    per_cs: dict[str, dict[str, Any]] = {}

    for cs in cs_names:
        _sub(f"Training CS: {cs}")
        cs_cfg    = topo_cfg["compliance_sets"][cs]
        ttype     = cs_cfg.get("topology_type", "")

        feats_nom = fs.select_features(cs, all_nominal)
        print(f"  Feature: {len(feats_nom)}  "
              f"(node={len([k for k in feats_nom if k.startswith('node:')])}, "
              f"edge={len([k for k in feats_nom if k.startswith('edge:')])}, "
              f"interf={len([k for k in feats_nom if k.startswith('interf:')])})")

        # StatForecaster
        t0 = time.time()
        fc = StatForecaster(config)
        fc.fit(feats_nom, nominal_snapshots=all_nominal)
        if not fc._is_fitted:
            raise RuntimeError(
                f"StatForecaster non fittato per {cs} - "
                "verificare che fit() sia chiamato prima del loop."
            )
        print(f"  StatForecaster fit: {time.time()-t0:.1f}s  routing={dict(Counter(fc.get_model_routing().values()))}")

        # CausalAnalyzer
        t0 = time.time()
        ca           = CausalAnalyzer(config, topology)
        causal_graph = ca.analyze(cs, feats_nom)
        print(f"  CausalAnalyzer: {len(causal_graph.get('edges', []))} link causali  "
              f"({time.time()-t0:.1f}s)")

        # StructuralMonitor
        t0 = time.time()
        mon = StructuralMonitor(config, topology, pbo)
        mon.fit(cs, feats_nom, all_nominal, weight_nominal, gold)
        print(f"  StructuralMonitor fit: {time.time()-t0:.1f}s")

        ag = AlertGenerator(config, topology)

        per_cs[cs] = {
            "feats_nom":    feats_nom,
            "fc":           fc,
            "causal_graph": causal_graph,
            "mon":          mon,
            "ag":           ag,
            "ttype":        ttype,
        }

    # -----------------------------------------------------------------------
    # FASE 3 - Inference per-source_file
    # -----------------------------------------------------------------------
    _sec("FASE 3 - INFERENCE PER SOURCE_FILE")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Buffer EWMA separati per CS (resettati per ogni source_file)
    observation_buffers: dict[str, dict[str, pd.DataFrame]] = {
        cs: {} for cs in cs_names
    }

    all_json_results: dict[str, dict] = {}
    n_processed = 0
    n_skipped_no_anom = 0

    for sf in proc_sfs:
        snaps    = sf_snapshots[sf]
        sf_nom   = ATGBuilder.get_nominal_snapshots(snaps)
        sf_anom  = ATGBuilder.get_anomalous_snapshots(snaps)

        if len(sf_anom) == 0:
            logger.debug("Skipping %s: no anomalous windows", sf)
            n_skipped_no_anom += 1
            continue

        fault_type = sf_to_fault.get(sf, "")
        logger.info(
            "Processing sf=%s  fault=%s  nom=%d  anom=%d",
            sf, fault_type, len(sf_nom), len(sf_anom),
        )

        # Reset CUSUM e buffer per questo source_file
        for cs in cs_names:
            per_cs[cs]["mon"].reset_cusum()
            observation_buffers[cs] = {}

        # Pre-warm: ultime min(2, len(nominali)) finestre nominali di QUESTO source_file
        prewarm_snaps = sf_nom[-min(5, len(sf_nom)):]
        for snap in prewarm_snaps:
            for cs in cs_names:
                feats = fs.select_features(cs, [snap])
                _update_buffer(observation_buffers[cs], feats)

        sf_alerts:      dict[str, list[dict]] = {cs: [] for cs in cs_names}
        sf_mon_results: dict[str, list[dict]] = {cs: [] for cs in cs_names}

        # Loop sulle finestre anomale ordinate per timestamp
        for snap in sorted(sf_anom, key=lambda s: s["timestamp"]):
            ts: int = snap["timestamp"]

            for cs in cs_names:
                try:
                    feats  = fs.select_features(cs, [snap])
                    w_curr = pbo.compute_transition_weights([snap])
                    m_res  = per_cs[cs]["mon"].monitor(cs, feats, w_curr, ts)
                    sf_mon_results[cs].append(m_res)

                    # Forecast: predict_adaptive se buffer sufficientemente pieno
                    buf = observation_buffers[cs]
                    recent_obs = {k: df for k, df in buf.items() if len(df) >= 1}

                    if recent_obs and all(len(df) >= 2 for df in recent_obs.values()):
                        forecasts = per_cs[cs]["fc"].predict_adaptive(recent_obs)
                    else:
                        forecasts = per_cs[cs]["fc"].predict()

                    alert = per_cs[cs]["ag"].generate(
                        cs, forecasts, per_cs[cs]["causal_graph"], m_res, ts
                    )
                    if alert is not None:
                        sf_alerts[cs].append(alert)

                    # Aggiorna buffer DOPO il forecast (l'osservazione corrente
                    # alimenta il passo successivo, non quello corrente)
                    _update_buffer(observation_buffers[cs], feats)

                except Exception as exc:
                    logger.warning(
                        "Errore sf=%s cs=%s ts=%d: %s", sf, cs, ts, exc
                    )

        # Costruisce il JSON di risultato per questo source_file
        sf_result: dict[str, Any] = {
            "source_file": sf,
            "fault_type":  fault_type,
            "fault_type": sf_to_fault.get(sf, ""),  # fault_type già estratto
        }
        for cs in cs_names:
            sf_result[cs] = _build_cs_result(
                cs,
                sf_alerts[cs],
                sf_mon_results[cs],
                len(sf_anom),
                per_cs[cs]["ttype"],
            )

        # Salva JSON per questo source_file
        json_name = sf.replace(".csv", ".json")
        json_path = RESULTS_DIR / json_name
        with json_path.open("w", encoding="utf-8") as fh:
            json.dump(sf_result, fh, indent=2, default=str)
        logger.info("Salvato: %s", json_path)

        all_json_results[sf] = sf_result
        n_processed += 1

    print(f"\nSource file processati: {n_processed}  "
          f"(saltati senza anomalie: {n_skipped_no_anom})")

    # -----------------------------------------------------------------------
    # FASE 4 - Stima FP su finestre nominali (pass separato, CUSUM reset)
    # -----------------------------------------------------------------------
    _sub("FP pass su finestre nominali globali")

    # Reset CUSUM e buffer per il FP pass
    for cs in cs_names:
        per_cs[cs]["mon"].reset_cusum()
    fp_alerts:  dict[str, list[dict]]              = {cs: [] for cs in cs_names}

    t0 = time.time()
    for snap in sorted(all_nominal, key=lambda s: s["timestamp"]):
        ts = snap["timestamp"]
        for cs in cs_names:
            try:
                feats  = fs.select_features(cs, [snap])
                w_curr = pbo.compute_transition_weights([snap])
                m_res  = per_cs[cs]["mon"].monitor(cs, feats, w_curr, ts)

                # Nel FP pass si usa sempre il forecast nominale fisso.
                # predict_adaptive() accumulerebbe un trend EWMA artificiale
                # scorrendo i nominali in sequenza, sovrastimando i FP.
                forecasts = per_cs[cs]["fc"].predict()

                alert = per_cs[cs]["ag"].generate(
                    cs, forecasts, per_cs[cs]["causal_graph"], m_res, ts
                )
                if alert is not None:
                    fp_alerts[cs].append(alert)

            except Exception as exc:
                logger.warning("FP pass errore cs=%s ts=%d: %s", cs, ts, exc)

    total_fp = sum(len(fp_alerts[cs]) for cs in cs_names)
    print(f"FP pass completato in {time.time()-t0:.1f}s  "
          f"({len(all_nominal)} finestre nominali)")
    for cs in cs_names:
        print(f"  {cs}: {len(fp_alerts[cs])} FP alert")

    # -----------------------------------------------------------------------
    # FASE 5 - Aggregazione e report finale
    # -----------------------------------------------------------------------
    _sec("GAMMA AUGMENTED - RIEPILOGO AGGREGATO")

    # Aggregazione per fault_type
    fault_types_present = sorted({sf_to_fault.get(sf, "") for sf in proc_sfs})
    agg: dict[str, dict[str, list]] = {
        ft: {cs: {"recalls": [], "lt_means": [], "cusum_rates": []}
             for cs in cs_names}
        for ft in fault_types_present
    }

    for sf, res in all_json_results.items():
        ft = sf_to_fault.get(sf, "")
        if ft not in agg:
            continue
        for cs in cs_names:
            cs_r = res.get(cs, {})
            n_anom = cs_r.get("total_anomalous_windows", 0)
            n_alert = cs_r.get("alert_count", 0)
            if n_anom > 0:
                agg[ft][cs]["recalls"].append(n_alert / n_anom)
            lt_raw = cs_r.get("lead_time_distribution", {})
            if lt_raw:
                lt_steps = [int(k) * v for k, v in lt_raw.items()]
                lt_total = sum(lt_raw.values())
                if lt_total > 0:
                    agg[ft][cs]["lt_means"].append(sum(lt_steps) / lt_total)
            agg[ft][cs]["cusum_rates"].append(cs_r.get("cusum_signal_rate", 0.0))

    # Global lead time distribution (H_crit)
    global_lt: Counter = Counter()
    global_crit: Counter = Counter()
    for res in all_json_results.values():
        cs_r = res.get(cs_names[0], {})
        for k, v in cs_r.get("lead_time_distribution", {}).items():
            global_lt[k] += v
        for k, v in cs_r.get("criticality_distribution", {}).items():
            global_crit[k] += v

    total_alerts_on_anom = sum(
        res.get(cs_names[0], {}).get("alert_count", 0)
        for res in all_json_results.values()
    )
    total_anom_windows = sum(
        res.get(cs_names[0], {}).get("total_anomalous_windows", 0)
        for res in all_json_results.values()
    )

    # Stampa tabella per fault_type
    n_nom_tot = len(all_nominal)

    print(f"\nCorpus: {n_nom_total + n_anom_total} snapshot - "
          f"{n_nom_total} nominali, {n_anom_total} anomali")
    print(f"Source file processati: {n_processed}  "
          f"(esclusi {len(excl_sfs)} + {n_skipped_no_anom} senza anomalie)")

    if fault_type_filter:
        print(f"Filtro fault_type: {fault_type_filter!r}")

    # Header tabella
    cs0, cs1 = cs_names[0], cs_names[1] if len(cs_names) > 1 else cs_names[0]
    print(f"\nPER FAULT TYPE (medie):")
    hdr = (
        f"  {'fault_type':<12} | "
        f"{'recall ' + cs0:<16} | "
        f"{'recall ' + cs1:<16} | "
        f"{'LT mean ' + cs0:<16} | "
        f"{'cusum ' + cs0:<14} | "
        f"{'cusum ' + cs1:<14}"
    )
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))

    for ft in fault_types_present:
        if not ft:
            continue
        vals0 = agg[ft][cs0]
        vals1 = agg[ft].get(cs1, {"recalls": [], "lt_means": [], "cusum_rates": []})

        recall0  = sum(vals0["recalls"])  / max(len(vals0["recalls"]), 1) * 100
        recall1  = sum(vals1["recalls"])  / max(len(vals1["recalls"]), 1) * 100
        lt_mean0 = sum(vals0["lt_means"]) / max(len(vals0["lt_means"]), 1)
        cusum0   = sum(vals0["cusum_rates"]) / max(len(vals0["cusum_rates"]), 1) * 100
        cusum1   = sum(vals1["cusum_rates"]) / max(len(vals1["cusum_rates"]), 1) * 100

        print(
            f"  {ft:<12} | "
            f"{recall0:>6.1f}%          | "
            f"{recall1:>6.1f}%          | "
            f"{lt_mean0:>6.2f}           | "
            f"{cusum0:>5.1f}%        | "
            f"{cusum1:>5.1f}%"
        )

    print(f"\nLEAD TIME DISTRIBUZIONE ({cs0}, tutti gli esperimenti):")
    print(f"  {dict(sorted(global_lt.items(), key=lambda x: int(x[0])))}")

    total_crit = sum(global_crit.values())
    if total_crit > 0:
        print(f"\nCRITICALITY ({cs0}):")
        for level in ("RED", "ORANGE", "YELLOW"):
            cnt = global_crit.get(level, 0)
            print(f"  {level:8s} {cnt / total_crit * 100:.0f}%  ({cnt})")
        no_alert = max(total_anom_windows - total_alerts_on_anom, 0)
        print(f"  {'nessun_alert':8s} "
              f"{no_alert / max(total_anom_windows, 1) * 100:.0f}%  ({no_alert})")

    print(f"\nFP SU NOMINALI: {total_fp} / {n_nom_tot} "
          f"({total_fp / max(n_nom_tot, 1) * 100:.2f}%)")
    for cs in cs_names:
        print(f"  {cs}: {len(fp_alerts[cs])} FP")

    print(f"\nRisultati per-esperimento salvati in {RESULTS_DIR}")

    elapsed = time.time() - t_global
    print(f"\nTempo totale: {elapsed:.0f}s")

    # -----------------------------------------------------------------------
    # Salvataggio JSON aggregato opzionale
    # -----------------------------------------------------------------------
    if output_path:
        summary = {
            "corpus": {
                "n_nominal":  n_nom_total,
                "n_anomalous": n_anom_total,
                "n_processed": n_processed,
                "n_excluded":  len(excl_sfs) + n_skipped_no_anom,
                "fault_type_filter": fault_type_filter,
            },
            "fp": {
                cs: len(fp_alerts[cs]) for cs in cs_names
            },
            "lead_time_dist": dict(global_lt),
            "criticality_dist": dict(global_crit),
            "per_source_file": {
                sf: {
                    cs: {
                        k: v for k, v in res[cs].items()
                        if k != "frobenius_values"  # lista potenzialmente grande
                    }
                    for cs in cs_names
                    if cs in res
                }
                for sf, res in all_json_results.items()
            },
            "elapsed_seconds": _safe(elapsed),
        }
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2, default=str)
        print(f"Riepilogo aggregato salvato in: {out.resolve()}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Pipeline GAMMA augmentata - training globale, buffer EWMA per-source_file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Path JSON per il riepilogo aggregato (opzionale).",
    )
    parser.add_argument(
        "--fault-type",
        dest="fault_type",
        choices=["cpu", "mem", "net", "cpu_mem"],
        default=None,
        help="Processa solo source_file con questo fault_type.",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="WARNING",
        help="Livello logging dei moduli interni (default: WARNING).",
    )
    args = parser.parse_args()

    logging.getLogger("src").setLevel(getattr(logging, args.log_level))
    logging.getLogger("prophet").setLevel(logging.ERROR)
    logging.getLogger("cmdstanpy").setLevel(logging.ERROR)
    logging.getLogger("numexpr").setLevel(logging.ERROR)

    run(
        output_path=args.output,
        fault_type_filter=args.fault_type,
        log_level=args.log_level,
    )
