# syntax=docker/dockerfile:1.7
# Stage 1: web-builder (node:22-bookworm-slim) -> pnpm --frozen-lockfile --ignore-scripts -> Vite SPA + .br/.gz + SRI
FROM node:22-bookworm-slim@sha256:e9f565d32859f0cbfb52125eafe8be39390f24dac302dc3cdf566e8ba3ab21ee AS web-builder
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml .npmrc ./
COPY kanban/web/package.json ./kanban/web/
RUN pnpm install --frozen-lockfile --ignore-scripts
COPY kanban/web/ ./kanban/web/
RUN pnpm --dir kanban/web build

# Stage 2: py-builder (python:3.12-slim-bookworm + uv) -> uv sync --locked --no-dev --no-build-isolation
FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df AS py-builder
COPY --from=ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490 /uv /uvx /bin/
WORKDIR /opt/kanban
ENV UV_PROJECT_ENVIRONMENT=/opt/kanban/.venv \
    UV_COMPILE_BYTECODE=1
COPY pyproject.toml uv.lock ./
COPY database/pyproject.toml ./database/
COPY kanban/pyproject.toml ./kanban/
COPY mcp/pyproject.toml ./mcp/
COPY agent/pyproject.toml ./agent/
RUN uv sync --locked --no-dev --no-install-workspace --no-build-isolation && \
    echo "/opt/kanban" > /opt/kanban/.venv/lib/python3.12/site-packages/kanban.pth

# Stage 3: runtime-slim (python:3.12-slim-bookworm + tini + libpq5 + git, USER 65532:65532)
FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df AS runtime-slim
WORKDIR /opt/kanban
# Base image digest is cryptographically pinned; allowing Debian security updates to flow
# hadolint ignore=DL3008
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        tini \
        libpq5 \
        ca-certificates \
        git && \
    rm -rf /var/lib/apt/lists/* && \
    rm -f /usr/local/bin/pip*
RUN groupadd -r -g 65532 kanban && \
    useradd -r -u 65532 -g 65532 -s /usr/sbin/nologin -M -d /nonexistent kanban
COPY --chown=65532:65532 --from=py-builder /opt/kanban/.venv /opt/kanban/.venv
COPY --chown=65532:65532 database/ /opt/kanban/database/
COPY --chown=65532:65532 kanban/ /opt/kanban/kanban/
COPY --chown=65532:65532 mcp/ /opt/kanban/mcp/
COPY --chown=65532:65532 agent/ /opt/kanban/agent/
COPY --chown=65532:65532 deploy/ /opt/kanban/deploy/
COPY --chown=65532:65532 alembic.ini /opt/kanban/alembic.ini
COPY --chown=65532:65532 LICENSE NOTICE license-allowlist.toml /opt/kanban/
COPY --chown=65532:65532 --from=web-builder /app/kanban/web/dist /opt/kanban/web/dist
RUN printf '#!/bin/sh\nexec /opt/kanban/.venv/bin/python -m kanban.cli.ctl "$@"\n' > /usr/local/bin/kanban-ctl && \
    chmod 0755 /usr/local/bin/kanban-ctl && \
    printf '#!/bin/sh\nexec /opt/kanban/.venv/bin/python -m agent.cli "$@"\n' > /usr/local/bin/kanban-agent && \
    chmod 0755 /usr/local/bin/kanban-agent && \
    ln -sf /usr/local/bin/kanban-ctl /opt/kanban/.venv/bin/kanban-ctl && \
    ln -sf /usr/local/bin/kanban-agent /opt/kanban/.venv/bin/kanban-agent
ENV PATH=/opt/kanban/.venv/bin:/usr/local/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    KB_WEB_DIST=/opt/kanban/web/dist
USER 65532:65532
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "kanban.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

# Stage 4: agent-runner (extends runtime-slim, USER 65532:65532, zero EXPOSE directives)
FROM runtime-slim AS agent-runner
USER root
RUN printf '#!/bin/sh\nexec /opt/kanban/.venv/bin/python -m agent.remote_runner.cli "$@"\n' > /usr/local/bin/kanban-agent-runner && \
    chmod 0755 /usr/local/bin/kanban-agent-runner
USER 65532:65532
ENTRYPOINT ["/usr/bin/tini", "--", "kanban-agent-runner"]
CMD ["run"]

# Stage 4b: sandbox (extends runtime-slim, runs isolated script runner/worker, non-root UID 10001:10001)
FROM runtime-slim AS sandbox
USER root
RUN groupadd -r -g 10001 sandbox && \
    useradd -r -u 10001 -g 10001 -s /usr/sbin/nologin -M -d /nonexistent sandbox && \
    install -d -o sandbox -g sandbox -m 0700 /run/kanban/sandbox && \
    printf '#!/bin/sh\nexec /opt/kanban/.venv/bin/python -m kanban.sandbox.worker "$@"\n' > /usr/local/bin/kanban-sandbox-worker && \
    chmod 0755 /usr/local/bin/kanban-sandbox-worker
USER 10001:10001
ENTRYPOINT ["/usr/bin/tini", "--", "kanban-sandbox-worker"]
CMD ["run"]

# Stage 5: standalone (default final stage: extends runtime-slim + PostgreSQL 16 + pgvector)
FROM runtime-slim AS standalone
# The standalone stage remains USER root only because the PID-1 entrypoint (KB-P0-08)
# must start PostgreSQL as postgres and drop Uvicorn to 65532 via setpriv.
# hadolint ignore=DL3002,DL3066
USER root
# Base image digest is cryptographically pinned; allowing Debian security updates to flow
# hadolint ignore=DL3008
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        gnupg && \
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc -o /tmp/ACCC4CF8.asc && \
    gpg --dearmor -o /etc/apt/trusted.gpg.d/apt.postgresql.org.gpg /tmp/ACCC4CF8.asc && \
    rm -f /tmp/ACCC4CF8.asc && \
    gpg --show-keys --with-colons /etc/apt/trusted.gpg.d/apt.postgresql.org.gpg > /tmp/pgdg-keys.txt && \
    grep -q "B97B0AFCAA1A47F044F244A07FCC7D46ACCC4CF8" /tmp/pgdg-keys.txt && \
    rm -f /tmp/pgdg-keys.txt && \
    echo "deb [signed-by=/etc/apt/trusted.gpg.d/apt.postgresql.org.gpg] http://apt.postgresql.org/pub/repos/apt/ bookworm-pgdg main" > /etc/apt/sources.list.d/pgdg.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        postgresql-16 \
        postgresql-16-pgvector \
        procps \
        util-linux && \
    apt-get purge -y --auto-remove curl gnupg && \
    rm -rf /var/lib/apt/lists/*
RUN usermod -aG kanban postgres && \
    install -d -o kanban -g kanban -m 0775 /var/lib/kanban/data && \
    install -d -o postgres -g postgres -m 0700 /var/lib/kanban/data/pgdata && \
    install -d -o kanban -g kanban -m 0775 /var/lib/kanban/data/backups && \
    install -d -o postgres -g kanban -m 2775 /run/postgresql
EXPOSE 8080
VOLUME /var/lib/kanban/data
ENTRYPOINT ["/usr/bin/tini", "--", "/opt/kanban/.venv/bin/python", "/opt/kanban/deploy/standalone/entrypoint.py"]
