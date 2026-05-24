# eval_framework.py
# Valutazione quantitativa: confusion matrix + early detection analysis

import json
from pathlib import Path
from collections import defaultdict

import pandas as pd

from src.utils.config_loader import ConfigLoader
from src.utils.logging_setup import LoggingSetup
from src.layer2.atg_builder import ATGBuilder

LoggingSetup.configure("eval", "WARNING")

config    = ConfigLoader(
    topology_path=Path("config/topology.yaml"),
    pipeline_path=Path("config/pipeline_params.yaml"),
)
node_csv  = Path("data/converted/node_metrics.csv")
edge_csv  = Path("data/converted/edge_metrics.csv")
gt_csv    = Path("data/converted/ground_truth.csv")

atg       = ATGBuilder(config, node_csv, edge_csv, gt_csv)
snapshots = atg.build()

# Indice ground truth: timestamp → label
gt_index = {s["timestamp"]: s["label"] for s in snapshots}
all_ts   = sorted(gt_index.keys())
ts_set   = set(all_ts)

# ---------------------------------------------------------------------------
# Carica gli alert prodotti dallo script precedente.
# Se non li hai serializzati su disco, aggiungere al run_pipeline_v2.py:
#   import json
#   with open("data/alerts_H_crit.json", "w") as f:
#       json.dump(results["H_crit"]["alerts"], f, default=str)
#   with open("data/alerts_H_cache.json", "w") as f:
#       json.dump(results["H_cache"]["alerts"], f, default=str)
# ---------------------------------------------------------------------------

for cs in ["H_crit", "H_cache"]:
    alert_path = Path(f"data/alerts_{cs}.json")
    if not alert_path.exists():
        print(f"File {alert_path} non trovato. Aggiungi il salvataggio a "
              f"run_pipeline_v2.py (vedi commento sopra).")
        continue

    with open(alert_path) as f:
        alerts = json.load(f)

    # Timestamp degli alert
    alert_ts = set(int(a["timestamp"]) for a in alerts)

    # ---------------------------------------------------------------------------
    # Confusion matrix sulle finestre anomale
    # ---------------------------------------------------------------------------

    # TP: alert su finestra anomala (label=1)
    # FP: alert su finestra nominale (label=0)
    # FN: finestra anomala senza alert
    # TN: finestra nominale senza alert

    tp = sum(1 for ts in alert_ts if gt_index.get(ts) == 1)
    fp = sum(1 for ts in alert_ts if gt_index.get(ts) == 0)
    fn = sum(1 for ts, lab in gt_index.items() if lab == 1 and ts not in alert_ts)
    tn = sum(1 for ts, lab in gt_index.items() if lab == 0 and ts not in alert_ts)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1        = (2 * precision * recall / (precision + recall)
                 if (precision + recall) > 0 else 0.0)
    fpr       = fp / (fp + tn) if (fp + tn) > 0 else 0.0

    print(f"\n{'='*50}")
    print(f"  {cs} — Confusion Matrix")
    print(f"{'='*50}")
    print(f"  TP (alert su anomalia)     : {tp}")
    print(f"  FP (alert su nominale)     : {fp}")
    print(f"  FN (anomalia senza alert)  : {fn}")
    print(f"  TN (nominale senza alert)  : {tn}")
    print(f"  Precision : {precision:.3f}")
    print(f"  Recall    : {recall:.3f}")
    print(f"  F1        : {f1:.3f}")
    print(f"  FPR       : {fpr:.3f}")

    # ---------------------------------------------------------------------------
    # Early detection: quante anomalie vengono coperte da un alert
    # nella finestra PRECEDENTE (lead_time_steps finestre prima)?
    # ---------------------------------------------------------------------------
    # Sul run attuale lead_time=1 costante → il framework identifica
    # la violazione alla stessa finestra in cui avviene.
    # Questo confronta ATG (0 step anticipazione) vs Framework (lead_time step).

    # Raggruppa le finestre anomale consecutive in episodi
    anomalous_ts = sorted(ts for ts, lab in gt_index.items() if lab == 1)

    episodes = []
    if anomalous_ts:
        ep_start = anomalous_ts[0]
        ep_prev  = anomalous_ts[0]
        for ts in anomalous_ts[1:]:
            # gap > 60s (12 finestre da 5s) = episodio separato
            if ts - ep_prev > 60_000_000:
                episodes.append((ep_start, ep_prev))
                ep_start = ts
            ep_prev = ts
        episodes.append((ep_start, ep_prev))

    print(f"\n  Episodi anomali distinti : {len(episodes)}")

    # Per ogni episodio, verifica se il framework ha generato un alert
    # PRIMA dell'inizio dell'episodio (true early detection)
    nominal_ts_sorted = sorted(ts for ts, lab in gt_index.items() if lab == 0)

    early_alerts = 0
    no_early     = 0
    lead_times_before = []

    for ep_start, ep_end in episodes:
        # Cerca alert su finestre nominali nelle 60s precedenti l'episodio
        window_before_start = ep_start - 60_000_000  # 60s prima
        pre_episode_alerts  = [
            ts for ts in alert_ts
            if window_before_start <= ts < ep_start
            and gt_index.get(ts) == 0  # finestre nominali pre-episodio
        ]
        if pre_episode_alerts:
            early_alerts += 1
            # Lead time = distanza tra il primo alert e l'inizio dell'episodio
            earliest = min(pre_episode_alerts)
            lead_us  = ep_start - earliest
            lead_steps = lead_us / 5_000_000  # finestre da 5s
            lead_times_before.append(lead_steps)
        else:
            no_early += 1

    print(f"  Episodi con early alert   : {early_alerts}")
    print(f"  Episodi senza early alert : {no_early}")
    if lead_times_before:
        avg_early = sum(lead_times_before) / len(lead_times_before)
        print(f"  Lead time medio (finestre): {avg_early:.1f}")

    # ---------------------------------------------------------------------------
    # Confronto esplicito ATG vs Framework
    # ---------------------------------------------------------------------------
    print(f"\n  --- ATG only vs Framework [{cs}] ---")
    print(f"  ATG: rileva {len(anomalous_ts)} finestre anomale a lead_time=0")
    print(f"       precision=1.0 per costruzione (sa sempre la label corrente)")
    print(f"       recall=1.0, f1=1.0 — ma SOLO in tempo reale, zero anticipazione")
    print(f"  Framework:")
    print(f"       precision={precision:.3f}, recall={recall:.3f}, f1={f1:.3f}")
    print(f"       lead_time_steps (da previsione): sempre=1 su training fisso")
    print(f"       early detection reale su episodi: {early_alerts}/{len(episodes)}")
    print(f"\n  Nota: il valore aggiunto del framework NON è la detection accuracy")
    print(f"  (l'ATG ha sempre precision=recall=1 per costruzione sul suo task).")
    print(f"  Il valore è: root_cause, critical_arc, cross_property_interference,")
    print(f"  classificazione red/orange/yellow — informazioni ASSENTI dall'ATG.")

print("\nDone.")