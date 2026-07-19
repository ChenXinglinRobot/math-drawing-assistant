# 数学绘图助手：Codex 协助开发步骤清单

版本：v0.3（架构同步版）  
最后更新：2026-07-19  
对应 PRD：`数学绘图助手 PRD.md` v0.3  
文档状态：待逐阶段执行；本次文档评审不自动开始阶段 0

## 1. 文档职责与执行前提

本清单只负责可执行阶段、每阶段允许修改的文件、自动测试、静态检查和人工验收。规范性架构见 `docs/architecture.md`；产品范围与验收见 PRD；决策及理由见 `docs/decisions.md`；外部事实与证据见 `联网确认.md`；未来的语法、错误码、限制值和验收公式以 `docs/supported-formulas.md` 为单一事实来源。

每次只执行一个阶段或一个有明确边界的子任务。开始前必须：

1. 检查分支与 `git status`，识别并保护用户现有改动；
2. 阅读本阶段关联文档和现有实现，不凭空覆盖；
3. 说明关联 PRD 需求域、允许修改文件和简短计划；
4. 依赖安装、升级、Pyright 配置、CI 或扫描工具必须获得当次明确批准；
5. 只修改允许文件；必须扩大范围时停止并请求批准；
6. 完成本阶段测试、静态检查和必要人工验收，不自动进入下一阶段；
7. 测试失败或人工验收未完成时不创建“完成”checkpoint。

开发阶段可以修改 Python 代码；但当前文档评审轮次不得修改 Python、安装依赖、创建 CI 或开始阶段 0。

## 2. 固定架构约束

所有阶段必须遵守：

* 单图与多图统一使用 `PlotSceneRequest`、`PlotItemRequest`、`PlotSceneSpec`、分类型 `PlotItemSpec`、`RenderPlan`、`PlotSceneResult` 和 `PlotItemResult`；
* 请求、Spec、Plan 和结果是不可变快照，集合优先 tuple，后台任务不引用 UI 可变列表；
* `ViewportRequest` 表达用户意图，`ResolvedViewport` 表达合法最终范围；
* UI 只收集意图和展示结果；AppController 不做规范化、分类、采样或 Matplotlib；
* 所有完整绘图请求都进入唯一常驻、单线程、串行消费的 RenderActor；
* RenderActor 只保留一个运行任务和一个 latest-wins 待任务；
* Matplotlib 只在渲染线程使用 Figure、FigureCanvasAgg 和 Agg，不使用 pyplot 全局状态，不调用 show；
* `request_id` 与 `scene_revision` 都匹配时结果才可接纳；任何影响结果的编辑立即递增 revision，不防抖；
* TaskPhase 只含 IDLE、CAPTURING、RECOGNIZING、REVIEWING、RENDERING、SHUTTING_DOWN；结果存在性、复制可用、stale 和 ready 全部派生；
* 多项场景原子生成，任一 item 失败、不可见或资源超限都不替换旧成功图；
* 原始手动/OCR 文本不直接进入 eval、exec、无约束 sympify、通用 parse_expr 或宽松 LaTeX parser；
* 所有 item 分类、验证且视口解析后，才构造 RenderPlan 和完整资源预算；
* 一般直线与视口求交；受限圆、椭圆、双曲线、抛物线以参数化采样为主；
* 真实密钥由 CredentialStore 管理，QSettings 只保存普通配置或凭据引用；
* 首版没有数据库、插件系统、事件总线、依赖注入框架、WebEngine、QML、多进程或通用 CAS；
* 缓存不阻塞 M1、M1.5、M1.6，只有性能基准证明需要后才进入可选阶段 19。

## 3. 类型、错误、日志和质量政策

* 公开函数与方法标注参数和返回类型，dataclass 字段全部有类型；
* 使用现代注解：`list[str]`、`tuple[T, ...]`、`T | None`、Protocol、TypeAlias、Final、Literal、Enum；
* Models、Engine、Services 公共接口不使用无理由 Any；跨线程 Signal 不传无结构 dict；
* 类型忽略必须局部且说明理由，不允许整文件静默关闭；
* 只选择一个强制类型检查器，拟采用 Pyright；Models/Engine 严格，UI/PySide6 边界先标准；
* 类型检查与 pytest 分开执行、分开报告，不同时强制 mypy 与 Pyright；
* ErrorInfo 使用稳定错误码，已发布错误码不得改写含义；
* 日志写入前脱敏，轮转并限制容量，日志失败不得阻塞绘图；
* `uv.lock` 纳入版本控制，依赖与锁文件同步更新；Python 版本由 `.python-version` 和项目配置共同固定；
* 建立统一的本地质量检查入口；CI 是独立阶段。

## 4. 阶段 0–30

### 阶段 0：文档职责、项目初始化、锁文件和目录骨架

目标：在不伪造能力的前提下建立可复现项目基础。

允许修改：

```text
pyproject.toml
.python-version
uv.lock
.gitignore
README.md
.env.example
docs/architecture.md
docs/decisions.md
docs/manual-test-checklist.md
联网确认.md
必要的包目录与 __init__.py
```

任务：

* 盘点现有演示代码、构建产物和工作区改动，不覆盖用户文件；
* 固定经过验证的 Python 与直接依赖组合，依赖变更同步锁文件；
* 确认 `uv.lock` 已跟踪，忽略虚拟环境、日志、缓存、构建产物和本地密钥；
* 建立目标包骨架，但不批量创建 pass 空壳或未实现 Worker；
* 记录文档职责、决策模板、联网核查模板和 supported-formulas 的未来位置；
* 记录基准设备环境：CPU、内存、Windows、缩放、Python 和核心依赖版本；M0 不伪造绘图性能数据。

自动/静态检查：锁文件与项目配置一致；仓库无真实密钥或开发机绝对路径；包可导入。

人工验收：目录与 architecture 一致；现有演示代码的保留/迁移决定明确；用户批准依赖变更后才执行同步。

### 阶段 1：QApplication 启动骨架

目标：建立单一、可关闭的 Qt Widgets 启动链路。

允许修改：`main.py`、`math_drawing_assistant/bootstrap.py`、最小 `ui/main_window.py`、必要资源路径测试。

任务：main 只调用 bootstrap；bootstrap 创建 QApplication、设置应用元数据、创建 MainWindow、show、exec 并返回退出码；资源路径不依赖当前工作目录。

自动测试：bootstrap 的非 GUI 配置可测；重复导入不创建第二个应用。

人工验收：只出现一个窗口；关闭后无残留进程；100%、150%、200% 缩放可启动；当前阶段没有数学、OCR 或 Worker。

### 阶段 2：不可变 Scene/Item、TaskPhase、revision 与 AppController

目标：先固定跨线程契约和状态不变量，不实现真实绘图。

允许修改：

```text
math_drawing_assistant/models/errors.py
math_drawing_assistant/models/requests.py
math_drawing_assistant/models/results.py
math_drawing_assistant/models/plot_specs.py
math_drawing_assistant/models/render_plan.py
math_drawing_assistant/models/viewport.py
math_drawing_assistant/models/state.py
math_drawing_assistant/app_controller.py
tests/test_models.py
tests/test_app_controller.py
```

任务：建立 frozen Scene/Item 请求、Spec、Plan、结果、ViewportRequest/ResolvedViewport、ErrorInfo、PlotKind、TaskPhase；items 使用 tuple；AppController 分配 request_id、维护 current_scene_revision、最后成功结果及任务上下文；派生复制、stale、ready 状态。

自动测试：模型不可变；单图为一个 item；请求模型不含采样/网格参数；TaskPhase 不混入结果/错误状态；每次影响结果的编辑立即递增 revision；旧 request_id/revision 被忽略；失败保留旧结果；关闭后拒绝新任务。

人工验收：模型没有无类型 dict 或共享可变默认值；不建立复杂状态机框架。

### 阶段 3：静态 UI 与可访问性基线

目标：完成 M0 静态界面结构，并从一开始满足基础可访问性。

允许修改：`ui/main_window.py`、`ui/widgets/` 下静态控件、`ui/theme.py`、QSS/SVG 资源、UI 测试、人工测试清单。

任务：单项输入、视口控件、生成/清空/复制、状态区、预览占位；核心操作可键盘完成；Tab 顺序按视觉顺序；焦点清晰且 QSS 不隐藏 focus；状态不只靠颜色；触控目标达到 PRD 最小逻辑尺寸；输入和按钮有可理解名称；高 DPI 下文字不裁切。

自动测试：状态到控件 enabled/visible 映射；关键控件 accessible name；Tab 顺序可验证部分。

人工验收：鼠标、键盘、触控基本操作；100%–200% 缩放；亮/暗主题；错误、警告、成功可区分。

### 阶段 4：固定 PNG 到 Qt 预览链路

目标：在无 Engine 时验证 GUI 图片边界。

允许修改：`ui/qt_image.py`、预览控件、固定测试 PNG/夹具、`tests/ui/test_qt_image.py`。

任务：仅实现 PNG bytes → QImage → QPixmap、加载校验和保持比例缩放；QPixmap 转换与显示在 GUI 主线程；不访问剪贴板。

自动测试：有效/无效 bytes、尺寸、比例、所有权；模块不依赖 Engine 或 QClipboard。

人工验收：窗口缩放不变形，旧图/stale 占位文案可展示。

### 阶段 5：limits、ErrorInfo、错误码、脱敏日志和类型检查入口

目标：在解析器之前建立横切基础设施。

允许修改：集中 limits/config 模块、错误模型与错误码、日志模块及测试、`docs/supported-formulas.md`、性能环境记录、经批准的类型检查配置和本地质量命令。

任务：集中字符/token/AST/数字/指数/item/采样/分支/内存/尺寸/DPI 限制；稳定 ErrorInfo；日志脱敏、轮转和容量；各阶段 elapsed_ms 结构；supported-formulas 单一事实来源；确定类型检查政策。

批准门：安装/配置 Pyright、修改锁文件前必须再次获得用户批准。未批准时只完成工具无关的类型规则和本地命令占位说明，不安装替代工具。

自动测试：限制边界；错误码唯一；日志不泄露凭据、完整公式/路径或图片；日志失败不阻塞业务；类型检查与 pytest 命令分离。

人工验收：日志位置、清理策略和基准设备记录可理解。

### 阶段 6：normalizer、tokenizer、SourceMap、equation_splitter

目标：建立不执行代数运算的输入前端。

允许修改：对应 engine 模块、supported-formulas、错误码和各自单元测试。

任务：受控空格/全角/Unicode 上标/数学符号规范化；SourceMap 将规范化位置映回原文；tokenizer 只产生白名单 token，限制数字与 token 数；equation_splitter 只区分表达式和恰一等号，不猜测多公式或求解。

自动测试：`x^2`、`x**2`、`x²`、`|x|`、受控隐式乘法、空输入、多等号、不等式、非法尾部、超长数字；SourceMap 在插入/替换后仍定位原始片段；固定随机种子无效字符串不崩溃。

人工验收：中文错误指向用户原始输入，不展示内部规范化偏移。

### 阶段 7：受限 parser、plot_classifier 和 typed validators

目标：构造受限 AST，完成显函数分类与结构安全验证。

允许修改：`engine/parser.py`、`plot_classifier.py`、`validators.py`、相关模型、supported-formulas 和 engine 测试。

任务：递归下降或 Pratt parser 构造自有受限 AST；在转换到 SymPy/数值函数前限制节点、深度、数字、指数和参数数；手动/OCR Adapter 归一到同一验证器；分类显函数候选；禁止通用 solve 和验证前的无限制 expand/simplify/factor。

自动测试：属性访问、`__import__`、eval/exec 字符串、Lambda、非法尾部、极端指数、超深嵌套、超长数字、未知函数/参数全部拒绝且不崩溃；`ln(x)`、`lg(x)`、`log(x,10)` 有效，裸 `log(x)` 拒绝；`x=y` 直接互换可支持，`y+1=x+2` 不做通用求解。

人工验收：错误消息不暴露栈；任何失败都能继续下一次输入。

### 阶段 8：explicit sampler

目标：把已验证显函数变为有界绘图数据。

允许修改：typed samplers 模块中的显函数实现、采样模型、limits、测试、supported-formulas。

任务：有限区间与点数限制；标量广播；NaN/无穷/定义域外点；渐近线断线；密集振荡警告；分批取消检查点；返回只读或任务私有数组。

自动测试：`1/x`、`sqrt(x)`、`ln(x)`、`lg(x)`、`log(x,10)`、`tan(x)`、标量常量、定义域外、渐近线、密集振荡和资源边界。

人工验收：不误连渐近线；警告中文可理解。

### 阶段 9：FigureCanvasAgg renderer

目标：由 RenderPlan/typed 数据生成 Qt 无关 PNG bytes。

允许修改：`engine/renderer.py`、渲染模型、renderer 测试。

任务：直接创建 Figure 与 FigureCanvasAgg；共享 ResolvedViewport、坐标轴、网格、尺寸/DPI；每请求独立 Figure；BytesIO 输出；finally 释放资源；不返回 Qt 对象。

自动测试：PNG 头/尺寸；无可见数据不成功；多次生成不泄漏 Figure；异常和取消释放 Figure/Canvas/BytesIO；不要求跨环境 PNG 字节完全一致。

人工验收：固定样例坐标轴、标签和边距正确。

### 阶段 10：常驻 RenderActor、latest-wins 与关闭生命周期

目标：在 M1 整合前建立唯一渲染并发边界。

允许修改：`workers/render_actor.py`、AppController、任务上下文/取消 token、actor 测试、architecture/decisions 的实现反馈。

任务：长期 QThread worker-object 或已批准等价单执行器；一个运行 + 一个最新待任务；新待任务覆盖旧待任务；Engine 全链路在 Actor；明确取消检查点；request_id/revision 双校验；关闭时拒绝新任务、清待任务、作废当前结果、有上限等待；不强制终止。

自动测试：同一时刻只有一个任务进入 Matplotlib；latest-wins；旧 request_id/revision 忽略；异常后消费下一任务；取消释放资源；关闭不接收新任务；不出现运行线程被销毁；不泄漏 Figure。

人工验收：快速提交、渲染中关闭、错误后继续绘图；UI 保持响应。

### 阶段 11：M1 场景流程整合

目标：完成手动显函数 → RenderActor → 预览的离线闭环。

允许修改：AppController、相关 UI、Engine/Actor 适配、端到端与状态测试。

任务：AppController 从当前 UI 快照创建单 item PlotSceneRequest；Actor 内执行请求验证、逐项解析、PlotSceneSpec、ResolvedViewport、RenderPlan、预算、采样、渲染；结果双校验后更新 UI；失败/过期保留旧图。

自动测试：成功、语法失败、资源失败、连续请求、编辑后 stale、旧图复制可用、关闭；AppController 未执行数学处理；GUI 主线程未运行完整 Engine。

人工验收：PRD M1 样例；生成期间窗口可移动；修改输入立即标记旧图。

### 阶段 12：ClipboardService 与 M1 完整验收

目标：完成预览图片复制和 M1 checkpoint。

允许修改：ClipboardService、qt_image/UI/AppController 边界、服务测试、README、supported-formulas、人工清单、基准记录。

任务：GUI 主线程把当前成功 PNG 转为 QImage 并写 QClipboard；记录内部图片指纹；无结果拒绝复制；stale 结果可复制但有清晰提示；完成显函数、安全、Actor、性能和离线回归。

自动测试：复制可用性派生；复制失败不删预览；内部写入标识；M1 全套 pytest、类型检查（若已批准）、独立性能基准。

人工验收：粘贴到 Windows 画图、PowerPoint、Word；断网仍可绘图/复制；记录 CPU、内存、Windows、缩放、版本、启动与典型场景耗时。

### 阶段 13：LineSpec 与四类 Conic Spec 分类

目标：在采样前固定一般直线和受限圆锥曲线的几何模型。

允许修改：plot specs、classifier、typed validators、parser contract、supported-formulas 和相关测试。

任务：`LINE_EQUATION`；LineSpec(A,B,C)；Circle/Ellipse/Hyperbola/Parabola Spec；保存规范化系数、几何参数、中心/顶点、主轴/开口和自动视口信息；只在复杂度验证后做有限一次/二次系数提取；拒绝退化、无实点、xy 旋转项、未知参数和非二次隐式方程。

自动测试：`x=2`、`x+y=1`、`2x-y+3=0`；四类非退化曲线、平移、左右交换、整体非零倍数；退化、无实点、xy、未知参数、三次和变量分母拒绝；巨大/近零系数不误分类。

人工验收：错误明确区分“不支持的方程类型”和“圆锥曲线退化”。

### 阶段 14：参数化直线和圆锥曲线采样

目标：在有限视口内产生正确、可预算的几何分支。

允许修改：typed samplers 的 line/conic 实现、RenderPlan/预算、limits 和测试。

任务：直线与视口矩形求交；圆/椭圆角参数；双曲线两支；抛物线按开口方向；按视口求有限参数区间；单位等比例元数据；单项/场景点数、分支和内存预算；合作取消。

自动测试：竖直/水平/斜线；圆、椭圆、双曲线、抛物线；完全可见、裁切、不可见；各分支不误连；采样点代回方程残差；极端视口/系数不崩溃。

人工/原型：与教材样例和独立数值对照核验；二维 contour 只可作为诊断对照，不进入主链路。

### 阶段 15：M1.5 渲染整合、回归与性能基准

目标：完成直线、圆与圆锥曲线的单项场景闭环。

允许修改：renderer、AppController/UI、Actor 适配、回归测试、supported-formulas、architecture/decisions、基准和人工清单。

任务：同一 Scene/Plan/Actor 链路；显示确定类型、规范化方程、不可见/裁切/精度警告；圆锥曲线默认 equal，用户明确比例优先；失败保留旧图。

自动测试：阶段 13/14 全矩阵、M1 回归、Actor 回归、单位比例、资源预算和原子单项结果。

人工验收：宽/窄窗口和不同 DPI 下圆不变形；复制正确；记录 M1.5 P50/P95、峰值内存和采样规模。

### 阶段 16：多输入行和稳定 item_id

目标：提供明确多项编辑，不从混合文本猜公式边界。

允许修改：`ui/widgets/plot_item_list.py`、相关输入/UI/AppController、模型和 UI/状态测试。

任务：添加、删除、重排，最多 8 项；item_id 在编辑期间稳定；键盘可完成操作；选中项可接未来 OCR；每次影响结果的操作立即递增 revision；逐行错误位置。

自动测试：1–8 项、第 9 项拒绝、增删/重排/编辑 revision、item_id 稳定、错误不串行。

人工验收：鼠标/键盘/触控、Tab 顺序、焦点和行级提示。

### 阶段 17：样式分配器、图例与 scene budget validator

目标：在渲染前形成完整多项 RenderPlan。

允许修改：样式分配器、RenderPlanBuilder、budget validator、models、renderer 接口及测试。

任务：所有 item 先分类/验证；解析共享视口；按 item_id/顺序分配稳定颜色与线型；图例顺序稳定；按点数、分支、内存、输出大小和耗时目标验证场景预算；错误映射 item_id/source span。

自动测试：样式稳定、重排后的图例、灰度线型、混合类型默认 equal、预算各维度边界、预算发生在分类和视口解析之后。

人工验收：图例可读，过长标签安全截断但可查看完整内容。

### 阶段 18：M1.6 原子场景整合和验收

目标：多项场景从 UI 到一张 PNG/复制的完整闭环。

允许修改：AppController、UI、RenderActor、Engine renderer、端到端/回归测试和文档。

任务：最多 8 个 item 在一个 Figure/坐标系渲染；任一项错误、不可见、超限或渲染失败，整场失败且旧图不被覆盖；结果逐项返回类型、样式、警告和可见分支；建立 item fingerprint、逐阶段 elapsed_ms、可扩展 cache_hit/cache_miss 诊断字段和可复现性能基准，但不实现缓存。

自动测试：多显函数、多圆锥、混合场景；第 9 项拒绝；逐项错误；旧图保护；stable item/style/legend；灰度区分；总预算；旧 revision 不覆盖；M1/M1.5 回归。

人工验收：PRD 教学场景、添加/删除/重排、快速连续生成、复制一张完整场景图。

### 阶段 19：可选 M1.6.1 缓存性能优化

入口条件：阶段 18 已建立 item fingerprint、逐阶段 elapsed_ms、可扩展命中字段和可复现基准，且基准证明解析或采样是明显瓶颈；没有证据则跳过并记录“不实施”。

允许修改：经决策指定的缓存模块、Engine/Plan 集成、limits、性能/正确性测试和 decisions。

顺序：先复用上一成功场景中未变的已验证 Spec；再评估采样复用；最后才考虑按字节容量限制的有界 LRU。

缓存键至少覆盖规范化输入、plot kind、parser contract/engine/limits 版本、ResolvedViewport、sampling policy 和质量级别。自动视口变化使视口依赖采样失效；数组只读或防御性复制；不跨版本持久化，不缓存失败/敏感原文。

自动测试：命中等价性、所有失效维度、容量/淘汰、内存上限、并发所有权、失败不缓存。不得把缓存测试倒灌为阶段 18 发布门槛。

### 阶段 20：本地图片导入与模拟 OCR

目标：在不接真实服务时完成安全图片核查流程。

允许修改：图片选择/验证 Service、FormulaReview UI、Ocr/InputAnalysis/Review 模型、模拟服务和测试。

任务：验证格式、编码大小、解码宽高/像素、损坏/伪装/解压炸弹；原图最短生命周期；模拟 OcrResult；本地安全分析得到 InputAnalysisResult；核查模型同时展示原图、OCR 文本、安全显示表达式和类型；一次结果只填当前 item。

自动测试：异常图片、资源上限、取消/清理、模型职责分离、确认/返回/取消、无真实网络。

人工验收：用户能修改识别文本；未确认不绘图；日志无完整路径/图片。

### 阶段 21：SimpleTex 官方、隐私和鉴权核实

目标：只核实外部事实，不写真实服务代码。

允许修改：`联网确认.md`、`docs/decisions.md`、`docs/privacy.md`、必要的独立原型目录（须另行批准且不混入正式架构）。

核实：官方接口/版本、请求/响应、文件限制、QPS/并发/429/配额/计费、置信度可选性、数据保存/删除/地点/训练用途、未成年人/教育条款、客户端授权、费用和重试计费。

入口决策：用户个人 UAT + 经批准凭据存储、供应商正式临时令牌、单独评审的服务端，或关闭真实 OCR。无安全方案不得进入阶段 22。

### 阶段 22：CredentialStore 与 SimpleTexService

目标：建立凭据与 HTTP 供应商边界，不混入数学判断。

允许修改：CredentialStore、SettingsService、SimpleTexService、配置/隐私文档和服务测试。

任务：QSettings 只存普通配置/引用；CredentialStore 实现已批准后端；Service 处理 TLS、鉴权、连接/读取超时、响应大小、并发、重试和 OcrResult 转换；不做规范化/分类/绘图。

自动测试：成功、鉴权失败、超时、非 JSON、缺字段、5xx、429、配额、重试上限、可选 confidence、超大响应、取消、脱敏；普通测试不调用付费 API。

人工验收：凭据填写、验证、替换、删除和卸载行为明确；断网不影响本地绘图。

### 阶段 23：RecognitionWorker 与公式核查

目标：OCR 网络等待不阻塞 GUI，并与 RenderActor 生命周期分离。

允许修改：RecognitionWorker、AppController、核查 UI/模型、线程/状态测试。

任务：独立 QThread worker-object；内部 recognition request_id；过期结果不进入核查；取消立即失效；RECOGNIZING → REVIEWING，用户确认后新建绘图 request；失败保留旧图；关闭清理。

自动测试：旧 OCR 结果、取消、失败、关闭、与 RenderActor 并行但不共享线程、OcrResult 到本地分析的安全边界。

人工验收：断网、错误凭据、超时、重复点击、请求期间关闭、取消后继续离线绘图。

### 阶段 24：Windows 截图最小原型

目标：用当前官方资料和目标 Windows 实测选定截图策略。

允许修改：独立原型、`联网确认.md`、`docs/decisions.md`；未经批准不改正式 ScreenshotService。

比较：有应用身份回调、用户主动粘贴、短时受限剪贴板观察。实测成功、取消、超时、相同截图、多显示器/缩放、截图工具关闭、外部程序同时改剪贴板。

输出：批准的策略、回退策略、截图事件去抖窗口及证据。该窗口不得复用公式派生分析防抖常量。

### 阶段 25：ScreenshotService 与 Clipboard 协调

目标：按批准策略接入截图，禁止常驻自动上传任意剪贴板图片。

允许修改：ScreenshotService、ClipboardService、AppController、相关状态/服务测试和人工清单。

任务：截图任务上下文、开始/超时、基线、内外部图片指纹、独立去抖、内部复制过滤；成功后先预览与隐私提示，用户确认后才 OCR；取消/失败/超时回到稳定阶段。

自动测试：内部复制不触发 OCR；无主动操作不上传；相同图和并发改写；旧截图 request/revision 忽略；关闭清理。

人工验收：多显示器/DPI、成功/取消/超时、复制与截图交错。

### 阶段 26：DPI、多显示器、触控和可访问性最终验收

目标：验证而非首次补做阶段 3 的基础能力。

允许修改：必要 UI/QSS/布局、窗口位置与屏幕服务、人工清单和针对性测试。

任务：100%/125%/150%/175%/200%；多屏移除/切换；逻辑像素；文字不裁切；键盘全流程、Tab、焦点、快捷键、非颜色状态；触控目标；多图灰度辨识。

人工验收：目标一体机或代表设备；记录系统、缩放和屏幕拓扑。

### 阶段 27：样式精修

目标：在结构稳定后统一课堂可读性，不引入复杂动效。

允许修改：QSS、主题、SVG/字体资源、展示文案和视觉回归清单。

任务：统一标题/正文/辅助文字、空/加载/错误/警告状态、间距/圆角/控件高度；字体回退与授权；不破坏焦点和单位比例；避免玻璃拟态、大量渐变或网页式装饰。

人工验收：亮/暗、高 DPI、投影/灰度、目标教学环境。

### 阶段 28：打包工具、资源和许可证核实

目标：先比较和决策，再改正式发布配置。

允许修改：独立打包原型、`联网确认.md`、`docs/decisions.md`、许可证清单；正式配置变更需本阶段明确批准。

核实：pyside6-deploy/Nuitka/PyInstaller 候选，Qt/Matplotlib 资源、onefile/standalone、应用身份、启动/包体/调试/误报、代码签名、Windows 10 风险、Qt/依赖/字体/图标许可证。

不要求两次产物二进制哈希完全一致；要求固定输入、依赖和步骤可重建，并记录差异来源。

### 阶段 29：CI、扫描和发布质量门禁

目标：经用户批准后，把已有本地质量命令映射为自动门禁。

批准门：创建/修改 `.github/workflows`，安装 CI、漏洞、许可证或敏感信息扫描工具前必须获得明确批准。

允许修改：经批准的 workflow、质量脚本、工具配置、锁文件和发布文档。

分层：Models/Engine 纯逻辑跨平台；Qt UI、QClipboard、Windows 截图、多显示器和正式打包在 Windows；发布前干净 Windows 重建。

分别报告：pytest、Pyright（若已批准）、构建/冒烟、漏洞/许可证、敏感信息。不得要求 Ubuntu 完整运行 Windows 桌面验收或 Linux Docker 构建正式 Windows GUI 安装包。

### 阶段 30：发布候选版本

目标：形成可安装、可追踪、可回退的 1.0 候选。

允许修改：版本/发布配置、README/隐私/许可证/人工清单、签名与校验输出；仅修复发布阻塞问题，不顺带扩张功能。

自动验收：全部声明公式/直线/圆锥/多图、安全、Actor、OCR 模拟/受控联调、取消/关闭/资源释放；类型检查；构建冒烟；无密钥/测试图/绝对路径；依赖/许可证/扫描门禁。

人工/实机：干净 Windows 11 安装/启动/升级/卸载/无 Python；经决策的 Windows 10 矩阵；DPI/多屏/触控；PowerPoint、Word、WPS、希沃白板；断网；后台任务关闭；配置/日志/凭据清理；SmartScreen/杀毒/签名。

发布阻塞：`联网确认.md` 的 P0 项关闭或有负责人批准的降级方案；M1.6 若延期必须有正式决策；真实 OCR 无安全鉴权/隐私结论时关闭。

## 5. 统一测试矩阵摘要

### 5.1 解析安全

必须覆盖属性访问、`__import__`、eval/exec 字符串、Lambda、非法尾部、极端指数、超深嵌套、超长数字、固定随机种子的无效字符串；任何输入不得造成进程崩溃或越过资源上限。

### 5.2 显函数

必须覆盖 `1/x`、`sqrt(x)`、`ln(x)`、`lg(x)`、`log(x,10)`、`tan(x)`、标量常量、定义域外点、渐近线断线和密集振荡。裸 `log(x)` 必须拒绝。

### 5.3 直线与圆锥曲线

必须覆盖一般/竖直直线、四类非退化二次曲线、平移标准式、左右交换、整体非零倍数、退化/无实点/xy/未知参数/非二次拒绝、不可见/裁切、分支正确和单位等比例。

### 5.4 多图

必须覆盖最多 8 项、第 9 项拒绝、任一项错误整场失败、旧成功图保护、item/style/legend 稳定、灰度线型、场景预算和 stale 结果保护。

### 5.5 RenderActor

必须覆盖单一 Matplotlib 进入者、latest-wins、旧 request/revision、异常后继续、取消释放、关闭拒绝、线程有序销毁和 Figure 不泄漏。

缓存测试只在阶段 19 实施，不提前成为 M1.6 发布门槛。

## 6. 本地命令与报告格式

具体命令以阶段 0/5 建立的本地质量入口为准。基础类别必须分开报告：

```text
依赖/环境一致性
pytest（快速单元/集成）
Pyright（仅批准并配置后）
独立性能基准
Windows GUI 人工/实机验收
```

每次完成报告：本轮目标、关联需求、初始 Git 状态、允许文件、实际修改、新增/删除、实现与未实现、测试命令及结果、人工步骤、架构/文档同步、风险、是否达到阶段验收、下一阶段建议。不得自动执行下一阶段。

## 7. checkpoint 建议

```text
M0: establish immutable scene and accessible UI skeleton
M1: complete safe RenderActor explicit-function flow
M1.5: add parameterized line and conic plotting
M1.6: add atomic multi-item scenes
M2: add safe local image review
M3: integrate reviewed OCR boundary
M4: integrate verified Windows capture strategy
M5: complete classroom accessibility and usability
M6: prepare signed release candidate
```

checkpoint 文案只描述实际完成内容；测试或人工验收未通过时不得使用“complete”。
