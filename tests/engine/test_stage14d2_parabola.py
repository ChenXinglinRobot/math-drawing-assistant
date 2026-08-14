"""Stage 14D-2 ParabolaSpec viewport, plan, budget, and sampler contracts."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace
from fractions import Fraction
from inspect import signature
from math import ceil, hypot, isfinite
from pathlib import Path

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
from math_drawing_assistant.engine.parameterized_budget import (
    _PARABOLA_EXACT_LIVE_BIGINT_VALUES,
    _PARABOLA_INTERVAL_EXACT_LIVE_BIGINT_VALUES,
    _PARABOLA_RESIDUAL_EXACT_LIVE_BIGINT_VALUES,
    _axis_aligned_conic_exact_max_integer_bits,
    build_parabola_parameterized_memory_budget,
    estimate_parabola_exact_workspace_bytes,
    plan_parabola_batch_size,
)
from math_drawing_assistant.engine.parabola_geometry import (
    normalized_parabola_residual,
    parabola_parameter_point,
    project_parabola_geometry,
)
from math_drawing_assistant.models import (
    AspectRequest,
    DEFAULT_PARABOLIC_SAMPLING_POLICY,
    ErrorCode,
    ErrorInfo,
    GeometryRenderItemPlan,
    InputSource,
    PARAMETERIZED_SAMPLER_CONTRACT_VERSION,
    ParameterIntervalPlan,
    ParabolaOpening,
    ParabolaSpec,
    ParabolicSamplingPolicy,
    PlotItemRequest,
    PlotKind,
    PlotSceneSpec,
    RENDER_PLAN_CONTRACT_VERSION,
    RenderPlan,
    ResolvedAspect,
    ResolvedViewport,
    SegmentClosure,
    ViewportMode,
    ViewportRequest,
    ViewportSource,
)
from math_drawing_assistant.models import render_plan as render_plan_model


def _spec(text: str, *, item_id: str = "parabola-item") -> ParabolaSpec:
    result = analyze_plot_item(
        PlotItemRequest(
            item_id=item_id,
            input_text=text,
            input_source=InputSource.MANUAL,
            requested_plot_kind=PlotKind.AUTO,
            display_order=0,
        ),
    )
    assert type(result) is ParabolaSpec, result
    return result


def _scene(text: str, *, item_id: str = "parabola-item") -> PlotSceneSpec:
    return PlotSceneSpec((_spec(text, item_id=item_id),))


def _viewport(
    x_min: float = -5.0,
    x_max: float = 5.0,
    y_min: float = -5.0,
    y_max: float = 5.0,
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
    text: str = "x^2=4*y",
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
    text: str = "x^2=4*y",
    viewport: ResolvedViewport | None = None,
) -> RenderPlan:
    result = _build(text, viewport)
    assert type(result) is RenderPlan, result
    return result


def _intervals(plan: RenderPlan) -> tuple[ParameterIntervalPlan, ...]:
    assert type(plan.item_plan) is GeometryRenderItemPlan
    assert all(type(value) is ParameterIntervalPlan for value in plan.item_plan.segments)
    return plan.item_plan.segments  # type: ignore[return-value]


def test_parabolic_policy_is_exact_frozen_slots_v1_and_public_identity() -> None:
    policy = DEFAULT_PARABOLIC_SAMPLING_POLICY
    assert type(policy) is ParabolicSamplingPolicy
    assert tuple(getattr(policy, field.name) for field in fields(policy)) == (
        "parabolic-sampling-policy-v1",
        1,
        2,
        4_096,
        8,
        8,
        32,
        256,
        256,
    )
    assert public_models.ParabolicSamplingPolicy is ParabolicSamplingPolicy
    assert public_models.DEFAULT_PARABOLIC_SAMPLING_POLICY is policy
    with pytest.raises(FrozenInstanceError):
        policy.samples_per_pixel = 2  # type: ignore[misc]
    assert not hasattr(policy, "__dict__")
    assert "ParabolaExecutionGeometry" not in public_engine.__all__
    assert "project_parabola_geometry" not in public_engine.__all__


@pytest.mark.parametrize(
    ("field_name", "value", "error_type"),
    [
        ("samples_per_pixel", True, TypeError),
        ("minimum_open_segment_samples", 1, ValueError),
        ("preferred_batch_points", 0, ValueError),
        ("parameter_merge_ulps", 0, ValueError),
        ("viewport_boundary_ulps", False, TypeError),
        ("target_residual_ulps", 256, ValueError),
        ("maximum_residual_ulps", 32, ValueError),
        ("cancellation_check_interval", 0, ValueError),
    ],
)
def test_parabolic_policy_rejects_invalid_values(
    field_name: str,
    value: object,
    error_type: type[Exception],
) -> None:
    with pytest.raises(error_type):
        replace(DEFAULT_PARABOLIC_SAMPLING_POLICY, **{field_name: value})


def test_parabolic_policy_v1_rejects_same_version_substitution() -> None:
    with pytest.raises(ValueError, match="semantics are fixed"):
        replace(DEFAULT_PARABOLIC_SAMPLING_POLICY, preferred_batch_points=2_048)
    assert RENDER_PLAN_CONTRACT_VERSION == "render-plan-v2-typed-geometry"
    assert PARAMETERIZED_SAMPLER_CONTRACT_VERSION == "parameterized-sampler-v1"


@pytest.mark.parametrize(
    ("text", "opening", "exact_bounds"),
    [
        ("x^2=4*y", ParabolaOpening.UP, (-2, 2, 0, 1)),
        ("x^2=-4*y", ParabolaOpening.DOWN, (-2, 2, -1, 0)),
        ("y^2=4*x", ParabolaOpening.RIGHT, (0, 1, -2, 2)),
        ("y^2=-4*x", ParabolaOpening.LEFT, (-1, 0, -2, 2)),
        ("(x-2)^2=8*(y+1)", ParabolaOpening.UP, (-2, 6, -1, 1)),
    ],
)
def test_auto_parabola_teaching_window_is_outward_padded_and_equal(
    text: str,
    opening: ParabolaOpening,
    exact_bounds: tuple[int, int, int, int],
) -> None:
    spec = _spec(text)
    assert spec.opening is opening
    geometry = project_parabola_geometry(spec)
    exact_x_lower, exact_x_upper, exact_y_lower, exact_y_upper = map(
        Fraction,
        exact_bounds,
    )
    assert Fraction.from_float(geometry.auto_x_lower) <= exact_x_lower
    assert Fraction.from_float(geometry.auto_x_upper) >= exact_x_upper
    assert Fraction.from_float(geometry.auto_y_lower) <= exact_y_lower
    assert Fraction.from_float(geometry.auto_y_upper) >= exact_y_upper

    result = resolve_single_item_viewport(PlotSceneSpec((spec,)), ViewportRequest())
    assert result.error is None
    assert result.warning is None
    assert result.viewport is not None
    assert result.viewport.source is ViewportSource.AUTO_GEOMETRY
    assert result.viewport.aspect is ResolvedAspect.EQUAL
    assert result.viewport.x_min <= geometry.auto_x_lower
    assert result.viewport.x_max >= geometry.auto_x_upper
    assert result.viewport.y_min <= geometry.auto_y_lower
    assert result.viewport.y_max >= geometry.auto_y_upper


@pytest.mark.parametrize(
    ("aspect", "resolved"),
    [(AspectRequest.AUTO, ResolvedAspect.AUTO), (AspectRequest.EQUAL, ResolvedAspect.EQUAL)],
)
def test_auto_parabola_explicit_aspect_wins(
    aspect: AspectRequest,
    resolved: ResolvedAspect,
) -> None:
    result = resolve_single_item_viewport(
        _scene("x^2=4*y"),
        ViewportRequest(aspect_request=aspect),
    )
    assert result.viewport is not None
    assert result.viewport.aspect is resolved


@pytest.mark.parametrize("field_name", ["x_min", "x_max", "y_min", "y_max"])
def test_auto_parabola_rejects_every_explicit_bound(field_name: str) -> None:
    result = resolve_single_item_viewport(
        _scene("x^2=4*y"),
        replace(ViewportRequest(), **{field_name: 0}),
    )
    assert result.error is not None
    assert result.error.code is ErrorCode.INVALID_VIEWPORT
    assert result.error.field_name == field_name


def test_auto_parabola_workspace_gate_precedes_projection_and_never_probes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    estimate = estimate_parabola_exact_workspace_bytes(DEFAULT_LIMITS)

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("parabola auto viewport must not probe, execute, or project")

    monkeypatch.setattr(viewport_resolver.np, "linspace", forbidden)
    monkeypatch.setattr(viewport_resolver, "execute_explicit_function", forbidden)
    monkeypatch.setattr(viewport_resolver, "estimate_numeric_execution_cost", forbidden)
    monkeypatch.setattr(viewport_resolver, "project_parabola_geometry", forbidden)
    result = resolve_single_item_viewport(
        _scene("x^2=4*y"),
        ViewportRequest(),
        limits=replace(DEFAULT_LIMITS, max_viewport_probe_bytes=estimate - 1),
    )
    assert result.error is not None
    assert result.error.code is ErrorCode.VIEWPORT_PROBE_BUDGET_EXCEEDED


def test_successful_auto_parabola_never_calls_explicit_probe_or_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("parabola AUTO_GEOMETRY must not use explicit probing")

    monkeypatch.setattr(viewport_resolver.np, "linspace", forbidden)
    monkeypatch.setattr(viewport_resolver, "execute_explicit_function", forbidden)
    monkeypatch.setattr(viewport_resolver, "estimate_numeric_execution_cost", forbidden)
    monkeypatch.setattr(viewport_resolver, "_fallback_resolution", forbidden)
    result = resolve_single_item_viewport(_scene("x^2=4*y"), ViewportRequest())
    assert result.viewport is not None
    assert result.viewport.source is ViewportSource.AUTO_GEOMETRY


def test_auto_parabola_coordinate_limit_failure_is_typed() -> None:
    spec = replace(
        _spec("x^2=4*y"),
        vertex_x=Fraction(DEFAULT_LIMITS.max_viewport_absolute_coordinate + 1),
    )
    result = resolve_single_item_viewport(PlotSceneSpec((spec,)), ViewportRequest())
    assert result.error is not None
    assert result.error.code is ErrorCode.NUMERIC_RANGE_UNSUPPORTED


def test_vertex_visible_is_one_open_branch_zero_interval() -> None:
    plan = _approved(viewport=_viewport(-4.0, 4.0, -1.0, 4.0))
    intervals = _intervals(plan)
    assert len(intervals) == 1
    assert intervals[0].mathematical_branch_id == 0
    assert intervals[0].closure is SegmentClosure.OPEN
    assert intervals[0].parameter_start == pytest.approx(-2.0)
    assert intervals[0].parameter_stop == pytest.approx(2.0)
    assert plan.item_plan is not None
    assert plan.item_plan.mathematical_branch_count == 1
    assert plan.item_plan.max_segment_count == 2


def test_vertex_excluded_produces_two_sorted_nonoverlapping_intervals() -> None:
    plan = _approved(viewport=_viewport(-10.0, 10.0, 1.0, 4.0))
    intervals = _intervals(plan)
    assert [(value.parameter_start, value.parameter_stop) for value in intervals] == [
        pytest.approx((-2.0, -1.0)),
        pytest.approx((1.0, 2.0)),
    ]
    assert intervals[0].parameter_stop < intervals[1].parameter_start
    assert all(value.mathematical_branch_id == 0 for value in intervals)


def test_single_side_clipping_produces_one_interval_without_misconnection() -> None:
    plan = _approved(viewport=_viewport(0.0, 4.0, -1.0, 4.0))
    intervals = _intervals(plan)
    assert len(intervals) == 1
    assert intervals[0].parameter_start == 0.0
    sampled = sample_parameterized_curve(plan)
    assert type(sampled) is SampledParameterizedCurve
    assert sampled.segment_ranges.shape == (1, 2)


@pytest.mark.parametrize(
    "viewport",
    [
        _viewport(-4.0, 4.0, -4.0, -1.0),
        _viewport(2.0, 4.0, 0.0, 1.0),
    ],
)
def test_invisible_and_exact_singleton_tangent_return_no_visible(
    viewport: ResolvedViewport,
) -> None:
    result = _build(viewport=viewport)
    assert type(result) is ErrorInfo
    assert result.code is ErrorCode.NO_VISIBLE_CURVE


@pytest.mark.parametrize(
    "viewport",
    [
        _viewport(-4.0, 4.0, -4.0, -1.0),
        _viewport(2.0, 4.0, 0.0, 1.0),
    ],
)
def test_exact_empty_or_singleton_decision_precedes_any_square_root(
    viewport: ResolvedViewport,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("exact topology must reject before square-root conversion")

    monkeypatch.setattr(render_plan_builder, "_finite_parabola_sqrt", forbidden)
    result = _build(viewport=viewport)
    assert type(result) is ErrorInfo
    assert result.code is ErrorCode.NO_VISIBLE_CURVE


def test_derivative_point_count_formula_is_frozen() -> None:
    viewport = _viewport(-4.0, 4.0, -1.0, 4.0)
    plan = _approved(viewport=viewport)
    geometry = project_parabola_geometry(_spec("x^2=4*y"))
    interval = _intervals(plan)[0]
    maximum_parameter = max(abs(interval.parameter_start), abs(interval.parameter_stop))
    x_speed = abs(geometry.two_focal_parameter_float) * 800 / (
        viewport.x_max - viewport.x_min
    )
    y_speed = (
        abs(geometry.two_focal_parameter_float)
        * maximum_parameter
        * 600
        / (viewport.y_max - viewport.y_min)
    )
    expected = max(
        2,
        ceil(hypot(x_speed, y_speed) * (interval.parameter_stop - interval.parameter_start))
        + 1,
    )
    assert interval.sample_count == expected


def test_parabola_exact_workspace_has_named_liveness_and_proven_bound() -> None:
    assert _PARABOLA_EXACT_LIVE_BIGINT_VALUES == (
        _PARABOLA_INTERVAL_EXACT_LIVE_BIGINT_VALUES
    )
    assert len(_PARABOLA_INTERVAL_EXACT_LIVE_BIGINT_VALUES) == 31
    assert len(_PARABOLA_RESIDUAL_EXACT_LIVE_BIGINT_VALUES) == 27
    assert len(set(_PARABOLA_INTERVAL_EXACT_LIVE_BIGINT_VALUES)) == 31
    assert _axis_aligned_conic_exact_max_integer_bits(DEFAULT_LIMITS) > 0
    assert 0 < estimate_parabola_exact_workspace_bytes(DEFAULT_LIMITS) < (
        DEFAULT_LIMITS.max_viewport_probe_bytes
    )


def test_parabola_budget_fields_and_zero_transcendental_workspace_are_exact() -> None:
    budget = build_parabola_parameterized_memory_budget(
        sample_count=100,
        batch_size=7,
        image_width=320,
        image_height=240,
        limits=DEFAULT_LIMITS,
    )
    exact = estimate_parabola_exact_workspace_bytes(DEFAULT_LIMITS)
    assert budget.final_x_bytes == 800
    assert budget.final_y_bytes == 800
    assert budget.artist_data_bytes == 1_600
    assert budget.segment_index_range_bytes == 2 * 2 * 8
    assert budget.segment_metadata_bytes == 2 * 2 * 8
    assert budget.parameter_batch_bytes == 7 * 8
    assert budget.transcendental_workspace_bytes == 0
    assert budget.validation_workspace_bytes == (
        exact + 6 * 8 + 6 + 2 * 2 * 8 + 7 + 7 * 8
    )


def test_parabola_batch_planner_returns_exact_largest_approved_value() -> None:
    minimum = build_parabola_parameterized_memory_budget(
        sample_count=100,
        batch_size=1,
        image_width=320,
        image_height=240,
        limits=DEFAULT_LIMITS,
    )
    target = 7
    limits = replace(
        DEFAULT_LIMITS,
        max_estimated_memory_bytes=minimum.total_bytes + (target - 1) * 17,
    )
    assert plan_parabola_batch_size(
        sample_count=100,
        preferred_batch_points=4_096,
        image_width=320,
        image_height=240,
        limits=limits,
    ) == target
    assert plan_parabola_batch_size(
        sample_count=10_000,
        preferred_batch_points=10_000,
        image_width=320,
        image_height=240,
        limits=replace(DEFAULT_LIMITS, max_estimated_memory_bytes=10**9),
    ) <= 4_096


@pytest.mark.parametrize(
    "text",
    ["x^2=4*y", "x^2=-4*y", "y^2=4*x", "y^2=-4*x"],
)
def test_four_openings_complete_analyzer_resolver_builder_sampler_flow(text: str) -> None:
    scene = _scene(text)
    resolution = resolve_single_item_viewport(scene, ViewportRequest())
    assert resolution.error is None
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
    assert plan.numeric_executor_contract_version is None
    assert plan.parameterized_sampler_contract_version == "parameterized-sampler-v1"
    result = sample_parameterized_curve(plan)
    assert type(result) is SampledParameterizedCurve
    assert np.all(np.isfinite(result.x))
    assert np.all(np.isfinite(result.y))
    assert result.x.flags.owndata and not result.x.flags.writeable
    assert result.y.flags.owndata and not result.y.flags.writeable
    assert result.segment_ranges.flags.owndata
    assert not result.segment_ranges.flags.writeable
    assert all(metadata.mathematical_branch_id == 0 for metadata in result.segment_metadata)
    assert all(metadata.closure is SegmentClosure.OPEN for metadata in result.segment_metadata)
    geometry = project_parabola_geometry(scene.items[0])  # type: ignore[arg-type]
    assert all(
        normalized_parabola_residual(geometry, float(x), float(y))
        <= DEFAULT_PARABOLIC_SAMPLING_POLICY.maximum_residual_ulps * Fraction(1, 1 << 52)
        for x, y in zip(result.x, result.y, strict=True)
    )


def test_parameter_point_rejects_overflow_and_projection_rejects_underflow() -> None:
    geometry = project_parabola_geometry(_spec("x^2=4*y"))
    with pytest.raises(OverflowError):
        parabola_parameter_point(geometry, 1.0e308)
    tiny = replace(_spec("x^2=4*y"), focal_parameter=Fraction(1, 10**400))
    with pytest.raises(OverflowError):
        project_parabola_geometry(tiny)


def test_success_always_reports_actual_segment_count_as_viewport_clipped() -> None:
    one = sample_parameterized_curve(
        _approved(viewport=_viewport(-4.0, 4.0, -1.0, 4.0)),
    )
    two = sample_parameterized_curve(
        _approved(viewport=_viewport(-10.0, 10.0, 1.0, 4.0)),
    )
    assert type(one) is SampledParameterizedCurve
    assert type(two) is SampledParameterizedCurve
    assert one.warnings[0].code is SamplingWarningCode.VIEWPORT_CLIPPED
    assert one.warnings[0].metrics.clipped_segment_count == 1  # type: ignore[union-attr]
    assert two.warnings[0].metrics.clipped_segment_count == 2  # type: ignore[union-attr]


def test_residual_precision_warning_and_hard_error_thresholds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    epsilon = Fraction(1, 1 << 52)
    plan = _approved(viewport=_viewport(-4.0, 4.0, -1.0, 4.0))
    monkeypatch.setattr(
        samplers,
        "normalized_parabola_residual",
        lambda *args: 33 * epsilon,
    )
    warned = sample_parameterized_curve(plan)
    assert type(warned) is SampledParameterizedCurve
    assert any(
        warning.code is SamplingWarningCode.SAMPLING_PRECISION_LIMITED
        for warning in warned.warnings
    )
    monkeypatch.setattr(
        samplers,
        "normalized_parabola_residual",
        lambda *args: 257 * epsilon,
    )
    failed = sample_parameterized_curve(plan)
    assert type(failed) is ErrorInfo
    assert failed.code is ErrorCode.NUMERIC_RANGE_UNSUPPORTED


@pytest.mark.parametrize(
    "field_name",
    [
        "final_x_bytes",
        "final_y_bytes",
        "artist_data_bytes",
        "segment_index_range_bytes",
        "segment_metadata_bytes",
        "parameter_batch_bytes",
        "transcendental_workspace_bytes",
        "validation_workspace_bytes",
        "rgba_canvas_bytes",
        "png_buffer_reserve_bytes",
        "png_copy_bytes",
    ],
)
def test_receipt_rejects_every_budget_field_tamper_before_allocation(
    field_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _approved()
    assert plan.memory_budget is not None
    tampered_budget = replace(plan.memory_budget)
    object.__setattr__(
        tampered_budget,
        field_name,
        getattr(tampered_budget, field_name) + 1,
    )
    tampered = replace(plan, memory_budget=tampered_budget)

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("receipt tamper must fail before allocation")

    monkeypatch.setattr(samplers.np, "empty", forbidden)
    result = sample_parameterized_curve(tampered)
    assert type(result) is ErrorInfo
    assert result.code is ErrorCode.INTERNAL_ERROR


@pytest.mark.parametrize(
    "target",
    ["spec", "opening", "viewport", "interval", "policy", "version", "output"],
)
def test_receipt_rejects_semantic_tamper_before_allocation(
    target: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _approved()
    if target == "spec":
        spec = plan.scene_spec.items[0]
        assert type(spec) is ParabolaSpec
        scene = PlotSceneSpec((replace(spec, vertex_x=spec.vertex_x + 1),))
        tampered = replace(plan, scene_spec=scene)
    elif target == "opening":
        spec = plan.scene_spec.items[0]
        assert type(spec) is ParabolaSpec
        object.__setattr__(spec, "opening", ParabolaOpening.DOWN)
        tampered = plan
    elif target == "viewport":
        tampered = replace(
            plan,
            resolved_viewport=replace(plan.resolved_viewport, x_min=-4.0),
        )
    elif target == "interval":
        assert type(plan.item_plan) is GeometryRenderItemPlan
        interval = _intervals(plan)[0]
        item_plan = replace(
            plan.item_plan,
            segments=(replace(interval, parameter_start=interval.parameter_start + 0.01),),
        )
        tampered = replace(plan, item_plan=item_plan)
    elif target == "policy":
        tampered = replace(plan, sampling_policy_version="parabolic-sampling-policy-v2")
    elif target == "version":
        tampered = replace(plan, parameterized_sampler_contract_version="other")
    else:
        tampered = replace(plan, image_width=plan.image_width + 1)

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("receipt tamper must fail before allocation")

    monkeypatch.setattr(samplers.np, "empty", forbidden)
    result = sample_parameterized_curve(tampered)
    assert type(result) is ErrorInfo
    assert result.code is ErrorCode.INTERNAL_ERROR


def test_batch_size_does_not_change_sample_coordinates() -> None:
    original = _approved(viewport=_viewport(-4.0, 4.0, -1.0, 4.0))
    assert type(original.item_plan) is GeometryRenderItemPlan
    baseline = sample_parameterized_curve(original)
    assert type(baseline) is SampledParameterizedCurve
    small_item_plan = replace(original.item_plan, batch_size=1)
    small_budget = build_parabola_parameterized_memory_budget(
        sample_count=small_item_plan.sample_count,
        batch_size=1,
        image_width=original.image_width,
        image_height=original.image_height,
        limits=DEFAULT_LIMITS,
    )
    small = render_plan_model._approve_render_plan(
        replace(original, item_plan=small_item_plan, memory_budget=small_budget),
    )
    sampled_small = sample_parameterized_curve(small)
    assert type(sampled_small) is SampledParameterizedCurve
    assert np.array_equal(baseline.x, sampled_small.x)
    assert np.array_equal(baseline.y, sampled_small.y)
    assert np.array_equal(baseline.segment_ranges, sampled_small.segment_ranges)


class _CountingProbe:
    def __init__(self, cancel_on: int | None = None) -> None:
        self.count = 0
        self.cancel_on = cancel_on

    def is_cancelled(self) -> bool:
        self.count += 1
        return self.cancel_on is not None and self.count >= self.cancel_on


def test_every_reached_parabola_cancellation_checkpoint_is_neutral() -> None:
    plan = _approved(viewport=_viewport(-4.0, 4.0, -1.0, 4.0))
    counter = _CountingProbe()
    successful = sample_parameterized_curve(plan, cancellation_probe=counter)
    assert type(successful) is SampledParameterizedCurve
    assert counter.count >= 10
    for target in range(1, counter.count + 1):
        result = sample_parameterized_curve(
            plan,
            cancellation_probe=_CountingProbe(target),
        )
        assert type(result) is SamplingCancelled


def test_sampler_does_not_reenter_resolver_builder_or_interval_planner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _approved()

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("approved parabola sampler must only consume its plan")

    monkeypatch.setattr(viewport_resolver, "resolve_single_item_viewport", forbidden)
    monkeypatch.setattr(render_plan_builder, "RenderPlanBuilder", forbidden)
    monkeypatch.setattr(render_plan_builder, "_plan_visible_parabola_intervals", forbidden)
    result = sample_parameterized_curve(plan)
    assert type(result) is SampledParameterizedCurve


def test_sampler_signature_and_static_stage_boundaries_remain_frozen() -> None:
    assert tuple(signature(sample_parameterized_curve).parameters) == (
        "plan",
        "cancellation_probe",
    )
    assert not hasattr(public_engine, "sample_parabola")
    package_root = Path(__file__).resolve().parents[2] / "math_drawing_assistant"
    for relative in (
        "engine/renderer.py",
        "engine/scene_executor.py",
        "workers/render_actor.py",
        "app_controller.py",
    ):
        source = (package_root / relative).read_text(encoding="utf-8")
        assert "parabola_geometry" not in source
    geometry_source = (package_root / "engine/parabola_geometry.py").read_text(
        encoding="utf-8",
    )
    assert "contour" not in geometry_source.lower()


def test_manual_multi_item_parabola_remains_outside_single_item_stage() -> None:
    scene = PlotSceneSpec((_spec("x^2=4*y", item_id="a"), _spec("y^2=4*x", item_id="b")))
    result = resolve_single_item_viewport(
        scene,
        ViewportRequest(
            mode=ViewportMode.MANUAL,
            x_min=-5,
            x_max=5,
            y_min=-5,
            y_max=5,
        ),
    )
    assert result.error is not None
    assert result.error.code is ErrorCode.INVALID_REQUEST


def test_parameterized_budget_values_are_finite_and_plan_uses_same_formula() -> None:
    plan = _approved()
    assert type(plan.item_plan) is GeometryRenderItemPlan
    expected = build_parabola_parameterized_memory_budget(
        sample_count=plan.item_plan.sample_count,
        batch_size=plan.item_plan.batch_size,
        image_width=plan.image_width,
        image_height=plan.image_height,
        limits=DEFAULT_LIMITS,
    )
    assert plan.memory_budget == expected
    assert all(
        isfinite(float(getattr(expected, field.name)))
        for field in fields(expected)
    )
