"""Phase 5 tests for immutable ordered elapsed-millisecond diagnostics."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from math import inf, nan
from typing import cast

import pytest

from math_drawing_assistant.models import PlotSceneResult, StageTiming


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
