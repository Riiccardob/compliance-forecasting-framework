"""Test per ATGBuilder - mock sintetici in memoria, nessun CSV reale."""
import json
from pathlib import Path

import pandas as pd
import pytest

from src.utils.config_loader import ConfigLoader
from src.layer2.atg_builder import ATGBuilder

_ROOT = Path(__file__).parent.parent
_TOPOLOGY_PATH = _ROOT / "config" / "topology.yaml"
_PIPELINE_PATH = _ROOT / "config" / "pipeline_params.yaml"

#  Costanti mock 
_T0 = 1_000_000   # nominale
_T1 = 6_000_000   # anomalo cpu
_T2 = 11_000_000  # anomalo cpu_mem

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
    ("e1", "nginx-web-server",       "nginx-thrift"),
    ("e2", "nginx-thrift",           "home-timeline-service"),
    ("e3", "home-timeline-service",  "home-timeline-redis"),
    ("e4", "home-timeline-service",  "post-storage-service"),
    ("e5", "post-storage-service",   "post-storage-memcached"),
    ("e6", "post-storage-service",   "post-storage-mongodb"),
]


#  Builder di mock DataFrame 

def _make_node_metrics(timestamps: list[int]) -> pd.DataFrame:
    rows = []
    for ts in timestamps:
        for node in _NODES:
            rows.append({
                "timestamp": ts,
                "window_id": f"w_{ts}",
                "node_id": node,
                "cpu_percent": 5.0,
                "mem_mb": 100.0,
                "net_rx_mb": 1.0,
                "net_tx_mb": 0.5,
                "source_file": "mock.csv",
            })
    return pd.DataFrame(rows)


def _make_edge_metrics(timestamps: list[int]) -> pd.DataFrame:
    rows = []
    for ts in timestamps:
        for edge_id, source, target in _EDGES:
            rows.append({
                "timestamp": ts,
                "window_id": f"w_{ts}",
                "edge_id": edge_id,
                "source": source,
                "target": target,
                "latency_ms": 10.0,
                "error_rate": 0.0 if ts == _T0 else 0.5,
                "throughput_rps": 5.0,
                "source_file": "mock.csv",
            })
    return pd.DataFrame(rows)


def _make_ground_truth(timestamps: list[int]) -> pd.DataFrame:
    gt_specs = {
        _T0: (0, "cpu",     "[]"),
        _T1: (1, "cpu",     json.dumps(["nginx-web-server"])),
        _T2: (1, "cpu_mem", json.dumps(["post-storage-service"])),
    }
    rows = []
    for ts in timestamps:
        label, fault, anomaly_ids = gt_specs[ts]
        rows.append({
            "timestamp": ts,
            "window_id": f"w_{ts}",
            "fault_type": fault,
            "date": "aug9",
            "duration": "25min",
            "rps": 400,
            "replica_idx": 0,
            "label_trace": label,
            "anomaly_node_ids": anomaly_ids,
            "source_file": "mock.csv",
        })
    return pd.DataFrame(rows)


#  Fixture 

@pytest.fixture
def config() -> ConfigLoader:
    return ConfigLoader(_TOPOLOGY_PATH, _PIPELINE_PATH)


@pytest.fixture
def mock_paths(tmp_path: Path) -> dict[str, Path]:
    """Scrive i tre CSV mock su disco e restituisce i path."""
    ts_list = [_T0, _T1, _T2]
    nm = _make_node_metrics(ts_list)
    em = _make_edge_metrics(ts_list)
    gt = _make_ground_truth(ts_list)

    nm_path = tmp_path / "node_metrics.csv"
    em_path = tmp_path / "edge_metrics.csv"
    gt_path = tmp_path / "ground_truth.csv"

    nm.to_csv(nm_path, index=False)
    em.to_csv(em_path, index=False)
    gt.to_csv(gt_path, index=False)

    return {"node_metrics": nm_path, "edge_metrics": em_path, "ground_truth": gt_path}


@pytest.fixture
def builder(config: ConfigLoader, mock_paths: dict[str, Path]) -> ATGBuilder:
    return ATGBuilder(
        config,
        mock_paths["node_metrics"],
        mock_paths["edge_metrics"],
        mock_paths["ground_truth"],
    )


@pytest.fixture
def snapshots(builder: ATGBuilder) -> list[dict]:
    return builder.build()


#  Test: struttura della lista di snapshot 

def test_build_returns_list(snapshots: list[dict]) -> None:
    assert isinstance(snapshots, list)


def test_snapshot_count(snapshots: list[dict]) -> None:
    assert len(snapshots) == 3


def test_snapshot_keys(snapshots: list[dict]) -> None:
    required = {"timestamp", "nodes", "edges", "label", "anomaly_type", "anomaly_node_ids"}
    for snap in snapshots:
        assert set(snap.keys()) == required


def test_node_ids_complete(snapshots: list[dict]) -> None:
    """Ogni snapshot contiene tutti e 7 i nodi da topology.yaml."""
    for snap in snapshots:
        assert set(snap["nodes"].keys()) == set(_NODES)


def test_edge_ids_complete(snapshots: list[dict]) -> None:
    """Ogni snapshot contiene tutti e 6 gli archi da topology.yaml."""
    expected_edge_ids = {e[0] for e in _EDGES}
    for snap in snapshots:
        assert set(snap["edges"].keys()) == expected_edge_ids


#  Test: label e anomaly_type 

def test_nominal_label(snapshots: list[dict]) -> None:
    """t0 ha label==0 e anomaly_type is None."""
    t0_snap = next(s for s in snapshots if s["timestamp"] == _T0)
    assert t0_snap["label"] == 0
    assert t0_snap["anomaly_type"] is None


def test_anomalous_label(snapshots: list[dict]) -> None:
    """t1 ha label==1 e anomaly_type=='cpu'."""
    t1_snap = next(s for s in snapshots if s["timestamp"] == _T1)
    assert t1_snap["label"] == 1
    assert t1_snap["anomaly_type"] == "cpu"


def test_cpu_mem_type(snapshots: list[dict]) -> None:
    """t2 ha anomaly_type=='cpu_mem'."""
    t2_snap = next(s for s in snapshots if s["timestamp"] == _T2)
    assert t2_snap["anomaly_type"] == "cpu_mem"


def test_nominal_anomaly_node_ids_empty(snapshots: list[dict]) -> None:
    """t0 nominale ha anomaly_node_ids=[]."""
    t0_snap = next(s for s in snapshots if s["timestamp"] == _T0)
    assert t0_snap["anomaly_node_ids"] == []


#  Test: ordinamento 

def test_snapshots_ordered_by_timestamp(snapshots: list[dict]) -> None:
    ts_list = [s["timestamp"] for s in snapshots]
    assert ts_list == sorted(ts_list)


#  Test: get_node_feature_matrix 

def test_get_node_feature_matrix_shape(
    builder: ATGBuilder, snapshots: list[dict]
) -> None:
    """get_node_feature_matrix su nginx-web-server: shape (3, 4)."""
    df = builder.get_node_feature_matrix(snapshots, "nginx-web-server")
    assert df.shape == (3, 4)
    assert list(df.columns) == ["cpu_percent", "mem_mb", "net_rx_mb", "net_tx_mb"]


#  Test: get_edge_feature_matrix 

def test_get_edge_feature_matrix_shape(
    builder: ATGBuilder, snapshots: list[dict]
) -> None:
    """get_edge_feature_matrix su e1: shape (3, 3)."""
    df = builder.get_edge_feature_matrix(snapshots, "e1")
    assert df.shape == (3, 3)
    assert list(df.columns) == ["latency_ms", "error_rate", "throughput_rps"]


#  Test: filtri snapshot 

def test_get_nominal_snapshots_count(
    builder: ATGBuilder, snapshots: list[dict]
) -> None:
    """get_nominal_snapshots restituisce esattamente 1 elemento (t0)."""
    nominal = builder.get_nominal_snapshots(snapshots)
    assert len(nominal) == 1
    assert nominal[0]["timestamp"] == _T0


def test_get_anomalous_snapshots_all_count(
    builder: ATGBuilder, snapshots: list[dict]
) -> None:
    """get_anomalous_snapshots senza filtro restituisce 2 elementi (t1, t2)."""
    anomalous = builder.get_anomalous_snapshots(snapshots)
    assert len(anomalous) == 2


def test_get_anomalous_snapshots_by_type_count(
    builder: ATGBuilder, snapshots: list[dict]
) -> None:
    """get_anomalous_snapshots(anomaly_type='cpu') restituisce 1 elemento (t1)."""
    cpu_only = builder.get_anomalous_snapshots(snapshots, anomaly_type="cpu")
    assert len(cpu_only) == 1
    assert cpu_only[0]["timestamp"] == _T1


#  Test: ValueError su timestamp disallineati 

def test_duplicate_gt_timestamp_deduplicates(
    config: ConfigLoader, tmp_path: Path
) -> None:
    """Timestamp duplicati in ground_truth con label diverse:
    build() deduplica tenendo la prima occorrenza senza eccezioni."""
    nm = _make_node_metrics([_T0])
    em = _make_edge_metrics([_T0])

    gt_rows = [
        {"timestamp": _T0, "window_id": "w_a", "fault_type": "cpu",
         "date": "aug9", "duration": "25min", "rps": 400,
         "replica_idx": 0, "label_trace": 0,
         "anomaly_node_ids": "[]", "source_file": "exp_a.csv"},
        {"timestamp": _T0, "window_id": "w_b", "fault_type": "cpu",
         "date": "aug9", "duration": "25min", "rps": 400,
         "replica_idx": 1, "label_trace": 1,
         "anomaly_node_ids": "[]", "source_file": "exp_b.csv"},
    ]
    gt = pd.DataFrame(gt_rows)

    nm_path = tmp_path / "nm_dup.csv"
    em_path = tmp_path / "em_dup.csv"
    gt_path = tmp_path / "gt_dup.csv"
    nm.to_csv(nm_path, index=False)
    em.to_csv(em_path, index=False)
    gt.to_csv(gt_path, index=False)

    atg = ATGBuilder(config, nm_path, em_path, gt_path)
    snaps = atg.build()

    assert len(snaps) == 1
    assert snaps[0]["label"] == 0


def test_timestamp_mismatch_raises(
    config: ConfigLoader, tmp_path: Path
) -> None:
    """ValueError se node_metrics e edge_metrics hanno timestamp senza overlap."""
    nm = _make_node_metrics([_T0, _T1, _T2])
    # edge_metrics con timestamp completamente diversi
    em = _make_edge_metrics([_T0 + 999_999_999, _T1 + 999_999_999, _T2 + 999_999_999])
    gt = _make_ground_truth([_T0, _T1, _T2])

    nm_path = tmp_path / "nm_mismatch.csv"
    em_path = tmp_path / "em_mismatch.csv"
    gt_path = tmp_path / "gt_mismatch.csv"
    nm.to_csv(nm_path, index=False)
    em.to_csv(em_path, index=False)
    gt.to_csv(gt_path, index=False)

    atg = ATGBuilder(config, nm_path, em_path, gt_path)
    with pytest.raises(ValueError):
        atg.build()


def test_duplicate_node_timestamp_deduplicates(
    config: ConfigLoader, tmp_path: Path
) -> None:
    """Righe duplicate su (timestamp, node_id) con valori diversi:
    build() deduplica tenendo la prima occorrenza."""
    nm_rows = []
    for node in _NODES:
        nm_rows.append({
            "timestamp": _T0, "window_id": "w_a", "node_id": node,
            "cpu_percent": 10.0, "mem_mb": 100.0,
            "net_rx_mb": 1.0, "net_tx_mb": 0.5, "source_file": "exp_a.csv",
        })
        nm_rows.append({
            "timestamp": _T0, "window_id": "w_b", "node_id": node,
            "cpu_percent": 99.0, "mem_mb": 200.0,
            "net_rx_mb": 5.0, "net_tx_mb": 3.0, "source_file": "exp_b.csv",
        })
    nm = pd.DataFrame(nm_rows)
    em = _make_edge_metrics([_T0])
    gt = _make_ground_truth([_T0])

    nm_path = tmp_path / "nm_node_dup.csv"
    em_path = tmp_path / "em_node_dup.csv"
    gt_path = tmp_path / "gt_node_dup.csv"
    nm.to_csv(nm_path, index=False)
    em.to_csv(em_path, index=False)
    gt.to_csv(gt_path, index=False)

    snaps = ATGBuilder(config, nm_path, em_path, gt_path).build()

    assert len(snaps) == 1
    assert snaps[0]["nodes"]["nginx-web-server"]["cpu_percent"] == 10.0


def test_duplicate_edge_timestamp_deduplicates(
    config: ConfigLoader, tmp_path: Path
) -> None:
    """Righe duplicate su (timestamp, edge_id) con valori diversi:
    build() deduplica tenendo la prima occorrenza."""
    em_rows = []
    for edge_id, source, target in _EDGES:
        em_rows.append({
            "timestamp": _T0, "window_id": "w_a", "edge_id": edge_id,
            "source": source, "target": target,
            "latency_ms": 10.0, "error_rate": 0.0, "throughput_rps": 5.0,
            "source_file": "exp_a.csv",
        })
        em_rows.append({
            "timestamp": _T0, "window_id": "w_b", "edge_id": edge_id,
            "source": source, "target": target,
            "latency_ms": 999.0, "error_rate": 1.0, "throughput_rps": 0.0,
            "source_file": "exp_b.csv",
        })
    nm = _make_node_metrics([_T0])
    em = pd.DataFrame(em_rows)
    gt = _make_ground_truth([_T0])

    nm_path = tmp_path / "nm_edge_dup.csv"
    em_path = tmp_path / "em_edge_dup.csv"
    gt_path = tmp_path / "gt_edge_dup.csv"
    nm.to_csv(nm_path, index=False)
    em.to_csv(em_path, index=False)
    gt.to_csv(gt_path, index=False)

    snaps = ATGBuilder(config, nm_path, em_path, gt_path).build()

    assert len(snaps) == 1
    assert snaps[0]["edges"]["e1"]["latency_ms"] == 10.0


def test_snapshot_node_value_exact(snapshots: list[dict]) -> None:
    """I valori numerici nel dict nodes corrispondono ai dati mock."""
    t0_snap = next(s for s in snapshots if s["timestamp"] == _T0)
    node = t0_snap["nodes"]["nginx-web-server"]
    assert abs(node["cpu_percent"] - 5.0) < 1e-9
    assert abs(node["mem_mb"] - 100.0) < 1e-9
    assert abs(node["net_rx_mb"] - 1.0) < 1e-9
    assert abs(node["net_tx_mb"] - 0.5) < 1e-9


def test_snapshot_edge_value_exact(snapshots: list[dict]) -> None:
    """I valori numerici nel dict edges corrispondono ai dati mock."""
    t0_snap = next(s for s in snapshots if s["timestamp"] == _T0)
    edge = t0_snap["edges"]["e1"]
    assert abs(edge["latency_ms"] - 10.0) < 1e-9
    assert abs(edge["throughput_rps"] - 5.0) < 1e-9


def test_get_node_feature_matrix_unknown_node_returns_empty(
    builder: ATGBuilder, snapshots: list[dict]
) -> None:
    """get_node_feature_matrix su node_id inesistente restituisce
    DataFrame vuoto (nessun KeyError)."""
    df = builder.get_node_feature_matrix(snapshots, "nonexistent-service")
    assert df.empty
