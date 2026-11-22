# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: T201, C901, PLR0911, PLR0912, PLR0915, PLR2004, E501, BLE001, PTH123, PTH101, TRY300
"""Authentication and configuration management for kanban-cli (KAN-48)."""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
import sys
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

__all__ = [
    "ResolvedConfig",
    "auth_login",
    "auth_logout",
    "auth_status",
    "get_config_dir",
    "get_credentials_path",
    "load_config",
    "load_credentials",
    "resolve_config",
    "save_credentials",
]


@dataclass(frozen=True)
class ResolvedConfig:
    """Resolved runtime configuration according to strict precedence rules."""

    url: str
    workspace: str | None
    project: str | None
    token: str | None


def get_config_dir() -> Path:
    """Return path to Kanban CLI configuration directory."""
    custom_dir = os.environ.get("KANBAN_CONFIG_DIR")
    if custom_dir:
        return Path(custom_dir)
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        return Path(xdg_config) / "kanban"
    return Path.home() / ".config" / "kanban"


def get_config_path() -> Path:
    """Return path to config.toml."""
    return get_config_dir() / "config.toml"


def get_credentials_path() -> Path:
    """Return path to credentials.toml."""
    return get_config_dir() / "credentials.toml"


def load_config() -> dict[str, Any]:
    """Load configuration from config.toml if it exists."""
    cfg_path = get_config_path()
    if not cfg_path.exists():
        return {}
    try:
        content = cfg_path.read_text(encoding="utf-8")
        return tomllib.loads(content)
    except Exception:
        return {}


def load_credentials() -> dict[str, Any]:
    """Load credentials from credentials.toml enforcing 0600 permissions and rejecting symlinks.

    Raises:
        ValueError: If credentials.toml is a symlink or has looser permissions than 0600.

    """
    cred_path = get_credentials_path()
    if not cred_path.exists():
        return {}

    # Reject symlinks fail-closed
    if cred_path.is_symlink():
        msg = f"Security error: credentials file '{cred_path}' must not be a symlink"
        raise ValueError(msg)

    # Check permissions (must not have group or world permissions)
    file_stat = cred_path.stat()
    file_mode = file_stat.st_mode & 0o777
    if file_mode & 0o077 != 0:
        msg = (
            f"Security error: credentials file '{cred_path}' has insecure permissions {oct(file_mode)}; "
            f"expected 0600"
        )
        raise ValueError(msg)

    try:
        content = cred_path.read_text(encoding="utf-8")
        return tomllib.loads(content)
    except Exception as exc:
        msg = f"Failed to parse credentials file: {exc}"
        raise ValueError(msg) from exc


def save_credentials(data: dict[str, Any]) -> None:
    """Write credentials securely to credentials.toml with 0600 permissions."""
    cfg_dir = get_config_dir()
    cfg_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    cred_path = get_credentials_path()

    if cred_path.is_symlink():
        msg = f"Security error: credentials file '{cred_path}' must not be a symlink"
        raise ValueError(msg)

    content_lines: list[str] = []
    for k, v in data.items():
        if isinstance(v, str):
            content_lines.append(f'{k} = "{v}"')
        elif isinstance(v, bool):
            content_lines.append(f"{k} = {str(v).lower()}")
        elif isinstance(v, (int, float)):
            content_lines.append(f"{k} = {v}")
    content = "\n".join(content_lines) + "\n"

    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(cred_path, flags, 0o600)
    try:
        with open(fd, "w", encoding="utf-8") as f:
            f.write(content)
    finally:
        pass
    os.chmod(cred_path, 0o600)


def resolve_config(
    cli_url: str | None = None,
    cli_workspace: str | None = None,
    cli_project: str | None = None,
    cli_token: str | None = None,
) -> ResolvedConfig:
    """Resolve active configuration in strict precedence order.

    Precedence:
    1. CLI flags (--url, --workspace, --project, --token / --api-key)
    2. Environment variables (KANBAN_URL, KANBAN_WORKSPACE, KANBAN_PROJECT, KANBAN_API_KEY / KANBAN_TOKEN)
    3. Configuration files (~/.config/kanban/config.toml, ~/.config/kanban/credentials.toml)
    4. Default fallback (http://localhost:8080)
    """
    file_cfg = load_config()
    file_creds: dict[str, Any] = {}
    try:
        file_creds = load_credentials()
    except ValueError as err:
        print(f"Warning: {err}", file=sys.stderr)

    url = cli_url or os.environ.get("KANBAN_URL") or file_cfg.get("url") or "http://localhost:8080"
    workspace = (
        cli_workspace or os.environ.get("KANBAN_WORKSPACE") or file_cfg.get("workspace") or None
    )
    project = cli_project or os.environ.get("KANBAN_PROJECT") or file_cfg.get("project") or None
    token = (
        cli_token
        or os.environ.get("KANBAN_API_KEY")
        or os.environ.get("KANBAN_TOKEN")
        or file_creds.get("api_key")
        or file_creds.get("token")
        or None
    )

    return ResolvedConfig(
        url=url.rstrip("/"),
        workspace=workspace,
        project=project,
        token=token,
    )


def auth_login(
    url: str,
    *,
    device: bool = False,
    token: str | None = None,
    client: httpx.Client | None = None,
) -> int:
    """Execute auth login command via manual token, RFC 8628 device flow, or PKCE."""
    if token:
        save_credentials({"api_key": token})
        print(f"Authentication token saved successfully to {get_credentials_path()}")
        return 0

    http_client = client or httpx.Client(base_url=url, timeout=30.0)
    try:
        if device:
            # RFC 8628 Device Authorization Flow
            dev_resp = http_client.post(
                "/oauth/device/authorize",
                data={"client_id": "kanban-cli", "scope": "mcp:all"},
            )
            if dev_resp.status_code >= 400:
                print(f"Device authorization failed: {dev_resp.text}", file=sys.stderr)
                return 1
            data = dev_resp.json()
            user_code = data.get("user_code")
            verification_uri = data.get("verification_uri_complete") or data.get("verification_uri")
            device_code = data.get("device_code")
            interval = int(data.get("interval", 5))

            print("=== Kanban CLI Device Login ===")
            print(f"Please open the following URL in your browser: {verification_uri}")
            print(f"Enter user code if prompted: {user_code}")
            print("Waiting for authorization...")

            # Poll for token
            start_time = time.time()
            expires_in = int(data.get("expires_in", 300))
            while time.time() - start_time < expires_in:
                time.sleep(interval)
                tok_resp = http_client.post(
                    "/oauth/token",
                    data={
                        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                        "device_code": device_code,
                        "client_id": "kanban-cli",
                    },
                )
                if tok_resp.status_code == 200:
                    tok_data = tok_resp.json()
                    access_token = tok_data.get("access_token")
                    if access_token:
                        save_credentials({"api_key": access_token})
                        print(
                            f"Authentication successful! Credentials saved to {get_credentials_path()}"
                        )
                        return 0
                tok_err = (
                    tok_resp.json().get("error")
                    if tok_resp.headers.get("content-type", "").startswith("application/json")
                    else ""
                )
                if tok_err and tok_err not in ("authorization_pending", "slow_down"):
                    print(f"Device authorization error: {tok_err}", file=sys.stderr)
                    return 1

            print("Device authorization timed out.", file=sys.stderr)
            return 1

        # Standard OAuth 2.1 PKCE Flow
        code_verifier = secrets.token_urlsafe(64)
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        code_challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

        auth_url = (
            f"{url}/oauth/authorize?response_type=code&client_id=kanban-cli"
            f"&code_challenge={code_challenge}&code_challenge_method=S256&scope=mcp:all"
        )
        print("=== Kanban CLI Login ===")
        print(f"Please visit the following URL to authenticate:\n{auth_url}\n")
        print("After approving, enter the authorization code below:")
        try:
            auth_code = input("Authorization Code: ").strip()
        except EOFError:
            auth_code = ""

        if not auth_code:
            print("Login cancelled (no authorization code provided).", file=sys.stderr)
            return 1

        tok_resp = http_client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": auth_code,
                "code_verifier": code_verifier,
                "client_id": "kanban-cli",
            },
        )
        if tok_resp.status_code != 200:
            print(f"Token exchange failed: {tok_resp.text}", file=sys.stderr)
            return 1

        tok_data = tok_resp.json()
        access_token = tok_data.get("access_token")
        if access_token:
            save_credentials({"api_key": access_token})
            print(f"Authentication successful! Credentials saved to {get_credentials_path()}")
            return 0

        print("Login failed: no access token returned in response.", file=sys.stderr)
        return 1
    finally:
        if client is None:
            http_client.close()


def auth_status(
    config: ResolvedConfig,
    *,
    client: httpx.Client | None = None,
) -> int:
    """Print current configuration status and probe remote API connectivity."""
    print("=== Kanban CLI Status ===")
    print(f"URL:       {config.url}")
    print(f"Workspace: {config.workspace or '(not configured)'}")
    print(f"Project:   {config.project or '(not configured)'}")
    token = config.token
    if token:
        token_preview = f"configured ({token[:6]}...)" if len(token) >= 6 else "configured"
    else:
        token_preview = "none"  # noqa: S105
    print(f"Auth Token: {token_preview}")

    if not config.token:
        print("Status: Unauthenticated (run 'kanban-cli auth login' to authenticate)")
        return 0

    http_client = client or httpx.Client(
        base_url=config.url,
        headers={"Authorization": f"Bearer {config.token}"},
        timeout=10.0,
    )
    try:
        resp = http_client.get("/api/v1/auth/session")
        if resp.status_code == 200:
            sess_data = resp.json()
            user_info = sess_data.get("user") or {}
            handle = user_info.get("handle") or user_info.get("email") or "authenticated user"
            print(f"Connection: Active (Logged in as {handle})")
            return 0
        print(f"Connection: Unauthorized (HTTP {resp.status_code})", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Connection: Failed to reach server ({exc})", file=sys.stderr)
        return 1
    finally:
        if client is None:
            http_client.close()


def auth_logout() -> int:
    """Clear credentials from credentials.toml."""
    cred_path = get_credentials_path()
    if cred_path.exists():
        try:
            cred_path.unlink()
            print(f"Credentials removed from {cred_path}. Logged out successfully.")
            return 0
        except Exception as exc:
            print(f"Failed to remove credentials file: {exc}", file=sys.stderr)
            return 1
    print("No credentials found. Already logged out.")
    return 0
