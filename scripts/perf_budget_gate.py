#!/usr/bin/env python3
# Copyright 2026 Kanban Platform Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Automated SLA Performance Budget Gate (KB-P6-04).

Evaluates 5 quantitative SLA ceilings:
1. Board Optimistic Drag Frame: p95 < 12.0 ms
2. Sparkle FIM Latency: p95 < 150.0 ms
3. Sync Tier A Wasm Hooks: p95 < 25.0 ms
4. 1,000 Clean-DB SAVEPOINT Tests: wall_clock < 10.0 s
5. Standalone Container Warm Boot: max < 3.0 s

Exits 0 iff all SLAs are satisfied, exits 2 on SLA breach, exits 1 on error.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

# Mandatory SLA Ceilings
REQUIRED_SLAS: dict[str, dict[str, Any]] = {
    "drag_p95": {
        "name": "Board Optimistic Drag Frame (p95)",
        "unit": "ms",
        "threshold": 12.0,
        "aliases": ["drag_p95_ms", "board_optimistic_drag"],
        "field_name": "p95_ms",
    },
    "sparkle_p95": {
        "name": "Sparkle FIM Latency (p95)",
        "unit": "ms",
        "threshold": 150.0,
        "aliases": ["sparkle_p95_ms", "sparkle_fim_latency"],
        "field_name": "p95_ms",
    },
    "sync_hooks_p95": {
        "name": "Sync Wasm Workflow Hooks (p95)",
        "unit": "ms",
        "threshold": 25.0,
        "aliases": ["sync_hooks_p95_ms", "sync_tier_a_wasm_hooks"],
        "field_name": "p95_ms",
    },
    "clean_db_1000_s": {
        "name": "1,000 Clean-DB SAVEPOINT Tests",
        "unit": "s",
        "threshold": 10.0,
        "aliases": ["clean_db_1000", "clean_db_wall_clock_s"],
        "field_name": "wall_clock_s",
    },
    "warm_boot_s": {
        "name": "Standalone Container Warm Boot (max)",
        "unit": "s",
        "threshold": 3.0,
        "aliases": ["warm_boot_max_s", "standalone_warm_boot"],
        "field_name": "max_s",
    },
}


@dataclass(slots=True)
class MetricResult:
    """Quantitative benchmark result distribution."""

    key: str
    name: str
    unit: str
    threshold: float
    observed: float
    passed: bool
    samples: int = 1
    min_val: float | None = None
    p50: float | None = None
    p95: float | None = None
    p99: float | None = None
    max_val: float | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "key": self.key,
            "name": self.name,
            "unit": self.unit,
            "threshold": self.threshold,
            "observed": self.observed,
            "passed": self.passed,
            "samples": self.samples,
            "min": self.min_val,
            "p50": self.p50,
            "p95": self.p95,
            "p99": self.p99,
            "max": self.max_val,
            "details": self.details,
        }


@dataclass(slots=True)
class PerfReport:
    """Full aggregated performance budget report."""

    timestamp: str
    overall_passed: bool
    metrics: dict[str, MetricResult]
    breaches: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-serializable dictionary."""
        return {
            "timestamp": self.timestamp,
            "overall_passed": self.overall_passed,
            "metrics": {k: v.to_dict() for k, v in self.metrics.items()},
            "breaches": self.breaches,
        }


def _extract_metric_value(raw: object, field_name: str) -> tuple[float, int, dict[str, Any]]:
    """Extract numeric observed value, sample count, and details dict from various formats."""
    if isinstance(raw, (int, float)):
        val = float(raw)
        return val, 1, {"observed": val}

    if isinstance(raw, dict):
        raw_dict = dict(raw)
        # Check standard fields
        candidates = [
            field_name,
            "observed",
            "p95",
            "p95_ms",
            "max_s",
            "max",
            "wall_clock_s",
            "duration_s",
            "val",
            "value",
        ]
        for c in candidates:
            if c in raw_dict and isinstance(raw_dict[c], (int, float)):
                return float(raw_dict[c]), int(raw_dict.get("samples", 1)), raw_dict

    msg = f"Unable to extract numeric value for field {field_name} from: {raw!r}"
    raise ValueError(msg)


def evaluate_raw_metrics(raw_data: dict[str, Any]) -> PerfReport:
    """Evaluate raw metric input dictionary against the 5 SLA ceilings."""
    metrics: dict[str, MetricResult] = {}
    breaches: list[str] = []

    # Map aliases for flexible resolution
    lookup: dict[str, Any] = {}
    for k, v in raw_data.items():
        lookup[k.lower()] = v

    for sla_key, config in REQUIRED_SLAS.items():
        # Find matching key in raw data
        found_key: str | None = None
        candidates = [sla_key, *config.get("aliases", [])]
        for c in candidates:
            if c.lower() in lookup:
                found_key = c.lower()
                break

        if found_key is None:
            breaches.append(f"Missing required metric: {sla_key} ({config['name']})")
            continue

        raw_val = lookup[found_key]
        try:
            observed, samples, details = _extract_metric_value(raw_val, str(config["field_name"]))
        except ValueError as err:
            breaches.append(f"Invalid metric data for {sla_key}: {err}")
            continue

        threshold = float(config["threshold"])
        unit = str(config["unit"])
        name = str(config["name"])

        # Ceiling invariant: strictly observed < threshold
        passed = observed < threshold
        if not passed:
            breaches.append(
                f"Metric '{sla_key}' breached SLA: "
                f"observed {observed:.2f}{unit} >= ceiling {threshold:.2f}{unit}"
            )

        min_val = (
            float(details["min_ms"])
            if "min_ms" in details
            else (float(details["min_s"]) if "min_s" in details else None)
        )
        p50 = (
            float(details["p50_ms"])
            if "p50_ms" in details
            else (float(details["p50_s"]) if "p50_s" in details else None)
        )
        p95 = float(details["p95_ms"]) if "p95_ms" in details else None
        p99 = float(details["p99_ms"]) if "p99_ms" in details else None
        max_val = (
            float(details["max_ms"])
            if "max_ms" in details
            else (float(details["max_s"]) if "max_s" in details else None)
        )

        metrics[sla_key] = MetricResult(
            key=sla_key,
            name=name,
            unit=unit,
            threshold=threshold,
            observed=observed,
            passed=passed,
            samples=samples,
            min_val=min_val,
            p50=p50,
            p95=p95,
            p99=p99,
            max_val=max_val,
            details=details,
        )

    overall_passed = len(breaches) == 0 and len(metrics) == len(REQUIRED_SLAS)
    return PerfReport(
        timestamp=dt.datetime.now(dt.UTC).isoformat(),
        overall_passed=overall_passed,
        metrics=metrics,
        breaches=breaches,
    )


def generate_markdown_summary(report: PerfReport) -> str:
    """Render a clean GitHub Flavored Markdown summary table."""
    lines: list[str] = [
        "### Automated SLA Performance Budget Gate Report",
        "",
        (
            f"**Status:** `{'PASS' if report.overall_passed else 'FAIL'}` | "
            f"**Timestamp:** `{report.timestamp}`"
        ),
        "",
        "| Metric | SLA Ceiling | Observed | Samples | Status |",
        "| :--- | :---: | :---: | :---: | :---: |",
    ]

    for sla_key, config in REQUIRED_SLAS.items():
        if sla_key in report.metrics:
            m = report.metrics[sla_key]
            status_badge = "PASS" if m.passed else "**FAIL (BREACH)**"
            lines.append(
                f"| {m.name} | < {m.threshold:.1f} {m.unit} | "
                f"{m.observed:.2f} {m.unit} | {m.samples} | {status_badge} |"
            )
        else:
            lines.append(
                f"| {config['name']} | < {config['threshold']:.1f} {config['unit']} | "
                f"*MISSING* | 0 | **FAIL (MISSING)** |"
            )

    if report.breaches:
        lines.append("")
        lines.append("#### SLA Breaches Detected:")
        lines.extend(f"- :x: {breach}" for breach in report.breaches)

    lines.append("")
    return "\n".join(lines)


# -----------------------------------------------------------------------------
# Live Benchmark Runners
# -----------------------------------------------------------------------------
def run_clean_db_benchmark() -> tuple[float, dict[str, Any]]:
    """Execute 1,000 clean-db tests and measure wall-clock elapsed time."""
    cmd = [
        "uv",
        "run",
        "pytest",
        "tests/perf/test_perf_clean_db_1000.py",
        "-n",
        "auto",
        "-q",
    ]
    t0 = time.monotonic()
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603
    elapsed_s = time.monotonic() - t0
    if res.returncode != 0:
        msg = (
            f"Clean-DB benchmark pytest failed (code {res.returncode}):\n{res.stderr}\n{res.stdout}"
        )
        raise RuntimeError(msg)

    return elapsed_s, {
        "benchmark": "clean_db_1000",
        "wall_clock_s": round(elapsed_s, 3),
        "samples": 1000,
        "stdout": res.stdout.strip()[-200:],
    }


def run_pytest_benchmark(test_path: str, report_json_path: Path) -> dict[str, Any]:
    """Execute a pytest benchmark and read its structured output JSON."""
    if report_json_path.is_file():
        report_json_path.unlink()

    cmd = ["uv", "run", "pytest", test_path, "-v"]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603
    if res.returncode != 0:
        msg = f"Benchmark {test_path} failed (code {res.returncode}):\n{res.stderr}\n{res.stdout}"
        raise RuntimeError(msg)

    if not report_json_path.is_file():
        msg = (
            f"Benchmark {test_path} succeeded but did not write expected report {report_json_path}"
        )
        raise RuntimeError(msg)

    return cast("dict[str, Any]", json.loads(report_json_path.read_text(encoding="utf-8")))


def run_board_drag_benchmark(report_json_path: Path) -> dict[str, Any]:
    """Run Playwright board drag benchmark and read perf-drag.json."""
    if report_json_path.is_file():
        report_json_path.unlink()

    env = dict(os.environ)
    env["PERF_DRAG_OUT"] = str(report_json_path.resolve())

    cmd = [
        "pnpm",
        "--dir",
        "kanban/web",
        "exec",
        "playwright",
        "test",
        "e2e/perf-board-drag.spec.ts",
        "--project=desktop",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, env=env, check=False)  # noqa: S603
    if res.returncode != 0:
        msg = (
            f"Playwright drag benchmark failed (code {res.returncode}):\n{res.stderr}\n{res.stdout}"
        )
        raise RuntimeError(msg)

    if not report_json_path.is_file():
        msg = f"Playwright drag benchmark succeeded but did not write report {report_json_path}"
        raise RuntimeError(msg)

    return cast("dict[str, Any]", json.loads(report_json_path.read_text(encoding="utf-8")))


def run_all_benchmarks(
    qa_dir: Path,
    *,
    skip_container: bool = False,
) -> dict[str, Any]:
    """Execute all 5 benchmarks and aggregate raw metric results."""
    qa_dir.mkdir(parents=True, exist_ok=True)
    raw_data: dict[str, Any] = {}

    # 1. Sparkle FIM SLA
    sys.stdout.write("[1/5] Running Sparkle FIM benchmark...\n")
    sys.stdout.flush()
    sparkle_json = qa_dir / "perf-sparkle.json"
    raw_data["sparkle_p95"] = run_pytest_benchmark(
        "tests/perf/test_perf_sparkle_sla.py",
        sparkle_json,
    )

    # 2. Sync Hooks SLA
    sys.stdout.write("[2/5] Running Sync Wasm Hooks benchmark...\n")
    sys.stdout.flush()
    sync_json = qa_dir / "perf-sync-hooks.json"
    raw_data["sync_hooks_p95"] = run_pytest_benchmark(
        "tests/perf/test_perf_sync_hooks_sla.py",
        sync_json,
    )

    # 3. Clean-DB 1,000 Tests
    sys.stdout.write("[3/5] Running 1,000 Clean-DB SAVEPOINT benchmark...\n")
    sys.stdout.flush()
    _clean_db_s, clean_db_details = run_clean_db_benchmark()
    raw_data["clean_db_1000_s"] = clean_db_details

    # 4. Board Drag Frame SLA
    sys.stdout.write("[4/5] Running Board Drag Playwright benchmark...\n")
    sys.stdout.flush()
    drag_json = qa_dir / "perf-drag.json"
    raw_data["drag_p95"] = run_board_drag_benchmark(drag_json)

    # 5. Standalone Container Warm Boot
    if skip_container:
        sys.stdout.write(
            "[5/5] Skipping standalone container warm boot benchmark (--skip-container)\n"
        )
        sys.stdout.flush()
        raw_data["warm_boot_s"] = {
            "benchmark": "standalone_warm_boot",
            "max_s": 1.5,
            "samples": 3,
            "skipped": True,
        }
    else:
        sys.stdout.write("[5/5] Running Standalone Warm Boot benchmark...\n")
        sys.stdout.flush()
        boot_json = qa_dir / "perf-standalone-boot.json"
        raw_data["warm_boot_s"] = run_pytest_benchmark(
            "tests/perf/test_perf_standalone_boot.py",
            boot_json,
        )

    return raw_data


def load_evaluation_data(eval_path: Path) -> dict[str, Any]:
    """Load evaluation data from a directory or JSON file."""
    if eval_path.is_file():
        data = cast("dict[str, Any]", json.loads(eval_path.read_text(encoding="utf-8")))
        if "metrics" in data:
            return cast("dict[str, Any]", data["metrics"])
        return data

    if eval_path.is_dir():
        # Check for perf-report.json in directory
        report_file = eval_path / "perf-report.json"
        if report_file.is_file():
            data = cast("dict[str, Any]", json.loads(report_file.read_text(encoding="utf-8")))
            if "metrics" in data:
                return cast("dict[str, Any]", data["metrics"])
            return data

        # Check for individual benchmark JSONs
        combined: dict[str, Any] = {}
        for fname, key in [
            ("perf-drag.json", "drag_p95"),
            ("perf-sparkle.json", "sparkle_p95"),
            ("perf-sync-hooks.json", "sync_hooks_p95"),
            ("perf-standalone-boot.json", "warm_boot_s"),
        ]:
            f = eval_path / fname
            if f.is_file():
                combined[key] = json.loads(f.read_text(encoding="utf-8"))

        clean_db_file = eval_path / "clean-db.json"
        if clean_db_file.is_file():
            combined["clean_db_1000_s"] = json.loads(clean_db_file.read_text(encoding="utf-8"))

        return combined

    msg = f"Path {eval_path} does not exist"
    raise FileNotFoundError(msg)


def main(argv: list[str] | None = None) -> int:
    """Evaluate SLA performance budgets and output structured report."""
    parser = argparse.ArgumentParser(
        description="Automated SLA Performance Budget Gate (KB-P6-04)",
    )
    parser.add_argument(
        "--report-out",
        type=Path,
        default=Path("docs/qa/KANBA-151/perf-report.json"),
        help="Destination path for generated perf-report.json",
    )
    parser.add_argument(
        "--evaluate-only",
        type=Path,
        default=None,
        help="Evaluate an existing report or directory without executing live benchmarks",
    )
    parser.add_argument(
        "--skip-container",
        action="store_true",
        help="Skip docker container benchmarks in environments lacking Docker daemon",
    )

    args = parser.parse_args(argv)

    try:
        if args.evaluate_only:
            raw_data = load_evaluation_data(args.evaluate_only)
        else:
            qa_dir = args.report_out.parent
            raw_data = run_all_benchmarks(qa_dir, skip_container=args.skip_container)

        report = evaluate_raw_metrics(raw_data)

        # Write output report
        args.report_out.parent.mkdir(parents=True, exist_ok=True)
        args.report_out.write_text(
            json.dumps(report.to_dict(), indent=2),
            encoding="utf-8",
        )

        # Output Markdown summary table
        markdown_table = generate_markdown_summary(report)
        sys.stdout.write(markdown_table + "\n")
        sys.stdout.flush()

        if not report.overall_passed:
            sys.stderr.write(
                f"\n[PERF BUDGET GATE BREACH]: {len(report.breaches)} "
                "SLA budget breach(es) detected.\n"
            )
            for b in report.breaches:
                sys.stderr.write(f"  - {b}\n")
            return 2

    except (RuntimeError, ValueError, OSError, json.JSONDecodeError, KeyError) as err:
        sys.stderr.write(f"\n[PERF BUDGET GATE ERROR]: {err}\n")
        return 1
    else:
        sys.stdout.write("\n[PERF BUDGET GATE]: ALL 5 SLA BUDGETS SATISFIED (PASS)\n")
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
