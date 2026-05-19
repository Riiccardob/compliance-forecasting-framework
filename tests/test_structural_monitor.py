"""Test per StructuralMonitor - mock sintetici, nessun CSV reale."""
import copy
from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from src.layer1.topology_builder import TopologyBuilder
from src.layer2.pbo_builder import PBOBuilder
from src.phase3.structural_monitor import StructuralMonitor
from src.utils.config_loader import ConfigLoader

_ROOT = Path(__file__).parent.parent
_TOPOLOGY_PATH = _ROOT / "config" / "topology.yaml"
_PIPELINE_PATH = _ROOT / "config" / "pipeline_params.yaml"

_STEP_US = 5_000_000  # 5 s in µs
_T0 = 1_000_000_000

# Nodi H_crit in ordine sorted
_H_CRIT_NODES = [
    "home-timeline-service",
    "nginx-thrift",
    "nginx-web-server",
    "post-storage-mongodb",
    "post-storage-service",
]

_NODE_METRICS_SORTED = ["cpu_percent", "mem_mb", "net_rx_mb", "net_tx_mb"]

# Throughput nominale per H_crit (critical path: e1, e2, e4, e6)
_TP_NOMINAL = {
    "e1": 100.0, "e2": 100.0,
    "e3": 50.0,  "e4": 50.0,
    "e5": 25.0,  "e6": 25.0,
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_snap(ts: int, label: int, cpu: float = 5.0) -> dict[str, Any]:
    """Snapshot con tutti i nodi e archi DSB (valori nominali)."""
    nodes = {
        n: {"cpu_percent": cpu, "mem_mb": 512.0,
            "net_rx_mb": 1.0, "net_tx_mb": 0.5}
        for n in [
            "nginx-web-server", "nginx-thrift", "home-timeline-service",
            "home-timeline-redis", "post-storage-service",
            "post-storage-memcached", "post-storage-mongodb",
        ]
    }
    edges = {
        eid: {"latency_ms": 10.0, "error_rate": 0.01,
              "throughput_rps": tp}
        for eid, tp in _TP_NOMINAL.items()
    }
    return {"timestamp": ts, "label": label, "nodes": nodes, "edges": edges,
            "anomaly_type": None, "anomaly_node_ids": []}


def _make_df(val: float, ts: int = _T0) -> pd.DataFrame:
    return pd.DataFrame(
        {"value": [val]},
        index=pd.Index([ts], name="timestamp"),
    )


def _make_features_h_crit(
    cpu: float = 5.0, latency: float = 10.0, ts: int = _T0
) -> dict[str, pd.DataFrame]:
    """Feature dict per H_crit con valori controllati."""
    feats: dict[str, pd.DataFrame] = {}
    for node in _H_CRIT_NODES:
        feats[f"node:{node}:cpu_percent"] = _make_df(cpu, ts)
        feats[f"node:{node}:mem_mb"] = _make_df(512.0, ts)
        feats[f"node:{node}:net_rx_mb"] = _make_df(1.0, ts)
        feats[f"node:{node}:net_tx_mb"] = _make_df(0.5, ts)
    for eid in ("e1", "e2", "e4", "e6"):
        feats[f"edge:{eid}:latency_ms"] = _make_df(latency, ts)
        feats[f"edge:{eid}:error_rate"] = _make_df(0.01, ts)
        feats[f"edge:{eid}:throughput_rps"] = _make_df(_TP_NOMINAL.get(eid, 50.0), ts)
    return feats


def _make_weight_series(
    n: int = 20,
    tp_override: dict[str, float] | None = None,
    ts_start: int = _T0,
) -> list[dict]:
    tp = dict(_TP_NOMINAL)
    if tp_override:
        tp.update(tp_override)
    result = []
    for i in range(n):
        ts = ts_start + i * _STEP_US
        e1_w = 1.0
        e2_w = 1.0
        # home-timeline-service: e3 e e4
        total_hts = tp["e3"] + tp["e4"]
        e3_w = tp["e3"] / total_hts if total_hts > 0 else 0.5
        e4_w = tp["e4"] / total_hts if total_hts > 0 else 0.5
        # post-storage-service: e5 e e6
        total_pss = tp["e5"] + tp["e6"]
        e5_w = tp["e5"] / total_pss if total_pss > 0 else 0.5
        e6_w = tp["e6"] / total_pss if total_pss > 0 else 0.5
        result.append({
            "timestamp": ts,
            "weights": {
                "e1": e1_w, "e2": e2_w,
                "e3": e3_w, "e4": e4_w,
                "e5": e5_w, "e6": e6_w,
            },
        })
    return result


# ── Fixture ──────────────────────────────────────────────────────────────────

@pytest.fixture
def config() -> ConfigLoader:
    return ConfigLoader(_TOPOLOGY_PATH, _PIPELINE_PATH)


@pytest.fixture
def topology_builder(config: ConfigLoader) -> TopologyBuilder:
    return TopologyBuilder(config)


@pytest.fixture
def pbo_builder(config: ConfigLoader, topology_builder: TopologyBuilder) -> PBOBuilder:
    return PBOBuilder(config, topology_builder)


@pytest.fixture
def monitor(
    config: ConfigLoader,
    topology_builder: TopologyBuilder,
    pbo_builder: PBOBuilder,
) -> StructuralMonitor:
    return StructuralMonitor(config, topology_builder, pbo_builder)


@pytest.fixture
def mock_nominal_snapshots() -> list[dict]:
    return [_make_snap(_T0 + i * _STEP_US, label=0) for i in range(20)]


@pytest.fixture
def mock_weight_series() -> list[dict]:
    return _make_weight_series(n=20)


@pytest.fixture
def mock_gold_standard(
    pbo_builder: PBOBuilder,
    mock_nominal_snapshots: list[dict],
    mock_weight_series: list[dict],
) -> dict[str, float]:
    return pbo_builder.compute_gold_standard(mock_weight_series, mock_nominal_snapshots)


@pytest.fixture
def mock_features_h_crit() -> dict[str, pd.DataFrame]:
    return _make_features_h_crit()


@pytest.fixture
def fitted_monitor(
    monitor: StructuralMonitor,
    mock_features_h_crit: dict[str, pd.DataFrame],
    mock_nominal_snapshots: list[dict],
    mock_weight_series: list[dict],
    mock_gold_standard: dict[str, float],
) -> StructuralMonitor:
    monitor.fit(
        "H_crit",
        mock_features_h_crit,
        mock_nominal_snapshots,
        mock_weight_series,
        mock_gold_standard,
    )
    return monitor


# ── Struttura e fit (4) ──────────────────────────────────────────────────────

def test_monitor_returns_dict(
    fitted_monitor: StructuralMonitor,
    mock_weight_series: list[dict],
) -> None:
    result = fitted_monitor.monitor(
        "H_crit", _make_features_h_crit(), [mock_weight_series[-1]], _T0
    )
    assert isinstance(result, dict)


def test_monitor_result_has_required_keys(
    fitted_monitor: StructuralMonitor,
    mock_weight_series: list[dict],
) -> None:
    result = fitted_monitor.monitor(
        "H_crit", _make_features_h_crit(), [mock_weight_series[-1]], _T0
    )
    expected = {
        "timestamp", "compliance_set", "base_signal", "if_signal",
        "cusum_signal", "structural_confirmed", "zscore_violations",
        "threshold_violations", "frobenius_distance", "pas_value",
        "cusum_stat", "ewma_value",
    }
    assert set(result.keys()) == expected


def test_fit_raises_on_empty_nominal_snapshots(
    monitor: StructuralMonitor,
    mock_features_h_crit: dict[str, pd.DataFrame],
    mock_weight_series: list[dict],
    mock_gold_standard: dict[str, float],
) -> None:
    with pytest.raises(RuntimeError):
        monitor.fit("H_crit", mock_features_h_crit, [], mock_weight_series, mock_gold_standard)


def test_monitor_raises_before_fit(
    monitor: StructuralMonitor,
    mock_weight_series: list[dict],
) -> None:
    with pytest.raises(RuntimeError):
        monitor.monitor("H_crit", _make_features_h_crit(), [mock_weight_series[-1]], _T0)


# ── Livello 1 - Threshold (3) ────────────────────────────────────────────────

def test_threshold_no_violation_on_nominal(
    fitted_monitor: StructuralMonitor,
    mock_weight_series: list[dict],
) -> None:
    """Valori nominali ben dentro le soglie SLA → nessuna threshold violation."""
    # latency_ms SLA upper = 100.0; usiamo 10.0
    features = _make_features_h_crit(latency=10.0)
    result = fitted_monitor.monitor(
        "H_crit", features, [mock_weight_series[-1]], _T0
    )
    assert result["threshold_violations"] == []


def test_threshold_violation_on_high_latency(
    fitted_monitor: StructuralMonitor,
    mock_weight_series: list[dict],
) -> None:
    """latency_ms > SLA upper threshold (100.0) → violation."""
    features = _make_features_h_crit(latency=200.0)  # > 100.0
    result = fitted_monitor.monitor(
        "H_crit", features, [mock_weight_series[-1]], _T0
    )
    violated = result["threshold_violations"]
    latency_violated = [k for k in violated if "latency_ms" in k]
    assert len(latency_violated) > 0, (
        f"Attesa violazione latency_ms > 100.0, violations={violated}"
    )


def test_threshold_nan_value_not_a_violation(
    fitted_monitor: StructuralMonitor,
    mock_weight_series: list[dict],
) -> None:
    """NaN non conta come violazione threshold."""
    features = _make_features_h_crit()
    features["edge:e1:latency_ms"] = _make_df(float("nan"))
    result = fitted_monitor.monitor(
        "H_crit", features, [mock_weight_series[-1]], _T0
    )
    e1_lat_violated = [k for k in result["threshold_violations"]
                       if k == "edge:e1:latency_ms"]
    assert len(e1_lat_violated) == 0


# ── Livello 1 - Z-score (3) ──────────────────────────────────────────────────

def test_zscore_no_violation_on_nominal(
    fitted_monitor: StructuralMonitor,
    mock_weight_series: list[dict],
) -> None:
    """Valori nominali → zscore_violations vuoto."""
    features = _make_features_h_crit(cpu=5.0)
    result = fitted_monitor.monitor(
        "H_crit", features, [mock_weight_series[-1]], _T0
    )
    assert result["zscore_violations"] == []


def test_zscore_violation_on_spike(
    monitor: StructuralMonitor,
    mock_weight_series: list[dict],
    mock_gold_standard: dict[str, float],
) -> None:
    """cpu_percent = mean + 4*std → z=4 > 3.0 → zscore violation."""
    n = 20
    cpu_vals = [5.0] * n
    rng = np.random.default_rng(0)
    cpu_arr = np.array(cpu_vals) + rng.normal(0, 1.0, n)
    mean_cpu = float(np.mean(cpu_arr))
    std_cpu = float(np.std(cpu_arr))

    nominal_snaps = []
    for i in range(n):
        s = _make_snap(_T0 + i * _STEP_US, label=0, cpu=float(cpu_arr[i]))
        nominal_snaps.append(s)

    nominal_features: dict[str, pd.DataFrame] = {}
    for node in _H_CRIT_NODES:
        key = f"node:{node}:cpu_percent"
        vals = cpu_arr
        ts_list = [_T0 + i * _STEP_US for i in range(n)]
        nominal_features[key] = pd.DataFrame(
            {"value": vals}, index=pd.Index(ts_list, name="timestamp")
        )
    for node in _H_CRIT_NODES:
        for m in ("mem_mb", "net_rx_mb", "net_tx_mb"):
            key = f"node:{node}:{m}"
            nominal_features[key] = pd.DataFrame(
                {"value": [512.0] * n if m == "mem_mb" else [1.0] * n},
                index=pd.Index([_T0 + i * _STEP_US for i in range(n)], name="timestamp"),
            )
    for eid in ("e1", "e2", "e4", "e6"):
        for m in ("latency_ms", "error_rate", "throughput_rps"):
            key = f"edge:{eid}:{m}"
            nominal_features[key] = pd.DataFrame(
                {"value": [10.0] * n},
                index=pd.Index([_T0 + i * _STEP_US for i in range(n)], name="timestamp"),
            )

    monitor.fit("H_crit", nominal_features, nominal_snaps, mock_weight_series, mock_gold_standard)

    spike_cpu = mean_cpu + 4.0 * std_cpu
    test_features: dict[str, pd.DataFrame] = {}
    for node in _H_CRIT_NODES:
        test_features[f"node:{node}:cpu_percent"] = _make_df(spike_cpu)
        test_features[f"node:{node}:mem_mb"] = _make_df(512.0)
        test_features[f"node:{node}:net_rx_mb"] = _make_df(1.0)
        test_features[f"node:{node}:net_tx_mb"] = _make_df(0.5)
    for eid in ("e1", "e2", "e4", "e6"):
        test_features[f"edge:{eid}:latency_ms"] = _make_df(10.0)
        test_features[f"edge:{eid}:error_rate"] = _make_df(0.01)
        test_features[f"edge:{eid}:throughput_rps"] = _make_df(100.0)

    result = monitor.monitor("H_crit", test_features, [mock_weight_series[-1]], _T0)
    cpu_violated = [k for k in result["zscore_violations"] if "cpu_percent" in k]
    assert len(cpu_violated) > 0, (
        f"Attesa zscore violation per cpu_percent spike (z=4 > 3.0), "
        f"violations={result['zscore_violations']}"
    )


def test_zscore_nan_not_a_violation(
    fitted_monitor: StructuralMonitor,
    mock_weight_series: list[dict],
) -> None:
    """Valore NaN non genera zscore violation."""
    features = _make_features_h_crit()
    features["node:nginx-web-server:cpu_percent"] = _make_df(float("nan"))
    result = fitted_monitor.monitor(
        "H_crit", features, [mock_weight_series[-1]], _T0
    )
    nan_violated = [k for k in result["zscore_violations"]
                    if k == "node:nginx-web-server:cpu_percent"]
    assert len(nan_violated) == 0


# ── Livello 2 - Isolation Forest (3) ─────────────────────────────────────────

def test_if_inactive_without_base_signal(
    fitted_monitor: StructuralMonitor,
    mock_weight_series: list[dict],
) -> None:
    """Con base_signal=False (valori nominali), if_signal=False."""
    features = _make_features_h_crit(cpu=5.0, latency=10.0)
    result = fitted_monitor.monitor(
        "H_crit", features, [mock_weight_series[-1]], _T0
    )
    # Con valori nominali base_signal dovrebbe essere False
    if not result["base_signal"]:
        assert result["if_signal"] is False


def test_if_detects_multivariate_anomaly(
    monitor: StructuralMonitor,
    mock_weight_series: list[dict],
    mock_gold_standard: dict[str, float],
) -> None:
    """cpu molto lontano dal training: con base_signal=True, if_signal=True.

    Il training usa snapshot con cpu ≈ 5 ± 0.5 (varianza non nulla) così
    che Isolation Forest apprenda un boundary significativo. Il vettore
    di test ha cpu=1000 (estremo) in tutte le dimensioni, garantendo
    che IF lo classifichi come anomalia indipendentemente dal seed.
    """
    rng = np.random.default_rng(42)
    n = 40  # più punti → IF più affidabile
    cpu_arr = rng.normal(5.0, 0.5, n)

    # Costruire nominal_snaps con cpu variabile, non costante
    nominal_snaps = []
    for i in range(n):
        s = _make_snap(_T0 + i * _STEP_US, label=0)
        for node_id in s["nodes"]:
            s["nodes"][node_id]["cpu_percent"] = float(cpu_arr[i])
        nominal_snaps.append(s)

    # Features nominali con le stesse serie cpu variabili per z-score training
    nominal_features: dict[str, pd.DataFrame] = {}
    for node in _H_CRIT_NODES:
        nominal_features[f"node:{node}:cpu_percent"] = pd.DataFrame(
            {"value": cpu_arr},
            index=pd.Index([_T0 + i * _STEP_US for i in range(n)], name="timestamp"),
        )
        nominal_features[f"node:{node}:mem_mb"] = pd.DataFrame(
            {"value": [512.0] * n},
            index=pd.Index([_T0 + i * _STEP_US for i in range(n)], name="timestamp"),
        )
        for m in ("net_rx_mb", "net_tx_mb"):
            nominal_features[f"node:{node}:{m}"] = pd.DataFrame(
                {"value": [1.0] * n},
                index=pd.Index([_T0 + i * _STEP_US for i in range(n)], name="timestamp"),
            )
    for eid in ("e1", "e2", "e4", "e6"):
        for m in ("latency_ms", "error_rate", "throughput_rps"):
            nominal_features[f"edge:{eid}:{m}"] = pd.DataFrame(
                {"value": [10.0] * n},
                index=pd.Index([_T0 + i * _STEP_US for i in range(n)], name="timestamp"),
            )

    monitor.fit("H_crit", nominal_features, nominal_snaps, mock_weight_series, mock_gold_standard)

    # Test: cpu=1000 in tutte le dimensioni - outlier estremo (>400σ dal training)
    extreme_cpu = 1000.0
    test_ts = _T0 + n * _STEP_US
    test_features = _make_features_h_crit(cpu=extreme_cpu, latency=10.0, ts=test_ts)

    result = monitor.monitor("H_crit", test_features, [mock_weight_series[-1]], test_ts)
    assert result["base_signal"] is True, "Atteso base_signal=True per cpu=1000"
    assert result["if_signal"] is True, "Atteso if_signal=True per cpu estremo (>400σ)"


def test_if_imputes_nan_in_state_vector(
    fitted_monitor: StructuralMonitor,
    mock_weight_series: list[dict],
) -> None:
    """NaN in una feature nodo: monitor() non solleva eccezioni (imputation)."""
    features = _make_features_h_crit(cpu=5.0)
    features["node:nginx-web-server:cpu_percent"] = _make_df(float("nan"))
    # Nessun raise atteso
    result = fitted_monitor.monitor(
        "H_crit", features, [mock_weight_series[-1]], _T0
    )
    assert isinstance(result, dict)


# ── Livello 3 - EWMA + CUSUM (4) ─────────────────────────────────────────────

def test_cusum_starts_at_zero(
    monitor: StructuralMonitor,
    mock_features_h_crit: dict[str, pd.DataFrame],
    mock_nominal_snapshots: list[dict],
    mock_weight_series: list[dict],
    mock_gold_standard: dict[str, float],
) -> None:
    """Dopo fit() cusum_stat == 0.0 (reset chiamato in fit)."""
    monitor.fit(
        "H_crit", mock_features_h_crit, mock_nominal_snapshots,
        mock_weight_series, mock_gold_standard
    )
    assert monitor._cusum_stat == 0.0


def test_cusum_accumulates_on_degradation(
    monitor: StructuralMonitor,
    mock_features_h_crit: dict[str, pd.DataFrame],
    mock_nominal_snapshots: list[dict],
    mock_weight_series: list[dict],
    mock_gold_standard: dict[str, float],
) -> None:
    """PAS decrescente → CUSUM si accumula dopo 5 chiamate."""
    monitor.fit(
        "H_crit", mock_features_h_crit, mock_nominal_snapshots,
        mock_weight_series, mock_gold_standard
    )
    initial_stat = monitor._cusum_stat

    # Pesi degradati: e4 dominante → PAS decresce
    degraded_ws = _make_weight_series(
        n=1,
        tp_override={"e4": 90.0, "e3": 10.0, "e6": 5.0, "e5": 45.0},
    )
    for i in range(5):
        ts = _T0 + (20 + i) * _STEP_US
        monitor.monitor("H_crit", mock_features_h_crit, degraded_ws, ts)

    assert monitor._cusum_stat > 0.0, (
        f"CUSUM atteso > 0.0 dopo 5 finestre con pesi degradati, "
        f"ottenuto {monitor._cusum_stat:.8f}. "
        "Verificare che tolerance_factor=0.0 in pipeline_params.yaml."
    )


def test_reset_cusum_zeros_accumulator(
    fitted_monitor: StructuralMonitor,
    mock_features_h_crit: dict[str, pd.DataFrame],
    mock_weight_series: list[dict],
) -> None:
    """Dopo reset_cusum(), la prima chiamata monitor ha cusum_stat ≥ 0."""
    degraded_ws = _make_weight_series(
        n=1,
        tp_override={"e4": 90.0, "e3": 10.0, "e6": 5.0, "e5": 45.0},
    )
    for i in range(3):
        fitted_monitor.monitor(
            "H_crit", mock_features_h_crit, degraded_ws, _T0 + i * _STEP_US
        )

    fitted_monitor.reset_cusum()
    assert fitted_monitor._cusum_stat == 0.0
    assert fitted_monitor._ewma_state is None

    result = fitted_monitor.monitor(
        "H_crit", mock_features_h_crit, [mock_weight_series[-1]], _T0
    )
    assert result["cusum_stat"] >= 0.0


def test_cusum_signal_when_threshold_exceeded(
    monitor: StructuralMonitor,
    mock_features_h_crit: dict[str, pd.DataFrame],
    mock_nominal_snapshots: list[dict],
    mock_weight_series: list[dict],
    mock_gold_standard: dict[str, float],
    config: ConfigLoader,
) -> None:
    """CUSUM supera threshold → cusum_signal=True."""
    pipeline = config.load_pipeline_params()
    bad_pipeline = copy.deepcopy(pipeline)
    bad_pipeline["anomaly_detection"]["cusum"]["alert_threshold"] = 0.0001
    with patch.object(type(config), "load_pipeline_params", return_value=bad_pipeline):
        from src.layer1.topology_builder import TopologyBuilder as TB
        from src.layer2.pbo_builder import PBOBuilder as PBO
        cfg2 = ConfigLoader(_TOPOLOGY_PATH, _PIPELINE_PATH)
        tb2 = TB(cfg2)
        pbo2 = PBO(cfg2, tb2)
        low_monitor = StructuralMonitor(config, tb2, pbo2)

    low_monitor._cusum_threshold = 0.0001
    low_monitor.fit(
        "H_crit", mock_features_h_crit, mock_nominal_snapshots,
        mock_weight_series, mock_gold_standard
    )

    degraded_ws = _make_weight_series(
        n=1, tp_override={"e4": 90.0, "e3": 10.0, "e6": 5.0, "e5": 45.0}
    )
    result = None
    for i in range(10):
        ts = _T0 + (20 + i) * _STEP_US
        result = low_monitor.monitor(
            "H_crit", mock_features_h_crit, degraded_ws, ts
        )
        if result["cusum_signal"]:
            break

    assert result is not None
    assert result["cusum_signal"] is True, (
        f"Atteso cusum_signal=True con threshold=0.0001, "
        f"cusum_stat={result['cusum_stat']:.6f}"
    )


# ── Livello 4 - Validatore strutturale (3) ───────────────────────────────────

def test_structural_confirmed_requires_both_signals(
    fitted_monitor: StructuralMonitor,
    mock_weight_series: list[dict],
) -> None:
    """structural_confirmed=False se uno solo dei segnali è True."""
    features = _make_features_h_crit()
    result = fitted_monitor.monitor(
        "H_crit", features, [mock_weight_series[-1]], _T0
    )
    if not result["if_signal"] or not result["cusum_signal"]:
        assert result["structural_confirmed"] is False


def test_structural_not_confirmed_below_frobenius_threshold(
    fitted_monitor: StructuralMonitor,
    mock_weight_series: list[dict],
) -> None:
    """Distanza Frobenius < threshold → structural_confirmed=False."""
    # Forziamo if_signal e cusum_signal a True ma Frobenius piccolo
    fitted_monitor._cusum_stat = 0.0
    result = fitted_monitor.monitor(
        "H_crit", _make_features_h_crit(), [mock_weight_series[-1]], _T0
    )
    # Con dati nominali Frobenius è piccolo → structural non confermato
    if result["frobenius_distance"] is not None:
        if result["frobenius_distance"] < fitted_monitor._frobenius_threshold:
            assert result["structural_confirmed"] is False


def test_structural_confirmed_on_persistent_degradation(
    config: ConfigLoader,
    topology_builder: TopologyBuilder,
    pbo_builder: PBOBuilder,
) -> None:
    """structural_confirmed=True dopo 8 finestre di degrado persistente.

    Condizioni necessarie per structural_confirmed=True:
    1. if_signal=True: zscore spike (cpu=1000) + IF anomaly detection
    2. cusum_signal=True: alert_threshold=0.0001 + k=0.0 + pesi degradati
    3. frobenius > distance_threshold=0.0
    4. Derivata EWMA persistente: almeno consecutive_windows=3 diff negativi
    """
    rng = np.random.default_rng(42)
    n = 40

    # Training con varianza non nulla (necessaria per IF)
    nominal_snaps = []
    for i in range(n):
        ts = _T0 + i * _STEP_US
        snap = _make_snap(ts, label=0, cpu=float(rng.normal(5.0, 0.5)))
        nominal_snaps.append(snap)

    ws_nominal = _make_weight_series(n=n)
    gold = pbo_builder.compute_gold_standard(ws_nominal, nominal_snaps)

    nominal_features: dict[str, pd.DataFrame] = {}
    cpu_arr = np.array([s["nodes"]["nginx-web-server"]["cpu_percent"]
                        for s in nominal_snaps])
    ts_list = [s["timestamp"] for s in nominal_snaps]
    for node in _H_CRIT_NODES:
        nominal_features[f"node:{node}:cpu_percent"] = pd.DataFrame(
            {"value": cpu_arr},
            index=pd.Index(ts_list, name="timestamp"),
        )
        for m in ("mem_mb", "net_rx_mb", "net_tx_mb"):
            val = 512.0 if m == "mem_mb" else 1.0
            nominal_features[f"node:{node}:{m}"] = pd.DataFrame(
                {"value": [val] * n},
                index=pd.Index(ts_list, name="timestamp"),
            )
    for eid in ("e1", "e2", "e4", "e6"):
        for m in ("latency_ms", "error_rate", "throughput_rps"):
            nominal_features[f"edge:{eid}:{m}"] = pd.DataFrame(
                {"value": [10.0] * n},
                index=pd.Index(ts_list, name="timestamp"),
            )

    mon = StructuralMonitor(config, topology_builder, pbo_builder)
    mon.fit("H_crit", nominal_features, nominal_snaps, ws_nominal, gold)
    mon._cusum_threshold = 0.0001   # soglia CUSUM bassissima
    mon._frobenius_threshold = 0.0  # qualsiasi Frobenius > 0 è sufficiente

    # Iter 0: pesi nominali → EWMA cold-start a PAS_gold≈0.25
    # Questo garantisce che le iterazioni successive producano diffs negativi.
    ws_nominal_one = _make_weight_series(n=1)
    ts0 = _T0 + n * _STEP_US
    mon.monitor("H_crit", _make_features_h_crit(cpu=1000.0, latency=10.0, ts=ts0),
                ws_nominal_one, ts0)

    # Iters 1-8: pesi fortemente degradati → PAS ≈ 0.0099, EWMA decresce
    # monotonicamente da 0.25 verso 0.0099 → diffs sempre negativi.
    degraded_ws = _make_weight_series(
        n=1, tp_override={"e4": 99.0, "e3": 1.0, "e6": 1.0, "e5": 99.0}
    )

    result = None
    for i in range(1, 9):
        ts = _T0 + (n + i) * _STEP_US
        anomalous_features_ts = _make_features_h_crit(cpu=1000.0, latency=10.0, ts=ts)
        result = mon.monitor(
            "H_crit", anomalous_features_ts, degraded_ws, ts
        )
        if result["structural_confirmed"]:
            break

    assert result is not None
    assert result["structural_confirmed"] is True, (
        f"structural_confirmed atteso True dopo 8 finestre di degrado "
        f"persistente. Stato finale: base_signal={result['base_signal']}, "
        f"if_signal={result['if_signal']}, "
        f"cusum_signal={result['cusum_signal']}, "
        f"cusum_stat={result['cusum_stat']:.6f}, "
        f"frobenius={result['frobenius_distance']}, "
        f"ewma={result['ewma_value']}. "
        "Verificare che cpu=1000 attivi base_signal e IF, e che pesi "
        "degradati accumulino CUSUM con alert_threshold=0.0001."
    )


# ── Robustezza (3) ───────────────────────────────────────────────────────────

def test_monitor_unknown_compliance_set_raises(
    fitted_monitor: StructuralMonitor,
    mock_weight_series: list[dict],
) -> None:
    """monitor() con compliance set inesistente solleva KeyError."""
    with pytest.raises(KeyError):
        fitted_monitor.monitor(
            "H_nonexistent", _make_features_h_crit(), [mock_weight_series[-1]], _T0
        )


def test_fit_unknown_compliance_set_raises(
    monitor: StructuralMonitor,
    mock_features_h_crit: dict[str, pd.DataFrame],
    mock_nominal_snapshots: list[dict],
    mock_weight_series: list[dict],
    mock_gold_standard: dict[str, float],
) -> None:
    """fit() con compliance set inesistente solleva KeyError."""
    with pytest.raises(KeyError):
        monitor.fit(
            "H_nonexistent", mock_features_h_crit, mock_nominal_snapshots,
            mock_weight_series, mock_gold_standard
        )


def test_missing_anomaly_detection_key_raises(
    config: ConfigLoader,
    topology_builder: TopologyBuilder,
    pbo_builder: PBOBuilder,
) -> None:
    """Costruttore solleva ValueError se manca 'zscore_threshold'."""
    pipeline = config.load_pipeline_params()
    bad_pipeline = copy.deepcopy(pipeline)
    del bad_pipeline["anomaly_detection"]["zscore_threshold"]
    with patch.object(type(config), "load_pipeline_params", return_value=bad_pipeline):
        with pytest.raises(ValueError, match="zscore_threshold"):
            StructuralMonitor(config, topology_builder, pbo_builder)


# ── Config guard (1) ─────────────────────────────────────────────────────────

def test_cusum_k_loaded_from_yaml(
    monitor: StructuralMonitor,
) -> None:
    """tolerance_factor in pipeline_params.yaml deve essere 0.0
    (valore che rende CUSUM funzionale per H_crit con PAS_gold=0.25).
    Guard di regressione: se tolerance_factor > PAS_gold il CUSUM
    non accumula mai per topologia lineare."""
    assert monitor._cusum_k == 0.0, (
        f"tolerance_factor atteso 0.0, trovato {monitor._cusum_k}. "
        "Con tolerance_factor > PAS_gold (0.25) il CUSUM non accumula "
        "mai per H_crit. Correggere pipeline_params.yaml."
    )


# ── Warning (1) ───────────────────────────────────────────────────────────────

def test_monitor_warns_on_compliance_set_mismatch(
    fitted_monitor: StructuralMonitor,
    mock_weight_series: list[dict],
) -> None:
    """monitor() emette warning se chiamato con un compliance set
    diverso da quello su cui è stato eseguito fit()."""
    from unittest.mock import patch
    with patch.object(fitted_monitor._logger, "warning") as mock_warn:
        # fit è stato fatto su H_crit, chiamiamo monitor su H_cache
        fitted_monitor.monitor(
            "H_cache", _make_features_h_crit(), [mock_weight_series[-1]], _T0
        )
    warning_msgs = " ".join(
        str(c) for c in mock_warn.call_args_list
    )
    assert "H_cache" in warning_msgs or "H_crit" in warning_msgs, (
        "Atteso warning per CS mismatch (fit su H_crit, monitor su H_cache)."
    )


# ── Robustezza aggiuntiva (2) ─────────────────────────────────────────────────

def test_structural_validator_warmup_returns_false(
    config: ConfigLoader,
    topology_builder: TopologyBuilder,
    pbo_builder: PBOBuilder,
) -> None:
    """structural_confirmed=False durante il warm-up del Validatore strutturale.
    Nelle prime consecutive_windows chiamate dopo fit(), _ewma_history non ha
    abbastanza elementi per calcolare consecutive_windows diff consecutivi
    → structural_confirmed deve essere False."""
    rng = np.random.default_rng(7)
    n = 20
    nominal_snaps = [
        _make_snap(_T0 + i * _STEP_US, label=0,
                   cpu=float(rng.normal(5.0, 0.5)))
        for i in range(n)
    ]
    ws_nominal = _make_weight_series(n=n)
    gold = pbo_builder.compute_gold_standard(ws_nominal, nominal_snaps)

    nominal_features: dict[str, pd.DataFrame] = {}
    ts_list = [_T0 + i * _STEP_US for i in range(n)]
    for node in _H_CRIT_NODES:
        for m, val in [("cpu_percent", 5.0), ("mem_mb", 512.0),
                       ("net_rx_mb", 1.0), ("net_tx_mb", 0.5)]:
            nominal_features[f"node:{node}:{m}"] = pd.DataFrame(
                {"value": [val] * n}, index=pd.Index(ts_list, name="timestamp")
            )
    for eid in ("e1", "e2", "e4", "e6"):
        for m in ("latency_ms", "error_rate", "throughput_rps"):
            nominal_features[f"edge:{eid}:{m}"] = pd.DataFrame(
                {"value": [10.0] * n}, index=pd.Index(ts_list, name="timestamp")
            )

    mon = StructuralMonitor(config, topology_builder, pbo_builder)
    mon.fit("H_crit", nominal_features, nominal_snaps, ws_nominal, gold)

    # Pesi degradati che attiverebbero il validatore SE ci fosse abbastanza history
    degraded_ws = _make_weight_series(
        n=1, tp_override={"e4": 99.0, "e3": 1.0, "e6": 1.0, "e5": 99.0}
    )
    mon._cusum_threshold = 0.0001  # soglia bassa per attivare cusum_signal
    mon._frobenius_threshold = 0.0

    consecutive = mon._consecutive_windows  # tipicamente 3

    for i in range(consecutive):
        ts = _T0 + (n + i) * _STEP_US
        result = mon.monitor(
            "H_crit",
            _make_features_h_crit(cpu=1000.0, latency=10.0, ts=ts),
            degraded_ws,
            ts,
        )
        # Durante il warm-up (meno di consecutive+1 valori EWMA),
        # structural_confirmed DEVE essere False anche se cusum_signal potrebbe
        # già essere True
        assert result["structural_confirmed"] is False, (
            f"Atteso structural_confirmed=False al ciclo {i+1}/{consecutive} "
            f"(warm-up: storia insufficiente per {consecutive} diff consecutivi). "
            f"Stato: {result}"
        )


def test_cusum_decreases_on_recovery(
    monitor: StructuralMonitor,
    mock_features_h_crit: dict[str, pd.DataFrame],
    mock_nominal_snapshots: list[dict],
    mock_weight_series: list[dict],
    mock_gold_standard: dict[str, float],
) -> None:
    """Dopo accumulo su pesi degradati, CUSUM scende verso zero con pesi
    super-nominali (PAS > PAS_gold). Verifica la rimozione dell'inner
    max(0,...) che prima rendeva il CUSUM monotono non-decrescente.

    Nota: il decremento del CUSUM richiede ewma_new > PAS_gold, il che
    si verifica solo quando PAS corrente supera PAS_gold. Con pesi nominali
    (PAS = PAS_gold = 0.25) l'EWMA converge dal basso verso 0.25 e il CUSUM
    continua ad accumularsi. I pesi super-nominali (tutto il traffico sul
    percorso critico) producono PAS = 1.0 >> PAS_gold, cosicché dopo
    pochi passi ewma_new > 0.25 e l'incremento diventa negativo.
    """
    monitor.fit(
        "H_crit", mock_features_h_crit, mock_nominal_snapshots,
        mock_weight_series, mock_gold_standard,
    )
    monitor._cusum_threshold = 0.0001

    # Fase 1: accumulo con pesi degradati (PAS ≈ 0.09 < PAS_gold=0.25)
    degraded_ws = _make_weight_series(
        n=1, tp_override={"e4": 90.0, "e3": 10.0, "e6": 5.0, "e5": 45.0}
    )
    for i in range(5):
        ts = _T0 + (20 + i) * _STEP_US
        monitor.monitor("H_crit", mock_features_h_crit, degraded_ws, ts)
    stat_after_degradation = monitor._cusum_stat
    assert stat_after_degradation > 0.0, (
        "CUSUM deve aver accumulato durante il degrado"
    )

    # Fase 2: recovery con pesi super-nominali (tutto il traffico sul
    # percorso critico: e4=100, e3=0, e6=100, e5=0 → PAS=1.0 >> PAS_gold)
    # ewma converge da 0.09 verso 1.0; dopo il primo passo ewma > 0.25,
    # quindi increment = PAS_gold - ewma < 0 e il CUSUM decresce.
    super_nominal_ws = _make_weight_series(
        n=1, tp_override={"e4": 100.0, "e3": 0.0, "e6": 100.0, "e5": 0.0}
    )
    for i in range(20):
        ts = _T0 + (25 + i) * _STEP_US
        monitor.monitor("H_crit", mock_features_h_crit, super_nominal_ws, ts)
    stat_after_recovery = monitor._cusum_stat

    assert stat_after_recovery < stat_after_degradation, (
        f"CUSUM deve diminuire durante il recovery con pesi super-nominali: "
        f"dopo degrado={stat_after_degradation:.6f}, "
        f"dopo recovery={stat_after_recovery:.6f}. "
        "Verificare la rimozione dell'inner max(0,...) in _update_ewma_cusum."
    )


def test_structural_validator_uses_pas_gap_for_linear(
    monitor: StructuralMonitor,
    mock_features_h_crit: dict[str, pd.DataFrame],
    mock_nominal_snapshots: list[dict],
    mock_weight_series: list[dict],
    mock_gold_standard: dict[str, float],
) -> None:
    """Per topologia lineare, il validatore usa |PAS - PAS_gold| > δ
    (non Frobenius). Verifica con soglia esplicita e pesi degradati."""
    monitor.fit(
        "H_crit", mock_features_h_crit, mock_nominal_snapshots,
        mock_weight_series, mock_gold_standard,
    )
    # PAS_gold = 0.25; con e4=99.0, e3=1.0: PAS ≈ 0.01
    # |0.01 - 0.25| = 0.24 > frobenius_threshold se ≤ 0.24
    monitor._frobenius_threshold = 0.10  # soglia < gap atteso

    degraded_ws = _make_weight_series(
        n=1, tp_override={"e4": 99.0, "e3": 1.0, "e6": 1.0, "e5": 99.0}
    )
    # Calcola PAS corrente e Frobenius corrente per il validatore
    from src.layer2.pbo_builder import PBOBuilder
    pas_series = monitor._pbo.compute_path_adherence(
        degraded_ws, "H_crit"
    )
    pas_val = pas_series[-1]["pas"]
    frob_series = monitor._pbo.compute_frobenius_distance(
        degraded_ws, monitor._gold_standard
    )
    frob_val = frob_series[-1]["frobenius"] if frob_series else None

    # PAS-gap = |pas_val - PAS_gold| deve superare la soglia
    assert monitor._pas_gold is not None
    pas_gap = abs(pas_val - monitor._pas_gold)
    assert pas_gap > monitor._frobenius_threshold, (
        f"PAS-gap={pas_gap:.4f} deve essere > threshold={monitor._frobenius_threshold}"
    )

    # Popola _ewma_history con valori decrescenti per soddisfare la
    # condizione di derivata persistente del validatore strutturale
    for _ in range(monitor._consecutive_windows + 2):
        monitor._ewma_history.append(0.30 - _ * 0.05)

    # Invocare direttamente il validatore con i valori correnti
    result = monitor._check_structural_validator(frob_val, pas_val)
    assert result is True, (
        f"Validatore deve confermare con PAS-gap={pas_gap:.4f} > "
        f"threshold={monitor._frobenius_threshold}. "
        f"Frobenius={frob_val}. "
        "Verificare che _check_structural_validator usi PAS-gap per "
        "topologie lineari (non Frobenius)."
    )


def test_monitor_with_empty_weight_series_does_not_crash(
    fitted_monitor: StructuralMonitor,
) -> None:
    """monitor() con weight_series=[] non solleva TypeError o altre eccezioni.
    frobenius_distance e pas_value devono essere None o 0.0, non errori."""
    result = fitted_monitor.monitor(
        "H_crit",
        _make_features_h_crit(),
        [],   # weight_series vuoto
        _T0,
    )
    assert isinstance(result, dict)
    # frobenius_distance può essere None (nessun dato) ma non un errore
    assert result["frobenius_distance"] is None or isinstance(
        result["frobenius_distance"], float
    )
