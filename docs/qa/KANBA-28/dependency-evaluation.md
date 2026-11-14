# Dependency Evaluation: pyyaml (KANBA-28 / KB-P0-06)

- **Change:** `pyyaml==6.0.3` is now declared explicitly in the `dev` dependency group of
  `pyproject.toml`, and `uv.lock` records it as a direct dev dependency
  (`{ name = "pyyaml", specifier = "==6.0.3" }`). The package was already present and
  hash-locked in `uv.lock` as a transitive dependency (via pre-commit and others), so no new
  code enters the supply chain; the resolved version did not change.
- **Pinned version and hash (from `uv.lock`):** `pyyaml==6.0.3`, sdist
  `sha256:d76623373421df22fb4cf8817020cbb7ef15c725b9d5e45f17e189bfc384190f`
  (every wheel is also hash-locked in `uv.lock`; installed version verified `6.0.3`).
- **License:** MIT (Apache-2.0 compatible; `make license` reports `violations=0`).
- **Usage:** `yaml.safe_load` only, in `scripts/tests/test_ci_workflow.py`, on repo-owned
  workflow files. Never `yaml.load`, never on network input.
- **Alternatives considered:** a hand-rolled YAML parser (rejected: error-prone, weak for a
  security test); `ruamel.yaml` (rejected: an extra, genuinely new dependency); `json`/`tomllib`
  (rejected: the workflow format is YAML).
- **Sign-off:** architect and engineer sub-agent consultation NOT obtained: the resolved
  dependency graph is unchanged (promotion of an already locked transitive package to a direct
  dev dependency). The coordinator/reality-checker should confirm this reading of the rule.
