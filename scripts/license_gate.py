"""Apache-2.0 license gate for uv.lock and pnpm-lock.yaml.

Inspects Python and Node dependencies to enforce a permissive-only supply chain
policy and reject copyleft licenses unless explicitly allowed by an approved allowlist.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Sequence


class Verdict(StrEnum):
    """Classifier verdict for an evaluated license expression."""

    ALLOW = "ALLOW"
    DENY = "DENY"
    UNKNOWN = "UNKNOWN"


class CollectorError(Exception):
    """Raised when dependency license data collection or parsing fails."""


class AllowlistError(Exception):
    """Raised when the license allowlist file is malformed or invalid."""


class AllowlistEntry(NamedTuple):
    """Represents a validated exception in license-allowlist.toml."""

    ecosystem: str
    package: str
    version: str
    license: str
    linkage: str | None
    justification: str
    is_non_waivable: bool = False


class Violation(NamedTuple):
    """Represents a discovered license violation."""

    ecosystem: str
    package: str
    version: str
    license: str
    reason: str


# Canonical permissive licenses approved under Section 2.5 and 15.4
ALLOW_SET: frozenset[str] = frozenset(
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

# Denylist prefixes representing copyleft or non-permissive terms
DENY_PREFIXES: tuple[str, ...] = (
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

# Common long names mapped to canonical SPDX identifiers
NORMALIZATION_MAP: dict[str, str] = {
    "mozilla public license 2.0 (mpl 2.0)": "MPL-2.0",
    "mozilla public license 2.0": "MPL-2.0",
    "mozilla public license": "MPL-2.0",
    "python software foundation license": "PSF-2.0",
    "python software foundation": "PSF-2.0",
    "psf license": "PSF-2.0",
    "psf": "PSF-2.0",
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
    "bsd 3-clause": "BSD-3-Clause",
    "bsd-3-clause": "BSD-3-Clause",
    "2-clause bsd license": "BSD-2-Clause",
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

PARENTHESIZED_PHRASES: dict[str, str] = {
    "mozilla public license 2.0 (mpl 2.0)": "MPL-2.0",
    "isc license (iscl)": "ISC",
    "apache license (v2.0)": "Apache-2.0",
}


def is_non_waivable(license_str: str) -> bool:
    """Check if a license string is a strictly non-waivable copyleft license.

    GPL, AGPL, and SSPL licenses can never be waived by allowlist entries.
    LGPL is excluded here as it can be waived under dynamic linkage.
    """
    cleaned = license_str.strip("() \t\n\r").upper()
    if cleaned.startswith(("LGPL", "GNU LESSER")):
        return False
    return cleaned.startswith(
        (
            "GPL",
            "AGPL",
            "SSPL",
            "GNU GENERAL PUBLIC",
            "GNU AFFERO",
            "SERVER SIDE PUBLIC",
        )
    )


def evaluate_atom(atom: str) -> Verdict:
    """Evaluate a single atomic license identifier."""
    cleaned = " ".join(atom.strip().split())
    if not cleaned or cleaned.upper() in {"UNKNOWN", "UNLICENSED", "CUSTOM", "NONE"}:
        return Verdict.UNKNOWN

    lowered = cleaned.lower()
    if lowered in NORMALIZATION_MAP:
        cleaned = NORMALIZATION_MAP[lowered]

    if " with " in cleaned.lower():
        parts = re.split(r"\s+with\s+", cleaned, maxsplit=1, flags=re.IGNORECASE)
        base_verdict = evaluate_atom(parts[0])
        if base_verdict == Verdict.ALLOW:
            return Verdict.ALLOW

    upper_cleaned = cleaned.upper()
    for prefix in DENY_PREFIXES:
        if upper_cleaned.startswith(prefix):
            return Verdict.DENY

    for allowed in ALLOW_SET:
        if cleaned.lower() == allowed.lower():
            return Verdict.ALLOW

    return Verdict.UNKNOWN


def tokenize_expression(expr: str) -> list[str]:
    """Tokenize a license expression into atoms and operators."""
    processed = " ".join(expr.strip().split())
    for phrase, replacement in PARENTHESIZED_PHRASES.items():
        processed = re.sub(re.escape(phrase), replacement, processed, flags=re.IGNORECASE)

    processed = re.sub(r"\s+/\s+", " OR ", processed)
    processed = re.sub(r"\s*;\s*", " OR ", processed)
    spaced = processed.replace("(", " ( ").replace(")", " ) ")
    raw_tokens = spaced.split()

    grouped_tokens: list[str] = []
    current_words: list[str] = []

    for tok in raw_tokens:
        tok_upper = tok.upper()
        if tok in ("(", ")") or tok_upper in ("AND", "OR"):
            if current_words:
                grouped_tokens.append(" ".join(current_words))
                current_words = []
            grouped_tokens.append(tok_upper if tok_upper in ("AND", "OR") else tok)
        else:
            current_words.append(tok)

    if current_words:
        grouped_tokens.append(" ".join(current_words))

    return grouped_tokens


class _Parser:
    """Recursive-descent parser for SPDX license expressions."""

    def __init__(self, tokens: list[str]) -> None:
        self.tokens = tokens
        self.pos = 0

    @property
    def current(self) -> str | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def consume(self, expected: str | None = None) -> str | None:
        tok = self.current
        if expected is not None and tok != expected:
            return None
        if tok is not None:
            self.pos += 1
        return tok

    def parse(self) -> Verdict:
        if not self.tokens:
            return Verdict.UNKNOWN
        return self.parse_or()

    def parse_or(self) -> Verdict:
        left = self.parse_and()
        while self.current == "OR":
            self.consume("OR")
            right = self.parse_and()
            if Verdict.ALLOW in (left, right):
                left = Verdict.ALLOW
            elif Verdict.DENY in (left, right):
                left = Verdict.DENY
            else:
                left = Verdict.UNKNOWN
        return left

    def parse_and(self) -> Verdict:
        left = self.parse_primary()
        while self.current == "AND":
            self.consume("AND")
            right = self.parse_primary()
            if Verdict.DENY in (left, right):
                left = Verdict.DENY
            elif left == Verdict.ALLOW and right == Verdict.ALLOW:
                left = Verdict.ALLOW
            else:
                left = Verdict.UNKNOWN
        return left

    def parse_primary(self) -> Verdict:
        tok = self.current
        if tok == "(":
            self.consume("(")
            res = self.parse_or()
            if self.current == ")":
                self.consume(")")
            return res
        if tok is None or tok == ")":
            return Verdict.UNKNOWN
        self.consume()
        return evaluate_atom(tok)


def classify(license_expr: str) -> Verdict:
    """Classify a license expression into ALLOW, DENY, or UNKNOWN.

    Normalizes whitespace and common aliases, respects SPDX OR/AND and parentheses,
    and returns Verdict.ALLOW, Verdict.DENY, or Verdict.UNKNOWN.
    """
    if not license_expr or not license_expr.strip():
        return Verdict.UNKNOWN

    tokens = tokenize_expression(license_expr)
    if not tokens:
        return Verdict.UNKNOWN

    parser = _Parser(tokens)
    return parser.parse()


def check_root_license(repo_root: Path) -> bool:
    """Verify that root LICENSE file exists and declares Apache License Version 2.0."""
    license_file = repo_root / "LICENSE"
    if not license_file.is_file():
        return False
    try:
        content = license_file.read_text(encoding="utf-8")
    except OSError:
        return False
    return "Apache License" in content and "Version 2.0" in content


MIN_JUSTIFICATION_LENGTH: int = 20


def validate_allowlist_entry(item: object, idx: int) -> AllowlistEntry:
    """Validate a single allowlist table entry according to Section 15.4 rules."""
    if not isinstance(item, dict):
        msg = f"Entry #{idx} in allowlist is not a table"
        raise AllowlistError(msg)

    required_keys = ("ecosystem", "package", "version", "license", "justification")
    for key in required_keys:
        if key not in item or item[key] is None or not str(item[key]).strip():
            msg = f"Entry #{idx} in allowlist is missing required field '{key}'"
            raise AllowlistError(msg)

    ecosystem = str(item["ecosystem"]).strip().lower()
    if ecosystem not in ("python", "node"):
        msg = f"Entry #{idx}: ecosystem must be 'python' or 'node', got '{ecosystem}'"
        raise AllowlistError(msg)

    package = str(item["package"]).strip()
    version = str(item["version"]).strip()
    license_str = str(item["license"]).strip()
    justification = str(item["justification"]).strip()

    if any(char in version for char in ("*", "^", "~", ">", "<")):
        msg = f"Entry #{idx} for '{package}': version cannot have wildcards: '{version}'"
        raise AllowlistError(msg)

    if len(justification) < MIN_JUSTIFICATION_LENGTH:
        msg = (
            f"Entry #{idx} for '{package}': justification must be >= "
            f"{MIN_JUSTIFICATION_LENGTH} chars ({len(justification)})"
        )
        raise AllowlistError(msg)

    linkage: str | None = None
    upper_lic = license_str.upper()
    if upper_lic.startswith(("LGPL", "GNU LESSER")):
        if "linkage" not in item:
            msg = f"Entry #{idx} for '{package}': 'linkage' field is required for LGPL licenses"
            raise AllowlistError(msg)
        linkage_val = str(item["linkage"]).strip()
        if linkage_val != "dynamic":
            msg = f"Entry #{idx} for '{package}': linkage must be 'dynamic' (got '{linkage_val}')"
            raise AllowlistError(msg)
        linkage = linkage_val

    entry_non_waivable = is_non_waivable(license_str)
    return AllowlistEntry(
        ecosystem=ecosystem,
        package=package,
        version=version,
        license=license_str,
        linkage=linkage,
        justification=justification,
        is_non_waivable=entry_non_waivable,
    )


def load_allowlist(path: Path) -> tuple[list[AllowlistEntry], bool]:
    """Load and validate the license allowlist TOML file.

    Returns:
        tuple[list[AllowlistEntry], bool]: Parsed valid entries and whether any non-waivable
        entry was present.

    Raises:
        AllowlistError: If the file is missing, malformed, or violates schema rules.

    """
    if not path.is_file():
        msg = f"Allowlist file not found: {path}"
        raise AllowlistError(msg)

    try:
        content = path.read_text(encoding="utf-8")
        data = tomllib.loads(content)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        msg = f"Failed to parse allowlist TOML at {path}: {exc}"
        raise AllowlistError(msg) from exc

    raw_exceptions = data.get("exception", [])
    if not isinstance(raw_exceptions, list):
        msg = "Key 'exception' must be an array of tables in allowlist TOML"
        raise AllowlistError(msg)

    entries = [validate_allowlist_entry(item, idx) for idx, item in enumerate(raw_exceptions, 1)]
    has_non_waivable = any(e.is_non_waivable for e in entries)
    return entries, has_non_waivable


def collect_python_packages(json_path: Path | None) -> list[dict[str, Any]]:
    """Collect Python dependencies either from JSON file or via pip-licenses."""
    if json_path is not None:
        if not json_path.is_file():
            msg = f"Python JSON file not found: {json_path}"
            raise CollectorError(msg)
        try:
            content = json_path.read_text(encoding="utf-8")
            data = json.loads(content)
        except (OSError, json.JSONDecodeError) as exc:
            msg = f"Invalid Python JSON from {json_path}: {exc}"
            raise CollectorError(msg) from exc
    else:
        cmd = ["uv", "run", "pip-licenses", "--format=json", "--with-system", "--from=mixed"]
        try:
            proc = subprocess.run(  # noqa: S603
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=120,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            msg = f"Failed to execute pip-licenses: {exc}"
            raise CollectorError(msg) from exc

        if proc.returncode != 0:
            msg = f"pip-licenses exited with return code {proc.returncode}: {proc.stderr}"
            raise CollectorError(msg)

        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            msg = f"pip-licenses produced invalid JSON: {exc}"
            raise CollectorError(msg) from exc

    if not isinstance(data, list):
        msg = "Python license data must be a JSON array"
        raise CollectorError(msg)

    return data


def collect_node_packages(json_path: Path | None) -> dict[str, Any]:
    """Collect Node dependencies either from JSON file or via license-checker."""
    if json_path is not None:
        if not json_path.is_file():
            msg = f"Node JSON file not found: {json_path}"
            raise CollectorError(msg)
        try:
            content = json_path.read_text(encoding="utf-8")
            data = json.loads(content)
        except (OSError, json.JSONDecodeError) as exc:
            msg = f"Invalid Node JSON from {json_path}: {exc}"
            raise CollectorError(msg) from exc
    else:
        cmd = ["pnpm", "exec", "license-checker", "--json", "--start", "."]
        try:
            proc = subprocess.run(  # noqa: S603
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=120,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            msg = f"Failed to execute license-checker: {exc}"
            raise CollectorError(msg) from exc

        if proc.returncode != 0:
            msg = f"license-checker exited with return code {proc.returncode}: {proc.stderr}"
            raise CollectorError(msg)

        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            msg = f"license-checker produced invalid JSON: {exc}"
            raise CollectorError(msg) from exc

    if not isinstance(data, dict):
        msg = "Node license data must be a JSON dictionary"
        raise CollectorError(msg)

    return data


def is_workspace_package(name: str) -> bool:
    """Return True if package is a workspace member or the root project."""
    lowered = name.lower()
    return lowered in {"kanban", "kanban-platform", "kanban-monorepo"} or lowered.startswith(
        ("kanban-", "@kanban/")
    )


def find_matching_entry(
    entries: list[AllowlistEntry],
    ecosystem: str,
    package: str,
    version: str,
) -> AllowlistEntry | None:
    """Find a matching exception entry in the allowlist."""
    pkg_lowered = package.lower()
    for entry in entries:
        if (
            entry.ecosystem.lower() == ecosystem.lower()
            and entry.package.lower() == pkg_lowered
            and entry.version == version
        ):
            return entry
    return None


def evaluate_python_dependencies(
    raw_python: list[dict[str, Any]],
    entries: list[AllowlistEntry],
) -> tuple[list[Violation], int]:
    """Evaluate Python packages and return violations and package count."""
    violations: list[Violation] = []
    count = 0

    for item in raw_python:
        name = str(item.get("Name") or item.get("name") or "").strip()
        version = str(item.get("Version") or item.get("version") or "").strip()
        lic = str(item.get("License") or item.get("license") or "").strip()

        if not name or is_workspace_package(name):
            continue

        count += 1
        verdict = classify(lic)
        if verdict == Verdict.ALLOW:
            continue

        match = find_matching_entry(entries, "python", name, version)
        if match is not None:
            if match.is_non_waivable or is_non_waivable(lic):
                sys.stderr.write(
                    f"NON_WAIVABLE_LICENSE: package '{name}' cannot waive license '{lic}'\n"
                )
                violations.append(Violation("python", name, version, lic, "NON_WAIVABLE_LICENSE"))
        else:
            violations.append(Violation("python", name, version, lic, verdict.value))

    return violations, count


def evaluate_node_dependencies(
    raw_node: dict[str, Any],
    entries: list[AllowlistEntry],
) -> tuple[list[Violation], int]:
    """Evaluate Node packages and return violations and package count."""
    violations: list[Violation] = []
    count = 0

    for key, info in raw_node.items():
        if not isinstance(info, dict):
            continue

        if "@" in key:
            pkg_name, version = key.rsplit("@", 1)
        else:
            pkg_name = key
            version = str(info.get("version", "")).strip()

        if is_workspace_package(pkg_name):
            continue

        count += 1
        raw_licenses = info.get("licenses")
        if isinstance(raw_licenses, list):
            lic = " OR ".join(f"({str(x).strip()})" for x in raw_licenses if str(x).strip())
        elif raw_licenses is not None:
            lic = str(raw_licenses).strip()
        else:
            lic = ""

        verdict = classify(lic)
        if verdict == Verdict.ALLOW:
            continue

        match = find_matching_entry(entries, "node", pkg_name, version)
        if match is not None:
            if match.is_non_waivable or is_non_waivable(lic):
                sys.stderr.write(
                    f"NON_WAIVABLE_LICENSE: package '{pkg_name}' cannot waive license '{lic}'\n"
                )
                violations.append(Violation("node", pkg_name, version, lic, "NON_WAIVABLE_LICENSE"))
        else:
            violations.append(Violation("node", pkg_name, version, lic, verdict.value))

    return violations, count


def run_license_gate(
    python_json: Path | None = None,
    node_json: Path | None = None,
    allowlist_path: Path | None = None,
    repo_root: Path | None = None,
) -> int:
    """Run the license gate audit and return the exit code."""
    root = repo_root or Path.cwd()

    if not check_root_license(root):
        msg = "LICENSE_MISSING_OR_NOT_APACHE2: root LICENSE is missing or not Apache 2.0\n"
        sys.stderr.write(msg)
        return 1

    effective_allowlist = allowlist_path or (root / "license-allowlist.toml")
    entries, has_non_waivable_entry = load_allowlist(effective_allowlist)

    raw_python = collect_python_packages(python_json)
    raw_node = collect_node_packages(node_json)

    py_violations, python_count = evaluate_python_dependencies(raw_python, entries)
    node_violations, node_count = evaluate_node_dependencies(raw_node, entries)

    violations = py_violations + node_violations

    if has_non_waivable_entry:
        for entry in entries:
            if entry.is_non_waivable:
                sys.stderr.write(
                    f"NON_WAIVABLE_LICENSE: allowlist entry for '{entry.package}' "
                    f"specifies non-waivable license '{entry.license}'\n"
                )

    violations.sort(key=lambda v: (v.ecosystem, v.package, v.version))

    for v in violations:
        sys.stdout.write(f"{v.ecosystem}\t{v.package}\t{v.version}\t{v.license}\t{v.reason}\n")

    sys.stdout.write(
        f"SUMMARY python={python_count} node={node_count} violations={len(violations)}\n"
    )

    if violations or has_non_waivable_entry:
        return 1

    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for scripts.license_gate."""
    parser = argparse.ArgumentParser(description="Apache-2.0 License Gate")
    parser.add_argument(
        "--python-json",
        type=Path,
        default=None,
        help="Path to Python packages JSON",
    )
    parser.add_argument(
        "--node-json",
        type=Path,
        default=None,
        help="Path to Node packages JSON",
    )
    parser.add_argument(
        "--allowlist",
        type=Path,
        default=None,
        help="Path to license allowlist TOML (defaults to license-allowlist.toml)",
    )

    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))

    try:
        return run_license_gate(
            python_json=args.python_json,
            node_json=args.node_json,
            allowlist_path=args.allowlist,
        )
    except (CollectorError, AllowlistError) as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 3
    except OSError as exc:
        sys.stderr.write(f"OS ERROR: {exc}\n")
        return 3


if __name__ == "__main__":
    sys.exit(main())
