"""Validation tool asserting Docker Compose network isolation and service hardening."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

EXPECTED_SERVICE_NETWORKS: dict[str, set[str]] = {
    "reverse-proxy": {"edge_net", "app_net"},
    "kanban-api": {"app_net", "data_net"},
    "mcp-server": {"app_net"},
    "agent-runtime": {"app_net", "egress_llm_net"},
    "script-sandbox": {"sandbox_net"},
    "outbox-relay": {"data_net"},
    "postgres": {"data_net"},
    "valkey": {"data_net"},
}

EXPECTED_NETWORKS_INTERNAL: dict[str, bool] = {
    "app_net": True,
    "data_net": True,
    "sandbox_net": True,
    "edge_net": False,
    "egress_llm_net": False,
}

SECRET_ENV_REGEX = re.compile(r"(?i)(password|secret|kek)=?.{8,}")


def _check_service_names(services: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    expected_services = set(EXPECTED_SERVICE_NETWORKS.keys())
    actual_services = set(services.keys())

    missing_services = expected_services - actual_services
    if missing_services:
        violations.append(f"Missing required services: {sorted(missing_services)}")

    extra_services = actual_services - expected_services
    if extra_services:
        violations.append(f"Unexpected services found: {sorted(extra_services)}")

    return violations


def _check_service_networks(services: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    for srv_name, expected_nets in EXPECTED_SERVICE_NETWORKS.items():
        if srv_name not in services:
            continue
        srv_data = services[srv_name]
        raw_nets = srv_data.get("networks")
        actual_nets = set(raw_nets.keys()) if isinstance(raw_nets, dict) else set(raw_nets or [])

        if actual_nets != expected_nets:
            violations.append(
                f"Service '{srv_name}' networks mismatch: expected {sorted(expected_nets)}, "
                f"got {sorted(actual_nets)}"
            )

        if srv_name == "mcp-server" and "data_net" in actual_nets:
            violations.append("Service 'mcp-server' must NOT connect to 'data_net'")

    return violations


def _check_networks_internal(networks: object) -> list[str]:
    if not isinstance(networks, dict):
        return ["Top-level 'networks' mapping is missing or invalid"]

    violations: list[str] = []
    for net_name, expected_internal in EXPECTED_NETWORKS_INTERNAL.items():
        net_data = networks.get(net_name)
        if not isinstance(net_data, dict):
            violations.append(f"Network '{net_name}' is missing from networks definition")
            continue
        actual_internal = bool(net_data.get("internal", False))
        if actual_internal != expected_internal:
            violations.append(
                f"Network '{net_name}' internal flag mismatch: expected {expected_internal}, "
                f"got {actual_internal}"
            )
    return violations


def _check_port_publishing(services: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    for srv_name, srv_data in services.items():
        ports = srv_data.get("ports") or []
        if ports and srv_name != "reverse-proxy":
            violations.append(
                f"Service '{srv_name}' publishes ports {ports}; "
                "only 'reverse-proxy' may publish ports"
            )
    return violations


def _check_hardening(services: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    for srv_name, srv_data in services.items():
        cap_drop = [str(c).upper() for c in (srv_data.get("cap_drop") or [])]
        if "ALL" not in cap_drop:
            violations.append(f"Service '{srv_name}' missing cap_drop containing 'ALL'")

        sec_opts = [str(o).lower() for o in (srv_data.get("security_opt") or [])]
        if not any("no-new-privileges:true" in opt for opt in sec_opts):
            violations.append(
                f"Service '{srv_name}' missing 'no-new-privileges:true' in security_opt"
            )
    return violations


def _check_plaintext_secrets(services: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    for srv_name, srv_data in services.items():
        env = srv_data.get("environment") or {}
        if isinstance(env, dict):
            for k, v in env.items():
                if str(k).upper().endswith("_FILE"):
                    continue
                full_val = f"{k}={v}" if v is not None else str(k)
                if SECRET_ENV_REGEX.search(full_val):
                    violations.append(
                        f"Service '{srv_name}' contains potential secret in environment: '{k}'"
                    )
        elif isinstance(env, list):
            for item in env:
                item_str = str(item)
                if "_FILE=" in item_str.upper():
                    continue
                if SECRET_ENV_REGEX.search(item_str):
                    violations.append(
                        f"Service '{srv_name}' contains potential secret in environment: "
                        f"'{item_str}'"
                    )
    return violations


def _check_sandbox_profile(services: dict[str, Any]) -> list[str]:
    sandbox_data = services.get("script-sandbox")
    if sandbox_data:
        profiles = sandbox_data.get("profiles") or []
        if "sandbox" not in profiles:
            return ["Service 'script-sandbox' must specify profile 'sandbox'"]
    return []


def validate_compose_dict(config: dict[str, Any]) -> list[str]:
    """Validate parsed Docker Compose configuration against architectural invariants."""
    services = config.get("services")
    if not isinstance(services, dict):
        return ["Top-level 'services' mapping is missing or invalid"]

    violations: list[str] = []
    violations.extend(_check_service_names(services))
    violations.extend(_check_service_networks(services))
    violations.extend(_check_networks_internal(config.get("networks")))
    violations.extend(_check_port_publishing(services))
    violations.extend(_check_hardening(services))
    violations.extend(_check_plaintext_secrets(services))
    violations.extend(_check_sandbox_profile(services))

    return violations


def _load_config_from_file(file_path: str) -> dict[str, Any] | None:
    try:
        path = Path(file_path)
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as err:
        sys.stderr.write(f"Error reading JSON config '{file_path}': {err}\n")
        return None

    if isinstance(data, dict):
        return data
    sys.stderr.write("Parsed Compose configuration is not a valid JSON object\n")
    return None


def _collect_config_dynamically(compose_file: str) -> dict[str, Any] | None:
    cmd = [
        "docker",
        "compose",
        "-f",
        compose_file,
        "--profile",
        "sandbox",
        "config",
        "--format",
        "json",
    ]
    try:
        proc = subprocess.run(  # noqa: S603
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as err:
        sys.stderr.write(f"Error executing docker compose config: {err}\n")
        return None

    if proc.returncode != 0:
        sys.stderr.write(f"docker compose config command failed:\n{proc.stderr}\n")
        return None

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as err:
        sys.stderr.write(f"Error executing docker compose config: {err}\n")
        return None

    if isinstance(data, dict):
        return data
    sys.stderr.write("Parsed Compose configuration is not a valid JSON object\n")
    return None


def main(argv: list[str] | None = None) -> int:
    """Parse CLI arguments, collect or read compose config, and validate."""
    parser = argparse.ArgumentParser(
        description="Verify Docker Compose network isolation and security hardening."
    )
    parser.add_argument(
        "--config-json",
        type=str,
        help="Path to pre-collected Docker Compose JSON config file.",
    )
    parser.add_argument(
        "--compose-file",
        type=str,
        default="docker-compose.yml",
        help="Path to docker-compose.yml file when collecting dynamically.",
    )
    args = parser.parse_args(argv)

    if args.config_json:
        config_data = _load_config_from_file(args.config_json)
    else:
        config_data = _collect_config_dynamically(args.compose_file)

    if config_data is None:
        return 3

    violations = validate_compose_dict(config_data)
    if violations:
        sys.stdout.write(f"FAIL: {len(violations)} compose policy violation(s) found:\n")
        for v in violations:
            sys.stdout.write(f"  - {v}\n")
        return 1

    sys.stdout.write("PASS: Docker Compose network isolation and hardening policies verified.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
