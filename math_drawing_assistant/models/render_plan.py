"""Immutable, budgeted render-plan contracts for stage 8C-1.

The approval receipt is a Python-level capability boundary, not cryptographic
privacy.  Future samplers must validate it before accepting a plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from math_drawing_assistant.models.plot_specs import PlotSceneSpec
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
class _RenderPlanApprovalSnapshot:
    """Complete immutable value snapshot bound into an approval receipt."""

    scene_spec: PlotSceneSpec
    resolved_viewport: ResolvedViewport
    image_width: int
    image_height: int
    dpi: int
    show_grid: bool
    show_legend: bool
    plan_version: str
    limits_version: str
    sampling_policy_version: str | None
    numeric_executor_contract_version: str | None
    item_plan: ExplicitRenderItemPlan | None
    memory_budget: RenderMemoryBudget | None


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

    return _RenderPlanApprovalSnapshot(
        scene_spec=plan.scene_spec,
        resolved_viewport=plan.resolved_viewport,
        image_width=plan.image_width,
        image_height=plan.image_height,
        dpi=plan.dpi,
        show_grid=plan.show_grid,
        show_legend=plan.show_legend,
        plan_version=plan.plan_version,
        limits_version=plan.limits_version,
        sampling_policy_version=plan.sampling_policy_version,
        numeric_executor_contract_version=plan.numeric_executor_contract_version,
        item_plan=plan.item_plan,
        memory_budget=plan.memory_budget,
    )


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
    value.__post_init__()
    receipt = value._approval_receipt
    if type(receipt) is not _RenderPlanApprovalReceipt:
        raise TypeError("render plan has no issued approval receipt.")
    try:
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
    except AttributeError as exc:
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
