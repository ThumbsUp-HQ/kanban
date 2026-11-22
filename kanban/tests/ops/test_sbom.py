# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for Software Bill of Materials (SBOM) generator (KAN-34)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    import pytest

from kanban.ops.sbom import (
    ALLOW_SET,
    DENY_PREFIXES,
    NORMALIZATION_MAP,
    PLATFORM_LICENSE_SPDX,
    PLATFORM_NAME,
    PLATFORM_SLUG,
    PLATFORM_TAGLINE,
    PLATFORM_VERSION,
    AllowlistException,
    Component,
    _classify_atomic,
    _format_npm_purl,
    _parse_web_manifest,
    _parse_web_package_json,
    calculate_sbom_summary,
    classify_license,
    clear_sbom_cache,
    collect_python_components,
    collect_web_components,
    extract_python_license,
    find_allowlist_match,
    generate_cyclonedx_1_5,
    get_license_texts,
    get_live_components,
    is_workspace_package,
    load_allowlist,
    normalize_license_atom,
    resolve_file_path,
)


def test_platform_metadata_constants() -> None:
    """Verify platform metadata branding invariants."""
    assert PLATFORM_NAME == "👍kanban"
    assert PLATFORM_SLUG == "thumbs-up-kanban"
    assert "Agile team" in PLATFORM_TAGLINE
    assert PLATFORM_VERSION == "2.0.0"
    assert PLATFORM_LICENSE_SPDX == "Apache-2.0"
    assert "MIT" in ALLOW_SET
    assert "GPL" in DENY_PREFIXES
    assert NORMALIZATION_MAP["mit license"] == "MIT"


def test_is_workspace_package() -> None:
    """Verify internal workspace package identification."""
    assert is_workspace_package("kanban") is True
    assert is_workspace_package("kanban-platform") is True
    assert is_workspace_package("kanban-core") is True
    assert is_workspace_package("@kanban/web") is True
    assert is_workspace_package("fastapi") is False
    assert is_workspace_package("react") is False


def test_normalize_license_atom() -> None:
    """Verify normalization of license identifiers."""
    assert normalize_license_atom("mit license") == "MIT"
    assert normalize_license_atom("apache license, version 2.0") == "Apache-2.0"
    assert normalize_license_atom("bsd 2-clause") == "BSD-2-Clause"
    assert normalize_license_atom("psfl") == "PSF-2.0"
    assert normalize_license_atom("mit") == "MIT"
    assert normalize_license_atom("UnknownLicenseX") == "UnknownLicenseX"


def test_classify_license_atomic_and_compounds() -> None:
    """Verify classification across single and compound license expressions."""
    assert classify_license("") == "UNKNOWN"
    assert classify_license("   ") == "UNKNOWN"
    assert classify_license("UNKNOWN") == "UNKNOWN"
    assert classify_license("Unlicensed") == "UNKNOWN"
    assert classify_license("CUSTOM") == "UNKNOWN"
    assert classify_license("NONE") == "UNKNOWN"

    # Single Permissive
    assert classify_license("MIT") == "ALLOW"
    assert classify_license("Apache-2.0") == "ALLOW"
    assert classify_license("BSD-3-Clause") == "ALLOW"
    assert classify_license("0BSD") == "ALLOW"
    assert classify_license("ISC") == "ALLOW"

    # Copyleft Deny
    assert classify_license("GPL-3.0") == "DENY"
    assert classify_license("AGPL-3.0") == "DENY"
    assert classify_license("SSPL-1.0") == "DENY"
    assert classify_license("LGPL-2.1") == "DENY"

    # Compound OR
    assert classify_license("(MPL-2.0 OR Apache-2.0)") == "ALLOW"
    assert classify_license("GPL-3.0 OR AGPL-3.0") == "DENY"
    assert classify_license("FOO OR BAR") == "UNKNOWN"

    # Compound AND
    assert classify_license("MIT AND Apache-2.0") == "ALLOW"
    assert classify_license("MIT AND GPL-3.0") == "DENY"
    assert classify_license("MIT AND FOOBAR") == "UNKNOWN"

    # WITH exception
    assert classify_license("Apache-2.0 WITH LLVM-exception") == "ALLOW"
    assert _classify_atomic("GPL-2.0 WITH Classpath-exception-2.0") == "DENY"


def test_resolve_file_path() -> None:
    """Verify resolution of existing project files."""
    assert resolve_file_path("LICENSE") is not None
    assert resolve_file_path("NOTICE") is not None
    assert resolve_file_path("non_existent_file_xyz.abc") is None


def test_load_allowlist(tmp_path: Path) -> None:
    """Verify parsing of allowlist TOML and error resilience."""
    # Test real repo file
    entries = load_allowlist()
    assert len(entries) > 0
    assert any(e.package == "pillow" for e in entries)

    # Test custom valid allowlist
    custom_toml = tmp_path / "custom.toml"
    custom_toml.write_text(
        """
[[exception]]
ecosystem = "python"
package = "test-pkg"
version = "1.0.0"
license = "MIT-CMU"
justification = "Testing exception justification with sufficient length."
""",
        encoding="utf-8",
    )
    custom_entries = load_allowlist(custom_toml)
    assert len(custom_entries) == 1
    assert custom_entries[0].package == "test-pkg"
    assert custom_entries[0].ecosystem == "python"

    # Test malformed TOML
    bad_toml = tmp_path / "bad.toml"
    bad_toml.write_text("invalid = [toml content", encoding="utf-8")
    assert load_allowlist(bad_toml) == []

    # Non-existent file
    assert load_allowlist(tmp_path / "ghost.toml") == []


def test_find_allowlist_match() -> None:
    """Verify exact matching of allowlist entries."""
    entries = [
        AllowlistException(
            ecosystem="python",
            package="pillow",
            version="13.0.0",
            license="MIT-CMU",
            justification="Valid justification",
        )
    ]
    assert find_allowlist_match(entries, "python", "pillow", "13.0.0") is not None
    assert find_allowlist_match(entries, "PYTHON", "Pillow", "13.0.0") is not None
    assert find_allowlist_match(entries, "node", "pillow", "13.0.0") is None
    assert find_allowlist_match(entries, "python", "pillow", "12.0.0") is None


def test_extract_python_license() -> None:
    """Verify license extraction from distribution metadata."""
    # 1. License-Expression
    dist_expr = MagicMock()
    dist_expr.metadata = {"License-Expression": "MIT"}
    assert extract_python_license(dist_expr) == "MIT"

    # 2. Short License field
    dist_short = MagicMock()
    dist_short.metadata = {"License": "Apache-2.0"}
    assert extract_python_license(dist_short) == "Apache-2.0"

    # 3. Classifiers
    dist_class = MagicMock()
    dist_class.metadata = {
        "Classifier": [
            "Operating System :: OS Independent",
            "License :: OSI Approved :: MIT License",
        ]
    }
    assert extract_python_license(dist_class) == "MIT"

    # 4. Long text with first line fallback
    dist_multiline = MagicMock()
    dist_multiline.metadata = {
        "License": "Apache License, Version 2.0\n\nFull text follows...",
    }
    assert extract_python_license(dist_multiline) == "Apache-2.0"

    # 5. Missing license
    dist_none = MagicMock()
    dist_none.metadata = {}
    assert extract_python_license(dist_none) == "UNKNOWN"


def test_collect_python_components() -> None:
    """Verify Python package collection from live virtual environment."""
    components = collect_python_components()
    assert len(components) > 10
    assert any(c.name.lower() == "fastapi" for c in components)
    assert all(c.ecosystem == "python" for c in components)
    assert all(c.purl.startswith("pkg:pypi/") for c in components)


def test_format_npm_purl() -> None:
    """Verify npm PURL formatting with and without scope."""
    assert _format_npm_purl("react", "19.3.1") == "pkg:npm/react@19.3.1"
    assert (
        _format_npm_purl("@tanstack/react-query", "5.67.1")
        == "pkg:npm/%40tanstack/react-query@5.67.1"
    )


def test_collect_web_components(tmp_path: Path) -> None:
    """Verify web component collection from manifest and package.json fallback."""
    # 1. From valid manifest file
    manifest_file = tmp_path / "sbom-web.json"
    manifest_file.write_text(
        json.dumps(
            {
                "bomFormat": "CycloneDX",
                "specVersion": "1.5",
                "components": [
                    {
                        "name": "react",
                        "version": "19.3.1",
                        "license": "MIT",
                        "scope": "required",
                        "description": "React library",
                    },
                    {
                        "name": "elkjs",
                        "version": "0.11.1",
                        "license": "EPL-2.0",
                        "scope": "required",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    allowlist = [
        AllowlistException(
            ecosystem="node",
            package="elkjs",
            version="0.11.1",
            license="EPL-2.0",
            justification="Sugiyama layout in Web Worker",
        )
    ]
    manifest_comps = collect_web_components(allowlist, manifest_path=manifest_file)
    assert len(manifest_comps) == 2
    assert manifest_comps[0].name in ("elkjs", "react")
    elk = next(c for c in manifest_comps if c.name == "elkjs")
    assert elk.license_verdict == "ALLOWLISTED"

    # 2. Test fallback to repo kanban/web/package.json
    fallback_comps = collect_web_components()
    assert len(fallback_comps) > 10
    assert any(c.name == "react" for c in fallback_comps)


def test_get_live_components_and_clear_cache() -> None:
    """Verify cached live component aggregation and cache invalidation."""
    clear_sbom_cache()
    comps1 = get_live_components()
    comps2 = get_live_components()
    assert comps1 is comps2
    assert len(comps1) > 50
    clear_sbom_cache()


def test_calculate_sbom_summary() -> None:
    """Verify SBOM summary computation."""
    comps = [
        Component(
            name="pkg1",
            version="1.0",
            ecosystem="python",
            purl="pkg:pypi/pkg1@1.0",
            license="MIT",
            license_verdict="ALLOW",
            scope="required",
        ),
        Component(
            name="pkg2",
            version="2.0",
            ecosystem="node",
            purl="pkg:npm/pkg2@2.0",
            license="LGPL",
            license_verdict="DENY",
            scope="required",
        ),
        Component(
            name="pkg3",
            version="3.0",
            ecosystem="node",
            purl="pkg:npm/pkg3@3.0",
            license="EPL-2.0",
            license_verdict="ALLOWLISTED",
            scope="required",
        ),
        Component(
            name="pkg4",
            version="4.0",
            ecosystem="python",
            purl="pkg:pypi/pkg4@4.0",
            license="UNKNOWN",
            license_verdict="UNKNOWN",
            scope="required",
        ),
    ]
    summary = calculate_sbom_summary(comps)
    assert summary.total_components == 4
    assert summary.python_components == 2
    assert summary.web_components == 2
    assert summary.permissive_count == 1
    assert summary.deny_count == 1
    assert summary.allowlisted_count == 1
    assert summary.unknown_count == 1
    assert summary.to_dict()["total_components"] == 4


def test_get_license_texts() -> None:
    """Verify reading of LICENSE and NOTICE files."""
    license_text, notice_text = get_license_texts()
    assert "Apache License" in license_text
    assert "Version 2.0" in license_text
    assert "Kanban Platform" in notice_text
    assert "Third-Party Notices" in notice_text


def test_generate_cyclonedx_1_5() -> None:
    """Verify CycloneDX 1.5 JSON serialization."""
    comps = [
        Component(
            name="fastapi",
            version="0.115.0",
            ecosystem="python",
            purl="pkg:pypi/fastapi@0.115.0",
            license="MIT",
            license_verdict="ALLOW",
            scope="required",
            description="FastAPI web framework",
        ),
        Component(
            name="unknown-lib",
            version="0.1.0",
            ecosystem="node",
            purl="pkg:npm/unknown-lib@0.1.0",
            license="UNKNOWN",
            license_verdict="UNKNOWN",
            scope="dev",
        ),
    ]
    cdx = generate_cyclonedx_1_5(comps, serial_number="urn:uuid:test-sbom-1234")
    assert cdx["bomFormat"] == "CycloneDX"
    assert cdx["specVersion"] == "1.5"
    assert cdx["serialNumber"] == "urn:uuid:test-sbom-1234"
    assert cdx["version"] == 1
    assert cdx["metadata"]["component"]["name"] == "thumbs-up-kanban"
    assert cdx["metadata"]["component"]["version"] == "2.0.0"

    components = cdx["components"]
    assert len(components) == 2
    f_comp = next(c for c in components if c["name"] == "fastapi")
    assert f_comp["licenses"][0]["license"]["id"] == "MIT"
    assert f_comp["scope"] == "required"
    assert f_comp["description"] == "FastAPI web framework"

    u_comp = next(c for c in components if c["name"] == "unknown-lib")
    assert u_comp["licenses"][0]["license"]["name"] == "Unknown"
    assert u_comp["scope"] == "optional"


def test_load_allowlist_invalid_items(tmp_path: Path) -> None:
    """Verify load_allowlist skips invalid or incomplete items."""
    toml_path = tmp_path / "allowlist_edge.toml"
    valid_entry = (
        '{ ecosystem = "python", package = "valid-pkg", version = "2.0.0", '
        'license = "BSD-3-Clause", justification = "Valid" }'
    )
    content = (
        "exception = [\n"
        '    "not-a-dict",\n'
        '    { ecosystem = "", package = "foo", version = "1.0" },\n'
        '    { ecosystem = "python", package = "", version = "1.0" },\n'
        f"    {valid_entry},\n"
        "]\n"
    )
    toml_path.write_text(content, encoding="utf-8")
    entries = load_allowlist(toml_path)
    assert len(entries) == 1
    assert entries[0].package == "valid-pkg"


def test_extract_python_license_edge_cases() -> None:
    """Verify edge cases in classifier and multiline license extraction."""
    # Classifier that doesn't normalize to ALLOW
    dist_custom_class = MagicMock()
    dist_custom_class.metadata = {
        "Classifier": ["License :: Other / Proprietary"],
        "License": "A" * 150,  # > MAX_INLINE_LICENSE_LEN
    }
    assert extract_python_license(dist_custom_class) == "UNKNOWN"

    # Multiline where first line is too long
    dist_long_first_line = MagicMock()
    dist_long_first_line.metadata = {
        "License": ("A" * 120) + "\nLine 2",
    }
    assert extract_python_license(dist_long_first_line) == "UNKNOWN"


def test_collect_python_components_exception_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify error resilience when distributions() fails."""
    monkeypatch.setattr(
        "importlib.metadata.distributions",
        MagicMock(side_effect=RuntimeError("Metadata failure")),
    )
    assert collect_python_components() == []


def test_collect_web_components_edge_cases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify web manifest parsing error handling and environment variable path."""
    # Manifest with corrupted JSON
    corrupt_manifest = tmp_path / "corrupt.json"
    corrupt_manifest.write_text("invalid json", encoding="utf-8")
    assert _parse_web_manifest(corrupt_manifest, []) is None

    # Manifest with non-dict items and missing name/version
    malformed_manifest = tmp_path / "malformed.json"
    malformed_manifest.write_text(
        json.dumps(
            {
                "components": [
                    "string-not-dict",
                    {"name": "", "version": "1.0"},
                    {"name": "valid-web", "version": "1.0.0", "license": "MIT"},
                ]
            }
        ),
        encoding="utf-8",
    )
    parsed = _parse_web_manifest(malformed_manifest, [])
    assert parsed is not None
    assert len(parsed) == 1
    assert parsed[0].name == "valid-web"

    # Package.json unparseable
    bad_pkg = tmp_path / "package.json"
    bad_pkg.write_text("not json", encoding="utf-8")
    assert _parse_web_package_json(bad_pkg, []) == []

    # Non-existent package.json
    assert collect_web_components(manifest_path=tmp_path / "none.json") != []

    # Manifest with unknown license matching allowlist
    allow_manifest = tmp_path / "allow_manifest.json"
    allow_manifest.write_text(
        json.dumps(
            {"components": [{"name": "custom-web", "version": "1.0.0", "license": "UNKNOWN"}]}
        ),
        encoding="utf-8",
    )
    custom_allow = [
        AllowlistException(
            ecosystem="node",
            package="custom-web",
            version="1.0.0",
            license="MIT",
            justification="Allowlisted test",
        )
    ]
    custom_comps = _parse_web_manifest(allow_manifest, custom_allow)
    assert custom_comps is not None
    assert custom_comps[0].license == "MIT"
    assert custom_comps[0].license_verdict == "ALLOWLISTED"

    # Test KB_WEB_DIST env var
    env_dir = tmp_path / "env_dist"
    env_dir.mkdir()
    env_sbom = env_dir / "sbom-web.json"
    env_sbom.write_text(
        json.dumps({"components": [{"name": "env-pkg", "version": "1.2.3", "license": "MIT"}]}),
        encoding="utf-8",
    )
    monkeypatch.setenv("KB_WEB_DIST", str(env_dir))
    comps = collect_web_components()
    assert any(c.name == "env-pkg" for c in comps)


def test_get_license_texts_io_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify license reading resilience on I/O error."""
    mock_path = MagicMock()
    mock_path.is_file.return_value = True
    mock_path.read_text.side_effect = OSError("Disk failure")

    monkeypatch.setattr(
        "kanban.ops.sbom.resolve_file_path",
        lambda f: mock_path if f in ("LICENSE", "NOTICE") else None,
    )
    lic, notice = get_license_texts()
    assert lic == ""
    assert notice == ""


def test_get_license_texts_missing_files(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify license reading when files do not exist."""
    monkeypatch.setattr("kanban.ops.sbom.resolve_file_path", lambda _f: None)
    lic, notice = get_license_texts()
    assert lic == ""
    assert notice == ""


def test_parse_web_package_json_with_node_modules_and_allowlist(tmp_path: Path) -> None:
    """Verify package.json fallback parsing with workspace filtering and allowlist."""
    pkg_file = tmp_path / "package.json"
    pkg_file.write_text(
        json.dumps(
            {
                "dependencies": {
                    "kanban-core": "1.0.0",
                    "custom-dep": "2.0.0",
                    "allowlisted-dep": "3.0.0",
                },
                "devDependencies": {
                    "@kanban/web": "1.0.0",
                    "dev-tool": "4.0.0",
                },
            }
        ),
        encoding="utf-8",
    )

    node_modules = tmp_path / "node_modules"
    custom_dep_dir = node_modules / "custom-dep"
    custom_dep_dir.mkdir(parents=True)
    (custom_dep_dir / "package.json").write_text(
        json.dumps(
            {
                "license": "MIT",
                "description": "A custom dependency",
            }
        ),
        encoding="utf-8",
    )

    allow_entries = [
        AllowlistException(
            ecosystem="node",
            package="allowlisted-dep",
            version="3.0.0",
            license="EPL-2.0",
            justification="Test allowlist justification",
        )
    ]

    comps = _parse_web_package_json(pkg_file, allow_entries)
    # kanban-core and @kanban/web should be filtered out
    assert not any("kanban" in c.name for c in comps)

    custom = next(c for c in comps if c.name == "custom-dep")
    assert custom.license == "MIT"
    assert custom.license_verdict == "ALLOW"
    assert custom.description == "A custom dependency"

    allowlisted = next(c for c in comps if c.name == "allowlisted-dep")
    assert allowlisted.license_verdict == "ALLOWLISTED"
    assert allowlisted.license == "EPL-2.0"


def test_live_workspace_sbom_verdicts_zero_deny_and_unknown() -> None:
    """Verify live workspace SBOM generation yields 0 DENY and 0 UNKNOWN license verdicts."""
    clear_sbom_cache()
    components = get_live_components()
    summary = calculate_sbom_summary(components)
    assert summary.total_components > 0
    deny_comps = [c for c in components if c.license_verdict == "DENY"]
    assert summary.deny_count == 0, f"Found DENY components: {deny_comps}"
    web_node_modules = Path("kanban/web/node_modules")
    web_dist_manifest = Path("kanban/web/dist/sbom-web.json")
    if not (web_node_modules.is_dir() or web_dist_manifest.is_file()):
        unknown_python = [
            c for c in components if c.ecosystem == "python" and c.license_verdict == "UNKNOWN"
        ]
        assert len(unknown_python) == 0, f"Found UNKNOWN Python components: {unknown_python}"
    else:
        unknown_comps = [c for c in components if c.license_verdict == "UNKNOWN"]
        assert summary.unknown_count == 0, f"Found UNKNOWN components: {unknown_comps}"
