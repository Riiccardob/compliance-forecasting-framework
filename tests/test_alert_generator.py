"""Test per AlertGenerator - mock sintetici, nessun CSV reale."""
import copy
from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from src.layer1.topology_builder import TopologyBuilder
from src.phase4.alert_generator import AlertGenerator
from src.utils.config_loader import ConfigLoader

_ROOT = Path(__file__).parent.parent
_TOPOLOGY_PATH = _ROOT / "config" / "topology.yaml"
_PIPELINE_PATH = _ROOT / "config" / "pipeline_params.yaml"

_T0 = 1_000_000_000
_N_STEPS = 6

# H_crit: A(H_crit) = {e1, e2, e4, e6}
_H_CRIT_LATENCY_KEYS = [
    "edge:e1:latency_ms",
    "edge:e2:latency_ms",
    "edge:e4:latency_ms",
    "edge:e6:latency_ms",
]

# SLA H_crit: latency_ms upper 100.0
_SLA_LATENCY_THRESHOLD = 100.0
# step_duration_hours=24.0 → lead_time_days = lead_time_steps


#  Helpers 

def _make_forecast_df(yhats: list[float]) -> pd.DataFrame:
    """DataFrame forecast con colonne yhat/yhat_lower/yhat_upper."""
    n = len(yhats)
    ts = [i * 5_000_000 for i in range(1, n + 1)]
    return pd.DataFrame(
        {
            "yhat": yhats,
            "yhat_lower": [y * 0.9 for y in yhats],
            "yhat_upper": [y * 1.1 for y in yhats],
        },
        index=pd.Index(ts, name="timestamp"),
    )


def _make_forecasts_h_crit(
    yhat_per_arc: float = 10.0, n_steps: int = _N_STEPS
) -> dict[str, pd.DataFrame]:
    """Forecasts per H_crit con yhat costante per tutti gli archi e step."""
    return {k: _make_forecast_df([yhat_per_arc] * n_steps) for k in _H_CRIT_LATENCY_KEYS}


def _make_forecasts_violation_at_step(
    step: int, n_steps: int = _N_STEPS
) -> dict[str, pd.DataFrame]:
    """Forecasts H_crit con violazione sum>100 a partire da step (1-based)."""
    # 20.0 → sum=80 < 100; 30.0 → sum=120 > 100
    yhats = [20.0 if i + 1 < step else 30.0 for i in range(n_steps)]
    return {k: _make_forecast_df(yhats) for k in _H_CRIT_LATENCY_KEYS}


def _make_causal_graph_empty(cs: str = "H_crit") -> dict[str, Any]:
    return {"compliance_set": cs, "edges": [], "cross_property_chains": []}


def _make_monitor_nominal() -> dict[str, Any]:
    return {
        "timestamp": _T0, "compliance_set": "H_crit",
        "base_signal": False, "if_signal": False,
        "cusum_signal": False, "structural_confirmed": False,
        "zscore_violations": [], "threshold_violations": [],
        "frobenius_distance": 0.0, "pas_value": 0.25,
        "cusum_stat": 0.0, "ewma_value": 0.25,
    }


def _make_monitor_red() -> dict[str, Any]:
    m = _make_monitor_nominal()
    m.update({"base_signal": True, "if_signal": True,
               "cusum_signal": True, "structural_confirmed": True})
    return m


def _make_monitor_orange() -> dict[str, Any]:
    m = _make_monitor_nominal()
    m.update({"cusum_signal": True, "structural_confirmed": False})
    return m


#  Fixtures 

@pytest.fixture
def config() -> ConfigLoader:
    return ConfigLoader(_TOPOLOGY_PATH, _PIPELINE_PATH)


@pytest.fixture
def topology_builder(config: ConfigLoader) -> TopologyBuilder:
    return TopologyBuilder(config)


@pytest.fixture
def alert_generator(
    config: ConfigLoader, topology_builder: TopologyBuilder
) -> AlertGenerator:
    return AlertGenerator(config, topology_builder)


@pytest.fixture
def mock_forecasts_h_crit() -> dict[str, pd.DataFrame]:
    return _make_forecasts_h_crit(yhat_per_arc=10.0)  # sum=40 < 100 → no violation


@pytest.fixture
def mock_forecasts_h_crit_violation() -> dict[str, pd.DataFrame]:
    return _make_forecasts_h_crit(yhat_per_arc=30.0)  # sum=120 > 100 → violation step 1


@pytest.fixture
def mock_causal_graph_empty() -> dict[str, Any]:
    return _make_causal_graph_empty()


@pytest.fixture
def mock_causal_graph_with_cause() -> dict[str, Any]:
    return {
        "compliance_set": "H_crit",
        "edges": [
            {
                "source": "node:post-storage-service:cpu_percent",
                "target": "edge:e4:latency_ms",
                "type": "linear",
                "intensity": 0.7,
                "method": "granger",
                "lag": 1,
            }
        ],
        "cross_property_chains": [],
    }


@pytest.fixture
def mock_monitor_nominal() -> dict[str, Any]:
    return _make_monitor_nominal()


@pytest.fixture
def mock_monitor_red() -> dict[str, Any]:
    return _make_monitor_red()


@pytest.fixture
def mock_monitor_orange() -> dict[str, Any]:
    return _make_monitor_orange()


#  Struttura output (4) 

def test_generate_returns_none_when_no_violation(
    alert_generator: AlertGenerator,
    mock_forecasts_h_crit: dict[str, pd.DataFrame],
    mock_causal_graph_empty: dict[str, Any],
    mock_monitor_nominal: dict[str, Any],
) -> None:
    """Forecasts nominali (sum=40 < SLA 100) → generate() restituisce None."""
    result = alert_generator.generate(
        "H_crit", mock_forecasts_h_crit,
        mock_causal_graph_empty, mock_monitor_nominal, _T0,
    )
    assert result is None


def test_generate_returns_dict_on_violation(
    alert_generator: AlertGenerator,
    mock_forecasts_h_crit_violation: dict[str, pd.DataFrame],
    mock_causal_graph_empty: dict[str, Any],
    mock_monitor_nominal: dict[str, Any],
) -> None:
    """Forecasts con sum=120 > SLA 100 → generate() restituisce dict."""
    result = alert_generator.generate(
        "H_crit", mock_forecasts_h_crit_violation,
        mock_causal_graph_empty, mock_monitor_nominal, _T0,
    )
    assert isinstance(result, dict)


def test_alert_has_required_keys(
    alert_generator: AlertGenerator,
    mock_forecasts_h_crit_violation: dict[str, pd.DataFrame],
    mock_causal_graph_empty: dict[str, Any],
    mock_monitor_nominal: dict[str, Any],
) -> None:
    """L'alert contiene esattamente le chiavi richieste dalla struttura Alert."""
    alert = alert_generator.generate(
        "H_crit", mock_forecasts_h_crit_violation,
        mock_causal_graph_empty, mock_monitor_nominal, _T0,
    )
    assert alert is not None
    expected_keys = {
        "timestamp", "compliance_set", "property_at_risk", "criticality",
        "lead_time_steps", "lead_time_hours", "aggregated_forecast",
        "sla_threshold", "sla_bound", "critical_arc", "root_cause",
        "cross_property_interference", "causal_chain", "structural_signals",
        "model_uncertainty_flag",
    }
    assert set(alert.keys()) == expected_keys


def test_compliance_set_in_alert(
    alert_generator: AlertGenerator,
    mock_forecasts_h_crit_violation: dict[str, pd.DataFrame],
    mock_causal_graph_empty: dict[str, Any],
    mock_monitor_nominal: dict[str, Any],
) -> None:
    """alert['compliance_set'] corrisponde al nome passato."""
    alert = alert_generator.generate(
        "H_crit", mock_forecasts_h_crit_violation,
        mock_causal_graph_empty, mock_monitor_nominal, _T0,
    )
    assert alert is not None
    assert alert["compliance_set"] == "H_crit"


#  Lead time (3) 

def test_lead_time_steps_is_first_violation(
    alert_generator: AlertGenerator,
    mock_causal_graph_empty: dict[str, Any],
    mock_monitor_nominal: dict[str, Any],
) -> None:
    """Violazione al step 3 (sum=120>100 da step 3): lead_time_steps==3."""
    forecasts = _make_forecasts_violation_at_step(step=3, n_steps=6)
    alert = alert_generator.generate(
        "H_crit", forecasts, mock_causal_graph_empty, mock_monitor_nominal, _T0,
    )
    assert alert is not None
    assert alert["lead_time_steps"] == 3, (
        f"Atteso lead_time_steps=3, ottenuto {alert['lead_time_steps']}"
    )


def test_lead_time_none_means_no_alert(
    alert_generator: AlertGenerator,
    mock_forecasts_h_crit: dict[str, pd.DataFrame],
    mock_causal_graph_empty: dict[str, Any],
    mock_monitor_nominal: dict[str, Any],
) -> None:
    """Nessuna violazione nell'orizzonte → generate() restituisce None."""
    result = alert_generator.generate(
        "H_crit", mock_forecasts_h_crit,
        mock_causal_graph_empty, mock_monitor_nominal, _T0,
    )
    assert result is None


def test_lead_time_step_1_possible(
    alert_generator: AlertGenerator,
    mock_causal_graph_empty: dict[str, Any],
    mock_monitor_nominal: dict[str, Any],
) -> None:
    """Violazione già al primo step → lead_time_steps==1."""
    forecasts = _make_forecasts_h_crit(yhat_per_arc=30.0)
    alert = alert_generator.generate(
        "H_crit", forecasts, mock_causal_graph_empty, mock_monitor_nominal, _T0,
    )
    assert alert is not None
    assert alert["lead_time_steps"] == 1


#  Classificazione criticità (4) 

def test_criticality_yellow_on_long_lead_time(
    alert_generator: AlertGenerator,
    mock_causal_graph_empty: dict[str, Any],
    mock_monitor_nominal: dict[str, Any],
) -> None:
    """lead_time_steps=10 (10 giorni > 7) + tutti segnali False → 'yellow'."""
    # Violation solo allo step 10 (steps 1-9 sum=80<100, step 10 sum=120>100)
    yhats_9_ok_1_violation = [20.0] * 9 + [30.0]
    forecasts = {k: _make_forecast_df(yhats_9_ok_1_violation) for k in _H_CRIT_LATENCY_KEYS}
    alert = alert_generator.generate(
        "H_crit", forecasts, mock_causal_graph_empty, mock_monitor_nominal, _T0,
    )
    assert alert is not None
    assert alert["criticality"] == "yellow", (
        f"Atteso 'yellow' con lead_time=10 giorni e segnali nominali, "
        f"ottenuto '{alert['criticality']}'"
    )


def test_criticality_orange_on_cusum_signal(
    alert_generator: AlertGenerator,
    mock_causal_graph_empty: dict[str, Any],
    mock_monitor_orange: dict[str, Any],
) -> None:
    """cusum_signal=True, structural_confirmed=False → almeno 'orange'."""
    forecasts = _make_forecasts_h_crit(yhat_per_arc=30.0)
    alert = alert_generator.generate(
        "H_crit", forecasts, mock_causal_graph_empty, mock_monitor_orange, _T0,
    )
    assert alert is not None
    assert alert["criticality"] in ("orange", "red"), (
        f"Atteso almeno 'orange' con cusum_signal=True, "
        f"ottenuto '{alert['criticality']}'"
    )


def test_criticality_red_on_structural_confirmed(
    alert_generator: AlertGenerator,
    mock_causal_graph_empty: dict[str, Any],
    mock_monitor_red: dict[str, Any],
) -> None:
    """cusum_signal=True AND structural_confirmed=True → 'red'."""
    forecasts = _make_forecasts_h_crit(yhat_per_arc=30.0)
    alert = alert_generator.generate(
        "H_crit", forecasts, mock_causal_graph_empty, mock_monitor_red, _T0,
    )
    assert alert is not None
    assert alert["criticality"] == "red", (
        f"Atteso 'red' con structural_confirmed=True, "
        f"ottenuto '{alert['criticality']}'"
    )


def test_criticality_red_on_short_lead_time(
    alert_generator: AlertGenerator,
    mock_causal_graph_empty: dict[str, Any],
    mock_monitor_nominal: dict[str, Any],
) -> None:
    """lead_time_steps=1 (1 giorno < orange_min_days=2) → 'red'."""
    forecasts = _make_forecasts_h_crit(yhat_per_arc=30.0)
    alert = alert_generator.generate(
        "H_crit", forecasts, mock_causal_graph_empty, mock_monitor_nominal, _T0,
    )
    assert alert is not None
    assert alert["criticality"] == "red", (
        f"Atteso 'red' per lead_time=1 giorno < orange_min_days=2, "
        f"ottenuto '{alert['criticality']}'"
    )


#  Aggregazione (3) 

def test_aggregation_latency_is_sum_for_linear(
    alert_generator: AlertGenerator,
    mock_causal_graph_empty: dict[str, Any],
    mock_monitor_nominal: dict[str, Any],
) -> None:
    """H_crit (linear): aggregated_forecast[0] = Σ yhat dei 4 archi al step 1."""
    yhat_per_arc = 30.0  # 4 archi × 30 = 120 > 100 → violation
    forecasts = _make_forecasts_h_crit(yhat_per_arc=yhat_per_arc)
    alert = alert_generator.generate(
        "H_crit", forecasts, mock_causal_graph_empty, mock_monitor_nominal, _T0,
    )
    assert alert is not None
    expected_sum = 4 * yhat_per_arc
    assert abs(alert["aggregated_forecast"][0] - expected_sum) < 1e-9, (
        f"Atteso aggregated_forecast[0]={expected_sum:.1f} (sum di 4 archi), "
        f"ottenuto {alert['aggregated_forecast'][0]:.6f}"
    )


def test_aggregation_no_relevant_features_returns_none(
    alert_generator: AlertGenerator,
    mock_causal_graph_empty: dict[str, Any],
    mock_monitor_nominal: dict[str, Any],
) -> None:
    """Forecasts senza feature latency per H_crit → generate() restituisce None."""
    forecasts_irrelevant = {
        "node:nginx-web-server:cpu_percent": _make_forecast_df([5.0] * _N_STEPS)
    }
    result = alert_generator.generate(
        "H_crit", forecasts_irrelevant,
        mock_causal_graph_empty, mock_monitor_nominal, _T0,
    )
    assert result is None


def test_aggregation_nan_yhat_uses_sla_as_conservative(
    alert_generator: AlertGenerator,
    mock_causal_graph_empty: dict[str, Any],
    mock_monitor_nominal: dict[str, Any],
) -> None:
    """yhat=NaN su tutti gli step: usa SLA (100.0) come fallback → violazione."""
    nan_df = _make_forecast_df([float("nan")] * _N_STEPS)
    forecasts = {k: nan_df for k in _H_CRIT_LATENCY_KEYS}
    # Fallback: 4 × 100.0 = 400 > 100 → violation
    result = alert_generator.generate(
        "H_crit", forecasts, mock_causal_graph_empty, mock_monitor_nominal, _T0,
    )
    assert isinstance(result, dict), (
        "Atteso dict (violazione dal fallback SLA), ottenuto None"
    )


#  Root cause (3) 

def test_root_cause_from_highest_intensity_edge(
    alert_generator: AlertGenerator,
    mock_monitor_nominal: dict[str, Any],
) -> None:
    """root_cause = source dell'edge con intensità maggiore nel CausalGraph."""
    causal_graph = {
        "compliance_set": "H_crit",
        "edges": [
            {
                "source": "node:nginx-web-server:cpu_percent",
                "target": "edge:e1:latency_ms",
                "type": "linear", "intensity": 0.3,
                "method": "granger", "lag": 1,
            },
            {
                "source": "node:post-storage-service:cpu_percent",
                "target": "edge:e4:latency_ms",
                "type": "linear", "intensity": 0.7,
                "method": "granger", "lag": 2,
            },
        ],
        "cross_property_chains": [],
    }
    forecasts = _make_forecasts_h_crit(yhat_per_arc=30.0)
    alert = alert_generator.generate(
        "H_crit", forecasts, causal_graph, mock_monitor_nominal, _T0,
    )
    assert alert is not None
    assert alert["root_cause"] == "node:post-storage-service:cpu_percent", (
        f"Attesa causa radice dell'edge con intensità 0.7, "
        f"ottenuto '{alert['root_cause']}'"
    )


def test_cross_property_interference_from_confirmed_chain(
    alert_generator: AlertGenerator,
    mock_monitor_nominal: dict[str, Any],
) -> None:
    """cross_property_interference = source_cs della catena cross-property confermata."""
    causal_graph = {
        "compliance_set": "H_crit",
        "edges": [],
        "cross_property_chains": [
            {
                "source_cs": "H_cache",
                "target_cs": "H_crit",
                "chain": ["interf:e2:throughput_rps", "node:home-timeline-service:cpu_percent", "edge:e4:latency_ms"],
                "confirmed": True,
            }
        ],
    }
    forecasts = _make_forecasts_h_crit(yhat_per_arc=30.0)
    alert = alert_generator.generate(
        "H_crit", forecasts, causal_graph, mock_monitor_nominal, _T0,
    )
    assert alert is not None
    assert alert["cross_property_interference"] == "H_cache"
    assert len(alert["causal_chain"]) == 3


def test_no_root_cause_on_empty_causal_graph(
    alert_generator: AlertGenerator,
    mock_causal_graph_empty: dict[str, Any],
    mock_monitor_nominal: dict[str, Any],
) -> None:
    """CausalGraph senza edges → root_cause=None, causal_chain=[]."""
    forecasts = _make_forecasts_h_crit(yhat_per_arc=30.0)
    alert = alert_generator.generate(
        "H_crit", forecasts, mock_causal_graph_empty, mock_monitor_nominal, _T0,
    )
    assert alert is not None
    assert alert["root_cause"] is None
    assert alert["causal_chain"] == []


#  Model uncertainty (3) 

def test_uncertainty_flag_false_on_smooth_forecast(
    alert_generator: AlertGenerator,
    mock_causal_graph_empty: dict[str, Any],
    mock_monitor_nominal: dict[str, Any],
) -> None:
    """Forecast lineare puro → model_uncertainty_flag=False."""
    # yhat=[30,40,50,60,70,80]: trend lineare esatto, deviazione=0 dalla baseline
    lin_yhats = [30.0 + 10.0 * i for i in range(_N_STEPS)]
    forecasts = {k: _make_forecast_df(lin_yhats) for k in _H_CRIT_LATENCY_KEYS}
    alert = alert_generator.generate(
        "H_crit", forecasts, mock_causal_graph_empty, mock_monitor_nominal, _T0,
    )
    assert alert is not None
    assert alert["model_uncertainty_flag"] is False, (
        "Atteso uncertainty_flag=False su forecast lineare puro"
    )


def test_uncertainty_flag_true_on_oscillating_forecast(
    alert_generator: AlertGenerator,
    mock_causal_graph_empty: dict[str, Any],
    mock_monitor_nominal: dict[str, Any],
) -> None:
    """Forecast fortemente oscillante → model_uncertainty_flag=True."""
    # [10,300,10,300,10,300]: MAD/range ≈ 0.46 > divergence_threshold=0.20
    osc_yhats = [10.0, 300.0, 10.0, 300.0, 10.0, 300.0]
    forecasts = {k: _make_forecast_df(osc_yhats) for k in _H_CRIT_LATENCY_KEYS}
    alert = alert_generator.generate(
        "H_crit", forecasts, mock_causal_graph_empty, mock_monitor_nominal, _T0,
    )
    assert alert is not None
    assert alert["model_uncertainty_flag"] is True, (
        "Atteso uncertainty_flag=True su forecast oscillante"
    )


def test_uncertainty_demotes_red_to_orange(
    alert_generator: AlertGenerator,
    mock_causal_graph_empty: dict[str, Any],
    mock_monitor_red: dict[str, Any],
) -> None:
    """RED + model_uncertainty_flag=True → criticality declassato a 'orange'."""
    # Oscillazione forte (violation al step 2, oscillazione attiva flag)
    # step 1: sum=4×10=40<100, step 2+: sum=4×300=1200>100 → violation step 2
    osc_yhats = [10.0, 300.0, 10.0, 300.0, 10.0, 300.0]
    forecasts = {k: _make_forecast_df(osc_yhats) for k in _H_CRIT_LATENCY_KEYS}
    # monitor_red: cusum_signal=True AND structural_confirmed=True → RED baseline
    alert = alert_generator.generate(
        "H_crit", forecasts, mock_causal_graph_empty, mock_monitor_red, _T0,
    )
    assert alert is not None
    assert alert["model_uncertainty_flag"] is True
    assert alert["criticality"] == "orange", (
        f"Atteso 'orange' dopo declassamento RED per incertezza modello, "
        f"ottenuto '{alert['criticality']}'"
    )


#  Robustezza (3) 

def test_generate_unknown_compliance_set_raises(
    alert_generator: AlertGenerator,
    mock_forecasts_h_crit: dict[str, pd.DataFrame],
    mock_causal_graph_empty: dict[str, Any],
    mock_monitor_nominal: dict[str, Any],
) -> None:
    """generate() con CS inesistente solleva KeyError."""
    with pytest.raises(KeyError):
        alert_generator.generate(
            "H_nonexistent", mock_forecasts_h_crit,
            mock_causal_graph_empty, mock_monitor_nominal, _T0,
        )


def test_missing_alert_generation_key_raises(
    config: ConfigLoader, topology_builder: TopologyBuilder
) -> None:
    """Costruttore solleva ValueError se manca 'yellow_min_days'."""
    pipeline = config.load_pipeline_params()
    bad_pipeline = copy.deepcopy(pipeline)
    del bad_pipeline["alert_generation"]["yellow_min_days"]
    with patch.object(
        type(config), "load_pipeline_params", return_value=bad_pipeline
    ):
        with pytest.raises(ValueError, match="yellow_min_days"):
            AlertGenerator(config, topology_builder)


def test_generate_with_empty_forecasts_returns_none(
    alert_generator: AlertGenerator,
    mock_causal_graph_empty: dict[str, Any],
    mock_monitor_nominal: dict[str, Any],
) -> None:
    """generate() con forecasts={} → None (nessuna feature da aggregare)."""
    result = alert_generator.generate(
        "H_crit", {}, mock_causal_graph_empty, mock_monitor_nominal, _T0,
    )
    assert result is None


#  Aggregazione estesa (2) 

def test_aggregation_reliability_product_complement(
    config: ConfigLoader,
    topology_builder: TopologyBuilder,
) -> None:
    """Reliability = Π(1-ε_e): 0.01 error_rate → no violation; 0.02 → violation.

    La SLA error_rate upper 0.05 equivale a reliability lower 0.95.
    Con 4 archi:
      (1-0.01)^4 ≈ 0.9606 > 0.95 → nessuna violazione → None
      (1-0.02)^4 ≈ 0.9224 < 0.95 → violazione → dict
    """
    bad_topology = copy.deepcopy(config.load_topology())
    bad_topology["compliance_sets"]["H_crit"]["sla"] = {
        "error_rate": {"bound": "upper", "threshold": 0.05}
    }
    with patch.object(type(config), "load_topology", return_value=bad_topology):
        ag = AlertGenerator(config, topology_builder)

    _H_CRIT_ERR_KEYS = [
        "edge:e1:error_rate",
        "edge:e2:error_rate",
        "edge:e4:error_rate",
        "edge:e6:error_rate",
    ]
    causal_graph = _make_causal_graph_empty()
    monitor = _make_monitor_nominal()

    # 0.01 per arco: reliability ≈ 0.9606 > 0.95 → no violation
    forecasts_ok = {k: _make_forecast_df([0.01] * _N_STEPS) for k in _H_CRIT_ERR_KEYS}
    result = ag.generate("H_crit", forecasts_ok, causal_graph, monitor, _T0)
    assert result is None, (
        f"Atteso None (reliability ≈ 0.9606 > 0.95), ma ottenuto alert."
    )

    # 0.02 per arco: reliability ≈ 0.9224 < 0.95 → violation
    forecasts_vio = {k: _make_forecast_df([0.02] * _N_STEPS) for k in _H_CRIT_ERR_KEYS}
    result = ag.generate("H_crit", forecasts_vio, causal_graph, monitor, _T0)
    assert isinstance(result, dict), (
        "Atteso dict (reliability ≈ 0.9224 < 0.95 → violation), ottenuto None."
    )


def test_aggregation_capacity_min(
    config: ConfigLoader,
    topology_builder: TopologyBuilder,
) -> None:
    """Capacity = min(throughput per arco): min(50,30,80,20)=20 < SLA 25 → violation."""
    bad_topology = copy.deepcopy(config.load_topology())
    bad_topology["compliance_sets"]["H_crit"]["sla"] = {
        "throughput_rps": {"bound": "lower", "threshold": 25.0}
    }
    with patch.object(type(config), "load_topology", return_value=bad_topology):
        ag = AlertGenerator(config, topology_builder)

    forecasts = {
        "edge:e1:throughput_rps": _make_forecast_df([50.0] * _N_STEPS),
        "edge:e2:throughput_rps": _make_forecast_df([30.0] * _N_STEPS),
        "edge:e4:throughput_rps": _make_forecast_df([80.0] * _N_STEPS),
        "edge:e6:throughput_rps": _make_forecast_df([20.0] * _N_STEPS),
    }
    causal_graph = _make_causal_graph_empty()
    monitor = _make_monitor_nominal()

    alert = ag.generate("H_crit", forecasts, causal_graph, monitor, _T0)
    assert alert is not None
    assert abs(alert["aggregated_forecast"][0] - 20.0) < 1e-9, (
        f"Atteso aggregated_forecast[0]=20.0 (min dei 4 archi), "
        f"ottenuto {alert['aggregated_forecast'][0]}"
    )
    assert alert["lead_time_steps"] == 1, (
        f"Atteso lead_time_steps=1 (20 < 25 al step 1), "
        f"ottenuto {alert['lead_time_steps']}"
    )
