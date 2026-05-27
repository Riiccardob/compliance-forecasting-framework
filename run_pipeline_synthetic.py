#!/usr/bin/env python3
"""
Runner per lo scenario sintetico SaaS Monitoring Platform.
Usa StatForecaster.predict_adaptive() per produrre lead_time variabile
per finestra tramite EWMA Trend Correction.

Utilizzo:
    python run_pipeline_synthetic.py
    python run_pipeline_synthetic.py --topology config/topology_synthetic.yaml
    python run_pipeline_synthetic.py --input data/synthetic/metrics_ingestor_memory_leak/1
    python run_pipeline_synthetic.py --output results/synthetic_run.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from src.layer1.topology_builder import TopologyBuilder
from src.layer2.atg_builder import ATGBuilder
from src.layer2.pbo_builder import PBOBuilder
from src.layer3.feature_selector import FeatureSelector
from src.phase1.stat_forecaster import StatForecaster
from src.phase2.causal_analyzer import CausalAnalyzer
from src.phase3.structural_monitor import StructuralMonitor
from src.phase4.alert_generator import AlertGenerator
from src.utils.config_loader import ConfigLoader
from src.utils.logging_setup import LoggingSetup

logger = LoggingSetup.configure(__name__, "INFO")


def _print_summary(
    cs: str,
    alerts: list[dict],
    n_snapshots: int,
    n_nominal: int,
    n_anomalous: int,
) -> None:
    """Stampa il riepilogo per compliance set dopo il run."""
    alerts_on_anomalous = [a for a in alerts if not a.get("is_nominal", True)]
    alerts_on_nominal = [a for a in alerts if a.get("is_nominal", True)]

    recall_num = len(alerts_on_anomalous)
    recall_pct = recall_num / max(n_anomalous, 1) * 100
    fp_num = len(alerts_on_nominal)

    lt_dist: dict[int, int] = {}
    crit_dist: dict[str, int] = {"red": 0, "orange": 0, "yellow": 0}
    for a in alerts:
        lt = int(a.get("lead_time_steps", 0))
        lt_dist[lt] = lt_dist.get(lt, 0) + 1
        crit = str(a.get("criticality", "unknown"))
        if crit in crit_dist:
            crit_dist[crit] += 1

    print(f"\nCS: {cs}")
    print(f"  Alert su finestre anomale: {recall_num}/{n_anomalous} (recall={recall_pct:.1f}%)")
    print(f"  Alert su finestre nominali (FP): {fp_num}/{n_nominal}")
    print(f"  Lead time distribution: {dict(sorted(lt_dist.items()))}")
    print(f"  Criticality: {crit_dist}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Runner sintetico con StatForecaster.predict_adaptive()"
    )
    parser.add_argument(
        "--topology",
        default="config/topology_synthetic.yaml",
        help="Path a topology.yaml (default: config/topology_synthetic.yaml)",
    )
    parser.add_argument(
        "--pipeline",
        default="config/pipeline_params.yaml",
        help="Path a pipeline_params.yaml",
    )
    parser.add_argument(
        "--input",
        default="data/synthetic/metrics_ingestor_memory_leak/1",
        help="Directory con node_metrics.csv, edge_metrics.csv, ground_truth.csv",
    )
    parser.add_argument(
        "--output",
        default="results/synthetic_run.json",
        help="Path al file JSON di output",
    )
    parser.add_argument(
        "--cs",
        default=None,
        help="Compliance set da processare (default: tutti)",
    )
    args = parser.parse_args()

    # Step 1 - Caricamento configurazione
    logger.info(
        "Caricamento configurazione: topology=%s pipeline=%s",
        args.topology,
        args.pipeline,
    )
    config = ConfigLoader(
        topology_path=Path(args.topology),
        pipeline_path=Path(args.pipeline),
    )
    topology = TopologyBuilder(config)
    topology.build()
    logger.info("TopologyBuilder costruito")

    # Step 2 - Build ATG dai CSV canonici
    input_dir = Path(args.input)
    logger.info("Build ATG da: %s", input_dir)
    atg = ATGBuilder(
        config,
        node_metrics_path=input_dir / "node_metrics.csv",
        edge_metrics_path=input_dir / "edge_metrics.csv",
        ground_truth_path=input_dir / "ground_truth.csv",
    )
    snapshots = atg.build()
    logger.info("ATG costruito: %d snapshot totali", len(snapshots))

    # Step 3 - Separazione nominali / anomali
    nominal = ATGBuilder.get_nominal_snapshots(snapshots)
    anomalous = ATGBuilder.get_anomalous_snapshots(snapshots)
    logger.info(
        "Snapshot: %d totali, %d nominali, %d anomali",
        len(snapshots),
        len(nominal),
        len(anomalous),
    )

    # Step 4 - Setup PBO
    logger.info("Calibrazione PBO su %d snapshot nominali", len(nominal))
    pbo = PBOBuilder(config, topology)
    weight_series = pbo.compute_transition_weights(nominal)
    gold_standard = pbo.compute_gold_standard(weight_series, nominal)

    # Step 5 - Per ogni compliance set
    compliance_sets = list(config.load_topology()["compliance_sets"].keys())
    if args.cs:
        compliance_sets = [args.cs]

    pp = config.load_pipeline_params()
    lookback_k: int = int(
        pp.get("forecasting", {}).get("adaptive", {}).get("lookback_windows", 8)
    )

    results: dict = {}

    for cs in compliance_sets:
        logger.info("=== Compliance set: %s ===", cs)

        # Feature selection nominali
        feature_sel = FeatureSelector(config, topology)
        features_nom = feature_sel.select_features(cs, nominal)
        logger.info("[%s] Feature nominali: %d serie", cs, len(features_nom))

        # Forecaster addestrato su nominali
        forecaster = StatForecaster(config)
        forecaster.fit(features_nom, nominal_snapshots=nominal)
        logger.info("[%s] StatForecaster addestrato: routing=%s", cs, forecaster.get_model_routing())

        # Analisi causale sui nominali (design-time)
        causal = CausalAnalyzer(config, topology)
        causal_graph = causal.analyze(cs, features_nom)
        logger.info(
            "[%s] CausalGraph: %d archi causali, %d cross-property chains",
            cs,
            len(causal_graph.get("edges", [])),
            len(causal_graph.get("cross_property_chains", [])),
        )

        # Monitor strutturale fittato su nominali
        monitor = StructuralMonitor(config, topology, pbo)
        monitor.fit(cs, features_nom, nominal, weight_series, gold_standard)
        logger.info("[%s] StructuralMonitor fittato", cs)

        alert_gen = AlertGenerator(config, topology)

        alerts: list[dict] = []
        # buffer[feat_key] = lista di (timestamp_µs, valore) più recenti
        observation_buffer: dict[str, list[tuple[int, float]]] = {}

        # Pre-warm del buffer con le ultime 2 osservazioni nominali.
        # Garantisce che la prima finestra processata usi predict_adaptive
        # invece di predict(), evitando FP da estrapolazione del trend nominale.
        for pre_snap in nominal[-2:]:
            pre_features = feature_sel.select_features(cs, [pre_snap])
            for feat_key, feat_df in pre_features.items():
                if feat_key not in observation_buffer:
                    observation_buffer[feat_key] = []
                if len(feat_df) > 0:
                    val = float(feat_df["value"].mean())
                    observation_buffer[feat_key].append((pre_snap["timestamp"], val))
            # Non applicare il cap lookback_k qui: il buffer è ancora molto piccolo.

        for snap in sorted(snapshots, key=lambda s: s["timestamp"]):
            ts: int = snap["timestamp"]
            try:
                features_curr = feature_sel.select_features(cs, [snap])
                weight_curr = pbo.compute_transition_weights([snap])
                mon_result = monitor.monitor(cs, features_curr, weight_curr, ts)

                # Aggiorna il buffer di osservazioni per predict_adaptive
                for feat_key, feat_df in features_curr.items():
                    if feat_key not in observation_buffer:
                        observation_buffer[feat_key] = []
                    if len(feat_df) > 0:
                        val = float(feat_df["value"].mean())
                        observation_buffer[feat_key].append((ts, val))
                    if len(observation_buffer[feat_key]) > lookback_k:
                        observation_buffer[feat_key] = observation_buffer[feat_key][-lookback_k:]

                # Costruisce recent_observations nel formato atteso da predict_adaptive
                recent_obs: dict[str, pd.DataFrame] = {
                    feat_key: pd.DataFrame(
                        {"value": [h[1] for h in history]},
                        index=[h[0] for h in history],
                    )
                    for feat_key, history in observation_buffer.items()
                    if len(history) >= 1
                }

                # predict_adaptive se tutte le feature hanno >= 2 osservazioni,
                # altrimenti predict() nominale (warmup delle prime finestre)
                if recent_obs and all(len(v) >= 2 for v in recent_obs.values()):
                    forecasts = forecaster.predict_adaptive(recent_obs)
                else:
                    forecasts = forecaster.predict()

                alert = alert_gen.generate(cs, forecasts, causal_graph, mon_result, ts)
                if alert is not None:
                    alerts.append({
                        **alert,
                        "true_label": snap["label"],
                        "is_nominal": snap["label"] == 0,
                    })

            except Exception as exc:
                logger.warning("Errore alla finestra ts=%d: %s", ts, exc)
                continue

        results[cs] = {
            "alerts": alerts,
            "n_snapshots": len(snapshots),
            "n_nominal": len(nominal),
            "n_anomalous": len(anomalous),
            "causal_graph": causal_graph,
        }

        _print_summary(cs, alerts, len(snapshots), len(nominal), len(anomalous))

    # Step 6 - Salvataggio risultati
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, default=str, indent=2)
    logger.info("Risultati salvati in %s", out_path)
    print(f"\nRisultati salvati in {out_path}")


if __name__ == "__main__":
    main()
