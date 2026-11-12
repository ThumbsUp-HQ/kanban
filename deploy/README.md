# Deployment Architecture and Operations Guide

This directory contains container deployment configurations, reverse-proxy definitions, and secrets management guidelines for the Kanban platform.

## 1. Secrets Generation for Production Compose Stack

The production Compose stack (`docker-compose.yml`) consumes runtime secrets exclusively via Docker Compose secrets mounts from `deploy/secrets/`. These files are strictly gitignored and must never be committed to source control.

To generate the required secrets for local or staging environments:

```bash
# Create directory with restricted permissions
install -d -m 0700 deploy/secrets

# Generate 256-bit cryptographic secrets
openssl rand -base64 32 > deploy/secrets/postgres_password.txt
openssl rand -base64 32 > deploy/secrets/master_kek.txt

# Enforce strict file permissions
chmod 0600 deploy/secrets/*.txt
```

### Managed Secrets List
- `postgres_password.txt`: Database administrative and connection password for PostgreSQL 16.
- `master_kek.txt`: Master Key Encryption Key (256-bit AES-GCM) for envelope encryption of authentication card secrets and credentials.

---

## 2. Network Isolation Architecture

The production compose stack enforces strict network segmentation across five isolated networks:

1. `edge_net` (bridge):
   - Ingress network for external traffic.
   - Connected only to `reverse-proxy` (Caddy).
   - Only `reverse-proxy` publishes ports (`80:80`, `443:443`, `443:443/udp`).

2. `app_net` (`internal: true`):
   - Internal application communication bus.
   - Connects `reverse-proxy`, `kanban-api`, `mcp-server`, and `agent-runtime`.
   - Has zero route to the external internet.

3. `data_net` (`internal: true`):
   - Internal persistence tier.
   - Connects `kanban-api`, `outbox-relay`, `postgres`, and `valkey`.
   - `mcp-server` has NO route to `data_net` (zero direct database connectivity).

4. `sandbox_net` (`internal: true`):
   - Isolated tier B custom script execution environment.
   - Connects `script-sandbox` only.

5. `egress_llm_net` (bridge):
   - Dedicated outbound network for `agent-runtime` to reach external LLM APIs (OpenAI, Gemini, Ollama).

---

## 3. Container Hardening Invariants

Every production container adheres to strict security defaults:
- `read_only: true`: Root filesystem is mounted read-only with ephemeral `tmpfs` mounts for `/tmp` and `/run`.
- `cap_drop: [ALL]`: All Linux capabilities dropped by default (`reverse-proxy` adds only `NET_BIND_SERVICE`).
- `security_opt: ["no-new-privileges:true"]`: Prevents privilege escalation.
- `user: "65532:65532"`: Non-root execution for all application containers.
- Resource limits: Explicit `mem_limit` and `pids_limit` constraints on every service.
