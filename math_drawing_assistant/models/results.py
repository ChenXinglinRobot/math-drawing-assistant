"""Immutable plot result snapshots without GUI objects or mutable buffers."""

from __future__ import annotations

from dataclasses import dataclass

from math_drawing_assistant.models.diagnostics import StageTiming
from math_drawing_assistant.models.errors import ErrorInfo
from math_drawing_assistant.models.state import PlotKind
from math_drawing_assistant.models.viewport import ResolvedViewport


def _warning_snapshot(warnings: tuple[str, ...]) -> tuple[str, ...]:
    snapshot = tuple(warnings)
    if not all(isinstance(warning, str) for warning in snapshot):
        raise TypeError("warnings must contain strings.")
    return snapshot


def _timing_snapshot(
    timings: tuple[StageTiming, ...],
) -> tuple[StageTiming, ...]:
    snapshot = tuple(timings)
    if not all(isinstance(timing, StageTiming) for timing in snapshot):
        raise TypeError("elapsed_ms must contain StageTiming instances.")
    return snapshot


@dataclass(frozen=True, slots=True)
class PlotItemResult:
    """The stable outcome for one requested item."""

    item_id: str
    success: bool
    normalized_input: str | None = None
    plot_kind: PlotKind | None = None
    style_key: str | None = None
    warnings: tuple[str, ...] = ()
    error: ErrorInfo | None = None

    def __post_init__(self) -> None:
        if not self.item_id:
            raise ValueError("PlotItemResult.item_id must not be empty.")
        if not isinstance(self.success, bool):
            raise TypeError("success must be a bool.")
        if self.normalized_input is not None and not isinstance(
            self.normalized_input,
            str,
        ):
            raise TypeError("normalized_input must be a string or None.")
        if self.plot_kind is not None and not isinstance(self.plot_kind, PlotKind):
            raise TypeError("plot_kind must be a PlotKind or None.")
        if self.error is not None and not isinstance(self.error, ErrorInfo):
            raise TypeError("error must be an ErrorInfo or None.")
        if self.success and self.error is not None:
            raise ValueError("A successful item result cannot contain an error.")
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
        result_snapshot = tuple(self.item_results)
        if not all(isinstance(result, PlotItemResult) for result in result_snapshot):
            raise TypeError("item_results must contain PlotItemResult instances.")
        object.__setattr__(self, "item_results", result_snapshot)
        object.__setattr__(self, "warnings", _warning_snapshot(self.warnings))
        object.__setattr__(self, "elapsed_ms", _timing_snapshot(self.elapsed_ms))
