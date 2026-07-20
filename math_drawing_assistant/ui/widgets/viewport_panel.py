"""共享视口设置面板 —— 只收集和展示静态值。

不执行数学验证、自动范围计算或构造 PlotSceneRequest。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class ViewportPanel(QGroupBox):
    """共享视口设置分组控件。

    包含视口模式、四个坐标边界、坐标比例、网格开关及图片尺寸。
    所有值均可通过公共方法读写，不做范围验证。
    """

    # ---- 视口模式选项 ----
    VIEWPORT_MODES = {
        "auto": "自动",
        "manual": "手动",
    }

    # ---- 坐标比例选项 ----
    ASPECT_OPTIONS = {
        "auto": "自动",
        "equal": "等比例",
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("视口设置", parent)

        # ------------------------------------------------------------------
        # 视口模式
        # ------------------------------------------------------------------
        self._mode_combo = QComboBox()
        self._mode_combo.setAccessibleName("视口模式")
        self._mode_combo.setAccessibleDescription("选择自动或手动设置坐标范围")
        self._mode_combo.setMinimumHeight(44)
        for key, label in self.VIEWPORT_MODES.items():
            self._mode_combo.addItem(label, key)

        # ------------------------------------------------------------------
        # 四个坐标边界
        # ------------------------------------------------------------------
        self._x_min = self._create_bound_spinbox("x 最小值", "x 轴最小坐标值")
        self._x_max = self._create_bound_spinbox("x 最大值", "x 轴最大坐标值")
        self._y_min = self._create_bound_spinbox("y 最小值", "y 轴最小坐标值")
        self._y_max = self._create_bound_spinbox("y 最大值", "y 轴最大坐标值")

        # 默认自动模式 → 边界控件禁用
        self._x_min.setEnabled(False)
        self._x_max.setEnabled(False)
        self._y_min.setEnabled(False)
        self._y_max.setEnabled(False)

        # ------------------------------------------------------------------
        # 坐标比例
        # ------------------------------------------------------------------
        self._aspect_combo = QComboBox()
        self._aspect_combo.setAccessibleName("坐标比例模式")
        self._aspect_combo.setAccessibleDescription("选择自动或等比例坐标")
        self._aspect_combo.setMinimumHeight(44)
        for key, label in self.ASPECT_OPTIONS.items():
            self._aspect_combo.addItem(label, key)

        # ------------------------------------------------------------------
        # 显示网格
        # ------------------------------------------------------------------
        self._grid_checkbox = QCheckBox("显示网格")
        self._grid_checkbox.setAccessibleName("显示网格")
        self._grid_checkbox.setAccessibleDescription("切换坐标网格显示")
        self._grid_checkbox.setMinimumHeight(44)
        self._grid_checkbox.setChecked(True)

        # ------------------------------------------------------------------
        # 图片宽度与高度
        # ------------------------------------------------------------------
        self._image_width = QSpinBox()
        self._image_width.setAccessibleName("图片宽度")
        self._image_width.setAccessibleDescription("输出图片的宽度（像素）")
        self._image_width.setRange(200, 4096)
        self._image_width.setValue(800)
        self._image_width.setSuffix(" px")
        self._image_width.setMinimumHeight(44)

        self._image_height = QSpinBox()
        self._image_height.setAccessibleName("图片高度")
        self._image_height.setAccessibleDescription("输出图片的高度（像素）")
        self._image_height.setRange(200, 4096)
        self._image_height.setValue(600)
        self._image_height.setSuffix(" px")
        self._image_height.setMinimumHeight(44)

        # ------------------------------------------------------------------
        # 布局
        # ------------------------------------------------------------------
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )

        mode_row = QVBoxLayout()
        mode_row.setContentsMargins(0, 0, 0, 0)
        mode_row.addWidget(self._mode_combo)
        form.addRow("视口模式：", mode_row)

        form.addRow("x 最小值：", self._x_min)
        form.addRow("x 最大值：", self._x_max)
        form.addRow("y 最小值：", self._y_min)
        form.addRow("y 最大值：", self._y_max)
        form.addRow("坐标比例：", self._aspect_combo)
        form.addRow(self._grid_checkbox)
        form.addRow("图片宽度：", self._image_width)
        form.addRow("图片高度：", self._image_height)

        self.setLayout(form)

        # ------------------------------------------------------------------
        # 连接：自动/手动切换边界控件启用状态
        # ------------------------------------------------------------------
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    @staticmethod
    def _create_bound_spinbox(name: str, description: str) -> QDoubleSpinBox:
        """创建一个统一的坐标边界微调框。"""
        box = QDoubleSpinBox()
        box.setAccessibleName(name)
        box.setAccessibleDescription(description)
        box.setRange(-1_000_000.0, 1_000_000.0)
        box.setDecimals(2)
        box.setValue(-10.0 if "最小" in name else 10.0)
        box.setMinimumHeight(44)
        box.setSizePolicy(
            QSizePolicy.Policy.MinimumExpanding,
            QSizePolicy.Policy.Fixed,
        )
        return box

    def _on_mode_changed(self) -> None:
        manual = self._mode_combo.currentData() == "manual"
        self._x_min.setEnabled(manual)
        self._x_max.setEnabled(manual)
        self._y_min.setEnabled(manual)
        self._y_max.setEnabled(manual)

    # ------------------------------------------------------------------
    # 公共读取接口
    # ------------------------------------------------------------------

    def viewport_mode(self) -> str:
        """返回 ``"auto"`` 或 ``"manual"``。"""
        data = self._mode_combo.currentData()
        return data if isinstance(data, str) else "auto"

    def set_viewport_mode(self, mode: str) -> None:
        index = self._mode_combo.findData(mode)
        if index >= 0:
            self._mode_combo.setCurrentIndex(index)

    def x_min(self) -> float:
        return self._x_min.value()

    def set_x_min(self, value: float) -> None:
        self._x_min.setValue(value)

    def x_max(self) -> float:
        return self._x_max.value()

    def set_x_max(self, value: float) -> None:
        self._x_max.setValue(value)

    def y_min(self) -> float:
        return self._y_min.value()

    def set_y_min(self, value: float) -> None:
        self._y_min.setValue(value)

    def y_max(self) -> float:
        return self._y_max.value()

    def set_y_max(self, value: float) -> None:
        self._y_max.setValue(value)

    def aspect_mode(self) -> str:
        """返回 ``"auto"`` 或 ``"equal"``。"""
        data = self._aspect_combo.currentData()
        return data if isinstance(data, str) else "auto"

    def set_aspect_mode(self, mode: str) -> None:
        index = self._aspect_combo.findData(mode)
        if index >= 0:
            self._aspect_combo.setCurrentIndex(index)

    def show_grid(self) -> bool:
        return self._grid_checkbox.isChecked()

    def set_show_grid(self, show: bool) -> None:
        self._grid_checkbox.setChecked(show)

    def image_width(self) -> int:
        return self._image_width.value()

    def set_image_width(self, width: int) -> None:
        self._image_width.setValue(width)

    def image_height(self) -> int:
        return self._image_height.value()

    def set_image_height(self, height: int) -> None:
        self._image_height.setValue(height)

    # ------------------------------------------------------------------
    # 批量启用/禁用
    # ------------------------------------------------------------------

    def set_inputs_enabled(self, enabled: bool) -> None:
        """批量设置所有用户可操作控件的启用状态。"""
        self._mode_combo.setEnabled(enabled)
        self._aspect_combo.setEnabled(enabled)
        self._grid_checkbox.setEnabled(enabled)
        self._image_width.setEnabled(enabled)
        self._image_height.setEnabled(enabled)
        # 边界控件是否可用由当前模式决定
        if enabled and self.viewport_mode() == "manual":
            self._x_min.setEnabled(True)
            self._x_max.setEnabled(True)
            self._y_min.setEnabled(True)
            self._y_max.setEnabled(True)
        elif not enabled:
            self._x_min.setEnabled(False)
            self._x_max.setEnabled(False)
            self._y_min.setEnabled(False)
            self._y_max.setEnabled(False)
