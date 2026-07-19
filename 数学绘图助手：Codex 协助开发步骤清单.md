# 数学绘图助手：Codex 协助开发步骤清单

## 1. 总体协作原则

Codex 每次只完成一个明确阶段，不一次性实现整个项目。

每个阶段必须遵循：

1. 先阅读项目说明和当前代码；
2. 检查 Git 状态；
3. 明确本轮允许修改的文件；
4. 先输出简短实施计划；
5. 再修改代码；
6. 运行自动测试和基本检查；
7. 总结修改文件；
8. 给出用户需要手动检查的项目；
9. 不擅自进入下一阶段；
10. 不擅自安装未批准的依赖。

Codex 不应：

* 把全部逻辑写进 `main.py`；
* 把完整业务流程写进按钮回调；
* 绕过 AppController；
* 让 Worker 修改 QWidget；
* 在 UI 层直接调用 SimpleTex；
* 让 Engine 依赖 QPixmap 或 QClipboard；
* 将真实密钥写入代码；
* 在测试中调用真实付费 API；
* 为了“看起来完整”伪造尚未实现的功能；
* 未经允许修改打包、服务器或 CI 配置。

---

## 2. 每个窗口的固定输入材料

每次新建 Codex 窗口时，提供：

```text
1. 当前 PRD：
docs/PRD.md

2. 当前架构：
docs/architecture.md

3. 当前决策记录：
docs/decisions.md

4. 当前里程碑和本轮任务

5. 本轮允许修改的文件

6. 本轮禁止修改的文件

7. 当前测试命令

8. 用户需要手动检查的内容
```

---

## 3. Codex 通用执行提示词

```text
你正在开发 Windows 桌面软件“数学绘图助手”。

技术栈：
- Python 3
- PySide6
- Qt Widgets
- SymPy
- NumPy
- Matplotlib
- uv
- pytest

先阅读：
- docs/PRD.md
- docs/architecture.md
- docs/decisions.md
- README.md
- pyproject.toml

工作要求：
1. 先检查 git status 和当前分支。
2. 先阅读本轮涉及的现有文件，不要凭空重写。
3. 先输出简短、可执行的实施计划。
4. 只完成本轮明确任务。
5. 不擅自安装新依赖。
6. 不擅自修改无关文件。
7. UI 不直接调用网络或实现数学引擎。
8. Engine 不依赖 PySide6。
9. Worker 不直接修改 QWidget。
10. 任务编排统一经过 AppController。
11. 所有异步结果必须携带 request_id。
12. 旧 request_id 的结果不得覆盖当前结果。
13. 不将密钥、截图或隐私内容写入日志。
14. 完成后运行本轮测试。
15. 最后输出：
   - 修改了哪些文件；
   - 实现了什么；
   - 测试结果；
   - 仍未实现的内容；
   - 需要我手动检查的步骤。

不要自动进入下一里程碑。
```

---

# 阶段 0：项目初始化

## 目标

建立可维护的 uv、PySide6 和 pytest 项目基础。

## Codex 任务

* 检查当前目录；
* 初始化 Git；
* 初始化 uv 项目；
* 创建 `pyproject.toml`；
* 添加基础依赖；
* 创建完整目标目录；
* 创建 `.gitignore`；
* 创建 `.env.example`；
* 创建 README；
* 保存 PRD；
* 创建 architecture 和 decisions 文档；
* 创建最小测试入口。

## 本阶段不做

* 不实现 OCR；
* 不实现截图；
* 不实现真实绘图；
* 不实现 Worker；
* 不打包。

## 验收命令

```powershell
uv sync
uv run python --version
uv run pytest
```

## 人工检查

* 目录是否清晰；
* `.env` 是否被忽略；
* 是否没有真实密钥；
* 是否能在当前电脑创建虚拟环境。

---

# 阶段 1：应用启动骨架

## 目标

建立正确的 QApplication 启动流程。

## 主要文件

```text
main.py
math_drawing_assistant/bootstrap.py
math_drawing_assistant/ui/main_window.py
```

## Codex 任务

* `main.py` 只调用 bootstrap；
* bootstrap 创建 QApplication；
* 设置应用名称、版本和组织信息；
* 加载主题；
* 创建 MainWindow；
* 调用 `show()`；
* 进入 `app.exec()`；
* 正确返回退出代码。

## 验收

```powershell
uv run python main.py
```

应出现空白或基础主窗口，关闭后进程正常结束。

## 人工检查

* 是否只能出现一个主窗口；
* 关闭后是否残留 Python 进程；
* 窗口标题是否正确；
* `main.py` 是否没有业务逻辑。

---

# 阶段 2：数据模型和 AppController

## 目标

提前建立完整状态和轻量协调层。

## 主要文件

```text
models/requests.py
models/results.py
models/state.py
app_controller.py
```

## Codex 任务

* 创建 PlotRequest；
* 创建 PlotResult；
* 创建 RecognitionRequest；
* 创建 RecognitionResult；
* 创建完整 AppPhase；
* 增加 `SHUTTING_DOWN`；
* 创建轻量 AppController；
* 由 AppController 保存当前状态；
* 由 AppController 生成 request_id；
* 预留当前 OCR 和绘图请求编号；
* 定义状态变化信号；
* 定义结果和错误信号；
* 不实现真实网络和绘图。

## 验收

自动测试应覆盖：

* dataclass 默认值；
* 列表字段使用 `default_factory`；
* request_id 唯一；
* 状态能够正常改变；
* SHUTTING_DOWN 后拒绝新任务。

## 人工检查

* AppController 是否没有创建 QWidget；
* AppController 是否没有解析 SymPy；
* MainWindow 是否能收到状态变化。

---

# 阶段 3：界面组件

## 目标

完成 M0 的静态界面。

## 主要文件

```text
ui/main_window.py
ui/widgets/formula_input_panel.py
ui/widgets/formula_review_panel.py
ui/widgets/plot_preview.py
ui/widgets/status_panel.py
ui/theme.py
resources/styles/light.qss
resources/styles/dark.qss
```

## Codex 任务

* 创建公式输入区；
* 创建绘图区间输入；
* 创建生成按钮；
* 创建清空按钮；
* 创建图片预览占位区；
* 创建复制按钮；
* 创建状态面板；
* 创建暂时隐藏的公式核查面板；
* 连接 UI 信号到 AppController；
* 根据 AppPhase 更新按钮状态；
* 不实现真实绘图。

## 人工检查

* 界面是否不拥挤；
* 教学一体机上按钮是否足够大；
* 亮色主题是否统一；
* 深色主题是否可读；
* 缩放窗口时布局是否正常；
* 是否没有零散的大段 `setStyleSheet()`。

---

# 阶段 4：PNG 与 Qt 图片边界

## 目标

验证图片显示链路。

## 主要文件

```text
ui/qt_image.py
ui/widgets/plot_preview.py
```

## Codex 任务

* 实现 PNG bytes 转 QImage；
* 检查图片加载失败；
* 实现 QImage 转 QPixmap；
* 实现按预览区域保持比例缩放；
* 使用固定的内存 PNG 测试图片；
* 不访问 QClipboard。

## 自动测试

* 有效 PNG 可以读取；
* 无效 bytes 返回明确错误；
* QImage 非空；
* 图片宽高正确。

## 人工检查

* 图片比例是否正确；
* 调整窗口后是否重新适配；
* 是否没有模糊到不可用；
* `qt_image.py` 是否完全不访问剪贴板。

---

# 阶段 5：公式规范化和显函数提取

## 目标

建立安全管线的前两步。

## 主要文件

```text
engine/normalizer.py
engine/equation_extractor.py
tests/engine/test_normalizer.py
tests/engine/test_equation_extractor.py
```

## Codex 任务

支持和测试：

```text
x**2
x^2
x²
y=x**2
y = x²
y = sin(x)
```

拒绝：

```text
x=1
x+y=1
y=x=1
x>1
多个等号
空输入
超长输入
```

本阶段不调用 SymPy。

## 验收

所有字符串处理有明确输入和输出，不依赖 Qt。

---

# 阶段 6：受限解析和表达式验证

## 目标

实现安全的首版公式解析。

## 主要文件

```text
engine/parser.py
engine/validator.py
tests/engine/test_parser.py
tests/engine/test_validator.py
```

## Codex 任务

* 定义允许变量；
* 定义允许函数；
* 定义允许常量；
* 定义允许运算；
* 解析后检查表达式树；
* 限制输入长度；
* 限制节点数量；
* 限制嵌套深度；
* 限制极端指数；
* 拒绝未知变量；
* 拒绝未知函数；
* 拒绝非首版数学结构；
* 返回结构化错误。

## 重点要求

不得：

* 直接信任 OCR LaTeX；
* 仅因 SymPy 成功解析就允许绘图；
* 允许任意函数名；
* 允许多个自由变量；
* 让异常直接显示给普通用户。

## 人工检查

至少尝试：

```text
sin(x)
sqrt(x)
log(x)
x**2
x**1000000
unknown(x)
x+y
```

---

# 阶段 7：数值采样

## 目标

将合法表达式转换为可绘图数据。

## 主要文件

```text
engine/sampler.py
tests/engine/test_sampler.py
```

## Codex 任务

* 创建 x 采样点；
* 转换为 NumPy 数值函数；
* 处理标量返回；
* 处理 NaN；
* 处理正负无穷；
* 处理定义域错误；
* 标记不可绘制点；
* 识别明显跳变；
* 避免跨越渐近线连接；
* 返回警告列表；
* 限制采样数量。

## 必测公式

```text
x
x**2
1/x
sqrt(x)
log(x)
tan(x)
```

## 人工检查

重点观察：

* `1/x` 是否在 x=0 附近错误连线；
* `sqrt(x)` 是否不会绘制负数定义域；
* `log(x)` 是否正确处理 x≤0；
* `tan(x)` 是否出现不合理竖线。

---

# 阶段 8：Matplotlib PNG 渲染

## 目标

生成独立于 Qt 的 PNG bytes。

## 主要文件

```text
engine/renderer.py
tests/engine/test_renderer.py
```

## Codex 任务

* 每次创建独立 Figure；
* 不使用交互窗口；
* 将结果写入 BytesIO；
* 返回 PNG bytes；
* 返回耗时；
* 设置合理坐标轴；
* 支持网格；
* 正确释放 Figure；
* 不返回 QPixmap；
* 不操作剪贴板。

## 自动测试

* PNG 非空；
* PNG 文件头正确；
* 宽高正确；
* 多次绘图不会持续泄漏 Figure；
* 错误数据不会导致进程崩溃。

---

# 阶段 9：M1 流程整合

## 目标

完成手动输入到图片预览。

## 主要文件

```text
app_controller.py
ui/main_window.py
相关 Engine 文件
```

## Codex 任务

实现：

```text
用户点击生成
→ MainWindow 发出意图
→ AppController 创建 PlotRequest
→ Engine 执行管线
→ 返回 PlotResult
→ AppController 检查 request_id
→ MainWindow 显示图片
```

## 要求

* 先同步实现也可以；
* 架构上保留 RenderWorker；
* AppController 统一处理异常；
* 过期结果不得更新界面；
* 状态依次切换；
* 失败后保留用户输入；
* READY 后可以再次生成。

## 人工检查

快速连续提交：

```text
sin(x)
x**2
1/x
```

最终界面必须显示最后一次有效请求的结果。

---

# 阶段 10：ClipboardService

## 目标

完成复制图片功能。

## 主要文件

```text
services/clipboard_service.py
app_controller.py
ui/main_window.py
```

## Codex 任务

* 由 ClipboardService 获取 QClipboard；
* 将 QImage 写入剪贴板；
* 没有图片时拒绝复制；
* 写入前记录内部图片指纹；
* 标记内部写入；
* 返回复制成功或失败；
* UI 显示复制成功提示；
* `qt_image.py` 不得访问剪贴板。

## 人工验收

复制后分别粘贴到：

* Windows 画图；
* PowerPoint；
* Word；
* 西沃白板或可用替代软件。

---

# 阶段 11：M1 完整测试和文档

## Codex 任务

* 补齐 Engine 测试；
* 更新 supported-formulas；
* 更新 README；
* 创建人工测试清单；
* 记录已知限制；
* 运行全部测试；
* 检查是否有真实密钥；
* 检查是否有绝对路径；
* 创建 M1 checkpoint 提交。

## 验收命令

```powershell
uv run pytest
uv run python main.py
```

---

# 阶段 12：本地图片导入

## 目标

完成 M2。

## Codex 任务

* 文件选择对话框；
* 验证扩展名；
* 验证图片内容；
* 限制文件大小和像素尺寸；
* 显示原图预览；
* 创建模拟 OCR；
* 显示公式核查面板；
* 用户确认后进入现有绘图流程。

## 重点

不能为了模拟 OCR 提前调用真实 API。

---

# 阶段 13：SimpleTex 官方核实

在写代码前，单独完成核实：

* 当前接口地址；
* 鉴权；
* 请求格式；
* 文件限制；
* 超时；
* 并发限制；
* 返回结构；
* 是否有置信度；
* 图片保存政策；
* API 密钥能否分发；
* 手写公式支持情况。

核实结果写入：

```text
docs/decisions.md
```

未确认前不得根据旧博客猜测接口。

---

# 阶段 14：SimpleTexService

## Codex 任务

* 实现服务类；
* 使用明确超时；
* 不记录 Authorization；
* 转换为 RecognitionResult；
* 为成功和失败响应编写模拟测试；
* 不在普通测试中请求真实 API。

---

# 阶段 15：RecognitionWorker 和 QThread

在实现前先核实当前官方 QThread 写法。

## Codex 任务

* Worker 使用 QObject；
* moveToThread；
* AppController 持有线程和 Worker；
* started 启动工作；
* succeeded/failed 返回对象；
* finished 清理；
* 应用关闭时处理运行任务；
* 避免线程仍运行时被销毁；
* 网络超时可恢复；
* 结果携带 request_id；
* 过期 OCR 结果不进入核查面板。

## 人工检查

* 请求期间移动窗口；
* 请求期间重复点击；
* 请求期间关闭窗口；
* 断网；
* 错误密钥；
* 服务端超时。

---

# 阶段 16：Windows 截图原型

在正式整合前单独创建最小原型，验证：

* 当前 Windows 截图协议；
* 截图是否进入剪贴板；
* 用户取消时的行为；
* 截图工具关闭时的行为；
* 相同图片是否触发信号；
* 多显示器；
* 不同缩放比例。

原型代码不得直接混入正式架构。

验证结论写入 decisions.md。

---

# 阶段 17：ScreenshotService 与 Clipboard 协调

## Codex 任务

* 实现 capture_pending；
* 保存截图任务编号；
* 记录原剪贴板图片指纹；
* 调用系统截图；
* 监听图片变化；
* 区分内部复制；
* 区分外部新截图；
* 设置超时；
* 恢复窗口；
* 截图成功后启动 OCR；
* 截图取消后返回 IDLE；
* 不因普通文本复制而启动 OCR。

---

# 阶段 18：RenderWorker

只有实测绘图可能阻塞界面时才启用。

## Codex 任务

* 将现有纯 Engine 流程包装为 Worker；
* 不修改 Engine 的 Qt 独立性；
* AppController 持有线程；
* request_id 防止过期覆盖；
* 关闭时等待或合作式取消；
* 不尝试强行终止正在执行的 Python 代码；
* GUI 更新回到主线程。

---

# 阶段 19：DPI、多显示器和触控

## Codex 任务

* 核实 Qt 6 默认高 DPI 行为；
* 使用逻辑像素；
* 读取 QScreen 可用区域；
* 测试不同缩放比例；
* 保存窗口位置时记录所属屏幕；
* 屏幕不存在时回退到主屏；
* 增大触控按钮；
* 检查教学一体机操作。

不要在没有原型验证时大量调用 Windows 原生 API。

---

# 阶段 20：样式优化

## Codex 任务

* 统一 QSS；
* 设置视觉层级；
* 优化空状态；
* 优化加载状态；
* 优化错误状态；
* 优化触控尺寸；
* 检查亮色和深色；
* 统一 SVG 图标；
* 保持专业、简洁、可信。

不做：

* 复杂动画；
* 玻璃拟态；
* 大量渐变；
* 模仿网页组件；
* 影响课堂性能的特效。

---

# 阶段 21：打包核实

正式打包前分别核实：

* pyside6-deploy；
* Nuitka；
* PyInstaller；
* Qt 插件；
* QSS；
* SVG；
* Matplotlib 数据文件；
* 单文件与目录模式；
* Windows Defender 误报；
* LGPL/GPL 和第三方许可证。

结论写入 decisions.md。

---

# 阶段 22：发布候选版本

## Codex 任务

* 锁定验证过的依赖版本；
* 生成发布包；
* 包含资源；
* 创建许可证目录；
* 创建隐私说明；
* 检查日志路径；
* 检查配置路径；
* 移除真实密钥；
* 移除测试图片；
* 移除绝对路径；
* 运行干净环境测试；
* 创建发布检查清单。

---

## 4. 每次 Codex 完成后的固定报告格式

```text
本轮目标：

修改文件：

新增文件：

实现内容：

未实现内容：

自动测试：

测试结果：

人工检查步骤：

架构影响：

已知风险：

建议的下一阶段：
```

---

## 5. Git 建议

推荐长期分支：

```text
main
```

每个里程碑使用独立开发分支，例如：

```text
codex/m0-ui-skeleton
codex/m1-manual-plot
codex/m2-image-import
codex/m3-simpletex
codex/m4-windows-capture
codex/m5-classroom-ux
codex/m6-release
```

每完成一个稳定小阶段：

* 检查 `git diff`；
* 运行测试；
* 人工启动；
* 提交 checkpoint；
* 不使用无意义的巨大提交；
* 不在未通过测试时合并到 main。

---

## 6. 当前最先执行的顺序

```text
1. 保存 PRD
2. 创建 architecture.md
3. 初始化 uv 和完整目录
4. 建立启动骨架
5. 建立 models 和 AppController
6. 建立静态 UI
7. 打通固定 PNG 预览
8. 实现 normalizer
9. 实现 equation_extractor
10. 实现 parser 和 validator
11. 实现 sampler
12. 实现 renderer
13. 整合手动绘图
14. 实现 ClipboardService
15. 完成 M1 测试
16. 再进入图片和 OCR
```

在 M1 完成前，不让 Windows 截图、打包、置顶入口和自动更新干扰核心闭环。
