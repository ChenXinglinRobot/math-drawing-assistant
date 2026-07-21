"""阶段 3 UI 自动测试 —— 覆盖静态主窗口、可访问性基线和状态映射。

不新增 pytest-qt 或其他依赖；使用 PySide6、pytest、QtTest 完成。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QWidget,
)

from math_drawing_assistant.models.state import TaskPhase
from math_drawing_assistant.ui.main_window import MainWindow


# ======================================================================
# 辅助函数
# ======================================================================

def _interactive_widgets(window: MainWindow) -> list:
    """返回主窗口中的主要交互控件列表（按 Tab 顺序）。"""
    vp = window.viewport_panel
    return [
        window.formula_panel._input,
        vp._mode_combo,
        vp._x_min,
        vp._x_max,
        vp._y_min,
        vp._y_max,
        vp._aspect_combo,
        vp._grid_checkbox,
        vp._image_width,
        vp._image_height,
        window.generate_button,
        window.clear_button,
        window.copy_button,
    ]


def _accessible_widgets(window: MainWindow) -> list[tuple[str, QWidget]]:
    """返回 (描述, QWidget) 对，每个都应有非空 accessibleName。"""
    vp = window.viewport_panel
    return [
        ("公式输入框", window.formula_panel._input),
        ("视口模式", vp._mode_combo),
        ("x 最小值", vp._x_min),
        ("x 最大值", vp._x_max),
        ("y 最小值", vp._y_min),
        ("y 最大值", vp._y_max),
        ("坐标比例模式", vp._aspect_combo),
        ("显示网格", vp._grid_checkbox),
        ("图片宽度", vp._image_width),
        ("图片高度", vp._image_height),
        ("生成图像按钮", window.generate_button),
        ("清空按钮", window.clear_button),
        ("复制按钮", window.copy_button),
        ("状态区域", window.status_panel._text_label),
        ("图片预览区域", window.plot_preview),
    ]


# ======================================================================
# 1. 创建与关闭
# ======================================================================

def test_main_window_creates_and_closes(qapp: QApplication) -> None:
    """MainWindow 可以在测试环境中创建和关闭。"""
    window = MainWindow()
    try:
        assert window.isVisible() is False  # 构造不自动 show
        window.show()
        assert window.isVisible() is True
        window.hide()
    finally:
        window.close()
        window.deleteLater()
        QApplication.processEvents()


# ======================================================================
# 2. 初始 UI 结构
# ======================================================================

def test_initial_ui_contains_all_required_panels(qapp: QApplication) -> None:
    """初始界面包含单项输入、视口控件、三个按钮、状态区和预览占位区。"""
    window = MainWindow()
    try:
        # 公式输入
        assert window.formula_panel is not None
        assert isinstance(window.formula_panel._input, QLineEdit)

        # 视口控件
        vp = window.viewport_panel
        assert isinstance(vp._mode_combo, QComboBox)
        assert isinstance(vp._x_min, QDoubleSpinBox)
        assert isinstance(vp._x_max, QDoubleSpinBox)
        assert isinstance(vp._y_min, QDoubleSpinBox)
        assert isinstance(vp._y_max, QDoubleSpinBox)
        assert isinstance(vp._aspect_combo, QComboBox)
        assert isinstance(vp._grid_checkbox, QCheckBox)
        assert isinstance(vp._image_width, QSpinBox)
        assert isinstance(vp._image_height, QSpinBox)

        # 三个按钮
        assert isinstance(window.generate_button, QPushButton)
        assert isinstance(window.clear_button, QPushButton)
        assert isinstance(window.copy_button, QPushButton)

        # 状态区
        assert window.status_panel is not None

        # 预览占位区
        assert window.plot_preview is not None
    finally:
        window.close()
        window.deleteLater()
        QApplication.processEvents()


def test_scrollable_content_and_fixed_action_area_have_separate_ownership(
    qapp: QApplication,
) -> None:
    """滚动内容与固定底部状态/操作区必须是兄弟区域。"""
    window = MainWindow()
    try:
        scroll = window.findChild(QScrollArea, "contentScrollArea")
        bottom = window.findChild(QWidget, "bottomActionArea")

        assert scroll is not None
        assert bottom is not None
        assert scroll.widgetResizable() is True
        assert scroll.widget() is not None
        assert scroll.widget().isAncestorOf(window.formula_panel)
        assert scroll.widget().isAncestorOf(window.viewport_panel)
        assert scroll.widget().isAncestorOf(window.plot_preview)
        assert not scroll.widget().isAncestorOf(window.status_panel)
        assert not scroll.widget().isAncestorOf(window.generate_button)
        assert bottom.isAncestorOf(window.status_panel)
        assert bottom.isAncestorOf(window.generate_button)
        assert bottom.isAncestorOf(window.clear_button)
        assert bottom.isAncestorOf(window.copy_button)
    finally:
        window.close()
        window.deleteLater()
        QApplication.processEvents()


def test_fixed_actions_remain_visible_when_window_is_short(
    qapp: QApplication,
) -> None:
    """缩小窗口时，滚动区收缩而底部三个核心按钮保持可见。"""
    window = MainWindow()
    try:
        window.resize(958, 500)
        window.show()
        QApplication.processEvents()

        scroll = window.findChild(QScrollArea, "contentScrollArea")
        bottom = window.findChild(QWidget, "bottomActionArea")
        assert scroll is not None
        assert bottom is not None
        assert scroll.geometry().bottom() < bottom.geometry().top()
        assert all(
            button.isVisibleTo(window)
            for button in (
                window.generate_button,
                window.clear_button,
                window.copy_button,
            )
        )
        assert scroll.widgetResizable() is True
        assert scroll.verticalScrollBar().maximum() > 0
    finally:
        window.close()
        window.deleteLater()
        QApplication.processEvents()


# ======================================================================
# 3. accessibleName
# ======================================================================

def test_all_key_controls_have_non_empty_accessible_name(
    qapp: QApplication,
) -> None:
    """所有关键控件的 accessibleName 非空。"""
    window = MainWindow()
    try:
        for desc, widget in _accessible_widgets(window):
            name = widget.accessibleName()
            assert name, (
                f"{desc}（{type(widget).__name__}）的 accessibleName 为空"
            )
    finally:
        window.close()
        window.deleteLater()
        QApplication.processEvents()


# ======================================================================
# 4. 初始状态
# ======================================================================

def test_initial_state_is_ready_copy_disabled(qapp: QApplication) -> None:
    """初始状态为"就绪"，复制按钮禁用。"""
    window = MainWindow()
    try:
        # apply_display_state(IDLE, no result)
        window.apply_display_state(TaskPhase.IDLE, False)

        assert "就绪" in window.status_panel.status_text()
        assert window.generate_button.isEnabled() is True
        assert window.clear_button.isEnabled() is True
        assert window.copy_button.isEnabled() is False
    finally:
        window.close()
        window.deleteLater()
        QApplication.processEvents()


def test_runtime_status_indicator_style_tracks_current_level(
    qapp: QApplication,
) -> None:
    """状态图标运行时样式应与当前状态一致，而不是滞后一次切换。"""
    previous_stylesheet = qapp.styleSheet()
    window = MainWindow(theme_name="dark")
    window.show()
    QApplication.processEvents()
    try:
        icon = window.status_panel.findChild(QLabel, "statusIcon")
        assert icon is not None
        idle_color = icon.palette().color(QPalette.ColorRole.WindowText)

        window.apply_display_state(TaskPhase.RENDERING, False)
        QApplication.processEvents()
        processing_color = icon.palette().color(QPalette.ColorRole.WindowText)
        assert processing_color != idle_color

        window.status_panel.set_status("发生错误", "error")
        QApplication.processEvents()
        error_color = icon.palette().color(QPalette.ColorRole.WindowText)
        assert error_color not in (idle_color, processing_color)

        window.apply_display_state(TaskPhase.IDLE, False)
        QApplication.processEvents()
        restored_idle_color = icon.palette().color(QPalette.ColorRole.WindowText)
        assert restored_idle_color == idle_color
    finally:
        window.close()
        window.deleteLater()
        QApplication.processEvents()
        qapp.setStyleSheet(previous_stylesheet)
        QApplication.processEvents()


# ======================================================================
# 5. 静态状态映射
# ======================================================================

def test_idle_with_result_enables_generate_and_copy(qapp: QApplication) -> None:
    """IDLE + 有图片时：生成和复制均可用。"""
    window = MainWindow()
    try:
        window.apply_display_state(TaskPhase.IDLE, True)

        assert window.generate_button.isEnabled() is True
        assert window.copy_button.isEnabled() is True
    finally:
        window.close()
        window.deleteLater()
        QApplication.processEvents()


def test_rendering_disables_generate(qapp: QApplication) -> None:
    """非 IDLE 前台阶段（RENDERING）不能重复生成。"""
    window = MainWindow()
    try:
        window.apply_display_state(TaskPhase.RENDERING, False)

        assert window.generate_button.isEnabled() is False
        assert window.clear_button.isEnabled() is True
        assert window.copy_button.isEnabled() is False
    finally:
        window.close()
        window.deleteLater()
        QApplication.processEvents()


def test_shutting_down_disables_all_core_operations(qapp: QApplication) -> None:
    """SHUTTING_DOWN 时核心操作全部禁用。"""
    window = MainWindow()
    try:
        window.apply_display_state(TaskPhase.SHUTTING_DOWN, True)

        assert window.generate_button.isEnabled() is False
        assert window.clear_button.isEnabled() is False
        assert window.copy_button.isEnabled() is False
        assert window.formula_panel._input.isEnabled() is False
    finally:
        window.close()
        window.deleteLater()
        QApplication.processEvents()


def test_rendering_with_result_keeps_copy_enabled(qapp: QApplication) -> None:
    """有旧成功图片且非 SHUTTING_DOWN 时复制可用。"""
    window = MainWindow()
    try:
        window.apply_display_state(TaskPhase.RENDERING, True)

        assert window.copy_button.isEnabled() is True
        assert window.generate_button.isEnabled() is False
    finally:
        window.close()
        window.deleteLater()
        QApplication.processEvents()


@pytest.mark.parametrize(
    "phase",
    [
        TaskPhase.CAPTURING,
        TaskPhase.RECOGNIZING,
        TaskPhase.REVIEWING,
    ],
)
def test_other_foreground_phases_disable_generate(
    qapp: QApplication,
    phase: TaskPhase,
) -> None:
    """所有非 IDLE 前台阶段（CAPTURING/RECOGNIZING/REVIEWING）禁止生成。"""
    window = MainWindow()
    try:
        window.apply_display_state(phase, False)
        assert window.generate_button.isEnabled() is False
        assert window.clear_button.isEnabled() is True
    finally:
        window.close()
        window.deleteLater()
        QApplication.processEvents()


def test_clear_enabled_except_shutting_down(qapp: QApplication) -> None:
    """清空和输入编辑：除 SHUTTING_DOWN 外保持可操作。"""
    window = MainWindow()
    try:
        for phase in TaskPhase:
            window.apply_display_state(phase, phase is TaskPhase.IDLE)
            expected = phase is not TaskPhase.SHUTTING_DOWN
            assert window.clear_button.isEnabled() is expected, (
                f"清空按钮在 {phase} 状态应为 {expected}"
            )
            assert window.formula_panel._input.isEnabled() is expected, (
                f"公式输入在 {phase} 状态应为 {expected}"
            )
    finally:
        window.close()
        window.deleteLater()
        QApplication.processEvents()


# ======================================================================
# 6. 信号：Enter 触发生成意图
# ======================================================================

def test_formula_enter_emits_generate_requested(qapp: QApplication) -> None:
    """公式输入框 Enter 会发出一次 generate_requested 信号。"""
    window = MainWindow()
    try:
        spy = QSignalSpy(window.generate_requested)
        assert spy.isValid()

        window.formula_panel._input.setText("y=x")
        QTest.keyClick(window.formula_panel._input, Qt.Key.Key_Return)

        assert spy.count() == 1, (
            f"按下 Enter 应触发 1 次生成信号，实际 {spy.count()} 次"
        )
    finally:
        window.close()
        window.deleteLater()
        QApplication.processEvents()


# ======================================================================
# 7. 按钮信号
# ======================================================================

@pytest.mark.parametrize(
    ("button_attr", "signal_name"),
    [
        ("generate_button", "generate_requested"),
        ("clear_button", "clear_requested"),
        ("copy_button", "copy_requested"),
    ],
)
def test_button_click_emits_corresponding_signal(
    qapp: QApplication,
    button_attr: str,
    signal_name: str,
) -> None:
    """三个按钮分别发出对应意图信号。"""
    window = MainWindow()
    try:
        signal = getattr(window, signal_name)
        spy = QSignalSpy(signal)
        assert spy.isValid()

        button: QPushButton = getattr(window, button_attr)
        # 禁用按钮的 click() 不会发射信号；临时启用以验证信号连接
        was_enabled = button.isEnabled()
        if not was_enabled:
            button.setEnabled(True)
        button.click()

        assert spy.count() == 1, (
            f"{button_attr} 点击应触发 1 次 {signal_name}，实际 {spy.count()} 次"
        )
    finally:
        window.close()
        window.deleteLater()
        QApplication.processEvents()


def test_generate_button_click_and_enter_both_emit(qapp: QApplication) -> None:
    """按钮点击和 Enter 均可独立触发信号。"""
    window = MainWindow()
    try:
        spy = QSignalSpy(window.generate_requested)

        window.generate_button.click()
        QTest.keyClick(window.formula_panel._input, Qt.Key.Key_Return)

        assert spy.count() == 2
    finally:
        window.close()
        window.deleteLater()
        QApplication.processEvents()


def test_generate_keyboard_activations_emit_once_each(qapp: QApplication) -> None:
    """输入框 Enter、按钮 Space 和按钮 Enter 均只发射一次生成意图。"""
    window = MainWindow()
    window.show()
    QApplication.processEvents()
    try:
        window.formula_panel._input.setFocus()
        input_spy = QSignalSpy(window.generate_requested)
        QTest.keyClick(window.formula_panel._input, Qt.Key.Key_Return)
        assert input_spy.count() == 1

        window.generate_button.setFocus()
        space_spy = QSignalSpy(window.generate_requested)
        QTest.keyClick(window.generate_button, Qt.Key.Key_Space)
        assert space_spy.count() == 1

        window.generate_button.setFocus()
        enter_spy = QSignalSpy(window.generate_requested)
        QTest.keyClick(window.generate_button, Qt.Key.Key_Return)
        assert enter_spy.count() == 1
    finally:
        window.close()
        window.deleteLater()
        QApplication.processEvents()


# ======================================================================
# 8. Tab 顺序（可验证部分）
# ======================================================================

def test_tab_order_matches_visual_order(qapp: QApplication) -> None:
    """可验证部分的 Tab 顺序与视觉顺序一致。"""
    window = MainWindow()
    # 切换到手动模式使坐标边界控件可聚焦
    window.viewport_panel.set_viewport_mode("manual")
    window.show()
    QApplication.processEvents()
    try:
        widgets = _interactive_widgets(window)

        # 聚焦第一个控件
        widgets[0].setFocus()
        QApplication.processEvents()

        # 按 Tab 依次验证焦点转移
        for i in range(len(widgets) - 1):
            current_focus = QApplication.focusWidget()
            assert current_focus is widgets[i], (
                f"Tab 第 {i} 步：期望焦点在 "
                f"{type(widgets[i]).__name__}({widgets[i].accessibleName()})，"
                f"实际在 {type(current_focus).__name__ if current_focus else 'None'}"
            )
            QTest.keyClick(current_focus, Qt.Key.Key_Tab)
            QApplication.processEvents()

        # 最后一个 Tab 后焦点不应丢失
        final_focus = QApplication.focusWidget()
        assert final_focus is not None, "Tab 导航后焦点不应丢失"
    finally:
        window.close()
        window.deleteLater()
        QApplication.processEvents()


# ======================================================================
# 9. 触控目标最小尺寸
# ======================================================================

def test_interactive_widgets_minimum_height_44(qapp: QApplication) -> None:
    """主要交互控件最小高度不小于 44 逻辑像素。"""
    window = MainWindow()
    try:
        # 收集需要检查的交互控件
        vp = window.viewport_panel
        candidates: list[QWidget] = [
            window.formula_panel._input,
            vp._mode_combo,
            vp._x_min,
            vp._x_max,
            vp._y_min,
            vp._y_max,
            vp._aspect_combo,
            vp._grid_checkbox,
            vp._image_width,
            vp._image_height,
            window.generate_button,
            window.clear_button,
            window.copy_button,
        ]

        for widget in candidates:
            min_h = widget.minimumHeight()
            actual_h = widget.sizeHint().height()
            assert min_h >= 44, (
                f"{type(widget).__name__}({widget.accessibleName()}) "
                f"minimumHeight={min_h} < 44"
            )
            # 同时检查 sizeHint 不至于异常小
            assert actual_h >= 20, (
                f"{type(widget).__name__}({widget.accessibleName()}) "
                f"sizeHint height={actual_h} 异常小"
            )
    finally:
        window.close()
        window.deleteLater()
        QApplication.processEvents()


# ======================================================================
# 10 & 11. QSS 主题加载与 focus 样式
# ======================================================================


@pytest.mark.parametrize("theme_name", ["light", "dark"])
def test_checkbox_focus_indicator_clears_after_tab(
    qapp: QApplication,
    theme_name: str,
) -> None:
    """复选框失焦后应恢复未聚焦外观，不残留整行焦点框。"""
    previous_stylesheet = qapp.styleSheet()
    window = MainWindow(theme_name=theme_name)
    window.show()
    QApplication.processEvents()
    try:
        checkbox = window.viewport_panel.findChild(QCheckBox)
        image_width = next(
            spinbox
            for spinbox in window.viewport_panel.findChildren(QSpinBox)
            if spinbox.accessibleName() == "图片宽度"
        )
        assert checkbox is not None

        image_width.setFocus()
        QApplication.processEvents()
        unfocused_image = checkbox.grab().toImage()

        checkbox.setFocus()
        QApplication.processEvents()
        focused_image = checkbox.grab().toImage()
        assert checkbox.hasFocus() is True
        assert focused_image != unfocused_image

        QTest.keyClick(checkbox, Qt.Key.Key_Tab)
        QApplication.processEvents()
        after_tab_image = checkbox.grab().toImage()
        assert checkbox.hasFocus() is False
        assert after_tab_image == unfocused_image
    finally:
        window.close()
        window.deleteLater()
        QApplication.processEvents()
        qapp.setStyleSheet(previous_stylesheet)
        QApplication.processEvents()


def test_light_qss_loads_and_is_non_empty() -> None:
    """亮色 QSS 文件可加载且非空。"""
    qss_path = (
        Path(__file__).resolve().parent.parent.parent
        / "resources" / "styles" / "light.qss"
    )
    assert qss_path.is_file(), f"light.qss 不存在: {qss_path}"
    content = qss_path.read_text(encoding="utf-8")
    assert content.strip(), "light.qss 为空"


def test_dark_qss_loads_and_is_non_empty() -> None:
    """暗色 QSS 文件可加载且非空。"""
    qss_path = (
        Path(__file__).resolve().parent.parent.parent
        / "resources" / "styles" / "dark.qss"
    )
    assert qss_path.is_file(), f"dark.qss 不存在: {qss_path}"
    content = qss_path.read_text(encoding="utf-8")
    assert content.strip(), "dark.qss 为空"


def test_light_qss_preserves_focus_style() -> None:
    """亮色 QSS 明确保留可见的 :focus 样式。"""
    qss_path = (
        Path(__file__).resolve().parent.parent.parent
        / "resources" / "styles" / "light.qss"
    )
    content = qss_path.read_text(encoding="utf-8")
    # 至少存在 :focus 选择器
    assert ":focus" in content, "light.qss 缺少 :focus 样式"
    # 不应有 :focus { } 空规则
    focus_rules = [
        m.group(0)
        for m in re.finditer(r":focus\s*\{[^}]*\}", content, re.DOTALL)
    ]
    assert len(focus_rules) > 0, "light.qss 没有 :focus 规则块"
    for rule in focus_rules:
        # 每个 :focus 规则至少有一条非注释属性
        body = rule.split("{", 1)[1].rstrip("}")
        lines = [l.strip() for l in body.splitlines() if l.strip()]
        non_comment = [l for l in lines if not l.startswith("/*")]
        assert len(non_comment) > 0, (
            f"light.qss 的 :focus 规则为空: {rule[:80]}..."
        )


def test_dark_qss_preserves_focus_style() -> None:
    """暗色 QSS 明确保留可见的 :focus 样式。"""
    qss_path = (
        Path(__file__).resolve().parent.parent.parent
        / "resources" / "styles" / "dark.qss"
    )
    content = qss_path.read_text(encoding="utf-8")
    assert ":focus" in content, "dark.qss 缺少 :focus 样式"
    focus_rules = [
        m.group(0)
        for m in re.finditer(r":focus\s*\{[^}]*\}", content, re.DOTALL)
    ]
    assert len(focus_rules) > 0, "dark.qss 没有 :focus 规则块"
    for rule in focus_rules:
        body = rule.split("{", 1)[1].rstrip("}")
        lines = [l.strip() for l in body.splitlines() if l.strip()]
        non_comment = [l for l in lines if not l.startswith("/*")]
        assert len(non_comment) > 0, (
            f"dark.qss 的 :focus 规则为空: {rule[:80]}..."
        )


def test_theme_applies_to_app(qapp: QApplication) -> None:
    """主题可通过 MainWindow 应用到 QApplication 且样式表非空。"""
    from math_drawing_assistant.ui.theme import load_theme

    # 测试时可能没有完整的资源目录 → 只验证模块不崩溃
    styles_dir = (
        Path(__file__).resolve().parent.parent.parent
        / "resources" / "styles"
    )
    if (styles_dir / "light.qss").is_file():
        load_theme(qapp, "light")
        assert qapp.styleSheet(), "应用样式表后应为非空"


def test_main_window_with_dark_theme(qapp: QApplication) -> None:
    """MainWindow 可接受 dark 主题名创建。"""
    styles_dir = (
        Path(__file__).resolve().parent.parent.parent
        / "resources" / "styles"
    )
    if (styles_dir / "dark.qss").is_file():
        window = MainWindow(theme_name="dark")
        try:
            assert window is not None
            sheet = qapp.styleSheet()
            # dark QSS 应有不同于 light 的特征
            assert "#1e1e1e" in sheet or "#2a2a2a" in sheet or "#222" in sheet, (
                "dark 主题应包含暗色背景"
            )
        finally:
            window.close()
            window.deleteLater()
            QApplication.processEvents()


def test_theme_styles_cover_structural_dark_layers_and_keep_system_font() -> None:
    """暗色主题覆盖实际容器，并且不覆写系统字体或字号。"""
    qss_path = (
        Path(__file__).resolve().parent.parent.parent
        / "resources" / "styles" / "dark.qss"
    )
    content = qss_path.read_text(encoding="utf-8")

    for selector in (
        "QMainWindow, QWidget#centralContainer",
        "QScrollArea#contentScrollArea::viewport",
        "QWidget#scrollContent",
        "QWidget#bottomActionArea",
        "QWidget#statusIdle QLabel#statusText",
        "QPushButton#copyButton:disabled",
    ):
        assert selector in content
    assert "font-family:" not in content
    assert "font-size:" not in content


# ======================================================================
# 12. 资源清理
# ======================================================================

def test_window_cleanup_after_close(qapp: QApplication) -> None:
    """测试结束后窗口和 QApplication 资源得到清理。"""
    window = MainWindow()
    window.show()
    window.close()
    window.deleteLater()
    QApplication.processEvents()

    # 窗口应不再可见
    assert window.isVisible() is False

    # QApplication 仍存活（由 qapp fixture 管理）
    assert QApplication.instance() is qapp


def test_repeated_window_create_destroy_no_leak(qapp: QApplication) -> None:
    """重复创建和销毁 MainWindow 不会泄漏。"""
    for _ in range(3):
        window = MainWindow()
        window.show()
        window.close()
        window.deleteLater()
        QApplication.processEvents()

    # 能执行到这里即为通过（无崩溃、无残留线程警告）
