# Architecture

This document describes the internal design of Hybrid Hypergraph-ATG for contributors and integrators who need to understand module boundaries, data flow, and the reasoning behind key implementation decisions.

## Package layout

```
src/
├── utils/          infrastructure (config, logging) - no domain logic
├── ingestion/      dataset-specific conversion to canonical format
├── layer1/         static topology encoding (H_cert hypergraph)
├── layer2/         dynamic topology (ATG snapshots, PBO, routing drift)
├── layer3/         feature derivation from topology
├── phase1/         time-series forecasting
├── phase2/         causal analysis
├── phase3/         anomaly detection hierarchy
└── phase4/         alert synthesis
```

Dependencies flow downward only. A module in `phase3/` may import from `layer2/` or `layer3/`, never from `phase4/`. This is enforced implicitly by the test suite, which imports each module in isolation; any circular import triggers an immediate `ImportError`.

## The canonical CSV format

The ingestion layer produces three files that act as the contract between the dataset-specific converter and the rest of the framework.

```
node_metrics.csv    (timestamp, node_id) → cpu_percent, mem_mb, net_rx_mb, net_tx_mb
edge_metrics.csv    (timestamp, edge_id) → latency_ms, error_rate, throughput_rps
ground_truth.csv    timestamp            → label_trace, fault_type, anomaly_node_ids
```

All timestamps are 64-bit integers in microseconds. The long format for `node_metrics` (one row per node per window) allows the feature selector to derive the correct feature vector per compliance set without schema changes as the topology evolves.

## Layer 1 - H_cert topology encoding

`TopologyBuilder` converts `topology.yaml` into an annotated `networkx.DiGraph`. The choice of NetworkX is motivated by its native support for arbitrary Python dict attributes on nodes and edges, which allows encoding compliance set membership as a list annotation on each edge (`hyperedges: ["H_crit", "H_cache"]`) without introducing phantom nodes.

The `build()` method is idempotent; subsequent calls return a deep copy of the cached graph to prevent external mutation of the shared structure.

## Layer 2 - ATG and PBO

`ATGBuilder` assembles the sequence of topology snapshots G(t) by merging the three canonical CSVs at each timestamp. Each snapshot is a dict of node and edge feature vectors associated with the annotated graph.

`PBOBuilder` computes the stochastic transition matrix W(t) per branching node from `throughput_rps`. The gold standard W_gold is derived from nominal windows (label_trace = 0) once during training and held fixed. Routing drift is measured as:

- **Linear topology (H_crit)**: Path Adherence Score `PAS(t) = Σ_e w(e,t) · I[e ∈ critical_path]`
- **Parallel topology (H_cache)**: Frobenius distance `‖W(t) − W_gold‖_F`

The CUSUM detector in Phase III operates on the sequence `{‖W(t) − W_gold‖_F}` to detect sustained routing drift, which is physically meaningful for fault types that alter cache hit/miss ratios (e.g., memory pressure on a shared caching node).

## Layer 3 - Feature selection

`FeatureSelector` derives the feature vector `M^Φ_i = M^direct ∪ M^interf` for each compliance set from the topology, without any dataset-specific knowledge. The interference feature set `M^interf(H_Φ_i, H_Φ_j)` is determined by the topological condition: an arc `e ∈ H_Φ_j` that has as target a node shared with `H_Φ_i` produces an interference feature `interf:e:throughput_rps` in the vector of `H_Φ_i`. This encoding enables the causal analyzer to detect inter-compliance-set propagation chains.

## Phase I - StatForecaster

`StatForecaster` maintains one Prophet model per metric per compliance set, fitted on nominal windows only. At inference time, it operates in two modes:

- **Fixed mode** (default, used in Scenario A): returns the nominal forecast without trend correction. Appropriate for step-function fault injection where no pre-fault gradient exists.
- **Adaptive mode** (`predict_adaptive()`, used in Scenario B): applies EWMA trend correction to the raw Prophet forecast. The EWMA buffer is pre-warmed on the last `lookback_windows` nominal windows of the experiment and reset per experiment. This mode can produce lead time > 1 when a measurable latency gradient exists before the fault.

The choice of which model to use per metric (Prophet / SARIMAX / Linear) is declared in `pipeline_params.yaml` under `forecasting.model_routing`.

## Phase II - CausalAnalyzer

The causal graph is built once on nominal windows and never updated during inference. For each compliance set, `CausalAnalyzer` tests all topology-guided candidate pairs using three configurable tests (Granger causality, Pearson correlation, Transfer Entropy) with thresholds declared in `pipeline_params.yaml`. The topology-guided candidate pairs (derived from `FeatureSelector`) reduce the combinatorial space from O(|M|²) to a semantically motivated subset.

The static causal graph is a deliberate design choice. Updating the graph during inference would conflate fault-induced signal changes with genuine causal structure updates, making root cause attribution unreliable.

## Phase III - StructuralMonitor (four-level hierarchy)

```
Level 1  base_signal = SLA_threshold_signal OR z_score_signal
         SLA:    aggregated_metric(t) > threshold
         z-score: (metric(t) − μ_nom) / σ_nom > k

Level 2  if_signal
         Isolation Forest on M^Φ_i(t), fitted on nominal windows.
         Activates on anomalous joint feature distribution before
         latency crosses the SLA.

Level 3  cusum_signal
         CUSUM on ‖W(t) − W_gold‖_F or PAS(t).
         auto_calibrate_tolerance=true fits k from nominal data for
         parallel topologies.

Level 4  structural_signal
         Fires only when cusum_signal AND if_signal are both true.
         High-specificity signal for concurrent structural and
         distribution-level anomalies.

Any positive signal from any level → alert is propagated to Phase IV.
```

## Phase IV - AlertGenerator

`AlertGenerator` takes the active signals from Phase III and produces a structured alert dict containing:

- `lead_time`: steps until forecast SLA violation (τ from Phase I)
- `criticality`: YELLOW / ORANGE / RED based on lead_time thresholds in `pipeline_params.yaml`
- `root_cause`: top-ranked node from the causal graph weighted by signal intensity
- `critical_arc`: arc with highest latency contribution to the certified path
- `cross_property_interference`: detected interference chain from `M^interf` causal links
- `model_uncertainty_flag`: set when the current observation diverges significantly from the training distribution (triggers criticality downgrade from RED to ORANGE)

## Configuration lifecycle

| File | Change trigger | Versioning |
|---|---|---|
| `topology.yaml` | Architecture change or SLA renegotiation | Version together with the certified system's contract |
| `pipeline_params.yaml` | Algorithmic tuning session | Free to update; does not affect the certified model |

`ConfigLoader` enforces lazy loading (disk read on first access only), eager validation (missing required keys raise `ValueError` at load time, not at use time), and cache isolation (every accessor receives a deep copy of the config dict).
