"""Caricamento e validazione dei file di configurazione del framework"""

import copy
from pathlib import Path

import yaml

from src.utils.logging_setup import LoggingSetup

logger = LoggingSetup.configure(__name__, "INFO")

_TOPOLOGY_REQUIRED_KEYS = (
    "metadata",
    "nodes",
    "edges",
    "compliance_sets",
    "node_metrics",
    "edge_metrics",
    "data_paths",
)

_PIPELINE_REQUIRED_KEYS = (
    "version",
    "pbo",
    "forecasting",
    "causal_analysis",
    "anomaly_detection",
    "alert_generation",
)


class ConfigLoader:
    """Carica e valida topology.yaml e pipeline_params.yaml

    Entrambi i file vengono letti in modo lazy
        --> prima chiamata del metodo corrispondente
    La validazione è eager
        --> alla prima chiamata si verifica la presenza di tutte le chiavi obbligatorie.
    """

    def __init__(self, topology_path: Path, pipeline_path: Path) -> None:
        """Inizializza il loader con i path ai due file di configurazione.

        Parameters
        ----------
        topology_path:
            Path al file topology.yaml.
        pipeline_path:
            Path al file pipeline_params.yaml.
        """
        self._topology_path = Path(topology_path)
        self._pipeline_path = Path(pipeline_path)
        self._topology: dict | None = None
        self._pipeline: dict | None = None

    def load_topology(self) -> dict:
        """Carica e valida topology.yaml.

        Returns
        -------
        dict
            Contenuto del file YAML come dizionario.

        Raises
        ------
        FileNotFoundError
            Se il file non esiste; il messaggio include il path completo.
        ValueError
            Se manca una chiave obbligatoria; il messaggio include il nome
            della prima chiave mancante trovata.
        """
        if self._topology is None:
            data = self._load_and_validate(self._topology_path, _TOPOLOGY_REQUIRED_KEYS)
            metadata = data.get("metadata", {})
            wds = metadata.get("window_duration_seconds")
            if wds is None:
                raise ValueError(
                    f"{self._topology_path.name}: chiave mancante 'metadata."
                    "window_duration_seconds'. "
                    "Richiesta da DSBConverter come fallback per delta_t."
                )
            if not isinstance(wds, (int, float)) or float(wds) <= 0:
                raise ValueError(
                    f"{self._topology_path.name}: metadata.window_duration_seconds = "
                    f"{wds!r} non è un numero positivo."
                )
            self._topology = data
            logger.info("topology.yaml caricato da: %s", self._topology_path)
        return copy.deepcopy(self._topology)

    def load_pipeline_params(self) -> dict:
        """Carica e valida pipeline_params.yaml.

        Returns
        -------
        dict
            Contenuto del file YAML come dizionario.

        Raises
        ------
        FileNotFoundError
            Se il file non esiste; il messaggio include il path completo.
        ValueError
            Se manca una chiave obbligatoria; il messaggio include il nome
            della prima chiave mancante trovata.
        """
        if self._pipeline is None:
            self._pipeline = self._load_and_validate(
                self._pipeline_path, _PIPELINE_REQUIRED_KEYS
            )
            logger.info("pipeline_params.yaml caricato da: %s", self._pipeline_path)
        return copy.deepcopy(self._pipeline)

    @staticmethod
    def _load_and_validate(path: Path, required_keys: tuple[str, ...]) -> dict:
        """Legge un file YAML e verifica la presenza delle chiavi obbligatorie.

        Parameters
        ----------
        path:
            Path al file YAML da leggere.
        required_keys:
            Chiavi obbligatorie al livello radice del dizionario.

        Raises
        ------
        FileNotFoundError
            Se il file non esiste.
        ValueError
            Se manca almeno una chiave obbligatoria.
        """
        if not path.exists():
            raise FileNotFoundError(
                f"File di configurazione non trovato: {path.resolve()}"
            )

        try:
            with path.open(encoding="utf-8") as fh:
                data: dict = yaml.safe_load(fh)
        except yaml.YAMLError as exc:
            raise ValueError(
                f"{path.name} contiene YAML sintaticamente non valido: {exc}"
            ) from exc

        if not isinstance(data, dict):
            raise ValueError(
                f"{path.name} non contiene un mapping YAML valido "
                f"(ottenuto: {type(data).__name__})"
            )

        for key in required_keys:
            if key not in data:
                raise ValueError(
                    f"Chiave obbligatoria mancante in {path.name}: '{key}'"
                )

        return data
