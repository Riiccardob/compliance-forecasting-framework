"""Test per TopologyBuilder — ipergrafo di certificazione H_cert."""
from pathlib import Path

import networkx as nx
import pytest

from src.utils.config_loader import ConfigLoader
from src.layer1.topology_builder import TopologyBuilder

_ROOT = Path(__file__).parent.parent
_TOPOLOGY_PATH = _ROOT / "config" / "topology.yaml"
_PIPELINE_PATH = _ROOT / "config" / "pipeline_params.yaml"


@pytest.fixture
def config() -> ConfigLoader:
    return ConfigLoader(_TOPOLOGY_PATH, _PIPELINE_PATH)


@pytest.fixture
def builder(config: ConfigLoader) -> TopologyBuilder:
    return TopologyBuilder(config)


@pytest.fixture
def graph(builder: TopologyBuilder) -> nx.DiGraph:
    return builder.build()


# ── Struttura del grafo ───────────────────────────────────────────────────────

def test_graph_node_count(graph: nx.DiGraph) -> None:
    assert graph.number_of_nodes() == 7


def test_graph_edge_count(graph: nx.DiGraph) -> None:
    assert graph.number_of_edges() == 6


def test_is_directed(graph: nx.DiGraph) -> None:
    assert isinstance(graph, nx.DiGraph)


# ── Annotazione semantica degli archi ─────────────────────────────────────────

def test_semantic_annotation_e4(graph: nx.DiGraph) -> None:
    """e4 (home-timeline-service → post-storage-service): in H_crit E H_cache."""
    edge_data = graph["home-timeline-service"]["post-storage-service"]
    assert "H_crit" in edge_data["hyperedges"]
    assert "H_cache" in edge_data["hyperedges"]


def test_semantic_annotation_e3(graph: nx.DiGraph) -> None:
    """e3 (home-timeline-service → home-timeline-redis): solo H_cache."""
    edge_data = graph["home-timeline-service"]["home-timeline-redis"]
    assert edge_data["hyperedges"] == ["H_cache"]


def test_semantic_annotation_e1(graph: nx.DiGraph) -> None:
    """e1 (nginx-web-server → nginx-thrift): solo H_crit."""
    edge_data = graph["nginx-web-server"]["nginx-thrift"]
    assert edge_data["hyperedges"] == ["H_crit"]


# ── Nodi condivisi ────────────────────────────────────────────────────────────

def test_shared_nodes_correct(builder: TopologyBuilder) -> None:
    """Shared(H_crit, H_cache) = {home-timeline-service, post-storage-service}."""
    shared = builder.get_shared_nodes("H_crit", "H_cache")
    assert shared == {"home-timeline-service", "post-storage-service"}


def test_shared_nodes_symmetric(builder: TopologyBuilder) -> None:
    """Shared è simmetrica: H_crit∩H_cache == H_cache∩H_crit."""
    assert (
        builder.get_shared_nodes("H_crit", "H_cache")
        == builder.get_shared_nodes("H_cache", "H_crit")
    )


# ── A(H_Φi) — archi interni ───────────────────────────────────────────────────

def test_edges_h_crit_count(builder: TopologyBuilder) -> None:
    """A(H_crit) ha esattamente 4 archi: e1, e2, e4, e6."""
    edges = builder.get_edges_for_compliance_set("H_crit")
    assert len(edges) == 4


def test_edges_h_cache_count(builder: TopologyBuilder) -> None:
    """A(H_cache) ha esattamente 3 archi: e3, e4, e5."""
    edges = builder.get_edges_for_compliance_set("H_cache")
    assert len(edges) == 3


# ── Critical path ─────────────────────────────────────────────────────────────

def test_critical_path_h_crit(builder: TopologyBuilder) -> None:
    """H_crit ha critical_path con 5 nodi (topologia lineare)."""
    path = builder.get_critical_path("H_crit")
    assert len(path) == 5


def test_critical_path_h_cache_empty(builder: TopologyBuilder) -> None:
    """H_cache non ha critical_path (topologia parallela): restituisce []."""
    path = builder.get_critical_path("H_cache")
    assert path == []


# ── M_interf — archi di interferenza ─────────────────────────────────────────

def test_interference_h_crit_empty(builder: TopologyBuilder) -> None:
    """M_interf(H_crit, H_cache) = ∅: nessun arco esterno a H_crit punta ai nodi condivisi."""
    edges = builder.get_interference_edges("H_crit", "H_cache")
    assert edges == []


def test_interference_h_cache_has_e2(builder: TopologyBuilder) -> None:
    """M_interf(H_cache, H_crit): 1 arco, target = home-timeline-service (e2)."""
    edges = builder.get_interference_edges("H_cache", "H_crit")
    assert len(edges) == 1
    _, target = edges[0]
    assert target == "home-timeline-service"


# ── get_compliance_set_nodes ──────────────────────────────────────────────────

def test_compliance_set_nodes_h_crit(builder: TopologyBuilder) -> None:
    nodes = builder.get_compliance_set_nodes("H_crit")
    assert len(nodes) == 5


def test_compliance_set_nodes_h_cache(builder: TopologyBuilder) -> None:
    nodes = builder.get_compliance_set_nodes("H_cache")
    assert len(nodes) == 4


def test_unknown_compliance_set_raises(builder: TopologyBuilder) -> None:
    with pytest.raises(KeyError):
        builder.get_compliance_set_nodes("H_invalid")


def test_build_idempotent(builder: TopologyBuilder) -> None:
    """Due chiamate a build() restituiscono grafi strutturalmente
    identici. Ogni chiamata produce una copia indipendente."""
    g1 = builder.build()
    g2 = builder.build()
    assert set(g1.nodes()) == set(g2.nodes())
    assert set(g1.edges()) == set(g2.edges())


def test_interference_h_cache_source_and_target(
    builder: TopologyBuilder,
) -> None:
    """M_interf(H_cache, H_crit): l'arco ha source=nginx-thrift
    e target=home-timeline-service."""
    edges = builder.get_interference_edges("H_cache", "H_crit")
    assert len(edges) == 1
    source, target = edges[0]
    assert source == "nginx-thrift"
    assert target == "home-timeline-service"


def test_critical_path_invalid_raises(builder: TopologyBuilder) -> None:
    """get_critical_path su nome inesistente solleva KeyError."""
    with pytest.raises(KeyError):
        builder.get_critical_path("H_invalid")

def test_edges_h_crit_content(builder: TopologyBuilder) -> None:
    """A(H_crit) contiene esattamente le coppie (e1,e2,e4,e6)."""
    edges = set(builder.get_edges_for_compliance_set("H_crit"))
    assert ("nginx-web-server", "nginx-thrift") in edges
    assert ("nginx-thrift", "home-timeline-service") in edges
    assert ("home-timeline-service", "post-storage-service") in edges
    assert ("post-storage-service", "post-storage-mongodb") in edges


def test_edges_h_cache_content(builder: TopologyBuilder) -> None:
    """A(H_cache) contiene esattamente le coppie (e3,e4,e5)."""
    edges = set(builder.get_edges_for_compliance_set("H_cache"))
    assert ("home-timeline-service", "home-timeline-redis") in edges
    assert ("home-timeline-service", "post-storage-service") in edges
    assert ("post-storage-service", "post-storage-memcached") in edges


def test_critical_path_h_crit_sequence(builder: TopologyBuilder) -> None:
    """Il critical path di H_crit è esattamente la sequenza attesa."""
    path = builder.get_critical_path("H_crit")
    assert path == [
        "nginx-web-server",
        "nginx-thrift",
        "home-timeline-service",
        "post-storage-service",
        "post-storage-mongodb",
    ]


def test_get_shared_nodes_invalid_raises(builder: TopologyBuilder) -> None:
    """get_shared_nodes con nome invalido solleva KeyError descrittivo."""
    with pytest.raises(KeyError, match="Compliance set non trovato"):
        builder.get_shared_nodes("H_invalid", "H_crit")


def test_get_edges_invalid_raises(builder: TopologyBuilder) -> None:
    """get_edges_for_compliance_set con nome invalido solleva KeyError."""
    with pytest.raises(KeyError, match="Compliance set non trovato"):
        builder.get_edges_for_compliance_set("H_invalid")


def test_get_interference_edges_invalid_raises(
    builder: TopologyBuilder,
) -> None:
    """get_interference_edges con nome invalido solleva KeyError."""
    with pytest.raises(KeyError, match="Compliance set non trovato"):
        builder.get_interference_edges("H_invalid", "H_crit")


def test_edge_id_attribute_in_graph(builder: TopologyBuilder) -> None:
    """Ogni arco nel DiGraph ha attributo 'id' corrispondente
    all'edge_id in topology.yaml."""
    g = builder.build()
    attr = g.edges["nginx-web-server", "nginx-thrift"]
    assert attr.get("id") == "e1"


def test_compliance_set_node_not_in_v_raises(
    config: ConfigLoader,
) -> None:
    """__init__ solleva ValueError se un nodo del compliance set
    non esiste in topology['nodes']."""
    import copy
    from unittest.mock import patch
    topo = config.load_topology()
    bad_topo = copy.deepcopy(topo)
    bad_topo["compliance_sets"]["H_crit"]["nodes"].append(
        "nonexistent-service"
    )
    with patch.object(
        type(config), "load_topology", return_value=bad_topo
    ):
        with pytest.raises(ValueError, match="non presente in topology"):
            TopologyBuilder(config)


def test_critical_path_invalid_arc_raises(
    config: ConfigLoader,
) -> None:
    """get_critical_path solleva ValueError se il path contiene
    una coppia consecutiva senza arco reale."""
    import copy
    from unittest.mock import patch
    topo = config.load_topology()
    bad_topo = copy.deepcopy(topo)
    bad_topo["compliance_sets"]["H_crit"]["critical_path"][
        "sequence"
    ] = ["nginx-web-server", "post-storage-mongodb"]
    with patch.object(
        type(config), "load_topology", return_value=bad_topo
    ):
        bad_builder = TopologyBuilder(config)
    with pytest.raises(ValueError, match="non esiste in topology"):
        bad_builder.get_critical_path("H_crit")


def test_critical_path_node_outside_cs_raises(config: ConfigLoader) -> None:
    """get_critical_path solleva ValueError se il path contiene un nodo
    non appartenente al compliance set."""
    import copy
    from unittest.mock import patch

    topo = config.load_topology()
    bad_topo = copy.deepcopy(topo)
    bad_topo["compliance_sets"]["H_crit"]["critical_path"]["sequence"] = [
        "nginx-web-server",
        "home-timeline-redis",  # non in H_crit
        "post-storage-mongodb",
    ]
    with patch.object(type(config), "load_topology", return_value=bad_topo):
        bad_builder = TopologyBuilder(config)
    with pytest.raises(ValueError, match="non appartiene al compliance set"):
        bad_builder.get_critical_path("H_crit")


def test_build_invalid_endpoint_raises(config: ConfigLoader) -> None:
    """build() solleva ValueError se un arco punta a un nodo non dichiarato."""
    import copy
    from unittest.mock import patch

    topo = config.load_topology()
    bad_topo = copy.deepcopy(topo)
    bad_topo["edges"][0]["target"] = "nonexistent-node"
    with patch.object(type(config), "load_topology", return_value=bad_topo):
        bad_builder = TopologyBuilder(config)
    with pytest.raises(ValueError, match="non presente in topology"):
        bad_builder.build()


def test_build_returns_independent_copy(
    builder: TopologyBuilder,
) -> None:
    """Modificare il grafo restituito da build() non corrompe
    la cache interna di TopologyBuilder."""
    g1 = builder.build()
    g1.add_node("injected-sentinel")
    g2 = builder.build()
    assert "injected-sentinel" not in g2.nodes()


def test_build_warns_on_isolated_node(
    config: ConfigLoader,
) -> None:
    """build() non solleva eccezioni e include il nodo nel grafo
    anche se non appartiene ad alcun compliance set."""
    import copy
    from unittest.mock import patch

    topo = config.load_topology()
    bad_topo = copy.deepcopy(topo)
    bad_topo["nodes"].append({"id": "orphan-service"})
    with patch.object(type(config), "load_topology", return_value=bad_topo):
        orphan_builder = TopologyBuilder(config)
    g = orphan_builder.build()
    assert "orphan-service" in g.nodes()


def test_get_interference_edges_same_cs_raises(
    builder: TopologyBuilder,
) -> None:
    """get_interference_edges con target_cs == other_cs solleva
    ValueError (auto-interferenza non definita)."""
    with pytest.raises(ValueError, match="identici"):
        builder.get_interference_edges("H_crit", "H_crit")


def test_critical_path_linear_without_path_warns(
    config: ConfigLoader,
) -> None:
    """get_critical_path su topology_type=linear senza critical_path
    restituisce [] ed emette logger.warning."""
    import copy
    import src.layer1.topology_builder as tb_module
    from unittest.mock import patch

    topo = config.load_topology()
    bad_topo = copy.deepcopy(topo)
    bad_topo["compliance_sets"]["H_crit"].pop("critical_path", None)
    with patch.object(type(config), "load_topology", return_value=bad_topo):
        bad_builder = TopologyBuilder(config)
    with patch.object(tb_module, "logger") as mock_logger:
        result = bad_builder.get_critical_path("H_crit")
    assert result == []
    mock_logger.warning.assert_called()
    warning_msg = str(mock_logger.warning.call_args_list)
    assert "linear" in warning_msg or "critical_path" in warning_msg


def test_critical_path_unknown_topology_type_warns(
    config: ConfigLoader,
) -> None:
    """get_critical_path con topology_type non riconosciuto
    restituisce [] ed emette logger.warning."""
    import copy
    import src.layer1.topology_builder as tb_module
    from unittest.mock import patch

    topo = config.load_topology()
    bad_topo = copy.deepcopy(topo)
    bad_topo["compliance_sets"]["H_crit"]["topology_type"] = "hierarchical"
    with patch.object(type(config), "load_topology", return_value=bad_topo):
        bad_builder = TopologyBuilder(config)
    with patch.object(tb_module, "logger") as mock_logger:
        result = bad_builder.get_critical_path("H_crit")
    assert result == []
    mock_logger.warning.assert_called()
    warning_msg = str(mock_logger.warning.call_args_list)
    assert "hierarchical" in warning_msg or "non riconosciuto" in warning_msg