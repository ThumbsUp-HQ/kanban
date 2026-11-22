# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Software Bill of Materials (SBOM) generation and supply-chain auditing (KAN-34).

Collects Python runtime packages from importlib.metadata and web packages from
build-time verified manifests (sbom-web.json) or package.json fallback with
local and hoisted node_modules inspection. Evaluates license compliance against
ALLOW_SET and license-allowlist.toml, and generates canonical CycloneDX 1.5 JSON documents.
"""

from __future__ import annotations

import functools
import importlib.metadata
import json
import logging
import os
import re
import tomllib
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from kanban.ops.build_info import resolve_platform_version

logger = logging.getLogger(__name__)

PLATFORM_NAME: Final[str] = "👍kanban"
PLATFORM_SLUG: Final[str] = "thumbs-up-kanban"
PLATFORM_TAGLINE: Final[str] = "The difference between a swarm and an Agile team is a kanban."
PLATFORM_VERSION: Final[str] = resolve_platform_version()
PLATFORM_LICENSE_SPDX: Final[str] = "Apache-2.0"

MAX_INLINE_LICENSE_LEN: Final[int] = 100
MAX_FIRST_LINE_LEN: Final[int] = 80

ALLOW_SET: Final[frozenset[str]] = frozenset(
    {
        "MIT",
        "MIT-0",
        "ISC",
        "BSD",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "0BSD",
        "Apache-2.0",
        "PSF-2.0",
        "Python-2.0",
        "PostgreSQL",
        "Zlib",
        "Unlicense",
        "CC0-1.0",
        "BlueOak-1.0.0",
        "MPL-2.0",
    }
)

DENY_PREFIXES: Final[tuple[str, ...]] = (
    "GPL",
    "AGPL",
    "SSPL",
    "LGPL",
    "GNU GENERAL PUBLIC",
    "GNU AFFERO",
    "GNU LESSER",
    "SERVER SIDE PUBLIC",
    "RSAL",
    "BUSL",
    "COMMONS CLAUSE",
)

NORMALIZATION_MAP: Final[dict[str, str]] = {
    "mozilla public license 2.0 (mpl 2.0)": "MPL-2.0",
    "mozilla public license 2.0": "MPL-2.0",
    "mozilla public license": "MPL-2.0",
    "python software foundation license": "PSF-2.0",
    "python software foundation": "PSF-2.0",
    "psf license": "PSF-2.0",
    "psf": "PSF-2.0",
    "psfl": "PSF-2.0",
    "python-2.0": "Python-2.0",
    "apache software license": "Apache-2.0",
    "apache license, version 2.0": "Apache-2.0",
    "apache license 2.0": "Apache-2.0",
    "apache license (v2.0)": "Apache-2.0",
    "apache license": "Apache-2.0",
    "apache 2.0": "Apache-2.0",
    "apache-2.0": "Apache-2.0",
    "apache 2": "Apache-2.0",
    "apache-2": "Apache-2.0",
    "mit license": "MIT",
    "mit": "MIT",
    "bsd license": "BSD",
    "bsd": "BSD",
    "3-clause bsd license": "BSD-3-Clause",
    "bsd 3-clause license": "BSD-3-Clause",
    "bsd 3-clause": "BSD-3-Clause",
    "bsd-3-clause": "BSD-3-Clause",
    "2-clause bsd license": "BSD-2-Clause",
    "bsd 2-clause license": "BSD-2-Clause",
    "bsd 2-clause": "BSD-2-Clause",
    "bsd-2-clause": "BSD-2-Clause",
    "isc license (iscl)": "ISC",
    "isc license": "ISC",
    "isc": "ISC",
    "the unlicense": "Unlicense",
    "unlicense": "Unlicense",
    "postgresql license": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "cmu license": "MIT",
    "cmu": "MIT",
    "0bsd": "0BSD",
    "cc0-1.0": "CC0-1.0",
    "cc0": "CC0-1.0",
    "blueoak-1.0.0": "BlueOak-1.0.0",
    "zlib": "Zlib",
}


@dataclass(frozen=True)
class AllowlistException:
    """Approved third-party license exception loaded from license-allowlist.toml."""

    ecosystem: str
    package: str
    version: str
    license: str
    justification: str


@dataclass(frozen=True)
class Component:
    """Normalized third-party software component for SBOM reporting."""

    name: str
    version: str
    ecosystem: str
    purl: str
    license: str
    license_verdict: str
    scope: str
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert component to dictionary."""
        return asdict(self)


@dataclass(frozen=True)
class SbomSummary:
    """Summary statistics for discovered SBOM components."""

    total_components: int
    python_components: int
    web_components: int
    permissive_count: int
    allowlisted_count: int
    unknown_count: int
    deny_count: int

    def to_dict(self) -> dict[str, Any]:
        """Convert summary to dictionary."""
        return asdict(self)


def is_workspace_package(name: str) -> bool:
    """Check if package belongs to internal Kanban workspace."""
    lowered = name.lower()
    return lowered in {"kanban", "kanban-platform", "kanban-monorepo"} or lowered.startswith(
        ("kanban-", "@kanban/")
    )


def normalize_license_atom(atom: str) -> str:
    """Normalize raw license name to canonical SPDX identifier when known."""
    cleaned = " ".join(atom.strip().split())
    lowered = cleaned.lower()
    if lowered in NORMALIZATION_MAP:
        return NORMALIZATION_MAP[lowered]
    for allowed in ALLOW_SET:
        if lowered == allowed.lower():
            return allowed
    return cleaned


def _classify_atomic(cleaned: str) -> str:
    """Classify a single atomic license string without compound operators."""
    if " with " in cleaned.lower():
        parts = re.split(r"\s+with\s+", cleaned, maxsplit=1, flags=re.IGNORECASE)
        if _classify_atomic(parts[0]) == "ALLOW":
            return "ALLOW"

    normalized = normalize_license_atom(cleaned)
    normalized_upper = normalized.upper()

    for prefix in DENY_PREFIXES:
        if normalized_upper.startswith(prefix):
            return "DENY"

    for allowed in ALLOW_SET:
        if normalized.lower() == allowed.lower():
            return "ALLOW"

    return "UNKNOWN"


def classify_license(license_expr: str) -> str:
    """Classify a license expression into ALLOW, DENY, or UNKNOWN.

    Follows Section 2.5/15.4 rules: permissive licenses in ALLOW_SET are ALLOW,
    copyleft prefixes are DENY, and compound OR/AND expressions are evaluated.
    """
    cleaned = license_expr.strip()
    if not cleaned or cleaned.upper() in {"UNKNOWN", "UNLICENSED", "CUSTOM", "NONE"}:
        return "UNKNOWN"

    cleaned = re.sub(r"[()]", " ", cleaned)
    if " OR " in cleaned:
        sub_verdicts = [classify_license(part) for part in cleaned.split(" OR ")]
        if "ALLOW" in sub_verdicts:
            return "ALLOW"
        return "DENY" if "DENY" in sub_verdicts else "UNKNOWN"

    if " AND " in cleaned:
        sub_verdicts = [classify_license(part) for part in cleaned.split(" AND ")]
        if "DENY" in sub_verdicts:
            return "DENY"
        return "ALLOW" if all(v == "ALLOW" for v in sub_verdicts) else "UNKNOWN"

    return _classify_atomic(cleaned)


def resolve_file_path(filename: str) -> Path | None:
    """Find a project file across repository root, current directory, and container path."""
    candidates = [
        Path(filename),
        Path(__file__).resolve().parents[2] / filename,
        Path("/opt/kanban") / filename,
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None


def load_allowlist(allowlist_path: Path | None = None) -> list[AllowlistException]:
    """Parse license-allowlist.toml into structured exceptions."""
    path = allowlist_path or resolve_file_path("license-allowlist.toml")
    if not path or not path.is_file():
        return []

    try:
        content = path.read_text(encoding="utf-8")
        data = tomllib.loads(content)
        raw_exceptions = data.get("exception", [])
        entries: list[AllowlistException] = []
        for item in raw_exceptions:
            if not isinstance(item, dict):
                continue
            ecosystem = str(item.get("ecosystem", "")).strip().lower()
            package = str(item.get("package", "")).strip().lower()
            version = str(item.get("version", "")).strip()
            lic = str(item.get("license", "")).strip()
            justification = str(item.get("justification", "")).strip()
            if ecosystem and package and version:
                entries.append(
                    AllowlistException(
                        ecosystem=ecosystem,
                        package=package,
                        version=version,
                        license=lic,
                        justification=justification,
                    )
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to parse license-allowlist.toml: %s", exc)
        return []
    else:
        return entries


def find_allowlist_match(
    entries: list[AllowlistException],
    ecosystem: str,
    package: str,
    version: str,
) -> AllowlistException | None:
    """Locate matching allowlist exception by ecosystem, package name, and version."""
    eco = ecosystem.lower()
    pkg = package.lower()
    for entry in entries:
        if entry.ecosystem == eco and entry.package == pkg and entry.version == version:
            return entry
    return None


def _extract_from_classifiers(
    metadata: importlib.metadata.PackageMetadata | object,
) -> str | None:
    get_all_fn = getattr(metadata, "get_all", None)
    get_fn = getattr(metadata, "get", None)
    raw_classifiers = (
        get_all_fn("Classifier")
        if get_all_fn is not None
        else (get_fn("Classifier") if get_fn is not None else None)
    )
    classifiers: list[str] = []
    if isinstance(raw_classifiers, list):
        classifiers = raw_classifiers
    elif isinstance(raw_classifiers, str):
        classifiers = [raw_classifiers]

    for c in classifiers:
        if "License" in c:
            tail = c.split("::")[-1].strip()
            norm = normalize_license_atom(tail)
            if norm in ALLOW_SET or norm.lower() in NORMALIZATION_MAP:
                return norm
    return None


def extract_python_license(dist: importlib.metadata.Distribution) -> str:
    """Extract SPDX expression or normalized license string from distribution metadata."""
    metadata = dist.metadata
    lic_expr = metadata.get("License-Expression")
    if lic_expr and lic_expr.strip():
        return lic_expr.strip()

    lic_field = metadata.get("License")
    if lic_field:
        lic_clean = lic_field.strip()
        if len(lic_clean) < MAX_INLINE_LICENSE_LEN and "\n" not in lic_clean:
            return normalize_license_atom(lic_clean)

    from_classifiers = _extract_from_classifiers(metadata)
    if from_classifiers:
        return from_classifiers

    if lic_field and lic_field.strip():
        first_line = lic_field.strip().split("\n")[0].strip()
        if len(first_line) < MAX_FIRST_LINE_LEN:
            return normalize_license_atom(first_line)

    return "UNKNOWN"


def collect_python_components(
    allowlist: list[AllowlistException] | None = None,
) -> list[Component]:
    """Inspect runtime environment via importlib.metadata.distributions()."""
    entries = allowlist if allowlist is not None else load_allowlist()
    components: list[Component] = []

    try:
        dists = list(importlib.metadata.distributions())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to inspect python distributions: %s", exc)
        return []

    for dist in dists:
        name = dist.metadata.get("Name")
        version = dist.metadata.get("Version")
        if not name or not version or is_workspace_package(name):
            continue

        raw_lic = extract_python_license(dist)
        verdict = classify_license(raw_lic)

        if verdict != "ALLOW":
            match = find_allowlist_match(entries, "python", name, version)
            if match:
                verdict = "ALLOWLISTED"
                if not raw_lic or raw_lic == "UNKNOWN":
                    raw_lic = match.license

        summary = dist.metadata.get("Summary") or ""
        purl = f"pkg:pypi/{name.lower()}@{version}"

        components.append(
            Component(
                name=name,
                version=version,
                ecosystem="python",
                purl=purl,
                license=raw_lic,
                license_verdict=verdict,
                scope="required",
                description=summary,
            )
        )

    components.sort(key=lambda c: c.name.lower())
    return components


def _format_npm_purl(name: str, version: str) -> str:
    """Format canonical npm PURL respecting scoped package percent-encoding."""
    if name.startswith("@") and "/" in name:
        scope, pkg = name.split("/", 1)
        return f"pkg:npm/%40{scope[1:]}/{pkg}@{version}"
    return f"pkg:npm/{name}@{version}"


def _find_web_manifest() -> Path | None:
    """Resolve pre-built sbom-web.json from dist or web directories."""
    candidates = [
        resolve_file_path("kanban/web/dist/sbom-web.json"),
        resolve_file_path("kanban/web/sbom-web.json"),
        resolve_file_path("web/dist/sbom-web.json"),
        Path("/opt/kanban/web/dist/sbom-web.json"),
    ]
    env_dist = os.getenv("KB_WEB_DIST")
    if env_dist:
        candidates.insert(0, Path(env_dist) / "sbom-web.json")

    for p in candidates:
        if p and p.is_file():
            return p
    return None


def _parse_web_manifest(
    manifest_file: Path,
    entries: list[AllowlistException],
) -> list[Component] | None:
    """Parse web manifest JSON into Component objects."""
    try:
        content = manifest_file.read_text(encoding="utf-8")
        data = json.loads(content)
        raw_comps = data.get("components", data if isinstance(data, list) else [])
        components: list[Component] = []
        for item in raw_comps:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            version = str(item.get("version", "")).strip()
            if not name or not version or is_workspace_package(name):
                continue
            raw_lic = str(item.get("license", "UNKNOWN")).strip()
            scope = str(item.get("scope", "required")).strip()
            desc = str(item.get("description", "")).strip()
            purl = str(item.get("purl") or _format_npm_purl(name, version)).strip()

            verdict = classify_license(raw_lic)
            if verdict != "ALLOW":
                match = find_allowlist_match(entries, "node", name, version)
                if match:
                    verdict = "ALLOWLISTED"
                    if raw_lic == "UNKNOWN":
                        raw_lic = match.license

            components.append(
                Component(
                    name=name,
                    version=version,
                    ecosystem="node",
                    purl=purl,
                    license=raw_lic,
                    license_verdict=verdict,
                    scope=scope,
                    description=desc,
                )
            )
        if components:
            components.sort(key=lambda c: c.name.lower())
            return components
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load sbom-web.json: %s", exc)
    return None


def _parse_web_package_json(
    pkg_json_path: Path,
    entries: list[AllowlistException],
) -> list[Component]:
    """Fallback collector parsing kanban/web/package.json and local/hoisted node_modules."""
    try:
        pkg_data = json.loads(pkg_json_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to parse kanban/web/package.json: %s", exc)
        return []

    node_modules_dir = pkg_json_path.parent / "node_modules"
    root_node_modules_dir = pkg_json_path.parent.parent.parent / "node_modules"
    deps = pkg_data.get("dependencies", {})
    dev_deps = pkg_data.get("devDependencies", {})

    all_pkgs: list[tuple[str, str, str]] = [
        (n, str(v).lstrip("^~"), "required") for n, v in deps.items()
    ]
    all_pkgs.extend((n, str(v).lstrip("^~"), "dev") for n, v in dev_deps.items())

    fallback_components: list[Component] = []
    for name, version, scope in all_pkgs:
        if is_workspace_package(name):
            continue

        raw_lic = "UNKNOWN"
        desc = ""
        candidate_paths = [
            node_modules_dir / name / "package.json",
            root_node_modules_dir / name / "package.json",
        ]
        for dep_pkg_path in candidate_paths:
            if dep_pkg_path.is_file():
                try:
                    dep_json = json.loads(dep_pkg_path.read_text(encoding="utf-8"))
                    raw_lic = str(dep_json.get("license") or "UNKNOWN")
                    desc = str(dep_json.get("description") or "")
                    break
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Could not inspect package.json for %s: %s", name, exc)

        verdict = classify_license(raw_lic)
        if verdict != "ALLOW":
            match = find_allowlist_match(entries, "node", name, version)
            if match:
                verdict = "ALLOWLISTED"
                if raw_lic == "UNKNOWN":
                    raw_lic = match.license

        purl = _format_npm_purl(name, version)
        fallback_components.append(
            Component(
                name=name,
                version=version,
                ecosystem="node",
                purl=purl,
                license=raw_lic,
                license_verdict=verdict,
                scope=scope,
                description=desc,
            )
        )

    fallback_components.sort(key=lambda c: c.name.lower())
    return fallback_components


def collect_web_components(
    allowlist: list[AllowlistException] | None = None,
    manifest_path: Path | None = None,
) -> list[Component]:
    """Collect web packages from sbom-web.json or fallback to package.json and node_modules."""
    entries = allowlist if allowlist is not None else load_allowlist()
    manifest_file = manifest_path or _find_web_manifest()

    if manifest_file and manifest_file.is_file():
        parsed = _parse_web_manifest(manifest_file, entries)
        if parsed is not None:
            return parsed

    pkg_json_path = resolve_file_path("kanban/web/package.json")
    if not pkg_json_path or not pkg_json_path.is_file():
        return []

    return _parse_web_package_json(pkg_json_path, entries)


@functools.lru_cache(maxsize=1)
def get_live_components() -> tuple[Component, ...]:
    """Retrieve full cached collection of Python and Web runtime components."""
    allowlist = load_allowlist()
    py_comps = collect_python_components(allowlist)
    web_comps = collect_web_components(allowlist)
    return tuple(py_comps + web_comps)


def clear_sbom_cache() -> None:
    """Clear lru_cache for testing."""
    get_live_components.cache_clear()


def calculate_sbom_summary(components: list[Component] | tuple[Component, ...]) -> SbomSummary:
    """Compute summary metrics from component list."""
    total = len(components)
    python_count = sum(1 for c in components if c.ecosystem == "python")
    web_count = sum(1 for c in components if c.ecosystem == "node")
    permissive_count = sum(1 for c in components if c.license_verdict == "ALLOW")
    allowlisted_count = sum(1 for c in components if c.license_verdict == "ALLOWLISTED")
    unknown_count = sum(1 for c in components if c.license_verdict == "UNKNOWN")
    deny_count = sum(1 for c in components if c.license_verdict == "DENY")

    return SbomSummary(
        total_components=total,
        python_components=python_count,
        web_components=web_count,
        permissive_count=permissive_count,
        allowlisted_count=allowlisted_count,
        unknown_count=unknown_count,
        deny_count=deny_count,
    )


def get_license_texts() -> tuple[str, str]:
    """Read verbatim LICENSE and NOTICE text files."""
    license_path = resolve_file_path("LICENSE")
    notice_path = resolve_file_path("NOTICE")

    license_text = ""
    notice_text = ""

    if license_path and license_path.is_file():
        try:
            license_text = license_path.read_text(encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to read LICENSE: %s", exc)

    if notice_path and notice_path.is_file():
        try:
            notice_text = notice_path.read_text(encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to read NOTICE: %s", exc)

    return license_text, notice_text


def generate_cyclonedx_1_5(
    components: list[Component] | tuple[Component, ...] | None = None,
    serial_number: str | None = None,
) -> dict[str, Any]:
    """Generate canonical CycloneDX 1.5 JSON Software Bill of Materials."""
    comps = components if components is not None else get_live_components()
    sn = serial_number or f"urn:uuid:{uuid.uuid4()}"
    timestamp = datetime.now(UTC).isoformat()

    cdx_components: list[dict[str, Any]] = []
    for c in comps:
        cdx_scope = (
            "optional"
            if c.scope == "dev"
            else (c.scope if c.scope in {"required", "optional", "excluded"} else "required")
        )
        comp_dict: dict[str, Any] = {
            "type": "library",
            "bom-ref": c.purl,
            "name": c.name,
            "version": c.version,
            "purl": c.purl,
            "scope": cdx_scope,
        }
        if c.description:
            comp_dict["description"] = c.description

        if c.license and c.license != "UNKNOWN":
            comp_dict["licenses"] = [{"license": {"id": c.license}}]
        else:
            comp_dict["licenses"] = [{"license": {"name": "Unknown"}}]

        comp_dict["properties"] = [
            {"name": "kanban:ecosystem", "value": c.ecosystem},
            {"name": "kanban:license_verdict", "value": c.license_verdict},
        ]
        cdx_components.append(comp_dict)

    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": sn,
        "version": 1,
        "metadata": {
            "timestamp": timestamp,
            "tools": [
                {
                    "vendor": PLATFORM_NAME,
                    "name": PLATFORM_SLUG,
                    "version": resolve_platform_version(),
                }
            ],
            "component": {
                "type": "application",
                "name": PLATFORM_SLUG,
                "version": resolve_platform_version(),
                "description": PLATFORM_TAGLINE,
                "licenses": [{"license": {"id": PLATFORM_LICENSE_SPDX}}],
                "purl": f"pkg:generic/{PLATFORM_SLUG}@{resolve_platform_version()}",
            },
        },
        "components": cdx_components,
    }
