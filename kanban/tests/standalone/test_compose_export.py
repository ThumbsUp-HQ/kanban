"""Unit tests for standalone to production Compose bundle exporter."""

from __future__ import annotations

import json
import stat
from typing import TYPE_CHECKING

import yaml

from kanban.standalone.compose_export import export_production_bundle

if TYPE_CHECKING:
    from pathlib import Path


def test_compose_export_with_keyring_carryover(tmp_path: Path) -> None:  # noqa: PLR0915
    """Test exporting compose bundle carrying over MASTER_KEK and KB_AUTH_PEPPER."""
    # Create synthetic standalone keyring.json
    keyring_dir = tmp_path / "secrets"
    keyring_dir.mkdir(parents=True)
    keyring_file = keyring_dir / "keyring.json"

    master_kek = "k4zX9_EXAMPLE_MASTER_KEK_BASE64URL_32B_KEY123"
    auth_pepper = "p8wY2_EXAMPLE_AUTH_PEPPER_BASE64URL_32B_KEY45"
    old_session_key = "s1aB3_OLD_SESSION_KEY_TO_BE_ROTATED_AWAY123"

    keyring_file.write_text(
        json.dumps(
            {
                "version": 1,
                "created_at": "2026-11-11T00:00:00Z",
                "MASTER_KEK": master_kek,
                "KB_AUTH_PEPPER": auth_pepper,
                "SESSION_HMAC_KEY": old_session_key,
                "db_roles": {
                    "kanban_app": "app_pw_123",
                    "kanban_migrator": "mig_pw_123",
                },
            }
        ),
        encoding="utf-8",
    )

    out_dir = tmp_path / "prod_bundle"
    domain = "kanban.production.corp"

    summary = export_production_bundle(
        out_dir=out_dir,
        keyring_path=keyring_file,
        domain=domain,
    )

    assert summary.carried_over_secrets is True
    assert summary.domain == domain

    # 1. Verify docker-compose.yml structure and network isolation
    assert summary.compose_path.is_file()
    compose_content = summary.compose_path.read_text(encoding="utf-8")
    compose_data = yaml.safe_load(compose_content)

    assert "services" in compose_data
    assert "networks" in compose_data

    # Networks check
    networks = compose_data["networks"]
    assert "edge_net" in networks
    assert networks["app_net"].get("internal") is True
    assert networks["data_net"].get("internal") is True
    assert networks["sandbox_net"].get("internal") is True
    assert "egress_llm_net" in networks

    # Services check
    services = compose_data["services"]
    assert "reverse-proxy" in services
    assert set(services["reverse-proxy"]["networks"]) == {"edge_net", "app_net"}
    # Verify port 8444 is exposed on reverse-proxy
    assert "8444:8444" in services["reverse-proxy"]["ports"]

    assert "kanban-api" in services
    assert set(services["kanban-api"]["networks"]) == {"app_net", "data_net"}
    # Verify KB_TRUSTED_PROXIES environment variable configured for app_net
    api_env = services["kanban-api"].get("environment", {})
    assert "KB_TRUSTED_PROXIES" in api_env

    # CRITICAL: mcp-server must strictly NOT be on data_net
    assert "mcp-server" in services
    assert set(services["mcp-server"]["networks"]) == {"app_net"}
    assert "data_net" not in services["mcp-server"]["networks"]

    assert "agent-runtime" in services
    assert set(services["agent-runtime"]["networks"]) == {"app_net", "egress_llm_net"}

    assert "script-sandbox" in services
    assert set(services["script-sandbox"]["networks"]) == {"sandbox_net"}

    assert "postgres" in services
    assert set(services["postgres"]["networks"]) == {"data_net"}

    assert "valkey" in services
    assert set(services["valkey"]["networks"]) == {"data_net"}

    # 2. Verify Caddyfile content
    assert summary.caddyfile_path.is_file()
    caddy_content = summary.caddyfile_path.read_text(encoding="utf-8")
    assert domain in caddy_content
    assert "protocols tls1.3" in caddy_content
    assert "Content-Security-Policy" in caddy_content
    assert "reverse_proxy kanban-api:8000" in caddy_content
    assert "reverse_proxy mcp-server:8000" in caddy_content

    # Action 1: Stripped spoofable headers and blocked internal routes
    assert "@internal_routes path /internal/* /api/v1/internal/*" in caddy_content
    assert "respond @internal_routes 404" in caddy_content
    assert "header_up -X-Client-Cert-Pem" in caddy_content
    assert "header_up -X-KB-Service-Principal" in caddy_content
    assert "header_up -X-KB-Internal-Auth" in caddy_content

    # Action 2: Dedicated :8444 runner mTLS block
    assert ":8444 {" in caddy_content
    assert "mode require" in caddy_content
    assert "@runner_ws path /api/v1/runners/ws /api/v1/runners/ws/*" in caddy_content
    assert "X-Client-Cert-Pem {http.request.tls.client.certificate_pem}" in caddy_content
    assert "X-Client-Cert-Der-B64 {http.request.tls.client.certificate_der_base64}" in caddy_content

    # 3. Verify .env.production permissions and secret carryover / rotation
    assert summary.env_path.is_file()
    mode = stat.S_IMODE(summary.env_path.stat().st_mode)
    assert mode == 0o600

    env_content = summary.env_path.read_text(encoding="utf-8")
    env_vars: dict[str, str] = {}
    for line in env_content.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            env_vars[k.strip()] = v.strip()

    assert env_vars["KB_DOMAIN"] == domain
    # Preserved secrets
    assert env_vars["KB_MASTER_KEK_B64"] == master_kek
    assert env_vars["KB_AUTH_PEPPER_B64"] == auth_pepper
    assert env_vars["KB_TRUSTED_PROXIES"] == "172.28.0.0/16"

    # Rotated session key: MUST be distinct from old_session_key!
    assert "KB_SESSION_HMAC_KEY_B64" in env_vars
    assert env_vars["KB_SESSION_HMAC_KEY_B64"] != old_session_key
    assert len(env_vars["KB_SESSION_HMAC_KEY_B64"]) >= 32

    # Freshly generated database passwords
    assert "POSTGRES_PASSWORD" in env_vars
    assert "KANBAN_APP_PASSWORD" in env_vars
    assert "KANBAN_MIGRATOR_PASSWORD" in env_vars
    assert "VALKEY_PASSWORD" in env_vars


def test_compose_export_without_keyring(tmp_path: Path) -> None:
    """Test exporting compose bundle when no standalone keyring exists."""
    out_dir = tmp_path / "fresh_prod"
    summary = export_production_bundle(
        out_dir=out_dir,
        keyring_path=None,
        domain="fresh.kanban.local",
    )

    assert summary.carried_over_secrets is False
    assert summary.env_path.is_file()
    mode = stat.S_IMODE(summary.env_path.stat().st_mode)
    assert mode == 0o600

    env_content = summary.env_path.read_text(encoding="utf-8")
    assert "KB_MASTER_KEK_B64=" in env_content
    assert "KB_AUTH_PEPPER_B64=" in env_content
    assert "KB_SESSION_HMAC_KEY_B64=" in env_content
    assert "KB_TRUSTED_PROXIES=172.28.0.0/16" in env_content


def test_compose_export_nonexistent_or_corrupt_keyring(tmp_path: Path) -> None:
    """Test edge cases with nonexistent, invalid JSON, and non-dict keyring files."""
    # 1. Non-existent path
    out_dir1 = tmp_path / "nonexistent_keyring"
    summary1 = export_production_bundle(
        out_dir=out_dir1,
        keyring_path=tmp_path / "does_not_exist.json",
        domain="localhost",
    )
    assert summary1.carried_over_secrets is False

    # 2. Corrupt JSON
    corrupt_file = tmp_path / "corrupt.json"
    corrupt_file.write_text("NOT_VALID_JSON{", encoding="utf-8")
    out_dir2 = tmp_path / "corrupt_keyring"
    summary2 = export_production_bundle(
        out_dir=out_dir2,
        keyring_path=corrupt_file,
        domain="localhost",
    )
    assert summary2.carried_over_secrets is False

    # 3. Valid JSON but not a dict (e.g., JSON list)
    list_file = tmp_path / "list_keyring.json"
    list_file.write_text("[1, 2, 3]", encoding="utf-8")
    out_dir3 = tmp_path / "list_keyring"
    summary3 = export_production_bundle(
        out_dir=out_dir3,
        keyring_path=list_file,
        domain="localhost",
    )
    assert summary3.carried_over_secrets is False

    # 4. Partial keyring (only MASTER_KEK, missing pepper)
    partial_file = tmp_path / "partial.json"
    partial_file.write_text(json.dumps({"MASTER_KEK": "partial_kek"}), encoding="utf-8")
    out_dir4 = tmp_path / "partial_keyring"
    summary4 = export_production_bundle(
        out_dir=out_dir4,
        keyring_path=partial_file,
        domain="localhost",
    )
    assert summary4.carried_over_secrets is False
