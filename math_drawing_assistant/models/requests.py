"""Immutable, typed user-intent request snapshots."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from math_drawing_assistant.models.state import InputSource, PlotKind
from math_drawing_assistant.models.viewport import ViewportRequest


@dataclass(frozen=True, slots=True)
class PlotItemRequest:
    """One ordered user input in a scene request."""

    item_id: str
    input_text: str
    input_source: InputSource
    requested_plot_kind: PlotKind
    display_order: int
    style_key: str | None = None

    def __post_init__(self) -> None:
        if not self.item_id:
            raise ValueError("PlotItemRequest.item_id must not be empty.")
        if not isinstance(self.input_text, str):
            raise TypeError("input_text must be a string.")
        if not isinstance(self.input_source, InputSource):
            raise TypeError("input_source must be an InputSource.")
        if not isinstance(self.requested_plot_kind, PlotKind):
            raise TypeError("requested_plot_kind must be a PlotKind.")
        if isinstance(self.display_order, bool) or not isinstance(
            self.display_order,
            int,
        ):
            raise TypeError("display_order must be an integer.")
        if self.display_order < 0:
            raise ValueError("display_order must not be negative.")
        if self.style_key is not None and not self.style_key:
            raise ValueError("style_key must not be an empty string.")


@dataclass(frozen=True, slots=True)
class PlotSceneRequest:
    """A complete immutable request for a single- or multi-item plot scene."""

    request_id: int
    scene_revision: int
    items: tuple[PlotItemRequest, ...]
    viewport: ViewportRequest
    image_width: int
    image_height: int
    dpi: int
    show_grid: bool
    show_legend: bool
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )

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
        if not isinstance(self.viewport, ViewportRequest):
            raise TypeError("viewport must be a ViewportRequest.")
        if not isinstance(self.created_at, datetime):
            raise TypeError("created_at must be a datetime.")

        item_snapshot = tuple(self.items)
        if not item_snapshot:
            raise ValueError("PlotSceneRequest.items must not be empty.")
        if not all(isinstance(item, PlotItemRequest) for item in item_snapshot):
            raise TypeError("items must contain PlotItemRequest instances.")
        item_ids = tuple(item.item_id for item in item_snapshot)
        if len(set(item_ids)) != len(item_ids):
            raise ValueError("PlotSceneRequest item_id values must be unique.")
        object.__setattr__(self, "items", item_snapshot)

        for name in ("image_width", "image_height", "dpi"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer.")
            if value < 1:
                raise ValueError(f"{name} must be positive.")
        if not isinstance(self.show_grid, bool):
            raise TypeError("show_grid must be a bool.")
        if not isinstance(self.show_legend, bool):
            raise TypeError("show_legend must be a bool.")
