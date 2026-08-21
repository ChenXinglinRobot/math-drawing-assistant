"""Stage 15A acceptance matrix for the unified sampled-curve renderer.

The local five-step chain (analyze → scene → viewport → Builder → sampler)
replicates the Stage 14E production boundaries; nothing here bypasses an
approved plan or receipt.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import gc
import weakref

import numpy as np
import pytest
from matplotlib.axes import Axes

from math_drawing_assistant.config import ApplicationLimits, DEFAULT_LIMITS
from math_drawing_assistant.engine import (
    RenderCancelled,
    RenderPlanBuilder,
    SampledExplicitFunction,
    SampledParameterizedCurve,
    SamplingCancelled,
    analyze_plot_item,
    render_explicit_png,
    render_sampled_curve_png,
    resolve_single_item_viewport,
    sample_explicit_function,
    sample_parameterized_curve,
)
from math_drawing_assistant.engine import renderer
from math_drawing_assistant.engine.samplers import (
    ParameterizedSamplingDiagnostics,
    SampledSegmentMetadata,
)
from math_drawing_assistant.models import (
    ErrorCode,
    ErrorInfo,
    ExplicitFunctionSpec,
    GeometryRenderItemPlan,
    InputSource,
    ParameterizedRenderMemoryBudget,
    PlotItemRequest,
    PlotKind,
    PlotSceneSpec,
    RenderPlan,
    ResolvedAspect,
    SegmentClosure,
    ViewportMode,
    ViewportRequest,
)

GEOMETRY_CASES = (
    ("line", "2*x-y+3=0"),
    ("circle", "x^2+y^2=25"),
    ("ellipse", "x^2/9+y^2/4=1"),
    ("hyperbola", "x^2/9-y^2/4=1"),
    ("parabola", "x^2=4*y"),
)
GEOMETRY_CASE_IDS = [name for name, _ in GEOMETRY_CASES]

# BC-15A-01: the two-point closing chord carries four float64 values.
_CHORD_DATA_BYTES = 32


@dataclass(frozen=True, slots=True)
class _Artifacts:
    spec: object
    plan: RenderPlan
    sampled: SampledParameterizedCurve


def _request(text: str, *, item_id: str) -> PlotItemRequest:
    return PlotItemRequest(
        item_id=item_id,
        input_text=text,
        input_source=InputSource.MANUAL,
        requested_plot_kind=PlotKind.AUTO,
        display_order=0,
    )


def _manual(
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
) -> ViewportRequest:
    return ViewportRequest(
        mode=ViewportMode.MANUAL,
        x_min=x_min,
        x_max=x_max,
        y_min=y_min,
        y_max=y_max,
    )


def _artifacts(
    text: str,
    *,
    item_id: str,
    viewport_request: ViewportRequest | None = None,
    show_legend: bool = False,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> _Artifacts:
    spec = analyze_plot_item(_request(text, item_id=item_id))
    assert not isinstance(spec, ErrorInfo), spec
    scene = PlotSceneSpec(items=(spec,))
    resolution = resolve_single_item_viewport(
        scene,
        viewport_request or ViewportRequest(),
    )
    assert resolution.error is None, resolution.error
    assert resolution.viewport is not None
    plan = RenderPlanBuilder(limits=limits).build(
        scene,
        resolution.viewport,
        image_width=800,
        image_height=600,
        dpi=96,
        show_grid=True,
        show_legend=show_legend,
    )
    assert type(plan) is RenderPlan, plan
    sampled = sample_parameterized_curve(plan)
    assert type(sampled) is SampledParameterizedCurve, sampled
    return _Artifacts(spec, plan, sampled)


def _explicit_artifacts(
    *,
    item_id: str = "stage15a-explicit",
) -> tuple[RenderPlan, SampledExplicitFunction]:
    spec = analyze_plot_item(_request("y=x^2", item_id=item_id))
    assert type(spec) is ExplicitFunctionSpec, spec
    scene = PlotSceneSpec(items=(spec,))
    resolution = resolve_single_item_viewport(
        scene,
        _manual(-10.0, 10.0, -10.0, 10.0),
    )
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
    sampled = sample_explicit_function(plan)
    assert type(sampled) is SampledExplicitFunction, sampled
    return plan, sampled


class _CancelOnCall:
    def __init__(self, call_number: int) -> None:
        self.call_number = call_number
        self.calls = 0

    def is_cancelled(self) -> bool:
        self.calls += 1
        return self.calls == self.call_number


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


def _line_data(line: object) -> tuple[np.ndarray, np.ndarray]:
    return (
        np.asarray(line.get_xdata(), dtype=np.float64),
        np.asarray(line.get_ydata(), dtype=np.float64),
    )


# --- Matrix 1: all six exact types render through the unified entry ----------


@pytest.mark.parametrize(("name", "text"), GEOMETRY_CASES, ids=GEOMETRY_CASE_IDS)
def test_all_geometry_types_render_to_png_with_exact_ihdr(name: str, text: str) -> None:
    artifacts = _artifacts(text, item_id=f"stage15a-{name}")
    plan = artifacts.plan
    budget = plan.memory_budget
    assert isinstance(budget, ParameterizedRenderMemoryBudget)

    outcome = render_sampled_curve_png(plan, artifacts.sampled)

    assert isinstance(outcome, bytes)
    assert outcome[:8] == b"\x89PNG\r\n\x1a\n"
    assert outcome[12:16] == b"IHDR"
    assert int.from_bytes(outcome[16:20], "big") == plan.image_width
    assert int.from_bytes(outcome[20:24], "big") == plan.image_height
    assert len(outcome) <= min(
        budget.png_buffer_reserve_bytes,
        budget.png_copy_bytes,
    )


@pytest.mark.parametrize(("name", "text"), GEOMETRY_CASES, ids=GEOMETRY_CASE_IDS)
def test_bc_15a_01_chord_bytes_stay_inside_validation_workspace_budget(
    name: str,
    text: str,
) -> None:
    """BC-15A-01: 32-byte chord data reuses the dead sampler validation phase."""

    artifacts = _artifacts(text, item_id=f"stage15a-budget-{name}")
    budget = artifacts.plan.memory_budget
    assert isinstance(budget, ParameterizedRenderMemoryBudget)

    assert _CHORD_DATA_BYTES <= budget.validation_workspace_bytes


def test_unified_entry_still_renders_the_explicit_pipeline() -> None:
    plan, sampled = _explicit_artifacts()

    outcome = render_sampled_curve_png(plan, sampled)

    assert isinstance(outcome, bytes)
    assert outcome[12:16] == b"IHDR"
    assert int.from_bytes(outcome[16:20], "big") == 800
    assert int.from_bytes(outcome[20:24], "big") == 600


@pytest.mark.parametrize(("name", "text"), GEOMETRY_CASES, ids=GEOMETRY_CASE_IDS)
def test_explicit_entry_keeps_rejecting_every_geometry_result(
    name: str,
    text: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifacts = _artifacts(text, item_id=f"stage15a-old-{name}")
    events, buffers, _references = _track_render_resources(monkeypatch)

    outcome = render_explicit_png(artifacts.plan, artifacts.sampled)

    assert isinstance(outcome, ErrorInfo)
    assert outcome.code is ErrorCode.INTERNAL_ERROR
    assert outcome.recoverable is False
    assert outcome.technical_message == "approved render-plan item contract failed"
    assert events == []
    assert buffers == []


# --- Matrix 2: per-segment artists never bridge ranges -----------------------


def test_hyperbola_two_branches_draw_two_independent_artists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifacts = _artifacts(
        "x^2/9-y^2/4=1",
        item_id="stage15a-hb-two",
        viewport_request=_manual(-10.0, 10.0, -8.0, 8.0),
    )
    sampled = artifacts.sampled
    assert sampled.segment_ranges.shape == (2, 2)
    assert all(
        metadata.closure is SegmentClosure.OPEN
        for metadata in sampled.segment_metadata
    )
    captured = _capture_rendered_axes(monkeypatch)

    outcome = render_sampled_curve_png(artifacts.plan, sampled)

    assert isinstance(outcome, bytes)
    axes = captured[0]
    assert len(axes.lines) == 2
    for line, (start, stop) in zip(
        axes.lines,
        sampled.segment_ranges.tolist(),
    ):
        line_x, line_y = _line_data(line)
        assert line_x.shape[0] == stop - start
        np.testing.assert_array_equal(line_x, sampled.x[start:stop])
        np.testing.assert_array_equal(line_y, sampled.y[start:stop])
    center_x = float(artifacts.spec.center_x)  # type: ignore[attr-defined]
    left_x, _ = _line_data(axes.lines[0])
    right_x, _ = _line_data(axes.lines[1])
    assert max(left_x) < center_x < min(right_x)


def test_parabola_two_intervals_draw_independent_artists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifacts = _artifacts(
        "x^2=4*y",
        item_id="stage15a-pb-two",
        viewport_request=_manual(-10.0, 10.0, 1.0, 4.0),
    )
    sampled = artifacts.sampled
    assert sampled.segment_ranges.shape == (2, 2)
    captured = _capture_rendered_axes(monkeypatch)

    outcome = render_sampled_curve_png(artifacts.plan, sampled)

    assert isinstance(outcome, bytes)
    axes = captured[0]
    assert len(axes.lines) == 2
    for line, (start, stop) in zip(
        axes.lines,
        sampled.segment_ranges.tolist(),
    ):
        line_x, line_y = _line_data(line)
        assert line_x.shape[0] == stop - start
        np.testing.assert_array_equal(line_x, sampled.x[start:stop])
        np.testing.assert_array_equal(line_y, sampled.y[start:stop])


def test_partial_circle_four_arcs_never_connect_across_ranges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifacts = _artifacts(
        "x^2+y^2=25",
        item_id="stage15a-arc-four",
        viewport_request=_manual(-4.0, 4.0, -4.0, 4.0),
    )
    sampled = artifacts.sampled
    assert sampled.segment_ranges.shape == (4, 2)
    assert all(
        metadata.closure is SegmentClosure.OPEN
        for metadata in sampled.segment_metadata
    )
    captured = _capture_rendered_axes(monkeypatch)

    outcome = render_sampled_curve_png(artifacts.plan, sampled)

    assert isinstance(outcome, bytes)
    axes = captured[0]
    assert len(axes.lines) == 4
    for line, (start, stop) in zip(
        axes.lines,
        sampled.segment_ranges.tolist(),
    ):
        line_x, line_y = _line_data(line)
        assert line_x.shape[0] == stop - start
        np.testing.assert_array_equal(line_x, sampled.x[start:stop])
        np.testing.assert_array_equal(line_y, sampled.y[start:stop])


# --- Matrix 3: CLOSED visual closure via one two-point chord artist ----------


@pytest.mark.parametrize(
    "text",
    ("x^2+y^2=25", "x^2/9+y^2/4=1"),
    ids=["circle", "ellipse"],
)
def test_closed_oval_renders_main_points_plus_exact_chord(
    text: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifacts = _artifacts(text, item_id="stage15a-closed")
    sampled = artifacts.sampled
    assert sampled.segment_ranges.shape == (1, 2)
    assert all(
        metadata.closure is SegmentClosure.CLOSED
        for metadata in sampled.segment_metadata
    )
    captured = _capture_rendered_axes(monkeypatch)

    outcome = render_sampled_curve_png(artifacts.plan, sampled)

    assert isinstance(outcome, bytes)
    axes = captured[0]
    assert len(axes.lines) == 2
    main, chord = axes.lines
    start, stop = (int(value) for value in sampled.segment_ranges[0])

    main_x, main_y = _line_data(main)
    assert main_x.shape[0] == stop - start
    np.testing.assert_array_equal(main_x, sampled.x[start:stop])
    np.testing.assert_array_equal(main_y, sampled.y[start:stop])

    chord_x, chord_y = _line_data(chord)
    assert chord_x.shape == (2,)
    assert chord_y.shape == (2,)
    np.testing.assert_array_equal(
        chord_x,
        np.asarray(
            [sampled.x[stop - 1], sampled.x[start]],
            dtype=np.float64,
        ),
    )
    np.testing.assert_array_equal(
        chord_y,
        np.asarray(
            [sampled.y[stop - 1], sampled.y[start]],
            dtype=np.float64,
        ),
    )
    assert chord.get_color() == main.get_color()
    assert chord.get_linewidth() == main.get_linewidth()
    assert chord.get_label().startswith("_")
    assert chord_x.nbytes + chord_y.nbytes == _CHORD_DATA_BYTES

    assert sampled.x.flags.writeable is False
    assert sampled.y.flags.writeable is False
    assert sampled.segment_ranges.flags.writeable is False


@pytest.mark.parametrize(
    ("name", "text", "clip_viewport"),
    (
        ("line", "2*x-y+3=0", False),
        ("hyperbola", "x^2/9-y^2/4=1", True),
        ("parabola", "x^2=4*y", False),
        ("partial-arc", "x^2+y^2=25", True),
    ),
    ids=["line", "hyperbola", "parabola", "partial-arc"],
)
def test_open_segments_never_get_a_closing_chord(
    name: str,
    text: str,
    clip_viewport: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if name == "hyperbola":
        viewport_request: ViewportRequest | None = _manual(
            -10.0,
            10.0,
            -8.0,
            8.0,
        )
    elif name == "partial-arc":
        viewport_request = _manual(-4.0, 4.0, -4.0, 4.0)
    else:
        viewport_request = None
    assert clip_viewport is (viewport_request is not None)
    artifacts = _artifacts(
        text,
        item_id=f"stage15a-open-{name}",
        viewport_request=viewport_request,
    )
    sampled = artifacts.sampled
    assert all(
        metadata.closure is SegmentClosure.OPEN
        for metadata in sampled.segment_metadata
    )
    captured = _capture_rendered_axes(monkeypatch)

    outcome = render_sampled_curve_png(artifacts.plan, sampled)

    assert isinstance(outcome, bytes)
    axes = captured[0]
    assert len(axes.lines) == sampled.segment_ranges.shape[0]
    for line, (start, stop) in zip(
        axes.lines,
        sampled.segment_ranges.tolist(),
    ):
        line_x, _ = _line_data(line)
        assert line_x.shape[0] == stop - start


# --- Matrix 4: legend from provenance ----------------------------------------


def test_closed_circle_legend_uses_provenance_and_chord_adds_no_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifacts = _artifacts(
        "x^2+y^2=25",
        item_id="stage15a-legend",
        show_legend=True,
    )
    captured = _capture_rendered_axes(monkeypatch)

    outcome = render_sampled_curve_png(artifacts.plan, artifacts.sampled)

    assert isinstance(outcome, bytes)
    axes = captured[0]
    assert len(axes.lines) == 2
    legend = axes.get_legend()
    assert legend is not None
    assert [text.get_text() for text in legend.get_texts()] == [
        artifacts.spec.provenance.normalized_input,  # type: ignore[attr-defined]
    ]


def test_hyperbola_two_branches_have_one_legend_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifacts = _artifacts(
        "x^2/9-y^2/4=1",
        item_id="stage15a-legend-hb",
        viewport_request=_manual(-10.0, 10.0, -8.0, 8.0),
        show_legend=True,
    )
    captured = _capture_rendered_axes(monkeypatch)

    outcome = render_sampled_curve_png(artifacts.plan, artifacts.sampled)

    assert isinstance(outcome, bytes)
    axes = captured[0]
    assert len(axes.lines) == 2
    legend = axes.get_legend()
    assert legend is not None
    assert [text.get_text() for text in legend.get_texts()] == [
        artifacts.spec.provenance.normalized_input,  # type: ignore[attr-defined]
    ]


def test_no_legend_without_the_plan_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    artifacts = _artifacts("x^2+y^2=25", item_id="stage15a-no-legend")
    captured = _capture_rendered_axes(monkeypatch)

    outcome = render_sampled_curve_png(artifacts.plan, artifacts.sampled)

    assert isinstance(outcome, bytes)
    assert captured[0].get_legend() is None


# --- Matrix 5: fixed aspect and viewport -------------------------------------


def test_circle_keeps_equal_aspect_and_undrifted_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifacts = _artifacts("x^2+y^2=25", item_id="stage15a-aspect")
    assert artifacts.plan.resolved_viewport.aspect is ResolvedAspect.EQUAL
    captured = _capture_rendered_axes(monkeypatch)

    outcome = render_sampled_curve_png(artifacts.plan, artifacts.sampled)

    assert isinstance(outcome, bytes)
    axes = captured[0]
    viewport = artifacts.plan.resolved_viewport
    assert axes.get_autoscale_on() is False
    assert axes.get_aspect() == 1.0
    assert axes.get_adjustable() == "box"
    assert axes.get_xlim() == pytest.approx((viewport.x_min, viewport.x_max))
    assert axes.get_ylim() == pytest.approx((viewport.y_min, viewport.y_max))


# --- Matrix 6: cancellation across every geometry checkpoint -----------------


@pytest.mark.parametrize(
    ("call_number", "expected_plots", "expect_encode", "expect_getvalue"),
    (
        (1, 0, False, False),
        (2, 0, False, False),
        (3, 1, False, False),
        (4, 2, False, False),
        (5, 2, True, False),
        (6, 2, True, True),
    ),
    ids=[
        "pre-resource",
        "pre-first-segment",
        "between-segments",
        "pre-encoding",
        "post-encoding",
        "pre-return",
    ],
)
def test_geometry_cancellation_matrix_releases_all_resources(
    monkeypatch: pytest.MonkeyPatch,
    call_number: int,
    expected_plots: int,
    expect_encode: bool,
    expect_getvalue: bool,
) -> None:
    artifacts = _artifacts(
        "x^2/9-y^2/4=1",
        item_id="stage15a-cancel",
        viewport_request=_manual(-10.0, 10.0, -8.0, 8.0),
    )
    assert artifacts.sampled.segment_ranges.shape == (2, 2)
    events, buffers, references = _track_render_resources(monkeypatch)

    outcome = render_sampled_curve_png(
        artifacts.plan,
        artifacts.sampled,
        cancellation_probe=_CancelOnCall(call_number),
    )

    assert outcome == RenderCancelled(artifacts.sampled.item_id)
    assert events.count("plot") == expected_plots
    assert ("encode" in events) is expect_encode
    assert ("getvalue" in events) is expect_getvalue
    assert ("figure" in events) is (call_number >= 2)
    _assert_resources_released(buffers, references)


# --- Matrix 7: validation and error contract ---------------------------------


def test_tampered_geometry_plan_fails_before_any_resource(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifacts = _artifacts("x^2+y^2=25", item_id="stage15a-tamper")
    receipt = artifacts.plan._approval_receipt
    assert receipt is not None
    # Negative defense: break the private seal and require rejection before
    # any Figure, Canvas, or buffer allocation.
    object.__setattr__(receipt, "_seal", object())
    events, buffers, _references = _track_render_resources(monkeypatch)

    outcome = render_sampled_curve_png(artifacts.plan, artifacts.sampled)

    assert isinstance(outcome, ErrorInfo)
    assert outcome.code is ErrorCode.INTERNAL_ERROR
    assert outcome.recoverable is False
    assert events == []
    assert buffers == []


def test_ordinary_constructed_curve_is_rejected_before_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifacts = _artifacts("x^2+y^2=25", item_id="stage15a-ordinary")
    sampled = artifacts.sampled
    ordinary = SampledParameterizedCurve(
        item_id=sampled.item_id,
        x=sampled.x,
        y=sampled.y,
        segment_ranges=sampled.segment_ranges,
        segment_metadata=sampled.segment_metadata,
        visible_segment_count=sampled.visible_segment_count,
        warnings=sampled.warnings,
        diagnostics=sampled.diagnostics,
    )
    events, buffers, _references = _track_render_resources(monkeypatch)

    outcome = render_sampled_curve_png(artifacts.plan, ordinary)

    assert isinstance(outcome, ErrorInfo)
    assert outcome.code is ErrorCode.INTERNAL_ERROR
    assert outcome.recoverable is False
    assert outcome.technical_message == "sampling outcome type mismatch"
    assert events == []
    assert buffers == []


def test_zero_range_forgery_is_internal_not_no_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifacts = _artifacts("x^2+y^2=25", item_id="stage15a-zero-range")
    sampled = artifacts.sampled
    empty_ranges = np.empty((0, 2), dtype=np.int64)
    empty_ranges.setflags(write=False)
    # Negative defense: an owned read-only (0, 2) array passes the frozen
    # gate and reaches the "at least one segment" dataclass invariant, which
    # rejects it as a contract violation rather than a visibility outcome.
    object.__setattr__(sampled, "segment_ranges", empty_ranges)
    events, buffers, _references = _track_render_resources(monkeypatch)

    outcome = render_sampled_curve_png(artifacts.plan, sampled)

    assert isinstance(outcome, ErrorInfo)
    assert outcome.code is ErrorCode.INTERNAL_ERROR
    assert outcome.recoverable is False
    assert outcome.technical_message == "sampled result contract validation failed"
    assert outcome.code is not ErrorCode.NO_VISIBLE_CURVE
    assert events == []
    assert buffers == []


def test_geometry_sample_count_mismatch_is_internal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifacts = _artifacts("2*x-y+3=0", item_id="stage15a-count")
    sampled = artifacts.sampled
    assert sampled.x.shape[0] == 2
    replacement_x = np.array([0.0, 1.0, 2.0], dtype=np.float64)
    replacement_y = np.array([3.0, 4.0, 5.0], dtype=np.float64)
    replacement_x.setflags(write=False)
    replacement_y.setflags(write=False)
    replacement_ranges = np.empty((1, 2), dtype=np.int64)
    replacement_ranges[0] = (0, 3)
    replacement_ranges.setflags(write=False)
    # Negative defense: corrupt a genuine sampler result consistently so
    # every dataclass invariant still passes but the approved sample count
    # no longer matches the item plan.
    object.__setattr__(sampled, "x", replacement_x)
    object.__setattr__(sampled, "y", replacement_y)
    object.__setattr__(sampled, "segment_ranges", replacement_ranges)
    object.__setattr__(
        sampled,
        "diagnostics",
        ParameterizedSamplingDiagnostics(
            sampled_segment_count=1,
            sampled_point_count=3,
        ),
    )
    events, buffers, _references = _track_render_resources(monkeypatch)

    outcome = render_sampled_curve_png(artifacts.plan, sampled)

    assert isinstance(outcome, ErrorInfo)
    assert outcome.code is ErrorCode.INTERNAL_ERROR
    assert outcome.recoverable is False
    assert outcome.technical_message == "sampled result contract validation failed"
    assert events == []
    assert buffers == []


@pytest.mark.parametrize(
    "tamper_kind",
    (
        "closed-to-open",
        "open-to-closed",
        "non-closure",
        "wrong-branch",
        "negative-branch",
        "shift-segment-boundary",
        "gap-with-final-coverage",
    ),
)
def test_tampered_segment_contract_is_rejected_before_resources(
    monkeypatch: pytest.MonkeyPatch,
    tamper_kind: str,
) -> None:
    if tamper_kind == "closed-to-open":
        artifacts = _artifacts("x^2+y^2=25", item_id="stage15a-closed-open")
        metadata = artifacts.sampled.segment_metadata[0]
        assert metadata.closure is SegmentClosure.CLOSED
        object.__setattr__(metadata, "closure", SegmentClosure.OPEN)
    elif tamper_kind == "open-to-closed":
        artifacts = _artifacts("2*x-y+3=0", item_id="stage15a-open-closed")
        metadata = artifacts.sampled.segment_metadata[0]
        assert metadata.closure is SegmentClosure.OPEN
        object.__setattr__(metadata, "closure", SegmentClosure.CLOSED)
    elif tamper_kind == "non-closure":
        artifacts = _artifacts("x^2+y^2=25", item_id="stage15a-non-closure")
        object.__setattr__(
            artifacts.sampled.segment_metadata[0],
            "closure",
            "closed",
        )
    elif tamper_kind in ("wrong-branch", "negative-branch"):
        artifacts = _artifacts("x^2+y^2=25", item_id=f"stage15a-{tamper_kind}")
        replacement = 1 if tamper_kind == "wrong-branch" else -1
        object.__setattr__(
            artifacts.sampled.segment_metadata[0],
            "mathematical_branch_id",
            replacement,
        )
    else:
        artifacts = _artifacts(
            "x^2/9-y^2/4=1",
            item_id=f"stage15a-{tamper_kind}",
            viewport_request=_manual(-10.0, 10.0, -8.0, 8.0),
        )
        sampled = artifacts.sampled
        ranges = sampled.segment_ranges.copy()
        first_stop = int(ranges[0, 1])
        if tamper_kind == "shift-segment-boundary":
            # Preserve the total point count and continuous final coverage,
            # but transfer one point from the second approved segment to the first.
            ranges[0, 1] = first_stop + 1
            ranges[1, 0] = first_stop + 1
        else:
            # Keep the final stop equal to the sampled point count while leaving
            # a one-point hole between otherwise ordered ranges.
            ranges[1, 0] = first_stop + 1
        ranges.setflags(write=False)
        object.__setattr__(sampled, "segment_ranges", ranges)

    # Retain exact tuple/type shape so the negative cases reach the explicit
    # per-metadata and per-approved-segment checks added by Stage 15A.
    assert type(artifacts.sampled.segment_metadata) is tuple
    assert all(
        type(metadata) is SampledSegmentMetadata
        for metadata in artifacts.sampled.segment_metadata
    )
    events, buffers, _references = _track_render_resources(monkeypatch)

    outcome = render_sampled_curve_png(artifacts.plan, artifacts.sampled)

    assert isinstance(outcome, ErrorInfo)
    assert outcome.code is ErrorCode.INTERNAL_ERROR
    assert outcome.recoverable is False
    assert outcome.technical_message == "sampled result contract validation failed"
    assert events == []
    assert buffers == []


def test_cross_type_plan_outcome_mixing_is_rejected_before_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    geometry = _artifacts("x^2+y^2=25", item_id="stage15a-mix-geometry")
    explicit_plan, explicit_sampled = _explicit_artifacts(
        item_id="stage15a-mix-explicit",
    )
    events, buffers, _references = _track_render_resources(monkeypatch)

    geometry_plan_explicit_outcome = render_sampled_curve_png(
        geometry.plan,
        explicit_sampled,
    )
    explicit_plan_geometry_outcome = render_sampled_curve_png(
        explicit_plan,
        geometry.sampled,
    )

    for outcome in (
        geometry_plan_explicit_outcome,
        explicit_plan_geometry_outcome,
    ):
        assert isinstance(outcome, ErrorInfo)
        assert outcome.code is ErrorCode.INTERNAL_ERROR
        assert outcome.recoverable is False
        assert outcome.technical_message == "sampling outcome type mismatch"
    assert events == []
    assert buffers == []


def test_upstream_no_visible_error_passes_through_with_item_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifacts = _artifacts("x^2+y^2=25", item_id="stage15a-invisible")
    upstream = ErrorInfo(
        code=ErrorCode.NO_VISIBLE_CURVE,
        user_message="当前视口内没有可绘制曲线，请调整坐标范围。",
        technical_message="reason=OUTSIDE_VIEWPORT",
        item_id=artifacts.sampled.item_id,
        field_name="sampling_visibility",
        recoverable=True,
    )
    events, buffers, _references = _track_render_resources(monkeypatch)

    outcome = render_sampled_curve_png(artifacts.plan, upstream)

    assert outcome is upstream
    assert outcome.item_id == artifacts.plan.item_plan.item_id  # type: ignore[union-attr]
    assert events == []
    assert buffers == []


def test_sampling_cancellation_becomes_render_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifacts = _artifacts("x^2+y^2=25", item_id="stage15a-sampling-cancel")
    events, buffers, _references = _track_render_resources(monkeypatch)

    outcome = render_sampled_curve_png(
        artifacts.plan,
        SamplingCancelled(artifacts.sampled.item_id),
    )

    assert outcome == RenderCancelled(artifacts.sampled.item_id)
    assert events == []
    assert buffers == []


# --- Matrix 8: PNG ceiling ----------------------------------------------------


def test_geometry_png_over_limit_is_resource_error_and_releases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifacts = _artifacts("x^2+y^2=25", item_id="stage15a-png-limit")
    budget = artifacts.plan.memory_budget
    assert isinstance(budget, ParameterizedRenderMemoryBudget)
    approved_png_limit = min(
        budget.png_buffer_reserve_bytes,
        budget.png_copy_bytes,
    )
    # The parameterized sampler re-derives its budget from DEFAULT_LIMITS, so
    # the ceiling is exercised by padding the encoded stream past the
    # approved reserve instead of building a tight-limits plan.
    original_print_png = renderer.FigureCanvasAgg.print_png

    def oversized_encode(
        canvas_self: object,
        target: object,
        *args: object,
        **kwargs: object,
    ) -> None:
        original_print_png(canvas_self, target, *args, **kwargs)
        target.write(b"\x00" * (approved_png_limit + 1))  # type: ignore[attr-defined]

    monkeypatch.setattr(renderer.FigureCanvasAgg, "print_png", oversized_encode)
    events, buffers, references = _track_render_resources(monkeypatch)

    outcome = render_sampled_curve_png(artifacts.plan, artifacts.sampled)

    assert isinstance(outcome, ErrorInfo)
    assert outcome.code is ErrorCode.RESOURCE_LIMIT_EXCEEDED
    assert outcome.recoverable is True
    assert outcome.field_name == "png_bytes"
    assert outcome.technical_message == "encoded PNG exceeds approved plan limit"
    assert events.count("encode") == 1
    assert "getvalue" not in events
    assert getattr(buffers[0], "size_at_close") > approved_png_limit
    _assert_resources_released(buffers, references)


# --- Matrix 9: failure mapping and release -----------------------------------


@pytest.mark.parametrize("failure_kind", ["encode-runtime", "figure-memory"])
def test_geometry_failure_mapping_is_sanitized_and_releases(
    monkeypatch: pytest.MonkeyPatch,
    failure_kind: str,
) -> None:
    artifacts = _artifacts("x^2+y^2=25", item_id=f"stage15a-{failure_kind}")
    events, buffers, references = _track_render_resources(monkeypatch)

    if failure_kind == "encode-runtime":
        def fail_encoding(*args: object, **kwargs: object) -> None:
            raise RuntimeError("secret geometry encode detail")

        monkeypatch.setattr(renderer.FigureCanvasAgg, "print_png", fail_encoding)
        outcome = render_sampled_curve_png(artifacts.plan, artifacts.sampled)
        assert isinstance(outcome, ErrorInfo)
        assert outcome.code is ErrorCode.RENDER_FAILED
        assert outcome.recoverable is True
        assert "RuntimeError" in (outcome.technical_message or "")
        assert "secret" not in (outcome.technical_message or "")
    else:
        def fail_allocation(*args: object, **kwargs: object) -> object:
            raise MemoryError("secret geometry allocation detail")

        monkeypatch.setattr(renderer, "Figure", fail_allocation)
        outcome = render_sampled_curve_png(artifacts.plan, artifacts.sampled)
        assert isinstance(outcome, ErrorInfo)
        assert outcome.code is ErrorCode.RESOURCE_LIMIT_EXCEEDED
        assert outcome.recoverable is True
        assert "MemoryError" in (outcome.technical_message or "")
        assert "secret" not in (outcome.technical_message or "")

    _assert_resources_released(buffers, references)


# --- Matrix 10: upstream warnings survive rendering --------------------------


def test_hyperbola_warnings_survive_rendering_untouched() -> None:
    artifacts = _artifacts(
        "x^2/9-y^2/4=1",
        item_id="stage15a-warnings",
        viewport_request=_manual(-10.0, 10.0, -8.0, 8.0),
    )
    warnings_before = artifacts.sampled.warnings
    assert any(
        warning.code.value == "viewport_clipped" for warning in warnings_before
    )

    outcome = render_sampled_curve_png(artifacts.plan, artifacts.sampled)

    assert isinstance(outcome, bytes)
    assert artifacts.sampled.warnings is warnings_before
