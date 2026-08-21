"""Stage 15-D2 accepted-result GUI, warning, retention and copy closure."""

from __future__ import annotations

import base64
import inspect

import pytest
from PySide6.QtCore import QEventLoop, QPoint, QRect, QTimer
from PySide6.QtGui import QImage
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from math_drawing_assistant import bootstrap
from math_drawing_assistant.app_controller import (
    AppController,
    RenderResultDisposition,
)
from math_drawing_assistant.models import (
    ConcretePlotType,
    ErrorCode,
    ErrorInfo,
    PlotItemResult,
    PlotKind,
    PlotSceneResult,
    ResolvedAspect,
    TaskPhase,
    ViewportSource,
)
from math_drawing_assistant.services.clipboard_service import ClipboardService
from math_drawing_assistant.ui.main_window import MainWindow


PNG_3X2 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAMAAAACCAYAAACddGYaAAAAEUlEQVR4nGP4z8DwH4YZ"
    "kDkAm34L9XKwuTwAAAAASUVORK5CYII="
)
_GUARD_TIMEOUT_MS = 15_000

TYPE_CASES = (
    ("y=x²", ConcretePlotType.EXPLICIT_FUNCTION, "显函数", ResolvedAspect.AUTO),
    ("x+y=1", ConcretePlotType.GENERAL_LINE, "一般直线", ResolvedAspect.AUTO),
    ("x^2+y^2=4", ConcretePlotType.CIRCLE, "圆", ResolvedAspect.EQUAL),
    ("x^2/9+y^2/4=1", ConcretePlotType.ELLIPSE, "椭圆", ResolvedAspect.EQUAL),
    ("x^2/9-y^2/4=1", ConcretePlotType.HYPERBOLA, "双曲线", ResolvedAspect.EQUAL),
    ("x^2=4*y", ConcretePlotType.PARABOLA, "抛物线", ResolvedAspect.EQUAL),
)

WARNING_MESSAGES = {
    "auto_viewport_fallback": "自动视口探测不可靠，已使用安全范围。",
    "partial_domain_omitted": "部分定义域没有可绘制值，已省略不可绘制部分。",
    "dense_oscillation_suspected": (
        "当前区间内可能包含密集振荡，请确认是否需要调整范围。"
    ),
    "viewport_clipped": "曲线在当前视口中被裁切。",
    "sampling_precision_limited": "当前采样精度受限，图像可能不够精确。",
}


class _ImageClipboard:
    def __init__(self) -> None:
        self.images: list[QImage] = []

    def setImage(self, image: QImage) -> None:
        self.images.append(image)


def _spin_until(predicate, *, timeout_ms: int = _GUARD_TIMEOUT_MS) -> None:
    if predicate():
        return
    loop = QEventLoop()
    poll = QTimer()
    guard = QTimer()
    guard.setSingleShot(True)

    def finish_if_ready() -> None:
        if predicate():
            loop.quit()

    poll.timeout.connect(finish_if_ready)
    guard.timeout.connect(loop.quit)
    poll.start(1)
    guard.start(timeout_ms)
    loop.exec()
    poll.stop()
    guard.stop()
    assert predicate(), "Qt event-loop guard timeout"


@pytest.fixture
def production_runtime(qapp: QApplication):
    runtime = bootstrap.create_application_runtime(qapp)
    started = QSignalSpy(runtime.actor._thread.started)
    runtime.actor.start()
    assert started.count() >= 1 or started.wait(3_000) is True
    runtime.window.viewport_panel.set_image_width(400)
    runtime.window.viewport_panel.set_image_height(300)
    runtime.window.show()
    QApplication.processEvents()
    yield runtime
    if runtime.actor.is_running:
        assert runtime.actor.shutdown(5_000) is True
    runtime.window.close()
    runtime.window.deleteLater()
    QApplication.processEvents()


def _generate(
    runtime: object,
    formula: str,
    *,
    viewport_mode: str = "auto",
    image_width: int = 400,
) -> PlotSceneResult:
    window = runtime.window
    window.formula_panel.set_text(formula)
    window.viewport_panel.set_viewport_mode(viewport_mode)
    window.viewport_panel.set_aspect_mode("default")
    window.viewport_panel.set_image_width(image_width)
    if viewport_mode == "manual":
        window.viewport_panel.set_x_min(-10.0)
        window.viewport_panel.set_x_max(10.0)
        window.viewport_panel.set_y_min(-10.0)
        window.viewport_panel.set_y_max(10.0)
    results = QSignalSpy(runtime.actor.result_ready)
    window.generate_button.click()
    _spin_until(lambda: results.count() == 1)
    QApplication.processEvents()
    delivered = results.at(0)[0]
    assert type(delivered) is PlotSceneResult
    return delivered


def _accepted_result(
    request: object,
    *,
    warnings: tuple[str, ...] = (),
    concrete_plot_type: ConcretePlotType = ConcretePlotType.EXPLICIT_FUNCTION,
    normalized_input: str = "y=x",
) -> PlotSceneResult:
    plot_kind = (
        PlotKind.EXPLICIT_FUNCTION
        if concrete_plot_type is ConcretePlotType.EXPLICIT_FUNCTION
        else PlotKind.LINE_EQUATION
        if concrete_plot_type is ConcretePlotType.GENERAL_LINE
        else PlotKind.CONIC_EQUATION
    )
    return PlotSceneResult(
        request_id=request.request_id,
        scene_revision=request.scene_revision,
        success=True,
        png_bytes=PNG_3X2,
        item_results=(
            PlotItemResult(
                item_id=request.items[0].item_id,
                success=True,
                normalized_input=normalized_input,
                plot_kind=plot_kind,
                concrete_plot_type=concrete_plot_type,
            ),
        ),
        warnings=warnings,
    )


def _unit_window(
    qapp: QApplication,
) -> tuple[MainWindow, AppController, _ImageClipboard]:
    controller = AppController()
    backend = _ImageClipboard()
    window = MainWindow(
        controller=controller,
        clipboard_service=ClipboardService(backend),
    )
    window.show()
    QApplication.processEvents()
    return window, controller, backend


def _request(controller: AppController, formula: str = "y=x") -> object:
    return controller.create_m1_render_request(
        formula_text=formula,
        viewport_mode="auto",
        x_min=-10.0,
        x_max=10.0,
        y_min=-10.0,
        y_max=10.0,
        aspect_request="default",
        show_grid=True,
        image_width=400,
        image_height=300,
    )


def test_six_exact_types_share_one_bootstrap_controller_actor_gui_pipeline(
    production_runtime,
) -> None:
    runtime = production_runtime
    window = runtime.window

    for formula, expected_type, expected_label, expected_aspect in TYPE_CASES:
        delivered = _generate(runtime, formula)

        assert delivered.success is True
        assert len(delivered.item_results) == 1
        item = delivered.item_results[0]
        assert item.concrete_plot_type is expected_type
        assert window.plot_preview.result_plot_type == expected_label
        assert window.plot_preview.normalized_input == item.normalized_input
        assert f"图形类型：{expected_label}" in window.plot_preview.summary_text()
        assert f"规范化表达式：{item.normalized_input}" in (
            window.plot_preview.summary_text()
        )
        assert delivered.resolved_viewport is not None
        assert delivered.resolved_viewport.aspect is expected_aspect
        assert runtime.controller.last_successful_result is delivered
        assert window.plot_preview.source_image is not None

    assert type(runtime.executor).__name__ == "SceneRenderExecutor"
    assert runtime.actor._worker._executor is runtime.executor
    assert runtime.controller._render_submitter is runtime.actor
    assert runtime.window.controller is runtime.controller


def test_default_circle_and_repeated_window_resize_preserve_both_aspect_layers(
    production_runtime,
) -> None:
    """圆由 resolver 选 EQUAL，Qt 预览再从源图按比例反复缩放。"""

    runtime = production_runtime
    window = runtime.window
    delivered = _generate(runtime, "x^2+y^2=4")
    assert delivered.success is True
    assert delivered.resolved_viewport is not None
    assert delivered.resolved_viewport.aspect is ResolvedAspect.EQUAL

    source = window.plot_preview.source_image
    assert source is not None
    source_size = source.size()
    baseline_pixmap_sizes: list[tuple[int, int]] = []
    minimum = window.minimumSize()
    sizes = (
        (minimum.width(), minimum.height()),
        (minimum.width() + 420, minimum.height() + 280),
        (minimum.width(), minimum.height()),
    )
    for _ in range(3):
        for width, height in sizes:
            window.resize(width, height)
            QApplication.processEvents()
            retained = window.plot_preview.source_image
            pixmap = window.plot_preview.displayed_pixmap
            assert retained is not None
            assert retained == source
            assert retained.size() == source_size
            assert pixmap is not None
            assert abs(
                pixmap.width() * source_size.height()
                - pixmap.height() * source_size.width()
            ) <= max(source_size.width(), source_size.height())
            if (width, height) == sizes[0]:
                baseline_pixmap_sizes.append(
                    (pixmap.width(), pixmap.height())
                )

    assert len(set(baseline_pixmap_sizes)) == 1


def test_no_image_rendering_keeps_placeholder_and_copy_disabled(
    qapp: QApplication,
) -> None:
    window, controller, _ = _unit_window(qapp)
    try:
        _request(controller)
        window._sync_controller_state()

        assert controller.task_phase is TaskPhase.RENDERING
        assert window.plot_preview.source_image is None
        assert window.plot_preview._placeholder.isVisible() is True
        assert window.plot_preview._image_label.isVisible() is False
        assert window.plot_preview._summary_label.isVisible() is False
        assert window.plot_preview._stale_label.isVisible() is False
        assert window.copy_button.isEnabled() is False
        assert window.status_panel.status_text() == "正在生成图像…"
    finally:
        window.close()
        window.deleteLater()
        QApplication.processEvents()


def test_narrow_window_keeps_preview_summary_warning_and_stale_regions_disjoint(
    qapp: QApplication,
) -> None:
    window, controller, _ = _unit_window(qapp)
    try:
        request = _request(controller)
        result = _accepted_result(
            request,
            warnings=tuple(WARNING_MESSAGES),
            concrete_plot_type=ConcretePlotType.CIRCLE,
            normalized_input="x^2+y^2=4",
        )
        window.handle_render_result(result)
        window.formula_panel.set_text("x^2+y^2=9")
        window.resize(window.minimumSize())
        QApplication.processEvents()

        preview = window.plot_preview
        assert preview._placeholder.isVisible() is False
        assert preview._image_label.isVisible() is True
        assert preview._summary_label.isVisible() is True
        assert preview._stale_label.isVisible() is True
        assert window.status_panel._warning_label.isVisible() is True
        assert window.status_panel.warning_messages() == tuple(
            WARNING_MESSAGES.values()
        )

        preview_regions = (
            preview._image_label,
            preview._summary_label,
            preview._stale_label,
        )
        assert all(region.width() > 0 and region.height() > 0 for region in preview_regions)
        assert all(
            not left.geometry().intersects(right.geometry())
            for index, left in enumerate(preview_regions)
            for right in preview_regions[index + 1 :]
        )

        def window_rect(widget) -> QRect:
            return QRect(widget.mapTo(window, QPoint(0, 0)), widget.size())

        preview_rect = window_rect(preview)
        warning_rect = window_rect(window.status_panel._warning_label)
        assert not preview_rect.intersects(warning_rect)
        assert all(
            not warning_rect.intersects(window_rect(button))
            for button in (
                window.generate_button,
                window.clear_button,
                window.copy_button,
            )
        )
        assert all(
            button.isVisibleTo(window)
            for button in (
                window.generate_button,
                window.clear_button,
                window.copy_button,
            )
        )
    finally:
        window.close()
        window.deleteLater()
        QApplication.processEvents()


def test_actual_viewport_and_auto_fallback_warning_order_reaches_gui(
    production_runtime,
) -> None:
    runtime = production_runtime

    clipped = _generate(runtime, "x^2/9-y^2/4=1")
    assert clipped.success is True
    assert "viewport_clipped" in clipped.warnings
    assert runtime.window.status_panel.warning_messages() == tuple(
        WARNING_MESSAGES[code] for code in clipped.warnings
    )

    fallback = _generate(
        runtime,
        "y=sqrt(0.000064-x^2)",
        image_width=800,
    )
    assert fallback.success is True
    assert fallback.resolved_viewport is not None
    assert fallback.resolved_viewport.source is ViewportSource.AUTO_FALLBACK
    assert fallback.warnings == (
        "auto_viewport_fallback",
        "partial_domain_omitted",
    )
    assert runtime.window.status_panel.warning_messages() == tuple(
        WARNING_MESSAGES[code] for code in fallback.warnings
    )


def test_all_published_warning_codes_are_pure_ordered_display_mapping(
    qapp: QApplication,
) -> None:
    window, controller, backend = _unit_window(qapp)
    try:
        request = _request(controller)
        codes = tuple(WARNING_MESSAGES)
        result = _accepted_result(request, warnings=codes)
        assert window.handle_render_result(result) is (
            RenderResultDisposition.ACCEPTED_SUCCESS
        )

        assert window.status_panel.warning_messages() == tuple(
            WARNING_MESSAGES[code] for code in codes
        )
        assert window.status_panel._warning_label.isVisible() is True
        assert "非阻塞警告" not in window.status_panel.warning_text()
        assert window.status_panel._warning_label.accessibleName() == "绘图警告"
        assert all(
            message in window.status_panel._warning_label.accessibleDescription()
            for message in WARNING_MESSAGES.values()
        )
        assert window.copy_button.isEnabled() is True

        window.copy_button.click()
        assert len(backend.images) == 1
        assert window.status_panel.warning_messages() == tuple(
            WARNING_MESSAGES[code] for code in codes
        )
        window._copy_feedback_timer.timeout.emit()
        assert window.status_panel.warning_messages() == tuple(
            WARNING_MESSAGES[code] for code in codes
        )

        window.formula_panel.set_text("y=x+1")
        assert window.status_panel.warning_messages() == tuple(
            WARNING_MESSAGES[code] for code in codes
        )

        replacement_request = _request(controller, "y=x+1")
        replacement = _accepted_result(replacement_request, warnings=())
        window.handle_render_result(replacement)
        assert window.status_panel.warning_messages() == ()
        assert window.status_panel._warning_label.isVisible() is False
    finally:
        window.close()
        window.deleteLater()
        QApplication.processEvents()


def test_actual_no_visible_curve_without_and_with_old_plot(
    production_runtime,
) -> None:
    runtime = production_runtime
    window = runtime.window

    first_failure = _generate(runtime, "y=100", viewport_mode="manual")
    assert first_failure.success is False
    assert first_failure.error is not None
    assert first_failure.error.code is ErrorCode.NO_VISIBLE_CURVE
    assert window.status_panel.status_text() == (
        "当前视口内没有发现曲线，请调整 x、y 范围。"
    )
    assert window.formula_panel.text() == "y=100"
    assert window.plot_preview.source_image is None
    assert window.copy_button.isEnabled() is False

    baseline = _generate(runtime, "y=x", viewport_mode="manual")
    assert baseline.success is True
    retained_image = window.plot_preview.source_image
    retained_summary = window.plot_preview.summary_text()
    retained_warnings = window.status_panel.warning_messages()

    second_failure = _generate(
        runtime,
        "(x-100)^2+(y-100)^2=1",
        viewport_mode="manual",
    )
    assert second_failure.success is False
    assert second_failure.error is not None
    assert second_failure.error.code is ErrorCode.NO_VISIBLE_CURVE
    assert window.formula_panel.text() == "(x-100)^2+(y-100)^2=1"
    assert window.plot_preview.source_image == retained_image
    assert window.plot_preview.summary_text() == retained_summary
    assert window.status_panel.warning_messages() == retained_warnings
    assert window.plot_preview._stale_label.text() == (
        "本次生成失败，预览仍是上一张成功图片。"
    )
    assert window.status_panel.status_text() == (
        "当前视口内没有发现曲线，请调整 x、y 范围。 "
        "本次生成失败，预览仍是上一张成功图片。"
    )
    assert window.status_panel.status_text().count(
        "本次生成失败，预览仍是上一张成功图片。"
    ) == 1
    assert window.copy_button.isEnabled() is True


def test_failure_stale_and_obsolete_never_replace_accepted_artifacts(
    qapp: QApplication,
) -> None:
    window, controller, _ = _unit_window(qapp)
    try:
        baseline_request = _request(controller)
        baseline = _accepted_result(
            baseline_request,
            warnings=("viewport_clipped",),
        )
        window.handle_render_result(baseline)
        retained = (
            window.plot_preview.source_image,
            window.plot_preview.summary_text(),
            window.status_panel.warning_messages(),
            controller.prepare_copy_candidate(),
        )

        window.formula_panel.set_text("y=x+1")
        assert controller.result_is_stale is True
        assert window.plot_preview._stale_label.text() == (
            "输入已修改，当前图像对应旧输入。"
        )
        assert (
            window.plot_preview.source_image,
            window.plot_preview.summary_text(),
            window.status_panel.warning_messages(),
        ) == retained[:3]

        failed_request = _request(controller, "y=x+1")
        failure = PlotSceneResult(
            request_id=failed_request.request_id,
            scene_revision=failed_request.scene_revision,
            success=False,
            error=ErrorInfo(
                code=ErrorCode.RENDER_FAILED,
                user_message="本次生成失败。",
            ),
        )
        assert window.handle_render_result(failure) is (
            RenderResultDisposition.HANDLED_CURRENT_FAILURE
        )
        assert (
            window.plot_preview.source_image,
            window.plot_preview.summary_text(),
            window.status_panel.warning_messages(),
        ) == retained[:3]

        current_request = _request(controller, "y=x+2")
        obsolete = PlotSceneResult(
            request_id=current_request.request_id + 100,
            scene_revision=current_request.scene_revision,
            success=True,
            png_bytes=PNG_3X2,
            warnings=("sampling_precision_limited",),
        )
        assert window.handle_render_result(obsolete) is (
            RenderResultDisposition.IGNORED_OBSOLETE
        )
        assert (
            window.plot_preview.source_image,
            window.plot_preview.summary_text(),
            window.status_panel.warning_messages(),
        ) == retained[:3]
        after = controller.prepare_copy_candidate()
        assert after.candidate is not None
        assert retained[3].candidate is not None
        assert after.candidate.png_bytes == retained[3].candidate.png_bytes
        assert after.candidate.request_id == retained[3].candidate.request_id
        assert after.candidate.scene_revision == retained[3].candidate.scene_revision
    finally:
        window.close()
        window.deleteLater()
        QApplication.processEvents()


def test_fresh_repeated_stale_rendering_and_failed_current_copy_closure(
    qapp: QApplication,
) -> None:
    window, controller, backend = _unit_window(qapp)
    try:
        baseline_request = _request(controller)
        baseline = _accepted_result(baseline_request)
        window.handle_render_result(baseline)

        window.copy_button.click()
        window.copy_button.click()
        assert len(backend.images) == 2
        assert window.status_panel.status_text() == "图片已写入剪贴板"

        same_revision_request = _request(controller)
        assert same_revision_request.scene_revision == baseline.scene_revision
        window._sync_controller_state()
        assert window.status_panel.status_text() == (
            "正在生成图像，当前仍显示上一张成功图片。"
        )
        window.copy_button.click()
        assert len(backend.images) == 3
        assert window.status_panel.status_text() == (
            "已复制上一张成功图；新图仍在生成"
        )

        failure = PlotSceneResult(
            request_id=same_revision_request.request_id,
            scene_revision=same_revision_request.scene_revision,
            success=False,
            error=ErrorInfo(
                code=ErrorCode.RENDER_FAILED,
                user_message="本次生成失败。",
            ),
        )
        window.handle_render_result(failure)
        assert controller.result_is_stale is False
        window.copy_button.click()
        assert len(backend.images) == 4
        assert window.status_panel.status_text() == (
            "已复制上一张成功图；本次生成失败"
        )

        replacement_request = _request(controller)
        replacement = _accepted_result(
            replacement_request,
            normalized_input="y=x+1",
        )
        window.handle_render_result(replacement)
        window.formula_panel.set_text("y=x+1")
        window.copy_button.click()
        assert len(backend.images) == 5
        assert window.status_panel.status_text() == (
            "已复制上一张成功图；当前输入已修改"
        )
        assert all(not image.isNull() for image in backend.images)
    finally:
        window.close()
        window.deleteLater()
        QApplication.processEvents()


def test_ui_has_one_result_pipeline_not_one_state_machine_per_formula_type() -> None:
    import math_drawing_assistant.ui.main_window as main_window_module

    source = inspect.getsource(main_window_module)
    assert source.count("RenderResultDisposition.ACCEPTED_SUCCESS") == 1
    assert source.count("set_result(") == 1
    assert "math_drawing_assistant.engine" not in source
    assert "matplotlib" not in source.lower()
    assert all(
        f"if item_result.concrete_plot_type is ConcretePlotType.{member.name}"
        not in source
        for member in ConcretePlotType
    )
    assert TaskPhase.RENDERING.value == "rendering"
