# Stage 15-B 独立只读审核 notes：统一 SceneRenderExecutor 与结果契约候选变更

日期：2026-08-21（Asia/Shanghai）
审核者：独立审核窗口（Claude Code 会话，非 Stage 15-B 主实施 Codex）
审核对象：工作树中 Stage 15-B 全部候选变更（14 个 modified + 4 个 untracked，其中 1 个为 completion report）
授权基线：`master @ 124ceb215b7b5ba584456fd6c19273697ec0f887`（`feat(stage15a): unify sampled-curve renderer`）
依据：本审核授权指令、`docs/stage-15-execution-charter.md` §1/§3/§4/§6/§7/§11/§17、`docs/audits/stage-15-0-p3-disposition.md`、`数学绘图助手 PRD.md` §4.2/§6.4/§10.4–§10.5.1/§12.1–§12.3/§20.1、`docs/m1.5-math-input-scope.md`、`docs/decisions.md` D-002/D-003/D-007/D-008/D-017

## 1. 基线与开始状态（本窗口实测）

- `git rev-parse --abbrev-ref HEAD` → `master`；`git rev-parse HEAD` → `124ceb215b7b5ba584456fd6c19273697ec0f887`，与授权基线**精确相等**；`git log -5` 首条为 15A 基线提交
- `git status --short --branch` → `## master...origin/master` + 14 `M` + 4 `??`（含 completion report 与三个新测试文件）
- `docs/audits/stage-15b-independent-review-notes.md` 初始不存在（实测 `REVIEW-NOTES-ABSENT`，符合"实施者不得预建"要求）
- `git diff --check` → exit 0（仅既有 LF/CRLF 信息性提示）
- `git diff --stat` → 14 文件 `928 insertions / 137 deletions`；最大变更为 `scene_executor.py`（±515）与 `results.py`（±145）
- 仓库根 `.codegraph/` 存在；代码理解按约定优先经 CodeGraph 完成（`SceneRenderExecutor`/`analyze_plot_item`/`RenderPlanBuilder`/samplers 调用拓扑、`PlotSceneResult` 默认值、snapshot 构造）
- AGENTS 指令文件：仓库内不存在 `AGENTS.md`（全树查找无命中；本 notes 按 §3 顺序如实登记该事实）

## 2. 审核边界声明

本审核为纯只读核查 + 本 notes 写入；未修改任何生产代码、测试、架构文档、completion report、执行章程、历史审核或任何其他文件；未执行 `git add`/`commit`/`push`/`reset`/`checkout`/`clean`；未实施修复；未进入 Stage 15-C、未运行正式性能、未创建教材证据、未关闭 P0-07、未创建 checkpoint、未做人工视觉看图。主实施者的 completion report 与自报测试结果一律不作为独立证据，全部定向/回归/全量命令由本窗口独立复跑。

## 3. 实际阅读材料

1. `docs/stage-15-execution-charter.md` 全文（重点 §1 优先级、§3 八项冻结契约、§4 唯一目标链、§6 候选文件职责、§7 顺序门禁、§11 15B 边界/allowlist/退出、§17 证据真实性）
2. `docs/audits/stage-15-0-p3-disposition.md`（P3-3/P3-4/P3-5/P3-6 逐项处置）
3. `docs/audits/stage-15a-completion-report.md`、`docs/audits/stage-15a-independent-review-notes.md`
4. `docs/audits/stage-15b-completion-report.md`（仅作被核验对象，不作证据）
5. `数学绘图助手 PRD.md` §4.2、§6.4、§10.4、§10.5、§10.5.1、§12.1–§12.3、§20.1
6. `docs/m1.5-math-input-scope.md` 全文（重点 §10 M1/M1.5 路由、§12.3 旋转拒绝、§16 M1 不回归边界）
7. `docs/architecture.md` 现行相关章节 + diff；`docs/decisions.md` D-002/D-003/D-007/D-008/D-017
8. `docs/supported-formulas.md` 现行相关章节 + diff（版本、STAGE_13_STATUS 块、15A 契约小节 caller 事实更新、新增 15B 小节、STAGE_13_REQUESTED_KIND_MATRIX）
9. Stage 15-B 全部候选 diff 逐 hunk（14 modified 文件）+ 3 个新测试文件全文（999 行）+ completion report 全文
10. 只读 production 依赖源码核验（零修改，git diff --stat 逐文件证实）：`models/state.py`、`models/render_plan.py`（snapshot/receipt 构造 :760-1097）、`engine/plot_analyzer.py`（analyze_plot_item :48-108、_requested_kind_error :426-435）、`engine/viewport_resolver.py`、`engine/render_plan_builder.py`、`engine/samplers.py`（sample_explicit_function :520、sample_parameterized_curve :546 及取消轮询拓扑）、`engine/renderer.py`

## 4. allowlist 与只读依赖核验

授权 allowlist（审核指令 §四 + 章程 §11.2）17 条 + 审核指令明确批准的最小扩展 `tests/engine/test_stage15a_production_boundary.py`：

- 命中 allowlist：scene_executor.py、engine/__init__.py、models/results.py、models/diagnostics.py、models/__init__.py、tests/engine/test_scene_executor.py、三个新 test_stage15b_*.py、test_stage15a_production_boundary.py（获批扩展）、tests/test_models.py、tests/test_diagnostics.py、tests/test_stage13_public_api.py、docs/architecture.md、docs/supported-formulas.md、步骤清单、completion report
- **越界 1 项：`tests/ui/test_m1_scene_flow.py`**（3 处行级修改，±6 行）——章程 §6.2 该文件写入子步为 **15D**（15C 只读、15G 只读）；本审核授权 allowlist 不含它；仓库内（章程、步骤清单、architecture、decisions）无任何 15B 扩展批准留档。completion report §3.2 声称"项目所有者随后明确批准一次性最小 allowlist 扩展"，但该声称仅存在于 completion report 本身，无可独立验证的仓库留档，按证据规则不予采信 → **finding F-1（P2）**
- 只读 production 依赖零触碰：`models/state.py`、`models/render_plan.py`、`plot_analyzer.py`、`viewport_resolver.py`、`render_plan_builder.py`、`samplers.py`、`renderer.py`、limits、Actor、Controller、bootstrap、UI production、clipboard、Stage 14/15A 历史测试与结果、`stage-15a-independent-review-notes.md`——`git diff --stat` 逐文件核实为零 diff

`test_stage15a_production_boundary.py` 获批扩展核验：diff 仅 11 行、只触及两个 caller 事实（`render_explicit_png` 期望改为无 production caller；`render_sampled_curve_png` 期望改为仅 scene_executor.py）及测试名/说明；P3-1 AST 扫描、别名 self-test、renderer singleton、contour/重依赖/反向依赖/benchmark 禁入规则全部未删除未放宽（848 passed 回归门实证）。

## 5. production 链与公共契约核验

唯一链成立：`PlotSceneRequest → _validated_single_manual_item（单项/manual gate）→ analyze_plot_item → PlotSceneSpec(items=(spec,)) → resolve_single_item_viewport → RenderPlanBuilder.build → exact typed sampler → render_sampled_curve_png → PlotSceneResult`。

- scene_executor.py 已删除 `analyze_explicit_function`/`build_explicit_scene_spec`/`resolve_single_explicit_viewport`/`render_explicit_png` 的全部 import 与调用（grep 零命中；engine/__init__.py 保留的 `analyze_explicit_function`/`render_explicit_png` 为 15A 既有公共兼容导出，非 executor 调用）
- exact 分发（scene_executor.py:213-225）：`ConcretePlotType.EXPLICIT_FUNCTION` → `sample_explicit_function` + exact `SampledExplicitFunction`；五种 geometry → `_sample_geometry_curve_for_scene`（engine/__init__.py:49 与 `sample_parameterized_curve` 同一函数对象的私有别名，不在 `__all__`，import 顺序无循环问题）+ exact `SampledParameterizedCurve`；union/type/item_id 不一致一律 fail-closed INTERNAL_ERROR 且不进 renderer（sampler_identity 测试六类+跨类+裸 object+错 item_id+plan union mismatch 矩阵实证）
- `_validate_dispatch_plan`（:450-480）复核 plan.scene_spec 单项 exact type 与 analyzer spec 同型同 item_id、item plan 与 concrete type 匹配、memory_budget 存在
- 无第二 executor/resolver/Builder/sampler/renderer/receipt；无 contour、solve 或通用 fallback；无 Actor/Controller/UI/clipboard/bootstrap 修改
- `ConcretePlotType` 六成员与冻结值逐字一致；`PlotKind` 四值不变（models/state.py 零 diff + 哨兵测试钉住）；六 Spec→(PlotKind, ConcretePlotType) 映射与冻结表逐项一致；`PlotItemResult` 新增 `concrete_plot_type`/`diagnostics`，成功/失败互斥、failed error 必绑定同 item_id、plot_kind 与 concrete 同现同缺、映射不矛盾、diagnostics 需已知 concrete type、warnings 为自有 exact-str tuple 非空无重复、frozen/slots、拒任意字符串 enum——均由 `__post_init__` 源码 + test_models/test_stage13_public_api 实证
- 诊断契约：`PlotItemDiagnostics`（planned/actual/segments 四字段）与 `PlotSceneDiagnostics`（total planned/actual、approved memory、PNG count）frozen/slots；bool 拒绝、正数、三字段全有全无、actual==planned、visible≤sampled、scene actual==planned、PNG count 依赖 sampling 完成且 `== len(png_bytes)`（构造时交叉校验）；字段语义逐一核验：planned 来自 `plan.item_plan.sample_count`、actual 来自 `sampled.x.shape[0]`、segments 来自 `segment_ranges.shape[0]`/`visible_segment_count`、parameterized 与 `ParameterizedSamplingDiagnostics` 交叉核验、approved memory 来自 `plan.memory_budget.total_bytes` 且文档明确为获批预算而非进程峰值；结果不携带 RenderPlan/receipt/NumPy/Matplotlib 对象

## 6. 字段保留阶段、warning/failure/cancellation、elapsed_ms

七阶段保留矩阵（源码 :59-377 逐路径 + unified_executor 测试实测）：

1. request gate / analyzer 失败：无 concrete type、无 diagnostics，item 已知时 ErrorInfo 绑定该 item；empty/multi 无唯一归属时不生成 item result（实测 `item_results == ()`）
2. viewport 失败：normalized input、PlotKind、ConcretePlotType 保留；无 viewport、无 diagnostics
3. plan 失败：类型与 resolved viewport 保留；无 diagnostics；viewport warning 只属 scene（`test_plan_failure_keeps_viewport_warning_scene_only` 实证 item warnings == ()——旧实现把 viewport warning 复制到 item 的不一致已消除）
4. sampling 失败：planned diagnostics + approved memory 保留；actual/segments/visible/PNG 不伪造（全 None，构造不变量强制）
5. render 失败：完整 sampling diagnostics 保留；PNG count 不存在
6. 成功：item/scene diagnostics 完整，PNG count 精确 == len(png_bytes)
7. 取消：九字段中性 sentinel（success=False、error=None、png_bytes=None、item_results=()、resolved_viewport=None、warnings=()、diagnostics=None、elapsed_ms=()），本窗口独立探针实测输出逐字段吻合

warning 归属：viewport warning 仅 scene；sampling warning 归 item；scene 顺序 viewport 在前 sampling 在后（`_stable_unique` 保首次去重）；同一 sampler outcome 内重复 code → INTERNAL_ERROR fail-closed；`viewport_clipped`/`sampling_precision_limited` 不丢失。ErrorInfo：item_id=None 复制补绑；不同 item_id → 绑定当前 item 的不可恢复 INTERNAL_ERROR；scene 与 item error 为同一对象（`is` 断言）；`NO_VISIBLE_CURVE` 为 typed failure、renderer 不运行、无空白成功 PNG（双输入参数化实证）。`SamplingCancelled`/`RenderCancelled` item_id 不匹配时 fail-closed 为 INTERNAL_ERROR，不作中性取消。异常边界：executor 仅 3 处窄捕获 `(AttributeError, TypeError, ValueError)`，无 RuntimeError/MemoryError 宽泛捕获；未约定异常传播出 executor 由 Actor 脱敏（旧测试保留并通过）。

elapsed_ms：`perf_counter_ns` 单调高分辨率、毫秒单位、`StageTiming` frozen/slots、六阶段固定顺序（request_validation/analysis/viewport_resolution/render_plan/sampling/rendering）、失败只含已执行前缀（各失败路径 timings 实测）、取消 sentinel 空、文档明确不冒充 15F 正式性能证据。

## 7. M1 不回归与 requested-kind 矩阵

本窗口独立探针（`uv run --locked python -B`，只读）：

- `analyze_explicit_function("y+1=x+2")` → `UNSUPPORTED_EQUATION`（M1 旧入口不改写）
- `analyze_plot_item`：`y=2*x+1`、`x=y` → `ExplicitFunctionSpec` / `EXPLICIT_FUNCTION`（直接显函数优先保持）
- 统一 executor：`y+1=x+2`（400×300）成功为 `LINE_EQUATION` / `GENERAL_LINE`，PNG 非空，六阶段 timings 完整
- OCR → `INVALID_REQUEST/input_source`；empty/multi → `INVALID_REQUEST` 且无 item result（探针中 200×150 失败系既有输出尺寸下限，与 15B 无关，已另行澄清）
- 七输入 × 四 PlotKind：`tests/engine/test_stage15b_unified_executor.py` REQUESTED_KIND_MATRIX 28 格与 `docs/supported-formulas.md` STAGE_13_REQUESTED_KIND_MATRIX（:742-752）逐格一致并全部通过
- `tests/engine/test_scene_executor.py`：无旧核心断言删除或实质放宽；删除的仅 requested_plot_kind 两用例（其断言行为已被 15B 冻结契约有意改变），由 28 格矩阵等价且更强覆盖；Actor 脱敏/恢复、取消语义、禁止依赖/裸名唯一性断言全部保留并经 242+2542 passed 实证
- 旧错误码语义：`INVALID_REQUEST` 等错误码保留；仅两处 user/technical 文案随语义统一必要调整（见 F-2）

## 8. P3-3/P3-4/P3-5/P3-6 结果

- **P3-3 完整**：FRACTION_FIELDS 与生产 `_snapshot_geometry_spec`（render_plan.py:1044-1073）的 14 个 Fraction 字段逐项一致（Circle 3 + Ellipse 4 + Hyperbola 4 + Parabola 3），测试固定 `len == 14`；逐字段原位篡改全部被 `validate_approved_render_plan` 拒绝，receipt identity 不变、不重新签发（`plan._approval_receipt is receipt` 断言）
- **P3-4 完整**：六种 exact spec 的 scene-spec `item_id`（六参数化，含显函数与五种 geometry）+ explicit item-plan `item_id` 各自独立篡改拒绝
- **P3-5 完整**：EXPLICIT_PLAN_SNAPSHOT_FIELDS 31 项与生产 `_approval_snapshot_from_plan`/`_snapshot_explicit_item_plan`/`_snapshot_explicit_memory`（render_plan.py:862-995）的 explicit 计划侧拷贝点**精确相等**（viewport 6 + top-level 10 + item-plan 5 + memory 10），测试固定 `len == 31`；每字段单独篡改（保型篡改，非 None 字段不触发类型拒绝，必须由 snapshot 比对拒绝）、receipt identity 不变
- **P3-6 完整**：ellipse（oval 共享采样分支）/hyperbola/parabola 三参数化，先以永不取消 probe 实测总 poll 数，再遍历 target=1..poll_count 全部取消点，每次得到 exact `SamplingCancelled`、item_id 精确等于 `plan.item_plan.item_id`、`fields == ["item_id"]` 且无 x/y/ranges/warnings/diagnostics 部分结果——无固定点抽查

## 9. public API、文档与 completion report

- `models.__all__` 恰好新增 `ConcretePlotType`、`PlotItemDiagnostics`、`PlotSceneDiagnostics`（哨兵 frozenset 同步 + identity/frozen/slots 断言）；`engine.__all__` 集合不变，`_sample_geometry_curve_for_scene` 为不在 `__all__` 的私有别名；无分类型 executor/renderer、dispatcher、receipt helper、Spec-to-result 公共导出（`test_engine_package_publishes_only_the_stage_13_entry_point` 未改动并通过）
- `docs/supported-formulas.md` 版本精确为 `stage-15b-unified-executor-v1`；15B 小节准确说明统一 executor、六类型进统一 renderer、未修改 Actor/Controller/UI、15C/15D 归属、Stage 15 未完成、P0-07/教材/性能/checkpoint/核心 MVP 未完成；「明确未实现与门禁」同步
- `docs/architecture.md`：新增 §7.11 Stage 15B 契约；最后更新日期 2026-08-21（= 实际实施日期）；未改写 15A 历史审核内容（15A review notes 零触碰；supported-formulas 15A 小节仅做 caller 事实前向更新并保留「15A 完成时」历史限定）；无提前宣称后续阶段
- 步骤清单只登记 15B 候选完成、等待审核，未宣称 15C
- completion report：文件清单、命令、计数与事实核对——242/848/2542 passed 与本窗口复跑精确一致；`git diff --check` 通过一致；未预称独立审核 APPROVE；未声称进入 15-C。其 §3.2 的项目所有者批准声称除外（见 F-1，不可作为独立证据）

## 10. 实际运行命令与真实结果（本窗口，Git Bash 适配）

| 门 | 命令（前缀 `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. uv run --locked pytest -q -p no:cacheprovider`） | 结果 |
|---|---|---|
| 15B 定向门 | test_scene_executor.py test_stage15b_unified_executor.py test_stage15b_receipt_hardening.py test_stage15b_sampler_identity.py test_render_plan.py test_models.py test_diagnostics.py test_stage13_public_api.py | **242 passed** in 11.49s；0 failed / 0 errors / 0 skipped |
| 只读回归门 | test_renderer.py test_stage15a_geometry_renderer.py test_stage15a_production_boundary.py test_samplers.py test_stage14b1_contracts.py test_stage14b2_line.py test_stage14c_circle_ellipse.py test_stage14d1_hyperbola.py test_stage14d2_parabola.py test_stage14e_acceptance.py test_render_actor_agg_probe.py | **848 passed** in 59.56s；0 failed / 0 errors / 0 skipped |
| 全量 | 同前缀全仓库 | **2542 passed** in 169.90s；0 failed / 0 errors / 0 skipped（全量耗时与 completion report 的 96.21s 不同，属机器负载差异，计数一致） |
| 行为探针 | `uv run --locked python -B`（只读脚本） | M1 旧入口拒绝 / 直接显函数保持 / 统一入口成功 / 九字段取消 sentinel / OCR 与 empty/multi 门禁全部吻合 |
| 差异检查 | `git diff --check 124ceb2…` | 通过（exit 0） |
| 新文件行尾空白 | grep 三个新测试文件 | 零行尾空白；completion report :3-4 行尾双空格为既有 audit 文档 Markdown 硬换行惯例（15A 审核同判），非缺陷 |

一次成功、无重试、未修改任何代码/测试/skip/xfail。

## 11. findings

**F-1（P2）：`tests/ui/test_m1_scene_flow.py` 越出 Stage 15-B 授权 allowlist，且仓库内无批准留档 —— 【已关闭：2026-08-21 项目所有者正式授权追认，见 §14】**

- 位置：`tests/ui/test_m1_scene_flow.py:508`、`:516`（monkeypatch 目标 `render_explicit_png`→`render_sampled_curve_png`）、`:640`（失败输入 `x+y=1/UNSUPPORTED_EQUATION`→`x*y=0/ROTATED_CONIC_NOT_SUPPORTED`）
- 违反条款：章程 §6.2（该文件写入子步为 15D；15B 只读）与 §6.1/§11.2 allowlist；本审核授权 §四 allowlist 亦不含该文件
- 证据：`git diff` 3 处行级修改 ±6 行；章程 :165 明确归属；全仓 grep 无 15B 扩展批准留档；completion report §3.2 的"项目所有者明确批准"声称仅存在于该报告自身，按章程 §17 与本审核指令不可作为独立证据
- 影响评估（两方面如实登记）：修改**技术上必要且正确**——production executor 收口后旧 monkeypatch 探针必然失效；AUTO `x+y=1` 按 15B 冻结契约（PRD §20.1、supported-formulas 矩阵）必须成功为 LINE_EQUATION，历史失败断言必然失效；替代输入 `x*y=0 → ROTATED_CONIC_NOT_SUPPORTED` 为 Stage 13 既有 analyzer 契约（test_plot_analyzer.py:252，该文件零修改）；renderer/Actor/GUI 线程归属、输入保留、错误显示、复制状态断言全部保留，无断言放宽。但**授权链不完整**：该文件对 15B 属只读，越界写入本身违反冻结 allowlist，且无法在仓库内验证批准
- 为什么现有测试没有发现：allowlist 合规由人工审核与 git status 核验，无自动化哨兵
- 最小修复方向：由项目所有者/总架构师在验收时对 completion report §3.2 声称的一次性批准做正式确认并补充留档（例如章程 §11.2 补记该扩展及理由，或以等效变更控制记录登记），使该两处维护获得追溯授权；若不获确认，则 15B 候选须回退该文件——但注意回退后 `test_real_scene_executor_runs_in_actor_and_preview_updates_on_gui_thread` 与 `test_formal_failures_preserve_input_previous_preview_and_copy_state` 将因 15B 冻结契约必然失败，全量门无法保持绿色，故实质出路是补授权而非回退
- 退回责任：Stage 15-B（补授权留档后由总架构师验收处置；不需要改代码）

**F-2（P3，非阻塞）：`_invalid_request` 用户文案与技术文案随统一语义调整，属行为可见变化**

- 位置：`math_drawing_assistant/engine/scene_executor.py:650`（"当前阶段只支持一个手动输入的显函数绘图项。"→"当前阶段只支持一个手动输入的绘图项。"）及 :414-427 三条 technical message（"M1 …"→"manual …"）
- 违反条款：无硬性冻结条款；错误码 `INVALID_REQUEST` 与 field_name 语义保留，文案变化是 executor 从 M1 显函数专用统一为六类型后的必然伴随，非"为通过测试而改写"（无任何测试断言旧文案，grep 证实）
- 影响：用户在 request gate 失败时看到的中文提示措辞变化；M1 场景错误码与恢复语义不变
- 为什么现有测试没有发现：无文案级哨兵（既有测试只钉错误码/field_name）
- 最小修复方向：无需代码修改；建议后续文档触点（15D/15G）在用户可见文案登记中同步该变化
- 退回责任：无需退回；登记供 15G 文档一致性复查

**F-3（P3，非阻塞，观察登记）：executor 三处旧 `raise TypeError` 防线改为 typed `INTERNAL_ERROR` failure**

- 位置：scene_executor.py:131-140（viewport outcome）、:258-271（sampling outcome type）、:326-340（renderer outcome type）
- 说明：旧 M1 对非 exact stage outcome 直接 raise 交 Actor 脱敏；15B 改为绑定 item 的不可恢复 `INTERNAL_ERROR`（recoverable=False，technical_message 脱敏）。方向与 15B fail-closed 契约一致且均有测试；`_is_cancelled` 的 probe 契约 TypeError（:556-557）与 request 类型 TypeError（:411-412）保留 raise。未约定 RuntimeError/MemoryError 仍无宽泛捕获（全文件仅 3 处窄捕获）。无行动需求
- 退回责任：无需退回

F-1 已由项目所有者正式授权追认关闭；当前无未关闭的 P0/P1/P2 findings。无安全/数据破坏/证据造假；无错误成功、漏画、错误类型或 M1 破坏；失败/取消/warning/diagnostic/API 契约完整。

## 12. 最终 git status（审核结束时）

`## master...origin/master`；`M docs/architecture.md`、`M docs/supported-formulas.md`、`M math_drawing_assistant/engine/__init__.py`、`M math_drawing_assistant/engine/scene_executor.py`、`M math_drawing_assistant/models/__init__.py`、`M math_drawing_assistant/models/diagnostics.py`、`M math_drawing_assistant/models/results.py`、`M tests/engine/test_scene_executor.py`、`M tests/engine/test_stage15a_production_boundary.py`、`M tests/test_diagnostics.py`、`M tests/test_models.py`、`M tests/test_stage13_public_api.py`、`M tests/ui/test_m1_scene_flow.py`、`M 数学绘图助手_Codex协助开发步骤清单_v0.3.md`；`?? docs/audits/stage-15b-completion-report.md`、`?? tests/engine/test_stage15b_receipt_hardening.py`、`?? tests/engine/test_stage15b_sampler_identity.py`、`?? tests/engine/test_stage15b_unified_executor.py`、`?? docs/audits/stage-15b-independent-review-notes.md`（本文件，唯一新增写入）。HEAD 保持 `124ceb215b7b5ba584456fd6c19273697ec0f887` 未变。

## 13. 最终裁定

**PASS**

- 技术实质：唯一 production 链、六类型与 requested-kind 矩阵、公共结果/诊断契约、warning/failure/cancellation 归属、P3-3/4/5/6、15A production boundary 获批扩展、M1 不回归、定向 242 / 回归 848 / 全量 2542 独立复跑全绿、diff check 通过、文档与 completion report 计数准确——**全部满足 APPROVE 的技术条件**
- F-1：项目所有者已于 2026-08-21 正式批准并追认 `tests/ui/test_m1_scene_flow.py` 的 Stage 15-B 最小 allowlist 扩展；当前实际 diff 与授权范围逐项相等，变更控制证据见 §14。原唯一阻塞项已关闭，allowlist 合规条件成立
- F-2/F-3 为非阻塞 P3，已登记责任点，可在后续文档触点消化
- 明确声明：本审核及本次变更控制闭环未修改任何候选代码或测试、未进入 Stage 15-C、未运行正式性能、未创建教材证据或 checkpoint、未关闭 P0-07、未执行 `git add`/`commit`/`push`；本次闭环仅更新本 notes

## 14. F-1 变更控制证据与关闭复核

2026-08-21，项目所有者正式批准并追认将 `tests/ui/test_m1_scene_flow.py` 加入 Stage 15-B 授权修改范围。授权严格限于：

1. 将已退出 production 的 `scene_executor.render_explicit_png` monkeypatch 探针更新为唯一 production renderer `scene_executor.render_sampled_curve_png`；
2. 将与 Stage 15-B 冻结成功契约冲突的失败参数 `("x+y=1", ErrorCode.UNSUPPORTED_EQUATION)` 替换为既有稳定失败契约 `("x*y=0", ErrorCode.ROTATED_CONIC_NOT_SUPPORTED)`；
3. 仅在必要时进行相应 import/格式同步；不授权修改 Actor/UI production，不授权降低或删除原有 UI 断言。

批准理由：旧 renderer 探针在 Stage 15-B production 链收口后必然失效；AUTO `x+y=1` 已冻结为 `GENERAL_LINE / LINE_EQUATION` 成功契约；两项变更仅维护历史回归测试，不实施 Stage 15-C/15-D；独立审核已确认其技术必要性、正确性和断言强度不变。

关闭复核：

- 当前 UI diff 恰为 3 个行级替换：保存真实 renderer 与 monkeypatch target 两行改用 `render_sampled_curve_png`，参数表一行改用 `x*y=0 / ROTATED_CONIC_NOT_SUPPORTED`；没有 import 或格式附带变更；
- renderer/Actor/GUI 线程归属断言，以及输入、旧预览、错误显示、复制状态断言均原样保留；
- Actor/UI production 零修改，`render_explicit_png` production 调用或兼容 alias 未恢复，AUTO `x+y=1` 成功契约未回退；
- 独立审核针对同一候选 diff 的 Stage 15-B 定向门 **242 passed**、只读回归门 **848 passed**、全量 **2542 passed**，且 `git diff --check` 通过；本次仅追加变更控制证据与同步裁定，不改变这些门禁覆盖的代码或测试，既有结果继续有效。

据此，F-1 的授权链缺口已消除并正式关闭；Stage 15-B 最终裁定为 **PASS**。不需要回退或重新设计 production 代码。
