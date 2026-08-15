"""Stage 14E cross-type acceptance gates for the frozen public pipeline."""

from __future__ import annotations

from dataclasses import dataclass, fields
from fractions import Fraction
from inspect import signature
from math import isfinite, ulp
from pathlib import Path

import numpy as np
import pytest

import math_drawing_assistant.engine as public_engine
from math_drawing_assistant.config import DEFAULT_LIMITS
from math_drawing_assistant.engine import (
    RenderPlanBuilder,
    SampledExplicitFunction,
    SampledParameterizedCurve,
    SamplingCancelled,
    analyze_plot_item,
    resolve_single_item_viewport,
    sample_explicit_function,
    sample_parameterized_curve,
)
from math_drawing_assistant.engine import samplers
from math_drawing_assistant.models import (
    AxisOrientation,
    CircleSpec,
    EllipseSpec,
    ErrorCode,
    ErrorInfo,
    ExplicitFunctionSpec,
    ExplicitRenderItemPlan,
    GeometryRenderItemPlan,
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
    RenderMemoryBudget,
    RenderPlan,
    ResolvedAspect,
    ResolvedViewport,
    SegmentClosure,
    ViewportMode,
    ViewportRequest,
    ViewportSource,
    HyperbolaSpec,
    validate_approved_render_plan,
)


@dataclass(frozen=True, slots=True)
class Stage14Case:
    name: str
    text: str
    spec_type: type[PlotItemSpec]
    expected_aspect: ResolvedAspect
    mathematical_branch_count: int
    max_segment_count: int
    maximum_residual_ulps: int
    viewport_boundary_ulps: int


@dataclass(frozen=True, slots=True)
class Stage14Artifacts:
    spec: PlotItemSpec
    scene: PlotSceneSpec
    viewport: ResolvedViewport
    plan: RenderPlan
    sampled: SampledParameterizedCurve


GEOMETRY_CASES = (
    Stage14Case(
        "line",
        "2*x-y+3=0",
        LineSpec,
        ResolvedAspect.AUTO,
        1,
        1,
        16,
        2,
    ),
    Stage14Case(
        "circle",
        "x^2+y^2=25",
        CircleSpec,
        ResolvedAspect.EQUAL,
        1,
        4,
        256,
        8,
    ),
    Stage14Case(
        "ellipse",
        "x^2/9+y^2/4=1",
        EllipseSpec,
        ResolvedAspect.EQUAL,
        1,
        4,
        256,
        8,
    ),
    Stage14Case(
        "hyperbola",
        "x^2/9-y^2/4=1",
        HyperbolaSpec,
        ResolvedAspect.EQUAL,
        2,
        4,
        256,
        8,
    ),
    Stage14Case(
        "parabola",
        "x^2=4*y",
        ParabolaSpec,
        ResolvedAspect.EQUAL,
        1,
        2,
        256,
        8,
    ),
)

CASE_BY_NAME = {case.name: case for case in GEOMETRY_CASES}
PARAMETERIZED_BUDGET_FIELDS = tuple(
    field.name for field in fields(ParameterizedRenderMemoryBudget)
)


def _request(text: str, *, item_id: str) -> PlotItemRequest:
    return PlotItemRequest(
        item_id=item_id,
        input_text=text,
        input_source=InputSource.MANUAL,
        requested_plot_kind=PlotKind.AUTO,
        display_order=0,
    )


def _scene(text: str, *, item_id: str) -> tuple[PlotItemSpec, PlotSceneSpec]:
    spec = analyze_plot_item(_request(text, item_id=item_id))
    assert not isinstance(spec, ErrorInfo), spec
    return spec, PlotSceneSpec(items=(spec,))


def _manual_request(
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
    case: Stage14Case,
    viewport_request: ViewportRequest | None = None,
    *,
    item_id: str | None = None,
) -> Stage14Artifacts:
    resolved_item_id = item_id or f"stage14e-{case.name}"
    spec, scene = _scene(case.text, item_id=resolved_item_id)
    assert type(spec) is case.spec_type
    resolution = resolve_single_item_viewport(
        scene,
        viewport_request or ViewportRequest(),
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
    sampled = sample_parameterized_curve(plan)
    assert type(sampled) is SampledParameterizedCurve, sampled
    return Stage14Artifacts(spec, scene, resolution.viewport, plan, sampled)


def _explicit_plan(*, item_id: str = "stage14e-explicit") -> RenderPlan:
    spec, scene = _scene("y=x^2", item_id=item_id)
    assert type(spec) is ExplicitFunctionSpec
    resolution = resolve_single_item_viewport(
        scene,
        _manual_request(-10.0, 10.0, -10.0, 10.0),
    )
    assert resolution.error is None
    assert resolution.viewport is not None
    result = RenderPlanBuilder().build(
        scene,
        resolution.viewport,
        image_width=800,
        image_height=600,
        dpi=96,
        show_grid=True,
        show_legend=False,
    )
    assert type(result) is RenderPlan, result
    return result


def _assert_owned_readonly_arrays(
    sampled: SampledExplicitFunction | SampledParameterizedCurve,
) -> None:
    assert sampled.x.dtype == sampled.y.dtype == np.dtype(np.float64)
    assert sampled.x.ndim == sampled.y.ndim == 1
    assert sampled.x.shape == sampled.y.shape
    assert sampled.x.flags.owndata and sampled.x.base is None
    assert sampled.y.flags.owndata and sampled.y.base is None
    assert not sampled.x.flags.writeable and not sampled.y.flags.writeable
    assert sampled.segment_ranges.dtype == np.dtype(np.int64)
    assert sampled.segment_ranges.ndim == 2
    assert sampled.segment_ranges.shape[1] == 2
    assert sampled.segment_ranges.flags.owndata
    assert sampled.segment_ranges.base is None
    assert not sampled.segment_ranges.flags.writeable


def _assert_segment_integrity(sampled: SampledParameterizedCurve) -> None:
    assert sampled.visible_segment_count == sampled.segment_ranges.shape[0]
    assert len(sampled.segment_metadata) == sampled.segment_ranges.shape[0]
    assert sampled.diagnostics.sampled_segment_count == sampled.segment_ranges.shape[0]
    assert sampled.diagnostics.sampled_point_count == sampled.x.size
    previous_stop = 0
    for (start, stop), metadata in zip(
        sampled.segment_ranges.tolist(),
        sampled.segment_metadata,
        strict=True,
    ):
        assert previous_stop <= start < stop <= sampled.x.size
        assert stop - start >= 2
        assert metadata.mathematical_branch_id is not None
        assert np.all(np.isfinite(sampled.x[start:stop]))
        assert np.all(np.isfinite(sampled.y[start:stop]))
        previous_stop = stop


@pytest.mark.parametrize("case", GEOMETRY_CASES, ids=lambda case: case.name)
def test_cross_type_public_contract_and_actual_buffer_matrix(case: Stage14Case) -> None:
    artifacts = _artifacts(case)
    plan = artifacts.plan
    sampled = artifacts.sampled

    assert type(artifacts.spec) is case.spec_type
    assert artifacts.viewport.aspect is case.expected_aspect
    assert not isinstance(artifacts.viewport.aspect, type(ViewportRequest().aspect_request))
    assert artifacts.viewport.source is ViewportSource.AUTO_GEOMETRY
    assert validate_approved_render_plan(plan) is plan
    assert plan.plan_version == RENDER_PLAN_CONTRACT_VERSION
    assert type(plan.item_plan) is GeometryRenderItemPlan
    assert plan.item_plan.mathematical_branch_count == case.mathematical_branch_count
    assert plan.item_plan.max_segment_count == case.max_segment_count
    assert plan.numeric_executor_contract_version is None
    assert (
        plan.parameterized_sampler_contract_version
        == PARAMETERIZED_SAMPLER_CONTRACT_VERSION
    )
    assert type(plan.memory_budget) is ParameterizedRenderMemoryBudget
    assert type(sampled) is SampledParameterizedCurve
    assert sampled.item_id == artifacts.spec.item_id == plan.item_plan.item_id
    _assert_owned_readonly_arrays(sampled)
    _assert_segment_integrity(sampled)
    assert samplers._sampled_parameterized_curve_matches_approved_plan(sampled, plan)

    budget = plan.memory_budget
    assert sampled.x.size == sampled.y.size == plan.item_plan.sample_count
    assert sampled.x.nbytes == budget.final_x_bytes
    assert sampled.y.nbytes == budget.final_y_bytes
    assert sampled.segment_ranges.shape[0] <= plan.item_plan.max_segment_count
    assert sampled.segment_ranges.nbytes <= budget.segment_index_range_bytes
    actual_metadata_logical_bytes = len(sampled.segment_metadata) * 2 * 8
    assert actual_metadata_logical_bytes <= budget.segment_metadata_bytes
    assert budget.fixed_bytes + budget.batch_bytes == budget.total_bytes
    assert budget.total_bytes <= DEFAULT_LIMITS.max_estimated_memory_bytes
    assert not hasattr(budget, "executor_extra_batch_bytes")


def test_explicit_m1_exact_type_signature_versions_and_branchless_metadata_regress() -> None:
    plan = _explicit_plan()
    assert validate_approved_render_plan(plan) is plan
    assert type(plan.item_plan) is ExplicitRenderItemPlan
    assert type(plan.memory_budget) is RenderMemoryBudget
    assert plan.numeric_executor_contract_version
    assert plan.parameterized_sampler_contract_version is None
    sampled = sample_explicit_function(plan)
    assert type(sampled) is SampledExplicitFunction, sampled
    _assert_owned_readonly_arrays(sampled)
    assert samplers._sampled_explicit_function_matches_approved_plan(sampled, plan)
    assert sampled.item_id == plan.item_plan.item_id
    assert sampled.x.size == sampled.y.size == plan.item_plan.sample_count
    assert all(
        metadata.mathematical_branch_id is None
        and metadata.closure is SegmentClosure.OPEN
        for metadata in sampled.segment_metadata
    )
    assert {field.name for field in fields(SampledExplicitFunction)} == {
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
    assert "segment_metadata" not in signature(SampledExplicitFunction).parameters


@dataclass(frozen=True, slots=True)
class TopologyCase:
    name: str
    geometry_case: Stage14Case
    viewport_request: ViewportRequest | None
    expected_branch_ids: tuple[int, ...]
    expected_closure: SegmentClosure


TOPOLOGY_CASES = (
    TopologyCase("line-one-segment", CASE_BY_NAME["line"], None, (0,), SegmentClosure.OPEN),
    TopologyCase("circle-closed", CASE_BY_NAME["circle"], None, (0,), SegmentClosure.CLOSED),
    TopologyCase(
        "circle-four-open-arcs",
        CASE_BY_NAME["circle"],
        _manual_request(-4.0, 4.0, -4.0, 4.0),
        (0, 0, 0, 0),
        SegmentClosure.OPEN,
    ),
    TopologyCase(
        "ellipse-two-open-arcs",
        CASE_BY_NAME["ellipse"],
        _manual_request(-1.0, 1.0, -3.0, 3.0),
        (0, 0),
        SegmentClosure.OPEN,
    ),
    TopologyCase(
        "hyperbola-two-branches",
        CASE_BY_NAME["hyperbola"],
        _manual_request(-10.0, 10.0, -8.0, 8.0),
        (0, 1),
        SegmentClosure.OPEN,
    ),
    TopologyCase(
        "hyperbola-one-branch-split",
        CASE_BY_NAME["hyperbola"],
        _manual_request(5.0, 10.0, -8.0, 8.0),
        (1, 1),
        SegmentClosure.OPEN,
    ),
    TopologyCase(
        "parabola-vertex-excluded",
        CASE_BY_NAME["parabola"],
        _manual_request(-10.0, 10.0, 1.0, 4.0),
        (0, 0),
        SegmentClosure.OPEN,
    ),
)


@pytest.mark.parametrize("topology", TOPOLOGY_CASES, ids=lambda value: value.name)
def test_branch_and_drawable_segment_nonconnection_matrix(topology: TopologyCase) -> None:
    artifacts = _artifacts(topology.geometry_case, topology.viewport_request)
    sampled = artifacts.sampled
    _assert_segment_integrity(sampled)
    assert tuple(
        metadata.mathematical_branch_id for metadata in sampled.segment_metadata
    ) == topology.expected_branch_ids
    assert all(
        metadata.closure is topology.expected_closure
        for metadata in sampled.segment_metadata
    )
    assert sampled.visible_segment_count == len(topology.expected_branch_ids)
    assert sampled.visible_segment_count <= artifacts.plan.item_plan.max_segment_count  # type: ignore[union-attr]

    item_plan = artifacts.plan.item_plan
    assert type(item_plan) is GeometryRenderItemPlan
    intervals = tuple(
        segment for segment in item_plan.segments if type(segment) is ParameterIntervalPlan
    )
    assert intervals == tuple(
        sorted(
            intervals,
            key=lambda interval: (
                interval.mathematical_branch_id,
                interval.parameter_start,
            ),
        ),
    )
    for previous, current in zip(intervals, intervals[1:]):
        if previous.mathematical_branch_id == current.mathematical_branch_id:
            assert previous.parameter_stop <= current.parameter_start


COMMON_RECEIPT_TAMPERS = (
    "spec_coefficients",
    "provenance",
    "x_min",
    "x_max",
    "y_min",
    "y_max",
    "aspect",
    "source",
    "item_id",
    "mathematical_branch_count",
    "sample_count",
    "batch_size",
    "max_segment_count",
    "sampling_policy_version",
    "numeric_executor_contract_version",
    "parameterized_sampler_contract_version",
    "image_width",
    "image_height",
    "dpi",
    "show_grid",
    "show_legend",
    "limits_version",
    "plan_version",
)


def _tamper_common_geometry_semantic(plan: RenderPlan, target: str) -> None:
    assert type(plan.item_plan) is GeometryRenderItemPlan
    spec = plan.scene_spec.items[0]
    if target == "spec_coefficients":
        object.__setattr__(spec.coefficients, "f", spec.coefficients.f + 1)  # type: ignore[union-attr]
    elif target == "provenance":
        object.__setattr__(
            spec.provenance,  # type: ignore[union-attr]
            "normalized_input",
            f"{spec.provenance.normalized_input}+tampered",  # type: ignore[union-attr]
        )
    elif target in {"x_min", "y_min"}:
        object.__setattr__(
            plan.resolved_viewport,
            target,
            getattr(plan.resolved_viewport, target) + 0.125,
        )
    elif target in {"x_max", "y_max"}:
        object.__setattr__(
            plan.resolved_viewport,
            target,
            getattr(plan.resolved_viewport, target) - 0.125,
        )
    elif target == "aspect":
        replacement = (
            ResolvedAspect.EQUAL
            if plan.resolved_viewport.aspect is ResolvedAspect.AUTO
            else ResolvedAspect.AUTO
        )
        object.__setattr__(plan.resolved_viewport, target, replacement)
    elif target == "source":
        object.__setattr__(plan.resolved_viewport, target, ViewportSource.MANUAL)
    elif target in {
        "item_id",
        "mathematical_branch_count",
        "sample_count",
        "batch_size",
        "max_segment_count",
    }:
        current = getattr(plan.item_plan, target)
        replacement = f"{current}-tampered" if target == "item_id" else current + 1
        object.__setattr__(plan.item_plan, target, replacement)
    elif target in {"image_width", "image_height", "dpi"}:
        object.__setattr__(plan, target, getattr(plan, target) + 1)
    elif target in {"show_grid", "show_legend"}:
        object.__setattr__(plan, target, not getattr(plan, target))
    else:
        object.__setattr__(plan, target, "tampered-version")


@pytest.mark.parametrize("case", GEOMETRY_CASES, ids=lambda case: case.name)
@pytest.mark.parametrize("target", COMMON_RECEIPT_TAMPERS)
def test_receipt_rejects_every_common_semantic_for_each_exact_geometry_type(
    case: Stage14Case,
    target: str,
) -> None:
    plan = _artifacts(case).plan
    receipt = plan._approval_receipt
    _tamper_common_geometry_semantic(plan, target)
    with pytest.raises((TypeError, ValueError)):
        validate_approved_render_plan(plan)
    assert plan._approval_receipt is receipt


@pytest.mark.parametrize("case", GEOMETRY_CASES, ids=lambda case: case.name)
@pytest.mark.parametrize("field_name", PARAMETERIZED_BUDGET_FIELDS)
def test_receipt_rejects_every_parameterized_budget_field_for_each_exact_geometry_type(
    case: Stage14Case,
    field_name: str,
) -> None:
    plan = _artifacts(case).plan
    receipt = plan._approval_receipt
    assert type(plan.memory_budget) is ParameterizedRenderMemoryBudget
    object.__setattr__(
        plan.memory_budget,
        field_name,
        getattr(plan.memory_budget, field_name) + 1,
    )
    with pytest.raises((TypeError, ValueError)):
        validate_approved_render_plan(plan)
    assert plan._approval_receipt is receipt


@pytest.mark.parametrize("target", ("x0", "y0", "x1", "y1"))
def test_receipt_rejects_each_line_endpoint_without_reissuing(target: str) -> None:
    plan = _artifacts(CASE_BY_NAME["line"]).plan
    receipt = plan._approval_receipt
    assert type(plan.item_plan) is GeometryRenderItemPlan
    segment = plan.item_plan.segments[0]
    assert type(segment) is LineSegmentPlan
    object.__setattr__(segment, target, getattr(segment, target) + 0.125)
    with pytest.raises((TypeError, ValueError)):
        validate_approved_render_plan(plan)
    assert plan._approval_receipt is receipt


@pytest.mark.parametrize("case", GEOMETRY_CASES[1:], ids=lambda case: case.name)
@pytest.mark.parametrize(
    "target",
    (
        "parameter_start",
        "parameter_stop",
        "mathematical_branch_id",
        "sample_count",
        "closure",
    ),
)
def test_receipt_rejects_each_parameter_interval_semantic_for_each_conic_type(
    case: Stage14Case,
    target: str,
) -> None:
    plan = _artifacts(case).plan
    receipt = plan._approval_receipt
    assert type(plan.item_plan) is GeometryRenderItemPlan
    interval = plan.item_plan.segments[0]
    assert type(interval) is ParameterIntervalPlan
    if target == "parameter_start":
        replacement: object = interval.parameter_start + 0.001
    elif target == "parameter_stop":
        replacement = interval.parameter_stop - 0.001
    elif target == "mathematical_branch_id":
        replacement = interval.mathematical_branch_id + 1
    elif target == "sample_count":
        replacement = interval.sample_count + 1
    else:
        replacement = (
            SegmentClosure.OPEN
            if interval.closure is SegmentClosure.CLOSED
            else SegmentClosure.CLOSED
        )
    object.__setattr__(interval, target, replacement)
    with pytest.raises((TypeError, ValueError)):
        validate_approved_render_plan(plan)
    assert plan._approval_receipt is receipt


def _independent_normalized_residual(
    spec: PlotItemSpec,
    x_value: float,
    y_value: float,
) -> Fraction:
    """Independent Stage 14 oracle; it does not call any production projector."""

    coefficients = spec.coefficients  # type: ignore[union-attr]
    x = Fraction.from_float(x_value)
    y = Fraction.from_float(y_value)
    polynomial = (
        coefficients.a * x * x
        + coefficients.b * x * y
        + coefficients.c * y * y
        + coefficients.d * x
        + coefficients.e * y
        + coefficients.f
    )
    scale = (
        abs(coefficients.a) * max(Fraction(1), abs(x * x))
        + abs(coefficients.b) * max(Fraction(1), abs(x * y))
        + abs(coefficients.c) * max(Fraction(1), abs(y * y))
        + abs(coefficients.d) * max(Fraction(1), abs(x))
        + abs(coefficients.e) * max(Fraction(1), abs(y))
        + abs(coefficients.f)
    )
    assert scale > 0
    return abs(polynomial) / scale


def _viewport_tolerance(minimum: float, maximum: float, ulps: int) -> float:
    return ulps * max(ulp(minimum), ulp(maximum), ulp(maximum - minimum))


def _assert_hyperbola_branch_direction(
    spec: HyperbolaSpec,
    sampled: SampledParameterizedCurve,
) -> None:
    assert type(spec.transverse_axis) is AxisOrientation
    assert spec.transverse_axis in {
        AxisOrientation.HORIZONTAL,
        AxisOrientation.VERTICAL,
    }
    if spec.transverse_axis is AxisOrientation.HORIZONTAL:
        branch_coordinate = sampled.x
        center = float(spec.center_x)
    else:
        branch_coordinate = sampled.y
        center = float(spec.center_y)

    for (start, stop), metadata in zip(
        sampled.segment_ranges.tolist(),
        sampled.segment_metadata,
        strict=True,
    ):
        branch_id = metadata.mathematical_branch_id
        assert branch_id in {0, 1}
        coordinate_segment = branch_coordinate[start:stop]
        if branch_id == 0:
            assert np.all(coordinate_segment < center)
        else:
            assert np.all(coordinate_segment > center)


@pytest.mark.parametrize("case", GEOMETRY_CASES, ids=lambda case: case.name)
def test_independent_fraction_residual_viewport_and_branch_oracle(case: Stage14Case) -> None:
    artifacts = _artifacts(case)
    sampled = artifacts.sampled
    viewport = artifacts.viewport
    x_tolerance = _viewport_tolerance(
        viewport.x_min,
        viewport.x_max,
        case.viewport_boundary_ulps,
    )
    y_tolerance = _viewport_tolerance(
        viewport.y_min,
        viewport.y_max,
        case.viewport_boundary_ulps,
    )
    hard_threshold = Fraction(case.maximum_residual_ulps, 1 << 52)
    for x_value, y_value in zip(sampled.x, sampled.y, strict=True):
        x_float = float(x_value)
        y_float = float(y_value)
        assert isfinite(x_float) and isfinite(y_float)
        assert _independent_normalized_residual(
            artifacts.spec,
            x_float,
            y_float,
        ) <= hard_threshold
        assert viewport.x_min - x_tolerance <= x_float <= viewport.x_max + x_tolerance
        assert viewport.y_min - y_tolerance <= y_float <= viewport.y_max + y_tolerance

    if type(artifacts.spec) is HyperbolaSpec:
        _assert_hyperbola_branch_direction(artifacts.spec, sampled)


HYPERBOLA_DIRECTION_CASES = (
    ("x^2/9-y^2/4=1", AxisOrientation.HORIZONTAL),
    ("y^2/4-x^2/9=1", AxisOrientation.VERTICAL),
)


@pytest.mark.parametrize(("text", "axis"), HYPERBOLA_DIRECTION_CASES)
def test_hyperbola_branch_direction_oracle_covers_both_transverse_axes(
    text: str,
    axis: AxisOrientation,
) -> None:
    case = Stage14Case(
        f"hyperbola-{axis.value}",
        text,
        HyperbolaSpec,
        ResolvedAspect.EQUAL,
        2,
        4,
        256,
        8,
    )
    artifacts = _artifacts(case)
    assert type(artifacts.spec) is HyperbolaSpec
    assert artifacts.spec.transverse_axis is axis
    assert {
        metadata.mathematical_branch_id
        for metadata in artifacts.sampled.segment_metadata
    } == {0, 1}
    _assert_hyperbola_branch_direction(artifacts.spec, artifacts.sampled)


@pytest.mark.parametrize(
    ("text", "opening"),
    (
        ("x^2=4*y", ParabolaOpening.UP),
        ("x^2=-4*y", ParabolaOpening.DOWN),
        ("y^2=4*x", ParabolaOpening.RIGHT),
        ("y^2=-4*x", ParabolaOpening.LEFT),
    ),
)
def test_four_parabola_openings_match_independent_direction_oracle(
    text: str,
    opening: ParabolaOpening,
) -> None:
    case = Stage14Case(
        opening.value,
        text,
        ParabolaSpec,
        ResolvedAspect.EQUAL,
        1,
        2,
        256,
        8,
    )
    artifacts = _artifacts(case)
    spec = artifacts.spec
    assert type(spec) is ParabolaSpec
    assert spec.opening is opening
    hard_threshold = Fraction(256, 1 << 52)
    assert all(
        _independent_normalized_residual(spec, float(x), float(y)) <= hard_threshold
        for x, y in zip(artifacts.sampled.x, artifacts.sampled.y, strict=True)
    )
    if opening is ParabolaOpening.UP:
        assert np.all(artifacts.sampled.y >= float(spec.vertex_y))
    elif opening is ParabolaOpening.DOWN:
        assert np.all(artifacts.sampled.y <= float(spec.vertex_y))
    elif opening is ParabolaOpening.RIGHT:
        assert np.all(artifacts.sampled.x >= float(spec.vertex_x))
    else:
        assert np.all(artifacts.sampled.x <= float(spec.vertex_x))


EXTREME_LEGAL_CASES = (
    (
        f"{10**127 - 1}*x+{10**127 - 2}*y+1=0",
        LineSpec,
    ),
    ("100000000*x^2+100000000*y^2=1", CircleSpec),
    ("x^2+100000000*y^2=1", EllipseSpec),
    ("x^2/1000000-y^2/250000=1", HyperbolaSpec),
    ("1000000*x^2=4*y", ParabolaSpec),
    ("(x-9999998)^2+y^2=1", CircleSpec),
)


@pytest.mark.parametrize(("text", "spec_type"), EXTREME_LEGAL_CASES)
def test_large_flat_small_and_coordinate_limit_legal_cases_remain_bounded(
    text: str,
    spec_type: type[PlotItemSpec],
) -> None:
    spec, scene = _scene(text, item_id="stage14e-extreme")
    assert type(spec) is spec_type
    resolution = resolve_single_item_viewport(scene, ViewportRequest())
    assert resolution.error is None, resolution.error
    assert resolution.viewport is not None
    assert all(
        isfinite(value)
        and abs(value) <= DEFAULT_LIMITS.max_viewport_absolute_coordinate
        for value in (
            resolution.viewport.x_min,
            resolution.viewport.x_max,
            resolution.viewport.y_min,
            resolution.viewport.y_max,
        )
    )
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
    assert type(sampled) is SampledParameterizedCurve, sampled
    assert np.all(np.isfinite(sampled.x)) and np.all(np.isfinite(sampled.y))


NARROW_VIEWPORT_CASES = (
    (CASE_BY_NAME["line"], _manual_request(0.0, 1.0, 3.0, 4.0)),
    (CASE_BY_NAME["circle"], _manual_request(4.0, 5.0, -0.5, 0.5)),
    (CASE_BY_NAME["ellipse"], _manual_request(2.0, 3.0, -0.5, 0.5)),
    (CASE_BY_NAME["hyperbola"], _manual_request(3.0, 4.0, -0.5, 0.5)),
    (CASE_BY_NAME["parabola"], _manual_request(-0.5, 0.5, 0.0, 1.0)),
)


@pytest.mark.parametrize(
    ("case", "viewport_request"),
    NARROW_VIEWPORT_CASES,
    ids=lambda value: value.name if isinstance(value, Stage14Case) else None,
)
def test_minimum_span_narrow_legal_viewports_have_bounded_success(
    case: Stage14Case,
    viewport_request: ViewportRequest,
) -> None:
    artifacts = _artifacts(case, viewport_request)
    assert artifacts.viewport.x_max - artifacts.viewport.x_min == 1.0
    assert artifacts.viewport.y_max - artifacts.viewport.y_min == 1.0
    assert np.all(np.isfinite(artifacts.sampled.x))
    assert np.all(np.isfinite(artifacts.sampled.y))


@pytest.mark.parametrize(
    "text",
    (
        f"x={10**127}",
        "x^2+y^2=100000000000000",
        "x^2/100000000000000+y^2=1",
        "(x-10000001)^2/9-y^2/4=1",
        "(x-10000001)^2=4*y",
    ),
)
def test_unsafe_auto_geometry_ranges_return_typed_numeric_failure(text: str) -> None:
    _, scene = _scene(text, item_id="stage14e-range-error")
    resolution = resolve_single_item_viewport(scene, ViewportRequest())
    assert resolution.viewport is None
    assert resolution.error is not None
    assert resolution.error.code is ErrorCode.NUMERIC_RANGE_UNSUPPORTED


@pytest.mark.parametrize(
    ("text", "viewport_request"),
    (
        ("x=2", _manual_request(-1.0, 0.0, -1.0, 1.0)),
        ("x^2+y^2=25", _manual_request(5.0, 6.0, -1.0, 1.0)),
        ("x^2/9+y^2/4=1", _manual_request(4.0, 5.0, -1.0, 1.0)),
        ("x^2/9-y^2/4=1", _manual_request(-1.0, 1.0, -1.0, 1.0)),
        ("x^2=4*y", _manual_request(2.0, 4.0, 0.0, 1.0)),
    ),
)
def test_empty_or_singleton_visible_sets_return_no_visible_curve(
    text: str,
    viewport_request: ViewportRequest,
) -> None:
    _, scene = _scene(text, item_id="stage14e-no-visible")
    resolution = resolve_single_item_viewport(scene, viewport_request)
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
    assert type(plan) is ErrorInfo
    assert plan.code is ErrorCode.NO_VISIBLE_CURVE


class _ImmediateCancellationProbe:
    def __init__(self) -> None:
        self.calls = 0

    def is_cancelled(self) -> bool:
        self.calls += 1
        return True


@pytest.mark.parametrize(
    "label",
    ("explicit", *(case.name for case in GEOMETRY_CASES)),
)
def test_public_cancellation_matrix_validates_receipt_first_and_returns_no_partial_result(
    label: str,
) -> None:
    if label == "explicit":
        plan = _explicit_plan(item_id="stage14e-cancel-explicit")
        sampler = sample_explicit_function
    else:
        case = CASE_BY_NAME[label]
        plan = _artifacts(case, item_id=f"stage14e-cancel-{label}").plan
        sampler = sample_parameterized_curve

    probe = _ImmediateCancellationProbe()
    cancelled = sampler(plan, cancellation_probe=probe)
    assert type(cancelled) is SamplingCancelled
    assert cancelled.item_id == plan.scene_spec.items[0].item_id
    assert probe.calls >= 1
    assert not isinstance(cancelled, (SampledExplicitFunction, SampledParameterizedCurve))

    object.__setattr__(plan, "sampling_policy_version", "tampered-before-cancel")
    validation_probe = _ImmediateCancellationProbe()
    invalid = sampler(plan, cancellation_probe=validation_probe)
    assert type(invalid) is ErrorInfo
    assert validation_probe.calls == 0


def test_stage14_static_production_boundaries_and_no_parallel_public_pipeline() -> None:
    package_root = Path(__file__).resolve().parents[2] / "math_drawing_assistant"
    production_paths = (
        package_root / "engine" / "viewport_resolver.py",
        package_root / "engine" / "render_plan_builder.py",
        package_root / "engine" / "samplers.py",
        package_root / "engine" / "renderer.py",
        package_root / "engine" / "scene_executor.py",
        package_root / "app_controller.py",
        package_root / "bootstrap.py",
        *sorted((package_root / "workers").rglob("*.py")),
        *sorted((package_root / "ui").rglob("*.py")),
    )
    for path in production_paths:
        source = path.read_text(encoding="utf-8")
        assert ".contour(" not in source
        assert "plt.contour(" not in source
        assert "axes.contour(" not in source

    sampler_source = (package_root / "engine" / "samplers.py").read_text(
        encoding="utf-8",
    )
    assert "resolve_single_item_viewport(" not in sampler_source
    assert "RenderPlanBuilder(" not in sampler_source
    assert "_plan_visible_" not in sampler_source

    renderer_source = (package_root / "engine" / "renderer.py").read_text(
        encoding="utf-8",
    )
    scene_source = (package_root / "engine" / "scene_executor.py").read_text(
        encoding="utf-8",
    )
    assert "SampledParameterizedCurve" not in renderer_source
    assert "sample_parameterized_curve" not in renderer_source
    assert "GeometryRenderItemPlan" not in scene_source
    assert "sample_parameterized_curve" not in scene_source

    forbidden_public_names = {
        "sample_line",
        "sample_circle",
        "sample_ellipse",
        "sample_hyperbola",
        "sample_parabola",
        "resolve_conic_viewport",
        "build_conic_render_plan",
    }
    assert forbidden_public_names.isdisjoint(public_engine.__all__)
    for path in package_root.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "stage14_parameterized_probe" not in source
