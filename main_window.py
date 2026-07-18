from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from matplotlib.backends.backend_qtagg import FigureCanvas

from plot_engine import create_preview_figure, draw_formula


class MainWindow(QMainWindow):
    """数学绘图助手的主窗口。"""

    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("数学绘图助手")
        self.resize(900, 650)

        self.formula_input = QLineEdit()
        self.formula_input.setPlaceholderText("请输入公式，例如：y=x^2")
        self.formula_input.setText("y=x^2")

        self.generate_button = QPushButton("生成图像")

        self.status_label = QLabel("当前版本支持：y=x^2")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.figure = create_preview_figure()
        self.canvas = FigureCanvas(self.figure)

        layout = QVBoxLayout()
        layout.addWidget(self.formula_input)
        layout.addWidget(self.generate_button)
        layout.addWidget(self.status_label)
        layout.addWidget(self.canvas, stretch=1)

        central_widget = QWidget()
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

        self.generate_button.clicked.connect(
            self.handle_generate_clicked
        )

        self.formula_input.returnPressed.connect(
            self.handle_generate_clicked
        )

    def handle_generate_clicked(self) -> None:
        """读取公式，调用绘图模块并刷新画布。"""

        formula = self.formula_input.text().strip()

        if not formula:
            self.status_label.setText("请先输入公式。")
            return

        try:
            draw_formula(self.figure, formula)
        except ValueError as error:
            self.status_label.setText(str(error))
            return

        self.canvas.draw()
        self.status_label.setText(f"已生成图像：{formula}")