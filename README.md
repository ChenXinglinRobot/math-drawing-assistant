# 数学绘图助手

面向高中数学教师的 Windows 桌面绘图工具。阶段 12 已通过总架构师独立审核：有限范围 M1 单显函数 checkpoint 的正式链路为“手动输入 → 安全解析 → 预算与采样 → Agg 渲染 → 唯一 RenderActor → GUI 预览 → Windows 剪贴板复制”。当前正式入口为 package bootstrap（`main.py → math_drawing_assistant.bootstrap`）；根目录遗留演示文件不是正式入口。

该通过范围仅覆盖 Windows 11 开发参考机上的 M1 单显函数 checkpoint。人工替代验证使用 Windows 画图 11.2605.71.0 与 WPS Office 12.1.0.19302 的 WPS 演示、WPS 文字；Microsoft PowerPoint 与 Microsoft Word 未验证，本文不声明 Microsoft Office 兼容性。M1.5、M1.6、OCR、Windows 截图输入、核心 MVP、正式发布及完整目标软件矩阵仍未完成或关闭。

文档入口：

* [产品需求](数学绘图助手%20PRD.md)
* [架构约束](docs/architecture.md)
* [决策记录](docs/decisions.md)
* [M1.5 首期数学与输入范围](docs/m1.5-math-input-scope.md)
* [开发步骤清单](数学绘图助手_Codex协助开发步骤清单_v0.3.md)
* [联网确认与外部验证](联网确认.md)

请按开发步骤清单逐阶段执行。任何依赖安装、Pyright 配置、CI/扫描工具或正式开发阶段，都需要当次明确批准；本文不复制易变化的安装命令、限制值或外部事实。
