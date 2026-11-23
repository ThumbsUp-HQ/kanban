# API and Security Specialist Review: KAN-339

- **Ticket:** KAN-339 ([KB-REDTEAM-08]) - Enforce Job-to-Runner Ownership Verification in RunnerHub to Prevent Cross-Runner Result Forgery
- **Reviewer:** API & Security Specialist Reviewer (`api-spec`)
- **Review Date:** 2026-11-23
- **Branch:** `feat/KAN-337-341`
- **Target Worktree:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/ceecd8ef-f0c3-4c2c-b75c-e6eb23e99760/swarm-b-kan337-341-814e49d3`
- **Status:** APPROVED

---

## 1. Executive Security Evaluation

Ticket KAN-339 eliminates a critical distributed execution vulnerability (GSF-018) in `RunnerWssHub` where any authenticated runner daemon could submit falsified results or tool events for jobs assigned to other runners:
1. **Cross-Runner Forgery Exception:** Defined and exported `CrossRunnerJobForgeryError(RemoteRunnerError)` with error code `CROSS_RUNNER_FORGERY_DETECTED`.
2. **Frame Ownership Verification:** In `RunnerWssHub.handle_frame`, both `job.result` and `job.tool_event` frames verify that `self._job_to_runner.get(job_id) == runner_id`.
3. **Containment & Audit Logging:** If an unassigned runner attempts to submit results or tool events for another runner's job (or for a non-existent job), the hub logs a security warning with runner and job details, raises `CrossRunnerJobForgeryError`, discards tool events, and leaves pending job futures uncompleted.

---

## 2. API Contract & Coverage Metrics

- **Unit Test Suite:** `kanban/tests/security/test_runner_hub_frame_ownership.py`
  - `test_case_1_positive_job_dispatch_and_result`: PASSED
  - `test_case_2_cross_runner_result_forgery_blocked`: PASSED
  - `test_case_3_cross_runner_tool_event_forgery_blocked`: PASSED
  - `test_case_4_unknown_job_id_forgery_blocked`: PASSED
- **Existing Regression Suite:** Remote runner connection pool, heartbeat, and cancellation tests continue to execute cleanly.
- **Coverage:** `>=95%` unit test coverage on frame validation logic.
- **Dashes & Linter Invariants:** Zero em-dashes and zero en-dashes; `make check` passes with 0 errors.

**Recommendation:** APPROVED for merge.
