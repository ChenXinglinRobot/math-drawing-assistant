"""Immutable viewport intent and resolved viewport snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from math_drawing_assistant.models.state import (
    AspectRequest,
    ViewportMode,
    ViewportSource,
)


def _finite_bound(value: float | None, name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a finite number or None.")

    numeric_value = float(value)
    if not isfinite(numeric_value):
        raise ValueError(f"{name} must be finite.")
    return numeric_value


@dataclass(frozen=True, slots=True)
class ViewportRequest:
    """User intent for a shared scene viewport; it is not a final range."""

    mode: ViewportMode = ViewportMode.AUTO
    x_min: float | None = None
    x_max: float | None = None
    y_min: float | None = None
    y_max: float | None = None
    aspect_request: AspectRequest = AspectRequest.AUTO

    def __post_init__(self) -> None:
        if not isinstance(self.mode, ViewportMode):
            raise TypeError("mode must be a ViewportMode.")
        if not isinstance(self.aspect_request, AspectRequest):
            raise TypeError("aspect_request must be an AspectRequest.")

        for name in ("x_min", "x_max", "y_min", "y_max"):
            object.__setattr__(
                self,
                name,
                _finite_bound(getattr(self, name), name),
            )

        if self.mode is ViewportMode.MANUAL and any(
            bound is None
            for bound in (self.x_min, self.x_max, self.y_min, self.y_max)
        ):
            raise ValueError(
                "Manual viewport requests require x_min, x_max, y_min, and y_max."
            )


@dataclass(frozen=True, slots=True)
class ResolvedViewport:
    """A complete, legal viewport produced by a future resolver."""

    x_min: float
    x_max: float
    y_min: float
    y_max: float
    aspect: AspectRequest
    source: ViewportSource

    def __post_init__(self) -> None:
        if not isinstance(self.aspect, AspectRequest):
            raise TypeError("aspect must be an AspectRequest.")
        if not isinstance(self.source, ViewportSource):
            raise TypeError("source must be a ViewportSource.")

        for name in ("x_min", "x_max", "y_min", "y_max"):
            resolved_bound = _finite_bound(getattr(self, name), name)
            assert resolved_bound is not None
            object.__setattr__(self, name, resolved_bound)

        if self.x_min >= self.x_max:
            raise ValueError("ResolvedViewport.x_min must be smaller than x_max.")
        if self.y_min >= self.y_max:
            raise ValueError("ResolvedViewport.y_min must be smaller than y_max.")
