"""Script one-shot per eseguire il DSBConverter sull'intero dataset raw."""
from pathlib import Path

from src.utils.config_loader import ConfigLoader
from src.ingestion.converter import DSBConverter

ROOT = Path(__file__).parent
TOPOLOGY_PATH = ROOT / "config" / "topology.yaml"
PIPELINE_PATH = ROOT / "config" / "pipeline_params.yaml"
RAW_DIR = ROOT / "DATASET"

config = ConfigLoader(TOPOLOGY_PATH, PIPELINE_PATH)
converter = DSBConverter(config)
converter.convert_all(RAW_DIR)
