"""Costruisce il Probabilistic Behavioral Overlay G_Behavior(t) = (V, E_all, W_t)."""
import math
from typing import Any

from src.utils.config_loader import ConfigLoader
from src.utils.logging_setup import LoggingSetup
from src.layer1.topology_builder import TopologyBuilder

logger = LoggingSetup.configure(__name__, "INFO")


class PBOBuilder:
    """Calcola la matrice stocastica W_t dei pesi di transizione del traffico.

    W_t è stocastica per righe limitatamente ai nodi non-terminali: la somma
    dei pesi uscenti da ogni nodo con archi attivi è pari a 1. I nodi
    terminali (sink) non compaiono nei risultati.

    Il gold standard W_gold è la media di W_t sulle finestre nominali
    (label == gold_standard_label da pipeline_params), usato come riferimento
    per la norma di Frobenius. W_gold è definito su E_all (tutti gli archi
    della topologia), non solo sugli archi presenti nel primo snapshot nominale.

    Il Path Adherence Score (PAS) è definito solo per compliance set con
    topology_type == "linear" (H_crit). Per topologie parallele (H_cache),
    il monitoraggio strutturale usa la norma di Frobenius come fallback.
    """

    def __init__(
        self,
        config: ConfigLoader,
        topology_builder: TopologyBuilder,
    ) -> None:
        """Inizializza il builder con configurazione e ipergrafo.

        Parameters
        ----------
        config:
            ConfigLoader già inizializzato.
        topology_builder:
            TopologyBuilder già inizializzato (usato per critical_path e
            topology_type).
        """
        self._topology = config.load_topology()
        self._topology_builder = topology_builder
        self._edges: list[dict] = self._topology["edges"]

        pipeline = config.load_pipeline_params()
        pbo_cfg = pipeline["pbo"]
        self._weight_metric: str = pbo_cfg["weight_metric"]
        self._gold_standard_label: int = int(pbo_cfg["gold_standard_label"])

        # Raggruppa archi per nodo sorgente — O(1) lookup in compute_transition_weights
        self._source_to_edges: dict[str, list[str]] = {}
        for edge in self._edges:
            self._source_to_edges.setdefault(edge["source"], []).append(edge["id"])

        # Lookup (source, target) → edge_id per il PAS
        self._edge_lookup: dict[tuple[str, str], str] = {
            (e["source"], e["target"]): e["id"] for e in self._edges
        }

        logger.info(
            "PBOBuilder inizializzato: %d archi, %d sorgenti con archi uscenti, "
            "weight_metric='%s', gold_standard_label=%d",
            len(self._edges),
            len(self._source_to_edges),
            self._weight_metric,
            self._gold_standard_label,
        )

    def compute_transition_weights(
        self, snapshots: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Calcola i pesi di transizione stocastici per ogni snapshot.

        Per ogni nodo u con archi uscenti:
            w(u→v, t) = weight_metric(u→v, t) / Σ_k weight_metric(u→k, t)

        La metrica usata è letta da pipeline_params["pbo"]["weight_metric"]
        (default: "throughput_rps"). Se il totale è zero si usano pesi uniformi
        1/n. I nodi terminali (sink) non compaiono nel risultato.

        Parameters
        ----------
        snapshots:
            Lista di snapshot prodotta da ATGBuilder.build().

        Returns
        -------
        list[dict]
            [{"timestamp": int, "weights": {"e1": float, ...}}, ...]
        """
        result: list[dict[str, Any]] = []
        for snap in snapshots:
            weights: dict[str, float] = {}
            for src, edge_ids in self._source_to_edges.items():
                available = [eid for eid in edge_ids if eid in snap["edges"]]
                if not available:
                    continue
                total_tp = sum(
                    snap["edges"][eid][self._weight_metric] for eid in available
                )
                if total_tp <= 0:
                    w_uniform = 1.0 / len(available)
                    for eid in available:
                        weights[eid] = w_uniform
                else:
                    for eid in available:
                        weights[eid] = snap["edges"][eid][self._weight_metric] / total_tp
            result.append({"timestamp": snap["timestamp"], "weights": weights})
        return result

    def compute_gold_standard(
        self,
        weight_series: list[dict[str, Any]],
        snapshots: list[dict[str, Any]],
    ) -> dict[str, float]:
        """Calcola W_gold come media dei pesi sulle finestre nominali.

        La label che identifica le finestre nominali è letta da
        pipeline_params["pbo"]["gold_standard_label"] (default: 0).

        W_gold è definito su E_all (tutti gli archi della topologia),
        non solo sugli archi presenti nel primo snapshot nominale.

        Parameters
        ----------
        weight_series:
            Output di compute_transition_weights.
        snapshots:
            Lista di snapshot (stessa lunghezza e ordine di weight_series).

        Returns
        -------
        dict[str, float]
            {"e1": float, "e2": float, ...} — un valore per ogni arco in E_all.

        Raises
        ------
        ValueError
            Se nessuno snapshot ha label == gold_standard_label.
        """
        ts_to_weights = {ws["timestamp"]: ws["weights"] for ws in weight_series}
        nominal_weights = [
            ts_to_weights[s["timestamp"]]
            for s in snapshots
            if s["label"] == self._gold_standard_label
            and s["timestamp"] in ts_to_weights
        ]
        if not nominal_weights:
            raise ValueError(
                f"Nessuno snapshot con label == {self._gold_standard_label} "
                "disponibile per calibrare W_gold."
            )
        all_eids = [e["id"] for e in self._edges]
        gold = {
            eid: sum(w.get(eid, 0.0) for w in nominal_weights) / len(nominal_weights)
            for eid in all_eids
        }
        logger.info("W_gold calibrato su %d snapshot nominali.", len(nominal_weights))
        return gold

    def compute_path_adherence(
        self,
        weight_series: list[dict[str, Any]],
        compliance_set_name: str,
    ) -> list[dict[str, Any]]:
        """Calcola PA(P_cert, t) = ∏ w(v_k → v_{k+1}, t) per il critical_path.

        Parameters
        ----------
        weight_series:
            Output di compute_transition_weights.
        compliance_set_name:
            Nome del compliance set (es. "H_crit").

        Returns
        -------
        list[dict]
            [{"timestamp": int, "pas": float}, ...]

        Raises
        ------
        ValueError
            Se topology_type != "linear" (PAS non applicabile).
        """
        cs = self._topology["compliance_sets"].get(compliance_set_name)
        if cs is None:
            raise KeyError(f"Compliance set non trovato: '{compliance_set_name}'")
        if cs.get("topology_type") != "linear":
            raise ValueError(
                f"PAS non applicabile per '{compliance_set_name}': "
                f"topology_type='{cs.get('topology_type')}'. "
                "Usa compute_frobenius_distance come fallback."
            )
        path = self._topology_builder.get_critical_path(compliance_set_name)
        if len(path) < 2:
            raise ValueError(
                f"Il critical path di '{compliance_set_name}' ha "
                f"{len(path)} nodi: PAS non calcolabile su un percorso "
                "privo di archi. Verificare la sequenza in topology.yaml."
            )
        path_edge_ids = [
            self._edge_lookup[(path[i], path[i + 1])]
            for i in range(len(path) - 1)
        ]
        result: list[dict[str, Any]] = []
        for entry in weight_series:
            weights = entry["weights"]
            pas = 1.0
            for eid in path_edge_ids:
                pas *= weights.get(eid, 0.0)
            result.append({"timestamp": entry["timestamp"], "pas": pas})
        return result

    def compute_frobenius_distance(
        self,
        weight_series: list[dict[str, Any]],
        gold_standard: dict[str, float],
    ) -> list[dict[str, Any]]:
        """Calcola ||W(t) − W_gold||_F per ogni timestamp.

        Itera su tutti gli archi della topologia (E_all). Archi non presenti
        in weights contribuiscono con peso 0.

        Parameters
        ----------
        weight_series:
            Output di compute_transition_weights.
        gold_standard:
            Output di compute_gold_standard.

        Returns
        -------
        list[dict]
            [{"timestamp": int, "frobenius": float}, ...]
        """
        all_eids = [e["id"] for e in self._edges]
        result: list[dict[str, Any]] = []
        for entry in weight_series:
            weights = entry["weights"]
            sq_sum = sum(
                (weights.get(eid, 0.0) - gold_standard.get(eid, 0.0)) ** 2
                for eid in all_eids
            )
            result.append({
                "timestamp": entry["timestamp"],
                "frobenius": math.sqrt(sq_sum),
            })
        return result
