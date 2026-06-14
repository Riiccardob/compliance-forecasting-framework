"""Augmenta edge_metrics.csv con throughput per-arco reale da trace graph_1/graph_2."""

from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd

from src.utils.logging_setup import LoggingSetup

logger = LoggingSetup.configure(__name__, "INFO")

DATASET_RAW: Path = Path("DATASET/raw_dataset")
EDGE_CSV_IN: Path = Path("data/converted/edge_metrics.csv")
EDGE_CSV_OUT: Path = Path("data/converted/edge_metrics_aug.csv")
WINDOW_DUR_S: float = 5.0

# Mapping arco → quale contatore di trace usa
_EDGES_ALL: frozenset[str] = frozenset({"e1", "e2"})  # N1 + N2
_EDGES_N1: frozenset[str] = frozenset({"e3"})  # solo graph_1
_EDGES_N2: frozenset[str] = frozenset({"e4", "e5", "e6"})  # solo graph_2


class GammaPerArcConverter:
    """Aggiunge throughput per-arco reale a edge_metrics.csv.

    Legge ``home_rps_start_time_1.csv`` (graph_1) e
    ``home_rps_start_time_2.csv`` (graph_2) dalla cartella
    ``DATASET/raw_dataset/{exp}/processed_traces/`` di ciascun
    esperimento e calcola il throughput effettivo per arco usando
    ``np.searchsorted`` per efficienza O(n log n).

    Il file prodotto è identico a ``edge_metrics.csv`` tranne per la
    colonna ``throughput_rps``, che diventa differenziata per arco
    invece di essere uniforme per finestra.
    """

    def __init__(
        self,
        edge_csv_in: Path = EDGE_CSV_IN,
        edge_csv_out: Path = EDGE_CSV_OUT,
        dataset_raw: Path = DATASET_RAW,
        window_dur_s: float = WINDOW_DUR_S,
    ) -> None:
        """Inizializza il converter con i path e i parametri di finestra.

        Parameters
        ----------
        edge_csv_in:
            Path a ``edge_metrics.csv`` di input.
        edge_csv_out:
            Path a ``edge_metrics_aug.csv`` di output.
        dataset_raw:
            Radice di ``DATASET/raw_dataset``.
        window_dur_s:
            Durata nominale della finestra temporale in secondi.
        """
        self._edge_csv_in = Path(edge_csv_in)
        self._edge_csv_out = Path(edge_csv_out)
        self._dataset_raw = Path(dataset_raw)
        self._window_dur_s = window_dur_s
        self._window_dur_us = int(window_dur_s * 1_000_000)

    def convert(
        self,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> pd.DataFrame:
        """Produce ``edge_metrics_aug.csv`` con throughput per-arco reale.

        Parameters
        ----------
        progress_callback:
            Callable opzionale ``(i, n_total, source_file)`` invocato prima
            di elaborare ogni source_file. Utile per aggiornare una progress
            bar esterna.

        Returns
        -------
        pd.DataFrame
            DataFrame augmentato, già scritto su disco.
        """
        edge_df = pd.read_csv(self._edge_csv_in)
        source_files = edge_df["source_file"].unique()
        n_total = len(source_files)

        augmented_frames: list[pd.DataFrame] = []

        for i, sf in enumerate(source_files):
            if progress_callback is not None:
                progress_callback(i, n_total, sf)

            sf_df = edge_df[edge_df["source_file"] == sf].copy()
            exp_folder = sf.replace("_graph_2.csv", "")
            rps_dir = self._dataset_raw / exp_folder / "processed_traces"

            rps1_path = rps_dir / "home_rps_start_time_1.csv"
            rps2_path = rps_dir / "home_rps_start_time_2.csv"

            missing = [p.name for p in (rps1_path, rps2_path) if not p.exists()]
            if missing:
                logger.warning(
                    "[%s] File mancanti: %s - throughput uniforme mantenuto",
                    sf,
                    ", ".join(missing),
                )
                augmented_frames.append(sf_df)
                continue

            rps1_df = pd.read_csv(rps1_path, header=0)
            rps2_df = pd.read_csv(rps2_path, header=0)

            sf_df = self.compute_per_arc_throughput(sf_df, rps1_df, rps2_df)
            augmented_frames.append(sf_df)

        result = pd.concat(augmented_frames, ignore_index=True)
        self._edge_csv_out.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(self._edge_csv_out, index=False)
        logger.info("Scritto: %s (%d righe)", self._edge_csv_out, len(result))
        return result

    def compute_per_arc_throughput(
        self,
        edge_df: pd.DataFrame,
        rps1_df: pd.DataFrame,
        rps2_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """Calcola throughput per-arco per ogni finestra.

        Usa ``np.searchsorted`` sugli array di timestamp ordinati per
        contare N1 e N2 in O(n log n) anziché O(n²).

        Parameters
        ----------
        edge_df:
            Righe di un singolo source_file (tutti gli archi, tutte le
            finestre). Non è richiesto che siano ordinate.
        rps1_df:
            ``home_rps_start_time_1.csv``; colonna 0 = timestamp µs (graph_1).
        rps2_df:
            ``home_rps_start_time_2.csv``; colonna 0 = timestamp µs (graph_2).

        Returns
        -------
        pd.DataFrame
            Copia di ``edge_df`` con colonna ``throughput_rps`` aggiornata.
        """
        ts1 = np.sort(rps1_df.iloc[:, 0].values.astype(np.int64))
        ts2 = np.sort(rps2_df.iloc[:, 0].values.astype(np.int64))

        window_ts = np.sort(edge_df["timestamp"].unique().astype(np.int64))
        n_win = len(window_ts)

        w_starts = window_ts
        w_ends = np.empty(n_win, dtype=np.int64)
        if n_win > 1:
            w_ends[:-1] = window_ts[1:]
        w_ends[-1] = window_ts[-1] + self._window_dur_us

        n1_arr = np.searchsorted(ts1, w_ends, side="left") - np.searchsorted(
            ts1, w_starts, side="left"
        )
        n2_arr = np.searchsorted(ts2, w_ends, side="left") - np.searchsorted(
            ts2, w_starts, side="left"
        )

        ts_to_n1: dict[int, int] = dict(
            zip(window_ts.tolist(), n1_arr.tolist(), strict=True)
        )
        ts_to_n2: dict[int, int] = dict(
            zip(window_ts.tolist(), n2_arr.tolist(), strict=True)
        )

        result = edge_df.copy()
        ts_col = result["timestamp"].values.astype(np.int64)
        eid_col = result["edge_id"].values

        n1_vals = np.array([ts_to_n1[t] for t in ts_col], dtype=np.float64)
        n2_vals = np.array([ts_to_n2[t] for t in ts_col], dtype=np.float64)
        n_total = n1_vals + n2_vals

        is_all = np.isin(eid_col, list(_EDGES_ALL))
        is_n1 = np.isin(eid_col, list(_EDGES_N1))

        throughput = np.where(
            is_all,
            n_total / self._window_dur_s,
            np.where(
                is_n1,
                n1_vals / self._window_dur_s,
                n2_vals / self._window_dur_s,
            ),
        )

        result["throughput_rps"] = throughput
        return result
