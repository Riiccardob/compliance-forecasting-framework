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
    MAX_GLOBAL_SCALE,
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
    injector: "GammaRampInjector",
) -> None:
    """Stampa le stats di un singolo source_file campione."""
    sf_out = out_df[out_df["source_file"] == sf].copy()
    sf_gt = gt[gt["source_file"] == sf]

    nominal_ts = np.sort(
        sf_gt.loc[sf_gt["label_trace"] == 0, "timestamp"].unique()
    )
    anomal_ts = sf_gt.loc[sf_gt["label_trace"] == 1, "timestamp"].unique()
    n_nominal = len(nominal_ts)

    if n_nominal < 5:
        print(f"  {sf}: saltato (n_nominal={n_nominal} < 5)")
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

    scale_eff = injector.exp_scale_factors.get(sf, MAX_GLOBAL_SCALE)

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


def _fp_check(out_df: pd.DataFrame, in_df: pd.DataFrame, gt: pd.DataFrame) -> None:
    """Controlla falsi positivi su tutte le finestre nominali dell'output."""
    nominal_ts = set(gt.loc[gt["label_trace"] == 0, "timestamp"].unique())

    def _agg_mean_df(df: pd.DataFrame, edge_set: frozenset[str]) -> pd.Series:
        sub = df[df["timestamp"].isin(nominal_ts) & df["edge_id"].isin(edge_set)]
        return sub.groupby(["source_file", "timestamp"])["latency_ms"].mean()

    h_crit_out = _agg_mean_df(out_df, H_CRIT_EDGES)
    h_cache_out = _agg_mean_df(out_df, H_CACHE_EDGES)
    h_crit_in  = _agg_mean_df(in_df,  H_CRIT_EDGES)

    n_tot_crit  = len(h_crit_out)
    n_tot_cache = len(h_cache_out)
    n_viol_crit  = (h_crit_out  > SLA_H_CRIT_MS).sum()
    n_viol_cache = (h_cache_out > SLA_H_CACHE_MS).sum()

    # Violazioni introdotte dal ramp (non preesistenti nell'input)
    viol_out_mask = h_crit_out > SLA_H_CRIT_MS
    viol_in_mask  = h_crit_in.reindex(h_crit_out.index).fillna(0.0) > SLA_H_CRIT_MS
    n_new_fp = (viol_out_mask & ~viol_in_mask).sum()

    pct_crit  = 100.0 * n_viol_crit  / n_tot_crit  if n_tot_crit  else 0.0
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
    print(f"  Nuovi FP introdotti dal ramp: {n_new_fp}")
    print("  (ATTESO: 0% -- se > 0% ridurre MAX_GLOBAL_SCALE)")


def _scale_factor_report(injector: GammaRampInjector, gt: pd.DataFrame) -> None:
    """Stampa statistiche sui scale factor per-esperimento."""
    scales = list(injector.exp_scale_factors.values())
    if not scales:
        print("Scale factor per-esperimento: nessun esperimento rampato.")
        return

    scales_arr = np.array(scales)
    n_low  = int((scales_arr < 1.5).sum())
    n_max  = int(np.isclose(scales_arr, MAX_GLOBAL_SCALE).sum())

    print("Scale factor per-esperimento:")
    print(f"  min = {scales_arr.min():.2f}  max = {scales_arr.max():.2f}  "
          f"mean = {scales_arr.mean():.2f}")
    print(f"  Esperimenti con scale < 1.5 (latenza nominale alta): {n_low}")
    print(f"  Esperimenti con scale == MAX ({MAX_GLOBAL_SCALE:.2f}):                 {n_max}")
    print()

    # Esperimenti con n_nominal 5-9 (precedentemente saltati con soglia 10)
    n_newly = sum(
        1 for sf in injector.exp_scale_factors
        if 5 <= gt[gt["source_file"] == sf]["label_trace"].eq(0).sum() <= 9
    )
    print(f"Esperimenti precedentemente skippati ora inclusi: {n_newly}")
    print("  (erano n_nominal 5-9, ora processati)")
    print()


def _print_verification_report(
    injector: GammaRampInjector,
    out_df: pd.DataFrame,
    in_df: pd.DataFrame,
) -> None:
    gt = pd.read_csv(GT_CSV)
    all_sf = out_df["source_file"].unique()

    print("\n=== VERIFICA RAMP INJECTOR ===\n")
    print(f"Esperimenti esclusi ({EXCLUDE_PREFIX}*): {injector.n_excluded}")
    print(f"Esperimenti con rampa applicata: {injector.n_ramped}")
    print(f"Esperimenti copiati invariati (n_nominal < 5 o lat. alta): {injector.n_skipped}")
    print()

    # Seleziona 3 campioni: uno per fault_type (cpu non-escluso, mem, net)
    sample_files: list[str] = []
    for prefix in ("cpu_", "mem_", "net_"):
        for sf in all_sf:
            if sf.startswith(prefix) and not sf.startswith(EXCLUDE_PREFIX):
                n_nom = (gt[(gt["source_file"] == sf) & (gt["label_trace"] == 0)]).shape[0]
                if n_nom >= 5:
                    sample_files.append(sf)
                    break

    print("Campione 3 source_file (uno cpu, uno mem, uno net):")
    for sf in sample_files[:3]:
        _report_sample(sf, out_df, gt, injector)
        print()

    _scale_factor_report(injector, gt)
    _fp_check(out_df, in_df, gt)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    injector = GammaRampInjector()

    in_df = pd.read_csv(EDGE_AUG_IN)
    n_total = in_df["source_file"].nunique()

    print(f"GammaRampInjector — {n_total} esperimenti da elaborare")

    cb, bar = _make_progress_callback(n_total)
    out_df = injector.inject(progress_callback=cb)

    if bar is not None:
        bar.close()

    print(f"\nScritto: {EDGE_AUG_OUT} ({len(out_df)} righe)")

    _print_verification_report(injector, out_df, in_df)


if __name__ == "__main__":
    main()
