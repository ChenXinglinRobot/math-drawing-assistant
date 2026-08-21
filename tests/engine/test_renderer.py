"""Stage 9B/9C tests for the minimal Qt-independent Agg PNG renderer."""

from __future__ import annotations

import ast
from dataclasses import fields, replace
import gc
import inspect
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
from typing import get_args
import weakref

import matplotlib
import numpy as np
import pytest
from matplotlib.axes import Axes
from matplotlib.backend_bases import FigureManagerBase

from math_drawing_assistant.config import ApplicationLimits, DEFAULT_LIMITS
from math_drawing_assistant.engine import (
    RenderPlanBuilder,
    RenderCancelled,
    RenderOutcome,
    SampledExplicitFunction,
    SamplingCancelled,
    analyze_explicit_function,
    build_explicit_scene_spec,
    render_explicit_png,
    sample_explicit_function,
)
from math_drawing_assistant.engine import renderer
from math_drawing_assistant.models import render_plan as render_plan_model
from math_drawing_assistant.models import (
    ErrorCode,
    ErrorInfo,
    InputSource,
    PlotItemRequest,
    PlotKind,
    RenderPlan,
    ResolvedAspect,
    ResolvedViewport,
    ValidatedExplicitExpression,
    ViewportSource,
)


def _plan(
    text: str = "x",
    *,
    x_bounds: tuple[float, float] = (-10, 10),
    y_bounds: tuple[float, float] = (-10, 10),
    aspect: ResolvedAspect = ResolvedAspect.AUTO,
    image_width: int = 320,
    image_height: int = 240,
    dpi: int = 96,
    item_id: str = "render-item",
    show_grid: bool = True,
    show_legend: bool = False,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> RenderPlan:
    validated = analyze_explicit_function(text)
    assert isinstance(validated, ValidatedExplicitExpression), validated
    request = PlotItemRequest(
        item_id=item_id,
        input_text=text,
        input_source=InputSource.MANUAL,
        requested_plot_kind=PlotKind.EXPLICIT_FUNCTION,
        display_order=0,
    )
    scene = build_explicit_scene_spec(request, validated)
    viewport = ResolvedViewport(
        x_min=x_bounds[0],
        x_max=x_bounds[1],
        y_min=y_bounds[0],
        y_max=y_bounds[1],
        aspect=aspect,
        source=ViewportSource.MANUAL,
    )
    result = RenderPlanBuilder(limits=limits).build(
        scene,
        viewport,
        image_width=image_width,
        image_height=image_height,
        dpi=dpi,
        show_grid=show_grid,
        show_legend=show_legend,
    )
    assert isinstance(result, RenderPlan), result
    return result


def _sample(plan: RenderPlan) -> SampledExplicitFunction:
    outcome = sample_explicit_function(plan)
    assert isinstance(outcome, SampledExplicitFunction), outcome
    return outcome


def _ordinary_sampled_copy(
    sampled: SampledExplicitFunction,
    *,
    item_id: str | None = None,
    x: np.ndarray | None = None,
    y: np.ndarray | None = None,
    segment_ranges: np.ndarray | None = None,
    finite_sample_count: int | None = None,
    nonfinite_sample_count: int | None = None,
    visible_segment_count: int | None = None,
) -> SampledExplicitFunction:
    result = SampledExplicitFunction(
        item_id=sampled.item_id if item_id is None else item_id,
        x=sampled.x if x is None else x,
        y=sampled.y if y is None else y,
        segment_ranges=(
            sampled.segment_ranges if segment_ranges is None else segment_ranges
        ),
        finite_sample_count=(
            sampled.finite_sample_count
            if finite_sample_count is None
            else finite_sample_count
        ),
        nonfinite_sample_count=(
            sampled.nonfinite_sample_count
            if nonfinite_sample_count is None
            else nonfinite_sample_count
        ),
        isolated_finite_count=sampled.isolated_finite_count,
        discontinuity_break_count=sampled.discontinuity_break_count,
        visible_segment_count=(
            sampled.visible_segment_count
            if visible_segment_count is None
            else visible_segment_count
        ),
        warnings=sampled.warnings,
        diagnostics=sampled.diagnostics,
    )
    return result


def _corrupt_for_negative_test(
    target: object,
    name: str,
    value: object,
) -> None:
    """Deliberately break a private/frozen contract for a rejection assertion."""

    # Negative defense only: every caller verifies that rendering rejects the
    # corrupted object; this helper is never used to create a success outcome.
    object.__setattr__(target, name, value)


def _frozen_ranges(values: list[tuple[int, int]]) -> np.ndarray:
    result = np.empty((len(values), 2), dtype=np.int64)
    for index, (start, stop) in enumerate(values):
        result[index, 0] = start
        result[index, 1] = stop
    result.setflags(write=False)
    return result


def _capture_rendered_axes(
    monkeypatch: pytest.MonkeyPatch,
) -> list[object]:
    captured: list[object] = []
    original = renderer._configure_axes

    def capture(axes: object, plan: RenderPlan) -> None:
        original(axes, plan)
        captured.append(axes)
        axes.clear = lambda: None

    monkeypatch.setattr(renderer, "_configure_axes", capture)
    return captured


class _CancelOnCall:
    def __init__(self, call_number: int) -> None:
        self.call_number = call_number
        self.calls = 0

    def is_cancelled(self) -> bool:
        self.calls += 1
        return self.calls == self.call_number


class _RaiseOnCall:
    def __init__(self, call_number: int) -> None:
        self.call_number = call_number
        self.calls = 0

    def is_cancelled(self) -> bool:
        self.calls += 1
        if self.calls == self.call_number:
            raise RuntimeError("secret cancellation probe detail")
        return False


class _MemoryRaiseOnCall:
    def __init__(self, call_number: int) -> None:
        self.call_number = call_number
        self.calls = 0

    def is_cancelled(self) -> bool:
        self.calls += 1
        if self.calls == self.call_number:
            raise MemoryError("sensitive test detail")
        return False


def _track_render_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[
    list[str],
    list[BytesIO],
    dict[str, list[weakref.ReferenceType[object]]],
]:
    events: list[str] = []
    buffers: list[BytesIO] = []
    references: dict[str, list[weakref.ReferenceType[object]]] = {
        "figure": [],
        "canvas": [],
        "axes": [],
    }
    figure_type = renderer.Figure
    canvas_type = renderer.FigureCanvasAgg
    plot = Axes.plot

    class TrackingFigure(figure_type):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, **kwargs)
            references["figure"].append(weakref.ref(self))
            events.append("figure")
            self._tracking_ready = True

        def add_subplot(self, *args: object, **kwargs: object) -> object:
            axes = super().add_subplot(*args, **kwargs)
            references["axes"].append(weakref.ref(axes))
            events.append("axes")
            return axes

        def clear(self, *args: object, **kwargs: object) -> None:
            if getattr(self, "_tracking_ready", False):
                events.append("figure.close")
            super().clear(*args, **kwargs)

    class TrackingCanvas(canvas_type):
        def __init__(self, figure: object) -> None:
            super().__init__(figure)
            references["canvas"].append(weakref.ref(self))
            events.append("canvas")

        def print_png(self, *args: object, **kwargs: object) -> None:
            events.append("encode")
            super().print_png(*args, **kwargs)

    class TrackingBytesIO(BytesIO):
        def __init__(self) -> None:
            super().__init__()
            buffers.append(self)
            events.append("buffer")

        def getvalue(self) -> bytes:
            events.append("getvalue")
            return super().getvalue()

        def close(self) -> None:
            events.append("buffer.close")
            self.size_at_close = self.tell()
            super().close()

    def tracking_plot(
        axes: Axes,
        *args: object,
        **kwargs: object,
    ) -> list[object]:
        events.append("plot")
        return plot(axes, *args, **kwargs)

    monkeypatch.setattr(renderer, "Figure", TrackingFigure)
    monkeypatch.setattr(renderer, "FigureCanvasAgg", TrackingCanvas)
    monkeypatch.setattr(renderer, "BytesIO", TrackingBytesIO)
    monkeypatch.setattr(Axes, "plot", tracking_plot)
    return events, buffers, references


def _assert_resources_released(
    buffers: list[BytesIO],
    references: dict[str, list[weakref.ReferenceType[object]]],
) -> None:
    assert all(buffer.closed for buffer in buffers)
    gc.collect()
    assert all(
        reference() is None
        for values in references.values()
        for reference in values
    )


def _forbid_figure(*args: object, **kwargs: object) -> object:
    raise AssertionError("renderer must not create a Figure on this path")


def _forbid_resource(*args: object, **kwargs: object) -> object:
    raise AssertionError("renderer must not create this resource on this path")


def _tracked_backend_modules() -> set[str]:
    return {
        name
        for name in sys.modules
        if name == "matplotlib.pyplot"
        or name == "PySide6"
        or name.startswith("PySide6.")
    }


def _assert_sanitized_probe_internal_error(outcome: object) -> None:
    assert isinstance(outcome, ErrorInfo)
    assert outcome.code is ErrorCode.INTERNAL_ERROR
    assert outcome.recoverable is False
    assert outcome.technical_message == "cancellation probe raised unexpectedly"
    for forbidden in (
        "sensitive test detail",
        "Traceback",
        "RenderPlan(",
        "_APPROVAL_SEAL",
        "_seal",
        "array(",
        "x^2",
        "\\",
        "/",
    ):
        assert forbidden not in outcome.technical_message


def test_public_api_is_the_minimal_typed_boundary() -> None:
    signature = inspect.signature(render_explicit_png)

    assert tuple(signature.parameters) == (
        "plan",
        "sampling_outcome",
        "cancellation_probe",
    )
    assert signature.parameters["cancellation_probe"].kind is inspect.Parameter.KEYWORD_ONLY
    assert set(get_args(RenderOutcome)) == {bytes, RenderCancelled, ErrorInfo}
    assert RenderCancelled.__dataclass_params__.frozen is True
    assert "item_id" in {field.name for field in fields(RenderCancelled)}
    assert "__dict__" not in RenderCancelled.__dict__


@pytest.mark.parametrize("tamper_receipt", [False, True])
def test_unapproved_or_tampered_plan_fails_before_figure(
    monkeypatch: pytest.MonkeyPatch,
    tamper_receipt: bool,
) -> None:
    approved = _plan()
    sampled = _sample(approved)
    if tamper_receipt:
        plan = approved
        receipt = plan._approval_receipt
        assert receipt is not None
        # Negative defense: deliberately corrupt the private approval seal and
        # verify that rendering rejects it before allocating any resources.
        _corrupt_for_negative_test(receipt, "_seal", object())
    else:
        plan = replace(approved)
    monkeypatch.setattr(renderer, "Figure", _forbid_figure)

    outcome = render_explicit_png(plan, sampled)

    assert isinstance(outcome, ErrorInfo)
    assert outcome.code is ErrorCode.INTERNAL_ERROR
    assert outcome.recoverable is False
    assert "receipt" not in outcome.user_message.lower()


def test_ordinary_sampled_object_is_rejected_before_figure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan()
    ordinary = _ordinary_sampled_copy(_sample(plan))
    monkeypatch.setattr(renderer, "Figure", _forbid_figure)

    outcome = render_explicit_png(plan, ordinary)

    assert isinstance(outcome, ErrorInfo)
    assert outcome.code is ErrorCode.INTERNAL_ERROR
    assert outcome.recoverable is False


@pytest.mark.parametrize(
    "other_plan",
    [
        lambda: _plan("x^2"),
        lambda: _plan("x", x_bounds=(-9, 10)),
    ],
)
def test_sample_from_another_approved_plan_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    other_plan: object,
) -> None:
    original_plan = _plan("x")
    sampled = _sample(original_plan)
    plan = other_plan()
    assert original_plan.item_plan is not None
    assert plan.item_plan is not None
    assert original_plan.item_plan.item_id == plan.item_plan.item_id
    assert original_plan.item_plan.sample_count == plan.item_plan.sample_count
    monkeypatch.setattr(renderer, "Figure", _forbid_figure)

    outcome = render_explicit_png(plan, sampled)

    assert isinstance(outcome, ErrorInfo)
    assert outcome.code is ErrorCode.INTERNAL_ERROR


def test_formal_sampler_outcome_renders_png_with_exact_ihdr_dimensions() -> None:
    plan = _plan(image_width=641, image_height=377, dpi=123)

    outcome = render_explicit_png(plan, _sample(plan))

    assert isinstance(outcome, bytes)
    assert outcome[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(outcome) > 24
    assert outcome[12:16] == b"IHDR"
    assert int.from_bytes(outcome[16:20], "big") == 641
    assert int.from_bytes(outcome[20:24], "big") == 377


def test_upstream_error_is_returned_unchanged_without_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan()
    expected = ErrorInfo(
        code=ErrorCode.NO_VISIBLE_CURVE,
        user_message="No visible curve.",
        item_id=plan.item_plan.item_id if plan.item_plan is not None else None,
        recoverable=True,
    )
    monkeypatch.setattr(renderer, "Figure", _forbid_figure)

    outcome = render_explicit_png(plan, expected)

    assert outcome is expected


@pytest.mark.parametrize(
    "upstream",
    [
        ErrorInfo(
            code=ErrorCode.RENDER_FAILED,
            user_message="Upstream failure.",
            item_id="another-item",
        ),
        SamplingCancelled("another-item"),
    ],
)
def test_upstream_item_mismatch_is_internal_without_resources(
    monkeypatch: pytest.MonkeyPatch,
    upstream: ErrorInfo | SamplingCancelled,
) -> None:
    plan = _plan()
    monkeypatch.setattr(renderer, "Figure", _forbid_figure)

    outcome = render_explicit_png(plan, upstream)

    assert isinstance(outcome, ErrorInfo)
    assert outcome.code is ErrorCode.INTERNAL_ERROR
    assert outcome.recoverable is False


def test_sampling_cancellation_becomes_render_cancellation_without_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan()
    assert plan.item_plan is not None
    monkeypatch.setattr(renderer, "Figure", _forbid_figure)

    outcome = render_explicit_png(
        plan,
        SamplingCancelled(plan.item_plan.item_id),
    )

    assert outcome == RenderCancelled(plan.item_plan.item_id)


def test_forged_empty_segment_set_is_rejected_before_figure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan()
    sampled = _sample(plan)
    empty = _ordinary_sampled_copy(
        sampled,
        segment_ranges=_frozen_ranges([]),
        visible_segment_count=0,
    )
    monkeypatch.setattr(renderer, "Figure", _forbid_figure)

    outcome = render_explicit_png(plan, empty)

    assert isinstance(outcome, ErrorInfo)
    assert outcome.code is ErrorCode.INTERNAL_ERROR
    assert outcome.recoverable is False


def test_sample_count_and_segment_invariants_are_rechecked_before_figure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan()
    sampled = _sample(plan)
    shorter_x = np.array(sampled.x[:-1], dtype=np.float64, copy=True)
    shorter_y = np.array(sampled.y[:-1], dtype=np.float64, copy=True)
    shorter_x.setflags(write=False)
    shorter_y.setflags(write=False)
    wrong_count = sampled
    # Negative defense: corrupt a genuine sampler result after provenance was
    # issued so the renderer must reject the now-invalid shape/count contract.
    _corrupt_for_negative_test(wrong_count, "x", shorter_x)
    _corrupt_for_negative_test(wrong_count, "y", shorter_y)
    _corrupt_for_negative_test(
        wrong_count,
        "segment_ranges",
        _frozen_ranges([(0, shorter_x.shape[0])]),
    )
    _corrupt_for_negative_test(
        wrong_count,
        "finite_sample_count",
        shorter_x.shape[0],
    )

    invalid_range = _sample(plan)
    # Negative defense: corrupt only the segment range of a genuine sampler
    # result and verify that rendering rejects it before Figure construction.
    _corrupt_for_negative_test(
        invalid_range,
        "segment_ranges",
        _frozen_ranges([(0, invalid_range.x.shape[0] + 1)]),
    )
    monkeypatch.setattr(renderer, "Figure", _forbid_figure)

    for candidate in (wrong_count, invalid_range):
        outcome = render_explicit_png(plan, candidate)
        assert isinstance(outcome, ErrorInfo)
        assert outcome.code is ErrorCode.INTERNAL_ERROR
        assert outcome.recoverable is False


def test_sampled_item_id_is_rechecked_after_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan()
    sampled = _sample(plan)
    mismatch = sampled
    # Negative defense: corrupt the item identity on a genuine sampler result
    # and verify that the renderer refuses the provenance/item mismatch.
    _corrupt_for_negative_test(mismatch, "item_id", "another-item")
    monkeypatch.setattr(renderer, "Figure", _forbid_figure)

    outcome = render_explicit_png(plan, mismatch)

    assert isinstance(outcome, ErrorInfo)
    assert outcome.code is ErrorCode.INTERNAL_ERROR


@pytest.mark.parametrize(
    ("aspect", "expected_aspect"),
    [
        (ResolvedAspect.AUTO, "auto"),
        (ResolvedAspect.EQUAL, 1.0),
    ],
)
def test_viewport_autoscale_and_aspect_are_fixed_by_the_plan(
    monkeypatch: pytest.MonkeyPatch,
    aspect: ResolvedAspect,
    expected_aspect: str | float,
) -> None:
    plan = _plan(
        x_bounds=(-3, 7),
        y_bounds=(-4, 9),
        aspect=aspect,
    )
    captured = _capture_rendered_axes(monkeypatch)

    outcome = render_explicit_png(plan, _sample(plan))

    assert isinstance(outcome, bytes)
    axes = captured[0]
    assert axes.get_autoscale_on() is False
    assert axes.get_xlim() == pytest.approx((-3.0, 7.0))
    assert axes.get_ylim() == pytest.approx((-4.0, 9.0))
    assert axes.get_aspect() == expected_aspect


@pytest.mark.parametrize(
    ("x_bounds", "y_bounds", "left_position", "bottom_position"),
    [
        ((-3, 7), (-4, 9), ("data", 0.0), ("data", 0.0)),
        ((-3, 7), (4, 9), ("data", 0.0), ("axes", 0.0)),
        ((2, 7), (-4, 9), ("axes", 0.0), ("data", 0.0)),
        ((2, 7), (3, 9), ("axes", 0.0), ("axes", 0.0)),
        ((-7, -2), (-9, -3), ("axes", 1.0), ("axes", 1.0)),
    ],
)
def test_axis_spines_follow_origin_or_nearest_frame_edge(
    monkeypatch: pytest.MonkeyPatch,
    x_bounds: tuple[float, float],
    y_bounds: tuple[float, float],
    left_position: tuple[str, float],
    bottom_position: tuple[str, float],
) -> None:
    plan = _plan(x_bounds=x_bounds, y_bounds=y_bounds)
    captured = _capture_rendered_axes(monkeypatch)

    outcome = render_explicit_png(plan, _sample(plan))

    assert isinstance(outcome, bytes)
    axes = captured[0]
    assert axes.spines["left"].get_position() == left_position
    assert axes.spines["bottom"].get_position() == bottom_position
    assert axes.spines["right"].get_visible() is False
    assert axes.spines["top"].get_visible() is False
    assert axes.get_xlabel() == "x"
    assert axes.get_ylabel() == "y"


@pytest.mark.parametrize("show_grid", [False, True])
def test_grid_and_legend_follow_only_plan_flags(
    monkeypatch: pytest.MonkeyPatch,
    show_grid: bool,
) -> None:
    plan = _plan(
        "1/x",
        x_bounds=(-1, 1),
        y_bounds=(-10, 10),
        image_width=800,
        show_grid=show_grid,
        show_legend=show_grid,
    )
    sampled = _sample(plan)
    assert sampled.segment_ranges.shape == (2, 2)
    captured = _capture_rendered_axes(monkeypatch)

    outcome = render_explicit_png(plan, sampled)

    assert isinstance(outcome, bytes)
    axes = captured[0]
    assert len(axes.lines) == 2
    assert [len(line.get_xdata()) for line in axes.lines] == [
        int(stop - start)
        for start, stop in sampled.segment_ranges
    ]
    if show_grid:
        assert axes.lines[0].get_label() == plan.scene_spec.items[0].normalized_input
        assert axes.lines[1].get_label().startswith("_")
        assert axes.get_legend() is not None
    else:
        assert axes.get_legend() is None
    gridlines = axes.get_xgridlines() + axes.get_ygridlines()
    assert any(line.get_visible() for line in gridlines) is show_grid


def test_renderer_never_mutates_or_thaws_sampled_arrays() -> None:
    plan = _plan("x^2")
    sampled = _sample(plan)
    before_x = np.array(sampled.x, copy=True)
    before_y = np.array(sampled.y, copy=True)
    before_ranges = np.array(sampled.segment_ranges, copy=True)

    outcome = render_explicit_png(plan, sampled)

    assert isinstance(outcome, bytes)
    assert sampled.x.flags.writeable is False
    assert sampled.y.flags.writeable is False
    assert sampled.segment_ranges.flags.writeable is False
    np.testing.assert_array_equal(sampled.x, before_x)
    np.testing.assert_array_equal(sampled.y, before_y)
    np.testing.assert_array_equal(sampled.segment_ranges, before_ranges)


def test_actual_encoded_png_limit_is_checked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    custom_limits = replace(DEFAULT_LIMITS, max_png_bytes=1_024)
    plan = _plan(limits=custom_limits)
    assert plan.memory_budget is not None
    assert plan.memory_budget.png_buffer_reserve_bytes == 1_024
    assert plan.memory_budget.png_copy_bytes == 1_024
    sampled = _sample(plan)
    events, buffers, references = _track_render_resources(monkeypatch)

    outcome = render_explicit_png(plan, sampled)

    assert isinstance(outcome, ErrorInfo)
    assert outcome.code is ErrorCode.RESOURCE_LIMIT_EXCEEDED
    assert outcome.recoverable is True
    assert outcome.field_name == "png_bytes"
    assert outcome.technical_message == "encoded PNG exceeds approved plan limit"
    assert events.count("encode") == 1
    assert "getvalue" not in events
    assert getattr(buffers[0], "size_at_close") > 1_024
    _assert_resources_released(buffers, references)

    normal_plan = _plan()
    succeeded = render_explicit_png(normal_plan, _sample(normal_plan))
    assert isinstance(succeeded, bytes)
    _assert_resources_released(buffers, references)


def test_pre_figure_cancellation_and_invalid_probe_are_internal_or_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan()
    sampled = _sample(plan)
    monkeypatch.setattr(renderer, "Figure", _forbid_figure)
    monkeypatch.setattr(renderer, "FigureCanvasAgg", _forbid_resource)
    monkeypatch.setattr(renderer, "BytesIO", _forbid_resource)

    cancelled = render_explicit_png(
        plan,
        sampled,
        cancellation_probe=_CancelOnCall(1),
    )

    class InvalidProbe:
        def is_cancelled(self) -> int:
            return 1

    invalid = render_explicit_png(
        plan,
        sampled,
        cancellation_probe=InvalidProbe(),
    )

    assert cancelled == RenderCancelled(sampled.item_id)
    assert isinstance(invalid, ErrorInfo)
    assert invalid.code is ErrorCode.INTERNAL_ERROR
    assert invalid.recoverable is False


def test_probe_memory_error_before_figure_is_internal_and_recovers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan("x^2")
    sampled = _sample(plan)
    probe = _MemoryRaiseOnCall(1)

    with monkeypatch.context() as injected:
        injected.setattr(renderer, "Figure", _forbid_figure)
        injected.setattr(renderer, "FigureCanvasAgg", _forbid_resource)
        injected.setattr(renderer, "BytesIO", _forbid_resource)
        outcome = render_explicit_png(
            plan,
            sampled,
            cancellation_probe=probe,
        )

    assert probe.calls == 1
    _assert_sanitized_probe_internal_error(outcome)
    assert not isinstance(outcome, bytes)
    assert isinstance(render_explicit_png(plan, sampled), bytes)


def test_success_and_encoding_failure_always_close_bytesio_and_recover(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan()
    sampled = _sample(plan)
    buffers: list[BytesIO] = []

    class TrackingBytesIO(BytesIO):
        def __init__(self) -> None:
            super().__init__()
            buffers.append(self)

    monkeypatch.setattr(renderer, "BytesIO", TrackingBytesIO)
    original_print_png = renderer.FigureCanvasAgg.print_png

    def fail_encoding(*args: object, **kwargs: object) -> None:
        raise RuntimeError("secret local path and formula")

    monkeypatch.setattr(renderer.FigureCanvasAgg, "print_png", fail_encoding)
    failed = render_explicit_png(plan, sampled)
    assert isinstance(failed, ErrorInfo)
    assert failed.code is ErrorCode.RENDER_FAILED
    assert failed.recoverable is True
    assert failed.technical_message is not None
    assert "RuntimeError" in failed.technical_message
    assert "secret" not in failed.technical_message
    assert buffers[-1].closed is True

    monkeypatch.setattr(
        renderer.FigureCanvasAgg,
        "print_png",
        original_print_png,
    )
    succeeded = render_explicit_png(plan, sampled)
    assert isinstance(succeeded, bytes)
    assert buffers[-1].closed is True


def test_memory_error_is_a_recoverable_resource_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan()
    sampled = _sample(plan)

    def fail_allocation(*args: object, **kwargs: object) -> object:
        raise MemoryError("secret allocation detail")

    monkeypatch.setattr(renderer, "Figure", fail_allocation)

    outcome = render_explicit_png(plan, sampled)

    assert isinstance(outcome, ErrorInfo)
    assert outcome.code is ErrorCode.RESOURCE_LIMIT_EXCEEDED
    assert outcome.recoverable is True
    assert outcome.technical_message is not None
    assert "MemoryError" in outcome.technical_message
    assert "secret" not in outcome.technical_message


def _assert_sanitized_prefigure_memory_error(
    outcome: object,
    *,
    technical_message: str,
) -> None:
    assert isinstance(outcome, ErrorInfo)
    assert outcome.code is ErrorCode.RESOURCE_LIMIT_EXCEEDED
    assert outcome.recoverable is True
    assert outcome.technical_message == technical_message
    for forbidden in (
        "secret",
        "Traceback",
        "RenderPlan(",
        "_APPROVAL_SEAL",
        "array(",
        "_seal",
    ):
        assert forbidden not in outcome.technical_message


def test_approval_validation_memory_error_precedes_all_render_resources_and_recovers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan("x^2")
    sampled = _sample(plan)

    def fail_snapshot(*args: object, **kwargs: object) -> object:
        raise MemoryError("secret approval snapshot and plan repr")

    with monkeypatch.context() as injected:
        injected.setattr(
            render_plan_model,
            "_approval_snapshot_from_plan",
            fail_snapshot,
        )
        injected.setattr(renderer, "Figure", _forbid_figure)
        injected.setattr(renderer, "FigureCanvasAgg", _forbid_resource)
        injected.setattr(renderer, "BytesIO", _forbid_resource)
        outcome = render_explicit_png(plan, sampled)

    _assert_sanitized_prefigure_memory_error(
        outcome,
        technical_message="approved render-plan validation allocation failed",
    )
    assert isinstance(render_explicit_png(plan, sampled), bytes)


def test_render_context_memory_error_precedes_all_render_resources_and_recovers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan("x^2")
    sampled = _sample(plan)

    class MemoryFailingLimits:
        @property
        def version(self) -> str:
            raise MemoryError("secret render context and formula")

    with monkeypatch.context() as injected:
        injected.setattr(renderer, "DEFAULT_LIMITS", MemoryFailingLimits())
        injected.setattr(renderer, "Figure", _forbid_figure)
        injected.setattr(renderer, "FigureCanvasAgg", _forbid_resource)
        injected.setattr(renderer, "BytesIO", _forbid_resource)
        outcome = render_explicit_png(plan, sampled)

    _assert_sanitized_prefigure_memory_error(
        outcome,
        technical_message="render context construction allocation failed",
    )
    assert isinstance(render_explicit_png(plan, sampled), bytes)


def test_provenance_snapshot_memory_error_precedes_all_render_resources_and_recovers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan("x^2")
    sampled = _sample(plan)
    original_snapshot = render_plan_model._approval_snapshot_from_plan
    snapshot_calls = 0

    def fail_current_plan_snapshot(value: object) -> object:
        nonlocal snapshot_calls
        snapshot_calls += 1
        if snapshot_calls == 2:
            raise MemoryError("secret provenance snapshot and arrays")
        return original_snapshot(value)

    with monkeypatch.context() as injected:
        injected.setattr(
            render_plan_model,
            "_approval_snapshot_from_plan",
            fail_current_plan_snapshot,
        )
        injected.setattr(renderer, "Figure", _forbid_figure)
        injected.setattr(renderer, "FigureCanvasAgg", _forbid_resource)
        injected.setattr(renderer, "BytesIO", _forbid_resource)
        outcome = render_explicit_png(plan, sampled)

    assert snapshot_calls == 2
    _assert_sanitized_prefigure_memory_error(
        outcome,
        technical_message="sampled provenance validation allocation failed",
    )
    assert isinstance(render_explicit_png(plan, sampled), bytes)


def test_renderer_does_not_persist_a_figure_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan()
    sampled = _sample(plan)
    references: list[weakref.ReferenceType[object]] = []
    figure_type = renderer.Figure

    def track_figure(*args: object, **kwargs: object) -> object:
        figure = figure_type(*args, **kwargs)
        references.append(weakref.ref(figure))
        return figure

    monkeypatch.setattr(renderer, "Figure", track_figure)

    outcome = render_explicit_png(plan, sampled)
    assert isinstance(outcome, bytes)
    gc.collect()
    assert len(references) == 1
    assert references[0]() is None


def test_renderer_static_boundary_has_no_qt_pyplot_or_upstream_execution() -> None:
    source_path = Path(renderer.__file__)
    source = source_path.read_text(encoding="utf-8")
    lowered = source.lower()
    tree = ast.parse(source)
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    imports.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    calls = {
        (
            node.func.id
            if isinstance(node.func, ast.Name)
            else node.func.attr
            if isinstance(node.func, ast.Attribute)
            else ""
        )
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }
    identifiers = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
    }
    identifiers.update(
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
    )

    assert "pyside6" not in lowered
    assert "matplotlib.pyplot" not in lowered
    assert "pyplot" not in lowered
    assert "plt." not in lowered
    assert "sample_explicit_function(" not in source
    assert "parse_input(" not in source
    assert "resolve_single_explicit_viewport(" not in source
    assert "execute_explicit_function(" not in source
    assert "bbox_inches=\"tight\"" not in source
    assert "bbox_inches='tight'" not in source
    assert "matplotlib.figure" in imports
    assert "matplotlib.backends.backend_agg" in imports
    assert calls.isdisjoint(
        {
            "sample_explicit_function",
            "analyze_explicit_function",
            "resolve_single_explicit_viewport",
            "build",
            "execute_explicit_function",
        },
    )
    assert identifiers.isdisjoint(
        {
            "QImage",
            "QPixmap",
            "QClipboard",
            "QThread",
            "QObject",
            "RenderActor",
            "RenderPlanBuilder",
            "NumericExecutor",
        },
    )
    assert not any(module == "main_window" for module in imports)
    assert not any(module.endswith("app_controller") for module in imports)
    assert not any(module.startswith("math_drawing_assistant.ui") for module in imports)
    assert not any(module.startswith("math_drawing_assistant.workers") for module in imports)


def test_first_segment_cancellation_releases_all_created_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan()
    events, buffers, references = _track_render_resources(monkeypatch)

    outcome = render_explicit_png(
        plan,
        _sample(plan),
        cancellation_probe=_CancelOnCall(2),
    )

    assert outcome == RenderCancelled(plan.item_plan.item_id)
    assert "plot" not in events
    assert "encode" not in events
    assert "getvalue" not in events
    _assert_resources_released(buffers, references)

    succeeded = render_explicit_png(plan, _sample(plan))
    assert isinstance(succeeded, bytes)
    assert len(buffers) == 2
    _assert_resources_released(buffers, references)


def test_cancellation_between_segments_discards_partial_drawing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan(
        "1/x",
        x_bounds=(-1, 1),
        y_bounds=(-10, 10),
        image_width=800,
    )
    sampled = _sample(plan)
    assert sampled.segment_ranges.shape == (2, 2)
    events, buffers, references = _track_render_resources(monkeypatch)

    outcome = render_explicit_png(
        plan,
        sampled,
        cancellation_probe=_CancelOnCall(3),
    )

    assert outcome == RenderCancelled(sampled.item_id)
    assert events.count("plot") == 1
    assert "encode" not in events
    assert "getvalue" not in events
    _assert_resources_released(buffers, references)


def test_pre_encoding_cancellation_never_writes_png(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan()
    events, buffers, references = _track_render_resources(monkeypatch)

    outcome = render_explicit_png(
        plan,
        _sample(plan),
        cancellation_probe=_CancelOnCall(3),
    )

    assert outcome == RenderCancelled(plan.item_plan.item_id)
    assert events.count("plot") == 1
    assert "encode" not in events
    assert "getvalue" not in events
    _assert_resources_released(buffers, references)


def test_post_encoding_cancellation_discards_temporary_png(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan()
    events, buffers, references = _track_render_resources(monkeypatch)

    outcome = render_explicit_png(
        plan,
        _sample(plan),
        cancellation_probe=_CancelOnCall(4),
    )

    assert outcome == RenderCancelled(plan.item_plan.item_id)
    assert events.count("encode") == 1
    assert "getvalue" not in events
    assert getattr(buffers[0], "size_at_close") > 24
    _assert_resources_released(buffers, references)


def test_final_return_cancellation_discards_owned_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan()
    events, buffers, references = _track_render_resources(monkeypatch)

    outcome = render_explicit_png(
        plan,
        _sample(plan),
        cancellation_probe=_CancelOnCall(5),
    )

    assert outcome == RenderCancelled(plan.item_plan.item_id)
    assert events.count("encode") == 1
    assert events.count("getvalue") == 1
    _assert_resources_released(buffers, references)


def test_probe_exception_is_internal_and_releases_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan()
    events, buffers, references = _track_render_resources(monkeypatch)

    outcome = render_explicit_png(
        plan,
        _sample(plan),
        cancellation_probe=_RaiseOnCall(2),
    )

    assert isinstance(outcome, ErrorInfo)
    assert outcome.code is ErrorCode.INTERNAL_ERROR
    assert outcome.recoverable is False
    assert outcome.technical_message is not None
    assert "secret" not in outcome.technical_message
    assert "plot" not in events
    _assert_resources_released(buffers, references)


def test_probe_memory_error_after_resources_is_internal_and_releases_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan("x^2")
    sampled = _sample(plan)
    probe = _MemoryRaiseOnCall(3)
    events, buffers, references = _track_render_resources(monkeypatch)

    outcome = render_explicit_png(
        plan,
        sampled,
        cancellation_probe=probe,
    )

    assert probe.calls == 3
    _assert_sanitized_probe_internal_error(outcome)
    assert not isinstance(outcome, bytes)
    assert {"figure", "canvas", "axes", "buffer", "plot"} <= set(events)
    assert "encode" not in events
    assert "getvalue" not in events
    assert getattr(buffers[0], "size_at_close") == 0
    _assert_resources_released(buffers, references)

    succeeded = render_explicit_png(plan, sampled)
    assert isinstance(succeeded, bytes)
    assert len(buffers) == 2
    _assert_resources_released(buffers, references)


@pytest.mark.parametrize(
    "failure_point",
    ["figure", "canvas", "axes", "plot", "legend", "encode"],
)
def test_rendering_failures_are_recoverable_and_release_partial_resources(
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
) -> None:
    plan = _plan(show_legend=True)
    sampled = _sample(plan)
    events: list[str] = []
    buffers: list[BytesIO] = []
    references: dict[str, list[weakref.ReferenceType[object]]] = {
        "figure": [],
        "canvas": [],
        "axes": [],
    }

    def fail(*args: object, **kwargs: object) -> object:
        raise RuntimeError("secret rendering failure detail")

    if failure_point == "figure":
        monkeypatch.setattr(renderer, "Figure", fail)
        monkeypatch.setattr(renderer, "FigureCanvasAgg", _forbid_resource)
        monkeypatch.setattr(renderer, "BytesIO", _forbid_resource)
    else:
        events, buffers, references = _track_render_resources(monkeypatch)
        if failure_point == "canvas":
            monkeypatch.setattr(renderer, "FigureCanvasAgg", fail)
        elif failure_point == "axes":
            monkeypatch.setattr(renderer.Figure, "add_subplot", fail)
        elif failure_point == "plot":
            monkeypatch.setattr(Axes, "plot", fail)
        elif failure_point == "legend":
            monkeypatch.setattr(Axes, "legend", fail)
        else:
            monkeypatch.setattr(renderer.FigureCanvasAgg, "print_png", fail)

    outcome = render_explicit_png(plan, sampled)

    assert isinstance(outcome, ErrorInfo)
    assert outcome.code is ErrorCode.RENDER_FAILED
    assert outcome.recoverable is True
    assert outcome.technical_message is not None
    assert "RuntimeError" in outcome.technical_message
    assert "secret" not in outcome.technical_message
    _assert_resources_released(buffers, references)


@pytest.mark.parametrize("operation", ["write", "read", "getvalue"])
def test_bytesio_failures_are_render_failures_and_close_the_buffer(
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    plan = _plan()
    events, buffers, references = _track_render_resources(monkeypatch)
    tracked_buffer_type = renderer.BytesIO

    class FailingBytesIO(tracked_buffer_type):
        def write(self, data: object) -> int:
            if operation == "write":
                raise OSError("secret buffer write detail")
            return super().write(data)

        def read(self, size: int = -1) -> bytes:
            if operation == "read":
                raise OSError("secret buffer read detail")
            return super().read(size)

        def getvalue(self) -> bytes:
            if operation == "getvalue":
                raise OSError("secret buffer copy detail")
            return super().getvalue()

    monkeypatch.setattr(renderer, "BytesIO", FailingBytesIO)

    outcome = render_explicit_png(plan, _sample(plan))

    assert isinstance(outcome, ErrorInfo)
    assert outcome.code is ErrorCode.RENDER_FAILED
    assert outcome.recoverable is True
    assert outcome.technical_message is not None
    assert "OSError" in outcome.technical_message
    assert "secret" not in outcome.technical_message
    _assert_resources_released(buffers, references)


def test_png_copy_memory_error_is_recoverable_and_releases_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan()
    events, buffers, references = _track_render_resources(monkeypatch)
    tracked_buffer_type = renderer.BytesIO

    class MemoryFailingBytesIO(tracked_buffer_type):
        def getvalue(self) -> bytes:
            raise MemoryError("secret PNG copy detail")

    monkeypatch.setattr(renderer, "BytesIO", MemoryFailingBytesIO)

    outcome = render_explicit_png(plan, _sample(plan))

    assert isinstance(outcome, ErrorInfo)
    assert outcome.code is ErrorCode.RESOURCE_LIMIT_EXCEEDED
    assert outcome.recoverable is True
    assert outcome.technical_message is not None
    assert "MemoryError" in outcome.technical_message
    assert "secret" not in outcome.technical_message
    _assert_resources_released(buffers, references)


@pytest.mark.parametrize(
    ("image_width", "image_height", "dpi"),
    [
        (320, 240, 72),
        (640, 480, 96),
        (777, 333, 144),
        (421, 287, 300),
    ],
)
def test_ihdr_matches_every_approved_output_geometry(
    image_width: int,
    image_height: int,
    dpi: int,
) -> None:
    plan = _plan(
        image_width=image_width,
        image_height=image_height,
        dpi=dpi,
    )

    outcome = render_explicit_png(plan, _sample(plan))

    assert isinstance(outcome, bytes)
    assert outcome[:8] == b"\x89PNG\r\n\x1a\n"
    assert outcome[12:16] == b"IHDR"
    assert int.from_bytes(outcome[16:20], "big") == image_width
    assert int.from_bytes(outcome[20:24], "big") == image_height


@pytest.mark.parametrize("data_scale", [0.05, 20.0])
def test_sampled_data_cannot_autoscale_beyond_approved_viewport(
    monkeypatch: pytest.MonkeyPatch,
    data_scale: float,
) -> None:
    plan = _plan(
        f"{data_scale}*x",
        x_bounds=(-5, 5),
        y_bounds=(-7, 7),
    )
    sampled = _sample(plan)
    captured = _capture_rendered_axes(monkeypatch)

    outcome = render_explicit_png(plan, sampled)

    assert isinstance(outcome, bytes)
    axes = captured[0]
    assert axes.get_autoscale_on() is False
    assert axes.get_xlim() == pytest.approx((-5.0, 5.0))
    assert axes.get_ylim() == pytest.approx((-7.0, 7.0))


def test_visually_disjoint_segments_create_independent_line_artists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan(
        "1/x",
        x_bounds=(-1, 1),
        y_bounds=(-10, 10),
        image_width=800,
    )
    sampled = _sample(plan)
    assert sampled.segment_ranges.shape == (2, 2)
    left_stop = int(sampled.segment_ranges[0, 1])
    right_start = int(sampled.segment_ranges[1, 0])
    assert left_stop == right_start
    captured = _capture_rendered_axes(monkeypatch)

    outcome = render_explicit_png(plan, sampled)

    assert isinstance(outcome, bytes)
    axes = captured[0]
    assert len(axes.lines) == 2
    assert max(axes.lines[0].get_xdata()) < 0.0
    assert min(axes.lines[1].get_xdata()) > 0.0
    assert axes.lines[0].get_xdata()[-1] == sampled.x[left_stop - 1]
    assert axes.lines[1].get_xdata()[0] == sampled.x[right_start]


def test_labels_and_fixed_layout_margins_survive_without_tight_bbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan(image_width=613, image_height=347, dpi=144)
    captured: list[tuple[str, str, float, float, float, float]] = []
    configure_axes = renderer._configure_axes

    def capture_layout(axes: object, approved_plan: RenderPlan) -> None:
        configure_axes(axes, approved_plan)
        subplot_parameters = axes.get_figure().subplotpars
        captured.append(
            (
                axes.get_xlabel(),
                axes.get_ylabel(),
                subplot_parameters.left,
                subplot_parameters.right,
                subplot_parameters.bottom,
                subplot_parameters.top,
            ),
        )

    monkeypatch.setattr(renderer, "_configure_axes", capture_layout)

    outcome = render_explicit_png(plan, _sample(plan))

    assert isinstance(outcome, bytes)
    assert int.from_bytes(outcome[16:20], "big") == 613
    assert int.from_bytes(outcome[20:24], "big") == 347
    assert captured == [
        (
            "x",
            "y",
            pytest.approx(0.12),
            pytest.approx(0.94),
            pytest.approx(0.12),
            pytest.approx(0.94),
        ),
    ]


def test_hostile_savefig_bbox_cannot_crop_the_approved_canvas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan(image_width=613, image_height=347, dpi=144)
    sampled = _sample(plan)
    modules_before_backend_query = _tracked_backend_modules()
    backend_before = matplotlib.get_backend(auto_select=False)
    modules_before = _tracked_backend_modules()
    assert modules_before == modules_before_backend_query
    bbox_before = matplotlib.rcParams["savefig.bbox"]
    pad_before = matplotlib.rcParams["savefig.pad_inches"]

    def forbidden_print_figure(*args: object, **kwargs: object) -> object:
        raise AssertionError("direct Agg PNG output must not use print_figure")

    monkeypatch.setattr(
        renderer.FigureCanvasAgg,
        "print_figure",
        forbidden_print_figure,
    )
    with matplotlib.rc_context():
        matplotlib.rcParams["savefig.bbox"] = "tight"
        matplotlib.rcParams["savefig.pad_inches"] = 3.75
        assert _tracked_backend_modules() == modules_before
        assert matplotlib.get_backend(auto_select=False) == backend_before
        assert _tracked_backend_modules() == modules_before
        hostile_before = {
            "savefig.bbox": matplotlib.rcParams["savefig.bbox"],
            "savefig.pad_inches": matplotlib.rcParams["savefig.pad_inches"],
        }

        outcome = render_explicit_png(plan, sampled)

        assert isinstance(outcome, bytes)
        assert outcome[12:16] == b"IHDR"
        assert int.from_bytes(outcome[16:20], "big") == 613
        assert int.from_bytes(outcome[20:24], "big") == 347
        assert {
            "savefig.bbox": matplotlib.rcParams["savefig.bbox"],
            "savefig.pad_inches": matplotlib.rcParams["savefig.pad_inches"],
        } == hostile_before
        assert matplotlib.get_backend(auto_select=False) == backend_before
        assert _tracked_backend_modules() == modules_before

    assert matplotlib.rcParams["savefig.bbox"] == bbox_before
    assert matplotlib.rcParams["savefig.pad_inches"] == pad_before
    assert matplotlib.get_backend(auto_select=False) == backend_before
    assert _tracked_backend_modules() == modules_before


def test_fresh_process_renderer_does_not_select_backend_or_import_gui_modules() -> None:
    child_source = textwrap.dedent(
        """
        import json
        import sys

        try:
            import matplotlib

            def tracked_modules():
                return sorted(
                    name
                    for name in sys.modules
                    if name == "matplotlib.pyplot"
                    or name == "PySide6"
                    or name.startswith("PySide6.")
                )

            modules_before_query = tracked_modules()
            backend_before = matplotlib.get_backend(auto_select=False)
            modules_after_query = tracked_modules()

            from math_drawing_assistant.config import DEFAULT_LIMITS
            from math_drawing_assistant.engine import (
                RenderPlanBuilder,
                SampledExplicitFunction,
                analyze_explicit_function,
                build_explicit_scene_spec,
                render_explicit_png,
                renderer,
                sample_explicit_function,
            )
            from math_drawing_assistant.models import (
                ResolvedAspect,
                InputSource,
                PlotItemRequest,
                PlotKind,
                RenderPlan,
                ResolvedViewport,
                ValidatedExplicitExpression,
                ViewportSource,
            )

            backend_after_import = matplotlib.get_backend(auto_select=False)
            modules_after_import = tracked_modules()

            validated = analyze_explicit_function("x")
            assert isinstance(validated, ValidatedExplicitExpression)
            request = PlotItemRequest(
                item_id="fresh-process-item",
                input_text="x",
                input_source=InputSource.MANUAL,
                requested_plot_kind=PlotKind.EXPLICIT_FUNCTION,
                display_order=0,
            )
            scene = build_explicit_scene_spec(request, validated)
            viewport = ResolvedViewport(
                x_min=-10,
                x_max=10,
                y_min=-10,
                y_max=10,
                aspect=ResolvedAspect.AUTO,
                source=ViewportSource.MANUAL,
            )
            plan = RenderPlanBuilder(limits=DEFAULT_LIMITS).build(
                scene,
                viewport,
                image_width=613,
                image_height=347,
                dpi=144,
                show_grid=True,
                show_legend=False,
            )
            assert isinstance(plan, RenderPlan)
            sampled = sample_explicit_function(plan)
            assert isinstance(sampled, SampledExplicitFunction)

            with matplotlib.rc_context():
                matplotlib.rcParams["savefig.bbox"] = "tight"
                png = render_explicit_png(plan, sampled)
                assert isinstance(png, bytes)
                backend_after_render = matplotlib.get_backend(auto_select=False)
                modules_after_render = tracked_modules()

            backend_after_context = matplotlib.get_backend(auto_select=False)
            modules_after_context = tracked_modules()
            dimensions = [
                int.from_bytes(png[16:20], "big"),
                int.from_bytes(png[20:24], "big"),
            ]
            print(
                json.dumps(
                    {
                        "ok": True,
                        "backends": [
                            backend_before,
                            backend_after_import,
                            backend_after_render,
                            backend_after_context,
                        ],
                        "modules": [
                            modules_before_query,
                            modules_after_query,
                            modules_after_import,
                            modules_after_render,
                            modules_after_context,
                        ],
                        "dimensions": dimensions,
                    },
                    sort_keys=True,
                ),
            )
        except BaseException as exc:
            print(json.dumps({"ok": False, "error": type(exc).__name__}))
            raise SystemExit(1)
        """,
    )
    project_root = Path(__file__).resolve().parents[2]
    config_parent = os.environ.get("MPLCONFIGDIR")
    config_dir = tempfile.mkdtemp(
        prefix="mda-stage9-fresh-backend-",
        dir=config_parent,
    )
    try:
        environment = os.environ.copy()
        environment["MPLCONFIGDIR"] = config_dir
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["PYTHONPATH"] = str(project_root)
        environment.pop("MPLBACKEND", None)
        completed = subprocess.run(
            [sys.executable, "-c", child_source],
            cwd=project_root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    finally:
        try:
            shutil.rmtree(config_dir)
        except OSError:
            # The validated outer MPLCONFIGDIR cleanup is the sandbox fallback.
            pass

    try:
        payload = json.loads(completed.stdout.strip())
    except json.JSONDecodeError:
        pytest.fail("fresh renderer isolation subprocess returned invalid diagnostics")
    assert completed.returncode == 0, (
        "fresh renderer isolation subprocess failed: "
        f"{payload.get('error', 'unknown')}"
    )
    assert payload["ok"] is True
    assert payload["backends"] == [None, None, None, None]
    assert payload["modules"] == [[], [], [], [], []]
    assert payload["dimensions"] == [613, 347]


def test_owned_png_survives_closed_buffer_and_has_no_matplotlib_references(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan()
    events, buffers, references = _track_render_resources(monkeypatch)

    outcome = render_explicit_png(plan, _sample(plan))

    assert type(outcome) is bytes
    assert memoryview(outcome).readonly is True
    assert outcome[:8] == b"\x89PNG\r\n\x1a\n"
    assert buffers[0].closed is True
    assert getattr(buffers[0], "size_at_close") == len(outcome)
    assert events.count("getvalue") == 1
    _assert_resources_released(buffers, references)


def test_renderer_does_not_retain_sample_arrays_or_matplotlib_instances() -> None:
    plan = _plan()
    sampled = _sample(plan)

    outcome = render_explicit_png(plan, sampled)

    assert isinstance(outcome, bytes)
    module_values = tuple(vars(renderer).values())
    assert not any(isinstance(value, np.ndarray) for value in module_values)
    assert not any(
        isinstance(value, renderer.FigureCanvasAgg)
        for value in module_values
        if not isinstance(value, type)
    )
    assert not any(isinstance(value, Axes) for value in module_values)
    assert not any(
        isinstance(value, renderer.Figure)
        for value in module_values
        if not isinstance(value, type)
    )
    for value in module_values:
        if isinstance(value, dict):
            contents = (*value.keys(), *value.values())
        elif isinstance(value, (list, set, tuple)):
            contents = tuple(value)
        else:
            continue
        for array in (sampled.x, sampled.y, sampled.segment_ranges):
            assert all(item is not array for item in contents)


def test_bounded_repeated_rendering_has_no_manager_or_object_retention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan(image_width=320, image_height=240, dpi=72)
    sampled = _sample(plan)
    events, buffers, references = _track_render_resources(monkeypatch)
    dimensions: set[tuple[int, int]] = set()
    manager_creations = 0
    manager_init = FigureManagerBase.__init__

    def track_manager_creation(
        manager: FigureManagerBase,
        *args: object,
        **kwargs: object,
    ) -> None:
        nonlocal manager_creations
        manager_creations += 1
        manager_init(manager, *args, **kwargs)

    monkeypatch.setattr(FigureManagerBase, "__init__", track_manager_creation)

    for _ in range(20):
        outcome = render_explicit_png(plan, sampled)
        assert isinstance(outcome, bytes)
        dimensions.add(
            (
                int.from_bytes(outcome[16:20], "big"),
                int.from_bytes(outcome[20:24], "big"),
            ),
        )

    assert dimensions == {(320, 240)}
    assert len(buffers) == 20
    assert events.count("encode") == 20
    assert manager_creations == 0
    _assert_resources_released(buffers, references)


# --- Stage 15A additions: unified sampled-curve renderer entry ----------------
#
# The additions below are append-only; every pre-Stage-15A assertion above is
# unchanged and must keep passing against the shared implementation core.


GEOMETRY_REJECTION_TEXTS = (
    "2*x-y+3=0",
    "x^2+y^2=25",
    "x^2/9+y^2/4=1",
    "x^2/9-y^2/4=1",
    "x^2=4*y",
)


def _geometry_plan_and_sampled(
    text: str,
    *,
    item_id: str,
) -> tuple[RenderPlan, object]:
    from math_drawing_assistant.engine import (
        analyze_plot_item,
        resolve_single_item_viewport,
        sample_parameterized_curve,
    )
    from math_drawing_assistant.models import PlotSceneSpec, ViewportRequest

    spec = analyze_plot_item(
        PlotItemRequest(
            item_id=item_id,
            input_text=text,
            input_source=InputSource.MANUAL,
            requested_plot_kind=PlotKind.AUTO,
            display_order=0,
        )
    )
    assert not isinstance(spec, ErrorInfo), spec
    scene = PlotSceneSpec(items=(spec,))
    resolution = resolve_single_item_viewport(scene, ViewportRequest())
    assert resolution.error is None, resolution.error
    assert resolution.viewport is not None
    plan = RenderPlanBuilder().build(
        scene,
        resolution.viewport,
        image_width=800,
        image_height=600,
        dpi=96,
        show_grid=True,
        show_legend=False,
    )
    assert type(plan) is RenderPlan, plan
    sampled = sample_parameterized_curve(plan)
    assert not isinstance(sampled, ErrorInfo), sampled
    return plan, sampled


def test_unified_entry_pins_the_public_signature() -> None:
    from math_drawing_assistant.engine import render_sampled_curve_png

    signature = inspect.signature(render_sampled_curve_png)

    assert tuple(signature.parameters) == (
        "plan",
        "sampling_outcome",
        "cancellation_probe",
    )
    assert signature.parameters["cancellation_probe"].kind is inspect.Parameter.KEYWORD_ONLY
    assert set(get_args(RenderOutcome)) == {bytes, RenderCancelled, ErrorInfo}


def test_unified_entry_renders_the_existing_explicit_pipeline() -> None:
    from math_drawing_assistant.engine import render_sampled_curve_png

    plan = _plan(image_width=613, image_height=347, dpi=144)

    outcome = render_sampled_curve_png(plan, _sample(plan))

    assert isinstance(outcome, bytes)
    assert outcome[12:16] == b"IHDR"
    assert int.from_bytes(outcome[16:20], "big") == 613
    assert int.from_bytes(outcome[20:24], "big") == 347


@pytest.mark.parametrize("text", GEOMETRY_REJECTION_TEXTS)
def test_explicit_entry_rejects_geometry_results_before_any_resource(
    text: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, sampled = _geometry_plan_and_sampled(
        text,
        item_id="stage15a-old-contract",
    )
    events, buffers, references = _track_render_resources(monkeypatch)

    outcome = render_explicit_png(plan, sampled)

    assert isinstance(outcome, ErrorInfo)
    assert outcome.code is ErrorCode.INTERNAL_ERROR
    assert outcome.recoverable is False
    assert outcome.technical_message == "approved render-plan item contract failed"
    assert events == []
    assert buffers == []

    explicit_plan = _plan("x", item_id="stage15a-old-explicit")
    mismatched = render_explicit_png(explicit_plan, sampled)

    assert isinstance(mismatched, ErrorInfo)
    assert mismatched.code is ErrorCode.INTERNAL_ERROR
    assert mismatched.recoverable is False
    assert mismatched.technical_message == "sampling outcome type mismatch"
    assert events == []
    assert buffers == []
