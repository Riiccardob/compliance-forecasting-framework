"""Test per ConfigLoader: caricamento e validazione dei file di configurazione."""

import logging
from pathlib import Path

import pytest

from src.utils.config_loader import ConfigLoader
from src.utils.logging_setup import LoggingSetup

_ROOT = Path(__file__).parent.parent
_TOPOLOGY_PATH = _ROOT / "config" / "topology.yaml"
_PIPELINE_PATH = _ROOT / "config" / "pipeline_params.yaml"

_MOCK_TOPOLOGY_YAML = """\
metadata:
  system_name: test-system
  window_duration_seconds: 5.0
nodes:
  - {id: s1}
  - {id: s2}
edges:
  - {id: e1, source: s1, target: s2}
compliance_sets:
  CS_test:
    topology_type: linear
    nodes: [s1, s2]
    critical_path:
      sequence: [s1, s2]
    sla: {}
node_metrics: [cpu_percent]
edge_metrics: [latency_ms]
data_paths:
  raw_dir: data/raw
  node_metrics_csv: data/node_metrics.csv
  edge_metrics_csv: data/edge_metrics.csv
  ground_truth_csv: data/ground_truth.csv
"""

_MOCK_PIPELINE_YAML = """\
version: "1.0"
pbo:
  weight_metric: latency_ms
  gold_standard_label: 0
forecasting:
  horizon_steps: 6
  lstm:
    nonlinear_metrics: [cpu_percent]
    input_window: 4
  arima:
    max_p: 2
    max_d: 1
    max_q: 2
causal_analysis:
  pearson_threshold: 0.3
  granger_max_lag: 5
anomaly_detection:
  cusum:
    ewma_alpha: 0.3
alert_generation:
  red_days: 2
"""


#  Module-level fixtures (used by DSB pipeline content tests)


@pytest.fixture
def loader() -> ConfigLoader:
    return ConfigLoader(_TOPOLOGY_PATH, _PIPELINE_PATH)


@pytest.fixture
def pipeline(loader: ConfigLoader) -> dict:
    return loader.load_pipeline_params()


#  Behavior tests


def test_load_topology_returns_dict(tmp_path: Path) -> None:
    topo = tmp_path / "topology.yaml"
    pipe = tmp_path / "pipeline.yaml"
    topo.write_text(_MOCK_TOPOLOGY_YAML, encoding="utf-8")
    pipe.write_text(_MOCK_PIPELINE_YAML, encoding="utf-8")
    mock_loader = ConfigLoader(topo, pipe)
    assert isinstance(mock_loader.load_topology(), dict)


def test_pipeline_params_loads(tmp_path: Path) -> None:
    topo = tmp_path / "topology.yaml"
    pipe = tmp_path / "pipeline.yaml"
    topo.write_text(_MOCK_TOPOLOGY_YAML, encoding="utf-8")
    pipe.write_text(_MOCK_PIPELINE_YAML, encoding="utf-8")
    mock_loader = ConfigLoader(topo, pipe)
    assert isinstance(mock_loader.load_pipeline_params(), dict)


#  Pipeline content - DSB regression guard


def test_lstm_config_present(pipeline: dict) -> None:
    assert "lstm" in pipeline["forecasting"]


def test_arima_config_present(pipeline: dict) -> None:
    assert "arima" in pipeline["forecasting"]


#  Error handling


def test_missing_topology_file_raises() -> None:
    missing = Path("/nonexistent/path/topology.yaml")
    loader = ConfigLoader(missing, _PIPELINE_PATH)
    with pytest.raises(FileNotFoundError) as exc_info:
        loader.load_topology()
    assert str(missing.resolve()) in str(exc_info.value)


def test_missing_key_raises(tmp_path: Path) -> None:
    incomplete = tmp_path / "topology_incomplete.yaml"
    incomplete.write_text("metadata: {}\nnodes: []\n", encoding="utf-8")
    loader = ConfigLoader(incomplete, _PIPELINE_PATH)
    with pytest.raises(ValueError) as exc_info:
        loader.load_topology()
    assert "edges" in str(exc_info.value)


def test_empty_yaml_raises_value_error(tmp_path: Path) -> None:
    empty = tmp_path / "empty.yaml"
    empty.write_text("", encoding="utf-8")
    loader = ConfigLoader(empty, _PIPELINE_PATH)
    with pytest.raises(ValueError, match="mapping YAML valido"):
        loader.load_topology()


def test_invalid_log_level_raises() -> None:
    with pytest.raises(ValueError, match="Livello di log non valido"):
        LoggingSetup.configure("test", "VERBOS")


def test_lowercase_level_accepted() -> None:
    """configure() accepts lowercase level strings
    (e.g. 'info' is equivalent to 'INFO')."""
    logger = LoggingSetup.configure("lowercase_test", "info")
    assert logger.level == logging.INFO


def test_logging_idempotent_no_duplicate_handlers() -> None:
    """Chiamate multiple a configure() sullo stesso nome non
    duplicano gli handler e non cambiano il livello."""
    logger1 = LoggingSetup.configure("idempotency_test", "INFO")
    logger2 = LoggingSetup.configure("idempotency_test", "DEBUG")
    assert logger1 is logger2
    assert len(logger1.handlers) == 1
    # Il livello rimane quello della prima configurazione (INFO),
    # non viene sovrascritto dalla seconda chiamata (DEBUG).
    assert logger1.level == logging.INFO


def test_load_pipeline_params_missing_file_raises() -> None:
    """FileNotFoundError se pipeline_path non esiste."""
    missing = Path("/nonexistent/pipeline_params.yaml")
    loader = ConfigLoader(_TOPOLOGY_PATH, missing)
    with pytest.raises(FileNotFoundError) as exc_info:
        loader.load_pipeline_params()
    assert str(missing.resolve()) in str(exc_info.value)


def test_load_pipeline_params_missing_key_raises(
    tmp_path: Path,
) -> None:
    """ValueError se manca una chiave obbligatoria in pipeline_params."""
    incomplete = tmp_path / "pipeline_incomplete.yaml"
    incomplete.write_text("version: '1.0'\npbo: {}\n", encoding="utf-8")
    loader = ConfigLoader(_TOPOLOGY_PATH, incomplete)
    with pytest.raises(ValueError) as exc_info:
        loader.load_pipeline_params()
    assert "forecasting" in str(exc_info.value)


def test_yaml_root_list_raises(tmp_path: Path) -> None:
    """YAML con radice lista (non dict) solleva ValueError."""
    list_yaml = tmp_path / "list.yaml"
    list_yaml.write_text("- item1\n- item2\n", encoding="utf-8")
    loader = ConfigLoader(list_yaml, _PIPELINE_PATH)
    with pytest.raises(ValueError):
        loader.load_topology()


def test_window_duration_seconds_missing_raises(
    tmp_path: Path,
) -> None:
    """load_topology solleva ValueError se metadata non ha
    window_duration_seconds."""
    bad = tmp_path / "topo_no_wds.yaml"
    bad.write_text(
        "metadata:\n"
        "  system_name: test\n"
        "nodes: [{id: s1}]\n"
        "edges: []\n"
        "compliance_sets: {}\n"
        "node_metrics: [cpu]\n"
        "edge_metrics: [latency]\n"
        "data_paths: {raw_dir: data/raw,\n"
        "  node_metrics_csv: data/n.csv,\n"
        "  edge_metrics_csv: data/e.csv,\n"
        "  ground_truth_csv: data/g.csv}\n",
        encoding="utf-8",
    )
    loader = ConfigLoader(bad, _PIPELINE_PATH)
    with pytest.raises(ValueError, match="window_duration_seconds"):
        loader.load_topology()


def test_window_duration_seconds_invalid_raises(
    tmp_path: Path,
) -> None:
    """load_topology solleva ValueError se window_duration_seconds
    è non positivo."""
    bad = tmp_path / "topo_bad_wds.yaml"
    bad.write_text(
        "metadata:\n"
        "  system_name: test\n"
        "  window_duration_seconds: -5.0\n"
        "nodes: [{id: s1}]\n"
        "edges: []\n"
        "compliance_sets: {}\n"
        "node_metrics: [cpu]\n"
        "edge_metrics: [latency]\n"
        "data_paths: {raw_dir: data/raw,\n"
        "  node_metrics_csv: data/n.csv,\n"
        "  edge_metrics_csv: data/e.csv,\n"
        "  ground_truth_csv: data/g.csv}\n",
        encoding="utf-8",
    )
    loader = ConfigLoader(bad, _PIPELINE_PATH)
    with pytest.raises(ValueError):
        loader.load_topology()


def test_malformed_yaml_raises(tmp_path: Path) -> None:
    """YAML sintaticamente invalido solleva ValueError con messaggio
    esplicito - non propaga yaml.YAMLError raw."""
    malformed = tmp_path / "malformed.yaml"
    malformed.write_text(
        "metadata:\n  key: valid\nnodes: [\n  - broken",
        encoding="utf-8",
    )
    loader = ConfigLoader(malformed, _PIPELINE_PATH)
    with pytest.raises(ValueError, match="sintaticamente non valido"):
        loader.load_topology()


#  Cache isolation


def test_load_topology_cache_is_isolated(tmp_path: Path) -> None:
    """Mutare il dict restituito non corrompe la cache interna."""
    topo = tmp_path / "topology.yaml"
    pipe = tmp_path / "pipeline.yaml"
    topo.write_text(_MOCK_TOPOLOGY_YAML, encoding="utf-8")
    pipe.write_text(_MOCK_PIPELINE_YAML, encoding="utf-8")
    mock_loader = ConfigLoader(topo, pipe)
    t1 = mock_loader.load_topology()
    original_count = len(t1["nodes"])
    t1["nodes"].append({"id": "injected-sentinel"})
    t2 = mock_loader.load_topology()
    assert len(t2["nodes"]) == original_count


def test_load_pipeline_cache_is_isolated(tmp_path: Path) -> None:
    """Mutare il dict di pipeline restituito non corrompe la cache."""
    topo = tmp_path / "topology.yaml"
    pipe = tmp_path / "pipeline.yaml"
    topo.write_text(_MOCK_TOPOLOGY_YAML, encoding="utf-8")
    pipe.write_text(_MOCK_PIPELINE_YAML, encoding="utf-8")
    mock_loader = ConfigLoader(topo, pipe)
    p1 = mock_loader.load_pipeline_params()
    p1["forecasting"]["injected_key"] = "sentinel"
    p2 = mock_loader.load_pipeline_params()
    assert "injected_key" not in p2["forecasting"]


def test_load_topology_cache_deep_isolation(tmp_path: Path) -> None:
    """Mutare una struttura annidata nel dict restituito non corrompe
    la cache interna (deepcopy protegge anche i livelli annidati)."""
    topo = tmp_path / "topology.yaml"
    pipe = tmp_path / "pipeline.yaml"
    topo.write_text(_MOCK_TOPOLOGY_YAML, encoding="utf-8")
    pipe.write_text(_MOCK_PIPELINE_YAML, encoding="utf-8")
    mock_loader = ConfigLoader(topo, pipe)
    t1 = mock_loader.load_topology()
    original_len = len(t1["compliance_sets"]["CS_test"]["nodes"])
    t1["compliance_sets"]["CS_test"]["nodes"].append("injected-sentinel")
    t2 = mock_loader.load_topology()
    assert len(t2["compliance_sets"]["CS_test"]["nodes"]) == original_len


def test_load_pipeline_cache_deep_isolation(tmp_path: Path) -> None:
    """Mutare una struttura annidata nel dict pipeline restituito
    non corrompe la cache interna."""
    topo = tmp_path / "topology.yaml"
    pipe = tmp_path / "pipeline.yaml"
    topo.write_text(_MOCK_TOPOLOGY_YAML, encoding="utf-8")
    pipe.write_text(_MOCK_PIPELINE_YAML, encoding="utf-8")
    mock_loader = ConfigLoader(topo, pipe)
    p1 = mock_loader.load_pipeline_params()
    p1["anomaly_detection"]["cusum"]["ewma_alpha"] = 999.0
    p2 = mock_loader.load_pipeline_params()
    assert p2["anomaly_detection"]["cusum"]["ewma_alpha"] != 999.0


#  DSB topology content - regression guard


class TestTopologyYamlContent:
    """Regression guard on the content of config/topology.yaml for
    the DSB dataset. These tests verify the structure of the current
    dataset-specific configuration, NOT the behavior of ConfigLoader.
    Update them when switching to a different dataset or topology."""

    @pytest.fixture
    def real_topology(self) -> dict:
        loader = ConfigLoader(_TOPOLOGY_PATH, _PIPELINE_PATH)
        return loader.load_topology()

    @pytest.fixture
    def real_pipeline(self) -> dict:
        loader = ConfigLoader(_TOPOLOGY_PATH, _PIPELINE_PATH)
        return loader.load_pipeline_params()

    def test_nodes_count(self, real_topology: dict) -> None:
        assert len(real_topology["nodes"]) == 7

    def test_edges_count(self, real_topology: dict) -> None:
        assert len(real_topology["edges"]) == 6

    def test_compliance_sets_present(self, real_topology: dict) -> None:
        cs = real_topology["compliance_sets"]
        assert "H_crit" in cs
        assert "H_cache" in cs

    def test_h_crit_node_count(self, real_topology: dict) -> None:
        assert len(real_topology["compliance_sets"]["H_crit"]["nodes"]) == 5

    def test_h_cache_node_count(self, real_topology: dict) -> None:
        assert len(real_topology["compliance_sets"]["H_cache"]["nodes"]) == 4

    def test_critical_path_length(self, real_topology: dict) -> None:
        seq = real_topology["compliance_sets"]["H_crit"]["critical_path"]["sequence"]
        assert len(seq) == 5

    def test_edge_naming_starts_at_e1(self, real_topology: dict) -> None:
        assert real_topology["edges"][0]["id"] == "e1"

    def test_node_metrics_exact(self, real_topology: dict) -> None:
        assert real_topology["node_metrics"] == [
            "cpu_percent",
            "mem_mb",
            "net_rx_mb",
            "net_tx_mb",
        ]

    def test_compliance_nodes_subset_of_nodes(self, real_topology: dict) -> None:
        all_node_ids = {n["id"] for n in real_topology["nodes"]}
        for cs_name, cs in real_topology["compliance_sets"].items():
            for node_id in cs["nodes"]:
                assert node_id in all_node_ids, (
                    f"{cs_name}: nodo '{node_id}' non presente in topology['nodes']"
                )

    def test_h_cache_has_no_critical_path(self, real_topology: dict) -> None:
        assert "critical_path" not in real_topology["compliance_sets"]["H_cache"]

    def test_topology_type_h_crit_linear(self, real_topology: dict) -> None:
        assert real_topology["compliance_sets"]["H_crit"]["topology_type"] == "linear"

    def test_topology_type_h_cache_parallel(self, real_topology: dict) -> None:
        assert (
            real_topology["compliance_sets"]["H_cache"]["topology_type"] == "parallel"
        )

    def test_edge_metrics_exact(self, real_topology: dict) -> None:
        """topology['edge_metrics'] contiene esattamente le 3 metriche di arco."""
        assert real_topology["edge_metrics"] == [
            "latency_ms",
            "error_rate",
            "throughput_rps",
        ]
