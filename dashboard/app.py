import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import multiprocess as mp
import dash
import diskcache
from dash import html, dcc
import dash_mantine_components as dmc
import dash_cytoscape as cyto
cyto.load_extra_layouts()

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

_disk_cache = diskcache.Cache(str(CACHE_DIR / "dash_diskcache"))
background_callback_manager = dash.DiskcacheManager(_disk_cache)

app = dash.Dash(
    __name__,
    background_callback_manager=background_callback_manager,
    suppress_callback_exceptions=True,
)
app.title = "Compliance Forecasting"

from dashboard.layout.sidebar import create_sidebar  # noqa: E402

app.layout = dmc.MantineProvider(
    forceColorScheme="dark",
    theme={
        "primaryColor": "yellow",
        "colors": {
            "dark": [
                "#e2ddd5",  # 0
                "#c4a35a",  # 1
                "#5a5a5a",  # 2
                "#2a2a2a",  # 3
                "#1c1c1c",  # 4
                "#0e0e0e",  # 5
                "#0e0e0e",  # 6
                "#0e0e0e",  # 7
                "#0e0e0e",  # 8
                "#0e0e0e",  # 9
            ]
        },
    },
    children=[
        dcc.Store(id="active-section", data="s0"),
        html.Div(
            id="app-shell",
            style={
                "display": "flex",
                "height": "100vh",
                "overflow": "hidden",
                "backgroundColor": "var(--bg)",
            },
            children=[
                create_sidebar(),
                html.Div(
                    id="content-area",
                    style={
                        "flex": "1",
                        "overflowY": "auto",
                        "padding": "24px",
                        "backgroundColor": "var(--bg)",
                    },
                    children=html.Div(id="section-content"),
                ),
            ],
        ),
    ],
)

if mp.current_process().name == "MainProcess":
    _missing = []
    for _cb_module in [
            "cb_navigation",
            "cb_pipeline",
            "cb_s0",
            "cb_s1",
            "cb_s2",
            "cb_s3",
            "cb_s4",
            "cb_s5",
        ]:
        try:
            import importlib
            importlib.import_module(f"dashboard.callbacks.{_cb_module}")
        except ImportError:
            _missing.append(_cb_module)
    if _missing:
        import warnings
        warnings.warn(
            f"Callback non trovati (sviluppo in corso): {_missing}",
            stacklevel=2,
        )

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False, port=8050)
