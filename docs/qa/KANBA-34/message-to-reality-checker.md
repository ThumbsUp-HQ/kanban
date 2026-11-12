# Reality-Checker Verification Packet: KANBA-34 (KB-P0-09)

## Ticket Overview
- **Ticket ID**: `KANBA-34` (`KB-P0-09`)
- **Title**: [Phase 0 / Standalone] First-boot CSPRNG keyring & ephemeral-storage detection
- **Branch**: `feat/KANBA-34`
- **Base Commit**: `eb1daba71147679d545d52b826f36aa19dd138b8` (HEAD of `feat/KANBA-29`)
- **Author**: `builder-21`

---

## Technical Deliverables Summary

1. **`deploy/standalone/keyring.py`**:
   - `load_or_create_keyring(path: Path) -> Keyring`:
     * Generates 5 distinct 256-bit (32-byte) cryptographic secrets (`os.urandom(32)`): `MASTER_KEK`, `KB_AUTH_PEPPER`, `SESSION_HMAC_KEY`, `kanban_app`, `kanban_migrator`.
     * Writes atomically to `<parent>/keyring.json.<hex>.tmp` with mode `0600` (`O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW`), ensures parent directory permissions are `0700`, calls `os.fsync`, and renames atomically with `Path.replace`. Directory fsync is performed after replace.
     * Concurrent creation race handled: if replace target appears first, discards temp file and loads existing keyring fail-closed.
     * Validation on existing file: raises `KeyringError` if symlink, owner UID != 0 (when root), mode != `0600`, parent mode != `0700`, file size > 64 KiB, invalid JSON, version != 1, unexpected/missing keys, or secret length != 32 bytes.
     * `Keyring` frozen dataclass with redacted representation: `__repr__` and `__str__` return `Keyring(<redacted>)`.
   - `compute_scram_sha256_verifier(password, salt, iterations)`:
     * Computes RFC 7677 / RFC 5802 SCRAM-SHA-256 verifier with PBKDF2-HMAC-SHA256 (4096 iterations, 16-byte salt, `SCRAM-SHA-256$4096:<salt>$<StoredKey>:<ServerKey>`).
     * Confirmed against RFC 7677 Section 3 test vector (`pencil` / `W22ZaJ0SNY7soEsUEjb6gQ==`).

2. **`deploy/standalone/storage_probe.py`**:
   - `probe(data_dir, mounts_text, mountinfo_text, mode) -> StandaloneStatus`:
     * Decodes octal escape sequences in mount points (e.g. `\040` -> space).
     * Finds longest prefix mount point matching `data_dir`.
     * Identifies ephemeral storage: `overlay`, `tmpfs`, anonymous Docker volumes (`/var/lib/docker/volumes/[0-9a-f]{64}/_data`), or unmounted paths mark `persistent_volume = False`. Named Docker volumes evaluate to `persistent_volume = True`.
   - `emit_ephemeral_warning()`:
     * Emits verbatim warning line to stderr: `⚠️ Ephemeral Storage: Mount -v kanban_data:/var/lib/kanban/data to persist data across container removal\n`.
   - `write_standalone_status(status, target_path)`:
     * Writes `StandaloneStatus` JSON to `/run/kanban/standalone_status.json` atomically with mode `0644`.

3. **`deploy/standalone/pg_config.py`**:
   - Updated `pg_hba.conf` configuration to authenticate `kanban_app` over local socket via `scram-sha-256` (while `postgres` and `kanban_migrator` remain `peer`).
   - Added `generate_role_passwords_sql(app_scram, mig_scram)` to apply SCRAM verifiers without exposing plaintext passwords in PostgreSQL logs or SQL scripts.

4. **`deploy/standalone/entrypoint.py`**:
   - Wired storage probe and ephemeral warning check into entrypoint bootstrap.
   - Integrated `load_or_create_keyring` on startup. Failure logs `KEYRING_INVALID` to stderr and exits 78 (`EXIT_CONFIG_ERROR`).
   - Passed SCRAM verifiers into `bootstrap_database()` to execute role password statements on embedded cluster.
   - Extended `build_child_env()` with `KB_MASTER_KEK_B64`, `KB_AUTH_PEPPER_B64`, `KB_SESSION_HMAC_KEY_B64`, and `KB_STANDALONE_STATUS_PATH`.

5. **Automated Unit Tests & Coverage**:
   - `tests/deploy/test_keyring.py`: 16 comprehensive test cases covering creation, permissions, symlinks, corrupted/truncated JSON, oversized files, invalid keys, invalid secret lengths, redacted repr, RFC 7677 test vector, and concurrent creation race.
   - `tests/deploy/test_storage_probe.py`: 11 test cases covering octal escape decoding, overlay/tmpfs/anon/named volume detection, longest prefix matching, missing mount fallback, warning emission, and atomic JSON write.
   - `tests/deploy/test_standalone_entrypoint.py`: Extended with 18 tests covering keyring loading, SCRAM password bootstrap, child environment allowlist, and exit code 78 on invalid keyring.
   - Total test suite: 45 passed in 0.26s.
   - Total line and branch coverage across `deploy.standalone`: 97.02% (exceeds >= 95% mandate).

6. **Container Verification Proof**:
   - Ephemeral run (`kb-eph`): Warning emitted to stderr; keyring permissions verified as `600 root`; non-root UID 65532 access confirmed blocked with `Permission denied`; `standalone_status.json` captured with `persistent_volume: false`.
   - Persistent run (`kb-pers` with `kb_test_vol`): Warning suppressed; keyring SHA-256 hash verified byte-identical before and after restart (`874f899faa01ccf8820f37060d03509e4664153491e1f9555f6a8128e407ce3c`); `standalone_status.json` captured with `persistent_volume: true`.

---

## Artifact Index
- `docs/qa/KANBA-34/git-diff.patch`
- `docs/qa/KANBA-34/unit-test-results.txt`
- `docs/qa/KANBA-34/build-check.txt`
- `docs/qa/KANBA-34/container-check.txt`
- `docs/qa/KANBA-34/standalone-status-sample.json`
- `docs/qa/KANBA-34/message-to-reality-checker.md`
