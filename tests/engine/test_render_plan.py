"""Stage 8C-1 tests for scalar render planning and formal budget approval."""

from __future__ import annotations

from dataclasses import replace
from math import inf
from pathlib import Path

import pytest

from math_drawing_assistant.config import DEFAULT_LIMITS
from math_drawing_assistant.engine import (
    RenderPlanBuilder,
    analyze_explicit_function,
    build_explicit_scene_spec,
    build_single_explicit_render_plan,
)
from math_drawing_assistant.engine import render_plan_builder
from math_drawing_assistant.models import render_plan as render_plan_model
from math_drawing_assistant.models import (
    DEFAULT_EXPLICIT_SAMPLING_POLICY,
    AspectRequest,
    ErrorCode,
    ErrorInfo,
    ExplicitSamplingPolicy,
    InputSource,
    PlotItemRequest,
    PlotKind,
    PlotSceneSpec,
    RenderPlan,
    ResolvedViewport,
    ValidatedExplicitExpression,
    ViewportSource,
    validate_approved_render_plan,
)


def _scene(text: str = "x", *, item_id: str = "plan-item") -> PlotSceneSpec:
    validated = analyze_explicit_function(text)
    assert isinstance(validated, ValidatedExplicitExpression), validated
    item_request = PlotItemRequest(
        item_id=item_id,
        input_text=text,
        input_source=InputSource.MANUAL,
        requested_plot_kind=PlotKind.EXPLICIT_FUNCTION,
        display_order=0,
    )
    result = build_explicit_scene_spec(item_request, validated)
    assert isinstance(result, PlotSceneSpec), result
    return result


def _viewport() -> ResolvedViewport:
    return ResolvedViewport(
        x_min=-10,
        x_max=10,
        y_min=-8,
        y_max=8,
        aspect=AspectRequest.AUTO,
        source=ViewportSource.MANUAL,
    )


def _plan(**kwargs: object) -> RenderPlan | ErrorInfo:
    defaults: dict[str, object] = {
        "scene_spec": _scene(),
        "resolved_viewport": _viewport(),
        "image_width": 800,
        "image_height": 600,
        "dpi": 96,
        "show_grid": True,
        "show_legend": True,
    }
    defaults.update(kwargs)
    return build_single_explicit_render_plan(**defaults)  # type: ignore[arg-type]


def _success(**kwargs: object) -> RenderPlan:
    result = _plan(**kwargs)
    assert isinstance(result, RenderPlan), result
    return result


def _error(**kwargs: object) -> ErrorInfo:
    result = _plan(**kwargs)
    assert isinstance(result, ErrorInfo), result
    return result


def _forged_viewport(**overrides: object) -> ResolvedViewport:
    """Produce a tampered value object without invoking its public constructor."""

    values: dict[str, object] = {
        "x_min": -10.0,
        "x_max": 10.0,
        "y_min": -8.0,
        "y_max": 8.0,
        "aspect": AspectRequest.AUTO,
        "source": ViewportSource.MANUAL,
    }
    values.update(overrides)
    value = object.__new__(ResolvedViewport)
    for name, field_value in values.items():
        object.__setattr__(value, name, field_value)
    return value


def test_single_explicit_item_builds_an_approved_scalar_plan() -> None:
    plan = _success()

    assert validate_approved_render_plan(plan) is plan
    assert plan.item_plan is not None
    assert plan.memory_budget is not None
    assert plan.item_plan.sample_count == 1_600
    assert plan.item_plan.batch_size == 1_600
    assert plan.limits_version == DEFAULT_LIMITS.version
    assert plan.sampling_policy_version == DEFAULT_EXPLICIT_SAMPLING_POLICY.version
    assert (plan.resolved_viewport.x_min, plan.resolved_viewport.x_max) == (-10.0, 10.0)


def test_ordinary_construction_is_not_sampler_approved() -> None:
    ordinary = RenderPlan(
        scene_spec=_scene(),
        resolved_viewport=_viewport(),
        image_width=800,
        image_height=600,
        dpi=96,
        plan_version="ordinary",
        limits_version=DEFAULT_LIMITS.version,
    )

    with pytest.raises(TypeError, match="approval receipt"):
        validate_approved_render_plan(ordinary)


def test_budget_components_follow_the_published_scalar_formula() -> None:
    plan = _success()
    assert plan.item_plan is not None
    assert plan.memory_budget is not None
    item = plan.item_plan
    budget = plan.memory_budget

    assert budget.final_x_bytes == item.sample_count * 8
    assert budget.final_y_bytes == item.sample_count * 8
    assert budget.validity_mask_bytes == item.sample_count
    assert budget.segment_index_range_bytes == item.max_segment_count * 2 * 8
    assert budget.executor_extra_batch_bytes == (
        max(item.max_live_float64_vectors - 1, 0) * item.batch_size * 8
    )
    assert budget.rgba_canvas_bytes == plan.image_width * plan.image_height * 4
    assert budget.png_buffer_reserve_bytes == DEFAULT_LIMITS.max_png_bytes
    assert budget.total_bytes == budget.fixed_bytes + budget.executor_extra_batch_bytes


def test_sample_count_changes_with_width_and_obeys_policy() -> None:
    narrow = _success(image_width=320)
    wide = _success(image_width=1_200)
    assert narrow.item_plan is not None
    assert wide.item_plan is not None
    assert narrow.item_plan.sample_count == 640
    assert wide.item_plan.sample_count == 2_400
    assert wide.item_plan.sample_count < DEFAULT_LIMITS.max_sample_points_per_item


def test_batch_is_shrunk_from_preference_then_minimum_failure_is_resource_error() -> None:
    baseline = _success()
    assert baseline.memory_budget is not None
    tight_limits = replace(
        DEFAULT_LIMITS,
        max_estimated_memory_bytes=baseline.memory_budget.fixed_bytes + 100 * 8,
    )
    reduced = RenderPlanBuilder(limits=tight_limits).build(
        _scene(),
        _viewport(),
        image_width=800,
        image_height=600,
        dpi=96,
        show_grid=True,
        show_legend=True,
    )
    assert isinstance(reduced, RenderPlan), reduced
    assert reduced.item_plan is not None
    assert reduced.item_plan.batch_size == 100

    impossible_limits = replace(
        DEFAULT_LIMITS,
        max_estimated_memory_bytes=baseline.memory_budget.fixed_bytes + 7,
    )
    failure = RenderPlanBuilder(limits=impossible_limits).build(
        _scene(),
        _viewport(),
        image_width=800,
        image_height=600,
        dpi=96,
        show_grid=True,
        show_legend=True,
    )
    assert isinstance(failure, ErrorInfo)
    assert failure.code is ErrorCode.RESOURCE_LIMIT_EXCEEDED
    assert failure.recoverable is True
    assert failure.field_name == "max_estimated_memory_bytes"


def test_liveness_one_has_no_executor_extra_batch_budget() -> None:
    plan = _success(scene_spec=_scene("2"))
    assert plan.item_plan is not None
    assert plan.memory_budget is not None
    assert plan.item_plan.max_live_float64_vectors == 1
    assert plan.memory_budget.executor_extra_batch_bytes == 0


@pytest.mark.parametrize(
    "scene_spec",
    [
        _forged_scene := object.__new__(PlotSceneSpec),
        PlotSceneSpec(items=(_scene().items[0], _scene(item_id="second").items[0])),
        object(),
    ],
)
def test_empty_multi_or_wrong_scene_is_rejected(scene_spec: object) -> None:
    if type(scene_spec) is PlotSceneSpec and not hasattr(scene_spec, "items"):
        object.__setattr__(scene_spec, "items", ())
    error = _error(scene_spec=scene_spec)
    assert error.code in {ErrorCode.INVALID_REQUEST, ErrorCode.INTERNAL_ERROR}


@pytest.mark.parametrize(
    ("kwargs", "field"),
    [
        ({"image_width": True}, "output"),
        ({"image_width": 800.0}, "output"),
        ({"image_width": DEFAULT_LIMITS.min_image_width - 1}, "output"),
        ({"image_height": DEFAULT_LIMITS.max_image_height + 1}, "output"),
        ({"dpi": DEFAULT_LIMITS.max_dpi + 1}, "output"),
        ({"show_grid": 1}, "output"),
    ],
)
def test_output_scalar_boundaries_are_strict(
    kwargs: dict[str, object], field: str
) -> None:
    error = _error(**kwargs)
    assert error.code is ErrorCode.INVALID_REQUEST
    assert error.field_name == field


@pytest.mark.parametrize(
    ("viewport", "field"),
    [
        (_forged_viewport(x_min=inf), "resolved_viewport.x_min"),
        (_forged_viewport(x_min=2, x_max=1), "resolved_viewport.x_bounds"),
        (_forged_viewport(x_max=-9.5), "resolved_viewport.x_bounds"),
        (_forged_viewport(x_min=-1_000_001, x_max=1_000_001), "resolved_viewport.x_bounds"),
        (_forged_viewport(x_min=-10_000_001), "resolved_viewport.x_bounds"),
        (_forged_viewport(x_min=True), "resolved_viewport.x_min"),
        (_forged_viewport(aspect="auto"), "resolved_viewport.aspect"),
    ],
)
def test_viewport_is_revalidated_against_active_limits(
    viewport: ResolvedViewport, field: str
) -> None:
    error = _error(resolved_viewport=viewport)
    assert error.code is ErrorCode.INVALID_REQUEST
    assert error.field_name == field


def test_legal_ordinary_viewport_value_is_revalidated_and_accepted() -> None:
    viewport = ResolvedViewport(
        x_min=-2,
        x_max=3,
        y_min=-4,
        y_max=5,
        aspect=AspectRequest.EQUAL,
        source=ViewportSource.AUTO_PROBE,
    )
    plan = _success(resolved_viewport=viewport)
    assert plan.resolved_viewport is viewport


def test_viewport_failure_precedes_numeric_cost_or_any_sampling_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("invalid viewport must fail before numeric work")

    monkeypatch.setattr(render_plan_builder, "estimate_numeric_execution_cost", forbidden)
    error = _error(resolved_viewport=_forged_viewport(x_min=inf))
    assert error.code is ErrorCode.INVALID_REQUEST


def test_versions_are_fixed_and_spec_mismatch_is_internal_error() -> None:
    active_limits = replace(DEFAULT_LIMITS, version="limits-test-other")
    result = RenderPlanBuilder(limits=active_limits).build(
        _scene(),
        _viewport(),
        image_width=800,
        image_height=600,
        dpi=96,
        show_grid=True,
        show_legend=True,
    )
    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.INTERNAL_ERROR


def test_plan_tampering_or_forged_receipt_is_rejected() -> None:
    tampered = _success()
    object.__setattr__(tampered, "image_width", 801)
    with pytest.raises(ValueError, match="do not match"):
        validate_approved_render_plan(tampered)

    forged = _success()
    fake_receipt = object.__new__(render_plan_model._RenderPlanApprovalReceipt)
    object.__setattr__(forged, "_approval_receipt", fake_receipt)
    with pytest.raises(ValueError, match="receipt is invalid"):
        validate_approved_render_plan(forged)


def test_approval_snapshot_rejects_viewport_replacements() -> None:
    nonfinite = _success()
    object.__setattr__(nonfinite, "resolved_viewport", _forged_viewport(x_min=-inf))
    with pytest.raises(ValueError, match="do not match"):
        validate_approved_render_plan(nonfinite)

    different_bounds = _success()
    object.__setattr__(
        different_bounds,
        "resolved_viewport",
        ResolvedViewport(
            x_min=-9,
            x_max=10,
            y_min=-8,
            y_max=8,
            aspect=AspectRequest.AUTO,
            source=ViewportSource.MANUAL,
        ),
    )
    with pytest.raises(ValueError, match="do not match"):
        validate_approved_render_plan(different_bounds)


def test_approval_snapshot_rejects_a_legal_different_scene() -> None:
    plan = _success(scene_spec=_scene("2"))
    object.__setattr__(plan, "scene_spec", _scene("sin(x) + cos(x)"))

    with pytest.raises(ValueError, match="do not match"):
        validate_approved_render_plan(plan)


def test_approval_snapshot_rejects_budget_component_tampering() -> None:
    plan = _success()
    assert plan.memory_budget is not None
    altered_budget = replace(
        plan.memory_budget,
        final_x_bytes=plan.memory_budget.final_x_bytes - 8,
        executor_extra_batch_bytes=plan.memory_budget.executor_extra_batch_bytes + 8,
    )
    assert altered_budget.total_bytes == plan.memory_budget.total_bytes
    object.__setattr__(plan, "memory_budget", altered_budget)

    with pytest.raises(ValueError, match="do not match"):
        validate_approved_render_plan(plan)


def test_approval_snapshot_rejects_display_option_tampering_and_is_stable() -> None:
    plan = _success()
    receipt = plan._approval_receipt
    item_plan = plan.item_plan
    memory_budget = plan.memory_budget
    assert validate_approved_render_plan(plan) is plan
    assert validate_approved_render_plan(plan) is plan
    assert plan._approval_receipt is receipt
    assert plan.item_plan is item_plan
    assert plan.memory_budget is memory_budget

    object.__setattr__(plan, "show_grid", False)
    with pytest.raises(ValueError, match="do not match"):
        validate_approved_render_plan(plan)


def test_policy_contract_is_frozen_scalar_only_and_engine_has_no_gui_dependencies() -> None:
    policy = ExplicitSamplingPolicy(
        version="test-policy",
        points_per_horizontal_pixel=1,
        min_sample_points=1,
        preferred_batch_points=1,
        preferred_max_segment_count=1,
        cancellation_check_interval=1,
        finite_jump_threshold=1,
        dense_oscillation_proxy_threshold=1,
    )
    assert policy.version == "test-policy"
    source = Path(render_plan_builder.__file__).read_text(encoding="utf-8")
    assert "numpy" not in source.lower()
    assert "matplotlib" not in source.lower()
    assert "pyside" not in source.lower()
