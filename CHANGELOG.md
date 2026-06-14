# Changelog

All notable changes to this project are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- README.md with installation, quickstart, output format reference, and architecture overview
- ARCHITECTURE.md with module dependency graph and design invariants
- CONTRIBUTING.md with development setup and PR checklist
- CHANGELOG.md
- requirements.txt and requirements-dev.txt
- GitHub Actions CI workflow (Python 3.10, 3.11, 3.12)
- ruff.toml linter configuration
- Issue templates and PR template

<<<<<<< HEAD
## [1.0.0] - 2026-06-01
=======
## [1.0.0] — 2026-06-01
>>>>>>> 5f90656 (add CI workflow, ruff confing, CHANGELOG)

### Added
- Complete 4-phase pipeline: Layer 1 (topology), Layer 2 (ATG + PBO), 
  Phase I (forecasting), Phase II (causal analysis), Phase III (structural 
  monitoring), Phase IV (alert generation)
- DSBConverter with per-arc throughput disaggregation via home_rps_start_time_*.csv
- CausalAnalyzer with Granger causality, Pearson correlation and Transfer Entropy
- StructuralMonitor with 4-level detection hierarchy (SLA threshold, z-score,
  Isolation Forest, CUSUM routing drift)
- AlertGenerator producing structured alerts with lead time, criticality,
  root cause, and cross-property interference chain
- 306 unit tests across 10 modules, all in-memory (no dataset required)
- Dash + Mantine interactive dashboard
- run_pipeline.py and run_etl.py entry points
- topology.yaml and pipeline_params.yaml configuration system with
  strict lifecycle separation

### Branch: gamma-synthetic
- GammaRampInjector: calibrated latency ramp injection on nominal windows
- run_pipeline_gamma_aug.py: per-source-file Adaptive Forecasting with EWMA pre-warm
- topology_gamma_aug.yaml: recalibrated SLA thresholds (284.4 ms / 45.0 ms)
- eval_batch_synthetic.py: aggregate evaluation over augmented corpus
- synthetic_generator_v2.py: standalone synthetic SaaS Monitoring Platform scenario
