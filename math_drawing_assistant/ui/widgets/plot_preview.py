"""GUI-thread-only PNG preview widget."""

from __future__ import annotations

from PySide6.QtCore import QThread, Qt
from PySide6.QtGui import QImage, QPixmap, QResizeEvent
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QSizePolicy, QVBoxLayout

from math_drawing_assistant.ui.qt_image import qimage_from_png_bytes


class GuiThreadViolationError(RuntimeError):
    """Raised before a display operation touches a Qt GUI object off-thread."""


class PlotPreview(QFrame):
    """Display a PNG image while preserving its aspect ratio.

    ``QImage`` is retained as the unscaled source.  Every resize recreates the
    displayed pixmap from that source, avoiding repeated scaling artifacts.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setFrameStyle(QFrame.Shape.StyledPanel)
        self.setObjectName("plotPreview")
        self.setAccessibleName("图片预览区域")
        self.setAccessibleDescription("显示生成的数学图像预览")
        self.setMinimumSize(300, 200)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        self._placeholder = QLabel("尚未生成图像")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setWordWrap(True)
        self._placeholder.setObjectName("previewPlaceholder")

        self._image_label = QLabel()
        self._image_label.setObjectName("previewImage")
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self._image_label.setVisible(False)

        self._stale_label = QLabel("当前图像对应旧输入")
        self._stale_label.setObjectName("previewStaleNotice")
        self._stale_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._stale_label.setWordWrap(True)
        self._stale_label.setVisible(False)

        self._summary_label = QLabel()
        self._summary_label.setObjectName("previewResultSummary")
        self._summary_label.setWordWrap(True)
        self._summary_label.setAccessibleName("绘图结果摘要")
        self._summary_label.setAccessibleDescription(
            "显示当前预览图片的图形类型和规范化表达式"
        )
        self._summary_label.setVisible(False)

        self._source_image: QImage | None = None
        self._result_plot_type: str | None = None
        self._normalized_input: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._placeholder)
        layout.addWidget(self._image_label, 1)
        layout.addWidget(self._summary_label)
        layout.addWidget(self._stale_label)

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def show_placeholder(self, text: str = "尚未生成图像") -> None:
        """Clear the image and show visible no-image text."""
        self._assert_gui_thread()
        self._show_empty_state(text)

    def set_placeholder_text(self, text: str) -> None:
        """更新占位文字。"""
        self._assert_gui_thread()
        self._placeholder.setText(text)

    def placeholder_text(self) -> str:
        """返回当前占位文字。"""
        return self._placeholder.text()

    def set_png_bytes(self, data: bytes | bytearray | memoryview) -> None:
        """Decode PNG bytes and display the resulting image on the GUI thread."""
        self._assert_gui_thread()
        self.set_image(qimage_from_png_bytes(data))

    def set_result(
        self,
        data: bytes | bytearray | memoryview,
        *,
        plot_type: str,
        normalized_input: str,
    ) -> None:
        """Atomically replace the accepted image and its single-item summary."""

        self._assert_gui_thread()
        if type(plot_type) is not str or not plot_type.strip():
            raise ValueError("plot_type must be a non-empty string")
        if type(normalized_input) is not str or not normalized_input.strip():
            raise ValueError("normalized_input must be a non-empty string")
        image = qimage_from_png_bytes(data)
        self._set_image(
            image,
            plot_type=plot_type,
            normalized_input=normalized_input,
        )

    def set_image(self, image: QImage) -> None:
        """Display a valid QImage, retaining a detached unscaled source copy."""
        self._assert_gui_thread()
        self._set_image(image, plot_type=None, normalized_input=None)

    def _set_image(
        self,
        image: QImage,
        *,
        plot_type: str | None,
        normalized_input: str | None,
    ) -> None:
        if image.isNull() or image.width() <= 0 or image.height() <= 0:
            raise ValueError("预览图像必须具有正的宽度和高度")

        self._source_image = image.copy()
        self._result_plot_type = plot_type
        self._normalized_input = normalized_input
        if plot_type is None or normalized_input is None:
            self._summary_label.clear()
            self._summary_label.setVisible(False)
        else:
            summary = (
                f"图形类型：{plot_type}\n"
                f"规范化表达式：{normalized_input}"
            )
            self._summary_label.setText(summary)
            self._summary_label.setAccessibleDescription(summary.replace("\n", "；"))
            self._summary_label.setVisible(True)
        self._stale_label.setVisible(False)
        self._placeholder.setVisible(False)
        self._image_label.setVisible(True)
        self._refresh_pixmap()

    def clear_image(self) -> None:
        """Remove the image and restore the visible no-image placeholder."""
        self._assert_gui_thread()
        self._show_empty_state("尚未生成图像")

    def set_stale(self, stale: bool, text: str = "当前图像对应旧输入") -> None:
        """Show or hide explicit stale-input text while retaining the image."""
        self._assert_gui_thread()
        if self._source_image is None:
            self._stale_label.setVisible(False)
            return

        self._stale_label.setText(text)
        self._stale_label.setVisible(stale)
        self.layout().activate()
        self._refresh_pixmap()

    @property
    def source_image(self) -> QImage | None:
        """Return a copy of the retained source image for UI tests/inspection."""
        return None if self._source_image is None else self._source_image.copy()

    @property
    def displayed_pixmap(self) -> QPixmap | None:
        """Return the current scaled pixmap, if the preview has drawable space."""
        pixmap = self._image_label.pixmap()
        return None if pixmap is None or pixmap.isNull() else pixmap

    @property
    def result_plot_type(self) -> str | None:
        """Return the concrete type label bound to the displayed image."""

        return self._result_plot_type

    @property
    def normalized_input(self) -> str | None:
        """Return the normalized expression bound to the displayed image."""

        return self._normalized_input

    def summary_text(self) -> str:
        """Return the visible accepted-result summary text."""

        return self._summary_label.text()

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Adapt the display to the newly available preview area."""
        super().resizeEvent(event)
        if self._source_image is not None:
            self._assert_gui_thread()
            self._refresh_pixmap()

    def _show_empty_state(self, text: str) -> None:
        self._source_image = None
        self._result_plot_type = None
        self._normalized_input = None
        self._image_label.clear()
        self._image_label.setVisible(False)
        self._summary_label.clear()
        self._summary_label.setVisible(False)
        self._stale_label.setVisible(False)
        self._placeholder.setText(text)
        self._placeholder.setVisible(True)

    def _refresh_pixmap(self) -> None:
        """Scale from the original source image, never from a prior thumbnail."""
        if self._source_image is None:
            return

        layout = self.layout()
        if layout is not None:
            layout.activate()
        target_size = self._image_label.contentsRect().size()
        if target_size.width() <= 0 or target_size.height() <= 0:
            self._image_label.clear()
            return

        source_pixmap = QPixmap.fromImage(self._source_image)
        scaled = source_pixmap.scaled(
            target_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._image_label.setPixmap(scaled)

    @staticmethod
    def _assert_gui_thread() -> None:
        app = QApplication.instance()
        if app is None or QThread.currentThread() != app.thread():
            raise GuiThreadViolationError("图片预览只能在 GUI 主线程中更新")
