"""Tests for GUI-thread-only, aspect-preserving preview display."""

from __future__ import annotations

import base64
import threading

import pytest
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
    preview.set_png_bytes(PNG_3X2)
    first = preview.displayed_pixmap
    preview.set_image(qimage_from_png_bytes(PNG_3X2))
    assert preview.displayed_pixmap is not None
    assert preview.source_image is not None

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
    assert first is not None


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
