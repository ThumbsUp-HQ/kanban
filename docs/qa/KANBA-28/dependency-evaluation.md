# Dependency Evaluation: pyyaml (KANBA-28 / KB-P0-06)

- **Change to dependency set:** NONE. No entry was added to `pyproject.toml` or `uv.lock`.
  `pyyaml` is already present and hash-locked in `uv.lock` as a transitive dependency
  (via pre-commit and others). `types-PyYAML==6.0.12.20261111` is already a pinned dev dependency.
- **Pinned version and hash (from `uv.lock`):** `pyyaml==6.0.3`, sdist
  `sha256:d76623373421df22fb4cf8817020cbb7ef15c725b9d5e45f17e189bfc384190f`
  (every wheel is also hash-locked in `uv.lock`; installed version verified `6.0.3`).
- **License:** MIT (Apache-2.0 compatible; `scripts/license_gate.py` passes).
- **Usage:** `yaml.safe_load` only, in `scripts/tests/test_ci_workflow.py`, on repo-owned
  workflow files. Never `yaml.load`, never on network input.
- **Alternatives considered:** a hand-rolled YAML parser (rejected: error-prone, worse for
  a security test); `tomllib`/`json` (rejected: workflow format is YAML). `ruamel.yaml` (rejected:
  extra new dependency for no benefit).
- **Residual item:** the ticket asks to declare `pyyaml` explicitly in the dev group. That
  would be a `pyproject.toml`/`uv.lock` change outside this task's file list; it is deferred
  and flagged to the coordinator.
- **Sign-off:** architect and engineer sub-agent sign-off NOT obtained (no dependency was
  introduced, so the consult gate was not triggered). Coordinator to confirm.
