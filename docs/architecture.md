# 数学绘图助手：架构约束

版本：v0.1  
最后更新：2026-08-15
状态：实施中的架构基线（Stage 14E 跨类型最终验收已通过，P0-06 已关闭，Stage 14 已完成；Stage 15、geometry renderer 与应用整合尚未实施）

## 1. 文档职责与事实来源

本文是数据模型、模块边界、线程模型、解析与渲染管线、状态不变量、资源所有权和生命周期的单一事实来源。它描述目标架构，不表示仓库当前已有相应 Python 实现。

其他文档的职责：

* 根目录 `数学绘图助手 PRD.md`：产品范围、用户流程、里程碑、验收标准和非功能要求；
* 根目录 `数学绘图助手_Codex协助开发步骤清单_v0.3.md`：可执行阶段、每阶段允许修改的文件、自动测试和人工验收；
* `docs/decisions.md`：产品与技术方案决策、理由、替代方案和后果；
* 根目录 `联网确认.md`：供应商、法律、目标设备、Qt、Windows 截图和打包工具等外部事实、证据及原型/实机核查；
* 未来的 `docs/supported-formulas.md`：允许语法、错误码、限制值和验收公式的单一事实来源。

易变化的限制值只在集中配置及 `docs/supported-formulas.md` 维护；外部事实只在 `联网确认.md` 维护。本文只定义结构和不变量，不复制具体阈值或供应商承诺。

## 2. 首版边界

采用 Python、PySide6 Qt Widgets、受限数学解析、NumPy 和 Matplotlib Agg。首版不引入：

* 数据库、插件系统、事件总线或依赖注入框架；
* Qt WebEngine、QML 或 Qt Quick；
* 多进程或通用计算机代数系统；
* 服务端、账号系统、遥测或自动更新；
* 为未验证性能问题准备的通用缓存层。

## 3. 核心架构不变量

从 M0 起必须保持以下不变量：

1. 所有绘图入口都是 `PlotSceneRequest`；单图是 `items` 长度为 1 的场景，多图是长度大于 1 的场景。
2. 请求、已验证规范、渲染计划和结果是不可变快照；后台任务不得引用 UI 正在编辑的可变对象。
3. `AppController` 只协调用户意图、任务编号、revision、阶段和结果接纳，不做公式规范化、分类、采样或 Matplotlib 操作。
4. 所有完整绘图请求都进入唯一、常驻、单线程串行消费的 `RenderActor`；不存在 GUI 主线程绘图旁路。
5. Matplotlib `Figure`、`Axes`、`FigureCanvasAgg` 和字体初始化只在渲染线程使用，不依赖 `pyplot` 全局状态，不调用 `pyplot.show()`。
6. `request_id` 决定任务是否仍是最新任务；`scene_revision` 决定结果是否属于当前输入。两者都匹配时结果才可成为当前成功结果。
7. `scene_revision` 在任何影响结果的编辑发生时立即递增，不防抖。
8. 失败、取消或过期结果不能覆盖 `last_successful_result`；旧图可继续预览和复制，但必须标记为 stale。
9. 多项场景采用原子语义：任一 item 失败、不可见或资源超限，本次场景整体失败。
10. 先完成结构验证和分类；视口解析若需要数值探测，必须先通过独立、集中配置且有硬上限的探测预算。得到 `ResolvedViewport` 后构造完整 RenderPlan 并验证最终预算；任何正式采样或渲染前必须通过该最终预算。
11. 原始用户文本和 OCR 文本不能直接进入可执行式解析器或宽松通用解析器。
12. PNG bytes、数值数组和元数据的所有权必须明确；Qt GUI 对象不跨入 RenderActor。

## 4. 模块边界

```text
UI
↕ 用户意图 / 显示模型
AppController
├─ RenderActor → Engine → PlotSceneResult
├─ RecognitionWorker → SimpleTexService → OcrResult
└─ ScreenshotService / ClipboardService / CredentialStore / SettingsService
```

### 4.1 UI

负责创建控件、收集用户输入、发出用户意图、展示状态与结果，以及在 GUI 主线程执行 `PNG bytes → QImage → QPixmap`。UI 不解析数学表达式、不访问 OCR 服务、不判断过期结果，也不持有 Engine 内部对象。

静态 UI 阶段即建立可访问性基线：键盘可完成核心操作、Tab 顺序符合视觉顺序、焦点可见、状态不只靠颜色、触控目标达到 PRD 约束、高 DPI 下文字不被裁切。QSS 不得隐藏 focus 状态。

### 4.2 AppController

负责：

* 从 UI 当前值创建不可变 `PlotSceneRequest`；
* 分配内部 `request_id`，递增 `scene_revision`；
* 维护 `TaskPhase`、当前任务上下文和最后成功结果；
* 向 RenderActor 提交请求，接收结构化结果；
* 同时校验 `request_id` 与 `scene_revision`；
* 协调 OCR、截图、核查、绘图、复制与关闭流程；
* 将可显示状态通知 UI。

不负责：

* normalizer、tokenizer、parser、分类或验证；
* 构造 `PlotSceneSpec` 或 `RenderPlan`；
* NumPy 采样或 Matplotlib 渲染；
* HTTP、凭据存储或 QWidget 创建。

### 4.3 Engine

Engine 是 Qt 无关的数学与渲染业务层，接收完整 `PlotSceneRequest`，依次完成请求验证、规范化、受限解析、分类、分类型验证、视口解析、计划、预算、采样和渲染，返回 `PlotSceneResult`。

Engine 不访问网络、剪贴板、QSettings、真实凭据或 QWidget。除时间与诊断字段外，相同输入和固定版本配置应产生等价结果。

### 4.4 Services

* `SimpleTexService`：只负责 HTTP、鉴权、超时、限流/重试约束和供应商响应到 `OcrResult` 的转换；
* `ScreenshotService`：只负责经原型批准的 Windows 截图策略和截图任务结果；
* `ClipboardService`：只在 GUI 主线程读写 `QClipboard`，并区分内部写入与外部截图事件；
* `SettingsService`：只保存普通配置或凭据引用；
* `CredentialStore`：独立接口，负责真实凭据的读取、写入、替换和删除，具体后端须经决策批准。

### 4.5 Worker 与 Actor

`RecognitionWorker` 承载网络/OCR 生命周期；`RenderActor` 承载绘图生命周期。它们使用不同线程、不同取消标记和不同 request_id，不共享 Worker 实例。

Worker/Actor 不修改 QWidget，不返回 `QWidget`、`QPixmap` 或 `QClipboard`，跨线程 Signal 使用明确结果类型，不传无结构 `dict`。

### 4.6 阶段 12 复制边界

阶段 12 的 `CopyCandidate` 与 `CopyPreparation` 是 Qt-free 的不可变快照。只有 `AppController` 已接纳的成功 `PlotSceneResult.png_bytes` 可以成为复制来源；UI 不得从 `QLabel`、`QPixmap`、截图或 preview 反取内容。`ClipboardService` 只在 GUI 主线程把该 PNG 解码为 `QImage` 后写入 `QClipboard`，并在 `setImage` 前建立内部写入上下文。

源 PNG 的 SHA-256 与规范 RGBA8888 `QImage` 指纹承担不同语义，不能互相替代。复制临时反馈仅覆盖显示状态，结束后恢复 Controller 的真实 fresh/stale/error 状态；复制失败不得改变 revision、`TaskPhase`、旧成功结果或 preview。正式 benchmark 仅复用 runtime factory 与渲染链，不创建复制意图、不触发真实 `ClipboardService`，也不写真实剪贴板。

## 5. 不可变场景数据模型

公开模型使用现代类型注解，优先采用 `@dataclass(frozen=True, slots=True)`；集合字段优先使用 tuple。确需可变缓冲时必须局部创建，并在跨线程前转换为不可变快照或明确转移所有权。

### 5.1 请求模型

```text
PlotSceneRequest
├─ request_id
├─ scene_revision
├─ items: tuple[PlotItemRequest, ...]
├─ viewport: ViewportRequest
├─ image_width / image_height / dpi
├─ show_grid / show_legend
└─ created_at

PlotItemRequest
├─ item_id
├─ input_text
├─ input_source
├─ requested_plot_kind
├─ display_order
└─ style_key (optional)
```

`PlotItemRequest` 只表达用户意图，不公开采样点、网格或分支等底层策略参数。采样质量来自集中配置或明确的场景级质量选项。

### 5.2 视口

`ViewportRequest` 表示用户请求：

* `mode`：auto 或 manual；
* 可选的 x/y 边界；
* `aspect_request`：auto 或 equal。

`ResolvedViewport` 表示最终绘图范围：

* x/y 四个边界均为有限合法数值；
* 最小值严格小于最大值且跨度符合限制；
* 坐标比例已经解析；
* 记录自动推导或手动来源。

Engine 及采样器不接收含缺失边界或 auto 语义的混合 `Viewport`。

`aspect_request` 只属于 `ViewportRequest`，不在 `PlotSceneRequest` 另存一份。它与范围共同定义一套场景级坐标变换，天然由全部 items 共享；修改 `viewport.aspect_request` 与修改其他视口字段一样立即递增 `scene_revision`。M1.6 仍只有一套共享坐标轴，不能为单个 item 覆盖该值。

显函数自动 y 范围属于视口解析，不得在 sampler 或 renderer 中静默改写用户请求。手动四边界优先；自动推导失败时使用 PRD 规定的产品回退。若自动推导需要对已验证显函数做数值探测，探测规模必须先通过集中限制和探测预算，探测结果只用于形成 `ResolvedViewport`，不能绕过最终 RenderPlan 预算。

### 5.3 已验证规范

```text
PlotSceneSpec
└─ items: tuple[PlotItemSpec, ...]
   ├─ ExplicitFunctionSpec
   ├─ LineSpec
   ├─ CircleSpec
   ├─ EllipseSpec
   ├─ HyperbolaSpec
   └─ ParabolaSpec
```

`PlotKind` 至少包含：

* `AUTO`：只允许出现在请求中；
* `EXPLICIT_FUNCTION`；
* `LINE_EQUATION`；
* `CONIC_EQUATION`。

每个几何 Spec 保存规范化系数、几何参数、中心或顶点、主轴或开口方向、自动视口所需信息，以及后续教学标注可复用但当前不一定展示的信息。

Spec 不用“多个可空字段 + 布尔标志”模拟联合类型。可以用明确 dataclass 联合、`TypeAlias`、`Literal` 或 Enum 表达分支。

### 5.4 RenderPlan

`RenderPlan` 在所有 item 已验证且视口已解析后创建，至少包含：

* `PlotSceneSpec`；
* `ResolvedViewport`；
* 每项稳定样式；
* 每项采样策略与分支计划；
* 输出宽高和 DPI；
* 预计总采样点数、分支数和内存；
* 预算验证结果；
* 计划/限制版本。

不得在 item 尚未分类或视口尚未解析时计算完整资源预算。请求级早期检查只处理字符数、item 数、输出参数等无需分类即可判断的限制。

M1 的单项场景已经使用 `RenderPlanBuilder` 和 `budget_validator`：阶段 8 首次实现单项 `ResolvedViewport` 解析、RenderPlan 构建和正式采样前预算门禁。M1.6 只扩展多项样式分配、场景总预算和逐项错误映射，不能把这套能力的首次实现延后到多项阶段。

### 5.5 结果模型

`PlotItemResult` 至少包含 `item_id`、规范化输入、确定的 `plot_kind`、已分配样式、警告、可见分支/片段元数据和可选 `ErrorInfo`。

`PlotSceneResult` 至少包含：

* `request_id` 与 `scene_revision`；
* success；
* 仅在原子成功时存在的 PNG bytes；
* 顺序与请求一致的 item results；
* `ResolvedViewport`；
* 警告、`ErrorInfo`；
* 各阶段 `elapsed_ms`、总采样点数、预计/实际资源元数据；
* 为未来性能优化预留的 `cache_hit` / `cache_miss` 可选诊断字段。

bytes 是不可变值；发送方在发送后不再修改其来源缓冲。NumPy 数组若跨组件共享，必须设为只读或进行防御性复制；首版优先只把渲染后的 bytes 和小型元数据跨线程返回。

## 6. 安全解析管线

统一管线：

```text
PlotSceneRequest
→ request_validator
→ 对每个 item：
   normalizer
   → tokenizer
   → equation_splitter
   → restricted parser
   → plot_classifier
   → typed validator
→ PlotSceneSpec
→ viewport resolver
   → 可选的受预算数值探测
→ ResolvedViewport
→ RenderPlanBuilder
→ budget_validator
→ typed samplers
→ FigureCanvasAgg renderer
→ PlotSceneResult
```

### 6.1 SourceMap

normalizer 返回规范化文本及 `SourceMap`。SourceMap 能把规范化文本的字符区间、token 区间和解析错误位置映射回原始用户输入。规范化不得静默删除未知尾部。

### 6.2 Tokenizer 与 parser

不得把用户文本或 OCR 文本直接交给：

* `eval`、`exec`；
* 无约束 `sympify`；
* 对原始输入直接使用的通用 `parse_expr`；
* 对原始 OCR LaTeX 直接使用的宽松 LaTeX parser。

tokenizer 只识别当前版本白名单内的数字、x/y、pi/E、函数、运算符、括号、函数参数逗号、受控隐式乘法以及允许的 Unicode 数学符号。

首选流程是先构造项目自有的受限 AST，完成 token 数、节点数、深度、数字位数、指数和函数参数数量限制后，再转换为受限 SymPy 节点或数值函数。若直接构造 SymPy 节点，必须证明构造过程不会在复杂度验证前触发无界求值；未经该证明不得作为安全边界。

手动文本与 OCR LaTeX 可以使用不同 Adapter，但最终进入同一 token、AST 和结构验证器。

### 6.3 集中限制

集中限制覆盖：字符数、token 数、AST 节点数、嵌套深度、单个数字位数、小数位数、有理数分子/分母位数、指数绝对值、函数参数数、item 数、单项与场景总采样点数、分支数、内存、输出尺寸和 DPI。

在复杂度验证前，不执行无约束的 `expand`、`simplify`、`factor`、`solve` 或通用代数变换。圆锥曲线的有限次数系数提取只能发生在输入已通过结构/复杂度限制之后。

## 7. 分类型分类与采样

M1.5 支持的图形、方程、精确系数、隐式乘法继承、M1 路由和拒绝边界以 [`m1.5-math-input-scope.md`](m1.5-math-input-scope.md) 为产品范围基线。本节只定义分类、Spec 和采样架构，不得自行扩大或收窄该范围。

### 7.1 显函数

单独表达式、`y=rhs(x)`，以及等号一侧恰为 `y` 的 `lhs(x)=y` 可成为 `EXPLICIT_FUNCTION`。不做通用移项或 `solve()`；例如 `y+1=x+2` 不作为显函数快捷变换。

现有 M1 专用 classifier/validator 和 `analyze_explicit_function` 保持原行为。阶段 13 的统一 M1/M1.5 路由位于其外层：等号一侧恰为 `y`、另一侧再次含 `y` 时不接受为显函数，但可继续进入有界一次/二次分类；例如统一路由把 `y=x+y` 形成 `LINE_EQUATION`，而 M1 专用入口仍返回既有 `explicit_function_y_not_allowed`。fallback 不调用 `solve()`，也不修改旧 validated receipt。

显函数采样处理标量返回、定义域外点、NaN、无穷大、渐近线断线和密集振荡警告。密集振荡不得声称精确统计任意函数的“周期数”；阶段 8 应基于受预算采样序列定义可测代理指标，并把指标、阈值和验收样例写入 `docs/supported-formulas.md`。

### 7.2 一般直线

总次数为 1、仅含 x/y、数值系数且非退化的方程分类为 `LINE_EQUATION`，例如 `x=2`、`x+y=1`、`2x-y+3=0`。`LineSpec` 使用规范化 `Ax+By+C=0`，要求 `(A,B)` 不同时为零。

采样时直接计算直线与 `ResolvedViewport` 矩形边界的交点，去重后形成最多一个可见线段；不通过二维网格或 contour。

### 7.3 圆与轴向平行圆锥曲线

受限二次方程先形成规范化系数，再分类为 `CircleSpec`、`EllipseSpec`、`HyperbolaSpec` 或 `ParabolaSpec`。拒绝退化、无实点、含 xy 旋转项、未知参数和非二次隐式方程。

主实现使用几何参数化采样：

* 圆、椭圆：角参数；
* 双曲线：按可见参数区间分别生成两支；
* 抛物线：按开口方向和可见视口参数化；
* 每支独立返回，禁止错误连接不同分支。

通用二维 contour 不是受限直线/圆锥曲线的默认主实现。它只可作为诊断对照或未来任意隐式曲线方案的独立原型，不能绕过当前 OUT 范围。

### 7.4 Stage 14B/14C/14D-1/14D-2/14E 公共契约、参数化原型与阶段边界

Stage 14B-1 把既有 M1 显函数链路扩展为可容纳 Stage 13 六种 exact Spec 的统一公共边界；Stage 14B-2 在该边界内放行 exact、非退化 `LineSpec`；Stage 14C 沿用同一边界放行 `CircleSpec | EllipseSpec`；Stage 14D-1 放行 `HyperbolaSpec`；Stage 14D-2 继续沿用同一边界放行 `ParabolaSpec`。正式单项数据流固定为：

```text
Stage 13 typed PlotSceneSpec
→ resolve_single_item_viewport
→ ResolvedViewport
→ RenderPlanBuilder.build
→ 带内部 approval receipt 的 RenderPlan
→ typed sampler
→ SampledCurve
```

`resolve_single_explicit_viewport` 与 `build_single_explicit_render_plan` 保留原签名，仅作为统一实现的兼容 wrapper；不得保留第二套 resolver、Builder 或绕过 RenderPlan/receipt 的采样入口。

Stage 14B-2/14C/14D-1/14D-2 的直接原型沿用同一条链路：`analyze_plot_item → PlotSceneSpec → resolve_single_item_viewport → RenderPlanBuilder.build → sample_parameterized_curve`。resolver 负责唯一的视口解析，Builder 负责 exact 边界几何、可见 segment 规划并签发现有 receipt，sampler 只消费已批准端点或参数区间；sampler 不重新解析视口、不重新求交/规划区间，也不调用 Builder。

用户意图与解析结果使用两个 exact enum：

* `AspectRequest` 为 `DEFAULT | AUTO | EQUAL`，只存在于 `ViewportRequest`；
* `ResolvedAspect` 为 `AUTO | EQUAL`，只存在于 `ResolvedViewport`；
* `DEFAULT` 对显函数和一般直线解析为 `AUTO`，对圆、椭圆、双曲线和抛物线解析为 `EQUAL`；用户显式 `AUTO/EQUAL` 始终优先；
* exact `LineSpec` 自动视口使用有界 exact arithmetic，成功 source 为 `ViewportSource.AUTO_GEOMETRY`；它不运行显函数 probe 或 fallback；
* exact `CircleSpec | EllipseSpec` 自动视口从完整数学包围盒推导，应用集中 padding/span/coordinate limits，成功 source 为 `AUTO_GEOMETRY`；它不运行显函数 probe 或 fallback；
* exact `HyperbolaSpec` 自动视口从有限教学窗口推导：水平横轴为 `x=h±sqrt(2*a²), y=k±sqrt(b²)`，垂直横轴交换坐标角色；outward float64 包围完成后复用 oval 的同一套 padding/span/coordinate limits，成功 source 为 `AUTO_GEOMETRY`，不运行 probe、numeric executor 或 fallback；
* exact `ParabolaSpec` 自动视口采用 `t∈[-1,1]` 的有限教学窗口：竖轴时 `x=h±2|p|` 且 y 覆盖 `k,k+p`，横轴时交换坐标角色；exact 边界 outward 转换后复用同一 padding/span/coordinate limits，成功 source 为 `AUTO_GEOMETRY`，不运行 probe、numeric executor 或 fallback。

计划层保持一个顶层 `RenderPlan`，并形成两个封闭联合：

```text
RenderItemPlan = ExplicitRenderItemPlan | GeometryRenderItemPlan
GeometrySegmentPlan = LineSegmentPlan | ParameterIntervalPlan
```

`LineSegmentPlan` 只表示两个不同的有限端点，固定 mathematical branch 0、两个样本和 `OPEN`；`ParameterIntervalPlan` 显式保存 mathematical branch ID、有序有限参数区间、样本数和 `SegmentClosure`。`GeometryRenderItemPlan` 禁止两类 segment 混装，并分别校验数学分支数、drawable segment capacity、样本总数和 batch 上界。数学分支数描述曲线本体；segment/path capacity 描述经视口裁切后的可绘制片段，两者不得混用。

approval receipt 是内部 typed union。签发前和每次消费时都统一交叉验证 exact Spec、item plan、memory budget 和版本组合，并独立快照 Spec、精确系数、provenance/source spans、Fraction 分子分母、几何 enum、ResolvedViewport、segment、版本、全部预算与输出字段。对象即使通过 `object.__setattr__` 被篡改，也只能验证失败，不重新签 receipt。

合法版本/预算组合只有：

| item plan | numeric executor version | parameterized sampler version | memory |
|---|---|---|---|
| `ExplicitRenderItemPlan` | 当前 numeric executor version | `None` | exact `RenderMemoryBudget` |
| `GeometryRenderItemPlan` | `None` | `parameterized-sampler-v1` | exact `ParameterizedRenderMemoryBudget` |

`RenderMemoryBudget` 保持公开名称并新增 `segment_metadata_bytes`；参数化预算独立记录最终 x/y、artist、segment ranges/metadata、parameter batch、transcendental/validation workspace、RGBA canvas 与 PNG 缓冲/复制，提供 fixed、batch 和 total 求和。参数化预算不复用 numeric executor 的 `executor_extra_batch_bytes`。直线、圆/椭圆、双曲线和抛物线分别由 Builder 与 sampler 调用各自唯一的共享参数化预算公式；Builder 在签发 plan 前审批完整预算，sampler 在第一次数组分配前重新计算并逐字段核对。

成功结果联合为：

```text
SampledCurve = SampledExplicitFunction | SampledParameterizedCurve
```

`SampledExplicitFunction` 保持 exact class、构造签名和原 dataclass 字段，通过只读 property 投影 branch ID 为 `None` 的 segment metadata。`SampledParameterizedCurve` 只接受自有、只读 `float64` x/y 和 `int64 [start, stop)` ranges，每个 segment 至少两个点并与 typed metadata 一一对应；普通公共构造不能注入 approval snapshot。

Stage 14B-2 已交付一般直线的 exact 自动视口、exact 矩形边界求交、稳定端点排序、ULP 合并与归一化残差门禁，以及只读两点开放线段采样。Stage 14C 已交付圆/椭圆的 outward 几何包围、自动视口、边界根加循环 sweep 的最多四个可见角区间、显式 `CLOSED` 完整曲线、确定性点数/batch/预算、exact 隐式残差与正式只读参数化采样；算法版本由 `angular-sampling-policy-v1` 标识。

Stage 14D-1 固定 `HyperbolaSpec` 的两个数学分支：branch 0 是横轴负方向（左支或下支），branch 1 是横轴正方向（右支或上支）。令 `a=sqrt(semi_transverse_squared)`、`b=sqrt(semi_conjugate_squared)`、`s=-1/+1` 对应 branch 0/1：

```text
水平：x=h+s*a*cosh(t), y=k+b*sinh(t)
垂直：x=h+b*sinh(t), y=k+s*a*cosh(t)
```

Builder 先把最终 float64 viewport 边界还原为 exact `Fraction`，按分支用横轴距离平方与 `a²` 比较，判定不可进入、孤立顶点接触、含顶点的一段或排除顶点的正负两段；只有 exact 判定完成后才计算有限 `asinh/acosh` 根。`sinh` 单调区间与 `cosh` 的一或两段求交，每支最多两个 `OPEN` interval、总容量四个，按 `(branch_id, parameter_start)` 稳定排序且 ranges 永不跨支误连。根的 float64 舍入若落在边界外，只能在 policy 的 ULP 上限内向区间内部修正；无法修正即返回 `NUMERIC_RANGE_UNSUPPORTED`。

`hyperbolic-sampling-policy-v1` 固定每像素 1 点、开放段至少 2 点、preferred batch 4096、parameter merge 与 viewport boundary 各 8 ULP、target/maximum residual 32/256 ULP、取消间隔 256。每段以最大绝对端点参数处的 `dx/dt,dy/dt` 像素空间范数为导数上界，点数为 `max(2, ceil(max_pixel_speed*parameter_span)+1)`。sampler 在首次数组分配前复算完整 hyperbola 预算和安全 sinh/cosh 范围，使用 `j/(N-1)` 并固定两端点，逐点用 primitive equation 的 exact normalized residual 复验；所有成功结果因数学曲线无界而报告 `VIEWPORT_CLIPPED`，32–256 ULP 报 `SAMPLING_PRECISION_LIMITED`，超过 256 ULP 或发生 branch/segment 数值坍缩则 typed 拒绝。

Stage 14D-1 没有升级既有 RenderPlan、parameterized sampler 或 limits version，也没有新增第二套 resolver、receipt 或公开 sampler；这些已审核选择在 Stage 14D-2 继续冻结。Stage 14D-2 不顺带修改已关闭的双曲线路径或其审核观察。

Stage 14D-2 固定抛物线只有一个数学分支 `branch_id=0`，最多两个互不连接的 `OPEN` 参数区间。令顶点为 `(h,k)`、有符号焦参数为 `p`：

```text
竖轴（上/下）：x=h+2pt, y=k+pt²
横轴（左/右）：x=h+pt², y=k+2pt
```

`p` 的符号自然确定开口，不建立四套算法。Builder 把 viewport 分成 cross 轴与 opening 轴，exact 计算 `cross_interval=(cross_edge-cross_vertex)/(2p)` 和 `q_interval=(axis_edge-axis_vertex)/p`，再将 `t²` 限制于 `q_interval∩[0,+∞)`。可见性、空集、孤立切点、单双区间以及有理端点与 `±sqrt(q)` 的顺序全部在任何 float/sqrt 转换前用 Fraction、符号和平方比较决定；转换后只允许在 `parameter_merge_ulps` 内向区间内部修正，并逐端点评估 viewport 容差。float64 坍缩使用 `NUMERIC_RANGE_UNSUPPORTED`，exact 不可见或孤立切点使用 `NO_VISIBLE_CURVE`。

`parabolic-sampling-policy-v1` 固定每像素 1 点、开放段至少 2 点、preferred batch 4096、parameter merge 与 viewport boundary 各 8 ULP、target/maximum residual 32/256 ULP、取消间隔 256。每段在最大绝对端点参数处计算 `dx/dt,dy/dt` 的像素速度上界，点数为 `max(2, ceil(max_pixel_speed*(stop-start))+1)`。抛物线预算固定 segment capacity 2、parameter-root capacity 6、interval capacity 2；parameter batch 只有 `B*8`，`t²` 直接写入最终坐标 slice，transcendental workspace 为 0。exact workspace 以命名的 interval/residual 同时存活整数和既有 axis-aligned-conic 位宽证明计入，不使用经验倍率。

sampler 在首个输出数组分配前重投影 geometry、逐字段重算预算并复验 receipt/limits，只消费已批准 interval。每个区间使用绝对样本索引的 `j/(N-1)` 并显式固定两端点；逐点以 primitive equation 和 `Fraction.from_float` 计算 normalized residual。超过 256 ULP typed 拒绝，32–256 ULP 成功并报告 `SAMPLING_PRECISION_LIMITED`；曲线无界，因此所有成功结果报告一次 `VIEWPORT_CLIPPED`，计数为实际成功 segment 数。x/y/ranges 自有只读，取消不保留部分结果。

Stage 14D-2 没有升级 RenderPlan、parameterized sampler 或 limits version，也没有新增第二套 resolver、receipt 或公开 sampler。

Stage 14E 以直线、圆、椭圆、双曲线、抛物线和既有 M1 显函数组成跨类型矩阵，复验同一 analyzer/resolver/Builder/receipt/sampler 边界、AUTO_GEOMETRY、aspect、segment topology、预算、只读数组、snapshot、warning/error、receipt 篡改、极端合法输入、无可见曲线和合作取消。独立 `Fraction.from_float` 数值 oracle 不调用生产 normalized residual、projector 或 planner；静态边界检查确认生产采样路径未导入 contour、未重入 resolver/Builder/interval planner，也未把几何类型接入 renderer、`SceneRenderExecutor`、Actor、Controller、UI 或新的公开流水线。

参数化开发探针 `stage14-parameterized-prototype-v1` 只测量 `analyze_plot_item → resolve_single_item_viewport → RenderPlanBuilder.build → sample_parameterized_curve`。14 个固定场景、每场景 1 次预热和 5 次保留测量全部成功；原始总耗时范围为 0.9235–70.9235 ms，最大获批总内存预算为 69,301,000 bytes。该数据只证明当前开发机上的 Stage 14 原型可执行、可预算且明显低于两秒筛查线；不包含 renderer、Actor、PNG、GUI、preview 或 copy，不计算或宣称正式 P50/P95，也不构成 M1.5 性能验收。

据跨类型测试、静态边界和确定性证据包，P0-06 于 2026-08-15 关闭，Stage 14 完成并允许进入 Stage 15。Stage 15、geometry renderer、`SceneRenderExecutor`、Actor、Controller、UI、多 item、contour 后备链路、P0-07、真实教材矩阵和 M1.5 checkpoint 仍未实施或完成。

## 8. RenderActor 并发模型

### 8.1 正确链路

```text
UI
→ AppController 创建不可变 PlotSceneRequest
→ RenderActor
→ Engine 完成解析、验证、规划、采样和渲染
→ PlotSceneResult
→ AppController 校验 request_id + scene_revision
→ UI
```

RenderActor 由一个长期存在的后台 QThread worker-object 或经批准的等价单并发执行器承载。应用中只存在一个 RenderActor 消费者，不创建多个渲染 worker 再用全局 Matplotlib 锁补救。

阶段 10 的实现采用一个 GUI-owner `RenderActor` facade 和一个移动到唯一常驻 `QThread` 的 `_RenderWorker`。facade 的唤醒信号以 queued connection 进入 worker；worker 的内部结果信号再以 queued connection 进入 facade 的 `_relay_result`，由这个 GUI relay 在 owner/GUI 线程发射公共 `result_ready`。Engine 和 Matplotlib 不进入 GUI 线程，Qt GUI 对象也不进入 Actor 线程。

上述唯一常驻 RenderActor、GUI relay 与正式 Qt/Agg 线程边界已经通过阶段 10 最终技术复验；Matplotlib 仍只由唯一 worker 串行进入。

阶段 11 实施反馈：正式 bootstrap 只创建一个 `SceneRenderExecutor` 和一个 `RenderActor`，正式调用链为：

```text
MainWindow
→ AppController
→ RenderActor
→ SceneRenderExecutor
→ Engine/Agg
→ GUI relay
→ PlotPreview
```

`AppController` 只协调 UI 快照、请求、revision 和结果接纳，不做数学处理；`QImage` 与 `QPixmap` 只在 GUI 线程创建和使用。结果以 `ACCEPTED_SUCCESS`、`HANDLED_CURRENT_FAILURE` 和 `IGNORED_OBSOLETE` 三分处理：输入修改立即使旧图 stale，`request_id` 与 `scene_revision` 必须同时匹配；失败、取消和过期结果不覆盖上一张成功图。一个 current 加一个 latest pending 的有界 latest-wins mailbox 保持不变。

### 8.2 队列和取消

阶段 10 的 mailbox 是共享锁保护的单槽 mailbox，不是 FIFO。Actor 最多持有：

* 一个当前运行任务；
* 一个最新待运行任务。

`submit` 在 mailbox 锁内用新任务替换 `pending`，取消被替换的 pending，并取消 current token；`take_pending` 在同一把锁内把唯一 pending 移为 current；`complete` 在同一把锁内清除 current，并线性化“是否允许发布结果”的决定。因此 current/pending 不会同时指向两个运行任务，中间 pending 可以在进入 executor 前被覆盖，且不存在无界积压。

新请求覆盖尚未开始的旧待运行请求（latest-wins）。协作取消使用 `workers/cancellation.py` 中 Qt 无关的 `CancellationToken`；取消边界至少包括 analyzer、spec builder、viewport resolver、RenderPlan builder、正式 sampler 和 renderer 之间的阶段边界；sampler 还在执行批次间轮询，renderer 在资源创建前、片段间、PNG 编码前后及返回 bytes 前轮询。同一个 task token 贯穿 Actor、sampler 和 renderer；`SamplingCancelled` / `RenderCancelled` 是中性取消结果，只由 Actor 的 token/result gate 抑制，不扩展 `ErrorCode`。

结果门选择 **B**：`close()` 在 mailbox 锁内同时关闭提交门和结果门、清除 pending 并取消 current。关闭前尚未完成发布决定的结果不得发射；已经在线性化点获准、但 queued signal 仍在途的结果可以抵达 GUI relay，随后必须由已进入 `SHUTTING_DOWN` 且已清除 request/revision 上下文的 AppController 拒绝。不得把断开所有信号或无界等待当作结果门。

取消是协作式的，不使用 `QThread.terminate()`。即使某个底层操作不能立即中断，旧 `request_id` 或 `scene_revision` 也使其结果无效。

真实 Qt worker 在每任务消费边界遏制 `SystemExit`、`KeyboardInterrupt` 等 `BaseException`；这类异常不映射为业务结果，current token 仍在 `finally` 中清除，mailbox 随后继续消费 pending 任务。

### 8.3 Matplotlib 边界

* 使用 Agg 非交互式后端；
* 直接创建 `Figure` 和 `FigureCanvasAgg`；
* 不依赖 `pyplot` 全局状态；
* Figure、Axes、Canvas、字体管理和保存 PNG 均在 RenderActor 线程；
* 每个请求在 `finally` 中关闭 BytesIO，清理 Figure/Axes 并释放 Figure、Canvas 和大型 sampled 数组引用；
* 任一时刻只有一个请求进入 Matplotlib。

### 8.4 关闭生命周期

应用关闭时按顺序：

1. `TaskPhase` 进入 `SHUTTING_DOWN` 并拒绝新任务；
2. 清除待运行请求；
3. 使当前 request_id 失效并设置取消标记；
4. 断开或门控会更新 UI 的结果通道；
5. 请求线程有序退出并执行有上限的等待；
6. 不让过期信号访问已关闭界面；
7. 不使用强制终止补救正常生命周期设计。

阶段 10 实现只接受 `[0, 60000]` ms 的 shutdown timeout；`bool`、非整数、负数和超上限值在任何 lifecycle、mailbox、token、result gate、stop flag 或 keepalive registry 变化前被拒绝，并且不会进入 `QThread.wait()`。

`shutdown(timeout_ms)` 只执行一次有上限的协作等待。等待成功后进入 `STOPPED`；等待失败后进入 `TIMED_OUT`，并把仍在运行的 QThread、worker 和 finish observer 放入同步的临时 keepalive 注册表，直到线程真的结束或后续 `shutdown` 重试成功。超时后的重复 `shutdown` 可以重试，并在成功后最终进入 `STOPPED`。该注册表只防止 `QThread: Destroyed while thread is still running`，不把失败改写为成功。

当 `shutdown()` 返回 `False` 时，长生命周期调用者必须保留/重试 Actor；不得完成最终 UI 应用、`QApplication`、模块或进程退出。阶段 11 已将该退出门接入正式 `MainWindow.closeEvent` 与 bootstrap：`shutdown=False` 阻止退出并允许后续重试。阶段 12 的复制边界、正式性能证据和有限 M1 checkpoint 已通过总架构师独立审核；不改变后续阶段的生命周期门禁。

## 9. 状态模型与 revision

`TaskPhase` 只表示当前活动：

```text
IDLE
CAPTURING
RECOGNIZING
REVIEWING
RENDERING
SHUTTING_DOWN
```

六值枚举表达的是唯一的用户可见前台活动。首版 AppController 不同时启动截图/OCR 与绘图；冲突操作在另一任务活动时被禁用或明确拒绝。RenderActor 与 RecognitionWorker 可以同时常驻且生命周期分离，但这不表示首版允许两个前台任务并发。未来若要允许真正并发，必须先以新决策把状态改为可表达正交活动的模型。

“就绪”和“错误”不是 TaskPhase。错误是 `last_error_notice`；ready 是派生状态。

AppController 保存的核心状态：

* `current_scene_revision`；
* `current_render_request_id`；
* `current_recognition_request_id`；
* `last_successful_result`；
* `last_result_scene_revision`；
* `last_error_notice`；
* 当前截图、OCR 或渲染任务上下文。

以下值只派生，不重复保存为可失配字段：

```text
has_plot_result = last_successful_result is not None
copy_enabled = last_successful_result is not None
result_is_stale = (
    last_successful_result is not None
    and last_result_scene_revision != current_scene_revision
)
is_ready = task_phase == IDLE and has_plot_result and not result_is_stale
```

输入文本修改、item 添加/删除/重排、视口（含 `aspect_request`）、图片尺寸、网格显示或任何影响结果的显示配置变化，都立即递增 `scene_revision`。递增操作不防抖；旧结果随即 stale。

`return_phase` 如确有需要，只放入当前截图/OCR 任务上下文，不作为持久结果状态。

## 10. 防抖边界

不得防抖：revision 更新、dirty/stale 判定、用户点击生成、复制可用性、错误定位。

可选的单次 QTimer 防抖仅用于实时语法提示、规范化预览、轻量输入分析和自动建议。初始候选为 250–300 ms，实际值由集中配置和用户测试确定，不在其他文档复制。正式生成只由用户明确提交触发。

快速连续生成由 request_id 失效、scene_revision 校验和 RenderActor latest-wins 处理。

剪贴板截图事件使用独立去抖策略；时间窗由 Windows 截图最小原型决定，不能复用公式输入的防抖常量。

## 11. OCR 模型边界

`OcrResult` 保存 raw text/LaTeX、provider request id、可选 confidence、必要且脱敏的供应商字段、warnings 和 error。

`InputAnalysisResult` 保存 normalized input、detected plot kind、安全显示表达式、warnings 和 error。

`FormulaReviewModel` 组合原图、`OcrResult` 和 `InputAnalysisResult`。供应商返回不直接成为 `PlotItemSpec`；用户核查后仍从 `PlotItemRequest` 进入同一受限解析管线。

## 12. 错误、日志、限制与类型

### 12.1 错误

`ErrorInfo` 至少包含稳定 error code、用户消息、脱敏技术消息、可选 item id/source span 和 recoverable。已发布错误码不得重新赋予不同含义。

### 12.2 日志

日志接口在写入前统一脱敏，不记录真实凭据、Authorization、完整截图、完整原始公式、完整本地路径或完整供应商响应。日志轮转并限制容量；日志失败不能阻塞绘图。

每个渲染结果/诊断记录各阶段 elapsed_ms、环境与版本信息。M0 只记录基准设备环境；M1 起记录可复现绘图基准。

### 12.3 类型政策

* 公开函数/方法标注参数和返回类型；
* dataclass 字段全部有类型；
* Models、Engine、Services 公共接口不使用无理由的 `Any`；
* 使用 `list[str]`、`tuple[T, ...]`、`T | None`、`Protocol`、`TypeAlias`、`Final`、`Literal` 和 Enum；
* 类型忽略必须局部且附原因，不允许整文件关闭；
* 只选择一个强制类型检查器，拟采用 Pyright：Models/Engine 严格，UI/PySide6 信号层先标准；
* Pyright 与 pytest 分开执行和报告，不同时强制 mypy。

Pyright 的安装与配置是后续开发阶段的显式批准项，本轮不安装。

## 13. 缓存与性能优化

M1、M1.5、M1.6 不以缓存为发布阻塞需求。M1.6 先建立 `item_fingerprint`、各阶段 `elapsed_ms`、可扩展命中字段和可复现基准。

只有基准证明解析或采样是明显瓶颈，才进入可选 M1.6.1：

1. 先复用上一张成功场景中未改变的已验证 `PlotItemSpec`；
2. 再评估采样结果复用；
3. 最后才考虑按字节容量限制的有界 LRU。

缓存键不能只有 normalized input 和 viewport；它必须覆盖 plot kind、parser contract version、engine version、resolved viewport、sampling policy、quality level 和 relevant limits version。自动视口变化使所有依赖该视口的采样缓存失效。

缓存数组只读或防御性复制，按字节数限制并有淘汰策略；不跨版本持久化，不缓存失败结果或敏感原始输入。禁止无界字典缓存。

## 14. 计划目录边界

2026-07-19 的实际仓库仍是早期演示骨架：根目录有 `main.py`、`main_window.py`、`plot_engine.py`、`pyproject.toml`、`.python-version`、`uv.lock` 和既有打包/构建输出目录，尚未形成 `math_drawing_assistant/` 包与 `tests/`。本轮只建立文档基线，不迁移或删除这些代码/产物。阶段 0 默认只盘点并记录保留、忽略、迁移或清理决定；实际移动、删除或改写遗留演示文件必须作为显式批准的独立子任务，并先在清单中扩展准确的允许文件。

下列结构是按阶段逐步形成的目标，不得在阶段 0 前批量创建空壳：

```text
math_drawing_assistant/
├─ bootstrap.py
├─ app_controller.py
├─ models/
│  ├─ errors.py
│  ├─ requests.py
│  ├─ results.py
│  ├─ plot_specs.py
│  ├─ render_plan.py
│  ├─ state.py
│  └─ viewport.py
├─ engine/
│  ├─ normalizer.py
│  ├─ tokenizer.py
│  ├─ source_map.py
│  ├─ equation_splitter.py
│  ├─ parser.py
│  ├─ plot_classifier.py
│  ├─ validators.py
│  ├─ render_plan_builder.py
│  ├─ samplers.py
│  └─ renderer.py
├─ workers/
│  ├─ render_actor.py
│  └─ recognition_worker.py
├─ services/
│  ├─ clipboard_service.py
│  ├─ credential_store.py
│  ├─ settings_service.py
│  ├─ simpletex_service.py
│  └─ screenshot_service.py
└─ ui/
```

测试目录同样按阶段形成，规范性测试职责如下；具体文件可随模块拆分调整，但必须与清单的阶段测试和允许文件一致：

```text
tests/
├─ test_models.py
├─ test_app_controller.py
├─ engine/
├─ workers/
├─ services/
└─ ui/
```

`samplers.py` 是分类型采样器的聚合模块或包入口，不是无类型的“万能 sampler”。若实现规模证明需要拆分，可以建立 `engine/samplers/explicit.py`、`line.py` 和 `conics.py`；文件布局变化须先同步本文，不能产生并行管线。

## 15. 依赖与质量门禁

`uv.lock` 必须纳入版本控制；`.python-version` 与 `pyproject.toml` 的 Python 约束应在阶段 0 固定为经验证组合。依赖变更同步更新锁文件。

Models/Engine 纯逻辑测试应可跨平台；Qt UI、QClipboard、Windows 截图、多显示器和打包以 Windows 验收为准。发布前在干净 Windows 测试机或虚拟机重建环境。

CI 是独立阶段，只在用户批准后创建。不要要求 Ubuntu 完成 Windows GUI 验收、Linux Docker 构建正式 Windows 安装包，或要求两次打包产物二进制哈希完全一致。
