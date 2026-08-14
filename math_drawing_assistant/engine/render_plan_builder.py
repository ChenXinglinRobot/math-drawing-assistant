"""Stage 8C-1 scalar-only construction and approval of one explicit render plan."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
from fractions import Fraction
from math import acosh, acos, asin, asinh, ceil, cosh, hypot, isfinite, nextafter, pi, sinh, tau, ulp

from math_drawing_assistant.config import ApplicationLimits, DEFAULT_LIMITS
from math_drawing_assistant.engine.numeric_executor import (
    NUMERIC_EXECUTOR_CONTRACT_VERSION,
    NumericExecutionCost,
    estimate_numeric_execution_cost,
)
from math_drawing_assistant.engine.parameterized_budget import (
    build_hyperbola_parameterized_memory_budget,
    build_line_parameterized_memory_budget,
    build_oval_parameterized_memory_budget,
    build_parabola_parameterized_memory_budget,
    plan_hyperbola_batch_size,
    plan_oval_batch_size,
    plan_parabola_batch_size,
)
from math_drawing_assistant.engine.hyperbola_geometry import (
    HyperbolaExecutionGeometry,
    hyperbola_parameter_point,
    project_hyperbola_geometry,
)
from math_drawing_assistant.engine.oval_geometry import (
    OvalExecutionGeometry,
    oval_parameter_point,
    project_oval_geometry,
)
from math_drawing_assistant.engine.parabola_geometry import (
    ParabolaExecutionGeometry,
    parabola_parameter_point,
    project_parabola_geometry,
)
from math_drawing_assistant.models.errors import ErrorCode, ErrorInfo
from math_drawing_assistant.models.plot_specs import (
    AxisOrientation,
    CircleSpec,
    EllipseSpec,
    ExplicitFunctionSpec,
    HyperbolaSpec,
    LineSpec,
    ParabolaSpec,
    PlotSceneSpec,
    _validate_validated_explicit_expression,
)
from math_drawing_assistant.models.render_plan import (
    AngularSamplingPolicy,
    DEFAULT_ANGULAR_SAMPLING_POLICY,
    DEFAULT_EXPLICIT_SAMPLING_POLICY,
    DEFAULT_HYPERBOLIC_SAMPLING_POLICY,
    DEFAULT_LINE_SAMPLING_POLICY,
    DEFAULT_PARABOLIC_SAMPLING_POLICY,
    PARAMETERIZED_SAMPLER_CONTRACT_VERSION,
    RENDER_PLAN_CONTRACT_VERSION,
    ExplicitRenderItemPlan,
    ExplicitSamplingPolicy,
    GeometryRenderItemPlan,
    HyperbolicSamplingPolicy,
    LineSamplingPolicy,
    LineSegmentPlan,
    ParabolicSamplingPolicy,
    ParameterIntervalPlan,
    ParameterizedRenderMemoryBudget,
    RenderMemoryBudget,
    RenderPlan,
    SegmentClosure,
    _approve_render_plan,
)
from math_drawing_assistant.models.state import ResolvedAspect, ViewportSource
from math_drawing_assistant.models.viewport import ResolvedViewport


_FLOAT64_BYTES = 8
_RGBA_BYTES_PER_PIXEL = 4
_SEGMENT_INDEX_RANGE_BYTES = 2 * _FLOAT64_BYTES
_SEGMENT_METADATA_BYTES = 2 * _FLOAT64_BYTES
_GEOMETRY_SPEC_TYPES = (
    LineSpec,
    CircleSpec,
    EllipseSpec,
    HyperbolaSpec,
    ParabolaSpec,
)
_SINGLE_ITEM_SPEC_TYPES = (ExplicitFunctionSpec, *_GEOMETRY_SPEC_TYPES)
_FLOAT64_EPSILON = Fraction(1, 1 << 52)
_MAX_FLOAT64 = sys.float_info.max


@dataclass(frozen=True, slots=True)
class _ExactParabolaParameterBound:
    """A rational parameter or one signed exact square root."""

    rational: Fraction | None
    root_squared: Fraction | None
    root_sign: int


@dataclass(frozen=True, slots=True)
class RenderPlanBuilder:
    """Unified exact-Spec dispatch boundary for one scalar-only render plan."""

    limits: ApplicationLimits = DEFAULT_LIMITS
    sampling_policy: ExplicitSamplingPolicy = DEFAULT_EXPLICIT_SAMPLING_POLICY
    line_sampling_policy: LineSamplingPolicy = DEFAULT_LINE_SAMPLING_POLICY
    angular_sampling_policy: AngularSamplingPolicy = DEFAULT_ANGULAR_SAMPLING_POLICY
    hyperbolic_sampling_policy: HyperbolicSamplingPolicy = (
        DEFAULT_HYPERBOLIC_SAMPLING_POLICY
    )
    parabolic_sampling_policy: ParabolicSamplingPolicy = (
        DEFAULT_PARABOLIC_SAMPLING_POLICY
    )

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

        spec_or_error = _validated_single_spec(scene_spec, limits=limits)
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

        if type(spec) is LineSpec:
            line_policy_or_error = _validated_line_policy(self.line_sampling_policy)
            if isinstance(line_policy_or_error, ErrorInfo):
                return line_policy_or_error
            return _build_line_plan(
                scene_spec,
                spec,
                resolved_viewport,
                image_width=image_width,
                image_height=image_height,
                dpi=dpi,
                show_grid=show_grid,
                show_legend=show_legend,
                limits=limits,
                policy=line_policy_or_error,
            )
        if type(spec) in {CircleSpec, EllipseSpec}:
            angular_policy_or_error = _validated_angular_policy(
                self.angular_sampling_policy,
            )
            if isinstance(angular_policy_or_error, ErrorInfo):
                return angular_policy_or_error
            return _build_oval_plan(
                scene_spec,
                spec,
                resolved_viewport,
                image_width=image_width,
                image_height=image_height,
                dpi=dpi,
                show_grid=show_grid,
                show_legend=show_legend,
                limits=limits,
                policy=angular_policy_or_error,
            )
        if type(spec) is HyperbolaSpec:
            hyperbolic_policy_or_error = _validated_hyperbolic_policy(
                self.hyperbolic_sampling_policy,
            )
            if isinstance(hyperbolic_policy_or_error, ErrorInfo):
                return hyperbolic_policy_or_error
            return _build_hyperbola_plan(
                scene_spec,
                spec,
                resolved_viewport,
                image_width=image_width,
                image_height=image_height,
                dpi=dpi,
                show_grid=show_grid,
                show_legend=show_legend,
                limits=limits,
                policy=hyperbolic_policy_or_error,
            )
        if type(spec) is ParabolaSpec:
            parabolic_policy_or_error = _validated_parabolic_policy(
                self.parabolic_sampling_policy,
            )
            if isinstance(parabolic_policy_or_error, ErrorInfo):
                return parabolic_policy_or_error
            return _build_parabola_plan(
                scene_spec,
                spec,
                resolved_viewport,
                image_width=image_width,
                image_height=image_height,
                dpi=dpi,
                show_grid=show_grid,
                show_legend=show_legend,
                limits=limits,
                policy=parabolic_policy_or_error,
            )
        if type(spec) is not ExplicitFunctionSpec:
            return _internal_error(
                "geometry_strategy",
                "geometry plan construction is not implemented in stage 14B-1",
                item_id=spec.item_id,
            )

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
                parameterized_sampler_contract_version=None,
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


def _validated_line_policy(policy: object) -> LineSamplingPolicy | ErrorInfo:
    if type(policy) is not LineSamplingPolicy:
        return _internal_error(
            "line_sampling_policy",
            "builder requires an exact LineSamplingPolicy",
        )
    try:
        policy.__post_init__()
    except (AttributeError, TypeError, ValueError):
        return _internal_error(
            "line_sampling_policy",
            "line sampling policy contract mismatch",
        )
    if policy != DEFAULT_LINE_SAMPLING_POLICY:
        return _internal_error(
            "line_sampling_policy",
            "line sampling policy version is not active",
        )
    return policy


def _validated_angular_policy(
    policy: object,
) -> AngularSamplingPolicy | ErrorInfo:
    if type(policy) is not AngularSamplingPolicy:
        return _internal_error(
            "angular_sampling_policy",
            "builder requires an exact AngularSamplingPolicy",
        )
    try:
        policy.__post_init__()
    except (AttributeError, TypeError, ValueError):
        return _internal_error(
            "angular_sampling_policy",
            "angular sampling policy contract mismatch",
        )
    if policy != DEFAULT_ANGULAR_SAMPLING_POLICY:
        return _internal_error(
            "angular_sampling_policy",
            "angular sampling policy version is not active",
        )
    return policy


def _validated_hyperbolic_policy(
    policy: object,
) -> HyperbolicSamplingPolicy | ErrorInfo:
    if type(policy) is not HyperbolicSamplingPolicy:
        return _internal_error(
            "hyperbolic_sampling_policy",
            "builder requires an exact HyperbolicSamplingPolicy",
        )
    try:
        policy.__post_init__()
    except (AttributeError, TypeError, ValueError):
        return _internal_error(
            "hyperbolic_sampling_policy",
            "hyperbolic sampling policy contract mismatch",
        )
    if policy != DEFAULT_HYPERBOLIC_SAMPLING_POLICY:
        return _internal_error(
            "hyperbolic_sampling_policy",
            "hyperbolic sampling policy version is not active",
        )
    return policy


def _validated_parabolic_policy(
    policy: object,
) -> ParabolicSamplingPolicy | ErrorInfo:
    if type(policy) is not ParabolicSamplingPolicy:
        return _internal_error(
            "parabolic_sampling_policy",
            "builder requires an exact ParabolicSamplingPolicy",
        )
    try:
        policy.__post_init__()
    except (AttributeError, TypeError, ValueError):
        return _internal_error(
            "parabolic_sampling_policy",
            "parabolic sampling policy contract mismatch",
        )
    if policy != DEFAULT_PARABOLIC_SAMPLING_POLICY:
        return _internal_error(
            "parabolic_sampling_policy",
            "parabolic sampling policy version is not active",
        )
    return policy


def _validated_single_spec(
    scene_spec: object,
    *,
    limits: ApplicationLimits,
) -> (
    ExplicitFunctionSpec
    | LineSpec
    | CircleSpec
    | EllipseSpec
    | HyperbolaSpec
    | ParabolaSpec
    | ErrorInfo
):
    if type(scene_spec) is not PlotSceneSpec:
        return _invalid_request("scene_spec", "builder requires an exact PlotSceneSpec")
    if len(scene_spec.items) != 1:
        return _invalid_request("scene_spec", "builder requires exactly one scene item")
    spec = scene_spec.items[0]
    if type(spec) not in _SINGLE_ITEM_SPEC_TYPES:
        return _invalid_request(
            "scene_spec",
            "builder requires one exact supported Stage 13 item",
        )
    try:
        scene_spec.__post_init__()
        spec.__post_init__()
        if type(spec) is ExplicitFunctionSpec:
            _validate_validated_explicit_expression(
                spec.validated_expression,
                active_limits_version=limits.version,
            )
        else:
            spec.coefficients.__post_init__()
            spec.provenance.__post_init__()
            spec.provenance.normalized_span.__post_init__()
            spec.provenance.source_span.__post_init__()
            if spec.provenance.limits_version != limits.version:
                raise ValueError("geometry specification limits version is not active")
    except (AttributeError, TypeError, ValueError):
        return _internal_error(
            "scene_spec",
            "specification limits contract is not active",
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
    if type(viewport.aspect) is not ResolvedAspect:
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
        artist_data_bytes=sample_count * _FLOAT64_BYTES * 2,
        validity_mask_bytes=sample_count,
        segment_index_range_bytes=(
            max_segment_count * _SEGMENT_INDEX_RANGE_BYTES
        ),
        segment_metadata_bytes=max_segment_count * _SEGMENT_METADATA_BYTES,
        executor_extra_batch_bytes=0,
        rgba_canvas_bytes=image_width * image_height * _RGBA_BYTES_PER_PIXEL,
        png_buffer_reserve_bytes=limits.max_png_bytes,
        png_copy_bytes=limits.max_png_bytes,
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
        artist_data_bytes=fixed_budget.artist_data_bytes,
        validity_mask_bytes=fixed_budget.validity_mask_bytes,
        segment_index_range_bytes=fixed_budget.segment_index_range_bytes,
        segment_metadata_bytes=fixed_budget.segment_metadata_bytes,
        executor_extra_batch_bytes=(bytes_per_batch_point * batch_size),
        rgba_canvas_bytes=fixed_budget.rgba_canvas_bytes,
        png_buffer_reserve_bytes=fixed_budget.png_buffer_reserve_bytes,
        png_copy_bytes=fixed_budget.png_copy_bytes,
    )
    return (item_plan, memory_budget)


def _build_line_plan(
    scene_spec: PlotSceneSpec,
    spec: LineSpec,
    resolved_viewport: ResolvedViewport,
    *,
    image_width: int,
    image_height: int,
    dpi: int,
    show_grid: bool,
    show_legend: bool,
    limits: ApplicationLimits,
    policy: LineSamplingPolicy,
) -> RenderPlan | ErrorInfo:
    """Approve one exact visible general-line segment and its full budget."""

    try:
        memory_budget = build_line_parameterized_memory_budget(
            image_width=image_width,
            image_height=image_height,
            limits=limits,
        )
    except MemoryError:
        return _resource_error(
            "max_estimated_memory_bytes",
            "line parameterized budget construction failed",
            item_id=spec.item_id,
        )
    except (AttributeError, TypeError, ValueError):
        return _internal_error(
            "parameterized_budget",
            "line parameterized budget contract mismatch",
            item_id=spec.item_id,
        )
    try:
        limits.validate_scene_resources(
            item_count=1,
            sample_points_per_item=policy.sample_count,
            total_sample_points=policy.sample_count,
            branches_per_item=1,
            total_branches=1,
            estimated_memory_bytes=memory_budget.total_bytes,
        )
    except (TypeError, ValueError):
        return _resource_error(
            "line_plan_resources",
            "line sampling plan exceeds active scene resource limits",
            item_id=spec.item_id,
        )

    try:
        segment_or_error = _line_segment_for_viewport(
            spec,
            resolved_viewport,
            policy=policy,
        )
    except MemoryError:
        return _resource_error(
            "max_estimated_memory_bytes",
            "approved exact line workspace allocation failed",
            item_id=spec.item_id,
        )
    if isinstance(segment_or_error, ErrorInfo):
        return segment_or_error
    segment = segment_or_error

    try:
        item_plan = GeometryRenderItemPlan(
            item_id=spec.item_id,
            mathematical_branch_count=1,
            segments=(segment,),
            sample_count=policy.sample_count,
            batch_size=policy.batch_size,
            max_segment_count=1,
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
            numeric_executor_contract_version=None,
            parameterized_sampler_contract_version=(
                PARAMETERIZED_SAMPLER_CONTRACT_VERSION
            ),
            item_plan=item_plan,
            memory_budget=memory_budget,
        )
        return _approve_render_plan(plan)
    except MemoryError:
        return _resource_error(
            "max_estimated_memory_bytes",
            "line render-plan approval allocation failed",
            item_id=spec.item_id,
        )
    except (AttributeError, TypeError, ValueError):
        return _internal_error(
            "render_plan",
            "approved line render-plan contract construction failed",
            item_id=spec.item_id,
        )


def _build_oval_plan(
    scene_spec: PlotSceneSpec,
    spec: CircleSpec | EllipseSpec,
    resolved_viewport: ResolvedViewport,
    *,
    image_width: int,
    image_height: int,
    dpi: int,
    show_grid: bool,
    show_legend: bool,
    limits: ApplicationLimits,
    policy: AngularSamplingPolicy,
) -> RenderPlan | ErrorInfo:
    """Approve visible angular intervals and the complete Circle/Ellipse budget."""

    try:
        geometry = project_oval_geometry(spec)
        interval_bounds_or_error = _plan_visible_oval_intervals(
            geometry,
            resolved_viewport,
            policy=policy,
        )
    except MemoryError:
        return _resource_error(
            "max_estimated_memory_bytes",
            "oval interval-planning workspace allocation failed",
            item_id=spec.item_id,
        )
    except (AttributeError, OverflowError, TypeError, ValueError, ZeroDivisionError):
        return _numeric_range_error_for_oval(
            spec.item_id,
            "oval geometry cannot be represented for interval planning",
        )
    if isinstance(interval_bounds_or_error, ErrorInfo):
        return interval_bounds_or_error

    intervals_or_error = _sampled_oval_intervals(
        geometry,
        resolved_viewport,
        interval_bounds_or_error,
        image_width=image_width,
        image_height=image_height,
        limits=limits,
        policy=policy,
    )
    if isinstance(intervals_or_error, ErrorInfo):
        return intervals_or_error
    intervals = intervals_or_error
    total_samples = sum(interval.sample_count for interval in intervals)
    try:
        batch_size = plan_oval_batch_size(
            sample_count=total_samples,
            preferred_batch_points=policy.preferred_batch_points,
            image_width=image_width,
            image_height=image_height,
            limits=limits,
        )
        memory_budget = build_oval_parameterized_memory_budget(
            sample_count=total_samples,
            batch_size=batch_size,
            image_width=image_width,
            image_height=image_height,
            limits=limits,
        )
        try:
            limits.validate_scene_resources(
                item_count=1,
                sample_points_per_item=total_samples,
                total_sample_points=total_samples,
                branches_per_item=4,
                total_branches=4,
                estimated_memory_bytes=memory_budget.total_bytes,
            )
        except (TypeError, ValueError):
            return _resource_error(
                "oval_plan_resources",
                "oval sampling plan exceeds active scene resource limits",
                item_id=spec.item_id,
            )
        item_plan = GeometryRenderItemPlan(
            item_id=spec.item_id,
            mathematical_branch_count=1,
            segments=intervals,
            sample_count=total_samples,
            batch_size=batch_size,
            max_segment_count=4,
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
            numeric_executor_contract_version=None,
            parameterized_sampler_contract_version=(
                PARAMETERIZED_SAMPLER_CONTRACT_VERSION
            ),
            item_plan=item_plan,
            memory_budget=memory_budget,
        )
        return _approve_render_plan(plan)
    except MemoryError:
        return _resource_error(
            "max_estimated_memory_bytes",
            "oval plan or approval allocation failed",
            item_id=spec.item_id,
        )
    except ValueError as exc:
        if "budget cannot fit" in str(exc) or "resource" in str(exc):
            return _resource_error(
                "oval_plan_resources",
                "oval sampling plan exceeds active scene resource limits",
                item_id=spec.item_id,
            )
        return _internal_error(
            "render_plan",
            "approved oval render-plan contract construction failed",
            item_id=spec.item_id,
        )
    except (AttributeError, TypeError):
        return _internal_error(
            "render_plan",
            "approved oval render-plan contract construction failed",
            item_id=spec.item_id,
        )


def _plan_visible_oval_intervals(
    geometry: OvalExecutionGeometry,
    viewport: ResolvedViewport,
    *,
    policy: AngularSamplingPolicy,
) -> tuple[tuple[float, float, SegmentClosure], ...] | ErrorInfo:
    """Find visible arcs using exact boundary roots and a cyclic interval sweep."""

    candidates = [0.0]
    left = Fraction.from_float(viewport.x_min)
    right = Fraction.from_float(viewport.x_max)
    bottom = Fraction.from_float(viewport.y_min)
    top = Fraction.from_float(viewport.y_max)
    for edge in (left, right):
        delta = edge - geometry.center_x
        candidates.extend(
            _x_boundary_angles(
                delta,
                geometry.semi_axis_x_squared,
                geometry.semi_axis_x_float,
            ),
        )
    for edge in (bottom, top):
        delta = edge - geometry.center_y
        candidates.extend(
            _y_boundary_angles(
                delta,
                geometry.semi_axis_y_squared,
                geometry.semi_axis_y_float,
            ),
        )
    angles = _merged_normalized_angles(candidates, policy.angle_merge_ulps)
    visible: list[bool] = []
    for index, start in enumerate(angles):
        stop = angles[index + 1] if index + 1 < len(angles) else angles[0] + tau
        midpoint = start + (stop - start) / 2.0
        x_value, y_value = oval_parameter_point(geometry, midpoint)
        visible.append(
            _inside_closed_viewport(
                x_value,
                y_value,
                viewport,
                ulps=policy.viewport_boundary_ulps,
            ),
        )
    if all(visible):
        return ((0.0, tau, SegmentClosure.CLOSED),)
    if not any(visible):
        return _no_visible_oval_error(
            geometry.spec.item_id,
            "oval has no visible open interval in the viewport",
        )

    runs: list[tuple[float, float, SegmentClosure]] = []
    count = len(angles)
    for index, is_visible in enumerate(visible):
        if not is_visible or visible[(index - 1) % count]:
            continue
        stop_index = index
        while visible[stop_index % count]:
            stop_index += 1
            if stop_index - index > count:
                return _numeric_range_error_for_oval(
                    geometry.spec.item_id,
                    "cyclic oval interval sweep did not terminate",
                )
        start = angles[index]
        stop = angles[stop_index % count]
        if stop <= start:
            stop += tau
        if not isfinite(start) or not isfinite(stop) or not 0.0 < stop - start < tau:
            continue
        runs.append((start, stop, SegmentClosure.OPEN))
    runs.sort(key=lambda interval: interval[0])
    if not runs:
        return _no_visible_oval_error(
            geometry.spec.item_id,
            "visible oval intervals collapsed numerically",
        )
    if len(runs) > 4:
        return _numeric_range_error_for_oval(
            geometry.spec.item_id,
            "oval visibility produced more than four independent arcs",
        )
    return tuple(runs)


def _x_boundary_angles(
    delta: Fraction,
    axis_squared: Fraction,
    axis_float: float,
) -> tuple[float, ...]:
    squared = delta * delta
    if squared > axis_squared:
        return ()
    if squared == axis_squared:
        return (0.0 if delta > 0 else pi,)
    ratio = max(-1.0, min(1.0, float(delta) / axis_float))
    angle = acos(ratio)
    return (angle, tau - angle)


def _y_boundary_angles(
    delta: Fraction,
    axis_squared: Fraction,
    axis_float: float,
) -> tuple[float, ...]:
    squared = delta * delta
    if squared > axis_squared:
        return ()
    if squared == axis_squared:
        return (pi / 2.0 if delta > 0 else 3.0 * pi / 2.0,)
    ratio = max(-1.0, min(1.0, float(delta) / axis_float))
    angle = asin(ratio)
    return (_normalize_angle(angle), _normalize_angle(pi - angle))


def _normalize_angle(value: float) -> float:
    normalized = value % tau
    return 0.0 if normalized == tau else normalized


def _merged_normalized_angles(values: list[float], merge_ulps: int) -> tuple[float, ...]:
    seam_tolerance = merge_ulps * ulp(tau)
    normalized = []
    for value in values:
        angle = _normalize_angle(value)
        if angle <= seam_tolerance or tau - angle <= seam_tolerance:
            angle = 0.0
        normalized.append(angle)
    normalized.sort()
    merged: list[float] = []
    for angle in normalized:
        if not merged or abs(angle - merged[-1]) > seam_tolerance:
            merged.append(angle)
    return tuple(merged)


def _inside_closed_viewport(
    x_value: float,
    y_value: float,
    viewport: ResolvedViewport,
    *,
    ulps: int,
) -> bool:
    return _within_axis_ulps(x_value, viewport.x_min, viewport.x_max, ulps) and (
        _within_axis_ulps(y_value, viewport.y_min, viewport.y_max, ulps)
    )


def _within_axis_ulps(value: float, lower: float, upper: float, ulps: int) -> bool:
    tolerance = ulps * max(ulp(value), ulp(lower), ulp(upper), ulp(upper - lower))
    return lower - tolerance <= value <= upper + tolerance


def _sampled_oval_intervals(
    geometry: OvalExecutionGeometry,
    viewport: ResolvedViewport,
    bounds: tuple[tuple[float, float, SegmentClosure], ...],
    *,
    image_width: int,
    image_height: int,
    limits: ApplicationLimits,
    policy: AngularSamplingPolicy,
) -> tuple[ParameterIntervalPlan, ...] | ErrorInfo:
    x_span = viewport.x_max - viewport.x_min
    y_span = viewport.y_max - viewport.y_min
    try:
        rx_px = geometry.outward_semi_axis_x * image_width / x_span
        ry_px = geometry.outward_semi_axis_y * image_height / y_span
        rho = max(rx_px, ry_px)
    except (OverflowError, ZeroDivisionError):
        return _numeric_range_error_for_oval(
            geometry.spec.item_id,
            "oval pixel-radius calculation overflowed",
        )
    if not isfinite(rho) or rho <= 0.0:
        return _numeric_range_error_for_oval(
            geometry.spec.item_id,
            "oval pixel-radius calculation is not finite and positive",
        )
    intervals: list[ParameterIntervalPlan] = []
    total_samples = 0
    for start, stop, closure in bounds:
        delta = stop - start
        planned = policy.samples_per_pixel * rho * delta
        if not isfinite(planned) or planned < 0.0:
            return _numeric_range_error_for_oval(
                geometry.spec.item_id,
                "oval sample-count calculation is not finite",
            )
        try:
            if closure is SegmentClosure.CLOSED:
                sample_count = max(
                    policy.minimum_closed_curve_samples,
                    ceil(policy.samples_per_pixel * rho * tau),
                )
            else:
                sample_count = max(
                    policy.minimum_open_segment_samples,
                    ceil(planned) + 1,
                )
        except (OverflowError, ValueError):
            return _numeric_range_error_for_oval(
                geometry.spec.item_id,
                "oval sample-count calculation cannot be safely rounded",
            )
        total_samples += sample_count
        if (
            total_samples > limits.max_sample_points_per_item
            or total_samples > limits.max_total_sample_points
        ):
            return _resource_error(
                "oval_sample_count",
                "oval sample count exceeds active point limits",
                item_id=geometry.spec.item_id,
            )
        try:
            intervals.append(
                ParameterIntervalPlan(
                    mathematical_branch_id=0,
                    parameter_start=start,
                    parameter_stop=stop,
                    sample_count=sample_count,
                    closure=closure,
                ),
            )
        except (TypeError, ValueError):
            return _numeric_range_error_for_oval(
                geometry.spec.item_id,
                "oval parameter interval construction failed",
            )
    return tuple(intervals)


def _build_hyperbola_plan(
    scene_spec: PlotSceneSpec,
    spec: HyperbolaSpec,
    resolved_viewport: ResolvedViewport,
    *,
    image_width: int,
    image_height: int,
    dpi: int,
    show_grid: bool,
    show_legend: bool,
    limits: ApplicationLimits,
    policy: HyperbolicSamplingPolicy,
) -> RenderPlan | ErrorInfo:
    """Approve visible branch intervals and the complete hyperbola budget."""

    try:
        geometry = project_hyperbola_geometry(spec)
        bounds_or_error = _plan_visible_hyperbola_intervals(
            geometry,
            resolved_viewport,
            policy=policy,
        )
    except MemoryError:
        return _resource_error(
            "max_estimated_memory_bytes",
            "hyperbola interval-planning workspace allocation failed",
            item_id=spec.item_id,
        )
    except (AttributeError, OverflowError, TypeError, ValueError, ZeroDivisionError):
        return _numeric_range_error_for_hyperbola(
            spec.item_id,
            "hyperbola geometry cannot be represented for interval planning",
        )
    if isinstance(bounds_or_error, ErrorInfo):
        return bounds_or_error

    intervals_or_error = _sampled_hyperbola_intervals(
        geometry,
        resolved_viewport,
        bounds_or_error,
        image_width=image_width,
        image_height=image_height,
        limits=limits,
        policy=policy,
    )
    if isinstance(intervals_or_error, ErrorInfo):
        return intervals_or_error
    intervals = intervals_or_error
    total_samples = sum(interval.sample_count for interval in intervals)
    try:
        batch_size = plan_hyperbola_batch_size(
            sample_count=total_samples,
            preferred_batch_points=policy.preferred_batch_points,
            image_width=image_width,
            image_height=image_height,
            limits=limits,
        )
        memory_budget = build_hyperbola_parameterized_memory_budget(
            sample_count=total_samples,
            batch_size=batch_size,
            image_width=image_width,
            image_height=image_height,
            limits=limits,
        )
        try:
            limits.validate_scene_resources(
                item_count=1,
                sample_points_per_item=total_samples,
                total_sample_points=total_samples,
                branches_per_item=4,
                total_branches=4,
                estimated_memory_bytes=memory_budget.total_bytes,
            )
        except (TypeError, ValueError):
            return _resource_error(
                "hyperbola_plan_resources",
                "hyperbola sampling plan exceeds active scene resource limits",
                item_id=spec.item_id,
            )
        item_plan = GeometryRenderItemPlan(
            item_id=spec.item_id,
            mathematical_branch_count=2,
            segments=intervals,
            sample_count=total_samples,
            batch_size=batch_size,
            max_segment_count=4,
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
            numeric_executor_contract_version=None,
            parameterized_sampler_contract_version=(
                PARAMETERIZED_SAMPLER_CONTRACT_VERSION
            ),
            item_plan=item_plan,
            memory_budget=memory_budget,
        )
        return _approve_render_plan(plan)
    except MemoryError:
        return _resource_error(
            "max_estimated_memory_bytes",
            "hyperbola plan or approval allocation failed",
            item_id=spec.item_id,
        )
    except ValueError as exc:
        if "budget cannot fit" in str(exc) or "resource" in str(exc):
            return _resource_error(
                "hyperbola_plan_resources",
                "hyperbola sampling plan exceeds active scene resource limits",
                item_id=spec.item_id,
            )
        return _internal_error(
            "render_plan",
            "approved hyperbola render-plan contract construction failed",
            item_id=spec.item_id,
        )
    except (AttributeError, TypeError):
        return _internal_error(
            "render_plan",
            "approved hyperbola render-plan contract construction failed",
            item_id=spec.item_id,
        )


def _plan_visible_hyperbola_intervals(
    geometry: HyperbolaExecutionGeometry,
    viewport: ResolvedViewport,
    *,
    policy: HyperbolicSamplingPolicy,
) -> tuple[tuple[int, float, float], ...] | ErrorInfo:
    """Intersect exact branch bounds before converting approved roots to float64."""

    left = Fraction.from_float(viewport.x_min)
    right = Fraction.from_float(viewport.x_max)
    bottom = Fraction.from_float(viewport.y_min)
    top = Fraction.from_float(viewport.y_max)
    if geometry.transverse_axis is AxisOrientation.HORIZONTAL:
        transverse_lower, transverse_upper = left, right
        transverse_center = geometry.center_x
        conjugate_lower, conjugate_upper = bottom, top
        conjugate_center = geometry.center_y
    else:
        transverse_lower, transverse_upper = bottom, top
        transverse_center = geometry.center_y
        conjugate_lower, conjugate_upper = left, right
        conjugate_center = geometry.center_x

    # Decide branch reachability, vertex exclusion, split topology, and isolated
    # tangent contact entirely with exact binary-rational viewport edges before
    # converting any sinh/cosh root to float64.
    exact_branches: list[tuple[int, Fraction, Fraction, bool]] = []
    axis_squared = geometry.semi_transverse_squared
    for branch_id in (0, 1):
        if branch_id == 0:
            branch_lower = transverse_center - transverse_upper
            branch_upper = transverse_center - transverse_lower
        else:
            branch_lower = transverse_lower - transverse_center
            branch_upper = transverse_upper - transverse_center

        if branch_upper <= 0:
            continue
        upper_squared = branch_upper * branch_upper
        if upper_squared <= axis_squared:
            # Equality is an isolated vertex contact, not a drawable interval.
            continue
        split_around_vertex = (
            branch_lower > 0 and branch_lower * branch_lower > axis_squared
        )
        exact_branches.append(
            (branch_id, branch_lower, branch_upper, split_around_vertex),
        )

    if not exact_branches:
        return _no_visible_hyperbola_error(
            geometry.spec.item_id,
            "neither exact hyperbola branch can enter the viewport",
        )

    conjugate_start = _finite_asinh_root(
        conjugate_lower - conjugate_center,
        geometry.semi_conjugate_float,
        geometry.max_safe_parameter,
    )
    conjugate_stop = _finite_asinh_root(
        conjugate_upper - conjugate_center,
        geometry.semi_conjugate_float,
        geometry.max_safe_parameter,
    )
    if conjugate_start >= conjugate_stop:
        return _numeric_range_error_for_hyperbola(
            geometry.spec.item_id,
            "hyperbola conjugate parameter bounds collapse in float64",
        )

    visible: list[tuple[int, float, float]] = []
    for branch_id, branch_lower, branch_upper, split_around_vertex in exact_branches:
        parameter_max = _finite_acosh_root(
            branch_upper,
            geometry.semi_transverse_float,
            geometry.max_safe_parameter,
        )
        if split_around_vertex:
            parameter_min = _finite_acosh_root(
                branch_lower,
                geometry.semi_transverse_float,
                geometry.max_safe_parameter,
            )
            transverse_intervals = (
                (-parameter_max, -parameter_min),
                (parameter_min, parameter_max),
            )
        else:
            transverse_intervals = ((-parameter_max, parameter_max),)

        for transverse_start, transverse_stop in transverse_intervals:
            start = max(transverse_start, conjugate_start)
            stop = min(transverse_stop, conjugate_stop)
            tolerance = policy.parameter_merge_ulps * max(ulp(start), ulp(stop))
            if stop - start <= tolerance:
                continue
            corrected = _correct_hyperbola_interval_inward(
                geometry,
                viewport,
                branch_id,
                start,
                stop,
                policy=policy,
            )
            if corrected is None:
                return _numeric_range_error_for_hyperbola(
                    geometry.spec.item_id,
                    "hyperbola parameter roots cannot be corrected inside the viewport",
                )
            start, stop = corrected
            first = hyperbola_parameter_point(geometry, branch_id, start)
            last = hyperbola_parameter_point(geometry, branch_id, stop)
            if first == last:
                return _numeric_range_error_for_hyperbola(
                    geometry.spec.item_id,
                    "visible hyperbola interval collapses to one float64 point",
                )
            visible.append((branch_id, start, stop))

    visible.sort(key=lambda value: (value[0], value[1]))
    if not visible:
        return _no_visible_hyperbola_error(
            geometry.spec.item_id,
            "hyperbola has no non-zero visible interval in the viewport",
        )
    if len(visible) > 4:
        return _numeric_range_error_for_hyperbola(
            geometry.spec.item_id,
            "hyperbola visibility produced more than four intervals",
        )
    return tuple(visible)


def _finite_asinh_root(delta: Fraction, axis: float, safe_limit: float) -> float:
    try:
        converted = float(delta)
    except OverflowError as exc:
        raise OverflowError("hyperbola sinh boundary is not finite.") from exc
    ratio = converted / axis
    if not isfinite(ratio):
        raise OverflowError("hyperbola sinh ratio is not finite.")
    parameter = asinh(ratio)
    if not isfinite(parameter) or abs(parameter) > safe_limit:
        raise OverflowError("hyperbola sinh root exceeds the safe parameter range.")
    return parameter


def _finite_acosh_root(distance: Fraction, axis: float, safe_limit: float) -> float:
    try:
        converted = float(distance)
    except OverflowError as exc:
        raise OverflowError("hyperbola cosh boundary is not finite.") from exc
    ratio = converted / axis
    if not isfinite(ratio) or ratio <= 1.0:
        raise OverflowError("hyperbola cosh root collapses in float64.")
    parameter = acosh(ratio)
    if not isfinite(parameter) or parameter <= 0.0 or parameter > safe_limit:
        raise OverflowError("hyperbola cosh root exceeds the safe parameter range.")
    return parameter


def _correct_hyperbola_interval_inward(
    geometry: HyperbolaExecutionGeometry,
    viewport: ResolvedViewport,
    branch_id: int,
    start: float,
    stop: float,
    *,
    policy: HyperbolicSamplingPolicy,
) -> tuple[float, float] | None:
    corrected_start = start
    corrected_stop = stop
    for _ in range(policy.parameter_merge_ulps + 1):
        x_value, y_value = hyperbola_parameter_point(
            geometry,
            branch_id,
            corrected_start,
        )
        if _inside_closed_viewport(
            x_value,
            y_value,
            viewport,
            ulps=0,
        ):
            break
        corrected_start = nextafter(corrected_start, stop)
    else:
        return None
    for _ in range(policy.parameter_merge_ulps + 1):
        x_value, y_value = hyperbola_parameter_point(
            geometry,
            branch_id,
            corrected_stop,
        )
        if _inside_closed_viewport(
            x_value,
            y_value,
            viewport,
            ulps=0,
        ):
            break
        corrected_stop = nextafter(corrected_stop, corrected_start)
    else:
        return None
    tolerance = policy.parameter_merge_ulps * max(
        ulp(corrected_start),
        ulp(corrected_stop),
    )
    if corrected_stop - corrected_start <= tolerance:
        return None
    return (corrected_start, corrected_stop)


def _sampled_hyperbola_intervals(
    geometry: HyperbolaExecutionGeometry,
    viewport: ResolvedViewport,
    bounds: tuple[tuple[int, float, float], ...],
    *,
    image_width: int,
    image_height: int,
    limits: ApplicationLimits,
    policy: HyperbolicSamplingPolicy,
) -> tuple[ParameterIntervalPlan, ...] | ErrorInfo:
    x_span = viewport.x_max - viewport.x_min
    y_span = viewport.y_max - viewport.y_min
    intervals: list[ParameterIntervalPlan] = []
    total_samples = 0
    for branch_id, start, stop in bounds:
        maximum_parameter = max(abs(start), abs(stop))
        if maximum_parameter > geometry.max_safe_parameter:
            return _numeric_range_error_for_hyperbola(
                geometry.spec.item_id,
                "hyperbola interval exceeds the safe parameter range",
            )
        try:
            hyperbolic_sine = abs(sinh(maximum_parameter))
            hyperbolic_cosine = cosh(maximum_parameter)
            transverse_speed = (
                geometry.outward_semi_transverse * hyperbolic_sine
            )
            conjugate_speed = (
                geometry.outward_semi_conjugate * hyperbolic_cosine
            )
            if geometry.transverse_axis is AxisOrientation.HORIZONTAL:
                x_speed = transverse_speed * image_width / x_span
                y_speed = conjugate_speed * image_height / y_span
            else:
                x_speed = conjugate_speed * image_width / x_span
                y_speed = transverse_speed * image_height / y_span
            maximum_pixel_speed = hypot(x_speed, y_speed)
            parameter_span = stop - start
            planned = (
                policy.samples_per_pixel
                * maximum_pixel_speed
                * parameter_span
            )
        except (OverflowError, ZeroDivisionError):
            return _numeric_range_error_for_hyperbola(
                geometry.spec.item_id,
                "hyperbola sample-count derivative bound overflowed",
            )
        if (
            not isfinite(maximum_pixel_speed)
            or maximum_pixel_speed < 0.0
            or not isfinite(planned)
            or planned < 0.0
        ):
            return _numeric_range_error_for_hyperbola(
                geometry.spec.item_id,
                "hyperbola sample-count calculation is not finite",
            )
        try:
            sample_count = max(
                policy.minimum_open_segment_samples,
                ceil(planned) + 1,
            )
        except (OverflowError, ValueError):
            return _numeric_range_error_for_hyperbola(
                geometry.spec.item_id,
                "hyperbola sample count cannot be safely rounded",
            )
        total_samples += sample_count
        if (
            total_samples > limits.max_sample_points_per_item
            or total_samples > limits.max_total_sample_points
        ):
            return _resource_error(
                "hyperbola_sample_count",
                "hyperbola sample count exceeds active point limits",
                item_id=geometry.spec.item_id,
            )
        try:
            intervals.append(
                ParameterIntervalPlan(
                    mathematical_branch_id=branch_id,
                    parameter_start=start,
                    parameter_stop=stop,
                    sample_count=sample_count,
                    closure=SegmentClosure.OPEN,
                ),
            )
        except (TypeError, ValueError):
            return _numeric_range_error_for_hyperbola(
                geometry.spec.item_id,
                "hyperbola parameter interval construction failed",
            )
    return tuple(intervals)


def _build_parabola_plan(
    scene_spec: PlotSceneSpec,
    spec: ParabolaSpec,
    resolved_viewport: ResolvedViewport,
    *,
    image_width: int,
    image_height: int,
    dpi: int,
    show_grid: bool,
    show_legend: bool,
    limits: ApplicationLimits,
    policy: ParabolicSamplingPolicy,
) -> RenderPlan | ErrorInfo:
    """Approve visible parameter intervals and the complete parabola budget."""

    try:
        geometry = project_parabola_geometry(spec)
        bounds_or_error = _plan_visible_parabola_intervals(
            geometry,
            resolved_viewport,
            policy=policy,
        )
    except MemoryError:
        return _resource_error(
            "max_estimated_memory_bytes",
            "parabola interval-planning workspace allocation failed",
            item_id=spec.item_id,
        )
    except (AttributeError, OverflowError, TypeError, ValueError, ZeroDivisionError):
        return _numeric_range_error_for_parabola(
            spec.item_id,
            "parabola geometry cannot be represented for interval planning",
        )
    if isinstance(bounds_or_error, ErrorInfo):
        return bounds_or_error

    intervals_or_error = _sampled_parabola_intervals(
        geometry,
        resolved_viewport,
        bounds_or_error,
        image_width=image_width,
        image_height=image_height,
        limits=limits,
        policy=policy,
    )
    if isinstance(intervals_or_error, ErrorInfo):
        return intervals_or_error
    intervals = intervals_or_error
    total_samples = sum(interval.sample_count for interval in intervals)
    try:
        batch_size = plan_parabola_batch_size(
            sample_count=total_samples,
            preferred_batch_points=policy.preferred_batch_points,
            image_width=image_width,
            image_height=image_height,
            limits=limits,
        )
        memory_budget = build_parabola_parameterized_memory_budget(
            sample_count=total_samples,
            batch_size=batch_size,
            image_width=image_width,
            image_height=image_height,
            limits=limits,
        )
        try:
            limits.validate_scene_resources(
                item_count=1,
                sample_points_per_item=total_samples,
                total_sample_points=total_samples,
                branches_per_item=2,
                total_branches=2,
                estimated_memory_bytes=memory_budget.total_bytes,
            )
        except (TypeError, ValueError):
            return _resource_error(
                "parabola_plan_resources",
                "parabola sampling plan exceeds active scene resource limits",
                item_id=spec.item_id,
            )
        item_plan = GeometryRenderItemPlan(
            item_id=spec.item_id,
            mathematical_branch_count=1,
            segments=intervals,
            sample_count=total_samples,
            batch_size=batch_size,
            max_segment_count=2,
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
            numeric_executor_contract_version=None,
            parameterized_sampler_contract_version=(
                PARAMETERIZED_SAMPLER_CONTRACT_VERSION
            ),
            item_plan=item_plan,
            memory_budget=memory_budget,
        )
        return _approve_render_plan(plan)
    except MemoryError:
        return _resource_error(
            "max_estimated_memory_bytes",
            "parabola plan or approval allocation failed",
            item_id=spec.item_id,
        )
    except ValueError as exc:
        if "budget cannot fit" in str(exc) or "resource" in str(exc):
            return _resource_error(
                "parabola_plan_resources",
                "parabola sampling plan exceeds active scene resource limits",
                item_id=spec.item_id,
            )
        return _internal_error(
            "render_plan",
            "approved parabola render-plan contract construction failed",
            item_id=spec.item_id,
        )
    except (AttributeError, TypeError):
        return _internal_error(
            "render_plan",
            "approved parabola render-plan contract construction failed",
            item_id=spec.item_id,
        )


def _plan_visible_parabola_intervals(
    geometry: ParabolaExecutionGeometry,
    viewport: ResolvedViewport,
    *,
    policy: ParabolicSamplingPolicy,
) -> tuple[tuple[float, float], ...] | ErrorInfo:
    """Decide exact visibility/topology before converting any square root."""

    left = Fraction.from_float(viewport.x_min)
    right = Fraction.from_float(viewport.x_max)
    bottom = Fraction.from_float(viewport.y_min)
    top = Fraction.from_float(viewport.y_max)
    if geometry.has_vertical_axis:
        cross_lower, cross_upper = left, right
        cross_vertex = geometry.vertex_x
        axis_lower, axis_upper = bottom, top
        axis_vertex = geometry.vertex_y
    else:
        cross_lower, cross_upper = bottom, top
        cross_vertex = geometry.vertex_y
        axis_lower, axis_upper = left, right
        axis_vertex = geometry.vertex_x

    twice_parameter = 2 * geometry.focal_parameter
    cross_interval = tuple(
        sorted(
            (
                (cross_lower - cross_vertex) / twice_parameter,
                (cross_upper - cross_vertex) / twice_parameter,
            ),
        ),
    )
    q_interval = tuple(
        sorted(
            (
                (axis_lower - axis_vertex) / geometry.focal_parameter,
                (axis_upper - axis_vertex) / geometry.focal_parameter,
            ),
        ),
    )
    q_lower, q_upper = q_interval
    if q_upper <= 0:
        # q_upper == 0 is at most an isolated vertex, never a drawable interval.
        return _no_visible_parabola_error(
            geometry.spec.item_id,
            "exact parabola opening-axis intersection is empty or a singleton",
        )
    constrained_q_lower = max(Fraction(0), q_lower)
    if constrained_q_lower == 0:
        candidates = (
            (
                _parabola_root_bound(-1, q_upper),
                _parabola_root_bound(1, q_upper),
            ),
        )
    else:
        candidates = (
            (
                _parabola_root_bound(-1, q_upper),
                _parabola_root_bound(-1, constrained_q_lower),
            ),
            (
                _parabola_root_bound(1, constrained_q_lower),
                _parabola_root_bound(1, q_upper),
            ),
        )

    cross_start = _parabola_rational_bound(cross_interval[0])
    cross_stop = _parabola_rational_bound(cross_interval[1])
    exact_intersections: list[
        tuple[_ExactParabolaParameterBound, _ExactParabolaParameterBound]
    ] = []
    for candidate_start, candidate_stop in candidates:
        start = (
            candidate_start
            if _compare_parabola_bounds(candidate_start, cross_start) >= 0
            else cross_start
        )
        stop = (
            candidate_stop
            if _compare_parabola_bounds(candidate_stop, cross_stop) <= 0
            else cross_stop
        )
        if _compare_parabola_bounds(start, stop) < 0:
            exact_intersections.append((start, stop))

    # Empty and exact singleton intersections return before any Decimal/float sqrt.
    if not exact_intersections:
        return _no_visible_parabola_error(
            geometry.spec.item_id,
            "parabola has no non-zero exact parameter interval in the viewport",
        )

    visible: list[tuple[float, float]] = []
    for exact_start, exact_stop in exact_intersections:
        start = _parabola_bound_to_float(exact_start)
        stop = _parabola_bound_to_float(exact_stop)
        if start >= stop:
            return _numeric_range_error_for_parabola(
                geometry.spec.item_id,
                "visible parabola interval collapses during float64 conversion",
            )
        corrected = _correct_parabola_interval_inward(
            geometry,
            viewport,
            start,
            stop,
            policy=policy,
        )
        if corrected is None:
            return _numeric_range_error_for_parabola(
                geometry.spec.item_id,
                "parabola parameter roots cannot be corrected inside the viewport",
            )
        start, stop = corrected
        first = parabola_parameter_point(geometry, start)
        last = parabola_parameter_point(geometry, stop)
        if first == last:
            return _numeric_range_error_for_parabola(
                geometry.spec.item_id,
                "visible parabola interval collapses to one float64 point",
            )
        visible.append((start, stop))

    visible.sort(key=lambda value: value[0])
    if len(visible) > 2:
        return _numeric_range_error_for_parabola(
            geometry.spec.item_id,
            "parabola visibility produced more than two intervals",
        )
    return tuple(visible)


def _parabola_rational_bound(value: Fraction) -> _ExactParabolaParameterBound:
    return _ExactParabolaParameterBound(
        rational=value,
        root_squared=None,
        root_sign=0,
    )


def _parabola_root_bound(
    sign: int,
    squared: Fraction,
) -> _ExactParabolaParameterBound:
    if sign not in {-1, 1} or type(squared) is not Fraction or squared <= 0:
        raise ValueError("parabola square-root bound is invalid.")
    return _ExactParabolaParameterBound(
        rational=None,
        root_squared=squared,
        root_sign=sign,
    )


def _compare_parabola_bounds(
    left: _ExactParabolaParameterBound,
    right: _ExactParabolaParameterBound,
) -> int:
    """Compare rational and signed-sqrt bounds using signs and exact squares."""

    if left.rational is not None and right.rational is not None:
        return (left.rational > right.rational) - (left.rational < right.rational)
    if left.rational is not None:
        return _compare_rational_to_parabola_root(left.rational, right)
    if right.rational is not None:
        return -_compare_rational_to_parabola_root(right.rational, left)
    assert left.root_squared is not None and right.root_squared is not None
    if left.root_sign != right.root_sign:
        return (left.root_sign > right.root_sign) - (left.root_sign < right.root_sign)
    squared_comparison = (left.root_squared > right.root_squared) - (
        left.root_squared < right.root_squared
    )
    return squared_comparison if left.root_sign > 0 else -squared_comparison


def _compare_rational_to_parabola_root(
    rational: Fraction,
    root: _ExactParabolaParameterBound,
) -> int:
    assert root.root_squared is not None and root.root_sign in {-1, 1}
    if root.root_sign > 0:
        if rational < 0:
            return -1
        squared_comparison = (rational * rational > root.root_squared) - (
            rational * rational < root.root_squared
        )
        return squared_comparison
    if rational > 0:
        return 1
    squared_comparison = (rational * rational > root.root_squared) - (
        rational * rational < root.root_squared
    )
    return -squared_comparison


def _parabola_bound_to_float(bound: _ExactParabolaParameterBound) -> float:
    if bound.rational is not None:
        try:
            value = float(bound.rational)
        except OverflowError as exc:
            raise OverflowError("parabola rational parameter is not finite.") from exc
    else:
        assert bound.root_squared is not None
        value = bound.root_sign * _finite_parabola_sqrt(bound.root_squared)
    if not isfinite(value):
        raise OverflowError("parabola parameter is not finite.")
    return value


def _finite_parabola_sqrt(value: Fraction) -> float:
    if type(value) is not Fraction or value <= 0:
        raise ValueError("parabola parameter square must be a positive Fraction.")
    try:
        with localcontext() as context:
            context.prec = 80
            decimal_value = Decimal(value.numerator) / Decimal(value.denominator)
            result = float(decimal_value.sqrt())
    except (InvalidOperation, OverflowError, ValueError) as exc:
        raise OverflowError("parabola square root is not representable.") from exc
    if not isfinite(result) or result <= 0.0:
        raise OverflowError("parabola square root is not finite and positive.")
    return result


def _correct_parabola_interval_inward(
    geometry: ParabolaExecutionGeometry,
    viewport: ResolvedViewport,
    start: float,
    stop: float,
    *,
    policy: ParabolicSamplingPolicy,
) -> tuple[float, float] | None:
    corrected_start = start
    corrected_stop = stop
    for _ in range(policy.parameter_merge_ulps + 1):
        x_value, y_value = parabola_parameter_point(geometry, corrected_start)
        if _inside_closed_viewport(
            x_value,
            y_value,
            viewport,
            ulps=0,
        ):
            break
        corrected_start = nextafter(corrected_start, stop)
    else:
        return None
    for _ in range(policy.parameter_merge_ulps + 1):
        x_value, y_value = parabola_parameter_point(geometry, corrected_stop)
        if _inside_closed_viewport(
            x_value,
            y_value,
            viewport,
            ulps=0,
        ):
            break
        corrected_stop = nextafter(corrected_stop, corrected_start)
    else:
        return None
    if corrected_start >= corrected_stop:
        return None
    for parameter in (corrected_start, corrected_stop):
        x_value, y_value = parabola_parameter_point(geometry, parameter)
        if not _inside_closed_viewport(
            x_value,
            y_value,
            viewport,
            ulps=policy.viewport_boundary_ulps,
        ):
            return None
    return (corrected_start, corrected_stop)


def _sampled_parabola_intervals(
    geometry: ParabolaExecutionGeometry,
    viewport: ResolvedViewport,
    bounds: tuple[tuple[float, float], ...],
    *,
    image_width: int,
    image_height: int,
    limits: ApplicationLimits,
    policy: ParabolicSamplingPolicy,
) -> tuple[ParameterIntervalPlan, ...] | ErrorInfo:
    x_span = viewport.x_max - viewport.x_min
    y_span = viewport.y_max - viewport.y_min
    intervals: list[ParameterIntervalPlan] = []
    total_samples = 0
    for start, stop in bounds:
        maximum_parameter = max(abs(start), abs(stop))
        try:
            constant_speed = abs(geometry.two_focal_parameter_float)
            variable_speed = _finite_parabola_product(
                constant_speed,
                maximum_parameter,
                "parabola variable derivative",
            )
            if geometry.has_vertical_axis:
                x_speed = _finite_parabola_pixel_speed(
                    constant_speed,
                    image_width,
                    x_span,
                )
                y_speed = _finite_parabola_pixel_speed(
                    variable_speed,
                    image_height,
                    y_span,
                )
            else:
                x_speed = _finite_parabola_pixel_speed(
                    variable_speed,
                    image_width,
                    x_span,
                )
                y_speed = _finite_parabola_pixel_speed(
                    constant_speed,
                    image_height,
                    y_span,
                )
            maximum_pixel_speed = hypot(x_speed, y_speed)
            parameter_span = stop - start
            planned = _finite_parabola_product(
                float(policy.samples_per_pixel),
                maximum_pixel_speed,
                "parabola policy derivative",
            )
            planned = _finite_parabola_product(
                planned,
                parameter_span,
                "parabola sample-count span",
            )
        except (OverflowError, ZeroDivisionError):
            return _numeric_range_error_for_parabola(
                geometry.spec.item_id,
                "parabola sample-count derivative bound overflowed",
            )
        if (
            not isfinite(maximum_pixel_speed)
            or maximum_pixel_speed < 0.0
            or not isfinite(planned)
            or planned < 0.0
        ):
            return _numeric_range_error_for_parabola(
                geometry.spec.item_id,
                "parabola sample-count calculation is not finite",
            )
        try:
            sample_count = max(
                policy.minimum_open_segment_samples,
                ceil(planned) + 1,
            )
        except (OverflowError, ValueError):
            return _numeric_range_error_for_parabola(
                geometry.spec.item_id,
                "parabola sample count cannot be safely rounded",
            )
        total_samples += sample_count
        if (
            total_samples > limits.max_sample_points_per_item
            or total_samples > limits.max_total_sample_points
        ):
            return _resource_error(
                "parabola_sample_count",
                "parabola sample count exceeds active point limits",
                item_id=geometry.spec.item_id,
            )
        try:
            intervals.append(
                ParameterIntervalPlan(
                    mathematical_branch_id=0,
                    parameter_start=start,
                    parameter_stop=stop,
                    sample_count=sample_count,
                    closure=SegmentClosure.OPEN,
                ),
            )
        except (TypeError, ValueError):
            return _numeric_range_error_for_parabola(
                geometry.spec.item_id,
                "parabola parameter interval construction failed",
            )
    return tuple(intervals)


def _finite_parabola_product(left: float, right: float, name: str) -> float:
    if not isfinite(left) or not isfinite(right):
        raise OverflowError(f"{name} inputs must be finite.")
    if left != 0.0 and right != 0.0 and abs(left) > _MAX_FLOAT64 / abs(right):
        raise OverflowError(f"{name} would overflow.")
    result = left * right
    if not isfinite(result):
        raise OverflowError(f"{name} is not finite.")
    return result


def _finite_parabola_pixel_speed(
    coordinate_speed: float,
    pixels: int,
    viewport_span: float,
) -> float:
    scaled = _finite_parabola_product(
        coordinate_speed,
        float(pixels),
        "parabola pixel derivative",
    )
    if not isfinite(viewport_span) or viewport_span <= 0.0:
        raise ZeroDivisionError("parabola viewport span is invalid.")
    if viewport_span < 1.0 and scaled > _MAX_FLOAT64 * viewport_span:
        raise OverflowError("parabola pixel derivative would overflow division.")
    result = scaled / viewport_span
    if not isfinite(result):
        raise OverflowError("parabola pixel derivative is not finite.")
    return result


def _line_segment_for_viewport(
    spec: LineSpec,
    viewport: ResolvedViewport,
    *,
    policy: LineSamplingPolicy,
) -> LineSegmentPlan | ErrorInfo:
    """Intersect ``d*x + e*y + f = 0`` with four exact binary viewport edges."""

    left = Fraction.from_float(viewport.x_min)
    right = Fraction.from_float(viewport.x_max)
    bottom = Fraction.from_float(viewport.y_min)
    top = Fraction.from_float(viewport.y_max)
    candidates: list[tuple[Fraction, Fraction]] = []

    def add_candidate(x_value: Fraction, y_value: Fraction) -> None:
        if not (left <= x_value <= right and bottom <= y_value <= top):
            return
        candidate = (x_value, y_value)
        if candidate not in candidates:
            candidates.append(candidate)

    # Fixed edge order: left, right, bottom, top.
    for x_value in (left, right):
        edge_value = spec.d * x_value + spec.f
        if spec.e != 0:
            add_candidate(x_value, -edge_value / spec.e)
        elif edge_value == 0:
            add_candidate(x_value, bottom)
            add_candidate(x_value, top)
    for y_value in (bottom, top):
        edge_value = spec.e * y_value + spec.f
        if spec.d != 0:
            add_candidate(-edge_value / spec.d, y_value)
        elif edge_value == 0:
            add_candidate(left, y_value)
            add_candidate(right, y_value)

    if len(candidates) > 4:
        return _numeric_range_error(spec.item_id, "line intersection produced too many candidates")

    converted: list[tuple[float, float, Fraction, Fraction]] = []
    for exact_x, exact_y in candidates:
        try:
            x_value = float(exact_x)
            y_value = float(exact_y)
        except OverflowError:
            return _numeric_range_error(
                spec.item_id,
                "line intersection cannot be represented as finite float64",
            )
        if not isfinite(x_value) or not isfinite(y_value):
            return _numeric_range_error(
                spec.item_id,
                "line intersection cannot be represented as finite float64",
            )
        if any(
            _float_points_within_ulps(
                x_value,
                y_value,
                existing_x,
                existing_y,
                policy.endpoint_merge_ulps,
            )
            for existing_x, existing_y, _, _ in converted
        ):
            continue
        converted.append((x_value, y_value, exact_x, exact_y))

    if len(converted) < 2:
        return _no_visible_line_error(spec.item_id, "line has fewer than two distinct viewport intersections")
    if len(converted) > 2:
        return _numeric_range_error(spec.item_id, "line intersection did not reduce to two endpoints")

    converted.sort(key=lambda point: -spec.e * point[2] + spec.d * point[3])
    for x_value, y_value, _, _ in converted:
        residual = _normalized_line_residual(spec, x_value, y_value)
        if residual > policy.maximum_residual_ulps * _FLOAT64_EPSILON:
            return _numeric_range_error(
                spec.item_id,
                "line endpoint residual exceeds the approved hard threshold",
            )
    try:
        return LineSegmentPlan(
            x0=converted[0][0],
            y0=converted[0][1],
            x1=converted[1][0],
            y1=converted[1][1],
        )
    except (TypeError, ValueError):
        return _no_visible_line_error(spec.item_id, "line endpoints collapsed after float64 conversion")


def _float_points_within_ulps(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    endpoint_merge_ulps: int,
) -> bool:
    x_tolerance = endpoint_merge_ulps * max(ulp(x0), ulp(x1))
    y_tolerance = endpoint_merge_ulps * max(ulp(y0), ulp(y1))
    return abs(x0 - x1) <= x_tolerance and abs(y0 - y1) <= y_tolerance


def _normalized_line_residual(spec: LineSpec, x: float, y: float) -> Fraction:
    exact_x = Fraction.from_float(x)
    exact_y = Fraction.from_float(y)
    numerator = abs(spec.d * exact_x + spec.e * exact_y + spec.f)
    scale = (
        abs(spec.d) * max(Fraction(1), abs(exact_x))
        + abs(spec.e) * max(Fraction(1), abs(exact_y))
        + abs(spec.f)
    )
    return numerator / scale


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


def _no_visible_line_error(item_id: str, technical_message: str) -> ErrorInfo:
    return ErrorInfo(
        code=ErrorCode.NO_VISIBLE_CURVE,
        user_message="The line has no visible segment in the current viewport.",
        technical_message=technical_message,
        item_id=item_id,
        field_name="line_intersection",
        recoverable=True,
    )


def _no_visible_oval_error(item_id: str, technical_message: str) -> ErrorInfo:
    return ErrorInfo(
        code=ErrorCode.NO_VISIBLE_CURVE,
        user_message="The circle or ellipse has no visible arc in the current viewport.",
        technical_message=technical_message,
        item_id=item_id,
        field_name="oval_visibility",
        recoverable=True,
    )


def _no_visible_hyperbola_error(item_id: str, technical_message: str) -> ErrorInfo:
    return ErrorInfo(
        code=ErrorCode.NO_VISIBLE_CURVE,
        user_message="The hyperbola has no drawable segment in the current viewport.",
        technical_message=technical_message,
        item_id=item_id,
        field_name="hyperbola_visibility",
        recoverable=True,
    )


def _no_visible_parabola_error(item_id: str, technical_message: str) -> ErrorInfo:
    return ErrorInfo(
        code=ErrorCode.NO_VISIBLE_CURVE,
        user_message="The parabola has no drawable segment in the current viewport.",
        technical_message=technical_message,
        item_id=item_id,
        field_name="parabola_visibility",
        recoverable=True,
    )


def _numeric_range_error(item_id: str, technical_message: str) -> ErrorInfo:
    return ErrorInfo(
        code=ErrorCode.NUMERIC_RANGE_UNSUPPORTED,
        user_message="The line is outside the currently supported numeric range.",
        technical_message=technical_message,
        item_id=item_id,
        field_name="line_numeric_range",
        recoverable=True,
    )


def _numeric_range_error_for_oval(item_id: str, technical_message: str) -> ErrorInfo:
    return ErrorInfo(
        code=ErrorCode.NUMERIC_RANGE_UNSUPPORTED,
        user_message="The circle or ellipse is outside the supported numeric range.",
        technical_message=technical_message,
        item_id=item_id,
        field_name="oval_numeric_range",
        recoverable=True,
    )


def _numeric_range_error_for_hyperbola(
    item_id: str,
    technical_message: str,
) -> ErrorInfo:
    return ErrorInfo(
        code=ErrorCode.NUMERIC_RANGE_UNSUPPORTED,
        user_message="The hyperbola exceeds the supported numeric precision.",
        technical_message=technical_message,
        item_id=item_id,
        field_name="hyperbola_numeric_range",
        recoverable=True,
    )


def _numeric_range_error_for_parabola(
    item_id: str,
    technical_message: str,
) -> ErrorInfo:
    return ErrorInfo(
        code=ErrorCode.NUMERIC_RANGE_UNSUPPORTED,
        user_message="The parabola exceeds the supported numeric precision.",
        technical_message=technical_message,
        item_id=item_id,
        field_name="parabola_numeric_range",
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
