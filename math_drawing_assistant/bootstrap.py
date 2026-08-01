"""Application composition root for the formal M1 scene flow.

职责仅包括：
1. 接收可选的命令行参数；
2. 检查是否已存在 QApplication 实例；
3. 仅在不存在时创建 QApplication；
4. 设置最小应用元数据；
5. 创建唯一 SceneRenderExecutor / RenderActor / AppController；
6. 创建 MainWindow、连接结果 relay 并保有强引用；
7. 显示窗口、进入事件循环并返回整数退出码。

不在模块顶层创建应用、窗口或启动事件循环。
模块被重复导入时不产生 GUI 副作用。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Sequence

from PySide6.QtWidgets import QApplication

from math_drawing_assistant.app_controller import AppController
from math_drawing_assistant.engine.scene_executor import SceneRenderExecutor
from math_drawing_assistant.ui.main_window import MainWindow
from math_drawing_assistant.workers.render_actor import RenderActor


@dataclass(slots=True)
class _ApplicationRuntime:
    """Explicitly own every production object for the event-loop lifetime."""

    executor: SceneRenderExecutor
    actor: RenderActor
    controller: AppController
    window: MainWindow


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

    executor = SceneRenderExecutor()
    actor = RenderActor(executor)
    controller = AppController(render_submitter=actor)
    window = MainWindow(controller=controller)
    actor.result_ready.connect(window.handle_render_result)

    runtime = _ApplicationRuntime(
        executor=executor,
        actor=actor,
        controller=controller,
        window=window,
    )
    # QApplication can outlive this Python stack in embedded launchers.  The
    # composition object makes production ownership explicit in either mode.
    app._math_drawing_assistant_runtime = runtime  # type: ignore[attr-defined]

    actor.start()
    window.show()

    exit_code = app.exec()

    # Normal exit is decided inside MainWindow.closeEvent while this event loop
    # still runs.  For an external app.exit(), do not turn a timed-out shutdown
    # into process exit: resume the UI loop so the retained runtime can retry.
    while actor.is_running:
        if controller.shutdown():
            break
        exit_code = app.exec()
    return exit_code
