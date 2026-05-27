"""Script di esecuzione per GammaRampInjector.

Produce data/converted/edge_metrics_aug_ramp.csv e stampa il report di verifica.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from src.ingestion.gamma_ramp_injector import (
    EDGE_AUG_IN,
    EDGE_AUG_OUT,
    GT_CSV,
    EXCLUDE_PREFIX,
    H_CACHE_EDGES,
    H_CRIT_EDGES,
    RAMP_SCALE_FACTOR,
    SLA_H_CACHE_MS,
    SLA_H_CRIT_MS,
    GammaRampInjector,
    compute_n_ramp,
)

try:
    from tqdm import tqdm
    _HAS_TQDM = True
except ImportError:
    _HAS_TQDM = False


# ---------------------------------------------------------------------------
# Progress bar
# ---------------------------------------------------------------------------

def _make_progress_callback(n_total: int):
    if _HAS_TQDM:
        bar = tqdm(total=n_total, unit="exp", desc="Ramp injection")

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
# Helpers per la verifica
# ---------------------------------------------------------------------------

def _mean_lat(df: pd.DataFrame, ts_list, edge_set: frozenset[str] | None = None) -> float:
    """Media latency_ms per i timestamp e gli archi dati."""
    sub = df[df["timestamp"].isin(ts_list)]
    if edge_set is not None:
        sub = sub[sub["edge_id"].isin(edge_set)]
    if sub.empty:
        return float("nan")
    return sub["latency_ms"].mean()


def _report_sample(
    sf: str,
    out_df: pd.DataFrame,
    gt: pd.DataFrame,
) -> None:
    """Stampa le stats di un singolo source_file campione."""
    sf_out = out_df[out_df["source_file"] == sf].copy()
    sf_gt = gt[gt["source_file"] == sf]

    nominal_ts = np.sort(
        sf_gt.loc[sf_gt["label_trace"] == 0, "timestamp"].unique()
    )
    anomal_ts = sf_gt.loc[sf_gt["label_trace"] == 1, "timestamp"].unique()
    n_nominal = len(nominal_ts)

    if n_nominal < 10:
        print(f"  {sf}: saltato (n_nominal={n_nominal} < 10)")
        return

    n_ramp = compute_n_ramp(n_nominal)
    ramp_ts = nominal_ts[-n_ramp:]
    pre_ramp_ts = nominal_ts[-(n_ramp + 5) : -n_ramp] if n_ramp + 5 <= n_nominal else nominal_ts[:5]
    last_ramp_ts = [ramp_ts[-1]]

    lat_pre = _mean_lat(sf_out, pre_ramp_ts)
    lat_post = _mean_lat(sf_out, last_ramp_ts)
    lat_anom = _mean_lat(sf_out, anomal_ts) if len(anomal_ts) > 0 else float("nan")
    h_crit_end = _mean_lat(sf_out, last_ramp_ts, H_CRIT_EDGES)
    h_cache_end = _mean_lat(sf_out, last_ramp_ts, H_CACHE_EDGES)

    scale_eff = 1.0 + (RAMP_SCALE_FACTOR - 1.0) * ((n_ramp - 1) / (n_ramp - 1))

    print(f"  {sf}:")
    print(f"    Latenza nominale pre-rampa (last 5 finestre prima della rampa): mean={lat_pre:.1f}ms")
    print(f"    Latenza nominale post-rampa (last finestra rampata): mean={lat_post:.1f}ms")
    print(f"    Scale factor effettivo: {scale_eff:.2f}")
    print(f"    Latenza anomala media:  {lat_anom:.1f}ms")
    h_crit_flag = "OK" if h_crit_end < SLA_H_CRIT_MS else "WARN"
    h_cache_flag = "OK" if h_cache_end < SLA_H_CACHE_MS else "WARN"
    print(
        f"    H_crit aggregato ramp_end: {h_crit_end:.1f}ms "
        f"(SLA={SLA_H_CRIT_MS:.1f}ms) -> {h_crit_flag}"
    )
    print(
        f"    H_cache aggregato ramp_end: {h_cache_end:.1f}ms "
        f"(SLA={SLA_H_CACHE_MS:.1f}ms) -> {h_cache_flag}"
    )


def _fp_check(out_df: pd.DataFrame, gt: pd.DataFrame) -> None:
    """Controlla falsi positivi su tutte le finestre nominali dell'output."""
    nominal_ts = set(gt.loc[gt["label_trace"] == 0, "timestamp"].unique())
    nominal_rows = out_df[out_df["timestamp"].isin(nominal_ts)]

    # Aggrega per (source_file, timestamp): media latenza per compliance set
    def _agg_mean(edge_set: frozenset[str]) -> pd.Series:
        sub = nominal_rows[nominal_rows["edge_id"].isin(edge_set)]
        return sub.groupby(["source_file", "timestamp"])["latency_ms"].mean()

    h_crit_mean = _agg_mean(H_CRIT_EDGES)
    h_cache_mean = _agg_mean(H_CACHE_EDGES)

    n_tot_crit = len(h_crit_mean)
    n_tot_cache = len(h_cache_mean)
    n_viol_crit = (h_crit_mean > SLA_H_CRIT_MS).sum()
    n_viol_cache = (h_cache_mean > SLA_H_CACHE_MS).sum()

    pct_crit = 100.0 * n_viol_crit / n_tot_crit if n_tot_crit else 0.0
    pct_cache = 100.0 * n_viol_cache / n_tot_cache if n_tot_cache else 0.0

    print("Controllo FP su nominali:")
    print(
        f"  Finestre nominali con latenza H_crit > SLA_H_CRIT: "
        f"{n_viol_crit} / {n_tot_crit} ({pct_crit:.1f}%)"
    )
    print(
        f"  Finestre nominali con latenza H_cache > SLA_H_CACHE: "
        f"{n_viol_cache} / {n_tot_cache} ({pct_cache:.1f}%)"
    )
    print("  (ATTESO: 0% -- se > 0% ridurre RAMP_SCALE_FACTOR)")


def _print_verification_report(
    injector: GammaRampInjector,
    out_df: pd.DataFrame,
) -> None:
    gt = pd.read_csv(GT_CSV)
    all_sf = out_df["source_file"].unique()

    print("\n=== VERIFICA RAMP INJECTOR ===\n")
    print(f"Esperimenti esclusi ({EXCLUDE_PREFIX}*): {injector.n_excluded}")
    print(f"Esperimenti con rampa applicata: {injector.n_ramped}")
    print(f"Esperimenti copiati invariati (n_nominal < 10): {injector.n_skipped}")
    print()

    # Seleziona 3 campioni: uno per fault_type (cpu non-escluso, mem, net)
    sample_files: list[str] = []
    for prefix in ("cpu_", "mem_", "net_"):
        for sf in all_sf:
            if sf.startswith(prefix) and not sf.startswith(EXCLUDE_PREFIX):
                n_nom = (gt[(gt["source_file"] == sf) & (gt["label_trace"] == 0)]).shape[0]
                if n_nom >= 10:
                    sample_files.append(sf)
                    break

    print("Campione 3 source_file (uno cpu, uno mem, uno net):")
    for sf in sample_files[:3]:
        _report_sample(sf, out_df, gt)
        print()

    _fp_check(out_df, gt)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    injector = GammaRampInjector()

    edges_in = pd.read_csv(EDGE_AUG_IN)
    n_total = edges_in["source_file"].nunique()
    del edges_in

    print(f"GammaRampInjector — {n_total} esperimenti da elaborare")

    cb, bar = _make_progress_callback(n_total)
    out_df = injector.inject(progress_callback=cb)

    if bar is not None:
        bar.close()

    print(f"\nScritto: {EDGE_AUG_OUT} ({len(out_df)} righe)")

    _print_verification_report(injector, out_df)


if __name__ == "__main__":
    main()
