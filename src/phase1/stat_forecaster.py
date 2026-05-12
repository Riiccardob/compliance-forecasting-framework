"""Fase I — orchestratore del forecasting per-metrica con routing Prophet/LSTM/ARIMA/Linear."""
from typing import Any

import numpy as np
import pandas as pd
from prophet import Prophet
from sklearn.linear_model import LinearRegression, Ridge

from src.utils.config_loader import ConfigLoader
from src.utils.logging_setup import LoggingSetup

logger = LoggingSetup.configure(__name__, "INFO")


class StatForecaster:
    """Addestra e applica modelli di forecasting per ogni feature di FeatureSelector.

    Il routing del modello è determinato da pipeline_params.yaml e da un
    eventuale ``model_override`` passato a ``fit()``:

    - chiave in ``model_override`` → modello specificato nell'override
    - metriche in ``forecasting.lstm.nonlinear_metrics`` → LSTM (Ridge placeholder)
    - tutte le altre → Prophet (default)

    Modelli disponibili: ``"prophet"``, ``"lstm"``, ``"arima"``, ``"linear"``.

    Se il training set di una metrica nonlinear ha meno di
    ``input_window × 2`` campioni, il routing degrada automaticamente
    a Prophet con un warning.
    """

    _VALID_MODELS: frozenset[str] = frozenset({"prophet", "lstm", "arima", "linear"})

    def __init__(self, config: ConfigLoader) -> None:
        """Legge i parametri di forecasting da pipeline_params.yaml.

        Parameters
        ----------
        config:
            ConfigLoader già inizializzato.
        """
        self._params = config.load_pipeline_params()

        fc = self._params["forecasting"]
        self._horizon_steps: int = fc["horizon_steps"]
        self._nonlinear_metrics: set[str] = set(fc["lstm"]["nonlinear_metrics"])
        self._input_window: int = fc["lstm"]["input_window"]

        arima_cfg = fc.get("arima", {})
        self._arima_max_p: int = arima_cfg.get("max_p", 2)
        self._arima_max_d: int = arima_cfg.get("max_d", 1)
        self._arima_max_q: int = arima_cfg.get("max_q", 2)

        self._models: dict[str, Any] = {}
        self._routing: dict[str, str] = {}
        self._train_data: dict[str, pd.DataFrame] = {}
        self._is_fitted: bool = False

    # ------------------------------------------------------------------
    # API pubblica
    # ------------------------------------------------------------------

    def fit(
        self,
        features: dict[str, pd.DataFrame],
        nominal_snapshots: list[dict] | None = None,
        model_override: dict[str, str] | None = None,
    ) -> None:
        """Addestra un modello per ogni feature nel dizionario.

        Parameters
        ----------
        features:
            Output di FeatureSelector.select_features().
        nominal_snapshots:
            Snapshot nominali (label==0). Se None usa tutte le righe.
        model_override:
            Mappa feature_key → nome modello. Sovrascrive il routing
            automatico per le chiavi specificate. Valori ammessi:
            ``"prophet"``, ``"lstm"``, ``"arima"``, ``"linear"``.
        """
        self._models = {}
        self._routing = {}
        self._train_data = {}

        nominal_ts: set[int] | None = None
        if nominal_snapshots is not None:
            nominal_ts = {int(s["timestamp"]) for s in nominal_snapshots}

        for key, df in features.items():
            metric_name = key.split(":")[-1]

            if nominal_ts is not None:
                train_df = df[df.index.isin(nominal_ts)].dropna()
            else:
                train_df = df.dropna()

            if len(train_df) == 0:
                logger.warning(
                    "Feature '%s': training set vuoto dopo filtraggio "
                    "nominale — feature esclusa dal forecasting.", key
                )
                continue

            routing = self._route_model(key, metric_name, len(train_df), model_override)
            if routing not in StatForecaster._VALID_MODELS:
                raise ValueError(
                    f"model_override per '{key}': modello '{routing}' "
                    f"non valido. Valori ammessi: {sorted(StatForecaster._VALID_MODELS)}."
                )
            self._routing[key] = routing
            self._train_data[key] = train_df

            if routing == "prophet":
                self._models[key] = self._fit_prophet(train_df)
            elif routing == "lstm":
                self._models[key] = self._fit_lstm_placeholder(train_df)
            elif routing == "arima":
                self._models[key] = self._fit_arima(key, train_df)
            else:  # linear
                self._models[key] = self._fit_linear(key, train_df)

        self._is_fitted = True
        logger.info(
            "StatForecaster addestrato: %d feature, routing=%s",
            len(features),
            self._routing,
        )

    def predict(
        self,
        horizon_steps: int | None = None,
    ) -> dict[str, pd.DataFrame]:
        """Genera previsioni per tutte le feature addestrate.

        Parameters
        ----------
        horizon_steps:
            Numero di step da prevedere. Se None usa forecasting.horizon_steps.

        Returns
        -------
        dict[str, pd.DataFrame]
            Index: timestamp futuro (int µs). Colonne: yhat, yhat_lower, yhat_upper.
        """
        if not self._is_fitted:
            raise RuntimeError(
                "StatForecaster non ancora addestrato. Chiama fit() prima di predict()."
            )

        h = horizon_steps if horizon_steps is not None else self._horizon_steps
        result: dict[str, pd.DataFrame] = {}

        for key, model in self._models.items():
            train_df = self._train_data[key]
            freq_us = self._infer_freq_us(train_df)
            last_ts = int(train_df.index[-1]) if len(train_df) > 0 else 0

            routing = self._routing[key]
            if routing == "prophet":
                result[key] = self._predict_prophet(model, h, last_ts, freq_us)
            elif routing == "lstm":
                result[key] = self._predict_lstm_placeholder(
                    model, train_df, h, last_ts, freq_us
                )
            elif routing == "arima":
                result[key] = self._predict_arima(model, h, last_ts, freq_us)
            else:  # linear
                model_lr, std = model
                result[key] = self._predict_linear(model_lr, std, last_ts, h, freq_us)

        return result

    def get_model_routing(self) -> dict[str, str]:
        """Restituisce il routing modello per ogni feature.

        Returns
        -------
        dict[str, str]
            Mappa feature_key → nome del modello
            (``"prophet"``, ``"lstm"``, ``"arima"``, ``"linear"``).

        Raises
        ------
        RuntimeError
            Se chiamato prima di fit().
        """
        if not self._is_fitted:
            raise RuntimeError(
                "StatForecaster non ancora addestrato. Chiama fit() prima di get_model_routing()."
            )
        return dict(self._routing)

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def _route_model(
        self,
        key: str,
        metric_name: str,
        n_samples: int,
        model_override: dict[str, str] | None,
    ) -> str:
        """Determina il modello per una feature."""
        if model_override and key in model_override:
            return model_override[key]

        if metric_name in self._nonlinear_metrics:
            if n_samples < self._input_window * 2:
                logger.warning(
                    "Serie '%s' ha %d campioni < input_window×2=%d. "
                    "Fallback da LSTM a Prophet.",
                    key, n_samples, self._input_window * 2,
                )
                return "prophet"
            return "lstm"

        return "prophet"

    # ------------------------------------------------------------------
    # Fitting
    # ------------------------------------------------------------------

    def _fit_prophet(self, df: pd.DataFrame) -> Prophet:
        prophet_df = pd.DataFrame({
            "ds": pd.to_datetime(df.index, unit="us"),
            "y": df["value"].values.astype(float),
        })
        model = Prophet(changepoint_prior_scale=0.05)
        model.fit(prophet_df)
        return model

    def _fit_lstm_placeholder(self, df: pd.DataFrame) -> Ridge:
        # TODO: Replace with actual LSTM (PyTorch/Keras) when GPU/training budget available.
        # Ridge regression on lagged features simulates the fit/predict API.
        values = df["value"].values.astype(float)
        n = len(values)
        window = min(self._input_window, n - 1)
        if window <= 0:
            model = Ridge()
            model.fit([[0.0]], [0.0])
            return model
        X = np.array([values[i:i + window] for i in range(n - window)])
        y = values[window:]
        model = Ridge()
        model.fit(X, y)
        return model

    def _fit_arima(self, key: str, df: pd.DataFrame) -> Any:
        """Addestra ARIMA con selezione automatica dell'ordine (p,d,q) via AIC."""
        from statsmodels.tsa.statespace.sarimax import SARIMAX

        y = df["value"].dropna().values.astype(float)
        best_aic = float("inf")
        best_model = None
        for p in range(self._arima_max_p + 1):
            for d in range(self._arima_max_d + 1):
                for q in range(self._arima_max_q + 1):
                    try:
                        m = SARIMAX(
                            y,
                            order=(p, d, q),
                            enforce_stationarity=False,
                            enforce_invertibility=False,
                        )
                        r = m.fit(disp=False)
                        if r.aic < best_aic:
                            best_aic = r.aic
                            best_model = r
                    except Exception:
                        continue
        if best_model is None:
            raise RuntimeError(f"ARIMA fitting fallito per {key}")
        return best_model

    def _fit_linear(self, key: str, df: pd.DataFrame) -> tuple[LinearRegression, float]:
        """Regressione lineare su indice temporale → valore. Baseline stazionario."""
        mask = ~df["value"].isna()
        X = df.index.values[mask].reshape(-1, 1).astype(float)
        y = df["value"].values[mask].astype(float)
        model = LinearRegression().fit(X, y)
        residuals = y - model.predict(X)
        std = float(np.std(residuals)) if len(residuals) > 1 else 0.0
        return model, std

    # ------------------------------------------------------------------
    # Predizione
    # ------------------------------------------------------------------

    def _predict_prophet(
        self, model: Prophet, horizon_steps: int, last_ts: int, freq_us: int
    ) -> pd.DataFrame:
        future_ts = [last_ts + (i + 1) * freq_us for i in range(horizon_steps)]
        future_df = pd.DataFrame({"ds": pd.to_datetime(future_ts, unit="us")})
        forecast = model.predict(future_df)
        return pd.DataFrame(
            {
                "yhat": forecast["yhat"].values,
                "yhat_lower": forecast["yhat_lower"].values,
                "yhat_upper": forecast["yhat_upper"].values,
            },
            index=pd.Index(future_ts, name="timestamp"),
        )

    def _predict_lstm_placeholder(
        self,
        model: Ridge,
        train_df: pd.DataFrame,
        horizon_steps: int,
        last_ts: int,
        freq_us: int,
    ) -> pd.DataFrame:
        # TODO: Replace with LSTM forward pass + Monte Carlo Dropout for uncertainty
        future_ts = [last_ts + (i + 1) * freq_us for i in range(horizon_steps)]
        values = train_df["value"].values.astype(float)
        window = len(model.coef_)  # coef_ is 1D for single-output Ridge

        # Seed the prediction buffer with the last `window` training values
        buffer = list(values[-window:]) if len(values) >= window else list(values)
        while len(buffer) < window:
            buffer.insert(0, buffer[0])

        yhats: list[float] = []
        for _ in range(horizon_steps):
            x = np.array(buffer[-window:]).reshape(1, -1)
            yhat = float(model.predict(x)[0])
            yhats.append(yhat)
            buffer.append(yhat)

        yhats_arr = np.array(yhats)
        # Symmetric margin: 5% of absolute value, minimum 1e-6 to avoid degenerate intervals
        margin = np.abs(yhats_arr) * 0.05 + 1e-6
        return pd.DataFrame(
            {
                "yhat": yhats_arr,
                "yhat_lower": yhats_arr - margin,
                "yhat_upper": yhats_arr + margin,
            },
            index=pd.Index(future_ts, name="timestamp"),
        )

    def _predict_arima(
        self, fitted_model: Any, horizon_steps: int, last_ts: int, freq_us: int
    ) -> pd.DataFrame:
        future_ts = [last_ts + (i + 1) * freq_us for i in range(horizon_steps)]
        forecast_res = fitted_model.get_forecast(steps=horizon_steps)
        yhat = np.asarray(forecast_res.predicted_mean)
        conf = np.asarray(forecast_res.conf_int(alpha=0.05))
        return pd.DataFrame(
            {
                "yhat": yhat,
                "yhat_lower": conf[:, 0],
                "yhat_upper": conf[:, 1],
            },
            index=pd.Index(future_ts, name="timestamp"),
        )

    def _predict_linear(
        self,
        model: LinearRegression,
        std: float,
        last_ts: int,
        horizon_steps: int,
        freq_us: int,
    ) -> pd.DataFrame:
        """Proietta l'orizzonte futuro per la regressione lineare."""
        future_ts = [last_ts + (i + 1) * freq_us for i in range(horizon_steps)]
        future_X = np.array(future_ts, dtype=float).reshape(-1, 1)
        yhat = model.predict(future_X)
        return pd.DataFrame(
            {
                "yhat": yhat,
                "yhat_lower": yhat - 1.96 * std,
                "yhat_upper": yhat + 1.96 * std,
            },
            index=pd.Index(future_ts, name="timestamp"),
        )

    # ------------------------------------------------------------------
    # Utilità
    # ------------------------------------------------------------------

    def _infer_freq_us(self, df: pd.DataFrame) -> int:
        """Stima la frequenza di campionamento in µs dalla mediana dei diff."""
        if len(df) < 2:
            return 5_000_000  # default: 5 s in µs
        diffs = np.diff(df.index.values.astype(np.int64))
        freq = int(np.median(diffs))
        if freq <= 0:
            logger.warning(
                "_infer_freq_us: frequenza stimata %d µs ≤ 0 "
                "(timestamp identici o decrescenti) — fallback a 5 s.",
                freq,
            )
            return 5_000_000
        return freq
