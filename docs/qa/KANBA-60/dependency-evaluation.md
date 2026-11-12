# Dependency Evaluation: KANBA-60 (KB-P2-13)

## Overview
- Ticket: KANBA-60 (KB-P2-13)
- Title: Server Markdown Ingestion Normalizer
- Package: `nh3` (Version 0.3.7)
- License: MIT License (Permissive; 100% Apache-2.0 compatible)
- Scope: Server-side HTML sanitization per Specification S2.5 and S5.2

## Pinned Version and Integrity Hashes
Pinned in `kanban/pyproject.toml` as `nh3==0.3.7` and locked in `uv.lock`.

### Source Distribution (sdist)
- URL: `https://files.pythonhosted.org/packages/18/2f/022b27146d52d24b1b353b003359134788ecbcd6fcdf6283adbd57c0fbc8/nh3-0.3.7.tar.gz`
- SHA256: `71860d01c16f4d8c72e334e0674beb2b0899dbd0bf760de18932ef4390303848`
- Size: 25,662 bytes

### Linux x86_64 Wheel
- URL: `https://files.pythonhosted.org/packages/a6/ed/c5510c615dce55b6fcc364aa1838142f938beed64f5e4927490dfcaf4405/nh3-0.3.7-cp38-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl`
- SHA256: `70f5ac8626e899a4bab0ef74ca2f5bd602f49c7b739e6e5026b4afc6d63dac42`
- Size: 832,161 bytes

### Linux aarch64 Wheel
- URL: `https://files.pythonhosted.org/packages/07/42/a687e7091928806e514f89fa2666f25ec9bfe0a902fc4402b25e51ce408b/nh3-0.3.7-cp38-abi3-manylinux_2_17_aarch64.manylinux2014_aarch64.whl`
- SHA256: `f266d3f1b3647449923a8e406524632220dd5d8b647078dfe45b885d33d10479`
- Size: 859,615 bytes

### macOS Universal2 Wheel
- URL: `https://files.pythonhosted.org/packages/94/0d/c257754bf57f829f307aa226bbe136d3a1356b5a0d08324c7b6bd2a8aacd/nh3-0.3.7-cp38-abi3-macosx_10_12_x86_64.macosx_11_0_arm64.macosx_10_12_universal2.whl`
- SHA256: `6c3aa50eb26e9228238271db9f983cbc3b006dfbfeca2d4dc34c33ddc6ac5ea5`
- Size: 1,493,959 bytes

## Evaluated and Rejected Alternatives

### 1. Bleach (Mozilla)
- Status: BANNED Repository-Wide (Architecture Spec S2.5)
- Rationale:
  - Mozilla officially deprecated and archived `bleach` in 2023.
  - Relies on html5lib, which is known for quadratic parsing complexity and severe ReDoS vulnerabilities.
  - Spec S2.5 mandates `bleach` is strictly banned repository-wide.
- Audit Verification:
  - `grep -rn "bleach" pyproject.toml kanban/ uv.lock` returns zero matches.

### 2. lxml / BeautifulSoup
- Status: REJECTED
- Rationale:
  - `lxml` links against C `libxml2` with an extensive history of memory corruption CVEs (use-after-free, buffer overflows).
  - BeautifulSoup is a parsing wrapper without built-in sanitization guarantees.
  - `nh3` provides Python bindings to Rust `ammonia`, guaranteeing native memory safety, linear parsing performance, and zero C ABI vulnerabilities.

## Specialist Review Sign-Offs

### Architect Review (@arch-reviewer, Board Post #116)
- Evaluated: Architecture Spec S2.5, S5.1, and S5.2 compliance.
- Finding: `nh3` provides Python bindings to the Rust ammonia HTML sanitizer. It executes in memory-safe compiled native code, eliminating ReDoS and quadratic parsing vulnerabilities. Essential for server-side sanitization of pasted HTML before conversion to Markdown, stripping dangerous tags (`<script>`, `<object>`, `<embed>`) and event handlers (`onerror`). Rejected `bleach` (deprecated, archived by Mozilla) and `lxml` (historic memory corruption CVEs in C libxml2).
- Verdict: APPROVED.

### Security Engineering Review (@sec-eng, Board Post #118)
- Evaluated: Supply-chain risk, memory safety, and attack surface.
- Finding: `nh3` bindings to Rust `ammonia` provide compile-time memory safety without runtime C library vulnerabilities. Pinned `nh3==0.3.7` eliminates dependency drift and satisfies all S2.5 security mandates.
- Verdict: APPROVED.

### QA Engineering Review (@qa-eng, Board Post #120)
- Evaluated: Determinism, test execution speed, and coverage compatibility.
- Finding: Native wheel installs quickly across Linux and macOS architectures. Executes sub-millisecond sanitization in automated tests without requiring background daemon processes.
- Verdict: APPROVED.

## Conclusion
`nh3==0.3.7` is pinned, cryptographically verified, and fully approved for server-side HTML sanitization in Kanban. Zero `bleach` occurrences exist in the repository.
