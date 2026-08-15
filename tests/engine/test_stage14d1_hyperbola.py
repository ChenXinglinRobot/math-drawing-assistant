"""Stage 14D-1 HyperbolaSpec viewport, plan, budget, and sampler contracts."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace
from fractions import Fraction
from math import asinh, ceil, cosh, hypot, inf, isfinite, nextafter, sinh, ulp

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
from math_drawing_assistant.engine.hyperbola_geometry import (
    normalized_hyperbola_residual,
    project_hyperbola_geometry,
)
from math_drawing_assistant.engine.parameterized_budget import (
    _HYPERBOLA_EXACT_LIVE_BIGINT_VALUES,
    _axis_aligned_conic_exact_max_integer_bits,
    build_hyperbola_parameterized_memory_budget,
    estimate_hyperbola_exact_workspace_bytes,
    plan_hyperbola_batch_size,
)
from math_drawing_assistant.models import (
    AspectRequest,
    AxisOrientation,
    DEFAULT_HYPERBOLIC_SAMPLING_POLICY,
    ErrorCode,
    ErrorInfo,
    GeometryRenderItemPlan,
    HyperbolaSpec,
    HyperbolicSamplingPolicy,
    InputSource,
    PARAMETERIZED_SAMPLER_CONTRACT_VERSION,
    ParameterIntervalPlan,
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
    validate_approved_render_plan,
)
from math_drawing_assistant.models import render_plan as render_plan_model


def _spec(text: str, *, item_id: str = "hyperbola-item") -> HyperbolaSpec:
    result = analyze_plot_item(
        PlotItemRequest(
            item_id=item_id,
            input_text=text,
            input_source=InputSource.MANUAL,
            requested_plot_kind=PlotKind.AUTO,
            display_order=0,
        ),
    )
    assert type(result) is HyperbolaSpec, result
    return result


def _scene(text: str, *, item_id: str = "hyperbola-item") -> PlotSceneSpec:
    return PlotSceneSpec((_spec(text, item_id=item_id),))


def _viewport(
    x_min: float = -10.0,
    x_max: float = 10.0,
    y_min: float = -8.0,
    y_max: float = 8.0,
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
    text: str = "x^2/9-y^2/4=1",
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
    text: str = "x^2/9-y^2/4=1",
    viewport: ResolvedViewport | None = None,
) -> RenderPlan:
    result = _build(text, viewport)
    assert type(result) is RenderPlan, result
    return result


def _intervals(plan: RenderPlan) -> tuple[ParameterIntervalPlan, ...]:
    assert type(plan.item_plan) is GeometryRenderItemPlan
    assert all(type(value) is ParameterIntervalPlan for value in plan.item_plan.segments)
    return plan.item_plan.segments  # type: ignore[return-value]


def test_hyperbolic_policy_is_exact_frozen_slots_v1_and_public_identity() -> None:
    policy = DEFAULT_HYPERBOLIC_SAMPLING_POLICY
    assert type(policy) is HyperbolicSamplingPolicy
    assert tuple(getattr(policy, field.name) for field in fields(policy)) == (
        "hyperbolic-sampling-policy-v1",
        1,
        2,
        4_096,
        8,
        8,
        32,
        256,
        256,
    )
    assert public_models.HyperbolicSamplingPolicy is HyperbolicSamplingPolicy
    assert public_models.DEFAULT_HYPERBOLIC_SAMPLING_POLICY is policy
    with pytest.raises(FrozenInstanceError):
        policy.samples_per_pixel = 2  # type: ignore[misc]
    assert not hasattr(policy, "__dict__")
    assert "HyperbolaExecutionGeometry" not in public_engine.__all__
    assert "project_hyperbola_geometry" not in public_engine.__all__


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
def test_hyperbolic_policy_rejects_invalid_values(
    field_name: str,
    value: object,
    error_type: type[Exception],
) -> None:
    with pytest.raises(error_type):
        replace(DEFAULT_HYPERBOLIC_SAMPLING_POLICY, **{field_name: value})


def test_hyperbolic_policy_v1_rejects_same_version_substitution() -> None:
    with pytest.raises(ValueError, match="semantics are fixed"):
        replace(DEFAULT_HYPERBOLIC_SAMPLING_POLICY, preferred_batch_points=2_048)
    assert RENDER_PLAN_CONTRACT_VERSION == "render-plan-v2-typed-geometry"
    assert PARAMETERIZED_SAMPLER_CONTRACT_VERSION == "parameterized-sampler-v1"


@pytest.mark.parametrize(
    ("text", "expected_bounds"),
    [
        ("x^2/9-y^2/4=1", (-5.242640687119286, 5.242640687119286, -3.0, 3.0)),
        ("y^2/4-x^2/9=1", (-4.0, 4.0, -3.8284271247461903, 3.8284271247461903)),
        (
            "(x-5)^2/9-(y+7)^2/4=1",
            (-0.24264068711928566, 10.242640687119286, -10.0, -4.0),
        ),
    ],
)
def test_auto_hyperbola_viewport_uses_outward_teaching_window_padding_and_equal_default(
    text: str,
    expected_bounds: tuple[float, float, float, float],
) -> None:
    result = resolve_single_item_viewport(_scene(text), ViewportRequest())
    assert result.error is None
    assert result.warning is None
    assert result.viewport is not None
    viewport = result.viewport
    assert viewport.source is ViewportSource.AUTO_GEOMETRY
    assert viewport.aspect is ResolvedAspect.EQUAL
    assert (
        viewport.x_min,
        viewport.x_max,
        viewport.y_min,
        viewport.y_max,
    ) == pytest.approx(expected_bounds)

    geometry = project_hyperbola_geometry(_spec(text))
    assert viewport.x_min <= geometry.auto_x_lower < geometry.auto_x_upper <= viewport.x_max
    assert viewport.y_min <= geometry.auto_y_lower < geometry.auto_y_upper <= viewport.y_max
    teaching = asinh(1.0)
    assert teaching > 0.0


@pytest.mark.parametrize(
    ("aspect", "resolved"),
    [(AspectRequest.AUTO, ResolvedAspect.AUTO), (AspectRequest.EQUAL, ResolvedAspect.EQUAL)],
)
def test_auto_hyperbola_explicit_aspect_wins(
    aspect: AspectRequest,
    resolved: ResolvedAspect,
) -> None:
    result = resolve_single_item_viewport(
        _scene("x^2/9-y^2/4=1"),
        ViewportRequest(aspect_request=aspect),
    )
    assert result.viewport is not None
    assert result.viewport.aspect is resolved


@pytest.mark.parametrize("field_name", ["x_min", "x_max", "y_min", "y_max"])
def test_auto_hyperbola_rejects_every_explicit_bound(field_name: str) -> None:
    result = resolve_single_item_viewport(
        _scene("x^2/9-y^2/4=1"),
        replace(ViewportRequest(), **{field_name: 0}),
    )
    assert result.error is not None
    assert result.error.code is ErrorCode.INVALID_VIEWPORT
    assert result.error.field_name == field_name


def test_auto_hyperbola_workspace_gate_precedes_projection_and_never_probes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene = _scene("x^2/9-y^2/4=1")
    estimate = estimate_hyperbola_exact_workspace_bytes(DEFAULT_LIMITS)

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("hyperbola auto viewport must not probe, execute, or project")

    monkeypatch.setattr(viewport_resolver.np, "linspace", forbidden)
    monkeypatch.setattr(viewport_resolver, "execute_explicit_function", forbidden)
    monkeypatch.setattr(viewport_resolver, "estimate_numeric_execution_cost", forbidden)
    monkeypatch.setattr(viewport_resolver, "project_hyperbola_geometry", forbidden)
    result = resolve_single_item_viewport(
        scene,
        ViewportRequest(),
        limits=replace(DEFAULT_LIMITS, max_viewport_probe_bytes=estimate - 1),
    )
    assert result.error is not None
    assert result.error.code is ErrorCode.VIEWPORT_PROBE_BUDGET_EXCEEDED


def test_auto_hyperbola_extreme_range_is_typed_without_fallback() -> None:
    spec = _spec("x^2/9-y^2/4=1")
    huge = replace(spec, center_x=Fraction(10**400))
    result = resolve_single_item_viewport(
        PlotSceneSpec((huge,)),
        ViewportRequest(),
    )
    assert result.error is not None
    assert result.error.code is ErrorCode.NUMERIC_RANGE_UNSUPPORTED
    assert result.viewport is None


def test_auto_hyperbola_uses_relative_padding_and_translates_at_coordinate_limit() -> None:
    relative = resolve_single_item_viewport(
        _scene("x^2/1000000-y^2/250000=1"),
        ViewportRequest(),
    )
    assert relative.viewport is not None
    geometry = project_hyperbola_geometry(_spec("x^2/1000000-y^2/250000=1"))
    x_data_span = geometry.auto_x_upper - geometry.auto_x_lower
    y_data_span = geometry.auto_y_upper - geometry.auto_y_lower
    assert relative.viewport.x_max - relative.viewport.x_min == pytest.approx(
        1.2 * x_data_span,
    )
    assert relative.viewport.y_max - relative.viewport.y_min == pytest.approx(
        1.2 * y_data_span,
    )

    translated_spec = replace(
        _spec("x^2/9-y^2/4=1"),
        center_x=Fraction(DEFAULT_LIMITS.max_viewport_absolute_coordinate - 5),
    )
    translated = resolve_single_item_viewport(
        PlotSceneSpec((translated_spec,)),
        ViewportRequest(),
    )
    assert translated.viewport is not None
    assert translated.viewport.x_max == float(
        DEFAULT_LIMITS.max_viewport_absolute_coordinate,
    )
    assert translated.viewport.x_min < translated.viewport.x_max


def test_successful_auto_hyperbola_never_calls_explicit_probe_or_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("hyperbola AUTO_GEOMETRY must not use explicit probing")

    monkeypatch.setattr(viewport_resolver.np, "linspace", forbidden)
    monkeypatch.setattr(viewport_resolver, "execute_explicit_function", forbidden)
    monkeypatch.setattr(viewport_resolver, "estimate_numeric_execution_cost", forbidden)
    monkeypatch.setattr(viewport_resolver, "_fallback_resolution", forbidden)
    result = resolve_single_item_viewport(
        _scene("x^2/9-y^2/4=1"),
        ViewportRequest(),
    )
    assert result.viewport is not None
    assert result.viewport.source is ViewportSource.AUTO_GEOMETRY


@pytest.mark.parametrize(
    ("text", "axis"),
    [
        ("x^2/9-y^2/4=1", AxisOrientation.HORIZONTAL),
        ("y^2/4-x^2/9=1", AxisOrientation.VERTICAL),
    ],
)
def test_direct_full_pipeline_has_stable_branch_semantics(
    text: str,
    axis: AxisOrientation,
) -> None:
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
    assert type(plan.item_plan) is GeometryRenderItemPlan
    assert plan.item_plan.mathematical_branch_count == 2
    assert plan.item_plan.max_segment_count == 4
    intervals = _intervals(plan)
    assert [interval.mathematical_branch_id for interval in intervals] == [0, 1]
    assert all(interval.closure is SegmentClosure.OPEN for interval in intervals)
    assert intervals == tuple(
        sorted(intervals, key=lambda value: (value.mathematical_branch_id, value.parameter_start)),
    )

    sampled = sample_parameterized_curve(plan)
    assert type(sampled) is SampledParameterizedCurve, sampled
    assert sampled.x.flags.owndata and not sampled.x.flags.writeable
    assert sampled.y.flags.owndata and not sampled.y.flags.writeable
    assert sampled.segment_ranges.flags.owndata and not sampled.segment_ranges.flags.writeable
    assert sampled.x.dtype == sampled.y.dtype == np.dtype(np.float64)
    assert sampled.segment_ranges.dtype == np.dtype(np.int64)
    assert [metadata.mathematical_branch_id for metadata in sampled.segment_metadata] == [0, 1]
    first_points = tuple(
        (sampled.x[int(start)], sampled.y[int(start)])
        for start, _ in sampled.segment_ranges
    )
    if axis is AxisOrientation.HORIZONTAL:
        assert first_points[0][0] < 0.0 < first_points[1][0]
    else:
        assert first_points[0][1] < 0.0 < first_points[1][1]
    assert [warning.code for warning in sampled.warnings] == [
        SamplingWarningCode.VIEWPORT_CLIPPED,
    ]
    assert sampled.warnings[0].metrics.clipped_segment_count == len(intervals)  # type: ignore[union-attr]
    geometry = project_hyperbola_geometry(_spec(text))
    for interval, (start, stop) in zip(intervals, sampled.segment_ranges):
        expected_start = render_plan_builder.hyperbola_parameter_point(
            geometry,
            interval.mathematical_branch_id,
            interval.parameter_start,
        )
        expected_stop = render_plan_builder.hyperbola_parameter_point(
            geometry,
            interval.mathematical_branch_id,
            interval.parameter_stop,
        )
        assert (sampled.x[int(start)], sampled.y[int(start)]) == expected_start
        assert (sampled.x[int(stop) - 1], sampled.y[int(stop) - 1]) == expected_stop
    tolerance_x = DEFAULT_HYPERBOLIC_SAMPLING_POLICY.viewport_boundary_ulps * max(
        ulp(resolution.viewport.x_min),
        ulp(resolution.viewport.x_max),
        ulp(resolution.viewport.x_max - resolution.viewport.x_min),
    )
    tolerance_y = DEFAULT_HYPERBOLIC_SAMPLING_POLICY.viewport_boundary_ulps * max(
        ulp(resolution.viewport.y_min),
        ulp(resolution.viewport.y_max),
        ulp(resolution.viewport.y_max - resolution.viewport.y_min),
    )
    assert np.all(sampled.x >= resolution.viewport.x_min - tolerance_x)
    assert np.all(sampled.x <= resolution.viewport.x_max + tolerance_x)
    assert np.all(sampled.y >= resolution.viewport.y_min - tolerance_y)
    assert np.all(sampled.y <= resolution.viewport.y_max + tolerance_y)


def test_visible_interval_topologies_cover_single_branch_split_two_branches_and_none() -> None:
    single = _approved(viewport=_viewport(3.0, 10.0, -8.0, 8.0))
    assert {interval.mathematical_branch_id for interval in _intervals(single)} == {1}

    split = _approved(viewport=_viewport(5.0, 10.0, -8.0, 8.0))
    split_intervals = _intervals(split)
    assert len(split_intervals) == 2
    assert {interval.mathematical_branch_id for interval in split_intervals} == {1}
    assert split_intervals[0].parameter_stop <= split_intervals[1].parameter_start

    both = _approved(viewport=_viewport(-10.0, 10.0, -8.0, 8.0))
    assert {interval.mathematical_branch_id for interval in _intervals(both)} == {0, 1}

    tangent = _build(viewport=_viewport(2.0, 3.0, -1.0, 1.0))
    assert type(tangent) is ErrorInfo
    assert tangent.code in {ErrorCode.NO_VISIBLE_CURVE, ErrorCode.NUMERIC_RANGE_UNSUPPORTED}
    invisible = _build(viewport=_viewport(-1.0, 1.0, -1.0, 1.0))
    assert type(invisible) is ErrorInfo
    assert invisible.code is ErrorCode.NO_VISIBLE_CURVE


def test_exact_branch_rejection_precedes_any_parameter_root_conversion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    geometry = project_hyperbola_geometry(_spec("x^2/9-y^2/4=1"))

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("exact branch rejection must precede asinh/acosh")

    monkeypatch.setattr(render_plan_builder, "_finite_asinh_root", forbidden)
    monkeypatch.setattr(render_plan_builder, "_finite_acosh_root", forbidden)
    result = render_plan_builder._plan_visible_hyperbola_intervals(
        geometry,
        _viewport(-1.0, 1.0, -8.0, 8.0),
        policy=DEFAULT_HYPERBOLIC_SAMPLING_POLICY,
    )
    assert type(result) is ErrorInfo
    assert result.code is ErrorCode.NO_VISIBLE_CURVE


def test_hyperbola_sample_count_uses_endpoint_pixel_derivative_bound() -> None:
    viewport = _viewport(-10.0, 10.0, -8.0, 8.0)
    plan = _approved(viewport=viewport)
    geometry = project_hyperbola_geometry(_spec("x^2/9-y^2/4=1"))
    for interval in _intervals(plan):
        maximum_parameter = max(abs(interval.parameter_start), abs(interval.parameter_stop))
        x_speed = (
            geometry.outward_semi_transverse
            * abs(sinh(maximum_parameter))
            * 800
            / (viewport.x_max - viewport.x_min)
        )
        y_speed = (
            geometry.outward_semi_conjugate
            * cosh(maximum_parameter)
            * 600
            / (viewport.y_max - viewport.y_min)
        )
        expected = max(
            2,
            ceil(
                hypot(x_speed, y_speed)
                * (interval.parameter_stop - interval.parameter_start),
            )
            + 1,
        )
        assert interval.sample_count == expected


def test_hyperbola_budget_fields_sums_batch_and_exact_workspace_contract() -> None:
    sample_count = 100
    batch_size = 20
    budget = build_hyperbola_parameterized_memory_budget(
        sample_count=sample_count,
        batch_size=batch_size,
        image_width=10,
        image_height=20,
        limits=DEFAULT_LIMITS,
    )
    exact = estimate_hyperbola_exact_workspace_bytes(DEFAULT_LIMITS)
    assert len(_HYPERBOLA_EXACT_LIVE_BIGINT_VALUES) == 49
    assert budget.final_x_bytes == budget.final_y_bytes == sample_count * 8
    assert budget.artist_data_bytes == 2 * sample_count * 8
    assert budget.segment_index_range_bytes == 4 * 2 * 8
    assert budget.segment_metadata_bytes == 4 * 2 * 8
    assert budget.parameter_batch_bytes == batch_size * 8
    assert budget.transcendental_workspace_bytes == 2 * batch_size * 8
    assert budget.validation_workspace_bytes == (
        exact + 12 * 8 + 12 + 4 * 2 * 8 + batch_size + batch_size * 8
    )
    assert budget.rgba_canvas_bytes == 10 * 20 * 4
    assert budget.png_buffer_reserve_bytes == DEFAULT_LIMITS.max_png_bytes
    assert budget.png_copy_bytes == DEFAULT_LIMITS.max_png_bytes
    assert budget.total_bytes == budget.fixed_bytes + budget.batch_bytes
    assert plan_hyperbola_batch_size(
        sample_count=10_000,
        preferred_batch_points=4_096,
        image_width=100,
        image_height=100,
        limits=DEFAULT_LIMITS,
    ) == 4_096


def test_hyperbola_exact_workspace_is_monotonic_and_bit_bound_covers_witness() -> None:
    minimum_digits = max(
        6 * DEFAULT_LIMITS.max_equation_coefficient_denominator_digits,
        DEFAULT_LIMITS.max_equation_coefficient_numerator_digits
        + 5 * DEFAULT_LIMITS.max_equation_coefficient_denominator_digits,
    )
    custom_limits = tuple(
        replace(DEFAULT_LIMITS, max_equation_canonical_coefficient_digits=value)
        for value in (minimum_digits, minimum_digits + 1, minimum_digits + 32)
    )
    bounds = tuple(
        (
            _axis_aligned_conic_exact_max_integer_bits(limits),
            estimate_hyperbola_exact_workspace_bytes(limits),
        )
        for limits in custom_limits
    )
    assert all(
        next_bits > bits and next_bytes >= byte_count
        for (bits, byte_count), (next_bits, next_bytes) in zip(bounds, bounds[1:])
    )
    coefficient_bits = 4 * DEFAULT_LIMITS.max_equation_canonical_coefficient_digits
    float_bits = 1_075
    witness_bits = 5 * coefficient_bits + 2 * float_bits + 6
    assert witness_bits <= _axis_aligned_conic_exact_max_integer_bits(DEFAULT_LIMITS)


def test_hyperbola_exact_workspace_is_shared_across_resolver_builder_and_sampler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exact_workspace = estimate_hyperbola_exact_workspace_bytes(DEFAULT_LIMITS)
    calls: list[tuple[str, int]] = []
    original_resolver_estimate = viewport_resolver.estimate_hyperbola_exact_workspace_bytes
    original_builder_budget = render_plan_builder.build_hyperbola_parameterized_memory_budget
    original_sampler_budget = samplers.build_hyperbola_parameterized_memory_budget

    def resolver_estimate(*args: object, **kwargs: object) -> int:
        result = original_resolver_estimate(*args, **kwargs)  # type: ignore[arg-type]
        calls.append(("resolver", result))
        return result

    def builder_budget(*args: object, **kwargs: object) -> object:
        result = original_builder_budget(*args, **kwargs)  # type: ignore[arg-type]
        calls.append(("builder", result.validation_workspace_bytes))
        return result

    def sampler_budget(*args: object, **kwargs: object) -> object:
        result = original_sampler_budget(*args, **kwargs)  # type: ignore[arg-type]
        calls.append(("sampler", result.validation_workspace_bytes))
        return result

    monkeypatch.setattr(
        viewport_resolver,
        "estimate_hyperbola_exact_workspace_bytes",
        resolver_estimate,
    )
    monkeypatch.setattr(
        render_plan_builder,
        "build_hyperbola_parameterized_memory_budget",
        builder_budget,
    )
    monkeypatch.setattr(
        samplers,
        "build_hyperbola_parameterized_memory_budget",
        sampler_budget,
    )

    scene = _scene("x^2/9-y^2/4=1")
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
    assert type(sample_parameterized_curve(plan)) is SampledParameterizedCurve
    assert calls[0] == ("resolver", exact_workspace)
    overhead = plan.memory_budget.validation_workspace_bytes - exact_workspace
    assert calls[-2:] == [
        ("builder", exact_workspace + overhead),
        ("sampler", exact_workspace + overhead),
    ]


def test_hyperbola_full_budget_boundary_rejects_before_receipt_issue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = _approved()
    assert type(baseline.item_plan) is GeometryRenderItemPlan
    required = build_hyperbola_parameterized_memory_budget(
        sample_count=baseline.item_plan.sample_count,
        batch_size=1,
        image_width=baseline.image_width,
        image_height=baseline.image_height,
        limits=DEFAULT_LIMITS,
    )
    issued: list[int] = []
    original_approve = render_plan_builder._approve_render_plan

    def approve(plan: RenderPlan) -> RenderPlan:
        assert plan.memory_budget is not None
        issued.append(plan.memory_budget.total_bytes)
        return original_approve(plan)

    monkeypatch.setattr(render_plan_builder, "_approve_render_plan", approve)
    approved = _build(
        builder=RenderPlanBuilder(
            limits=replace(DEFAULT_LIMITS, max_estimated_memory_bytes=required.total_bytes),
        ),
    )
    assert type(approved) is RenderPlan
    assert approved.memory_budget == required
    issued.clear()
    rejected = _build(
        builder=RenderPlanBuilder(
            limits=replace(DEFAULT_LIMITS, max_estimated_memory_bytes=required.total_bytes - 1),
        ),
    )
    assert type(rejected) is ErrorInfo
    assert rejected.code is ErrorCode.RESOURCE_LIMIT_EXCEEDED
    assert issued == []


def test_builder_point_segment_and_memory_limits_remain_hard() -> None:
    point_result = _build(
        builder=RenderPlanBuilder(
            limits=replace(
                DEFAULT_LIMITS,
                max_sample_points_per_item=10,
                max_total_sample_points=10,
            ),
        ),
    )
    assert type(point_result) is ErrorInfo
    assert point_result.code is ErrorCode.RESOURCE_LIMIT_EXCEEDED

    segment_result = _build(
        builder=RenderPlanBuilder(
            limits=replace(
                DEFAULT_LIMITS,
                max_branches_per_item=3,
                max_total_branches=3,
            ),
        ),
    )
    assert type(segment_result) is ErrorInfo
    assert segment_result.code is ErrorCode.RESOURCE_LIMIT_EXCEEDED

    memory_result = _build(
        builder=RenderPlanBuilder(
            limits=replace(DEFAULT_LIMITS, max_estimated_memory_bytes=1),
        ),
    )
    assert type(memory_result) is ErrorInfo
    assert memory_result.code is ErrorCode.RESOURCE_LIMIT_EXCEEDED


def test_private_projection_and_samples_are_finite_with_exact_residual() -> None:
    for text in ("x^2/9-y^2/4=1", "y^2/4-x^2/9=1"):
        geometry = project_hyperbola_geometry(_spec(text))
        assert all(
            isfinite(value)
            for value in (
                geometry.center_x_float,
                geometry.center_y_float,
                geometry.semi_transverse_float,
                geometry.semi_conjugate_float,
                geometry.outward_semi_transverse,
                geometry.outward_semi_conjugate,
                geometry.max_safe_parameter,
            )
        )
        sampled = sample_parameterized_curve(_approved(text))
        assert type(sampled) is SampledParameterizedCurve
        assert np.all(np.isfinite(sampled.x))
        assert np.all(np.isfinite(sampled.y))
        assert all(
            normalized_hyperbola_residual(geometry, float(x_value), float(y_value))
            <= DEFAULT_HYPERBOLIC_SAMPLING_POLICY.maximum_residual_ulps
            * Fraction(1, 1 << 52)
            for x_value, y_value in zip(sampled.x, sampled.y)
        )


def test_projection_rejects_underflow_overflow_branch_collapse_and_unsafe_parameter() -> None:
    base = _spec("x^2/9-y^2/4=1")
    with pytest.raises(OverflowError):
        project_hyperbola_geometry(
            replace(base, semi_transverse_squared=Fraction(1, 10**2_000)),
        )
    with pytest.raises(OverflowError):
        project_hyperbola_geometry(
            replace(base, semi_transverse_squared=Fraction(10**2_000)),
        )
    with pytest.raises(OverflowError, match="branches collapse"):
        project_hyperbola_geometry(
            replace(base, center_x=Fraction(1 << 54), semi_transverse_squared=Fraction(1)),
        )

    tiny = project_hyperbola_geometry(
        replace(
            base,
            semi_transverse_squared=Fraction(1, 10**600),
            semi_conjugate_squared=Fraction(1, 10**600),
        ),
    )
    point = render_plan_builder.hyperbola_parameter_point(tiny, 1, 700.0)
    assert all(isfinite(value) for value in point)
    with pytest.raises(OverflowError):
        render_plan_builder.hyperbola_parameter_point(
            tiny,
            1,
            nextafter(tiny.max_safe_parameter, inf),
        )


@pytest.mark.parametrize(
    "target",
    [
        "center",
        "axis_square",
        "axis_enum",
        "viewport",
        "branch",
        "parameter_start",
        "parameter_stop",
        "sample_count",
        "closure",
        "policy",
        "sampler_version",
        "plan_version",
        "budget",
        "image_width",
        "image_height",
        "dpi",
        "show_grid",
        "item_id",
    ],
)
def test_receipt_rejects_every_hyperbola_contract_tamper(target: str) -> None:
    plan = _approved()
    assert type(plan.item_plan) is GeometryRenderItemPlan
    interval = _intervals(plan)[0]
    spec = plan.scene_spec.items[0]
    if target == "center":
        object.__setattr__(spec, "center_x", Fraction(1))
    elif target == "axis_square":
        object.__setattr__(spec, "semi_transverse_squared", Fraction(10))
    elif target == "axis_enum":
        object.__setattr__(spec, "transverse_axis", AxisOrientation.VERTICAL)
    elif target == "viewport":
        object.__setattr__(plan.resolved_viewport, "x_min", -9.0)
    elif target == "branch":
        object.__setattr__(interval, "mathematical_branch_id", 1)
    elif target == "parameter_start":
        object.__setattr__(interval, "parameter_start", interval.parameter_start + 0.01)
    elif target == "parameter_stop":
        object.__setattr__(interval, "parameter_stop", interval.parameter_stop - 0.01)
    elif target == "sample_count":
        object.__setattr__(interval, "sample_count", interval.sample_count + 1)
    elif target == "closure":
        object.__setattr__(interval, "closure", SegmentClosure.CLOSED)
    elif target == "policy":
        object.__setattr__(plan, "sampling_policy_version", "tampered")
    elif target == "sampler_version":
        object.__setattr__(plan, "parameterized_sampler_contract_version", "tampered")
    elif target == "plan_version":
        object.__setattr__(plan, "plan_version", "tampered")
    elif target == "budget":
        object.__setattr__(
            plan.memory_budget,
            "validation_workspace_bytes",
            plan.memory_budget.validation_workspace_bytes + 1,
        )
    elif target == "image_width":
        object.__setattr__(plan, "image_width", plan.image_width + 1)
    elif target == "image_height":
        object.__setattr__(plan, "image_height", plan.image_height + 1)
    elif target == "dpi":
        object.__setattr__(plan, "dpi", plan.dpi + 1)
    elif target == "show_grid":
        object.__setattr__(plan, "show_grid", not plan.show_grid)
    else:
        object.__setattr__(plan.item_plan, "item_id", "tampered")
    with pytest.raises(ValueError):
        validate_approved_render_plan(plan)


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
def test_receipt_rejects_tampering_of_every_budget_field(field_name: str) -> None:
    plan = _approved()
    value = getattr(plan.memory_budget, field_name)
    object.__setattr__(plan.memory_budget, field_name, value + 1)
    with pytest.raises((TypeError, ValueError)):
        validate_approved_render_plan(plan)


def test_approval_rejects_unsorted_overlapping_or_wrong_branch_intervals() -> None:
    plan = _approved()
    assert type(plan.item_plan) is GeometryRenderItemPlan
    count = plan.item_plan.sample_count // 2
    invalid_sets = (
        (
            ParameterIntervalPlan(1, -1.0, 1.0, count, SegmentClosure.OPEN),
            ParameterIntervalPlan(0, -1.0, 1.0, plan.item_plan.sample_count - count, SegmentClosure.OPEN),
        ),
        (
            ParameterIntervalPlan(0, -1.0, 0.5, count, SegmentClosure.OPEN),
            ParameterIntervalPlan(0, 0.0, 1.0, plan.item_plan.sample_count - count, SegmentClosure.OPEN),
        ),
        (
            ParameterIntervalPlan(2, -1.0, 0.0, count, SegmentClosure.OPEN),
            ParameterIntervalPlan(2, 0.0, 1.0, plan.item_plan.sample_count - count, SegmentClosure.OPEN),
        ),
    )
    for intervals in invalid_sets:
        with pytest.raises((TypeError, ValueError)):
            render_plan_model._approve_render_plan(
                replace(plan, item_plan=replace(plan.item_plan, segments=intervals)),
            )


def test_sampler_validates_receipt_and_recomputed_budget_before_allocation(
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


def test_sampler_recomputes_a_signed_budget_mismatch_before_first_allocation(
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
        raise AssertionError("signed budget mismatch must fail before output allocation")

    monkeypatch.setattr(samplers.np, "empty", forbidden)
    result = sample_parameterized_curve(signed_mismatch)
    assert type(result) is ErrorInfo
    assert result.code is ErrorCode.INTERNAL_ERROR


@pytest.mark.parametrize(
    ("residual_ulps", "expected"),
    [
        (33, SamplingWarningCode.SAMPLING_PRECISION_LIMITED),
        (257, ErrorCode.NUMERIC_RANGE_UNSUPPORTED),
    ],
)
def test_sampler_precision_warning_and_hard_residual_error(
    residual_ulps: int,
    expected: SamplingWarningCode | ErrorCode,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        samplers,
        "normalized_hyperbola_residual",
        lambda *args: residual_ulps * Fraction(1, 1 << 52),
    )
    result = sample_parameterized_curve(_approved())
    if residual_ulps > 256:
        assert type(result) is ErrorInfo
        assert result.code is expected
    else:
        assert type(result) is SampledParameterizedCurve
        assert [warning.code for warning in result.warnings] == [
            SamplingWarningCode.VIEWPORT_CLIPPED,
            expected,
        ]


def test_sampler_rejects_nonfinite_batch_and_float64_segment_collapse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_sinh = samplers.np.sinh
    monkeypatch.setattr(
        samplers.np,
        "sinh",
        lambda parameter: np.full(parameter.shape, np.inf, dtype=np.float64),
    )
    nonfinite = sample_parameterized_curve(_approved())
    assert type(nonfinite) is ErrorInfo
    assert nonfinite.code is ErrorCode.NUMERIC_RANGE_UNSUPPORTED

    monkeypatch.setattr(samplers.np, "sinh", original_sinh)
    monkeypatch.setattr(
        samplers,
        "_hyperbola_scalar_point",
        lambda geometry, branch, parameter: (geometry.center_x_float, geometry.center_y_float),
    )
    monkeypatch.setattr(
        samplers.np,
        "sinh",
        lambda parameter: np.zeros(parameter.shape, dtype=np.float64),
    )
    monkeypatch.setattr(
        samplers.np,
        "cosh",
        lambda parameter: np.zeros(parameter.shape, dtype=np.float64),
    )
    monkeypatch.setattr(samplers, "normalized_hyperbola_residual", lambda *args: Fraction(0))
    collapsed = sample_parameterized_curve(_approved())
    assert type(collapsed) is ErrorInfo
    assert collapsed.code is ErrorCode.NUMERIC_RANGE_UNSUPPORTED


class _CountingProbe:
    def __init__(self, cancel_on: int | None = None) -> None:
        self.cancel_on = cancel_on
        self.count = 0

    def is_cancelled(self) -> bool:
        self.count += 1
        return self.cancel_on is not None and self.count >= self.cancel_on


def test_every_reached_hyperbola_cancellation_checkpoint_is_neutral() -> None:
    plan = _approved()
    counter = _CountingProbe()
    successful = sample_parameterized_curve(plan, cancellation_probe=counter)
    assert type(successful) is SampledParameterizedCurve
    assert counter.count >= 25
    item_id = plan.scene_spec.items[0].item_id
    for target in range(1, counter.count + 1):
        probe = _CountingProbe(cancel_on=target)
        result = sample_parameterized_curve(plan, cancellation_probe=probe)
        assert type(result) is SamplingCancelled
        assert result.item_id == item_id
        assert probe.count == target


def test_sampler_does_not_reenter_resolver_builder_or_interval_planner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _approved()

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("approved hyperbola sampler must only consume its plan")

    monkeypatch.setattr(viewport_resolver, "resolve_single_item_viewport", forbidden)
    monkeypatch.setattr(render_plan_builder, "_plan_visible_hyperbola_intervals", forbidden)
    result = sample_parameterized_curve(plan)
    assert type(result) is SampledParameterizedCurve


def test_parabola_is_active_while_contour_application_layers_remain_untouched() -> None:
    item = analyze_plot_item(
        PlotItemRequest("p", "x^2=4*y", InputSource.MANUAL, PlotKind.AUTO, 0),
    )
    assert not isinstance(item, ErrorInfo)
    resolution = resolve_single_item_viewport(PlotSceneSpec((item,)), ViewportRequest())
    assert resolution.error is None
    assert resolution.viewport is not None
    assert resolution.viewport.source is ViewportSource.AUTO_GEOMETRY

    for path in (
        "math_drawing_assistant/engine/renderer.py",
        "math_drawing_assistant/engine/scene_executor.py",
        "math_drawing_assistant/workers/render_actor.py",
        "math_drawing_assistant/app_controller.py",
    ):
        assert "hyperbola_geometry" not in open(path, encoding="utf-8").read()
    assert "contour" not in open(
        "math_drawing_assistant/engine/hyperbola_geometry.py",
        encoding="utf-8",
    ).read().lower()
