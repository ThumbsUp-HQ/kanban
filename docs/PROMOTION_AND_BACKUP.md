# Production Promotion and Encrypted Backup Runbook

## 1. Overview and Architecture

The Kanban platform supports two primary deployment topologies:
1. **Standalone Single-Container Mode (`docker run`):**
   An all-in-one container running PostgreSQL 16, pgvector, and FastAPI behind a PID-1 supervisor on an internal Unix domain socket.
2. **Hardened Multi-Container Production Stack (`docker compose`):**
   A distributed deployment enforcing a strict 5-network isolation matrix, external or clustered PostgreSQL 16 with pgvector, Valkey 8 caching, Caddy TLS 1.3 reverse proxy, and sandboxed execution tiers.

This runbook specifies the operator procedure for lossless promotion from standalone single-container mode to external PostgreSQL 16 production infrastructure using `kanban-ctl`.

---

## 2. Lossless Standalone-to-Production Promotion

### 2.1 The Lossless Invariant
Promoting from single-container mode to external PostgreSQL 16 preserves:
- 100% of workspace, project, issue, document, page, sticky, and object link records.
- Cryptographic hash-chained activity audit history verified via `verify_activity_chain()`.
- Envelope-encrypted authentication credentials by carrying over `MASTER_KEK`.
- Local Admin password hashes by carrying over `KB_AUTH_PEPPER`.
- Row-Level Security (`FORCE RLS`) policies and role privileges.

Simultaneously, promotion hardens transport security:
- Generates a fresh 256-bit CSPRNG `KB_SESSION_HMAC_KEY_B64`, terminating active sessions and requiring clean operator re-authentication on cutover.
- Rotates database transport credentials (`kanban_app`, `kanban_migrator`, `postgres`).
- Rotates Valkey cache authentication passwords.

---

## 3. Step-by-Step Operator Promotion Procedure

### Step 1: Pre-Flight Verification and Standalone Backup
Inside the standalone container or host environment, export an encrypted backup archive.

```bash
# Set secure 256-bit backup key or passphrase file
export KB_BACKUP_KEY="base64url-encoded-32-byte-key"

# Create atomic encrypted backup bundle with secrets carryover
kanban-ctl backup create \
  --out /var/lib/kanban/backups/promotion-cutover.kbbak \
  --db-url "postgresql://postgres@/kanban?host=/var/run/postgresql" \
  --include-secrets \
  --keyring /var/lib/kanban/data/secrets/keyring.json
```

Verify archive cryptographic integrity, framing, and pgdump checksum prior to stopping standalone services:

```bash
kanban-ctl backup verify \
  --in /var/lib/kanban/backups/promotion-cutover.kbbak
```

### Step 2: Export Multi-Container Production Bundle
Generate the production Compose configuration and Caddyfile for your production domain:

```bash
kanban-ctl promote export-compose \
  --out-dir /opt/kanban-prod \
  --domain kanban.example.com \
  --carry-over-keyring /var/lib/kanban/data/secrets/keyring.json
```

This creates:
- `/opt/kanban-prod/docker-compose.yml`: Configured with the 5-network isolation matrix.
- `/opt/kanban-prod/Caddyfile`: Configured for TLS 1.3, CSP, HSTS, and WebSocket reverse-proxying.
- `/opt/kanban-prod/.env.production` (permissions `0600`): Contains carried-over `MASTER_KEK` and `KB_AUTH_PEPPER`, rotated session keys, and freshly generated database/cache passwords.

### Step 3: Initialize Production Database and Restore
Start the production persistence layer (`postgres` and `valkey`):

```bash
cd /opt/kanban-prod
docker compose up -d postgres valkey
```

Execute lossless restore from the encrypted backup archive into external PostgreSQL 16:

```bash
kanban-ctl restore \
  --in /var/lib/kanban/backups/promotion-cutover.kbbak \
  --target-db-url "postgresql://postgres:${POSTGRES_PASSWORD}@postgres:5432/kanban" \
  --confirm-overwrite
```

### Step 4: Launch Complete Production Stack
Launch all remaining application and agent tiers:

```bash
docker compose up -d
```

Verify service status and health checks:
```bash
docker compose ps
```

---

## 4. Encrypted Archive Format Specification (`KBBAK1`)

The `kanban-ctl` backup subsystem produces authenticated `.kbbak` archives designed for confidentiality at rest and streaming verification without RAM bloat.

### 4.1 Binary Header Layout (37 bytes)
| Offset | Field | Type | Description |
|---|---|---|---|
| `0..7` | Magic | `bytes[8]` | Literal ASCII `KBBAK1\x00\x01` |
| `8` | KDF Mode | `uint8` | `0x01` = Raw 256-bit Key, `0x02` = Argon2id |
| `9..24` | Salt | `bytes[16]` | CSPRNG salt for Argon2id key derivation |
| `25..36` | Base Nonce | `bytes[12]` | CSPRNG base nonce for chunk counters |

### 4.2 Streaming Chunk Framing
Payloads are encrypted in 4 MiB (4,194,304 byte) chunks using `AES-256-GCM`:
- **Nonce Derivation:** Each chunk XORs the 12-byte base nonce with a monotonic uint64 chunk index:
  `nonce = base_nonce ^ (0x00000000 || chunk_index_uint64_be)`.
- **Authenticated Additional Data (AAD):** Binds monotonic index and chunk termination:
  `AAD = "KBBAK1:" || chunk_index_uint64_be || is_final_byte`.
- **Chunk Frame Structure:**
  - `payload_len`: 4 bytes big-endian `uint32` (ciphertext length including 16-byte GCM tag).
  - `is_final`: 1 byte `uint8` (`0x01` for final chunk, `0x00` otherwise).
  - `ciphertext`: `payload_len` bytes.

### 4.3 Inner Tar Bundle
The decrypted stream represents a deterministic POSIX tar archive containing:
1. `manifest.json`: JSON metadata including format version, created timestamp, Alembic migration revision, PostgreSQL engine version, and SHA-256 checksums.
2. `database.pgdump`: PostgreSQL custom format archive (`pg_dump -Fc --no-owner --no-privileges`).
3. `secrets_carryover.json` (optional): Bundles `MASTER_KEK` and `KB_AUTH_PEPPER` when `--include-secrets` is specified.
4. `attachments/` (optional): Content-addressed attachments verified against manifest index.

---

## 5. Security Invariants and Guardrails

1. **Process List Secret Hygiene (`SECRET_IN_ARGV_FORBIDDEN`):**
   Passing secrets directly as command-line arguments (e.g. `--key <value>` or `--passphrase <value>`) is strictly rejected with exit code 2. Secrets must be supplied via `--key-env`, `--passphrase-file`, or interactive stdin prompt.
2. **Fail-Closed Overwrite Protection:**
   The `restore` command inspects the target database schema. If any public tables exist, restore is halted with `TargetDatabaseNotEmptyError` unless explicitly confirmed via `--confirm-overwrite`.
3. **Post-Restore Cryptographic Audit Gate:**
   Every restore operation validates:
   - PostgreSQL role flags: `ALTER ROLE kanban_app NOBYPASSRLS` and `ALTER ROLE app_rls_reader NOBYPASSRLS`.
   - Migration revision: Current `alembic_version` matches `manifest.alembic_revision`.
   - Audit trail hash chains: `verify_activity_chain()` evaluates to valid across every workspace.
   - Object link integrity: `audit_object_links()` yields zero invalid or orphaned links.
   - Tenant isolation: `FORCE ROW LEVEL SECURITY` is verified active on all public tenant tables.
4. **Network Segmentation:**
   The exported `docker-compose.yml` places `mcp-server` strictly on `app_net`, preventing direct route or access to `data_net`. Persistence networks (`data_net`, `sandbox_net`) are marked `internal: true`.
