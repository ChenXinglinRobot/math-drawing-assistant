"""数学绘图助手 —— 启动入口。

本模块是极薄入口，不放置窗口布局、绘图、业务状态或资源加载逻辑。
导入本模块不会创建 QApplication、显示窗口或启动事件循环。
"""

from math_drawing_assistant.bootstrap import run

if __name__ == "__main__":
    raise SystemExit(run())
