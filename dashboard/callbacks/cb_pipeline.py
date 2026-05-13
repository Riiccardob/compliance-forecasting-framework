from dash import Output, Input, State
from dashboard.app import app, background_callback_manager


@app.callback(
    output=[
        Output("s0-run-log", "children"),
    ],
    inputs=Input("s0-btn-run", "n_clicks"),
    state=[
        State("s0-mode", "value"),
        State("s0-n-snapshots", "value"),
    ],
    background=True,
    manager=background_callback_manager,
    running=[
        (Output("s0-btn-run", "disabled"), True, False),
        (Output("s0-progress", "style"),
         {"display": "block"}, {"display": "none"}),
    ],
    progress=[
        Output("s0-progress", "value"),
        Output("s0-progress-label", "children"),
    ],
    prevent_initial_call=True,
)
def run_pipeline_callback(set_progress, n_clicks, mode, n_snapshots):
    if not n_clicks:
        return [""]

    import sys
    from pathlib import Path as _Path
    sys.path.insert(0, str(_Path(__file__).parent.parent.parent))
    from dashboard.core.pipeline_runner import run_pipeline
    from dashboard.core.data_manager import DataManager

    dm = DataManager()
    if not dm.is_data_loaded():
        return ["Errore: dati non caricati. Caricare i CSV prima."]

    mode = mode or "DEMO"
    n_snapshots = n_snapshots or 50

    if mode == "DEMO":
        anomalous = dm.get_anomalous_snapshots()
        all_snaps = dm.get_snapshots()
        if anomalous:
            idx = all_snaps.index(anomalous[0])
            snapshot_indices = [idx]
        else:
            snapshot_indices = [0]
    elif mode == "BATCH":
        anomalous = dm.get_anomalous_snapshots()
        all_snaps = dm.get_snapshots()
        indices = [all_snaps.index(s) for s in anomalous[:n_snapshots]
                   if s in all_snaps]
        snapshot_indices = indices[:n_snapshots]
    else:  # FULL / "sample" / "full"
        snapshot_indices = []

    def _progress(value: int, label: str) -> None:
        set_progress(value, label)

    results = run_pipeline(mode, snapshot_indices, _progress)

    if "error" in results:
        return [f"Errore pipeline: {results['error']}"]

    lines = [f"Pipeline completata — modalita {mode}"]
    lines.append(f"Snapshot processati: {results['n_snapshots']}")
    for cs, cs_data in results.get("compliance_sets", {}).items():
        n_alerts = len(cs_data.get("alerts", []))
        n_links  = len(cs_data.get("causal_graph", {}).get("edges", []))
        lines.append(f"{cs}: {n_alerts} alert, {n_links} link causali")

    return [" | ".join(lines)]
