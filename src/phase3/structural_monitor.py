"""Fase III - Monitoraggio strutturale gerarchico su M_Φi."""
from collections import deque
from typing import Any

import numpy as np
from sklearn.ensemble import IsolationForest

from src.layer1.topology_builder import TopologyBuilder
from src.layer2.pbo_builder import PBOBuilder
from src.utils.config_loader import ConfigLoader
from src.utils.logging_setup import LoggingSetup


class StructuralMonitor:
    """Monitoraggio gerarchico a quattro livelli su M_Φi.

    Livello 1: threshold statico SLA + z-score adattivo (sempre attivi).
    Livello 2: Isolation Forest (condizionale a base_signal).
    Livello 3: EWMA + CUSUM su PAS (lineare) o Frobenius (parallelo).
    Livello 4: Validatore strutturale (condizionale a if_signal AND cusum_signal).

    Il monitor è stateful: mantiene accumulatore CUSUM e storia EWMA tra
    chiamate consecutive a monitor(). reset_cusum() azzera lo stato.
    """

    def __init__(
        self,
        config: ConfigLoader,
        topology_builder: TopologyBuilder,
        pbo_builder: PBOBuilder,
    ) -> None:
        """Legge parametri da pipeline_params.yaml e inizializza il monitor.

        Parameters
        ----------
        config:
            ConfigLoader già inizializzato.
        topology_builder:
            TopologyBuilder già inizializzato.
        pbo_builder:
            PBOBuilder già inizializzato.

        Raises
        ------
        ValueError
            Se manca una chiave obbligatoria in
            ``pipeline_params["anomaly_detection"]``.
        """
        self._logger = LoggingSetup.configure(__name__, "INFO")
        self._tb = topology_builder
        self._pbo = pbo_builder
        self._topology: dict[str, Any] = config.load_topology()
        self._node_metrics: list[str] = self._topology.get("node_metrics", [])

        ad = config.load_pipeline_params()["anomaly_detection"]

        # --- Validazione chiavi obbligatorie ---
        for key in ("zscore_threshold", "isolation_forest", "cusum", "structural_validator"):
            if key not in ad:
                raise ValueError(
                    f"Chiave obbligatoria mancante in "
                    f"pipeline_params['anomaly_detection']: '{key}'"
                )
        for sub_key in ("contamination", "n_estimators"):
            if sub_key not in ad["isolation_forest"]:
                raise ValueError(
                    f"Chiave obbligatoria mancante in "
                    f"pipeline_params['anomaly_detection']['isolation_forest']: '{sub_key}'"
                )
        for sub_key in ("ewma_alpha", "alert_threshold"):
            if sub_key not in ad["cusum"]:
                raise ValueError(
                    f"Chiave obbligatoria mancante in "
                    f"pipeline_params['anomaly_detection']['cusum']: '{sub_key}'"
                )
        if "distance_threshold" not in ad["structural_validator"]:
            raise ValueError(
                "Chiave obbligatoria mancante in "
                "pipeline_params['anomaly_detection']['structural_validator']: "
                "'distance_threshold'"
            )

        # --- Parametri ---
        self._zscore_threshold: float = float(ad["zscore_threshold"])
        if_cfg = ad["isolation_forest"]
        self._iso_contamination: float = float(if_cfg["contamination"])
        self._iso_n_estimators: int = int(if_cfg["n_estimators"])
        self._iso_random_state: int = int(if_cfg.get("random_state", 42))

        cusum_cfg = ad["cusum"]
        self._ewma_alpha: float = float(cusum_cfg["ewma_alpha"])
        self._cusum_threshold: float = float(cusum_cfg["alert_threshold"])
        self._cusum_k: float = float(cusum_cfg.get("tolerance_factor", 0.0))

        sv_cfg = ad["structural_validator"]
        self._frobenius_threshold: float = float(sv_cfg["distance_threshold"])
        self._consecutive_windows: int = int(sv_cfg.get("trend_intervals", 3))

        # --- Stato interno ---
        self._iso_forest: IsolationForest = IsolationForest(
            n_estimators=self._iso_n_estimators,
            contamination=self._iso_contamination,
            random_state=self._iso_random_state,
        )
        self._cusum_stat: float = 0.0
        self._ewma_state: float | None = None
        self._ewma_history: deque[float] = deque(maxlen=self._consecutive_windows + 1)

        self._is_fitted: bool = False
        self._training_means: dict[str, float] = {}
        self._training_stds: dict[str, float] = {}
        self._node_means: np.ndarray = np.array([])
        self._node_feature_order: list[tuple[str, str]] = []  # (node_id, metric)

        self._pas_gold: float | None = None
        self._reference: float = 0.0
        self._compliance_set_name: str = ""
        self._topology_type: str = ""
        self._gold_standard: dict[str, float] = {}

        self._logger.info(
            "StructuralMonitor inizializzato: zscore_threshold=%.1f, "
            "cusum_threshold=%.1f, frobenius_threshold=%.3f",
            self._zscore_threshold,
            self._cusum_threshold,
            self._frobenius_threshold,
        )

    # ------------------------------------------------------------------
    # API pubblica
    # ------------------------------------------------------------------

    def fit(
        self,
        compliance_set_name: str,
        features: dict[str, "pd.DataFrame"],
        nominal_snapshots: list[dict],
        weight_series: list[dict],
        gold_standard: dict[str, float],
    ) -> None:
        """Addestra il monitor sui dati nominali.

        Parameters
        ----------
        compliance_set_name:
            Nome del compliance set (es. ``"H_crit"``).
        features:
            Output di FeatureSelector.select_features() su dati nominali.
        nominal_snapshots:
            Snapshot label=0, da ATGBuilder.get_nominal_snapshots().
        weight_series:
            Output di PBOBuilder.compute_transition_weights() su nominali.
        gold_standard:
            Output di PBOBuilder.compute_gold_standard().

        Raises
        ------
        RuntimeError
            Se nominal_snapshots è vuoto.
        KeyError
            Se compliance_set_name non esiste in topology.yaml.
        """
        if compliance_set_name not in self._topology["compliance_sets"]:
            raise KeyError(f"Compliance set non trovato: '{compliance_set_name}'")
        if not nominal_snapshots:
            raise RuntimeError(
                "fit() richiede almeno uno snapshot nominale. "
                "nominal_snapshots è vuoto."
            )

        self._compliance_set_name = compliance_set_name
        self._gold_standard = gold_standard
        cs = self._topology["compliance_sets"][compliance_set_name]
        self._topology_type = cs.get("topology_type", "")

        cs_nodes = sorted(self._tb.get_compliance_set_nodes(compliance_set_name))
        node_metrics = sorted(self._node_metrics)
        self._node_feature_order = [
            (node_id, metric)
            for node_id in cs_nodes
            for metric in node_metrics
        ]

        # --- 1. Costruzione matrice X per Isolation Forest (solo feature nodo) ---
        X_rows: list[np.ndarray] = []
        for snap in nominal_snapshots:
            row = self._build_node_vector(snap)
            X_rows.append(row)
        X = np.array(X_rows)

        # Training mean per imputation NaN
        nan_frac = np.isnan(X).mean()
        if nan_frac > 0.1:
            self._logger.warning(
                "fit(): %.1f%% dei valori nel vettore aggregato sono NaN.",
                nan_frac * 100,
            )
        with np.errstate(all="ignore"):
            self._node_means = np.nanmean(X, axis=0)
        # Rimpiazza NaN in node_means con 0 (dimensioni tutte-NaN)
        self._node_means = np.where(np.isnan(self._node_means), 0.0, self._node_means)

        # Imputa NaN con column mean prima di addestrare IF
        X_imputed = np.where(np.isnan(X), self._node_means[np.newaxis, :], X)
        self._iso_forest.fit(X_imputed)

        # --- 2. Statistiche z-score su tutte le feature di M_Φi ---
        for key, df in features.items():
            vals = df["value"].dropna().values.astype(float)
            if len(vals) == 0:
                self._training_means[key] = 0.0
                self._training_stds[key] = 0.0
            else:
                self._training_means[key] = float(np.mean(vals))
                self._training_stds[key] = float(np.std(vals))

        # --- 3. PAS_gold o Frobenius_gold come riferimento CUSUM ---
        if self._topology_type == "linear":
            try:
                pas_series = self._pbo.compute_path_adherence(
                    [{"timestamp": 0, "weights": gold_standard}],
                    compliance_set_name,
                )
                self._pas_gold = pas_series[0]["pas"]
                self._reference = self._pas_gold
                self._logger.info(
                    "[%s] PAS_gold = %.6f", compliance_set_name, self._pas_gold
                )
            except (ValueError, KeyError, IndexError) as exc:
                self._logger.warning(
                    "Impossibile calcolare PAS_gold: %s - usando Frobenius.", exc
                )
                self._pas_gold = None
                self._reference = 0.0
        else:
            self._pas_gold = None
            self._reference = 0.0  # Frobenius_gold = 0 per costruzione

        # Reset stato CUSUM / EWMA
        self.reset_cusum()
        self._is_fitted = True
        self._logger.info(
            "[%s] fit() completato: %d snapshot nominali, "
            "%d feature, topology_type='%s'",
            compliance_set_name,
            len(nominal_snapshots),
            len(features),
            self._topology_type,
        )

    def monitor(
        self,
        compliance_set_name: str,
        features: dict[str, "pd.DataFrame"],
        weight_series: list[dict],
        timestamp: int,
    ) -> dict[str, Any]:
        """Esegue il monitoraggio gerarchico sulla finestra corrente.

        Parameters
        ----------
        compliance_set_name:
            Nome del compliance set.
        features:
            Feature correnti da FeatureSelector.select_features().
        weight_series:
            Pesi di transizione correnti da PBOBuilder.compute_transition_weights().
        timestamp:
            Timestamp della finestra corrente in µs.

        Returns
        -------
        dict
            MonitorResult con tutti i campi richiesti.

        Raises
        ------
        RuntimeError
            Se monitor() è chiamato prima di fit().
        KeyError
            Se compliance_set_name non esiste in topology.yaml.
        """
        if not self._is_fitted:
            raise RuntimeError(
                "monitor() chiamato prima di fit(). "
                "Chiamare fit() prima di monitorare."
            )
        if compliance_set_name not in self._topology["compliance_sets"]:
            raise KeyError(f"Compliance set non trovato: '{compliance_set_name}'")

        # Livello 1a - threshold SLA
        threshold_violations = self._check_threshold(
            compliance_set_name, features, timestamp
        )

        # Livello 1b - z-score
        zscore_violations = self._check_zscore(features, timestamp)

        base_signal = len(threshold_violations) > 0 or len(zscore_violations) > 0

        # Livello 2 - Isolation Forest (condizionale)
        if base_signal:
            if_signal = self._check_isolation_forest(features, timestamp)
        else:
            if_signal = False

        # Livello 3 - EWMA + CUSUM
        (
            cusum_signal,
            cusum_stat,
            ewma_value,
            frobenius_distance,
            pas_value,
        ) = self._update_ewma_cusum(weight_series, compliance_set_name)

        # Livello 4 - Validatore strutturale (condizionale)
        structural_confirmed = False
        if if_signal and cusum_signal:
            structural_confirmed = self._check_structural_validator(
                frobenius_distance, pas_value
            )

        self._logger.info(
            "[%s] ts=%d base=%s if=%s cusum=%s structural=%s",
            compliance_set_name,
            timestamp,
            base_signal,
            if_signal,
            cusum_signal,
            structural_confirmed,
        )

        return {
            "timestamp": timestamp,
            "compliance_set": compliance_set_name,
            "base_signal": base_signal,
            "if_signal": if_signal,
            "cusum_signal": cusum_signal,
            "structural_confirmed": structural_confirmed,
            "zscore_violations": zscore_violations,
            "threshold_violations": threshold_violations,
            "frobenius_distance": frobenius_distance,
            "pas_value": pas_value,
            "cusum_stat": cusum_stat,
            "ewma_value": ewma_value,
        }

    def reset_cusum(self) -> None:
        """Azzera l'accumulatore CUSUM e lo stato EWMA."""
        self._cusum_stat = 0.0
        self._ewma_state = None
        self._ewma_history.clear()

    # ------------------------------------------------------------------
    # Livello 1 - Threshold e Z-score
    # ------------------------------------------------------------------

    def _check_threshold(
        self,
        compliance_set_name: str,
        features: dict[str, "pd.DataFrame"],
        timestamp: int,
    ) -> list[str]:
        """Verifica violazioni delle soglie SLA statiche."""
        violations: list[str] = []
        cs = self._topology["compliance_sets"].get(compliance_set_name, {})
        sla: dict[str, Any] = cs.get("sla", {})
        if not sla:
            return violations

        for feature_key, df in features.items():
            metric_name = feature_key.split(":")[-1]
            if metric_name not in sla:
                continue
            sla_def = sla[metric_name]
            bound = sla_def.get("bound", "upper")
            threshold = sla_def.get("threshold")
            if threshold is None:
                continue

            val = self._get_current_value(df, timestamp)
            if val is None or (isinstance(val, float) and np.isnan(val)):
                continue

            if bound == "upper" and val > threshold:
                self._logger.warning(
                    "Threshold violation: %s = %.4f > %.4f (SLA upper)",
                    feature_key, val, threshold,
                )
                violations.append(feature_key)
            elif bound == "lower" and val < threshold:
                self._logger.warning(
                    "Threshold violation: %s = %.4f < %.4f (SLA lower)",
                    feature_key, val, threshold,
                )
                violations.append(feature_key)

        return violations

    def _check_zscore(
        self,
        features: dict[str, "pd.DataFrame"],
        timestamp: int,
    ) -> list[str]:
        """Verifica violazioni dello z-score adattivo."""
        violations: list[str] = []
        for feature_key, df in features.items():
            mean = self._training_means.get(feature_key)
            std = self._training_stds.get(feature_key)
            if mean is None or std is None or std == 0.0:
                continue

            val = self._get_current_value(df, timestamp)
            if val is None or (isinstance(val, float) and np.isnan(val)):
                continue

            z = abs((val - mean) / std)
            if z > self._zscore_threshold:
                violations.append(feature_key)

        return violations

    # ------------------------------------------------------------------
    # Livello 2 - Isolation Forest
    # ------------------------------------------------------------------

    def _check_isolation_forest(
        self,
        features: dict[str, "pd.DataFrame"],
        timestamp: int,
    ) -> bool:
        """Predice anomalia multivariata con Isolation Forest."""
        snap = self._features_to_snapshot(features, timestamp)
        x = self._build_node_vector(snap)

        # Imputa NaN con training mean
        nan_mask = np.isnan(x)
        if nan_mask.any():
            self._logger.warning(
                "IF: %d dimensioni NaN nel vettore corrente - imputazione con training mean.",
                int(nan_mask.sum()),
            )
            x = np.where(nan_mask, self._node_means, x)

        pred = self._iso_forest.predict(x.reshape(1, -1))[0]
        return bool(pred == -1)

    # ------------------------------------------------------------------
    # Livello 3 - EWMA + CUSUM
    # ------------------------------------------------------------------

    def _update_ewma_cusum(
        self,
        weight_series: list[dict],
        compliance_set_name: str,
    ) -> tuple[bool, float, float | None, float | None, float | None]:
        """Aggiorna EWMA e CUSUM; calcola PAS e Frobenius correnti."""
        pas_value: float | None = None
        frobenius_distance: float | None = None

        if self._topology_type == "linear" and self._pas_gold is not None:
            try:
                pas_series = self._pbo.compute_path_adherence(
                    weight_series, compliance_set_name
                )
                if pas_series:
                    pas_value = pas_series[-1]["pas"]
                    signal_raw = pas_value
                else:
                    signal_raw = self._reference
            except (ValueError, KeyError):
                signal_raw = self._reference

            # Frobenius anche per l'output (best effort)
            try:
                frob_series = self._pbo.compute_frobenius_distance(
                    weight_series, self._gold_standard
                )
                if frob_series:
                    frobenius_distance = frob_series[-1]["frobenius"]
            except Exception:
                pass

            # CUSUM: accumulare decrementi sotto reference
            ewma_new = self._apply_ewma(signal_raw)
            increment = max(0.0, self._reference - ewma_new - self._cusum_k)

        else:
            # Topologia parallela o PAS non disponibile: Frobenius
            try:
                frob_series = self._pbo.compute_frobenius_distance(
                    weight_series, self._gold_standard
                )
                if frob_series:
                    frobenius_distance = frob_series[-1]["frobenius"]
                    signal_raw = frobenius_distance
                else:
                    signal_raw = 0.0
            except Exception:
                signal_raw = 0.0

            # CUSUM: accumulare incrementi sopra reference (= 0)
            ewma_new = self._apply_ewma(signal_raw)
            increment = max(0.0, ewma_new - self._reference - self._cusum_k)

        self._cusum_stat = max(0.0, self._cusum_stat + increment)
        cusum_signal = self._cusum_stat > self._cusum_threshold

        if cusum_signal:
            self._logger.warning(
                "CUSUM superato: stat=%.4f > threshold=%.4f",
                self._cusum_stat,
                self._cusum_threshold,
            )

        return (
            cusum_signal,
            self._cusum_stat,
            self._ewma_state,
            frobenius_distance,
            pas_value,
        )

    def _apply_ewma(self, signal_raw: float) -> float:
        """Aggiorna lo stato EWMA e restituisce il valore corrente."""
        if self._ewma_state is None:
            self._ewma_state = signal_raw
        else:
            self._ewma_state = (
                self._ewma_alpha * signal_raw
                + (1.0 - self._ewma_alpha) * self._ewma_state
            )
        self._ewma_history.append(self._ewma_state)
        return self._ewma_state

    # ------------------------------------------------------------------
    # Livello 4 - Validatore strutturale
    # ------------------------------------------------------------------

    def _check_structural_validator(
        self,
        frobenius_distance: float | None,
        pas_value: float | None,
    ) -> bool:
        """Verifica derivata EWMA persistente e soglia distanza."""
        # Soglia distanza
        if frobenius_distance is not None:
            distance_ok = frobenius_distance > self._frobenius_threshold
        elif pas_value is not None and self._pas_gold is not None:
            distance_ok = pas_value < (self._pas_gold - self._frobenius_threshold)
        else:
            distance_ok = False

        if not distance_ok:
            return False

        # Derivata persistente: servono almeno consecutive_windows+1 valori
        if len(self._ewma_history) < self._consecutive_windows + 1:
            return False

        hist = list(self._ewma_history)
        diffs = [hist[i] - hist[i - 1] for i in range(1, len(hist))]
        last_diffs = diffs[-self._consecutive_windows:]

        if self._topology_type == "linear":
            # Degrado PAS = decremento → diffs negativi
            persistent = all(d < 0 for d in last_diffs)
        else:
            # Degrado Frobenius = incremento → diffs positivi
            persistent = all(d > 0 for d in last_diffs)

        return persistent

    # ------------------------------------------------------------------
    # Utilità
    # ------------------------------------------------------------------

    def _get_current_value(
        self, df: "pd.DataFrame", timestamp: int
    ) -> float | None:
        """Restituisce il valore al timestamp dato, o l'ultimo se assente."""
        import pandas as pd
        if len(df) == 0:
            return None
        if timestamp in df.index:
            return float(df.loc[timestamp, "value"])
        # Fallback: ultimo valore disponibile
        return float(df["value"].iloc[-1])

    def _build_node_vector(self, snap: dict) -> "np.ndarray":
        """Costruisce il vettore aggregato X_{H_Φi} da un snapshot."""
        row: list[float] = []
        for node_id, metric in self._node_feature_order:
            node_data = snap.get("nodes", {}).get(node_id)
            if node_data is None:
                row.append(float("nan"))
            else:
                val = node_data.get(metric)
                row.append(float("nan") if val is None else float(val))
        return np.array(row, dtype=float)

    def _features_to_snapshot(
        self,
        features: dict[str, "pd.DataFrame"],
        timestamp: int,
    ) -> dict:
        """Converte il dict di feature in formato snapshot per _build_node_vector."""
        import pandas as pd
        nodes: dict[str, dict[str, float]] = {}
        for key, df in features.items():
            parts = key.split(":", 2)
            if len(parts) != 3 or parts[0] != "node":
                continue
            node_id, metric = parts[1], parts[2]
            val = self._get_current_value(df, timestamp)
            nodes.setdefault(node_id, {})[metric] = (
                float("nan") if val is None else val
            )
        return {"timestamp": timestamp, "nodes": nodes, "edges": {}}
