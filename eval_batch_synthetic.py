#!/usr/bin/env python3
"""
Valutazione aggregata dei risultati del batch run sintetico.

Filtra automaticamente file JSON non pertinenti (GAMMA, calibration, test).
Calcola il recall per CS pertinente al fault scenario.

Utilizzo:
    python eval_batch_synthetic.py
    python eval_batch_synthetic.py --results-dir results
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

# Prefissi validi degli esperimenti sintetici.
# Qualsiasi file il cui stem non inizia con uno di questi viene ignorato.
VALID_PREFIXES = (
    "metrics_ingestor_memory_leak_",
    "data_enricher_memory_leak_",
    "stream_processor_cpu_saturation_",
    "analysis_engine_memory_leak_",
)

# Mapping scenario → CS pertinente (recall significativo solo su questo CS).
# Gli altri CS avranno recall=0% per costruzione (fault non propaga latenza).
SCENARIO_RELEVANT_CS: dict[str, list[str]] = {
    "metrics_ingestor": ["H_ingest"],
    "data_enricher":    ["H_ingest"],
    "stream_processor": ["H_ingest", "H_analysis"],   # nodo condiviso
    "analysis_engine":  ["H_analysis"],
}


def _relevant_cs(exp_name: str) -> list[str]:
    for prefix, cs_list in SCENARIO_RELEVANT_CS.items():
        if prefix in exp_name:
            return cs_list
    return []


def main(results_dir: Path) -> None:
    all_files = sorted(results_dir.glob("*.json"))
    json_files = [
        f for f in all_files
        if any(f.stem.startswith(p) for p in VALID_PREFIXES)
    ]

    skipped = len(all_files) - len(json_files)
    if skipped:
        print(f"Ignorati {skipped} file non pertinenti (GAMMA, test, calibrazione).\n")

    if not json_files:
        print(f"Nessun file di esperimento sintetico trovato in {results_dir.resolve()}")
        return

    hdr = (
        f"{'Esperimento':55s} {'CS':12s} {'Rilevante':9s} {'Rec%':5s} {'FP':3s} "
        f"{'lead_dist':35s} {'crit':28s} {'cusum%':7s} {'frob_rng':22s}"
    )
    print(hdr)
    print("-" * len(hdr))

    aggregated: dict[str, dict] = defaultdict(lambda: {
        "alerts":           0,
        "alerts_relevant":  0,
        "fp":               0,
        "fp_relevant":      0,
        "total_anomalous":  0,
        "total_anomalous_relevant": 0,
        "total_nominal":    0,
        "lt_dist":          Counter(),
        "crit_dist":        Counter(),
        "cusum_true":       0,
        "if_true":          0,
        "frob_vals":        [],
        "root_causes":      Counter(),
    })

    for jf in json_files:
        data = json.loads(jf.read_text(encoding="utf-8"))
        exp  = jf.stem
        relevant_cs = _relevant_cs(exp)

        for cs, cs_data in data.items():
            if cs not in ("H_ingest", "H_analysis"):
                continue

            alerts  = cs_data.get("alerts", [])
            n_anom  = cs_data.get("n_anomalous", 0)
            n_nom   = cs_data.get("n_nominal", 0)

            anom_alerts = [a for a in alerts if not a.get("is_nominal", True)]
            nom_alerts  = [a for a in alerts if a.get("is_nominal", False)]
            is_relevant = cs in relevant_cs

            recall  = len(anom_alerts) / n_anom * 100 if n_anom > 0 else 0.0
            fp      = len(nom_alerts)
            lt_dist = Counter(a.get("lead_time_steps") for a in anom_alerts)
            crit    = Counter(a.get("criticality")     for a in anom_alerts)

            frob = [
                a["structural_signals"].get("frobenius_distance")
                for a in anom_alerts
                if a.get("structural_signals") and
                   a["structural_signals"].get("frobenius_distance") is not None
            ]

            cusum_r = (
                sum(1 for a in anom_alerts
                    if a.get("structural_signals", {}).get("cusum_signal"))
                / max(1, len(anom_alerts)) * 100
            )

            frange = f"{min(frob):.3f}-{max(frob):.3f}" if frob else "N/A"
            lt_str = str(dict(sorted(lt_dist.items())))
            crit_str = str(dict(crit))

            print(
                f"  {exp:53s} {cs:12s} {'SI' if is_relevant else 'no':9s} "
                f"{recall:5.1f} {fp:3d} "
                f"{lt_str:35s} {crit_str:28s} "
                f"{cusum_r:7.1f} {frange:22s}"
            )

            agg = aggregated[cs]
            agg["alerts"]          += len(anom_alerts)
            agg["fp"]              += fp
            agg["total_anomalous"] += n_anom
            agg["total_nominal"]   += n_nom
            agg["lt_dist"]         += lt_dist
            agg["crit_dist"]       += crit
            agg["cusum_true"]      += sum(
                1 for a in anom_alerts if a.get("structural_signals", {}).get("cusum_signal")
            )
            agg["if_true"] += sum(
                1 for a in anom_alerts if a.get("structural_signals", {}).get("if_signal")
            )
            agg["frob_vals"] += frob
            agg["root_causes"].update(
                a.get("root_cause") for a in anom_alerts if a.get("root_cause")
            )

            if is_relevant:
                agg["alerts_relevant"]            += len(anom_alerts)
                agg["fp_relevant"]                += fp
                agg["total_anomalous_relevant"]   += n_anom

    print("\n" + "=" * 130)
    print("AGGREGATO PER COMPLIANCE SET")
    print("  recall_rilevante = alert su anomale / totale anomale, SOLO scenari pertinenti al CS")
    print("=" * 130)

    pass_all = True
    RECALL_MIN   = 70.0
    FP_MAX       = 0
    LT_MIN_VALS  = 3
    CUSUM_MIN    = 5.0

    for cs, agg in aggregated.items():
        n_rel   = agg["total_anomalous_relevant"]
        recall  = agg["alerts_relevant"] / n_rel * 100 if n_rel > 0 else 0.0
        recall_raw = agg["alerts"] / agg["total_anomalous"] * 100 if agg["total_anomalous"] > 0 else 0.0
        fp      = agg["fp_relevant"]
        cusum_r = agg["cusum_true"] / max(1, agg["alerts"]) * 100
        if_r    = agg["if_true"]   / max(1, agg["alerts"]) * 100
        fvals   = agg["frob_vals"]
        frange  = f"{min(fvals):.3f}-{max(fvals):.3f}" if fvals else "N/A"
        top_rc  = agg["root_causes"].most_common(3)

        n_lt    = len(agg["lt_dist"])
        ok_recall = recall >= RECALL_MIN
        ok_fp     = fp     <= FP_MAX
        ok_lt     = n_lt   >= LT_MIN_VALS
        ok_frob   = (min(fvals) >= 0.0 and max(fvals) > 0.0) if fvals else False
        ok_cusum  = cusum_r >= CUSUM_MIN

        if not all([ok_recall, ok_fp, ok_lt, ok_frob]):
            pass_all = False

        print(f"\n{cs}:")
        print(f"  Recall (CS pertinente): {recall:.1f}%  ({agg['alerts_relevant']}/{n_rel})"
              f"  {'OK' if ok_recall else f'FAIL (target >{RECALL_MIN}%)'}")
        print(f"  Recall (grezzo):        {recall_raw:.1f}%  (include scenari non pertinenti — non usare per valutazione)")
        print(f"  FP su nominali:         {fp}"
              f"  {'OK' if ok_fp else 'FAIL (FP > 0)'}")
        print(f"  Lead time dist:         {dict(sorted(agg['lt_dist'].items()))}"
              f"  {'OK' if ok_lt else f'FAIL ({n_lt} valori distinti, target >={LT_MIN_VALS})'}")
        print(f"  Criticality:            {dict(agg['crit_dist'])}")
        lt_status = "OK" if ok_cusum else "basso (accettabile se tolerance_factor calibrato)"
        print(f"  CUSUM rate:             {cusum_r:.1f}%  {lt_status}")
        print(f"  IF rate:                {if_r:.1f}%")
        frob_status = "OK (PBO attivo)" if ok_frob else "FAIL (PBO inattivo — Frobenius sempre 0)"
        print(f"  Frobenius range:        {frange}  {frob_status}")
        print(f"  Top root causes:        {top_rc}")

    print("\n" + "=" * 130)
    if pass_all:
        print("CRITERI PRINCIPALI SODDISFATTI.")
    else:
        print("ALCUNI CRITERI FALLITI. Vedi FAIL sopra.")
        print()
        print("Fix noti:")
        print("  FP > 0:         pre-warm observation_buffer in run_pipeline_synthetic.py")
        print("                  (vedi prompt_03_fixes.md, Fix 1)")
        print("  Recall basso:   verifica che il fix al generatore sia stato applicato")
        print("                  per stream_processor H_analysis")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Valutazione aggregata dei risultati del batch run sintetico."
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path("results"),
        help="Directory contenente i file JSON dei risultati (default: results)",
    )
    args = parser.parse_args()
    main(args.results_dir)