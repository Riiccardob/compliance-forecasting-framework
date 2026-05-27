"""Inietta una rampa lineare di latenza nelle ultime N finestre nominali di ogni esperimento."""
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from src.utils.logging_setup import LoggingSetup

logger = LoggingSetup.configure(__name__, "INFO")

EDGE_AUG_IN: Path = Path("data/converted/edge_metrics_aug.csv")
GT_CSV: Path = Path("data/converted/ground_truth.csv")
EDGE_AUG_OUT: Path = Path("data/converted/edge_metrics_aug_ramp.csv")

EXCLUDE_PREFIX: str = "cpu_aug12_25min_200_"

# Calibrati su dati GAMMA: min tra i due compliance set per mantenere
# entrambi sotto SLA al termine della rampa.
SLA_H_CRIT_MS: float = 284.4
SLA_H_CACHE_MS: float = 45.0
RAMP_SCALE_FACTOR: float = 3.82

# Archi per compliance set (source e target entrambi nel set)
H_CRIT_EDGES: frozenset[str] = frozenset({"e1", "e2", "e4", "e6"})
H_CACHE_EDGES: frozenset[str] = frozenset({"e3", "e4", "e5"})


def compute_n_ramp(n_nominal_windows: int) -> int:
    """Restituisce il numero di finestre nominali da rampare.

    Parameters
    ----------
    n_nominal_windows:
        Numero totale di finestre nominali per l'esperimento.

    Returns
    -------
    int
        Valore in [5, 30].
    """
    return max(5, min(30, n_nominal_windows // 3))


class GammaRampInjector:
    """Inietta una rampa lineare di latenza nelle ultime N finestre nominali.

    Solo la colonna ``latency_ms`` viene modificata. La colonna
    ``throughput_rps`` rimane invariata (già augmentata da GammaPerArcConverter).

    Le finestre anomale (``label_trace == 1``) non vengono mai toccate.
    Gli esperimenti con prefisso ``EXCLUDE_PREFIX`` o con meno di 10 finestre
    nominali vengono copiati invariati.
    """

    def __init__(
        self,
        edge_aug_in: Path = EDGE_AUG_IN,
        gt_csv: Path = GT_CSV,
        edge_aug_out: Path = EDGE_AUG_OUT,
        ramp_scale_factor: float = RAMP_SCALE_FACTOR,
        exclude_prefix: str = EXCLUDE_PREFIX,
        min_nominal_windows: int = 10,
    ) -> None:
        """Inizializza il ramp injector.

        Parameters
        ----------
        edge_aug_in:
            Path a ``edge_metrics_aug.csv`` (output di GammaPerArcConverter).
        gt_csv:
            Path a ``ground_truth.csv`` per i label ``label_trace``.
        edge_aug_out:
            Path di output ``edge_metrics_aug_ramp.csv``.
        ramp_scale_factor:
            Fattore di scaling al termine della rampa (ultima finestra).
        exclude_prefix:
            Prefisso dei source_file da escludere dall'augmentation.
        min_nominal_windows:
            Soglia minima di finestre nominali per applicare la rampa.
        """
        self._edge_aug_in = Path(edge_aug_in)
        self._gt_csv = Path(gt_csv)
        self._edge_aug_out = Path(edge_aug_out)
        self._ramp_scale = ramp_scale_factor
        self._exclude_prefix = exclude_prefix
        self._min_nominal = min_nominal_windows

        # Statistiche popolate da inject()
        self.n_excluded: int = 0
        self.n_ramped: int = 0
        self.n_skipped: int = 0

    def inject(
        self,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> pd.DataFrame:
        """Produce ``edge_metrics_aug_ramp.csv`` con la rampa iniettata.

        Parameters
        ----------
        progress_callback:
            Callable opzionale ``(i, n_total, source_file)`` invocato prima
            di elaborare ogni source_file.

        Returns
        -------
        pd.DataFrame
            DataFrame risultante, già scritto su disco.
        """
        edges = pd.read_csv(self._edge_aug_in)
        gt = pd.read_csv(self._gt_csv)

        # I timestamp sono globalmente unici tra esperimenti: il merge è sicuro.
        edges = edges.merge(
            gt[["timestamp", "label_trace"]], on="timestamp", how="left"
        )

        source_files = edges["source_file"].unique()
        n_total = len(source_files)
        self.n_excluded = self.n_ramped = self.n_skipped = 0

        augmented_frames: list[pd.DataFrame] = []

        for i, sf in enumerate(source_files):
            if progress_callback is not None:
                progress_callback(i, n_total, sf)

            sf_df = edges[edges["source_file"] == sf].copy()

            if sf.startswith(self._exclude_prefix):
                self.n_excluded += 1
                augmented_frames.append(sf_df.drop(columns=["label_trace"]))
                continue

            nominal_ts = np.sort(
                sf_df.loc[sf_df["label_trace"] == 0, "timestamp"].unique()
            )
            n_nominal = len(nominal_ts)

            if n_nominal < self._min_nominal:
                self.n_skipped += 1
                augmented_frames.append(sf_df.drop(columns=["label_trace"]))
                continue

            n_ramp = compute_n_ramp(n_nominal)
            ramp_ts = nominal_ts[-n_ramp:]

            result = sf_df.copy()
            for j, ts in enumerate(ramp_ts):
                scale = 1.0 + (self._ramp_scale - 1.0) * (j / (n_ramp - 1))
                mask = result["timestamp"] == ts
                result.loc[mask, "latency_ms"] *= scale

            self.n_ramped += 1
            augmented_frames.append(result.drop(columns=["label_trace"]))

            logger.debug(
                "[%s] rampa applicata: n_nominal=%d, n_ramp=%d", sf, n_nominal, n_ramp
            )

        result_df = pd.concat(augmented_frames, ignore_index=True)
        self._edge_aug_out.parent.mkdir(parents=True, exist_ok=True)
        result_df.to_csv(self._edge_aug_out, index=False)

        logger.info(
            "Scritto: %s (%d righe) | esclusi=%d, rampati=%d, saltati=%d",
            self._edge_aug_out,
            len(result_df),
            self.n_excluded,
            self.n_ramped,
            self.n_skipped,
        )
        return result_df
