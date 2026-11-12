"""Script to verify that repository files do not contain forbidden em-dash or en-dash characters."""

import os
import sys
from collections.abc import Sequence
from pathlib import Path

FORBIDDEN_DASHES: dict[str, str] = {
    "\u2014": "U+2014",
    "\u2013": "U+2013",
}

MAX_FILE_SIZE: int = 5 * 1024 * 1024  # 5 MiB (5,242,880 bytes)

SCAN_EXTENSIONS: set[str] = {".md", ".yaml", ".yml", ".toml", ".txt"}
SCAN_DIRECTORIES: list[str] = ["docs", ".agents"]


def check_file(path_str: str) -> tuple[int, bool]:
    """Check a single file for forbidden unicode dashes.

    Returns:
        tuple[int, bool]: (violation_count, utf8_error)

    """
    path = Path(path_str)
    if not path.is_file():
        return (0, False)

    size = path.stat().st_size
    if size > MAX_FILE_SIZE:
        sys.stderr.write(f"Notice: skipping {path_str} exceeding 5 MiB limit ({size} bytes)\n")
        return (0, False)

    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        sys.stdout.write(f"{path_str}: not valid UTF-8\n")
        return (1, True)

    violations = 0
    for line_idx, line in enumerate(content.splitlines(keepends=True), start=1):
        for col_idx, char in enumerate(line, start=1):
            if char in FORBIDDEN_DASHES:
                dash_code = FORBIDDEN_DASHES[char]
                sys.stdout.write(f"{path_str}:{line_idx}:{col_idx}: forbidden dash {dash_code}\n")
                violations += 1

    return (violations, False)


def collect_all_files(root: Path) -> list[str]:
    """Collect all md, yaml, yml, toml, txt files under docs/ and .agents/ relative to root."""
    collected: list[str] = []
    for dir_name in SCAN_DIRECTORIES:
        scan_dir = root / dir_name
        if not scan_dir.is_dir():
            continue
        for current_root, _dirs, files in os.walk(scan_dir):
            for file_name in files:
                file_path = Path(current_root) / file_name
                if file_path.suffix in SCAN_EXTENSIONS:
                    collected.append(str(file_path))
    return sorted(collected)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for check_no_dashes script."""
    args = list(sys.argv[1:] if argv is None else argv)

    scan_all = False
    files_to_check: list[str] = []

    for arg in args:
        if arg == "--all":
            scan_all = True
        elif not arg.startswith("-"):
            files_to_check.append(arg)

    if scan_all:
        files_to_check = collect_all_files(Path.cwd())
    elif not files_to_check:
        return 0

    total_violations = 0
    for file_path in files_to_check:
        violations, _ = check_file(file_path)
        total_violations += violations

    return 1 if total_violations > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
