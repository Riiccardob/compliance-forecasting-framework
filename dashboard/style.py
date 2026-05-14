"""CSS custom e costanti di stile per la dashboard."""
import streamlit as st

PALETTE = {
    "background": "#0D1117",
    "surface": "#161B22",
    "surface_alt": "#21262D",
    "border": "#30363D",
    "text_primary": "#E6EDF3",
    "text_secondary": "#8B949E",
    "accent": "#238636",
    "accent_blue": "#58A6FF",
    "yellow": "#D29922",
    "orange": "#BD561D",
    "red": "#DA3633",
    "h_crit": "#58A6FF",
    "h_cache": "#3FB950",
    "nominal": "#238636",
    "anomaly": "#DA3633",
}

CSS = """
<style>
/* ── Base ── */
html, body, [data-testid="stAppViewContainer"] {
    background-color: #0D1117 !important;
    color: #E6EDF3;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
}
[data-testid="stAppViewContainer"] > .main {
    background-color: #0D1117;
}
[data-testid="stMain"] {
    background-color: #0D1117;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background-color: #010409 !important;
    border-right: 1px solid #21262D;
}
[data-testid="stSidebar"] * {
    color: #8B949E;
}

/* Bottoni sidebar — secondary */
[data-testid="stSidebar"] .stButton button {
    background: transparent !important;
    border: none !important;
    color: #8B949E !important;
    text-align: left !important;
    padding: 8px 12px !important;
    border-radius: 6px !important;
    font-size: 14px !important;
    font-weight: 400 !important;
    width: 100%;
    transition: background 0.15s, color 0.15s;
}
[data-testid="stSidebar"] .stButton button:hover {
    background: #21262D !important;
    color: #E6EDF3 !important;
}
/* Bottone pagina attiva (type=primary) */
[data-testid="stSidebar"] .stButton button[kind="primaryFormSubmit"],
[data-testid="stSidebar"] .stButton button[kind="primary"] {
    background: #21262D !important;
    color: #58A6FF !important;
    font-weight: 600 !important;
}

/* ── Card generica ── */
.card {
    background: #161B22;
    border: 1px solid #30363D;
    border-radius: 8px;
    padding: 20px;
    margin-bottom: 16px;
}

/* ── Metriche ── */
[data-testid="stMetric"] {
    background: #161B22;
    border: 1px solid #30363D;
    border-radius: 8px;
    padding: 16px;
}
[data-testid="stMetricLabel"] p {
    color: #8B949E !important;
    font-size: 0.78rem !important;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
[data-testid="stMetricValue"] {
    color: #E6EDF3 !important;
}

/* ── Dataframe ── */
[data-testid="stDataFrame"] {
    border: 1px solid #30363D;
    border-radius: 8px;
    overflow: hidden;
}

/* ── Tabs ── */
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    background-color: #161B22;
    border-bottom: 1px solid #30363D;
    gap: 0;
}
[data-testid="stTabs"] [data-baseweb="tab"] {
    color: #8B949E;
    background: transparent;
    padding: 0.55rem 1.1rem;
}
[data-testid="stTabs"] [aria-selected="true"] {
    color: #E6EDF3;
    border-bottom: 2px solid #58A6FF;
}

/* ── Expander ── */
[data-testid="stExpander"] {
    background: #161B22;
    border: 1px solid #30363D;
    border-radius: 8px;
}

/* ── Buttons (main content) ── */
.stButton > button {
    background-color: #21262D !important;
    color: #E6EDF3 !important;
    border: 1px solid #30363D !important;
    border-radius: 6px !important;
    font-size: 14px !important;
    transition: border-color 0.15s, color 0.15s;
}
.stButton > button:hover {
    border-color: #58A6FF !important;
    color: #58A6FF !important;
}

/* ── Info / warning / error / success ── */
[data-testid="stInfo"] {
    background: rgba(88, 166, 255, 0.08) !important;
    border: 1px solid rgba(88, 166, 255, 0.25) !important;
    border-radius: 6px;
    color: #E6EDF3;
}
[data-testid="stWarning"] {
    background: rgba(210, 153, 34, 0.08) !important;
    border: 1px solid rgba(210, 153, 34, 0.25) !important;
    border-radius: 6px;
}
[data-testid="stSuccess"] {
    background: rgba(35, 134, 54, 0.08) !important;
    border: 1px solid rgba(35, 134, 54, 0.25) !important;
    border-radius: 6px;
}
[data-testid="stError"] {
    background: rgba(218, 54, 51, 0.08) !important;
    border: 1px solid rgba(218, 54, 51, 0.25) !important;
    border-radius: 6px;
}

/* ── Badge criticità — unico posto dove si usano i colori alert ── */
.badge-yellow {
    background: #D29922; color: #000;
    padding: 2px 8px; border-radius: 12px;
    font-size: 12px; font-weight: 600;
    display: inline-block;
}
.badge-orange {
    background: #BD561D; color: #fff;
    padding: 2px 8px; border-radius: 12px;
    font-size: 12px; font-weight: 600;
    display: inline-block;
}
.badge-red {
    background: #DA3633; color: #fff;
    padding: 2px 8px; border-radius: 12px;
    font-size: 12px; font-weight: 600;
    display: inline-block;
}
.badge-ok {
    background: #238636; color: #fff;
    padding: 2px 8px; border-radius: 12px;
    font-size: 12px; font-weight: 600;
    display: inline-block;
}
.badge-grey {
    background: #30363D; color: #8B949E;
    padding: 2px 8px; border-radius: 12px;
    font-size: 12px;
    display: inline-block;
}

/* ── Chip nodo (topologia) ── */
.node-chip {
    display: inline-block;
    background: #21262D;
    border: 1px solid #30363D;
    border-radius: 4px;
    padding: 0.12em 0.45em;
    font-size: 0.78rem;
    font-family: monospace;
    color: #E6EDF3;
    margin: 0.1em;
}

/* ── Nascondere chrome Streamlit ── */
/* #MainMenu { display: none; } */
/* footer { display: none; } */
/* header[data-testid="stHeader"] { display: none; } -> rimosso per permettere di vedere l'hamburger menu */
/* [data-testid="stDecoration"] { display: none; } */
/* [data-testid="stToolbar"] { display: none; } */
</style>
"""


def apply_style() -> None:
    """Inietta il CSS custom nella pagina Streamlit."""
    st.markdown(CSS, unsafe_allow_html=True)
