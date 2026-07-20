"""Focused stage-2 behaviour tests for AppController."""

from __future__ import annotations

import inspect

import pytest

import math_drawing_assistant.app_controller as controller_module
from math_drawing_assistant.app_controller import AppController
from math_drawing_assistant.models import (
    ErrorInfo,
    InputSource,
    PlotItemRequest,
    PlotKind,
    PlotSceneResult,
    TaskPhase,
    ViewportRequest,
)


def _item() -> PlotItemRequest:
    return PlotItemRequest(
        item_id="item-1",
        input_text="y=x",
        input_source=InputSource.MANUAL,
        requested_plot_kind=PlotKind.AUTO,
        display_order=0,
    )


def _start_render(controller: AppController):
    return controller.create_render_request(
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


def test_conflicting_foreground_render_is_rejected() -> None:
    controller = AppController()
    _start_render(controller)

    with pytest.raises(RuntimeError, match="already active"):
        _start_render(controller)


def test_matching_success_result_is_accepted_and_marks_controller_ready() -> None:
    controller = AppController()
    request = _start_render(controller)

    assert controller.handle_render_result(_success_for(request)) is True
    assert controller.last_successful_result == _success_for(request)
    assert controller.last_result_scene_revision == request.scene_revision
    assert controller.current_render_request_id is None
    assert controller.task_phase is TaskPhase.IDLE
    assert controller.is_ready is True


def test_old_request_result_cannot_clear_or_overwrite_newer_task() -> None:
    controller = AppController()
    old_request = _start_render(controller)
    assert controller.cancel_active_task() is True
    new_request = _start_render(controller)

    assert controller.handle_render_result(_success_for(old_request)) is False
    assert controller.current_render_request_id == new_request.request_id
    assert controller.task_phase is TaskPhase.RENDERING
    assert controller.last_successful_result is None


def test_current_request_with_old_revision_is_ignored_but_finishes_task() -> None:
    controller = AppController()
    request = _start_render(controller)
    controller.mark_scene_edited()

    assert controller.handle_render_result(_success_for(request)) is False
    assert controller.last_successful_result is None
    assert controller.current_render_request_id is None
    assert controller.task_phase is TaskPhase.IDLE
    assert controller.last_error_notice is None


def test_failure_preserves_previous_successful_plot_and_records_error() -> None:
    controller = AppController()
    successful_request = _start_render(controller)
    successful_result = _success_for(successful_request)
    controller.handle_render_result(successful_result)

    controller.mark_scene_edited()
    failed_request = _start_render(controller)
    assert controller.handle_render_result(_failure_for(failed_request)) is False

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
    assert controller.cancel_active_task() is True

    assert controller.last_successful_result is successful_result
    assert controller.last_result_scene_revision == successful_request.scene_revision
    assert controller.task_phase is TaskPhase.IDLE


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

    controller.shutdown()

    assert controller.task_phase is TaskPhase.SHUTTING_DOWN
    assert controller.current_render_request_id is None
    assert controller.handle_render_result(_success_for(request)) is False
    with pytest.raises(RuntimeError, match="shutting down"):
        _start_render(controller)


def test_app_controller_does_not_depend_on_rendering_or_gui_packages() -> None:
    source = inspect.getsource(controller_module)
    forbidden_terms = (
        "matplotlib",
        "numpy",
        "sympy",
        "QWidget",
        "RenderActor",
        "Worker",
        "QThread",
    )

    assert all(term not in source for term in forbidden_terms)
