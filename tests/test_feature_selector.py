"""Test per FeatureSelector - mock in memoria, nessun CSV reale."""
from pathlib import Path
from typing import Any

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
    feature_selector: FeatureSelector,
    topology_builder: TopologyBuilder,
    config: ConfigLoader,
    mock_snapshots: list[dict],
) -> None:
    """M_direct(H_crit): n_nodi × n_node_metrics chiavi 'node:'."""
    topo = config.load_topology()
    expected = (
        len(topology_builder.get_compliance_set_nodes("H_crit"))
        * len(topo["node_metrics"])
    )
    result = feature_selector.select_features("H_crit", mock_snapshots)
    node_keys = [k for k in result if k.startswith("node:")]
    assert len(node_keys) == expected


def test_h_crit_direct_edge_count(
    feature_selector: FeatureSelector,
    topology_builder: TopologyBuilder,
    config: ConfigLoader,
    mock_snapshots: list[dict],
) -> None:
    """M_direct(H_crit): |A(H_crit)| × n_edge_metrics chiavi 'edge:'."""
    topo = config.load_topology()
    expected = (
        len(topology_builder.get_edges_for_compliance_set("H_crit"))
        * len(topo["edge_metrics"])
    )
    result = feature_selector.select_features("H_crit", mock_snapshots)
    edge_keys = [k for k in result if k.startswith("edge:")]
    assert len(edge_keys) == expected


def test_h_crit_no_interference(
    feature_selector: FeatureSelector,
    topology_builder: TopologyBuilder,
    config: ConfigLoader,
    mock_snapshots: list[dict],
) -> None:
    """M_interf(H_crit) = ∅ - nessuna chiave 'interf:' per H_crit."""
    topo = config.load_topology()
    cs_names = list(topo["compliance_sets"].keys())
    seen: set[tuple[str, str]] = set()
    for other in cs_names:
        if other == "H_crit":
            continue
        seen.update(topology_builder.get_interference_edges("H_crit", other))
    result = feature_selector.select_features("H_crit", mock_snapshots)
    interf_keys = [k for k in result if k.startswith("interf:")]
    assert len(interf_keys) == len(seen)


def test_h_cache_direct_node_count(
    feature_selector: FeatureSelector,
    topology_builder: TopologyBuilder,
    config: ConfigLoader,
    mock_snapshots: list[dict],
) -> None:
    """M_direct(H_cache): n_nodi × n_node_metrics chiavi 'node:'."""
    topo = config.load_topology()
    expected = (
        len(topology_builder.get_compliance_set_nodes("H_cache"))
        * len(topo["node_metrics"])
    )
    result = feature_selector.select_features("H_cache", mock_snapshots)
    node_keys = [k for k in result if k.startswith("node:")]
    assert len(node_keys) == expected


def test_h_cache_direct_edge_count(
    feature_selector: FeatureSelector,
    topology_builder: TopologyBuilder,
    config: ConfigLoader,
    mock_snapshots: list[dict],
) -> None:
    """M_direct(H_cache): |A(H_cache)| × n_edge_metrics chiavi 'edge:'."""
    topo = config.load_topology()
    expected = (
        len(topology_builder.get_edges_for_compliance_set("H_cache"))
        * len(topo["edge_metrics"])
    )
    result = feature_selector.select_features("H_cache", mock_snapshots)
    edge_keys = [k for k in result if k.startswith("edge:")]
    assert len(edge_keys) == expected


def test_h_cache_has_interference(
    feature_selector: FeatureSelector,
    topology_builder: TopologyBuilder,
    config: ConfigLoader,
    mock_snapshots: list[dict],
) -> None:
    """M_interf(H_cache) ha archi di interferenza da tutti gli altri CS."""
    topo = config.load_topology()
    cs_names = list(topo["compliance_sets"].keys())
    seen: set[tuple[str, str]] = set()
    for other in cs_names:
        if other == "H_cache":
            continue
        seen.update(topology_builder.get_interference_edges("H_cache", other))
    result = feature_selector.select_features("H_cache", mock_snapshots)
    interf_keys = [k for k in result if k.startswith("interf:")]
    assert len(interf_keys) == len(seen)


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
    topology_builder: TopologyBuilder,
    config: ConfigLoader,
) -> None:
    """get_feature_names('H_crit')['direct'] = n_nodi×n_node_m + n_archi×n_edge_m."""
    topo = config.load_topology()
    expected = (
        len(topology_builder.get_compliance_set_nodes("H_crit"))
        * len(topo["node_metrics"])
        + len(topology_builder.get_edges_for_compliance_set("H_crit"))
        * len(topo["edge_metrics"])
    )
    names = feature_selector.get_feature_names("H_crit")
    assert len(names["direct"]) == expected


def test_get_feature_names_interference_count_h_crit(
    feature_selector: FeatureSelector,
    topology_builder: TopologyBuilder,
    config: ConfigLoader,
) -> None:
    """get_feature_names('H_crit')['interference'] riflette M_interf dalla topologia."""
    topo = config.load_topology()
    cs_names = list(topo["compliance_sets"].keys())
    seen: set[tuple[str, str]] = set()
    for other in cs_names:
        if other == "H_crit":
            continue
        seen.update(topology_builder.get_interference_edges("H_crit", other))
    names = feature_selector.get_feature_names("H_crit")
    assert len(names["interference"]) == len(seen)


def test_get_feature_names_interference_count_h_cache(
    feature_selector: FeatureSelector,
    topology_builder: TopologyBuilder,
    config: ConfigLoader,
) -> None:
    """get_feature_names('H_cache')['interference'] riflette M_interf dalla topologia."""
    topo = config.load_topology()
    cs_names = list(topo["compliance_sets"].keys())
    seen: set[tuple[str, str]] = set()
    for other in cs_names:
        if other == "H_cache":
            continue
        seen.update(topology_builder.get_interference_edges("H_cache", other))
    names = feature_selector.get_feature_names("H_cache")
    assert len(names["interference"]) == len(seen)


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


def test_select_features_empty_snapshots(
    feature_selector: FeatureSelector,
) -> None:
    """select_features con lista snapshot vuota restituisce dict con chiavi
    corrette e DataFrame a 0 righe per ogni chiave."""
    result = feature_selector.select_features("H_crit", [])
    assert isinstance(result, dict)
    assert len(result) > 0
    for key, df in result.items():
        assert hasattr(df, "columns"), f"Chiave {key!r}: atteso DataFrame"
        assert len(df) == 0, f"Chiave {key!r}: atteso 0 righe, trovato {len(df)}"
        assert "value" in df.columns


def test_missing_interf_metric_produces_warning_not_error(
    config: ConfigLoader, topology_builder: TopologyBuilder
) -> None:
    """Se throughput_rps è assente da edge_metrics, FeatureSelector emette
    warning durante __init__ (non ValueError) e M_interf è vuoto."""
    import copy
    from unittest.mock import patch

    topo = config.load_topology()
    bad_topo = copy.deepcopy(topo)
    bad_topo["edge_metrics"] = [
        m for m in bad_topo["edge_metrics"] if m != "throughput_rps"
    ]
    with patch.object(type(config), "load_topology", return_value=bad_topo):
        with patch("src.layer3.feature_selector.logger") as mock_logger:
            fs = FeatureSelector(config, topology_builder)
    assert mock_logger.warning.called
    warning_text = " ".join(
        str(c) for c in mock_logger.warning.call_args_list
    )
    assert "throughput_rps" in warning_text or "interferenza" in warning_text
    result = fs.select_features("H_cache", [])
    interf_keys = [k for k in result if k.startswith("interf:")]
    assert len(interf_keys) == 0


def test_node_nan_value_preserved_as_float_nan(
    feature_selector: FeatureSelector,
) -> None:
    """Un valore numerico intero nel nodo produce dtype float64 nella serie.

    Guard di regressione contro la mancanza del cast float() in
    _build_node_series: senza float(raw), un valore int puro (es. 5)
    può produrre una colonna dtype=int64 o object invece di float64.
    """
    snap = {
        "timestamp": _T0,
        "nodes": {
            "nginx-web-server": {"cpu_percent": 5},  # int, non float
        },
        "edges": {},
    }
    result = feature_selector.select_features("H_crit", [snap])
    df = result["node:nginx-web-server:cpu_percent"]
    assert df["value"].dtype == float, (
        f"dtype atteso float64, ottenuto {df['value'].dtype}. "
        "Manca il cast float() in _build_node_series."
    )
    assert abs(df["value"].iloc[0] - 5.0) < 1e-9


def test_interf_key_order_matches_get_feature_names(
    feature_selector: FeatureSelector,
    mock_snapshots: list[dict],
) -> None:
    """Le chiavi interf: di select_features coincidono in ordine con
    get_feature_names(...)["interference"]. Estende
    test_select_features_key_order_deterministic alle chiavi interf:."""
    result = feature_selector.select_features("H_cache", mock_snapshots)
    names = feature_selector.get_feature_names("H_cache")

    interf_keys_from_result = [
        k for k in result if k.startswith("interf:")
    ]
    interf_keys_from_names = names["interference"]

    assert interf_keys_from_result == interf_keys_from_names, (
        f"Ordine interf: divergente tra select_features e get_feature_names.\n"
        f"select_features: {interf_keys_from_result}\n"
        f"get_feature_names: {interf_keys_from_names}"
    )


def test_node_partial_presence_produces_float_nan(
    feature_selector: FeatureSelector,
    mock_snapshots: list[dict],
) -> None:
    """Nodo presente in alcuni snapshot e assente in altri: la serie
    prodotta ha dtype=float64 con valori validi e float('nan') misti."""
    import math
    # Costruisci snapshot in cui nginx-web-server è assente solo al primo ts
    snap_missing = {
        "timestamp": mock_snapshots[0]["timestamp"],
        "nodes": {
            n: mock_snapshots[0]["nodes"][n]
            for n in mock_snapshots[0]["nodes"]
            if n != "nginx-web-server"
        },
        "edges": mock_snapshots[0]["edges"],
        "label": 0,
        "anomaly_type": None,
        "anomaly_node_ids": [],
    }
    mixed_snapshots = [snap_missing] + mock_snapshots[1:]
    result = feature_selector.select_features("H_crit", mixed_snapshots)
    key = "node:nginx-web-server:cpu_percent"
    assert key in result
    df = result[key]
    assert df["value"].dtype == float, (
        f"dtype atteso float64, ottenuto {df['value'].dtype}"
    )
    # Prima riga: NaN (nodo assente)
    assert math.isnan(df["value"].iloc[0]), (
        "Primo valore atteso NaN (nodo assente nel primo snapshot)"
    )
    # Righe successive: valore numerico valido
    assert not math.isnan(df["value"].iloc[1]), (
        "Secondo valore atteso non-NaN (nodo presente dal secondo snapshot)"
    )


def test_edge_metric_key_absent_produces_float_nan(
    feature_selector: FeatureSelector,
) -> None:
    """Se uno snapshot ha l'arco ma manca la chiave della metrica,
    _build_edge_series produce float('nan') con dtype=float64."""
    import math

    snap = {
        "timestamp": _T0,
        "nodes": {
            n: {"cpu_percent": 5.0, "mem_mb": 512.0,
                "net_rx_mb": 1.0, "net_tx_mb": 0.5}
            for n in _NODES
        },
        "edges": {
            "e1": {"source": "nginx-web-server", "target": "nginx-thrift",
                   "latency_ms": 10.0, "error_rate": 0.0}
            # throughput_rps assente intenzionalmente
        },
        "label": 0, "anomaly_type": None, "anomaly_node_ids": [],
    }
    result = feature_selector.select_features("H_crit", [snap])
    key = "edge:e1:throughput_rps"
    assert key in result
    df = result[key]
    assert df["value"].dtype == float
    assert math.isnan(df.loc[_T0, "value"])
