"""Phase 5 tests for immutable ordered elapsed-millisecond diagnostics."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from math import inf, nan
from typing import cast

import pytest

from math_drawing_assistant.models import (
    PlotItemDiagnostics,
    PlotSceneDiagnostics,
    PlotSceneResult,
    StageTiming,
)


def test_stage_timing_accepts_zero_and_positive_finite_values() -> None:
    zero = StageTiming(stage="request_validation", elapsed_ms=0)
    positive = StageTiming(stage="future_stage", elapsed_ms=12.5)

    assert zero.elapsed_ms == 0.0
    assert positive.elapsed_ms == 12.5
    with pytest.raises(FrozenInstanceError):
        positive.elapsed_ms = 1.0  # type: ignore[misc]  # frozen contract probe


@pytest.mark.parametrize("elapsed_ms", [-0.1, nan, inf, -inf])
def test_stage_timing_rejects_negative_or_non_finite_values(
    elapsed_ms: float,
) -> None:
    with pytest.raises(ValueError):
        StageTiming(stage="validation", elapsed_ms=elapsed_ms)


def test_stage_timing_rejects_empty_names_and_non_numeric_values() -> None:
    with pytest.raises(ValueError, match="stage"):
        StageTiming(stage=" ", elapsed_ms=0)
    with pytest.raises(TypeError, match="elapsed_ms"):
        StageTiming(
            stage="validation",
            elapsed_ms=cast(float, "fast"),
        )


def test_plot_scene_result_reuses_elapsed_ms_as_ordered_tuple() -> None:
    validation = StageTiming(stage="request_validation", elapsed_ms=1.25)
    future = StageTiming(stage="future_stage", elapsed_ms=2.5)
    result = PlotSceneResult(
        request_id=1,
        scene_revision=0,
        success=True,
        elapsed_ms=(validation, future),
    )

    assert result.elapsed_ms == (validation, future)
    assert isinstance(result.elapsed_ms, tuple)
    assert [timing.stage for timing in result.elapsed_ms] == [
        "request_validation",
        "future_stage",
    ]


def test_plot_scene_result_rejects_unstructured_timing_entries() -> None:
    with pytest.raises(TypeError, match="StageTiming"):
        PlotSceneResult(
            request_id=1,
            scene_revision=0,
            success=True,
            elapsed_ms=cast(tuple[StageTiming, ...], ({"elapsed_ms": 1},)),
        )


def test_plot_item_diagnostics_enforces_planned_and_completed_counts() -> None:
    planned = PlotItemDiagnostics(planned_sample_point_count=20)
    completed = PlotItemDiagnostics(
        planned_sample_point_count=20,
        actual_sampled_point_count=20,
        sampled_segment_count=3,
        visible_segment_count=2,
    )

    assert planned.actual_sampled_point_count is None
    assert completed.visible_segment_count == 2
    with pytest.raises(ValueError, match="all present"):
        PlotItemDiagnostics(20, 20, 1, None)
    with pytest.raises(ValueError, match="planned"):
        PlotItemDiagnostics(20, 19, 1, 1)
    with pytest.raises(ValueError, match="exceed"):
        PlotItemDiagnostics(20, 20, 1, 2)


@pytest.mark.parametrize("value", [True, False, 0, -1])
def test_plot_diagnostics_reject_bool_and_nonpositive_required_counts(
    value: int,
) -> None:
    expected = TypeError if isinstance(value, bool) else ValueError
    with pytest.raises(expected):
        PlotItemDiagnostics(planned_sample_point_count=value)
    with pytest.raises(expected):
        PlotSceneDiagnostics(
            total_planned_sample_point_count=value,
            total_actual_sampled_point_count=None,
            approved_estimated_memory_bytes=1,
        )


def test_plot_scene_diagnostics_enforces_actual_and_png_dependencies() -> None:
    planned = PlotSceneDiagnostics(20, None, 1_000)
    completed = PlotSceneDiagnostics(20, 20, 1_000, 512)

    assert planned.final_png_byte_count is None
    assert completed.final_png_byte_count == 512
    with pytest.raises(ValueError, match="planned"):
        PlotSceneDiagnostics(20, 19, 1_000)
    with pytest.raises(ValueError, match="requires completed"):
        PlotSceneDiagnostics(20, None, 1_000, 512)


def test_scene_result_cross_checks_png_diagnostic_byte_count() -> None:
    diagnostics = PlotSceneDiagnostics(20, 20, 1_000, 4)
    result = PlotSceneResult(
        request_id=1,
        scene_revision=0,
        success=True,
        png_bytes=b"1234",
        diagnostics=diagnostics,
    )
    assert result.diagnostics is diagnostics
    with pytest.raises(ValueError, match="diagnostic byte count"):
        PlotSceneResult(
            request_id=1,
            scene_revision=0,
            success=True,
            png_bytes=b"123",
            diagnostics=diagnostics,
        )
