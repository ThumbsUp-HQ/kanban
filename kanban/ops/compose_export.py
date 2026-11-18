"""Standalone to production Compose bundle exporter.

Emits hardened 5-network docker-compose.yml, Caddyfile, and .env.production
carrying over MASTER_KEK and KB_AUTH_PEPPER while rotating session keys.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger("kanban.ops.compose_export")

ENV_FILE_MODE: Final[int] = 0o600

POSTGRES_IMAGE: Final[str] = (
    "pgvector/pgvector:pg16@sha256:0dd3149a06e4579a0d70d8fef9945636cd514005e7237deb27f9b67886f8dc4f"
)
VALKEY_IMAGE: Final[str] = (
    "valkey/valkey:8.0-alpine@sha256:19f0b3d350f5e6de618086d79ecdc9c474ab159bebb16ed95a92e4211562fee5"
)
CADDY_IMAGE: Final[str] = (
    "caddy:2.8-alpine@sha256:af32e97399febea808609119bb21544d0265c58a02836576e32a2d082c262c17"
)

CSP_VALUE: Final[str] = (
    "default-src 'none'; script-src 'self'; worker-src 'self'; style-src 'self'; "
    "img-src 'self' blob: data:image/png data:image/webp; font-src 'self'; "
    "connect-src 'self' wss:; media-src 'self'; object-src 'none'; base-uri 'none'; "
    "form-action 'self'; frame-ancestors 'none'; require-trusted-types-for 'script'; "
    "trusted-types kanban-sanitizer dompurify;"
)


def _get_compose_template() -> str:
    """Return formatted docker-compose.yml content enforcing 5-network isolation."""
    return f"""services:
  reverse-proxy:
    image: {CADDY_IMAGE}
    restart: unless-stopped
    read_only: true
    cap_drop:
      - ALL
    cap_add:
      - NET_BIND_SERVICE
    security_opt:
      - "no-new-privileges:true"
    pids_limit: 100
    mem_limit: 256m
    tmpfs:
      - /tmp
      - /var/run
    ports:
      - "80:80"
      - "443:443"
      - "443:443/udp"
    networks:
      - edge_net
      - app_net
    volumes:
      - caddy_data:/data
      - caddy_config:/config
      - web_dist:/srv/www:ro
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
    environment:
      KB_DOMAIN: "${{KB_DOMAIN}}"

  kanban-api:
    image: kanban:runtime-slim
    restart: unless-stopped
    read_only: true
    user: "65532:65532"
    cap_drop:
      - ALL
    security_opt:
      - "no-new-privileges:true"
    pids_limit: 200
    mem_limit: 512m
    tmpfs:
      - /tmp
    command:
      - "uvicorn"
      - "kanban.app:create_app"
      - "--factory"
      - "--host"
      - "0.0.0.0"
      - "--port"
      - "8000"
      - "--proxy-headers"
      - "--forwarded-allow-ips=*"
    networks:
      - app_net
      - data_net
    depends_on:
      postgres:
        condition: service_healthy
      kanban-migrate:
        condition: service_completed_successfully
    env_file:
      - .env.production

  kanban-migrate:
    image: kanban:runtime-slim
    restart: "no"
    read_only: true
    user: "65532:65532"
    cap_drop:
      - ALL
    security_opt:
      - "no-new-privileges:true"
    pids_limit: 100
    mem_limit: 256m
    tmpfs:
      - /tmp
    command: ["alembic", "upgrade", "head"]
    networks:
      - data_net
    depends_on:
      postgres:
        condition: service_healthy
    env_file:
      - .env.production

  mcp-server:
    image: kanban:runtime-slim
    restart: unless-stopped
    read_only: true
    user: "65532:65532"
    cap_drop:
      - ALL
    security_opt:
      - "no-new-privileges:true"
    pids_limit: 100
    mem_limit: 512m
    tmpfs:
      - /tmp
    command: ["python", "-m", "kanban.mcp_placeholder"]
    networks:
      - app_net

  agent-runtime:
    image: kanban:runtime-slim
    restart: unless-stopped
    read_only: true
    user: "65532:65532"
    cap_drop:
      - ALL
    security_opt:
      - "no-new-privileges:true"
    pids_limit: 100
    mem_limit: 1024m
    tmpfs:
      - /tmp
    command: ["python", "-m", "kanban.agent_placeholder"]
    networks:
      - app_net
      - egress_llm_net

  script-sandbox:
    image: kanban:sandbox
    profiles:
      - sandbox
    restart: unless-stopped
    read_only: true
    cap_drop:
      - ALL
    security_opt:
      - "no-new-privileges:true"
    pids_limit: 50
    mem_limit: 256m
    tmpfs:
      - /tmp
    networks:
      - sandbox_net

  outbox-relay:
    image: kanban:runtime-slim
    restart: unless-stopped
    read_only: true
    user: "65532:65532"
    cap_drop:
      - ALL
    security_opt:
      - "no-new-privileges:true"
    pids_limit: 100
    mem_limit: 256m
    tmpfs:
      - /tmp
    command: ["python", "-m", "kanban.relay_placeholder"]
    networks:
      - data_net
    depends_on:
      kanban-migrate:
        condition: service_completed_successfully
    env_file:
      - .env.production

  postgres:
    image: {POSTGRES_IMAGE}
    restart: unless-stopped
    read_only: true
    cap_drop:
      - ALL
    security_opt:
      - "no-new-privileges:true"
    pids_limit: 200
    mem_limit: 1024m
    tmpfs:
      - /tmp
      - /var/run/postgresql
    volumes:
      - pgdata:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: "${{POSTGRES_DB:-kanban}}"
      POSTGRES_USER: "${{POSTGRES_USER:-postgres}}"
      POSTGRES_PASSWORD: "${{POSTGRES_PASSWORD}}"
    networks:
      - data_net
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${{POSTGRES_USER:-postgres}}"]
      interval: 5s
      timeout: 5s
      retries: 5

  valkey:
    image: {VALKEY_IMAGE}
    restart: unless-stopped
    read_only: true
    cap_drop:
      - ALL
    security_opt:
      - "no-new-privileges:true"
    pids_limit: 100
    mem_limit: 256m
    tmpfs:
      - /tmp
    volumes:
      - valkeydata:/data
    networks:
      - data_net
    healthcheck:
      test: ["CMD", "valkey-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

networks:
  edge_net:
    driver: bridge
  app_net:
    internal: true
  data_net:
    internal: true
  sandbox_net:
    internal: true
  egress_llm_net:
    driver: bridge

volumes:
  caddy_data:
  caddy_config:
  web_dist:
  pgdata:
  valkeydata:
"""


def _get_caddyfile_content(domain: str) -> str:
    """Return formatted Caddyfile for domain terminating TLS 1.3."""
    return f"""{{
	servers {{
		protocols h1 h2 h3
	}}
}}

{domain} {{
	tls {{
		protocols tls1.3
	}}

	header {{
		Content-Security-Policy "{CSP_VALUE}"
		Strict-Transport-Security "max-age=63072000; includeSubDomains"
		X-Content-Type-Options "nosniff"
		Referrer-Policy "no-referrer"
		X-Frame-Options "DENY"
		-Server
	}}

	handle /api/* {{
		reverse_proxy kanban-api:8000
	}}

	handle /ws {{
		reverse_proxy kanban-api:8000 {{
			flush_interval -1
		}}
	}}

	handle /sse* {{
		reverse_proxy kanban-api:8000 {{
			flush_interval -1
		}}
	}}

	handle /mcp/* {{
		reverse_proxy mcp-server:8000 {{
			flush_interval -1
		}}
	}}

	handle {{
		root * /srv/www
		try_files {{path}} /index.html
		file_server {{
			precompressed br gzip
		}}
		@assets path /assets/*
		header @assets Cache-Control "public, max-age=31536000, immutable"
		@html path / /index.html
		header @html Cache-Control "no-cache"
	}}
}}
"""


@dataclass(frozen=True)
class ComposeExportSummary:
    """Summary of exported standalone to production bundle."""

    out_dir: Path
    compose_path: Path
    caddyfile_path: Path
    env_path: Path
    carried_over_secrets: bool
    domain: str


def _generate_secret_b64url() -> str:
    """Generate 256-bit CSPRNG secret encoded as unpadded base64url string."""
    return base64.urlsafe_b64encode(os.urandom(32)).decode("ascii").rstrip("=")


def _load_standalone_keyring(keyring_path: Path) -> dict[str, Any] | None:
    """Read and validate standalone keyring.json file if present."""
    if not keyring_path.is_file():
        return None
    try:
        content = keyring_path.read_text(encoding="utf-8")
        data = json.loads(content)
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as err:
        logger.warning("Could not read standalone keyring at %s: %s", keyring_path, err)
    return None


def export_production_bundle(
    out_dir: Path,
    *,
    keyring_path: Path | None = None,
    domain: str = "localhost",
) -> ComposeExportSummary:
    """Export hardened 5-network multi-container production bundle."""
    out_dir.mkdir(parents=True, exist_ok=True)

    compose_path = out_dir / "docker-compose.yml"
    compose_path.write_text(_get_compose_template(), encoding="utf-8")

    caddyfile_path = out_dir / "Caddyfile"
    caddyfile_path.write_text(_get_caddyfile_content(domain), encoding="utf-8")

    carried_over = False
    master_kek_b64 = ""
    pepper_b64 = ""

    if keyring_path is not None:
        keyring_data = _load_standalone_keyring(keyring_path)
        if keyring_data:
            master_kek_b64 = str(keyring_data.get("MASTER_KEK", ""))
            pepper_b64 = str(keyring_data.get("KB_AUTH_PEPPER", ""))
            if master_kek_b64 and pepper_b64:
                carried_over = True

    if not master_kek_b64:
        master_kek_b64 = _generate_secret_b64url()
    if not pepper_b64:
        pepper_b64 = _generate_secret_b64url()

    fresh_session_key_b64 = _generate_secret_b64url()
    fresh_pg_password = _generate_secret_b64url()
    fresh_app_password = _generate_secret_b64url()
    fresh_migrator_password = _generate_secret_b64url()
    fresh_valkey_password = _generate_secret_b64url()

    env_lines = [
        f"KB_DOMAIN={domain}",
        f"KB_MASTER_KEK_B64={master_kek_b64}",
        f"KB_AUTH_PEPPER_B64={pepper_b64}",
        f"KB_SESSION_HMAC_KEY_B64={fresh_session_key_b64}",
        "POSTGRES_DB=kanban",
        "POSTGRES_USER=postgres",
        f"POSTGRES_PASSWORD={fresh_pg_password}",
        f"KANBAN_APP_PASSWORD={fresh_app_password}",
        f"KANBAN_MIGRATOR_PASSWORD={fresh_migrator_password}",
        f"VALKEY_PASSWORD={fresh_valkey_password}",
    ]
    env_content = "\n".join(env_lines) + "\n"

    env_path = out_dir / ".env.production"
    env_path.write_text(env_content, encoding="utf-8")
    env_path.chmod(ENV_FILE_MODE)

    return ComposeExportSummary(
        out_dir=out_dir,
        compose_path=compose_path,
        caddyfile_path=caddyfile_path,
        env_path=env_path,
        carried_over_secrets=carried_over,
        domain=domain,
    )
