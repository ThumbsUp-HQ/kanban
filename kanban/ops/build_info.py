# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Build, commit, and OpenAPI/frontend bundle fingerprinting (KAN-57)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kanban.ops.sbom import PLATFORM_VERSION


@dataclass(frozen=True)
class BuildInfo:
    """Runtime build metadata and cryptographic bundle signatures."""

    git_commit: str
    build_timestamp: str | None
    openapi_version: str
    openapi_bundle_hash: str | None = None
    frontend_bundle_hash: str | None = None


def resolve_git_commit(cwd: Path | None = None) -> str:
    """Resolve git commit SHA from environment variables or git CLI fallback."""
    env_commit = os.environ.get("KB_GIT_COMMIT") or os.environ.get("GIT_SHA")
    if env_commit and env_commit.strip():
        return env_commit.strip()

    git_bin = shutil.which("git") or "/usr/bin/git"
    try:
        res = subprocess.run(  # noqa: S603
            [git_bin, "rev-parse", "--short=12", "HEAD"],
            cwd=cwd or Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return "unknown"

    return "unknown"


def resolve_build_timestamp() -> str | None:
    """Resolve build timestamp from environment variable or None."""
    ts = os.environ.get("KB_BUILD_TIMESTAMP")
    if ts and ts.strip():
        return ts.strip()
    return None


def compute_openapi_bundle_hash(openapi_doc: dict[str, Any]) -> str:
    """Compute deterministic SHA-256 fingerprint over OpenAPI paths and components."""
    subset = {
        "paths": openapi_doc.get("paths", {}),
        "components": openapi_doc.get("components", {}),
    }
    raw = json.dumps(subset, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def resolve_frontend_bundle_hash(repo_root: Path | None = None) -> str | None:
    """Resolve frontend bundle hash from sri-manifest.json or built index bundle."""
    root = repo_root or Path(__file__).resolve().parents[2]
    dist_dir = root / "kanban" / "web" / "dist"
    if not dist_dir.exists():
        env_dist = os.environ.get("KB_WEB_DIST")
        if env_dist:
            dist_dir = Path(env_dist)

    if not dist_dir.exists():
        return None

    manifest_file = dist_dir / "sri-manifest.json"
    if manifest_file.is_file():
        try:
            content = manifest_file.read_bytes()
            return hashlib.sha256(content).hexdigest()
        except OSError:
            pass

    assets_dir = dist_dir / "assets"
    if assets_dir.is_dir():
        for asset in sorted(assets_dir.glob("index-*.js")):
            try:
                content = asset.read_bytes()
                return hashlib.sha256(content).hexdigest()
            except OSError:
                continue

    return None


def get_build_info(openapi_doc: dict[str, Any] | None = None) -> BuildInfo:
    """Return consolidated BuildInfo snapshot."""
    bundle_hash = compute_openapi_bundle_hash(openapi_doc) if openapi_doc else None
    return BuildInfo(
        git_commit=resolve_git_commit(),
        build_timestamp=resolve_build_timestamp(),
        openapi_version=PLATFORM_VERSION,
        openapi_bundle_hash=bundle_hash,
        frontend_bundle_hash=resolve_frontend_bundle_hash(),
    )
