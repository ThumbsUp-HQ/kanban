# Dependency Evaluation: KANBA-93 (KB-P3-46)

## Evaluated Packages
- `dompurify` (3.2.4)
  - License: Apache-2.0 OR MPL-2.0 (Dual-licensed permissive)
  - Integrity: `sha512-ysFSFEDVduQpyhzAob/kkuJjf5zWkZD8/A9ywSp1byueyuCfHamrCBa14/Oc2iiB0e51B+NpxSl5gmzn+Ms/mg==`
  - Purpose: HTML sanitization in Step B of the clipboard pipeline before HAST transformation.
  - Trusted Types: Full native support; integrates with `window.trustedTypes.createPolicy('dompurify', ...)`.
  - Alternatives considered: Sanitizer API (experimental, not supported across all target browser baselines), raw regex stripper (vulnerable to mutation XSS and nested tag bypasses).

- `hast-util-from-dom` (5.0.1)
  - License: MIT (Permissive)
  - Integrity: `sha512-N+LqofjR2zuzTjCPzyDUdSshy4Ma6li7p/c3pA78uTwzFgENbgbUrm2ugwsOdcjI1muO+o6Dgzp9p8WHtn/39Q==`
  - Purpose: Converts sanitized DOM trees directly to HAST (Hypertext Abstract Syntax Tree) representation.
  - Alternatives considered: Direct string DOM manipulation (error-prone, loses structural hierarchy).

- `hast-util-to-mdast` (10.1.2)
  - License: MIT (Permissive)
  - Integrity: `sha512-FiCRI7NmOvM4y+f5w32jPRzcxDIz+PUqDwEqn1A+1q2cdp3B8Gx7aVrXORdOKjMNDQsD1ogOr896+0jJHW1EFQ==`
  - Purpose: Bridges HAST to MDAST (Markdown Abstract Syntax Tree) for clean canonical serialization via remark-gfm and remark-stringify.
  - Alternatives considered: `turndown` (MIT - lacks unified AST pipeline, fails on complex GFM task list and table structures).

## Architectural & Security Sign-Offs
- License Compliance: Verified via `python scripts/license_gate.py` (0 violations, Apache-2.0 and MIT permissive licenses).
- Security Posture: Pre-sanitization hidden-DOM pruner executes in Step A prior to DOMPurify to neutralize paste-jacking prompt injection attacks.
- Supply Chain: Pinned to exact semver versions with SHA-512 subresource integrity hashes in `pnpm-lock.yaml`.
- Sign-offs:
  - Architecture Reviewer: APPROVED
  - Security Engineer: APPROVED
  - QA Engineer: APPROVED
