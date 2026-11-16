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
"""Unit tests for Automated SLA Performance Budget Gate (KB-P6-04).

Asserts:
1. Synthetic report with all 5 metrics under ceiling exits 0.
2. Breaching any single SLA ceiling exits 2 naming the breached metric.
3. Missing any required metric exits 2.
4. Runtime error in runners exits 1.
5. >= 95% line and branch coverage on scripts.perf_budget_gate.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from scripts.perf_budget_gate import (
    REQUIRED_SLAS,
    _extract_metric_value,
    evaluate_raw_metrics,
    generate_markdown_summary,
    load_evaluation_data,
    main,
    run_all_benchmarks,
    run_board_drag_benchmark,
    run_clean_db_benchmark,
    run_pytest_benchmark,
)

PASSING_METRICS: dict[str, Any] = {
    "drag_p95": {
        "p95_ms": 11.9,
        "min_ms": 8.0,
        "p50_ms": 10.0,
        "max_ms": 11.9,
        "samples": 20,
    },
    "sparkle_p95": {
        "p95_ms": 149.9,
        "min_ms": 2.0,
        "p50_ms": 10.0,
        "max_ms": 149.9,
        "samples": 200,
    },
    "sync_hooks_p95": {
        "p95_ms": 24.9,
        "min_ms": 1.0,
        "p50_ms": 3.0,
        "max_ms": 24.9,
        "samples": 200,
    },
    "clean_db_1000_s": {
        "wall_clock_s": 9.9,
        "min_s": 9.0,
        "p50_s": 9.5,
        "max_s": 9.9,
        "samples": 1000,
    },
    "warm_boot_s": {
        "max_s": 2.9,
        "min_s": 2.0,
        "p50_s": 2.5,
        "samples": 3,
    },
}


def test_synthetic_passing_report_exits_0(tmp_path: Path) -> None:
    """Synthetic report with all 5 metrics under ceiling passes evaluation and exits 0."""
    eval_file = tmp_path / "perf-eval.json"
    eval_file.write_text(json.dumps(PASSING_METRICS), encoding="utf-8")
    out_file = tmp_path / "perf-report.json"

    ret = main(
        [
            "--evaluate-only",
            str(eval_file),
            "--report-out",
            str(out_file),
        ]
    )
    assert ret == 0

    assert out_file.is_file()
    saved = json.loads(out_file.read_text(encoding="utf-8"))
    assert saved["overall_passed"] is True
    assert len(saved["breaches"]) == 0
    assert len(saved["metrics"]) == 5


@pytest.mark.parametrize(
    ("breached_key", "breach_value", "expected_name"),
    [
        ("drag_p95", 12.0, "drag_p95"),
        ("drag_p95", 15.5, "drag_p95"),
        ("sparkle_p95", 150.0, "sparkle_p95"),
        ("sparkle_p95", 180.2, "sparkle_p95"),
        ("sync_hooks_p95", 25.0, "sync_hooks_p95"),
        ("sync_hooks_p95", 30.1, "sync_hooks_p95"),
        ("clean_db_1000_s", 10.0, "clean_db_1000_s"),
        ("clean_db_1000_s", 12.4, "clean_db_1000_s"),
        ("warm_boot_s", 3.0, "warm_boot_s"),
        ("warm_boot_s", 3.5, "warm_boot_s"),
    ],
)
def test_single_sla_breach_exits_2(
    tmp_path: Path,
    breached_key: str,
    breach_value: float,
    expected_name: str,
) -> None:
    """Breaching any single ceiling exits 2 naming the breached metric."""
    metrics = dict(PASSING_METRICS)
    breached_cfg = dict(metrics[breached_key])
    field_name = str(REQUIRED_SLAS[breached_key]["field_name"])
    breached_cfg[field_name] = breach_value
    metrics[breached_key] = breached_cfg

    eval_file = tmp_path / "perf-eval.json"
    eval_file.write_text(json.dumps(metrics), encoding="utf-8")
    out_file = tmp_path / "perf-report.json"

    ret = main(
        [
            "--evaluate-only",
            str(eval_file),
            "--report-out",
            str(out_file),
        ]
    )
    assert ret == 2

    assert out_file.is_file()
    saved = json.loads(out_file.read_text(encoding="utf-8"))
    assert saved["overall_passed"] is False
    assert any(expected_name in b for b in saved["breaches"])


@pytest.mark.parametrize("missing_key", list(REQUIRED_SLAS.keys()))
def test_missing_metric_exits_2(tmp_path: Path, missing_key: str) -> None:
    """Missing any of the 5 required SLAs causes overall failure and exits 2."""
    metrics = dict(PASSING_METRICS)
    del metrics[missing_key]

    eval_file = tmp_path / "perf-eval.json"
    eval_file.write_text(json.dumps(metrics), encoding="utf-8")
    out_file = tmp_path / "perf-report.json"

    ret = main(
        [
            "--evaluate-only",
            str(eval_file),
            "--report-out",
            str(out_file),
        ]
    )
    assert ret == 2

    saved = json.loads(out_file.read_text(encoding="utf-8"))
    assert saved["overall_passed"] is False
    assert any(missing_key in b for b in saved["breaches"])


def test_extract_metric_value_variants() -> None:
    """Extract numeric value from float, int, and various dict structures."""
    # Scalar float/int
    val, samples, details = _extract_metric_value(12.34, "observed")
    assert val == 12.34
    assert samples == 1
    assert details == {"observed": 12.34}

    val, samples, _ = _extract_metric_value(42, "observed")
    assert val == 42.0

    # Dict candidates
    val, samples, _ = _extract_metric_value({"p95_ms": 11.2, "samples": 50}, "p95_ms")
    assert val == 11.2
    assert samples == 50

    val, _, _ = _extract_metric_value({"wall_clock_s": 8.5}, "wall_clock_s")
    assert val == 8.5

    val, _, _ = _extract_metric_value({"max_s": 2.1}, "max_s")
    assert val == 2.1

    val, _, _ = _extract_metric_value({"val": 9.0}, "other")
    assert val == 9.0

    # Invalid formats
    with pytest.raises(ValueError, match="Unable to extract numeric value"):
        _extract_metric_value("non-numeric", "p95_ms")

    with pytest.raises(ValueError, match="Unable to extract numeric value"):
        _extract_metric_value({"other_key": "bad"}, "p95_ms")


def test_evaluate_raw_metrics_invalid_data() -> None:
    """Gracefully report breaches on invalid data structures."""
    invalid_data = dict(PASSING_METRICS)
    invalid_data["drag_p95"] = "invalid_string"
    report = evaluate_raw_metrics(invalid_data)
    assert report.overall_passed is False
    assert any("Invalid metric data for drag_p95" in b for b in report.breaches)


def test_load_evaluation_data_directory_with_report(tmp_path: Path) -> None:
    """Correctly read existing perf-report.json from directory or direct file."""
    report_file = tmp_path / "perf-report.json"
    report_file.write_text(
        json.dumps({"overall_passed": True, "metrics": PASSING_METRICS}),
        encoding="utf-8",
    )
    loaded = load_evaluation_data(tmp_path)
    assert "drag_p95" in loaded

    # Also test passing the file directly
    loaded_file = load_evaluation_data(report_file)
    assert "drag_p95" in loaded_file

    # Also test when metrics key is absent
    report_file.write_text(json.dumps(PASSING_METRICS), encoding="utf-8")
    loaded2 = load_evaluation_data(tmp_path)
    assert "drag_p95" in loaded2
    loaded2_file = load_evaluation_data(report_file)
    assert "drag_p95" in loaded2_file


def test_load_evaluation_data_individual_jsons(tmp_path: Path) -> None:
    """Combine individual benchmark JSON files."""
    (tmp_path / "perf-drag.json").write_text(json.dumps({"p95_ms": 11.0}), encoding="utf-8")
    (tmp_path / "perf-sparkle.json").write_text(json.dumps({"p95_ms": 140.0}), encoding="utf-8")
    (tmp_path / "perf-sync-hooks.json").write_text(json.dumps({"p95_ms": 20.0}), encoding="utf-8")
    (tmp_path / "perf-standalone-boot.json").write_text(
        json.dumps({"max_s": 2.5}), encoding="utf-8"
    )
    (tmp_path / "clean-db.json").write_text(json.dumps({"wall_clock_s": 8.0}), encoding="utf-8")

    combined = load_evaluation_data(tmp_path)
    assert combined["drag_p95"]["p95_ms"] == 11.0
    assert combined["sparkle_p95"]["p95_ms"] == 140.0
    assert combined["sync_hooks_p95"]["p95_ms"] == 20.0
    assert combined["warm_boot_s"]["max_s"] == 2.5
    assert combined["clean_db_1000_s"]["wall_clock_s"] == 8.0


def test_load_evaluation_data_missing_path() -> None:
    """Raise FileNotFoundError for missing path."""
    with pytest.raises(FileNotFoundError, match=r"Path .* does not exist"):
        load_evaluation_data(Path("/nonexistent/perf/dir"))


def test_generate_markdown_summary() -> None:
    """Format markdown with badges, tables, and breach lists."""
    report = evaluate_raw_metrics(PASSING_METRICS)
    md = generate_markdown_summary(report)
    assert "### Automated SLA Performance Budget Gate Report" in md
    assert "**Status:** `PASS`" in md
    assert "Board Optimistic Drag Frame (p95)" in md
    assert "PASS" in md

    # Breach report
    breach_metrics = dict(PASSING_METRICS)
    breach_metrics["drag_p95"] = {"p95_ms": 15.0}
    del breach_metrics["warm_boot_s"]
    breach_report = evaluate_raw_metrics(breach_metrics)
    breach_md = generate_markdown_summary(breach_report)
    assert "**Status:** `FAIL`" in breach_md
    assert "FAIL (BREACH)" in breach_md
    assert "FAIL (MISSING)" in breach_md
    assert "SLA Breaches Detected:" in breach_md


def test_run_pytest_benchmark(tmp_path: Path) -> None:
    """Run subprocess and read target report JSON."""
    report_json = tmp_path / "out.json"
    fake_payload = {"p95_ms": 10.5, "passed": True}

    def fake_subprocess_run(*_args: object, **_kwargs: object) -> MagicMock:
        report_json.write_text(json.dumps(fake_payload), encoding="utf-8")
        mock = MagicMock()
        mock.returncode = 0
        return mock

    with patch("subprocess.run", side_effect=fake_subprocess_run):
        res = run_pytest_benchmark("fake_test.py", report_json)
        assert res == fake_payload


def test_run_pytest_benchmark_failures(tmp_path: Path) -> None:
    """Raise RuntimeError on process error or missing output."""
    report_json = tmp_path / "out.json"

    # Process failure
    fail_mock = MagicMock()
    fail_mock.returncode = 1
    fail_mock.stderr = "Pytest execution failed"
    fail_mock.stdout = ""
    with (
        patch("subprocess.run", return_value=fail_mock),
        pytest.raises(RuntimeError, match=r"Benchmark fake_test\.py failed"),
    ):
        run_pytest_benchmark("fake_test.py", report_json)

    # Missing file output
    success_mock = MagicMock()
    success_mock.returncode = 0
    with (
        patch("subprocess.run", return_value=success_mock),
        pytest.raises(RuntimeError, match="did not write expected report"),
    ):
        run_pytest_benchmark("fake_test.py", report_json)


def test_run_clean_db_benchmark() -> None:
    """Execute clean-db benchmark and return elapsed seconds."""
    mock_res = MagicMock()
    mock_res.returncode = 0
    mock_res.stdout = "1000 passed in 4.5s"

    with patch("subprocess.run", return_value=mock_res):
        elapsed_s, details = run_clean_db_benchmark()
        assert elapsed_s >= 0.0
        assert details["benchmark"] == "clean_db_1000"
        assert details["samples"] == 1000

    # Failure
    mock_fail = MagicMock()
    mock_fail.returncode = 1
    mock_fail.stderr = "clean db failure"
    mock_fail.stdout = ""
    with (
        patch("subprocess.run", return_value=mock_fail),
        pytest.raises(RuntimeError, match="Clean-DB benchmark pytest failed"),
    ):
        run_clean_db_benchmark()


def test_run_board_drag_benchmark(tmp_path: Path) -> None:
    """Run Playwright test and read perf-drag.json."""
    report_json = tmp_path / "perf-drag.json"
    fake_payload = {"p95_ms": 9.2, "samples": 20}

    def fake_drag_run(*_args: object, **_kwargs: object) -> MagicMock:
        report_json.write_text(json.dumps(fake_payload), encoding="utf-8")
        mock = MagicMock()
        mock.returncode = 0
        return mock

    with patch("subprocess.run", side_effect=fake_drag_run):
        res = run_board_drag_benchmark(report_json)
        assert res == fake_payload

    # Failure
    fail_mock = MagicMock()
    fail_mock.returncode = 1
    fail_mock.stderr = "playwright failure"
    fail_mock.stdout = ""
    with (
        patch("subprocess.run", return_value=fail_mock),
        pytest.raises(RuntimeError, match="Playwright drag benchmark failed"),
    ):
        run_board_drag_benchmark(report_json)

    # Missing file output
    success_mock = MagicMock()
    success_mock.returncode = 0
    with (
        patch("subprocess.run", return_value=success_mock),
        pytest.raises(RuntimeError, match="did not write report"),
    ):
        run_board_drag_benchmark(report_json)


def test_run_all_benchmarks(tmp_path: Path) -> None:
    """Run all 5 benchmarks orchestrator."""
    with (
        patch(
            "scripts.perf_budget_gate.run_pytest_benchmark",
            return_value={"p95_ms": 10.0, "max_s": 2.0},
        ),
        patch(
            "scripts.perf_budget_gate.run_clean_db_benchmark",
            return_value=(4.5, {"wall_clock_s": 4.5}),
        ),
        patch(
            "scripts.perf_budget_gate.run_board_drag_benchmark",
            return_value={"p95_ms": 8.0},
        ),
    ):
        raw = run_all_benchmarks(tmp_path, skip_container=True)
        assert "sparkle_p95" in raw
        assert "sync_hooks_p95" in raw
        assert "clean_db_1000_s" in raw
        assert "drag_p95" in raw
        assert "warm_boot_s" in raw
        assert raw["warm_boot_s"]["skipped"] is True

        # Also test with skip_container=False
        raw2 = run_all_benchmarks(tmp_path, skip_container=False)
        assert raw2["warm_boot_s"]["max_s"] == 2.0


def test_main_runtime_error_exits_1(tmp_path: Path) -> None:
    """Exit 1 when a runner raises an unhandled error."""
    with (
        patch(
            "scripts.perf_budget_gate.run_all_benchmarks",
            side_effect=RuntimeError("Subprocess failed"),
        ),
    ):
        ret = main(["--report-out", str(tmp_path / "perf-report.json")])
        assert ret == 1
