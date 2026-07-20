"""单项公式输入面板 —— 只收集用户文本并发出提交信号。

不执行公式解析、规范化、分类或绘图。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class FormulaInputPanel(QWidget):
    """带标签的单项公式或方程输入区。

    信号:
        submit_requested: 用户在输入框按下 Enter 时发出。
    """

    submit_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # ---- 可见标签 ----
        self._label = QLabel("公式或方程")

        # ---- 输入框 ----
        self._input = QLineEdit()
        self._input.setPlaceholderText("例如：y = sin(x)")
        self._input.setAccessibleName("公式输入框")
        self._input.setAccessibleDescription(
            "输入要绘制的数学公式或方程，例如 y = sin(x)"
        )
        self._input.setMinimumHeight(44)
        self._input.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self._label.setBuddy(self._input)

        # ---- 辅助提示 ----
        self._hint = QLabel(
            "支持 y=f(x) 显函数、一般直线、圆与圆锥曲线方程"
        )
        self._hint.setWordWrap(True)
        self._hint.setObjectName("inputHint")

        # ---- 布局 ----
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(self._label)
        row.addWidget(self._input, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addLayout(row)
        layout.addWidget(self._hint)

        # ---- 连接 ----
        self._input.returnPressed.connect(self.submit_requested)

    # ------------------------------------------------------------------
    # 公共接口（供 MainWindow 读取和展示静态值）
    # ------------------------------------------------------------------

    def text(self) -> str:
        """返回当前输入框文本（不去除空白）。"""
        return self._input.text()

    def set_text(self, text: str) -> None:
        """以给定文本替换输入框内容。"""
        self._input.setText(text)

    def clear(self) -> None:
        """清空输入框。"""
        self._input.clear()

    def set_enabled(self, enabled: bool) -> None:
        """启用或禁用输入框（标签和提示保持可读）。"""
        self._input.setEnabled(enabled)

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def set_focus(self) -> None:
        """将键盘焦点移入输入框。"""
        self._input.setFocus()
