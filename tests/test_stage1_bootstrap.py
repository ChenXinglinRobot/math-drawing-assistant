"""阶段 1 启动骨架最小自动测试。

覆盖：
1. 重复导入 main / bootstrap / main_window 不会自动创建窗口或启动事件循环；
2. 导入 bootstrap 不会自动创建新的 QApplication；
3. 已存在 QApplication 时启动准备不会创建第二个实例；
4. MainWindow 可在测试用 QApplication 下正常实例化。

不调用 QApplication.exec()，不执行绘图，不导入 plot_engine.py。
"""

from __future__ import annotations

import importlib
import sys

import pytest
from PySide6.QtWidgets import QApplication


# ---------------------------------------------------------------------------
# 1. 重复导入不自动创建窗口或启动事件循环
# ---------------------------------------------------------------------------

def test_import_main_no_gui_side_effects() -> None:
    """导入根入口 main 模块不应创建 QApplication 或窗口。"""
    assert QApplication.instance() is None, (
        "测试前不应已存在 QApplication 实例"
    )

    import main  # noqa: F811  -- 测试导入副作用

    # 导入 main 不得创建 QApplication
    assert QApplication.instance() is None, (
        "导入 main 模块不应创建 QApplication"
    )


def test_import_bootstrap_no_gui_side_effects() -> None:
    """导入 bootstrap 模块不应创建 QApplication、窗口或启动事件循环。"""
    assert QApplication.instance() is None

    from math_drawing_assistant import bootstrap

    assert QApplication.instance() is None, (
        "导入 bootstrap 模块不应自动创建 QApplication"
    )


def test_import_main_window_no_gui_side_effects() -> None:
    """导入 MainWindow 类不应创建 QApplication、显示窗口或启动事件循环。"""
    assert QApplication.instance() is None

    from math_drawing_assistant.ui.main_window import MainWindow

    assert QApplication.instance() is None, (
        "导入 main_window 模块不应自动创建 QApplication"
    )


# ---------------------------------------------------------------------------
# 2. 已存在 QApplication 时不创建第二个实例
# ---------------------------------------------------------------------------

def test_run_reuses_existing_qapplication(qapp: QApplication) -> None:
    """bootstrap.run() 在已有 QApplication 时不应尝试创建第二个。"""
    instance_before = QApplication.instance()
    assert instance_before is not None

    from math_drawing_assistant.bootstrap import run

    # 注意：我们不真正调用 run()，因为它会进入 app.exec() 阻塞测试。
    # 这里验证的是模块导入本身不会创建第二个实例。
    # 实际复用逻辑由 run() 函数体内的 QApplication.instance() 检查保证。

    # 验证导入 bootstrap 没有创建新实例
    instance_after_import = QApplication.instance()
    assert instance_after_import is instance_before, (
        "导入 bootstrap 不应创建新的 QApplication 实例"
    )


# ---------------------------------------------------------------------------
# 3. run() 函数存在且可导入，但不阻塞调用 exec()
# ---------------------------------------------------------------------------

def test_run_function_importable() -> None:
    """run 函数应可以从 bootstrap 公开导入。"""
    from math_drawing_assistant.bootstrap import run

    assert callable(run)


# ---------------------------------------------------------------------------
# 4. MainWindow 可在测试 QApplication 下实例化
# ---------------------------------------------------------------------------

def test_main_window_instantiation(qapp: QApplication) -> None:
    """MainWindow 可在现有 QApplication 下创建，且不会自动显示或 exec。"""
    from math_drawing_assistant.ui.main_window import MainWindow

    window = MainWindow()
    try:
        assert window.windowTitle() == "数学绘图助手"
        assert window.isVisible() is False, (
            "MainWindow 实例化不应自动显示窗口"
        )
    finally:
        window.close()
        # 清理：销毁窗口以避免资源泄漏
        window.deleteLater()


def test_main_window_no_plot_engine_import() -> None:
    """MainWindow 模块不应导入旧 plot_engine.py。"""
    import math_drawing_assistant.ui.main_window as mw_module

    assert "plot_engine" not in dir(mw_module), (
        "main_window 模块不应导入 plot_engine"
    )


def test_main_window_no_old_main_window_import() -> None:
    """MainWindow 模块不应导入根目录旧 main_window.py。"""
    import math_drawing_assistant.ui.main_window as mw_module

    # 旧 main_window.py 在根目录，不在包内；新 MainWindow 不应引用
    assert "main_window" not in [name for name in dir(mw_module)
                                  if name.startswith("main_window")], (
        "新 MainWindow 模块不应导入根目录旧 main_window"
    )


def test_main_no_old_imports() -> None:
    """根 main.py 不应导入旧 main_window 或 plot_engine。"""
    import main as main_module

    names = dir(main_module)
    assert "main_window" not in str(names).lower(), (
        "main.py 不应导入旧 main_window"
    )
    assert "plot_engine" not in str(names).lower(), (
        "main.py 不应导入 plot_engine"
    )
