<div align="center">

<<<<<<< HEAD
# Hybrid Hypergraph-ATG - `gamma-synthetic` branch

**Adaptive Forecasting Validation with GAMMA Augmented Dataset**
=======
# Hybrid Hypergraph-ATG

**Predictive Compliance Monitoring for Microservice Architectures**
>>>>>>> e5a0ff1 (add project documentation and setup files)

[![Python](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-306%20passing-brightgreen?logo=pytest)](tests/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
<<<<<<< HEAD

</div>

> **You are on the `gamma-synthetic` branch.**
> This branch extends `main` with the GAMMA augmented dataset pipeline,
> adding `GammaRampInjector` and the per-source-file Adaptive Forecasting runner
> to validate variable lead time (`lead_time_steps > 1`) on real telemetry.
>
> For installation, architecture, configuration reference, and general
> framework documentation see the [`main` branch README](../../tree/main).

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
git clone https://github.com/your-username/hybrid-hypergraph-atg.git
cd hybrid-hypergraph-atg
git checkout gamma-synthetic

python -m venv .venv
source .venv/bin/activate
=======
[![NetworkX](https://img.shields.io/badge/graph-NetworkX-orange)](https://networkx.org)
[![Prophet](https://img.shields.io/badge/forecast-Prophet%20%7C%20SARIMAX-blueviolet)](https://facebook.github.io/prophet/)

</div>

---

> **What this is not**: a generic anomaly detector that fires when a metric looks unusual.
>
> **What this is**: a system that predicts *which certified SLA will be violated*, *how many time windows ahead*, *which component will cause it*, and *whether a separate compliance property is also at risk* — all from microservice telemetry.

---

## What it does

Hybrid Hypergraph-ATG monitors distributed microservice systems against formal, contractual SLA definitions (called *compliance sets*). For each monitored property it:

- **Predicts** SLA violations before they occur, estimating lead time in discrete time windows
- **Attributes** each alert to the root-cause node via topology-guided causal analysis
- **Detects cross-property interference** when a fault on one certified path degrades another through shared infrastructure
- **Classifies alerts** in three criticality levels (YELLOW / ORANGE / RED) based on estimated lead time
- **Maintains zero false positives** on nominal windows — all models are trained exclusively on fault-free data

Detection combines four hierarchical signals: SLA threshold + adaptive z-score (Level 1), Isolation Forest on the multivariate feature vector (Level 2), CUSUM on probabilistic routing drift (Level 3), and a structural co-occurrence validator (Level 4). Any positive signal propagates to the alert layer.

---

## Which branch should I use?

| I want to… | Branch |
|---|---|
| Run the framework on real GAMMA/DeathStarBench telemetry | **`main`** ← start here |
| Understand root cause attribution and cross-property interference | **`main`** |
| Adapt the framework to a new microservice system | **`main`** |
| Study the Adaptive Forecasting mode with variable lead time (lead time > 1) | `gamma-synthetic` |
| Reproduce the latency ramp augmentation pipeline | `gamma-synthetic` |

**`main`** is the complete implementation validated on 184 fault injection experiments from GAMMA/DeathStarBench (4 fault types: CPU saturation, memory leak, network degradation, combined CPU+memory). Start here.

**`gamma-synthetic`** extends `main` with `GammaRampInjector`, which injects a calibrated latency ramp into nominal windows to create the pre-fault gradient required by the EWMA Trend Correction mechanism. The core architecture is identical across branches.

---

## Table of Contents

- [Requirements and Installation](#requirements-and-installation)
- [Data Setup](#data-setup)
- [Quick Start](#quick-start)
- [Project Structure](#project-structure)
- [Configuration](#configuration)
- [Step-by-Step Pipeline Guide](#step-by-step-pipeline-guide)
- [Understanding the Output](#understanding-the-output)
- [Dashboard](#dashboard)
- [Using Your Own Dataset](#using-your-own-dataset)
- [Synthetic Scenario](#synthetic-scenario)
- [Running the Tests](#running-the-tests)
- [Architecture Overview](#architecture-overview)

---

## Requirements and Installation

**Python 3.10 or higher** is required.

```bash
git clone https://github.com/Riiccardob/hybrid-hypergraph-atg.git
cd hybrid-hypergraph-atg

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
>>>>>>> e5a0ff1 (add project documentation and setup files)

pip install -r requirements.txt
```

<<<<<<< HEAD
`tqdm` is an optional but recommended dependency for the ramp injection progress bar:

```bash
pip install tqdm
=======
Core dependencies:

| Area | Libraries |
|---|---|
| Data manipulation | `pandas`, `numpy` |
| Graph modeling | `networkx` |
| Forecasting | `prophet`, `cmdstanpy` (Prophet's Stan backend), `statsmodels` |
| Anomaly detection | `scikit-learn` (Isolation Forest, linear regression) |
| Causal analysis | `scipy` (Pearson, Transfer Entropy) |
| Configuration | `pyyaml` |
| Dashboard | `dash`, `dash-mantine-components`, `plotly` |

For development and testing only:

```bash
pip install -r requirements-dev.txt   # pytest, coverage, ruff
```

Verify the installation:

```bash
python -c "from src.layer1.topology_builder import TopologyBuilder; print('OK')"
pytest tests/ -q --tb=no              # should report 306 passed
```

---

## Data Setup

The GAMMA dataset is not included in this repository. Download it from the [GAMMA project](https://github.com/NetManAIOps/GAMMA) and place the files in `data/raw/` following this structure:

```
data/raw/
└── multi-modal-data-separate/
    └── home/
        └── graph_2/
            ├── cpu_aug9_25min_400_0_graph_2.csv
            ├── mem_sep22_10min_800_0_graph_2.csv
            ├── ...                                (184 files total)
            ├── home_rps_start_time_1.csv
            └── home_rps_start_time_2.csv
```

The two `home_rps_start_time_*.csv` files are required for per-arc throughput disaggregation. Without them the converter falls back to uniform throughput, which degenerates the Probabilistic Behavioral Overlay and disables the CUSUM signal.

Then point `topology.yaml` to your `raw_dir`:

```yaml
data_paths:
  raw_dir: "data/raw/multi-modal-data-separate/home/graph_2"
  node_metrics_csv: "data/converted/node_metrics.csv"
  edge_metrics_csv: "data/converted/edge_metrics.csv"
  ground_truth_csv: "data/converted/ground_truth.csv"
>>>>>>> e5a0ff1 (add project documentation and setup files)
```

---

## Quick Start

<<<<<<< HEAD
The augmented pipeline has four steps instead of two.

```bash
# Step 1 - Convert raw GAMMA traces to canonical format (same as main)
python run_etl.py

# Step 2 - Inject latency ramp into nominal windows
python run_gamma_ramp_injector.py

# Step 3 - Run the adaptive forecasting pipeline
python run_pipeline_gamma_aug.py

# Step 4 - Evaluate aggregate results
python eval_batch_synthetic.py --results-dir results/
=======
```bash
# 1. Convert raw GAMMA traces to canonical format
python run_etl.py

# 2. Run the full pipeline
python run_pipeline.py

# 3. Launch the dashboard
python dashboard/app.py          # → http://localhost:8050
```

That is all. Both scripts read configuration from `config/topology.yaml` and `config/pipeline_params.yaml` automatically. No additional arguments are required for a standard run.

---

## Project Structure

```
hybrid-hypergraph-atg/
│
├── config/
│   ├── topology.yaml            # compliance sets, SLA thresholds, node/edge topology
│   └── pipeline_params.yaml     # algorithmic parameters (CUSUM, EWMA, IF, etc.)
│
├── src/
│   ├── utils/
│   │   ├── config_loader.py     # lazy YAML loader with eager key validation
│   │   └── logging_setup.py     # idempotent structured logger factory
│   │
│   ├── ingestion/
│   │   └── converter.py         # DSBConverter: GAMMA raw CSV → canonical format
│   │
│   ├── layer1/
│   │   └── topology_builder.py  # builds annotated NetworkX DiGraph from topology.yaml
│   │
│   ├── layer2/
│   │   ├── atg_builder.py       # ATG snapshot sequence G(t) assembly
│   │   └── pbo_builder.py       # stochastic W(t), PAS score, Frobenius norm
│   │
│   ├── layer3/
│   │   └── feature_selector.py  # derives M^Φ_i = M^direct ∪ M^interf per CS
│   │
│   ├── phase1/
│   │   └── stat_forecaster.py   # per-metric forecasting (Prophet/SARIMAX/Linear + EWMA)
│   │
│   ├── phase2/
│   │   └── causal_analyzer.py   # topology-guided causal graph (Granger/Pearson/TE)
│   │
│   ├── phase3/
│   │   └── structural_monitor.py # 4-level hierarchical detection
│   │
│   └── phase4/
│       └── alert_generator.py   # alert synthesis: lead time, criticality, root cause
│
├── tests/                       # 306 unit tests across 10 files (all in-memory)
│
├── dashboard/
│   └── app.py                   # Dash + Mantine dashboard
│
├── data/
│   ├── raw/                     # raw GAMMA files — not tracked by git
│   └── converted/               # canonical CSV output — not tracked by git
│
├── results/                     # pipeline JSON output — not tracked by git
│
├── run_etl.py                   # data conversion entry point
├── run_pipeline.py              # pipeline entry point
└── eval_batch.py                # aggregate evaluation
>>>>>>> e5a0ff1 (add project documentation and setup files)
```

---

<<<<<<< HEAD
## What each script does

### `run_gamma_ramp_injector.py`

No arguments. Reads `data/converted/edge_metrics_aug.csv` and
`data/converted/ground_truth.csv`, produces
`data/converted/edge_metrics_aug_ramp.csv`.

For each experiment (source file) it:
- Computes a per-experiment scale factor from the nominal H_crit latency baseline
- Injects a linear ramp into the last `n_ramp` nominal windows (capped at 0.90 × SLA)
- Skips experiments with fewer than 5 nominal windows or whose baseline already exceeds
  the ramp target
- Excludes experiments with the `cpu_aug12_25min_200_*` prefix (200 RPS, SLA irrelevant)

Prints a full verification report showing false positive counts before and after
injection (expected delta: 0 new FPs).

```
GammaRampInjector - 163 esperimenti da elaborare
  [0/163] cpu_aug10_25min_400_0_graph_2.csv
  ...
Scritto: data/converted/edge_metrics_aug_ramp.csv (9671 righe)

=== VERIFICA RAMP INJECTOR ===

Esperimenti esclusi (cpu_aug12_25min_200_*): 10
Esperimenti con rampa applicata: 157
Esperimenti copiati invariati (n_nominal < 5 o lat. alta): 6

FP H_crit  PRIMA del ramp: 30
FP H_crit  DOPO  del ramp: 0
Nuovi FP H_crit introdotti: 0    (ATTESO: 0)
FP H_cache PRIMA del ramp: 42
FP H_cache DOPO  del ramp: 0
Nuovi FP H_cache introdotti: 0   (ATTESO: 0)

Esperimenti rampati: 157
Esperimenti skippati (n_nominal < 5): 0
Righe modificate: 11.702
```

The 30 H_crit and 42 H_cache windows that were nominal by label but already exceeded
the SLA (pre-existing contradictions in the GAMMA corpus) are corrected to fall below
threshold as a side effect of the cap mechanism.

### `run_pipeline_gamma_aug.py`

```
--output FILE        JSON output path for the aggregate summary (optional)
--fault-type TYPE    filter to one fault type: cpu | mem | net | cpu_mem
--log-level LEVEL    DEBUG | INFO | WARNING | ERROR (default: WARNING)
```

```bash
# Full run
python run_pipeline_gamma_aug.py --output results/augmented_results.json

# Quick test: MEM fault type only
python run_pipeline_gamma_aug.py --fault-type mem --log-level INFO
```

**Architecture differences from `run_pipeline.py` (main branch):**

| Aspect | `main` (`run_pipeline.py`) | `gamma-synthetic` (`run_pipeline_gamma_aug.py`) |
|---|---|---|
| Config file | `config/topology.yaml` | `config/topology_gamma_aug.yaml` |
| Edge metrics input | `edge_metrics.csv` | `edge_metrics_aug_ramp.csv` |
| SLA H_crit | 100.0 ms | 284.4 ms (P99_nominal × 1.30) |
| SLA H_cache | 20.0 ms | 45.0 ms (P99_nominal × 1.30) |
| Forecasting mode | Fixed Prophet (no EWMA) | `predict_adaptive()` with per-experiment EWMA pre-warm |
| Training | Global, one session | Global, one session (9,671 nominal windows) |
| Inference | Per-snapshot, sequential | Per-source-file, with CUSUM/EWMA reset and 5-window pre-warm |
| `--limit` arg | Yes | No |
| JSON output structure | Single flat result | Per-source-file breakdown |

**Per-source-file adaptive inference loop:**

For each of the 163 source files the runner:
1. Resets the CUSUM accumulator and EWMA buffer
2. Pre-warms the EWMA buffer on the last `min(5, n_nominal)` nominal windows of that
   experiment
3. Runs `predict_adaptive()` on each anomalous window in chronological order
4. Collects lead time, criticality, root cause, and cross-property signals

This per-experiment reset is required to prevent CUSUM state from one experiment
contaminating the next.

### `eval_batch_synthetic.py`

```bash
python eval_batch_synthetic.py --results-dir results/
```

Reads all JSON files in `results/`, filters to valid experiment prefixes, and prints
per-compliance-set aggregate recall, lead time distribution, CUSUM rate, and
Frobenius range.

---

## Configuration for this branch

### `config/topology_gamma_aug.yaml`

Identical topology to `config/topology.yaml` but with recalibrated SLA thresholds
and augmented data paths:

```yaml
# SLA recalibrated on augmented corpus nominal P99:
compliance_sets:
  H_crit:
    sla:
      latency_ms: { bound: upper, threshold: 284.4 }   # P99_nom (218.8) × 1.30
  H_cache:
    sla:
      latency_ms: { bound: upper, threshold: 45.0 }    # P99_nom (34.6)  × 1.30

# Points to ramp-injected file instead of edge_metrics.csv:
data_paths:
  edge_metrics_csv: "data/converted/edge_metrics_aug_ramp.csv"
```

The SLA recalibration is mandatory. The original 100 ms threshold for H_crit was
calibrated on Scenario A corpus where the nominal aggregate H_crit latency is ~55 ms.
The augmented corpus has a different nominal distribution due to the excluded 200 RPS
experiments; using the original threshold would produce a trivial detection baseline.
=======
## Configuration

The framework uses two configuration files with distinct lifecycles.

### `config/topology.yaml` — what you monitor

Defines the certified system structure. Modify this when the architecture changes or SLA thresholds are renegotiated. This file should be versioned alongside the system's certification documentation.

```yaml
# ── Node and edge definitions ────────────────────────────────────────────────
nodes:
  - id: nginx-thrift
    description: "Internal Thrift proxy"
  - id: home-timeline-service
    description: "Timeline aggregation logic"
  # ... all 7 nodes

edges:
  - id: e2
    source: nginx-thrift
    target: home-timeline-service
    rps_path_type: "all"    # "all" | "graph_1" | "graph_2" — for per-arc throughput
  # ... all 6 edges

node_metrics: [cpu_percent, mem_mb, net_rx_mb, net_tx_mb]
edge_metrics:  [latency_ms, error_rate, throughput_rps]

# ── Compliance set definitions ───────────────────────────────────────────────
compliance_sets:
  H_crit:
    topology_type: linear           # linear | parallel
    nodes:
      - nginx-web-server
      - nginx-thrift
      - home-timeline-service
      - post-storage-service
      - post-storage-mongodb
    critical_path:
      sequence:                     # required for linear topology only
        - nginx-web-server
        - nginx-thrift
        - home-timeline-service
        - post-storage-service
        - post-storage-mongodb
    sla:
      latency_ms:   { bound: upper, threshold: 100.0 }
      error_rate:   { bound: upper, threshold: 0.05  }

  H_cache:
    topology_type: parallel
    nodes:
      - home-timeline-service
      - home-timeline-redis
      - post-storage-service
      - post-storage-memcached
    sla:
      latency_ms:   { bound: upper, threshold: 20.0  }
      error_rate:   { bound: upper, threshold: 0.10  }

# ── Dataset paths ────────────────────────────────────────────────────────────
data_paths:
  raw_dir:           "data/raw/multi-modal-data-separate/home/graph_2"
  node_metrics_csv:  "data/converted/node_metrics.csv"
  edge_metrics_csv:  "data/converted/edge_metrics.csv"
  ground_truth_csv:  "data/converted/ground_truth.csv"
```

### `config/pipeline_params.yaml` — how you monitor

Algorithmic parameters. Safe to update between tuning sessions without touching `topology.yaml`.

```yaml
pbo:
  weight_metric: throughput_rps
  gold_standard_label: 0            # label_trace value for nominal windows

forecasting:
  horizon: 12                       # τ: forecast steps ahead
  model_routing:
    default: prophet
    linear_metrics: [latency_ms]
  adaptive:
    ewma_alpha: 0.3                 # EWMA smoothing factor
    lookback_windows: 5             # pre-warm buffer length per experiment

causal_analysis:
  pearson_threshold:  0.6
  granger_max_lag:    3
  granger_threshold:  0.05
  te_threshold:       0.02

anomaly_detection:
  zscore_threshold: 2.5
  isolation_forest:
    contamination: 0.05
    n_estimators:  100
    random_state:  42
  cusum:
    k: 0.5                          # allowance parameter
    h: 5.0                          # decision threshold
    auto_calibrate_tolerance: true  # calibrate k from nominal data (parallel topologies)
  structural_validator:
    require_both: true              # Level 4: require cusum AND if signal simultaneously

alert:
  criticality_thresholds:
    yellow: 3                       # lead_time_steps >= 3 → YELLOW
    orange: 2                       # lead_time_steps == 2 → ORANGE
    red: 1                          # lead_time_steps == 1 → RED
  step_duration_hours: 24.0         # projected duration of one forecast step
```

---

## Step-by-Step Pipeline Guide

### Step 1 — Data conversion

```bash
python run_etl.py
```

`run_etl.py` reads `data_paths.raw_dir` from `topology.yaml`, processes all `*_graph_2.csv` files recursively, and writes three canonical CSV files to the paths declared under `data_paths`. Output paths are overwritten on each run.

Sample `edge_metrics.csv` rows after conversion:

```
timestamp,edge_id,source,target,latency_ms,error_rate,throughput_rps,source_file
1663843200000000,e1,nginx-web-server,nginx-thrift,3.21,0.0,412.0,mem_sep22_10min_800_0_graph_2.csv
1663843200000000,e2,nginx-thrift,home-timeline-service,38.74,0.0,412.0,mem_sep22_10min_800_0_graph_2.csv
1663843200000000,e3,home-timeline-service,home-timeline-redis,8.11,0.0,93.0,mem_sep22_10min_800_0_graph_2.csv
1663843200000000,e4,home-timeline-service,post-storage-service,9.02,0.0,319.0,mem_sep22_10min_800_0_graph_2.csv
```

The converter handles three edge cases: negative CPU deltas (counter reset on container restart) are backfilled from the previous window; zero memory values (GAMMA missing-data sentinel) receive the same treatment; leading NaN values (no predecessor for the first window) are forward-filled or defaulted to 0.0. The first window of every source file is discarded because the CPU delta requires a prior sample.

### Step 2 — Run the pipeline

```bash
python run_pipeline.py
```

Config is read automatically from `config/topology.yaml` and `config/pipeline_params.yaml`. All optional arguments:

```
--output FILE        output JSON path (default: results/pipeline_results.json)
--fault-type TYPE    run inference only on one fault type: cpu | mem | net | cpu_mem
--limit N            limit to the first N anomalous snapshots (useful for quick tests)
--log-level LEVEL    internal module log verbosity: DEBUG | INFO | WARNING | ERROR
                     (default: WARNING — keeps stdout readable)
```

Examples:

```bash
# Full run, save to a custom path
python run_pipeline.py --output results/run_20240901.json

# Quick test: only first 200 MEM anomalous snapshots
python run_pipeline.py --fault-type mem --limit 200 --log-level INFO
```

Execution phases printed to stdout:

```
========================================================================
  INIZIALIZZAZIONE
========================================================================
[BUILD]  topology loaded — 7 nodes, 6 edges, 2 compliance sets
[TRAIN]  fitting on 11,093 nominal snapshots (label_trace = 0)
         StatForecaster ... done  (Prophet: 8 series)
         CausalAnalyzer ... done  (H_crit: 75 links, H_cache: 69 links + 24 cross-property)
         StructuralMonitor ... done  (Isolation Forest, CUSUM baseline)
[INFER]  19,112 snapshots — 8,019 anomalous
         ...
========================================================================
  RIEPILOGO FINALE
========================================================================
H_crit
  Alert:    8019/8019 (100.0%)
  RED:      8019 (100.0%)
  base_signal: 99.8%  if_signal: 4.2%  cusum: 98.8%  confirmed: 0.0%
  root_cause: 100.0%  cross_prop: 0.0%  uncertainty: 0.0%

H_cache
  Alert:    8019/8019 (100.0%)
  ORANGE:   8019 (100.0%)
  base_signal: 99.6%  if_signal: 5.2%  cusum: 99.6%  confirmed: 0.4%
  root_cause: 100.0%  cross_prop: 100.0%  uncertainty: 100.0%

Tempo di esecuzione totale: 847s
```
>>>>>>> e5a0ff1 (add project documentation and setup files)

---

## Understanding the Output

<<<<<<< HEAD
`run_pipeline_gamma_aug.py` writes a JSON with per-source-file results:

```json
{
  "corpus": {
    "n_nominal": 9671,
    "n_anomalous": 6818,
    "n_processed": 163,
    "n_excluded": 21
  },
  "fp": { "H_crit": 0, "H_cache": 0 },
  "lead_time_dist": { "1": 1778, "2": 103, "3": 48, "4": 32, "5": 14, "6": 11,
                      "7": 6, "8": 14, "9": 10, "10": 6, "11": 9, "12": 13 },
  "criticality_dist": { "red": 1777, "orange": 234, "yellow": 33 },
  "per_source_file": {
    "mem_sep22_10min_800_0_graph_2.csv": {
      "H_crit": {
        "n_anomalous": 23,
        "n_alerts": 18,
        "recall": 0.782,
        "lead_time_dist": { "1": 15, "3": 2, "5": 1 },
        "cusum_signal_rate": 0.48
      },
      "H_cache": { ... }
    }
  },
  "elapsed_seconds": 3412.0
}
```

**Key metrics:**

- Lead time is variable (1–12 steps) unlike `main` where it is always 1. The 266 alerts
  with `lead_time_steps > 1` (13% of total) represent genuine advance notice.
- Recall varies by fault type: CPU 2.7% (correct - CPU faults do not violate the
  284.4 ms SLA), MEM 77.9%, cpu_mem 88.5%, NET 43.8%.
- 0 false positives on 9,671 nominal windows for both compliance sets.

---

## Expected results (Scenario B)

| Metric | H_crit | H_cache |
|---|---|---|
| Corpus anomalous windows | 6,818 | 6,818 |
| False positives (nominal) | 0 / 9,671 | 0 / 9,671 |
| Recall cpu | 2.7% | 2.0% |
| Recall cpu\_mem | 88.5% | 86.0% |
| Recall mem | 77.9% | 84.5% |
| Recall net | 43.8% | 48.3% |
| Lead time distinct values | 12 (1–12 steps) | - |
| Alerts with lead time > 1 | 266 / 2,044 (13%) | - |
| CUSUM rate (MEM) | 48.0% | 55.7% |
| CUSUM rate (cpu\_mem) | 61.3% | 67.7% |
| PAS_gold | 0.3697 (non-degenerate) | - |
| Cross-property (MEM exps) | - | 100% |
=======
The pipeline writes a single JSON file to `--output` (default: `results/pipeline_results.json`).

### Top-level structure

```json
{
  "dataset_stats": { ... },
  "pbo_diagnostics": {
    "H_crit": { "pas_gold": 0.321, "pas_degenerate": false },
    "H_cache": { "frobenius_mean": 0.157, "frobenius_degenerate": false }
  },
  "compliance_sets": {
    "H_crit": { ... },
    "H_cache": { ... }
  },
  "elapsed_seconds": 847.3
}
```

### Per compliance set

```json
{
  "feature_count": 32,
  "feature_breakdown": { "node": 20, "edge": 12, "interf": 0 },
  "causal_graph_summary": {
    "edges": 75, "cross_property": 0, "confirmed": 0
  },
  "monitor_stats": {
    "base_signal_rate": 0.998,
    "if_signal_rate": 0.042,
    "cusum_signal_rate": 0.988,
    "structural_confirmed_rate": 0.0
  },
  "alert_stats": {
    "count": 8019,
    "recall": 1.0,
    "criticality": { "red": 8019 },
    "lead_time_steps_mean": 1.0,
    "lead_time_dist": { "1": 8019 },
    "root_cause_rate": 1.0,
    "cross_property_rate": 0.0,
    "uncertainty_flag_rate": 0.0,
    "root_cause_top5": {
      "node:home-timeline-service:mem_mb": 8019
    },
    "critical_arc_top5": { "e2": 8019 }
  },
  "alerts": [ ... ]
}
```

### Individual alert

```json
{
  "compliance_set": "H_cache",
  "property_at_risk": "latency_ms",
  "criticality": "orange",
  "lead_time_steps": 1,
  "lead_time_hours": 24.0,
  "sla_threshold": 20.0,
  "sla_bound": "upper",
  "critical_arc": "e4",
  "root_cause": "node:post-storage-service:mem_mb",
  "cross_property_interference": "H_crit",
  "causal_chain": [
    "interf:e2:throughput_rps",
    "node:home-timeline-service:cpu_percent",
    "edge:e3:latency_ms"
  ],
  "model_uncertainty_flag": true,
  "anomaly_type": "latency_violation",
  "structural_signals": {
    "base_signal": true,
    "if_signal": false,
    "cusum_signal": true,
    "structural_confirmed": false
  },
  "aggregated_forecast": [251.9, 253.1, 254.4, 255.8, 257.1, 258.5]
}
```

**Field reference:**

| Field | Meaning |
|---|---|
| `lead_time_steps` | Windows of advance notice before the forecast SLA violation. `1` means the violation is in the current or next window. |
| `lead_time_hours` | `lead_time_steps × step_duration_hours` from `pipeline_params.yaml`. Operational interpretation of the lead time. |
| `criticality` | `red` ≤ 1 step, `orange` = 2 steps, `yellow` ≥ 3 steps (thresholds in `pipeline_params.yaml`). |
| `root_cause` | `node:<name>:<metric>` — the node-metric pair with the strongest causal link to the violated metric in the nominal causal graph. |
| `critical_arc` | Arc with the highest latency contribution to the aggregated SLA violation. |
| `cross_property_interference` | The compliance set whose traffic is causing interference on this one, or `null`. |
| `causal_chain` | Three-step interference path: external arc → shared node metric → internal arc latency. |
| `model_uncertainty_flag` | `true` when the current observation is far outside the nominal training distribution. Expected `true` for all H_cache alerts (low nominal variance → any anomalous value diverges). Triggers criticality downgrade from `red` to `orange`. |
| `structural_confirmed` | Level 4 validator: `true` only when CUSUM and Isolation Forest fire simultaneously. |
| `aggregated_forecast` | τ-step Prophet forecast values (ms) on the certified path. |

---

## Dashboard

```bash
python dashboard/app.py
# → http://localhost:8050
```

The dashboard runs against the data in `data/converted/` and the results in `results/`. Run the pipeline before launching it.

The interface is built with [Dash Mantine Components](https://www.dash-mantine-components.com/) and provides:

- **Section 0 — Import**: canonical CSV schema viewer and dataset statistics
- **Section 1 — Topology**: interactive compliance set explorer with node/edge membership
- **Section 2 — Training**: feature selection summary, causal graph, PBO gold standard
- **Section 3 — Monitor**: per-window signal activation across the 4-level hierarchy
- **Section 4 — Alerts**: searchable alert table with criticality, root cause, cross-property chains
- **Section 5 — Routing drift**: W(t) time series with PAS / Frobenius distance and CUSUM threshold overlay

---

## Using Your Own Dataset

The only dataset-specific component is `src/ingestion/converter.py` (class `DSBConverter`). Everything downstream consumes the canonical three-file CSV format.

### 1. Write a converter

Subclass or replace `DSBConverter` with a class that produces the three canonical files:

| File | Key | Required columns |
|---|---|---|
| `node_metrics.csv` | `(timestamp, node_id)` | `cpu_percent`, `mem_mb`, `net_rx_mb`, `net_tx_mb` |
| `edge_metrics.csv` | `(timestamp, edge_id)` | `latency_ms`, `error_rate`, `throughput_rps`, `source`, `target` |
| `ground_truth.csv` | `timestamp` | `label_trace` (0/1), `fault_type`, `anomaly_node_ids` (JSON list) |

Timestamps must be 64-bit integers in microseconds. `throughput_rps` must be per-arc (not per-node aggregate) for a non-degenerate PBO and active CUSUM signal.

Update `run_etl.py` to call your converter.

### 2. Define your topology

Create `config/topology.yaml` for your system: nodes, edges with `rps_path_type` annotations, compliance sets with SLA thresholds and (for linear topologies) the certified critical path sequence.

### 3. Configure parameters

Tune `config/pipeline_params.yaml`. Set `auto_calibrate_tolerance: true` in the CUSUM section to calibrate the allowance parameter automatically from nominal data, which is recommended for parallel topologies.

### 4. Run

```bash
python run_etl.py && python run_pipeline.py
```

---

## Synthetic Scenario

The `gamma-synthetic` branch includes a fully self-contained scenario that requires no external dataset. It models an 8-node SaaS Monitoring Platform.

```
api-gateway ──e1──► metrics-ingestor ──e2──► data-enricher ──e3──► stream-processor ──e4──► storage-writer
     │                                                                     │
     └──────────e5──────────────────────────────────────────────────────── ├──e6──► analysis-engine
                                                                            ├──e7──► alert-dispatcher
                                                                            └──e8──► report-generator
```

Two compliance sets: **H_ingest** (linear, SLA 70ms) and **H_analysis** (parallel, SLA 120ms). Shared nodes: `api-gateway`, `stream-processor`. Cross-property interference path: `data-enricher → stream-processor` (e3 ∈ H_ingest targets `stream-processor` ∈ H_analysis).

```bash
git checkout gamma-synthetic

# Generate synthetic data (no external files needed)
python synthetic_generator_v2.py \
    --n-nominal 60 --n-ramp 25 --n-anomalous 30 --seed 42

# Run adaptive pipeline
python run_pipeline.py --output results/synthetic_results.json

# Evaluate
python eval_batch_synthetic.py --results-dir results/
```

The synthetic generator produces scenarios with continuous latency ramps (not step functions), variable ramp rates (0.7×, 1.0×, 1.4×), and deterministic faults for full reproducibility.
>>>>>>> e5a0ff1 (add project documentation and setup files)

---

## Running the Tests

<<<<<<< HEAD
Tests are identical to `main`. See the `main` branch README for details.

```bash
pytest tests/ -v
```

=======
```bash
pytest tests/ -v
pytest tests/ --cov=src --cov-report=term-missing
```

306 test cases across 10 files. All tests operate on in-memory data structures; no test reads from disk (except `ConfigLoader` tests that use `tmp_path`). A full run completes in under 10 seconds.

| Category | What is verified |
|---|---|
| Output structure | DataFrame shape, column names, index types, dtypes |
| Numerical correctness | Computed values vs. closed-form expectations with explicit tolerances |
| Edge cases | NaN inputs, empty feature vectors, single-window training sets, zero-variance features |
| Idempotency | `build()` and `fit()` return identical results on repeated calls |
| Cache isolation | ConfigLoader returns deep copies; external mutation does not corrupt shared state |
| Hierarchy invariants | No circular imports between layers (verified implicitly by import order) |

---

## Architecture Overview

### Module dependency graph

```
topology.yaml          pipeline_params.yaml
      │                         │
      ▼                         ▼
 ConfigLoader ─────────────────────────────────┐
      │                                         │
      ▼                                         │
 TopologyBuilder (Layer 1)                     │
      │                                         │
      ▼                                         │
 ATGBuilder + PBOBuilder (Layer 2)             │
      │                                         │
      ▼                                         ▼
 FeatureSelector (Layer 3)               pipeline_params
      │
      ├──► StatForecaster (Phase I)
      ├──► CausalAnalyzer (Phase II)
      └──► StructuralMonitor (Phase III)
                │
                ▼
           AlertGenerator (Phase IV)
                │
                ▼
         results/*.json  ──►  Dashboard
```

Dependencies flow downward only. `StructuralMonitor` may import from Layer 2, never from `AlertGenerator`. This invariant is verified by the test suite import sequence.

### Detection levels

| Level | Signal key | Activates when |
|---|---|---|
| 1a | `base_signal` | `aggregated_latency(t) > SLA_threshold` |
| 1b | `base_signal` | `(metric(t) − μ_nominal) / σ_nominal > zscore_threshold` |
| 2 | `if_signal` | joint feature vector `M^Φ_i(t)` classified as anomalous by Isolation Forest |
| 3 | `cusum_signal` | cumulative routing drift `‖W(t) − W_gold‖_F` exceeds threshold `h` |
| 4 | `structural_confirmed` | Level 3 AND Level 2 simultaneously active |

Any positive signal from any level produces an alert propagated to Phase IV.

### Key design invariants

- **Training isolation**: all models fit exclusively on `label_trace = 0` snapshots. No anomalous data ever enters training.
- **Static causal graph**: `CausalAnalyzer` builds the causal graph once on nominal data and holds it fixed during inference. Updating it at inference time would conflate anomaly signals with model adaptation.
- **No hardcoding**: all thresholds and parameters are read from YAML at startup. Test expectations are computed from the loaded configuration, so the test suite remains valid as the config evolves.
- **In-memory testing**: no test reads from the GAMMA dataset; the suite runs on any machine regardless of dataset availability.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, code conventions, and pull request checklist.

When adding a module: place it in the correct `src/phase*/` or `src/layer*/` package, add a test file following the in-memory fixture pattern, update `config/` for any new parameters, and verify no circular imports by running the test suite.

>>>>>>> e5a0ff1 (add project documentation and setup files)
---

## License

<<<<<<< HEAD
MIT - see [LICENSE](LICENSE).
=======
MIT — see [LICENSE](LICENSE).

---

<div align="center">
Built on <a href="https://networkx.org">NetworkX</a> · <a href="https://facebook.github.io/prophet/">Prophet</a> · <a href="https://scikit-learn.org">scikit-learn</a> · <a href="https://dash.plotly.com">Dash</a> · <a href="https://www.dash-mantine-components.com/">Mantine</a>
</div>
>>>>>>> e5a0ff1 (add project documentation and setup files)
