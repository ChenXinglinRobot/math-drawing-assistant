"""Coordination for immutable scene requests and render results."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum, auto
from typing import Final, Iterable

from math_drawing_assistant.models.errors import ErrorCode, ErrorInfo
from math_drawing_assistant.models.requests import PlotItemRequest, PlotSceneRequest
from math_drawing_assistant.models.results import PlotSceneResult
from math_drawing_assistant.models.state import (
    AspectRequest,
    InputSource,
    PlotKind,
    TaskPhase,
    ViewportMode,
)
from math_drawing_assistant.models.viewport import ViewportRequest
from math_drawing_assistant.workers.cancellation import (
    CancellationToken,
    RenderSubmitter,
)

_RENDER_SUBMISSION_NOTICE = "Unable to start rendering."
_RENDER_SUBMISSION_FAILURE = "The render request could not be submitted."
_RENDER_SHUTDOWN_NOTICE = "Unable to shut down the render service."

M1_DEFAULT_DPI: Final[int] = 96
M1_SINGLE_ITEM_ID: Final[str] = "m1-manual-item"
M1_SHOW_LEGEND: Final[bool] = False
M1_DISPLAY_ORDER: Final[int] = 0


class RenderResultDisposition(Enum):
    """Controller-local decision for one relayed render result."""

    ACCEPTED_SUCCESS = auto()
    HANDLED_CURRENT_FAILURE = auto()
    IGNORED_OBSOLETE = auto()


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

    def create_m1_render_request(
        self,
        *,
        formula_text: str,
        viewport_mode: str,
        x_min: float,
        x_max: float,
        y_min: float,
        y_max: float,
        aspect_request: str,
        show_grid: bool,
        image_width: int,
        image_height: int,
        created_at: datetime | None = None,
    ) -> PlotSceneRequest:
        """Adapt one Qt-free M1 UI snapshot into the formal scene request."""

        mode = ViewportMode(viewport_mode)
        aspect = AspectRequest(aspect_request)
        if mode is ViewportMode.MANUAL:
            viewport = ViewportRequest(
                mode=mode,
                x_min=x_min,
                x_max=x_max,
                y_min=y_min,
                y_max=y_max,
                aspect_request=aspect,
            )
        else:
            # Disabled spin boxes retain display values in auto mode, but those
            # values are not user-requested bounds and must not enter the model.
            viewport = ViewportRequest(
                mode=mode,
                aspect_request=aspect,
            )

        item = PlotItemRequest(
            item_id=M1_SINGLE_ITEM_ID,
            input_text=formula_text,
            input_source=InputSource.MANUAL,
            requested_plot_kind=PlotKind.AUTO,
            display_order=M1_DISPLAY_ORDER,
        )
        return self.create_render_request(
            items=(item,),
            viewport=viewport,
            image_width=image_width,
            image_height=image_height,
            dpi=M1_DEFAULT_DPI,
            show_grid=show_grid,
            show_legend=M1_SHOW_LEGEND,
            created_at=created_at,
        )

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

    def handle_render_result(
        self,
        result: PlotSceneResult,
    ) -> RenderResultDisposition:
        """Classify a result once, keeping stale-result policy out of the UI."""

        if not isinstance(result, PlotSceneResult):
            raise TypeError("result must be a PlotSceneResult.")
        if self.task_phase is TaskPhase.SHUTTING_DOWN:
            return RenderResultDisposition.IGNORED_OBSOLETE
        if result.request_id != self.current_render_request_id:
            return RenderResultDisposition.IGNORED_OBSOLETE

        # This exact request has finished even when an intervening edit made
        # its revision obsolete.  Clear the completed foreground context so a
        # stale result cannot leave the UI permanently stuck in RENDERING.
        self.current_render_request_id = None
        self._current_render_token = None
        self.task_phase = TaskPhase.IDLE

        if result.scene_revision != self.current_scene_revision:
            return RenderResultDisposition.IGNORED_OBSOLETE

        if result.success:
            self.last_successful_result = result
            self.last_result_scene_revision = result.scene_revision
            self.last_error_notice = None
            return RenderResultDisposition.ACCEPTED_SUCCESS

        self.last_error_notice = result.error or ErrorInfo(
            code="render_failed",
            user_message="Unable to generate the plot.",
            recoverable=True,
        )
        return RenderResultDisposition.HANDLED_CURRENT_FAILURE

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
