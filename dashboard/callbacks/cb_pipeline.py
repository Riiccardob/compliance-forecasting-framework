from dash import callback, Output, Input, State


@callback(
    output=[
        Output("s0-run-log",         "children"),
        Output("s0-pipeline-config", "data"),
    ],
    inputs=Input("s0-btn-run", "n_clicks"),
    state=[
        State("s0-mode", "value"),
        State("s0-n-snapshots", "value"),
    ],
    background=True,
    running=[
        (Output("s0-btn-run", "disabled"), True, False),
        (Output("s0-progress", "style"),
         {"display": "block", "marginTop": "8px"},
         {"display": "none"}),
        (Output("s0-progress-label", "style"),
         {"display": "block", "fontSize": "11px",
          "color": "var(--muted)", "marginTop": "4px"},
         {"display": "none"}),
    ],
    progress=[
        Output("s0-progress", "value"),
        Output("s0-progress-label", "children"),
    ],
    prevent_initial_call=True,
)
def run_pipeline_callback(set_progress, n_clicks, mode, n_snapshots):
    if not n_clicks:
        return "", None

    MODE_MAP = {"sample": "DEMO", "batch": "BATCH", "full": "FULL", "full_ds": "FULL"}
    mode = MODE_MAP.get(mode, mode) or "DEMO"

    import sys
    from pathlib import Path as _Path
    sys.path.insert(0, str(_Path(__file__).parent.parent.parent))
    from dashboard.core.pipeline_runner import run_pipeline
    from dashboard.core.data_manager import DataManager

    dm = DataManager()
    if not dm.is_data_loaded():
        return "Errore: dati non caricati. Caricare i CSV prima.", None

    _MODE_MAP = {"sample": "DEMO", "batch": "BATCH", "full": "FULL",
                 "DEMO": "DEMO", "BATCH": "BATCH", "FULL": "FULL"}
    mode = _MODE_MAP.get(mode or "DEMO", "DEMO")
    n_snapshots = int(n_snapshots or 50)

    all_snaps = dm.get_snapshots()
    # Indice O(1): timestamp µs → posizione nella lista
    _ts_idx = {s["timestamp"]: i for i, s in enumerate(all_snaps)}

    if mode == "DEMO":
        anomalous = dm.get_anomalous_snapshots()
        if anomalous:
            ts = anomalous[0]["timestamp"]
            snapshot_indices = [_ts_idx[ts]] if ts in _ts_idx else [0]
        else:
            snapshot_indices = [0]

    elif mode == "BATCH":
        anomalous = dm.get_anomalous_snapshots()
        snapshot_indices = []
        for s in anomalous:
            ts = s["timestamp"]
            if ts in _ts_idx and len(snapshot_indices) < n_snapshots:
                snapshot_indices.append(_ts_idx[ts])

    else:  # FULL
        snapshot_indices = []

    def _progress(value: int, label: str) -> None:
        set_progress((value, label))

    results = run_pipeline(mode, snapshot_indices, _progress)

    if "error" in results:
        return f"Errore pipeline: {results['error']}", None

    lines = [f"Pipeline completata - modalita {mode}"]
    lines.append(f"Snapshot processati: {results['n_snapshots']}")
    for cs, cs_data in results.get("compliance_sets", {}).items():
        n_alerts = len(cs_data.get("alerts", []))
        n_links  = len(cs_data.get("causal_graph", {}).get("edges", []))
        lines.append(f"{cs}: {n_alerts} alert, {n_links} link causali")

    config_saved = {"mode": mode, "n_snapshots": n_snapshots}
    return " | ".join(lines), config_saved
