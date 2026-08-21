"""Contract tests for the frozen m1-performance-v1 protocol."""

from __future__ import annotations

from collections import Counter
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from benchmarks import m1_gui_benchmark as benchmark
from math_drawing_assistant.engine.validators import analyze_explicit_function
from math_drawing_assistant.models.errors import ErrorInfo


ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "docs" / "benchmarks" / "m1-performance-v1.md"
SUPPORTED = ROOT / "docs" / "supported-formulas.md"


def test_protocol_version_and_exact_scenarios_are_frozen() -> None:
    text = PROTOCOL.read_text(encoding="utf-8")
    assert benchmark.PROTOCOL_VERSION == "m1-performance-v1"
    assert "协议版本：`m1-performance-v1`" in text
    assert benchmark.SCHEDULE_SEED == 20260801
    assert [scenario.exact_input for scenario in benchmark.FORMULA_SCENARIOS] == [
        "x=y",
        "x^2",
        "1/x",
        "ln(x)",
        "sin(x)",
        "exp(x)",
        "log(x,10)",
        "sin(1000*x)",
    ]
    for scenario in benchmark.FORMULA_SCENARIOS:
        assert f"`{scenario.formula_id}`" in text
        assert f"`{scenario.exact_input}`" in text


def test_all_eight_scenarios_are_accepted_by_the_current_m1_validator() -> None:
    supported_text = SUPPORTED.read_text(encoding="utf-8")
    for scenario in benchmark.FORMULA_SCENARIOS:
        outcome = analyze_explicit_function(scenario.exact_input)
        assert not isinstance(outcome, ErrorInfo), scenario.exact_input
        assert scenario.exact_input in supported_text


@pytest.mark.parametrize(
    ("sample_kind", "rounds", "expected_per_formula", "expected_total"),
    [
        ("warmup", benchmark.WARMUP_ROUNDS, 5, 40),
        ("measurement", benchmark.MEASUREMENT_ROUNDS, 30, 240),
    ],
)
def test_schedule_counts_each_formula_once_per_round(
    sample_kind: str,
    rounds: int,
    expected_per_formula: int,
    expected_total: int,
) -> None:
    schedule = benchmark.build_schedule(sample_kind)
    assert len(schedule) == expected_total
    assert Counter(sample.formula_id for sample in schedule) == {
        scenario.formula_id: expected_per_formula
        for scenario in benchmark.FORMULA_SCENARIOS
    }
    for round_index in range(rounds):
        one_round = [sample for sample in schedule if sample.round_index == round_index]
        assert len(one_round) == 8
        assert {sample.formula_id for sample in one_round} == {
            scenario.formula_id for scenario in benchmark.FORMULA_SCENARIOS
        }


def test_schedule_is_deterministic_but_not_one_repeated_permutation() -> None:
    first = benchmark.full_render_schedule()
    second = benchmark.full_render_schedule()
    assert first == second

    measured = benchmark.build_schedule("measurement")
    permutations = {
        tuple(
            sample.formula_id
            for sample in measured
            if sample.round_index == round_index
        )
        for round_index in range(benchmark.MEASUREMENT_ROUNDS)
    }
    assert len(permutations) > 1


def test_nearest_rank_uses_frozen_one_based_ceil_positions() -> None:
    thirty = list(range(1, 31))
    twenty = list(range(1, 21))
    assert benchmark.nearest_rank(thirty, 0.50) == 15
    assert benchmark.nearest_rank(thirty, 0.95) == 29
    assert benchmark.nearest_rank(twenty, 0.50) == 10
    assert benchmark.nearest_rank(twenty, 0.95) == 19


def test_invalid_reason_enumerations_are_closed() -> None:
    assert {reason.value for reason in benchmark.InvalidReason} == {
        "application_process_exit",
        "request_failed",
        "request_cancelled",
        "request_timeout",
        "request_id_revision_mismatch",
        "missing_result",
        "duplicate_result",
        "benchmark_harness_exception",
        "incomplete_monotonic_record",
        "preview_not_updated",
    }
    assert {reason.value for reason in benchmark.InvalidBatchReason} == {
        "windows_sleep_or_resume",
        "benchmark_process_crash",
        "user_closed_window",
        "environment_changed",
        "schedule_corrupted",
        "result_integrity_failed",
    }


def test_threshold_retest_interval_is_strict_at_ninety_percent() -> None:
    assert benchmark.threshold_status(900.0, 1_000.0) == "met"
    assert benchmark.threshold_status(900.0001, 1_000.0) == "retest_required"
    assert benchmark.threshold_status(1_000.0, 1_000.0) == "retest_required"
    assert benchmark.threshold_status(1_000.0001, 1_000.0) == "not_met"


def test_protocol_freezes_required_result_files_and_sample_fields() -> None:
    text = PROTOCOL.read_text(encoding="utf-8")
    for name in benchmark.REQUIRED_RESULT_FILES:
        assert name in text
    for field in benchmark.RENDER_REQUIRED_FIELDS:
        assert field in text
    for field in benchmark.STARTUP_REQUIRED_FIELDS:
        assert field in text
    assert benchmark.FONT_CACHE_READY_MARKER in text
    assert benchmark.FONT_CACHE_READY_SCHEMA in text
    assert benchmark.FONT_CACHE_READY_SCHEMA_VERSION == 2
    assert "`schema_version` 固定为 `2`" in text
    for field in benchmark.MANIFEST_REQUIRED_FIELDS:
        assert f"`{field}`" in text
    assert "`basename`、byte `size` 和 SHA-256" in text
    assert "全部直属条目（包括文件和目录）" in text
    assert "非符号链接的普通文件" in text
    assert "不得提前 import Matplotlib" in text
    assert "retained `_source_image`" in text
    assert "staging" in text and "原子 rename" in text
    assert "<external-result-directory>" in text
    assert "协议与工具已冻结，尚未运行正式测量" in text


def test_protocol_freezes_new_batch_retest_command_contract() -> None:
    text = PROTOCOL.read_text(encoding="utf-8")
    assert "第二批正式命令模板" in text
    assert "--batch-id '<new-unique-batch-id>'" in text
    assert "--retest-of '<first-batch-id>'" in text
    assert "--output-dir '<new-nonexistent-external-result-directory>'" in text
    assert "禁止 self-retest" in text


def test_m1_performance_v1_keeps_its_historical_auto_aspect_default() -> None:
    text = PROTOCOL.read_text(encoding="utf-8")

    assert "| 比例 | `auto` | `ViewportPanel` 首个 aspect 项 |" in text


def test_current_ui_and_controller_defaults_are_exercised_separately() -> None:
    script = """
import json
from PySide6.QtWidgets import QApplication
from math_drawing_assistant.app_controller import AppController, M1_DEFAULT_DPI
from math_drawing_assistant.ui.main_window import MainWindow
app = QApplication([])
window = MainWindow(controller=AppController())
viewport = window.viewport_panel
print(json.dumps({
    "viewport_mode": viewport.viewport_mode(),
    "aspect_mode": viewport.aspect_mode(),
    "show_grid": viewport.show_grid(),
    "image_width": viewport.image_width(),
    "image_height": viewport.image_height(),
    "dpi": M1_DEFAULT_DPI,
}))
window.close()
"""
    environment = os.environ.copy()
    environment["QT_QPA_PLATFORM"] = "offscreen"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = str(ROOT)
    completed = subprocess.run(
        [sys.executable, "-B", "-c", script],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert json.loads(completed.stdout) == {
        "viewport_mode": "auto",
        "aspect_mode": "default",
        "show_grid": True,
        "image_width": 800,
        "image_height": 600,
        "dpi": 96,
    }
