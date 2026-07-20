"""测试夹具与 Qt 无界面平台配置。

仅在自动测试进程内设置 offscreen 平台插件，
不写入正式应用启动代码。
"""

from __future__ import annotations

import os
import sys

import pytest


@pytest.fixture(autouse=True)
def _ensure_offscreen_platform() -> None:
    """确保 Qt 使用 offscreen 平台插件，避免测试时需要图形桌面。"""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def qapp() -> "QApplication":
    """提供独立的 QApplication 实例供测试使用。"""
    from PySide6.QtWidgets import QApplication

    existing = QApplication.instance()
    if existing is not None:
        return existing

    app = QApplication(sys.argv)
    app.setApplicationName("数学绘图助手-test")
    return app
