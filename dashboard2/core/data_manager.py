import pickle
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent.parent / "cache"


class DataManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._snapshots: list[dict] | None = None
        self._weight_series: list[dict] | None = None
        self._gold_standard: dict[str, float] | None = None
        self._pipeline_results: dict | None = None
        self._node_path: Path | None = None
        self._edge_path: Path | None = None
        self._gt_path: Path | None = None

    def _save_pickle(self, filename: str, obj: object) -> None:
        try:
            with open(CACHE_DIR / filename, "wb") as f:
                pickle.dump(obj, f)
        except Exception as e:
            logger.warning("Salvataggio pickle fallito (%s): %s", filename, e)

    def _load_pickle(self, filename: str) -> object | None:
        try:
            path = CACHE_DIR / filename
            if path.exists():
                with open(path, "rb") as f:
                    return pickle.load(f)
        except Exception as e:
            logger.warning("Caricamento pickle fallito (%s): %s", filename, e)
        return None

    def load_csvs(self, node_path: Path, edge_path: Path, gt_path: Path) -> None:
        self._node_path = node_path
        self._edge_path = edge_path
        self._gt_path = gt_path

    def build_snapshots(self) -> None:
        if self._node_path is None:
            raise RuntimeError("CSV non caricati")
        import sys
        from pathlib import Path as _Path
        sys.path.insert(0, str(_Path(__file__).parent.parent.parent))
        from src.utils.config_loader import ConfigLoader
        from src.layer2.atg_builder import ATGBuilder
        from src.layer2.pbo_builder import PBOBuilder
        from src.layer1.topology_builder import TopologyBuilder

        topology_path = _Path(__file__).parent.parent.parent / "config" / "topology.yaml"
        pipeline_path = _Path(__file__).parent.parent.parent / "config" / "pipeline_params.yaml"

        config = ConfigLoader(topology_path, pipeline_path)
        atg = ATGBuilder(config, self._node_path, self._edge_path, self._gt_path)
        snapshots = atg.build()
        topology_builder = TopologyBuilder(config)
        pbo = PBOBuilder(config, topology_builder)
        weight_series = pbo.compute_transition_weights(snapshots)
        gold_standard = pbo.compute_gold_standard(weight_series, snapshots)

        self._snapshots = snapshots
        self._weight_series = weight_series
        self._gold_standard = gold_standard
        self._save_pickle("snapshots.pkl", snapshots)
        self._save_pickle("weight_series.pkl", weight_series)
        self._save_pickle("gold_standard.pkl", gold_standard)

    def get_snapshots(self) -> list[dict]:
        if self._snapshots is not None:
            return self._snapshots
        loaded = self._load_pickle("snapshots.pkl")
        if loaded is not None:
            self._snapshots = loaded
            return self._snapshots
        return []

    def get_nominal_snapshots(self) -> list[dict]:
        return [s for s in self.get_snapshots() if s.get("label") == 0]

    def get_anomalous_snapshots(self) -> list[dict]:
        return [s for s in self.get_snapshots() if s.get("label") == 1]

    def get_weight_series(self) -> list[dict]:
        if self._weight_series is not None:
            return self._weight_series
        loaded = self._load_pickle("weight_series.pkl")
        if loaded is not None:
            self._weight_series = loaded
            return self._weight_series
        return []

    def get_gold_standard(self) -> dict[str, float]:
        if self._gold_standard is not None:
            return self._gold_standard
        loaded = self._load_pickle("gold_standard.pkl")
        if loaded is not None:
            self._gold_standard = loaded
            return self._gold_standard
        return {}

    def save_pipeline_results(self, results: dict) -> None:
        self._pipeline_results = results
        self._save_pickle("pipeline_results.pkl", results)

    def load_pipeline_results(self) -> dict | None:
        if self._pipeline_results is not None:
            return self._pipeline_results
        loaded = self._load_pickle("pipeline_results.pkl")
        if loaded is not None:
            self._pipeline_results = loaded
        return self._pipeline_results

    def is_data_loaded(self) -> bool:
        return len(self.get_snapshots()) > 0

    def is_pipeline_run(self) -> bool:
        return self.load_pipeline_results() is not None
