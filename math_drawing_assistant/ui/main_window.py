"""阶段 1 最小主窗口 —— 仅验证 Qt 窗口创建与正常关闭。

不包含公式输入、绘图预览、按钮组、状态面板或完整布局。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMainWindow


class MainWindow(QMainWindow):
    """阶段 1 启动骨架主窗口。

    设置窗口标题、初始尺寸和一个最小中央占位控件，
    明确当前只是启动骨架，尚未实现业务功能。
    """

    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("数学绘图助手")
        self.resize(800, 600)

        placeholder = QLabel("阶段 1 启动骨架 —— 业务功能尚未实现")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCentralWidget(placeholder)
