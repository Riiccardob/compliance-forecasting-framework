"""Fase IV — Generatore di alert strutturati con lead time e causa radice."""
from typing import Any

import numpy as np
import pandas as pd

from src.layer1.topology_builder import TopologyBuilder
from src.utils.config_loader import ConfigLoader
from src.utils.logging_setup import LoggingSetup

_METRIC_MAP: dict[str, str] = {
    "latency": "latency_ms",
    "reliability": "error_rate",
    "capacity": "throughput_rps",
}


class AlertGenerator:
    """Aggregazione di Fase I-III per la produzione di alert strutturati.

    Per ogni finestra produce zero o un alert. L'alert include:
    - proprietà a rischio, criticità (yellow/orange/red), lead time
    - causa radice da Fase II, segnali strutturali da Fase III
    - flag di incertezza del modello con eventuale declassamento criticità.
    """

    def __init__(
        self,
        config: ConfigLoader,
        topology_builder: TopologyBuilder,
    ) -> None:
        """Legge i parametri di configurazione e prepara la topologia.

        Parameters
        ----------
        config:
            ConfigLoader già inizializzato.
        topology_builder:
            TopologyBuilder già inizializzato.

        Raises
        ------
        ValueError
            Se manca una chiave obbligatoria in
            ``pipeline_params["alert_generation"]``.
        """
        self._logger = LoggingSetup.configure(__name__, "INFO")
        self._tb = topology_builder
        self._topology: dict[str, Any] = config.load_topology()

        pipeline = config.load_pipeline_params()
        ag = pipeline["alert_generation"]
        for key in ("yellow_min_days", "orange_min_days"):
            if key not in ag:
                raise ValueError(
                    f"Chiave obbligatoria mancante in "
                    f"pipeline_params['alert_generation']: '{key}'"
                )
        self._yellow_min_days: float = float(ag["yellow_min_days"])
        self._orange_min_days: float = float(ag["orange_min_days"])

        fc = pipeline["forecasting"]
        if "step_duration_hours" in fc:
            self._step_duration_hours: float = float(fc["step_duration_hours"])
        else:
            self._step_duration_hours = 24.0
            self._logger.warning(
                "forecasting.step_duration_hours non trovato in "
                "pipeline_params.yaml — uso default 24.0 ore per step."
            )

        self._divergence_threshold: float = float(
            fc.get("divergence_threshold", 0.2)
        )

        # Lookup (source, target) → edge_id per la query topologica
        self._edge_id_lookup: dict[tuple[str, str], str] = {
            (e["source"], e["target"]): e["id"]
            for e in self._topology["edges"]
        }

        self._logger.info(
            "AlertGenerator inizializzato: yellow_min_days=%.1f, "
            "orange_min_days=%.1f, step_duration_hours=%.1f",
            self._yellow_min_days,
            self._orange_min_days,
            self._step_duration_hours,
        )

    # ------------------------------------------------------------------
    # API pubblica
    # ------------------------------------------------------------------

    def generate(
        self,
        compliance_set_name: str,
        forecasts: dict[str, pd.DataFrame],
        causal_graph: dict[str, Any],
        monitor_result: dict[str, Any],
        timestamp: int,
    ) -> dict[str, Any] | None:
        """Genera un alert strutturato per la finestra corrente.

        Parameters
        ----------
        compliance_set_name:
            Nome del compliance set (es. ``"H_crit"``).
        forecasts:
            Output di ``StatForecaster.predict()``.
        causal_graph:
            Output di ``CausalAnalyzer.analyze()``.
        monitor_result:
            Output di ``StructuralMonitor.monitor()``.
        timestamp:
            Timestamp della finestra corrente in µs.

        Returns
        -------
        dict | None
            Alert strutturato se almeno una violazione SLA è prevista
            nell'orizzonte, altrimenti ``None``.

        Raises
        ------
        KeyError
            Se ``compliance_set_name`` non esiste in topology.yaml.
        """
        if compliance_set_name not in self._topology["compliance_sets"]:
            raise KeyError(
                f"Compliance set non trovato: '{compliance_set_name}'"
            )

        # 1. Proprietà monitorata e SLA
        # check_threshold/check_bound: soglia interna per violation check.
        # display_threshold/display_bound: valori originali del certificato SLA
        # (uguali a check per latency/capacity; convertiti per reliability).
        property_at_risk, check_threshold, check_bound, agg_func, \
            display_threshold, display_bound = (
                self._detect_property(compliance_set_name)
            )

        # 2. Aggregazione previsioni
        # NaN fallback = display_threshold (soglia metrica grezza, es. error_rate=0.05)
        aggregated = self._aggregate_forecasts(
            forecasts, compliance_set_name, agg_func,
            property_at_risk, display_threshold,
        )

        # 3. Lead time (confronto con soglia interna convertita)
        lead_time_steps = self._estimate_lead_time(
            aggregated, check_threshold, check_bound
        )

        # 4. Nessuna violazione prevista
        if lead_time_steps is None:
            self._logger.info(
                "[%s] Nessun alert generato nel ciclo corrente.",
                compliance_set_name,
            )
            return None

        # 5. Classificazione criticità
        criticality = self._classify_criticality(lead_time_steps, monitor_result)

        # 6. Causa radice
        root_cause, cross_interference, causal_chain, critical_arc = (
            self._extract_root_cause(
                causal_graph, property_at_risk, forecasts,
                compliance_set_name, lead_time_steps,
            )
        )

        # 7. Incertezza del modello
        uncertainty_flag = self._check_model_uncertainty(forecasts)

        # 8. Declassamento per incertezza
        if uncertainty_flag and criticality != "yellow":
            if criticality == "red":
                criticality = "orange"
            elif criticality == "orange":
                criticality = "yellow"

        # 9. Segnali strutturali
        structural_signals: dict[str, Any] = {
            "base_signal": monitor_result.get("base_signal", False),
            "if_signal": monitor_result.get("if_signal", False),
            "cusum_signal": monitor_result.get("cusum_signal", False),
            "structural_confirmed": monitor_result.get("structural_confirmed", False),
            "frobenius_distance": monitor_result.get("frobenius_distance"),
            "pas_value": monitor_result.get("pas_value"),
        }

        lead_time_hours = lead_time_steps * self._step_duration_hours

        alert: dict[str, Any] = {
            "timestamp": timestamp,
            "compliance_set": compliance_set_name,
            "property_at_risk": property_at_risk,
            "criticality": criticality,
            "lead_time_steps": lead_time_steps,
            "lead_time_hours": lead_time_hours,
            "aggregated_forecast": aggregated,
            "sla_threshold": display_threshold,
            "sla_bound": display_bound,
            "critical_arc": critical_arc,
            "root_cause": root_cause,
            "cross_property_interference": cross_interference,
            "causal_chain": causal_chain,
            "structural_signals": structural_signals,
            "model_uncertainty_flag": uncertainty_flag,
        }

        self._logger.info(
            "Alert generato: cs=%s, criticality=%s, lead_time_steps=%d, "
            "property=%s, root_cause=%s",
            compliance_set_name,
            criticality,
            lead_time_steps,
            property_at_risk,
            root_cause,
        )
        return alert

    # ------------------------------------------------------------------
    # Metodi privati
    # ------------------------------------------------------------------

    def _detect_property(
        self, compliance_set_name: str
    ) -> tuple[str, float, str, str, float, str]:
        """Determina proprietà, soglia SLA e funzione di aggregazione.

        Returns
        -------
        tuple
            (property_at_risk, check_threshold, check_bound,
             aggregation_function, display_threshold, display_bound)

            ``check_threshold/check_bound`` sono usati internamente per
            il violation check. ``display_threshold/display_bound`` sono
            i valori originali del certificato SLA, esposti nell'alert
            per leggibilità dell'operatore.

            Per la proprietà "reliability" i due set differiscono:
            la SLA error_rate (upper, ε_max) è convertita in reliability
            (lower, 1-ε_max) secondo Eq. 3.32 di methodology.tex, perché
            la product_complement produce un valore in [0,1] che deve
            essere confrontato con una soglia inferiore.

        Raises
        ------
        ValueError
            Se il compliance set non ha SLA definiti o non contiene
            metriche riconoscibili.
        """
        cs = self._topology["compliance_sets"][compliance_set_name]
        sla: dict[str, Any] = cs.get("sla", {})
        topology_type: str = cs.get("topology_type", "")

        if not sla:
            raise ValueError(
                f"Compliance set '{compliance_set_name}' non ha SLA definiti. "
                "Impossibile determinare la proprietà a rischio."
            )

        # Priorità: latency > reliability > capacity
        latency_key = next((k for k in sla if "latency" in k), None)
        if latency_key:
            threshold = float(sla[latency_key]["threshold"])
            bound = str(sla[latency_key]["bound"])
            agg = "sum" if topology_type == "linear" else "max"
            return "latency", threshold, bound, agg, threshold, bound

        error_key = next((k for k in sla if "error_rate" in k), None)
        if error_key:
            raw_threshold = float(sla[error_key]["threshold"])
            raw_bound = str(sla[error_key].get("bound", "upper"))
            # Eq. 3.32: error_rate ≤ ε_max (upper) ↔ reliability ≥ 1-ε_max (lower).
            # product_complement ∈ [0,1] → confronto con soglia inferiore.
            if raw_bound == "upper":
                check_threshold = 1.0 - raw_threshold
                check_bound = "lower"
            else:
                check_threshold = raw_threshold
                check_bound = raw_bound
            return (
                "reliability", check_threshold, check_bound,
                "product_complement", raw_threshold, raw_bound,
            )

        throughput_key = next((k for k in sla if "throughput" in k), None)
        if throughput_key:
            threshold = float(sla[throughput_key]["threshold"])
            bound = str(sla[throughput_key]["bound"])
            return "capacity", threshold, bound, "min", threshold, bound

        raise ValueError(
            f"SLA di '{compliance_set_name}' non contiene metriche "
            "riconoscibili (latency/error_rate/throughput)."
        )

    def _aggregate_forecasts(
        self,
        forecasts: dict[str, pd.DataFrame],
        compliance_set_name: str,
        aggregation_function: str,
        property_at_risk: str,
        sla_threshold: float,
    ) -> list[float]:
        """Aggrega le previsioni per la metrica rilevante.

        Seleziona le feature di arco in A(H_Φi) corrispondenti alla
        metrica della proprietà e aggrega per ogni step futuro.

        Returns
        -------
        list[float]
            Previsione aggregata per ogni step futuro.
        """
        metric_name = _METRIC_MAP[property_at_risk]
        edges_for_cs = self._tb.get_edges_for_compliance_set(compliance_set_name)
        relevant_keys = [
            f"edge:{self._edge_id_lookup[(src, tgt)]}:{metric_name}"
            for src, tgt in edges_for_cs
            if (src, tgt) in self._edge_id_lookup
            and f"edge:{self._edge_id_lookup[(src, tgt)]}:{metric_name}" in forecasts
        ]

        if not relevant_keys:
            self._logger.warning(
                "[%s] Nessuna feature rilevante (%s) in forecasts per l'aggregazione.",
                compliance_set_name,
                metric_name,
            )
            return []

        n_steps = min(len(forecasts[k]) for k in relevant_keys)
        result: list[float] = []

        for i in range(n_steps):
            values: list[float] = []
            for key in relevant_keys:
                df = forecasts[key]
                yhat = float(df.iloc[i]["yhat"])
                if np.isnan(yhat):
                    self._logger.warning(
                        "NaN in forecast '%s' step %d — "
                        "uso soglia SLA (%.4f) come fallback conservativo.",
                        key, i + 1, sla_threshold,
                    )
                    yhat = sla_threshold
                values.append(yhat)

            if not values:
                result.append(float("nan"))
                continue

            if aggregation_function == "sum":
                agg = float(sum(values))
            elif aggregation_function == "max":
                agg = float(max(values))
            elif aggregation_function == "min":
                agg = float(min(values))
            elif aggregation_function == "product_complement":
                agg = 1.0
                for v in values:
                    agg *= max(0.0, 1.0 - v)
                agg = float(agg)
            else:
                agg = float(sum(values))

            result.append(agg)

        return result

    def _estimate_lead_time(
        self,
        aggregated_forecast: list[float],
        sla_threshold: float,
        sla_bound: str,
    ) -> int | None:
        """Restituisce il primo step τ' con violazione SLA, o None.

        Parameters
        ----------
        aggregated_forecast:
            Lista di valori aggregati per step τ'=1..n.

        Returns
        -------
        int | None
            Step 1-based della prima violazione, o ``None`` se nessuna.
        """
        for i, value in enumerate(aggregated_forecast):
            if np.isnan(value):
                continue
            if sla_bound == "upper" and value > sla_threshold:
                return i + 1
            if sla_bound == "lower" and value < sla_threshold:
                return i + 1
        return None

    def _classify_criticality(
        self,
        lead_time_steps: int,
        monitor_result: dict[str, Any],
    ) -> str:
        """Classifica la criticità dell'alert secondo methodology.tex §3.2.4.

        RED se:
          - lead_time_days < orange_min_days, OPPURE
          - (cusum_signal AND structural_confirmed), OPPURE
          - (if_signal AND structural_confirmed)

        ORANGE se non RED e:
          - orange_min_days <= lead_time_days < yellow_min_days, OPPURE
          - cusum_signal, OPPURE
          - if_signal

        YELLOW altrimenti.
        """
        lead_time_days = lead_time_steps * self._step_duration_hours / 24.0

        cusum = bool(monitor_result.get("cusum_signal", False))
        if_sig = bool(monitor_result.get("if_signal", False))
        confirmed = bool(monitor_result.get("structural_confirmed", False))

        if (
            lead_time_days < self._orange_min_days
            or (cusum and confirmed)
            or (if_sig and confirmed)
        ):
            return "red"

        if (
            self._orange_min_days <= lead_time_days < self._yellow_min_days
            or cusum
            or if_sig
        ):
            return "orange"

        return "yellow"

    def _extract_root_cause(
        self,
        causal_graph: dict[str, Any],
        property_at_risk: str,
        forecasts: dict[str, pd.DataFrame],
        compliance_set_name: str,
        lead_time_steps: int,
    ) -> tuple[str | None, str | None, list[str], str | None]:
        """Estrae causa radice, interferenza cross-property e catena causale.

        Returns
        -------
        tuple
            (root_cause, cross_property_interference, causal_chain, critical_arc)
        """
        edges = causal_graph.get("edges", [])
        chains = causal_graph.get("cross_property_chains", [])
        metric_suffix = _METRIC_MAP.get(property_at_risk, "latency_ms")

        # Cerca prima gli edge il cui target termina con la metrica di interesse
        relevant_edges = [
            e for e in edges
            if str(e.get("target", "")).endswith(f":{metric_suffix}")
        ]
        candidate_edges = relevant_edges if relevant_edges else edges

        if candidate_edges:
            best = max(candidate_edges, key=lambda e: float(e.get("intensity", 0.0)))
            # Estrai solo l'edge_id dalla feature key (es. "edge:e4:latency_ms" → "e4")
            target_str = str(best.get("target", ""))
            target_parts = target_str.split(":")
            critical_arc: str | None = (
                target_parts[1]
                if len(target_parts) >= 2 and target_parts[0] == "edge"
                else (target_str or None)
            )
            root_cause: str | None = str(best.get("source"))
        else:
            # Fallback: arco con massimo yhat al lead_time_steps da forecast
            critical_arc = self._find_critical_arc_from_forecast(
                forecasts, compliance_set_name, property_at_risk, lead_time_steps
            )
            root_cause = None

        # Interferenza cross-property
        confirmed_chain = next(
            (c for c in chains if c.get("confirmed", False)), None
        )
        if confirmed_chain:
            cross_interference: str | None = str(confirmed_chain.get("source_cs"))
            causal_chain: list[str] = list(confirmed_chain.get("chain", []))
        else:
            cross_interference = None
            causal_chain = []

        return root_cause, cross_interference, causal_chain, critical_arc

    def _find_critical_arc_from_forecast(
        self,
        forecasts: dict[str, pd.DataFrame],
        compliance_set_name: str,
        property_at_risk: str,
        lead_time_steps: int,
    ) -> str | None:
        """Identifica l'arco critico dalla previsione al passo lead_time_steps."""
        metric_name = _METRIC_MAP.get(property_at_risk, "latency_ms")
        edges_for_cs = self._tb.get_edges_for_compliance_set(compliance_set_name)
        step_idx = lead_time_steps - 1

        best_eid: str | None = None
        best_val: float = float("-inf") if property_at_risk != "capacity" else float("inf")

        for src, tgt in edges_for_cs:
            eid = self._edge_id_lookup.get((src, tgt))
            if eid is None:
                continue
            key = f"edge:{eid}:{metric_name}"
            if key not in forecasts:
                continue
            df = forecasts[key]
            if step_idx >= len(df):
                continue
            val = float(df.iloc[step_idx]["yhat"])
            if np.isnan(val):
                continue
            if property_at_risk == "capacity":
                if val < best_val:
                    best_val, best_eid = val, eid
            else:
                if val > best_val:
                    best_val, best_eid = val, eid

        return best_eid

    def _check_model_uncertainty(
        self, forecasts: dict[str, pd.DataFrame]
    ) -> bool:
        """Ritorna True se almeno una feature ha divergenza > threshold.

        La divergenza è calcolata come MAD dalla baseline lineare,
        normalizzata per il range del segnale.
        """
        for key, df in forecasts.items():
            if len(df) < 2:
                continue
            yhats = df["yhat"].values.astype(float)
            valid = yhats[~np.isnan(yhats)]
            if len(valid) < 2:
                continue

            x = np.arange(len(valid), dtype=float)
            try:
                coeffs = np.polyfit(x, valid, 1)
            except (np.linalg.LinAlgError, ValueError):
                continue
            baseline = np.polyval(coeffs, x)
            mad = float(np.mean(np.abs(valid - baseline)))

            value_range = float(valid.max() - valid.min())
            if value_range > 0.0:
                normalized_div = mad / value_range
            elif abs(float(valid.mean())) > 0.0:
                normalized_div = mad / abs(float(valid.mean()))
            else:
                normalized_div = 0.0

            if normalized_div > self._divergence_threshold:
                return True

        return False
