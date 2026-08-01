"""Focused coordination and render-submission tests for AppController."""

from __future__ import annotations

import inspect
from collections import deque

import pytest

import math_drawing_assistant.app_controller as controller_module
from math_drawing_assistant.app_controller import (
    M1_DEFAULT_DPI,
    M1_DISPLAY_ORDER,
    M1_SHOW_LEGEND,
    M1_SINGLE_ITEM_ID,
    AppController,
    RenderResultDisposition,
)
from math_drawing_assistant.models import (
    ErrorCode,
    ErrorInfo,
    InputSource,
    PlotItemRequest,
    PlotKind,
    PlotSceneRequest,
    PlotSceneResult,
    TaskPhase,
    ViewportRequest,
)
from math_drawing_assistant.workers import CancellationToken


class _FakeRenderSubmitter:
    def __init__(
        self,
        *,
        submit_outcomes: tuple[bool | Exception, ...] = (),
        shutdown_outcomes: tuple[bool | Exception, ...] = (),
    ) -> None:
        self._submit_outcomes = deque(submit_outcomes)
        self._shutdown_outcomes = deque(shutdown_outcomes)
        self.submit_attempts: list[
            tuple[PlotSceneRequest, CancellationToken]
        ] = []
        self.accepted_submissions: list[
            tuple[PlotSceneRequest, CancellationToken]
        ] = []
        self.shutdown_calls = 0

    def submit(
        self,
        request: PlotSceneRequest,
        token: CancellationToken,
    ) -> bool:
        self.submit_attempts.append((request, token))
        outcome = self._submit_outcomes.popleft() if self._submit_outcomes else True
        if isinstance(outcome, Exception):
            raise outcome
        if outcome:
            self.accepted_submissions.append((request, token))
        return outcome

    def shutdown(self) -> bool:
        self.shutdown_calls += 1
        outcome = (
            self._shutdown_outcomes.popleft()
            if self._shutdown_outcomes
            else True
        )
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _item() -> PlotItemRequest:
    return PlotItemRequest(
        item_id="item-1",
        input_text="y=x",
        input_source=InputSource.MANUAL,
        requested_plot_kind=PlotKind.AUTO,
        display_order=0,
    )


def _start_render(controller: AppController):
    return controller.start_render(
        items=[_item()],
        viewport=ViewportRequest(),
        image_width=800,
        image_height=600,
        dpi=96,
        show_grid=True,
        show_legend=True,
    )


def _success_for(request) -> PlotSceneResult:
    return PlotSceneResult(
        request_id=request.request_id,
        scene_revision=request.scene_revision,
        success=True,
        png_bytes=b"png",
    )


def _failure_for(request) -> PlotSceneResult:
    return PlotSceneResult(
        request_id=request.request_id,
        scene_revision=request.scene_revision,
        success=False,
        error=ErrorInfo(code="render_failed", user_message="Rendering failed."),
    )


def test_initial_state_is_idle_without_a_result() -> None:
    controller = AppController()

    assert controller.task_phase is TaskPhase.IDLE
    assert controller.current_scene_revision == 0
    assert controller.current_render_request_id is None
    assert controller._current_render_token is None
    assert controller.last_successful_result is None
    assert controller.last_result_scene_revision is None
    assert controller.last_error_notice is None
    assert controller.has_plot_result is False
    assert controller.copy_enabled is False
    assert controller.result_is_stale is False
    assert controller.is_ready is False


def test_request_ids_are_unique_and_monotonically_increasing() -> None:
    controller = AppController()
    first_request = _start_render(controller)
    controller.handle_render_result(_failure_for(first_request))

    second_request = _start_render(controller)

    assert (first_request.request_id, second_request.request_id) == (1, 2)


def test_every_scene_edit_immediately_increments_revision() -> None:
    controller = AppController()

    assert controller.mark_scene_edited() == 1
    assert controller.mark_scene_edited() == 2
    assert controller.current_scene_revision == 2


def test_created_request_uses_current_revision_and_owns_item_snapshot() -> None:
    controller = AppController()
    controller.mark_scene_edited()
    items = [_item()]

    request = controller.create_render_request(
        items=items,
        viewport=ViewportRequest(),
        image_width=800,
        image_height=600,
        dpi=96,
        show_grid=True,
        show_legend=True,
    )
    items.append(
        PlotItemRequest(
            item_id="item-2",
            input_text="y=x+1",
            input_source=InputSource.MANUAL,
            requested_plot_kind=PlotKind.AUTO,
            display_order=1,
        )
    )

    assert request.scene_revision == 1
    assert len(request.items) == 1
    assert controller.current_render_request_id == request.request_id
    assert controller.task_phase is TaskPhase.RENDERING


def test_m1_manual_adapter_uses_the_controller_defaults_and_four_bounds() -> None:
    controller = AppController()

    request = controller.create_m1_render_request(
        formula_text="y=x^2",
        viewport_mode="manual",
        x_min=-3.0,
        x_max=7.0,
        y_min=-11.0,
        y_max=13.0,
        aspect_request="equal",
        show_grid=False,
        image_width=640,
        image_height=480,
    )

    assert len(request.items) == 1
    item = request.items[0]
    assert item.item_id == M1_SINGLE_ITEM_ID
    assert item.input_text == "y=x^2"
    assert item.input_source is InputSource.MANUAL
    assert item.requested_plot_kind is PlotKind.AUTO
    assert item.display_order == M1_DISPLAY_ORDER
    assert request.dpi == M1_DEFAULT_DPI
    assert request.show_legend is M1_SHOW_LEGEND
    assert request.show_grid is False
    assert request.viewport.mode.value == "manual"
    assert request.viewport.aspect_request.value == "equal"
    assert (
        request.viewport.x_min,
        request.viewport.x_max,
        request.viewport.y_min,
        request.viewport.y_max,
    ) == (-3.0, 7.0, -11.0, 13.0)


def test_m1_auto_adapter_does_not_copy_disabled_display_bounds() -> None:
    controller = AppController()

    request = controller.create_m1_render_request(
        formula_text="sin(x)",
        viewport_mode="auto",
        x_min=float("nan"),
        x_max=float("nan"),
        y_min=float("nan"),
        y_max=float("nan"),
        aspect_request="auto",
        show_grid=True,
        image_width=800,
        image_height=600,
    )

    assert request.viewport.mode.value == "auto"
    assert request.viewport.aspect_request.value == "auto"
    assert request.viewport.x_min is None
    assert request.viewport.x_max is None
    assert request.viewport.y_min is None
    assert request.viewport.y_max is None


def test_first_submission_commits_request_and_token() -> None:
    submitter = _FakeRenderSubmitter()
    controller = AppController(render_submitter=submitter)

    request = _start_render(controller)
    accepted_request, token = submitter.accepted_submissions[0]

    assert accepted_request is request
    assert request.request_id == 1
    assert controller._next_request_id == 2
    assert controller.current_render_request_id == request.request_id
    assert controller._current_render_token is token
    assert token.is_cancelled() is False
    assert controller.task_phase is TaskPhase.RENDERING


def test_successful_supersede_commits_new_context_and_rejects_old_result() -> None:
    submitter = _FakeRenderSubmitter()
    controller = AppController(render_submitter=submitter)
    old_request = _start_render(controller)
    old_token = submitter.accepted_submissions[0][1]
    controller.mark_scene_edited()

    new_request = _start_render(controller)
    new_token = submitter.accepted_submissions[1][1]

    assert new_request.request_id == old_request.request_id + 1
    assert new_request.scene_revision == old_request.scene_revision + 1
    assert controller.current_render_request_id == new_request.request_id
    assert controller._current_render_token is new_token
    assert old_token.is_cancelled() is True
    assert new_token.is_cancelled() is False
    assert controller.handle_render_result(_success_for(old_request)) is (
        RenderResultDisposition.IGNORED_OBSOLETE
    )
    assert controller.current_render_request_id == new_request.request_id
    assert controller._current_render_token is new_token
    assert controller.task_phase is TaskPhase.RENDERING


def test_compatibility_mode_supersede_also_cancels_old_token() -> None:
    controller = AppController()
    _start_render(controller)
    old_token = controller._current_render_token
    assert old_token is not None

    new_request = _start_render(controller)

    assert old_token.is_cancelled() is True
    assert controller.current_render_request_id == new_request.request_id
    assert controller._current_render_token is not old_token
    assert controller._current_render_token is not None
    assert controller._current_render_token.is_cancelled() is False


def test_submit_false_preserves_active_transaction_and_request_id() -> None:
    submitter = _FakeRenderSubmitter(submit_outcomes=(True, False))
    controller = AppController(render_submitter=submitter)
    active_request = _start_render(controller)
    active_token = submitter.accepted_submissions[0][1]
    next_request_id = controller._next_request_id

    with pytest.raises(RuntimeError) as exc_info:
        _start_render(controller)

    assert str(exc_info.value) == "The render request could not be submitted."
    assert controller._next_request_id == next_request_id
    assert controller.current_render_request_id == active_request.request_id
    assert controller._current_render_token is active_token
    assert controller.task_phase is TaskPhase.RENDERING
    assert active_token.is_cancelled() is False
    assert [request.request_id for request, _ in submitter.accepted_submissions] == [1]
    assert submitter.submit_attempts[-1][0].request_id == next_request_id
    assert controller.last_error_notice is not None
    assert controller.last_error_notice.code is ErrorCode.INTERNAL_ERROR
    assert controller.last_error_notice.technical_message is None

    retry_request = _start_render(controller)
    assert retry_request.request_id == next_request_id


def test_submit_exception_preserves_core_state_and_redacts_details() -> None:
    sensitive_detail = r"secret y=x at C:\private\plot.png"
    submitter = _FakeRenderSubmitter(
        submit_outcomes=(True, RuntimeError(sensitive_detail)),
    )
    controller = AppController(render_submitter=submitter)
    active_request = _start_render(controller)
    active_token = submitter.accepted_submissions[0][1]
    next_request_id = controller._next_request_id

    with pytest.raises(RuntimeError) as exc_info:
        _start_render(controller)

    rejected_token = submitter.submit_attempts[-1][1]
    assert str(exc_info.value) == "The render request could not be submitted."
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    assert controller._next_request_id == next_request_id
    assert controller.current_render_request_id == active_request.request_id
    assert controller._current_render_token is active_token
    assert controller.task_phase is TaskPhase.RENDERING
    assert active_token.is_cancelled() is False
    assert rejected_token.is_cancelled() is True
    assert [request.request_id for request, _ in submitter.accepted_submissions] == [1]
    assert controller.last_error_notice is not None
    assert controller.last_error_notice.code is ErrorCode.INTERNAL_ERROR
    assert controller.last_error_notice.recoverable is True
    assert controller.last_error_notice.technical_message is None
    exposed_text = f"{exc_info.value!r} {controller.last_error_notice!r}"
    assert sensitive_detail not in exposed_text
    assert "y=x" not in exposed_text
    assert "private" not in exposed_text


@pytest.mark.parametrize(
    "phase",
    (TaskPhase.CAPTURING, TaskPhase.RECOGNIZING, TaskPhase.REVIEWING),
)
def test_non_rendering_foreground_phases_reject_render(phase: TaskPhase) -> None:
    submitter = _FakeRenderSubmitter()
    controller = AppController(render_submitter=submitter)
    controller.task_phase = phase

    with pytest.raises(RuntimeError, match="already active"):
        _start_render(controller)

    assert controller._next_request_id == 1
    assert controller.current_render_request_id is None
    assert controller._current_render_token is None
    assert controller.task_phase is phase
    assert submitter.submit_attempts == []


def test_matching_success_result_is_accepted_and_marks_controller_ready() -> None:
    controller = AppController()
    request = _start_render(controller)

    assert controller.handle_render_result(_success_for(request)) is (
        RenderResultDisposition.ACCEPTED_SUCCESS
    )
    assert controller.last_successful_result == _success_for(request)
    assert controller.last_result_scene_revision == request.scene_revision
    assert controller.current_render_request_id is None
    assert controller._current_render_token is None
    assert controller.task_phase is TaskPhase.IDLE
    assert controller.is_ready is True


def test_old_request_result_cannot_clear_or_overwrite_newer_task() -> None:
    controller = AppController()
    old_request = _start_render(controller)
    assert controller.cancel_active_task() is True
    new_request = _start_render(controller)

    assert controller.handle_render_result(_success_for(old_request)) is (
        RenderResultDisposition.IGNORED_OBSOLETE
    )
    assert controller.current_render_request_id == new_request.request_id
    assert controller.task_phase is TaskPhase.RENDERING
    assert controller.last_successful_result is None


def test_current_request_with_old_revision_is_silent_and_finishes_task() -> None:
    controller = AppController()
    request = _start_render(controller)
    controller.mark_scene_edited()

    assert controller.handle_render_result(_success_for(request)) is (
        RenderResultDisposition.IGNORED_OBSOLETE
    )
    assert controller.last_successful_result is None
    assert controller.current_render_request_id is None
    assert controller._current_render_token is None
    assert controller.task_phase is TaskPhase.IDLE
    assert controller.last_error_notice is None


def test_failure_preserves_previous_successful_plot_and_records_error() -> None:
    controller = AppController()
    successful_request = _start_render(controller)
    successful_result = _success_for(successful_request)
    controller.handle_render_result(successful_result)

    controller.mark_scene_edited()
    failed_request = _start_render(controller)
    assert controller.handle_render_result(_failure_for(failed_request)) is (
        RenderResultDisposition.HANDLED_CURRENT_FAILURE
    )

    assert controller.last_successful_result is successful_result
    assert controller.last_result_scene_revision == successful_request.scene_revision
    assert controller.last_error_notice is not None
    assert controller.task_phase is TaskPhase.IDLE


def test_cancelling_an_active_task_preserves_previous_successful_plot() -> None:
    controller = AppController()
    successful_request = _start_render(controller)
    successful_result = _success_for(successful_request)
    controller.handle_render_result(successful_result)

    controller.mark_scene_edited()
    _start_render(controller)
    active_token = controller._current_render_token
    assert active_token is not None
    assert controller.cancel_active_task() is True

    assert active_token.is_cancelled() is True
    assert controller.current_render_request_id is None
    assert controller._current_render_token is None
    assert controller.last_successful_result is successful_result
    assert controller.last_result_scene_revision == successful_request.scene_revision
    assert controller.task_phase is TaskPhase.IDLE
    assert controller.cancel_active_task() is False


def test_edit_makes_old_result_stale_but_keeps_copy_enabled() -> None:
    controller = AppController()
    request = _start_render(controller)
    controller.handle_render_result(_success_for(request))

    controller.mark_scene_edited()

    assert controller.has_plot_result is True
    assert controller.copy_enabled is True
    assert controller.result_is_stale is True
    assert controller.is_ready is False


def test_derived_statuses_are_read_only_and_not_duplicated_fields() -> None:
    controller = AppController()

    assert {"ready", "stale", "copy_enabled"}.isdisjoint(controller.__dict__)
    with pytest.raises(AttributeError):
        controller.copy_enabled = True  # type: ignore[misc]


def test_shutdown_invalidates_active_context_and_rejects_new_tasks() -> None:
    controller = AppController()
    request = _start_render(controller)
    active_token = controller._current_render_token
    assert active_token is not None

    assert controller.shutdown() is True

    assert controller.task_phase is TaskPhase.SHUTTING_DOWN
    assert controller.current_render_request_id is None
    assert controller._current_render_token is None
    assert active_token.is_cancelled() is True
    assert controller.handle_render_result(_success_for(request)) is (
        RenderResultDisposition.IGNORED_OBSOLETE
    )
    with pytest.raises(RuntimeError, match="shutting down"):
        _start_render(controller)


def test_shutdown_success_is_repeatable_and_delegated_each_time() -> None:
    submitter = _FakeRenderSubmitter()
    controller = AppController(render_submitter=submitter)
    _start_render(controller)
    active_token = submitter.accepted_submissions[0][1]

    assert controller.shutdown() is True
    assert controller.shutdown() is True

    assert submitter.shutdown_calls == 2
    assert controller.task_phase is TaskPhase.SHUTTING_DOWN
    assert controller.current_render_request_id is None
    assert controller.current_recognition_request_id is None
    assert controller._current_render_token is None
    assert active_token.is_cancelled() is True


def test_shutdown_false_is_redacted_and_retry_can_succeed() -> None:
    sensitive_detail = r"secret shutdown path C:\private\plot.png"
    submitter = _FakeRenderSubmitter(shutdown_outcomes=(False, True))
    submitter.sensitive_detail = sensitive_detail
    controller = AppController(render_submitter=submitter)
    _start_render(controller)
    active_token = submitter.accepted_submissions[0][1]

    assert controller.shutdown() is False

    assert controller.task_phase is TaskPhase.SHUTTING_DOWN
    assert controller.current_render_request_id is None
    assert controller._current_render_token is None
    assert active_token.is_cancelled() is True
    assert controller.last_error_notice is not None
    assert controller.last_error_notice.code is ErrorCode.INTERNAL_ERROR
    assert controller.last_error_notice.recoverable is False
    assert controller.last_error_notice.technical_message is None
    exposed_text = repr(controller.last_error_notice)
    assert sensitive_detail not in exposed_text
    assert "private" not in exposed_text

    assert controller.shutdown() is True
    assert submitter.shutdown_calls == 2


def test_shutdown_exception_is_reported_without_leaking_details() -> None:
    sensitive_detail = r"secret shutdown exception C:\private\plot.png"
    submitter = _FakeRenderSubmitter(
        shutdown_outcomes=(RuntimeError(sensitive_detail),),
    )
    controller = AppController(render_submitter=submitter)

    assert controller.shutdown() is False

    assert controller.last_error_notice is not None
    assert controller.last_error_notice.code is ErrorCode.INTERNAL_ERROR
    assert controller.last_error_notice.recoverable is False
    exposed_text = repr(controller.last_error_notice)
    assert sensitive_detail not in exposed_text
    assert "private" not in exposed_text


def test_app_controller_does_not_depend_on_rendering_or_gui_packages() -> None:
    source = inspect.getsource(controller_module)
    forbidden_terms = (
        "matplotlib",
        "numpy",
        "sympy",
        "PySide6",
        "math_drawing_assistant.ui",
        "QWidget",
        "RenderActor",
        "Worker",
        "QThread",
    )

    assert all(term not in source for term in forbidden_terms)
