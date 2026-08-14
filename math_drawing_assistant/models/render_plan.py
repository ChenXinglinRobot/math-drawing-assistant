"""Immutable, budgeted render-plan contracts with typed approval receipts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from fractions import Fraction
from math import isfinite, tau
from typing import Final, TypeAlias

from math_drawing_assistant.models.errors import SourceSpan
from math_drawing_assistant.models.plot_specs import (
    AxisOrientation,
    CircleSpec,
    EllipseSpec,
    EquationProvenance,
    ExplicitFunctionSpec,
    HyperbolaSpec,
    LineSpec,
    ParabolaOpening,
    ParabolaSpec,
    PlotSceneSpec,
    PrimitiveEquationCoefficients,
    ValidatedExplicitExpression,
)
from math_drawing_assistant.models.restricted_ast import (
    BinaryOpNode,
    ConstantNode,
    FunctionCallNode,
    NumberNode,
    RestrictedExpression,
    SymbolNode,
    UnaryOpNode,
)
from math_drawing_assistant.models.state import ResolvedAspect, ViewportSource
from math_drawing_assistant.models.viewport import ResolvedViewport


RENDER_PLAN_CONTRACT_VERSION: Final[str] = "render-plan-v2-typed-geometry"
PARAMETERIZED_SAMPLER_CONTRACT_VERSION: Final[str] = "parameterized-sampler-v1"
_EXPECTED_NUMERIC_EXECUTOR_CONTRACT_VERSION: Final[str] = (
    "numeric-executor-v1-postorder-float64"
)
_APPROVAL_SEAL = object()


def _positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer.")
    if value < 1:
        raise ValueError(f"{name} must be positive.")
    return value


def _nonnegative_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer.")
    if value < 0:
        raise ValueError(f"{name} must not be negative.")
    return value


def _nonempty_version(value: object, name: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{name} must be a non-empty string.")
    return value


def _finite_float(value: object, name: str) -> float:
    if type(value) is not float:
        raise TypeError(f"{name} must be an exact float.")
    if not isfinite(value):
        raise ValueError(f"{name} must be finite.")
    return value


@dataclass(frozen=True, slots=True)
class ExplicitSamplingPolicy:
    """Scalar-only policy used to derive one explicit-function sampling plan."""

    version: str
    points_per_horizontal_pixel: int
    min_sample_points: int
    preferred_batch_points: int
    preferred_max_segment_count: int
    cancellation_check_interval: int
    finite_jump_threshold: int
    dense_oscillation_proxy_threshold: int

    def __post_init__(self) -> None:
        _nonempty_version(self.version, "version")
        for name in (
            "points_per_horizontal_pixel",
            "min_sample_points",
            "preferred_batch_points",
            "preferred_max_segment_count",
            "cancellation_check_interval",
            "finite_jump_threshold",
            "dense_oscillation_proxy_threshold",
        ):
            _positive_int(getattr(self, name), name)


DEFAULT_EXPLICIT_SAMPLING_POLICY: Final[ExplicitSamplingPolicy] = (
    ExplicitSamplingPolicy(
        version="explicit-sampling-policy-v1",
        points_per_horizontal_pixel=2,
        min_sample_points=320,
        preferred_batch_points=4_096,
        preferred_max_segment_count=16,
        cancellation_check_interval=256,
        finite_jump_threshold=64,
        dense_oscillation_proxy_threshold=32,
    )
)


@dataclass(frozen=True, slots=True)
class LineSamplingPolicy:
    """Scalar-only active policy for exact general-line sampling."""

    version: str
    sample_count: int
    batch_size: int
    endpoint_merge_ulps: int
    target_residual_ulps: int
    maximum_residual_ulps: int
    cancellation_check_interval: int

    def __post_init__(self) -> None:
        _nonempty_version(self.version, "version")
        for name in (
            "sample_count",
            "batch_size",
            "endpoint_merge_ulps",
            "target_residual_ulps",
            "maximum_residual_ulps",
            "cancellation_check_interval",
        ):
            _positive_int(getattr(self, name), name)
        if self.sample_count < 2:
            raise ValueError("line sampling needs at least two samples.")
        if self.batch_size > self.sample_count:
            raise ValueError("batch_size must not exceed sample_count.")
        if self.target_residual_ulps >= self.maximum_residual_ulps:
            raise ValueError("target residual must be below the maximum residual.")
        if self.version == "line-sampling-policy-v1" and (
            self.sample_count,
            self.batch_size,
            self.endpoint_merge_ulps,
            self.target_residual_ulps,
            self.maximum_residual_ulps,
            self.cancellation_check_interval,
        ) != (2, 1, 2, 4, 16, 1):
            raise ValueError("line-sampling-policy-v1 semantics are fixed.")


DEFAULT_LINE_SAMPLING_POLICY: Final[LineSamplingPolicy] = LineSamplingPolicy(
    version="line-sampling-policy-v1",
    sample_count=2,
    batch_size=1,
    endpoint_merge_ulps=2,
    target_residual_ulps=4,
    maximum_residual_ulps=16,
    cancellation_check_interval=1,
)


@dataclass(frozen=True, slots=True)
class AngularSamplingPolicy:
    """Scalar-only active policy for exact circle and ellipse sampling."""

    version: str
    samples_per_pixel: int
    minimum_open_segment_samples: int
    minimum_closed_curve_samples: int
    preferred_batch_points: int
    angle_merge_ulps: int
    viewport_boundary_ulps: int
    target_residual_ulps: int
    maximum_residual_ulps: int
    cancellation_check_interval: int

    def __post_init__(self) -> None:
        _nonempty_version(self.version, "version")
        for name in (
            "samples_per_pixel",
            "minimum_open_segment_samples",
            "minimum_closed_curve_samples",
            "preferred_batch_points",
            "angle_merge_ulps",
            "viewport_boundary_ulps",
            "target_residual_ulps",
            "maximum_residual_ulps",
            "cancellation_check_interval",
        ):
            _positive_int(getattr(self, name), name)
        if self.minimum_open_segment_samples < 2:
            raise ValueError("open angular segments need at least two samples.")
        if self.minimum_closed_curve_samples < 3:
            raise ValueError("closed angular curves need at least three samples.")
        if self.target_residual_ulps >= self.maximum_residual_ulps:
            raise ValueError("target residual must be below the maximum residual.")
        if self.version == "angular-sampling-policy-v1" and (
            self.samples_per_pixel,
            self.minimum_open_segment_samples,
            self.minimum_closed_curve_samples,
            self.preferred_batch_points,
            self.angle_merge_ulps,
            self.viewport_boundary_ulps,
            self.target_residual_ulps,
            self.maximum_residual_ulps,
            self.cancellation_check_interval,
        ) != (1, 2, 64, 4_096, 8, 8, 32, 256, 256):
            raise ValueError("angular-sampling-policy-v1 semantics are fixed.")


DEFAULT_ANGULAR_SAMPLING_POLICY: Final[AngularSamplingPolicy] = (
    AngularSamplingPolicy(
        version="angular-sampling-policy-v1",
        samples_per_pixel=1,
        minimum_open_segment_samples=2,
        minimum_closed_curve_samples=64,
        preferred_batch_points=4_096,
        angle_merge_ulps=8,
        viewport_boundary_ulps=8,
        target_residual_ulps=32,
        maximum_residual_ulps=256,
        cancellation_check_interval=256,
    )
)


@dataclass(frozen=True, slots=True)
class HyperbolicSamplingPolicy:
    """Scalar-only active policy for exact hyperbola sampling."""

    version: str
    samples_per_pixel: int
    minimum_open_segment_samples: int
    preferred_batch_points: int
    parameter_merge_ulps: int
    viewport_boundary_ulps: int
    target_residual_ulps: int
    maximum_residual_ulps: int
    cancellation_check_interval: int

    def __post_init__(self) -> None:
        _nonempty_version(self.version, "version")
        for name in (
            "samples_per_pixel",
            "minimum_open_segment_samples",
            "preferred_batch_points",
            "parameter_merge_ulps",
            "viewport_boundary_ulps",
            "target_residual_ulps",
            "maximum_residual_ulps",
            "cancellation_check_interval",
        ):
            _positive_int(getattr(self, name), name)
        if self.minimum_open_segment_samples < 2:
            raise ValueError("open hyperbolic segments need at least two samples.")
        if self.target_residual_ulps >= self.maximum_residual_ulps:
            raise ValueError("target residual must be below the maximum residual.")
        if self.version == "hyperbolic-sampling-policy-v1" and (
            self.samples_per_pixel,
            self.minimum_open_segment_samples,
            self.preferred_batch_points,
            self.parameter_merge_ulps,
            self.viewport_boundary_ulps,
            self.target_residual_ulps,
            self.maximum_residual_ulps,
            self.cancellation_check_interval,
        ) != (1, 2, 4_096, 8, 8, 32, 256, 256):
            raise ValueError("hyperbolic-sampling-policy-v1 semantics are fixed.")


DEFAULT_HYPERBOLIC_SAMPLING_POLICY: Final[HyperbolicSamplingPolicy] = (
    HyperbolicSamplingPolicy(
        version="hyperbolic-sampling-policy-v1",
        samples_per_pixel=1,
        minimum_open_segment_samples=2,
        preferred_batch_points=4_096,
        parameter_merge_ulps=8,
        viewport_boundary_ulps=8,
        target_residual_ulps=32,
        maximum_residual_ulps=256,
        cancellation_check_interval=256,
    )
)


@dataclass(frozen=True, slots=True)
class ParabolicSamplingPolicy:
    """Scalar-only active policy for exact parabola sampling."""

    version: str
    samples_per_pixel: int
    minimum_open_segment_samples: int
    preferred_batch_points: int
    parameter_merge_ulps: int
    viewport_boundary_ulps: int
    target_residual_ulps: int
    maximum_residual_ulps: int
    cancellation_check_interval: int

    def __post_init__(self) -> None:
        _nonempty_version(self.version, "version")
        for name in (
            "samples_per_pixel",
            "minimum_open_segment_samples",
            "preferred_batch_points",
            "parameter_merge_ulps",
            "viewport_boundary_ulps",
            "target_residual_ulps",
            "maximum_residual_ulps",
            "cancellation_check_interval",
        ):
            _positive_int(getattr(self, name), name)
        if self.minimum_open_segment_samples < 2:
            raise ValueError("open parabolic segments need at least two samples.")
        if self.target_residual_ulps >= self.maximum_residual_ulps:
            raise ValueError("target residual must be below the maximum residual.")
        if self.version == "parabolic-sampling-policy-v1" and (
            self.samples_per_pixel,
            self.minimum_open_segment_samples,
            self.preferred_batch_points,
            self.parameter_merge_ulps,
            self.viewport_boundary_ulps,
            self.target_residual_ulps,
            self.maximum_residual_ulps,
            self.cancellation_check_interval,
        ) != (1, 2, 4_096, 8, 8, 32, 256, 256):
            raise ValueError("parabolic-sampling-policy-v1 semantics are fixed.")


DEFAULT_PARABOLIC_SAMPLING_POLICY: Final[ParabolicSamplingPolicy] = (
    ParabolicSamplingPolicy(
        version="parabolic-sampling-policy-v1",
        samples_per_pixel=1,
        minimum_open_segment_samples=2,
        preferred_batch_points=4_096,
        parameter_merge_ulps=8,
        viewport_boundary_ulps=8,
        target_residual_ulps=32,
        maximum_residual_ulps=256,
        cancellation_check_interval=256,
    )
)


class SegmentClosure(str, Enum):
    """Whether a parameterized segment is mathematically open or closed."""

    OPEN = "open"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class LineSegmentPlan:
    """Two distinct finite endpoints for one general-line drawable segment."""

    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self) -> None:
        for name in ("x0", "y0", "x1", "y1"):
            _finite_float(getattr(self, name), name)
        if self.x0 == self.x1 and self.y0 == self.y1:
            raise ValueError("line segment endpoints must be distinct.")

    @property
    def mathematical_branch_id(self) -> int:
        return 0

    @property
    def sample_count(self) -> int:
        return 2

    @property
    def closure(self) -> SegmentClosure:
        return SegmentClosure.OPEN


@dataclass(frozen=True, slots=True)
class ParameterIntervalPlan:
    """One finite, ordered parameter interval for a mathematical branch."""

    mathematical_branch_id: int
    parameter_start: float
    parameter_stop: float
    sample_count: int
    closure: SegmentClosure

    def __post_init__(self) -> None:
        _nonnegative_int(self.mathematical_branch_id, "mathematical_branch_id")
        _finite_float(self.parameter_start, "parameter_start")
        _finite_float(self.parameter_stop, "parameter_stop")
        if self.parameter_start >= self.parameter_stop:
            raise ValueError("parameter_start must be below parameter_stop.")
        if _positive_int(self.sample_count, "sample_count") < 2:
            raise ValueError("each parameter interval needs at least two samples.")
        if type(self.closure) is not SegmentClosure:
            raise TypeError("closure must be an exact SegmentClosure.")


GeometrySegmentPlan: TypeAlias = LineSegmentPlan | ParameterIntervalPlan


@dataclass(frozen=True, slots=True)
class ExplicitRenderItemPlan:
    """Scalar execution bounds for one explicit-function item."""

    item_id: str
    sample_count: int
    batch_size: int
    max_segment_count: int
    max_live_float64_vectors: int

    def __post_init__(self) -> None:
        if type(self.item_id) is not str or not self.item_id.strip():
            raise ValueError("item_id must be a non-empty string.")
        for name in (
            "sample_count",
            "batch_size",
            "max_segment_count",
            "max_live_float64_vectors",
        ):
            _positive_int(getattr(self, name), name)
        if self.batch_size > self.sample_count:
            raise ValueError("batch_size must not exceed sample_count.")


@dataclass(frozen=True, slots=True)
class GeometryRenderItemPlan:
    """Closed union of typed drawable segments for one exact geometry item."""

    item_id: str
    mathematical_branch_count: int
    segments: tuple[GeometrySegmentPlan, ...]
    sample_count: int
    batch_size: int
    max_segment_count: int

    def __post_init__(self) -> None:
        if type(self.item_id) is not str or not self.item_id.strip():
            raise ValueError("item_id must be a non-empty string.")
        _positive_int(self.mathematical_branch_count, "mathematical_branch_count")
        for name in ("sample_count", "batch_size", "max_segment_count"):
            _positive_int(getattr(self, name), name)
        if type(self.segments) is not tuple or not self.segments:
            raise TypeError("segments must be a non-empty exact tuple.")
        segment_types = {type(segment) for segment in self.segments}
        if not segment_types.issubset({LineSegmentPlan, ParameterIntervalPlan}):
            raise TypeError("segments contain an unsupported exact segment type.")
        if len(segment_types) != 1:
            raise TypeError("line and parameter interval segments must not be mixed.")
        for segment in self.segments:
            segment.__post_init__()
            if segment.mathematical_branch_id >= self.mathematical_branch_count:
                raise ValueError("segment branch id is outside the declared branch count.")
        if self.sample_count != sum(segment.sample_count for segment in self.segments):
            raise ValueError("sample_count must equal the sum of segment samples.")
        if len(self.segments) > self.max_segment_count:
            raise ValueError("segment count exceeds max_segment_count.")
        if self.batch_size > self.sample_count:
            raise ValueError("batch_size must not exceed sample_count.")


RenderItemPlan: TypeAlias = ExplicitRenderItemPlan | GeometryRenderItemPlan


@dataclass(frozen=True, slots=True)
class RenderMemoryBudget:
    """Named explicit-function upper-bound components."""

    final_x_bytes: int
    final_y_bytes: int
    artist_data_bytes: int
    validity_mask_bytes: int
    segment_index_range_bytes: int
    segment_metadata_bytes: int
    executor_extra_batch_bytes: int
    rgba_canvas_bytes: int
    png_buffer_reserve_bytes: int
    png_copy_bytes: int

    def __post_init__(self) -> None:
        for name in (
            "final_x_bytes",
            "final_y_bytes",
            "artist_data_bytes",
            "validity_mask_bytes",
            "segment_index_range_bytes",
            "segment_metadata_bytes",
            "executor_extra_batch_bytes",
            "rgba_canvas_bytes",
            "png_buffer_reserve_bytes",
            "png_copy_bytes",
        ):
            _nonnegative_int(getattr(self, name), name)
        if self.artist_data_bytes != self.final_x_bytes + self.final_y_bytes:
            raise ValueError("artist_data_bytes must equal final x plus final y bytes.")
        if self.png_copy_bytes != self.png_buffer_reserve_bytes:
            raise ValueError("png_copy_bytes must equal the PNG buffer reserve.")

    @property
    def fixed_bytes(self) -> int:
        return (
            self.final_x_bytes
            + self.final_y_bytes
            + self.artist_data_bytes
            + self.validity_mask_bytes
            + self.segment_index_range_bytes
            + self.segment_metadata_bytes
            + self.rgba_canvas_bytes
            + self.png_buffer_reserve_bytes
            + self.png_copy_bytes
        )

    @property
    def batch_bytes(self) -> int:
        return self.executor_extra_batch_bytes

    @property
    def total_bytes(self) -> int:
        return self.fixed_bytes + self.batch_bytes


@dataclass(frozen=True, slots=True)
class ParameterizedRenderMemoryBudget:
    """Named parameterized-sampling upper-bound components."""

    final_x_bytes: int
    final_y_bytes: int
    artist_data_bytes: int
    segment_index_range_bytes: int
    segment_metadata_bytes: int
    parameter_batch_bytes: int
    transcendental_workspace_bytes: int
    validation_workspace_bytes: int
    rgba_canvas_bytes: int
    png_buffer_reserve_bytes: int
    png_copy_bytes: int

    def __post_init__(self) -> None:
        for name in (
            "final_x_bytes",
            "final_y_bytes",
            "artist_data_bytes",
            "segment_index_range_bytes",
            "segment_metadata_bytes",
            "parameter_batch_bytes",
            "transcendental_workspace_bytes",
            "validation_workspace_bytes",
            "rgba_canvas_bytes",
            "png_buffer_reserve_bytes",
            "png_copy_bytes",
        ):
            _nonnegative_int(getattr(self, name), name)
        if self.artist_data_bytes != self.final_x_bytes + self.final_y_bytes:
            raise ValueError("artist_data_bytes must equal final x plus final y bytes.")
        if self.png_copy_bytes != self.png_buffer_reserve_bytes:
            raise ValueError("png_copy_bytes must equal the PNG buffer reserve.")

    @property
    def fixed_bytes(self) -> int:
        return (
            self.final_x_bytes
            + self.final_y_bytes
            + self.artist_data_bytes
            + self.segment_index_range_bytes
            + self.segment_metadata_bytes
            + self.rgba_canvas_bytes
            + self.png_buffer_reserve_bytes
            + self.png_copy_bytes
        )

    @property
    def batch_bytes(self) -> int:
        return (
            self.parameter_batch_bytes
            + self.transcendental_workspace_bytes
            + self.validation_workspace_bytes
        )

    @property
    def total_bytes(self) -> int:
        return self.fixed_bytes + self.batch_bytes


@dataclass(frozen=True, slots=True)
class _SourceSpanSnapshot:
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class _RestrictedExpressionSnapshot:
    node_kind: str
    normalized_span: _SourceSpanSnapshot
    source_span: _SourceSpanSnapshot
    scalar_values: tuple[str | bool, ...]
    children: tuple["_RestrictedExpressionSnapshot", ...]


@dataclass(frozen=True, slots=True)
class _ValidatedExpressionSnapshot:
    expression: _RestrictedExpressionSnapshot
    normalized_input: str
    normalized_span: _SourceSpanSnapshot
    source_span: _SourceSpanSnapshot
    source_form: str
    free_variables: tuple[str, ...]
    limits_version: str


@dataclass(frozen=True, slots=True)
class _ExplicitFunctionSpecSnapshot:
    item_id: str
    validated_expression: _ValidatedExpressionSnapshot


@dataclass(frozen=True, slots=True)
class _PrimitiveEquationCoefficientsSnapshot:
    a: int
    b: int
    c: int
    d: int
    e: int
    f: int


@dataclass(frozen=True, slots=True)
class _EquationProvenanceSnapshot:
    normalized_input: str
    normalized_span: _SourceSpanSnapshot
    source_span: _SourceSpanSnapshot
    limits_version: str


@dataclass(frozen=True, slots=True)
class _FractionSnapshot:
    numerator: int
    denominator: int


@dataclass(frozen=True, slots=True)
class _GeometrySpecSnapshot:
    spec_type: str
    item_id: str
    coefficients: _PrimitiveEquationCoefficientsSnapshot
    provenance: _EquationProvenanceSnapshot
    fraction_fields: tuple[tuple[str, _FractionSnapshot], ...]
    enum_fields: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class _ResolvedViewportSnapshot:
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    aspect: str
    source: str


@dataclass(frozen=True, slots=True)
class _ExplicitRenderItemPlanSnapshot:
    item_id: str
    sample_count: int
    batch_size: int
    max_segment_count: int
    max_live_float64_vectors: int


@dataclass(frozen=True, slots=True)
class _LineSegmentPlanSnapshot:
    x0: float
    y0: float
    x1: float
    y1: float
    mathematical_branch_id: int
    sample_count: int
    closure: str


@dataclass(frozen=True, slots=True)
class _ParameterIntervalPlanSnapshot:
    mathematical_branch_id: int
    parameter_start: float
    parameter_stop: float
    sample_count: int
    closure: str


_GeometrySegmentPlanSnapshot: TypeAlias = (
    _LineSegmentPlanSnapshot | _ParameterIntervalPlanSnapshot
)


@dataclass(frozen=True, slots=True)
class _GeometryRenderItemPlanSnapshot:
    item_id: str
    mathematical_branch_count: int
    segments: tuple[_GeometrySegmentPlanSnapshot, ...]
    sample_count: int
    batch_size: int
    max_segment_count: int


@dataclass(frozen=True, slots=True)
class _RenderMemoryBudgetSnapshot:
    final_x_bytes: int
    final_y_bytes: int
    artist_data_bytes: int
    validity_mask_bytes: int
    segment_index_range_bytes: int
    segment_metadata_bytes: int
    executor_extra_batch_bytes: int
    rgba_canvas_bytes: int
    png_buffer_reserve_bytes: int
    png_copy_bytes: int


@dataclass(frozen=True, slots=True)
class _ParameterizedRenderMemoryBudgetSnapshot:
    final_x_bytes: int
    final_y_bytes: int
    artist_data_bytes: int
    segment_index_range_bytes: int
    segment_metadata_bytes: int
    parameter_batch_bytes: int
    transcendental_workspace_bytes: int
    validation_workspace_bytes: int
    rgba_canvas_bytes: int
    png_buffer_reserve_bytes: int
    png_copy_bytes: int


@dataclass(frozen=True, slots=True)
class _ExplicitRenderPlanApprovalSnapshot:
    scene_items: tuple[_ExplicitFunctionSpecSnapshot, ...]
    resolved_viewport: _ResolvedViewportSnapshot
    image_width: int
    image_height: int
    dpi: int
    show_grid: bool
    show_legend: bool
    plan_version: str
    limits_version: str
    sampling_policy_version: str | None
    numeric_executor_contract_version: str | None
    parameterized_sampler_contract_version: str | None
    item_plan: _ExplicitRenderItemPlanSnapshot
    memory_budget: _RenderMemoryBudgetSnapshot


# Private compatibility alias used by the existing explicit sampler provenance tests.
_RenderPlanApprovalSnapshot = _ExplicitRenderPlanApprovalSnapshot


@dataclass(frozen=True, slots=True)
class _GeometryRenderPlanApprovalSnapshot:
    scene_items: tuple[_GeometrySpecSnapshot, ...]
    resolved_viewport: _ResolvedViewportSnapshot
    image_width: int
    image_height: int
    dpi: int
    show_grid: bool
    show_legend: bool
    plan_version: str
    limits_version: str
    sampling_policy_version: str | None
    numeric_executor_contract_version: str | None
    parameterized_sampler_contract_version: str | None
    item_plan: _GeometryRenderItemPlanSnapshot
    memory_budget: _ParameterizedRenderMemoryBudgetSnapshot


_ApprovedRenderPlanSnapshot: TypeAlias = (
    _ExplicitRenderPlanApprovalSnapshot | _GeometryRenderPlanApprovalSnapshot
)


@dataclass(frozen=True, slots=True, init=False)
class _RenderPlanApprovalReceipt:
    approved_snapshot: _ApprovedRenderPlanSnapshot
    _seal: object = field(repr=False)

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("Render-plan approval receipts are issued internally.")


@dataclass(frozen=True, slots=True)
class RenderPlan:
    """A final render snapshot; ordinary construction remains unapproved."""

    scene_spec: PlotSceneSpec
    resolved_viewport: ResolvedViewport
    image_width: int
    image_height: int
    dpi: int
    plan_version: str
    limits_version: str
    show_grid: bool = False
    show_legend: bool = False
    sampling_policy_version: str | None = None
    numeric_executor_contract_version: str | None = None
    parameterized_sampler_contract_version: str | None = None
    item_plan: RenderItemPlan | None = None
    memory_budget: RenderMemoryBudget | ParameterizedRenderMemoryBudget | None = None
    _approval_receipt: _RenderPlanApprovalReceipt | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if type(self.scene_spec) is not PlotSceneSpec:
            raise TypeError("scene_spec must be an exact PlotSceneSpec.")
        if type(self.resolved_viewport) is not ResolvedViewport:
            raise TypeError("resolved_viewport must be an exact ResolvedViewport.")
        for name in ("image_width", "image_height", "dpi"):
            _positive_int(getattr(self, name), name)
        _nonempty_version(self.plan_version, "plan_version")
        _nonempty_version(self.limits_version, "limits_version")
        for name in ("show_grid", "show_legend"):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be a bool.")
        for name in (
            "sampling_policy_version",
            "numeric_executor_contract_version",
            "parameterized_sampler_contract_version",
        ):
            value = getattr(self, name)
            if value is not None:
                _nonempty_version(value, name)
        if self.item_plan is not None and type(self.item_plan) not in {
            ExplicitRenderItemPlan,
            GeometryRenderItemPlan,
        }:
            raise TypeError("item_plan must be an exact RenderItemPlan member or None.")
        if self.memory_budget is not None and type(self.memory_budget) not in {
            RenderMemoryBudget,
            ParameterizedRenderMemoryBudget,
        }:
            raise TypeError("memory_budget must be an exact render memory member or None.")


def _issue_approval_receipt(plan: RenderPlan) -> _RenderPlanApprovalReceipt:
    _validate_cross_plan_contracts(plan)
    receipt = object.__new__(_RenderPlanApprovalReceipt)
    object.__setattr__(receipt, "approved_snapshot", _approval_snapshot_from_plan(plan))
    object.__setattr__(receipt, "_seal", _APPROVAL_SEAL)
    return receipt


def _approval_snapshot_from_plan(plan: RenderPlan) -> _ApprovedRenderPlanSnapshot:
    if type(plan.scene_spec) is not PlotSceneSpec:
        raise TypeError("scene_spec must be an exact PlotSceneSpec.")
    if type(plan.scene_spec.items) is not tuple or len(plan.scene_spec.items) != 1:
        raise TypeError("approved scene items must be an exact single-item tuple.")
    viewport = plan.resolved_viewport
    if type(viewport) is not ResolvedViewport:
        raise TypeError("resolved_viewport must be an exact ResolvedViewport.")
    viewport_snapshot = _ResolvedViewportSnapshot(
        x_min=viewport.x_min,
        x_max=viewport.x_max,
        y_min=viewport.y_min,
        y_max=viewport.y_max,
        aspect=viewport.aspect.value,
        source=viewport.source.value,
    )
    item = plan.scene_spec.items[0]
    if type(item) is ExplicitFunctionSpec:
        item_plan = plan.item_plan
        memory = plan.memory_budget
        if type(item_plan) is not ExplicitRenderItemPlan:
            raise TypeError("explicit item plan must be exact.")
        if type(memory) is not RenderMemoryBudget:
            raise TypeError("explicit memory budget must be exact.")
        return _ExplicitRenderPlanApprovalSnapshot(
            scene_items=(_snapshot_explicit_spec(item),),
            resolved_viewport=viewport_snapshot,
            image_width=plan.image_width,
            image_height=plan.image_height,
            dpi=plan.dpi,
            show_grid=plan.show_grid,
            show_legend=plan.show_legend,
            plan_version=plan.plan_version,
            limits_version=plan.limits_version,
            sampling_policy_version=plan.sampling_policy_version,
            numeric_executor_contract_version=plan.numeric_executor_contract_version,
            parameterized_sampler_contract_version=(
                plan.parameterized_sampler_contract_version
            ),
            item_plan=_snapshot_explicit_item_plan(item_plan),
            memory_budget=_snapshot_explicit_memory(memory),
        )
    if type(item) in {LineSpec, CircleSpec, EllipseSpec, HyperbolaSpec, ParabolaSpec}:
        item_plan = plan.item_plan
        memory = plan.memory_budget
        if type(item_plan) is not GeometryRenderItemPlan:
            raise TypeError("geometry item plan must be exact.")
        if type(memory) is not ParameterizedRenderMemoryBudget:
            raise TypeError("parameterized memory budget must be exact.")
        return _GeometryRenderPlanApprovalSnapshot(
            scene_items=(_snapshot_geometry_spec(item),),
            resolved_viewport=viewport_snapshot,
            image_width=plan.image_width,
            image_height=plan.image_height,
            dpi=plan.dpi,
            show_grid=plan.show_grid,
            show_legend=plan.show_legend,
            plan_version=plan.plan_version,
            limits_version=plan.limits_version,
            sampling_policy_version=plan.sampling_policy_version,
            numeric_executor_contract_version=plan.numeric_executor_contract_version,
            parameterized_sampler_contract_version=(
                plan.parameterized_sampler_contract_version
            ),
            item_plan=_snapshot_geometry_item_plan(item_plan),
            memory_budget=_snapshot_parameterized_memory(memory),
        )
    raise TypeError("scene item exact type is unsupported.")


def _snapshot_explicit_item_plan(
    value: ExplicitRenderItemPlan,
) -> _ExplicitRenderItemPlanSnapshot:
    return _ExplicitRenderItemPlanSnapshot(
        item_id=value.item_id,
        sample_count=value.sample_count,
        batch_size=value.batch_size,
        max_segment_count=value.max_segment_count,
        max_live_float64_vectors=value.max_live_float64_vectors,
    )


def _snapshot_geometry_item_plan(
    value: GeometryRenderItemPlan,
) -> _GeometryRenderItemPlanSnapshot:
    segment_snapshots: list[_GeometrySegmentPlanSnapshot] = []
    for segment in value.segments:
        if type(segment) is LineSegmentPlan:
            segment_snapshots.append(
                _LineSegmentPlanSnapshot(
                    x0=segment.x0,
                    y0=segment.y0,
                    x1=segment.x1,
                    y1=segment.y1,
                    mathematical_branch_id=segment.mathematical_branch_id,
                    sample_count=segment.sample_count,
                    closure=segment.closure.value,
                ),
            )
        elif type(segment) is ParameterIntervalPlan:
            segment_snapshots.append(
                _ParameterIntervalPlanSnapshot(
                    mathematical_branch_id=segment.mathematical_branch_id,
                    parameter_start=segment.parameter_start,
                    parameter_stop=segment.parameter_stop,
                    sample_count=segment.sample_count,
                    closure=segment.closure.value,
                ),
            )
        else:
            raise TypeError("geometry segment exact type is unsupported.")
    return _GeometryRenderItemPlanSnapshot(
        item_id=value.item_id,
        mathematical_branch_count=value.mathematical_branch_count,
        segments=tuple(segment_snapshots),
        sample_count=value.sample_count,
        batch_size=value.batch_size,
        max_segment_count=value.max_segment_count,
    )


def _snapshot_explicit_memory(value: RenderMemoryBudget) -> _RenderMemoryBudgetSnapshot:
    return _RenderMemoryBudgetSnapshot(
        final_x_bytes=value.final_x_bytes,
        final_y_bytes=value.final_y_bytes,
        artist_data_bytes=value.artist_data_bytes,
        validity_mask_bytes=value.validity_mask_bytes,
        segment_index_range_bytes=value.segment_index_range_bytes,
        segment_metadata_bytes=value.segment_metadata_bytes,
        executor_extra_batch_bytes=value.executor_extra_batch_bytes,
        rgba_canvas_bytes=value.rgba_canvas_bytes,
        png_buffer_reserve_bytes=value.png_buffer_reserve_bytes,
        png_copy_bytes=value.png_copy_bytes,
    )


def _snapshot_parameterized_memory(
    value: ParameterizedRenderMemoryBudget,
) -> _ParameterizedRenderMemoryBudgetSnapshot:
    return _ParameterizedRenderMemoryBudgetSnapshot(
        final_x_bytes=value.final_x_bytes,
        final_y_bytes=value.final_y_bytes,
        artist_data_bytes=value.artist_data_bytes,
        segment_index_range_bytes=value.segment_index_range_bytes,
        segment_metadata_bytes=value.segment_metadata_bytes,
        parameter_batch_bytes=value.parameter_batch_bytes,
        transcendental_workspace_bytes=value.transcendental_workspace_bytes,
        validation_workspace_bytes=value.validation_workspace_bytes,
        rgba_canvas_bytes=value.rgba_canvas_bytes,
        png_buffer_reserve_bytes=value.png_buffer_reserve_bytes,
        png_copy_bytes=value.png_copy_bytes,
    )


def _snapshot_explicit_spec(value: object) -> _ExplicitFunctionSpecSnapshot:
    if type(value) is not ExplicitFunctionSpec:
        raise TypeError("scene items must be exact ExplicitFunctionSpec values.")
    validated = value.validated_expression
    if type(validated) is not ValidatedExplicitExpression:
        raise TypeError("validated_expression must be exact.")
    return _ExplicitFunctionSpecSnapshot(
        item_id=value.item_id,
        validated_expression=_ValidatedExpressionSnapshot(
            expression=_snapshot_restricted_expression(validated.expression),
            normalized_input=validated.normalized_input,
            normalized_span=_snapshot_source_span(validated.normalized_span),
            source_span=_snapshot_source_span(validated.source_span),
            source_form=validated.source_form,
            free_variables=tuple(validated.free_variables),
            limits_version=validated.limits_version,
        ),
    )


def _snapshot_geometry_spec(
    value: LineSpec | CircleSpec | EllipseSpec | HyperbolaSpec | ParabolaSpec,
) -> _GeometrySpecSnapshot:
    fraction_fields: tuple[tuple[str, _FractionSnapshot], ...]
    enum_fields: tuple[tuple[str, str], ...]
    if type(value) is LineSpec:
        fraction_fields = ()
        enum_fields = ()
    elif type(value) is CircleSpec:
        fraction_fields = (
            ("center_x", _snapshot_fraction(value.center_x)),
            ("center_y", _snapshot_fraction(value.center_y)),
            ("radius_squared", _snapshot_fraction(value.radius_squared)),
        )
        enum_fields = ()
    elif type(value) is EllipseSpec:
        fraction_fields = (
            ("center_x", _snapshot_fraction(value.center_x)),
            ("center_y", _snapshot_fraction(value.center_y)),
            ("semi_axis_x_squared", _snapshot_fraction(value.semi_axis_x_squared)),
            ("semi_axis_y_squared", _snapshot_fraction(value.semi_axis_y_squared)),
        )
        enum_fields = (("major_axis", value.major_axis.value),)
    elif type(value) is HyperbolaSpec:
        fraction_fields = (
            ("center_x", _snapshot_fraction(value.center_x)),
            ("center_y", _snapshot_fraction(value.center_y)),
            ("semi_transverse_squared", _snapshot_fraction(value.semi_transverse_squared)),
            ("semi_conjugate_squared", _snapshot_fraction(value.semi_conjugate_squared)),
        )
        enum_fields = (("transverse_axis", value.transverse_axis.value),)
    elif type(value) is ParabolaSpec:
        fraction_fields = (
            ("vertex_x", _snapshot_fraction(value.vertex_x)),
            ("vertex_y", _snapshot_fraction(value.vertex_y)),
            ("focal_parameter", _snapshot_fraction(value.focal_parameter)),
        )
        enum_fields = (("opening", value.opening.value),)
    else:
        raise TypeError("scene item exact geometry type is unsupported.")
    coefficients = value.coefficients
    provenance = value.provenance
    return _GeometrySpecSnapshot(
        spec_type=type(value).__name__,
        item_id=value.item_id,
        coefficients=_PrimitiveEquationCoefficientsSnapshot(
            a=coefficients.a,
            b=coefficients.b,
            c=coefficients.c,
            d=coefficients.d,
            e=coefficients.e,
            f=coefficients.f,
        ),
        provenance=_EquationProvenanceSnapshot(
            normalized_input=provenance.normalized_input,
            normalized_span=_snapshot_source_span(provenance.normalized_span),
            source_span=_snapshot_source_span(provenance.source_span),
            limits_version=provenance.limits_version,
        ),
        fraction_fields=fraction_fields,
        enum_fields=enum_fields,
    )


def _snapshot_fraction(value: object) -> _FractionSnapshot:
    if type(value) is not Fraction:
        raise TypeError("geometry fractions must be exact Fraction values.")
    return _FractionSnapshot(value.numerator, value.denominator)


def _snapshot_source_span(value: object) -> _SourceSpanSnapshot:
    if type(value) is not SourceSpan:
        raise TypeError("source locations must be exact SourceSpan values.")
    return _SourceSpanSnapshot(start=value.start, end=value.end)


def _snapshot_restricted_expression(
    value: RestrictedExpression,
) -> _RestrictedExpressionSnapshot:
    normalized_span = _snapshot_source_span(value.normalized_span)
    source_span = _snapshot_source_span(value.source_span)
    scalar_values: tuple[str | bool, ...]
    children: tuple[_RestrictedExpressionSnapshot, ...]
    if type(value) is NumberNode:
        node_kind = "number"
        scalar_values = (value.lexeme,)
        children = ()
    elif type(value) is SymbolNode:
        node_kind = "symbol"
        scalar_values = (value.name,)
        children = ()
    elif type(value) is ConstantNode:
        node_kind = "constant"
        scalar_values = (value.name,)
        children = ()
    elif type(value) is UnaryOpNode:
        node_kind = "unary"
        scalar_values = (value.operator.value,)
        children = (_snapshot_restricted_expression(value.operand),)
    elif type(value) is BinaryOpNode:
        node_kind = "binary"
        scalar_values = (value.operator.value, value.implicit)
        children = (
            _snapshot_restricted_expression(value.left),
            _snapshot_restricted_expression(value.right),
        )
    elif type(value) is FunctionCallNode:
        node_kind = "function"
        scalar_values = (value.name,)
        children = tuple(
            _snapshot_restricted_expression(argument) for argument in value.arguments
        )
    else:
        raise TypeError("expression must contain exact restricted AST nodes.")
    return _RestrictedExpressionSnapshot(
        node_kind=node_kind,
        normalized_span=normalized_span,
        source_span=source_span,
        scalar_values=scalar_values,
        children=children,
    )


def _validate_cross_plan_contracts(plan: RenderPlan) -> None:
    """Validate the exact Spec/plan/version/memory combination."""

    if type(plan.scene_spec.items) is not tuple or len(plan.scene_spec.items) != 1:
        raise ValueError("approved render plans require one exact scene item.")
    if plan.plan_version != RENDER_PLAN_CONTRACT_VERSION:
        raise ValueError("render plan contract version is not active.")
    if plan.sampling_policy_version is None:
        raise ValueError("approved render plan is missing a sampling policy version.")
    item = plan.scene_spec.items[0]
    item_plan = plan.item_plan
    memory = plan.memory_budget
    if type(item) is ExplicitFunctionSpec:
        if type(item_plan) is not ExplicitRenderItemPlan:
            raise TypeError("explicit Spec requires ExplicitRenderItemPlan.")
        if type(memory) is not RenderMemoryBudget:
            raise TypeError("explicit Spec requires RenderMemoryBudget.")
        if plan.numeric_executor_contract_version != (
            _EXPECTED_NUMERIC_EXECUTOR_CONTRACT_VERSION
        ):
            raise ValueError("explicit plan numeric executor contract version is invalid.")
        if plan.parameterized_sampler_contract_version is not None:
            raise ValueError("explicit plan must not carry a parameterized sampler version.")
        if item.limits_version != plan.limits_version:
            raise ValueError("explicit Spec and plan limits versions do not match.")
    elif type(item) in {LineSpec, CircleSpec, EllipseSpec, HyperbolaSpec, ParabolaSpec}:
        if type(item_plan) is not GeometryRenderItemPlan:
            raise TypeError("geometry Spec requires GeometryRenderItemPlan.")
        if type(memory) is not ParameterizedRenderMemoryBudget:
            raise TypeError("geometry Spec requires ParameterizedRenderMemoryBudget.")
        if plan.numeric_executor_contract_version is not None:
            raise ValueError("geometry plan must not carry a numeric executor version.")
        if plan.parameterized_sampler_contract_version != (
            PARAMETERIZED_SAMPLER_CONTRACT_VERSION
        ):
            raise ValueError("geometry parameterized sampler contract version is invalid.")
        if item.provenance.limits_version != plan.limits_version:
            raise ValueError("geometry Spec and plan limits versions do not match.")
        if type(item) is LineSpec:
            if plan.sampling_policy_version != DEFAULT_LINE_SAMPLING_POLICY.version:
                raise ValueError("line sampling policy version is not active.")
            if item_plan.sample_count != DEFAULT_LINE_SAMPLING_POLICY.sample_count:
                raise ValueError("line sample count is invalid.")
            if item_plan.batch_size != DEFAULT_LINE_SAMPLING_POLICY.batch_size:
                raise ValueError("line batch size is invalid.")
        elif type(item) in {CircleSpec, EllipseSpec}:
            if plan.sampling_policy_version != DEFAULT_ANGULAR_SAMPLING_POLICY.version:
                raise ValueError("angular sampling policy version is not active.")
            _validate_oval_parameter_plan(item_plan)
        elif type(item) is HyperbolaSpec:
            if plan.sampling_policy_version != DEFAULT_HYPERBOLIC_SAMPLING_POLICY.version:
                raise ValueError("hyperbolic sampling policy version is not active.")
            _validate_hyperbola_parameter_plan(item_plan)
        elif type(item) is ParabolaSpec:
            if plan.sampling_policy_version != DEFAULT_PARABOLIC_SAMPLING_POLICY.version:
                raise ValueError("parabolic sampling policy version is not active.")
            _validate_parabola_parameter_plan(item_plan)
        expected_branch_count, expected_capacity, expected_segment_type = (
            _geometry_approval_shape(type(item))
        )
        if item_plan.mathematical_branch_count != expected_branch_count:
            raise ValueError("geometry mathematical branch count is invalid.")
        if item_plan.max_segment_count != expected_capacity:
            raise ValueError("geometry drawable segment capacity is invalid.")
        if any(type(segment) is not expected_segment_type for segment in item_plan.segments):
            raise TypeError("geometry segment type does not match the exact Spec.")
    else:
        raise TypeError("approved scene item exact type is unsupported.")
    if item_plan.item_id != item.item_id:
        raise ValueError("Spec and item plan identities do not match.")


def _geometry_approval_shape(spec_type: type[object]) -> tuple[int, int, type[object]]:
    if spec_type is LineSpec:
        return (1, 1, LineSegmentPlan)
    if spec_type is CircleSpec:
        return (1, 4, ParameterIntervalPlan)
    if spec_type is EllipseSpec:
        return (1, 4, ParameterIntervalPlan)
    if spec_type is HyperbolaSpec:
        return (2, 4, ParameterIntervalPlan)
    if spec_type is ParabolaSpec:
        return (1, 2, ParameterIntervalPlan)
    raise TypeError("geometry Spec exact type is unsupported.")


def _validate_oval_parameter_plan(item_plan: GeometryRenderItemPlan) -> None:
    policy = DEFAULT_ANGULAR_SAMPLING_POLICY
    intervals = item_plan.segments
    if any(type(interval) is not ParameterIntervalPlan for interval in intervals):
        raise TypeError("circle and ellipse plans require exact parameter intervals.")
    typed_intervals = tuple(intervals)
    if any(interval.mathematical_branch_id != 0 for interval in typed_intervals):
        raise ValueError("circle and ellipse intervals require mathematical branch zero.")
    if (
        tuple(sorted(typed_intervals, key=lambda value: value.parameter_start))
        != typed_intervals
    ):
        raise ValueError("circle and ellipse intervals must be stably ordered.")
    if item_plan.batch_size > policy.preferred_batch_points:
        raise ValueError("circle and ellipse batch size exceeds the active policy.")

    closed = tuple(
        interval
        for interval in typed_intervals
        if interval.closure is SegmentClosure.CLOSED
    )
    if closed:
        if len(typed_intervals) != 1 or len(closed) != 1:
            raise ValueError("a closed circle or ellipse plan must contain one interval.")
        interval = closed[0]
        if interval.parameter_start != 0.0 or interval.parameter_stop != tau:
            raise ValueError("a closed circle or ellipse interval must be exactly [0, 2*pi].")
        if interval.sample_count < policy.minimum_closed_curve_samples:
            raise ValueError("closed circle and ellipse sampling is below the active minimum.")
        return

    crossing_interval: ParameterIntervalPlan | None = None
    previous_stop: float | None = None
    for index, interval in enumerate(typed_intervals):
        if interval.closure is not SegmentClosure.OPEN:
            raise ValueError("partial circle and ellipse intervals must be open.")
        if not 0.0 <= interval.parameter_start < tau:
            raise ValueError("open angular interval starts must be normalized to one turn.")
        span = interval.parameter_stop - interval.parameter_start
        if not 0.0 < span < tau:
            raise ValueError("open angular intervals must be shorter than one turn.")
        if previous_stop is not None and interval.parameter_start < previous_stop:
            raise ValueError("open angular intervals must not overlap.")
        if interval.parameter_stop > tau:
            if crossing_interval is not None or index != len(typed_intervals) - 1:
                raise ValueError("only the final visible interval may cross the seam.")
            crossing_interval = interval
            if interval.parameter_stop >= 2.0 * tau:
                raise ValueError("expanded angular intervals must end before two turns.")
        else:
            previous_stop = interval.parameter_stop
        if interval.sample_count < policy.minimum_open_segment_samples:
            raise ValueError("open circle and ellipse sampling is below the active minimum.")
    if (
        crossing_interval is not None
        and len(typed_intervals) > 1
        and crossing_interval.parameter_stop - tau
        > typed_intervals[0].parameter_start
    ):
        raise ValueError("expanded angular interval overlaps the first visible interval.")


def _validate_hyperbola_parameter_plan(item_plan: GeometryRenderItemPlan) -> None:
    policy = DEFAULT_HYPERBOLIC_SAMPLING_POLICY
    intervals = item_plan.segments
    if any(type(interval) is not ParameterIntervalPlan for interval in intervals):
        raise TypeError("hyperbola plans require exact parameter intervals.")
    typed_intervals = tuple(intervals)
    if any(interval.closure is not SegmentClosure.OPEN for interval in typed_intervals):
        raise ValueError("hyperbola intervals must be open.")
    if any(interval.mathematical_branch_id not in {0, 1} for interval in typed_intervals):
        raise ValueError("hyperbola intervals require branch zero or one.")
    if (
        tuple(
            sorted(
                typed_intervals,
                key=lambda value: (
                    value.mathematical_branch_id,
                    value.parameter_start,
                ),
            ),
        )
        != typed_intervals
    ):
        raise ValueError("hyperbola intervals must be stably ordered by branch and start.")
    if item_plan.batch_size > policy.preferred_batch_points:
        raise ValueError("hyperbola batch size exceeds the active policy.")
    for branch_id in (0, 1):
        branch_intervals = tuple(
            interval
            for interval in typed_intervals
            if interval.mathematical_branch_id == branch_id
        )
        if len(branch_intervals) > 2:
            raise ValueError("each hyperbola branch supports at most two intervals.")
        previous_stop: float | None = None
        for interval in branch_intervals:
            if interval.sample_count < policy.minimum_open_segment_samples:
                raise ValueError("hyperbola sampling is below the active minimum.")
            if previous_stop is not None and interval.parameter_start < previous_stop:
                raise ValueError("hyperbola intervals on one branch must not overlap.")
            previous_stop = interval.parameter_stop


def _validate_parabola_parameter_plan(item_plan: GeometryRenderItemPlan) -> None:
    policy = DEFAULT_PARABOLIC_SAMPLING_POLICY
    intervals = item_plan.segments
    if any(type(interval) is not ParameterIntervalPlan for interval in intervals):
        raise TypeError("parabola plans require exact parameter intervals.")
    typed_intervals = tuple(intervals)
    if len(typed_intervals) > 2:
        raise ValueError("a parabola supports at most two visible intervals.")
    if any(interval.closure is not SegmentClosure.OPEN for interval in typed_intervals):
        raise ValueError("parabola intervals must be open.")
    if any(interval.mathematical_branch_id != 0 for interval in typed_intervals):
        raise ValueError("parabola intervals require mathematical branch zero.")
    if (
        tuple(sorted(typed_intervals, key=lambda value: value.parameter_start))
        != typed_intervals
    ):
        raise ValueError("parabola intervals must be stably ordered by start.")
    if item_plan.batch_size > policy.preferred_batch_points:
        raise ValueError("parabola batch size exceeds the active policy.")
    previous_stop: float | None = None
    for interval in typed_intervals:
        if interval.sample_count < policy.minimum_open_segment_samples:
            raise ValueError("parabola sampling is below the active minimum.")
        if previous_stop is not None and interval.parameter_start < previous_stop:
            raise ValueError("parabola intervals must not overlap.")
        previous_stop = interval.parameter_stop


def _validate_geometry_nested(
    item: LineSpec | CircleSpec | EllipseSpec | HyperbolaSpec | ParabolaSpec,
) -> None:
    item.__post_init__()
    if type(item.coefficients) is not PrimitiveEquationCoefficients:
        raise TypeError("geometry coefficients must be exact.")
    item.coefficients.__post_init__()
    provenance = item.provenance
    if type(provenance) is not EquationProvenance:
        raise TypeError("geometry provenance must be exact.")
    provenance.__post_init__()
    provenance.normalized_span.__post_init__()
    provenance.source_span.__post_init__()
    if type(item) is CircleSpec:
        fractions = (item.center_x, item.center_y, item.radius_squared)
    elif type(item) is EllipseSpec:
        fractions = (
            item.center_x,
            item.center_y,
            item.semi_axis_x_squared,
            item.semi_axis_y_squared,
        )
        if type(item.major_axis) is not AxisOrientation:
            raise TypeError("major axis must be exact.")
    elif type(item) is HyperbolaSpec:
        fractions = (
            item.center_x,
            item.center_y,
            item.semi_transverse_squared,
            item.semi_conjugate_squared,
        )
        if type(item.transverse_axis) is not AxisOrientation:
            raise TypeError("transverse axis must be exact.")
    elif type(item) is ParabolaSpec:
        fractions = (item.vertex_x, item.vertex_y, item.focal_parameter)
        if type(item.opening) is not ParabolaOpening:
            raise TypeError("parabola opening must be exact.")
    else:
        fractions = ()
    for value in fractions:
        if type(value) is not Fraction or value.denominator <= 0:
            raise TypeError("geometry fractions must be normalized exact values.")
        if Fraction(value.numerator, value.denominator) != value:
            raise ValueError("geometry fraction semantics are invalid.")


def _validate_nested_approved_contracts(plan: RenderPlan) -> None:
    plan.scene_spec.__post_init__()
    item = plan.scene_spec.items[0]
    if type(item) is ExplicitFunctionSpec:
        item.__post_init__()
    elif type(item) in {LineSpec, CircleSpec, EllipseSpec, HyperbolaSpec, ParabolaSpec}:
        _validate_geometry_nested(item)
    else:
        raise TypeError("scene item exact type is unsupported.")
    plan.resolved_viewport.__post_init__()
    if type(plan.resolved_viewport.aspect) is not ResolvedAspect:
        raise TypeError("resolved aspect must be exact.")
    if type(plan.resolved_viewport.source) is not ViewportSource:
        raise TypeError("viewport source must be exact.")
    assert plan.item_plan is not None
    assert plan.memory_budget is not None
    plan.item_plan.__post_init__()
    plan.memory_budget.__post_init__()


def _approve_render_plan(plan: RenderPlan) -> RenderPlan:
    if type(plan) is not RenderPlan:
        raise TypeError("plan must be an exact RenderPlan.")
    plan.__post_init__()
    _validate_cross_plan_contracts(plan)
    _validate_nested_approved_contracts(plan)
    receipt = _issue_approval_receipt(plan)
    object.__setattr__(plan, "_approval_receipt", receipt)
    return validate_approved_render_plan(plan)


def validate_approved_render_plan(value: object) -> RenderPlan:
    if type(value) is not RenderPlan:
        raise TypeError("render plan must be an exact RenderPlan.")
    try:
        value.__post_init__()
        receipt = value._approval_receipt
        if type(receipt) is not _RenderPlanApprovalReceipt:
            raise TypeError("render plan has no issued approval receipt.")
        if receipt._seal is not _APPROVAL_SEAL:
            raise ValueError("render plan approval receipt is invalid.")
        if value.plan_version != RENDER_PLAN_CONTRACT_VERSION:
            raise ValueError("render plan contract version is not active.")
        if (
            value.item_plan is None
            or value.memory_budget is None
            or value.sampling_policy_version is None
        ):
            raise ValueError("approved render plan is missing budgeted fields.")
        if type(receipt.approved_snapshot) not in {
            _ExplicitRenderPlanApprovalSnapshot,
            _GeometryRenderPlanApprovalSnapshot,
        }:
            raise ValueError("render plan approval receipt is invalid.")
        if receipt.approved_snapshot != _approval_snapshot_from_plan(value):
            raise ValueError("render plan and approval receipt do not match.")
        _validate_cross_plan_contracts(value)
        _validate_nested_approved_contracts(value)
    except MemoryError:
        raise
    except TypeError:
        raise
    except (AttributeError, ValueError) as exc:
        if isinstance(exc, ValueError) and str(exc) in {
            "render plan contract version is not active.",
            "approved render plan is missing budgeted fields.",
            "render plan and approval receipt do not match.",
        }:
            raise
        raise ValueError("render plan approval receipt is invalid.") from exc
    return value


def _snapshot_approved_render_plan(value: object) -> _ApprovedRenderPlanSnapshot:
    return _approval_snapshot_from_plan(validate_approved_render_plan(value))


__all__ = [
    "AngularSamplingPolicy",
    "DEFAULT_ANGULAR_SAMPLING_POLICY",
    "DEFAULT_EXPLICIT_SAMPLING_POLICY",
    "DEFAULT_HYPERBOLIC_SAMPLING_POLICY",
    "DEFAULT_LINE_SAMPLING_POLICY",
    "DEFAULT_PARABOLIC_SAMPLING_POLICY",
    "ExplicitRenderItemPlan",
    "ExplicitSamplingPolicy",
    "GeometryRenderItemPlan",
    "GeometrySegmentPlan",
    "HyperbolicSamplingPolicy",
    "LineSegmentPlan",
    "LineSamplingPolicy",
    "ParabolicSamplingPolicy",
    "PARAMETERIZED_SAMPLER_CONTRACT_VERSION",
    "ParameterIntervalPlan",
    "ParameterizedRenderMemoryBudget",
    "RENDER_PLAN_CONTRACT_VERSION",
    "RenderItemPlan",
    "RenderMemoryBudget",
    "RenderPlan",
    "SegmentClosure",
    "validate_approved_render_plan",
]
