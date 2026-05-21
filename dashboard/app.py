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
_disk_cache.clear()
background_callback_manager = dash.DiskcacheManager(_disk_cache)

app = dash.Dash(
    __name__,
    background_callback_manager=background_callback_manager,
    suppress_callback_exceptions=True,
)
app.title = "Compliance Forecasting"
app.server.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

app.index_string = r"""<!DOCTYPE html>
<html>
<head>
    {%metas%}
    <title>{%title%}</title>
    {%favicon%}
    {%css%}
</head>
<body>
    {%app_entry%}
    <footer>
        {%config%}
        {%scripts%}
        {%renderer%}
    </footer>
    <script>
    (function() {
        var BG   = "#1c1c1c";
        var BG2  = "#0e0e0e";
        var BD   = "#2a2a2a";
        var TEXT = "#e2ddd5";
        var MUT  = "#888888";
        var ACC  = "rgba(196,163,90,0.15)";
        var ACCT = "#c4a35a";

        function styleEl(el) {
            var c = el.className || "";
            if (typeof c !== "string") return;
            if (c.indexOf("control") > -1) {
                el.style.setProperty("background-color", BG, "important");
                el.style.setProperty("border-color", BD, "important");
                el.style.setProperty("border-radius", "2px", "important");
                el.style.setProperty("box-shadow", "none", "important");
                el.style.setProperty("min-height", "32px", "important");
            }
            if (c.indexOf("ValueContainer") > -1 ||
                c.indexOf("singleValue") > -1 ||
                c.indexOf("placeholder") > -1 ||
                c.indexOf("Input") > -1) {
                el.style.setProperty("color", TEXT, "important");
                el.style.setProperty("background-color", "transparent", "important");
            }
            if (c.indexOf("-menu") > -1 || c.indexOf("MenuList") > -1) {
                el.style.setProperty("background-color", BG, "important");
                el.style.setProperty("border", "1px solid " + BD, "important");
                el.style.setProperty("border-radius", "2px", "important");
                el.style.setProperty("z-index", "99999", "important");
                el.style.setProperty("box-shadow", "0 4px 16px rgba(0,0,0,0.6)", "important");
                el.style.setProperty("color", TEXT, "important");
                if (el.style.backgroundColor === "white" ||
                    el.style.backgroundColor === "#ffffff" ||
                    el.style.backgroundColor === "rgb(255, 255, 255)") {
                    el.style.setProperty("background-color", BG, "important");
                }
            }
            if (c.indexOf("option") > -1) {
                if (el.style.backgroundColor === "white" ||
                    el.style.backgroundColor === "#ffffff" ||
                    el.style.backgroundColor === "rgb(255, 255, 255)") {
                    el.style.setProperty("background-color", BG, "important");
                }
                el.style.setProperty("color", TEXT, "important");
                el.style.setProperty("cursor", "pointer", "important");
            }
            if (c.indexOf("indicatorSeparator") > -1) {
                el.style.setProperty("background-color", BD, "important");
            }
            if (c.indexOf("dropdownIndicator") > -1 ||
                c.indexOf("clearIndicator") > -1) {
                var svgs = el.querySelectorAll("svg");
                svgs.forEach(function(s) {
                    s.style.setProperty("fill", MUT, "important");
                });
            }
            if (c.indexOf("multiValue") > -1 && c.indexOf("Label") < 0
                    && c.indexOf("Remove") < 0) {
                el.style.setProperty("background-color", BD, "important");
                el.style.setProperty("border-radius", "2px", "important");
            }
            if (c.indexOf("multiValueLabel") > -1) {
                el.style.setProperty("color", TEXT, "important");
            }
        }

        function applyAll(root) {
            var all = root.querySelectorAll("*");
            for (var i = 0; i < all.length; i++) { styleEl(all[i]); }
        }

        var observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(m) {
                if (m.type === "attributes" && m.attributeName === "style") {
                    styleEl(m.target);
                }
                m.addedNodes.forEach(function(node) {
                    if (node.nodeType !== 1) return;
                    styleEl(node);
                    applyAll(node);
                });
                if (m.type === "attributes" && m.attributeName === "class") {
                    styleEl(m.target);
                }
            });
        });

        document.addEventListener("DOMContentLoaded", function() {
            observer.observe(document.body, {
                childList: true,
                subtree: true,
                attributes: true,
                attributeFilter: ["class", "style"]
            });
            applyAll(document.body);
        });

        /* hover effect per le opzioni */
        document.addEventListener("mouseover", function(e) {
            var el = e.target;
            var c = el.className || "";
            if (typeof c === "string" && c.indexOf("option") > -1) {
                el.style.setProperty("background-color", BD, "important");
            }
        });
        document.addEventListener("mouseout", function(e) {
            var el = e.target;
            var c = el.className || "";
            if (typeof c === "string" && c.indexOf("option") > -1 &&
                c.indexOf("selected") < 0) {
                el.style.setProperty("background-color", BG, "important");
            }
        });
    })();
    </script>
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
