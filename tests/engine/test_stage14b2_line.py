"""Stage 14B-2 exact general-line viewport, plan, receipt, and sampler tests."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace
from fractions import Fraction
from inspect import signature
from math import isfinite
from pathlib import Path
import sys

import numpy as np
import pytest

from math_drawing_assistant.config import DEFAULT_LIMITS
from math_drawing_assistant.engine import (
    ParameterizedSamplingDiagnostics,
    RenderPlanBuilder,
    SampledParameterizedCurve,
    SamplingCancelled,
    SamplingWarningCode,
    analyze_plot_item,
    resolve_single_explicit_viewport,
    resolve_single_item_viewport,
    sample_parameterized_curve,
)
from math_drawing_assistant.engine import render_plan_builder, samplers, viewport_resolver
from math_drawing_assistant.engine.parameterized_budget import (
    build_line_parameterized_memory_budget,
    estimate_line_exact_workspace_bytes,
)
from math_drawing_assistant.models import (
    AspectRequest,
    CircleSpec,
    DEFAULT_LINE_SAMPLING_POLICY,
    EllipseSpec,
    ErrorCode,
    ErrorInfo,
    ExplicitFunctionSpec,
    GeometryRenderItemPlan,
    HyperbolaSpec,
    InputSource,
    LineSamplingPolicy,
    LineSegmentPlan,
    LineSpec,
    PARAMETERIZED_SAMPLER_CONTRACT_VERSION,
    ParameterizedRenderMemoryBudget,
    ParabolaSpec,
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


def _spec(text: str, *, item_id: str = "line-item") -> ExplicitFunctionSpec | LineSpec | CircleSpec | EllipseSpec | HyperbolaSpec | ParabolaSpec:
    result = analyze_plot_item(
        PlotItemRequest(
            item_id=item_id,
            input_text=text,
            input_source=InputSource.MANUAL,
            requested_plot_kind=PlotKind.AUTO,
            display_order=0,
        ),
    )
    assert not isinstance(result, ErrorInfo), result
    return result


def _scene(text: str, *, item_id: str = "line-item") -> PlotSceneSpec:
    return PlotSceneSpec(items=(_spec(text, item_id=item_id),))


def _manual_request(
    *,
    x_min: float = -10.0,
    x_max: float = 10.0,
    y_min: float = -8.0,
    y_max: float = 8.0,
    aspect: AspectRequest = AspectRequest.DEFAULT,
) -> ViewportRequest:
    return ViewportRequest(
        mode=ViewportMode.MANUAL,
        x_min=x_min,
        x_max=x_max,
        y_min=y_min,
        y_max=y_max,
        aspect_request=aspect,
    )


def _viewport(
    *,
    x_min: float = -10.0,
    x_max: float = 10.0,
    y_min: float = -8.0,
    y_max: float = 8.0,
    aspect: ResolvedAspect = ResolvedAspect.AUTO,
    source: ViewportSource = ViewportSource.MANUAL,
) -> ResolvedViewport:
    return ResolvedViewport(x_min, x_max, y_min, y_max, aspect, source)


def _build(
    text: str,
    *,
    viewport: ResolvedViewport | None = None,
    builder: RenderPlanBuilder | None = None,
) -> RenderPlan | ErrorInfo:
    return (builder or RenderPlanBuilder()).build(
        _scene(text),
        viewport or _viewport(),
        image_width=800,
        image_height=600,
        dpi=96,
        show_grid=True,
        show_legend=False,
    )


def _approved(text: str = "x+y=1") -> RenderPlan:
    result = _build(text)
    assert type(result) is RenderPlan, result
    return result


def _segment(plan: RenderPlan) -> LineSegmentPlan:
    assert type(plan.item_plan) is GeometryRenderItemPlan
    assert len(plan.item_plan.segments) == 1
    segment = plan.item_plan.segments[0]
    assert type(segment) is LineSegmentPlan
    return segment


def test_line_policy_is_exact_frozen_slots_active_v1() -> None:
    policy = DEFAULT_LINE_SAMPLING_POLICY
    assert type(policy) is LineSamplingPolicy
    assert {field.name for field in fields(policy)} == {
        "version",
        "sample_count",
        "batch_size",
        "endpoint_merge_ulps",
        "target_residual_ulps",
        "maximum_residual_ulps",
        "cancellation_check_interval",
    }
    assert (
        policy.version,
        policy.sample_count,
        policy.batch_size,
        policy.endpoint_merge_ulps,
        policy.target_residual_ulps,
        policy.maximum_residual_ulps,
        policy.cancellation_check_interval,
    ) == ("line-sampling-policy-v1", 2, 1, 2, 4, 16, 1)
    assert not hasattr(policy, "__dict__")
    with pytest.raises(FrozenInstanceError):
        policy.sample_count = 3  # type: ignore[misc]


@pytest.mark.parametrize(
    "changes",
    [
        {"sample_count": 1},
        {"batch_size": 3},
        {"endpoint_merge_ulps": 0},
        {"target_residual_ulps": 16},
        {"maximum_residual_ulps": 4},
        {"cancellation_check_interval": 0},
        {"sample_count": 3},
    ],
)
def test_line_policy_rejects_invalid_or_alternate_v1_semantics(
    changes: dict[str, int],
) -> None:
    values = {
        "version": "line-sampling-policy-v1",
        "sample_count": 2,
        "batch_size": 1,
        "endpoint_merge_ulps": 2,
        "target_residual_ulps": 4,
        "maximum_residual_ulps": 16,
        "cancellation_check_interval": 1,
    }
    values.update(changes)
    with pytest.raises((TypeError, ValueError)):
        LineSamplingPolicy(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("x=2", (-8.0, 12.0, -10.0, 10.0)),
        ("x+y=x", (-10.0, 10.0, -10.0, 10.0)),
        ("x+y=1", (-9.5, 10.5, -9.5, 10.5)),
    ],
)
def test_auto_line_default_centers_fixed_spans_and_uses_geometry_source(
    text: str,
    expected: tuple[float, float, float, float],
) -> None:
    result = resolve_single_item_viewport(_scene(text), ViewportRequest())
    assert result.error is None
    assert result.warning is None
    assert result.viewport is not None
    assert (
        result.viewport.x_min,
        result.viewport.x_max,
        result.viewport.y_min,
        result.viewport.y_max,
    ) == expected
    assert result.viewport.aspect is ResolvedAspect.AUTO
    assert result.viewport.source is ViewportSource.AUTO_GEOMETRY


def test_auto_line_complete_x_is_preserved_and_derives_padded_y_exactly() -> None:
    request = ViewportRequest(
        mode=ViewportMode.AUTO,
        x_min=2.0,
        x_max=4.0,
        aspect_request=AspectRequest.EQUAL,
    )
    result = resolve_single_item_viewport(_scene("x+y=1"), request)
    assert result.viewport is not None
    assert (result.viewport.x_min, result.viewport.x_max) == (2.0, 4.0)
    assert (result.viewport.y_min, result.viewport.y_max) == (-4.0, 0.0)
    assert result.viewport.aspect is ResolvedAspect.EQUAL


def test_auto_vertical_line_with_complete_x_uses_fallback_y_span_about_zero() -> None:
    request = ViewportRequest(mode=ViewportMode.AUTO, x_min=-5.0, x_max=5.0)
    result = resolve_single_item_viewport(_scene("x=2"), request)
    assert result.viewport is not None
    assert (result.viewport.x_min, result.viewport.x_max) == (-5.0, 5.0)
    assert (result.viewport.y_min, result.viewport.y_max) == (-10.0, 10.0)


@pytest.mark.parametrize(
    "viewport_request",
    [
        ViewportRequest(mode=ViewportMode.AUTO, x_min=-1.0),
        ViewportRequest(mode=ViewportMode.AUTO, y_min=-1.0),
        ViewportRequest(mode=ViewportMode.AUTO, y_max=1.0),
    ],
)
def test_auto_line_rejects_partial_x_and_all_explicit_y(
    viewport_request: ViewportRequest,
) -> None:
    result = resolve_single_item_viewport(_scene("x+y=1"), viewport_request)
    assert result.error is not None
    assert result.error.code is ErrorCode.INVALID_VIEWPORT


def test_manual_line_preserves_bounds_source_and_explicit_aspect() -> None:
    request = _manual_request(aspect=AspectRequest.EQUAL)
    result = resolve_single_item_viewport(_scene("x=2"), request)
    assert result.viewport == _viewport(
        aspect=ResolvedAspect.EQUAL,
        source=ViewportSource.MANUAL,
    )


def test_line_auto_workspace_is_rejected_before_exact_arithmetic_when_over_budget() -> None:
    limits = replace(DEFAULT_LIMITS, max_viewport_probe_bytes=1)
    result = resolve_single_item_viewport(_scene("x+y=1"), ViewportRequest(), limits=limits)
    assert result.error is not None
    assert result.error.code is ErrorCode.VIEWPORT_PROBE_BUDGET_EXCEEDED
    assert result.error.field_name == "max_viewport_probe_bytes"


def test_auto_line_with_extreme_legal_primitive_coefficients_stays_bounded() -> None:
    coefficient = 10**127 - 1
    result = resolve_single_item_viewport(
        _scene(f"{coefficient}*x+{coefficient - 1}*y+1=0"),
        ViewportRequest(),
    )
    assert result.error is None
    assert result.viewport is not None
    assert all(
        isfinite(value)
        for value in (
            result.viewport.x_min,
            result.viewport.x_max,
            result.viewport.y_min,
            result.viewport.y_max,
        )
    )


def test_auto_line_anchor_outside_supported_viewport_has_no_fallback() -> None:
    result = resolve_single_item_viewport(
        _scene(f"x={10**127}"),
        ViewportRequest(),
    )
    assert result.error is not None
    assert result.error.code is ErrorCode.NUMERIC_RANGE_UNSUPPORTED
    assert result.viewport is None


@pytest.mark.parametrize(
    "text",
    ["x^2+y^2=25", "4*x^2+9*y^2=36", "4*x^2-9*y^2=36", "x^2=4*y"],
)
def test_conic_auto_viewport_remains_stage14b1_strategy_error(text: str) -> None:
    result = resolve_single_item_viewport(_scene(text), ViewportRequest())
    assert result.error is not None
    assert result.error.code is ErrorCode.INTERNAL_ERROR
    assert result.error.field_name == "viewport_strategy"


def test_explicit_viewport_wrapper_remains_bit_for_bit_equivalent() -> None:
    scene = _scene("y=x^2")
    request = ViewportRequest()
    assert resolve_single_item_viewport(scene, request) == resolve_single_explicit_viewport(
        scene,
        request,
    )


def test_resolved_viewport_never_contains_request_default_enum() -> None:
    result = resolve_single_item_viewport(_scene("x=2"), ViewportRequest())
    assert result.viewport is not None
    assert type(result.viewport.aspect) is ResolvedAspect
    assert result.viewport.aspect is not AspectRequest.DEFAULT


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("x=2", (2.0, -8.0, 2.0, 8.0)),
        ("x+y=x", (10.0, 0.0, -10.0, 0.0)),
        ("x+y=1", (9.0, -8.0, -7.0, 8.0)),
        ("x-y+3=0", (-10.0, -7.0, 5.0, 8.0)),
        ("x+y-3=0", (10.0, -7.0, -5.0, 8.0)),
        ("x+y=18", (10.0, 8.0, 10.0, 8.0)),
    ],
)
def test_exact_four_edge_intersection_and_stable_projection_order(
    text: str,
    expected: tuple[float, float, float, float],
) -> None:
    result = _build(text)
    if expected[0:2] == expected[2:4]:
        assert type(result) is ErrorInfo
        assert result.code is ErrorCode.NO_VISIBLE_CURVE
        return
    assert type(result) is RenderPlan, result
    segment = _segment(result)
    assert (segment.x0, segment.y0, segment.x1, segment.y1) == expected


@pytest.mark.parametrize(
    "text",
    ["x=-10", "x=10", "x+y=x-8", "x+y=x+8"],
)
def test_each_viewport_edge_collinearity_produces_two_corners(text: str) -> None:
    plan = _approved(text)
    segment = _segment(plan)
    assert (segment.x0, segment.y0) != (segment.x1, segment.y1)
    assert all(
        -10.0 <= value_x <= 10.0 and -8.0 <= value_y <= 8.0
        for value_x, value_y in (
            (segment.x0, segment.y0),
            (segment.x1, segment.y1),
        )
    )


@pytest.mark.parametrize("text", ["x=20", "x+y=19"])
def test_invisible_or_single_corner_line_returns_no_visible_curve(text: str) -> None:
    result = _build(text)
    assert type(result) is ErrorInfo
    assert result.code is ErrorCode.NO_VISIBLE_CURVE


def test_exact_distinct_near_corner_intersections_collapse_under_two_ulps() -> None:
    coefficient = 10**16
    result = _build(
        f"{coefficient}*x+{coefficient}*y={2 * coefficient + 1}",
        viewport=_viewport(x_min=1.0, x_max=2.0, y_min=1.0, y_max=2.0),
    )
    assert type(result) is ErrorInfo
    assert result.code is ErrorCode.NO_VISIBLE_CURVE


def test_extreme_legal_viewport_and_coefficients_produce_finite_segment() -> None:
    result = _build(
        "2*x=18000001",
        viewport=_viewport(
            x_min=9_000_000.0,
            x_max=9_000_001.0,
            y_min=9_000_000.0,
            y_max=9_000_001.0,
        ),
    )
    assert type(result) is RenderPlan, result
    segment = _segment(result)
    assert (segment.x0, segment.y0, segment.x1, segment.y1) == (
        9_000_000.5,
        9_000_000.0,
        9_000_000.5,
        9_000_001.0,
    )


def test_successful_line_plan_has_one_finite_distinct_segment_and_normalized_residual() -> None:
    plan = _approved("2*x-y+3=0")
    assert validate_approved_render_plan(plan) is plan
    assert type(plan.item_plan) is GeometryRenderItemPlan
    assert plan.item_plan.mathematical_branch_count == 1
    assert plan.item_plan.max_segment_count == 1
    assert plan.item_plan.sample_count == 2
    assert plan.item_plan.batch_size == 1
    segment = _segment(plan)
    spec = plan.scene_spec.items[0]
    assert type(spec) is LineSpec
    for x_value, y_value in ((segment.x0, segment.y0), (segment.x1, segment.y1)):
        assert isfinite(x_value) and isfinite(y_value)
        numerator = abs(spec.d * Fraction.from_float(x_value) + spec.e * Fraction.from_float(y_value) + spec.f)
        scale = (
            abs(spec.d) * max(Fraction(1), abs(Fraction.from_float(x_value)))
            + abs(spec.e) * max(Fraction(1), abs(Fraction.from_float(y_value)))
            + abs(spec.f)
        )
        assert numerator / scale <= Fraction(16, 1 << 52)


def test_line_budget_fields_fixed_batch_and_total_are_exact() -> None:
    plan = _approved()
    assert type(plan.memory_budget) is ParameterizedRenderMemoryBudget
    budget = plan.memory_budget
    max_bits = 4 * DEFAULT_LIMITS.max_equation_canonical_coefficient_digits + 2 * 1074 + 2
    bigint_digits = (
        max_bits + sys.int_info.bits_per_digit - 1
    ) // sys.int_info.bits_per_digit
    exact_workspace = 28 * (
        sys.getsizeof(0) + bigint_digits * sys.int_info.sizeof_digit
    )
    assert estimate_line_exact_workspace_bytes(DEFAULT_LIMITS) == exact_workspace
    assert budget == build_line_parameterized_memory_budget(
        image_width=800,
        image_height=600,
        limits=DEFAULT_LIMITS,
    )
    assert (
        budget.final_x_bytes,
        budget.final_y_bytes,
        budget.artist_data_bytes,
        budget.segment_index_range_bytes,
        budget.segment_metadata_bytes,
        budget.parameter_batch_bytes,
        budget.transcendental_workspace_bytes,
        budget.validation_workspace_bytes,
    ) == (
        16,
        16,
        32,
        16,
        16,
        16,
        0,
        exact_workspace + 4 * 17 + 4 * 8 + 2 * 8,
    )
    assert budget.fixed_bytes + budget.batch_bytes == budget.total_bytes
    assert not hasattr(budget, "executor_extra_batch_bytes")


@pytest.mark.parametrize(
    "limits",
    [
        replace(DEFAULT_LIMITS, max_sample_points_per_item=1),
        replace(
            DEFAULT_LIMITS,
            max_sample_points_per_item=1,
            max_total_sample_points=1,
        ),
        replace(DEFAULT_LIMITS, max_estimated_memory_bytes=1),
    ],
)
def test_line_plan_resource_limits_reject_before_approval(limits: object) -> None:
    result = _build("x+y=1", builder=RenderPlanBuilder(limits=limits))  # type: ignore[arg-type]
    assert type(result) is ErrorInfo
    assert result.code is ErrorCode.RESOURCE_LIMIT_EXCEEDED


def test_line_plan_versions_and_receipt_are_exact() -> None:
    plan = _approved()
    assert plan.plan_version == RENDER_PLAN_CONTRACT_VERSION
    assert plan.limits_version == DEFAULT_LIMITS.version
    assert plan.sampling_policy_version == DEFAULT_LINE_SAMPLING_POLICY.version
    assert plan.numeric_executor_contract_version is None
    assert plan.parameterized_sampler_contract_version == PARAMETERIZED_SAMPLER_CONTRACT_VERSION
    assert plan._approval_receipt is not None


def _tamper(plan: RenderPlan, target: str) -> None:
    assert type(plan.item_plan) is GeometryRenderItemPlan
    assert type(plan.memory_budget) is ParameterizedRenderMemoryBudget
    segment = _segment(plan)
    spec = plan.scene_spec.items[0]
    assert type(spec) is LineSpec
    if target in {"x0", "y0", "x1", "y1"}:
        object.__setattr__(segment, target, getattr(segment, target) + 0.25)
    elif target == "item_id":
        object.__setattr__(plan.item_plan, target, "tampered")
    elif target in {
        "mathematical_branch_count",
        "sample_count",
        "batch_size",
        "max_segment_count",
    }:
        object.__setattr__(plan.item_plan, target, getattr(plan.item_plan, target) + 1)
    elif target in {"x_min", "x_max", "y_min", "y_max"}:
        object.__setattr__(plan.resolved_viewport, target, getattr(plan.resolved_viewport, target) + 0.25)
    elif target == "aspect":
        object.__setattr__(plan.resolved_viewport, target, ResolvedAspect.EQUAL)
    elif target == "source":
        object.__setattr__(plan.resolved_viewport, target, ViewportSource.AUTO_GEOMETRY)
    elif target in {
        "sampling_policy_version",
        "parameterized_sampler_contract_version",
    }:
        object.__setattr__(plan, target, "tampered-version")
    elif target == "numeric_executor_contract_version":
        object.__setattr__(plan, target, "tampered-version")
    elif target == "coefficient":
        object.__setattr__(spec.coefficients, "f", spec.f + 1)
    elif target == "provenance":
        object.__setattr__(spec.provenance, "normalized_input", "tampered")
    else:
        object.__setattr__(plan.memory_budget, target, getattr(plan.memory_budget, target) + 1)


@pytest.mark.parametrize(
    "target",
    [
        "x0", "y0", "x1", "y1", "item_id", "mathematical_branch_count",
        "sample_count", "batch_size", "max_segment_count", "x_min", "x_max",
        "y_min", "y_max", "aspect", "source", "sampling_policy_version",
        "parameterized_sampler_contract_version", "numeric_executor_contract_version",
        "coefficient", "provenance", "final_x_bytes", "final_y_bytes",
        "artist_data_bytes", "segment_index_range_bytes", "segment_metadata_bytes",
        "parameter_batch_bytes", "transcendental_workspace_bytes",
        "validation_workspace_bytes", "rgba_canvas_bytes", "png_buffer_reserve_bytes",
        "png_copy_bytes",
    ],
)
def test_every_line_receipt_field_tamper_is_rejected_before_allocation(
    target: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _approved()
    receipt = plan._approval_receipt
    _tamper(plan, target)

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("tampered receipt must fail before allocation")

    monkeypatch.setattr(samplers.np, "empty", forbidden)
    result = sample_parameterized_curve(plan)
    assert type(result) is ErrorInfo
    assert result.code is ErrorCode.INTERNAL_ERROR
    assert plan._approval_receipt is receipt


def test_unapproved_line_plan_is_rejected_before_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approved = _approved()
    ordinary = replace(approved)

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("unapproved plan must fail before allocation")

    monkeypatch.setattr(samplers.np, "empty", forbidden)
    result = sample_parameterized_curve(ordinary)
    assert type(result) is ErrorInfo
    assert result.code is ErrorCode.INTERNAL_ERROR


@pytest.mark.parametrize(
    "text",
    ["x^2+y^2=25", "4*x^2+9*y^2=36", "4*x^2-9*y^2=36", "x^2=4*y"],
)
def test_builder_does_not_approve_conics(text: str) -> None:
    result = _build(text)
    assert type(result) is ErrorInfo
    assert result.code is ErrorCode.INTERNAL_ERROR
    assert result.field_name == "geometry_strategy"


def test_parameterized_sampler_public_signature_is_exact() -> None:
    assert tuple(signature(sample_parameterized_curve).parameters) == (
        "plan",
        "cancellation_probe",
    )
    assert signature(sample_parameterized_curve).parameters["cancellation_probe"].kind.name == "KEYWORD_ONLY"


def test_parameterized_sampler_returns_owned_frozen_typed_line_result() -> None:
    plan = _approved("2*x-y+3=0")
    original_viewport = plan.resolved_viewport
    result = sample_parameterized_curve(plan)
    assert type(result) is SampledParameterizedCurve, result
    assert result.item_id == "line-item"
    assert result.x.dtype == np.dtype(np.float64)
    assert result.y.dtype == np.dtype(np.float64)
    assert result.segment_ranges.dtype == np.dtype(np.int64)
    assert result.x.flags.owndata and not result.x.flags.writeable
    assert result.y.flags.owndata and not result.y.flags.writeable
    assert result.segment_ranges.flags.owndata and not result.segment_ranges.flags.writeable
    assert result.segment_ranges.tolist() == [[0, 2]]
    assert result.segment_metadata[0].mathematical_branch_id == 0
    assert result.segment_metadata[0].closure is SegmentClosure.OPEN
    assert result.visible_segment_count == 1
    assert result.diagnostics == ParameterizedSamplingDiagnostics(1, 2)
    assert result.warnings[0].code is SamplingWarningCode.VIEWPORT_CLIPPED
    assert [warning.code for warning in result.warnings] == [
        SamplingWarningCode.VIEWPORT_CLIPPED,
    ]
    assert result._plan_contract_snapshot is not None
    assert samplers._sampled_parameterized_curve_matches_approved_plan(result, plan)
    assert plan.resolved_viewport is original_viewport


def _approved_with_first_endpoint_residual(residual_ulps: int) -> RenderPlan:
    plan = _approved("x=0")
    assert type(plan.item_plan) is GeometryRenderItemPlan
    shifted_segment = replace(
        _segment(plan),
        x0=float(Fraction(residual_ulps, 1 << 52)),
    )
    item_plan = replace(plan.item_plan, segments=(shifted_segment,))
    return render_plan_model._approve_render_plan(replace(plan, item_plan=item_plan))


def test_parameterized_sampler_reports_target_to_hard_residual_warning() -> None:
    result = sample_parameterized_curve(_approved_with_first_endpoint_residual(5))
    assert type(result) is SampledParameterizedCurve, result
    assert [warning.code for warning in result.warnings] == [
        SamplingWarningCode.VIEWPORT_CLIPPED,
        SamplingWarningCode.SAMPLING_PRECISION_LIMITED,
    ]


def test_parameterized_sampler_rejects_residual_above_hard_threshold() -> None:
    result = sample_parameterized_curve(_approved_with_first_endpoint_residual(17))
    assert type(result) is ErrorInfo
    assert result.code is ErrorCode.NUMERIC_RANGE_UNSUPPORTED


class _CancelOnCall:
    def __init__(self, target: int) -> None:
        self.target = target
        self.calls = 0

    def is_cancelled(self) -> bool:
        self.calls += 1
        return self.calls >= self.target


@pytest.mark.parametrize("target", [1, 2, 3, 4, 5, 6])
def test_parameterized_sampler_cancels_at_each_frozen_checkpoint(target: int) -> None:
    result = sample_parameterized_curve(_approved(), cancellation_probe=_CancelOnCall(target))
    assert type(result) is SamplingCancelled
    assert result.item_id == "line-item"


def test_approval_precedes_already_cancelled_probe() -> None:
    plan = _approved()
    object.__setattr__(plan, "sampling_policy_version", "tampered")
    probe = _CancelOnCall(1)
    result = sample_parameterized_curve(plan, cancellation_probe=probe)
    assert type(result) is ErrorInfo
    assert probe.calls == 0


def test_parameterized_sampler_revalidates_full_budget_before_first_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _approved()
    calls: list[str] = []
    original_budget = samplers.build_line_parameterized_memory_budget
    original_validate = DEFAULT_LIMITS.validate_scene_resources
    original_empty = samplers.np.empty

    def budget(*args: object, **kwargs: object) -> object:
        calls.append("budget")
        return original_budget(*args, **kwargs)  # type: ignore[arg-type]

    def validate(_self: object, *args: object, **kwargs: object) -> object:
        calls.append("validate")
        return original_validate(*args, **kwargs)  # type: ignore[arg-type]

    def empty(*args: object, **kwargs: object) -> object:
        calls.append("empty")
        return original_empty(*args, **kwargs)

    monkeypatch.setattr(samplers, "build_line_parameterized_memory_budget", budget)
    monkeypatch.setattr(type(DEFAULT_LIMITS), "validate_scene_resources", validate)
    monkeypatch.setattr(samplers.np, "empty", empty)
    result = sample_parameterized_curve(plan)
    assert type(result) is SampledParameterizedCurve
    assert calls[:3] == ["budget", "validate", "empty"]


def test_sampler_does_not_call_resolver_intersection_or_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _approved()

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("sampler must consume only the approved segment")

    monkeypatch.setattr(viewport_resolver, "resolve_single_item_viewport", forbidden)
    monkeypatch.setattr(render_plan_builder, "_line_segment_for_viewport", forbidden)
    monkeypatch.setattr(RenderPlanBuilder, "build", forbidden)
    assert type(sample_parameterized_curve(plan)) is SampledParameterizedCurve


@pytest.mark.parametrize("text", ["x=2", "x+y=1", "2*x-y+3=0"])
def test_direct_line_prototype_uses_analyzer_scene_resolver_builder_sampler_only(
    text: str,
) -> None:
    spec = _spec(text)
    assert type(spec) is LineSpec
    scene = PlotSceneSpec(items=(spec,))
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
    assert type(plan) is RenderPlan, plan
    assert type(sample_parameterized_curve(plan)) is SampledParameterizedCurve


def test_stage14b2_keeps_renderer_scene_executor_and_contour_boundaries() -> None:
    package_root = Path(__file__).parents[2] / "math_drawing_assistant"
    scene_source = (package_root / "engine" / "scene_executor.py").read_text(encoding="utf-8")
    renderer_source = (package_root / "engine" / "renderer.py").read_text(encoding="utf-8")
    assert "GeometryRenderItemPlan" not in scene_source
    assert "LineSpec" not in scene_source
    assert "SampledParameterizedCurve" not in renderer_source
    for path in (package_root / "engine").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert ".contour(" not in source
