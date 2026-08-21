"""Immutable plot result snapshots without GUI objects or mutable buffers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from math_drawing_assistant.models.diagnostics import (
    PlotItemDiagnostics,
    PlotSceneDiagnostics,
    StageTiming,
)
from math_drawing_assistant.models.errors import ErrorInfo
from math_drawing_assistant.models.plot_specs import (
    CircleSpec,
    EllipseSpec,
    ExplicitFunctionSpec,
    HyperbolaSpec,
    LineSpec,
    ParabolaSpec,
)
from math_drawing_assistant.models.render_plan import (
    ExplicitRenderItemPlan,
    GeometryRenderItemPlan,
)
from math_drawing_assistant.models.state import PlotKind
from math_drawing_assistant.models.viewport import ResolvedViewport


def _warning_snapshot(warnings: tuple[str, ...]) -> tuple[str, ...]:
    snapshot = tuple(warning for warning in warnings)
    if not all(type(warning) is str for warning in snapshot):
        raise TypeError("warnings must contain exact strings.")
    if any(not warning.strip() for warning in snapshot):
        raise ValueError("warnings must not contain empty strings.")
    if len(snapshot) != len(set(snapshot)):
        raise ValueError("warnings must not contain duplicate values.")
    return snapshot


def _timing_snapshot(
    timings: tuple[StageTiming, ...],
) -> tuple[StageTiming, ...]:
    snapshot = tuple(timings)
    if not all(isinstance(timing, StageTiming) for timing in snapshot):
        raise TypeError("elapsed_ms must contain StageTiming instances.")
    return snapshot


class ConcretePlotType(str, Enum):
    """Closed concrete plot identity orthogonal to coarse PlotKind routing."""

    EXPLICIT_FUNCTION = "explicit_function"
    GENERAL_LINE = "general_line"
    CIRCLE = "circle"
    ELLIPSE = "ellipse"
    HYPERBOLA = "hyperbola"
    PARABOLA = "parabola"


_PLOT_TYPE_KIND = {
    ConcretePlotType.EXPLICIT_FUNCTION: PlotKind.EXPLICIT_FUNCTION,
    ConcretePlotType.GENERAL_LINE: PlotKind.LINE_EQUATION,
    ConcretePlotType.CIRCLE: PlotKind.CONIC_EQUATION,
    ConcretePlotType.ELLIPSE: PlotKind.CONIC_EQUATION,
    ConcretePlotType.HYPERBOLA: PlotKind.CONIC_EQUATION,
    ConcretePlotType.PARABOLA: PlotKind.CONIC_EQUATION,
}
_SPEC_CONCRETE_TYPE = {
    ExplicitFunctionSpec: ConcretePlotType.EXPLICIT_FUNCTION,
    LineSpec: ConcretePlotType.GENERAL_LINE,
    CircleSpec: ConcretePlotType.CIRCLE,
    EllipseSpec: ConcretePlotType.ELLIPSE,
    HyperbolaSpec: ConcretePlotType.HYPERBOLA,
    ParabolaSpec: ConcretePlotType.PARABOLA,
}


def _plot_result_metadata_for_spec(
    value: object,
    item_id: str,
) -> tuple[str, PlotKind, ConcretePlotType] | None:
    """Validate and project one exact Spec without exposing a public helper."""

    concrete_plot_type = _SPEC_CONCRETE_TYPE.get(type(value))
    if concrete_plot_type is None:
        return None
    try:
        value.__post_init__()
        if value.item_id != item_id:
            return None
        plot_kind = _PLOT_TYPE_KIND[concrete_plot_type]
        if value.plot_kind is not plot_kind:
            return None
        normalized_input = (
            value.normalized_input
            if concrete_plot_type is ConcretePlotType.EXPLICIT_FUNCTION
            else value.provenance.normalized_input
        )
    except (AttributeError, TypeError, ValueError):
        return None
    return normalized_input, plot_kind, concrete_plot_type


def _item_plan_matches_concrete_type(
    value: object,
    concrete_plot_type: ConcretePlotType,
    item_id: str,
) -> bool:
    """Return whether an exact item plan matches the closed concrete result type."""

    expected_type = (
        ExplicitRenderItemPlan
        if concrete_plot_type is ConcretePlotType.EXPLICIT_FUNCTION
        else GeometryRenderItemPlan
    )
    return type(value) is expected_type and value.item_id == item_id


@dataclass(frozen=True, slots=True)
class PlotItemResult:
    """The stable outcome for one requested item."""

    item_id: str
    success: bool
    normalized_input: str | None = None
    plot_kind: PlotKind | None = None
    concrete_plot_type: ConcretePlotType | None = None
    diagnostics: PlotItemDiagnostics | None = None
    style_key: str | None = None
    warnings: tuple[str, ...] = ()
    error: ErrorInfo | None = None

    def __post_init__(self) -> None:
        if type(self.item_id) is not str or not self.item_id.strip():
            raise ValueError("PlotItemResult.item_id must be a non-empty string.")
        if type(self.success) is not bool:
            raise TypeError("success must be a bool.")
        if self.normalized_input is not None and not isinstance(
            self.normalized_input,
            str,
        ):
            raise TypeError("normalized_input must be a string or None.")
        if self.plot_kind is not None and type(self.plot_kind) is not PlotKind:
            raise TypeError("plot_kind must be a PlotKind or None.")
        if self.concrete_plot_type is not None and type(
            self.concrete_plot_type
        ) is not ConcretePlotType:
            raise TypeError("concrete_plot_type must be a ConcretePlotType or None.")
        if (self.plot_kind is None) != (self.concrete_plot_type is None):
            raise ValueError("plot_kind and concrete_plot_type must be present together.")
        if (
            self.concrete_plot_type is not None
            and _PLOT_TYPE_KIND[self.concrete_plot_type] is not self.plot_kind
        ):
            raise ValueError("plot_kind does not match concrete_plot_type.")
        if self.diagnostics is not None:
            if type(self.diagnostics) is not PlotItemDiagnostics:
                raise TypeError("diagnostics must be PlotItemDiagnostics or None.")
            if self.concrete_plot_type is None:
                raise ValueError("diagnostics require a known concrete plot type.")
        if self.style_key is not None and (
            type(self.style_key) is not str or not self.style_key.strip()
        ):
            raise ValueError("style_key must be a non-empty string or None.")
        if self.error is not None and type(self.error) is not ErrorInfo:
            raise TypeError("error must be an ErrorInfo or None.")
        if self.success and self.error is not None:
            raise ValueError("A successful item result cannot contain an error.")
        if not self.success:
            if self.error is None:
                raise ValueError("A failed item result must contain an error.")
            if self.error.item_id != self.item_id:
                raise ValueError("A failed item error must match the result item_id.")
        object.__setattr__(self, "warnings", _warning_snapshot(self.warnings))


@dataclass(frozen=True, slots=True)
class PlotSceneResult:
    """The atomic outcome for one scene request."""

    request_id: int
    scene_revision: int
    success: bool
    png_bytes: bytes | None = None
    item_results: tuple[PlotItemResult, ...] = ()
    resolved_viewport: ResolvedViewport | None = None
    warnings: tuple[str, ...] = ()
    error: ErrorInfo | None = None
    elapsed_ms: tuple[StageTiming, ...] = ()
    diagnostics: PlotSceneDiagnostics | None = None

    def __post_init__(self) -> None:
        if isinstance(self.request_id, bool) or not isinstance(self.request_id, int):
            raise TypeError("request_id must be an integer.")
        if self.request_id < 1:
            raise ValueError("request_id must be positive.")
        if isinstance(self.scene_revision, bool) or not isinstance(
            self.scene_revision,
            int,
        ):
            raise TypeError("scene_revision must be an integer.")
        if self.scene_revision < 0:
            raise ValueError("scene_revision must not be negative.")
        if not isinstance(self.success, bool):
            raise TypeError("success must be a bool.")
        if self.png_bytes is not None and not isinstance(self.png_bytes, bytes):
            raise TypeError("png_bytes must be bytes or None.")
        if not self.success and self.png_bytes is not None:
            raise ValueError("A failed scene result cannot contain PNG bytes.")
        if self.error is not None and not isinstance(self.error, ErrorInfo):
            raise TypeError("error must be an ErrorInfo or None.")
        if self.success and self.error is not None:
            raise ValueError("A successful scene result cannot contain an error.")
        if self.resolved_viewport is not None and not isinstance(
            self.resolved_viewport,
            ResolvedViewport,
        ):
            raise TypeError(
                "resolved_viewport must be a ResolvedViewport or None.",
            )
        if self.diagnostics is not None:
            if type(self.diagnostics) is not PlotSceneDiagnostics:
                raise TypeError("diagnostics must be PlotSceneDiagnostics or None.")
            if (
                self.png_bytes is not None
                and self.diagnostics.final_png_byte_count != len(self.png_bytes)
            ):
                raise ValueError("PNG bytes must match the diagnostic byte count.")
        result_snapshot = tuple(self.item_results)
        if not all(isinstance(result, PlotItemResult) for result in result_snapshot):
            raise TypeError("item_results must contain PlotItemResult instances.")
        object.__setattr__(self, "item_results", result_snapshot)
        object.__setattr__(self, "warnings", _warning_snapshot(self.warnings))
        object.__setattr__(self, "elapsed_ms", _timing_snapshot(self.elapsed_ms))
