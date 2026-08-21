"""正式 M1 主窗口：收集快照、展示结果并守住 GUI 线程边界。

职责：
1. 创建并布局所有静态控件面板；
2. 声明用户意图信号（generate / clear / copy）；
3. 把可选 AppController 的派生状态映射到控件；
4. 建立 Tab 顺序、焦点、accessible name 和触控尺寸基线；
5. 加载默认 QSS 主题。

不解析公式，不构造 Engine 对象，不启动线程，不直接访问 QClipboard。
"""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt, Signal, Slot
from PySide6.QtGui import QCloseEvent
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

from math_drawing_assistant.app_controller import (
    AppController,
    CopyPreparationStatus,
    RenderResultDisposition,
)
from math_drawing_assistant.models.errors import ErrorCode
from math_drawing_assistant.models.results import ConcretePlotType, PlotSceneResult
from math_drawing_assistant.models.state import TaskPhase
from math_drawing_assistant.services.clipboard_service import (
    ClipboardService,
    ClipboardWriteStatus,
)
from math_drawing_assistant.ui.theme import load_theme
from math_drawing_assistant.ui.widgets import (
    FormulaInputPanel,
    PlotPreview,
    StatusPanel,
    ViewportPanel,
)


class MainWindow(QMainWindow):
    """M1 main window with an optional controller for no-argument compatibility.

    信号:
        generate_requested: 用户点击"生成图像"或公式输入框 Enter。
        clear_requested: 用户点击"清空"。
        copy_requested: 用户点击"复制图片"。
    """

    generate_requested = Signal()
    clear_requested = Signal()
    copy_requested = Signal()

    COPY_FEEDBACK_DURATION_MS = 1500

    _PLOT_TYPE_LABELS: dict[ConcretePlotType, str] = {
        ConcretePlotType.EXPLICIT_FUNCTION: "显函数",
        ConcretePlotType.GENERAL_LINE: "一般直线",
        ConcretePlotType.CIRCLE: "圆",
        ConcretePlotType.ELLIPSE: "椭圆",
        ConcretePlotType.HYPERBOLA: "双曲线",
        ConcretePlotType.PARABOLA: "抛物线",
    }

    _WARNING_MESSAGES: dict[str, str] = {
        "auto_viewport_fallback": "自动视口探测不可靠，已使用安全范围。",
        "partial_domain_omitted": "部分定义域没有可绘制值，已省略不可绘制部分。",
        "dense_oscillation_suspected": (
            "当前区间内可能包含密集振荡，请确认是否需要调整范围。"
        ),
        "viewport_clipped": "曲线在当前视口中被裁切。",
        "sampling_precision_limited": "当前采样精度受限，图像可能不够精确。",
    }

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

    def __init__(
        self,
        theme_name: str = "light",
        *,
        controller: AppController | None = None,
        clipboard_service: ClipboardService | None = None,
    ) -> None:
        """创建主窗口并加载默认主题。

        Args:
            theme_name: QSS 主题名（默认 ``"light"``）。仅用于测试；
                        正常启动不传参。
        """
        super().__init__()
        self._controller = controller
        self._clipboard_service = clipboard_service

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

        self._copy_feedback_timer = QTimer(self)
        self._copy_feedback_timer.setSingleShot(True)
        self._copy_feedback_timer.timeout.connect(self._restore_after_copy_feedback)

        # ---- 连接信号（按钮 → MainWindow 信号）----
        self._generate_button.clicked.connect(self.generate_requested)
        self._clear_button.clicked.connect(self.clear_requested)
        self._copy_button.clicked.connect(self.copy_requested)

        # 公式输入框 Enter → 生成意图
        self._formula_panel.submit_requested.connect(self.generate_requested)

        # MainWindow owns the one UI snapshot/revision adapter.  With no
        # controller these connections retain the stage-3 signal-only mode.
        self.generate_requested.connect(self._handle_generate_requested)
        self.clear_requested.connect(self._handle_clear_requested)
        self.copy_requested.connect(self._handle_copy_requested)
        self._formula_panel.scene_edited.connect(self._handle_scene_edited)
        self._viewport_panel.scene_edited.connect(self._handle_scene_edited)

        # ---- 构建布局 ----
        self._build_layout()

        # ---- 建立 Tab 顺序 ----
        self._establish_tab_order()

        if self._controller is not None:
            self._sync_controller_state()

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
        render_allowed = task_phase in (TaskPhase.IDLE, TaskPhase.RENDERING)

        # ---- 按钮 ----
        self._generate_button.setEnabled(render_allowed)
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
    # M1 dynamic flow
    # ------------------------------------------------------------------

    @Slot()
    def _handle_scene_edited(self) -> None:
        self._cancel_copy_feedback()
        controller = self._controller
        if controller is None:
            return
        try:
            controller.mark_scene_edited()
        except RuntimeError:
            # A late widget signal cannot reopen work after shutdown begins.
            return
        self._sync_controller_state()

    @Slot()
    def _handle_clear_requested(self) -> None:
        self._cancel_copy_feedback()
        self._formula_panel.clear()
        self._formula_panel.set_focus()

    @Slot()
    def _handle_generate_requested(self) -> None:
        self._cancel_copy_feedback()
        controller = self._controller
        if controller is None:
            return

        # Read every UI value exactly once so one explicit action produces one
        # immutable request snapshot even if queued edits follow immediately.
        formula_text = self._formula_panel.text()
        viewport_mode = self._viewport_panel.viewport_mode()
        x_min = self._viewport_panel.x_min()
        x_max = self._viewport_panel.x_max()
        y_min = self._viewport_panel.y_min()
        y_max = self._viewport_panel.y_max()
        aspect_request = self._viewport_panel.aspect_mode()
        show_grid = self._viewport_panel.show_grid()
        image_width = self._viewport_panel.image_width()
        image_height = self._viewport_panel.image_height()

        try:
            controller.create_m1_render_request(
                formula_text=formula_text,
                viewport_mode=viewport_mode,
                x_min=x_min,
                x_max=x_max,
                y_min=y_min,
                y_max=y_max,
                aspect_request=aspect_request,
                show_grid=show_grid,
                image_width=image_width,
                image_height=image_height,
            )
        except (RuntimeError, TypeError, ValueError):
            notice = controller.last_error_notice
            message = (
                notice.user_message
                if notice is not None
                else "无法开始生成，请检查公式和视口设置。"
            )
            self._sync_controller_state()
            self._status_panel.set_status(message, "error")
            return

        self._sync_controller_state()

    @Slot()
    def _handle_copy_requested(self) -> None:
        """Execute the Controller-approved copy path exactly once per intent."""

        controller = self._controller
        if controller is None:
            return

        preparation = controller.prepare_copy_candidate()
        if preparation.status is CopyPreparationStatus.SHUTTING_DOWN:
            self._cancel_copy_feedback()
            self._sync_controller_state()
            return
        if preparation.candidate is None:
            self._show_copy_feedback("暂无可复制图片", "warning")
            return

        service = self._clipboard_service
        if service is None:
            self._show_copy_feedback("无法写入剪贴板，请重试", "error")
            return

        outcome = service.write_candidate(preparation.candidate)
        if outcome.status is ClipboardWriteStatus.INVALID_IMAGE:
            self._show_copy_feedback("图片数据无效，复制失败", "error")
            return
        if outcome.status is ClipboardWriteStatus.WRITE_EXCEPTION:
            self._show_copy_feedback("无法写入剪贴板，请重试", "error")
            return

        if controller.task_phase is TaskPhase.RENDERING:
            message = "已复制上一张成功图；新图仍在生成"
            level = "warning"
        elif controller.last_error_notice is not None:
            message = "已复制上一张成功图；本次生成失败"
            level = "warning"
        elif preparation.candidate.is_stale:
            message = "已复制上一张成功图；当前输入已修改"
            level = "warning"
        else:
            message = "图片已写入剪贴板"
            level = "success"
        self._show_copy_feedback(message, level)

    @Slot(object)
    def handle_render_result(
        self,
        result: PlotSceneResult,
    ) -> RenderResultDisposition | None:
        """Apply the controller's sole result classification on the GUI thread."""

        controller = self._controller
        if controller is None:
            return None

        self._cancel_copy_feedback()
        disposition = controller.handle_render_result(result)
        if disposition is RenderResultDisposition.IGNORED_OBSOLETE:
            # A same-request result can become obsolete because the scene was
            # edited while it ran.  The controller then finishes that request
            # without accepting its payload, so refresh the phase/stale UI.
            self._sync_controller_state()
            return disposition

        if disposition is RenderResultDisposition.ACCEPTED_SUCCESS:
            accepted = controller.last_successful_result
            if accepted is None or accepted.png_bytes is None:
                self._status_panel.set_status("无法显示生成的图像。", "error")
                return disposition
            item_result = (
                accepted.item_results[0]
                if len(accepted.item_results) == 1
                else None
            )
            if (
                item_result is not None
                and item_result.concrete_plot_type in self._PLOT_TYPE_LABELS
                and item_result.normalized_input
            ):
                self._plot_preview.set_result(
                    accepted.png_bytes,
                    plot_type=self._PLOT_TYPE_LABELS[
                        item_result.concrete_plot_type
                    ],
                    normalized_input=item_result.normalized_input,
                )
            else:
                # Compatibility for historical successful scene fixtures that
                # predate accepted-result metadata. Production M1/M1.5 results
                # always take the summary-bearing branch above.
                self._plot_preview.set_png_bytes(accepted.png_bytes)
            self._status_panel.set_warning_messages(
                tuple(
                    self._WARNING_MESSAGES.get(
                        code,
                        "绘图成功，但有一项提示需要注意。",
                    )
                    for code in accepted.warnings
                )
            )

        self._sync_controller_state()
        return disposition

    def _sync_controller_state(self) -> None:
        controller = self._controller
        if controller is None:
            return

        self.apply_display_state(
            controller.task_phase,
            controller.copy_enabled,
        )
        if controller.has_plot_result:
            if controller.task_phase is TaskPhase.RENDERING:
                self._plot_preview.set_stale(
                    True,
                    "正在生成新图，当前仍显示上一张成功图片。",
                )
            elif controller.last_error_notice is not None:
                self._plot_preview.set_stale(
                    True,
                    "本次生成失败，预览仍是上一张成功图片。",
                )
            else:
                self._plot_preview.set_stale(
                    controller.result_is_stale,
                    "输入已修改，当前图像对应旧输入。",
                )
        else:
            self._plot_preview.set_stale(False)

        if controller.task_phase is TaskPhase.SHUTTING_DOWN:
            if controller.last_error_notice is not None:
                self._status_panel.set_status(
                    controller.last_error_notice.user_message,
                    "error",
                )
            return
        if controller.task_phase is TaskPhase.RENDERING:
            if controller.has_plot_result:
                self._status_panel.set_status(
                    "正在生成图像，当前仍显示上一张成功图片。",
                    "processing",
                )
            return
        if controller.last_error_notice is not None:
            message = self._failure_message(controller.last_error_notice)
            if controller.has_plot_result:
                retained_notice = "本次生成失败，预览仍是上一张成功图片。"
                if retained_notice not in message:
                    message = f"{message} {retained_notice}"
            self._status_panel.set_status(
                message,
                "error",
            )
        elif controller.result_is_stale:
            self._status_panel.set_status("输入已修改，当前图像对应旧输入。", "warning")
        elif controller.is_ready:
            self._status_panel.set_status("图像生成成功。", "success")

    def _show_copy_feedback(self, message: str, level: str) -> None:
        self._copy_feedback_timer.stop()
        self._status_panel.set_status(message, level)
        self._copy_feedback_timer.start(self.COPY_FEEDBACK_DURATION_MS)

    @staticmethod
    def _failure_message(notice: object) -> str:
        """Apply the narrow F-GUI-01 no-visible product wording ruling."""

        if getattr(notice, "code", None) is ErrorCode.NO_VISIBLE_CURVE:
            return "当前视口内没有发现曲线，请调整 x、y 范围。"
        return str(getattr(notice, "user_message", "本次生成失败。"))

    def _cancel_copy_feedback(self) -> None:
        if self._copy_feedback_timer.isActive():
            self._copy_feedback_timer.stop()

    @Slot()
    def _restore_after_copy_feedback(self) -> None:
        self._sync_controller_state()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Keep the event loop alive unless orderly Actor shutdown succeeds."""

        self._cancel_copy_feedback()
        controller = self._controller
        if controller is None:
            super().closeEvent(event)
            return

        stopped = controller.shutdown()
        self._sync_controller_state()
        if stopped:
            event.accept()
        else:
            event.ignore()

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

    @property
    def controller(self) -> AppController | None:
        """Return the bound controller without creating a compatibility one."""

        return self._controller

    @property
    def clipboard_service(self) -> ClipboardService | None:
        """Return the injected service without creating another clipboard path."""

        return self._clipboard_service
