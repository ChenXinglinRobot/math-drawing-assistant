import numpy as np
from matplotlib.figure import Figure


def create_preview_figure() -> Figure:
    """创建初始的空白预览画布。"""

    figure = Figure(figsize=(7, 5), tight_layout=True)
    axes = figure.subplots()

    axes.text(
        0.5,
        0.5,
        "图像预览区域",
        horizontalalignment="center",
        verticalalignment="center",
        transform=axes.transAxes,
        fontsize=16,
    )
    axes.set_axis_off()

    return figure


def draw_formula(figure: Figure, formula: str) -> None:
    """在指定 Figure 中绘制公式。

    V0.1 当前只支持 y=x^2。
    """

    normalized_formula = formula.replace(" ", "").lower()

    if normalized_formula != "y=x^2":
        raise ValueError("当前版本暂时只支持公式：y=x^2")

    x = np.linspace(-5, 5, 400)
    y = x**2

    figure.clear()
    axes = figure.subplots()

    axes.plot(x, y, label="y = x²")
    axes.axhline(0, linewidth=0.8)
    axes.axvline(0, linewidth=0.8)

    axes.set_title("y = x²")
    axes.set_xlabel("x")
    axes.set_ylabel("y")
    axes.grid(True, alpha=0.3)
    axes.legend()

    figure.tight_layout()