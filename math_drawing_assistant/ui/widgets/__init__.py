"""Stage-3 static UI widget panels.

每个模块只负责创建控件、读取/展示静态值、发出用户意图信号、应用显示状态。
不调用 AppController，不创建 PlotSceneRequest，不解析公式，不启动线程。
"""

from math_drawing_assistant.ui.widgets.formula_input_panel import FormulaInputPanel
from math_drawing_assistant.ui.widgets.plot_preview import PlotPreview
from math_drawing_assistant.ui.widgets.status_panel import StatusPanel
from math_drawing_assistant.ui.widgets.viewport_panel import ViewportPanel

__all__ = [
    "FormulaInputPanel",
    "PlotPreview",
    "StatusPanel",
    "ViewportPanel",
]
