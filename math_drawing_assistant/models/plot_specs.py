"""Minimal typed boundary for validated plot specifications."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from math_drawing_assistant.models.state import PlotKind


@runtime_checkable
class PlotItemSpec(Protocol):
    """Contract fulfilled by future validated, immutable item specifications."""

    @property
    def item_id(self) -> str:
        """Return the item identity inherited from its request."""

    @property
    def plot_kind(self) -> PlotKind:
        """Return the classified plot kind."""


@dataclass(frozen=True, slots=True)
class PlotSceneSpec:
    """Validated snapshot of all items in a scene."""

    items: tuple[PlotItemSpec, ...]

    def __post_init__(self) -> None:
        item_snapshot = tuple(self.items)
        if not item_snapshot:
            raise ValueError("PlotSceneSpec.items must not be empty.")
        if not all(isinstance(item, PlotItemSpec) for item in item_snapshot):
            raise TypeError("items must satisfy the PlotItemSpec contract.")

        item_ids = tuple(item.item_id for item in item_snapshot)
        if len(set(item_ids)) != len(item_ids):
            raise ValueError("PlotSceneSpec item_id values must be unique.")
        object.__setattr__(self, "items", item_snapshot)
