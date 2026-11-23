# API Specialist Review: KAN-327

## Audit Metadata
- Ticket ID: KAN-327 ([KB-SEC-MODEL-04])
- Title: Enforce POSIX Resource Limits on Attachment PDF Subprocess Active-Content Sanitizer
- Reviewer: backend-architect (API Specialist)
- Date: 2026-11-23
- Status: APPROVED

---

## 1. Scope & Objective
Ticket KAN-327 implements POSIX resource limits on the child subprocess running PDF active-content validation in `kanban/attachments/pdf.py`. Previously, while bounded subprocess timeouts existed, subprocess memory address space and CPU resource limits were not enforced at fork time via `preexec_fn`.

---

## 2. API & POSIX Resource Limit Verification
1. **POSIX Resource Limits Definition:**
   - Address Space: `DEFAULT_AS_LIMIT_BYTES = 256 * 1024 * 1024` (256 MiB).
   - CPU Time: `DEFAULT_CPU_LIMIT_SECONDS = 5` seconds.
   - File Size Output: `DEFAULT_FSIZE_LIMIT_BYTES = 10 * 1024 * 1024` (10 MiB).
   - Open File Descriptors: `DEFAULT_NOFILE_LIMIT = 64`.
   - Core Dumps: `DEFAULT_CORE_LIMIT_BYTES = 0` (preventing sensitive core dumps).
2. **`preexec_fn` Fork-Time Application:**
   - `_set_posix_limits` is configured as the `preexec_fn` argument to `subprocess.run` on POSIX systems.
   - Resource limits are applied in the child process immediately after `fork()` and before executing Python or parsing input, eliminating denial-of-service or memory exhaustion risks.
3. **Signal & Termination Handling:**
   - Child process termination via signals (e.g., `-SIGXCPU`, `-SIGKILL`, `-SIGSEGV`) is trapped and translated to structured `ProblemException(status=422, code="UNSAFE_PDF_CONTENT")`.
   - Rejection is immediate and clean without leaving orphan processes.

---

## 3. Test Coverage & Quality Gate
- `kanban/tests/attachments/test_pdf_resource_limits.py`: 12 comprehensive unit and integration tests verifying all limit types, signal handling, and e2e subprocess validation.
- `kanban/tests/attachments/test_pdf_validation.py`: 28 tests passed.
- Total PDF test suite: 40 tests passed in 25s.
- Combined coverage on `kanban.attachments.pdf`: **96%**.

---

## 4. Conclusion
The POSIX resource limit enforcement protects the platform from denial-of-service, memory bombs, and recursive decompression attacks during PDF attachment sanitization. Approved for ticket closure.
