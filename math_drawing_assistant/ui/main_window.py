"""阶段 3 静态主窗口 —— 完整 UI 布局、信号和可访问性基线。

职责：
1. 创建并布局所有静态控件面板；
2. 声明用户意图信号（generate / clear / copy）；
3. 提供 apply_display_state() 做纯显示映射；
4. 建立 Tab 顺序、焦点、accessible name 和触控尺寸基线；
5. 加载默认 QSS 主题。

不调用 AppController，不创建 PlotSceneRequest，不解析公式，不启动线程。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from math_drawing_assistant.models.state import TaskPhase
from math_drawing_assistant.ui.theme import load_theme
from math_drawing_assistant.ui.widgets import (
    FormulaInputPanel,
    PlotPreview,
    StatusPanel,
    ViewportPanel,
)


class MainWindow(QMainWindow):
    """阶段 3 静态主窗口。

    信号:
        generate_requested: 用户点击"生成图像"或公式输入框 Enter。
        clear_requested: 用户点击"清空"。
        copy_requested: 用户点击"复制图片"。
    """

    generate_requested = Signal()
    clear_requested = Signal()
    copy_requested = Signal()

    # ---- TaskPhase → 状态文字映射 ----
    _PHASE_STATUS_TEXT: dict[TaskPhase, str] = {
        TaskPhase.IDLE: "就绪",
        TaskPhase.RENDERING: "正在生成图像…",
        TaskPhase.CAPTURING: "正在截图…",
        TaskPhase.RECOGNIZING: "正在识别公式…",
        TaskPhase.REVIEWING: "请确认识别结果",
        TaskPhase.SHUTTING_DOWN: "正在关闭…",
    }

    _PHASE_STATUS_LEVEL: dict[TaskPhase, str] = {
        TaskPhase.IDLE: "idle",
        TaskPhase.RENDERING: "processing",
        TaskPhase.CAPTURING: "processing",
        TaskPhase.RECOGNIZING: "processing",
        TaskPhase.REVIEWING: "warning",
        TaskPhase.SHUTTING_DOWN: "warning",
    }

    def __init__(self, theme_name: str = "light") -> None:
        """创建主窗口并加载默认主题。

        Args:
            theme_name: QSS 主题名（默认 ``"light"``）。仅用于测试；
                        正常启动不传参。
        """
        super().__init__()

        self.setWindowTitle("数学绘图助手")
        self.resize(960, 720)
        self.setMinimumSize(640, 480)

        # ---- 加载主题（在创建控件之前）----
        app = QApplication.instance()
        if app is not None:
            try:
                load_theme(app, theme_name)
            except (FileNotFoundError, ValueError):
                # 测试环境可能没有 QSS 文件；静默回退
                pass

        # ---- 创建控件 ----
        self._formula_panel = FormulaInputPanel()
        self._viewport_panel = ViewportPanel()
        self._status_panel = StatusPanel()
        self._plot_preview = PlotPreview()

        # ---- 核心操作按钮 ----
        self._generate_button = QPushButton("生成图像")
        self._generate_button.setObjectName("generateButton")
        self._generate_button.setAccessibleName("生成图像")
        self._generate_button.setAccessibleDescription("根据输入的公式或方程生成数学图像")
        self._generate_button.setDefault(True)
        self._generate_button.setMinimumHeight(44)

        self._clear_button = QPushButton("清空")
        self._clear_button.setObjectName("clearButton")
        self._clear_button.setAccessibleName("清空输入")
        self._clear_button.setAccessibleDescription("清空当前公式输入")
        self._clear_button.setMinimumHeight(44)

        self._copy_button = QPushButton("复制图片")
        self._copy_button.setObjectName("copyButton")
        self._copy_button.setAccessibleName("复制图片")
        self._copy_button.setAccessibleDescription("将生成的图像复制到剪贴板")
        self._copy_button.setMinimumHeight(44)
        self._copy_button.setEnabled(False)  # 无图片时禁用

        # ---- 连接信号（按钮 → MainWindow 信号）----
        self._generate_button.clicked.connect(self.generate_requested)
        self._clear_button.clicked.connect(self.clear_requested)
        self._copy_button.clicked.connect(self.copy_requested)

        # 公式输入框 Enter → 生成意图
        self._formula_panel.submit_requested.connect(self.generate_requested)

        # ---- 构建布局 ----
        self._build_layout()

        # ---- 建立 Tab 顺序 ----
        self._establish_tab_order()

    # ------------------------------------------------------------------
    # 布局
    # ------------------------------------------------------------------

    def _build_layout(self) -> None:
        """构建完整窗口布局：滚动区域 → 垂直三段结构。"""

        # ---- 中央容器 ----
        central = QWidget()
        central.setObjectName("centralContainer")

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # ---- 可滚动内容区 ----
        # Only the content that can grow vertically belongs to this scroll
        # area.  The bottom action row is deliberately a sibling so core
        # actions remain visible in short windows.
        self._content_scroll_area = QScrollArea()
        self._content_scroll_area.setObjectName("contentScrollArea")
        self._content_scroll_area.setWidgetResizable(True)

        scroll_content = QWidget()
        scroll_content.setObjectName("scrollContent")
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(12)

        # 1) 公式输入
        scroll_layout.addWidget(self._formula_panel)

        # 2) 中部：视口设置（左） + 图片预览（右）
        middle = QHBoxLayout()
        middle.setSpacing(12)
        middle.addWidget(self._viewport_panel, 0)  # 不伸缩
        middle.addWidget(self._plot_preview, 1)     # 伸缩
        scroll_layout.addLayout(middle, 1)

        self._content_scroll_area.setWidget(scroll_content)
        main_layout.addWidget(self._content_scroll_area, 1)

        # ---- 固定底部操作区：状态（左） + 操作按钮（右） ----
        self._bottom_action_area = QWidget()
        self._bottom_action_area.setObjectName("bottomActionArea")
        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.addWidget(self._status_panel, 1)
        bottom.addWidget(self._generate_button)
        bottom.addWidget(self._clear_button)
        bottom.addWidget(self._copy_button)
        self._bottom_action_area.setLayout(bottom)
        main_layout.addWidget(self._bottom_action_area)

        self.setCentralWidget(central)

    # ------------------------------------------------------------------
    # Tab 顺序
    # ------------------------------------------------------------------

    def _establish_tab_order(self) -> None:
        """按视觉顺序显式建立 Tab 导航链。"""
        w = [
            self._formula_panel._input,
            self._viewport_panel._mode_combo,
            self._viewport_panel._x_min,
            self._viewport_panel._x_max,
            self._viewport_panel._y_min,
            self._viewport_panel._y_max,
            self._viewport_panel._aspect_combo,
            self._viewport_panel._grid_checkbox,
            self._viewport_panel._image_width,
            self._viewport_panel._image_height,
            self._generate_button,
            self._clear_button,
            self._copy_button,
        ]
        for i in range(len(w) - 1):
            self.setTabOrder(w[i], w[i + 1])

    # ------------------------------------------------------------------
    # 显示状态映射
    # ------------------------------------------------------------------

    def apply_display_state(
        self,
        task_phase: TaskPhase,
        has_plot_result: bool,
    ) -> None:
        """根据外部状态更新按钮、输入控件和状态文字的可用性和显示。

        本方法只做显示映射，不修改或实例化 AppController。

        Args:
            task_phase: 当前 TaskPhase。
            has_plot_result: 是否存在可预览的成功图片结果。
        """
        shutting_down = task_phase is TaskPhase.SHUTTING_DOWN
        is_idle = task_phase is TaskPhase.IDLE

        # ---- 按钮 ----
        self._generate_button.setEnabled(is_idle)
        self._clear_button.setEnabled(not shutting_down)
        self._copy_button.setEnabled(has_plot_result and not shutting_down)

        # ---- 输入控件 ----
        self._formula_panel.set_enabled(not shutting_down)
        self._viewport_panel.set_inputs_enabled(not shutting_down)

        # ---- 状态文字 ----
        status_text = self._PHASE_STATUS_TEXT.get(task_phase, "就绪")
        status_level = self._PHASE_STATUS_LEVEL.get(task_phase, "idle")
        self._status_panel.set_status(status_text, status_level)

    # ------------------------------------------------------------------
    # 便捷属性（供测试和外部读取）
    # ------------------------------------------------------------------

    @property
    def formula_panel(self) -> FormulaInputPanel:
        """公开公式输入面板。"""
        return self._formula_panel

    @property
    def viewport_panel(self) -> ViewportPanel:
        """公开视口设置面板。"""
        return self._viewport_panel

    @property
    def status_panel(self) -> StatusPanel:
        """公开状态面板。"""
        return self._status_panel

    @property
    def plot_preview(self) -> PlotPreview:
        """公开图片预览面板。"""
        return self._plot_preview

    @property
    def generate_button(self) -> QPushButton:
        """生成图像按钮。"""
        return self._generate_button

    @property
    def clear_button(self) -> QPushButton:
        """清空按钮。"""
        return self._clear_button

    @property
    def copy_button(self) -> QPushButton:
        """复制图片按钮。"""
        return self._copy_button
