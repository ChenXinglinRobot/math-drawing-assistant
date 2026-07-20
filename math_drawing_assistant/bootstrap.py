"""阶段 1 启动骨架：QApplication 创建、MainWindow 显示与事件循环。

职责仅包括：
1. 接收可选的命令行参数；
2. 检查是否已存在 QApplication 实例；
3. 仅在不存在时创建 QApplication；
4. 设置最小应用元数据；
5. 创建 MainWindow 并显示；
6. 进入 QApplication.exec()；
7. 返回整数退出码。

不在模块顶层创建应用、窗口或启动事件循环。
模块被重复导入时不产生 GUI 副作用。
"""

from __future__ import annotations

import sys
from typing import Sequence

from PySide6.QtWidgets import QApplication

from math_drawing_assistant.ui.main_window import MainWindow


def run(argv: Sequence[str] | None = None) -> int:
    """启动应用：必要时创建 QApplication、显示主窗口、进入事件循环。

    Args:
        argv: 命令行参数列表；若为 None 则使用 sys.argv。

    Returns:
        整数退出码，适合传递给 SystemExit 或 sys.exit。

    Raises:
        RuntimeError: 已存在 QApplication 实例且尝试用不同参数创建时。
    """
    if argv is None:
        argv = list(sys.argv)

    existing = QApplication.instance()
    if existing is not None:
        app: QApplication = existing
    else:
        app = QApplication(list(argv))

    # 仅设置文档已明确的软件名称，不虚构公司名、组织域名或版本号。
    if not app.applicationName():
        app.setApplicationName("数学绘图助手")

    window = MainWindow()
    window.show()

    return app.exec()
