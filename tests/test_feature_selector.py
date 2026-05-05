"""Test per FeatureSelector — mock in memoria, nessun CSV reale."""
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from src.layer1.topology_builder import TopologyBuilder
from src.layer3.feature_selector import FeatureSelector
from src.utils.config_loader import ConfigLoader

_ROOT = Path(__file__).parent.parent
_TOPOLOGY_PATH = _ROOT / "config" / "topology.yaml"
_PIPELINE_PATH = _ROOT / "config" / "pipeline_params.yaml"

_T0 = 1_000_000
_T1 = 6_000_000
_T2 = 11_000_000

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

_TP = {"e1": 5.0, "e2": 5.0, "e3": 10.0, "e4": 10.0, "e5": 8.0, "e6": 12.0}


def _make_snapshot(ts: int, label: int) -> dict[str, Any]:
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
                "throughput_rps": _TP[eid],
            }
            for eid, src, tgt in _EDGES
        },
        "label": label,
        "anomaly_type": "cpu" if label == 1 else None,
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
def feature_selector(
    config: ConfigLoader, topology_builder: TopologyBuilder
) -> FeatureSelector:
    return FeatureSelector(config, topology_builder)


@pytest.fixture
def mock_snapshots() -> list[dict]:
    return [
        _make_snapshot(_T0, 0),
        _make_snapshot(_T1, 0),
        _make_snapshot(_T2, 1),
    ]


#TEST

def test_select_returns_dict(
    feature_selector: FeatureSelector, mock_snapshots: list[dict]
) -> None:
    result = feature_selector.select_features("H_crit", mock_snapshots)
    assert isinstance(result, dict)


def test_h_crit_direct_node_count(
    feature_selector: FeatureSelector, mock_snapshots: list[dict]
) -> None:
    """M_direct(H_crit): 5 nodi × 4 metriche = 20 chiavi 'node:'."""
    result = feature_selector.select_features("H_crit", mock_snapshots)
    node_keys = [k for k in result if k.startswith("node:")]
    assert len(node_keys) == 20


def test_h_crit_direct_edge_count(
    feature_selector: FeatureSelector, mock_snapshots: list[dict]
) -> None:
    """M_direct(H_crit): A(H_crit) = {e1,e2,e4,e6} × 3 metriche = 12 chiavi 'edge:'."""
    result = feature_selector.select_features("H_crit", mock_snapshots)
    edge_keys = [k for k in result if k.startswith("edge:")]
    assert len(edge_keys) == 12


def test_h_crit_no_interference(
    feature_selector: FeatureSelector, mock_snapshots: list[dict]
) -> None:
    """M_interf(H_crit, H_cache) = ∅ — nessuna chiave 'interf:' per H_crit."""
    result = feature_selector.select_features("H_crit", mock_snapshots)
    interf_keys = [k for k in result if k.startswith("interf:")]
    assert len(interf_keys) == 0


def test_h_cache_direct_node_count(
    feature_selector: FeatureSelector, mock_snapshots: list[dict]
) -> None:
    """M_direct(H_cache): 4 nodi × 4 metriche = 16 chiavi 'node:'."""
    result = feature_selector.select_features("H_cache", mock_snapshots)
    node_keys = [k for k in result if k.startswith("node:")]
    assert len(node_keys) == 16


def test_h_cache_direct_edge_count(
    feature_selector: FeatureSelector, mock_snapshots: list[dict]
) -> None:
    """M_direct(H_cache): A(H_cache) = {e3,e4,e5} × 3 metriche = 9 chiavi 'edge:'."""
    result = feature_selector.select_features("H_cache", mock_snapshots)
    edge_keys = [k for k in result if k.startswith("edge:")]
    assert len(edge_keys) == 9


def test_h_cache_has_interference(
    feature_selector: FeatureSelector, mock_snapshots: list[dict]
) -> None:
    """M_interf(H_cache, H_crit) = {e2} — esattamente 1 chiave 'interf:'."""
    result = feature_selector.select_features("H_cache", mock_snapshots)
    interf_keys = [k for k in result if k.startswith("interf:")]
    assert len(interf_keys) == 1


def test_h_cache_interference_key_format(
    feature_selector: FeatureSelector, mock_snapshots: list[dict]
) -> None:
    """La chiave di interferenza è 'interf:e2:throughput_rps'."""
    result = feature_selector.select_features("H_cache", mock_snapshots)
    assert "interf:e2:throughput_rps" in result


def test_dataframe_index_is_timestamp(
    feature_selector: FeatureSelector, mock_snapshots: list[dict]
) -> None:
    """Ogni DataFrame ha l'indice denominato 'timestamp'."""
    result = feature_selector.select_features("H_crit", mock_snapshots)
    key = next(iter(result))
    assert result[key].index.name == "timestamp"


def test_dataframe_column_is_value(
    feature_selector: FeatureSelector, mock_snapshots: list[dict]
) -> None:
    """Ogni DataFrame ha un'unica colonna 'value'."""
    result = feature_selector.select_features("H_crit", mock_snapshots)
    key = next(iter(result))
    assert list(result[key].columns) == ["value"]


def test_dataframe_length_matches_snapshots(
    feature_selector: FeatureSelector, mock_snapshots: list[dict]
) -> None:
    """Ogni DataFrame ha tante righe quanti gli snapshot (3)."""
    result = feature_selector.select_features("H_crit", mock_snapshots)
    key = next(iter(result))
    assert len(result[key]) == len(mock_snapshots)


def test_node_value_correct(
    feature_selector: FeatureSelector, mock_snapshots: list[dict]
) -> None:
    """cpu_percent di nginx-web-server a T0 corrisponde al valore nel mock (5.0)."""
    result = feature_selector.select_features("H_crit", mock_snapshots)
    df = result["node:nginx-web-server:cpu_percent"]
    assert abs(df.loc[_T0, "value"] - 5.0) < 1e-9


def test_edge_value_correct(
    feature_selector: FeatureSelector, mock_snapshots: list[dict]
) -> None:
    """latency_ms di e1 a T0 corrisponde al valore nel mock (10.0 ms)."""
    result = feature_selector.select_features("H_crit", mock_snapshots)
    df = result["edge:e1:latency_ms"]
    assert abs(df.loc[_T0, "value"] - 10.0) < 1e-9


def test_interf_value_is_throughput_only(
    feature_selector: FeatureSelector, mock_snapshots: list[dict]
) -> None:
    """La feature di interferenza contiene solo throughput_rps,
    non latency_ms né error_rate."""
    result = feature_selector.select_features("H_cache", mock_snapshots)
    assert "interf:e2:throughput_rps" in result
    assert "interf:e2:latency_ms" not in result
    assert "interf:e2:error_rate" not in result


def test_unknown_compliance_set_raises(
    feature_selector: FeatureSelector, mock_snapshots: list[dict]
) -> None:
    """select_features su nome inesistente solleva KeyError."""
    with pytest.raises(KeyError):
        feature_selector.select_features("H_nonexistent", mock_snapshots)


def test_get_feature_names_direct_count_h_crit(
    feature_selector: FeatureSelector,
) -> None:
    """get_feature_names('H_crit')['direct'] ha 32 elementi (20 nodo + 12 arco)."""
    names = feature_selector.get_feature_names("H_crit")
    assert len(names["direct"]) == 32


def test_get_feature_names_interference_count_h_crit(
    feature_selector: FeatureSelector,
) -> None:
    """get_feature_names('H_crit')['interference'] ha 0 elementi."""
    names = feature_selector.get_feature_names("H_crit")
    assert len(names["interference"]) == 0


def test_get_feature_names_interference_count_h_cache(
    feature_selector: FeatureSelector,
) -> None:
    """get_feature_names('H_cache')['interference'] ha 1 elemento (e2)."""
    names = feature_selector.get_feature_names("H_cache")
    assert len(names["interference"]) == 1


def test_select_features_key_order_deterministic(
    feature_selector: FeatureSelector, mock_snapshots: list[dict]
) -> None:
    """L'ordine delle chiavi node: in select_features è deterministico
    e coincide con quello di get_feature_names."""
    result = feature_selector.select_features("H_crit", mock_snapshots)
    names = feature_selector.get_feature_names("H_crit")
    result_direct_keys = [k for k in result if not k.startswith("interf:")]
    assert result_direct_keys == names["direct"]


def test_missing_node_series_has_float_nan_dtype(
    feature_selector: FeatureSelector,
) -> None:
    """Snapshot privo di un nodo: la serie restituisce float64
    con float('nan'), non dtype=object con pd.NA."""
    import math
    snap = {
        "timestamp": _T0,
        "nodes": {
            n: {"cpu_percent": 5.0, "mem_mb": 100.0,
                "net_rx_mb": 1.0, "net_tx_mb": 0.5}
            for n in _NODES if n != "nginx-web-server"
        },
        "edges": {
            eid: {"source": src, "target": tgt,
                  "latency_ms": 10.0, "error_rate": 0.0,
                  "throughput_rps": _TP[eid]}
            for eid, src, tgt in _EDGES
        },
        "label": 0,
        "anomaly_type": None,
        "anomaly_node_ids": [],
    }
    result = feature_selector.select_features("H_crit", [snap])
    df = result["node:nginx-web-server:cpu_percent"]
    assert df["value"].dtype == float, (
        f"Atteso dtype float64, ottenuto {df['value'].dtype}"
    )
    assert math.isnan(df.loc[_T0, "value"])


def test_get_feature_names_unknown_raises(
    feature_selector: FeatureSelector,
) -> None:
    """get_feature_names su nome inesistente solleva KeyError."""
    with pytest.raises(KeyError):
        feature_selector.get_feature_names("H_nonexistent")


def test_interf_value_numeric(
    feature_selector: FeatureSelector, mock_snapshots: list[dict]
) -> None:
    """Il valore della feature di interferenza 'interf:e2:throughput_rps'
    a T0 corrisponde a _TP['e2'] = 5.0."""
    result = feature_selector.select_features("H_cache", mock_snapshots)
    df = result["interf:e2:throughput_rps"]
    assert abs(df.loc[_T0, "value"] - _TP["e2"]) < 1e-9
