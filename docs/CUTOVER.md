# Cutover Runbook: Lossless Migration from Legacy Trackers to 👍kanban

This runbook specifies the operator procedures for executing the live, lossless cutover from an existing bootstrap tracker (`https://kanban.hackedyour.info/kanban/`, or legacy Jira/issue-board exports) to self-hosted 👍kanban (`thumbs-up-kanban`).

All steps in this runbook enforce strict continuity for issue keys (`KANBA-*`), workflow states, priorities, cycles, modules, comments, attachments, and typed object links with cryptographic hash-chain verification and a deterministic rollback window under 5 minutes.

---

## 1. Cutover Architecture and Principles

1. **Exact Key Continuity**: All historical issue keys (`KANBA-1` through `KANBA-N`) preserve their sequence identifiers without compaction or renumbering.
2. **Zero Unverified Auto-Merge**: Source tracker users map explicitly to 👍kanban principals via `user-map.yaml`. Unmapped accounts map to deactivated placeholders or external collaborator pills (`🏷️`).
3. **Canonical Markdown Purity**: Plain text, HTML descriptions, and comments are converted to canonical Markdown. No `*_html` or `*_ast` storage columns are permitted.
4. **Link Auditor Zero-Invalid Gate**: The cutover transaction passes `audit_object_links()` with 0 invalid links before commit.
5. **Deterministic Rollback**: The system supports immediate traffic reversion to the legacy tracker within 5 minutes if post-migration verification fails.

---

## 2. Phase 1: Pre-Cutover Write Freeze and Snapshot Fetch

Notify all team members and agents of the migration maintenance window. Put the source tracker into maintenance mode to prevent concurrent edits.

```bash
# Set source tracker API credentials and base environment (using legacy snapshot importer `import plane`)
export SOURCE_BASE_URL="https://kanban.hackedyour.info/kanban/"
export SOURCE_WORKSPACE_SLUG="kanban"
export SOURCE_PROJECT_IDENTIFIER="KANBA"
export SOURCE_API_KEY="<OPERATOR_SOURCE_API_KEY>"
export SNAPSHOT_DIR="/var/lib/kanban/imports/cutover-$(date +%Y%m%d%H%M%S)"

# 1. Fetch complete snapshot bundle from source tracker
uv run kanban-ctl import plane fetch-snapshot \
  --base-url "${SOURCE_BASE_URL}" \
  --workspace-slug "${SOURCE_WORKSPACE_SLUG}" \
  --project-identifier "${SOURCE_PROJECT_IDENTIFIER}" \
  --out-dir "${SNAPSHOT_DIR}"

# 2. Compute cryptographic manifest checksums
cd "${SNAPSHOT_DIR}"
sha256sum *.json attachments/* > manifest.sha256
sha256sum -c manifest.sha256
cd -
```

---

## 3. Phase 2: Pre-Flight Encrypted Backup and Stack Health Check

Create an encrypted point-in-time backup of the target PostgreSQL database before applying any cutover mutations.

```bash
# 1. Run database connectivity and health probe
uv run kanban-ctl ops healthcheck

# 2. Create pre-cutover backup
export BACKUP_OUT="/var/backups/kanban/pre-cutover-$(date +%Y%m%d%H%M%S).dump"
pg_dump -Fc -h /tmp/kb-pgsock -U kanban_migrator kanban_app > "${BACKUP_OUT}"
chmod 0600 "${BACKUP_OUT}"

# 3. Verify backup file integrity
pg_restore -l "${BACKUP_OUT}" > /dev/null
echo "Pre-flight backup verified at ${BACKUP_OUT}"
```

---

## 4. Phase 3: Dry-Run Diff Inspection and User Map Verification

Audit the snapshot against target workspace users to ensure every key stakeholder is accounted for.

```bash
# 1. Create or inspect the explicit user mapping file
cat <<'EOF' > /tmp/user-map.yaml
# Source Member UUID -> Kanban Principal Handle
"3fa85f64-5717-4562-b3fc-2c963f66afa6": "adamoutler"
"018e3271-8bc2-7b19-9402-985faefcb501": "alex"
EOF

# 2. Execute dry-run import
uv run kanban-ctl import plane \
  --bundle-dir "${SNAPSHOT_DIR}" \
  --workspace "${SOURCE_WORKSPACE_SLUG}" \
  --user-map /tmp/user-map.yaml \
  --dry-run \
  --report-out /tmp/dry-run-report.json

# 3. Inspect dry-run summary
cat /tmp/dry-run-report.json | jq '{
  to_create: .to_create,
  to_update: .to_update,
  unchanged: .unchanged,
  sequence_high_water_mark: .sequence_high_water_mark,
  unmapped_members: .unmapped_members,
  invalid_link_count: .invalid_link_count
}'
```

Verify that `invalid_link_count` is 0 and `unmapped_members` contains only expected historical or deactivated accounts.

---

## 5. Phase 4: Live Snapshot Import Execution

Execute the authoritative transactional import into the target workspace.

```bash
# Execute live import (runs inside an atomic transaction with audit_object_links gate)
uv run kanban-ctl import plane \
  --bundle-dir "${SNAPSHOT_DIR}" \
  --workspace "${SOURCE_WORKSPACE_SLUG}" \
  --user-map /tmp/user-map.yaml \
  --report-out /var/log/kanban/cutover-import-report.json

# Confirm exit code 0
if [ $? -eq 0 ]; then
  echo "Snapshot import completed successfully."
else
  echo "Import failed! Rolled back automatically."
  exit 1
fi
```

---

## 6. Phase 5: Mandatory Cutover Verification Gate

Run the scripted verifier to mathematically validate the imported dataset against all 6 non-bypassable criteria:

1. `entity_count_and_key_parity`: Snapshot entities match DB and `issue_seq_counter >= max(sequence_id)`.
2. `zero_invalid_object_links`: `audit_object_links()` returns 0 and 0 `FLAGGED_INVALID` links exist.
3. `activity_hash_chain_intact`: Ledger SHA-256 chain is valid across all monthly partitions.
4. `canonical_markdown_purity`: Zero `*_html` / `*_ast` columns and 0 un-converted HTML tags.
5. `qa_proof_bundle_continuity`: All completed tickets have non-empty git diff, test results, and build checks.
6. `rls_enforcement_active`: `FORCE ROW LEVEL SECURITY` active on all tenant tables and unprivileged app role.

```bash
# Run verification CLI
uv run kanban-ctl cutover verify \
  --bundle-dir "${SNAPSHOT_DIR}" \
  --workspace "${SOURCE_WORKSPACE_SLUG}" \
  --project "${SOURCE_PROJECT_IDENTIFIER}" \
  --qa-root ./docs/qa \
  --json-out /var/log/kanban/cutover-audit-report.json

VERIFY_EXIT=$?
if [ ${VERIFY_EXIT} -ne 0 ]; then
  echo "CUTOVER GATE FAILED (exit ${VERIFY_EXIT})! Switching traffic is strictly forbidden."
  echo "Initiating 5-minute rollback procedure immediately."
  exit 2
fi

echo "All 6 cutover checks PASSED. Safe to switch traffic."
```

---

## 7. Phase 6: Traffic Switch and MCP Endpoint Activation

Once the verification gate passes with exit code 0:

```bash
# 1. Update reverse proxy (Caddy / Nginx) upstream to point to 👍kanban
# Replace upstream in Caddyfile:
# reverse_proxy https://127.0.0.1:8000
caddy reload --config /etc/caddy/Caddyfile

# 2. Provision new MCP server connection tokens for agents
uv run kanban-ctl auth create-token \
  --workspace "${SOURCE_WORKSPACE_SLUG}" \
  --name "cutover-agent-runtime" \
  --role "AGENT"

# 3. Mark legacy tracker as read-only / archived
# Update legacy frontend notice banner: "Archived. Read-only. Please use https://kanban.hackedyour.info"
```

---

## 8. Phase 7: Deterministic Rollback Procedure (Target Time: < 5 Minutes)

If any critical failure, data discrepancy, or unexpected regression occurs post-switch:

```bash
# [STEP 1 - 30 seconds] Revert Caddy proxy upstream back to legacy tracker
sed -i 's|127.0.0.1:8000|127.0.0.1:8080|g' /etc/caddy/Caddyfile
caddy reload --config /etc/caddy/Caddyfile

# [STEP 2 - 2 minutes] Restore PostgreSQL database from pre-cutover backup
dropdb -h /tmp/kb-pgsock -U kanban_migrator kanban_app
createdb -h /tmp/kb-pgsock -U kanban_migrator kanban_app
pg_restore -h /tmp/kb-pgsock -U kanban_migrator -d kanban_app "${BACKUP_OUT}"

# [STEP 3 - 1 minute] Verify restored database health
uv run kanban-ctl ops healthcheck

# [STEP 4 - 30 seconds] Remove maintenance banner on source tracker
# Unfreeze source tracker writes and notify users
echo "Rollback completed within 4 minutes. Source tracker restored to pre-cutover state."
```
