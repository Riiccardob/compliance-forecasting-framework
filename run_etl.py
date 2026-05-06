from pathlib import Path
from src.utils.config_loader import ConfigLoader
from src.ingestion.converter import DSBConverter


def main() -> None:
    root = Path(__file__).parent
    config = ConfigLoader(
        root / "config" / "topology.yaml",
        root / "config" / "pipeline_params.yaml",
    )
    topo = config.load_topology()
    raw_dir = root / topo["data_paths"]["raw_dir"]
    converter = DSBConverter(config)
    converter.convert_all(raw_dir)


if __name__ == "__main__":
    main()
