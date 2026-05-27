"""Script di esecuzione per GammaPerArcConverter.

Produce data/converted/edge_metrics_aug.csv e stampa un report di verifica.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Aggiunge la radice del progetto al sys.path per importare src.*
sys.path.insert(0, str(Path(__file__).parent))

from src.ingestion.gamma_per_arc_converter import GammaPerArcConverter

try:
    from tqdm import tqdm
    _HAS_TQDM = True
except ImportError:
    _HAS_TQDM = False


# ---------------------------------------------------------------------------
# Progress bar
# ---------------------------------------------------------------------------

def _make_progress_callback(n_total: int):
    """Restituisce un callback compatibile con tqdm o fallback a print."""
    if _HAS_TQDM:
        bar = tqdm(total=n_total, unit="exp", desc="Conversione")

        def _cb(i: int, n: int, sf: str) -> None:
            bar.set_postfix_str(sf[:40])
            bar.update(1)

        return _cb, bar
    else:
        def _cb(i: int, n: int, sf: str) -> None:
            if i % 20 == 0:
                print(f"  [{i}/{n}] {sf}")

        return _cb, None


# ---------------------------------------------------------------------------
# Verifica per source_file
# ---------------------------------------------------------------------------

def _verify_source_files(
    aug_df: pd.DataFrame,
    orig_df: pd.DataFrame,
    sample_files: list[str],
) -> None:
    """Stampa stats per 3 source_file campione."""
    print("\nVerifica per 3 source_file campione:")
    for sf in sample_files:
        a = aug_df[aug_df["source_file"] == sf]
        o = orig_df[orig_df["source_file"] == sf]

        e1_a = a[a["edge_id"] == "e1"]["throughput_rps"]
        e3_a = a[a["edge_id"] == "e3"]["throughput_rps"]
        e4_a = a[a["edge_id"] == "e4"]["throughput_rps"]
        e1_o = o[o["edge_id"] == "e1"]["throughput_rps"]

        print(f"  {sf}:")
        print(
            f"    e1 throughput: mean={e1_a.mean():.2f} std={e1_a.std():.2f}"
            f"  (originale mean={e1_o.mean():.2f})"
        )
        print(
            f"    e3 throughput: mean={e3_a.mean():.2f} std={e3_a.std():.2f}"
            f"  (atteso: < e4)"
        )
        print(
            f"    e4 throughput: mean={e4_a.mean():.2f} std={e4_a.std():.2f}"
            f"  (atteso: > e3)"
        )
        print(
            f"    std(w_e3): {e3_a.std():.4f}"
            f"  (atteso: > 0.05 per esperimenti MEM)"
        )
        print()


# ---------------------------------------------------------------------------
# Frobenius simulato su finestre nominali
# ---------------------------------------------------------------------------

def _frobenius_report(
    aug_df: pd.DataFrame,
    gt_path: Path,
) -> None:
    """Calcola e stampa Frobenius simulato sulle finestre nominali.

    W_t è approssimata dai soli archi variabili (e3/e4 determinano
    il routing di home-timeline-service). Le altre colonne della
    matrice W sono costanti o zero, e non contribuiscono alla norma.
    """
    if not gt_path.exists():
        print("ground_truth.csv non trovato - Frobenius simulato saltato.")
        return

    gt_df = pd.read_csv(gt_path, usecols=["source_file", "window_id", "label_trace"])

    # Pivot: per ogni (source_file, window_id) recupera throughput e3 e e4
    e34 = aug_df[aug_df["edge_id"].isin(["e3", "e4"])].copy()
    pivot = e34.pivot_table(
        index=["source_file", "window_id"],
        columns="edge_id",
        values="throughput_rps",
        aggfunc="first",
    ).reset_index()

    # Aggiungi label_trace tramite join
    merged = pivot.merge(gt_df, on=["source_file", "window_id"], how="left")
    nominal = merged[merged["label_trace"] == 0].copy()

    if nominal.empty:
        print("Nessuna finestra nominale trovata - Frobenius simulato saltato.")
        return

    e3_col = nominal["e3"].fillna(0.0).values
    e4_col = nominal["e4"].fillna(0.0).values
    total = e3_col + e4_col

    # w23 = e3 / (e3 + e4); 0.0 se total == 0
    with np.errstate(invalid="ignore", divide="ignore"):
        w23 = np.where(total > 0, e3_col / total, 0.0)

    w23_gold = w23.mean()

    # Frobenius = sqrt((w23 - w23_gold)^2 + (w24 - w24_gold)^2)
    #           = sqrt(2) * |w23 - w23_gold|  [poiché w24 = 1 - w23]
    frob = np.sqrt(2.0) * np.abs(w23 - w23_gold)

    pct_nonzero = (frob > 0).mean() * 100.0
    print("Frobenius simulato (campione nominale):")
    print(f"  mean = {frob.mean():.4f}  (atteso: > 0 per almeno 90% delle finestre)")
    print(f"  max  = {frob.max():.4f}")
    print(f"  % finestre con Frobenius > 0: {pct_nonzero:.1f}%")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    converter = GammaPerArcConverter()

    # Conta source_files per dimensionare la progress bar
    orig_df = pd.read_csv(converter._edge_csv_in)
    n_total = orig_df["source_file"].nunique()

    print(f"GammaPerArcConverter - {n_total} esperimenti da elaborare")

    cb, bar = _make_progress_callback(n_total)
    aug_df = converter.convert(progress_callback=cb)

    if bar is not None:
        bar.close()

    print(f"\nScritto: {converter._edge_csv_out} ({len(aug_df)} righe)\n")

    # -------------------------------------------------------------------
    # Report di verifica - 3 source_file campione (cpu, mem, net se presenti)
    # -------------------------------------------------------------------
    all_files = aug_df["source_file"].unique()
    sample_files: list[str] = []
    for prefix in ("cpu_", "mem_", "net_"):
        match = next((sf for sf in all_files if sf.startswith(prefix)), None)
        if match:
            sample_files.append(match)
    # Fallback se uno dei prefissi non esiste
    for sf in all_files:
        if sf not in sample_files:
            sample_files.append(sf)
            if len(sample_files) == 3:
                break

    _verify_source_files(aug_df, orig_df, sample_files[:3])

    gt_path = Path("data/converted/ground_truth.csv")
    _frobenius_report(aug_df, gt_path)


if __name__ == "__main__":
    main()
