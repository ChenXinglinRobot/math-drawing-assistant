"""Approved-plan explicit sampling, segmentation, and typed diagnostics.

This stage consumes the scalar-only plan approved by stage 8C-1.  It does not
accept source text, ASTs, function objects, viewport values, or sampling parameters as
parallel inputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from fractions import Fraction
from math import isfinite, sqrt, ulp
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
from math_drawing_assistant.engine.parameterized_budget import (
    build_hyperbola_parameterized_memory_budget,
    build_line_parameterized_memory_budget,
    build_oval_parameterized_memory_budget,
    build_parabola_parameterized_memory_budget,
)
from math_drawing_assistant.engine.hyperbola_geometry import (
    HyperbolaExecutionGeometry,
    hyperbola_parameter_point,
    normalized_hyperbola_residual,
    project_hyperbola_geometry,
)
from math_drawing_assistant.engine.oval_geometry import (
    OvalExecutionGeometry,
    normalized_oval_residual,
    oval_parameter_point,
    project_oval_geometry,
)
from math_drawing_assistant.engine.parabola_geometry import (
    ParabolaExecutionGeometry,
    normalized_parabola_residual,
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
)
from math_drawing_assistant.models.render_plan import (
    DEFAULT_ANGULAR_SAMPLING_POLICY,
    DEFAULT_EXPLICIT_SAMPLING_POLICY,
    DEFAULT_HYPERBOLIC_SAMPLING_POLICY,
    DEFAULT_LINE_SAMPLING_POLICY,
    DEFAULT_PARABOLIC_SAMPLING_POLICY,
    PARAMETERIZED_SAMPLER_CONTRACT_VERSION,
    AngularSamplingPolicy,
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
    _GeometryRenderPlanApprovalSnapshot,
    _RenderPlanApprovalSnapshot,
    _snapshot_approved_render_plan,
    validate_approved_render_plan,
)
from math_drawing_assistant.models.viewport import ResolvedViewport


Float64Vector: TypeAlias = NDArray[np.float64]
Int64Ranges: TypeAlias = NDArray[np.int64]
_FLOAT64_EPSILON = Fraction(1, 1 << 52)

class CancellationProbe(Protocol):
    """Qt-independent cooperative cancellation boundary."""

    def is_cancelled(self) -> bool:
        """Return whether the current sampling task should stop."""


class SamplingWarningCode(str, Enum):
    """Stable warning codes emitted by a successful explicit sample."""

    PARTIAL_DOMAIN_OMITTED = "partial_domain_omitted"
    DENSE_OSCILLATION_SUSPECTED = "dense_oscillation_suspected"
    VIEWPORT_CLIPPED = "viewport_clipped"
    SAMPLING_PRECISION_LIMITED = "sampling_precision_limited"


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


@dataclass(frozen=True, slots=True)
class ViewportClippedMetrics:
    """Typed count of parameterized segments clipped by the final viewport."""

    clipped_segment_count: int

    def __post_init__(self) -> None:
        _positive_int(self.clipped_segment_count, "clipped_segment_count")


@dataclass(frozen=True, slots=True)
class SamplingPrecisionLimitedMetrics:
    """Typed count of parameterized segments affected by precision limits."""

    limited_segment_count: int

    def __post_init__(self) -> None:
        _positive_int(self.limited_segment_count, "limited_segment_count")


SamplingWarningMetrics: TypeAlias = (
    PartialDomainMetrics
    | DenseOscillationMetrics
    | ViewportClippedMetrics
    | SamplingPrecisionLimitedMetrics
)


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
        elif self.code is SamplingWarningCode.VIEWPORT_CLIPPED:
            if type(self.metrics) is not ViewportClippedMetrics:
                raise TypeError("viewport-clipped warnings need ViewportClippedMetrics.")
        elif self.code is SamplingWarningCode.SAMPLING_PRECISION_LIMITED:
            if type(self.metrics) is not SamplingPrecisionLimitedMetrics:
                raise TypeError(
                    "sampling-precision warnings need SamplingPrecisionLimitedMetrics.",
                )


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


    @property
    def segment_metadata(self) -> tuple["SampledSegmentMetadata", ...]:
        """Return explicit segments as branchless, open metadata values."""

        return tuple(
            SampledSegmentMetadata(
                mathematical_branch_id=None,
                closure=SegmentClosure.OPEN,
            )
            for _ in range(self.segment_ranges.shape[0])
        )


@dataclass(frozen=True, slots=True)
class SampledSegmentMetadata:
    """Typed mathematical branch and closure metadata for one sampled segment."""

    mathematical_branch_id: int | None
    closure: SegmentClosure

    def __post_init__(self) -> None:
        if self.mathematical_branch_id is not None:
            _nonnegative_int(self.mathematical_branch_id, "mathematical_branch_id")
        if type(self.closure) is not SegmentClosure:
            raise TypeError("closure must be an exact SegmentClosure.")


@dataclass(frozen=True, slots=True)
class ParameterizedSamplingDiagnostics:
    """Structural diagnostics for a future approved parameterized sampler."""

    sampled_segment_count: int
    sampled_point_count: int

    def __post_init__(self) -> None:
        _positive_int(self.sampled_segment_count, "sampled_segment_count")
        _positive_int(self.sampled_point_count, "sampled_point_count")


@dataclass(frozen=True, slots=True)
class SampledParameterizedCurve:
    """Owned, read-only typed result model for approved parameterized sampling."""

    item_id: str
    x: Float64Vector
    y: Float64Vector
    segment_ranges: Int64Ranges
    segment_metadata: tuple[SampledSegmentMetadata, ...]
    visible_segment_count: int
    warnings: tuple[SamplingWarning, ...]
    diagnostics: ParameterizedSamplingDiagnostics
    _plan_contract_snapshot: _GeometryRenderPlanApprovalSnapshot | None = field(
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
        if self.segment_ranges.shape[0] == 0:
            raise ValueError("parameterized sampling needs at least one segment.")
        if type(self.segment_metadata) is not tuple or not all(
            type(metadata) is SampledSegmentMetadata
            for metadata in self.segment_metadata
        ):
            raise TypeError("segment_metadata must be an exact typed tuple.")
        if len(self.segment_metadata) != self.segment_ranges.shape[0]:
            raise ValueError("segment metadata must correspond one-to-one with ranges.")
        if any(
            metadata.mathematical_branch_id is None
            for metadata in self.segment_metadata
        ):
            raise ValueError("parameterized segments require mathematical branch ids.")
        _positive_int(self.visible_segment_count, "visible_segment_count")
        if self.visible_segment_count > self.segment_ranges.shape[0]:
            raise ValueError("visible segment count exceeds segment count.")
        if type(self.warnings) is not tuple or not all(
            type(warning) is SamplingWarning for warning in self.warnings
        ):
            raise TypeError("warnings must be a tuple of SamplingWarning values.")
        if type(self.diagnostics) is not ParameterizedSamplingDiagnostics:
            raise TypeError("diagnostics must be ParameterizedSamplingDiagnostics.")
        if self.diagnostics.sampled_segment_count != self.segment_ranges.shape[0]:
            raise ValueError("diagnostic segment count does not match ranges.")
        if self.diagnostics.sampled_point_count != self.x.shape[0]:
            raise ValueError("diagnostic point count does not match samples.")
        previous_stop = 0
        for start_value, stop_value in self.segment_ranges:
            start = int(start_value)
            stop = int(stop_value)
            if start < previous_stop or stop - start < 2 or stop > self.x.shape[0]:
                raise ValueError("segment ranges must be ordered valid half-open ranges.")
            previous_stop = stop


SampledCurve: TypeAlias = SampledExplicitFunction | SampledParameterizedCurve
SamplingOutcome: TypeAlias = SampledCurve | SamplingCancelled | ErrorInfo


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


def _sampled_parameterized_curve_matches_approved_plan(
    value: object,
    plan: object,
) -> bool:
    """Compare one parameterized result with the sole approved plan snapshot."""

    if type(value) is not SampledParameterizedCurve:
        return False
    snapshot = value._plan_contract_snapshot
    return (
        type(snapshot) is _GeometryRenderPlanApprovalSnapshot
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
class _ParameterizedSamplingContext:
    plan: RenderPlan
    spec: LineSpec
    viewport: ResolvedViewport
    item_plan: GeometryRenderItemPlan
    segment: LineSegmentPlan
    memory_budget: ParameterizedRenderMemoryBudget
    limits: ApplicationLimits
    policy: LineSamplingPolicy


@dataclass(frozen=True, slots=True)
class _OvalSamplingContext:
    plan: RenderPlan
    spec: CircleSpec | EllipseSpec
    viewport: ResolvedViewport
    item_plan: GeometryRenderItemPlan
    intervals: tuple[ParameterIntervalPlan, ...]
    memory_budget: ParameterizedRenderMemoryBudget
    limits: ApplicationLimits
    policy: AngularSamplingPolicy
    geometry: OvalExecutionGeometry


@dataclass(frozen=True, slots=True)
class _HyperbolaSamplingContext:
    plan: RenderPlan
    spec: HyperbolaSpec
    viewport: ResolvedViewport
    item_plan: GeometryRenderItemPlan
    intervals: tuple[ParameterIntervalPlan, ...]
    memory_budget: ParameterizedRenderMemoryBudget
    limits: ApplicationLimits
    policy: HyperbolicSamplingPolicy
    geometry: HyperbolaExecutionGeometry


@dataclass(frozen=True, slots=True)
class _ParabolaSamplingContext:
    plan: RenderPlan
    spec: ParabolaSpec
    viewport: ResolvedViewport
    item_plan: GeometryRenderItemPlan
    intervals: tuple[ParameterIntervalPlan, ...]
    memory_budget: ParameterizedRenderMemoryBudget
    limits: ApplicationLimits
    policy: ParabolicSamplingPolicy
    geometry: ParabolaExecutionGeometry


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


def sample_parameterized_curve(
    plan: RenderPlan,
    *,
    cancellation_probe: CancellationProbe | None = None,
) -> SamplingOutcome:
    """Sample the sole approved parameterized geometry plan."""

    # Approval is intentionally the first operation at this public boundary.
    try:
        approved_plan = validate_approved_render_plan(plan)
    except MemoryError:
        return _allocation_error(None, "approval snapshot allocation failed")
    except (AttributeError, TypeError, ValueError):
        return _contract_error(None, "approved render-plan validation failed")

    try:
        return _sample_approved_parameterized_curve(
            approved_plan,
            cancellation_probe=cancellation_probe,
        )
    except MemoryError:
        return _allocation_error(None, "parameterized sampling allocation failed")


def _sample_approved_parameterized_curve(
    approved_plan: RenderPlan,
    *,
    cancellation_probe: CancellationProbe | None,
) -> SamplingOutcome:
    item_id = approved_plan.scene_spec.items[0].item_id
    cancelled_or_error = _poll_cancellation(cancellation_probe, item_id=item_id)
    if isinstance(cancelled_or_error, ErrorInfo):
        return cancelled_or_error
    if cancelled_or_error:
        return SamplingCancelled(item_id)

    spec = approved_plan.scene_spec.items[0]
    if type(spec) in {CircleSpec, EllipseSpec}:
        return _sample_approved_oval_curve(
            approved_plan,
            cancellation_probe=cancellation_probe,
        )
    if type(spec) is HyperbolaSpec:
        return _sample_approved_hyperbola_curve(
            approved_plan,
            cancellation_probe=cancellation_probe,
        )
    if type(spec) is ParabolaSpec:
        return _sample_approved_parabola_curve(
            approved_plan,
            cancellation_probe=cancellation_probe,
        )

    context_or_error = _validated_parameterized_sampling_context(approved_plan)
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
        x = np.empty(context.item_plan.sample_count, dtype=np.float64)
        y = np.empty(context.item_plan.sample_count, dtype=np.float64)
    except MemoryError:
        return _allocation_error(context.spec.item_id, "formal line x/y allocation failed")
    except (TypeError, ValueError):
        return _contract_error(context.spec.item_id, "formal line x/y allocation failed")
    if not _owned_writable_vector(x, context.item_plan.sample_count):
        return _contract_error(context.spec.item_id, "formal line x allocation is invalid")
    if not _owned_writable_vector(y, context.item_plan.sample_count):
        return _contract_error(context.spec.item_id, "formal line y allocation is invalid")

    x[0] = context.segment.x0
    y[0] = context.segment.y0
    cancelled_or_error = _poll_cancellation(
        cancellation_probe,
        item_id=context.spec.item_id,
    )
    if isinstance(cancelled_or_error, ErrorInfo):
        return cancelled_or_error
    if cancelled_or_error:
        return SamplingCancelled(context.spec.item_id)

    x[1] = context.segment.x1
    y[1] = context.segment.y1
    cancelled_or_error = _poll_cancellation(
        cancellation_probe,
        item_id=context.spec.item_id,
    )
    if isinstance(cancelled_or_error, ErrorInfo):
        return cancelled_or_error
    if cancelled_or_error:
        return SamplingCancelled(context.spec.item_id)

    precision_limited = False
    for index in range(context.item_plan.sample_count):
        residual = _normalized_line_residual(
            context.spec,
            float(x[index]),
            float(y[index]),
        )
        if residual > context.policy.maximum_residual_ulps * _FLOAT64_EPSILON:
            return _numeric_range_error(
                context.spec.item_id,
                "approved line endpoint residual exceeds the hard threshold",
            )
        if residual > context.policy.target_residual_ulps * _FLOAT64_EPSILON:
            precision_limited = True

    metadata = (
        SampledSegmentMetadata(
            mathematical_branch_id=0,
            closure=SegmentClosure.OPEN,
        ),
    )
    diagnostics = ParameterizedSamplingDiagnostics(
        sampled_segment_count=1,
        sampled_point_count=context.item_plan.sample_count,
    )
    warnings = [
        SamplingWarning(
            code=SamplingWarningCode.VIEWPORT_CLIPPED,
            metrics=ViewportClippedMetrics(clipped_segment_count=1),
        ),
    ]
    if precision_limited:
        warnings.append(
            SamplingWarning(
                code=SamplingWarningCode.SAMPLING_PRECISION_LIMITED,
                metrics=SamplingPrecisionLimitedMetrics(limited_segment_count=1),
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

    try:
        segment_ranges = np.empty((1, 2), dtype=np.int64)
        segment_ranges[0, 0] = 0
        segment_ranges[0, 1] = context.item_plan.sample_count
    except MemoryError:
        return _allocation_error(context.spec.item_id, "line segment-range allocation failed")
    except (IndexError, TypeError, ValueError):
        return _contract_error(context.spec.item_id, "line segment-range construction failed")
    if (
        type(segment_ranges) is not np.ndarray
        or segment_ranges.dtype != np.dtype(np.int64)
        or segment_ranges.shape != (1, 2)
        or not segment_ranges.flags.owndata
        or not segment_ranges.flags.writeable
    ):
        return _contract_error(context.spec.item_id, "line segment ranges are invalid")

    cancelled_or_error = _poll_cancellation(
        cancellation_probe,
        item_id=context.spec.item_id,
    )
    if isinstance(cancelled_or_error, ErrorInfo):
        return cancelled_or_error
    if cancelled_or_error:
        return SamplingCancelled(context.spec.item_id)

    x.setflags(write=False)
    y.setflags(write=False)
    segment_ranges.setflags(write=False)
    try:
        sampled = SampledParameterizedCurve(
            item_id=context.spec.item_id,
            x=x,
            y=y,
            segment_ranges=segment_ranges,
            segment_metadata=metadata,
            visible_segment_count=1,
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
        return _contract_error(
            context.spec.item_id,
            "frozen parameterized sampling result contract failed",
        )


def _sample_approved_oval_curve(
    approved_plan: RenderPlan,
    *,
    cancellation_probe: CancellationProbe | None,
) -> SamplingOutcome:
    """Execute one approved Circle/Ellipse plan in bounded angular batches."""

    context_or_error = _validated_oval_sampling_context(approved_plan)
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

    segment_count = len(context.intervals)
    try:
        x = np.empty(context.item_plan.sample_count, dtype=np.float64)
        y = np.empty(context.item_plan.sample_count, dtype=np.float64)
        segment_ranges = np.empty((segment_count, 2), dtype=np.int64)
    except MemoryError:
        return _allocation_error(context.spec.item_id, "formal oval output allocation failed")
    except (TypeError, ValueError):
        return _contract_error(context.spec.item_id, "formal oval output allocation failed")
    if not _owned_writable_vector(x, context.item_plan.sample_count):
        return _contract_error(context.spec.item_id, "formal oval x allocation is invalid")
    if not _owned_writable_vector(y, context.item_plan.sample_count):
        return _contract_error(context.spec.item_id, "formal oval y allocation is invalid")
    if (
        type(segment_ranges) is not np.ndarray
        or segment_ranges.dtype != np.dtype(np.int64)
        or segment_ranges.shape != (segment_count, 2)
        or not segment_ranges.flags.owndata
        or not segment_ranges.flags.writeable
    ):
        return _contract_error(context.spec.item_id, "oval segment ranges are invalid")

    offset = 0
    precision_limited_segment_count = 0
    for segment_index, interval in enumerate(context.intervals):
        cancelled_or_error = _poll_cancellation(
            cancellation_probe,
            item_id=context.spec.item_id,
        )
        if isinstance(cancelled_or_error, ErrorInfo):
            return cancelled_or_error
        if cancelled_or_error:
            return SamplingCancelled(context.spec.item_id)

        segment_start = offset
        segment_stop = segment_start + interval.sample_count
        segment_ranges[segment_index, 0] = segment_start
        segment_ranges[segment_index, 1] = segment_stop
        interval_span = interval.parameter_stop - interval.parameter_start
        denominator = (
            interval.sample_count
            if interval.closure is SegmentClosure.CLOSED
            else interval.sample_count - 1
        )
        precision_limited = False
        validation_since_poll = 0

        for batch_start in range(0, interval.sample_count, context.item_plan.batch_size):
            batch_stop = min(
                interval.sample_count,
                batch_start + context.item_plan.batch_size,
            )
            cancelled_or_error = _poll_cancellation(
                cancellation_probe,
                item_id=context.spec.item_id,
            )
            if isinstance(cancelled_or_error, ErrorInfo):
                return cancelled_or_error
            if cancelled_or_error:
                return SamplingCancelled(context.spec.item_id)

            try:
                # Absolute interval indices keep results invariant across batch sizes.
                theta = np.arange(batch_start, batch_stop, dtype=np.float64)
                np.divide(theta, denominator, out=theta)
                np.multiply(theta, interval_span, out=theta)
                np.add(theta, interval.parameter_start, out=theta)
                if batch_start == 0:
                    theta[0] = interval.parameter_start
                if (
                    interval.closure is SegmentClosure.OPEN
                    and batch_stop == interval.sample_count
                ):
                    theta[-1] = interval.parameter_stop
                cosine = np.cos(theta)
                sine = np.sin(theta)
                destination = slice(
                    segment_start + batch_start,
                    segment_start + batch_stop,
                )
                np.multiply(cosine, context.geometry.semi_axis_x_float, out=x[destination])
                np.add(x[destination], context.geometry.center_x_float, out=x[destination])
                np.multiply(sine, context.geometry.semi_axis_y_float, out=y[destination])
                np.add(y[destination], context.geometry.center_y_float, out=y[destination])

                if batch_start == 0:
                    x[segment_start], y[segment_start] = _oval_scalar_point(
                        context.geometry,
                        interval.parameter_start,
                    )
                if (
                    interval.closure is SegmentClosure.OPEN
                    and batch_stop == interval.sample_count
                ):
                    x[segment_stop - 1], y[segment_stop - 1] = _oval_scalar_point(
                        context.geometry,
                        interval.parameter_stop,
                    )

                finite = np.empty(theta.shape, dtype=np.bool_)
                np.isfinite(theta, out=finite)
                all_finite = bool(np.all(finite))
                np.isfinite(x[destination], out=finite)
                all_finite = all_finite and bool(np.all(finite))
                np.isfinite(y[destination], out=finite)
                all_finite = all_finite and bool(np.all(finite))
                if not all_finite:
                    return _oval_numeric_range_error(
                        context.spec.item_id,
                        "oval angular batch produced a non-finite sample",
                    )
            except MemoryError:
                return _allocation_error(
                    context.spec.item_id,
                    "oval angular batch allocation failed",
                )
            except (FloatingPointError, IndexError, OverflowError, TypeError, ValueError):
                return _oval_numeric_range_error(
                    context.spec.item_id,
                    "oval angular batch execution failed",
                )

            cancelled_or_error = _poll_cancellation(
                cancellation_probe,
                item_id=context.spec.item_id,
            )
            if isinstance(cancelled_or_error, ErrorInfo):
                return cancelled_or_error
            if cancelled_or_error:
                return SamplingCancelled(context.spec.item_id)

            for sample_index in range(destination.start, destination.stop):
                if validation_since_poll >= context.policy.cancellation_check_interval:
                    cancelled_or_error = _poll_cancellation(
                        cancellation_probe,
                        item_id=context.spec.item_id,
                    )
                    if isinstance(cancelled_or_error, ErrorInfo):
                        return cancelled_or_error
                    if cancelled_or_error:
                        return SamplingCancelled(context.spec.item_id)
                    validation_since_poll = 0
                try:
                    residual = normalized_oval_residual(
                        context.geometry,
                        float(x[sample_index]),
                        float(y[sample_index]),
                    )
                except MemoryError:
                    return _allocation_error(
                        context.spec.item_id,
                        "oval exact residual allocation failed",
                    )
                except (AttributeError, OverflowError, TypeError, ValueError, ZeroDivisionError):
                    return _oval_numeric_range_error(
                        context.spec.item_id,
                        "oval exact residual validation failed",
                    )
                if residual > context.policy.maximum_residual_ulps * _FLOAT64_EPSILON:
                    return _oval_numeric_range_error(
                        context.spec.item_id,
                        "approved oval residual exceeds the hard threshold",
                    )
                if residual > context.policy.target_residual_ulps * _FLOAT64_EPSILON:
                    precision_limited = True
                validation_since_poll += 1

        if not _segment_contains_distinct_adjacent_points(x, y, segment_start, segment_stop):
            return _no_visible_error(
                context.spec.item_id,
                NoVisibleCurveReason.NO_DRAWABLE_SEGMENT,
            )
        if precision_limited:
            precision_limited_segment_count += 1
        offset = segment_stop

    if offset != context.item_plan.sample_count:
        return _contract_error(context.spec.item_id, "oval sample ranges do not fill output")

    cancelled_or_error = _poll_cancellation(
        cancellation_probe,
        item_id=context.spec.item_id,
    )
    if isinstance(cancelled_or_error, ErrorInfo):
        return cancelled_or_error
    if cancelled_or_error:
        return SamplingCancelled(context.spec.item_id)

    try:
        metadata = tuple(
            SampledSegmentMetadata(
                mathematical_branch_id=interval.mathematical_branch_id,
                closure=interval.closure,
            )
            for interval in context.intervals
        )
        diagnostics = ParameterizedSamplingDiagnostics(
            sampled_segment_count=segment_count,
            sampled_point_count=context.item_plan.sample_count,
        )
        warnings: list[SamplingWarning] = []
        clipped_segment_count = sum(
            interval.closure is SegmentClosure.OPEN for interval in context.intervals
        )
        if clipped_segment_count:
            warnings.append(
                SamplingWarning(
                    code=SamplingWarningCode.VIEWPORT_CLIPPED,
                    metrics=ViewportClippedMetrics(
                        clipped_segment_count=clipped_segment_count,
                    ),
                ),
            )
        if precision_limited_segment_count:
            warnings.append(
                SamplingWarning(
                    code=SamplingWarningCode.SAMPLING_PRECISION_LIMITED,
                    metrics=SamplingPrecisionLimitedMetrics(
                        limited_segment_count=precision_limited_segment_count,
                    ),
                ),
            )
    except MemoryError:
        return _allocation_error(context.spec.item_id, "oval metadata allocation failed")
    except (AttributeError, TypeError, ValueError):
        return _contract_error(context.spec.item_id, "oval metadata construction failed")

    x.setflags(write=False)
    y.setflags(write=False)
    segment_ranges.setflags(write=False)
    cancelled_or_error = _poll_cancellation(
        cancellation_probe,
        item_id=context.spec.item_id,
    )
    if isinstance(cancelled_or_error, ErrorInfo):
        return cancelled_or_error
    if cancelled_or_error:
        return SamplingCancelled(context.spec.item_id)

    try:
        sampled = SampledParameterizedCurve(
            item_id=context.spec.item_id,
            x=x,
            y=y,
            segment_ranges=segment_ranges,
            segment_metadata=metadata,
            visible_segment_count=segment_count,
            warnings=tuple(warnings),
            diagnostics=diagnostics,
        )
        object.__setattr__(
            sampled,
            "_plan_contract_snapshot",
            _snapshot_approved_render_plan(context.plan),
        )
    except MemoryError:
        return _allocation_error(context.spec.item_id, "oval result snapshot allocation failed")
    except (AttributeError, TypeError, ValueError):
        return _contract_error(
            context.spec.item_id,
            "frozen oval sampling result contract failed",
        )

    cancelled_or_error = _poll_cancellation(
        cancellation_probe,
        item_id=context.spec.item_id,
    )
    if isinstance(cancelled_or_error, ErrorInfo):
        return cancelled_or_error
    if cancelled_or_error:
        return SamplingCancelled(context.spec.item_id)
    return sampled


def _sample_approved_hyperbola_curve(
    approved_plan: RenderPlan,
    *,
    cancellation_probe: CancellationProbe | None,
) -> SamplingOutcome:
    """Execute one approved HyperbolaSpec plan in bounded sinh/cosh batches."""

    context_or_error = _validated_hyperbola_sampling_context(approved_plan)
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

    segment_count = len(context.intervals)
    try:
        x = np.empty(context.item_plan.sample_count, dtype=np.float64)
        y = np.empty(context.item_plan.sample_count, dtype=np.float64)
        segment_ranges = np.empty((segment_count, 2), dtype=np.int64)
    except MemoryError:
        return _allocation_error(
            context.spec.item_id,
            "formal hyperbola output allocation failed",
        )
    except (TypeError, ValueError):
        return _contract_error(
            context.spec.item_id,
            "formal hyperbola output allocation failed",
        )
    if not _owned_writable_vector(x, context.item_plan.sample_count):
        return _contract_error(context.spec.item_id, "formal hyperbola x allocation is invalid")
    if not _owned_writable_vector(y, context.item_plan.sample_count):
        return _contract_error(context.spec.item_id, "formal hyperbola y allocation is invalid")
    if (
        type(segment_ranges) is not np.ndarray
        or segment_ranges.dtype != np.dtype(np.int64)
        or segment_ranges.shape != (segment_count, 2)
        or not segment_ranges.flags.owndata
        or not segment_ranges.flags.writeable
    ):
        return _contract_error(context.spec.item_id, "hyperbola segment ranges are invalid")

    cancelled_or_error = _poll_cancellation(
        cancellation_probe,
        item_id=context.spec.item_id,
    )
    if isinstance(cancelled_or_error, ErrorInfo):
        return cancelled_or_error
    if cancelled_or_error:
        return SamplingCancelled(context.spec.item_id)

    offset = 0
    precision_limited_segment_count = 0
    for segment_index, interval in enumerate(context.intervals):
        cancelled_or_error = _poll_cancellation(
            cancellation_probe,
            item_id=context.spec.item_id,
        )
        if isinstance(cancelled_or_error, ErrorInfo):
            return cancelled_or_error
        if cancelled_or_error:
            return SamplingCancelled(context.spec.item_id)

        segment_start = offset
        segment_stop = segment_start + interval.sample_count
        segment_ranges[segment_index, 0] = segment_start
        segment_ranges[segment_index, 1] = segment_stop
        interval_span = interval.parameter_stop - interval.parameter_start
        denominator = interval.sample_count - 1
        branch_sign = -1.0 if interval.mathematical_branch_id == 0 else 1.0
        precision_limited = False
        validation_since_poll = 0

        for batch_start in range(0, interval.sample_count, context.item_plan.batch_size):
            batch_stop = min(
                interval.sample_count,
                batch_start + context.item_plan.batch_size,
            )
            cancelled_or_error = _poll_cancellation(
                cancellation_probe,
                item_id=context.spec.item_id,
            )
            if isinstance(cancelled_or_error, ErrorInfo):
                return cancelled_or_error
            if cancelled_or_error:
                return SamplingCancelled(context.spec.item_id)

            try:
                parameter = np.arange(batch_start, batch_stop, dtype=np.float64)
                np.divide(parameter, denominator, out=parameter)
                np.multiply(parameter, interval_span, out=parameter)
                np.add(parameter, interval.parameter_start, out=parameter)
                if batch_start == 0:
                    parameter[0] = interval.parameter_start
                if batch_stop == interval.sample_count:
                    parameter[-1] = interval.parameter_stop
                with np.errstate(over="raise", invalid="raise"):
                    hyperbolic_cosine = np.cosh(parameter)
                    hyperbolic_sine = np.sinh(parameter)
                    destination = slice(
                        segment_start + batch_start,
                        segment_start + batch_stop,
                    )
                    if context.geometry.transverse_axis is AxisOrientation.HORIZONTAL:
                        np.multiply(
                            hyperbolic_cosine,
                            branch_sign * context.geometry.semi_transverse_float,
                            out=x[destination],
                        )
                        np.add(
                            x[destination],
                            context.geometry.center_x_float,
                            out=x[destination],
                        )
                        np.multiply(
                            hyperbolic_sine,
                            context.geometry.semi_conjugate_float,
                            out=y[destination],
                        )
                        np.add(
                            y[destination],
                            context.geometry.center_y_float,
                            out=y[destination],
                        )
                    else:
                        np.multiply(
                            hyperbolic_sine,
                            context.geometry.semi_conjugate_float,
                            out=x[destination],
                        )
                        np.add(
                            x[destination],
                            context.geometry.center_x_float,
                            out=x[destination],
                        )
                        np.multiply(
                            hyperbolic_cosine,
                            branch_sign * context.geometry.semi_transverse_float,
                            out=y[destination],
                        )
                        np.add(
                            y[destination],
                            context.geometry.center_y_float,
                            out=y[destination],
                        )

                if batch_start == 0:
                    x[segment_start], y[segment_start] = _hyperbola_scalar_point(
                        context.geometry,
                        interval.mathematical_branch_id,
                        interval.parameter_start,
                    )
                if batch_stop == interval.sample_count:
                    x[segment_stop - 1], y[segment_stop - 1] = _hyperbola_scalar_point(
                        context.geometry,
                        interval.mathematical_branch_id,
                        interval.parameter_stop,
                    )

                finite = np.empty(parameter.shape, dtype=np.bool_)
                np.isfinite(parameter, out=finite)
                all_finite = bool(np.all(finite))
                np.isfinite(hyperbolic_cosine, out=finite)
                all_finite = all_finite and bool(np.all(finite))
                np.isfinite(hyperbolic_sine, out=finite)
                all_finite = all_finite and bool(np.all(finite))
                np.isfinite(x[destination], out=finite)
                all_finite = all_finite and bool(np.all(finite))
                np.isfinite(y[destination], out=finite)
                all_finite = all_finite and bool(np.all(finite))
                if not all_finite:
                    return _hyperbola_numeric_range_error(
                        context.spec.item_id,
                        "hyperbola batch produced a non-finite sample",
                    )
            except MemoryError:
                return _allocation_error(
                    context.spec.item_id,
                    "hyperbola batch allocation failed",
                )
            except (FloatingPointError, IndexError, OverflowError, TypeError, ValueError):
                return _hyperbola_numeric_range_error(
                    context.spec.item_id,
                    "hyperbola batch execution failed",
                )

            cancelled_or_error = _poll_cancellation(
                cancellation_probe,
                item_id=context.spec.item_id,
            )
            if isinstance(cancelled_or_error, ErrorInfo):
                return cancelled_or_error
            if cancelled_or_error:
                return SamplingCancelled(context.spec.item_id)

            for sample_index in range(destination.start, destination.stop):
                if validation_since_poll >= context.policy.cancellation_check_interval:
                    cancelled_or_error = _poll_cancellation(
                        cancellation_probe,
                        item_id=context.spec.item_id,
                    )
                    if isinstance(cancelled_or_error, ErrorInfo):
                        return cancelled_or_error
                    if cancelled_or_error:
                        return SamplingCancelled(context.spec.item_id)
                    validation_since_poll = 0
                sample_x = float(x[sample_index])
                sample_y = float(y[sample_index])
                if not _point_within_viewport_ulps(
                    sample_x,
                    sample_y,
                    context.viewport,
                    context.policy.viewport_boundary_ulps,
                ):
                    return _hyperbola_numeric_range_error(
                        context.spec.item_id,
                        "approved hyperbola sample lies outside the viewport tolerance",
                    )
                try:
                    residual = normalized_hyperbola_residual(
                        context.geometry,
                        sample_x,
                        sample_y,
                    )
                except MemoryError:
                    return _allocation_error(
                        context.spec.item_id,
                        "hyperbola exact residual allocation failed",
                    )
                except (AttributeError, OverflowError, TypeError, ValueError, ZeroDivisionError):
                    return _hyperbola_numeric_range_error(
                        context.spec.item_id,
                        "hyperbola exact residual validation failed",
                    )
                if residual > context.policy.maximum_residual_ulps * _FLOAT64_EPSILON:
                    return _hyperbola_numeric_range_error(
                        context.spec.item_id,
                        "approved hyperbola residual exceeds the hard threshold",
                    )
                if residual > context.policy.target_residual_ulps * _FLOAT64_EPSILON:
                    precision_limited = True
                validation_since_poll += 1

        if not _segment_contains_distinct_adjacent_points(x, y, segment_start, segment_stop):
            return _hyperbola_numeric_range_error(
                context.spec.item_id,
                "approved hyperbola segment collapses in float64",
            )
        if precision_limited:
            precision_limited_segment_count += 1
        offset = segment_stop

    if offset != context.item_plan.sample_count:
        return _contract_error(
            context.spec.item_id,
            "hyperbola sample ranges do not fill output",
        )

    cancelled_or_error = _poll_cancellation(
        cancellation_probe,
        item_id=context.spec.item_id,
    )
    if isinstance(cancelled_or_error, ErrorInfo):
        return cancelled_or_error
    if cancelled_or_error:
        return SamplingCancelled(context.spec.item_id)

    try:
        metadata = tuple(
            SampledSegmentMetadata(
                mathematical_branch_id=interval.mathematical_branch_id,
                closure=SegmentClosure.OPEN,
            )
            for interval in context.intervals
        )
        diagnostics = ParameterizedSamplingDiagnostics(
            sampled_segment_count=segment_count,
            sampled_point_count=context.item_plan.sample_count,
        )
        warnings = [
            SamplingWarning(
                code=SamplingWarningCode.VIEWPORT_CLIPPED,
                metrics=ViewportClippedMetrics(clipped_segment_count=segment_count),
            ),
        ]
        if precision_limited_segment_count:
            warnings.append(
                SamplingWarning(
                    code=SamplingWarningCode.SAMPLING_PRECISION_LIMITED,
                    metrics=SamplingPrecisionLimitedMetrics(
                        limited_segment_count=precision_limited_segment_count,
                    ),
                ),
            )
    except MemoryError:
        return _allocation_error(context.spec.item_id, "hyperbola metadata allocation failed")
    except (AttributeError, TypeError, ValueError):
        return _contract_error(context.spec.item_id, "hyperbola metadata construction failed")

    cancelled_or_error = _poll_cancellation(
        cancellation_probe,
        item_id=context.spec.item_id,
    )
    if isinstance(cancelled_or_error, ErrorInfo):
        return cancelled_or_error
    if cancelled_or_error:
        return SamplingCancelled(context.spec.item_id)

    x.setflags(write=False)
    y.setflags(write=False)
    segment_ranges.setflags(write=False)
    cancelled_or_error = _poll_cancellation(
        cancellation_probe,
        item_id=context.spec.item_id,
    )
    if isinstance(cancelled_or_error, ErrorInfo):
        return cancelled_or_error
    if cancelled_or_error:
        return SamplingCancelled(context.spec.item_id)

    try:
        sampled = SampledParameterizedCurve(
            item_id=context.spec.item_id,
            x=x,
            y=y,
            segment_ranges=segment_ranges,
            segment_metadata=metadata,
            visible_segment_count=segment_count,
            warnings=tuple(warnings),
            diagnostics=diagnostics,
        )
        object.__setattr__(
            sampled,
            "_plan_contract_snapshot",
            _snapshot_approved_render_plan(context.plan),
        )
    except MemoryError:
        return _allocation_error(
            context.spec.item_id,
            "hyperbola result snapshot allocation failed",
        )
    except (AttributeError, TypeError, ValueError):
        return _contract_error(
            context.spec.item_id,
            "frozen hyperbola sampling result contract failed",
        )

    cancelled_or_error = _poll_cancellation(
        cancellation_probe,
        item_id=context.spec.item_id,
    )
    if isinstance(cancelled_or_error, ErrorInfo):
        return cancelled_or_error
    if cancelled_or_error:
        return SamplingCancelled(context.spec.item_id)
    return sampled


def _sample_approved_parabola_curve(
    approved_plan: RenderPlan,
    *,
    cancellation_probe: CancellationProbe | None,
) -> SamplingOutcome:
    """Execute one approved ParabolaSpec plan with no transient square array."""

    context_or_error = _validated_parabola_sampling_context(approved_plan)
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

    segment_count = len(context.intervals)
    try:
        x = np.empty(context.item_plan.sample_count, dtype=np.float64)
        y = np.empty(context.item_plan.sample_count, dtype=np.float64)
        segment_ranges = np.empty((segment_count, 2), dtype=np.int64)
    except MemoryError:
        return _allocation_error(
            context.spec.item_id,
            "formal parabola output allocation failed",
        )
    except (TypeError, ValueError):
        return _contract_error(
            context.spec.item_id,
            "formal parabola output allocation failed",
        )
    if not _owned_writable_vector(x, context.item_plan.sample_count):
        return _contract_error(context.spec.item_id, "formal parabola x allocation is invalid")
    if not _owned_writable_vector(y, context.item_plan.sample_count):
        return _contract_error(context.spec.item_id, "formal parabola y allocation is invalid")
    if (
        type(segment_ranges) is not np.ndarray
        or segment_ranges.dtype != np.dtype(np.int64)
        or segment_ranges.shape != (segment_count, 2)
        or not segment_ranges.flags.owndata
        or not segment_ranges.flags.writeable
    ):
        return _contract_error(context.spec.item_id, "parabola segment ranges are invalid")

    cancelled_or_error = _poll_cancellation(
        cancellation_probe,
        item_id=context.spec.item_id,
    )
    if isinstance(cancelled_or_error, ErrorInfo):
        return cancelled_or_error
    if cancelled_or_error:
        return SamplingCancelled(context.spec.item_id)

    offset = 0
    precision_limited_segment_count = 0
    for segment_index, interval in enumerate(context.intervals):
        cancelled_or_error = _poll_cancellation(
            cancellation_probe,
            item_id=context.spec.item_id,
        )
        if isinstance(cancelled_or_error, ErrorInfo):
            return cancelled_or_error
        if cancelled_or_error:
            return SamplingCancelled(context.spec.item_id)

        segment_start = offset
        segment_stop = segment_start + interval.sample_count
        segment_ranges[segment_index, 0] = segment_start
        segment_ranges[segment_index, 1] = segment_stop
        interval_span = interval.parameter_stop - interval.parameter_start
        denominator = interval.sample_count - 1
        precision_limited = False
        validation_since_poll = 0

        for batch_start in range(0, interval.sample_count, context.item_plan.batch_size):
            batch_stop = min(
                interval.sample_count,
                batch_start + context.item_plan.batch_size,
            )
            cancelled_or_error = _poll_cancellation(
                cancellation_probe,
                item_id=context.spec.item_id,
            )
            if isinstance(cancelled_or_error, ErrorInfo):
                return cancelled_or_error
            if cancelled_or_error:
                return SamplingCancelled(context.spec.item_id)

            try:
                parameter = np.arange(batch_start, batch_stop, dtype=np.float64)
                np.divide(parameter, denominator, out=parameter)
                np.multiply(parameter, interval_span, out=parameter)
                np.add(parameter, interval.parameter_start, out=parameter)
                if batch_start == 0:
                    parameter[0] = interval.parameter_start
                if batch_stop == interval.sample_count:
                    parameter[-1] = interval.parameter_stop
                destination = slice(
                    segment_start + batch_start,
                    segment_start + batch_stop,
                )
                with np.errstate(over="raise", invalid="raise"):
                    if context.geometry.has_vertical_axis:
                        np.multiply(
                            parameter,
                            context.geometry.two_focal_parameter_float,
                            out=x[destination],
                        )
                        np.add(
                            x[destination],
                            context.geometry.vertex_x_float,
                            out=x[destination],
                        )
                        np.square(parameter, out=y[destination])
                        np.multiply(
                            y[destination],
                            context.geometry.focal_parameter_float,
                            out=y[destination],
                        )
                        np.add(
                            y[destination],
                            context.geometry.vertex_y_float,
                            out=y[destination],
                        )
                    else:
                        np.square(parameter, out=x[destination])
                        np.multiply(
                            x[destination],
                            context.geometry.focal_parameter_float,
                            out=x[destination],
                        )
                        np.add(
                            x[destination],
                            context.geometry.vertex_x_float,
                            out=x[destination],
                        )
                        np.multiply(
                            parameter,
                            context.geometry.two_focal_parameter_float,
                            out=y[destination],
                        )
                        np.add(
                            y[destination],
                            context.geometry.vertex_y_float,
                            out=y[destination],
                        )

                if batch_start == 0:
                    x[segment_start], y[segment_start] = parabola_parameter_point(
                        context.geometry,
                        interval.parameter_start,
                    )
                if batch_stop == interval.sample_count:
                    x[segment_stop - 1], y[segment_stop - 1] = parabola_parameter_point(
                        context.geometry,
                        interval.parameter_stop,
                    )

                finite = np.empty(parameter.shape, dtype=np.bool_)
                np.isfinite(parameter, out=finite)
                all_finite = bool(np.all(finite))
                np.isfinite(x[destination], out=finite)
                all_finite = all_finite and bool(np.all(finite))
                np.isfinite(y[destination], out=finite)
                all_finite = all_finite and bool(np.all(finite))
                if not all_finite:
                    return _parabola_numeric_range_error(
                        context.spec.item_id,
                        "parabola batch produced a non-finite sample",
                    )
            except MemoryError:
                return _allocation_error(
                    context.spec.item_id,
                    "parabola batch allocation failed",
                )
            except (FloatingPointError, IndexError, OverflowError, TypeError, ValueError):
                return _parabola_numeric_range_error(
                    context.spec.item_id,
                    "parabola batch execution failed",
                )

            cancelled_or_error = _poll_cancellation(
                cancellation_probe,
                item_id=context.spec.item_id,
            )
            if isinstance(cancelled_or_error, ErrorInfo):
                return cancelled_or_error
            if cancelled_or_error:
                return SamplingCancelled(context.spec.item_id)

            for sample_index in range(destination.start, destination.stop):
                if validation_since_poll >= context.policy.cancellation_check_interval:
                    cancelled_or_error = _poll_cancellation(
                        cancellation_probe,
                        item_id=context.spec.item_id,
                    )
                    if isinstance(cancelled_or_error, ErrorInfo):
                        return cancelled_or_error
                    if cancelled_or_error:
                        return SamplingCancelled(context.spec.item_id)
                    validation_since_poll = 0
                sample_x = float(x[sample_index])
                sample_y = float(y[sample_index])
                if not _point_within_viewport_ulps(
                    sample_x,
                    sample_y,
                    context.viewport,
                    context.policy.viewport_boundary_ulps,
                ):
                    return _parabola_numeric_range_error(
                        context.spec.item_id,
                        "approved parabola sample lies outside the viewport tolerance",
                    )
                try:
                    residual = normalized_parabola_residual(
                        context.geometry,
                        sample_x,
                        sample_y,
                    )
                except MemoryError:
                    return _allocation_error(
                        context.spec.item_id,
                        "parabola exact residual allocation failed",
                    )
                except (AttributeError, OverflowError, TypeError, ValueError, ZeroDivisionError):
                    return _parabola_numeric_range_error(
                        context.spec.item_id,
                        "parabola exact residual validation failed",
                    )
                if residual > context.policy.maximum_residual_ulps * _FLOAT64_EPSILON:
                    return _parabola_numeric_range_error(
                        context.spec.item_id,
                        "approved parabola residual exceeds the hard threshold",
                    )
                if residual > context.policy.target_residual_ulps * _FLOAT64_EPSILON:
                    precision_limited = True
                validation_since_poll += 1

        if not _segment_contains_distinct_adjacent_points(x, y, segment_start, segment_stop):
            return _parabola_numeric_range_error(
                context.spec.item_id,
                "approved parabola segment collapses in float64",
            )
        if precision_limited:
            precision_limited_segment_count += 1
        offset = segment_stop

    if offset != context.item_plan.sample_count:
        return _contract_error(
            context.spec.item_id,
            "parabola sample ranges do not fill output",
        )

    cancelled_or_error = _poll_cancellation(
        cancellation_probe,
        item_id=context.spec.item_id,
    )
    if isinstance(cancelled_or_error, ErrorInfo):
        return cancelled_or_error
    if cancelled_or_error:
        return SamplingCancelled(context.spec.item_id)

    try:
        metadata = tuple(
            SampledSegmentMetadata(
                mathematical_branch_id=0,
                closure=SegmentClosure.OPEN,
            )
            for _ in context.intervals
        )
        diagnostics = ParameterizedSamplingDiagnostics(
            sampled_segment_count=segment_count,
            sampled_point_count=context.item_plan.sample_count,
        )
        warnings = [
            SamplingWarning(
                code=SamplingWarningCode.VIEWPORT_CLIPPED,
                metrics=ViewportClippedMetrics(clipped_segment_count=segment_count),
            ),
        ]
        if precision_limited_segment_count:
            warnings.append(
                SamplingWarning(
                    code=SamplingWarningCode.SAMPLING_PRECISION_LIMITED,
                    metrics=SamplingPrecisionLimitedMetrics(
                        limited_segment_count=precision_limited_segment_count,
                    ),
                ),
            )
    except MemoryError:
        return _allocation_error(context.spec.item_id, "parabola metadata allocation failed")
    except (AttributeError, TypeError, ValueError):
        return _contract_error(context.spec.item_id, "parabola metadata construction failed")

    cancelled_or_error = _poll_cancellation(
        cancellation_probe,
        item_id=context.spec.item_id,
    )
    if isinstance(cancelled_or_error, ErrorInfo):
        return cancelled_or_error
    if cancelled_or_error:
        return SamplingCancelled(context.spec.item_id)

    x.setflags(write=False)
    y.setflags(write=False)
    segment_ranges.setflags(write=False)
    cancelled_or_error = _poll_cancellation(
        cancellation_probe,
        item_id=context.spec.item_id,
    )
    if isinstance(cancelled_or_error, ErrorInfo):
        return cancelled_or_error
    if cancelled_or_error:
        return SamplingCancelled(context.spec.item_id)

    try:
        sampled = SampledParameterizedCurve(
            item_id=context.spec.item_id,
            x=x,
            y=y,
            segment_ranges=segment_ranges,
            segment_metadata=metadata,
            visible_segment_count=segment_count,
            warnings=tuple(warnings),
            diagnostics=diagnostics,
        )
        object.__setattr__(
            sampled,
            "_plan_contract_snapshot",
            _snapshot_approved_render_plan(context.plan),
        )
    except MemoryError:
        return _allocation_error(
            context.spec.item_id,
            "parabola result snapshot allocation failed",
        )
    except (AttributeError, TypeError, ValueError):
        return _contract_error(
            context.spec.item_id,
            "frozen parabola sampling result contract failed",
        )

    cancelled_or_error = _poll_cancellation(
        cancellation_probe,
        item_id=context.spec.item_id,
    )
    if isinstance(cancelled_or_error, ErrorInfo):
        return cancelled_or_error
    if cancelled_or_error:
        return SamplingCancelled(context.spec.item_id)
    return sampled


def _validated_parabola_sampling_context(
    plan: RenderPlan,
) -> _ParabolaSamplingContext | ErrorInfo:
    """Revalidate the signed plan, complete budget, and executable endpoints."""

    limits = DEFAULT_LIMITS
    policy = DEFAULT_PARABOLIC_SAMPLING_POLICY
    if plan.limits_version != limits.version:
        return _contract_error(None, "render plan limits version is not active")
    if type(plan.scene_spec) is not PlotSceneSpec or len(plan.scene_spec.items) != 1:
        return _contract_error(None, "render plan must contain one exact scene specification")
    spec = plan.scene_spec.items[0]
    if type(spec) is not ParabolaSpec:
        return _contract_error(None, "render plan item is not an exact ParabolaSpec")
    if plan.sampling_policy_version != policy.version:
        return _contract_error(spec.item_id, "parabolic sampling policy version is not active")
    if plan.numeric_executor_contract_version is not None:
        return _contract_error(spec.item_id, "parabola plan must not carry a numeric executor version")
    if (
        plan.parameterized_sampler_contract_version
        != PARAMETERIZED_SAMPLER_CONTRACT_VERSION
    ):
        return _contract_error(spec.item_id, "parameterized sampler version is not active")
    if type(plan.resolved_viewport) is not ResolvedViewport:
        return _contract_error(spec.item_id, "parabola plan viewport is not exact")
    if type(plan.item_plan) is not GeometryRenderItemPlan:
        return _contract_error(spec.item_id, "parabola item plan is missing")
    if type(plan.memory_budget) is not ParameterizedRenderMemoryBudget:
        return _contract_error(spec.item_id, "parabola memory budget is missing")
    item_plan = plan.item_plan
    budget = plan.memory_budget
    if (
        type(item_plan.segments) is not tuple
        or not item_plan.segments
        or not all(type(interval) is ParameterIntervalPlan for interval in item_plan.segments)
    ):
        return _contract_error(spec.item_id, "parabola plan requires exact parameter intervals")
    intervals = item_plan.segments
    try:
        plan.scene_spec.__post_init__()
        spec.__post_init__()
        plan.resolved_viewport.__post_init__()
        item_plan.__post_init__()
        for interval in intervals:
            interval.__post_init__()
        budget.__post_init__()
        policy.__post_init__()
        geometry = project_parabola_geometry(spec)
        for interval in intervals:
            if (
                interval.closure is not SegmentClosure.OPEN
                or interval.mathematical_branch_id != 0
            ):
                raise ValueError("approved parabola interval contract is invalid")
            for parameter in (interval.parameter_start, interval.parameter_stop):
                point = parabola_parameter_point(geometry, parameter)
                if not _point_within_viewport_ulps(
                    point[0],
                    point[1],
                    plan.resolved_viewport,
                    policy.viewport_boundary_ulps,
                ):
                    raise OverflowError("approved parabola endpoint is outside viewport")
        recomputed_budget = build_parabola_parameterized_memory_budget(
            sample_count=item_plan.sample_count,
            batch_size=item_plan.batch_size,
            image_width=plan.image_width,
            image_height=plan.image_height,
            limits=limits,
        )
    except MemoryError:
        return _allocation_error(
            spec.item_id,
            "parabola budget revalidation allocation failed",
        )
    except (AttributeError, TypeError, ValueError):
        return _contract_error(
            spec.item_id,
            "approved parabola plan contains an invalid contract",
        )
    except (OverflowError, ZeroDivisionError):
        return _parabola_numeric_range_error(
            spec.item_id,
            "approved parabola geometry is outside the executable float64 range",
        )
    if (
        spec.provenance.limits_version != limits.version
        or item_plan.item_id != spec.item_id
        or item_plan.mathematical_branch_count != 1
        or item_plan.max_segment_count != 2
        or len(intervals) > 2
    ):
        return _contract_error(spec.item_id, "parabola plan identity or capacity is invalid")
    if recomputed_budget != budget:
        return _contract_error(spec.item_id, "parabola parameterized budget is not active")
    try:
        limits.validate_scene_resources(
            item_count=1,
            sample_points_per_item=item_plan.sample_count,
            total_sample_points=item_plan.sample_count,
            branches_per_item=2,
            total_branches=2,
            estimated_memory_bytes=budget.total_bytes,
        )
    except (TypeError, ValueError):
        return _parameterized_resource_error(
            spec.item_id,
            "approved parabola plan exceeds active scene resource limits",
        )
    return _ParabolaSamplingContext(
        plan=plan,
        spec=spec,
        viewport=plan.resolved_viewport,
        item_plan=item_plan,
        intervals=intervals,
        memory_budget=budget,
        limits=limits,
        policy=policy,
        geometry=geometry,
    )


def _validated_hyperbola_sampling_context(
    plan: RenderPlan,
) -> _HyperbolaSamplingContext | ErrorInfo:
    """Revalidate the signed plan, full budget, and safe parameter range."""

    limits = DEFAULT_LIMITS
    policy = DEFAULT_HYPERBOLIC_SAMPLING_POLICY
    if plan.limits_version != limits.version:
        return _contract_error(None, "render plan limits version is not active")
    if type(plan.scene_spec) is not PlotSceneSpec or len(plan.scene_spec.items) != 1:
        return _contract_error(None, "render plan must contain one exact scene specification")
    spec = plan.scene_spec.items[0]
    if type(spec) is not HyperbolaSpec:
        return _contract_error(None, "render plan item is not an exact HyperbolaSpec")
    if plan.sampling_policy_version != policy.version:
        return _contract_error(spec.item_id, "hyperbolic sampling policy version is not active")
    if plan.numeric_executor_contract_version is not None:
        return _contract_error(spec.item_id, "hyperbola plan must not carry a numeric executor version")
    if (
        plan.parameterized_sampler_contract_version
        != PARAMETERIZED_SAMPLER_CONTRACT_VERSION
    ):
        return _contract_error(spec.item_id, "parameterized sampler version is not active")
    if type(plan.resolved_viewport) is not ResolvedViewport:
        return _contract_error(spec.item_id, "hyperbola plan viewport is not exact")
    if type(plan.item_plan) is not GeometryRenderItemPlan:
        return _contract_error(spec.item_id, "hyperbola item plan is missing")
    if type(plan.memory_budget) is not ParameterizedRenderMemoryBudget:
        return _contract_error(spec.item_id, "hyperbola memory budget is missing")
    item_plan = plan.item_plan
    budget = plan.memory_budget
    if (
        type(item_plan.segments) is not tuple
        or not item_plan.segments
        or not all(type(interval) is ParameterIntervalPlan for interval in item_plan.segments)
    ):
        return _contract_error(spec.item_id, "hyperbola plan requires exact parameter intervals")
    intervals = item_plan.segments
    try:
        plan.scene_spec.__post_init__()
        spec.__post_init__()
        plan.resolved_viewport.__post_init__()
        item_plan.__post_init__()
        for interval in intervals:
            interval.__post_init__()
        budget.__post_init__()
        policy.__post_init__()
        geometry = project_hyperbola_geometry(spec)
        for interval in intervals:
            if (
                interval.closure is not SegmentClosure.OPEN
                or abs(interval.parameter_start) > geometry.max_safe_parameter
                or abs(interval.parameter_stop) > geometry.max_safe_parameter
            ):
                raise OverflowError("approved hyperbola parameter range is unsafe")
            for parameter in (interval.parameter_start, interval.parameter_stop):
                point = hyperbola_parameter_point(
                    geometry,
                    interval.mathematical_branch_id,
                    parameter,
                )
                if not _point_within_viewport_ulps(
                    point[0],
                    point[1],
                    plan.resolved_viewport,
                    policy.viewport_boundary_ulps,
                ):
                    raise OverflowError("approved hyperbola endpoint is outside viewport")
        recomputed_budget = build_hyperbola_parameterized_memory_budget(
            sample_count=item_plan.sample_count,
            batch_size=item_plan.batch_size,
            image_width=plan.image_width,
            image_height=plan.image_height,
            limits=limits,
        )
    except MemoryError:
        return _allocation_error(
            spec.item_id,
            "hyperbola budget revalidation allocation failed",
        )
    except (AttributeError, TypeError, ValueError):
        return _contract_error(
            spec.item_id,
            "approved hyperbola plan contains an invalid contract",
        )
    except (OverflowError, ZeroDivisionError):
        return _hyperbola_numeric_range_error(
            spec.item_id,
            "approved hyperbola geometry is outside the executable float64 range",
        )
    if (
        spec.provenance.limits_version != limits.version
        or item_plan.item_id != spec.item_id
        or item_plan.mathematical_branch_count != 2
        or item_plan.max_segment_count != 4
        or len(intervals) > 4
    ):
        return _contract_error(spec.item_id, "hyperbola plan identity or capacity is invalid")
    if recomputed_budget != budget:
        return _contract_error(spec.item_id, "hyperbola parameterized budget is not active")
    try:
        limits.validate_scene_resources(
            item_count=1,
            sample_points_per_item=item_plan.sample_count,
            total_sample_points=item_plan.sample_count,
            branches_per_item=4,
            total_branches=4,
            estimated_memory_bytes=budget.total_bytes,
        )
    except (TypeError, ValueError):
        return _parameterized_resource_error(
            spec.item_id,
            "approved hyperbola plan exceeds active scene resource limits",
        )
    return _HyperbolaSamplingContext(
        plan=plan,
        spec=spec,
        viewport=plan.resolved_viewport,
        item_plan=item_plan,
        intervals=intervals,
        memory_budget=budget,
        limits=limits,
        policy=policy,
        geometry=geometry,
    )


def _hyperbola_scalar_point(
    geometry: HyperbolaExecutionGeometry,
    mathematical_branch_id: int,
    parameter: float,
) -> tuple[float, float]:
    return hyperbola_parameter_point(geometry, mathematical_branch_id, parameter)


def _point_within_viewport_ulps(
    x_value: float,
    y_value: float,
    viewport: ResolvedViewport,
    boundary_ulps: int,
) -> bool:
    x_tolerance = boundary_ulps * max(
        ulp(x_value),
        ulp(viewport.x_min),
        ulp(viewport.x_max),
        ulp(viewport.x_max - viewport.x_min),
    )
    y_tolerance = boundary_ulps * max(
        ulp(y_value),
        ulp(viewport.y_min),
        ulp(viewport.y_max),
        ulp(viewport.y_max - viewport.y_min),
    )
    return (
        viewport.x_min - x_tolerance <= x_value <= viewport.x_max + x_tolerance
        and viewport.y_min - y_tolerance <= y_value <= viewport.y_max + y_tolerance
    )


def _validated_oval_sampling_context(
    plan: RenderPlan,
) -> _OvalSamplingContext | ErrorInfo:
    limits = DEFAULT_LIMITS
    policy = DEFAULT_ANGULAR_SAMPLING_POLICY
    if plan.limits_version != limits.version:
        return _contract_error(None, "render plan limits version is not active")
    if type(plan.scene_spec) is not PlotSceneSpec or len(plan.scene_spec.items) != 1:
        return _contract_error(None, "render plan must contain one exact scene specification")
    spec = plan.scene_spec.items[0]
    if type(spec) not in {CircleSpec, EllipseSpec}:
        return _contract_error(None, "render plan item is not an exact oval specification")
    if plan.sampling_policy_version != policy.version:
        return _contract_error(spec.item_id, "angular sampling policy version is not active")
    if plan.numeric_executor_contract_version is not None:
        return _contract_error(spec.item_id, "oval plan must not carry a numeric executor version")
    if (
        plan.parameterized_sampler_contract_version
        != PARAMETERIZED_SAMPLER_CONTRACT_VERSION
    ):
        return _contract_error(spec.item_id, "parameterized sampler version is not active")
    if type(plan.resolved_viewport) is not ResolvedViewport:
        return _contract_error(spec.item_id, "oval plan viewport is not exact")
    if type(plan.item_plan) is not GeometryRenderItemPlan:
        return _contract_error(spec.item_id, "oval item plan is missing")
    if type(plan.memory_budget) is not ParameterizedRenderMemoryBudget:
        return _contract_error(spec.item_id, "oval memory budget is missing")
    item_plan = plan.item_plan
    budget = plan.memory_budget
    if (
        type(item_plan.segments) is not tuple
        or not item_plan.segments
        or not all(type(interval) is ParameterIntervalPlan for interval in item_plan.segments)
    ):
        return _contract_error(spec.item_id, "oval plan requires exact parameter intervals")
    intervals = item_plan.segments
    try:
        plan.scene_spec.__post_init__()
        spec.__post_init__()
        plan.resolved_viewport.__post_init__()
        item_plan.__post_init__()
        for interval in intervals:
            interval.__post_init__()
        budget.__post_init__()
        policy.__post_init__()
        geometry = project_oval_geometry(spec)
        recomputed_budget = build_oval_parameterized_memory_budget(
            sample_count=item_plan.sample_count,
            batch_size=item_plan.batch_size,
            image_width=plan.image_width,
            image_height=plan.image_height,
            limits=limits,
        )
    except MemoryError:
        return _allocation_error(spec.item_id, "oval budget revalidation allocation failed")
    except (AttributeError, TypeError, ValueError):
        return _contract_error(spec.item_id, "approved oval plan contains an invalid contract")
    except (OverflowError, ZeroDivisionError):
        return _oval_numeric_range_error(
            spec.item_id,
            "approved oval geometry is outside the executable float64 range",
        )
    if (
        spec.provenance.limits_version != limits.version
        or item_plan.item_id != spec.item_id
        or item_plan.mathematical_branch_count != 1
        or item_plan.max_segment_count != 4
        or len(intervals) > 4
    ):
        return _contract_error(spec.item_id, "oval plan identity or capacity is invalid")
    if recomputed_budget != budget:
        return _contract_error(spec.item_id, "oval parameterized budget is not active")
    try:
        limits.validate_scene_resources(
            item_count=1,
            sample_points_per_item=item_plan.sample_count,
            total_sample_points=item_plan.sample_count,
            branches_per_item=4,
            total_branches=4,
            estimated_memory_bytes=budget.total_bytes,
        )
    except (TypeError, ValueError):
        return _parameterized_resource_error(
            spec.item_id,
            "approved oval plan exceeds active scene resource limits",
        )
    return _OvalSamplingContext(
        plan=plan,
        spec=spec,
        viewport=plan.resolved_viewport,
        item_plan=item_plan,
        intervals=intervals,
        memory_budget=budget,
        limits=limits,
        policy=policy,
        geometry=geometry,
    )


def _oval_scalar_point(
    geometry: OvalExecutionGeometry,
    theta: float,
) -> tuple[float, float]:
    return oval_parameter_point(geometry, theta)


def _segment_contains_distinct_adjacent_points(
    x: Float64Vector,
    y: Float64Vector,
    start: int,
    stop: int,
) -> bool:
    for index in range(start + 1, stop):
        if x[index] != x[index - 1] or y[index] != y[index - 1]:
            return True
    return False


def _validated_parameterized_sampling_context(
    plan: RenderPlan,
) -> _ParameterizedSamplingContext | ErrorInfo:
    limits = DEFAULT_LIMITS
    policy = DEFAULT_LINE_SAMPLING_POLICY
    if plan.limits_version != limits.version:
        return _contract_error(None, "render plan limits version is not active")
    if type(plan.scene_spec) is not PlotSceneSpec or len(plan.scene_spec.items) != 1:
        return _contract_error(None, "render plan must contain one exact scene specification")
    spec = plan.scene_spec.items[0]
    if type(spec) in {CircleSpec, EllipseSpec, HyperbolaSpec, ParabolaSpec}:
        return _contract_error(
            spec.item_id,
            "parameterized geometry strategy is not implemented in stage 14B-2",
        )
    if type(spec) is not LineSpec:
        return _contract_error(None, "render plan item is not an exact LineSpec")
    if plan.sampling_policy_version != policy.version:
        return _contract_error(spec.item_id, "line sampling policy version is not active")
    if plan.numeric_executor_contract_version is not None:
        return _contract_error(spec.item_id, "line plan must not carry a numeric executor version")
    if (
        plan.parameterized_sampler_contract_version
        != PARAMETERIZED_SAMPLER_CONTRACT_VERSION
    ):
        return _contract_error(spec.item_id, "parameterized sampler version is not active")
    if type(plan.resolved_viewport) is not ResolvedViewport:
        return _contract_error(spec.item_id, "line plan viewport is not exact")
    if type(plan.item_plan) is not GeometryRenderItemPlan:
        return _contract_error(spec.item_id, "line item plan is missing")
    if type(plan.memory_budget) is not ParameterizedRenderMemoryBudget:
        return _contract_error(spec.item_id, "line memory budget is missing")
    item_plan = plan.item_plan
    budget = plan.memory_budget
    if len(item_plan.segments) != 1 or type(item_plan.segments[0]) is not LineSegmentPlan:
        return _contract_error(spec.item_id, "line plan must contain one exact segment")
    segment = item_plan.segments[0]
    try:
        plan.scene_spec.__post_init__()
        spec.__post_init__()
        plan.resolved_viewport.__post_init__()
        item_plan.__post_init__()
        segment.__post_init__()
        budget.__post_init__()
        policy.__post_init__()
        recomputed_budget = build_line_parameterized_memory_budget(
            image_width=plan.image_width,
            image_height=plan.image_height,
            limits=limits,
        )
    except MemoryError:
        return _allocation_error(spec.item_id, "line budget revalidation allocation failed")
    except (AttributeError, TypeError, ValueError):
        return _contract_error(spec.item_id, "approved line plan contains an invalid contract")
    if spec.provenance.limits_version != limits.version or item_plan.item_id != spec.item_id:
        return _contract_error(spec.item_id, "line plan item identity or limits mismatch")
    if recomputed_budget != budget:
        return _contract_error(spec.item_id, "line parameterized budget is not active")
    try:
        limits.validate_scene_resources(
            item_count=1,
            sample_points_per_item=item_plan.sample_count,
            total_sample_points=item_plan.sample_count,
            branches_per_item=item_plan.max_segment_count,
            total_branches=item_plan.max_segment_count,
            estimated_memory_bytes=budget.total_bytes,
        )
    except (TypeError, ValueError):
        return _parameterized_resource_error(
            spec.item_id,
            "approved line plan exceeds active scene resource limits",
        )
    return _ParameterizedSamplingContext(
        plan=plan,
        spec=spec,
        viewport=plan.resolved_viewport,
        item_plan=item_plan,
        segment=segment,
        memory_budget=budget,
        limits=limits,
        policy=policy,
    )


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


def _parameterized_resource_error(item_id: str, technical_message: str) -> ErrorInfo:
    return ErrorInfo(
        code=ErrorCode.RESOURCE_LIMIT_EXCEEDED,
        user_message="参数化直线超过当前资源限制，请缩小输出规模后重试。",
        technical_message=technical_message,
        item_id=item_id,
        field_name="parameterized_budget",
        recoverable=True,
    )


def _numeric_range_error(item_id: str, technical_message: str) -> ErrorInfo:
    return ErrorInfo(
        code=ErrorCode.NUMERIC_RANGE_UNSUPPORTED,
        user_message="直线端点超出当前可保证的数值精度范围。",
        technical_message=technical_message,
        item_id=item_id,
        field_name="line_residual",
        recoverable=True,
    )


def _oval_numeric_range_error(item_id: str, technical_message: str) -> ErrorInfo:
    return ErrorInfo(
        code=ErrorCode.NUMERIC_RANGE_UNSUPPORTED,
        user_message="The circle or ellipse exceeds the supported numeric precision.",
        technical_message=technical_message,
        item_id=item_id,
        field_name="oval_residual",
        recoverable=True,
    )


def _hyperbola_numeric_range_error(item_id: str, technical_message: str) -> ErrorInfo:
    return ErrorInfo(
        code=ErrorCode.NUMERIC_RANGE_UNSUPPORTED,
        user_message="The hyperbola exceeds the supported numeric precision.",
        technical_message=technical_message,
        item_id=item_id,
        field_name="hyperbola_residual",
        recoverable=True,
    )


def _parabola_numeric_range_error(item_id: str, technical_message: str) -> ErrorInfo:
    return ErrorInfo(
        code=ErrorCode.NUMERIC_RANGE_UNSUPPORTED,
        user_message="The parabola exceeds the supported numeric precision.",
        technical_message=technical_message,
        item_id=item_id,
        field_name="parabola_residual",
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
    "ParameterizedSamplingDiagnostics",
    "SampledCurve",
    "SampledExplicitFunction",
    "SampledParameterizedCurve",
    "SampledSegmentMetadata",
    "SamplingPrecisionLimitedMetrics",
    "SamplingCancelled",
    "SamplingDiagnostics",
    "SamplingOutcome",
    "SamplingWarning",
    "SamplingWarningCode",
    "SamplingWarningMetrics",
    "ViewportClippedMetrics",
    "sample_explicit_function",
    "sample_parameterized_curve",
]
