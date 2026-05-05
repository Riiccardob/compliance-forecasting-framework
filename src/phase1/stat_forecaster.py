"""Fase I — orchestratore del forecasting per-metrica con routing Prophet/LSTM/ARIMA."""
from typing import Any

import numpy as np
import pandas as pd
from prophet import Prophet
from sklearn.linear_model import Ridge

from src.utils.config_loader import ConfigLoader
from src.utils.logging_setup import LoggingSetup


class StatForecaster:
    """Addestra e applica modelli di forecasting per ogni feature di FeatureSelector.

    Il routing del modello è determinato staticamente da pipeline_params.yaml:
    - metriche in ``forecasting.lstm.nonlinear_metrics`` → LSTM (Ridge placeholder)
    - tutte le altre → Prophet (default)

    Se il training set di una metrica nonlinear ha meno di
    ``input_window × 2`` campioni, il routing degrada automaticamente
    a Prophet con un warning.
    """

    def __init__(self, config: ConfigLoader) -> None:
        """Legge i parametri di forecasting da pipeline_params.yaml.

        Parameters
        ----------
        config:
            ConfigLoader già inizializzato.
        """
        self._params = config.load_pipeline_params()
        self._logger = LoggingSetup.configure(__name__, "INFO")

        fc = self._params["forecasting"]
        self._horizon_steps: int = fc["horizon_steps"]
        self._nonlinear_metrics: set[str] = set(fc["lstm"]["nonlinear_metrics"])
        self._input_window: int = fc["lstm"]["input_window"]

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
    ) -> None:
        """Addestra un modello per ogni feature nel dizionario.

        Parameters
        ----------
        features:
            Output di FeatureSelector.select_features().
        nominal_snapshots:
            Snapshot nominali (label==0). Se None usa tutte le righe.
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

            # Routing: nonlinear → LSTM se dati sufficienti, altrimenti Prophet
            if metric_name in self._nonlinear_metrics:
                if len(train_df) < self._input_window * 2:
                    self._logger.warning(
                        "Serie '%s' ha %d campioni < input_window×2=%d. "
                        "Fallback da LSTM a Prophet.",
                        key, len(train_df), self._input_window * 2,
                    )
                    routing = "prophet"
                else:
                    routing = "lstm"
            else:
                routing = "prophet"

            self._routing[key] = routing
            self._train_data[key] = train_df

            if routing == "prophet":
                self._models[key] = self._fit_prophet(train_df)
            else:
                self._models[key] = self._fit_lstm_placeholder(train_df)

        self._is_fitted = True
        self._logger.info(
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

            if self._routing[key] == "prophet":
                result[key] = self._predict_prophet(model, h, last_ts, freq_us)
            else:
                result[key] = self._predict_lstm_placeholder(
                    model, train_df, h, last_ts, freq_us
                )

        return result

    def get_model_routing(self) -> dict[str, str]:
        """Restituisce il routing modello per ogni feature.

        Returns
        -------
        dict[str, str]
            Mappa feature_key → nome del modello ("prophet" o "lstm").

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

    # ------------------------------------------------------------------
    # Utilità
    # ------------------------------------------------------------------

    @staticmethod
    def _infer_freq_us(df: pd.DataFrame) -> int:
        """Stima la frequenza di campionamento in µs dalla mediana dei diff."""
        if len(df) < 2:
            return 5_000_000  # default: 5 s in µs
        diffs = np.diff(df.index.values.astype(np.int64))
        return int(np.median(diffs))
