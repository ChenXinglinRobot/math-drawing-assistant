"""Stage 11B tests for the formal UI/controller/Actor M1 scene flow."""

from __future__ import annotations

import base64
from collections import deque
from dataclasses import replace
from threading import Event, get_ident

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QImage
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from math_drawing_assistant.app_controller import (
    AppController,
    RenderResultDisposition,
)
from math_drawing_assistant.config import DEFAULT_LIMITS
from math_drawing_assistant.engine import scene_executor as scene_executor_module
from math_drawing_assistant.engine.scene_executor import SceneRenderExecutor
from math_drawing_assistant.models import (
    ErrorCode,
    ErrorInfo,
    PlotKind,
    PlotSceneResult,
    TaskPhase,
)
from math_drawing_assistant.services.clipboard_service import (
    ClipboardService,
    ClipboardWriteResult,
    ClipboardWriteStatus,
)
from math_drawing_assistant.ui.main_window import MainWindow
from math_drawing_assistant.workers import CancellationToken
from math_drawing_assistant.workers.render_actor import RenderActor


PNG_3X2 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAMAAAACCAYAAACddGYaAAAAEUlEQVR4nGP4z8DwH4YZ"
    "kDkAm34L9XKwuTwAAAAASUVORK5CYII="
)


class _Submitter:
    def __init__(self, shutdown_outcomes: tuple[bool, ...] = (True,)) -> None:
        self.submissions: list[tuple[object, CancellationToken]] = []
        self._shutdown_outcomes = deque(shutdown_outcomes)
        self.shutdown_calls = 0

    def submit(self, request: object, token: CancellationToken) -> bool:
        self.submissions.append((request, token))
        return True

    def shutdown(self) -> bool:
        self.shutdown_calls += 1
        if self._shutdown_outcomes:
            return self._shutdown_outcomes.popleft()
        return True


class _FakeClipboard:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.failure = failure
        self.images: list[QImage] = []

    def setImage(self, image: QImage) -> None:
        if self.failure is not None:
            raise self.failure
        self.images.append(image)


def _window_with_submitter(
    qapp: QApplication,
    *,
    shutdown_outcomes: tuple[bool, ...] = (True,),
) -> tuple[MainWindow, AppController, _Submitter]:
    submitter = _Submitter(shutdown_outcomes)
    controller = AppController(render_submitter=submitter)
    window = MainWindow(controller=controller)
    window.show()
    QApplication.processEvents()
    return window, controller, submitter


def _copy_window_with_submitter(
    qapp: QApplication,
    *,
    clipboard_failure: Exception | None = None,
) -> tuple[MainWindow, AppController, _Submitter, _FakeClipboard]:
    submitter = _Submitter()
    controller = AppController(render_submitter=submitter)
    backend = _FakeClipboard(failure=clipboard_failure)
    clipboard_service = ClipboardService(backend)
    window = MainWindow(
        controller=controller,
        clipboard_service=clipboard_service,
    )
    window.show()
    QApplication.processEvents()
    return window, controller, submitter, backend


def _success(request: object, png_bytes: bytes = PNG_3X2) -> PlotSceneResult:
    return PlotSceneResult(
        request_id=request.request_id,
        scene_revision=request.scene_revision,
        success=True,
        png_bytes=png_bytes,
    )


def _failure(request: object, message: str = "本次生成失败。") -> PlotSceneResult:
    return PlotSceneResult(
        request_id=request.request_id,
        scene_revision=request.scene_revision,
        success=False,
        error=ErrorInfo(code="render_failed", user_message=message),
    )


def _wait_for_signal_count(
    signal: object,
    spy: QSignalSpy,
    expected: int,
    *,
    timeout_ms: int = 10_000,
) -> None:
    if spy.count() < expected:
        relay_loop = QEventLoop()

        def finish_wait(*args: object) -> None:
            relay_loop.quit()

        signal.connect(finish_wait)  # type: ignore[attr-defined]
        try:
            QTimer.singleShot(timeout_ms, relay_loop.quit)
            relay_loop.exec()
        finally:
            signal.disconnect(finish_wait)  # type: ignore[attr-defined]
    QApplication.processEvents()
    assert spy.count() == expected


def test_every_result_relevant_widget_change_immediately_marks_revision(
    qapp: QApplication,
) -> None:
    window, controller, _ = _window_with_submitter(qapp)
    try:
        edits = (
            lambda: window.formula_panel.set_text("x"),
            lambda: window.viewport_panel.set_viewport_mode("manual"),
            lambda: window.viewport_panel.set_x_min(-9.0),
            lambda: window.viewport_panel.set_x_max(9.0),
            lambda: window.viewport_panel.set_y_min(-8.0),
            lambda: window.viewport_panel.set_y_max(8.0),
            lambda: window.viewport_panel.set_aspect_mode("equal"),
            lambda: window.viewport_panel.set_show_grid(False),
            lambda: window.viewport_panel.set_image_width(900),
            lambda: window.viewport_panel.set_image_height(700),
            window.formula_panel.clear,
        )
        for edit in edits:
            previous = controller.current_scene_revision
            edit()
            assert controller.current_scene_revision == previous + 1
    finally:
        window.close()
        window.deleteLater()
        QApplication.processEvents()


def test_generate_reads_one_manual_snapshot_and_rendering_can_supersede(
    qapp: QApplication,
) -> None:
    window, controller, submitter = _window_with_submitter(qapp)
    try:
        window.formula_panel.set_text("y=x^2")
        window.viewport_panel.set_viewport_mode("manual")
        window.viewport_panel.set_x_min(-3)
        window.viewport_panel.set_x_max(7)
        window.viewport_panel.set_y_min(-11)
        window.viewport_panel.set_y_max(13)
        window.viewport_panel.set_aspect_mode("equal")
        window.viewport_panel.set_show_grid(False)
        window.viewport_panel.set_image_width(640)
        window.viewport_panel.set_image_height(480)

        window.generate_button.click()
        first_request, first_token = submitter.submissions[0]

        assert first_request.scene_revision == controller.current_scene_revision
        assert first_request.items[0].input_text == "y=x^2"
        assert first_request.viewport.mode.value == "manual"
        assert (
            first_request.viewport.x_min,
            first_request.viewport.x_max,
            first_request.viewport.y_min,
            first_request.viewport.y_max,
        ) == (-3.0, 7.0, -11.0, 13.0)
        assert first_request.viewport.aspect_request.value == "equal"
        assert first_request.show_grid is False
        assert (first_request.image_width, first_request.image_height) == (640, 480)
        assert controller.task_phase is TaskPhase.RENDERING
        assert window.generate_button.isEnabled() is True

        window.formula_panel.set_text("y=x^3")
        window.generate_button.click()
        second_request, second_token = submitter.submissions[1]

        assert second_request.request_id == first_request.request_id + 1
        assert second_request.items[0].input_text == "y=x^3"
        assert first_token.is_cancelled() is True
        assert second_token.is_cancelled() is False
        assert controller.current_render_request_id == second_request.request_id
    finally:
        window.close()
        window.deleteLater()
        QApplication.processEvents()


def test_success_stale_failure_and_obsolete_ui_behavior(qapp: QApplication) -> None:
    window, controller, submitter = _window_with_submitter(qapp)
    try:
        window.formula_panel.set_text("x")
        window.generate_button.click()
        request = submitter.submissions[0][0]

        assert window.handle_render_result(_success(request)) is (
            RenderResultDisposition.ACCEPTED_SUCCESS
        )
        assert window.plot_preview.source_image is not None
        retained_image = window.plot_preview.source_image
        assert window.copy_button.isEnabled() is True
        assert window.status_panel.status_text() == "图像生成成功。"

        window.formula_panel.set_text("x+1")
        assert controller.result_is_stale is True
        assert window.plot_preview._stale_label.isVisible() is True
        stale_status = window.status_panel.status_text()

        obsolete = PlotSceneResult(
            request_id=request.request_id,
            scene_revision=request.scene_revision,
            success=False,
            error=ErrorInfo(
                code="render_failed",
                user_message="不应显示的旧错误。",
            ),
        )
        assert window.handle_render_result(obsolete) is (
            RenderResultDisposition.IGNORED_OBSOLETE
        )
        assert window.status_panel.status_text() == stale_status
        assert window.plot_preview.source_image == retained_image

        window.generate_button.click()
        current_request = submitter.submissions[-1][0]
        assert window.handle_render_result(_failure(current_request)) is (
            RenderResultDisposition.HANDLED_CURRENT_FAILURE
        )
        assert window.status_panel.status_text() == "本次生成失败。"
        assert window.plot_preview.source_image == retained_image
        assert window.plot_preview._stale_label.isVisible() is True
        assert window.copy_button.isEnabled() is True
    finally:
        window.close()
        window.deleteLater()
        QApplication.processEvents()


def test_one_copy_click_writes_once_and_feedback_restores_fresh_state(
    qapp: QApplication,
) -> None:
    window, controller, submitter, backend = _copy_window_with_submitter(qapp)
    try:
        window.formula_panel.set_text("x")
        window.generate_button.click()
        request = submitter.submissions[0][0]
        window.handle_render_result(_success(request))

        window.copy_button.click()

        assert len(backend.images) == 1
        assert window.status_panel.status_text() == "图片已写入剪贴板"
        assert window._copy_feedback_timer.isSingleShot() is True
        assert window._copy_feedback_timer.isActive() is True
        window._copy_feedback_timer.timeout.emit()
        assert window.status_panel.status_text() == "图像生成成功。"
        assert controller.is_ready is True
    finally:
        window.close()
        window.deleteLater()
        QApplication.processEvents()


def test_stale_rendering_and_failed_current_copy_the_retained_old_plot(
    qapp: QApplication,
) -> None:
    window, controller, submitter, backend = _copy_window_with_submitter(qapp)
    try:
        window.formula_panel.set_text("x")
        window.generate_button.click()
        old_request = submitter.submissions[0][0]
        old_result = _success(old_request)
        window.handle_render_result(old_result)

        window.formula_panel.set_text("x+1")
        window.copy_button.click()
        assert len(backend.images) == 1
        assert window.status_panel.status_text() == (
            "已复制上一张图；当前输入已修改"
        )

        window.generate_button.click()
        current_request = submitter.submissions[-1][0]
        window.copy_button.click()
        assert len(backend.images) == 2
        assert window.status_panel.status_text() == (
            "已复制上一张图；新图仍在生成"
        )

        window.handle_render_result(_failure(current_request))
        assert controller.last_successful_result is old_result
        window.copy_button.click()
        assert len(backend.images) == 3
        assert window.status_panel.status_text() == (
            "已复制上一张图；当前输入已修改"
        )
        assert window.plot_preview.source_image is not None
    finally:
        window.close()
        window.deleteLater()
        QApplication.processEvents()


def test_no_result_and_shutdown_reject_copy_without_backend_write(
    qapp: QApplication,
) -> None:
    window, controller, _, backend = _copy_window_with_submitter(qapp)
    try:
        window._handle_copy_requested()
        assert backend.images == []
        assert window.status_panel.status_text() == "暂无可复制图片"

        assert controller.shutdown() is True
        window._handle_copy_requested()
        assert backend.images == []
        assert window.status_panel.status_text() == "正在关闭…"
        assert window._copy_feedback_timer.isActive() is False
    finally:
        window.close()
        window.deleteLater()
        QApplication.processEvents()


def test_copy_exception_preserves_preview_and_all_controller_state(
    qapp: QApplication,
) -> None:
    window, controller, submitter, backend = _copy_window_with_submitter(
        qapp,
        clipboard_failure=RuntimeError("clipboard unavailable"),
    )
    try:
        window.formula_panel.set_text("x")
        window.generate_button.click()
        request = submitter.submissions[0][0]
        result = _success(request)
        window.handle_render_result(result)
        window.formula_panel.set_text("x+1")
        retained_image = window.plot_preview.source_image
        state_before = (
            controller.current_scene_revision,
            controller.task_phase,
            controller.result_is_stale,
            controller.is_ready,
            controller.last_successful_result,
            controller.last_result_scene_revision,
        )

        window.copy_button.click()

        assert backend.images == []
        assert window.status_panel.status_text() == "无法写入剪贴板，请重试"
        assert window.plot_preview.source_image == retained_image
        assert (
            controller.current_scene_revision,
            controller.task_phase,
            controller.result_is_stale,
            controller.is_ready,
            controller.last_successful_result,
            controller.last_result_scene_revision,
        ) == state_before
    finally:
        window.close()
        window.deleteLater()
        QApplication.processEvents()


def test_invalid_image_copy_feedback_does_not_remove_preview(
    qapp: QApplication,
) -> None:
    class _InvalidClipboardService:
        def __init__(self) -> None:
            self.calls = 0

        def write_candidate(self, candidate: object) -> ClipboardWriteResult:
            self.calls += 1
            return ClipboardWriteResult(ClipboardWriteStatus.INVALID_IMAGE)

    submitter = _Submitter()
    controller = AppController(render_submitter=submitter)
    service = _InvalidClipboardService()
    window = MainWindow(  # type: ignore[arg-type]
        controller=controller,
        clipboard_service=service,
    )
    window.show()
    QApplication.processEvents()
    try:
        window.formula_panel.set_text("x")
        window.generate_button.click()
        request = submitter.submissions[0][0]
        window.handle_render_result(_success(request))
        retained_image = window.plot_preview.source_image

        window.copy_button.click()

        assert service.calls == 1
        assert window.status_panel.status_text() == "图片数据无效，复制失败"
        assert window.plot_preview.source_image == retained_image
        assert controller.last_successful_result is not None
    finally:
        window.close()
        window.deleteLater()
        QApplication.processEvents()


def test_copy_feedback_is_replaced_cancelled_by_new_result_and_never_reopens_shutdown(
    qapp: QApplication,
) -> None:
    window, controller, submitter, backend = _copy_window_with_submitter(qapp)
    window.formula_panel.set_text("x")
    window.generate_button.click()
    first_request = submitter.submissions[0][0]
    window.handle_render_result(_success(first_request))

    window.copy_button.click()
    assert window._copy_feedback_timer.isActive() is True
    window.formula_panel.set_text("x+1")
    assert window._copy_feedback_timer.isActive() is False

    window.copy_button.click()
    assert len(backend.images) == 2
    assert window.status_panel.status_text() == "已复制上一张图；当前输入已修改"
    assert window._copy_feedback_timer.isActive() is True

    window.generate_button.click()
    second_request = submitter.submissions[-1][0]
    window.copy_button.click()
    assert window.status_panel.status_text() == "已复制上一张图；新图仍在生成"
    assert window._copy_feedback_timer.isActive() is True

    window.handle_render_result(_success(second_request))
    assert window._copy_feedback_timer.isActive() is False
    assert window.status_panel.status_text() == "图像生成成功。"

    window.copy_button.click()
    assert window._copy_feedback_timer.isActive() is True
    assert window.close() is True
    assert controller.task_phase is TaskPhase.SHUTTING_DOWN
    assert window._copy_feedback_timer.isActive() is False
    status_after_shutdown = window.status_panel.status_text()
    window._copy_feedback_timer.timeout.emit()
    assert window.status_panel.status_text() == status_after_shutdown
    assert window.copy_button.isEnabled() is False
    window.deleteLater()
    QApplication.processEvents()


class _RecordingSceneExecutor:
    def __init__(self) -> None:
        self.delegate = SceneRenderExecutor()
        self.thread_ids: list[int] = []
        self.entered = Event()
        self.finished = Event()
        self.results: list[PlotSceneResult] = []
        self.cancelled_after: list[bool] = []

    def execute(self, request: object, cancellation: CancellationToken):
        self.thread_ids.append(get_ident())
        self.entered.set()
        try:
            result = self.delegate.execute(request, cancellation)
            self.results.append(result)
            self.cancelled_after.append(cancellation.is_cancelled())
            return result
        finally:
            self.finished.set()


def test_real_scene_executor_runs_in_actor_and_preview_updates_on_gui_thread(
    qapp: QApplication,
    monkeypatch,
) -> None:
    gui_thread_id = get_ident()
    renderer_thread_ids: list[int] = []
    real_renderer = scene_executor_module.render_sampled_curve_png

    def record_renderer_thread(*args: object, **kwargs: object):
        renderer_thread_ids.append(get_ident())
        return real_renderer(*args, **kwargs)

    monkeypatch.setattr(
        scene_executor_module,
        "render_sampled_curve_png",
        record_renderer_thread,
    )
    executor = _RecordingSceneExecutor()
    actor = RenderActor(executor)
    controller = AppController(render_submitter=actor)
    window = MainWindow(controller=controller)
    preview_thread_ids: list[int] = []
    original_set_png_bytes = window.plot_preview.set_png_bytes

    def record_preview(data: bytes) -> None:
        preview_thread_ids.append(get_ident())
        original_set_png_bytes(data)

    window.plot_preview.set_png_bytes = record_preview  # type: ignore[method-assign]
    actor.result_ready.connect(window.handle_render_result)
    results = QSignalSpy(actor.result_ready)
    started = QSignalSpy(actor._thread.started)
    actor.start()
    assert started.count() >= 1 or started.wait(3_000) is True
    window.show()
    QApplication.processEvents()
    try:
        window.formula_panel.set_text("y=x^2")
        window.generate_button.click()
        assert controller.task_phase is TaskPhase.RENDERING
        assert executor.entered.wait(3) is True
        assert executor.finished.wait(10) is True
        assert executor.cancelled_after == [False]
        assert executor.results[0].success is True
        if results.count() == 0:
            relay_loop = QEventLoop()
            actor.result_ready.connect(relay_loop.quit)
            QTimer.singleShot(3_000, relay_loop.quit)
            relay_loop.exec()
        assert results.count() == 1
        QApplication.processEvents()

        assert len(executor.thread_ids) == 1
        assert executor.thread_ids[0] != gui_thread_id
        assert renderer_thread_ids == executor.thread_ids
        assert preview_thread_ids == [gui_thread_id]
        assert window.plot_preview.source_image is not None
        assert controller.is_ready is True
    finally:
        assert window.close() is True
        assert actor.is_running is False
        window.deleteLater()
        QApplication.processEvents()


def test_formal_production_chain_accepts_declared_m1_formulas(
    qapp: QApplication,
) -> None:
    cases = (
        ("y=x²", "y=x^2"),
        ("y=x^2", "y=x^2"),
        ("y=x**2", "y=x^2"),
        ("y=sin(x)", "y=sin(x)"),
        ("y=1/x", "y=1/x"),
        ("y=sqrt(x)", "y=sqrt(x)"),
        ("y=2", "y=2"),
        ("y=|x|", "y=|x|"),
        ("y=ln(x)", "y=ln(x)"),
        ("y=lg(x)", "y=lg(x)"),
        ("y=log(x,10)", "y=log(x,10)"),
        ("y=tan(x)", "y=tan(x)"),
    )
    executor = _RecordingSceneExecutor()
    actor = RenderActor(executor)
    controller = AppController(render_submitter=actor)
    window = MainWindow(controller=controller)
    actor.result_ready.connect(window.handle_render_result)
    results = QSignalSpy(actor.result_ready)
    started = QSignalSpy(actor._thread.started)
    actor.start()
    assert started.count() >= 1 or started.wait(3_000) is True
    window.viewport_panel.set_image_width(400)
    window.viewport_panel.set_image_height(300)
    window.show()
    QApplication.processEvents()
    try:
        for index, (formula, normalized) in enumerate(cases, start=1):
            window.formula_panel.set_text(formula)
            expected_revision = controller.current_scene_revision
            window.generate_button.click()
            _wait_for_signal_count(actor.result_ready, results, index)

            delivered = results.at(index - 1)[0]
            assert delivered.success is True
            assert delivered.scene_revision == expected_revision
            assert delivered.scene_revision == controller.current_scene_revision
            assert delivered.error is None
            assert delivered.png_bytes is not None
            assert len(delivered.item_results) == 1
            item_result = delivered.item_results[0]
            assert item_result.success is True
            assert item_result.normalized_input == normalized
            assert item_result.plot_kind is PlotKind.EXPLICIT_FUNCTION
            assert controller.last_successful_result is delivered
            assert controller.is_ready is True
            assert window.plot_preview.source_image is not None
            assert window.plot_preview.source_image.width() == 400
            assert window.plot_preview.source_image.height() == 300
            assert window.plot_preview._stale_label.isVisible() is False

        assert len(executor.thread_ids) == len(cases)
        assert len(set(executor.thread_ids)) == 1
        assert executor.thread_ids[0] != get_ident()
    finally:
        assert window.close() is True
        assert actor.is_running is False
        window.deleteLater()
        QApplication.processEvents()


def test_formal_failures_preserve_input_previous_preview_and_copy_state(
    qapp: QApplication,
) -> None:
    cases = (
        ("", ErrorCode.EMPTY_INPUT),
        ("x@", ErrorCode.UNKNOWN_CHARACTER),
        ("x+", ErrorCode.ILLEGAL_TRAILING),
        ("log(x)", ErrorCode.LOG_REQUIRES_BASE),
        ("x*y=0", ErrorCode.ROTATED_CONIC_NOT_SUPPORTED),
    )
    executor = _RecordingSceneExecutor()
    actor = RenderActor(executor)
    controller = AppController(render_submitter=actor)
    window = MainWindow(controller=controller)
    actor.result_ready.connect(window.handle_render_result)
    results = QSignalSpy(actor.result_ready)
    started = QSignalSpy(actor._thread.started)
    actor.start()
    assert started.count() >= 1 or started.wait(3_000) is True
    window.viewport_panel.set_image_width(400)
    window.viewport_panel.set_image_height(300)
    window.show()
    QApplication.processEvents()
    try:
        window.formula_panel.set_text("y=x^2")
        window.generate_button.click()
        _wait_for_signal_count(actor.result_ready, results, 1)
        baseline = results.at(0)[0]
        assert baseline.success is True
        retained_image = window.plot_preview.source_image
        assert retained_image is not None

        for offset, (formula, error_code) in enumerate(cases, start=2):
            window.formula_panel.set_text(formula)
            window.generate_button.click()
            _wait_for_signal_count(actor.result_ready, results, offset)

            delivered = results.at(offset - 1)[0]
            assert delivered.success is False
            assert delivered.png_bytes is None
            assert delivered.error is not None
            assert delivered.error.code is error_code
            assert delivered.error.item_id == "m1-manual-item"
            assert controller.task_phase is TaskPhase.IDLE
            assert controller.last_successful_result is baseline
            assert window.formula_panel.text() == formula
            assert window.plot_preview.source_image == retained_image
            assert window.plot_preview._stale_label.isVisible() is True
            assert window.copy_button.isEnabled() is True

        executor.delegate = SceneRenderExecutor(
            limits=replace(DEFAULT_LIMITS, max_estimated_memory_bytes=1),
        )
        window.formula_panel.set_text("y=x^3")
        window.generate_button.click()
        _wait_for_signal_count(actor.result_ready, results, len(cases) + 2)
        resource_failure = results.at(len(cases) + 1)[0]
        assert resource_failure.success is False
        assert resource_failure.error is not None
        assert resource_failure.error.code is ErrorCode.RESOURCE_LIMIT_EXCEEDED
        assert controller.last_successful_result is baseline
        assert window.formula_panel.text() == "y=x^3"
        assert window.plot_preview.source_image == retained_image
        assert window.copy_button.isEnabled() is True
    finally:
        assert window.close() is True
        assert actor.is_running is False
        window.deleteLater()
        QApplication.processEvents()


def test_invalid_manual_bounds_become_a_safe_current_failure(
    qapp: QApplication,
) -> None:
    actor = RenderActor(SceneRenderExecutor())
    controller = AppController(render_submitter=actor)
    window = MainWindow(controller=controller)
    actor.result_ready.connect(window.handle_render_result)
    results = QSignalSpy(actor.result_ready)
    started = QSignalSpy(actor._thread.started)
    actor.start()
    assert started.count() >= 1 or started.wait(3_000) is True
    window.show()
    QApplication.processEvents()
    try:
        window.formula_panel.set_text("x")
        window.viewport_panel.set_viewport_mode("manual")
        window.viewport_panel.set_x_min(5)
        window.viewport_panel.set_x_max(1)
        window.generate_button.click()

        if results.count() == 0:
            relay_loop = QEventLoop()
            actor.result_ready.connect(relay_loop.quit)
            QTimer.singleShot(10_000, relay_loop.quit)
            relay_loop.exec()
        QApplication.processEvents()

        assert results.count() == 1
        assert controller.task_phase is TaskPhase.IDLE
        assert controller.last_error_notice is not None
        assert controller.last_error_notice.code.value == "invalid_viewport"
        assert window.status_panel.status_text() == (
            controller.last_error_notice.user_message
        )
        assert window.plot_preview.source_image is None
    finally:
        assert window.close() is True
        assert actor.is_running is False
        window.deleteLater()
        QApplication.processEvents()


class _BlockingLatestExecutor:
    def __init__(self) -> None:
        self.first_entered = Event()
        self.release_first = Event()
        self.entered_ids: list[int] = []

    def execute(self, request: object, cancellation: CancellationToken):
        self.entered_ids.append(request.request_id)
        if len(self.entered_ids) == 1:
            self.first_entered.set()
            assert self.release_first.wait(10) is True
        return _success(request)


def test_same_request_obsoleted_by_edit_finishes_without_updating_preview(
    qapp: QApplication,
) -> None:
    executor = _BlockingLatestExecutor()
    actor = RenderActor(executor)
    controller = AppController(render_submitter=actor)
    window = MainWindow(controller=controller)
    actor.result_ready.connect(window.handle_render_result)
    results = QSignalSpy(actor.result_ready)
    started = QSignalSpy(actor._thread.started)
    actor.start()
    assert started.count() >= 1 or started.wait(3_000) is True
    window.show()
    QApplication.processEvents()
    try:
        window.formula_panel.set_text("x")
        window.generate_button.click()
        request_id = controller.current_render_request_id
        request_revision = controller.current_scene_revision
        assert executor.first_entered.wait(3) is True

        window.formula_panel.set_text("x+1")
        assert controller.current_scene_revision == request_revision + 1
        executor.release_first.set()
        _wait_for_signal_count(actor.result_ready, results, 1)

        delivered = results.at(0)[0]
        assert delivered.request_id == request_id
        assert delivered.scene_revision == request_revision
        assert delivered.success is True
        assert controller.current_render_request_id is None
        assert controller.task_phase is TaskPhase.IDLE
        assert controller.last_successful_result is None
        assert controller.last_error_notice is None
        assert window.plot_preview.source_image is None
        assert window.status_panel.status_text() == "就绪"
    finally:
        assert window.close() is True
        assert actor.is_running is False
        window.deleteLater()
        QApplication.processEvents()


def test_real_actor_latest_wins_only_displays_the_last_explicit_request(
    qapp: QApplication,
) -> None:
    executor = _BlockingLatestExecutor()
    actor = RenderActor(executor)
    controller = AppController(render_submitter=actor)
    window = MainWindow(controller=controller)
    actor.result_ready.connect(window.handle_render_result)
    results = QSignalSpy(actor.result_ready)
    started = QSignalSpy(actor._thread.started)
    actor.start()
    assert started.count() >= 1 or started.wait(3_000) is True
    window.show()
    QApplication.processEvents()
    try:
        window.formula_panel.set_text("x")
        window.generate_button.click()
        first_id = controller.current_render_request_id
        assert executor.first_entered.wait(3) is True

        heartbeat_thread_ids: list[int] = []
        heartbeat_loop = QEventLoop()

        def record_heartbeat() -> None:
            heartbeat_thread_ids.append(get_ident())
            heartbeat_loop.quit()

        QTimer.singleShot(0, record_heartbeat)
        QTimer.singleShot(3_000, heartbeat_loop.quit)
        heartbeat_loop.exec()
        assert heartbeat_thread_ids == [get_ident()]

        window.formula_panel.set_text("x+1")
        window.generate_button.click()
        second_id = controller.current_render_request_id
        window.formula_panel.set_text("x+2")
        window.generate_button.click()
        third_id = controller.current_render_request_id
        assert first_id is not None
        assert second_id == first_id + 1
        assert third_id == second_id + 1

        relay_loop = QEventLoop()
        actor.result_ready.connect(relay_loop.quit)
        QTimer.singleShot(10_000, relay_loop.quit)
        executor.release_first.set()
        relay_loop.exec()
        QApplication.processEvents()

        assert results.count() == 1
        delivered = results.at(0)[0]
        assert delivered.request_id == third_id
        assert executor.entered_ids == [first_id, third_id]
        assert controller.last_successful_result is delivered
        assert window.plot_preview.source_image is not None
    finally:
        assert window.close() is True
        assert actor.is_running is False
        window.deleteLater()
        QApplication.processEvents()


def test_close_false_keeps_runtime_alive_silent_results_and_allows_retry(
    qapp: QApplication,
) -> None:
    window, controller, submitter = _window_with_submitter(
        qapp,
        shutdown_outcomes=(False, True),
    )
    window.formula_panel.set_text("x")
    window.generate_button.click()
    request = submitter.submissions[0][0]

    assert window.close() is False
    assert window.isVisible() is True
    assert controller.task_phase is TaskPhase.SHUTTING_DOWN
    assert window.controller is controller
    assert controller._render_submitter is submitter
    assert window.status_panel.status_text() == "Unable to shut down the render service."

    status_before = window.status_panel.status_text()
    assert window.handle_render_result(_success(request)) is (
        RenderResultDisposition.IGNORED_OBSOLETE
    )
    assert window.plot_preview.source_image is None
    assert window.status_panel.status_text() == status_before

    assert window.close() is True
    assert submitter.shutdown_calls == 2
    window.deleteLater()
    QApplication.processEvents()


def test_main_window_delegates_clipboard_io_to_the_injected_service() -> None:
    import inspect
    import math_drawing_assistant.ui.main_window as main_window_module

    source = inspect.getsource(main_window_module)
    assert "import QClipboard" not in source
    assert ".clipboard()" not in source
    assert "setImage(" not in source
    assert "qimage_from_png_bytes" not in source
    assert "ClipboardService" in source
    assert "copy_requested.connect(self._handle_copy_requested)" in source
