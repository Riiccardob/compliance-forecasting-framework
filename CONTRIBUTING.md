# Contributing

Thank you for your interest in contributing to Hybrid Hypergraph-ATG.

## Development setup

```bash
git clone https://github.com/Riiccardob/hybrid-hypergraph-atg.git
cd hybrid-hypergraph-atg
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt   # pytest, coverage, ruff
```

## Running the test suite

```bash
pytest tests/ -v
pytest tests/ --cov=src --cov-report=term-missing
```

All 306 tests must pass before opening a pull request. The suite runs without access to the GAMMA dataset; all tests use in-memory data structures.

## Code conventions

- Python 3.10+, type hints on all public method signatures.
- `ruff` for linting and formatting (`ruff check . && ruff format .`).
- No hardcoded numeric constants in module code. Any threshold or parameter must be readable from `pipeline_params.yaml` via `ConfigLoader`.
- No test reads from disk except `ConfigLoader` tests that use `tmp_path`.

## Adding a new module

1. Place the module in the correct `src/layer*/` or `src/phase*/` package based on its responsibility.
2. Create `tests/test_<module_name>.py` following the in-memory test pattern.
3. If the module introduces new configuration keys, add them to the appropriate YAML file and document them in `docs/configuration.md`.
4. Verify that no circular imports are introduced by running `pytest tests/` — any circular import will surface as an `ImportError` on first import.
5. Update `ARCHITECTURE.md` if the module changes data flow or introduces a new design invariant.

## Pull request checklist

- [ ] All existing tests pass (`pytest tests/ -v`)
- [ ] New functionality is covered by tests
- [ ] No hardcoded constants in module code
- [ ] `ruff check` passes with no errors
- [ ] `ARCHITECTURE.md` updated if data flow changed
- [ ] `CHANGELOG.md` entry added under `[Unreleased]`

## Branch conventions

| Branch | Purpose |
|---|---|
| `main` | stable, GAMMA original dataset implementation |
| `gamma-synthetic` | augmented dataset (GammaRampInjector + adaptive pipeline) |
| `feature/<name>` | feature branches, merge into `main` via PR |
| `fix/<name>` | bug fix branches |

Changes to `gamma-synthetic` that also apply to `main` should be cherry-picked, not merged wholesale, to keep the two scenarios clearly separated.
