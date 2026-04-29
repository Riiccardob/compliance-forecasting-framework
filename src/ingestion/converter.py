"""Conversione dei CSV raw GAMMA/DSB nei tre CSV interni del framework."""
import json
import re
from pathlib import Path

import pandas as pd

from src.utils.config_loader import ConfigLoader
from src.utils.logging_setup import LoggingSetup

# Pattern tollerante per i nomi file GAMMA:
# {fault_type}_{date}[_{duration}][_{token(s)}]_{rps}_{replica_idx}_graph_2.csv
_FILENAME_PATTERN = re.compile(
    r"^(?P<fault_type>cpu_mem|cpu|mem|net)"
    r"_(?P<date>[a-z]+\d+)"
    r"(?:_(?P<duration>\d+min))?"
    r"(?:_(?:repeat|rerun|test))*"
    r"_(?P<rps>\d+)"
    r"_(?P<replica_idx>\d+)"
    r"_graph_2\.csv$"
)


class DSBConverter:
    """Converte i CSV raw GAMMA (graph_2) nei tre CSV interni del framework.

    Ogni record raw rappresenta una singola traccia distribuita. Il converter
    aggrega le tracce per ``window_id``, calcola metriche differenziali sui
    counter Prometheus (CPU, rete) e produce tre DataFrame distinti:

    - **node_metrics**: stato interno per nodo per finestra
    - **edge_metrics**: qualità delle interazioni per arco per finestra
    - **ground_truth**: etichette di anomalia e metadati esperimento

    La mappatura indice → nome servizio e la lista degli archi sono lette
    da ``topology.yaml`` tramite ``ConfigLoader``. Nessuna costante è
    hardcoded nel codice Python.

    Strategia di scrittura in ``convert_all``: **sovrascrittura completa**.
    I file di destinazione vengono ricreati ad ogni esecuzione; l'append non
    è supportato per evitare duplicati da esecuzioni parziali o ripetute.
    """

    def __init__(self, config: ConfigLoader) -> None:
        """Inizializza il converter caricando la topologia.

        Parameters
        ----------
        config:
            Istanza già inizializzata di ``ConfigLoader``.
        """
        self._config = config
        self._logger = LoggingSetup.configure(__name__, "INFO")

        topology = config.load_topology()
        self._topology: dict = topology

        # Mappatura indice → nome servizio (ordine lista topology.yaml)
        self._node_map: dict[int, str] = {
            i: node["id"] for i, node in enumerate(topology["nodes"])
        }
        self._node_name_to_idx: dict[str, int] = {
            v: k for k, v in self._node_map.items()
        }
        self._n_nodes: int = len(topology["nodes"])

        # Lista archi; per ciascuno, indice del nodo destinazione usato
        # per recuperare la colonna {n}_latency dal CSV raw.
        self._edges: list[dict] = topology["edges"]
        self._edge_dest_idx: dict[str, int] = {
            edge["id"]: self._node_name_to_idx[edge["target"]]
            for edge in self._edges
        }

        self._data_paths: dict = topology["data_paths"]

    # ------------------------------------------------------------------
    # API pubblica
    # ------------------------------------------------------------------

    def convert_all(self, raw_dir: Path) -> None:
        """Processa tutti i ``*_graph_2.csv`` in ``raw_dir`` e scrive i CSV.

        Cerca ricorsivamente i file ``*_graph_2.csv``, li converte e
        sovrascrive i tre file di output definiti in ``data_paths`` del
        topology.yaml.

        Parameters
        ----------
        raw_dir:
            Directory radice contenente i CSV raw GAMMA.
        """
        files = sorted(raw_dir.rglob("*_graph_2.csv"))
        if not files:
            self._logger.warning("Nessun file *_graph_2.csv trovato in: %s", raw_dir)
            return

        node_frames: list[pd.DataFrame] = []
        edge_frames: list[pd.DataFrame] = []
        gt_frames: list[pd.DataFrame] = []

        for fp in files:
            self._logger.info("Elaborazione: %s", fp.name)
            n_df, e_df, g_df = self.convert_file(fp)
            node_frames.append(n_df)
            edge_frames.append(e_df)
            gt_frames.append(g_df)

        node_out = Path(self._data_paths["node_metrics_csv"])
        edge_out = Path(self._data_paths["edge_metrics_csv"])
        gt_out = Path(self._data_paths["ground_truth_csv"])

        for p in (node_out, edge_out, gt_out):
            p.parent.mkdir(parents=True, exist_ok=True)

        pd.concat(node_frames, ignore_index=True).to_csv(node_out, index=False)
        pd.concat(edge_frames, ignore_index=True).to_csv(edge_out, index=False)
        pd.concat(gt_frames, ignore_index=True).to_csv(gt_out, index=False)

        self._logger.info(
            "Conversione completata: %d file → %s, %s, %s",
            len(files),
            node_out,
            edge_out,
            gt_out,
        )

    def convert_file(
        self, filepath: Path
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Processa un singolo file senza scrivere su disco.

        Parameters
        ----------
        filepath:
            Path al file ``*_graph_2.csv`` da convertire.

        Returns
        -------
        tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]
            ``(node_df, edge_df, gt_df)`` nel formato interno del framework.
        """
        metadata = self._parse_filename(filepath.name)
        df = pd.read_csv(filepath)
        self._logger.debug(
            "File %s: %d righe, %d colonne",
            filepath.name,
            len(df),
            len(df.columns),
        )
        agg = self._aggregate_window_metrics(df)
        node_df = self._compute_node_metrics(agg, filepath.name)
        edge_df = self._compute_edge_metrics(agg, filepath.name)
        gt_df = self._compute_ground_truth(agg, metadata, filepath.name)
        return node_df, edge_df, gt_df

    # ------------------------------------------------------------------
    # Metodi privati
    # ------------------------------------------------------------------

    def _parse_filename(
        self, filename: str
    ) -> dict[str, str | int | None]:
        """Estrae metadati dal nome file GAMMA con regex tollerante.

        Gestisce: assenza del campo ``duration``, token extra come
        ``repeat``, ``rerun``, ``test`` tra duration e rps.

        Parameters
        ----------
        filename:
            Basename del file (es. ``cpu_aug9_25min_400_0_graph_2.csv``).

        Returns
        -------
        dict
            Chiavi: ``fault_type``, ``date``, ``duration`` (None se assente),
            ``rps`` (int), ``replica_idx`` (int). Tutti None se il pattern
            non viene riconosciuto.
        """
        m = _FILENAME_PATTERN.match(filename)
        if not m:
            self._logger.warning("Pattern filename non riconosciuto: %s", filename)
            return {
                "fault_type": None,
                "date": None,
                "duration": None,
                "rps": None,
                "replica_idx": None,
            }
        return {
            "fault_type": m.group("fault_type"),
            "date": m.group("date"),
            "duration": m.group("duration"),  # None se assente
            "rps": int(m.group("rps")),
            "replica_idx": int(m.group("replica_idx")),
        }

    def _aggregate_window_metrics(
        self, df: pd.DataFrame
    ) -> pd.DataFrame:
        """Aggrega le righe per ``window_id``.

        Aggregazioni applicate:

        - ``min(0_start)`` → ``timestamp`` (primo timestamp in µs)
        - ``first()`` dei counter Prometheus (costanti per finestra)
        - ``mean({n}_latency)`` per ogni nodo n (latenza media delle tracce)
        - ``count()`` delle righe → ``n_traces``
        - ``sum(label_trace)`` → ``n_anomalous_traces``
        - ``max({n}_label_RPC)`` → flag anomalia per nodo

        Parameters
        ----------
        df:
            DataFrame grezzo letto dal CSV raw.

        Returns
        -------
        pd.DataFrame
            Un record per ``window_id``, ordinato per ``timestamp``.
        """
        agg_dict: dict[str, str] = {"0_start": "min"}

        for n in range(self._n_nodes):
            for suffix in (
                "_container_cpu_usage_seconds_total",
                "_container_memory_usage_bytes",
                "_container_network_receive_bytes_total",
                "_container_network_transmit_bytes_total",
            ):
                col = f"{n}{suffix}"
                if col in df.columns:
                    agg_dict[col] = "first"
            lat_col = f"{n}_latency"
            if lat_col in df.columns:
                agg_dict[lat_col] = "mean"
            rpc_col = f"{n}_label_RPC"
            if rpc_col in df.columns:
                agg_dict[rpc_col] = "max"

        agg = df.groupby("window_id").agg(agg_dict).reset_index()
        agg = agg.rename(columns={"0_start": "timestamp"})

        # n_traces e n_anomalous_traces calcolati separatamente per chiarezza
        n_traces = (
            df.groupby("window_id")["label_trace"].count().rename("n_traces")
        )
        n_anom = (
            df.groupby("window_id")["label_trace"].sum().rename("n_anomalous_traces")
        )
        agg = agg.join(n_traces, on="window_id").join(n_anom, on="window_id")

        return agg.sort_values("timestamp").reset_index(drop=True)

    def _compute_node_metrics(
        self,
        agg: pd.DataFrame,
        source_file: str,
    ) -> pd.DataFrame:
        """Calcola ``cpu_percent``, ``mem_mb``, ``net_rx_mb``, ``net_tx_mb``.

        Usa ``diff()`` sui counter Prometheus aggregati per finestra; la
        prima finestra viene scartata (NaN prodotto da ``diff``). Gli zero
        nella memoria sono sostituiti con NaN e poi forward-filled per
        gestire gap di raccolta dati (container riavviato o metriche
        non ancora disponibili).

        Parameters
        ----------
        agg:
            DataFrame aggregato da ``_aggregate_window_metrics``.
        source_file:
            Nome del file sorgente (usato nel logging).

        Returns
        -------
        pd.DataFrame
            Formato long: ``timestamp``, ``window_id``, ``node_id``,
            ``cpu_percent``, ``mem_mb``, ``net_rx_mb``, ``net_tx_mb``,
            ``source_file``.
        """
        agg = agg.sort_values("timestamp").reset_index(drop=True)
        # Intervallo temporale in secondi tra finestre consecutive (µs → s)
        delta_t_sec: pd.Series = agg["timestamp"].diff() / 1_000_000.0

        records: list[dict] = []
        for n, node_name in self._node_map.items():
            cpu_col = f"{n}_container_cpu_usage_seconds_total"
            mem_col = f"{n}_container_memory_usage_bytes"
            rx_col = f"{n}_container_network_receive_bytes_total"
            tx_col = f"{n}_container_network_transmit_bytes_total"

            if cpu_col not in agg.columns:
                self._logger.warning(
                    "[%s] Colonna assente: %s - nodo %s saltato",
                    source_file,
                    cpu_col,
                    node_name,
                )
                continue

            cpu_pct: pd.Series = (agg[cpu_col].diff() / delta_t_sec) * 100.0

            mem_bytes: pd.Series = agg[mem_col].copy()
            mem_bytes = mem_bytes.replace(0.0, float("nan")).ffill().bfill()
            mem_mb: pd.Series = mem_bytes / (1024.0 * 1024.0)

            rx_mb: pd.Series = agg[rx_col].diff() / (1024.0 * 1024.0)
            rx_mb = rx_mb.mask(rx_mb < 0).ffill().fillna(0.0)
            tx_mb: pd.Series = agg[tx_col].diff() / (1024.0 * 1024.0)
            tx_mb = tx_mb.mask(tx_mb < 0).ffill().fillna(0.0)

            for i in range(len(agg)):
                if pd.isna(cpu_pct.iloc[i]):
                    continue  # prima finestra: diff NaN → scartata
                records.append(
                    {
                        "timestamp": agg.iloc[i]["timestamp"],
                        "window_id": agg.iloc[i]["window_id"],
                        "node_id": node_name,
                        "cpu_percent": cpu_pct.iloc[i],
                        "mem_mb": mem_mb.iloc[i],
                        "net_rx_mb": rx_mb.iloc[i],
                        "net_tx_mb": tx_mb.iloc[i],
                        "source_file": source_file,
                    }
                )

        self._logger.debug(
            "[%s] node_metrics: %d record", source_file, len(records)
        )
        return pd.DataFrame(records)

    def _compute_edge_metrics(
        self,
        agg: pd.DataFrame,
        source_file: str,
    ) -> pd.DataFrame:
        """Calcola ``latency_ms``, ``error_rate``, ``throughput_rps``.

        ``throughput_rps`` = ``n_traces`` / T_w dove T_w è l'intervallo
        verso la finestra successiva (``diff().shift(-1)``). Se delta_t
        è NaN o zero (caso single-window), si usa
        window_duration_seconds da topology.yaml (metadata.
        window_duration_seconds, default 30.0s).

        Parameters
        ----------
        agg:
            DataFrame aggregato da ``_aggregate_window_metrics``.
        source_file:
            Nome del file sorgente (usato nel logging).

        Returns
        -------
        pd.DataFrame
            Formato long: ``timestamp``, ``window_id``, ``edge_id``,
            ``source``, ``target``, ``latency_ms``, ``error_rate``,
            ``throughput_rps``, ``source_file``.
        """
        agg = agg.sort_values("timestamp").reset_index(drop=True)

        t_sec: pd.Series = agg["timestamp"] / 1_000_000.0
        # T_w[i] = t[i+1] - t[i]
        t_w: pd.Series = t_sec.diff().shift(-1)

        error_rate: pd.Series = agg["n_anomalous_traces"] / agg["n_traces"]
        fallback_duration = (
            self._topology.get("metadata", {}).get("window_duration_seconds")
        )
        if fallback_duration is None:
            fallback_duration = 30.0
            self._logger.warning(
                "[%s] 'window_duration_seconds' non definito in topology.yaml: "
                "uso fallback 30.0s",
                source_file,
            )

        records: list[dict] = []
        for edge in self._edges:
            dest_idx = self._edge_dest_idx[edge["id"]]
            lat_col = f"{dest_idx}_latency"

            if lat_col not in agg.columns:
                self._logger.warning(
                    "[%s] Colonna latenza assente: %s - arco %s saltato",
                    source_file,
                    lat_col,
                    edge["id"],
                )
                continue

            latency_ms: pd.Series = agg[lat_col] / 1000.0  # µs → ms

            for i in range(len(agg)):
                delta_t_seconds = t_w.iloc[i]
                if pd.isna(delta_t_seconds) or delta_t_seconds <= 0:
                    delta_t_seconds = fallback_duration

                records.append(
                    {
                        "timestamp": agg.iloc[i]["timestamp"],
                        "window_id": agg.iloc[i]["window_id"],
                        "edge_id": edge["id"],
                        "source": edge["source"],
                        "target": edge["target"],
                        "latency_ms": latency_ms.iloc[i],
                        "error_rate": error_rate.iloc[i],
                        "throughput_rps": agg.iloc[i]["n_traces"] / delta_t_seconds,
                        "source_file": source_file,
                    }
                )

        self._logger.debug(
            "[%s] edge_metrics: %d record", source_file, len(records)
        )
        return pd.DataFrame(records)

    def _compute_ground_truth(
        self,
        agg: pd.DataFrame,
        metadata: dict[str, str | int | None],
        source_file: str,
    ) -> pd.DataFrame:
        """Costruisce il ground truth per finestra.

        ``anomaly_node_ids`` è una stringa JSON contenente i nomi dei
        microservizi (non gli indici numerici) con ``max(label_RPC) == 1``
        per quella finestra.

        Parameters
        ----------
        agg:
            DataFrame aggregato da ``_aggregate_window_metrics``.
        metadata:
            Dizionario restituito da ``_parse_filename``.
        source_file:
            Nome del file sorgente.

        Returns
        -------
        pd.DataFrame
            Colonne: ``timestamp``, ``window_id``, ``fault_type``, ``date``,
            ``duration``, ``rps``, ``replica_idx``, ``label_trace``,
            ``anomaly_node_ids``, ``source_file``.
        """
        records: list[dict] = []
        for i in range(len(agg)):
            row = agg.iloc[i]

            anomaly_nodes: list[str] = [
                self._node_map[n]
                for n in range(self._n_nodes)
                if f"{n}_label_RPC" in agg.columns
                and row[f"{n}_label_RPC"] == 1
            ]

            label = int(row["n_anomalous_traces"] > 0)

            records.append(
                {
                    "timestamp": row["timestamp"],
                    "window_id": row["window_id"],
                    "fault_type": metadata["fault_type"],
                    "date": metadata["date"],
                    "duration": metadata["duration"],
                    "rps": metadata["rps"],
                    "replica_idx": metadata["replica_idx"],
                    "label_trace": label,
                    "anomaly_node_ids": json.dumps(anomaly_nodes),
                    "source_file": source_file,
                }
            )

        return pd.DataFrame(records)
