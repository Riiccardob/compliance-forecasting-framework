"""Costruisce la sequenza di snapshot G_t = (V, E_t, X_V,t, X_E,t) del Layer 2."""
import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.utils.config_loader import ConfigLoader
from src.utils.logging_setup import LoggingSetup

logger = LoggingSetup.configure(__name__, "INFO")

_NODE_FEATURE_COLS: list[str] = ["cpu_percent", "mem_mb", "net_rx_mb", "net_tx_mb"]
_EDGE_FEATURE_COLS: list[str] = ["latency_ms", "error_rate", "throughput_rps"]


class ATGBuilder:
    """Carica i tre CSV canonici e costruisce la sequenza di snapshot ATG.

    Ogni snapshot G_t rappresenta lo stato del sistema distribuito in un
    istante temporale: feature di nodo (X_V,t) e feature di arco (X_E,t),
    annotate con label e metadati ground truth.

    La costruzione avviene per inner join sui timestamp comuni ai tre CSV.
    Se i timestamp unici di node_metrics e edge_metrics differiscono
    (atteso nel dataset DSB per la prima window scartata per nodo),
    viene emesso un warning e si procede con l'intersezione. Un ValueError
    viene sollevato solo se l'intersezione è vuota (mismatch totale).
    """

    def __init__(
        self,
        config: ConfigLoader,
        node_metrics_path: Path,
        edge_metrics_path: Path,
        ground_truth_path: Path,
    ) -> None:
        """Inizializza il builder con i path ai tre CSV canonici.

        Parameters
        ----------
        config:
            ConfigLoader già inizializzato.
        node_metrics_path:
            Path a ``node_metrics.csv`` nel formato canonico.
        edge_metrics_path:
            Path a ``edge_metrics.csv`` nel formato canonico.
        ground_truth_path:
            Path a ``ground_truth.csv`` nel formato canonico.
        """
        self._topology = config.load_topology()
        self._node_metrics_path = Path(node_metrics_path)
        self._edge_metrics_path = Path(edge_metrics_path)
        self._ground_truth_path = Path(ground_truth_path)

    def build(self) -> list[dict[str, Any]]:
        """Carica i tre CSV e restituisce la lista ordinata di snapshot temporali.

        Returns
        -------
        list[dict]
            Lista ordinata per timestamp crescente. Ogni snapshot ha le chiavi:
            ``timestamp``, ``nodes``, ``edges``, ``label``,
            ``anomaly_type``, ``anomaly_node_ids``.

        Raises
        ------
        ValueError
            Se l'intersezione dei timestamp tra node_metrics e edge_metrics
            è vuota (mismatch totale dei dati).
        """
        node_df = pd.read_csv(self._node_metrics_path)
        edge_df = pd.read_csv(self._edge_metrics_path)
        gt_df = pd.read_csv(self._ground_truth_path)

        n_gt_dup = int(gt_df.duplicated(subset=["timestamp"]).sum())
        if n_gt_dup > 0:
            logger.warning(
                "ground_truth contiene %d righe con timestamp duplicato "
                "(esperimenti distinti con timestamp µs coincidenti). "
                "Mantenuta la prima occorrenza per timestamp.",
                n_gt_dup,
            )
            gt_df = gt_df.drop_duplicates(subset=["timestamp"], keep="first")

        n_nm_dup = int(
            node_df.duplicated(subset=["timestamp", "node_id"]).sum()
        )
        if n_nm_dup > 0:
            logger.warning(
                "node_metrics contiene %d righe duplicate su "
                "(timestamp, node_id) — esperimenti distinti con "
                "timestamp µs coincidenti. Mantenuta la prima "
                "occorrenza per coppia.",
                n_nm_dup,
            )
            node_df = node_df.drop_duplicates(
                subset=["timestamp", "node_id"], keep="first"
            )

        n_em_dup = int(
            edge_df.duplicated(subset=["timestamp", "edge_id"]).sum()
        )
        if n_em_dup > 0:
            logger.warning(
                "edge_metrics contiene %d righe duplicate su "
                "(timestamp, edge_id) — esperimenti distinti con "
                "timestamp µs coincidenti. Mantenuta la prima "
                "occorrenza per coppia.",
                n_em_dup,
            )
            edge_df = edge_df.drop_duplicates(
                subset=["timestamp", "edge_id"], keep="first"
            )

        node_ts = set(node_df["timestamp"].unique())
        edge_ts = set(edge_df["timestamp"].unique())
        gt_ts = set(gt_df["timestamp"].unique())

        if len(node_ts) != len(edge_ts):
            logger.warning(
                "Timestamp unici differiscono: node_metrics=%d, edge_metrics=%d "
                "(atteso nel dataset DSB: prima window scartata per nodo).",
                len(node_ts),
                len(edge_ts),
            )

        # NaN check su feature di nodo
        available_cols = [c for c in _NODE_FEATURE_COLS if c in node_df.columns]
        nan_counts = node_df[available_cols].isna().sum()
        total_nan = int(nan_counts.sum())
        if total_nan > 0:
            logger.warning(
                "NaN residui in node_metrics (%d celle): %s",
                total_nan,
                nan_counts[nan_counts > 0].to_dict(),
            )

        common_ts = sorted(node_ts & edge_ts & gt_ts)
        if not common_ts:
            raise ValueError(
                f"Nessun timestamp comune tra node_metrics ({len(node_ts)} ts) "
                f"e edge_metrics ({len(edge_ts)} ts). "
                "Verificare la coerenza dei file di input."
            )

        logger.info(
            "Build ATG: %d snapshot allineati (node_ts=%d, edge_ts=%d, gt_ts=%d)",
            len(common_ts), len(node_ts), len(edge_ts), len(gt_ts),
        )

        node_grouped = node_df.groupby("timestamp")
        edge_grouped = edge_df.groupby("timestamp")
        gt_indexed = gt_df.set_index("timestamp")

        snapshots: list[dict[str, Any]] = []
        for ts in common_ts:
            nodes_dict = self._build_nodes(node_grouped.get_group(ts))
            edges_dict = self._build_edges(edge_grouped.get_group(ts))

            gt_row = gt_indexed.loc[ts]
            if isinstance(gt_row, pd.DataFrame):
                gt_row = gt_row.iloc[0]

            label = int(gt_row["label_trace"])
            if label == 1:
                anomaly_type: str | None = str(gt_row["fault_type"])
                anomaly_node_ids: list[str] = json.loads(str(gt_row["anomaly_node_ids"]))
            else:
                anomaly_type = None
                anomaly_node_ids = []

            snapshots.append({
                "timestamp": ts,
                "nodes": nodes_dict,
                "edges": edges_dict,
                "label": label,
                "anomaly_type": anomaly_type,
                "anomaly_node_ids": anomaly_node_ids,
            })

        return snapshots

    def get_node_feature_matrix(
        self, snapshots: list[dict[str, Any]], node_id: str
    ) -> pd.DataFrame:
        """Estrae la serie temporale delle feature del nodo specificato.

        Parameters
        ----------
        snapshots:
            Lista di snapshot prodotta da ``build()``.
        node_id:
            Identificatore del nodo (es. ``"nginx-web-server"``).

        Returns
        -------
        pd.DataFrame
            Index: timestamp. Colonne: cpu_percent, mem_mb, net_rx_mb, net_tx_mb.
        """
        records = [
            {"timestamp": s["timestamp"], **s["nodes"][node_id]}
            for s in snapshots
            if node_id in s["nodes"]
        ]
        df = pd.DataFrame(records)
        if df.empty:
            return df
        return df.set_index("timestamp")

    def get_edge_feature_matrix(
        self, snapshots: list[dict[str, Any]], edge_id: str
    ) -> pd.DataFrame:
        """Estrae la serie temporale delle feature dell'arco specificato.

        Parameters
        ----------
        snapshots:
            Lista di snapshot prodotta da ``build()``.
        edge_id:
            Identificatore dell'arco (es. ``"e1"``).

        Returns
        -------
        pd.DataFrame
            Index: timestamp. Colonne: latency_ms, error_rate, throughput_rps.
        """
        records = [
            {
                "timestamp": s["timestamp"],
                "latency_ms": s["edges"][edge_id]["latency_ms"],
                "error_rate": s["edges"][edge_id]["error_rate"],
                "throughput_rps": s["edges"][edge_id]["throughput_rps"],
            }
            for s in snapshots
            if edge_id in s["edges"]
        ]
        df = pd.DataFrame(records)
        if df.empty:
            return df
        return df.set_index("timestamp")

    @staticmethod
    def get_nominal_snapshots(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Restituisce i soli snapshot nominali (label == 0)."""
        return [s for s in snapshots if s["label"] == 0]

    @staticmethod
    def get_anomalous_snapshots(
        snapshots: list[dict[str, Any]], anomaly_type: str | None = None
    ) -> list[dict[str, Any]]:
        """Restituisce i soli snapshot anomali (label == 1).

        Parameters
        ----------
        snapshots:
            Lista di snapshot prodotta da ``build()``.
        anomaly_type:
            Se specificato, filtra per tipo di anomalia (es. ``"cpu_mem"``).
        """
        result = [s for s in snapshots if s["label"] == 1]
        if anomaly_type is not None:
            result = [s for s in result if s["anomaly_type"] == anomaly_type]
        return result

    @staticmethod
    def _build_nodes(rows: pd.DataFrame) -> dict[str, dict[str, float]]:
        return {
            row["node_id"]: {
                "cpu_percent": row["cpu_percent"],
                "mem_mb": row["mem_mb"],
                "net_rx_mb": row["net_rx_mb"],
                "net_tx_mb": row["net_tx_mb"],
            }
            for _, row in rows.iterrows()
        }

    @staticmethod
    def _build_edges(rows: pd.DataFrame) -> dict[str, dict[str, Any]]:
        return {
            row["edge_id"]: {
                "source": row["source"],
                "target": row["target"],
                "latency_ms": row["latency_ms"],
                "error_rate": row["error_rate"],
                "throughput_rps": row["throughput_rps"],
            }
            for _, row in rows.iterrows()
        }
