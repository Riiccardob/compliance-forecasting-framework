"""Costruisce l'ipergrafo di certificazione H_cert usando Annotazione Semantica."""
from typing import Any

import networkx as nx

from src.utils.config_loader import ConfigLoader
from src.utils.logging_setup import LoggingSetup

logger = LoggingSetup.configure(__name__, "INFO")


class TopologyBuilder:
    """Costruisce H_cert dal topology.yaml e fornisce le query semantiche.

    Usa la Strategia di Annotazione Semantica: la topologia del grafo
    è invariata rispetto al service dependency graph reale; la semantica
    dei compliance set è codificata come attributo ``hyperedges`` su ogni
    arco, calcolato al momento della costruzione.
    """

    def __init__(self, config: ConfigLoader) -> None:
        """Carica la topologia tramite ConfigLoader.

        Parameters
        ----------
        config:
            Istanza già inizializzata di ConfigLoader.
        """
        self._topology: dict[str, Any] = config.load_topology()
        self._compliance_sets: dict[str, Any] = self._topology["compliance_sets"]
        self._graph: nx.DiGraph | None = None

        # Precalcola i set di nodi per ogni compliance set per O(1) lookup
        self._cs_node_sets: dict[str, set[str]] = {
            name: set(cs["nodes"])
            for name, cs in self._compliance_sets.items()
        }
        logger.info(
            "TopologyBuilder inizializzato: %d nodi, %d archi, %d compliance set",
            len(self._topology["nodes"]),
            len(self._topology["edges"]),
            len(self._compliance_sets),
        )

    def build(self) -> nx.DiGraph:
        """Costruisce il grafo orientato H_cert con annotazione semantica.

        Ogni arco riceve l'attributo ``hyperedges``: lista dei nomi di
        compliance set a cui appartiene, seguendo la definizione formale
        A(H_Φi) = {e=(u,v) | u ∈ H_Φi AND v ∈ H_Φi}.

        Returns
        -------
        nx.DiGraph
            Grafo orientato con 7 nodi e 6 archi annotati.
        """
        if self._graph is not None:
            return self._graph

        g = nx.DiGraph()

        for node in self._topology["nodes"]:
            g.add_node(node["id"])

        for edge in self._topology["edges"]:
            u, v = edge["source"], edge["target"]
            hyperedges = [
                name
                for name, node_set in self._cs_node_sets.items()
                if u in node_set and v in node_set
            ]
            g.add_edge(u, v, hyperedges=hyperedges)
            logger.debug("Arco %s → %s annotato con: %s", u, v, hyperedges)

        self._graph = g
        logger.info("Grafo H_cert costruito: %d nodi, %d archi", g.number_of_nodes(), g.number_of_edges())
        return g

    def get_compliance_set_nodes(self, name: str) -> set[str]:
        """Restituisce l'insieme dei nodi del compliance set.

        Parameters
        ----------
        name:
            Nome del compliance set (es. ``"H_crit"``).

        Returns
        -------
        set[str]
            Insieme degli identificatori di nodo.

        Raises
        ------
        KeyError
            Se il compliance set non esiste in topology.yaml.
        """
        if name not in self._cs_node_sets:
            raise KeyError(f"Compliance set non trovato: '{name}'")
        return set(self._cs_node_sets[name])

    def get_critical_path(self, name: str) -> list[str]:
        """Restituisce la sequenza del percorso critico certificato.

        Parameters
        ----------
        name:
            Nome del compliance set.

        Returns
        -------
        list[str]
            Sequenza ordinata di nodi del percorso critico, oppure lista
            vuota se il compliance set ha topologia parallela (nessun
            ``critical_path`` definito in topology.yaml).

        Raises
        ------
        KeyError
            Se il compliance set non esiste in topology.yaml.
        """
        if name not in self._compliance_sets:
            raise KeyError(f"Compliance set non trovato: '{name}'")
        cs = self._compliance_sets[name]
        return list(cs.get("critical_path", {}).get("sequence", []))

    def get_shared_nodes(self, h_i: str, h_j: str) -> set[str]:
        """Implementa Shared(H_Φi, H_Φj) = H_Φi ∩ H_Φj.

        Parameters
        ----------
        h_i:
            Nome del primo compliance set.
        h_j:
            Nome del secondo compliance set.

        Returns
        -------
        set[str]
            Insieme dei nodi condivisi tra i due compliance set.
        """
        if h_i not in self._cs_node_sets:
            raise KeyError(f"Compliance set non trovato: '{h_i}'")
        if h_j not in self._cs_node_sets:
            raise KeyError(f"Compliance set non trovato: '{h_j}'")
        return self._cs_node_sets[h_i] & self._cs_node_sets[h_j]

    def get_edges_for_compliance_set(self, name: str) -> list[tuple[str, str]]:
        """Implementa A(H_Φi) = {e=(u,v) | u ∈ H_Φi AND v ∈ H_Φi}.

        Parameters
        ----------
        name:
            Nome del compliance set.

        Returns
        -------
        list[tuple[str, str]]
            Lista di archi (source, target) interni al compliance set.
        """
        if name not in self._cs_node_sets:
            raise KeyError(f"Compliance set non trovato: '{name}'")
        node_set = self._cs_node_sets[name]
        return [
            (e["source"], e["target"])
            for e in self._topology["edges"]
            if e["source"] in node_set and e["target"] in node_set
        ]

    def get_interference_edges(
        self, target_cs: str, other_cs: str
    ) -> list[tuple[str, str]]:
        """Implementa M_interf: archi e=(u,v) con v ∈ Shared e u ∉ target_cs.

        Individua gli archi che convogliano traffico da nodi esterni a
        ``target_cs`` verso nodi condivisi con ``other_cs``. Questi archi
        portano traffico che può saturare risorse condivise e impattare
        ``target_cs`` senza che la sorgente ne faccia parte.

        Parameters
        ----------
        target_cs:
            Compliance set per cui cercare interferenze.
        other_cs:
            Altro compliance set che condivide nodi con ``target_cs``.

        Returns
        -------
        list[tuple[str, str]]
            Lista di archi di interferenza. Lista vuota se M_interf = ∅.
        """
        shared = self.get_shared_nodes(target_cs, other_cs)
        target_nodes = self._cs_node_sets[target_cs]
        return [
            (e["source"], e["target"])
            for e in self._topology["edges"]
            if e["target"] in shared and e["source"] not in target_nodes
        ]
