"""Test per StatForecaster — mock leggeri, nessun CSV reale."""
import warnings
from pathlib import Path

import pandas as pd
import pytest

from src.utils.config_loader import ConfigLoader
from src.phase1.stat_forecaster import StatForecaster

warnings.filterwarnings("ignore", category=UserWarning)

_ROOT = Path(__file__).parent.parent
_TOPOLOGY_PATH = _ROOT / "config" / "topology.yaml"
_PIPELINE_PATH = _ROOT / "config" / "pipeline_params.yaml"

_T0 = 1_000_000_000      # µs — punto di partenza lontano dall'origine
_STEP_US = 5_000_000     # 5 s in µs
_N = 50                  # ≥ input_window × 2 = 24 × 2 = 48 → LSTM routing attivo


def _make_series(
    n: int,
    start_ts: int = _T0,
    step: int = _STEP_US,
    trend: float = 0.1,
) -> pd.DataFrame:
    timestamps = [start_ts + i * step for i in range(n)]
    values = [5.0 + trend * i for i in range(n)]
    return pd.DataFrame(
        {"value": values},
        index=pd.Index(timestamps, name="timestamp"),
    )


#FIXTURE

@pytest.fixture
def config() -> ConfigLoader:
    return ConfigLoader(_TOPOLOGY_PATH, _PIPELINE_PATH)


@pytest.fixture
def forecaster(config: ConfigLoader) -> StatForecaster:
    return StatForecaster(config)


@pytest.fixture
def mock_features() -> dict[str, pd.DataFrame]:
    return {
        "node:nginx-web-server:cpu_percent": _make_series(_N),
        "node:home-timeline-service:mem_mb": _make_series(_N),
    }


#TEST

def test_get_model_routing_before_fit_raises(
    forecaster: StatForecaster,
) -> None:
    """get_model_routing() prima di fit() solleva RuntimeError."""
    with pytest.raises(RuntimeError):
        forecaster.get_model_routing()


def test_routing_cpu_percent_is_prophet(
    forecaster: StatForecaster, mock_features: dict[str, pd.DataFrame]
) -> None:
    """cpu_percent non è in nonlinear_metrics → Prophet."""
    forecaster.fit(mock_features)
    assert forecaster.get_model_routing()["node:nginx-web-server:cpu_percent"] == "prophet"


def test_routing_mem_mb_is_lstm(
    forecaster: StatForecaster, mock_features: dict[str, pd.DataFrame]
) -> None:
    """mem_mb è in nonlinear_metrics e _N=50 ≥ input_window×2=48 → LSTM (Ridge placeholder)."""
    forecaster.fit(mock_features)
    assert forecaster.get_model_routing()["node:home-timeline-service:mem_mb"] == "lstm"


def test_fit_completes_without_exception(
    forecaster: StatForecaster, mock_features: dict[str, pd.DataFrame]
) -> None:
    """fit() su mock_features non solleva eccezioni."""
    forecaster.fit(mock_features)


def test_predict_returns_dict(
    forecaster: StatForecaster, mock_features: dict[str, pd.DataFrame]
) -> None:
    """predict() restituisce dict."""
    forecaster.fit(mock_features)
    assert isinstance(forecaster.predict(), dict)


def test_predict_keys_match_features(
    forecaster: StatForecaster, mock_features: dict[str, pd.DataFrame]
) -> None:
    """Le chiavi di predict() corrispondono alle chiavi di fit()."""
    forecaster.fit(mock_features)
    result = forecaster.predict()
    assert set(result.keys()) == set(mock_features.keys())


def test_predict_columns_yhat_lower_upper(
    forecaster: StatForecaster, mock_features: dict[str, pd.DataFrame]
) -> None:
    """Ogni DataFrame di predict() ha colonne ['yhat', 'yhat_lower', 'yhat_upper']."""
    forecaster.fit(mock_features)
    for key, df in forecaster.predict().items():
        assert list(df.columns) == ["yhat", "yhat_lower", "yhat_upper"], (
            f"Colonne errate per '{key}': {list(df.columns)}"
        )


def test_predict_horizon_default(
    forecaster: StatForecaster, mock_features: dict[str, pd.DataFrame]
) -> None:
    """predict() senza argomenti produce horizon_steps=12 righe (da pipeline_params.yaml)."""
    forecaster.fit(mock_features)
    for key, df in forecaster.predict().items():
        assert len(df) == 12, f"Atteso 12 righe per '{key}', ottenuto {len(df)}"


def test_predict_horizon_override(
    forecaster: StatForecaster, mock_features: dict[str, pd.DataFrame]
) -> None:
    """predict(horizon_steps=5) produce esattamente 5 righe per ogni feature."""
    forecaster.fit(mock_features)
    for key, df in forecaster.predict(horizon_steps=5).items():
        assert len(df) == 5, f"Atteso 5 righe per '{key}', ottenuto {len(df)}"


def test_predict_before_fit_raises(forecaster: StatForecaster) -> None:
    """predict() prima di fit() solleva RuntimeError."""
    with pytest.raises(RuntimeError):
        forecaster.predict()


def test_yhat_lower_leq_yhat_leq_upper(
    forecaster: StatForecaster, mock_features: dict[str, pd.DataFrame]
) -> None:
    """yhat_lower ≤ yhat ≤ yhat_upper per ogni riga e ogni feature."""
    forecaster.fit(mock_features)
    for key, df in forecaster.predict().items():
        assert (df["yhat_lower"] <= df["yhat"] + 1e-9).all(), (
            f"yhat_lower > yhat per '{key}'"
        )
        assert (df["yhat"] <= df["yhat_upper"] + 1e-9).all(), (
            f"yhat > yhat_upper per '{key}'"
        )


def test_fallback_to_prophet_on_short_series(
    forecaster: StatForecaster,
) -> None:
    """Con 3 timestep (< input_window×2=48), mem_mb usa Prophet come fallback
    e viene emesso un logger.warning."""
    short_features = {"node:home-timeline-service:mem_mb": _make_series(3)}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        forecaster.fit(short_features)
    assert forecaster.get_model_routing()["node:home-timeline-service:mem_mb"] == "prophet"


def test_fit_ignores_anomalous_snapshots(
    forecaster: StatForecaster, mock_features: dict[str, pd.DataFrame]
) -> None:
    """nominal_snapshots con 10 righe: il modello si addestra su 10 campioni;
    predict() produce comunque horizon_steps=12 righe."""
    nominal_ts = list(mock_features["node:nginx-web-server:cpu_percent"].index[:10])
    nominal_snaps = [{"timestamp": ts} for ts in nominal_ts]
    forecaster.fit(mock_features, nominal_snapshots=nominal_snaps)
    for key, df in forecaster.predict().items():
        assert len(df) == 12, f"Atteso 12 righe per '{key}', ottenuto {len(df)}"


def test_get_model_routing_after_fit_returns_dict(
    forecaster: StatForecaster, mock_features: dict[str, pd.DataFrame]
) -> None:
    """get_model_routing() dopo fit() restituisce dict con una chiave per ogni feature."""
    forecaster.fit(mock_features)
    routing = forecaster.get_model_routing()
    assert isinstance(routing, dict)
    assert set(routing.keys()) == set(mock_features.keys())


def test_arima_fit_and_predict(
    config: ConfigLoader, mock_features: dict[str, pd.DataFrame]
) -> None:
    """ARIMA addestrato con model_override produce previsioni con le colonne attese
    e yhat_lower ≤ yhat ≤ yhat_upper."""
    forecaster = StatForecaster(config)
    forecaster.fit(
        mock_features,
        model_override={"node:nginx-web-server:cpu_percent": "arima"},
    )
    preds = forecaster.predict(horizon_steps=3)
    df = preds["node:nginx-web-server:cpu_percent"]
    assert list(df.columns) == ["yhat", "yhat_lower", "yhat_upper"]
    assert (df["yhat_lower"] <= df["yhat"] + 1e-9).all()
    assert (df["yhat"] <= df["yhat_upper"] + 1e-9).all()


def test_linear_fit_and_predict(
    config: ConfigLoader, mock_features: dict[str, pd.DataFrame]
) -> None:
    """Linear Regression addestrato con model_override produce previsioni con
    le colonne attese."""
    forecaster = StatForecaster(config)
    forecaster.fit(
        mock_features,
        model_override={"node:nginx-web-server:cpu_percent": "linear"},
    )
    preds = forecaster.predict(horizon_steps=3)
    df = preds["node:nginx-web-server:cpu_percent"]
    assert list(df.columns) == ["yhat", "yhat_lower", "yhat_upper"]


def test_routing_reflects_override(
    config: ConfigLoader, mock_features: dict[str, pd.DataFrame]
) -> None:
    """get_model_routing() riflette il model_override passato a fit()."""
    forecaster = StatForecaster(config)
    forecaster.fit(
        mock_features,
        model_override={"node:nginx-web-server:cpu_percent": "arima"},
    )
    routing = forecaster.get_model_routing()
    assert routing["node:nginx-web-server:cpu_percent"] == "arima"
