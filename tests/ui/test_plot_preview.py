"""Tests for GUI-thread-only, aspect-preserving preview display."""

from __future__ import annotations

import base64
import inspect
import threading

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from math_drawing_assistant.ui.qt_image import qimage_from_png_bytes
from math_drawing_assistant.ui.widgets.plot_preview import (
    GuiThreadViolationError,
    PlotPreview,
)


PNG_3X2 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAMAAAACCAYAAACddGYaAAAAEUlEQVR4nGP4z8DwH4YZ"
    "kDkAm34L9XKwuTwAAAAASUVORK5CYII="
)


@pytest.fixture
def preview(qapp: QApplication) -> PlotPreview:
    widget = PlotPreview()
    widget.resize(300, 200)
    widget.show()
    QApplication.processEvents()
    yield widget
    widget.close()
    widget.deleteLater()
    QApplication.processEvents()


def _assert_aspect_ratio(preview: PlotPreview) -> None:
    pixmap = preview.displayed_pixmap
    assert pixmap is not None
    assert pixmap.width() <= preview._image_label.contentsRect().width()
    assert pixmap.height() <= preview._image_label.contentsRect().height()
    assert abs((pixmap.width() / pixmap.height()) - (3 / 2)) <= 0.05


def test_initial_state_is_visible_no_image_placeholder(preview: PlotPreview) -> None:
    assert preview.placeholder_text() == "尚未生成图像"
    assert preview._placeholder.isVisible() is True
    assert preview.displayed_pixmap is None


def test_png_display_is_aspect_preserving_and_reacts_to_resize(
    preview: PlotPreview,
) -> None:
    preview.set_png_bytes(PNG_3X2)
    QApplication.processEvents()
    _assert_aspect_ratio(preview)

    preview.resize(120, 300)
    QApplication.processEvents()
    _assert_aspect_ratio(preview)

    preview.resize(500, 160)
    QApplication.processEvents()
    _assert_aspect_ratio(preview)


def test_resize_reuses_unscaled_source_image(preview: PlotPreview) -> None:
    preview.set_png_bytes(PNG_3X2)
    preview.resize(80, 80)
    QApplication.processEvents()
    small_pixmap = preview.displayed_pixmap
    assert small_pixmap is not None

    preview.resize(400, 300)
    QApplication.processEvents()
    large_pixmap = preview.displayed_pixmap
    assert large_pixmap is not None
    assert large_pixmap.width() > small_pixmap.width()
    assert preview.source_image is not None
    assert preview.source_image.size() == qimage_from_png_bytes(PNG_3X2).size()


def test_repeated_resize_cycles_preserve_source_and_scale_only_from_it(
    preview: PlotPreview,
) -> None:
    """反复宽窄缩放不改变 retained source，也不累计缩略图误差。"""

    preview.set_result(
        PNG_3X2,
        plot_type="圆",
        normalized_input="x^2+y^2=4",
    )
    original = preview.source_image
    assert original is not None
    original_size = original.size()
    repeated_baseline_sizes: list[tuple[int, int]] = []

    sizes = (
        (300, 200),
        (720, 420),
        (360, 620),
        (900, 260),
        (300, 200),
    )
    for _ in range(3):
        for width, height in sizes:
            preview.resize(width, height)
            QApplication.processEvents()

            retained = preview.source_image
            pixmap = preview.displayed_pixmap
            assert retained is not None
            assert retained.size() == original_size
            assert retained == original
            assert pixmap is not None
            assert pixmap.width() <= preview._image_label.contentsRect().width()
            assert pixmap.height() <= preview._image_label.contentsRect().height()
            assert abs(
                pixmap.width() * original_size.height()
                - pixmap.height() * original_size.width()
            ) <= max(original_size.width(), original_size.height())

            if (width, height) == sizes[0]:
                repeated_baseline_sizes.append(
                    (pixmap.width(), pixmap.height())
                )

    assert len(set(repeated_baseline_sizes)) == 1

    refresh_source = inspect.getsource(PlotPreview._refresh_pixmap)
    assert "self._source_image" in refresh_source
    assert "self._image_label.pixmap" not in refresh_source
    assert "Qt.AspectRatioMode.KeepAspectRatio" in refresh_source
    assert Qt.AspectRatioMode.KeepAspectRatio is not None


def test_tiny_or_zero_size_does_not_crash_and_later_recovers(
    preview: PlotPreview,
) -> None:
    preview.set_png_bytes(PNG_3X2)
    preview.resize(0, 0)
    QApplication.processEvents()
    assert preview.source_image is not None

    preview.resize(180, 120)
    QApplication.processEvents()
    assert preview.displayed_pixmap is not None


def test_repeated_set_replacement_clear_and_stale_states(preview: PlotPreview) -> None:
    preview.set_result(
        PNG_3X2,
        plot_type="圆",
        normalized_input="x^2+y^2=4",
    )
    first = preview.displayed_pixmap
    assert preview.result_plot_type == "圆"
    assert preview.normalized_input == "x^2+y^2=4"
    assert preview.summary_text() == (
        "图形类型：圆\n规范化表达式：x^2+y^2=4"
    )
    assert preview._summary_label.isVisible() is True

    preview.set_image(qimage_from_png_bytes(PNG_3X2))
    assert preview.displayed_pixmap is not None
    assert preview.source_image is not None
    assert preview.result_plot_type is None
    assert preview.normalized_input is None
    assert preview._summary_label.isVisible() is False

    preview.set_stale(True)
    assert preview._stale_label.isVisible() is True
    assert "旧输入" in preview._stale_label.text()
    assert preview.displayed_pixmap is not None

    preview.set_stale(False)
    assert preview._stale_label.isVisible() is False
    assert preview.displayed_pixmap is not None

    preview.clear_image()
    preview.clear_image()
    assert preview.source_image is None
    assert preview.displayed_pixmap is None
    assert preview._placeholder.isVisible() is True
    assert preview._stale_label.isVisible() is False
    assert preview._summary_label.isVisible() is False
    assert preview.result_plot_type is None
    assert preview.normalized_input is None
    assert first is not None


def test_result_summary_replaces_atomically_and_shares_image_lifetime(
    preview: PlotPreview,
) -> None:
    preview.set_result(
        PNG_3X2,
        plot_type="抛物线",
        normalized_input="x^2=4*y",
    )
    source = preview.source_image

    with pytest.raises(ValueError):
        preview.set_result(
            PNG_3X2,
            plot_type="",
            normalized_input="x^2=4*y",
        )
    assert preview.source_image == source
    assert preview.result_plot_type == "抛物线"
    assert preview.normalized_input == "x^2=4*y"

    preview.show_placeholder()
    assert preview.source_image is None
    assert preview.summary_text() == ""
    assert preview.result_plot_type is None
    assert preview.normalized_input is None


def test_invalid_qimage_is_rejected(preview: PlotPreview) -> None:
    with pytest.raises(ValueError):
        preview.set_image(QImage())


def test_display_entry_rejects_non_gui_thread_before_widget_updates(
    preview: PlotPreview,
) -> None:
    errors: list[BaseException] = []

    def call_from_worker() -> None:
        try:
            preview.set_png_bytes(PNG_3X2)
        except BaseException as exc:  # assert the public boundary behavior
            errors.append(exc)

    worker = threading.Thread(target=call_from_worker)
    worker.start()
    worker.join(timeout=2)

    assert worker.is_alive() is False
    assert len(errors) == 1
    assert isinstance(errors[0], GuiThreadViolationError)
    assert preview.source_image is None
