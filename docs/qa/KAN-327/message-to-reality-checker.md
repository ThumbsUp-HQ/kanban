# Forensic QA Handoff: KAN-327

## Overview & User Story
- Ticket ID: KAN-327 ([KB-SEC-MODEL-04] Enforce POSIX Resource Limits on Attachment PDF Subprocess Active-Content Sanitizer)
- Classification: N/A - Non-UI Security Ticket
- Branch: feat/KAN-324-328
- Touched Files:
  - `kanban/attachments/pdf.py`
  - `kanban/tests/attachments/test_pdf_resource_limits.py`

## User Story
As an application security engineer, I require the PDF active-content sanitizer child process to execute under strict POSIX rlimits (address space, CPU time, file size, file descriptors, core dumps) via `preexec_fn` so that malformed or adversarial PDFs cannot consume server resources or crash the host process.

---

## Evidence Manifest
1. `git-diff.patch`: Unified diff showing POSIX limit definitions (`DEFAULT_AS_LIMIT_BYTES`, `DEFAULT_CPU_LIMIT_SECONDS`, etc.), `_set_posix_limits`, and `preexec_fn` wiring into `subprocess.run`.
2. `unit-test-results.txt`: 40 passed tests (12 in `test_pdf_resource_limits.py`, 28 in `test_pdf_validation.py`) achieving 96% coverage on `kanban.attachments.pdf`.
3. `build-check.txt`: Clean static gate checks (`make check` exited 0).
4. `api-specialist-review.md`: Backend architect sign-off on POSIX isolation and signal handling.
5. `ui-specialist-review.md`: Confirmed N/A - Non-UI Ticket.
6. `changed-files-manifest.txt`: Cryptographic SHA-256 manifest verified with `sha256sum -c`.
