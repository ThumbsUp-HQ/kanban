# API Specialist Review: KAN-328

## Audit Metadata
- Ticket ID: KAN-328 ([KB-SEC-MODEL-05])
- Title: Enforce Strict 0600 Permissions and Root-Execution Check in kanban-ctl Keyring Loader
- Reviewer: backend-architect (API Specialist)
- Date: 2026-11-23
- Status: APPROVED

---

## 1. Scope & Objective
Ticket KAN-328 hardens the platform keyring loader (`kanban-ctl` and `StaticKekProvider`) against unauthorized local file access and root-execution elevation. Master keys and auth peppers stored on disk must enforce strict permissions before bytes are ingested into memory.

---

## 2. API & Security Invariant Verification
1. **File Permissions & Attribute Invariants (`validate_keyring_file_permissions`):**
   - Path existence: Target must exist and resolve to a regular file (symlinks, sockets, devices, and directories are strictly rejected).
   - File size: Bounded by `MAX_KEYRING_FILE_BYTES = 65536` (64 KiB), rejecting unbounded read attempts.
   - Mode checks: Must NOT have execute bits set (`mode & 0o111 != 0` -> error).
   - Mode checks: Group and other permissions must be 0 (`mode & 0o077 != 0` -> error). Only owner read/write (`0o600` or `0o400`) is permitted.
2. **POSIX Ownership & Root-Execution Invariants:**
   - When running as root (`os.geteuid() == 0`), keyring file MUST be owned by root (`stat.st_uid == 0`). A foreign non-root keyring file is rejected to prevent privilege elevation.
   - When running as a non-root user, keyring file MUST be owned by that same UID (`stat.st_uid == current_uid`).
   - Parent directory check: If parent directory is world-writable (`mode & 0o002`), it MUST have the sticky bit set (`mode & 0o1000`), preventing symlink swap / TOCTOU races in shared directories like `/tmp`.
3. **Integration Across Keyring Ingestion Surfaces:**
   - In `kanban/security/keys.py`: `validate_keyring_file_permissions` runs before reading file contents in `_load_from_keyring_file`.
   - In `kanban/security/envelope.py`: `StaticKekProvider.from_keyring_file(path)` enforces validation.
   - In `kanban/cli/ctl.py`: `load_ctl_keyring(path)` enforces validation and raises informative CLI error messages.

---

## 3. Test Coverage & Quality Gate
- `kanban/tests/security/test_keyring_permissions.py`: 25 comprehensive unit tests verifying symlink rejection, non-regular files, executable permissions, group/other permissions, file size limits, foreign UID ownership, root execution enforcement, and parent directory sticky bits.
- `kanban/tests/security/test_keys.py`: 15 tests passed.
- `kanban/tests/security/test_envelope.py`: 8 tests passed.
- Combined coverage on `kanban.security.keys`: **99%**.

---

## 4. Conclusion
The keyring permissions and root-execution validation prevents privilege escalation, credentials harvesting, and insecure configuration. Approved for ticket closure.
