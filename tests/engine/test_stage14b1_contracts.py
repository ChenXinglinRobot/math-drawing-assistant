"""Stage 14B-1 public contracts without geometry sampling algorithms."""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from fractions import Fraction
from inspect import signature
from math import tau
from pathlib import Path
from typing import get_args

import numpy as np
import pytest

import math_drawing_assistant.engine as public_engine
import math_drawing_assistant.models as public_models
from math_drawing_assistant.config import DEFAULT_LIMITS
from math_drawing_assistant.engine import (
    ParameterizedSamplingDiagnostics,
    RenderPlanBuilder,
    SampledExplicitFunction,
    SampledParameterizedCurve,
    SampledSegmentMetadata,
    SamplingPrecisionLimitedMetrics,
    SamplingWarning,
    SamplingWarningCode,
    ViewportClippedMetrics,
    analyze_plot_item,
    resolve_single_explicit_viewport,
    resolve_single_item_viewport,
    sample_explicit_function,
    sample_parameterized_curve,
)
from math_drawing_assistant.engine import render_plan_builder, viewport_resolver
from math_drawing_assistant.models import (
    AspectRequest,
    AxisOrientation,
    CircleSpec,
    DEFAULT_ANGULAR_SAMPLING_POLICY,
    DEFAULT_LINE_SAMPLING_POLICY,
    EllipseSpec,
    ErrorCode,
    ErrorInfo,
    ExplicitFunctionSpec,
    GeometryRenderItemPlan,
    GeometrySegmentPlan,
    HyperbolaSpec,
    InputSource,
    LineSegmentPlan,
    LineSpec,
    PARAMETERIZED_SAMPLER_CONTRACT_VERSION,
    ParameterIntervalPlan,
    ParameterizedRenderMemoryBudget,
    ParabolaOpening,
    ParabolaSpec,
    PlotItemRequest,
    PlotItemSpec,
    PlotKind,
    PlotSceneSpec,
    RENDER_PLAN_CONTRACT_VERSION,
    RenderItemPlan,
    RenderMemoryBudget,
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


_GEOMETRY_CASES = (
    ("x=2", LineSpec, ResolvedAspect.AUTO),
    ("x^2+y^2=25", CircleSpec, ResolvedAspect.EQUAL),
    ("4*x^2+9*y^2=36", EllipseSpec, ResolvedAspect.EQUAL),
    ("4*x^2-9*y^2=36", HyperbolaSpec, ResolvedAspect.EQUAL),
    ("x^2=4*y", ParabolaSpec, ResolvedAspect.EQUAL),
)


def _spec(text: str, *, item_id: str = "stage14b1-item") -> PlotItemSpec:
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


def _scene(text: str, *, item_id: str = "stage14b1-item") -> PlotSceneSpec:
    return PlotSceneSpec(items=(_spec(text, item_id=item_id),))


def _manual_request(
    aspect: AspectRequest = AspectRequest.DEFAULT,
) -> ViewportRequest:
    return ViewportRequest(
        mode=ViewportMode.MANUAL,
        x_min=-10,
        x_max=10,
        y_min=-8,
        y_max=8,
        aspect_request=aspect,
    )


def _viewport() -> ResolvedViewport:
    return ResolvedViewport(
        x_min=-10,
        x_max=10,
        y_min=-8,
        y_max=8,
        aspect=ResolvedAspect.EQUAL,
        source=ViewportSource.MANUAL,
    )


def _parameterized_budget() -> ParameterizedRenderMemoryBudget:
    return ParameterizedRenderMemoryBudget(
        final_x_bytes=64,
        final_y_bytes=64,
        artist_data_bytes=128,
        segment_index_range_bytes=64,
        segment_metadata_bytes=64,
        parameter_batch_bytes=32,
        transcendental_workspace_bytes=48,
        validation_workspace_bytes=16,
        rgba_canvas_bytes=1_024,
        png_buffer_reserve_bytes=2_048,
        png_copy_bytes=2_048,
    )


def _explicit_budget() -> RenderMemoryBudget:
    return RenderMemoryBudget(
        final_x_bytes=16,
        final_y_bytes=16,
        artist_data_bytes=32,
        validity_mask_bytes=2,
        segment_index_range_bytes=16,
        segment_metadata_bytes=16,
        executor_extra_batch_bytes=8,
        rgba_canvas_bytes=1_024,
        png_buffer_reserve_bytes=2_048,
        png_copy_bytes=2_048,
    )


def _geometry_item_plan(spec: PlotItemSpec) -> GeometryRenderItemPlan:
    if type(spec) is LineSpec:
        segments: tuple[GeometrySegmentPlan, ...] = (
            LineSegmentPlan(x0=-1.0, y0=-1.0, x1=1.0, y1=1.0),
        )
        branches = 1
        capacity = 1
    elif type(spec) in {CircleSpec, EllipseSpec}:
        segments = (
            ParameterIntervalPlan(
                mathematical_branch_id=0,
                parameter_start=0.0,
                parameter_stop=tau,
                sample_count=64,
                closure=SegmentClosure.CLOSED,
            ),
        )
        branches = 1
        capacity = 4
    else:
        intervals = [
            ParameterIntervalPlan(
                mathematical_branch_id=0,
                parameter_start=-1.0,
                parameter_stop=1.0,
                sample_count=4,
                closure=(
                    SegmentClosure.CLOSED
                    if type(spec) in {CircleSpec, EllipseSpec}
                    else SegmentClosure.OPEN
                ),
            ),
        ]
        branches = 2 if type(spec) is HyperbolaSpec else 1
        if type(spec) is HyperbolaSpec:
            intervals.append(
                ParameterIntervalPlan(
                    mathematical_branch_id=1,
                    parameter_start=-1.0,
                    parameter_stop=1.0,
                    sample_count=4,
                    closure=SegmentClosure.OPEN,
                ),
            )
        segments = tuple(intervals)
        capacity = 2 if type(spec) is ParabolaSpec else 4
    return GeometryRenderItemPlan(
        item_id=spec.item_id,
        mathematical_branch_count=branches,
        segments=segments,
        sample_count=sum(segment.sample_count for segment in segments),
        batch_size=(1 if type(spec) is LineSpec else 2),
        max_segment_count=capacity,
    )


def _approved_geometry_plan(text: str) -> RenderPlan:
    scene = _scene(text)
    spec = scene.items[0]
    if type(spec) in {HyperbolaSpec, ParabolaSpec}:
        built = RenderPlanBuilder().build(
            scene,
            _viewport(),
            image_width=800,
            image_height=600,
            dpi=96,
            show_grid=True,
            show_legend=False,
        )
        assert type(built) is RenderPlan, built
        return built
    plan = RenderPlan(
        scene_spec=scene,
        resolved_viewport=_viewport(),
        image_width=800,
        image_height=600,
        dpi=96,
        plan_version=RENDER_PLAN_CONTRACT_VERSION,
        limits_version=DEFAULT_LIMITS.version,
        show_grid=True,
        show_legend=False,
        sampling_policy_version=(
            DEFAULT_LINE_SAMPLING_POLICY.version
            if type(spec) is LineSpec
            else (
                DEFAULT_ANGULAR_SAMPLING_POLICY.version
                if type(spec) in {CircleSpec, EllipseSpec}
                else "parameterized-policy-test"
            )
        ),
        numeric_executor_contract_version=None,
        parameterized_sampler_contract_version=(
            PARAMETERIZED_SAMPLER_CONTRACT_VERSION
        ),
        item_plan=_geometry_item_plan(spec),
        memory_budget=_parameterized_budget(),
    )
    return render_plan_model._approve_render_plan(plan)


def _explicit_plan() -> RenderPlan:
    scene = _scene("y=x")
    result = RenderPlanBuilder().build(
        scene,
        ResolvedViewport(
            x_min=-10,
            x_max=10,
            y_min=-10,
            y_max=10,
            aspect=ResolvedAspect.AUTO,
            source=ViewportSource.MANUAL,
        ),
        image_width=320,
        image_height=240,
        dpi=96,
        show_grid=True,
        show_legend=False,
    )
    assert type(result) is RenderPlan, result
    return result


def _readonly_vector(values: list[float]) -> np.ndarray:
    result = np.array(values, dtype=np.float64)
    result.setflags(write=False)
    return result


def _readonly_ranges(values: list[list[int]]) -> np.ndarray:
    result = np.array(values, dtype=np.int64)
    result.setflags(write=False)
    return result


def test_request_and_resolved_aspect_are_disjoint_exact_enums() -> None:
    assert ViewportRequest().aspect_request is AspectRequest.DEFAULT
    assert {member.name for member in AspectRequest} == {"DEFAULT", "AUTO", "EQUAL"}
    assert {member.name for member in ResolvedAspect} == {"AUTO", "EQUAL"}
    assert AspectRequest is not ResolvedAspect
    assert type(AspectRequest.AUTO) is AspectRequest
    assert type(ResolvedAspect.AUTO) is ResolvedAspect

    with pytest.raises(TypeError, match="ResolvedAspect"):
        ResolvedViewport(
            -1,
            1,
            -1,
            1,
            AspectRequest.AUTO,  # type: ignore[arg-type]
            ViewportSource.MANUAL,
        )


@pytest.mark.parametrize(("text", "spec_type", "expected_aspect"), _GEOMETRY_CASES)
def test_geometry_default_aspect_mapping_and_explicit_override(
    text: str,
    spec_type: type[PlotItemSpec],
    expected_aspect: ResolvedAspect,
) -> None:
    scene = _scene(text)
    assert type(scene.items[0]) is spec_type

    default = resolve_single_item_viewport(scene, _manual_request())
    overridden = resolve_single_item_viewport(
        scene,
        _manual_request(AspectRequest.AUTO),
    )

    assert default.error is None
    assert default.viewport is not None
    assert default.viewport.aspect is expected_aspect
    assert overridden.viewport is not None
    assert overridden.viewport.aspect is ResolvedAspect.AUTO


def test_explicit_default_mapping_and_compatibility_wrapper_are_identical() -> None:
    scene = _scene("y=x")
    request = ViewportRequest()

    unified = resolve_single_item_viewport(scene, request)
    legacy = resolve_single_explicit_viewport(scene, request)

    assert unified == legacy
    assert unified.viewport is not None
    assert unified.viewport.aspect is ResolvedAspect.AUTO


@pytest.mark.parametrize("text", [case[0] for case in _GEOMETRY_CASES])
def test_manual_geometry_resolves_without_probe_or_fallback(
    text: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("manual geometry must not probe")

    monkeypatch.setattr(viewport_resolver.np, "linspace", forbidden)
    monkeypatch.setattr(viewport_resolver, "execute_explicit_function", forbidden)

    result = resolve_single_item_viewport(_scene(text), _manual_request())

    assert result.error is None
    assert result.warning is None
    assert result.viewport is not None
    assert result.viewport.source is ViewportSource.MANUAL


def test_parabola_auto_geometry_uses_exact_strategy_before_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = "x^2=4*y"
    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("parabola auto geometry must not probe or estimate")

    monkeypatch.setattr(viewport_resolver.np, "linspace", forbidden)
    monkeypatch.setattr(viewport_resolver, "execute_explicit_function", forbidden)
    monkeypatch.setattr(viewport_resolver, "estimate_numeric_execution_cost", forbidden)

    result = resolve_single_item_viewport(_scene(text), ViewportRequest())

    assert result.error is None
    assert result.viewport is not None
    assert result.viewport.source is ViewportSource.AUTO_GEOMETRY
    assert result.viewport.aspect is ResolvedAspect.EQUAL
    assert result.warning is None


@pytest.mark.parametrize("text", [case[0] for case in _GEOMETRY_CASES[1:3]])
def test_auto_circle_and_ellipse_use_geometry_without_explicit_probe(
    text: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("oval auto geometry must not use the explicit probe")

    monkeypatch.setattr(viewport_resolver.np, "linspace", forbidden)
    monkeypatch.setattr(viewport_resolver, "execute_explicit_function", forbidden)
    monkeypatch.setattr(viewport_resolver, "estimate_numeric_execution_cost", forbidden)

    result = resolve_single_item_viewport(_scene(text), ViewportRequest())
    assert result.error is None
    assert result.viewport is not None
    assert result.viewport.source is ViewportSource.AUTO_GEOMETRY


@dataclass(frozen=True, slots=True)
class _UnknownSpec:
    item_id: str = "unknown"
    plot_kind: PlotKind = PlotKind.LINE_EQUATION


def test_unknown_exact_spec_is_invalid_request() -> None:
    result = resolve_single_item_viewport(
        PlotSceneSpec(items=(_UnknownSpec(),)),
        _manual_request(),
    )

    assert result.error is not None
    assert result.error.code is ErrorCode.INVALID_REQUEST
    assert result.error.field_name == "scene_spec"


def test_segment_plan_invariants_and_fixed_line_semantics() -> None:
    line = LineSegmentPlan(x0=0.0, y0=1.0, x1=2.0, y1=3.0)
    assert line.mathematical_branch_id == 0
    assert line.sample_count == 2
    assert line.closure is SegmentClosure.OPEN

    with pytest.raises(TypeError, match="exact float"):
        LineSegmentPlan(x0=0, y0=1.0, x1=2.0, y1=3.0)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="distinct"):
        LineSegmentPlan(x0=1.0, y0=1.0, x1=1.0, y1=1.0)
    with pytest.raises(ValueError, match="at least two"):
        ParameterIntervalPlan(0, 0.0, 1.0, 1, SegmentClosure.OPEN)
    with pytest.raises(ValueError, match="below"):
        ParameterIntervalPlan(0, 1.0, 1.0, 2, SegmentClosure.OPEN)


def test_geometry_item_plan_rejects_mixing_bad_sums_and_branch_ranges() -> None:
    line = LineSegmentPlan(0.0, 0.0, 1.0, 1.0)
    interval = ParameterIntervalPlan(0, 0.0, 1.0, 2, SegmentClosure.OPEN)

    with pytest.raises(TypeError, match="must not be mixed"):
        GeometryRenderItemPlan("mixed", 1, (line, interval), 4, 2, 2)
    with pytest.raises(ValueError, match="sum"):
        GeometryRenderItemPlan("sum", 1, (interval,), 3, 2, 1)
    with pytest.raises(ValueError, match="branch id"):
        GeometryRenderItemPlan(
            "branch",
            1,
            (ParameterIntervalPlan(1, 0.0, 1.0, 2, SegmentClosure.OPEN),),
            2,
            2,
            1,
        )


@pytest.mark.parametrize("text", [case[0] for case in _GEOMETRY_CASES])
def test_each_geometry_spec_has_fixed_branch_and_segment_capacity(text: str) -> None:
    plan = _approved_geometry_plan(text)
    assert validate_approved_render_plan(plan) is plan
    assert type(plan.item_plan) is GeometryRenderItemPlan
    expected = {
        LineSpec: (1, 1, LineSegmentPlan),
        CircleSpec: (1, 4, ParameterIntervalPlan),
        EllipseSpec: (1, 4, ParameterIntervalPlan),
        HyperbolaSpec: (2, 4, ParameterIntervalPlan),
        ParabolaSpec: (1, 2, ParameterIntervalPlan),
    }[type(plan.scene_spec.items[0])]
    assert (
        plan.item_plan.mathematical_branch_count,
        plan.item_plan.max_segment_count,
        type(plan.item_plan.segments[0]),
    ) == expected


def test_approval_rejects_version_memory_and_spec_plan_crosses() -> None:
    geometry = _approved_geometry_plan("x^2+y^2=25")
    assert type(geometry.item_plan) is GeometryRenderItemPlan

    for changes in (
        {"numeric_executor_contract_version": "numeric-executor-v1-postorder-float64"},
        {"parameterized_sampler_contract_version": None},
        {"memory_budget": _explicit_budget()},
    ):
        ordinary = replace(geometry, **changes)
        with pytest.raises((TypeError, ValueError)):
            render_plan_model._approve_render_plan(ordinary)

    explicit = _explicit_plan()
    ordinary_explicit = replace(
        explicit,
        parameterized_sampler_contract_version=(
            PARAMETERIZED_SAMPLER_CONTRACT_VERSION
        ),
    )
    with pytest.raises(ValueError, match="parameterized"):
        render_plan_model._approve_render_plan(ordinary_explicit)


def test_parameterized_sampler_accepts_builder_approved_parabola() -> None:
    text = "x^2=4*y"
    result = sample_parameterized_curve(_approved_geometry_plan(text))
    assert type(result) is SampledParameterizedCurve


@pytest.mark.parametrize("text", [case[0] for case in _GEOMETRY_CASES[1:3]])
def test_parameterized_sampler_accepts_builder_approved_circle_and_ellipse(
    text: str,
) -> None:
    plan = RenderPlanBuilder().build(
        _scene(text),
        _viewport(),
        image_width=800,
        image_height=600,
        dpi=96,
        show_grid=True,
        show_legend=False,
    )
    assert type(plan) is RenderPlan
    result = sample_parameterized_curve(plan)
    assert type(result) is SampledParameterizedCurve


def test_approval_rejects_geometry_mathematical_branch_count_mismatch() -> None:
    valid_plan = _approved_geometry_plan("x^2+y^2=25")
    assert type(valid_plan.item_plan) is GeometryRenderItemPlan
    invalid_item_plan = replace(
        valid_plan.item_plan,
        mathematical_branch_count=2,
    )
    invalid_plan = replace(valid_plan, item_plan=invalid_item_plan)

    with pytest.raises(
        ValueError,
        match="geometry mathematical branch count is invalid",
    ):
        render_plan_model._approve_render_plan(invalid_plan)


def test_approval_rejects_geometry_drawable_segment_capacity_mismatch() -> None:
    valid_plan = _approved_geometry_plan("x^2+y^2=25")
    assert type(valid_plan.item_plan) is GeometryRenderItemPlan
    invalid_item_plan = replace(
        valid_plan.item_plan,
        max_segment_count=5,
    )
    invalid_plan = replace(valid_plan, item_plan=invalid_item_plan)

    with pytest.raises(
        ValueError,
        match="geometry drawable segment capacity is invalid",
    ):
        render_plan_model._approve_render_plan(invalid_plan)


def test_approval_rejects_geometry_item_identity_mismatch() -> None:
    valid_plan = _approved_geometry_plan("x^2+y^2=25")
    assert type(valid_plan.item_plan) is GeometryRenderItemPlan
    invalid_item_plan = replace(
        valid_plan.item_plan,
        item_id="different-item",
    )
    invalid_plan = replace(valid_plan, item_plan=invalid_item_plan)

    with pytest.raises(
        ValueError,
        match="Spec and item plan identities do not match",
    ):
        render_plan_model._approve_render_plan(invalid_plan)


def test_approval_rejects_missing_explicit_numeric_executor_version() -> None:
    valid_plan = _explicit_plan()
    invalid_plan = replace(
        valid_plan,
        numeric_executor_contract_version=None,
    )

    with pytest.raises(
        ValueError,
        match="explicit plan numeric executor contract version is invalid",
    ):
        render_plan_model._approve_render_plan(invalid_plan)


def test_parabola_builder_uses_geometry_path_before_numeric_cost_and_has_no_bypass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("geometry builder must not enter numeric cost")

    monkeypatch.setattr(render_plan_builder, "estimate_numeric_execution_cost", forbidden)
    result = RenderPlanBuilder().build(
        _scene("x^2=4*y"),
        _viewport(),
        image_width=800,
        image_height=600,
        dpi=96,
        show_grid=True,
        show_legend=False,
    )

    assert type(result) is RenderPlan
    assert type(result.item_plan) is GeometryRenderItemPlan
    assert result.item_plan.mathematical_branch_count == 1
    assert result.item_plan.max_segment_count == 2
    assert "GeometryRenderItemPlan" not in signature(RenderPlanBuilder.build).parameters


@pytest.mark.parametrize(
    ("text", "target"),
    [
        ("x=2", "coefficients"),
        ("x^2+y^2=25", "radius_squared"),
        ("4*x^2+9*y^2=36", "major_axis"),
        ("4*x^2-9*y^2=36", "transverse_axis"),
        ("x^2=4*y", "opening"),
    ],
)
def test_geometry_receipt_detects_spec_semantic_tampering(
    text: str,
    target: str,
) -> None:
    plan = _approved_geometry_plan(text)
    spec = plan.scene_spec.items[0]
    receipt = plan._approval_receipt
    if target == "coefficients":
        object.__setattr__(spec.coefficients, "f", spec.coefficients.f + 1)
    elif target == "radius_squared":
        object.__setattr__(spec, target, Fraction(24))
    elif target == "major_axis":
        object.__setattr__(spec, target, AxisOrientation.VERTICAL)
    elif target == "transverse_axis":
        object.__setattr__(spec, target, AxisOrientation.VERTICAL)
    else:
        object.__setattr__(spec, target, ParabolaOpening.DOWN)

    with pytest.raises(ValueError, match="do not match"):
        validate_approved_render_plan(plan)
    assert plan._approval_receipt is receipt


@pytest.mark.parametrize(
    "target",
    [
        "parameter_start",
        "mathematical_branch_id",
        "sample_count",
        "closure",
        "parameter_batch_bytes",
        "transcendental_workspace_bytes",
        "validation_workspace_bytes",
        "segment_metadata_bytes",
        "parameterized_sampler_contract_version",
    ],
)
def test_geometry_receipt_detects_plan_version_and_memory_tampering(
    target: str,
) -> None:
    plan = _approved_geometry_plan("x^2+y^2=25")
    receipt = plan._approval_receipt
    assert type(plan.item_plan) is GeometryRenderItemPlan
    assert type(plan.memory_budget) is ParameterizedRenderMemoryBudget
    segment = plan.item_plan.segments[0]
    assert type(segment) is ParameterIntervalPlan
    if target in {"parameter_start", "mathematical_branch_id", "sample_count", "closure"}:
        value: object = {
            "parameter_start": -0.5,
            "mathematical_branch_id": 1,
            "sample_count": segment.sample_count + 1,
            "closure": SegmentClosure.OPEN,
        }[target]
        object.__setattr__(segment, target, value)
    elif target == "parameterized_sampler_contract_version":
        object.__setattr__(plan, target, "tampered-version")
    else:
        object.__setattr__(
            plan.memory_budget,
            target,
            getattr(plan.memory_budget, target) + 1,
        )

    with pytest.raises(ValueError, match="do not match"):
        validate_approved_render_plan(plan)
    assert plan._approval_receipt is receipt


def test_memory_budgets_have_separate_fixed_batch_and_total_contracts() -> None:
    explicit = _explicit_budget()
    parameterized = _parameterized_budget()

    assert explicit.batch_bytes == explicit.executor_extra_batch_bytes
    assert explicit.total_bytes == explicit.fixed_bytes + explicit.batch_bytes
    assert parameterized.batch_bytes == (
        parameterized.parameter_batch_bytes
        + parameterized.transcendental_workspace_bytes
        + parameterized.validation_workspace_bytes
    )
    assert parameterized.total_bytes == parameterized.fixed_bytes + parameterized.batch_bytes
    assert not hasattr(parameterized, "executor_extra_batch_bytes")


def test_explicit_result_keeps_exact_fields_signature_and_branchless_metadata() -> None:
    original_fields = {
        "item_id",
        "x",
        "y",
        "segment_ranges",
        "finite_sample_count",
        "nonfinite_sample_count",
        "isolated_finite_count",
        "discontinuity_break_count",
        "visible_segment_count",
        "warnings",
        "diagnostics",
        "_plan_contract_snapshot",
    }
    assert {field.name for field in fields(SampledExplicitFunction)} == original_fields
    assert "segment_metadata" not in signature(SampledExplicitFunction).parameters

    sampled = sample_explicit_function(_explicit_plan())
    assert type(sampled) is SampledExplicitFunction
    assert len(sampled.segment_metadata) == sampled.segment_ranges.shape[0]
    assert all(
        metadata.mathematical_branch_id is None
        and metadata.closure is SegmentClosure.OPEN
        for metadata in sampled.segment_metadata
    )


def test_parameterized_result_requires_owned_readonly_typed_arrays_and_metadata() -> None:
    x = _readonly_vector([0.0, 1.0, 2.0, 3.0])
    y = _readonly_vector([1.0, 2.0, 3.0, 4.0])
    ranges = _readonly_ranges([[0, 2], [2, 4]])
    metadata = (
        SampledSegmentMetadata(0, SegmentClosure.OPEN),
        SampledSegmentMetadata(1, SegmentClosure.CLOSED),
    )
    result = SampledParameterizedCurve(
        item_id="parameterized",
        x=x,
        y=y,
        segment_ranges=ranges,
        segment_metadata=metadata,
        visible_segment_count=2,
        warnings=(),
        diagnostics=ParameterizedSamplingDiagnostics(2, 4),
    )

    assert result.x.dtype == np.dtype(np.float64)
    assert result.y.dtype == np.dtype(np.float64)
    assert result.segment_ranges.dtype == np.dtype(np.int64)
    assert result.x.flags.owndata and not result.x.flags.writeable
    assert result.y.flags.owndata and not result.y.flags.writeable
    assert result.segment_ranges.flags.owndata
    assert not result.segment_ranges.flags.writeable
    assert "_plan_contract_snapshot" not in signature(SampledParameterizedCurve).parameters


def test_parameterized_result_rejects_one_point_segments() -> None:
    with pytest.raises(ValueError, match="half-open"):
        SampledParameterizedCurve(
            item_id="one-point",
            x=_readonly_vector([0.0]),
            y=_readonly_vector([0.0]),
            segment_ranges=_readonly_ranges([[0, 1]]),
            segment_metadata=(SampledSegmentMetadata(0, SegmentClosure.OPEN),),
            visible_segment_count=1,
            warnings=(),
            diagnostics=ParameterizedSamplingDiagnostics(1, 1),
        )


@pytest.mark.parametrize(
    ("code", "good_metrics", "bad_metrics"),
    [
        (
            SamplingWarningCode.VIEWPORT_CLIPPED,
            ViewportClippedMetrics(1),
            SamplingPrecisionLimitedMetrics(1),
        ),
        (
            SamplingWarningCode.SAMPLING_PRECISION_LIMITED,
            SamplingPrecisionLimitedMetrics(1),
            ViewportClippedMetrics(1),
        ),
    ],
)
def test_new_warning_codes_require_exact_typed_metrics(
    code: SamplingWarningCode,
    good_metrics: object,
    bad_metrics: object,
) -> None:
    assert SamplingWarning(code, good_metrics).metrics is good_metrics  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        SamplingWarning(code, bad_metrics)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        SamplingWarning(code, {})  # type: ignore[arg-type]


def test_public_exports_are_unique_identity_exports_without_reverse_dependencies() -> None:
    required_models = {
        "ResolvedAspect": ResolvedAspect,
        "GeometrySegmentPlan": GeometrySegmentPlan,
        "RenderItemPlan": RenderItemPlan,
        "GeometryRenderItemPlan": GeometryRenderItemPlan,
        "ParameterizedRenderMemoryBudget": ParameterizedRenderMemoryBudget,
        "SegmentClosure": SegmentClosure,
        "PARAMETERIZED_SAMPLER_CONTRACT_VERSION": (
            PARAMETERIZED_SAMPLER_CONTRACT_VERSION
        ),
    }
    required_engine = {
        "resolve_single_item_viewport": resolve_single_item_viewport,
        "SampledSegmentMetadata": SampledSegmentMetadata,
        "SampledParameterizedCurve": SampledParameterizedCurve,
        "ParameterizedSamplingDiagnostics": ParameterizedSamplingDiagnostics,
    }
    assert len(public_models.__all__) == len(set(public_models.__all__))
    assert len(public_engine.__all__) == len(set(public_engine.__all__))
    assert all(getattr(public_models, name) is value for name, value in required_models.items())
    assert all(getattr(public_engine, name) is value for name, value in required_engine.items())
    models_source = Path(public_models.__file__).read_text(encoding="utf-8")
    assert "math_drawing_assistant.engine" not in models_source


def test_stage14b1_production_code_has_no_contour_or_geometry_execution_chain() -> None:
    package_root = Path(public_models.__file__).parents[1]
    allowed_sources = tuple((package_root / "engine").glob("*.py"))
    contour_calls = []
    for path in allowed_sources:
        source = path.read_text(encoding="utf-8")
        if ".contour(" in source or "pyplot.contour(" in source:
            contour_calls.append(path.name)
    assert contour_calls == []

    scene_source = (package_root / "engine" / "scene_executor.py").read_text(
        encoding="utf-8",
    )
    for name in ("LineSpec", "CircleSpec", "EllipseSpec", "HyperbolaSpec", "ParabolaSpec"):
        assert name not in scene_source
