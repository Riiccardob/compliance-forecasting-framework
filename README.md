<div align="center">

# Hybrid Hypergraph-ATG — `gamma-synthetic` branch

**Adaptive Forecasting Validation with GAMMA Augmented Dataset**

[![CI](https://github.com/Riiccardob/hybrid-hypergraph-atg/actions/workflows/ci.yml/badge.svg?branch=gamma-synthetic)](https://github.com/Riiccardob/hybrid-hypergraph-atg/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

</div>

> **You are on the `gamma-synthetic` branch.**  
> This branch extends `main` with the GAMMA augmented dataset pipeline,
> adding `GammaRampInjector` and the per-source-file Adaptive Forecasting runner
> to validate variable lead time (`lead_time_steps > 1`) on real telemetry.
>
> For installation, architecture, configuration reference, and general
> framework documentation see the [**`main` branch README**](../../tree/main).

---

## What this branch adds

| Component | Description |
|---|---|
| `src/ingestion/gamma_ramp_injector.py` | Injects a calibrated latency ramp into nominal windows of each GAMMA experiment |
| `run_gamma_ramp_injector.py` | Entry point for ramp injection; produces `edge_metrics_aug_ramp.csv` |
| `run_pipeline_gamma_aug.py` | Adaptive forecasting pipeline: global training + per-experiment EWMA pre-warm |
| `eval_batch_synthetic.py` | Aggregate evaluation of augmented pipeline results |
| `config/topology_gamma_aug.yaml` | Topology config with recalibrated SLA thresholds (284.4 ms / 45.0 ms) |

The core architecture (`src/`, `config/pipeline_params.yaml`, `dashboard/`, `tests/`) is
**identical to `main`**. The augmentation layer operates exclusively on `latency_ms`
in nominal windows and does not modify anomalous windows, labels, node metrics, or
per-arc throughput.

---

## Installation

```bash
git clone https://github.com/Riiccardob/hybrid-hypergraph-atg.git
cd hybrid-hypergraph-atg
git checkout gamma-synthetic

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

## Running the augmented pipeline

```bash
# 1. Convert raw GAMMA data (same as main)
python run_etl.py

# 2. Inject latency ramps into nominal windows
python run_gamma_ramp_injector.py

# 3. Run adaptive pipeline (per-source-file EWMA pre-warm)
python run_pipeline_gamma_aug.py

# 4. Aggregate evaluation
python eval_batch_synthetic.py --results-dir results/
```

---

## Running the tests

```bash
pytest tests/ -v
```

Tests are identical to `main`. See the `main` branch README for details.

---

## License

MIT — see [LICENSE](LICENSE).