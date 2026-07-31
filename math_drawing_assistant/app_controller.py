"""Coordination for immutable scene requests and render results."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from math_drawing_assistant.models.errors import ErrorCode, ErrorInfo
from math_drawing_assistant.models.requests import PlotItemRequest, PlotSceneRequest
from math_drawing_assistant.models.results import PlotSceneResult
from math_drawing_assistant.models.state import TaskPhase
from math_drawing_assistant.models.viewport import ViewportRequest
from math_drawing_assistant.workers.cancellation import (
    CancellationToken,
    RenderSubmitter,
)

_RENDER_SUBMISSION_NOTICE = "Unable to start rendering."
_RENDER_SUBMISSION_FAILURE = "The render request could not be submitted."
_RENDER_SHUTDOWN_NOTICE = "Unable to shut down the render service."


class AppController:
    """Coordinate one foreground task without parsing or rendering anything."""

    def __init__(self, render_submitter: RenderSubmitter | None = None) -> None:
        self._render_submitter = render_submitter
        self._next_request_id = 1
        self._current_render_token: CancellationToken | None = None
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
        """Create, submit, and commit one foreground render request."""

        self._require_render_submission_phase()

        previous_request_id = self.current_render_request_id
        previous_token = self._current_render_token
        previous_phase = self.task_phase
        next_request_id = self._next_request_id
        item_snapshot = tuple(items)
        request = PlotSceneRequest(
            request_id=next_request_id,
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
        token = CancellationToken()

        if self._render_submitter is not None:
            try:
                accepted = self._render_submitter.submit(request, token)
            except Exception:
                token.cancel()
                accepted = False
            if accepted is not True:
                self._restore_render_transaction(
                    request_id=previous_request_id,
                    token=previous_token,
                    phase=previous_phase,
                    next_request_id=next_request_id,
                )
                self._record_render_submission_failure()
                raise RuntimeError(_RENDER_SUBMISSION_FAILURE) from None

        self._next_request_id = next_request_id + 1
        self.current_render_request_id = request.request_id
        self._current_render_token = token
        self.task_phase = TaskPhase.RENDERING
        if previous_token is not None:
            previous_token.cancel()
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
        self._current_render_token = None
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

        if self._current_render_token is not None:
            self._current_render_token.cancel()
        self._current_render_token = None
        self.current_render_request_id = None
        self.current_recognition_request_id = None
        self.task_phase = TaskPhase.IDLE
        return True

    def shutdown(self) -> bool:
        """Invalidate task context and request repeatable orderly shutdown."""

        self.task_phase = TaskPhase.SHUTTING_DOWN
        self.current_render_request_id = None
        self.current_recognition_request_id = None
        if self._current_render_token is not None:
            self._current_render_token.cancel()
        self._current_render_token = None

        if self._render_submitter is None:
            return True

        try:
            stopped = self._render_submitter.shutdown()
        except Exception:
            self._record_render_shutdown_failure()
            return False
        if stopped is not True:
            self._record_render_shutdown_failure()
            return False
        return True

    def _require_render_submission_phase(self) -> None:
        if self.task_phase is TaskPhase.SHUTTING_DOWN:
            raise RuntimeError("The application is shutting down.")
        if self.task_phase not in (TaskPhase.IDLE, TaskPhase.RENDERING):
            raise RuntimeError(
                "A user-visible foreground task is already active.",
            )

    def _restore_render_transaction(
        self,
        *,
        request_id: int | None,
        token: CancellationToken | None,
        phase: TaskPhase,
        next_request_id: int,
    ) -> None:
        self.current_render_request_id = request_id
        self._current_render_token = token
        self.task_phase = phase
        self._next_request_id = next_request_id

    def _record_render_submission_failure(self) -> None:
        self.last_error_notice = ErrorInfo(
            code=ErrorCode.INTERNAL_ERROR,
            user_message=_RENDER_SUBMISSION_NOTICE,
            recoverable=True,
        )

    def _record_render_shutdown_failure(self) -> None:
        self.last_error_notice = ErrorInfo(
            code=ErrorCode.INTERNAL_ERROR,
            user_message=_RENDER_SHUTDOWN_NOTICE,
            recoverable=False,
        )
