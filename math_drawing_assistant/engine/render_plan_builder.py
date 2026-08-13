"""Stage 8C-1 scalar-only construction and approval of one explicit render plan."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from math import acos, asin, ceil, isfinite, pi, tau, ulp

from math_drawing_assistant.config import ApplicationLimits, DEFAULT_LIMITS
from math_drawing_assistant.engine.numeric_executor import (
    NUMERIC_EXECUTOR_CONTRACT_VERSION,
    NumericExecutionCost,
    estimate_numeric_execution_cost,
)
from math_drawing_assistant.engine.parameterized_budget import (
    build_line_parameterized_memory_budget,
    build_oval_parameterized_memory_budget,
    plan_oval_batch_size,
)
from math_drawing_assistant.engine.oval_geometry import (
    OvalExecutionGeometry,
    oval_parameter_point,
    project_oval_geometry,
)
from math_drawing_assistant.models.errors import ErrorCode, ErrorInfo
from math_drawing_assistant.models.plot_specs import (
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
    DEFAULT_LINE_SAMPLING_POLICY,
    PARAMETERIZED_SAMPLER_CONTRACT_VERSION,
    RENDER_PLAN_CONTRACT_VERSION,
    ExplicitRenderItemPlan,
    ExplicitSamplingPolicy,
    GeometryRenderItemPlan,
    LineSamplingPolicy,
    LineSegmentPlan,
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


@dataclass(frozen=True, slots=True)
class RenderPlanBuilder:
    """Unified exact-Spec dispatch boundary for one scalar-only render plan."""

    limits: ApplicationLimits = DEFAULT_LIMITS
    sampling_policy: ExplicitSamplingPolicy = DEFAULT_EXPLICIT_SAMPLING_POLICY
    line_sampling_policy: LineSamplingPolicy = DEFAULT_LINE_SAMPLING_POLICY
    angular_sampling_policy: AngularSamplingPolicy = DEFAULT_ANGULAR_SAMPLING_POLICY

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
