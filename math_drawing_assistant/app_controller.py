"""Stage-2 coordination for immutable scene requests and render results."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from math_drawing_assistant.models.errors import ErrorInfo
from math_drawing_assistant.models.requests import PlotItemRequest, PlotSceneRequest
from math_drawing_assistant.models.results import PlotSceneResult
from math_drawing_assistant.models.state import TaskPhase
from math_drawing_assistant.models.viewport import ViewportRequest


class AppController:
    """Coordinate one foreground task without parsing or rendering anything."""

    def __init__(self) -> None:
        self._next_request_id = 1
        self.current_scene_revision = 0
        self.current_render_request_id: int | None = None
        self.current_recognition_request_id: int | None = None
        self.task_phase = TaskPhase.IDLE
        self.last_successful_result: PlotSceneResult | None = None
        self.last_result_scene_revision: int | None = None
        self.last_error_notice: ErrorInfo | None = None

    @property
    def has_plot_result(self) -> bool:
        """Whether a successful scene result is available for preview or copy."""

        return self.last_successful_result is not None

    @property
    def copy_enabled(self) -> bool:
        """Whether the last successful PNG remains eligible for copying."""

        return self.last_successful_result is not None

    @property
    def result_is_stale(self) -> bool:
        """Whether the retained successful result belongs to older scene input."""

        return (
            self.last_successful_result is not None
            and self.last_result_scene_revision != self.current_scene_revision
        )

    @property
    def is_ready(self) -> bool:
        """Whether the current scene has a fresh successful result and is idle."""

        return (
            self.task_phase is TaskPhase.IDLE
            and self.has_plot_result
            and not self.result_is_stale
        )

    def mark_scene_edited(self) -> int:
        """Immediately record any edit that can change a generated result."""

        if self.task_phase is TaskPhase.SHUTTING_DOWN:
            raise RuntimeError("The application is shutting down.")

        self.current_scene_revision += 1
        return self.current_scene_revision

    def create_render_request(
        self,
        *,
        items: Iterable[PlotItemRequest],
        viewport: ViewportRequest,
        image_width: int,
        image_height: int,
        dpi: int,
        show_grid: bool,
        show_legend: bool,
        created_at: datetime | None = None,
    ) -> PlotSceneRequest:
        """Create and register the one permitted foreground render request."""

        self._require_idle_for_new_task()

        item_snapshot = tuple(items)
        request = PlotSceneRequest(
            request_id=self._next_request_id,
            scene_revision=self.current_scene_revision,
            items=item_snapshot,
            viewport=viewport,
            image_width=image_width,
            image_height=image_height,
            dpi=dpi,
            show_grid=show_grid,
            show_legend=show_legend,
            created_at=(
                datetime.now(timezone.utc) if created_at is None else created_at
            ),
        )

        self._next_request_id += 1
        self.current_render_request_id = request.request_id
        self.task_phase = TaskPhase.RENDERING
        return request

    def start_render(
        self,
        *,
        items: Iterable[PlotItemRequest],
        viewport: ViewportRequest,
        image_width: int,
        image_height: int,
        dpi: int,
        show_grid: bool,
        show_legend: bool,
        created_at: datetime | None = None,
    ) -> PlotSceneRequest:
        """Alias the explicit request-creation operation as starting rendering."""

        return self.create_render_request(
            items=items,
            viewport=viewport,
            image_width=image_width,
            image_height=image_height,
            dpi=dpi,
            show_grid=show_grid,
            show_legend=show_legend,
            created_at=created_at,
        )

    def handle_render_result(self, result: PlotSceneResult) -> bool:
        """Accept only a current, fresh successful render result.

        Return True precisely when the result becomes the current successful
        result. A current failed or stale result is handled and returns False;
        an older request is ignored without changing any controller state.
        """

        if not isinstance(result, PlotSceneResult):
            raise TypeError("result must be a PlotSceneResult.")
        if result.request_id != self.current_render_request_id:
            return False

        self.current_render_request_id = None
        self.task_phase = TaskPhase.IDLE

        if result.scene_revision != self.current_scene_revision:
            return False

        if result.success:
            self.last_successful_result = result
            self.last_result_scene_revision = result.scene_revision
            self.last_error_notice = None
            return True

        self.last_error_notice = result.error or ErrorInfo(
            code="render_failed",
            user_message="Unable to generate the plot.",
            recoverable=True,
        )
        return False

    def cancel_active_task(self) -> bool:
        """Invalidate the active foreground context while retaining old results."""

        if self.task_phase in (TaskPhase.IDLE, TaskPhase.SHUTTING_DOWN):
            return False

        self.current_render_request_id = None
        self.current_recognition_request_id = None
        self.task_phase = TaskPhase.IDLE
        return True

    def shutdown(self) -> None:
        """Reject future tasks and invalidate any task context without threading."""

        self.current_render_request_id = None
        self.current_recognition_request_id = None
        self.task_phase = TaskPhase.SHUTTING_DOWN

    def _require_idle_for_new_task(self) -> None:
        if self.task_phase is TaskPhase.SHUTTING_DOWN:
            raise RuntimeError("The application is shutting down.")
        if self.task_phase is not TaskPhase.IDLE:
            raise RuntimeError(
                "A user-visible foreground task is already active.",
            )
