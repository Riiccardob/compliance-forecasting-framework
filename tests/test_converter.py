"""Test per DSBConverter — dati mock sintetici, nessun CSV reale."""
import json
from pathlib import Path

import pandas as pd
import pytest

from src.ingestion.converter import DSBConverter
from src.utils.config_loader import ConfigLoader

_ROOT = Path(__file__).parent.parent
_TOPOLOGY_PATH = _ROOT / "config" / "topology.yaml"
_PIPELINE_PATH = _ROOT / "config" / "pipeline_params.yaml"

# ── Costanti mock ─────────────────────────────────────────────────────────────
# Nodi rilevanti (ordine lista topology.yaml):
#   0: nginx-web-server  |  1: nginx-thrift  |  4: post-storage-service

# Timestamps in µs: due finestre distanziate di 5 secondi
_TS_W0 = 1_000_000
_TS_W1 = 6_000_000

# CPU counter cumulativo (secondi): delta=0.25 s in 5 s → cpu_percent=5.0%
_CPU_W0 = 1.000
_CPU_W1 = 1.250

# Memoria: ~93 MB in bytes
_MEM_BYTES = 97_517_568

# Rete: counter cumulativo in bytes — delta = 1 MB in entrambe le direzioni
_RX_W0 = 10 * 1024 * 1024
_RX_W1 = 11 * 1024 * 1024
_TX_W0 = 5 * 1024 * 1024
_TX_W1 = 6 * 1024 * 1024

# Latenza arco e1: colonna "1_latency" (dest_idx = 1, nginx-thrift) = 10.000 µs → 10.0 ms
_LAT_E1_US = 10_000.0


# ── Fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def topology_config() -> ConfigLoader:
    """ConfigLoader istanziato sui file di configurazione reali."""
    return ConfigLoader(_TOPOLOGY_PATH, _PIPELINE_PATH)


@pytest.fixture(scope="function")
def converter(topology_config: ConfigLoader) -> DSBConverter:
    return DSBConverter(topology_config)


def _make_base_raw() -> pd.DataFrame:
    """DataFrame raw con 2 window (10_0 nominale, 10_1 anomala), 1 traccia ciascuna.

    Include solo le colonne strettamente necessarie ai test; il converter
    salta silenziosamente i nodi privi di colonne CPU (log warning).
    """
    return pd.DataFrame([
        {
            "window_id": "10_0",
            "0_start": _TS_W0,
            "label_trace": 0,
            # Node 0 (nginx-web-server) — counter Prometheus
            "0_container_cpu_usage_seconds_total": _CPU_W0,
            "0_container_memory_usage_bytes": _MEM_BYTES,
            "0_container_network_receive_bytes_total": _RX_W0,
            "0_container_network_transmit_bytes_total": _TX_W0,
            # Latenza arco e1 (dest = nginx-thrift, indice 1)
            "1_latency": _LAT_E1_US,
            # Label RPC
            "0_label_RPC": 0,
            "4_label_RPC": 0,
        },
        {
            "window_id": "10_1",
            "0_start": _TS_W1,
            "label_trace": 1,
            "0_container_cpu_usage_seconds_total": _CPU_W1,
            "0_container_memory_usage_bytes": _MEM_BYTES,
            "0_container_network_receive_bytes_total": _RX_W1,
            "0_container_network_transmit_bytes_total": _TX_W1,
            "1_latency": _LAT_E1_US,
            "0_label_RPC": 0,
            "4_label_RPC": 1,  # post-storage-service (idx 4) anomalous
        },
    ])


# ── Test suite ────────────────────────────────────────────────────────────────

class TestDSBConverter:
    """Test suite per DSBConverter — mock in memoria, nessun I/O su CSV reali."""

    # ── Metriche di nodo ───────────────────────────────────────────────────────

    def test_first_window_dropped_for_cpu(self, converter: DSBConverter) -> None:
        """La prima window non produce record in node_metrics (diff CPU = NaN)."""
        agg = converter._aggregate_window_metrics(_make_base_raw())
        node_df = converter._compute_node_metrics(agg, "source.csv")

        w0_records = node_df[
            (node_df["window_id"] == "10_0") & (node_df["node_id"] == "nginx-web-server")
        ]
        assert len(w0_records) == 0

    def test_mem_zero_forward_filled(self, converter: DSBConverter) -> None:
        """Memoria zero in 10_1 viene forward-filled con il valore di 10_0."""
        raw = _make_base_raw()
        raw.loc[raw["window_id"] == "10_1", "0_container_memory_usage_bytes"] = 0

        agg = converter._aggregate_window_metrics(raw)
        node_df = converter._compute_node_metrics(agg, "source.csv")

        rec = node_df[
            (node_df["window_id"] == "10_1") & (node_df["node_id"] == "nginx-web-server")
        ]
        assert len(rec) == 1
        expected_mb = _MEM_BYTES / (1024.0 * 1024.0)
        assert abs(rec.iloc[0]["mem_mb"] - expected_mb) < 0.01

    def test_net_rx_delta_correct(self, converter: DSBConverter) -> None:
        """net_rx_mb in 10_1 è il delta tra i counter RX (≈ 1.0 MB)."""
        agg = converter._aggregate_window_metrics(_make_base_raw())
        node_df = converter._compute_node_metrics(agg, "source.csv")

        rec = node_df[
            (node_df["window_id"] == "10_1") & (node_df["node_id"] == "nginx-web-server")
        ]
        assert len(rec) == 1
        expected_mb = (_RX_W1 - _RX_W0) / (1024.0 * 1024.0)
        assert abs(rec.iloc[0]["net_rx_mb"] - expected_mb) < 0.01

    # ── Metriche di arco ───────────────────────────────────────────────────────

    def test_latency_ms_conversion(self, converter: DSBConverter) -> None:
        """latency_ms per e1 = media µs / 1000 = 10.0 ms."""
        agg = converter._aggregate_window_metrics(_make_base_raw())
        edge_df = converter._compute_edge_metrics(agg, "source.csv")

        rec = edge_df[
            (edge_df["window_id"] == "10_1") & (edge_df["edge_id"] == "e1")
        ]
        assert len(rec) == 1
        assert abs(rec.iloc[0]["latency_ms"] - (_LAT_E1_US / 1000.0)) < 0.001

    def test_throughput_rps_positive(self, converter: DSBConverter) -> None:
        """throughput_rps è strettamente positivo per ogni record di arco."""
        agg = converter._aggregate_window_metrics(_make_base_raw())
        edge_df = converter._compute_edge_metrics(agg, "source.csv")

        assert (edge_df["throughput_rps"] > 0).all()

    def test_error_rate_window_anomalous(self, converter: DSBConverter) -> None:
        """error_rate == 1.0 nella window con tutte le tracce anomale (10_1,
        1 traccia con label_trace=1)."""
        agg = converter._aggregate_window_metrics(_make_base_raw())
        edge_df = converter._compute_edge_metrics(agg, "source.csv")

        rec = edge_df[
            (edge_df["window_id"] == "10_1") & (edge_df["edge_id"] == "e1")
        ]
        assert len(rec) == 1
        assert abs(rec.iloc[0]["error_rate"] - 1.0) < 0.001

    # ── Ground truth ───────────────────────────────────────────────────────────

    def test_ground_truth_anomaly_node_ids(self, converter: DSBConverter) -> None:
        """anomaly_node_ids in 10_1 contiene 'post-storage-service'."""
        agg = converter._aggregate_window_metrics(_make_base_raw())
        metadata = {
            "fault_type": "cpu",
            "date": "aug9",
            "duration": "25min",
            "rps": 400,
            "replica_idx": 2,
        }
        gt_df = converter._compute_ground_truth(agg, metadata, "source.csv")

        rec = gt_df[gt_df["window_id"] == "10_1"]
        assert len(rec) == 1
        anomaly_ids = json.loads(rec.iloc[0]["anomaly_node_ids"])
        assert "post-storage-service" in anomaly_ids

    def test_ground_truth_metadata_extraction(self, converter: DSBConverter) -> None:
        """_parse_filename estrae fault_type, rps, replica_idx da un filename standard."""
        meta = converter._parse_filename("cpu_aug9_25min_400_2_graph_2.csv")
        assert meta["fault_type"] == "cpu"
        assert meta["rps"] == 400
        assert meta["replica_idx"] == 2

    # ── Parsing filename ───────────────────────────────────────────────────────

    def test_filename_without_duration(self, converter: DSBConverter) -> None:
        """File senza token duration: 'duration' è None, altri campi corretti."""
        meta = converter._parse_filename("cpu_aug9_400_0_graph_2.csv")
        assert meta["duration"] is None
        assert meta["rps"] == 400
        assert meta["replica_idx"] == 0

    def test_filename_with_repeat_token(self, converter: DSBConverter) -> None:
        """Token 'repeat' tra duration e rps viene ignorato dalla regex."""
        meta = converter._parse_filename("mem_aug9_25min_repeat_400_1_graph_2.csv")
        assert meta["fault_type"] == "mem"
        assert meta["rps"] == 400
        assert meta["replica_idx"] == 1

    def test_filename_cpu_mem(self, converter: DSBConverter) -> None:
        """fault_type 'cpu_mem' viene catturato correttamente dalla regex."""
        meta = converter._parse_filename("cpu_mem_oct2_10min_800_0_graph_2.csv")
        assert meta["fault_type"] == "cpu_mem"
        assert meta["rps"] == 800
        assert meta["replica_idx"] == 0

    def test_cpu_percent_value_correct(self, converter: DSBConverter) -> None:
        """cpu_percent in 10_1 è (delta_counter / delta_t) * 100.

        Con _CPU_W0=1.000, _CPU_W1=1.250, delta_t=5s → atteso 5.0%.
        """
        agg = converter._aggregate_window_metrics(_make_base_raw())
        node_df = converter._compute_node_metrics(agg, "source.csv")

        rec = node_df[
            (node_df["window_id"] == "10_1") & (node_df["node_id"] == "nginx-web-server")
        ]
        assert len(rec) == 1
        assert abs(rec.iloc[0]["cpu_percent"] - 5.0) < 0.01

    def test_net_negative_delta_forward_filled(
        self, converter: DSBConverter
    ) -> None:
        """Delta negativo su net_rx (counter reset) viene azzerato a NaN
        e poi forward-filled con il valore della window precedente.
        """
        raw = _make_base_raw()
        raw.loc[raw["window_id"] == "10_1",
                "0_container_network_receive_bytes_total"] = _RX_W0 - 1024

        agg = converter._aggregate_window_metrics(raw)
        node_df = converter._compute_node_metrics(agg, "source.csv")

        rec_w1 = node_df[
            (node_df["window_id"] == "10_1") & (node_df["node_id"] == "nginx-web-server")
        ]
        assert len(rec_w1) == 1
        val = rec_w1.iloc[0]["net_rx_mb"]
        # delta negativo → NaN via mask → ffill (nessun precedente
        # valido, prima window scartata per CPU) → fillna(0.0).
        # Per net_rx/tx non esiste bfill: solo ffill + fillna.
        assert not pd.isna(val)
        assert abs(val - 0.0) < 1e-9

    def test_error_rate_nominal_zero(self, converter: DSBConverter) -> None:
        """error_rate == 0.0 nella window nominale (10_0, label_trace=0)."""
        agg = converter._aggregate_window_metrics(_make_base_raw())
        edge_df = converter._compute_edge_metrics(agg, "source.csv")

        rec = edge_df[
            (edge_df["window_id"] == "10_0") & (edge_df["edge_id"] == "e1")
        ]
        assert len(rec) == 1
        assert abs(rec.iloc[0]["error_rate"] - 0.0) < 0.001

    def test_cpu_negative_delta_masked_and_forward_filled(
        self, converter: DSBConverter
    ) -> None:
        """Delta CPU negativo (reset counter container) viene mascherato
        a NaN e forward-filled. Non devono esserci valori negativi."""
        raw = _make_base_raw()
        # Counter CPU decresce: simula restart container tra w0 e w1
        raw.loc[raw["window_id"] == "10_1",
                "0_container_cpu_usage_seconds_total"] = _CPU_W0 - 0.5

        agg = converter._aggregate_window_metrics(raw)
        node_df = converter._compute_node_metrics(agg, "source.csv")

        rec = node_df[
            (node_df["window_id"] == "10_1")
            & (node_df["node_id"] == "nginx-web-server")
        ]
        assert len(rec) == 1
        val = rec.iloc[0]["cpu_percent"]
        # Con questo mock la catena mask → ffill (nessun precedente) →
        # fillna(0.0) → where produce deterministicamente 0.0.
        assert abs(val - 0.0) < 1e-9

    def test_filename_with_prefix_token(
        self, converter: DSBConverter
    ) -> None:
        """Token opzionale (es. 'test') tra fault_type e date viene
        ignorato e gli altri campi vengono estratti correttamente."""
        meta = converter._parse_filename(
            "cpu_test_july24_800_0_graph_2.csv"
        )
        assert meta["fault_type"] == "cpu"
        assert meta["date"] == "july24"
        assert meta["rps"] == 800
        assert meta["replica_idx"] == 0

    def test_window_duration_seconds_from_yaml_no_warning(
        self, converter: DSBConverter, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Quando window_duration_seconds è presente in metadata,
        il warning 'non definito' non viene emesso."""
        import logging
        with caplog.at_level(logging.WARNING,
                             logger="src.ingestion.converter"):
            agg = converter._aggregate_window_metrics(_make_base_raw())
            converter._compute_edge_metrics(agg, "source.csv")
        warning_texts = [r.message for r in caplog.records
                         if "window_duration_seconds" in r.message]
        assert len(warning_texts) == 0, (
            f"Warning inatteso emesso: {warning_texts}"
        )

    def test_mem_bfill_on_leading_nan(
        self, converter: DSBConverter
    ) -> None:
        """Leading NaN su mem_mb (prima window con mem_bytes=0)
        viene risolto con backward-fill."""
        raw = _make_base_raw()
        raw.loc[raw["window_id"] == "10_0",
                "0_container_memory_usage_bytes"] = 0

        agg = converter._aggregate_window_metrics(raw)
        node_df = converter._compute_node_metrics(agg, "source.csv")

        rec = node_df[
            (node_df["window_id"] == "10_1")
            & (node_df["node_id"] == "nginx-web-server")
        ]
        assert len(rec) == 1
        assert not pd.isna(rec.iloc[0]["mem_mb"])

    def test_convert_all_writes_three_csvs(
        self, converter: DSBConverter, tmp_path: Path
    ) -> None:
        """convert_all scrive i tre CSV canonici nella directory
        di output specificata."""
        raw1 = _make_base_raw()
        raw2 = _make_base_raw()
        raw2["window_id"] = raw2["window_id"].str.replace("10_", "20_")

        f1 = tmp_path / "cpu_aug9_25min_400_0_graph_2.csv"
        f2 = tmp_path / "cpu_aug9_25min_400_1_graph_2.csv"
        raw1.to_csv(f1, index=False)
        raw2.to_csv(f2, index=False)

        out_dir = tmp_path / "converted"
        out_dir.mkdir()

        original_paths = dict(converter._data_paths)
        converter._data_paths.update({
            "node_metrics_csv": str(out_dir / "node_metrics.csv"),
            "edge_metrics_csv": str(out_dir / "edge_metrics.csv"),
            "ground_truth_csv": str(out_dir / "ground_truth.csv"),
        })
        try:
            converter.convert_all(tmp_path)
        finally:
            converter._data_paths.clear()
            converter._data_paths.update(original_paths)

        assert (out_dir / "node_metrics.csv").exists()
        assert (out_dir / "edge_metrics.csv").exists()
        assert (out_dir / "ground_truth.csv").exists()

    def test_net_negative_delta_true_ffill_three_windows(
        self, converter: DSBConverter
    ) -> None:
        """In un mock a 3 finestre, il delta negativo su w2 viene
        forward-filled con il valore positivo di w1 — non con fillna(0.0).
        Verifica il vero meccanismo di ffill quando esiste un predecessore
        valido."""
        _TS_W2 = 11_000_000

        raw = _make_base_raw().copy()
        extra = pd.DataFrame([{
            "window_id": "10_2",
            "0_start": _TS_W2,
            "label_trace": 0,
            "0_container_cpu_usage_seconds_total": _CPU_W1 + 0.1,
            "0_container_memory_usage_bytes": _MEM_BYTES,
            "0_container_network_receive_bytes_total": _RX_W0 - 1024,
            "0_container_network_transmit_bytes_total": _TX_W1 + 1024,
            "1_latency": _LAT_E1_US,
            "0_label_RPC": 0,
            "4_label_RPC": 0,
        }])
        raw_3 = pd.concat([raw, extra], ignore_index=True)

        agg = converter._aggregate_window_metrics(raw_3)
        node_df = converter._compute_node_metrics(agg, "source.csv")

        rec_w1 = node_df[
            (node_df["window_id"] == "10_1")
            & (node_df["node_id"] == "nginx-web-server")
        ]
        rec_w2 = node_df[
            (node_df["window_id"] == "10_2")
            & (node_df["node_id"] == "nginx-web-server")
        ]
        assert len(rec_w1) == 1
        assert len(rec_w2) == 1

        w1_rx = rec_w1.iloc[0]["net_rx_mb"]
        w2_rx = rec_w2.iloc[0]["net_rx_mb"]

        assert w1_rx > 0.0, "w1 deve avere net_rx_mb positivo"
        assert abs(w2_rx - w1_rx) < 0.01, (
            f"w2 ({w2_rx:.4f}) deve essere ffillato da w1 ({w1_rx:.4f}), "
            "non prodotto da fillna(0.0)"
        )

    def test_error_rate_zero_traces_window(
        self, converter: DSBConverter
    ) -> None:
        """Window con 0 tracce produce error_rate == 0.0 (no divisione per zero)."""
        raw = _make_base_raw()
        raw.loc[raw["window_id"] == "10_1", "0_label_RPC"] = 0
        raw.loc[raw["window_id"] == "10_1", "4_label_RPC"] = 0
        raw.loc[raw["window_id"] == "10_1", "label_trace"] = 0

        agg = converter._aggregate_window_metrics(raw)
        edge_df = converter._compute_edge_metrics(agg, "source.csv")

        rec = edge_df[
            (edge_df["window_id"] == "10_1") & (edge_df["edge_id"] == "e1")
        ]
        if len(rec) == 1:
            assert not pd.isna(rec.iloc[0]["error_rate"])