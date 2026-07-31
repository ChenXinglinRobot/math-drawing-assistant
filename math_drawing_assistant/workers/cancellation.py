"""Qt-independent cooperative cancellation and render submission contracts."""

from __future__ import annotations

from threading import Event
from typing import Protocol

from math_drawing_assistant.models.requests import PlotSceneRequest


class CancellationToken:
    """A thread-safe, idempotent cooperative cancellation flag."""

    def __init__(self) -> None:
        self._event = Event()

    def cancel(self) -> None:
        """Request cancellation."""

        self._event.set()

    def is_cancelled(self) -> bool:
        """Return whether cancellation has been requested."""

        return self._event.is_set()


class RenderSubmitter(Protocol):
    """Submit immutable render work and coordinate orderly shutdown."""

    def submit(
        self,
        request: PlotSceneRequest,
        token: CancellationToken,
    ) -> bool:
        """Accept a request atomically, returning False with no side effects."""

    def shutdown(self) -> bool:
        """Attempt an orderly shutdown; repeated calls are permitted."""
