# Stage 15 执行章程：入口收口、单项 M1.5 闭环与证据门

版本：`stage-15-execution-charter-v1`<br>
冻结日期：2026-08-15（Asia/Shanghai）<br>
冻结基线：`master @ 9b4dc91b322e04ea5764ea6836dcfc8c68308ec5`<br>
当前状态：15-0 文档与裁定门；15A 尚未开始，Stage 15 尚未开始实施

## 1. 章程职责、优先级与开始条件

本章程把 Stage 15 的跨层契约、P3 处置、PRD 需求域、人工验收目标、性能证据边界、15A–15G 顺序及逐子步精确文件清单冻结为可执行门禁。它不实现 renderer、executor、Actor、Controller、GUI、教材矩阵或正式性能，也不授予自动进入下一子步的权限。

规范优先级如下：

1. `数学绘图助手 PRD.md` 定义产品范围和可观察语义；
2. `docs/m1.5-math-input-scope.md` 定义已批准的 M1.5 首期数学与输入范围；
3. `docs/architecture.md` 定义数据模型、模块、线程、状态和资源所有权；
4. 本章程定义 Stage 15 的工程顺序、文件边界和证据门；
5. `docs/supported-formulas.md` 登记当前已实现行为和集中限制；
6. `联网确认.md` 登记 P0-07、外部证据和仍开放风险。

若 PRD 与本章程的冻结契约出现真正产品范围冲突，责任子步必须记录精确章节、停止写入并交总架构师做变更控制；不得自行修改 `数学绘图助手 PRD.md`。实现缺陷、测试缺口或文档状态过期不是产品范围冲突，按本章程退回责任子步处理。

每次 15A–15G 开始前都必须重新记录：分支、HEAD、`git status --short --branch`、本子步 PRD 域和精确写入 allowlist。若工作区存在用户修改，必须保留并报告；若修改与本子步写入文件重叠，必须停止并请求处理。

## 2. 15-0 当前写入边界

15-0 只允许写入以下 literal path：

- `docs/stage-15-execution-charter.md`
- `docs/audits/stage-15-0-p3-disposition.md`
- `docs/audits/stage-15-0-independent-review-notes.md`
- `docs/audits/stage-15-0-completion-report.md`
- `docs/audits/stage-14e-candidate-independent-audit-2026-08-15.md`
- `数学绘图助手_Codex协助开发步骤清单_v0.3.md`
- `docs/architecture.md`
- `docs/decisions.md`
- `docs/m1.5-math-input-scope.md`
- `docs/supported-formulas.md`
- `联网确认.md`

`数学绘图助手 PRD.md`、所有 `.py` 文件、所有测试、所有 benchmark 工具、既有 Stage 12/14 历史结果和审核记录、`README.md`、`main.py`、`main_window.py`、`plot_engine.py` 均为只读或禁止写入。唯一例外是第 33 行获项目所有者一次性授权新增的外部审核原文归档；它不是对任何既有 Stage 14 历史文件的改写。15-0 不运行正式性能，不生成教材证据，不关闭 P0-07，不创建 checkpoint，不更新核心 MVP 状态。

## 3. 总架构师冻结契约

以下八项不是子步可重新选择的方案：

1. `PlotKind` 继续只表达粗粒度路由：显函数、一般直线、圆锥曲线。不得为 UI 区分圆、椭圆、双曲线、抛物线而改变 `PlotKind` 语义。
2. 15B 在结果模型中增加一项与 `PlotKind` 正交、封闭的具体图形类型信息，使 UI 能区分直线、圆、椭圆、双曲线和抛物线。具体类型名和字段名由 15B 在其公开契约审核中确定；15-0 不提前命名。
3. 15B 补齐 `PlotItemResult` 当前架构已要求的可见片段元数据、必要采样规模和资源诊断。不得加入 Stage 18/19 的 `cache_hit`、`fingerprint` 或同义字段。
4. 15D 将 `ViewportPanel` 的“按图形默认”映射为 `AspectRequest.DEFAULT` 并设为默认选中；“自动”映射 `AUTO`，“等比例”映射 `EQUAL`。显函数和一般直线的 DEFAULT 解析为 AUTO；圆、椭圆、双曲线、抛物线的 DEFAULT 解析为 EQUAL；用户显式 AUTO/EQUAL 始终优先。
5. `viewport_clipped` 与 `sampling_precision_limited` 是成功结果上的非阻塞通知。UI 必须以持续、可访问的中文提示显示；不得显示成失败，不得禁用复制。当前视口完全不可见才是失败。
6. 正式峰值内存必须使用进程级/操作系统级主口径，覆盖 NumPy、Matplotlib、Qt 等原生分配。`tracemalloc` 只能作为可选辅助诊断字段，不能单独充当正式峰值。
7. 不得把整个 `ApplicationLimits.status` 改为 `BENCHMARK_FROZEN`。输入安全限制没有获得 M1.5 性能证明；只能冻结有正式证据的场景或资源子集。若当前全局两态无法表达，15F 必须先设计并审核状态粒度，再冻结协议和测量。
8. 15E 必须先于 15F。正式性能场景必须来自已稳定、通过 production executor 且有来源证据的产品矩阵；未来 `docs/benchmarks/m1.5-performance-v1.md` 必须引用本条理由。仅为 15E→15F 顺序不得创建决策编号；只有长期产品或架构变化才进入 `docs/decisions.md`。

## 4. 当前实现基线与唯一目标链路

当前 HEAD 有两条职责不同的单项链：

```text
现有 M1 production：
PlotSceneRequest
→ SceneRenderExecutor.execute
→ analyze_explicit_function
→ build_explicit_scene_spec
→ resolve_single_explicit_viewport
→ RenderPlanBuilder.build
→ sample_explicit_function
→ render_explicit_png
→ PlotSceneResult

Stage 14 M1.5 原型：
PlotItemRequest
→ analyze_plot_item
→ PlotSceneSpec
→ resolve_single_item_viewport
→ RenderPlanBuilder.build
→ sample_parameterized_curve
```

15A–15B 收口后的唯一 production 目标链为：

```text
PlotSceneRequest
→ analyze_plot_item
→ PlotSceneSpec
→ resolve_single_item_viewport
→ RenderPlanBuilder.build
→ exact typed dispatch to the existing typed sampler
→ unified renderer
→ PlotSceneResult
```

按 exact Spec/typed union 做封闭分发是允许的；第二套 resolver、Builder、sampler、executor、receipt 或根目录旁路是禁止的。兼容 wrapper 可以保留原公开签名，但必须委托唯一实现，不能维持第二条行为链。

## 5. PRD 需求追踪矩阵

| PRD 域 | 冻结要求 | Stage 15 子步 | 验收证据 | 文档来源 |
|---|---|---|---|---|
| §4.2 | 单条实数非退化一般直线、圆、椭圆、双曲线、抛物线；标准式、平移式、左右式、精确有理数；拒绝旋转、退化、无实点、高次、变量分母、未知参数 | 15B、15E、15G | `tests/engine/test_stage15b_unified_executor.py`；`tests/data/m1_5_textbook_matrix_v1.json`；`tests/acceptance/test_stage15e_m1_5_textbook_matrix.py`；`tests/acceptance/test_stage15g_m1_5_final_acceptance.py` | `数学绘图助手 PRD.md` §4.2；`docs/m1.5-math-input-scope.md` |
| §6.2、§6.4 | 共享视口、手动优先、按图形默认比例、圆不变形、分支/闭合/裁切、不可见失败、部分裁切与精度非阻塞警告、资源释放 | 15A、15B、15D、15G | `tests/engine/test_stage15a_geometry_renderer.py`；`tests/engine/test_stage15b_unified_executor.py`；`tests/ui/test_stage15d_m1_5_scene_flow.py`；`docs/manual-test-checklist-m1.5.md` | `数学绘图助手 PRD.md` §6.2、§6.4；`docs/architecture.md` §7 |
| §7.2 | M1.5 提交到成功预览的 P95 目标；完整 Engine/Matplotlib 不在 GUI 主线程；唯一 Actor；资源硬上限；先冻结协议再测量 | 15C、15E、15F、15G | `tests/test_stage15c_production_chain.py`；`docs/benchmarks/m1.5-performance-v1.md`；`benchmarks/results/m1.5-performance-v1-primary/summary.json`；`docs/benchmarks/m1.5-performance-v1-results.md` | `数学绘图助手 PRD.md` §7.2；`docs/performance-environment.md` |
| §10.4、§10.5、§10.5.1 | 统一 typed route、共同安全验证、分类后/视口后计划与预算、item 归属、默认比例、禁止旁路 | 15B、15E、15F | `tests/engine/test_stage15b_unified_executor.py`；`tests/engine/test_stage15b_receipt_hardening.py`；`tests/acceptance/test_stage15e_m1_5_textbook_matrix.py`；`tests/test_limits.py` | `数学绘图助手 PRD.md` §10.4、§10.5、§10.5.1；`docs/architecture.md` §7 |
| §12.1–§12.3 | request/viewport/Scene/item/result 语义；具体图形类型、可见片段、稳定 item_id；成功/失败原子性和旧图保护 | 15B、15C、15D、15G | `tests/test_models.py`；`tests/test_diagnostics.py`；`tests/test_stage15c_production_chain.py`；`tests/ui/test_stage15d_m1_5_scene_flow.py` | `数学绘图助手 PRD.md` §12.1–§12.3；`docs/architecture.md` §5、§9、§11 |
| §14 | request_id 与 scene_revision 双门禁；latest-wins；取消/过期失效；旧结果不覆盖新结果 | 15C、15D、15G | `tests/workers/test_render_actor.py`；`tests/workers/test_render_actor_shutdown.py`；`tests/test_stage15c_production_chain.py`；`tests/ui/test_stage15d_m1_5_scene_flow.py` | `数学绘图助手 PRD.md` §14；`docs/architecture.md` §8、§9 |
| §15 | 每次复制意图只复制当前成功图片；处理中、stale、失败后仍可复制上一成功图；不重复触发 | 15D、15G | `tests/services/test_clipboard_service.py`；`tests/ui/test_stage15d_m1_5_scene_flow.py`；`docs/manual-test-checklist-m1.5.md` | `数学绘图助手 PRD.md` §15；`docs/architecture.md` §10、§11 |
| §20.1 | M1 正向/反向回归、四条正式直线、圆/圆锥曲线完整矩阵、Unicode/分数/左右交换/整体倍数、资源和 PNG | 15A、15B、15E、15G | `tests/engine/test_stage15a_geometry_renderer.py`；`tests/engine/test_stage15b_unified_executor.py`；`tests/acceptance/test_stage15e_m1_5_textbook_matrix.py`；`tests/acceptance/test_stage15g_m1_5_final_acceptance.py` | `数学绘图助手 PRD.md` §20.1；`docs/supported-formulas.md` |
| §20.4 | 宽/窄窗口、不同 DPI、圆不变形、状态、复制、错误恢复、快速提交、后台关闭、可访问性 | 15D、15G | `docs/manual-test-checklist-m1.5.md`；`docs/audits/stage-15g-completion-report.md` | `数学绘图助手 PRD.md` §20.4；本章程 §9 |
| §21 | M1.5 完整功能/性能/回归出口；P0-07；M1 不回归；随后才允许 M1.6 入口资源基线和 checkpoint | 15E、15F、15G | `docs/audits/stage-15e-completion-report.md`；`docs/benchmarks/m1.5-performance-v1-results.md`；`docs/audits/stage-15-final-acceptance.md` | `数学绘图助手 PRD.md` §21；`数学绘图助手_Codex协助开发步骤清单_v0.3.md` |
| §23 | P0-07 真实教材证据、来源/日期/隐私、外部证据边界、正式决策只用于长期变化 | 15E、15F、15G | `docs/evidence/m1.5-textbook-source-ledger-v1.md`；`联网确认.md`；`docs/audits/stage-15-final-acceptance.md` | `数学绘图助手 PRD.md` §23；`联网确认.md`；`docs/decisions.md` |

## 6. 候选文件调查与职责分配

以下分配来自当前 CodeGraph 调用链和 HEAD 源码。`写入子步` 以外均为只读；没有列出目录、通配符或“保险”文件。

### 6.1 生产与公共契约候选

| literal path | 当前职责 | 写入子步 | 明确边界 |
|---|---|---|---|
| `math_drawing_assistant/engine/renderer.py` | 当前只接受 `SampledExplicitFunction` 的 Agg/PNG renderer | 15A | 15B–15G 只读；15A 后不得再建 geometry renderer |
| `math_drawing_assistant/engine/scene_executor.py` | 当前 M1 显函数专用 production executor | 15B | 15A 只读；15C 以后作为唯一 executor 只读验证 |
| `math_drawing_assistant/engine/__init__.py` | Engine 公开导出 | 15A、15B | 只随 renderer 或 executor/result 公共契约同步；不得导出分类型旁路 |
| `math_drawing_assistant/models/results.py` | `PlotItemResult`、`PlotSceneResult` | 15B | 具体图形类型字段名只在 15B 设计；15C–15G 不改公共结果契约 |
| `math_drawing_assistant/models/diagnostics.py` | 当前仅有通用阶段计时 | 15B | 只容纳结果所需诊断值对象；不放 benchmark-only `cache_hit`/`fingerprint` |
| `math_drawing_assistant/models/__init__.py` | Models 公开导出 | 15B | 与结果/诊断封闭联合同步 |
| `math_drawing_assistant/app_controller.py` | request/revision、旧成功结果、copy candidate、shutdown 状态 | 15C、15D | 15C 证明真实链，15D 只接用户可见警告/显示闭环 |
| `math_drawing_assistant/workers/render_actor.py` | 唯一常驻串行 Actor、latest-wins、同一 token、关闭门 | 15C | 不复制 executor、渲染或并发逻辑 |
| `math_drawing_assistant/bootstrap.py` | `SceneRenderExecutor`、Actor、Controller、MainWindow 正式组合 | 15C | 只允许唯一 production composition |
| `math_drawing_assistant/ui/main_window.py` | UI 快照/revision 适配、结果映射、复制意图 | 15D | 不做数学分类、采样或渲染 |
| `math_drawing_assistant/ui/widgets/viewport_panel.py` | 当前仅有 auto/equal 字符串二态 | 15D | 增加 DEFAULT 三态并映射 exact enum；不得计算图形默认值 |
| `math_drawing_assistant/ui/widgets/status_panel.py` | 用户状态文字和可访问 level | 15D | 承载持续中文非阻塞通知，不把 warning 变成失败 |
| `math_drawing_assistant/ui/widgets/plot_preview.py` | PNG ownership、显示和 stale 标识 | 15D | 失败/取消/过期不得替换旧成功图 |
| `math_drawing_assistant/config/limits.py` | 当前单一 `ApplicationLimits.status` 两态 | 15F | 先解决状态粒度；不得全局冻结输入安全 limits |
| `math_drawing_assistant/config/__init__.py` | Limits 公开导出 | 15F | 仅同步已审核的状态粒度公共契约 |

以下真实生产文件在 Stage 15 保持只读：

- `math_drawing_assistant/models/state.py`：保护 `PlotKind` 粗粒度语义和现有 `AspectRequest`；
- `math_drawing_assistant/models/render_plan.py`：Stage 14 typed plan/receipt 已稳定，P3-3/4/5 先补测试，不预授权生产重写；
- `math_drawing_assistant/engine/plot_analyzer.py`：`analyze_plot_item` 作为唯一统一分析入口；
- `math_drawing_assistant/engine/viewport_resolver.py`：`resolve_single_item_viewport` 作为唯一单项 resolver；
- `math_drawing_assistant/engine/render_plan_builder.py`：现有 `RenderPlanBuilder` 作为唯一 Builder；
- `math_drawing_assistant/engine/samplers.py`：现有 explicit/parameterized typed samplers；
- `math_drawing_assistant/services/clipboard_service.py`：现有单次写入与 ownership 边界；
- `main.py`、`main_window.py`、`plot_engine.py`：根目录 V0.1 旁路永久不得接回 production。

若只读文件中的真实生产缺陷使某子步无法退出，必须停止并返回总架构师调整责任子步 allowlist；不得由当前子步自行扩权。

### 6.2 现有行为/API 测试候选

| literal path | 写入子步 | 其他子步用途 |
|---|---|---|
| `tests/engine/test_renderer.py` | 15A | 后续只读回归 |
| `tests/engine/test_scene_executor.py` | 15B | 15C–15G 只读回归 |
| `tests/test_models.py` | 15B | 15C–15G 只读回归 |
| `tests/test_diagnostics.py` | 15B | 15D、15F、15G 只读回归 |
| `tests/test_limits.py` | 15F | 15A–15E 只读哨兵，15G 只读回归 |
| `tests/test_stage13_public_api.py` | 15A、15B、15F | 15C、15D、15E、15G 只读公开 API 哨兵 |
| `tests/test_app_controller.py` | 15C、15D | 15G 只读回归 |
| `tests/test_bootstrap.py` | 15C | 15D–15G 只读组合哨兵 |
| `tests/workers/test_render_actor.py` | 15C | 15D–15G 只读回归 |
| `tests/workers/test_render_actor_agg_probe.py` | 15C | 15A、15B 只读边界证据，15D–15G 只读回归 |
| `tests/workers/test_render_actor_shutdown.py` | 15C | 15D–15G 只读生命周期回归 |
| `tests/ui/test_main_window.py` | 15D | 15G 只读回归 |
| `tests/ui/test_m1_scene_flow.py` | 15D | 15C 只读 M1 基线，15G 只读回归 |
| `tests/ui/test_plot_preview.py` | 15D | 15G 只读回归 |

`tests/engine/test_render_plan.py`、`tests/engine/test_stage14c_circle_ellipse.py`、`tests/engine/test_stage14d1_hyperbola.py`、`tests/engine/test_stage14d2_parabola.py`、`tests/engine/test_stage14e_acceptance.py` 和 `tests/benchmarks/test_stage14_parameterized_probe.py` 均保持只读历史回归。P3 加固写入新的 Stage 15 测试文件，不改写 Stage 14 证据。

## 7. 全阶段顺序与贯穿门禁

唯一顺序是：

```text
15-0 → 15A → 15B → 15C → 15D → 15E → 15F → 15G
```

不得合并、跳过或自动进入下一步。每一步必须：

1. 记录开始基线、PRD 域、精确 allowlist 和工作区状态；
2. 同步完成本步实现、行为测试、公开 API 哨兵和受影响文档；
3. 运行本步定向命令；
4. 运行全量回归：`$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='.'; uv run --locked pytest -q -p no:cacheprovider`；
5. 运行 `git diff --check` 和 `git status --short --branch`；
6. 接受真正独立的只读审核并写入本步 review notes；
7. 单独写入本步 completion report；
8. 停止，等待总架构师验收，不自动进入下一步。

任一生产代码、公共契约、协议、工具、场景集合或结果判定变化，都必须重跑受影响的定向测试和全量回归。15F 正式结果形成后，影响被测 production executor、renderer、Actor/Controller/UI 成功判定、协议工具或 15E 场景集合的变化会使相应结果失效；必须回到责任子步、重新冻结 hash，再经批准复测。

持续禁止：多输入 UI、多项样式与叠加、cache/fingerprint、OCR、contour 正式后备、课堂设备性能宣称、教学标注、根目录 V0.1 旁路、新依赖、Pyright、CI，以及未经批准的公共契约或产品范围变化。

## 8. 性能证据边界与固定结果文件

Stage 14 的 analyzer/resolver/Builder/sampler 直接探针不是正式端到端性能。Stage 12 `m1-performance-v1` 只可继承有证据支持且仍可比的部分；任何修改必须在 `docs/benchmarks/m1.5-performance-v1.md` 说明理由和可比性。

15F 第一门先冻结协议、工具、15E 场景、预热、样本量、P95 算法、计时边界、GUI 成功判定、失败样本规则、环境、hash、采样规模和进程级原生峰值内存口径；第二门才运行正式测量。正式主内存指标必须来自操作系统可观察的目标进程峰值，覆盖 Python 与 NumPy、Matplotlib、Qt 原生分配；`tracemalloc` 仅可作为辅助值。

固定主证据容器是 `benchmarks/results/m1.5-performance-v1-primary/`，只允许生成以下 literal file：

- `benchmarks/results/m1.5-performance-v1-primary/environment.json`
- `benchmarks/results/m1.5-performance-v1-primary/manifest.json`
- `benchmarks/results/m1.5-performance-v1-primary/records.jsonl`
- `benchmarks/results/m1.5-performance-v1-primary/summary.json`
- `benchmarks/results/m1.5-performance-v1-primary/protocol.sha256`
- `benchmarks/results/m1.5-performance-v1-primary/tools.sha256`
- `benchmarks/results/m1.5-performance-v1-primary/scenario-matrix.sha256`
- `benchmarks/results/m1.5-performance-v1-primary/stdout.txt`
- `benchmarks/results/m1.5-performance-v1-primary/stderr.txt`

不允许时间戳目录、通配符、任意写入 `benchmarks/results/` 或预授权 rerun 目录。正式结果失效后不得覆盖或另建目录绕过变更控制；必须由总架构师批准新的固定版本/路径后再测。

开发机结果只能标为开发参考，不能外推课堂设备。单项实测不能冒充多项实测；M1.6 入口只能区分登记：单项实测、基于单项的多项聚合外推、阶段 17/18 尚待真实验证。`ApplicationLimits` 输入安全状态不得因局部 M1.5 性能证据全局冻结。

## 9. 人工验收目标

15D 创建 `docs/manual-test-checklist-m1.5.md` 并先登记目标和“未执行”；15G 才登记项目所有者或获授权人工执行者的真实观察。自动化或主执行者不得伪造人工结果。

必须逐项保留：

- 宽窗口与窄窗口；
- 100%、125%、150%、175%、200% DPI；当前环境不能执行的档位保持“未完成”；
- 圆在按图形默认比例下不变形；
- “按图形默认/自动/等比例”三态和手动视口优先；
- `viewport_clipped`、`sampling_precision_limited` 的持续、可访问中文提示；
- 上述警告不使任务失败、不禁用复制；
- 当前视口完全不可见时失败；
- 错误不清空输入；
- 失败、取消、过期不替换上一张成功预览；
- 处理中或 stale 时重复复制始终复制当前成功图片；
- 宽窄窗口中核心操作保持可达。

人工结果必须注明执行者、日期、Windows 版本、窗口尺寸、DPI、显示器条件和无法执行项；不得把开发机观察外推为课堂设备、触控、多显示器或 Microsoft Office 兼容结论。

## 10. 15A：统一 Geometry Renderer

### 10.1 任务和边界

PRD 域：§6.2、§6.4、§10.8、§20.1。只在现有 renderer 边界扩展 typed sampled curve → Agg/PNG；不接 Actor、不改 GUI、不创建第二入口。receipt 与 sampled provenance 必须在创建 Figure、Canvas、Axes、BytesIO 前验证；复用取消、PNG 上限、PNG signature/IHDR 尺寸校验、异常映射和 `finally` 释放。每个 segment 独立绘制；双曲线分支和抛物线分段不误连；CLOSED 圆/椭圆由 renderer 明确视觉闭合；legend 使用 provenance。不得宣称 Actor 已是唯一 Matplotlib 进入者。

### 10.2 精确写入 allowlist

- `math_drawing_assistant/engine/renderer.py`
- `math_drawing_assistant/engine/__init__.py`
- `tests/engine/test_renderer.py`
- `tests/engine/test_stage15a_geometry_renderer.py`
- `tests/engine/test_stage15a_production_boundary.py`
- `tests/test_stage13_public_api.py`
- `docs/architecture.md`
- `docs/supported-formulas.md`
- `数学绘图助手_Codex协助开发步骤清单_v0.3.md`
- `docs/audits/stage-15a-independent-review-notes.md`
- `docs/audits/stage-15a-completion-report.md`

### 10.3 只读依赖

- `math_drawing_assistant/models/render_plan.py`
- `math_drawing_assistant/engine/samplers.py`
- `math_drawing_assistant/config/limits.py`
- `tests/engine/test_stage14b2_line.py`
- `tests/engine/test_stage14c_circle_ellipse.py`
- `tests/engine/test_stage14d1_hyperbola.py`
- `tests/engine/test_stage14d2_parabola.py`
- `tests/engine/test_stage14e_acceptance.py`
- `tests/workers/test_render_actor_agg_probe.py`
- `docs/stage-15-execution-charter.md`
- `数学绘图助手 PRD.md`

### 10.4 验证、审核与退出

定向命令：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='.'; uv run --locked pytest -q -p no:cacheprovider tests/engine/test_renderer.py tests/engine/test_stage15a_geometry_renderer.py tests/engine/test_stage15a_production_boundary.py tests/engine/test_stage14e_acceptance.py tests/test_stage13_public_api.py
```

公开 API 哨兵是 `tests/test_stage13_public_api.py`；不得导出分类型 renderer。随后运行 §7 的全量 pytest、`git diff --check` 和 status。独立审核写入 `docs/audits/stage-15a-independent-review-notes.md`，completion 写入 `docs/audits/stage-15a-completion-report.md`。

退出条件：六种当前 exact 类型的 sampled output 均通过统一 renderer；segment/closure/legend/取消/资源/PNG/释放矩阵通过；P3-1 AST 全包边界测试通过；无 Actor/GUI 接线。失败时只在本 allowlist 修复；若需要改 sampler/plan/limits，15A 失败并退回总架构师。完成后停止。

## 11. 15B：统一 SceneRenderExecutor 与结果契约

### 11.1 任务和边界

PRD 域：§4.2、§6.4、§10.4、§10.5、§10.5.1、§12.1–§12.3、§20.1。统一链路为 `analyze_plot_item → PlotSceneSpec → resolver → RenderPlanBuilder → typed sampler → unified renderer`。允许 exact Spec/typed union 封闭分发；禁止第二套 resolver、Builder、sampler、executor 或 receipt。统一 M1 显函数与 M1.5 方程，结果包含具体图形类型、规范化方程、可见片段、警告、采样规模和必要资源诊断。`y+1=x+2` 在旧 M1 专用入口继续拒绝，在统一入口成功为直线；保持 item 归属和旧 M1 错误语义。结果公共名称只在本步设计审核中确定，不使用 `cache_hit`/`fingerprint`。

### 11.2 精确写入 allowlist

- `math_drawing_assistant/engine/scene_executor.py`
- `math_drawing_assistant/engine/__init__.py`
- `math_drawing_assistant/models/results.py`
- `math_drawing_assistant/models/diagnostics.py`
- `math_drawing_assistant/models/__init__.py`
- `tests/engine/test_scene_executor.py`
- `tests/engine/test_stage15b_unified_executor.py`
- `tests/engine/test_stage15b_receipt_hardening.py`
- `tests/engine/test_stage15b_sampler_identity.py`
- `tests/test_models.py`
- `tests/test_diagnostics.py`
- `tests/test_stage13_public_api.py`
- `docs/architecture.md`
- `docs/supported-formulas.md`
- `数学绘图助手_Codex协助开发步骤清单_v0.3.md`
- `docs/audits/stage-15b-independent-review-notes.md`
- `docs/audits/stage-15b-completion-report.md`

### 11.3 只读依赖

- `math_drawing_assistant/models/state.py`
- `math_drawing_assistant/models/render_plan.py`
- `math_drawing_assistant/engine/plot_analyzer.py`
- `math_drawing_assistant/engine/viewport_resolver.py`
- `math_drawing_assistant/engine/render_plan_builder.py`
- `math_drawing_assistant/engine/samplers.py`
- `math_drawing_assistant/engine/renderer.py`
- `tests/engine/test_render_plan.py`
- `tests/engine/test_stage14c_circle_ellipse.py`
- `tests/engine/test_stage14d1_hyperbola.py`
- `tests/engine/test_stage14d2_parabola.py`
- `tests/engine/test_stage14e_acceptance.py`
- `docs/audits/stage-15a-completion-report.md`
- `docs/stage-15-execution-charter.md`
- `数学绘图助手 PRD.md`

### 11.4 验证、审核与退出

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='.'; uv run --locked pytest -q -p no:cacheprovider tests/engine/test_scene_executor.py tests/engine/test_stage15b_unified_executor.py tests/engine/test_stage15b_receipt_hardening.py tests/engine/test_stage15b_sampler_identity.py tests/engine/test_render_plan.py tests/test_models.py tests/test_diagnostics.py tests/test_stage13_public_api.py
```

`tests/test_stage13_public_api.py` 必须钉住封闭导出、`PlotKind` 不变和结果模型公共契约。随后运行 §7 全量门禁。独立审核写入 `docs/audits/stage-15b-independent-review-notes.md`；completion 写入 `docs/audits/stage-15b-completion-report.md`。

退出条件：M1 与 M1.5 单项均经唯一 executor；成功、typed failure、不可见、警告和取消的 item/scene 归属正确；P3-3/4/5 完整 receipt tamper 回归通过；P3-6 typed sampler identity 回归通过；无第二入口。若只读 plan/Builder/sampler 存在真实缺陷，停止并由总架构师决定退回 Stage 14 契约修复还是扩展 15B；不得自行改写。完成后停止。

## 12. 15C：RenderActor / AppController 真实链路证明

### 12.1 任务和边界

PRD 域：§7.2、§12.3、§14、§20.3。证明正式组合，不重复实现并发或渲染：唯一 production executor、唯一 Actor、latest-wins、同一 cancellation token、request/revision 双门禁；区分成功、当前失败和过期结果；失败、取消、过期不覆盖旧成功图。每请求仅一个 Matplotlib 进入者，Figure 全部在 Actor 线程创建；覆盖关闭、超时、资源释放和后续恢复；根目录旧入口不接回生产。

### 12.2 精确写入 allowlist

- `math_drawing_assistant/app_controller.py`
- `math_drawing_assistant/workers/render_actor.py`
- `math_drawing_assistant/bootstrap.py`
- `tests/test_app_controller.py`
- `tests/test_bootstrap.py`
- `tests/workers/test_render_actor.py`
- `tests/workers/test_render_actor_agg_probe.py`
- `tests/workers/test_render_actor_shutdown.py`
- `tests/test_stage15c_production_chain.py`
- `docs/architecture.md`
- `数学绘图助手_Codex协助开发步骤清单_v0.3.md`
- `docs/audits/stage-15c-independent-review-notes.md`
- `docs/audits/stage-15c-completion-report.md`

### 12.3 只读依赖

- `math_drawing_assistant/engine/scene_executor.py`
- `math_drawing_assistant/engine/renderer.py`
- `math_drawing_assistant/models/results.py`
- `math_drawing_assistant/workers/cancellation.py`
- `math_drawing_assistant/ui/main_window.py`
- `tests/engine/test_scene_executor.py`
- `tests/ui/test_m1_scene_flow.py`
- `tests/test_stage13_public_api.py`
- `docs/audits/stage-15b-completion-report.md`
- `docs/stage-15-execution-charter.md`
- `数学绘图助手 PRD.md`

### 12.4 验证、审核与退出

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='.'; uv run --locked pytest -q -p no:cacheprovider tests/test_app_controller.py tests/test_bootstrap.py tests/workers/test_render_actor.py tests/workers/test_render_actor_agg_probe.py tests/workers/test_render_actor_shutdown.py tests/test_stage15c_production_chain.py tests/ui/test_m1_scene_flow.py tests/test_stage13_public_api.py
```

公开 API 哨兵 `tests/test_stage13_public_api.py` 本步只读。随后运行 §7 全量门禁。独立审核写入 `docs/audits/stage-15c-independent-review-notes.md`；completion 写入 `docs/audits/stage-15c-completion-report.md`。

退出条件：真实 bootstrap 组合只有一个 executor/Actor；Actor 线程 Figure 探针、latest-wins、同 token、双门禁、旧图保护、超时关闭与恢复全部通过；P3-6 在真实取消链复验。若需要修改 SceneRenderExecutor/renderer/result contract，退回 15A 或 15B；不得在 15C 旁路。完成后停止。

## 13. 15D：GUI、预览、警告与复制闭环

### 13.1 任务和边界

PRD 域：§6.2、§6.4、§12.1–§12.3、§14、§15、§20.4。接入具体类型、规范化方程、持续非阻塞警告、不可见失败和旧图保护；覆盖 stale、处理中、按钮、重复复制；完成 DEFAULT/AUTO/EQUAL 三态和手动视口优先；任何影响结果的显示配置变化立即增加 revision。UI 不做数学分类、viewport 计算、采样或 Matplotlib。

### 13.2 精确写入 allowlist

- `math_drawing_assistant/app_controller.py`
- `math_drawing_assistant/ui/main_window.py`
- `math_drawing_assistant/ui/widgets/viewport_panel.py`
- `math_drawing_assistant/ui/widgets/status_panel.py`
- `math_drawing_assistant/ui/widgets/plot_preview.py`
- `tests/test_app_controller.py`
- `tests/ui/test_main_window.py`
- `tests/ui/test_m1_scene_flow.py`
- `tests/ui/test_plot_preview.py`
- `tests/ui/test_stage15d_m1_5_scene_flow.py`
- `docs/manual-test-checklist-m1.5.md`
- `docs/architecture.md`
- `docs/supported-formulas.md`
- `数学绘图助手_Codex协助开发步骤清单_v0.3.md`
- `docs/audits/stage-15d-independent-review-notes.md`
- `docs/audits/stage-15d-completion-report.md`

### 13.3 只读依赖

- `math_drawing_assistant/models/state.py`
- `math_drawing_assistant/models/results.py`
- `math_drawing_assistant/engine/scene_executor.py`
- `math_drawing_assistant/workers/render_actor.py`
- `math_drawing_assistant/bootstrap.py`
- `math_drawing_assistant/services/clipboard_service.py`
- `tests/services/test_clipboard_service.py`
- `tests/test_bootstrap.py`
- `tests/workers/test_render_actor.py`
- `tests/test_stage13_public_api.py`
- `docs/audits/stage-15c-completion-report.md`
- `docs/stage-15-execution-charter.md`
- `数学绘图助手 PRD.md`

### 13.4 验证、审核与退出

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='.'; uv run --locked pytest -q -p no:cacheprovider tests/test_app_controller.py tests/ui/test_main_window.py tests/ui/test_m1_scene_flow.py tests/ui/test_plot_preview.py tests/ui/test_stage15d_m1_5_scene_flow.py tests/services/test_clipboard_service.py tests/test_bootstrap.py tests/workers/test_render_actor.py tests/test_stage13_public_api.py
```

公开 API 哨兵本步只读；随后运行 §7 全量门禁。人工目标先写入 `docs/manual-test-checklist-m1.5.md`，不得填造结果。独立审核写入 `docs/audits/stage-15d-independent-review-notes.md`；completion 写入 `docs/audits/stage-15d-completion-report.md`。

退出条件：自动化证明三态比例、手动优先、revision、持续中文 warning、不可见失败、输入保留、旧图保护和重复复制；人工清单已建立且未执行项明确。若结果 contract 不足，退回 15B；若 Actor/Controller 门禁不足，退回 15C。完成后停止。

## 14. 15E：产品级教材与正反向矩阵

### 14.1 任务和边界

PRD 域：§4.2、§6.4、§20.1、§21、§23。15E 必须先于 15F。矩阵覆盖多套教材共同核心真实表达式、标准式、平移式、Unicode、分数、左右交换、整体倍数、四条正式直线和全部反向输入；每个真实样例必须经过 production executor。证据记录来源、教材版本快照、核实日期和无个人信息声明。禁止静默删样例。P3-2 的异构 oracle 在本步关闭。

### 14.2 精确写入 allowlist

- `tests/data/m1_5_textbook_matrix_v1.json`
- `tests/acceptance/test_stage15e_m1_5_textbook_matrix.py`
- `tests/acceptance/test_stage15e_independent_geometry_oracle.py`
- `docs/evidence/m1.5-textbook-source-ledger-v1.md`
- `docs/architecture.md`
- `docs/m1.5-math-input-scope.md`
- `docs/supported-formulas.md`
- `数学绘图助手_Codex协助开发步骤清单_v0.3.md`
- `docs/audits/stage-15e-independent-review-notes.md`
- `docs/audits/stage-15e-completion-report.md`

### 14.3 只读依赖

- `math_drawing_assistant/engine/scene_executor.py`
- `math_drawing_assistant/engine/renderer.py`
- `math_drawing_assistant/models/results.py`
- `math_drawing_assistant/app_controller.py`
- `math_drawing_assistant/workers/render_actor.py`
- `math_drawing_assistant/bootstrap.py`
- `tests/engine/test_plot_analyzer.py`
- `tests/engine/test_scene_executor.py`
- `tests/engine/test_stage14e_acceptance.py`
- `tests/ui/test_stage15d_m1_5_scene_flow.py`
- `tests/test_stage13_public_api.py`
- `docs/audits/stage-15d-completion-report.md`
- `docs/decisions.md`
- `联网确认.md`
- `docs/stage-15-execution-charter.md`
- `数学绘图助手 PRD.md`

### 14.4 验证、审核与退出

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='.'; uv run --locked pytest -q -p no:cacheprovider tests/acceptance/test_stage15e_m1_5_textbook_matrix.py tests/acceptance/test_stage15e_independent_geometry_oracle.py tests/engine/test_plot_analyzer.py tests/engine/test_scene_executor.py tests/engine/test_stage14e_acceptance.py tests/ui/test_stage15d_m1_5_scene_flow.py tests/test_stage13_public_api.py
```

随后运行 §7 全量门禁。独立审核写入 `docs/audits/stage-15e-independent-review-notes.md`；completion 写入 `docs/audits/stage-15e-completion-report.md`。

退出条件：来源 ledger 和 machine-readable matrix 完整；全部正反向样例经 production executor；P3-2 异构 oracle 通过；无个人信息；15E 只形成供后续综合验收使用的教材候选证据，`联网确认.md` 中的 P0-07 必须保持打开。P0-07 只能由 15G 在自动、人工、性能、教材和外部证据全部通过后正式关闭。若样例暴露生产缺陷，15E 保持失败并退回 15A–15D 的责任子步；若出现产品范围冲突，记录并暂停变更控制；不得静默删样例或在 15E 越权改生产。完成后停止，15F 不自动开始。

## 15. 15F：协议冻结、正式性能与 M1.6 入口资源基线

### 15.1 任务和边界

PRD 域：§7.2、§10.5.1、§21、§23。先解决 `ApplicationLimits` 状态粒度，再冻结 `m1.5-performance-v1` 协议和工具；协议必须引用本章程 §3 第 8 项与 §8，说明场景来自已通过的 15E 产品矩阵。协议冻结后才测量。记录 P50/P95、进程级原生峰值和采样规模；`tracemalloc` 仅辅助；结果只作开发参考。之后冻结 M1.6 项目数与总资源入口，并区分单项实测、多项聚合外推、阶段 17/18 多项实测。

### 15.2 精确写入 allowlist

- `math_drawing_assistant/config/limits.py`
- `math_drawing_assistant/config/__init__.py`
- `benchmarks/m1_5_performance_v1.py`
- `tests/benchmarks/test_m1_5_performance_v1.py`
- `tests/test_limits.py`
- `tests/test_stage13_public_api.py`
- `docs/benchmarks/m1.5-performance-v1.md`
- `docs/benchmarks/m1.5-performance-v1-results.md`
- `benchmarks/results/m1.5-performance-v1-primary/environment.json`
- `benchmarks/results/m1.5-performance-v1-primary/manifest.json`
- `benchmarks/results/m1.5-performance-v1-primary/records.jsonl`
- `benchmarks/results/m1.5-performance-v1-primary/summary.json`
- `benchmarks/results/m1.5-performance-v1-primary/protocol.sha256`
- `benchmarks/results/m1.5-performance-v1-primary/tools.sha256`
- `benchmarks/results/m1.5-performance-v1-primary/scenario-matrix.sha256`
- `benchmarks/results/m1.5-performance-v1-primary/stdout.txt`
- `benchmarks/results/m1.5-performance-v1-primary/stderr.txt`
- `docs/architecture.md`
- `docs/decisions.md`
- `docs/supported-formulas.md`
- `数学绘图助手_Codex协助开发步骤清单_v0.3.md`
- `docs/audits/stage-15f-independent-review-notes.md`
- `docs/audits/stage-15f-completion-report.md`

### 15.3 只读依赖

- `tests/data/m1_5_textbook_matrix_v1.json`
- `docs/evidence/m1.5-textbook-source-ledger-v1.md`
- `docs/audits/stage-15e-completion-report.md`
- `math_drawing_assistant/engine/scene_executor.py`
- `math_drawing_assistant/engine/renderer.py`
- `math_drawing_assistant/app_controller.py`
- `math_drawing_assistant/workers/render_actor.py`
- `math_drawing_assistant/bootstrap.py`
- `math_drawing_assistant/ui/main_window.py`
- `benchmarks/stage14_parameterized_probe.py`
- `tests/benchmarks/test_stage14_parameterized_probe.py`
- `docs/benchmarks/m1-performance-v1.md`
- `docs/benchmarks/m1-performance-v1-results.md`
- `docs/benchmarks/stage14-parameterized-prototype-v1.md`
- `docs/performance-environment.md`
- `docs/stage-15-execution-charter.md`
- `数学绘图助手 PRD.md`

### 15.4 两门验证、审核与退出

第一门只验证协议和工具，不生成正式结果：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='.'; uv run --locked pytest -q -p no:cacheprovider tests/benchmarks/test_m1_5_performance_v1.py tests/test_limits.py tests/test_stage13_public_api.py
```

第一门必须证明 P3-7 的机器可读失败与非零退出、固定文件集合、hash、场景来源、P95 算法、失败样本、GUI 成功判定、OS 进程峰值和禁止全局 limits frozen。独立审核通过并冻结协议/hash 后，才允许运行：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='.'; uv run --locked python -B -m benchmarks.m1_5_performance_v1
```

正式测量后再次运行定向测试、§7 全量 pytest、`git diff --check`、status，并核验九个固定结果文件。独立审核写入 `docs/audits/stage-15f-independent-review-notes.md`；completion 写入 `docs/audits/stage-15f-completion-report.md`。

退出条件：状态粒度不全局冻结输入安全；协议先于测量；15E 典型和最重获批场景均有 P50/P95、OS 进程峰值、采样规模和完整环境/hash；开发机边界明确；M1.6 入口资源值区分实测与外推。任何 production、协议、工具、场景或成功判定变化都使相应结果失效，必须变更控制后重冻和复测。完成后停止。

## 16. 15G：最终验收、P0-07 与 checkpoint 门

### 16.1 任务和边界

PRD 域：§4.2、§6.2、§6.4、§7.2、§12–§15、§20.1、§20.4、§21、§23。复验 Stage 13/14 全矩阵、M1、unified executor、Actor、比例、资源、PNG 和单项原子结果；核对 PRD §4.2/§20.1、人工证据、性能完整性、教材来源和 P0-07；确保 architecture、decisions、supported-formulas、步骤清单、联网确认和人工清单一致。

15G 不预授权生产代码修改。仅文档或最终验收测试中的小型、不改变范围/公共契约/架构的缺陷可在本 allowlist 修复；任何生产缺陷、公共契约变化或性能失效都必须退回 15A–15F 的责任子步。

### 16.2 精确写入 allowlist

- `tests/acceptance/test_stage15g_m1_5_final_acceptance.py`
- `docs/manual-test-checklist-m1.5.md`
- `docs/audits/stage-15-final-acceptance.md`
- `docs/audits/stage-15g-independent-review-notes.md`
- `docs/audits/stage-15g-completion-report.md`
- `docs/architecture.md`
- `docs/decisions.md`
- `docs/m1.5-math-input-scope.md`
- `docs/supported-formulas.md`
- `数学绘图助手_Codex协助开发步骤清单_v0.3.md`
- `联网确认.md`

### 16.3 只读依赖

- `math_drawing_assistant/engine/renderer.py`
- `math_drawing_assistant/engine/scene_executor.py`
- `math_drawing_assistant/engine/__init__.py`
- `math_drawing_assistant/models/results.py`
- `math_drawing_assistant/models/diagnostics.py`
- `math_drawing_assistant/models/__init__.py`
- `math_drawing_assistant/app_controller.py`
- `math_drawing_assistant/workers/render_actor.py`
- `math_drawing_assistant/bootstrap.py`
- `math_drawing_assistant/ui/main_window.py`
- `math_drawing_assistant/ui/widgets/viewport_panel.py`
- `math_drawing_assistant/ui/widgets/status_panel.py`
- `math_drawing_assistant/ui/widgets/plot_preview.py`
- `math_drawing_assistant/config/limits.py`
- `math_drawing_assistant/config/__init__.py`
- `tests/test_stage13_public_api.py`
- `tests/data/m1_5_textbook_matrix_v1.json`
- `docs/evidence/m1.5-textbook-source-ledger-v1.md`
- `docs/benchmarks/m1.5-performance-v1.md`
- `docs/benchmarks/m1.5-performance-v1-results.md`
- `benchmarks/results/m1.5-performance-v1-primary/environment.json`
- `benchmarks/results/m1.5-performance-v1-primary/manifest.json`
- `benchmarks/results/m1.5-performance-v1-primary/records.jsonl`
- `benchmarks/results/m1.5-performance-v1-primary/summary.json`
- `benchmarks/results/m1.5-performance-v1-primary/protocol.sha256`
- `benchmarks/results/m1.5-performance-v1-primary/tools.sha256`
- `benchmarks/results/m1.5-performance-v1-primary/scenario-matrix.sha256`
- `benchmarks/results/m1.5-performance-v1-primary/stdout.txt`
- `benchmarks/results/m1.5-performance-v1-primary/stderr.txt`
- `docs/audits/stage-15a-completion-report.md`
- `docs/audits/stage-15b-completion-report.md`
- `docs/audits/stage-15c-completion-report.md`
- `docs/audits/stage-15d-completion-report.md`
- `docs/audits/stage-15e-completion-report.md`
- `docs/audits/stage-15f-completion-report.md`
- `docs/stage-15-execution-charter.md`
- `数学绘图助手 PRD.md`

### 16.4 验证、审核与退出

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='.'; uv run --locked pytest -q -p no:cacheprovider tests/acceptance/test_stage15g_m1_5_final_acceptance.py tests/test_stage13_public_api.py tests/test_models.py tests/test_diagnostics.py tests/test_limits.py tests/engine/test_renderer.py tests/engine/test_scene_executor.py tests/engine/test_stage14e_acceptance.py tests/workers/test_render_actor.py tests/workers/test_render_actor_agg_probe.py tests/workers/test_render_actor_shutdown.py tests/test_app_controller.py tests/test_bootstrap.py tests/ui/test_main_window.py tests/ui/test_m1_scene_flow.py tests/ui/test_plot_preview.py tests/ui/test_stage15d_m1_5_scene_flow.py tests/acceptance/test_stage15e_m1_5_textbook_matrix.py tests/acceptance/test_stage15e_independent_geometry_oracle.py tests/benchmarks/test_m1_5_performance_v1.py
```

随后运行 §7 全量门禁和文档一致性搜索。独立审核写入 `docs/audits/stage-15g-independent-review-notes.md`；最终审计写入 `docs/audits/stage-15-final-acceptance.md`；completion 写入 `docs/audits/stage-15g-completion-report.md`。

只有全部自动、人工、教材、外部和性能证据通过后，P0-07 已正式关闭，才能创建 M1.5 checkpoint。checkpoint 不由前述文件写入自动触发，必须在 15G 验收后由总架构师明确批准。核心 MVP 状态只能在另行确认 M0/M1 checkpoint 仍有效后单独更新，不能随 M1.5 checkpoint 自动更新。15G 完成后停止。

## 17. 失效、退回与证据真实性规则

- review notes 只能记录真实独立只读审核，主执行者不能把自审冒充独立审核；
- completion report 只能记录实际运行的命令、实际结果和实际文件，不得预填未来通过；
- 人工清单不能用自动测试替代观察，也不能把无法执行的 DPI 档标为通过；
- 教材矩阵不能根据 PRD 示例自行伪造“真实教材来源”；来源缺失时 P0-07 保持打开；
- 正式性能不能使用 Stage 14 直接探针代替端到端链，不能用 `tracemalloc` 代替 OS 进程峰值；
- 生产代码、协议、工具、场景集合、成功判定或 hash 变化后，不得继续引用失效结果；
- 任一子步失败必须在其 completion report 登记，并退回责任子步；不得静默删除测试、样例、人工档位或结果记录来获得绿色出口；
- 每个子步的独立审核、completion 和总架构师验收完成前，下一子步保持未开始。
