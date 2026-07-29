"""Immutable, budgeted render-plan contracts for stage 8C-1.

The approval receipt is a Python-level capability boundary, not cryptographic
privacy.  Future samplers must validate it before accepting a plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from math_drawing_assistant.models.errors import SourceSpan
from math_drawing_assistant.models.plot_specs import (
    ExplicitFunctionSpec,
    PlotSceneSpec,
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
from math_drawing_assistant.models.viewport import ResolvedViewport


RENDER_PLAN_CONTRACT_VERSION: Final[str] = "render-plan-v1-budgeted-explicit"
_APPROVAL_SEAL = object()


def _positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer.")
    if value < 1:
        raise ValueError(f"{name} must be positive.")
    return value


def _nonempty_version(value: object, name: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{name} must be a non-empty string.")
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
class ExplicitRenderItemPlan:
    """Scalar execution bounds for the one supported explicit-function item."""

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
class RenderMemoryBudget:
    """Named upper-bound components; this is not a Python/NumPy RSS estimate."""

    final_x_bytes: int
    final_y_bytes: int
    validity_mask_bytes: int
    segment_index_range_bytes: int
    executor_extra_batch_bytes: int
    rgba_canvas_bytes: int
    png_buffer_reserve_bytes: int

    def __post_init__(self) -> None:
        for name in (
            "final_x_bytes",
            "final_y_bytes",
            "validity_mask_bytes",
            "segment_index_range_bytes",
            "executor_extra_batch_bytes",
            "rgba_canvas_bytes",
            "png_buffer_reserve_bytes",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer.")
            if value < 0:
                raise ValueError(f"{name} must not be negative.")

    @property
    def fixed_bytes(self) -> int:
        """Return all components that do not vary with a chosen batch size."""

        return (
            self.final_x_bytes
            + self.final_y_bytes
            + self.validity_mask_bytes
            + self.segment_index_range_bytes
            + self.rgba_canvas_bytes
            + self.png_buffer_reserve_bytes
        )

    @property
    def total_bytes(self) -> int:
        """Return the conservative project-buffer upper bound."""

        return self.fixed_bytes + self.executor_extra_batch_bytes


@dataclass(frozen=True, slots=True)
class _SourceSpanSnapshot:
    """Independent source-location values used by approval snapshots."""

    start: int
    end: int


@dataclass(frozen=True, slots=True)
class _RestrictedExpressionSnapshot:
    """Recursive, project-owned AST semantics without retaining AST nodes."""

    node_kind: str
    normalized_span: _SourceSpanSnapshot
    source_span: _SourceSpanSnapshot
    scalar_values: tuple[str | bool, ...]
    children: tuple["_RestrictedExpressionSnapshot", ...]


@dataclass(frozen=True, slots=True)
class _ValidatedExpressionSnapshot:
    """Stable public semantics of one parser-issued validated expression."""

    expression: _RestrictedExpressionSnapshot
    normalized_input: str
    normalized_span: _SourceSpanSnapshot
    source_span: _SourceSpanSnapshot
    source_form: str
    free_variables: tuple[str, ...]
    limits_version: str


@dataclass(frozen=True, slots=True)
class _ExplicitFunctionSpecSnapshot:
    """Exact supported scene-item type, identity, and execution semantics."""

    item_id: str
    validated_expression: _ValidatedExpressionSnapshot


@dataclass(frozen=True, slots=True)
class _ResolvedViewportSnapshot:
    """Independent resolved-viewport output values."""

    x_min: float
    x_max: float
    y_min: float
    y_max: float
    aspect: str
    source: str


@dataclass(frozen=True, slots=True)
class _ExplicitRenderItemPlanSnapshot:
    """Independent scalar execution-plan values."""

    item_id: str
    sample_count: int
    batch_size: int
    max_segment_count: int
    max_live_float64_vectors: int


@dataclass(frozen=True, slots=True)
class _RenderMemoryBudgetSnapshot:
    """Independent values for every named approved memory component."""

    final_x_bytes: int
    final_y_bytes: int
    validity_mask_bytes: int
    segment_index_range_bytes: int
    executor_extra_batch_bytes: int
    rgba_canvas_bytes: int
    png_buffer_reserve_bytes: int


@dataclass(frozen=True, slots=True)
class _RenderPlanApprovalSnapshot:
    """Complete independent value snapshot bound into an approval receipt."""

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
    item_plan: _ExplicitRenderItemPlanSnapshot
    memory_budget: _RenderMemoryBudgetSnapshot


@dataclass(frozen=True, slots=True, init=False)
class _RenderPlanApprovalReceipt:
    """Internal typed receipt issued only after the formal budget succeeds."""

    approved_snapshot: _RenderPlanApprovalSnapshot
    _seal: object = field(repr=False)

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("Render-plan approval receipts are issued internally.")


def _issue_approval_receipt(plan: "RenderPlan") -> _RenderPlanApprovalReceipt:
    if plan.item_plan is None or plan.memory_budget is None:
        raise ValueError("Only complete render plans can receive approval.")
    receipt = object.__new__(_RenderPlanApprovalReceipt)
    for name, value in (
        ("approved_snapshot", _approval_snapshot_from_plan(plan)),
        ("_seal", _APPROVAL_SEAL),
    ):
        object.__setattr__(receipt, name, value)
    return receipt


@dataclass(frozen=True, slots=True)
class RenderPlan:
    """A final render snapshot; ordinary construction creates an unapproved plan."""

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
    item_plan: ExplicitRenderItemPlan | None = None
    memory_budget: RenderMemoryBudget | None = None
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
        ):
            value = getattr(self, name)
            if value is not None:
                _nonempty_version(value, name)
        if self.item_plan is not None and type(self.item_plan) is not ExplicitRenderItemPlan:
            raise TypeError("item_plan must be an ExplicitRenderItemPlan or None.")
        if self.memory_budget is not None and type(self.memory_budget) is not RenderMemoryBudget:
            raise TypeError("memory_budget must be a RenderMemoryBudget or None.")


def _approval_snapshot_from_plan(plan: RenderPlan) -> _RenderPlanApprovalSnapshot:
    """Capture every public plan field that affects execution or output semantics."""

    if type(plan.scene_spec) is not PlotSceneSpec:
        raise TypeError("scene_spec must be an exact PlotSceneSpec.")
    if type(plan.scene_spec.items) is not tuple:
        raise TypeError("scene_spec.items must be a tuple.")
    scene_items = tuple(_snapshot_explicit_spec(item) for item in plan.scene_spec.items)
    viewport = plan.resolved_viewport
    if type(viewport) is not ResolvedViewport:
        raise TypeError("resolved_viewport must be an exact ResolvedViewport.")
    item_plan = plan.item_plan
    if type(item_plan) is not ExplicitRenderItemPlan:
        raise TypeError("item_plan must be an exact ExplicitRenderItemPlan.")
    memory_budget = plan.memory_budget
    if type(memory_budget) is not RenderMemoryBudget:
        raise TypeError("memory_budget must be an exact RenderMemoryBudget.")

    return _RenderPlanApprovalSnapshot(
        scene_items=scene_items,
        resolved_viewport=_ResolvedViewportSnapshot(
            x_min=viewport.x_min,
            x_max=viewport.x_max,
            y_min=viewport.y_min,
            y_max=viewport.y_max,
            aspect=viewport.aspect.value,
            source=viewport.source.value,
        ),
        image_width=plan.image_width,
        image_height=plan.image_height,
        dpi=plan.dpi,
        show_grid=plan.show_grid,
        show_legend=plan.show_legend,
        plan_version=plan.plan_version,
        limits_version=plan.limits_version,
        sampling_policy_version=plan.sampling_policy_version,
        numeric_executor_contract_version=plan.numeric_executor_contract_version,
        item_plan=_ExplicitRenderItemPlanSnapshot(
            item_id=item_plan.item_id,
            sample_count=item_plan.sample_count,
            batch_size=item_plan.batch_size,
            max_segment_count=item_plan.max_segment_count,
            max_live_float64_vectors=item_plan.max_live_float64_vectors,
        ),
        memory_budget=_RenderMemoryBudgetSnapshot(
            final_x_bytes=memory_budget.final_x_bytes,
            final_y_bytes=memory_budget.final_y_bytes,
            validity_mask_bytes=memory_budget.validity_mask_bytes,
            segment_index_range_bytes=memory_budget.segment_index_range_bytes,
            executor_extra_batch_bytes=memory_budget.executor_extra_batch_bytes,
            rgba_canvas_bytes=memory_budget.rgba_canvas_bytes,
            png_buffer_reserve_bytes=memory_budget.png_buffer_reserve_bytes,
        ),
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


def _validate_nested_approved_contracts(plan: RenderPlan) -> None:
    """Recheck nested typed contracts without replacing the issued receipt."""

    plan.scene_spec.__post_init__()
    for item in plan.scene_spec.items:
        if type(item) is not ExplicitFunctionSpec:
            raise TypeError("scene items must be exact ExplicitFunctionSpec values.")
        item.__post_init__()
    plan.resolved_viewport.__post_init__()
    assert plan.item_plan is not None
    assert plan.memory_budget is not None
    plan.item_plan.__post_init__()
    plan.memory_budget.__post_init__()


def _approve_render_plan(plan: RenderPlan) -> RenderPlan:
    """Attach the internal receipt after the builder completed every check."""

    if type(plan) is not RenderPlan:
        raise TypeError("plan must be an exact RenderPlan.")
    receipt = _issue_approval_receipt(plan)
    object.__setattr__(plan, "_approval_receipt", receipt)
    return validate_approved_render_plan(plan)


def validate_approved_render_plan(value: object) -> RenderPlan:
    """Validate the typed approval capability required by future samplers."""

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
            or value.numeric_executor_contract_version is None
        ):
            raise ValueError("approved render plan is missing budgeted fields.")
        if type(receipt.approved_snapshot) is not _RenderPlanApprovalSnapshot:
            raise ValueError("render plan approval receipt is invalid.")
        if receipt.approved_snapshot != _approval_snapshot_from_plan(value):
            raise ValueError("render plan and approval receipt do not match.")
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


__all__ = [
    "DEFAULT_EXPLICIT_SAMPLING_POLICY",
    "ExplicitRenderItemPlan",
    "ExplicitSamplingPolicy",
    "RENDER_PLAN_CONTRACT_VERSION",
    "RenderMemoryBudget",
    "RenderPlan",
    "validate_approved_render_plan",
]
