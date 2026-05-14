import logging
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).parent.parent.parent


def run_pipeline(
    mode: str,
    snapshot_indices: list[int],
    progress_cb: Callable[[int, str], None],
) -> dict:
    """Run the compliance forecasting pipeline and return results dict."""
    import sys
    sys.path.insert(0, str(_ROOT))

    try:
        from dashboard.core.data_manager import DataManager
        from src.utils.config_loader import ConfigLoader
        from src.layer1.topology_builder import TopologyBuilder
        from src.layer2.pbo_builder import PBOBuilder
        from src.layer3.feature_selector import FeatureSelector
        from src.phase1.stat_forecaster import StatForecaster
        from src.phase2.causal_analyzer import CausalAnalyzer
        from src.phase3.structural_monitor import StructuralMonitor
        from src.phase4.alert_generator import AlertGenerator

        progress_cb(5, "Inizializzazione...")
        dm = DataManager()
        all_snapshots = dm.get_snapshots()
        if not all_snapshots:
            return {"error": "Nessuno snapshot disponibile. Eseguire prima il build ATG."}
        _ts_to_idx = {s["timestamp"]: i for i, s in enumerate(all_snapshots)}  # noqa: F841

        nominal = dm.get_nominal_snapshots()
        gold    = dm.get_gold_standard()

        config = ConfigLoader(
            _ROOT / "config" / "topology.yaml",
            _ROOT / "config" / "pipeline_params.yaml",
        )
        topology = TopologyBuilder(config)
        topology.build()
        pbo = PBOBuilder(config, topology)
        weight_nominal = pbo.compute_transition_weights(nominal)

        if mode == "FULL" or not snapshot_indices:
            target_snapshots = all_snapshots
        else:
            target_snapshots = [
                all_snapshots[i]
                for i in snapshot_indices
                if i < len(all_snapshots)
            ]
        progress_cb(15, f"Target: {len(target_snapshots)} snapshot")

        cs_names = list(config.load_topology()["compliance_sets"].keys())
        span = max(1, (80 - 20) // len(cs_names))
        results_cs: dict = {}

        for i, cs in enumerate(cs_names):
            progress_cb(20 + i * span, f"Training {cs}...")

            fs  = FeatureSelector(config, topology)
            fc  = StatForecaster(config)
            ca  = CausalAnalyzer(config, topology)
            mon = StructuralMonitor(config, topology, pbo)
            ag  = AlertGenerator(config, topology)

            feats_nom = fs.select_features(cs, nominal)
            fc.fit(feats_nom, nominal_snapshots=nominal)
            causal_graph = ca.analyze(cs, feats_nom)
            mon.fit(cs, feats_nom, nominal, weight_nominal, gold)

            alerts = []
            for snap in target_snapshots:
                feats  = fs.select_features(cs, [snap])
                fcast  = fc.predict()
                w_curr = pbo.compute_transition_weights([snap])
                m_res  = mon.monitor(cs, feats, w_curr, snap["timestamp"])
                alert  = ag.generate(cs, fcast, causal_graph, m_res, snap["timestamp"])
                if alert is not None:
                    alerts.append(alert)

            mon.reset_cusum()
            results_cs[cs] = {"alerts": alerts, "causal_graph": causal_graph}
            progress_cb(20 + (i + 1) * span, f"{cs}: {len(alerts)} alert")

        progress_cb(100, "Completato")
        results = {"n_snapshots": len(target_snapshots), "compliance_sets": results_cs}
        dm.save_pipeline_results(results)
        return results

    except Exception as exc:
        import traceback
        msg = f"{type(exc).__name__}: {exc}"
        logger.error("Pipeline fallita: %s\n%s", msg, traceback.format_exc())
        return {"error": msg}
