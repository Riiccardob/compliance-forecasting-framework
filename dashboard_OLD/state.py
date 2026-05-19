"""SessionState centralizzato per la dashboard."""
from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any

import streamlit as st

if TYPE_CHECKING:
    from src.layer2.atg_builder import ATGBuilder
    from src.layer2.pbo_builder import PBOBuilder
    from src.layer3.feature_selector import FeatureSelector
    from src.phase1.stat_forecaster import StatForecaster
    from src.phase2.causal_analyzer import CausalAnalyzer
    from src.phase3.structural_monitor import StructuralMonitor
    from src.phase4.alert_generator import AlertGenerator
    from src.utils.config_loader import ConfigLoader
    from src.layer1.topology_builder import TopologyBuilder

_KEY = "_app_state"


class AppState:
    """Wrapper tipizzato su st.session_state."""

    _DEFAULTS: dict[str, Any] = {
        # Dati caricati
        "snapshots": None,
        "nominal_snapshots": None,
        "anomalous_snapshots": None,
        "weight_series": None,
        "gold_standard": None,
        # DataFrame raw
        "node_df": None,
        "edge_df": None,
        "gt_df": None,
        # Moduli inizializzati
        "config": None,
        "topology_builder": None,
        "atg_builder": None,
        "pbo_builder": None,
        "feature_selector": None,
        "stat_forecaster": None,
        "causal_analyzer": None,
        "structural_monitor": None,
        "alert_generator": None,
        # Risultati pipeline per compliance set
        "results": {},
        # Stato esecuzione
        "pipeline_running": False,
        "pipeline_phase": "idle",
        "pipeline_log": [],
        # Dataset info
        "dataset_path": None,
        "n_snapshots": 0,
        "n_nominal": 0,
        "n_anomalous": 0,
        # Navigazione
        "current_page": "Panoramica",
        # Topologia
        "current_snapshot_idx": 0,
        "selected_cs": "H_crit",
        "graph_layout": None,          # dict[str, tuple[float, float]] | None
        # PBO pre-calcolato
        "pas_series": None,            # list[dict] | None
        "frobenius_series": None,      # list[dict] | None
    }

    def __init__(self) -> None:
        ss = st.session_state
        for key, default in self._DEFAULTS.items():
            if key not in ss:
                ss[key] = default if not isinstance(default, (dict, list)) else type(default)()

    # ── Proprietà dati ────────────────────────────────────────────────────

    @property
    def snapshots(self) -> list[dict] | None:
        return st.session_state.get("snapshots")

    @snapshots.setter
    def snapshots(self, v: list[dict] | None) -> None:
        st.session_state["snapshots"] = v

    @property
    def nominal_snapshots(self) -> list[dict] | None:
        return st.session_state.get("nominal_snapshots")

    @nominal_snapshots.setter
    def nominal_snapshots(self, v: list[dict] | None) -> None:
        st.session_state["nominal_snapshots"] = v

    @property
    def anomalous_snapshots(self) -> list[dict] | None:
        return st.session_state.get("anomalous_snapshots")

    @anomalous_snapshots.setter
    def anomalous_snapshots(self, v: list[dict] | None) -> None:
        st.session_state["anomalous_snapshots"] = v

    @property
    def weight_series(self) -> list[dict] | None:
        return st.session_state.get("weight_series")

    @weight_series.setter
    def weight_series(self, v: list[dict] | None) -> None:
        st.session_state["weight_series"] = v

    @property
    def gold_standard(self) -> dict[str, float] | None:
        return st.session_state.get("gold_standard")

    @gold_standard.setter
    def gold_standard(self, v: dict[str, float] | None) -> None:
        st.session_state["gold_standard"] = v

    @property
    def node_df(self):
        return st.session_state.get("node_df")

    @node_df.setter
    def node_df(self, v) -> None:
        st.session_state["node_df"] = v

    @property
    def edge_df(self):
        return st.session_state.get("edge_df")

    @edge_df.setter
    def edge_df(self, v) -> None:
        st.session_state["edge_df"] = v

    @property
    def gt_df(self):
        return st.session_state.get("gt_df")

    @gt_df.setter
    def gt_df(self, v) -> None:
        st.session_state["gt_df"] = v

    # ── Moduli ───────────────────────────────────────────────────────────

    @property
    def config(self):
        return st.session_state.get("config")

    @config.setter
    def config(self, v) -> None:
        st.session_state["config"] = v

    @property
    def topology_builder(self):
        return st.session_state.get("topology_builder")

    @topology_builder.setter
    def topology_builder(self, v) -> None:
        st.session_state["topology_builder"] = v

    @property
    def atg_builder(self):
        return st.session_state.get("atg_builder")

    @atg_builder.setter
    def atg_builder(self, v) -> None:
        st.session_state["atg_builder"] = v

    @property
    def pbo_builder(self):
        return st.session_state.get("pbo_builder")

    @pbo_builder.setter
    def pbo_builder(self, v) -> None:
        st.session_state["pbo_builder"] = v

    @property
    def feature_selector(self):
        return st.session_state.get("feature_selector")

    @feature_selector.setter
    def feature_selector(self, v) -> None:
        st.session_state["feature_selector"] = v

    @property
    def stat_forecaster(self):
        return st.session_state.get("stat_forecaster")

    @stat_forecaster.setter
    def stat_forecaster(self, v) -> None:
        st.session_state["stat_forecaster"] = v

    @property
    def causal_analyzer(self):
        return st.session_state.get("causal_analyzer")

    @causal_analyzer.setter
    def causal_analyzer(self, v) -> None:
        st.session_state["causal_analyzer"] = v

    @property
    def structural_monitor(self):
        return st.session_state.get("structural_monitor")

    @structural_monitor.setter
    def structural_monitor(self, v) -> None:
        st.session_state["structural_monitor"] = v

    @property
    def alert_generator(self):
        return st.session_state.get("alert_generator")

    @alert_generator.setter
    def alert_generator(self, v) -> None:
        st.session_state["alert_generator"] = v

    # ── Risultati ────────────────────────────────────────────────────────

    @property
    def results(self) -> dict[str, dict]:
        return st.session_state.get("results", {})

    @results.setter
    def results(self, v: dict[str, dict]) -> None:
        st.session_state["results"] = v

    # ── Pipeline ─────────────────────────────────────────────────────────

    @property
    def pipeline_running(self) -> bool:
        return st.session_state.get("pipeline_running", False)

    @pipeline_running.setter
    def pipeline_running(self, v: bool) -> None:
        st.session_state["pipeline_running"] = v

    @property
    def pipeline_phase(self) -> str:
        return st.session_state.get("pipeline_phase", "idle")

    @pipeline_phase.setter
    def pipeline_phase(self, v: str) -> None:
        st.session_state["pipeline_phase"] = v

    @property
    def pipeline_log(self) -> list[str]:
        return st.session_state.get("pipeline_log", [])

    @pipeline_log.setter
    def pipeline_log(self, v: list[str]) -> None:
        st.session_state["pipeline_log"] = v

    # ── Dataset info ─────────────────────────────────────────────────────

    @property
    def dataset_path(self) -> str | None:
        return st.session_state.get("dataset_path")

    @dataset_path.setter
    def dataset_path(self, v: str | None) -> None:
        st.session_state["dataset_path"] = v

    @property
    def n_snapshots(self) -> int:
        return st.session_state.get("n_snapshots", 0)

    @n_snapshots.setter
    def n_snapshots(self, v: int) -> None:
        st.session_state["n_snapshots"] = v

    @property
    def n_nominal(self) -> int:
        return st.session_state.get("n_nominal", 0)

    @n_nominal.setter
    def n_nominal(self, v: int) -> None:
        st.session_state["n_nominal"] = v

    @property
    def n_anomalous(self) -> int:
        return st.session_state.get("n_anomalous", 0)

    @n_anomalous.setter
    def n_anomalous(self, v: int) -> None:
        st.session_state["n_anomalous"] = v

    # ── Navigazione ───────────────────────────────────────────────────────

    @property
    def current_page(self) -> str:
        return st.session_state.get("current_page", "1 - Panoramica sistema")

    @current_page.setter
    def current_page(self, v: str) -> None:
        st.session_state["current_page"] = v

    # ── Topologia ────────────────────────────────────────────────────────

    @property
    def current_snapshot_idx(self) -> int:
        return st.session_state.get("current_snapshot_idx", 0)

    @current_snapshot_idx.setter
    def current_snapshot_idx(self, v: int) -> None:
        st.session_state["current_snapshot_idx"] = v

    @property
    def selected_cs(self) -> str:
        return st.session_state.get("selected_cs", "H_crit")

    @selected_cs.setter
    def selected_cs(self, v: str) -> None:
        st.session_state["selected_cs"] = v

    @property
    def graph_layout(self) -> dict[str, tuple[float, float]] | None:
        return st.session_state.get("graph_layout")

    @graph_layout.setter
    def graph_layout(self, v: dict[str, tuple[float, float]] | None) -> None:
        st.session_state["graph_layout"] = v

    # ── PBO pre-calcolato ─────────────────────────────────────────────────

    @property
    def pas_series(self) -> list[dict] | None:
        return st.session_state.get("pas_series")

    @pas_series.setter
    def pas_series(self, v: list[dict] | None) -> None:
        st.session_state["pas_series"] = v

    @property
    def frobenius_series(self) -> list[dict] | None:
        return st.session_state.get("frobenius_series")

    @frobenius_series.setter
    def frobenius_series(self, v: list[dict] | None) -> None:
        st.session_state["frobenius_series"] = v

    # ── Metodi ───────────────────────────────────────────────────────────

    @classmethod
    def get(cls) -> "AppState":
        """Restituisce (o crea) il singleton AppState da session_state."""
        if _KEY not in st.session_state:
            st.session_state[_KEY] = cls()
        return st.session_state[_KEY]

    def reset_pipeline(self) -> None:
        """Azzera risultati, stato esecuzione e log della pipeline."""
        self.results = {}
        self.pipeline_running = False
        self.pipeline_phase = "idle"
        self.pipeline_log = []

    def add_log(self, msg: str) -> None:
        """Appende un messaggio al log della pipeline con timestamp."""
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        log = self.pipeline_log
        log.append(f"[{ts}] {msg}")
        self.pipeline_log = log

    def data_loaded(self) -> bool:
        """True se i dati sono stati caricati."""
        return self.snapshots is not None and len(self.snapshots) > 0

    def modules_ready(self) -> bool:
        """True se i moduli base sono inizializzati."""
        return (
            self.config is not None
            and self.topology_builder is not None
            and self.atg_builder is not None
        )

    def pipeline_done(self) -> bool:
        """True se la pipeline ha prodotto risultati."""
        return len(self.results) > 0
