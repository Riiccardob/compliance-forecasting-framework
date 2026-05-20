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
app.server.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

app.index_string = """<!DOCTYPE html>
<html>
<head>
    {%metas%}
    <title>{%title%}</title>
    {%favicon%}
    {%css%}
    <style>
/* ── Override definitivo dcc.Dropdown (React Select / emotion.js) ── */
[class$="-control"], [class*="-control "], div[class*="control"] {
    background-color: #1c1c1c !important;
    border-color: #2a2a2a !important; border-radius: 2px !important;
    box-shadow: none !important; min-height: 32px !important; cursor: pointer !important;
}
div[class*="control"]:hover { border-color: #c4a35a !important; }
div[class*="singleValue"], div[class*="placeholder"], div[class*="ValueContainer"],
div[class*="Input"] input, div[class*="input"] input {
    color: #e2ddd5 !important; background: transparent !important;
}
div[class*="menu"] {
    background-color: #1c1c1c !important; border: 1px solid #2a2a2a !important;
    border-radius: 2px !important; z-index: 99999 !important;
    box-shadow: 0 4px 16px rgba(0,0,0,0.6) !important;
}
div[class*="MenuList"], div[class*="menu-list"] {
    background-color: #1c1c1c !important; padding: 0 !important;
}
div[class*="option"] {
    background-color: #1c1c1c !important; color: #e2ddd5 !important;
    font-size: 13px !important; padding: 8px 12px !important; cursor: pointer !important;
}
div[class*="option"]:hover, div[class*="-is-focused"] {
    background-color: #2a2a2a !important; color: #e2ddd5 !important;
}
div[class*="-is-selected"] { background-color: rgba(196,163,90,0.15) !important; color: #c4a35a !important; }
span[class*="indicatorSeparator"] { background-color: #2a2a2a !important; }
div[class*="indicatorContainer"] svg { fill: #888888 !important; color: #888888 !important; }
div[class*="indicatorContainer"]:hover svg { fill: #e2ddd5 !important; }
div[class*="multiValue"] { background-color: #2a2a2a !important; border-radius: 2px !important; }
div[class*="multiValueLabel"] { color: #e2ddd5 !important; font-size: 12px !important; }
div[class*="multiValueRemove"]:hover { background-color: #b55e5e !important; color: #fff !important; }
input[type="number"], input[type="text"] {
    background-color: #0e0e0e !important; color: #e2ddd5 !important;
    border: 1px solid #2a2a2a !important; border-radius: 2px !important;
}
input[type="number"]:focus, input[type="text"]:focus {
    outline: none !important; border-color: #c4a35a !important;
}
    </style>
</head>
<body>
    {%app_entry%}
    <footer>{%config%}{%scripts%}{%renderer%}</footer>
</body>
</html>"""

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
    app.run(
        debug=True,
        use_reloader=False,
        port=8050,
        threaded=True,
    )
