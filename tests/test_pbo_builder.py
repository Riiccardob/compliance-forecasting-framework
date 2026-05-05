"""Test per PBOBuilder — Probabilistic Behavioral Overlay."""
import math
from pathlib import Path
from typing import Any

import pytest

from src.utils.config_loader import ConfigLoader
from src.layer1.topology_builder import TopologyBuilder
from src.layer2.pbo_builder import PBOBuilder

_ROOT = Path(__file__).parent.parent
_TOPOLOGY_PATH = _ROOT / "config" / "topology.yaml"
_PIPELINE_PATH = _ROOT / "config" / "pipeline_params.yaml"

_T0 = 1_000_000   # nominale
_T1 = 6_000_000   # nominale
_T2 = 11_000_000  # anomalo cpu

_NODES = [
    "nginx-web-server",
    "nginx-thrift",
    "home-timeline-service",
    "home-timeline-redis",
    "post-storage-service",
    "post-storage-memcached",
    "post-storage-mongodb",
]

_EDGES = [
    ("e1", "nginx-web-server",      "nginx-thrift"),
    ("e2", "nginx-thrift",          "home-timeline-service"),
    ("e3", "home-timeline-service", "home-timeline-redis"),
    ("e4", "home-timeline-service", "post-storage-service"),
    ("e5", "post-storage-service",  "post-storage-memcached"),
    ("e6", "post-storage-service",  "post-storage-mongodb"),
]

_TP_NOMINAL = {"e1": 5.0, "e2": 5.0, "e3": 10.0, "e4": 10.0, "e5": 8.0, "e6": 12.0}
_TP_ANOMALY = {"e1": 5.0, "e2": 5.0, "e3": 2.0,  "e4": 18.0, "e5": 8.0, "e6": 12.0}


def _make_snapshot(
    ts: int, label: int, fault_type: str, throughputs: dict[str, float]
) -> dict[str, Any]:
    return {
        "timestamp": ts,
        "nodes": {
            n: {"cpu_percent": 5.0, "mem_mb": 100.0, "net_rx_mb": 1.0, "net_tx_mb": 0.5}
            for n in _NODES
        },
        "edges": {
            eid: {
                "source": src,
                "target": tgt,
                "latency_ms": 10.0,
                "error_rate": 0.0,
                "throughput_rps": throughputs[eid],
            }
            for eid, src, tgt in _EDGES
        },
        "label": label,
        "anomaly_type": fault_type if label == 1 else None,
        "anomaly_node_ids": [],
    }


#FIXTURE

@pytest.fixture
def config() -> ConfigLoader:
    return ConfigLoader(_TOPOLOGY_PATH, _PIPELINE_PATH)


@pytest.fixture
def topology_builder(config: ConfigLoader) -> TopologyBuilder:
    return TopologyBuilder(config)


@pytest.fixture
def pbo(config: ConfigLoader, topology_builder: TopologyBuilder) -> PBOBuilder:
    return PBOBuilder(config, topology_builder)


@pytest.fixture
def mock_snapshots() -> list[dict]:
    return [
        _make_snapshot(_T0, 0, "cpu", _TP_NOMINAL),
        _make_snapshot(_T1, 0, "cpu", _TP_NOMINAL),
        _make_snapshot(_T2, 1, "cpu", _TP_ANOMALY),
    ]


@pytest.fixture
def weight_series(pbo: PBOBuilder, mock_snapshots: list[dict]) -> list[dict]:
    return pbo.compute_transition_weights(mock_snapshots)


@pytest.fixture
def gold_standard(
    pbo: PBOBuilder,
    weight_series: list[dict],
    mock_snapshots: list[dict],
) -> dict[str, float]:
    return pbo.compute_gold_standard(weight_series, mock_snapshots)


#TEST

def test_weight_series_length(weight_series: list[dict]) -> None:
    assert len(weight_series) == 3


def test_weights_stochastic_per_source(weight_series: list[dict]) -> None:
    """Per ogni nodo con archi uscenti, Σ w_uscenti == 1.0."""
    source_to_eids: dict[str, list[str]] = {}
    for eid, src, _ in _EDGES:
        source_to_eids.setdefault(src, []).append(eid)

    for entry in weight_series:
        weights = entry["weights"]
        for src, eids in source_to_eids.items():
            present = [eid for eid in eids if eid in weights]
            if present:
                total = sum(weights[eid] for eid in present)
                assert abs(total - 1.0) < 1e-6, (
                    f"t={entry['timestamp']}, src={src}: sum={total}"
                )


def test_weight_e4_symmetric_at_t0(weight_series: list[dict]) -> None:
    """A t0: w(e4) = 10 / (10+10) = 0.5."""
    entry = next(e for e in weight_series if e["timestamp"] == _T0)
    assert abs(entry["weights"]["e4"] - 0.5) < 1e-9


def test_weight_e4_asymmetric_at_t2(weight_series: list[dict]) -> None:
    """A t2: w(e4) = 18 / (18+2) = 0.9."""
    entry = next(e for e in weight_series if e["timestamp"] == _T2)
    assert abs(entry["weights"]["e4"] - 0.9) < 1e-9


def test_gold_standard_uses_only_nominal(
    gold_standard: dict[str, float],
) -> None:
    """W_gold["e4"] = (0.5 + 0.5) / 2 = 0.5 (media di t0 e t1, entrambi nominali)."""
    assert abs(gold_standard["e4"] - 0.5) < 1e-9


def test_gold_standard_no_nominal_raises(
    pbo: PBOBuilder,
) -> None:
    """ValueError se tutti gli snapshot hanno label==1."""
    all_anomalous = [
        _make_snapshot(_T0, 1, "cpu", _TP_NOMINAL),
        _make_snapshot(_T1, 1, "cpu", _TP_NOMINAL),
    ]
    ws_anomalous = pbo.compute_transition_weights(all_anomalous)
    with pytest.raises(ValueError):
        pbo.compute_gold_standard(ws_anomalous, all_anomalous)


def test_pas_h_crit_in_range(
    pbo: PBOBuilder, weight_series: list[dict]
) -> None:
    """PA(H_crit, t) ∈ [0.0, 1.0] per tutti i timestamp."""
    pas_series = pbo.compute_path_adherence(weight_series, "H_crit")
    for entry in pas_series:
        assert 0.0 <= entry["pas"] <= 1.0, f"PAS={entry['pas']} fuori range"


def test_pas_h_crit_length(
    pbo: PBOBuilder, weight_series: list[dict]
) -> None:
    """Lista PAS ha 3 elementi (uno per snapshot)."""
    pas_series = pbo.compute_path_adherence(weight_series, "H_crit")
    assert len(pas_series) == 3


def test_pas_parallel_raises(
    pbo: PBOBuilder, weight_series: list[dict]
) -> None:
    """compute_path_adherence su H_cache (parallel) solleva ValueError."""
    with pytest.raises(ValueError):
        pbo.compute_path_adherence(weight_series, "H_cache")


def test_frobenius_non_negative(
    pbo: PBOBuilder,
    weight_series: list[dict],
    gold_standard: dict[str, float],
) -> None:
    """frobenius ≥ 0.0 per tutti i timestamp."""
    frob_series = pbo.compute_frobenius_distance(weight_series, gold_standard)
    for entry in frob_series:
        assert entry["frobenius"] >= 0.0


def test_frobenius_zero_at_nominal(
    pbo: PBOBuilder,
    weight_series: list[dict],
    gold_standard: dict[str, float],
) -> None:
    """A t0 e t1 (weights == W_gold): frobenius ≈ 0.0."""
    frob_series = pbo.compute_frobenius_distance(weight_series, gold_standard)
    for entry in frob_series:
        if entry["timestamp"] in (_T0, _T1):
            assert entry["frobenius"] < 1e-9, (
                f"t={entry['timestamp']}: frobenius={entry['frobenius']} ≠ 0"
            )


def test_frobenius_positive_at_anomaly(
    pbo: PBOBuilder,
    weight_series: list[dict],
    gold_standard: dict[str, float],
) -> None:
    """A t2: frobenius > 0.0 (e4 cambia da 0.5 a 0.9)."""
    frob_series = pbo.compute_frobenius_distance(weight_series, gold_standard)
    t2_entry = next(e for e in frob_series if e["timestamp"] == _T2)
    assert t2_entry["frobenius"] > 0.0


def test_frobenius_length(
    pbo: PBOBuilder,
    weight_series: list[dict],
    gold_standard: dict[str, float],
) -> None:
    """Lista Frobenius ha 3 elementi."""
    frob_series = pbo.compute_frobenius_distance(weight_series, gold_standard)
    assert len(frob_series) == 3


def test_weight_fallback_uniform_on_zero_throughput(
    pbo: PBOBuilder,
) -> None:
    """Se throughput totale uscente da un nodo è zero, i pesi
    sono uniformi (1/n) e la somma rimane 1.0."""
    snap_zero_tp = _make_snapshot(
        _T0, 0, "cpu",
        {"e1": 5.0, "e2": 5.0, "e3": 0.0, "e4": 0.0,
         "e5": 8.0, "e6": 12.0},
    )
    ws = pbo.compute_transition_weights([snap_zero_tp])
    weights = ws[0]["weights"]
    assert abs(weights["e3"] - 0.5) < 1e-9
    assert abs(weights["e4"] - 0.5) < 1e-9
    assert abs(weights["e3"] + weights["e4"] - 1.0) < 1e-9


def test_gold_standard_covers_all_topology_edges(
    pbo: PBOBuilder,
) -> None:
    """W_gold include tutti gli archi della topologia (E_all),
    anche quelli assenti nel primo snapshot nominale."""
    snap_no_e6 = _make_snapshot(
        _T0, 0, "cpu",
        {"e1": 5.0, "e2": 5.0, "e3": 10.0, "e4": 10.0,
         "e5": 8.0, "e6": 0.0},
    )
    snap_with_e6 = _make_snapshot(
        _T1, 0, "cpu",
        {"e1": 5.0, "e2": 5.0, "e3": 10.0, "e4": 10.0,
         "e5": 8.0, "e6": 12.0},
    )
    ws = pbo.compute_transition_weights([snap_no_e6, snap_with_e6])
    snaps = [snap_no_e6, snap_with_e6]
    gold = pbo.compute_gold_standard(ws, snaps)
    assert "e6" in gold


def test_pas_h_crit_exact_value_nominal(
    pbo: PBOBuilder, weight_series: list[dict]
) -> None:
    """PA(H_crit, t0) = w(e1)×w(e2)×w(e4)×w(e6) = 1.0×1.0×0.5×0.6 = 0.30.

    Con _TP_NOMINAL: e1 e e2 hanno sorgenti con un solo arco uscente (w=1.0),
    e4 = 10/(10+10) = 0.5, e6 = 12/(8+12) = 0.6.
    """
    pas_series = pbo.compute_path_adherence(weight_series, "H_crit")
    t0_entry = next(e for e in pas_series if e["timestamp"] == _T0)
    assert abs(t0_entry["pas"] - 0.30) < 1e-9


def test_frobenius_exact_value_at_anomaly(
    pbo: PBOBuilder,
    weight_series: list[dict],
    gold_standard: dict[str, float],
) -> None:
    """frobenius(t2) = sqrt(Δe3² + Δe4²) = sqrt(0.16+0.16) = sqrt(0.32).

    A t2 con _TP_ANOMALY: e3=0.1, e4=0.9 vs W_gold e3=0.5, e4=0.5.
    Δe3 = −0.4, Δe4 = +0.4, tutti gli altri archi invariati.
    """
    frob_series = pbo.compute_frobenius_distance(weight_series, gold_standard)
    t2_entry = next(e for e in frob_series if e["timestamp"] == _T2)
    assert abs(t2_entry["frobenius"] - math.sqrt(0.32)) < 1e-9


def test_pas_invalid_compliance_set_raises(
    pbo: PBOBuilder, weight_series: list[dict]
) -> None:
    """compute_path_adherence su nome inesistente solleva KeyError."""
    with pytest.raises(KeyError, match="Compliance set non trovato"):
        pbo.compute_path_adherence(weight_series, "H_nonexistent")


def test_gold_standard_key_arcs(
    gold_standard: dict[str, float],
) -> None:
    """W_gold: e1=1.0 (sorgente con singolo arco uscente), e6=12/(8+12)=0.6."""
    assert abs(gold_standard["e1"] - 1.0) < 1e-9
    assert abs(gold_standard["e6"] - 0.6) < 1e-9


def test_weight_negative_throughput_uses_uniform_fallback(
    pbo: PBOBuilder,
) -> None:
    """Throughput negativo su un arco attiva fallback uniforme.
    Il peso negativo viola la proprietà stocastica."""
    snap = _make_snapshot(
        _T0, 0, "cpu",
        {"e1": 5.0, "e2": 5.0, "e3": -1.0, "e4": 10.0,
         "e5": 8.0, "e6": 12.0},
    )
    ws = pbo.compute_transition_weights([snap])
    w = ws[0]["weights"]
    # home-timeline-service ha e3 e e4 — fallback uniforme = 0.5
    assert abs(w["e3"] - 0.5) < 1e-9
    assert abs(w["e4"] - 0.5) < 1e-9


def test_weight_invalid_metric_raises_at_init(
    config: ConfigLoader,
    topology_builder: TopologyBuilder,
) -> None:
    """weight_metric non in edge_metrics solleva ValueError in __init__."""
    from unittest.mock import patch
    import copy
    pipeline = config.load_pipeline_params()
    bad_pipeline = copy.deepcopy(pipeline)
    bad_pipeline["pbo"]["weight_metric"] = "nonexistent_metric"
    with patch.object(type(config), "load_pipeline_params",
                      return_value=bad_pipeline):
        with pytest.raises(ValueError, match="weight_metric"):
            PBOBuilder(config, topology_builder)


def test_path_adherence_missing_arc_raises(
    pbo: PBOBuilder, weight_series: list[dict]
) -> None:
    """compute_path_adherence con critical_path che contiene
    un arco mancante solleva ValueError descrittivo."""
    from unittest.mock import patch
    bad_path = [
        "nginx-web-server", "post-storage-service", "post-storage-mongodb"
    ]
    with patch.object(
        pbo._topology_builder, "get_critical_path", return_value=bad_path
    ):
        with pytest.raises(ValueError, match="non esiste in topology"):
            pbo.compute_path_adherence(weight_series, "H_crit")


def test_gold_standard_covers_absent_edge(
    pbo: PBOBuilder,
    weight_series: list[dict],
    mock_snapshots: list[dict],
) -> None:
    """W_gold include e6 anche se e6 è assente da uno snapshot
    nominale — viene trattato come peso 0.0 per quel timestamp."""
    import copy
    ws_mod = copy.deepcopy(weight_series)
    ws_mod[0]["weights"].pop("e6", None)
    gold = pbo.compute_gold_standard(ws_mod, mock_snapshots)
    # e6 deve comunque esistere nel gold (media su 2 nominali:
    # 0.0 dal primo snapshot + 0.6 dal secondo = 0.3)
    assert "e6" in gold
    assert abs(gold["e6"] - 0.3) < 1e-9


def test_weight_nan_throughput_uses_uniform_fallback(
    pbo: PBOBuilder,
) -> None:
    """NaN in throughput_rps attiva il fallback uniforme
    senza propagare NaN nella matrice stocastica."""
    import math
    snap = _make_snapshot(
        _T0, 0, "cpu",
        {
            "e1": 5.0, "e2": 5.0,
            "e3": float("nan"), "e4": 10.0,
            "e5": 8.0, "e6": 12.0,
        },
    )
    ws = pbo.compute_transition_weights([snap])
    w = ws[0]["weights"]
    # Nessun NaN si propaga
    assert not math.isnan(w.get("e3", 0.0))
    assert not math.isnan(w.get("e4", 0.0))
    # Proprietà stocastica: e3 e e4 sommano a 1.0
    assert abs(w["e3"] + w["e4"] - 1.0) < 1e-9