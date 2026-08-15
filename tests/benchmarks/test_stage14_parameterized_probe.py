"""Contract tests for the direct Stage 14 parameterized prototype tool."""

from __future__ import annotations

import ast
from dataclasses import fields
import json
from pathlib import Path

import pytest

from benchmarks import stage14_parameterized_probe as probe
from math_drawing_assistant.engine import analyze_plot_item
from math_drawing_assistant.models import (
    CircleSpec,
    EllipseSpec,
    ErrorCode,
    ErrorInfo,
    HyperbolaSpec,
    LineSpec,
    ParameterizedRenderMemoryBudget,
    ParabolaOpening,
    ParabolaSpec,
    PlotItemRequest,
)


EXPECTED_SCENARIO_ORDER = (
    "line-vertical",
    "line-general",
    "circle-origin",
    "circle-translated",
    "ellipse-origin",
    "ellipse-translated",
    "hyperbola-horizontal",
    "hyperbola-vertical",
    "hyperbola-one-branch-split",
    "parabola-up",
    "parabola-down",
    "parabola-right",
    "parabola-left",
    "parabola-vertex-excluded-two-segments",
)


def _analyze_scenario(scenario: probe.PrototypeScenario) -> object:
    return analyze_plot_item(
        PlotItemRequest(
            item_id=f"test-{scenario.name}",
            input_text=scenario.formula,
            input_source=probe.InputSource.MANUAL,
            requested_plot_kind=probe.PlotKind.AUTO,
            display_order=0,
        ),
    )


def test_protocol_version_scenario_order_and_counts_are_frozen() -> None:
    assert probe.PROTOCOL_VERSION == "stage14-parameterized-prototype-v1"
    assert probe.WARMUP_RUNS == 1
    assert probe.MEASUREMENT_RUNS == 5
    assert tuple(scenario.name for scenario in probe.SCENARIOS) == EXPECTED_SCENARIO_ORDER
    assert len(EXPECTED_SCENARIO_ORDER) == len(set(EXPECTED_SCENARIO_ORDER))
    assert all(type(scenario) is probe.PrototypeScenario for scenario in probe.SCENARIOS)


def test_fixed_scenarios_cover_five_geometry_types_and_four_parabola_openings() -> None:
    analyzed = tuple(_analyze_scenario(scenario) for scenario in probe.SCENARIOS)
    assert {type(value) for value in analyzed} >= {
        LineSpec,
        CircleSpec,
        EllipseSpec,
        HyperbolaSpec,
        ParabolaSpec,
    }
    openings = {
        value.opening for value in analyzed if type(value) is ParabolaSpec
    }
    assert openings == {
        ParabolaOpening.UP,
        ParabolaOpening.DOWN,
        ParabolaOpening.RIGHT,
        ParabolaOpening.LEFT,
    }
    assert "hyperbola-one-branch-split" in EXPECTED_SCENARIO_ORDER
    assert "parabola-vertex-excluded-two-segments" in EXPECTED_SCENARIO_ORDER


def test_scenarios_and_environment_do_not_collect_personal_paths() -> None:
    environment = probe.collect_environment(generated_at_utc="2026-08-14T00:00:00Z")
    payload = json.dumps(
        {
            "scenarios": [
                {
                    "name": scenario.name,
                    "formula": scenario.formula,
                    "viewport": repr(scenario.viewport_request),
                }
                for scenario in probe.SCENARIOS
            ],
            "environment": environment,
        },
        ensure_ascii=False,
    ).lower()
    assert "\\users\\" not in payload
    assert "/users/" not in payload
    assert "/home/" not in payload
    assert "username" not in environment
    assert "environment_variables" not in environment


def test_success_record_schema_timing_and_actual_buffer_bytes_are_complete() -> None:
    records = probe.run_scenario(
        probe.SCENARIOS[0],
        warmup_runs=0,
        measurement_runs=1,
    )
    assert len(records) == 1
    record = records[0]
    assert set(record) == probe.RECORD_FIELDS
    assert record["success"] is True
    assert record["status"] == "success"
    assert record["failure_stage"] is None
    assert record["error_code"] is None
    assert record["spec_type"] == "LineSpec"
    for name in (
        "analyze_elapsed_ns",
        "resolve_elapsed_ns",
        "build_elapsed_ns",
        "sample_elapsed_ns",
        "total_elapsed_ns",
        "cancellation_elapsed_ns",
    ):
        assert type(record[name]) is int
        assert record[name] >= 0
    budget = record["memory_budget"]
    assert isinstance(budget, dict)
    assert set(budget) == probe.MEMORY_BUDGET_KEYS
    assert {field.name for field in fields(ParameterizedRenderMemoryBudget)} < set(budget)
    assert budget["fixed_bytes"] + budget["batch_bytes"] == budget["total_bytes"]
    assert record["actual_x_bytes"] == record["sample_count"] * 8
    assert record["actual_y_bytes"] == record["sample_count"] * 8
    assert record["actual_segment_range_bytes"] == record["actual_segment_count"] * 2 * 8
    assert record["actual_x_bytes"] == budget["final_x_bytes"]
    assert record["actual_y_bytes"] == budget["final_y_bytes"]
    assert record["actual_segment_range_bytes"] <= budget["segment_index_range_bytes"]
    assert record["cancellation_probe_calls"] >= 1
    assert record["cancellation_neutral"] is True


def test_typed_failure_is_retained_and_never_rewritten_as_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def typed_failure(request: PlotItemRequest) -> ErrorInfo:
        return ErrorInfo(
            code=ErrorCode.INVALID_REQUEST,
            user_message="typed failure",
            technical_message="benchmark test failure",
            item_id=request.item_id,
        )

    monkeypatch.setattr(probe, "analyze_plot_item", typed_failure)
    record, = probe.run_scenario(
        probe.SCENARIOS[0],
        warmup_runs=0,
        measurement_runs=1,
    )
    assert set(record) == probe.RECORD_FIELDS
    assert record["success"] is False
    assert record["status"] == "typed_failure"
    assert record["failure_stage"] == "analyze"
    assert record["error_code"] == ErrorCode.INVALID_REQUEST.value
    assert record["spec_type"] is None
    assert record["memory_budget"] is None


def test_result_bundle_contains_parseable_json_and_jsonl(tmp_path: Path) -> None:
    run = probe.run_probe(
        (probe.SCENARIOS[0],),
        warmup_runs=0,
        measurement_runs=1,
    )
    directory = probe.write_result_bundle(run, output_root=tmp_path)
    assert directory.name.endswith(f"-{probe.PROTOCOL_VERSION}")
    assert set(path.name for path in directory.iterdir()) == set(probe.RESULT_FILENAMES)

    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    environment = json.loads(
        (directory / "environment.json").read_text(encoding="utf-8"),
    )
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    records = [
        json.loads(line)
        for line in (directory / "records.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert manifest["record_count"] == 1
    assert manifest["scenario_order"] == [probe.SCENARIOS[0].name]
    assert environment["protocol_version"] == probe.PROTOCOL_VERSION
    assert records == run["records"]
    assert summary["formal_percentiles_computed"] is False
    summary_keys: set[str] = set()

    def collect_keys(value: object) -> None:
        if isinstance(value, dict):
            summary_keys.update(str(key).lower() for key in value)
            for child in value.values():
                collect_keys(child)
        elif isinstance(value, list):
            for child in value:
                collect_keys(child)

    collect_keys(summary)
    assert {"p50", "p95"}.isdisjoint(summary_keys)
    assert summary["overall"]["raw_total_elapsed_ns"] == [
        records[0]["total_elapsed_ns"],
    ]


def test_probe_module_imports_no_renderer_actor_ui_or_pyplot() -> None:
    source_path = Path(probe.__file__)
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_modules.append(node.module)
    forbidden = (
        "math_drawing_assistant.engine.renderer",
        "math_drawing_assistant.engine.scene_executor",
        "math_drawing_assistant.workers",
        "math_drawing_assistant.ui",
        "matplotlib.pyplot",
    )
    assert not any(
        module == prefix or module.startswith(f"{prefix}.")
        for module in imported_modules
        for prefix in forbidden
    )
    for required_call in (
        "analyze_plot_item(",
        "PlotSceneSpec(",
        "resolve_single_item_viewport(",
        "RenderPlanBuilder().build(",
        "sample_parameterized_curve(",
    ):
        assert required_call in source
