# 数学绘图助手 PRD

版本：v0.1
文档状态：初步开发基线
目标平台：Windows 10/11
目标用户：高中及以下学段教师，后续可扩展至学生和教研人员

---

## 1. 产品概述

“数学绘图助手”是一款面向教师电脑和教学一体机的 Windows 桌面软件。

软件帮助教师将手动输入或截图识别得到的数学公式快速转换为清晰的函数图像，并复制到 Windows 剪贴板，以便粘贴到西沃白板、PowerPoint、Word、教案或其他教学软件中。

首个可用版本重点解决：

1. 公式输入不方便；
2. 临时绘制函数图像耗时；
3. 教学软件之间转移函数图像步骤较多；
4. 手写公式识别结果需要人工确认；
5. 教学场景需要操作简单、反馈明确、触控友好。

---

## 2. 产品目标

### 2.1 核心目标

用户可以完成以下流程：

```text
输入公式
→ 检查和确认
→ 解析公式
→ 生成函数图像
→ 界面预览
→ 复制到剪贴板
→ 粘贴到其他教学软件
```

后续支持：

```text
Windows 截图或导入图片
→ SimpleTex 识别
→ 用户核查和修改
→ 解析公式
→ 生成函数图像
→ 复制到剪贴板
```

### 2.2 产品成功标准

首个可用版本应满足：

* 普通教师无需理解 Python、SymPy 或 Matplotlib；
* 从输入公式到得到图像不超过少量操作；
* 输入错误时给出可理解的中文提示；
* 不因错误公式导致程序崩溃；
* 生成的图片可以复制并粘贴到常见 Windows 软件；
* 界面在 Windows 10/11 常见缩放比例下可用；
* 不将 API 密钥、课堂截图或学生信息写入不安全日志；
* 核心数学功能可以通过自动化测试验证。

---

## 3. 目标用户

### 3.1 主要用户

高中及以下学段的：

* 数学教师；
* 信息技术教师；
* 科学教师；
* 教研人员；
* 使用教学一体机授课的教师。

### 3.2 用户特征

主要用户可能：

* 不熟悉 LaTeX；
* 不熟悉编程；
* 使用鼠标、触控屏或教学一体机；
* 需要在课堂上快速完成操作；
* 更关注结果是否正确、清晰和易复制；
* 无法处理复杂报错信息。

---

## 4. 产品范围

### 4.1 第一阶段支持范围

第一阶段只支持单自变量显函数：

```text
y = f(x)
```

典型输入：

```text
y = x²
y = x^2
y = x**2
y = sin(x)
y = 1/x
y = sqrt(x)
```

首版优先支持高中及以下常见函数：

* 一次函数；
* 二次函数；
* 反比例函数；
* 幂函数；
* 指数函数；
* 对数函数；
* 绝对值函数；
* 基本三角函数；
* 简单复合函数。

### 4.2 暂不支持

核心功能稳定前，不支持：

* 隐函数；
* 参数方程；
* 极坐标方程；
* 分段函数的复杂可视化编辑器；
* 不等式区域；
* 方程组联立绘图；
* 微分方程；
* 三维图；
* 几何作图；
* 动态几何；
* 数据表格绘图；
* MathLive；
* Qt WebEngine；
* QML 或 Qt Quick；
* 自研全屏截图遮罩；
* 数据库；
* 插件系统；
* 自动更新；
* 云端账号体系；
* 网络服务器；
* 多进程架构。

---

## 5. 核心用户流程

### 5.1 手动输入绘图

```text
用户输入公式
→ 设置或使用默认绘图区间
→ 点击“生成图像”
→ 软件检查公式
→ 软件生成函数图像
→ 显示预览
→ 用户点击“复制图片”
→ 图片写入 Windows 剪贴板
```

### 5.2 导入图片识别

```text
用户选择本地图片
→ 软件显示图片预览
→ 用户点击“识别公式”
→ SimpleTex 返回识别结果
→ 软件进入公式核查阶段
→ 用户修改或确认
→ 软件生成函数图像
```

### 5.3 Windows 截图识别

```text
用户点击“截图识别”
→ 软件调用 Windows 截图工具
→ 用户框选公式
→ 截图进入剪贴板
→ 软件判断这是本次外部截图
→ 软件进入 OCR
→ 用户核查识别公式
→ 软件生成图像
```

### 5.4 错误恢复

```text
发生错误
→ 界面显示简洁中文说明
→ 保留用户原始输入
→ 允许用户修改后再次提交
→ 不要求重启程序
```

---

## 6. 功能需求

## 6.1 公式输入

软件应提供：

* 单行或适当高度的公式输入区域；
* 示例占位文字；
* 生成按钮；
* 清空按钮；
* 最近一次有效输入保留；
* 支持键盘回车提交；
* 输入错误后不清空原内容；
* OCR 结果可直接进入同一输入区域修改。

第一版不提供完整 LaTeX 编辑器。

---

## 6.2 绘图参数

第一版至少提供：

* x 轴最小值；
* x 轴最大值；
* 是否显示网格；
* 图片宽度和高度的默认值；
* 自动使用合理采样点数量。

可以后续增加：

* y 轴范围；
* 线宽；
* 曲线颜色；
* 坐标轴样式；
* 背景透明；
* 图例；
* 标题；
* 多函数绘制。

首版必须对参数设置上限和下限，避免异常图片尺寸、DPI 或采样数量导致卡顿和内存占用。

---

## 6.3 公式识别

SimpleTex 接入后应满足：

* 支持本地图片；
* 支持 Windows 截图；
* OCR 请求不阻塞界面；
* 设置明确的连接和读取超时；
* 网络失败时可以恢复；
* 不自动信任识别结果；
* 用户必须看到并确认识别文本；
* 不将识别结果直接无提示地送入绘图；
* 不预先假设 API 一定返回置信度；
* API 返回结构以当前官方文档和实际响应为准。

---

## 6.4 图像预览

预览区域应：

* 在无图片时显示占位状态；
* 在生成期间显示处理中状态；
* 显示最新有效绘图结果；
* 保持图片比例；
* 不因窗口缩放导致图片严重变形；
* 生成失败时保留上一张成功图片，除非用户主动清除；
* 支持重新复制当前图片。

---

## 6.5 剪贴板

软件应支持：

* 将当前绘图结果写入 Windows 剪贴板；
* 判断当前是否存在可复制图片；
* 复制成功后显示明确提示；
* 软件自己写入剪贴板时，不触发截图 OCR；
* 外部截图写入和内部绘图写入必须区分；
* 不仅依靠一次 `dataChanged` 信号就直接开始 OCR。

---

## 6.6 状态反馈

界面应显示：

* 当前阶段；
* 正在执行的任务；
* 成功提示；
* 可恢复错误；
* 网络超时；
* 截图取消或超时；
* 复制成功；
* 当前公式不受支持。

按钮状态应与当前阶段一致，例如：

* OCR 进行中时避免重复提交；
* 绘图进行中时避免同一请求重复启动；
* 没有图片时禁用复制按钮；
* 关闭程序时不再接受新任务。

---

## 7. 非功能需求

### 7.1 易用性

* 默认界面使用中文；
* 关键按钮文字清晰；
* 不向普通用户显示 Python 异常堆栈；
* 触控目标不应过小；
* 常用流程尽量不超过三至五次主要操作；
* 默认参数应能直接生成大多数高中常见函数图像。

### 7.2 性能

* 普通常见函数绘图应快速完成；
* GUI 主线程不得执行网络等待；
* 高分辨率绘图和大量采样应支持放入 Worker；
* 任务结果必须携带请求编号；
* 旧任务结果不得覆盖新任务结果。

### 7.3 稳定性

* 不合法输入不得导致程序崩溃；
* 网络错误不得导致程序无法继续操作；
* 应用关闭时必须正确停止、等待或放弃后台任务；
* 不出现 `QThread: Destroyed while thread is still running`；
* Worker 不直接修改 QWidget；
* 所有 QWidget 更新在 GUI 主线程完成。

### 7.4 隐私

* 默认不保存课堂截图；
* 日志不记录完整截图内容；
* 日志不记录完整 API 密钥；
* OCR 前应提供必要的隐私说明；
* 涉及学生姓名、成绩或其他个人信息的截图应提示用户谨慎上传；
* SimpleTex 图片保存策略必须在接入前核实。

### 7.5 可维护性

* UI 和数学引擎分离；
* Engine 不依赖 PySide6；
* Service 不决定数学绘制规则；
* Worker 不承担界面设计；
* AppController 负责任务协调；
* 核心 Engine 可以使用 pytest 独立测试。

---

## 8. 技术架构

总体结构：

```text
UI
↓
AppController
↓
Engine / Services
↓
Workers
```

### 8.1 UI 层

负责：

* 创建和显示控件；
* 接收用户输入；
* 发出用户操作信号；
* 显示状态、错误和结果；
* 将 PNG 数据转换为 Qt 显示对象；
* 根据控制器状态启用或禁用按钮。

UI 不负责：

* 直接调用 SimpleTex；
* 直接管理复杂数学解析；
* 直接构建完整 Matplotlib 绘图流程；
* 保存 API 密钥；
* 在按钮回调中实现完整业务链路；
* 判断旧任务结果是否有效。

---

## 8.2 AppController

项目从初始架构开始加入轻量 `AppController`。

它负责：

* 接收 UI 发来的用户意图；
* 创建 PlotRequest 和 RecognitionRequest；
* 分配任务编号；
* 保存当前有效任务编号；
* 调用 Engine 或启动 Worker；
* 持有 QThread 和 Worker 的引用；
* 接收任务成功、失败和结束信号；
* 丢弃已经过期的任务结果；
* 控制 AppPhase；
* 将可显示结果通知 UI；
* 处理应用关闭流程；
* 防止同一任务重复提交；
* 协调截图、OCR、公式确认、绘图和复制流程。

它不负责：

* 创建具体 QWidget；
* 实现 SymPy 解析细节；
* 实现 HTTP 请求细节；
* 绘制 Matplotlib 图像；
* 保存真实密钥内容。

第一版不引入依赖注入框架、事件总线或复杂命令系统。

---

## 8.3 Engine 层

Engine 负责纯数学处理：

* 输入规范化；
* 识别首版支持的公式类型；
* 提取显函数右侧表达式；
* 解析为内部数学表达式；
* 验证变量、函数和结构；
* 构造 NumPy 数值函数；
* 采样；
* 处理定义域、NaN、无穷大和不连续点；
* 生成 Matplotlib Figure；
* 输出 PNG bytes；
* 返回警告和绘图元数据。

Engine 必须：

* 不依赖 QWidget；
* 不访问网络；
* 不操作 QClipboard；
* 不弹出窗口；
* 不读取真实配置文件；
* 输入确定时产生可预测结果；
* 可由 pytest 直接测试。

---

## 8.4 Services 层

Services 负责与外部环境交互。

### SimpleTexService

负责：

* 组装 HTTP 请求；
* 鉴权；
* 超时；
* 解析响应；
* 转换为 RecognitionResult；
* 对日志中的敏感字段脱敏。

不负责：

* 判断公式是否适合绘制；
* 直接修改界面；
* 直接生成图像。

### ScreenshotService

负责：

* 调用 Windows 截图工具；
* 管理截图启动；
* 配合剪贴板事件；
* 处理超时和取消推断；
* 返回截图数据或截图事件。

### ClipboardService

负责：

* 获取 `QClipboard`；
* 读取剪贴板图片；
* 判断剪贴板是否包含图片；
* 将 `QImage` 写入剪贴板；
* 区分外部截图和软件内部写入；
* 提供剪贴板事件给 AppController。

### SettingsService

负责：

* 用户普通配置；
* 绘图区间默认值；
* 主题；
* 窗口位置；
* 后续悬浮入口位置；
* API 密钥引用或读取接口。

`QSettings` 只作为普通配置存储，不预先认定其是安全密钥存储。

---

## 8.5 Workers 层

项目从初始目录中保留 Workers 层。

Workers 负责：

* OCR 网络请求；
* 后期较慢的绘图；
* 后期复杂公式处理；
* 可取消或可超时的耗时任务。

Worker：

* 继承 `QObject`；
* 不直接继承或修改 QWidget；
* 通过 Signal 返回结果；
* 不直接操作界面；
* 由 AppController 持有引用；
* 返回结果时携带 request_id。

推荐信号：

```text
started
succeeded(object)
failed(object)
finished
progress(object)  # 仅未来需要时增加
```

具体 QThread 连接和清理方式必须根据当前 Qt 官方资料确认。

---

## 9. 图片职责边界

### `ui/qt_image.py`

只负责 Qt 图片格式转换：

```text
PNG bytes → QImage
QImage → QPixmap
```

可以包含：

* 从字节安全创建 QImage；
* 检查图片是否加载成功；
* 将 QImage 转为预览用 QPixmap；
* 按预览区域缩放 QPixmap。

不得负责：

* 访问系统剪贴板；
* 监听剪贴板变化；
* 判断截图任务；
* 调用 OCR。

### `services/clipboard_service.py`

只负责系统剪贴板：

```text
QImage → QClipboard
QClipboard → QImage
剪贴板变化 → AppController
```

不得负责：

* PNG 解码显示；
* Matplotlib 绘图；
* 公式识别；
* UI 控件更新。

---

## 10. 公式处理管线

推荐流程：

```text
用户确认后的公式
↓
normalizer
↓
equation_extractor
↓
parser
↓
validator
↓
sampler
↓
renderer
```

### 10.1 normalizer

负责：

* 去除外围空格；
* 统一常见全角符号；
* 处理部分 Unicode 数学符号；
* 去除明确允许移除的外围 LaTeX 标记；
* 统一首版支持的少量写法。

它不是完整安全边界，不负责信任输入。

### 10.2 equation_extractor

负责：

* 判断是否为首版支持的显函数；
* 识别 `y = ...`；
* 必要时接受单独右侧表达式；
* 拒绝多个等号；
* 拒绝隐函数、参数方程和不等式；
* 输出待解析的右侧表达式。

### 10.3 parser

负责：

* 将受限文本或 LaTeX 转换为 SymPy 表达式；
* 使用明确的解析策略；
* 不直接信任 OCR 输出；
* 返回解析成功结果或清晰错误。

### 10.4 validator

在得到表达式树后检查：

* 只允许变量 `x`；
* 不允许未知自由变量；
* 只允许白名单函数；
* 只允许白名单运算；
* 限制表达式长度；
* 限制表达式树规模；
* 限制嵌套深度；
* 限制极端幂指数；
* 拒绝矩阵、积分、求和、导数等非首版结构；
* 拒绝可能造成异常耗时或内存占用的表达式。

### 10.5 sampler

负责：

* 在有限区间生成 x 值；
* 将 SymPy 表达式转换为 NumPy 数值函数；
* 捕获数值警告；
* 处理 NaN 和无穷大；
* 标记定义域外点；
* 对不连续点进行断线处理；
* 避免将渐近线两侧直接连接；
* 返回绘图数据和警告。

### 10.6 renderer

负责：

* 为每次绘图独立创建 Figure；
* 使用非交互式绘图方式；
* 不调用 `pyplot.show()`；
* 绘制坐标轴、网格和曲线；
* 写入 `BytesIO`；
* 返回 PNG bytes；
* 关闭或释放对应 Figure；
* 返回尺寸、耗时和警告信息。

---

## 11. 公式安全策略

项目主要面向高中及以下教师，因此首版采用受限白名单，不追求解析全部数学表达式。

### 11.1 允许内容

初步允许：

```text
变量：
x

运算：
+ - * / **

常量：
pi
E

函数：
sin
cos
tan
sqrt
abs
exp
log
```

最终白名单根据高中及以下实际需求扩展。

### 11.2 明确拒绝

首版拒绝：

* 未知变量；
* 多变量表达式；
* 任意函数名；
* 矩阵；
* 积分；
* 求和；
* 极限；
* 导数；
* Lambda；
* 方程求解命令；
* 任意代码结构；
* 过长输入；
* 过深嵌套；
* 极端指数；
* 超大图片；
* 超高 DPI；
* 超大采样量。

### 11.3 安全原则

* 不将 OCR 结果视为可信输入；
* 不将用户文本直接交给无约束执行逻辑；
* 解析成功不等于允许绘图；
* 所有表达式必须经过结构验证；
* 验证失败时返回用户可理解的提示；
* 技术细节写入日志，但不暴露敏感内容。

---

## 12. 数据模型

建议使用 `dataclass`。

### RecognitionRequest

字段：

* request_id；
* image_bytes；
* image_format；
* source；
* created_at。

### RecognitionResult

字段：

* request_id；
* success；
* raw_latex；
* normalized_latex；
* provider_data；
* warnings；
* error。

不得预设一定存在置信度。

### PlotRequest

字段：

* request_id；
* formula_text；
* variable；
* x_min；
* x_max；
* sample_count；
* image_width；
* image_height；
* dpi；
* show_grid；
* show_legend。

### PlotResult

字段：

* request_id；
* success；
* png_bytes；
* normalized_formula；
* x_range；
* warnings；
* elapsed_ms；
* ignored_point_count；
* has_discontinuity；
* error。

### AppPhase

完整定义：

```text
IDLE
CAPTURING
RECOGNIZING
REVIEWING
RENDERING
READY
ERROR
SHUTTING_DOWN
```

所有枚举值从项目初期定义。

但不建立复杂状态机框架。AppController 使用明确方法切换状态，并校验明显非法操作。

---

## 13. 状态转换

主要转换：

```text
IDLE → RENDERING
RENDERING → READY
RENDERING → ERROR
ERROR → IDLE
READY → RENDERING
```

加入 OCR 后：

```text
IDLE / READY → RECOGNIZING
RECOGNIZING → REVIEWING
RECOGNIZING → ERROR
REVIEWING → RENDERING
```

加入截图后：

```text
IDLE / READY → CAPTURING
CAPTURING → RECOGNIZING
CAPTURING → IDLE
CAPTURING → ERROR
```

关闭程序：

```text
任意状态 → SHUTTING_DOWN
```

处于 `SHUTTING_DOWN` 时不得启动新任务。

---

## 14. 请求编号和过期结果

每次 OCR 和绘图任务必须获得唯一 `request_id`。

AppController 保存：

```text
current_recognition_request_id
current_render_request_id
```

收到结果后：

* 编号一致：允许更新当前界面；
* 编号不一致：视为过期结果，不更新界面；
* 过期任务仍应完成资源清理；
* 日志记录任务已被忽略，但不作为用户错误显示。

这用于避免：

```text
旧任务较晚完成
→ 覆盖新任务结果
```

---

## 15. 截图和剪贴板防重复

AppController 或截图协调逻辑至少维护：

* `capture_pending`；
* `ignore_next_clipboard_change`；
* `last_external_image_hash`；
* `last_internal_image_hash`；
* 当前截图任务编号；
* 截图启动时间；
* 截图超时时间。

内部复制流程：

```text
准备写入绘图结果
→ 标记内部写入
→ 写入 QClipboard
→ 收到剪贴板信号
→ 判断为内部写入
→ 不启动 OCR
```

外部截图流程：

```text
capture_pending 为真
→ 收到新的图片
→ 与旧图片指纹比较
→ 确认为外部新截图
→ 清除 capture_pending
→ 启动 OCR
```

Windows 截图取消行为必须通过官方资料和最小原型确认。

---

## 16. API 密钥和配置

### 开发阶段

* 从环境变量或未提交本地配置读取；
* `.env` 加入 `.gitignore`；
* 提供 `.env.example`，不含真实密钥；
* 测试不调用真实付费 API；
* 日志只显示脱敏后的密钥标识。

### 发布阶段

在核实 SimpleTex 条款前，不将固定密钥直接嵌入桌面客户端。

优先考虑：

* 用户自行填写 API 密钥；
* Windows 凭据存储；
* 或由服务端代理，但首版不引入服务端。

不得把 `QSettings` 直接视为加密密钥库。

---

## 17. 日志和错误

日志至少记录：

* 程序启动和关闭；
* 应用版本；
* Python、PySide6、SymPy、NumPy、Matplotlib 版本；
* request_id；
* AppPhase 变化；
* OCR 开始和结束；
* HTTP 状态码；
* 请求耗时；
* 公式处理阶段；
* 绘图耗时；
* 异常类型；
* 完整技术堆栈；
* 截图取消、超时或失败；
* 过期结果被忽略；
* Worker 清理情况。

日志不得记录：

* 完整 API 密钥；
* 完整课堂截图；
* 不必要的学生信息；
* Authorization 请求头；
* 用户未同意保存的 OCR 图片。

界面错误示例：

```text
无法识别这个公式，请检查后重试。
当前版本只支持包含变量 x 的显函数。
绘图区间必须满足最小值小于最大值。
网络请求超时，请检查网络后重试。
图片复制失败，请重新生成后再试。
```

---

## 18. 推荐目录结构

```text
math-drawing-assistant/
├─ main.py
├─ pyproject.toml
├─ uv.lock
├─ README.md
├─ .gitignore
├─ .env.example
│
├─ math_drawing_assistant/
│  ├─ __init__.py
│  ├─ bootstrap.py
│  ├─ app_controller.py
│  │
│  ├─ models/
│  │  ├─ __init__.py
│  │  ├─ requests.py
│  │  ├─ results.py
│  │  └─ state.py
│  │
│  ├─ ui/
│  │  ├─ __init__.py
│  │  ├─ main_window.py
│  │  ├─ theme.py
│  │  ├─ qt_image.py
│  │  └─ widgets/
│  │     ├─ __init__.py
│  │     ├─ formula_input_panel.py
│  │     ├─ formula_review_panel.py
│  │     ├─ plot_preview.py
│  │     └─ status_panel.py
│  │
│  ├─ engine/
│  │  ├─ __init__.py
│  │  ├─ normalizer.py
│  │  ├─ equation_extractor.py
│  │  ├─ parser.py
│  │  ├─ validator.py
│  │  ├─ sampler.py
│  │  └─ renderer.py
│  │
│  ├─ services/
│  │  ├─ __init__.py
│  │  ├─ simpletex_service.py
│  │  ├─ screenshot_service.py
│  │  ├─ clipboard_service.py
│  │  └─ settings_service.py
│  │
│  └─ workers/
│     ├─ __init__.py
│     ├─ recognition_worker.py
│     └─ render_worker.py
│
├─ resources/
│  ├─ icons/
│  └─ styles/
│     ├─ light.qss
│     └─ dark.qss
│
├─ tests/
│  ├─ conftest.py
│  ├─ engine/
│  │  ├─ test_normalizer.py
│  │  ├─ test_equation_extractor.py
│  │  ├─ test_parser.py
│  │  ├─ test_validator.py
│  │  ├─ test_sampler.py
│  │  └─ test_renderer.py
│  ├─ services/
│  │  └─ test_simpletex_service.py
│  └─ test_models.py
│
└─ docs/
   ├─ PRD.md
   ├─ architecture.md
   ├─ decisions.md
   ├─ supported-formulas.md
   ├─ privacy.md
   └─ manual-test-checklist.md
```

允许第一天创建完整目录和文件，但未实现模块必须：

* 有清晰模块说明；
* 不伪造已经实现的能力；
* 不建立无意义的复杂抽象；
* 不阻塞当前里程碑；
* 不通过大量 `pass` 制造虚假的完成感。

---

## 19. 样式要求

从第一版开始统一样式：

* 不在各个控件中零散堆积 `setStyleSheet()`；
* 亮色和深色主题分别放入 QSS；
* `theme.py` 负责加载；
* 使用统一 SVG 图标；
* 统一按钮高度；
* 统一输入框高度；
* 统一圆角和间距；
* 建立标题、正文、辅助文字层级；
* 为触控设备保留足够点击区域；
* 错误、警告、成功使用一致的视觉语义；
* 不追求复杂动效；
* 不模仿网页式过度装饰。

---

## 20. 测试要求

### 20.1 Engine 自动测试

必须覆盖：

* `y=x`；
* `y=x²`；
* `y=x^2`；
* `y=x**2`；
* `sin(x)`；
* `1/x`；
* `sqrt(x)`；
* 多余空格；
* 常见 Unicode 数学符号；
* 多个等号；
* 未知变量；
* 多变量；
* 未知函数；
* 超长输入；
* 极端指数；
* x 轴区间错误；
* NaN；
* 无穷大；
* 不连续点；
* PNG 非空；
* PNG 尺寸正确；
* 绘图警告正确返回。

不要要求不同环境生成的 PNG 二进制完全一致。

### 20.2 Services 测试

SimpleTex 使用模拟响应：

* 成功；
* 鉴权失败；
* 超时；
* 非 JSON；
* 缺少字段；
* 服务端错误；
* 返回不支持公式。

普通测试不得调用真实付费接口。

### 20.3 GUI 人工验收

至少检查：

* 启动；
* 输入；
* 生成；
* 错误恢复；
* 复制；
* 窗口缩放；
* 亮色主题；
* 深色主题；
* 任务期间按钮状态；
* 快速连续提交；
* 关闭时有后台任务；
* Windows 10；
* Windows 11；
* 不同 DPI；
* 多显示器；
* 触控操作。

---

## 21. 开发里程碑

### M0：界面和架构骨架

完成：

* 完整包结构；
* QApplication 启动；
* MainWindow；
* AppController；
* AppPhase；
* 输入区；
* 状态区；
* 图片占位区；
* QSS 主题；
* 固定测试图片预览。

验收：

* 程序可启动和关闭；
* UI 不包含业务大函数；
* AppController 可以改变界面阶段；
* 无真实 OCR 和数学解析。

### M1：手动输入绘图

完成：

* 基础公式输入；
* 规范化；
* 显函数提取；
* 解析和验证；
* 数值采样；
* PNG 生成；
* QImage/QPixmap 转换；
* 图片预览；
* 复制到剪贴板；
* Engine 自动测试。

验收：

* 常见高中函数可以绘制；
* 不合法输入不崩溃；
* 复制后可粘贴到 PowerPoint 或画图；
* 旧请求不能覆盖新结果。

### M2：导入本地图片

完成：

* 文件选择；
* 图片预览；
* 图片格式和大小验证；
* 模拟 OCR；
* 公式核查面板；
* 用户确认后绘图。

验收：

* 尚未接真实 API 时流程仍可完整演示；
* 用户可修改模拟识别结果。

### M3：SimpleTex

完成：

* SimpleTexService；
* RecognitionWorker；
* 超时和错误处理；
* 模拟测试；
* 本地密钥读取；
* OCR 隐私提示；
* 识别结果核查。

验收：

* 网络请求不冻结界面；
* 失败后仍可继续操作；
* 日志不泄露密钥；
* 用户确认后才绘图。

### M4：Windows 截图

完成：

* 调用系统截图；
* ClipboardService 监听；
* 图片指纹；
* 内部写入过滤；
* 截图超时；
* 取消处理；
* 多显示器实验。

验收：

* 截图后能进入 OCR；
* 复制绘图结果不会触发 OCR；
* 取消截图不会长期卡在 CAPTURING。

### M5：课堂体验

完成：

* 置顶入口；
* 触控尺寸；
* DPI；
* 多显示器位置；
* 系统托盘；
* 快速复制；
* 更清晰的状态反馈。

### M6：发布准备

完成：

* 配置目录；
* 日志目录；
* 资源路径；
* 隐私说明；
* 许可证文本；
* 打包；
* Windows 实机测试；
* 发布检查清单。

---

## 22. 发布验收标准

发布候选版本必须：

* 可在目标 Windows 10/11 设备启动；
* 资源文件不依赖开发机绝对路径；
* 不包含真实 API 密钥；
* 不包含测试截图；
* 不包含内部调试文件；
* 公式错误不会使程序退出；
* OCR 超时不会冻结界面；
* 关闭程序不会遗留运行线程；
* 图片可以粘贴至常见教学软件；
* 包含第三方许可证；
* 有基本隐私说明；
* 有版本号和日志位置说明。

---

## 23. 仍需官方核实或原型验证

1. 当前 PySide6 和 Python 版本支持范围；
2. QThread Worker 的推荐连接和清理方式；
3. Windows 系统截图调用协议；
4. 截图取消的可检测性；
5. SimpleTex 接口、限制、条款和图片保存政策；
6. SymPy LaTeX 解析器状态；
7. OCR LaTeX 和 SymPy 的实际兼容率；
8. Matplotlib 非 GUI Worker 绘图边界；
9. QImage、QPixmap 和 QClipboard 的线程限制；
10. Qt 6 高 DPI 和多显示器行为；
11. API 密钥发布策略；
12. PySide6、Qt 和第三方库许可证义务；
13. pyside6-deploy、Nuitka 和 PyInstaller 的当前适用差异。

这些问题不阻塞 M0。与当前里程碑直接相关时再逐项核实。
