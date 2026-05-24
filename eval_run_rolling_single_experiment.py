"""
eval_run_rolling_single_experiment.py

Valutazione su un singolo esperimento GAMMA con training fisso sui nominali
e inference sequenziale su tutti gli snapshot.

Differenze rispetto al batch run (run_pipeline_user.py):
- Processa UN SOLO file CSV: il training e lo stato CUSUM partono da zero
  per quell'esperimento, senza saturazione da concatenazione di 184 file.
- Prophet viene addestrato una volta sui nominali del file scelto e non
  viene riaddestrato durante l'inference (training fisso).
- StructuralMonitor accumula il CUSUM dall'inizio dell'esperimento:
  su un file mem_* il CUSUM cresce durante la fase di fault e mostra
  il segnale graduali di degrado della cache.

File consigliati per test significativi:
  mem_sep22_10min_800_0_graph_2.csv   -- fault memoria, degrado graduale cache
  mem_sep25_10min_800_0_graph_2.csv   -- fault memoria, variante
  cpu_aug9_25min_400_0_graph_2.csv    -- fault CPU (CUSUM meno significativo)
"""

import json
import warnings
from collections import Counter
from pathlib import Path

import pandas as pd
from tqdm import tqdm

warnings.filterwarnings("ignore", category=RuntimeWarning, module="statsmodels")
warnings.filterwarnings("ignore", message="An input array is constant")

from src.utils.config_loader import ConfigLoader
from src.utils.logging_setup import LoggingSetup
from src.ingestion.user_converter import UserConverter
from src.layer1.topology_builder import TopologyBuilder
from src.layer2.atg_builder import ATGBuilder
from src.layer2.pbo_builder import PBOBuilder
from src.layer3.feature_selector import FeatureSelector
from src.phase1.stat_forecaster import StatForecaster
from src.phase2.causal_analyzer import CausalAnalyzer
from src.phase3.structural_monitor import StructuralMonitor
from src.phase4.alert_generator import AlertGenerator

LoggingSetup.configure("rolling_eval", "WARNING")

# ---------------------------------------------------------------------------
# Configurazione — modifica qui per cambiare file o compliance set
# ---------------------------------------------------------------------------

TOPOLOGY_PATH  = Path("config/topology.yaml")
PIPELINE_PATH  = Path("config/pipeline_params.yaml")

# Scegli il file da valutare. I file mem_* mostrano il CUSUM in azione.
USER_DATA_DIR  = Path("DATASET/processed_dataset_augmented/user/multi-modal-data-separate")
TARGET_FILE    = USER_DATA_DIR / "mem_sep22_10min_800_0_graph_2.csv"

# Output temporaneo per il singolo file convertito
SINGLE_CONV_DIR = Path("data/converted_single_user")

# Compliance set da valutare. H_cache e il piu interessante per mem_* files.
COMPLIANCE_SETS = ["H_crit", "H_cache"]

# ---------------------------------------------------------------------------
# Step 1 — Conversione del singolo file
# ---------------------------------------------------------------------------

SINGLE_CONV_DIR.mkdir(parents=True, exist_ok=True)

node_csv = SINGLE_CONV_DIR / "node_metrics.csv"
edge_csv = SINGLE_CONV_DIR / "edge_metrics.csv"
gt_csv   = SINGLE_CONV_DIR / "ground_truth.csv"

if not node_csv.exists():
    print(f"Conversione: {TARGET_FILE.name}")
    conv = UserConverter()
    node_df, edge_df, gt_df = conv.convert_file(TARGET_FILE)
    node_df.to_csv(node_csv, index=False)
    edge_df.to_csv(edge_csv, index=False)
    gt_df.to_csv(gt_csv,   index=False)
else:
    print(f"File gia convertiti in {SINGLE_CONV_DIR} — conversione saltata.")

# ---------------------------------------------------------------------------
# Step 2 — Build ATG
# ---------------------------------------------------------------------------

config   = ConfigLoader(TOPOLOGY_PATH, PIPELINE_PATH)
topology = TopologyBuilder(config)
topology.build()

atg       = ATGBuilder(config, node_csv, edge_csv, gt_csv)
snapshots = atg.build()
all_sorted = sorted(snapshots, key=lambda s: s["timestamp"])

nominal   = ATGBuilder.get_nominal_snapshots(snapshots)
anomalous = ATGBuilder.get_anomalous_snapshots(snapshots)

print(f"\nFile:            {TARGET_FILE.name}")
print(f"Snapshot totali: {len(all_sorted)}")
print(f"  Nominali:      {len(nominal)}")
print(f"  Anomali:       {len(anomalous)}")

if len(nominal) < 10:
    print("STOP: meno di 10 snapshot nominali. Scegli un file con piu finestre nominali.")
    raise SystemExit(1)

# Struttura temporale dell'esperimento
print("\nStruttura temporale:")
prev = all_sorted[0]["label"]
for i, s in enumerate(all_sorted):
    if s["label"] != prev:
        direction = f"label {prev} -> {s['label']}"
        print(f"  Finestra {i:>4}: {direction}")
        prev = s["label"]

# ---------------------------------------------------------------------------
# Step 3 — Training fisso su TUTTI i nominali dell'esperimento
# ---------------------------------------------------------------------------

pbo = PBOBuilder(config, topology)
weight_nom    = pbo.compute_transition_weights(nominal)
gold_standard = pbo.compute_gold_standard(weight_nom, nominal)

print(f"\nW_gold (PBO): {gold_standard}")
print("  -- valori diversi da 0.5 indicano un branch point reale nel grafo --")

all_results = {}

for CS in COMPLIANCE_SETS:
    print(f"\n{'='*60}")
    print(f"Training: {CS}")

    feature_sel  = FeatureSelector(config, topology)
    features_nom = feature_sel.select_features(CS, nominal)

    forecaster = StatForecaster(config)
    forecaster.fit(features_nom, nominal_snapshots=nominal)
    forecasts_fixed = forecaster.predict()

    causal_analyzer = CausalAnalyzer(config, topology)
    causal_graph    = causal_analyzer.analyze(CS, features_nom)

    # StructuralMonitor con CUSUM che parte da zero (single-file: no saturazione)
    monitor = StructuralMonitor(config, topology, pbo)
    monitor.fit(CS, features_nom, nominal, weight_nom, gold_standard)

    alert_gen = AlertGenerator(config, topology)

    # -----------------------------------------------------------------------
    # Step 4 — Inference su TUTTI gli snapshot in ordine temporale
    # -----------------------------------------------------------------------

    print(f"Inference: {len(all_sorted)} snapshot...")
    results = []

    for snap in tqdm(all_sorted, desc=CS):
        ts = snap["timestamp"]
        features_curr = feature_sel.select_features(CS, [snap])
        weight_curr   = pbo.compute_transition_weights([snap])
        mon_result    = monitor.monitor(CS, features_curr, weight_curr, ts)
        alert         = alert_gen.generate(CS, forecasts_fixed, causal_graph, mon_result, ts)

        results.append({
            "timestamp":    ts,
            "true_label":   snap["label"],
            "alert":        alert is not None,
            "criticality":  alert["criticality"] if alert else None,
            "lead_time":    alert["lead_time_steps"] if alert else None,
            "root_cause":   alert["root_cause"] if alert else None,
            "cross_prop":   alert["cross_property_interference"] if alert else None,
            "base_signal":  mon_result["base_signal"],
            "if_signal":    mon_result["if_signal"],
            "cusum_signal": mon_result["cusum_signal"],
        })

    all_results[CS] = results

# ---------------------------------------------------------------------------
# Step 5 — Analisi e stampa
# ---------------------------------------------------------------------------

for CS, results in all_results.items():
    n_nom = sum(1 for r in results if r["true_label"] == 0)
    n_ano = sum(1 for r in results if r["true_label"] == 1)
    tp = sum(1 for r in results if r["true_label"] == 1 and r["alert"])
    fp = sum(1 for r in results if r["true_label"] == 0 and r["alert"])
    fn = sum(1 for r in results if r["true_label"] == 1 and not r["alert"])
    tn = sum(1 for r in results if r["true_label"] == 0 and not r["alert"])
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1        = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    print(f"\n{'='*60}")
    print(f"RISULTATI — {CS}")
    print(f"{'='*60}")
    print(f"Finestre: {len(results)}  (nominali: {n_nom}, anomale: {n_ano})")
    print(f"\nConfusion matrix:")
    print(f"  TP={tp}  FP={fp}")
    print(f"  FN={fn}  TN={tn}")
    print(f"\nPrecision={precision:.3f}  Recall={recall:.3f}  F1={f1:.3f}")

    # Segnali strutturali sulle anomalie
    anom_res = [r for r in results if r["true_label"] == 1]
    if anom_res:
        n = len(anom_res)
        base  = sum(1 for r in anom_res if r["base_signal"])
        ifx   = sum(1 for r in anom_res if r["if_signal"])
        cusum = sum(1 for r in anom_res if r["cusum_signal"])
        print(f"\nSegnali su finestre anomale ({n} totali):")
        print(f"  base_signal:  {base}/{n} ({100*base/n:.1f}%)")
        print(f"  if_signal:    {ifx}/{n} ({100*ifx/n:.1f}%)")
        print(f"  cusum_signal: {cusum}/{n} ({100*cusum/n:.1f}%)")
        print("  -- cusum > 0 conferma che il PBO rileva la deriva del cache hit rate --")

    # Root cause e cross-property sugli alert su anomalie
    alert_on_anom = [r for r in results if r["true_label"] == 1 and r["alert"]]
    if alert_on_anom:
        rc  = Counter(r["root_cause"] for r in alert_on_anom)
        xp  = sum(1 for r in alert_on_anom if r["cross_prop"])
        crit = Counter(r["criticality"] for r in alert_on_anom)
        print(f"\nRoot cause: {rc.most_common(3)}")
        print(f"Cross-property interference: {xp}/{len(alert_on_anom)}")
        print(f"Criticita: {dict(crit)}")

    # Lead time
    lt_vals = [r["lead_time"] for r in results if r["true_label"] == 1 and r["lead_time"]]
    if lt_vals:
        print(f"\nDistribuzione lead_time (finestre anomale con alert):")
        for lt, cnt in sorted(Counter(lt_vals).items()):
            print(f"  lead_time={lt}: {cnt} finestre")

    # Early detection: alert nelle finestre nominali IMMEDIATAMENTE prima dell'anomalia
    first_anom = next((i for i, r in enumerate(results) if r["true_label"] == 1), None)
    if first_anom and first_anom > 0:
        pre_window = results[max(0, first_anom - 10):first_anom]
        pre_alerts = [r for r in pre_window if r["alert"]]
        if pre_alerts:
            print(f"\nEarly detection: {len(pre_alerts)} alert nelle {len(pre_window)}"
                  f" finestre pre-anomalia (prima anomalia a finestra {first_anom})")
        else:
            print(f"\nNessun alert nelle {len(pre_window)} finestre pre-anomalia.")

    # Sequenza temporale (mostra le 15 finestre intorno a ogni transizione)
    print(f"\nSequenza temporale (20 finestre intorno a ogni transizione nominale->anomalia):")
    print(f"{'i':>5} {'L':>2} {'A':>2} {'lt':>4} {'crit':>7} "
          f"{'base':>5} {'cusum':>6}")
    print("-" * 42)

    transitions = [
        i for i in range(1, len(results))
        if results[i-1]["true_label"] == 0 and results[i]["true_label"] == 1
    ]
    shown_indices = set()
    for t in transitions:
        for i in range(max(0, t - 8), min(len(results), t + 12)):
            shown_indices.add(i)

    for i in sorted(shown_indices):
        r    = results[i]
        lt   = str(r["lead_time"]) if r["lead_time"] else "-"
        crit = r["criticality"][:3] if r["criticality"] else "---"
        alt  = "Y" if r["alert"] else "-"
        bs   = "T" if r["base_signal"] else "F"
        cs_  = "T" if r["cusum_signal"] else "F"
        mark = " <-- FAULT INIZIA" if (i > 0 and results[i-1]["true_label"] == 0
                                         and r["true_label"] == 1) else ""
        print(f"{i:>5} {r['true_label']:>2} {alt:>2} {lt:>4} "
              f"{crit:>7} {bs:>5} {cs_:>6}{mark}")

# Salva JSON
out_path = Path("data/rolling_results_user.json")
with open(out_path, "w") as f:
    json.dump({cs: r for cs, r in all_results.items()}, f, default=str, indent=2)
print(f"\nRisultati salvati in {out_path}")