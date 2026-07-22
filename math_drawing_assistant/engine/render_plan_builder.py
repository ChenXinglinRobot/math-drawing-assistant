"""Stage 8C-1 scalar-only construction and approval of one explicit render plan."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from math_drawing_assistant.config import ApplicationLimits, DEFAULT_LIMITS
from math_drawing_assistant.engine.numeric_executor import (
    NUMERIC_EXECUTOR_CONTRACT_VERSION,
    NumericExecutionCost,
    estimate_numeric_execution_cost,
)
from math_drawing_assistant.models.errors import ErrorCode, ErrorInfo
from math_drawing_assistant.models.plot_specs import (
    ExplicitFunctionSpec,
    PlotSceneSpec,
    _validate_validated_explicit_expression,
)
from math_drawing_assistant.models.render_plan import (
    DEFAULT_EXPLICIT_SAMPLING_POLICY,
    RENDER_PLAN_CONTRACT_VERSION,
    ExplicitRenderItemPlan,
    ExplicitSamplingPolicy,
    RenderMemoryBudget,
    RenderPlan,
    _approve_render_plan,
)
from math_drawing_assistant.models.state import AspectRequest, ViewportSource
from math_drawing_assistant.models.viewport import ResolvedViewport


_FLOAT64_BYTES = 8
_RGBA_BYTES_PER_PIXEL = 4
_SEGMENT_INDEX_RANGE_BYTES = 2 * _FLOAT64_BYTES


@dataclass(frozen=True, slots=True)
class RenderPlanBuilder:
    """Build the only stage 8C-1 plan: one explicit item and scalar outputs."""

    limits: ApplicationLimits = DEFAULT_LIMITS
    sampling_policy: ExplicitSamplingPolicy = DEFAULT_EXPLICIT_SAMPLING_POLICY

    def build(
        self,
        scene_spec: PlotSceneSpec,
        resolved_viewport: ResolvedViewport,
        *,
        image_width: int,
        image_height: int,
        dpi: int,
        show_grid: bool,
        show_legend: bool,
    ) -> RenderPlan | ErrorInfo:
        """Approve a plan without executing, probing, or allocating sample arrays."""

        limits_or_error = _validated_limits(self.limits)
        if isinstance(limits_or_error, ErrorInfo):
            return limits_or_error
        limits = limits_or_error
        policy_or_error = _validated_policy(self.sampling_policy)
        if isinstance(policy_or_error, ErrorInfo):
            return policy_or_error
        policy = policy_or_error

        spec_or_error = _validated_single_explicit_spec(scene_spec, limits=limits)
        if isinstance(spec_or_error, ErrorInfo):
            return spec_or_error
        spec = spec_or_error

        viewport_error = _validate_resolved_viewport(resolved_viewport, limits=limits)
        if viewport_error is not None:
            return viewport_error
        output_error = _validate_output_scalars(
            image_width=image_width,
            image_height=image_height,
            dpi=dpi,
            show_grid=show_grid,
            show_legend=show_legend,
            limits=limits,
        )
        if output_error is not None:
            return output_error

        sample_count_or_error = _planned_sample_count(
            image_width=image_width,
            limits=limits,
            policy=policy,
            item_id=spec.item_id,
        )
        if isinstance(sample_count_or_error, ErrorInfo):
            return sample_count_or_error
        sample_count = sample_count_or_error
        max_segment_count = min(
            policy.preferred_max_segment_count,
            limits.max_branches_per_item,
            limits.max_total_branches,
        )

        # This is only the stage 8A scalar AST liveness estimator; it never
        # executes the expression or creates an x/y array.
        execution_cost = estimate_numeric_execution_cost(spec, limits=limits)
        if isinstance(execution_cost, ErrorInfo):
            return _internal_error(
                "numeric_executor",
                "numeric executor contract rejected the validated specification",
                item_id=spec.item_id,
            )
        if type(execution_cost) is not NumericExecutionCost:
            return _internal_error(
                "numeric_executor",
                "numeric executor cost result type mismatch",
                item_id=spec.item_id,
            )

        plan_or_error = _plan_memory_and_batch(
            item_id=spec.item_id,
            sample_count=sample_count,
            max_segment_count=max_segment_count,
            execution_cost=execution_cost,
            image_width=image_width,
            image_height=image_height,
            limits=limits,
            policy=policy,
        )
        if isinstance(plan_or_error, ErrorInfo):
            return plan_or_error
        item_plan, memory_budget = plan_or_error

        try:
            limits.validate_scene_resources(
                item_count=1,
                sample_points_per_item=item_plan.sample_count,
                total_sample_points=item_plan.sample_count,
                branches_per_item=item_plan.max_segment_count,
                total_branches=item_plan.max_segment_count,
                estimated_memory_bytes=memory_budget.total_bytes,
            )
            plan = RenderPlan(
                scene_spec=scene_spec,
                resolved_viewport=resolved_viewport,
                image_width=image_width,
                image_height=image_height,
                dpi=dpi,
                plan_version=RENDER_PLAN_CONTRACT_VERSION,
                limits_version=limits.version,
                show_grid=show_grid,
                show_legend=show_legend,
                sampling_policy_version=policy.version,
                numeric_executor_contract_version=(
                    NUMERIC_EXECUTOR_CONTRACT_VERSION
                ),
                item_plan=item_plan,
                memory_budget=memory_budget,
            )
            return _approve_render_plan(plan)
        except (AttributeError, TypeError, ValueError):
            return _internal_error(
                "render_plan",
                "approved render-plan contract construction failed",
                item_id=spec.item_id,
            )


def build_single_explicit_render_plan(
    scene_spec: PlotSceneSpec,
    resolved_viewport: ResolvedViewport,
    *,
    image_width: int,
    image_height: int,
    dpi: int,
    show_grid: bool,
    show_legend: bool,
    limits: ApplicationLimits = DEFAULT_LIMITS,
    sampling_policy: ExplicitSamplingPolicy = DEFAULT_EXPLICIT_SAMPLING_POLICY,
) -> RenderPlan | ErrorInfo:
    """Convenience entry point for the scalar-only stage 8C-1 pipeline."""

    return RenderPlanBuilder(limits=limits, sampling_policy=sampling_policy).build(
        scene_spec,
        resolved_viewport,
        image_width=image_width,
        image_height=image_height,
        dpi=dpi,
        show_grid=show_grid,
        show_legend=show_legend,
    )


def _validated_limits(limits: object) -> ApplicationLimits | ErrorInfo:
    if type(limits) is not ApplicationLimits:
        return _internal_error("limits", "builder requires an exact ApplicationLimits")
    try:
        limits.__post_init__()
    except (AttributeError, TypeError, ValueError):
        return _internal_error("limits", "active limits contract mismatch")
    return limits


def _validated_policy(policy: object) -> ExplicitSamplingPolicy | ErrorInfo:
    if type(policy) is not ExplicitSamplingPolicy:
        return _internal_error(
            "sampling_policy",
            "builder requires an exact ExplicitSamplingPolicy",
        )
    try:
        policy.__post_init__()
    except (AttributeError, TypeError, ValueError):
        return _internal_error("sampling_policy", "sampling policy contract mismatch")
    return policy


def _validated_single_explicit_spec(
    scene_spec: object,
    *,
    limits: ApplicationLimits,
) -> ExplicitFunctionSpec | ErrorInfo:
    if type(scene_spec) is not PlotSceneSpec:
        return _invalid_request("scene_spec", "builder requires an exact PlotSceneSpec")
    if len(scene_spec.items) != 1:
        return _invalid_request("scene_spec", "builder requires exactly one scene item")
    spec = scene_spec.items[0]
    if type(spec) is not ExplicitFunctionSpec:
        return _invalid_request(
            "scene_spec",
            "builder requires an exact ExplicitFunctionSpec item",
        )
    try:
        scene_spec.__post_init__()
        spec.__post_init__()
        _validate_validated_explicit_expression(
            spec.validated_expression,
            active_limits_version=limits.version,
        )
    except (AttributeError, TypeError, ValueError):
        return _internal_error(
            "scene_spec",
            "explicit specification limits contract is not active",
            item_id=spec.item_id,
        )
    return spec


def _validate_resolved_viewport(
    viewport: object,
    *,
    limits: ApplicationLimits,
) -> ErrorInfo | None:
    """Revalidate the value object against current planning limits without mutating it."""

    if type(viewport) is not ResolvedViewport:
        return _invalid_request(
            "resolved_viewport",
            "builder requires an exact ResolvedViewport",
        )
    if type(viewport.aspect) is not AspectRequest:
        return _invalid_request("resolved_viewport.aspect", "aspect is not published")
    if type(viewport.source) is not ViewportSource:
        return _invalid_request("resolved_viewport.source", "source is not published")
    values: dict[str, float] = {}
    for name in ("x_min", "x_max", "y_min", "y_max"):
        value = getattr(viewport, name, None)
        if type(value) not in {int, float}:
            return _invalid_request(
                f"resolved_viewport.{name}",
                "viewport boundary is not an allowed finite number",
            )
        numeric_value = float(value)
        if not isfinite(numeric_value):
            return _invalid_request(
                f"resolved_viewport.{name}",
                "viewport boundary is not finite",
            )
        values[name] = numeric_value
    for axis in ("x", "y"):
        minimum = values[f"{axis}_min"]
        maximum = values[f"{axis}_max"]
        if minimum >= maximum:
            return _invalid_request(
                f"resolved_viewport.{axis}_bounds",
                "viewport minimum is not below maximum",
            )
        span = maximum - minimum
        if span < limits.min_viewport_span or span > limits.max_viewport_span:
            return _invalid_request(
                f"resolved_viewport.{axis}_bounds",
                "viewport span is outside the active limits",
            )
        if max(abs(minimum), abs(maximum)) > limits.max_viewport_absolute_coordinate:
            return _invalid_request(
                f"resolved_viewport.{axis}_bounds",
                "viewport coordinate is outside the active limits",
            )
    return None


def _validate_output_scalars(
    *,
    image_width: object,
    image_height: object,
    dpi: object,
    show_grid: object,
    show_legend: object,
    limits: ApplicationLimits,
) -> ErrorInfo | None:
    if type(show_grid) is not bool or type(show_legend) is not bool:
        return _invalid_request("output", "show_grid and show_legend must be bool")
    try:
        limits.validate_output(
            image_width=image_width,  # type: ignore[arg-type]
            image_height=image_height,  # type: ignore[arg-type]
            dpi=dpi,  # type: ignore[arg-type]
            png_bytes=0,
        )
    except (TypeError, ValueError):
        return _invalid_request("output", "output dimensions or dpi are outside limits")
    return None


def _planned_sample_count(
    *,
    image_width: int,
    limits: ApplicationLimits,
    policy: ExplicitSamplingPolicy,
    item_id: str,
) -> int | ErrorInfo:
    sample_count = max(
        policy.min_sample_points,
        image_width * policy.points_per_horizontal_pixel,
    )
    if sample_count > limits.max_sample_points_per_item:
        return _resource_error(
            "max_sample_points_per_item",
            (
                f"sample_count={sample_count}; "
                f"max_sample_points_per_item={limits.max_sample_points_per_item}"
            ),
            item_id=item_id,
        )
    if sample_count > limits.max_total_sample_points:
        return _resource_error(
            "max_total_sample_points",
            (
                f"sample_count={sample_count}; "
                f"max_total_sample_points={limits.max_total_sample_points}"
            ),
            item_id=item_id,
        )
    return sample_count


def _plan_memory_and_batch(
    *,
    item_id: str,
    sample_count: int,
    max_segment_count: int,
    execution_cost: NumericExecutionCost,
    image_width: int,
    image_height: int,
    limits: ApplicationLimits,
    policy: ExplicitSamplingPolicy,
) -> tuple[ExplicitRenderItemPlan, RenderMemoryBudget] | ErrorInfo:
    fixed_budget = RenderMemoryBudget(
        final_x_bytes=sample_count * _FLOAT64_BYTES,
        final_y_bytes=sample_count * _FLOAT64_BYTES,
        validity_mask_bytes=sample_count,
        segment_index_range_bytes=(
            max_segment_count * _SEGMENT_INDEX_RANGE_BYTES
        ),
        executor_extra_batch_bytes=0,
        rgba_canvas_bytes=image_width * image_height * _RGBA_BYTES_PER_PIXEL,
        png_buffer_reserve_bytes=limits.max_png_bytes,
    )
    remaining_bytes = limits.max_estimated_memory_bytes - fixed_budget.fixed_bytes
    if remaining_bytes < 0:
        return _resource_error(
            "max_estimated_memory_bytes",
            (
                f"fixed_bytes={fixed_budget.fixed_bytes}; "
                f"max_estimated_memory_bytes={limits.max_estimated_memory_bytes}"
            ),
            item_id=item_id,
        )
    extra_live_vectors = max(execution_cost.max_live_float64_vectors - 1, 0)
    bytes_per_batch_point = extra_live_vectors * _FLOAT64_BYTES
    if bytes_per_batch_point == 0:
        batch_size = min(policy.preferred_batch_points, sample_count)
    else:
        batch_size = min(
            policy.preferred_batch_points,
            sample_count,
            remaining_bytes // bytes_per_batch_point,
        )
    if batch_size < 1:
        return _resource_error(
            "max_estimated_memory_bytes",
            (
                f"fixed_bytes={fixed_budget.fixed_bytes}; "
                f"bytes_per_batch_point={bytes_per_batch_point}; "
                f"max_estimated_memory_bytes={limits.max_estimated_memory_bytes}"
            ),
            item_id=item_id,
        )
    item_plan = ExplicitRenderItemPlan(
        item_id=item_id,
        sample_count=sample_count,
        batch_size=batch_size,
        max_segment_count=max_segment_count,
        max_live_float64_vectors=execution_cost.max_live_float64_vectors,
    )
    memory_budget = RenderMemoryBudget(
        final_x_bytes=fixed_budget.final_x_bytes,
        final_y_bytes=fixed_budget.final_y_bytes,
        validity_mask_bytes=fixed_budget.validity_mask_bytes,
        segment_index_range_bytes=fixed_budget.segment_index_range_bytes,
        executor_extra_batch_bytes=(bytes_per_batch_point * batch_size),
        rgba_canvas_bytes=fixed_budget.rgba_canvas_bytes,
        png_buffer_reserve_bytes=fixed_budget.png_buffer_reserve_bytes,
    )
    return (item_plan, memory_budget)


def _invalid_request(field_name: str, technical_message: str) -> ErrorInfo:
    return ErrorInfo(
        code=ErrorCode.INVALID_REQUEST,
        user_message="The render-plan request is invalid.",
        technical_message=technical_message,
        field_name=field_name,
        recoverable=True,
    )


def _resource_error(
    field_name: str,
    technical_message: str,
    *,
    item_id: str,
) -> ErrorInfo:
    return ErrorInfo(
        code=ErrorCode.RESOURCE_LIMIT_EXCEEDED,
        user_message="The requested render exceeds the configured resource budget.",
        technical_message=technical_message,
        item_id=item_id,
        field_name=field_name,
        recoverable=True,
    )


def _internal_error(
    field_name: str,
    technical_message: str,
    *,
    item_id: str | None = None,
) -> ErrorInfo:
    return ErrorInfo(
        code=ErrorCode.INTERNAL_ERROR,
        user_message="The render-plan contract is invalid.",
        technical_message=technical_message,
        item_id=item_id,
        field_name=field_name,
        recoverable=False,
    )


__all__ = ["RenderPlanBuilder", "build_single_explicit_render_plan"]
