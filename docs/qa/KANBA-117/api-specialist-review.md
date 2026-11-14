# API Specialist Gate Review: KANBA-117 (KB-P3-52)

- **Ticket**: `KANBA-117` (`KB-P3-52`: Standalone status panel: volume persistence, encrypted backup trigger & docker-compose.yml export)
- **Reviewer**: `@arch-reviewer` (Systems/Backend Architect & API Specialist)
- **Branch**: `feat/KANBA-117`
- **Worktree**: `/tmp/kb-wt-KANBA-117`
- **Scope**: `kanban/api/v1/system_status.py`, `kanban/standalone/export_service.py`, `kanban/tests/api/test_system_status.py`
- **Board Ref**: Architecture guidance in Swarm Message #838

---

### 1. Architectural, Contract & Security Evaluation

#### A. Backend Status & Anti-Enumeration Redaction (`GET /api/v1/system/status`, S3.4, S3.5)
- **Endpoint Integrity**: Authenticated route backed by `get_standalone_status()`. Reads `/run/kanban/standalone_status.json` via `KB_STANDALONE_STATUS_PATH` and cleanly falls back to `production_multi_container` defaults when the file is absent or corrupted.
- **Topology Redaction**:
  - For `SERVER_ADMIN` callers: returns full host details including `data_mount_point`, `data_mount_fstype`, and `local_llm_endpoint_host`.
  - For non-admin `MEMBER` callers: strictly redacts `data_mount_point` -> `null`, `data_mount_fstype` -> `null`, and `local_llm_endpoint_host` -> `null`. Verified zero internal filesystem or container topology leakage.
- **Strict Typing**: Pydantic response models use `model_config = ConfigDict(extra="forbid")`.

#### B. Encrypted Database Backup & Zero-Shell Invariants (`POST /api/v1/admin/standalone/backup`, S2.2, S4.2, S5.4)
- **Admin AAL2 Gate**: Route strictly declares `Depends(require_admin_aal2)` and `Depends(require_server_admin)`. Verified via `assert_admin_routes_protected(app)`.
- **Deployment Mode Check**: Rejects callers with RFC 7807 409 `NOT_STANDALONE_MODE` if `deployment_mode != "standalone_embedded_pg"`.
- **Passphrase Validation**: Defensively requires `MIN_PASSPHRASE_LENGTH = 16` characters; returns RFC 7807 422 `INVALID_BACKUP_PASSPHRASE` on short passphrases.
- **Zero-Shell Execution**: Invokes `/usr/bin/pg_dump` via `asyncio.create_subprocess_exec` using direct `execve` semantics (`shell=False`).
- **Binary Envelope (`.kbkp`)**:
  - 4-byte magic: `KBKP`
  - 1-byte version: `0x01`
  - 1-byte KDF mode: `0x01` (PBKDF2-HMAC-SHA256, 600,000 iterations) or `0x02` (HKDF-SHA256 from MASTER_KEK)
  - 16-byte cryptographic salt (`os.urandom(16)`)
  - 12-byte AES-GCM IV (`os.urandom(12)`)
  - Authenticated ciphertext with 16-byte GCM tag.
  - Roundtrip verified: decryption recovers bit-for-bit identical dump bytes.
- **Audit & Confidentiality**: Records `STANDALONE_BACKUP_EXPORTED` in the activity ledger under `ActivityCategory.SYSTEM`. Zero passphrase, KEK, or decrypted dump leakage in response headers, logs, or error models. Streams binary attachment with ISO timestamped filename `kanban-backup-<YYYYMMDDTHHMMSSZ>.kbkp`.

#### C. Secret-Free Production Compose Export (`GET /api/v1/admin/standalone/compose-export`, S2.4, KB-P0-11)
- **Access Control**: Restricted to `SERVER_ADMIN` callers.
- **Network Isolation Verification**:
  - `edge_net`: bridge for public ingress.
  - `app_net`: internal network connecting `kanban` and `mcp-server`.
  - `data_net`: internal network strictly connecting `postgres` and `kanban`.
  - `sandbox_net`: internal network strictly connecting `sandbox` and `kanban`.
  - `egress_llm_net`: bridge for external LLM access.
  - Both `mcp-server` and `sandbox` are strictly forbidden from connecting to `data_net`.
- **Zero Hardcoded Secrets**: Every secret in `docker-compose.yml` uses variable substitution (`${POSTGRES_PASSWORD}`, `${MASTER_KEK}`, etc.) paired with clear `.env.example` templates.

---

### 2. Specialist Verdict

The backend API endpoints, cryptographic envelope routines, zero-shell subprocess boundaries, and host-path redactions fully comply with all security invariants and architectural specifications.

**VERDICT: APPROVED**
