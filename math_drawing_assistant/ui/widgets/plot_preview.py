"""图片预览占位区 —— 只展示占位文字，不加载或生成真实图片。

阶段 3 不加载固定 PNG、不创建 QImage 或 QPixmap、不实现缩放。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout


class PlotPreview(QFrame):
    """静态图片预览占位区域。

    无图片时显示占位说明；设置合理最小尺寸和伸缩策略。
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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._placeholder)

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def show_placeholder(self, text: str = "尚未生成图像") -> None:
        """显示占位文字并清除任何已有图片（阶段 4 扩展）。"""
        self._placeholder.setText(text)
        self._placeholder.setVisible(True)

    def set_placeholder_text(self, text: str) -> None:
        """更新占位文字。"""
        self._placeholder.setText(text)

    def placeholder_text(self) -> str:
        """返回当前占位文字。"""
        return self._placeholder.text()
