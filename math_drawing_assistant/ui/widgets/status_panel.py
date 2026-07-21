"""应用状态面板 —— 静态展示当前阶段和状态文字。

不调用 AppController，不修改 TaskPhase，不执行任务协调。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget


class StatusPanel(QWidget):
    """只读状态指示区域。

    显示可理解的中文状态文字，同时通过 object name 提供辅助样式线索。
    从不只依赖颜色传递状态。
    """

    # 状态等级映射（用于 QSS 选择器）
    STATUS_LEVELS = {
        "idle": "statusIdle",
        "processing": "statusProcessing",
        "success": "statusSuccess",
        "warning": "statusWarning",
        "error": "statusError",
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._icon_label = QLabel("●")
        self._icon_label.setObjectName("statusIcon")
        self._icon_label.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )

        self._text_label = QLabel("就绪")
        self._text_label.setObjectName("statusText")
        self._text_label.setWordWrap(True)
        self._text_label.setAccessibleName("应用状态")
        self._text_label.setAccessibleDescription(
            "显示应用程序当前状态，包括就绪、处理中、成功、警告和错误"
        )
        self._text_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self._icon_label)
        layout.addWidget(self._text_label, 1)

        self.setObjectName("statusIdle")

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def set_status(self, text: str, level: str = "idle") -> None:
        """同时更新状态文字和视觉等级。

        Args:
            text: 用户可见的中文状态描述。
            level: ``"idle"`` | ``"processing"`` | ``"success"`` |
                   ``"warning"`` | ``"error"``。未知值回退为 ``"idle"``。
        """
        self._text_label.setText(text)
        obj_name = self.STATUS_LEVELS.get(level, "statusIdle")
        # 同时在 status bar 上设置 object name 以支持 QSS 整体选择
        self.setObjectName(obj_name)
        # 父面板状态必须先更新，再按当前选择器刷新子控件样式。
        icon_style = self._icon_label.style()
        icon_style.unpolish(self._icon_label)
        icon_style.polish(self._icon_label)
        self._icon_label.update()

    def status_text(self) -> str:
        """返回当前状态文字。"""
        return self._text_label.text()
