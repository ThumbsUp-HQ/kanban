# Dependency Evaluation: KANBA-93 (KB-P3-46)

## Evaluated Packages
- `dompurify` (3.4.17)
  - License: Apache-2.0 OR MPL-2.0 (Dual-licensed permissive)
  - SHA-256 cryptographic hash: `60c5d5ccbb466de3de3ba863461a92bf134f8c156cef7992da43e0f659bc5cbd`
  - Lockfile Integrity: `sha512-B/pSlYVHQ58kqISD/yDjuJ1yfzI34m1gF4lAod2bwSRhiN4K5Cl3H8Af7hqB2PmTL911tdEudnnXn5FnhRoz0w==`
  - Purpose: HTML sanitization in Step B of the clipboard pipeline before HAST transformation.
  - Trusted Types: Full native support; integrates with `window.trustedTypes.createPolicy('dompurify', ...)`.
  - Alternatives considered: Sanitizer API (experimental, not supported across all target browser baselines), raw regex stripper (vulnerable to mutation XSS and nested tag bypasses).

- `hast-util-from-dom` (5.0.1)
  - License: MIT (Permissive)
  - SHA-256 cryptographic hash: `3274e39fc145a36e5bc9f6a07506c6e916db03276d011501771ec50f3513052c`
  - Lockfile Integrity: `sha512-N+LqofjR2zuzTjCPzyDUdSshy4Ma6li7p/c3pA78uTwzFgENbgbUrm2ugwsOdcjI1muO+o6Dgzp9p8WHtn/39Q==`
  - Purpose: Converts sanitized DOM trees directly to HAST (Hypertext Abstract Syntax Tree) representation.
  - Alternatives considered: Direct string DOM manipulation (error-prone, loses structural hierarchy).

- `hast-util-to-mdast` (10.1.2)
  - License: MIT (Permissive)
  - SHA-256 cryptographic hash: `7bf01fcb03484d20f0fd0a5247f84f73b53d6cc54a22b63e4c82ef39e89da96d`
  - Lockfile Integrity: `sha512-FiCRI7NmOvM4y+f5w32jPRzcxDIz+PUqDwEqn1A+1q2cdp3B8Gx7aVrXORdOKjMNDQsD1ogOr896+0jJHW1EFQ==`
  - Purpose: Bridges HAST to MDAST (Markdown Abstract Syntax Tree) for clean canonical serialization via remark-gfm and remark-stringify.
  - Alternatives considered: `turndown` (MIT - lacks unified AST pipeline, fails on complex GFM task list and table structures).

## Architectural & Security Specialist Sign-Offs
- License Compliance: Verified via `python scripts/license_gate.py` (0 violations, Apache-2.0 and MIT permissive licenses).
- Security Posture: Pre-sanitization hidden-DOM pruner executes in Step A prior to DOMPurify to neutralize paste-jacking prompt injection attacks.
- Supply Chain: Pinned to exact semver versions with SHA-256 entry point hashes and SHA-512 subresource integrity hashes in `pnpm-lock.yaml`.
- Specialist Sign-Off:
  - @arch-reviewer (Lead System Architect): sign-off APPROVED
  - @sec-eng (Security Engineer): sign-off APPROVED
  - @qa-eng (QA Engineer): sign-off APPROVED
