"""Fase I — Mapping M: feature selection topologica per compliance set."""
import pandas as pd

from src.layer1.topology_builder import TopologyBuilder
from src.utils.config_loader import ConfigLoader
from src.utils.logging_setup import LoggingSetup


class FeatureSelector:
    """Implementa il Mapping M della Fase I: estrae M_direct ∪ M_interf.

    Dato un compliance set H_Φi e una sequenza di snapshot ATG, produce
    il dizionario di serie temporali usato come input per il forecasting.

    M_direct(H_Φi)
        Feature di nodo per ogni v ∈ H_Φi e feature di arco per ogni
        e ∈ A(H_Φi) = {e=(u,v) | u ∈ H_Φi AND v ∈ H_Φi}.

    M_interf(H_Φi, H_Φj)
        Solo throughput_rps degli archi e=(u,v) con v ∈ Shared(H_Φi, H_Φj)
        e u ∉ H_Φi.  Rappresenta il carico esterno sulle risorse condivise.
    """

    _INTERF_METRIC: str = "throughput_rps"

    def __init__(
        self,
        config: ConfigLoader,
        topology_builder: TopologyBuilder,
    ) -> None:
        """Inizializza il selettore dalla topologia.

        Parameters
        ----------
        config:
            ConfigLoader già inizializzato.
        topology_builder:
            TopologyBuilder già inizializzato e cachato.
        """
        self._tb = topology_builder
        self._logger = LoggingSetup.configure(__name__, "INFO")

        topology = config.load_topology()
        self._node_metrics: list[str] = topology["node_metrics"]
        self._edge_metrics: list[str] = topology["edge_metrics"]
        if self._INTERF_METRIC not in self._edge_metrics:
            self._logger.warning(
                "La metrica di interferenza '%s' non è in "
                "edge_metrics di topology.yaml. "
                "M_interf sarà sempre vuoto per tutti i compliance set.",
                self._INTERF_METRIC,
            )
            self._interf_available: bool = False
        else:
            self._interf_available = True
        self._all_cs_names: list[str] = list(
            topology["compliance_sets"].keys()
        )
        # Lookup (source, target) → edge_id per tradurre le tuple
        # restituite da TopologyBuilder nelle chiavi degli snapshot.
        self._edge_id_lookup: dict[tuple[str, str], str] = {
            (e["source"], e["target"]): e["id"]
            for e in topology["edges"]
        }

    # ------------------------------------------------------------------
    # API pubblica
    # ------------------------------------------------------------------

    def select_features(
        self,
        compliance_set_name: str,
        snapshots: list[dict],
    ) -> dict[str, pd.DataFrame]:
        """Estrae M_direct ∪ M_interf per il compliance set specificato.

        Parameters
        ----------
        compliance_set_name:
            Nome del compliance set (es. ``"H_crit"``).
        snapshots:
            Lista di snapshot ATG prodotti da ``ATGBuilder.build()``.

        Returns
        -------
        dict[str, pd.DataFrame]
            Chiavi nel formato:
            - ``"node:<node_id>:<metrica>"`` — feature di nodo (M_direct)
            - ``"edge:<edge_id>:<metrica>"`` — feature di arco (M_direct)
            - ``"interf:<edge_id>:throughput_rps"`` — interferenza (M_interf)

            Ogni valore è un DataFrame con indice ``timestamp`` (int µs)
            e colonna ``"value"``.

        Raises
        ------
        KeyError
            Se ``compliance_set_name`` non esiste in topology.yaml.
        """
        cs_nodes = self._tb.get_compliance_set_nodes(compliance_set_name)
        internal_edges = self._tb.get_edges_for_compliance_set(
            compliance_set_name
        )
        interf_edges = self._collect_interference_edges(compliance_set_name)

        result: dict[str, pd.DataFrame] = {}

        # M_direct — feature di nodo
        for node_id in sorted(cs_nodes):
            for metric in self._node_metrics:
                key = f"node:{node_id}:{metric}"
                result[key] = self._build_node_series(
                    node_id, metric, snapshots
                )

        # M_direct — feature di arco
        for src, tgt in internal_edges:
            edge_id = self._edge_id_lookup.get((src, tgt))
            if edge_id is None:
                continue
            for metric in self._edge_metrics:
                key = f"edge:{edge_id}:{metric}"
                result[key] = self._build_edge_series(
                    edge_id, metric, snapshots
                )

        # M_interf — solo throughput_rps
        for src, tgt in interf_edges:
            edge_id = self._edge_id_lookup.get((src, tgt))
            if edge_id is None:
                continue
            key = f"interf:{edge_id}:{self._INTERF_METRIC}"
            result[key] = self._build_edge_series(
                edge_id, self._INTERF_METRIC, snapshots
            )

        self._logger.debug(
            "[%s] select_features: %d serie estratte (%d node, %d edge, %d interf)",
            compliance_set_name,
            len(result),
            sum(1 for k in result if k.startswith("node:")),
            sum(1 for k in result if k.startswith("edge:")),
            sum(1 for k in result if k.startswith("interf:")),
        )
        return result

    def get_feature_names(
        self,
        compliance_set_name: str,
    ) -> dict[str, list[str]]:
        """Restituisce i nomi delle feature senza calcolare i valori.

        Parameters
        ----------
        compliance_set_name:
            Nome del compliance set.

        Returns
        -------
        dict[str, list[str]]
            ``{"direct": [...], "interference": [...]}``

        Raises
        ------
        KeyError
            Se ``compliance_set_name`` non esiste in topology.yaml.
        """
        cs_nodes = self._tb.get_compliance_set_nodes(compliance_set_name)
        internal_edges = self._tb.get_edges_for_compliance_set(
            compliance_set_name
        )
        interf_edges = self._collect_interference_edges(compliance_set_name)

        direct: list[str] = []
        for node_id in sorted(cs_nodes):
            for metric in self._node_metrics:
                direct.append(f"node:{node_id}:{metric}")
        for src, tgt in internal_edges:
            edge_id = self._edge_id_lookup.get((src, tgt))
            if edge_id is not None:
                for metric in self._edge_metrics:
                    direct.append(f"edge:{edge_id}:{metric}")

        interference: list[str] = [
            f"interf:{self._edge_id_lookup[(src, tgt)]}:{self._INTERF_METRIC}"
            for src, tgt in interf_edges
            if (src, tgt) in self._edge_id_lookup
        ]

        return {"direct": direct, "interference": interference}

    # ------------------------------------------------------------------
    # Metodi privati
    # ------------------------------------------------------------------

    def _collect_interference_edges(
        self, compliance_set_name: str
    ) -> list[tuple[str, str]]:
        """Raccoglie M_interf da tutti gli altri compliance set."""
        if not self._interf_available:
            return []
        seen: set[tuple[str, str]] = set()
        result: list[tuple[str, str]] = []
        for other in self._all_cs_names:
            if other == compliance_set_name:
                continue
            for edge in self._tb.get_interference_edges(
                compliance_set_name, other
            ):
                if edge not in seen:
                    seen.add(edge)
                    result.append(edge)
        return result

    def _build_node_series(
        self, node_id: str, metric: str, snapshots: list[dict]
    ) -> pd.DataFrame:
        """Costruisce la serie temporale di una metrica di nodo."""
        timestamps: list[int] = []
        values: list[float] = []
        for snap in snapshots:
            ts: int = snap["timestamp"]
            node_data = snap["nodes"].get(node_id)
            if node_data is None:
                self._logger.warning(
                    "Nodo '%s' assente nello snapshot ts=%d", node_id, ts
                )
                val = float("nan")
            else:
                raw = node_data.get(metric)
                val = float("nan") if raw is None else raw
            timestamps.append(ts)
            values.append(val)
        return pd.DataFrame(
            {"value": values},
            index=pd.Index(timestamps, name="timestamp"),
        )

    def _build_edge_series(
        self, edge_id: str, metric: str, snapshots: list[dict]
    ) -> pd.DataFrame:
        """Costruisce la serie temporale di una metrica di arco."""
        timestamps: list[int] = []
        values: list[float] = []
        for snap in snapshots:
            ts: int = snap["timestamp"]
            edge_data = snap["edges"].get(edge_id)
            if edge_data is None:
                self._logger.warning(
                    "Arco '%s' assente nello snapshot ts=%d", edge_id, ts
                )
                val = float("nan")
            else:
                raw = edge_data.get(metric)
                val = float("nan") if raw is None else raw
            timestamps.append(ts)
            values.append(val)
        return pd.DataFrame(
            {"value": values},
            index=pd.Index(timestamps, name="timestamp"),
        )
