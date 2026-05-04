"""Test per ConfigLoader: caricamento e validazione dei file di configurazione."""
import logging
from pathlib import Path

import pytest

from src.utils.config_loader import ConfigLoader
from src.utils.logging_setup import LoggingSetup

_ROOT = Path(__file__).parent.parent
_TOPOLOGY_PATH = _ROOT / "config" / "topology.yaml"
_PIPELINE_PATH = _ROOT / "config" / "pipeline_params.yaml"


@pytest.fixture
def loader() -> ConfigLoader:
    return ConfigLoader(_TOPOLOGY_PATH, _PIPELINE_PATH)


@pytest.fixture
def topology(loader: ConfigLoader) -> dict:
    return loader.load_topology()


@pytest.fixture
def pipeline(loader: ConfigLoader) -> dict:
    return loader.load_pipeline_params()


# ── Topology ──────────────────────────────────────────────────────────────────

def test_load_topology_returns_dict(topology: dict) -> None:
    assert isinstance(topology, dict)


def test_nodes_count(topology: dict) -> None:
    assert len(topology["nodes"]) == 7


def test_edges_count(topology: dict) -> None:
    assert len(topology["edges"]) == 6


def test_compliance_sets_present(topology: dict) -> None:
    cs = topology["compliance_sets"]
    assert "H_crit" in cs
    assert "H_cache" in cs


def test_h_crit_node_count(topology: dict) -> None:
    assert len(topology["compliance_sets"]["H_crit"]["nodes"]) == 5


def test_h_cache_node_count(topology: dict) -> None:
    assert len(topology["compliance_sets"]["H_cache"]["nodes"]) == 4


def test_critical_path_length(topology: dict) -> None:
    seq = topology["compliance_sets"]["H_crit"]["critical_path"]["sequence"]
    assert len(seq) == 5


def test_edge_naming_starts_at_e1(topology: dict) -> None:
    assert topology["edges"][0]["id"] == "e1"


def test_node_metrics_exact(topology: dict) -> None:
    assert topology["node_metrics"] == [
        "cpu_percent",
        "mem_mb",
        "net_rx_mb",
        "net_tx_mb",
    ]


def test_compliance_nodes_subset_of_nodes(topology: dict) -> None:
    all_node_ids = {n["id"] for n in topology["nodes"]}
    for cs_name, cs in topology["compliance_sets"].items():
        for node_id in cs["nodes"]:
            assert node_id in all_node_ids, (
                f"{cs_name}: nodo '{node_id}' non presente in topology['nodes']"
            )


def test_h_cache_has_no_critical_path(topology: dict) -> None:
    assert "critical_path" not in topology["compliance_sets"]["H_cache"]


def test_topology_type_h_crit_linear(topology: dict) -> None:
    assert topology["compliance_sets"]["H_crit"]["topology_type"] == "linear"


def test_topology_type_h_cache_parallel(topology: dict) -> None:
    assert topology["compliance_sets"]["H_cache"]["topology_type"] == "parallel"


# ── Pipeline params ───────────────────────────────────────────────────────────

def test_pipeline_params_loads(pipeline: dict) -> None:
    assert isinstance(pipeline, dict)


def test_lstm_config_present(pipeline: dict) -> None:
    assert "lstm" in pipeline["forecasting"]


def test_arima_config_present(pipeline: dict) -> None:
    assert "arima" in pipeline["forecasting"]


# ── Error handling ────────────────────────────────────────────────────────────

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


def test_load_topology_cache_is_isolated(loader: ConfigLoader) -> None:
    """Mutare il dict restituito non corrompe la cache interna."""
    t1 = loader.load_topology()
    original_count = len(t1["nodes"])
    t1["nodes"].append({"id": "injected-sentinel"})
    t2 = loader.load_topology()
    assert len(t2["nodes"]) == original_count


def test_load_pipeline_cache_is_isolated(loader: ConfigLoader) -> None:
    """Mutare il dict di pipeline restituito non corrompe la cache."""
    p1 = loader.load_pipeline_params()
    p1["forecasting"]["injected_key"] = "sentinel"
    p2 = loader.load_pipeline_params()
    assert "injected_key" not in p2["forecasting"]


def test_load_topology_cache_deep_isolation(
    loader: ConfigLoader,
) -> None:
    """Mutare una struttura annidata nel dict restituito non corrompe
    la cache interna (deepcopy protegge anche i livelli annidati)."""
    t1 = loader.load_topology()
    original_len = len(t1["compliance_sets"]["H_crit"]["nodes"])
    t1["compliance_sets"]["H_crit"]["nodes"].append("injected-sentinel")
    t2 = loader.load_topology()
    assert len(t2["compliance_sets"]["H_crit"]["nodes"]) == original_len


def test_load_pipeline_cache_deep_isolation(
    loader: ConfigLoader,
) -> None:
    """Mutare una struttura annidata nel dict pipeline restituito
    non corrompe la cache interna."""
    p1 = loader.load_pipeline_params()
    p1["anomaly_detection"]["cusum"]["ewma_alpha"] = 999.0
    p2 = loader.load_pipeline_params()
    assert p2["anomaly_detection"]["cusum"]["ewma_alpha"] != 999.0


def test_edge_metrics_exact(topology: dict) -> None:
    """topology['edge_metrics'] contiene esattamente le 3 metriche di arco."""
    assert topology["edge_metrics"] == [
        "latency_ms",
        "error_rate",
        "throughput_rps",
    ]


def test_malformed_yaml_raises(tmp_path: Path) -> None:
    """YAML sintaticamente invalido solleva ValueError con messaggio
    esplicito — non propaga yaml.YAMLError raw."""
    malformed = tmp_path / "malformed.yaml"
    malformed.write_text(
        "metadata:\n  key: valid\nnodes: [\n  - broken",
        encoding="utf-8",
    )
    loader = ConfigLoader(malformed, _PIPELINE_PATH)
    with pytest.raises(ValueError, match="sintaticamente non valido"):
        loader.load_topology()
