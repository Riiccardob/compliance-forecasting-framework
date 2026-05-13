import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import dash
import diskcache
from dash import html, dcc
import dash_mantine_components as dmc

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
    theme={
        "colorScheme": "dark",
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

from dashboard.callbacks import cb_navigation  # noqa: F401, E402
from dashboard.callbacks import cb_s0           # noqa: F401, E402
from dashboard.callbacks import cb_pipeline     # noqa: F401, E402

if __name__ == "__main__":
    app.run(debug=True, port=8050)
