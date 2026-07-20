"""Immutable render-plan data contract; no plan builder is implemented here."""

from __future__ import annotations

from dataclasses import dataclass

from math_drawing_assistant.models.plot_specs import PlotSceneSpec
from math_drawing_assistant.models.viewport import ResolvedViewport


@dataclass(frozen=True, slots=True)
class RenderPlan:
    """A final render snapshot after validation and viewport resolution."""

    scene_spec: PlotSceneSpec
    resolved_viewport: ResolvedViewport
    image_width: int
    image_height: int
    dpi: int
    plan_version: str
    limits_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.scene_spec, PlotSceneSpec):
            raise TypeError("scene_spec must be a PlotSceneSpec.")
        if not isinstance(self.resolved_viewport, ResolvedViewport):
            raise TypeError("resolved_viewport must be a ResolvedViewport.")
        for name in ("image_width", "image_height", "dpi"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer.")
            if value < 1:
                raise ValueError(f"{name} must be positive.")
        if not self.plan_version:
            raise ValueError("plan_version must not be empty.")
        if not self.limits_version:
            raise ValueError("limits_version must not be empty.")
