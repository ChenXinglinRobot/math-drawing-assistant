"""Stage 15-B P3-3/P3-4/P3-5 approval receipt tamper matrix."""

from __future__ import annotations

from enum import Enum
from fractions import Fraction

import pytest

from math_drawing_assistant.config import DEFAULT_LIMITS
from math_drawing_assistant.engine.plot_analyzer import analyze_plot_item
from math_drawing_assistant.engine.render_plan_builder import RenderPlanBuilder
from math_drawing_assistant.engine.viewport_resolver import resolve_single_item_viewport
from math_drawing_assistant.models import (
    ErrorInfo,
    InputSource,
    PlotItemRequest,
    PlotKind,
    PlotSceneSpec,
    RenderPlan,
    ViewportMode,
    ViewportRequest,
    validate_approved_render_plan,
)


def _plan(text: str) -> RenderPlan:
    request = PlotItemRequest(
        item_id="receipt-item",
        input_text=text,
        input_source=InputSource.MANUAL,
        requested_plot_kind=PlotKind.AUTO,
        display_order=0,
    )
    spec = analyze_plot_item(request)
    assert not isinstance(spec, ErrorInfo)
    scene = PlotSceneSpec(items=(spec,))
    resolution = resolve_single_item_viewport(
        scene,
        ViewportRequest(
            mode=ViewportMode.MANUAL,
            x_min=-10,
            x_max=10,
            y_min=-10,
            y_max=10,
        ),
    )
    assert resolution.error is None and resolution.viewport is not None
    plan = RenderPlanBuilder(limits=DEFAULT_LIMITS).build(
        scene,
        resolution.viewport,
        image_width=400,
        image_height=300,
        dpi=96,
        show_grid=True,
        show_legend=False,
    )
    assert type(plan) is RenderPlan
    assert validate_approved_render_plan(plan) is plan
    assert plan._approval_receipt is not None
    return plan


def _tampered(value: object) -> object:
    if type(value) is bool:
        return not value
    if type(value) is int:
        return value + 1
    if type(value) is float:
        return value + 0.125
    if type(value) is str:
        return value + "-tampered"
    if value is None:
        return "tampered-version"
    if type(value) is Fraction:
        return value + 1
    if isinstance(value, Enum):
        return next(member for member in type(value) if member is not value)
    raise AssertionError(f"no tamper value for {type(value)!r}")


def _assert_rejected_without_receipt_reissue(
    plan: RenderPlan,
    target: object,
    field_name: str,
) -> None:
    receipt = plan._approval_receipt
    original = getattr(target, field_name)
    object.__setattr__(target, field_name, _tampered(original))
    with pytest.raises((AttributeError, TypeError, ValueError)):
        validate_approved_render_plan(plan)
    assert plan._approval_receipt is receipt


FRACTION_FIELDS = (
    ("x^2+y^2=25", "center_x"),
    ("x^2+y^2=25", "center_y"),
    ("x^2+y^2=25", "radius_squared"),
    ("x^2/9+y^2/4=1", "center_x"),
    ("x^2/9+y^2/4=1", "center_y"),
    ("x^2/9+y^2/4=1", "semi_axis_x_squared"),
    ("x^2/9+y^2/4=1", "semi_axis_y_squared"),
    ("x^2/9-y^2/4=1", "center_x"),
    ("x^2/9-y^2/4=1", "center_y"),
    ("x^2/9-y^2/4=1", "semi_transverse_squared"),
    ("x^2/9-y^2/4=1", "semi_conjugate_squared"),
    ("x^2=4*y", "vertex_x"),
    ("x^2=4*y", "vertex_y"),
    ("x^2=4*y", "focal_parameter"),
)


@pytest.mark.parametrize(("text", "field_name"), FRACTION_FIELDS)
def test_all_fourteen_geometry_fraction_fields_are_receipt_bound(
    text: str,
    field_name: str,
) -> None:
    assert len(FRACTION_FIELDS) == 14
    plan = _plan(text)
    _assert_rejected_without_receipt_reissue(
        plan,
        plan.scene_spec.items[0],
        field_name,
    )


@pytest.mark.parametrize(
    "text",
    (
        "y=x^2",
        "x+y=1",
        "x^2+y^2=25",
        "x^2/9+y^2/4=1",
        "x^2/9-y^2/4=1",
        "x^2=4*y",
    ),
)
def test_each_exact_spec_item_id_is_receipt_bound(text: str) -> None:
    plan = _plan(text)
    _assert_rejected_without_receipt_reissue(
        plan,
        plan.scene_spec.items[0],
        "item_id",
    )


def test_explicit_item_plan_item_id_is_receipt_bound() -> None:
    plan = _plan("y=x^2")
    assert plan.item_plan is not None
    _assert_rejected_without_receipt_reissue(plan, plan.item_plan, "item_id")


EXPLICIT_PLAN_SNAPSHOT_FIELDS = (
    ("viewport", "x_min"),
    ("viewport", "x_max"),
    ("viewport", "y_min"),
    ("viewport", "y_max"),
    ("viewport", "aspect"),
    ("viewport", "source"),
    ("plan", "image_width"),
    ("plan", "image_height"),
    ("plan", "dpi"),
    ("plan", "show_grid"),
    ("plan", "show_legend"),
    ("plan", "plan_version"),
    ("plan", "limits_version"),
    ("plan", "sampling_policy_version"),
    ("plan", "numeric_executor_contract_version"),
    ("plan", "parameterized_sampler_contract_version"),
    ("item_plan", "item_id"),
    ("item_plan", "sample_count"),
    ("item_plan", "batch_size"),
    ("item_plan", "max_segment_count"),
    ("item_plan", "max_live_float64_vectors"),
    ("memory", "final_x_bytes"),
    ("memory", "final_y_bytes"),
    ("memory", "artist_data_bytes"),
    ("memory", "validity_mask_bytes"),
    ("memory", "segment_index_range_bytes"),
    ("memory", "segment_metadata_bytes"),
    ("memory", "executor_extra_batch_bytes"),
    ("memory", "rgba_canvas_bytes"),
    ("memory", "png_buffer_reserve_bytes"),
    ("memory", "png_copy_bytes"),
)


@pytest.mark.parametrize(("target_name", "field_name"), EXPLICIT_PLAN_SNAPSHOT_FIELDS)
def test_explicit_plan_side_snapshot_rejects_every_field_tamper(
    target_name: str,
    field_name: str,
) -> None:
    assert len(EXPLICIT_PLAN_SNAPSHOT_FIELDS) == 31
    plan = _plan("y=x^2")
    targets = {
        "viewport": plan.resolved_viewport,
        "plan": plan,
        "item_plan": plan.item_plan,
        "memory": plan.memory_budget,
    }
    target = targets[target_name]
    assert target is not None
    _assert_rejected_without_receipt_reissue(plan, target, field_name)
