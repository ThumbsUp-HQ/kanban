"""Static validation test suite for Dockerfile and .dockerignore contracts."""

import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DOCKERFILE_PATH = REPO_ROOT / "Dockerfile"
DOCKERIGNORE_PATH = REPO_ROOT / ".dockerignore"

REQUIRED_STAGES = [
    "web-builder",
    "py-builder",
    "runtime-slim",
    "agent-runner",
    "sandbox",
    "standalone",
]
REQUIRED_DOCKERIGNORE_ENTRIES = [
    ".git",
    ".venv",
    "node_modules",
    "**/__pycache__",
    "docs/qa",
    ".env*",
    "*.pem",
    "*.key",
    "ci-logs",
    "reports",
]

SECRET_PATTERN = re.compile(r"(?i)(secret|password|passwd|token|key|kek|pepper)")
SECRET_ALLOWLIST = {
    "KB_WEB_DIST",
    "PATH",
    "PYTHONDONTWRITEBYTECODE",
    "PYTHONUNBUFFERED",
    "UV_PROJECT_ENVIRONMENT",
    "UV_COMPILE_BYTECODE",
}
SHA256_PINNED_PATTERN = re.compile(r"@sha256:[0-9a-fA-F]{64}$")
CURL_SH_PATTERN = re.compile(r"(?:curl|wget)\s+[^|]+\|\s*(?:ba)?sh")
FORBIDDEN_SOURCE_PATTERN = re.compile(r"(\.env|\.pem|\.key|keyring\.json)")


def get_logical_lines(content: str) -> list[str]:
    """Parse Dockerfile content into logical lines, joining backslash continuations."""
    logical_lines: list[str] = []
    current_line = ""
    for raw_line in content.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.endswith("\\"):
            current_line += stripped[:-1].rstrip() + " "
        else:
            current_line += stripped
            logical_lines.append(current_line.strip())
            current_line = ""
    if current_line:
        logical_lines.append(current_line.strip())
    return logical_lines


def parse_dockerfile_stages(content: str) -> list[dict[str, Any]]:
    """Parse logical lines into structured stage dictionaries."""
    logical_lines = get_logical_lines(content)
    stages: list[dict[str, Any]] = []
    current_stage: dict[str, Any] | None = None

    for line in logical_lines:
        match = re.match(r"^FROM\s+(?:--\S+\s+)*(\S+)\s+AS\s+(\S+)$", line, re.IGNORECASE)
        if match:
            current_stage = {
                "image": match.group(1),
                "name": match.group(2),
                "instructions": [],
                "raw_lines": [line],
            }
            stages.append(current_stage)
        elif current_stage is not None:
            parts = line.split(None, 1)
            inst = parts[0].upper()
            body = parts[1] if len(parts) > 1 else ""
            current_stage["instructions"].append((inst, body))
            current_stage["raw_lines"].append(line)

    return stages


def extract_env_arg_names(instruction: str, body: str) -> list[str]:
    """Extract variable names declared in ENV or ARG instructions."""
    names: list[str] = []
    if instruction == "ARG":
        arg_match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)", body)
        if arg_match:
            names.append(arg_match.group(1))
    elif instruction == "ENV":
        if "=" in body:
            matches = re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*=", body)
            names.extend(matches)
        else:
            env_match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)", body)
            if env_match:
                names.append(env_match.group(1))
    return names


def test_dockerfile_stages_and_sha256_pinning() -> None:
    """Test Case 1: Positive check of stage names, order, default last, and sha256 pinning."""
    assert DOCKERFILE_PATH.is_file(), f"Dockerfile not found at {DOCKERFILE_PATH}"
    content = DOCKERFILE_PATH.read_text(encoding="utf-8")
    lines = content.splitlines()

    assert lines[0].strip() == "# syntax=docker/dockerfile:1.7", (
        "Dockerfile must declare # syntax=docker/dockerfile:1.7 on line 1"
    )

    stages = parse_dockerfile_stages(content)
    assert len(stages) == len(REQUIRED_STAGES), (
        f"Expected exactly {len(REQUIRED_STAGES)} stages, found {len(stages)}"
    )

    stage_names = [s["name"] for s in stages]
    assert stage_names == REQUIRED_STAGES, (
        f"Stage names and order mismatch: expected {REQUIRED_STAGES}, got {stage_names}"
    )
    assert stages[-1]["name"] == "standalone", "Final/default stage must be standalone"

    declared_stage_names = set()
    for stage in stages:
        image = str(stage["image"])
        name = str(stage["name"])
        if image not in declared_stage_names:
            assert SHA256_PINNED_PATTERN.search(image), (
                f"External image '{image}' in stage '{name}' is not pinned with @sha256:<64hex>"
            )
        declared_stage_names.add(name)

    # Verify external COPY --from references are also pinned with sha256
    for stage in stages:
        for inst, body in stage["instructions"]:
            if inst == "COPY" and "--from=" in body:
                match = re.search(r"--from=(\S+)", body)
                if match:
                    from_ref = match.group(1)
                    if from_ref not in declared_stage_names:
                        assert SHA256_PINNED_PATTERN.search(from_ref), (
                            f"COPY --from external reference '{from_ref}' not pinned with sha256"
                        )


def test_runtime_slim_and_standalone_directives() -> None:
    """Test Case 2: Positive check of USER, ENTRYPOINT, EXPOSE, and VOLUME instructions."""
    content = DOCKERFILE_PATH.read_text(encoding="utf-8")
    stages = parse_dockerfile_stages(content)
    stage_dict = {s["name"]: s for s in stages}

    # runtime-slim checks
    slim_stage = stage_dict["runtime-slim"]
    user_instructions = [body for inst, body in slim_stage["instructions"] if inst == "USER"]
    assert "65532:65532" in user_instructions, "runtime-slim stage must contain 'USER 65532:65532'"

    entrypoint_instructions = [
        body for inst, body in slim_stage["instructions"] if inst == "ENTRYPOINT"
    ]
    assert len(entrypoint_instructions) == 1, "runtime-slim must specify exactly one ENTRYPOINT"
    assert "/usr/bin/tini" in entrypoint_instructions[0], (
        f"runtime-slim ENTRYPOINT must invoke /usr/bin/tini, got {entrypoint_instructions[0]}"
    )

    # standalone checks
    standalone_stage = stage_dict["standalone"]
    expose_instructions = [
        body for inst, body in standalone_stage["instructions"] if inst == "EXPOSE"
    ]
    assert "8080" in expose_instructions, "standalone stage must declare 'EXPOSE 8080'"

    volume_instructions = [
        body for inst, body in standalone_stage["instructions"] if inst == "VOLUME"
    ]
    assert "/var/lib/kanban/data" in volume_instructions, (
        "standalone stage must declare 'VOLUME /var/lib/kanban/data'"
    )


def test_security_zero_secrets_and_no_remote_add() -> None:
    """Test Case 3: Negative security check for secrets, bad sources, remote ADD, curl|sh."""
    content = DOCKERFILE_PATH.read_text(encoding="utf-8")
    stages = parse_dockerfile_stages(content)

    for stage in stages:
        for inst, body in stage["instructions"]:
            if inst in ("ARG", "ENV"):
                var_names = extract_env_arg_names(inst, body)
                for var_name in var_names:
                    if var_name in SECRET_ALLOWLIST:
                        continue
                    assert not SECRET_PATTERN.search(var_name), (
                        f"Prohibited secret-like variable '{var_name}' in stage {stage['name']}"
                    )

            if inst in ("COPY", "ADD"):
                assert not FORBIDDEN_SOURCE_PATTERN.search(body), (
                    f"Forbidden file pattern copied in stage {stage['name']}: {body}"
                )

            if inst == "ADD":
                assert not re.search(r"https?://|ftp://", body, re.IGNORECASE), (
                    f"Remote URL in ADD instruction is prohibited: {body}"
                )

            if inst == "RUN":
                assert not CURL_SH_PATTERN.search(body), (
                    f"Prohibited curl/wget piped to shell found in stage {stage['name']}: {body}"
                )


def test_dockerignore_entries() -> None:
    """Test Case 4: Boundary check verifying .dockerignore excludes all required paths."""
    assert DOCKERIGNORE_PATH.is_file(), f".dockerignore not found at {DOCKERIGNORE_PATH}"
    content = DOCKERIGNORE_PATH.read_text(encoding="utf-8")
    entries = {
        line.strip()
        for line in content.splitlines()
        if line.strip() and not line.strip().startswith("#")
    }

    for required in REQUIRED_DOCKERIGNORE_ENTRIES:
        assert required in entries, f"Required entry '{required}' missing from .dockerignore"


def test_runtime_slim_apt_install_packages() -> None:
    """Test Case 5: Positive check of runtime-slim apt install packages & banned tools."""
    content = DOCKERFILE_PATH.read_text(encoding="utf-8")
    stages = parse_dockerfile_stages(content)
    stage_dict = {s["name"]: s for s in stages}

    slim_stage = stage_dict["runtime-slim"]
    apt_runs = [
        body
        for inst, body in slim_stage["instructions"]
        if inst == "RUN" and "apt-get install" in body
    ]
    assert len(apt_runs) >= 1, "runtime-slim must execute an apt-get install command"

    combined_apt = " ".join(apt_runs)
    assert "tini" in combined_apt, "runtime-slim apt-get install must include 'tini'"
    assert "libpq5" in combined_apt, "runtime-slim apt-get install must include 'libpq5'"

    banned_packages = ["gcc", "build-essential", "nodejs", "postgresql"]
    for banned in banned_packages:
        assert not re.search(rf"\b{banned}\b", combined_apt), (
            f"Banned package '{banned}' detected in runtime-slim apt-get install: {combined_apt}"
        )


# Unit tests for helper functions to maintain >=95% branch coverage
def test_get_logical_lines_continuations() -> None:
    """Validate multiline line-continuation joining and comment stripping."""
    sample = "# comment\nRUN echo foo \\\n    && echo bar\n\n# another\nUSER 1000\\\n"
    lines = get_logical_lines(sample)
    assert len(lines) == 2
    assert lines[0] == "RUN echo foo && echo bar"
    assert lines[1] == "USER 1000"


def test_extract_env_arg_names_variants() -> None:
    """Validate ARG and ENV syntax variants for name extraction."""
    assert extract_env_arg_names("ARG", "MY_ARG=default") == ["MY_ARG"]
    assert extract_env_arg_names("ARG", "PLAIN_ARG") == ["PLAIN_ARG"]
    assert extract_env_arg_names("ARG", "   ") == []
    assert extract_env_arg_names("ENV", "FOO=1 BAR=2") == ["FOO", "BAR"]
    assert extract_env_arg_names("ENV", "SINGLE_VAL val") == ["SINGLE_VAL"]
    assert extract_env_arg_names("ENV", "   ") == []
    assert extract_env_arg_names("OTHER", "ignored") == []


def test_security_rules_on_synthetic_samples() -> None:
    """Validate negative security patterns on synthetic snippets."""
    sample = "FROM alpine:3.20 AS test-stage\nENV APP_NAME=kanban\nADD local.txt /opt/local.txt\n"
    stages = parse_dockerfile_stages(sample)
    assert len(stages) == 1
    for stage in stages:
        for inst, body in stage["instructions"]:
            if inst in ("ARG", "ENV"):
                var_names = extract_env_arg_names(inst, body)
                for var_name in var_names:
                    assert not SECRET_PATTERN.search(var_name)
            if inst == "ADD":
                assert not re.search(r"https?://|ftp://", body, re.IGNORECASE)


def test_parse_dockerfile_stages_structure() -> None:
    """Validate stage parsing behavior with custom input."""
    sample = "FROM base:1.0 AS first\nRUN echo first\nFROM first AS second\nUSER root\n"
    stages = parse_dockerfile_stages(sample)
    assert len(stages) == 2
    assert stages[0]["name"] == "first"
    assert stages[1]["name"] == "second"
    assert stages[1]["image"] == "first"
