"""Approved-plan explicit sampling, segmentation, and typed diagnostics.

This stage consumes the scalar-only plan approved by stage 8C-1.  It does not
accept source text, ASTs, function objects, viewport values, or sampling parameters as
parallel inputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import isfinite, sqrt
from statistics import median
from typing import Protocol, TypeAlias

import numpy as np
from numpy.typing import NDArray

from math_drawing_assistant.config import DEFAULT_LIMITS, ApplicationLimits
from math_drawing_assistant.engine.numeric_executor import (
    NUMERIC_EXECUTOR_CONTRACT_VERSION,
    NumericExecutionResult,
    execute_explicit_function,
)
from math_drawing_assistant.models.errors import ErrorCode, ErrorInfo
from math_drawing_assistant.models.plot_specs import ExplicitFunctionSpec, PlotSceneSpec
from math_drawing_assistant.models.render_plan import (
    DEFAULT_EXPLICIT_SAMPLING_POLICY,
    ExplicitRenderItemPlan,
    ExplicitSamplingPolicy,
    RenderMemoryBudget,
    RenderPlan,
    _RenderPlanApprovalSnapshot,
    _snapshot_approved_render_plan,
    validate_approved_render_plan,
)
from math_drawing_assistant.models.viewport import ResolvedViewport


Float64Vector: TypeAlias = NDArray[np.float64]
Int64Ranges: TypeAlias = NDArray[np.int64]

class CancellationProbe(Protocol):
    """Qt-independent cooperative cancellation boundary."""

    def is_cancelled(self) -> bool:
        """Return whether the current sampling task should stop."""


class SamplingWarningCode(str, Enum):
    """Stable warning codes emitted by a successful explicit sample."""

    PARTIAL_DOMAIN_OMITTED = "partial_domain_omitted"
    DENSE_OSCILLATION_SUSPECTED = "dense_oscillation_suspected"


class NoVisibleCurveReason(str, Enum):
    """Internal typed reason behind the unified no-visible error code."""

    NO_FINITE_SAMPLES = "NO_FINITE_SAMPLES"
    NO_DRAWABLE_SEGMENT = "NO_DRAWABLE_SEGMENT"
    OUTSIDE_VIEWPORT = "OUTSIDE_VIEWPORT"


@dataclass(frozen=True, slots=True)
class PartialDomainMetrics:
    """Typed evidence for a partial-domain warning."""

    finite_sample_count: int
    nonfinite_sample_count: int

    def __post_init__(self) -> None:
        _nonnegative_int(self.finite_sample_count, "finite_sample_count")
        _positive_int(self.nonfinite_sample_count, "nonfinite_sample_count")


@dataclass(frozen=True, slots=True)
class DenseOscillationMetrics:
    """Measurable proxy values; these are not a count of function periods."""

    significant_direction_change_count: int
    valid_adjacent_pair_count: int
    samples_per_monotone_run: float

    def __post_init__(self) -> None:
        _nonnegative_int(
            self.significant_direction_change_count,
            "significant_direction_change_count",
        )
        _nonnegative_int(
            self.valid_adjacent_pair_count,
            "valid_adjacent_pair_count",
        )
        if type(self.samples_per_monotone_run) is not float:
            raise TypeError("samples_per_monotone_run must be a float.")
        if not isfinite(self.samples_per_monotone_run):
            raise ValueError("samples_per_monotone_run must be finite.")
        if self.samples_per_monotone_run < 0:
            raise ValueError("samples_per_monotone_run must not be negative.")


SamplingWarningMetrics: TypeAlias = PartialDomainMetrics | DenseOscillationMetrics


@dataclass(frozen=True, slots=True)
class SamplingWarning:
    """A warning code plus the matching typed metrics and no free-form claim."""

    code: SamplingWarningCode
    metrics: SamplingWarningMetrics

    def __post_init__(self) -> None:
        if type(self.code) is not SamplingWarningCode:
            raise TypeError("code must be a SamplingWarningCode.")
        if self.code is SamplingWarningCode.PARTIAL_DOMAIN_OMITTED:
            if type(self.metrics) is not PartialDomainMetrics:
                raise TypeError("partial-domain warnings need PartialDomainMetrics.")
        elif self.code is SamplingWarningCode.DENSE_OSCILLATION_SUSPECTED:
            if type(self.metrics) is not DenseOscillationMetrics:
                raise TypeError("dense-oscillation warnings need DenseOscillationMetrics.")


@dataclass(frozen=True, slots=True)
class SamplingDiagnostics:
    """Typed segmentation and oscillation evidence for one sampled item."""

    nonfinite_boundary_break_count: int
    finite_discontinuity_break_count: int
    significant_direction_change_count: int
    valid_adjacent_pair_count: int
    samples_per_monotone_run: float

    def __post_init__(self) -> None:
        for name in (
            "nonfinite_boundary_break_count",
            "finite_discontinuity_break_count",
            "significant_direction_change_count",
            "valid_adjacent_pair_count",
        ):
            _nonnegative_int(getattr(self, name), name)
        if type(self.samples_per_monotone_run) is not float:
            raise TypeError("samples_per_monotone_run must be a float.")
        if not isfinite(self.samples_per_monotone_run):
            raise ValueError("samples_per_monotone_run must be finite.")
        if self.samples_per_monotone_run < 0:
            raise ValueError("samples_per_monotone_run must not be negative.")


@dataclass(frozen=True, slots=True)
class SamplingCancelled:
    """Independent cancellation outcome; it is neither an error nor a warning."""

    item_id: str

    def __post_init__(self) -> None:
        _item_id(self.item_id)


@dataclass(frozen=True, slots=True)
class SampledExplicitFunction:
    """Task-private, owned, frozen arrays plus typed sampling metadata."""

    item_id: str
    x: Float64Vector
    y: Float64Vector
    segment_ranges: Int64Ranges
    finite_sample_count: int
    nonfinite_sample_count: int
    isolated_finite_count: int
    discontinuity_break_count: int
    visible_segment_count: int
    warnings: tuple[SamplingWarning, ...]
    diagnostics: SamplingDiagnostics
    _plan_contract_snapshot: _RenderPlanApprovalSnapshot | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        _item_id(self.item_id)
        _frozen_owned_vector(self.x, "x")
        _frozen_owned_vector(self.y, "y")
        if self.x.shape != self.y.shape:
            raise ValueError("x and y must have the same shape.")
        _frozen_owned_ranges(self.segment_ranges)
        for name in (
            "finite_sample_count",
            "nonfinite_sample_count",
            "isolated_finite_count",
            "discontinuity_break_count",
            "visible_segment_count",
        ):
            _nonnegative_int(getattr(self, name), name)
        if self.finite_sample_count + self.nonfinite_sample_count != self.x.shape[0]:
            raise ValueError("finite and nonfinite counts must cover every sample.")
        if self.visible_segment_count > self.segment_ranges.shape[0]:
            raise ValueError("visible segment count exceeds segment count.")
        if type(self.warnings) is not tuple or not all(
            type(warning) is SamplingWarning for warning in self.warnings
        ):
            raise TypeError("warnings must be a tuple of SamplingWarning values.")
        if type(self.diagnostics) is not SamplingDiagnostics:
            raise TypeError("diagnostics must be SamplingDiagnostics.")
        if self.discontinuity_break_count != (
            self.diagnostics.nonfinite_boundary_break_count
            + self.diagnostics.finite_discontinuity_break_count
        ):
            raise ValueError("break counts must match diagnostics.")
        previous_stop = 0
        for start_value, stop_value in self.segment_ranges:
            start = int(start_value)
            stop = int(stop_value)
            if start < previous_stop or stop - start < 2 or stop > self.x.shape[0]:
                raise ValueError("segment ranges must be ordered valid half-open ranges.")
            previous_stop = stop


SamplingOutcome: TypeAlias = SampledExplicitFunction | SamplingCancelled | ErrorInfo


def _sampled_explicit_function_matches_approved_plan(
    value: object,
    plan: object,
) -> bool:
    """Compare a sampled contract with the sole snapshot of a current approved plan."""

    if type(value) is not SampledExplicitFunction:
        return False
    snapshot = value._plan_contract_snapshot
    return (
        type(snapshot) is _RenderPlanApprovalSnapshot
        and snapshot == _snapshot_approved_render_plan(plan)
    )


@dataclass(frozen=True, slots=True)
class _SamplingContext:
    plan: RenderPlan
    spec: ExplicitFunctionSpec
    viewport: ResolvedViewport
    item_plan: ExplicitRenderItemPlan
    memory_budget: RenderMemoryBudget
    limits: ApplicationLimits
    policy: ExplicitSamplingPolicy


@dataclass(frozen=True, slots=True)
class _SegmentScan:
    ranges: tuple[tuple[int, int], ...]
    finite_sample_count: int
    nonfinite_sample_count: int
    isolated_finite_count: int
    nonfinite_boundary_break_count: int
    finite_discontinuity_break_count: int


@dataclass(frozen=True, slots=True)
class _CurveScan:
    visible_segment_count: int
    significant_direction_change_count: int
    valid_adjacent_pair_count: int
    samples_per_monotone_run: float


def sample_explicit_function(
    plan: RenderPlan,
    *,
    cancellation_probe: CancellationProbe | None = None,
) -> SamplingOutcome:
    """Sample the sole explicit item from one formally approved render plan."""

    # This formal approval check is intentionally the first sampler operation.
    try:
        approved_plan = validate_approved_render_plan(plan)
    except MemoryError:
        return _allocation_error(None, "approval snapshot allocation failed")
    except (AttributeError, TypeError, ValueError):
        return _contract_error(None, "approved render-plan validation failed")

    try:
        return _sample_approved_explicit_function(
            approved_plan,
            cancellation_probe=cancellation_probe,
        )
    except MemoryError:
        # Last-resort coverage for sampler-owned list/tuple/dataclass and NumPy
        # allocations.  Programmer errors are intentionally not swallowed.
        return _allocation_error(None, "sampling allocation failed")


def _sample_approved_explicit_function(
    approved_plan: RenderPlan,
    *,
    cancellation_probe: CancellationProbe | None,
) -> SamplingOutcome:
    """Execute sampling after the public entry validated the approval receipt."""

    context_or_error = _validated_sampling_context(approved_plan)
    if isinstance(context_or_error, ErrorInfo):
        return context_or_error
    context = context_or_error

    cancelled_or_error = _poll_cancellation(
        cancellation_probe,
        item_id=context.spec.item_id,
    )
    if isinstance(cancelled_or_error, ErrorInfo):
        return cancelled_or_error
    if cancelled_or_error:
        return SamplingCancelled(context.spec.item_id)

    try:
        x_candidate = np.linspace(
            context.viewport.x_min,
            context.viewport.x_max,
            context.item_plan.sample_count,
            dtype=np.float64,
        )
        x = _take_owned_linspace_buffer(
            x_candidate,
            context.item_plan.sample_count,
        )
        if x is None:
            return _contract_error(
                context.spec.item_id,
                "formal x allocation has no task-private owner",
            )
        del x_candidate
        y = np.empty(context.item_plan.sample_count, dtype=np.float64)
    except MemoryError:
        return _allocation_error(context.spec.item_id, "formal x/y allocation failed")
    except (TypeError, ValueError):
        return _contract_error(context.spec.item_id, "formal x/y allocation contract failed")

    if not _owned_writable_vector(x, context.item_plan.sample_count):
        return _contract_error(context.spec.item_id, "formal x allocation is not owned float64")
    if not _owned_writable_vector(y, context.item_plan.sample_count):
        return _contract_error(context.spec.item_id, "formal y allocation is not owned float64")

    # Freeze the formal owner before its first cross-component exposure.  Every
    # executor batch is then a read-only view, so a retained batch reference
    # cannot mutate the final x array after sampling succeeds.
    x.setflags(write=False)

    execution_outcome = _execute_batches(
        context,
        x,
        y,
        cancellation_probe=cancellation_probe,
    )
    if execution_outcome is not None:
        return execution_outcome

    try:
        finite_mask = np.isfinite(y)
    except MemoryError:
        return _allocation_error(context.spec.item_id, "validity-mask allocation failed")
    except (TypeError, ValueError):
        return _contract_error(context.spec.item_id, "validity-mask construction failed")
    if (
        type(finite_mask) is not np.ndarray
        or finite_mask.dtype != np.dtype(np.bool_)
        or finite_mask.shape != y.shape
        or not finite_mask.flags.owndata
    ):
        return _contract_error(context.spec.item_id, "validity mask violates its plan")

    segments_or_outcome = _scan_segments(
        context,
        y,
        finite_mask,
        cancellation_probe=cancellation_probe,
    )
    if not isinstance(segments_or_outcome, _SegmentScan):
        return segments_or_outcome
    segments = segments_or_outcome

    if segments.finite_sample_count == 0:
        return _no_visible_error(
            context.spec.item_id,
            NoVisibleCurveReason.NO_FINITE_SAMPLES,
        )
    if not segments.ranges:
        return _no_visible_error(
            context.spec.item_id,
            NoVisibleCurveReason.NO_DRAWABLE_SEGMENT,
        )

    curve_or_outcome = _scan_visibility_and_oscillation(
        context,
        y,
        segments.ranges,
        cancellation_probe=cancellation_probe,
    )
    if not isinstance(curve_or_outcome, _CurveScan):
        return curve_or_outcome
    curve = curve_or_outcome
    if curve.visible_segment_count == 0:
        return _no_visible_error(
            context.spec.item_id,
            NoVisibleCurveReason.OUTSIDE_VIEWPORT,
        )

    try:
        segment_ranges = np.empty((len(segments.ranges), 2), dtype=np.int64)
        for index, (start, stop) in enumerate(segments.ranges):
            segment_ranges[index, 0] = start
            segment_ranges[index, 1] = stop
    except MemoryError:
        return _allocation_error(context.spec.item_id, "segment-range allocation failed")
    except (IndexError, TypeError, ValueError):
        return _contract_error(context.spec.item_id, "segment-range construction failed")
    if (
        type(segment_ranges) is not np.ndarray
        or segment_ranges.dtype != np.dtype(np.int64)
        or segment_ranges.shape != (len(segments.ranges), 2)
        or not segment_ranges.flags.owndata
    ):
        return _contract_error(context.spec.item_id, "segment ranges violate their plan")

    diagnostics = SamplingDiagnostics(
        nonfinite_boundary_break_count=segments.nonfinite_boundary_break_count,
        finite_discontinuity_break_count=segments.finite_discontinuity_break_count,
        significant_direction_change_count=(
            curve.significant_direction_change_count
        ),
        valid_adjacent_pair_count=curve.valid_adjacent_pair_count,
        samples_per_monotone_run=curve.samples_per_monotone_run,
    )
    warnings: list[SamplingWarning] = []
    if segments.nonfinite_sample_count > 0:
        warnings.append(
            SamplingWarning(
                code=SamplingWarningCode.PARTIAL_DOMAIN_OMITTED,
                metrics=PartialDomainMetrics(
                    finite_sample_count=segments.finite_sample_count,
                    nonfinite_sample_count=segments.nonfinite_sample_count,
                ),
            ),
        )
    dense_threshold = context.policy.dense_oscillation_proxy_threshold
    minimum_direction_changes = max(1, dense_threshold // 2)
    maximum_samples_per_run = float(dense_threshold * 2)
    if (
        curve.significant_direction_change_count >= minimum_direction_changes
        and curve.samples_per_monotone_run <= maximum_samples_per_run
    ):
        warnings.append(
            SamplingWarning(
                code=SamplingWarningCode.DENSE_OSCILLATION_SUSPECTED,
                metrics=DenseOscillationMetrics(
                    significant_direction_change_count=(
                        curve.significant_direction_change_count
                    ),
                    valid_adjacent_pair_count=curve.valid_adjacent_pair_count,
                    samples_per_monotone_run=curve.samples_per_monotone_run,
                ),
            ),
        )

    cancelled_or_error = _poll_cancellation(
        cancellation_probe,
        item_id=context.spec.item_id,
    )
    if isinstance(cancelled_or_error, ErrorInfo):
        return cancelled_or_error
    if cancelled_or_error:
        return SamplingCancelled(context.spec.item_id)

    del finite_mask
    y.setflags(write=False)
    segment_ranges.setflags(write=False)
    try:
        sampled = SampledExplicitFunction(
            item_id=context.spec.item_id,
            x=x,
            y=y,
            segment_ranges=segment_ranges,
            finite_sample_count=segments.finite_sample_count,
            nonfinite_sample_count=segments.nonfinite_sample_count,
            isolated_finite_count=segments.isolated_finite_count,
            discontinuity_break_count=(
                segments.nonfinite_boundary_break_count
                + segments.finite_discontinuity_break_count
            ),
            visible_segment_count=curve.visible_segment_count,
            warnings=tuple(warnings),
            diagnostics=diagnostics,
        )
        object.__setattr__(
            sampled,
            "_plan_contract_snapshot",
            _snapshot_approved_render_plan(context.plan),
        )
        return sampled
    except (AttributeError, TypeError, ValueError):
        return _contract_error(context.spec.item_id, "frozen sampling result contract failed")


def _validated_sampling_context(plan: RenderPlan) -> _SamplingContext | ErrorInfo:
    limits = DEFAULT_LIMITS
    policy = DEFAULT_EXPLICIT_SAMPLING_POLICY
    if plan.limits_version != limits.version:
        return _contract_error(None, "render plan limits version is not active")
    if plan.sampling_policy_version != policy.version:
        return _contract_error(None, "render plan sampling policy version is not active")
    if plan.numeric_executor_contract_version != NUMERIC_EXECUTOR_CONTRACT_VERSION:
        return _contract_error(None, "render plan numeric executor version is not active")
    if type(plan.scene_spec) is not PlotSceneSpec or len(plan.scene_spec.items) != 1:
        return _contract_error(None, "render plan must contain one exact scene specification")
    spec = plan.scene_spec.items[0]
    if type(spec) is not ExplicitFunctionSpec:
        return _contract_error(None, "render plan item is not an explicit function")
    if type(plan.resolved_viewport) is not ResolvedViewport:
        return _contract_error(spec.item_id, "render plan viewport is not exact")
    if type(plan.item_plan) is not ExplicitRenderItemPlan:
        return _contract_error(spec.item_id, "render plan item budget is missing")
    if type(plan.memory_budget) is not RenderMemoryBudget:
        return _contract_error(spec.item_id, "render plan memory budget is missing")
    item_plan = plan.item_plan
    budget = plan.memory_budget
    try:
        plan.scene_spec.__post_init__()
        spec.__post_init__()
        plan.resolved_viewport.__post_init__()
        item_plan.__post_init__()
        budget.__post_init__()
    except (AttributeError, TypeError, ValueError):
        return _contract_error(spec.item_id, "approved plan contains an invalid nested contract")
    if spec.limits_version != limits.version or item_plan.item_id != spec.item_id:
        return _contract_error(spec.item_id, "approved plan item identity or limits mismatch")
    viewport = plan.resolved_viewport
    return _SamplingContext(
        plan=plan,
        spec=spec,
        viewport=viewport,
        item_plan=item_plan,
        memory_budget=budget,
        limits=limits,
        policy=policy,
    )


def _execute_batches(
    context: _SamplingContext,
    x: Float64Vector,
    y: Float64Vector,
    *,
    cancellation_probe: CancellationProbe | None,
) -> SamplingCancelled | ErrorInfo | None:
    for start in range(0, context.item_plan.sample_count, context.item_plan.batch_size):
        cancelled_or_error = _poll_cancellation(
            cancellation_probe,
            item_id=context.spec.item_id,
        )
        if isinstance(cancelled_or_error, ErrorInfo):
            return cancelled_or_error
        if cancelled_or_error:
            return SamplingCancelled(context.spec.item_id)
        stop = min(start + context.item_plan.batch_size, context.item_plan.sample_count)
        x_batch = x[start:stop]
        if (
            x_batch.flags.writeable
            or x_batch.flags.owndata
            or not np.shares_memory(x_batch, x)
        ):
            return _contract_error(
                context.spec.item_id,
                "numeric executor input view ownership mismatch",
            )
        try:
            execution = execute_explicit_function(
                context.spec,
                x_batch,
                limits=context.limits,
            )
        except MemoryError:
            return _allocation_error(context.spec.item_id, "numeric batch allocation failed")

        cancelled_or_error = _poll_cancellation(
            cancellation_probe,
            item_id=context.spec.item_id,
        )
        if isinstance(cancelled_or_error, ErrorInfo):
            return cancelled_or_error
        if cancelled_or_error:
            return SamplingCancelled(context.spec.item_id)
        if isinstance(execution, ErrorInfo):
            return execution
        if type(execution) is not NumericExecutionResult:
            return _contract_error(context.spec.item_id, "numeric executor result type mismatch")
        try:
            execution.__post_init__()
        except (AttributeError, TypeError, ValueError):
            return _contract_error(context.spec.item_id, "numeric executor result contract mismatch")
        if (
            execution.cost.max_live_float64_vectors
            != context.item_plan.max_live_float64_vectors
        ):
            return _contract_error(context.spec.item_id, "numeric executor cost mismatch")

        value = execution.value
        if type(value) is float:
            y[start:stop].fill(value)
        elif type(value) is np.ndarray:
            if (
                value.dtype != np.dtype(np.float64)
                or value.shape != (stop - start,)
                or value.flags.writeable
                or not value.flags.owndata
                or np.shares_memory(value, x)
            ):
                return _contract_error(
                    context.spec.item_id,
                    "numeric executor vector ownership mismatch",
                )
            try:
                np.copyto(y[start:stop], value, casting="no")
            except (TypeError, ValueError):
                return _contract_error(context.spec.item_id, "numeric batch copy failed")
        else:
            return _contract_error(context.spec.item_id, "numeric executor value type mismatch")
        del value
        del execution
        del x_batch
    return None


def _scan_segments(
    context: _SamplingContext,
    y: Float64Vector,
    finite_mask: NDArray[np.bool_],
    *,
    cancellation_probe: CancellationProbe | None,
) -> _SegmentScan | SamplingCancelled | ErrorInfo:
    ranges: list[tuple[int, int]] = []
    run_start: int | None = None
    isolated_finite_count = 0
    nonfinite_boundary_break_count = 0
    finite_discontinuity_break_count = 0
    interval = context.policy.cancellation_check_interval
    point_count = y.shape[0]

    def finish_run(stop: int) -> ErrorInfo | None:
        nonlocal run_start, isolated_finite_count
        if run_start is None:
            return None
        if stop - run_start >= 2:
            if len(ranges) >= context.item_plan.max_segment_count:
                return _segment_capacity_error(context.spec.item_id)
            ranges.append((run_start, stop))
        else:
            isolated_finite_count += 1
        run_start = None
        return None

    for index in range(point_count):
        if index % interval == 0:
            cancelled_or_error = _poll_cancellation(
                cancellation_probe,
                item_id=context.spec.item_id,
            )
            if isinstance(cancelled_or_error, ErrorInfo):
                return cancelled_or_error
            if cancelled_or_error:
                return SamplingCancelled(context.spec.item_id)

        if not bool(finite_mask[index]):
            if index + 1 < point_count and bool(finite_mask[index + 1]):
                nonfinite_boundary_break_count += 1
            continue
        if run_start is None:
            run_start = index
        if index + 1 == point_count:
            error = finish_run(point_count)
            if error is not None:
                return error
            continue
        if not bool(finite_mask[index + 1]):
            nonfinite_boundary_break_count += 1
            error = finish_run(index + 1)
            if error is not None:
                return error
            continue
        if _is_finite_discontinuity(context, y, finite_mask, index):
            finite_discontinuity_break_count += 1
            error = finish_run(index + 1)
            if error is not None:
                return error
            run_start = index + 1

    finite_sample_count = int(np.count_nonzero(finite_mask))
    return _SegmentScan(
        ranges=tuple(ranges),
        finite_sample_count=finite_sample_count,
        nonfinite_sample_count=point_count - finite_sample_count,
        isolated_finite_count=isolated_finite_count,
        nonfinite_boundary_break_count=nonfinite_boundary_break_count,
        finite_discontinuity_break_count=finite_discontinuity_break_count,
    )


def _is_finite_discontinuity(
    context: _SamplingContext,
    y: Float64Vector,
    finite_mask: NDArray[np.bool_],
    pair_index: int,
) -> bool:
    y_left = float(y[pair_index])
    y_right = float(y[pair_index + 1])
    viewport = context.viewport
    opposite_outside_bands = (
        y_left < viewport.y_min and y_right > viewport.y_max
    ) or (
        y_right < viewport.y_min and y_left > viewport.y_max
    )
    if not opposite_outside_bands:
        return False
    y_span = viewport.y_max - viewport.y_min
    normalized_jump = abs(y_right - y_left) / y_span
    threshold = float(context.policy.finite_jump_threshold)
    if normalized_jump <= threshold:
        return False

    radius = max(4, int(sqrt(threshold)))
    first_left_pair = pair_index - radius
    last_right_pair = pair_index + radius
    if first_left_pair < 0 or last_right_pair > y.shape[0] - 2:
        return False

    left_nearby: list[float] = []
    right_nearby: list[float] = []
    for target, first_pair, stop_pair in (
        (left_nearby, first_left_pair, pair_index),
        (right_nearby, pair_index + 1, last_right_pair + 1),
    ):
        for candidate in range(first_pair, stop_pair):
            if not (
                bool(finite_mask[candidate])
                and bool(finite_mask[candidate + 1])
            ):
                return False
            local_jump = (
                abs(float(y[candidate + 1]) - float(y[candidate])) / y_span
            )
            if not isfinite(local_jump):
                return False
            target.append(local_jump)
    if len(left_nearby) != radius or len(right_nearby) != radius:
        return False
    one_vertical_pixel = 1.0 / float(context.plan.image_height)
    left_baseline = max(float(median(left_nearby)), one_vertical_pixel)
    right_baseline = max(float(median(right_nearby)), one_vertical_pixel)
    robust_local_baseline = max(left_baseline, right_baseline)
    relative_multiplier = sqrt(threshold)
    return normalized_jump > relative_multiplier * robust_local_baseline


def _scan_visibility_and_oscillation(
    context: _SamplingContext,
    y: Float64Vector,
    ranges: tuple[tuple[int, int], ...],
    *,
    cancellation_probe: CancellationProbe | None,
) -> _CurveScan | SamplingCancelled | ErrorInfo:
    viewport = context.viewport
    pixel_height = (viewport.y_max - viewport.y_min) / float(context.plan.image_height)
    direction_change_count = 0
    valid_pair_count = 0
    significant_segment_count = 0
    visible_segment_count = 0
    processed_points = 0
    interval = context.policy.cancellation_check_interval

    for start, stop in ranges:
        previous_direction = 0
        has_significant_direction = False
        segment_visible = False
        for index in range(start, stop):
            if processed_points % interval == 0:
                cancelled_or_error = _poll_cancellation(
                    cancellation_probe,
                    item_id=context.spec.item_id,
                )
                if isinstance(cancelled_or_error, ErrorInfo):
                    return cancelled_or_error
                if cancelled_or_error:
                    return SamplingCancelled(context.spec.item_id)
            processed_points += 1
            current = float(y[index])
            if viewport.y_min <= current <= viewport.y_max:
                segment_visible = True
            if index + 1 >= stop:
                continue
            following = float(y[index + 1])
            valid_pair_count += 1
            lower = min(current, following)
            upper = max(current, following)
            if (
                lower <= viewport.y_min <= upper
                or lower <= viewport.y_max <= upper
            ):
                segment_visible = True
            difference = following - current
            if abs(difference) < pixel_height:
                continue
            direction = 1 if difference > 0 else -1
            if previous_direction != 0 and direction != previous_direction:
                direction_change_count += 1
            previous_direction = direction
            has_significant_direction = True
        if has_significant_direction:
            significant_segment_count += 1
        if segment_visible:
            visible_segment_count += 1

    total_segment_samples = valid_pair_count + len(ranges)
    monotone_run_count = direction_change_count + significant_segment_count
    if monotone_run_count == 0:
        samples_per_monotone_run = float(total_segment_samples)
    else:
        samples_per_monotone_run = total_segment_samples / monotone_run_count
    return _CurveScan(
        visible_segment_count=visible_segment_count,
        significant_direction_change_count=direction_change_count,
        valid_adjacent_pair_count=valid_pair_count,
        samples_per_monotone_run=float(samples_per_monotone_run),
    )


def _poll_cancellation(
    probe: CancellationProbe | None,
    *,
    item_id: str,
) -> bool | ErrorInfo:
    if probe is None:
        return False
    try:
        result = probe.is_cancelled()
    except Exception:
        return _contract_error(item_id, "cancellation probe raised unexpectedly")
    if type(result) is not bool:
        return _contract_error(item_id, "cancellation probe did not return bool")
    return result


def _owned_writable_vector(value: object, size: int) -> bool:
    return (
        type(value) is np.ndarray
        and value.dtype == np.dtype(np.float64)
        and value.shape == (size,)
        and value.flags.owndata
        and value.flags.writeable
    )


def _take_owned_linspace_buffer(
    value: object,
    size: int,
) -> Float64Vector | None:
    """Use NumPy's private owner directly when linspace returns its full view."""

    if not _owned_or_full_owner_candidate(value, size):
        return None
    assert type(value) is np.ndarray
    if value.flags.owndata:
        return value
    owner = value.base
    if not _owned_or_full_owner_candidate(owner, size):
        return None
    assert type(owner) is np.ndarray
    if (
        not owner.flags.owndata
        or value.strides != owner.strides
        or value.ctypes.data != owner.ctypes.data
    ):
        return None
    return owner


def _owned_or_full_owner_candidate(value: object, size: int) -> bool:
    return (
        type(value) is np.ndarray
        and value.dtype == np.dtype(np.float64)
        and value.shape == (size,)
        and value.flags.writeable
    )


def _frozen_owned_vector(value: object, name: str) -> None:
    if type(value) is not np.ndarray:
        raise TypeError(f"{name} must be an exact NumPy array.")
    if value.dtype != np.dtype(np.float64) or value.ndim != 1:
        raise TypeError(f"{name} must be a one-dimensional float64 array.")
    if not value.flags.owndata or value.flags.writeable:
        raise ValueError(f"{name} must own read-only data.")


def _frozen_owned_ranges(value: object) -> None:
    if type(value) is not np.ndarray:
        raise TypeError("segment_ranges must be an exact NumPy array.")
    if value.dtype != np.dtype(np.int64) or value.ndim != 2 or value.shape[1:] != (2,):
        raise TypeError("segment_ranges must have shape (S, 2) and dtype int64.")
    if not value.flags.owndata or value.flags.writeable:
        raise ValueError("segment_ranges must own read-only data.")


def _positive_int(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer.")
    if value < 1:
        raise ValueError(f"{name} must be positive.")


def _nonnegative_int(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer.")
    if value < 0:
        raise ValueError(f"{name} must not be negative.")


def _item_id(value: object) -> None:
    if type(value) is not str or not value.strip():
        raise ValueError("item_id must be a non-empty string.")


def _segment_capacity_error(item_id: str) -> ErrorInfo:
    return ErrorInfo(
        code=ErrorCode.RESOURCE_LIMIT_EXCEEDED,
        user_message="曲线分段数量超过当前资源限制。",
        technical_message="segment_count exceeds approved max_segment_count",
        item_id=item_id,
        field_name="max_segment_count",
        recoverable=True,
    )


def _allocation_error(item_id: str | None, technical_message: str) -> ErrorInfo:
    return ErrorInfo(
        code=ErrorCode.RESOURCE_LIMIT_EXCEEDED,
        user_message="无法分配已批准的采样缓冲区，请缩小输出规模后重试。",
        technical_message=technical_message,
        item_id=item_id,
        field_name="sampling_memory",
        recoverable=True,
    )


def _no_visible_error(item_id: str, reason: NoVisibleCurveReason) -> ErrorInfo:
    if type(reason) is not NoVisibleCurveReason:
        raise TypeError("reason must be a NoVisibleCurveReason.")
    return ErrorInfo(
        code=ErrorCode.NO_VISIBLE_CURVE,
        user_message="当前视口内没有可绘制曲线，请调整坐标范围。",
        technical_message=f"reason={reason.value}",
        item_id=item_id,
        field_name="sampling_visibility",
        recoverable=True,
    )


def _contract_error(item_id: str | None, technical_message: str) -> ErrorInfo:
    return ErrorInfo(
        code=ErrorCode.INTERNAL_ERROR,
        user_message="采样契约无效，请重新提交公式。",
        technical_message=technical_message,
        item_id=item_id,
        field_name="sampling",
        recoverable=False,
    )


__all__ = [
    "CancellationProbe",
    "DenseOscillationMetrics",
    "NoVisibleCurveReason",
    "PartialDomainMetrics",
    "SampledExplicitFunction",
    "SamplingCancelled",
    "SamplingDiagnostics",
    "SamplingOutcome",
    "SamplingWarning",
    "SamplingWarningCode",
    "sample_explicit_function",
]
