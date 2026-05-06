"""Test per CausalAnalyzer - dati mock sintetici, nessun CSV reale."""
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.layer1.topology_builder import TopologyBuilder
from src.phase2.causal_analyzer import CausalAnalyzer
from src.utils.config_loader import ConfigLoader

warnings.filterwarnings("ignore", category=UserWarning)

_ROOT = Path(__file__).parent.parent
_TOPOLOGY_PATH = _ROOT / "config" / "topology.yaml"
_PIPELINE_PATH = _ROOT / "config" / "pipeline_params.yaml"

_STEP_US = 5_000_000  # 5 s in µs


def _make_df(values: list[float] | np.ndarray, step: int = _STEP_US) -> pd.DataFrame:
    n = len(values)
    ts = [i * step for i in range(n)]
    return pd.DataFrame(
        {"value": np.asarray(values, dtype=float)},
        index=pd.Index(ts, name="timestamp"),
    )


def _make_series(values: np.ndarray) -> pd.Series:
    return pd.Series(values.astype(float), index=range(len(values)))


#  Fixtures 

@pytest.fixture
def config() -> ConfigLoader:
    return ConfigLoader(_TOPOLOGY_PATH, _PIPELINE_PATH)


@pytest.fixture
def topology_builder(config: ConfigLoader) -> TopologyBuilder:
    return TopologyBuilder(config)


@pytest.fixture
def analyzer(
    config: ConfigLoader, topology_builder: TopologyBuilder
) -> CausalAnalyzer:
    return CausalAnalyzer(config, topology_builder)


@pytest.fixture
def mock_features_h_crit() -> dict[str, pd.DataFrame]:
    """Minimal features for H_crit: 2 node features, 1 edge feature."""
    rng = np.random.default_rng(42)
    n = 30
    return {
        "node:nginx-web-server:cpu_percent": _make_df(rng.normal(5, 0.5, n)),
        "node:nginx-thrift:cpu_percent": _make_df(rng.normal(5, 0.5, n)),
        "edge:e1:latency_ms": _make_df(rng.normal(10, 1, n)),
    }


@pytest.fixture
def mock_features_h_cache() -> dict[str, pd.DataFrame]:
    """Features for H_cache: shared node + interf edge."""
    rng = np.random.default_rng(10)
    n = 30
    return {
        "node:home-timeline-service:cpu_percent": _make_df(rng.normal(5, 0.5, n)),
        "interf:e2:throughput_rps": _make_df(rng.normal(100, 10, n)),
        "edge:e3:latency_ms": _make_df(rng.normal(5, 0.5, n)),
        "edge:e4:latency_ms": _make_df(rng.normal(5, 0.5, n)),
    }


#  Test: struttura output (4) 

def test_analyze_returns_dict(
    analyzer: CausalAnalyzer, mock_features_h_crit: dict[str, pd.DataFrame]
) -> None:
    result = analyzer.analyze("H_crit", mock_features_h_crit)
    assert isinstance(result, dict)


def test_causal_graph_has_required_keys(
    analyzer: CausalAnalyzer, mock_features_h_crit: dict[str, pd.DataFrame]
) -> None:
    result = analyzer.analyze("H_crit", mock_features_h_crit)
    assert set(result.keys()) == {"compliance_set", "edges", "cross_property_chains"}


def test_edges_have_required_fields(
    analyzer: CausalAnalyzer, mock_features_h_crit: dict[str, pd.DataFrame]
) -> None:
    """Se edges non è vuoto, ogni elemento ha le chiavi richieste."""
    result = analyzer.analyze("H_crit", mock_features_h_crit)
    for edge in result["edges"]:
        assert {"source", "target", "type", "intensity", "method", "lag"} <= set(
            edge.keys()
        )


def test_compliance_set_in_output(
    analyzer: CausalAnalyzer, mock_features_h_crit: dict[str, pd.DataFrame]
) -> None:
    result = analyzer.analyze("H_crit", mock_features_h_crit)
    assert result["compliance_set"] == "H_crit"


#  Test: candidate pairs (3) 

def test_get_causal_pairs_returns_list(
    analyzer: CausalAnalyzer, mock_features_h_crit: dict[str, pd.DataFrame]
) -> None:
    result = analyzer.get_causal_pairs("H_crit", mock_features_h_crit)
    assert isinstance(result, list)


def test_get_causal_pairs_categories(
    analyzer: CausalAnalyzer, mock_features_h_crit: dict[str, pd.DataFrame]
) -> None:
    """Ogni elemento è una tupla (src, tgt, category) con category valida."""
    pairs = analyzer.get_causal_pairs("H_crit", mock_features_h_crit)
    valid_cats = {"intra", "inter", "node_arc"}
    for p in pairs:
        assert len(p) == 3, f"Attesa tupla di 3 elementi, ottenuto {len(p)}"
        assert p[2] in valid_cats, f"Categoria non valida: {p[2]}"


def test_inter_pairs_bypass_pearson(
    analyzer: CausalAnalyzer,
) -> None:
    """Coppie inter compaiono in get_causal_pairs anche con |r| < threshold.

    node:home-timeline-service è un nodo condiviso tra H_cache e H_crit.
    interf:e2:throughput_rps è la feature di interferenza per H_cache.
    Le due serie sono indipendenti (|r| ≈ 0.0 < 0.7 = pearson_threshold),
    ma la coppia deve essere classificata come "inter".
    """
    rng = np.random.default_rng(99)
    n = 30
    features = {
        "node:home-timeline-service:cpu_percent": _make_df(rng.normal(5, 1, n)),
        "interf:e2:throughput_rps": _make_df(rng.normal(100, 20, n)),
    }
    pairs = analyzer.get_causal_pairs("H_cache", features)
    inter = [(s, t) for s, t, c in pairs if c == "inter"]
    assert len(inter) > 0, "Nessuna coppia 'inter' trovata per H_cache"
    keys_in_inter = {k for s, t, _ in pairs if _ == "inter" for k in (s, t)}
    assert "node:home-timeline-service:cpu_percent" in keys_in_inter
    assert "interf:e2:throughput_rps" in keys_in_inter


#  Test: Granger (3) 

def test_granger_detects_linear_causality(
    analyzer: CausalAnalyzer,
) -> None:
    """Granger rileva causalità lineare lag-1 con dipendenza controllata."""
    rng = np.random.default_rng(0)
    n = 50
    cause_vals = rng.normal(0, 1, n)
    # effect_t = cause_{t-1} + piccolo rumore
    effect_vals = np.concatenate([[cause_vals[0]], cause_vals[:-1]]) + rng.normal(
        0, 0.05, n
    )
    cause_s = _make_series(cause_vals)
    effect_s = _make_series(effect_vals)
    result = analyzer._granger_test(cause_s, effect_s, max_lag=5, significance=0.05)
    assert result is not None, "Granger doveva rilevare causalità"
    assert result["intensity"] >= 0.0
    assert result["lag"] >= 1


def test_granger_returns_none_on_independent_series(
    analyzer: CausalAnalyzer,
) -> None:
    """Due serie di rumore bianco indipendente: Granger restituisce None."""
    rng = np.random.default_rng(0)
    n = 50
    cause_s = _make_series(rng.normal(0, 1, n))
    effect_s = _make_series(rng.normal(0, 1, n))
    result = analyzer._granger_test(cause_s, effect_s, max_lag=5, significance=0.05)
    assert result is None, "Granger non doveva rilevare causalità su rumore indipendente"


def test_granger_handles_insufficient_data(
    analyzer: CausalAnalyzer,
) -> None:
    """Con 3 campioni (< max_lag+2=7) _granger_test ritorna None senza eccezioni."""
    rng = np.random.default_rng(1)
    s = _make_series(rng.normal(0, 1, 3))
    result = analyzer._granger_test(s, s.copy(), max_lag=5, significance=0.05)
    assert result is None


#  Test: Pearson screening (2) 

def test_pearson_screen_passes_correlated(
    analyzer: CausalAnalyzer,
) -> None:
    """_pearson_screen passa serie con r ≈ 0.99 > threshold=0.7."""
    rng = np.random.default_rng(5)
    n = 50
    base = rng.normal(0, 1, n)
    s1 = _make_series(base)
    s2 = _make_series(base + rng.normal(0, 0.05, n))  # r ≈ 0.99
    assert analyzer._pearson_screen(s1, s2, threshold=0.7) is True


def test_pearson_screen_blocks_uncorrelated(
    analyzer: CausalAnalyzer,
) -> None:
    """_pearson_screen blocca serie indipendenti con r ≈ 0 < threshold=0.7."""
    rng = np.random.default_rng(7)
    n = 50
    s1 = _make_series(rng.normal(0, 1, n))
    s2 = _make_series(rng.normal(0, 1, n))
    assert analyzer._pearson_screen(s1, s2, threshold=0.7) is False


#  Test: Transfer Entropy (2) 

def test_transfer_entropy_positive_on_dependent(
    analyzer: CausalAnalyzer,
) -> None:
    """TE > transfer_entropy_threshold su serie con dipendenza forte."""
    rng = np.random.default_rng(123)
    n = 200
    cause_vals = rng.normal(0, 1, n)
    # dipendenza nonlineare forte: effect_t = tanh(cause_{t-1}) + piccolo rumore
    effect_vals = np.concatenate(
        [[np.tanh(cause_vals[0])], np.tanh(cause_vals[:-1])]
    ) + rng.normal(0, 0.1, n)
    cause_s = _make_series(cause_vals)
    effect_s = _make_series(effect_vals)
    te = analyzer._transfer_entropy(cause_s, effect_s, n_bins=10)
    assert te > 0.1, f"TE atteso > 0.1, ottenuto {te:.4f}"


def test_transfer_entropy_near_zero_on_independent(
    analyzer: CausalAnalyzer,
) -> None:
    """TE < 0.3 su due serie di rumore bianco indipendente (seed fisso).

    Con n=1000 e n_bins=5 il bias di campionamento finito è <0.02 bit,
    molto al di sotto della soglia 0.3.
    """
    rng = np.random.default_rng(0)
    n = 1000
    cause_s = _make_series(rng.normal(0, 1, n))
    effect_s = _make_series(rng.normal(0, 1, n))
    te = analyzer._transfer_entropy(cause_s, effect_s, n_bins=5)
    assert te < 0.3, f"TE atteso < 0.3 su serie indipendenti, ottenuto {te:.4f}"


#  Test: robustezza (3) 

def test_analyze_unknown_compliance_set_raises(
    analyzer: CausalAnalyzer, mock_features_h_crit: dict[str, pd.DataFrame]
) -> None:
    """analyze() con compliance set inesistente solleva KeyError."""
    with pytest.raises(KeyError):
        analyzer.analyze("H_nonexistent", mock_features_h_crit)


def test_analyze_empty_features_returns_empty_graph(
    analyzer: CausalAnalyzer,
) -> None:
    """analyze() con features={} restituisce edges=[] e cross_property_chains=[]."""
    result = analyzer.analyze("H_crit", {})
    assert result["edges"] == []
    assert result["cross_property_chains"] == []


def test_analyze_all_nan_series_skips_gracefully(
    analyzer: CausalAnalyzer,
) -> None:
    """Feature con tutti NaN: analyze() completa senza eccezioni."""
    n = 30
    nan_df = _make_df([float("nan")] * n)
    normal_df = _make_df(np.ones(n) * 5.0)
    features = {
        "node:nginx-web-server:cpu_percent": nan_df,
        "node:nginx-thrift:cpu_percent": normal_df,
    }
    result = analyzer.analyze("H_crit", features)
    assert isinstance(result, dict)
    # La coppia con NaN non deve comparire negli edges
    nan_in_edges = any(
        "nginx-web-server:cpu_percent" in e["source"]
        or "nginx-web-server:cpu_percent" in e["target"]
        for e in result["edges"]
    )
    assert not nan_in_edges


#  Test: error handling (1) 

def test_missing_causal_analysis_key_raises(
    config: ConfigLoader, topology_builder: TopologyBuilder
) -> None:
    """Costruttore solleva ValueError se manca pearson_threshold."""
    import copy
    from unittest.mock import patch

    pipeline = config.load_pipeline_params()
    bad_pipeline = copy.deepcopy(pipeline)
    del bad_pipeline["causal_analysis"]["pearson_threshold"]
    with patch.object(
        type(config), "load_pipeline_params", return_value=bad_pipeline
    ):
        with pytest.raises(ValueError, match="pearson_threshold"):
            CausalAnalyzer(config, topology_builder)
