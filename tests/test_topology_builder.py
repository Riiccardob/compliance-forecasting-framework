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
def builder() -> TopologyBuilder:
    config = ConfigLoader(_TOPOLOGY_PATH, _PIPELINE_PATH)
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
    """build() è idempotente: chiamate successive restituiscono
    lo stesso oggetto grafo dalla cache interna."""
    g1 = builder.build()
    g2 = builder.build()
    assert g1 is g2


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
