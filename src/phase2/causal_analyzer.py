"""Fase II - Analisi causale guidata dalla topologia su M_Φi."""
import contextlib
import io
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import pearsonr
from statsmodels.tsa.stattools import adfuller, grangercausalitytests

from src.layer1.topology_builder import TopologyBuilder
from src.utils.config_loader import ConfigLoader
from src.utils.logging_setup import LoggingSetup

logger = LoggingSetup.configure(__name__, "INFO")


class CausalAnalyzer:
    """Esegue l'analisi causale su M_Φi tramite pipeline Pearson → Granger → TE.

    Produce un CausalGraph orientato con tipo (linear/nonlinear), intensità
    e metodo per ogni arco causale rilevato.

    La pipeline è:
    - Per coppie intra/node_arc: Pearson screening → Granger → TE fallback.
    - Per coppie inter/inter2 (cross-compliance-set): Granger diretto (bypass Pearson).

    Tutti i parametri statistici sono letti da
    ``pipeline_params.yaml["causal_analysis"]``.
    """

    def __init__(
        self,
        config: ConfigLoader,
        topology_builder: TopologyBuilder,
    ) -> None:
        """Inizializza il modulo e valida i parametri di configurazione.

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
            ``pipeline_params["causal_analysis"]``.
        """
        self._tb = topology_builder
        self._topology: dict[str, Any] = config.load_topology()

        ca = config.load_pipeline_params()["causal_analysis"]
        for key in (
            "pearson_threshold",
            "granger_max_lag",
            "granger_significance",
            "transfer_entropy_threshold",
        ):
            if key not in ca:
                raise ValueError(
                    f"Chiave '{key}' mancante in "
                    "pipeline_params['causal_analysis']. "
                    "Verifica config/pipeline_params.yaml."
                )

        self._pearson_threshold: float = float(ca["pearson_threshold"])
        self._granger_max_lag: int = int(ca["granger_max_lag"])
        self._granger_significance: float = float(ca["granger_significance"])
        self._te_threshold: float = float(ca["transfer_entropy_threshold"])
        self._n_bins: int = int(ca.get("n_bins", 10))

        # Pre-calculate edge lookups for topology queries
        self._edge_endpoints: dict[str, tuple[str, str]] = {
            e["id"]: (e["source"], e["target"])
            for e in self._topology["edges"]
        }
        self._edge_target: dict[str, str] = {
            e["id"]: e["target"] for e in self._topology["edges"]
        }
        self._edge_id_pair: dict[tuple[str, str], str] = {
            (e["source"], e["target"]): e["id"]
            for e in self._topology["edges"]
        }

        logger.info(
            "CausalAnalyzer inizializzato: pearson_threshold=%.2f, "
            "granger_max_lag=%d, granger_significance=%.3f, "
            "te_threshold=%.2f",
            self._pearson_threshold,
            self._granger_max_lag,
            self._granger_significance,
            self._te_threshold,
        )

    # ------------------------------------------------------------------
    # API pubblica
    # ------------------------------------------------------------------

    def analyze(
        self,
        compliance_set_name: str,
        features: dict[str, pd.DataFrame],
    ) -> dict[str, Any]:
        """Esegue la pipeline causale completa e restituisce il CausalGraph.

        Parameters
        ----------
        compliance_set_name:
            Nome del compliance set (es. ``"H_crit"``).
        features:
            Output di ``FeatureSelector.select_features()``.

        Returns
        -------
        dict
            CausalGraph con chiavi ``compliance_set``, ``edges``,
            ``cross_property_chains``.

        Raises
        ------
        KeyError
            Se ``compliance_set_name`` non esiste in topology.yaml.
        """
        if compliance_set_name not in self._topology["compliance_sets"]:
            raise KeyError(
                f"Compliance set non trovato: '{compliance_set_name}'"
            )

        candidates = self._build_candidate_pairs(
            compliance_set_name, list(features.keys())
        )
        logger.info(
            "[%s] Coppie candidate: %d",
            compliance_set_name,
            len(candidates),
        )

        edges: list[dict[str, Any]] = []

        for source_key, target_key, category in candidates:
            if source_key not in features or target_key not in features:
                continue
            try:
                s1, s2 = self._align_series(
                    features[source_key], features[target_key]
                )
                if len(s1) < 3:
                    logger.warning(
                        "Coppia (%s, %s) saltata: intersezione con meno "
                        "di 3 campioni validi.",
                        source_key,
                        target_key,
                    )
                    continue

                if category in ("inter", "inter2"):
                    edge = self._test_pair_no_pearson(
                        source_key, target_key, s1, s2
                    )
                else:
                    edge = self._test_pair_with_pearson(
                        source_key, target_key, s1, s2
                    )

                if edge is not None:
                    edges.append(edge)

            except Exception as exc:
                logger.warning(
                    "Coppia (%s, %s) saltata per errore imprevisto: %s",
                    source_key,
                    target_key,
                    exc,
                )

        cross_chains = self._check_cross_property(compliance_set_name, features)

        logger.info(
            "[%s] Link causali trovati: %d (cross-property chains: %d)",
            compliance_set_name,
            len(edges),
            len(cross_chains),
        )

        return {
            "compliance_set": compliance_set_name,
            "edges": edges,
            "cross_property_chains": cross_chains,
        }

    def get_causal_pairs(
        self,
        compliance_set_name: str,
        features: dict[str, pd.DataFrame],
    ) -> list[tuple[str, str, str]]:
        """Restituisce le coppie candidate prima dell'analisi statistica.

        Parameters
        ----------
        compliance_set_name:
            Nome del compliance set.
        features:
            Output di ``FeatureSelector.select_features()``.

        Returns
        -------
        list[tuple[str, str, str]]
            Lista di ``(source_key, target_key, category)`` dove
            ``category ∈ {"intra", "inter", "inter2", "node_arc"}``.
        """
        if compliance_set_name not in self._topology["compliance_sets"]:
            raise KeyError(
                f"Compliance set non trovato: '{compliance_set_name}'"
            )
        return self._build_candidate_pairs(
            compliance_set_name, list(features.keys())
        )

    # ------------------------------------------------------------------
    # Metodi privati - analisi statistica
    # ------------------------------------------------------------------

    def _align_series(
        self, df1: pd.DataFrame, df2: pd.DataFrame
    ) -> tuple[pd.Series, pd.Series]:
        """Allinea due feature DataFrame sull'intersezione dei timestamp."""
        common = df1.index.intersection(df2.index)
        common = common.sort_values()
        both = pd.DataFrame(
            {"s1": df1.loc[common, "value"], "s2": df2.loc[common, "value"]}
        ).dropna()
        return both["s1"], both["s2"]

    def _pearson_screen(
        self, s1: pd.Series, s2: pd.Series, threshold: float
    ) -> bool:
        """Ritorna True se |r_Pearson| > threshold.

        Ritorna False con warning se l'intersezione ha meno di 3 punti.
        """
        if len(s1) < 3:
            logger.warning(
                "Pearson screening: meno di 3 campioni comuni - coppia scartata."
            )
            return False
        import warnings as _warnings
        try:
            with _warnings.catch_warnings():
                _warnings.simplefilter("ignore")
                r, _ = pearsonr(s1.values, s2.values)
            if not np.isfinite(r):
                return False
            return bool(abs(r) > threshold)
        except Exception as exc:
            logger.warning("Pearson screening fallito: %s", exc)
            return False

    def _granger_test(
        self,
        cause: pd.Series,
        effect: pd.Series,
        max_lag: int,
        significance: float,
    ) -> dict[str, Any] | None:
        """Esegue il test di causalità di Granger con differenziazione ADF.

        Parameters
        ----------
        cause, effect:
            Serie allineate senza NaN.
        max_lag:
            Massimo lag da testare.
        significance:
            Soglia p-value per considerare positivo il test.

        Returns
        -------
        dict con ``intensity`` (ΔR²) e ``lag`` (lag ottimale),
        oppure ``None`` se il test non è positivo o i dati sono
        insufficienti.
        """
        if len(cause) < max_lag + 2:
            logger.warning(
                "Granger test: %d campioni < max_lag+2=%d - coppia saltata.",
                len(cause),
                max_lag + 2,
            )
            return None

        effect_vals, cause_vals, _ = self._make_stationary_pair(
            effect.values.astype(float),
            cause.values.astype(float),
        )

        if len(effect_vals) < max_lag + 2:
            return None

        data = np.column_stack([effect_vals, cause_vals])

        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                results = grangercausalitytests(data, maxlag=max_lag)
        except Exception as exc:
            logger.warning("grangercausalitytests fallito: %s", exc)
            return None

        best_lag: int = 1
        best_pval: float = float("inf")
        for lag, lag_res in results.items():
            try:
                pval = float(lag_res[0]["ssr_ftest"][1])
                if pval < best_pval:
                    best_pval = pval
                    best_lag = lag
            except (KeyError, IndexError, TypeError):
                continue

        if best_pval >= significance:
            return None

        try:
            ols_models = results[best_lag][1]
            r2_restr = float(ols_models[0].rsquared)
            r2_full  = float(ols_models[1].rsquared)
            delta_r2 = max(0.0, r2_full - r2_restr)
        except (IndexError, AttributeError, TypeError):
            delta_r2 = 0.0
            logger.warning(
                "Impossibile estrarre ΔR² per lag=%d - intensità impostata a 0.0.",
                best_lag,
            )

        return {"intensity": delta_r2, "lag": best_lag}

    def _transfer_entropy(
        self, cause: pd.Series, effect: pd.Series, n_bins: int
    ) -> float:
        """Calcola la Transfer Entropy normalizzata tramite discretizzazione.

        TE(X→Y) / H(Y), con valore in [0, 1]. Ritorna 0.0 se H(Y) == 0
        (serie costante) o dati insufficienti.
        """
        x = cause.values.astype(float)
        y = effect.values.astype(float)

        if len(x) < 2 or len(y) < 2:
            return 0.0

        def digitize_safe(arr: np.ndarray, nb: int) -> np.ndarray:
            arr_min, arr_max = arr.min(), arr.max()
            if arr_max == arr_min:
                return np.zeros(len(arr), dtype=int)
            bins = np.linspace(arr_min, arr_max, nb + 1)
            d = np.digitize(arr, bins[:-1]) - 1
            return np.clip(d, 0, nb - 1)

        x_d = digitize_safe(x[:-1], n_bins)
        y_curr = digitize_safe(y[1:], n_bins)
        y_lag = digitize_safe(y[:-1], n_bins)
        n = len(y_curr)

        p_joint = np.zeros((n_bins, n_bins, n_bins))
        np.add.at(p_joint, (y_curr, y_lag, x_d), 1.0)
        p_joint /= n

        p_yt_ytm1 = p_joint.sum(axis=2)
        p_ytm1_xtm1 = p_joint.sum(axis=0)
        p_ytm1 = p_ytm1_xtm1.sum(axis=1)

        with np.errstate(divide="ignore", invalid="ignore"):
            numer = p_joint * p_ytm1[np.newaxis, :, np.newaxis]
            denom = p_ytm1_xtm1[np.newaxis, :, :] * p_yt_ytm1[:, :, np.newaxis]
            ratio = np.where((denom > 0) & (numer > 0), numer / denom, 0.0)
            log_ratio = np.where(ratio > 0, np.log2(ratio), 0.0)
            te = float(np.nansum(p_joint * log_ratio))

        te = max(0.0, te)

        p_yt = p_yt_ytm1.sum(axis=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            h_y = float(
                -np.nansum(np.where(p_yt > 0, p_yt * np.log2(p_yt), 0.0))
            )

        if h_y <= 0.0:
            return 0.0

        return float(min(1.0, te / h_y))

    # ------------------------------------------------------------------
    # Metodi privati - costruzione coppie candidate
    # ------------------------------------------------------------------

    def _build_candidate_pairs(
        self,
        compliance_set_name: str,
        feature_keys: list[str],
    ) -> list[tuple[str, str, str]]:
        """Costruisce le coppie candidate nelle tre categorie.

        Ordine: node_arc e intra prima, inter dopo.
        Deduplicazione: nessuna coppia (A,B) e (B,A) entrambe.
        """
        node_keys = [k for k in feature_keys if k.startswith("node:")]
        edge_keys = [k for k in feature_keys if k.startswith("edge:")]
        interf_keys = [k for k in feature_keys if k.startswith("interf:")]

        pairs: list[tuple[str, str, str]] = []
        seen: set[frozenset[str]] = set()

        # Pre-calcola shared_nodes per usarlo sia in node_arc che in inter
        cs_names = list(self._topology["compliance_sets"].keys())
        shared_nodes: set[str] = set()
        for other in cs_names:
            if other == compliance_set_name:
                continue
            try:
                shared_nodes.update(
                    self._tb.get_shared_nodes(compliance_set_name, other)
                )
            except KeyError:
                continue

        # --- 1. node_arc: node:v → edge:e where v is source or target of e ---
        # Se v ∈ Shared(H_i, H_j), la coppia è "inter2" (seconda freccia
        # della catena cross-property: bypass Pearson come "inter").
        for nk in node_keys:
            parts = nk.split(":", 2)
            if len(parts) < 3:
                continue
            node_id = parts[1]
            for ek in edge_keys:
                eparts = ek.split(":", 2)
                if len(eparts) < 3:
                    continue
                edge_id = eparts[1]
                src, tgt = self._edge_endpoints.get(edge_id, (None, None))
                if node_id in (src, tgt):
                    fs = frozenset([nk, ek])
                    if fs not in seen:
                        seen.add(fs)
                        cat = "inter2" if node_id in shared_nodes else "node_arc"
                        pairs.append((nk, ek, cat))

        # --- 2. intra: all pairs among M_direct not in node_arc ---
        direct_keys = node_keys + edge_keys
        for i in range(len(direct_keys)):
            for j in range(i + 1, len(direct_keys)):
                ki, kj = direct_keys[i], direct_keys[j]
                fs = frozenset([ki, kj])
                if fs not in seen:
                    seen.add(fs)
                    pairs.append((ki, kj, "intra"))

        # --- 3. inter: interf features → shared node features ---
        for nk in node_keys:
            parts = nk.split(":", 2)
            if len(parts) < 3:
                continue
            node_id = parts[1]
            if node_id not in shared_nodes:
                continue
            for ik in interf_keys:
                fs = frozenset([nk, ik])
                if fs not in seen:
                    seen.add(fs)
                    pairs.append((ik, nk, "inter"))

        return pairs

    def _check_cross_property(
        self,
        compliance_set_name: str,
        features: dict[str, pd.DataFrame],
    ) -> list[dict[str, Any]]:
        """Verifica catene causali cross-property attraverso nodi condivisi.

        Per ogni nodo condiviso v e ogni altro compliance set j, testa:
          interf_edge → node:v:metric → internal_edge ∈ A(H_Φi)

        Returns
        -------
        list[dict]
            Lista di catene con chiavi ``source_cs``, ``target_cs``,
            ``chain``, ``confirmed``.
        """
        chains: list[dict[str, Any]] = []
        cs_names = list(self._topology["compliance_sets"].keys())
        edge_metrics = self._topology.get("edge_metrics", [])

        for other in cs_names:
            if other == compliance_set_name:
                continue
            try:
                shared_nodes = self._tb.get_shared_nodes(
                    compliance_set_name, other
                )
                cs_edges = self._tb.get_edges_for_compliance_set(
                    compliance_set_name
                )
            except KeyError:
                continue

            for v in shared_nodes:
                fa_candidates = [
                    k for k in features
                    if k.startswith("interf:")
                    and self._edge_target.get(k.split(":")[1]) == v
                ]
                v_node_keys = [
                    k for k in features if k.startswith(f"node:{v}:")
                ]
                fb_candidates = [
                    f"edge:{self._edge_id_pair[(src, tgt)]}:{m}"
                    for src, tgt in cs_edges
                    if v in (src, tgt)
                    and (src, tgt) in self._edge_id_pair
                    for m in edge_metrics
                    if f"edge:{self._edge_id_pair[(src, tgt)]}:{m}" in features
                ]

                for fa in fa_candidates:
                    for vk in v_node_keys:
                        for fb in fb_candidates:
                            if fa == vk or vk == fb or fa == fb:
                                continue
                            try:
                                sa, sv1 = self._align_series(
                                    features[fa], features[vk]
                                )
                                sv2, sb = self._align_series(
                                    features[vk], features[fb]
                                )
                                min_n = self._granger_max_lag + 2
                                interf_edge_id = fa.split(":")[1]
                                fb_edge_id = fb.split(":")[1]
                                if fb_edge_id == interf_edge_id:
                                    continue  # catena auto-referenziale: interf e internal arc
                                                # sono lo stesso arco, skip semantico
                                r1 = (
                                    self._granger_test(
                                        sa, sv1,
                                        self._granger_max_lag,
                                        self._granger_significance,
                                    )
                                    if len(sa) >= min_n
                                    else None
                                )
                                r2 = (
                                    self._granger_test(
                                        sv2, sb,
                                        self._granger_max_lag,
                                        self._granger_significance,
                                    )
                                    if len(sv2) >= min_n
                                    else None
                                )
                                chains.append({
                                    "source_cs": other,
                                    "target_cs": compliance_set_name,
                                    "chain": [fa, vk, fb],
                                    "confirmed": (r1 is not None and r2 is not None),
                                })
                            except Exception as exc:
                                logger.warning(
                                    "Cross-property chain skipped: %s", exc
                                )

        return chains

    # ------------------------------------------------------------------
    # Metodi privati - utilità
    # ------------------------------------------------------------------

    def _test_pair_with_pearson(
        self,
        source_key: str,
        target_key: str,
        s1: pd.Series,
        s2: pd.Series,
    ) -> dict[str, Any] | None:
        """Testa una coppia intra/node_arc con filtro Pearson preliminare."""
        if not self._pearson_screen(s1, s2, self._pearson_threshold):
            return None
        return self._run_granger_then_te(source_key, target_key, s1, s2)

    def _test_pair_no_pearson(
        self,
        source_key: str,
        target_key: str,
        s1: pd.Series,
        s2: pd.Series,
    ) -> dict[str, Any] | None:
        """Testa una coppia inter senza filtro Pearson."""
        return self._run_granger_then_te(source_key, target_key, s1, s2)

    def _run_granger_then_te(
        self,
        source_key: str,
        target_key: str,
        cause: pd.Series,
        effect: pd.Series,
    ) -> dict[str, Any] | None:
        """Esegue Granger; se negativo, fallback a Transfer Entropy."""
        granger_res = self._granger_test(
            cause, effect, self._granger_max_lag, self._granger_significance
        )
        if granger_res is not None:
            return {
                "source": source_key,
                "target": target_key,
                "type": "linear",
                "intensity": granger_res["intensity"],
                "method": "granger",
                "lag": granger_res["lag"],
            }

        te_val = self._transfer_entropy(cause, effect, self._n_bins)
        if te_val > self._te_threshold:
            return {
                "source": source_key,
                "target": target_key,
                "type": "nonlinear",
                "intensity": float(te_val),
                "method": "transfer_entropy",
                "lag": None,
            }

        return None

    def _make_stationary_pair(
        self,
        effect_vals: np.ndarray,
        cause_vals: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, int]:
        """Applica differenziazioni fino a stazionarietà ADF su
        entrambe le serie, usando il massimo tra i diff necessari."""
        def _diffs_needed(arr: np.ndarray) -> int:
            n = 0
            for _ in range(2):
                try:
                    _, p, *_ = adfuller(arr, autolag="AIC")
                except Exception:
                    break
                if p <= 0.05:
                    break
                arr = np.diff(arr)
                n += 1
            return n

        n_effect = _diffs_needed(effect_vals)
        n_cause  = _diffs_needed(cause_vals)
        n_diff   = max(n_effect, n_cause)

        for _ in range(n_diff):
            effect_vals = np.diff(effect_vals)
            cause_vals  = np.diff(cause_vals)

        if n_diff == 2:
            for arr, name in [(effect_vals, "effect"), (cause_vals, "cause")]:
                try:
                    _, p_final, *_ = adfuller(arr, autolag="AIC")
                    if p_final > 0.05:
                        logger.warning(
                            "Serie '%s' ancora non stazionaria "
                            "(p=%.3f) dopo 2 differenziazioni — "
                            "si procede comunque.",
                            name, p_final,
                        )
                except Exception:
                    logger.warning(
                        "Impossibile verificare stazionarietà di "
                        "'%s' dopo 2 differenziazioni.",
                        name,
                    )

        return effect_vals, cause_vals, n_diff
