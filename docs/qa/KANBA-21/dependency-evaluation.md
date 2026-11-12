# Dependency Evaluation: KANBA-21 (Apache-2.0 License Gate)

## Evaluated Packages

### 1. pip-licenses (Python dev group)
- Ecosystem: Python (uv workspace root)
- Version Pinned: `5.5.5`
- License: `MIT` (Permissive, 100% compatible with Apache-2.0)
- Lockfile Artifact: `uv.lock`
- Hashes:
  * wheel: `sha256:f4c4c6d9e6a03612cf59f29f19dc8ab54904d82e055b8e191498f2279a224e14`
  * sdist: `sha256:60750c006adf7a0910347b726e8ee9fee3bc8d2e7c8307a5c4ec0776c8e2a276`
- Transitive Dependencies:
  * `prettytable` (`BSD-3-Clause`)
  * `wcwidth` (`MIT`)
- Scope: Development and CI governance only (under `[dependency-groups] dev`). Excluded from runtime distributions and production Docker images.
- Operational Characteristics: Offline execution against local metadata in `.venv`. Emits parseable JSON with package names, versions, and license declarations. Fully testable in isolation using synthetic fixture inputs (`--python-json`) with zero network access.

### 2. license-checker (Node devDependencies)
- Ecosystem: Node (root `package.json`)
- Version Pinned: `25.0.1`
- License: `BSD-3-Clause` (Permissive, 100% compatible with Apache-2.0)
- Lockfile Artifact: `pnpm-lock.yaml`
- Hash: `sha512-mET5AIwl7MR2IAKYYoVBBpV0OnkKQ1xGj2IMMeEFIs42QAkEVjRtFZGWmQ28WeU7MP779iAgOaOy93Mn44mn6g==`
- Scope: Development and CI governance only (under `devDependencies`). Excluded from runtime production artifacts.
- Operational Characteristics: Offline execution against local `node_modules`. Emits structured JSON mapping dependency paths to license expressions. Operates entirely offline and fails closed with return code 3 on parse or collection errors.

---

## Alternatives Considered

1. `license-checker-rseidelsohn`:
   - Community fork of `license-checker` maintaining active npm updates.
   - Evaluated by `qa-eng`, `sec-eng`, and `arch-reviewer`.
   - Produces compatible JSON schemas for `scripts/license_gate.py`.
   - `license-checker` 25.0.1 remains stable, fully compatible, and verified with `pnpm 10.30.0`. `license-checker-rseidelsohn` is designated as an approved drop-in fallback if future node resolution requires it.

2. `pnpm licenses list --json`:
   - Built-in native command in pnpm.
   - Evaluated by `qa-eng` and `arch-reviewer`.
   - Suffers from output schema instability across major pnpm versions (hierarchical group-by-license vs flat dependency mappings), complicating deterministic script normalization.
   - `license-checker` outputs a flat, predictable key-value mapping of package versions to licenses.

---

## Supply-Chain and Security Boundary

- Zero Runtime Contamination: Neither tool is bundled into web artifacts, ASGI server images, or agent runtime distributions.
- Cryptographic Immutability: Exact versions and cryptographic integrity hashes are locked in `uv.lock` and `pnpm-lock.yaml`.
- Offline Determinism: Both collectors run strictly offline without network sockets or telemetry.
- Fail-Closed Policy: `scripts/license_gate.py` fails closed (exit code 3) on invalid JSON, subprocess failure, or malformed allowlists. Non-waivable copyleft licenses (`GPL`, `AGPL`, `SSPL`) cannot be waived under any circumstances (exit code 1 with `NON_WAIVABLE_LICENSE`).

---

## Specialist Sign-Offs

- Test and Build Quality Engineer (`qa-eng` / Message #28): APPROVED
- Application and Supply-Chain Security Engineer (`sec-eng` / Message #29): APPROVED
- Systems and Backend Architect (`arch-reviewer` / Message #30): APPROVED
