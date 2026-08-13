"""Stage 14C Circle/Ellipse viewport, angular plan, budget, and sampler tests."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace
from fractions import Fraction
from math import ceil, isfinite, tau

import numpy as np
import pytest

import math_drawing_assistant.engine as public_engine
import math_drawing_assistant.models as public_models
from math_drawing_assistant.config import DEFAULT_LIMITS
from math_drawing_assistant.engine import (
    RenderPlanBuilder,
    SampledParameterizedCurve,
    SamplingCancelled,
    SamplingWarningCode,
    analyze_plot_item,
    resolve_single_item_viewport,
    sample_parameterized_curve,
)
from math_drawing_assistant.engine import render_plan_builder, samplers, viewport_resolver
from math_drawing_assistant.engine.oval_geometry import (
    normalized_oval_residual,
    oval_parameter_point,
    project_oval_geometry,
)
from math_drawing_assistant.engine.parameterized_budget import (
    build_oval_parameterized_memory_budget,
    estimate_oval_exact_workspace_bytes,
    plan_oval_batch_size,
)
from math_drawing_assistant.models import (
    AngularSamplingPolicy,
    AspectRequest,
    CircleSpec,
    DEFAULT_ANGULAR_SAMPLING_POLICY,
    EllipseSpec,
    ErrorCode,
    ErrorInfo,
    GeometryRenderItemPlan,
    InputSource,
    ParameterIntervalPlan,
    PlotItemRequest,
    PlotKind,
    PlotSceneSpec,
    RenderPlan,
    ResolvedAspect,
    ResolvedViewport,
    SegmentClosure,
    ViewportMode,
    ViewportRequest,
    ViewportSource,
    validate_approved_render_plan,
)
from math_drawing_assistant.models import render_plan as render_plan_model


def _spec(text: str, *, item_id: str = "oval-item") -> CircleSpec | EllipseSpec:
    result = analyze_plot_item(
        PlotItemRequest(
            item_id=item_id,
            input_text=text,
            input_source=InputSource.MANUAL,
            requested_plot_kind=PlotKind.AUTO,
            display_order=0,
        ),
    )
    assert type(result) in {CircleSpec, EllipseSpec}, result
    return result


def _scene(text: str, *, item_id: str = "oval-item") -> PlotSceneSpec:
    return PlotSceneSpec(items=(_spec(text, item_id=item_id),))


def _viewport(
    x_min: float = -10.0,
    x_max: float = 10.0,
    y_min: float = -10.0,
    y_max: float = 10.0,
) -> ResolvedViewport:
    return ResolvedViewport(
        x_min=x_min,
        x_max=x_max,
        y_min=y_min,
        y_max=y_max,
        aspect=ResolvedAspect.EQUAL,
        source=ViewportSource.MANUAL,
    )


def _build(
    text: str,
    viewport: ResolvedViewport | None = None,
    *,
    builder: RenderPlanBuilder | None = None,
    image_width: int = 800,
    image_height: int = 600,
) -> RenderPlan | ErrorInfo:
    return (builder or RenderPlanBuilder()).build(
        _scene(text),
        viewport or _viewport(),
        image_width=image_width,
        image_height=image_height,
        dpi=96,
        show_grid=True,
        show_legend=False,
    )


def _approved(
    text: str = "x^2+y^2=25",
    viewport: ResolvedViewport | None = None,
) -> RenderPlan:
    result = _build(text, viewport)
    assert type(result) is RenderPlan, result
    return result


def _intervals(plan: RenderPlan) -> tuple[ParameterIntervalPlan, ...]:
    assert type(plan.item_plan) is GeometryRenderItemPlan
    assert all(type(value) is ParameterIntervalPlan for value in plan.item_plan.segments)
    return plan.item_plan.segments  # type: ignore[return-value]


def test_angular_policy_is_exact_frozen_slots_active_v1_and_public_identity() -> None:
    policy = DEFAULT_ANGULAR_SAMPLING_POLICY
    assert type(policy) is AngularSamplingPolicy
    assert {field.name for field in fields(policy)} == {
        "version",
        "samples_per_pixel",
        "minimum_open_segment_samples",
        "minimum_closed_curve_samples",
        "preferred_batch_points",
        "angle_merge_ulps",
        "viewport_boundary_ulps",
        "target_residual_ulps",
        "maximum_residual_ulps",
        "cancellation_check_interval",
    }
    assert tuple(getattr(policy, field.name) for field in fields(policy)) == (
        "angular-sampling-policy-v1",
        1,
        2,
        64,
        4_096,
        8,
        8,
        32,
        256,
        256,
    )
    assert public_models.AngularSamplingPolicy is AngularSamplingPolicy
    assert public_models.DEFAULT_ANGULAR_SAMPLING_POLICY is policy
    with pytest.raises(FrozenInstanceError):
        policy.samples_per_pixel = 2  # type: ignore[misc]
    assert not hasattr(policy, "__dict__")
    assert "OvalExecutionGeometry" not in public_engine.__all__
    assert "project_oval_geometry" not in public_engine.__all__


@pytest.mark.parametrize(
    ("field_name", "value", "error_type"),
    [
        ("samples_per_pixel", True, TypeError),
        ("minimum_open_segment_samples", 0, ValueError),
        ("minimum_open_segment_samples", 1, ValueError),
        ("minimum_closed_curve_samples", 2, ValueError),
        ("preferred_batch_points", -1, ValueError),
        ("angle_merge_ulps", 0, ValueError),
        ("viewport_boundary_ulps", False, TypeError),
        ("target_residual_ulps", 256, ValueError),
        ("maximum_residual_ulps", 32, ValueError),
        ("cancellation_check_interval", 0, ValueError),
    ],
)
def test_angular_policy_rejects_invalid_values(
    field_name: str,
    value: object,
    error_type: type[Exception],
) -> None:
    with pytest.raises(error_type):
        replace(DEFAULT_ANGULAR_SAMPLING_POLICY, **{field_name: value})


def test_angular_policy_v1_rejects_same_version_substitution() -> None:
    with pytest.raises(ValueError, match="semantics are fixed"):
        replace(DEFAULT_ANGULAR_SAMPLING_POLICY, samples_per_pixel=2)


@pytest.mark.parametrize(
    ("text", "expected_bounds"),
    [
        ("x^2+y^2=25", (-6.0, 6.0, -6.0, 6.0)),
        ("(x-3)^2+(y+2)^2=4", (0.0, 6.0, -5.0, 1.0)),
        ("4*x^2+9*y^2=36", (-4.0, 4.0, -3.0, 3.0)),
        ("9*x^2+4*y^2=36", (-3.0, 3.0, -4.0, 4.0)),
    ],
)
def test_auto_oval_viewport_uses_complete_geometry_padding_and_equal_default(
    text: str,
    expected_bounds: tuple[float, float, float, float],
) -> None:
    result = resolve_single_item_viewport(_scene(text), ViewportRequest())
    assert result.error is None and result.warning is None
    assert result.viewport is not None
    assert (
        result.viewport.x_min,
        result.viewport.x_max,
        result.viewport.y_min,
        result.viewport.y_max,
    ) == expected_bounds
    assert result.viewport.aspect is ResolvedAspect.EQUAL
    assert result.viewport.source is ViewportSource.AUTO_GEOMETRY


@pytest.mark.parametrize(
    ("request_aspect", "expected"),
    [
        (AspectRequest.AUTO, ResolvedAspect.AUTO),
        (AspectRequest.EQUAL, ResolvedAspect.EQUAL),
    ],
)
def test_auto_oval_explicit_aspect_wins(
    request_aspect: AspectRequest,
    expected: ResolvedAspect,
) -> None:
    result = resolve_single_item_viewport(
        _scene("x^2+y^2=25"),
        ViewportRequest(aspect_request=request_aspect),
    )
    assert result.viewport is not None
    assert result.viewport.aspect is expected


def test_auto_oval_uses_relative_padding_when_it_exceeds_absolute_padding() -> None:
    result = resolve_single_item_viewport(
        _scene("x^2+y^2=10000"),
        ViewportRequest(),
    )
    assert result.viewport is not None
    assert (
        result.viewport.x_min,
        result.viewport.x_max,
        result.viewport.y_min,
        result.viewport.y_max,
    ) == (-120.0, 120.0, -120.0, 120.0)


@pytest.mark.parametrize("field_name", ["x_min", "x_max", "y_min", "y_max"])
def test_auto_oval_rejects_every_explicit_bound(field_name: str) -> None:
    result = resolve_single_item_viewport(
        _scene("x^2+y^2=25"),
        ViewportRequest(**{field_name: 0.0}),
    )
    assert result.error is not None
    assert result.error.code is ErrorCode.INVALID_VIEWPORT
    assert result.error.field_name == field_name


@pytest.mark.parametrize(
    "text",
    [
        "100000000*x^2+100000000*y^2=1",
        "x^2+100000000*y^2=1",
        "x^2+y^2=160000000000",
        "(x-9999998)^2+y^2=1",
    ],
)
def test_auto_oval_handles_small_flat_large_and_limit_translated_geometry(text: str) -> None:
    spec = _spec(text)
    geometry = project_oval_geometry(spec)
    result = resolve_single_item_viewport(PlotSceneSpec((spec,)), ViewportRequest())
    assert result.viewport is not None, result.error
    viewport = result.viewport
    assert viewport.x_min <= geometry.x_lower <= geometry.x_upper <= viewport.x_max
    assert viewport.y_min <= geometry.y_lower <= geometry.y_upper <= viewport.y_max
    assert abs(viewport.x_min) <= DEFAULT_LIMITS.max_viewport_absolute_coordinate
    assert abs(viewport.x_max) <= DEFAULT_LIMITS.max_viewport_absolute_coordinate


def test_auto_oval_out_of_range_is_typed_numeric_error_without_fallback() -> None:
    result = resolve_single_item_viewport(
        _scene("x^2+y^2=100000000000000"),
        ViewportRequest(),
    )
    assert result.viewport is None and result.warning is None
    assert result.error is not None
    assert result.error.code is ErrorCode.NUMERIC_RANGE_UNSUPPORTED


def test_auto_oval_exact_workspace_gate_precedes_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limits = replace(DEFAULT_LIMITS, max_viewport_probe_bytes=1)

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("projection must remain behind the exact-workspace gate")

    monkeypatch.setattr(viewport_resolver, "project_oval_geometry", forbidden)
    result = resolve_single_item_viewport(
        _scene("x^2+y^2=25"),
        ViewportRequest(),
        limits=limits,
    )
    assert result.error is not None
    assert result.error.code is ErrorCode.VIEWPORT_PROBE_BUDGET_EXCEEDED


def test_auto_oval_never_uses_explicit_probe_executor_or_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("oval auto viewport must use exact geometry only")

    monkeypatch.setattr(viewport_resolver, "estimate_numeric_execution_cost", forbidden)
    monkeypatch.setattr(viewport_resolver, "execute_explicit_function", forbidden)
    monkeypatch.setattr(viewport_resolver.np, "linspace", forbidden)
    result = resolve_single_item_viewport(_scene("x^2+y^2=25"), ViewportRequest())
    assert result.viewport is not None
    assert result.viewport.source is ViewportSource.AUTO_GEOMETRY


@pytest.mark.parametrize("text", ["4*x^2-9*y^2=36", "x^2=4*y"])
def test_hyperbola_and_parabola_auto_viewports_remain_strategy_errors(text: str) -> None:
    item = analyze_plot_item(
        PlotItemRequest("future", text, InputSource.MANUAL, PlotKind.AUTO, 0),
    )
    assert not isinstance(item, ErrorInfo)
    result = resolve_single_item_viewport(PlotSceneSpec((item,)), ViewportRequest())
    assert result.error is not None
    assert result.error.code is ErrorCode.INTERNAL_ERROR
    assert result.error.field_name == "viewport_strategy"


def test_full_oval_plan_is_one_closed_turn_with_fixed_branch_and_capacity() -> None:
    plan = _approved()
    assert plan.sampling_policy_version == DEFAULT_ANGULAR_SAMPLING_POLICY.version
    assert type(plan.item_plan) is GeometryRenderItemPlan
    assert plan.item_plan.mathematical_branch_count == 1
    assert plan.item_plan.max_segment_count == 4
    interval, = _intervals(plan)
    assert (
        interval.mathematical_branch_id,
        interval.parameter_start,
        interval.parameter_stop,
        interval.closure,
    ) == (0, 0.0, tau, SegmentClosure.CLOSED)
    rho = max(5.0 * 800 / 20, 5.0 * 600 / 20)
    assert interval.sample_count == max(64, ceil(rho * tau))


@pytest.mark.parametrize(
    ("viewport", "expected_count"),
    [
        (_viewport(-1.0, 1.0, -6.0, 6.0), 2),
        (_viewport(-4.0, 4.0, -4.0, 4.0), 4),
    ],
)
def test_partial_oval_plans_keep_independent_sorted_open_arcs(
    viewport: ResolvedViewport,
    expected_count: int,
) -> None:
    plan = _approved(viewport=viewport)
    intervals = _intervals(plan)
    assert len(intervals) == expected_count
    assert all(interval.closure is SegmentClosure.OPEN for interval in intervals)
    assert all(interval.mathematical_branch_id == 0 for interval in intervals)
    assert list(intervals) == sorted(intervals, key=lambda value: value.parameter_start)
    assert all(interval.sample_count >= 2 for interval in intervals)
    assert len(intervals) <= 4


def test_visible_arc_crossing_zero_is_one_expanded_open_interval() -> None:
    plan = _approved(viewport=_viewport(4.0, 6.0, -1.0, 1.0))
    interval, = _intervals(plan)
    assert 0.0 <= interval.parameter_start < tau
    assert interval.parameter_stop > tau
    assert 0.0 < interval.parameter_stop - interval.parameter_start < tau
    assert interval.closure is SegmentClosure.OPEN


@pytest.mark.parametrize(
    ("viewport", "expected_count"),
    [
        (_viewport(-5.0, 3.0, -5.0, 4.0), 1),
        (_viewport(-5.0, 5.0, -4.0, 4.0), 2),
    ],
)
def test_corner_intersections_and_tangent_edges_preserve_visible_arcs(
    viewport: ResolvedViewport,
    expected_count: int,
) -> None:
    plan = _approved(viewport=viewport)
    intervals = _intervals(plan)
    assert len(intervals) == expected_count
    assert all(interval.closure is SegmentClosure.OPEN for interval in intervals)


@pytest.mark.parametrize(
    "viewport",
    [
        _viewport(5.0, 6.0, -1.0, 1.0),
        _viewport(6.0, 7.0, -1.0, 1.0),
    ],
)
def test_isolated_tangent_or_invisible_oval_returns_no_visible(
    viewport: ResolvedViewport,
) -> None:
    result = _build("x^2+y^2=25", viewport)
    assert type(result) is ErrorInfo
    assert result.code is ErrorCode.NO_VISIBLE_CURVE


def test_open_sample_count_uses_each_approved_arc_span() -> None:
    viewport = _viewport(-1.0, 1.0, -6.0, 6.0)
    plan = _approved(viewport=viewport)
    rho = max(5.0 * 800 / 2.0, 5.0 * 600 / 12.0)
    for interval in _intervals(plan):
        assert interval.sample_count == max(
            2,
            ceil(rho * (interval.parameter_stop - interval.parameter_start)) + 1,
        )


def test_oval_budget_fields_and_sums_match_the_frozen_formula() -> None:
    sample_count = 100
    batch_size = 20
    budget = build_oval_parameterized_memory_budget(
        sample_count=sample_count,
        batch_size=batch_size,
        image_width=10,
        image_height=20,
        limits=DEFAULT_LIMITS,
    )
    exact = estimate_oval_exact_workspace_bytes(DEFAULT_LIMITS)
    assert budget.final_x_bytes == budget.final_y_bytes == sample_count * 8
    assert budget.artist_data_bytes == 2 * sample_count * 8
    assert budget.segment_index_range_bytes == 4 * 2 * 8
    assert budget.segment_metadata_bytes == 4 * 2 * 8
    assert budget.parameter_batch_bytes == batch_size * 8
    assert budget.transcendental_workspace_bytes == 2 * batch_size * 8
    assert budget.validation_workspace_bytes == (
        exact + 9 * 8 + 9 + 4 * 2 * 8 + batch_size + batch_size * 8
    )
    assert budget.rgba_canvas_bytes == 10 * 20 * 4
    assert budget.png_buffer_reserve_bytes == DEFAULT_LIMITS.max_png_bytes
    assert budget.png_copy_bytes == DEFAULT_LIMITS.max_png_bytes
    assert budget.total_bytes == budget.fixed_bytes + budget.batch_bytes


def test_batch_planner_returns_preference_when_memory_allows() -> None:
    assert plan_oval_batch_size(
        sample_count=10_000,
        preferred_batch_points=4_096,
        image_width=100,
        image_height=100,
        limits=DEFAULT_LIMITS,
    ) == 4_096


def test_builder_rejects_point_and_memory_limits_before_sampling_allocation() -> None:
    point_limits = replace(
        DEFAULT_LIMITS,
        max_sample_points_per_item=10,
        max_total_sample_points=10,
    )
    point_result = _build(
        "x^2+y^2=25",
        builder=RenderPlanBuilder(limits=point_limits),
    )
    assert type(point_result) is ErrorInfo
    assert point_result.code is ErrorCode.RESOURCE_LIMIT_EXCEEDED

    branch_limits = replace(
        DEFAULT_LIMITS,
        max_branches_per_item=3,
        max_total_branches=3,
    )
    branch_result = _build(
        "x^2+y^2=25",
        builder=RenderPlanBuilder(limits=branch_limits),
    )
    assert type(branch_result) is ErrorInfo
    assert branch_result.code is ErrorCode.RESOURCE_LIMIT_EXCEEDED

    memory_limits = replace(DEFAULT_LIMITS, max_estimated_memory_bytes=1)
    memory_result = _build(
        "x^2+y^2=25",
        builder=RenderPlanBuilder(limits=memory_limits),
    )
    assert type(memory_result) is ErrorInfo
    assert memory_result.code is ErrorCode.RESOURCE_LIMIT_EXCEEDED


@pytest.mark.parametrize(
    "text",
    ["x^2+y^2=25", "4*x^2+9*y^2=36"],
)
def test_direct_stage13_to_resolver_builder_sampler_pipeline(text: str) -> None:
    scene = _scene(text)
    resolution = resolve_single_item_viewport(scene, ViewportRequest())
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
    assert type(plan) is RenderPlan
    sampled = sample_parameterized_curve(plan)
    assert type(sampled) is SampledParameterizedCurve
    assert sampled.x.dtype == sampled.y.dtype == np.dtype(np.float64)
    assert sampled.segment_ranges.dtype == np.dtype(np.int64)
    assert sampled.x.ndim == sampled.y.ndim == 1
    assert sampled.segment_ranges.shape == (1, 2)
    assert sampled.x.flags.owndata and not sampled.x.flags.writeable
    assert sampled.y.flags.owndata and not sampled.y.flags.writeable
    assert sampled.segment_ranges.flags.owndata
    assert not sampled.segment_ranges.flags.writeable
    assert sampled.segment_metadata[0].closure is SegmentClosure.CLOSED
    assert sampled.segment_metadata[0].mathematical_branch_id == 0
    assert sampled.visible_segment_count == 1
    assert sampled.warnings == ()
    assert sampled.x[0] != sampled.x[-1] or sampled.y[0] != sampled.y[-1]
    assert samplers._sampled_parameterized_curve_matches_approved_plan(sampled, plan)


def test_open_sampler_includes_approved_endpoints_and_keeps_arc_ranges_separate() -> None:
    plan = _approved(viewport=_viewport(-4.0, 4.0, -4.0, 4.0))
    sampled = sample_parameterized_curve(plan)
    assert type(sampled) is SampledParameterizedCurve
    geometry = project_oval_geometry(plan.scene_spec.items[0])  # type: ignore[arg-type]
    intervals = _intervals(plan)
    assert sampled.segment_ranges.shape == (4, 2)
    for index, interval in enumerate(intervals):
        start, stop = map(int, sampled.segment_ranges[index])
        assert (sampled.x[start], sampled.y[start]) == oval_parameter_point(
            geometry,
            interval.parameter_start,
        )
        assert (sampled.x[stop - 1], sampled.y[stop - 1]) == oval_parameter_point(
            geometry,
            interval.parameter_stop,
        )
        assert sampled.segment_metadata[index].closure is SegmentClosure.OPEN
        assert sampled.segment_metadata[index].mathematical_branch_id == 0
    assert [warning.code for warning in sampled.warnings] == [
        SamplingWarningCode.VIEWPORT_CLIPPED,
    ]
    assert sampled.warnings[0].metrics.clipped_segment_count == 4  # type: ignore[union-attr]


@pytest.mark.parametrize("text", ["x^2+y^2=25", "4*x^2+9*y^2=36"])
def test_sampled_points_are_finite_and_within_exact_hard_residual(text: str) -> None:
    plan = _approved(text)
    sampled = sample_parameterized_curve(plan)
    assert type(sampled) is SampledParameterizedCurve
    geometry = project_oval_geometry(plan.scene_spec.items[0])  # type: ignore[arg-type]
    residuals = [
        normalized_oval_residual(geometry, float(x), float(y))
        for x, y in zip(sampled.x, sampled.y, strict=True)
    ]
    assert np.all(np.isfinite(sampled.x)) and np.all(np.isfinite(sampled.y))
    assert max(residuals) <= 256 * Fraction(1, 1 << 52)


@pytest.mark.parametrize(
    "target",
    [
        "spec",
        "interval",
        "closure",
        "policy",
        "sampler_version",
        "budget",
        "viewport",
    ],
)
def test_receipt_rejects_every_oval_contract_tamper(target: str) -> None:
    plan = _approved()
    interval, = _intervals(plan)
    if target == "spec":
        object.__setattr__(plan.scene_spec.items[0], "radius_squared", Fraction(24))
    elif target == "interval":
        object.__setattr__(interval, "sample_count", interval.sample_count + 1)
    elif target == "closure":
        object.__setattr__(interval, "closure", SegmentClosure.OPEN)
    elif target == "policy":
        object.__setattr__(plan, "sampling_policy_version", "tampered")
    elif target == "sampler_version":
        object.__setattr__(plan, "parameterized_sampler_contract_version", "tampered")
    elif target == "budget":
        object.__setattr__(
            plan.memory_budget,
            "validation_workspace_bytes",
            plan.memory_budget.validation_workspace_bytes + 1,
        )
    else:
        object.__setattr__(plan.resolved_viewport, "x_min", -9.0)
    with pytest.raises(ValueError, match="do not match"):
        validate_approved_render_plan(plan)


def test_approval_rejects_overlapping_open_oval_intervals() -> None:
    plan = _approved()
    assert type(plan.item_plan) is GeometryRenderItemPlan
    first_count = plan.item_plan.sample_count // 2
    intervals = (
        ParameterIntervalPlan(0, 0.1, 1.0, first_count, SegmentClosure.OPEN),
        ParameterIntervalPlan(
            0,
            0.5,
            1.5,
            plan.item_plan.sample_count - first_count,
            SegmentClosure.OPEN,
        ),
    )
    overlapping_item_plan = replace(plan.item_plan, segments=intervals)
    with pytest.raises(ValueError, match="must not overlap"):
        render_plan_model._approve_render_plan(
            replace(plan, item_plan=overlapping_item_plan),
        )


def test_sampler_approval_validation_precedes_allocation_after_tamper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _approved()
    object.__setattr__(plan.memory_budget, "parameter_batch_bytes", 1)

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("tampered receipt must fail before allocation")

    monkeypatch.setattr(samplers.np, "empty", forbidden)
    result = sample_parameterized_curve(plan)
    assert type(result) is ErrorInfo
    assert result.code is ErrorCode.INTERNAL_ERROR


def test_sampler_recomputes_signed_oval_budget_before_first_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _approved()
    invalid_budget = replace(
        plan.memory_budget,
        validation_workspace_bytes=plan.memory_budget.validation_workspace_bytes + 1,
    )
    signed_mismatch = render_plan_model._approve_render_plan(
        replace(plan, memory_budget=invalid_budget),
    )

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("budget mismatch must fail before formal allocation")

    monkeypatch.setattr(samplers.np, "empty", forbidden)
    result = sample_parameterized_curve(signed_mismatch)
    assert type(result) is ErrorInfo
    assert result.code is ErrorCode.INTERNAL_ERROR


@pytest.mark.parametrize(
    ("residual_ulps", "expected"),
    [(33, SamplingWarningCode.SAMPLING_PRECISION_LIMITED), (257, ErrorCode.NUMERIC_RANGE_UNSUPPORTED)],
)
def test_sampler_precision_warning_and_hard_error(
    residual_ulps: int,
    expected: SamplingWarningCode | ErrorCode,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        samplers,
        "normalized_oval_residual",
        lambda *args: residual_ulps * Fraction(1, 1 << 52),
    )
    result = sample_parameterized_curve(_approved())
    if residual_ulps > 256:
        assert type(result) is ErrorInfo
        assert result.code is expected
    else:
        assert type(result) is SampledParameterizedCurve
        assert [warning.code for warning in result.warnings] == [expected]
        assert result.warnings[0].metrics.limited_segment_count == 1  # type: ignore[union-attr]


def test_sampler_rejects_nonfinite_batch_and_numeric_single_point_collapse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_sin = samplers.np.sin
    monkeypatch.setattr(
        samplers.np,
        "sin",
        lambda theta: np.full(theta.shape, np.inf, dtype=np.float64),
    )
    nonfinite = sample_parameterized_curve(_approved())
    assert type(nonfinite) is ErrorInfo
    assert nonfinite.code is ErrorCode.NUMERIC_RANGE_UNSUPPORTED

    monkeypatch.setattr(samplers.np, "sin", original_sin)
    monkeypatch.setattr(
        samplers.np,
        "cos",
        lambda theta: np.zeros(theta.shape, dtype=np.float64),
    )
    monkeypatch.setattr(
        samplers.np,
        "sin",
        lambda theta: np.zeros(theta.shape, dtype=np.float64),
    )
    monkeypatch.setattr(
        samplers,
        "_oval_scalar_point",
        lambda geometry, theta: (geometry.center_x_float, geometry.center_y_float),
    )
    monkeypatch.setattr(samplers, "normalized_oval_residual", lambda *args: Fraction(0))
    collapsed = sample_parameterized_curve(_approved())
    assert type(collapsed) is ErrorInfo
    assert collapsed.code is ErrorCode.NO_VISIBLE_CURVE


class _CancelOnPoll:
    def __init__(self, target: int) -> None:
        self.target = target
        self.count = 0

    def is_cancelled(self) -> bool:
        self.count += 1
        return self.count == self.target


@pytest.mark.parametrize("target", [1, 2, 3, 4, 5, 6, 10, 11, 12])
def test_oval_sampler_cooperative_cancellation_checkpoints(target: int) -> None:
    probe = _CancelOnPoll(target)
    result = sample_parameterized_curve(_approved(), cancellation_probe=probe)
    assert type(result) is SamplingCancelled
    assert probe.count == target


def test_sampler_does_not_reenter_resolver_builder_or_interval_planner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _approved(viewport=_viewport(-1.0, 1.0, -6.0, 6.0))

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("approved sampler must only consume its plan")

    monkeypatch.setattr(viewport_resolver, "resolve_single_item_viewport", forbidden)
    monkeypatch.setattr(render_plan_builder, "_plan_visible_oval_intervals", forbidden)
    result = sample_parameterized_curve(plan)
    assert type(result) is SampledParameterizedCurve
    assert result.diagnostics.sampled_segment_count == 2
    assert result.diagnostics.sampled_point_count == result.x.size


def test_private_oval_execution_values_are_finite_and_outward() -> None:
    geometry = project_oval_geometry(_spec("4*x^2+9*y^2=36"))
    assert all(
        isfinite(value)
        for value in (
            geometry.center_x_float,
            geometry.center_y_float,
            geometry.semi_axis_x_float,
            geometry.semi_axis_y_float,
            geometry.outward_semi_axis_x,
            geometry.outward_semi_axis_y,
        )
    )
    assert Fraction.from_float(geometry.outward_semi_axis_x) ** 2 >= (
        geometry.semi_axis_x_squared
    )
    assert Fraction.from_float(geometry.outward_semi_axis_y) ** 2 >= (
        geometry.semi_axis_y_squared
    )
