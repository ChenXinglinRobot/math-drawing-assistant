# Stage 15-D1 + 15-D2 累积候选独立只读审核 notes

日期：2026-08-21（Asia/Shanghai）
审核者：独立只读审核窗口（Claude Code 会话，非 Stage 15-D 主实施 Codex）
审核对象：工作树中 Stage 15-D1 + Stage 15-D2 全部累积候选变更（11 个 tracked modified + 2 个 untracked，共 13 个文件）
依据：本审核授权指令、`docs/stage-15-execution-charter.md` §1/§3（第 4、5 项）/§7/§13/§17、`docs/decisions.md` D-002/D-003/D-004/D-017、`docs/audits/stage-15c-completion-report.md`、`docs/audits/stage-15c-independent-review-notes.md`、`数学绘图助手 PRD.md` §6.2/§6.4/§6.6/§6.7/§6.8/§12/§14/§15/§20.1/§20.4

## 1. 审核基线与开始状态

本窗口开始时逐条实测并记录原始输出：

- `git rev-parse HEAD` → `3c8984176f77936daf197183b3b0434638b54b21`（`Complete Stage 15-C production chain verification`），与 Stage 15-C 收口基线**精确相等**。
- `git rev-parse origin/master` → `3c8984176f77936daf197183b3b0434638b54b21`，与 HEAD 相等。
- `git status --short --branch` → `## master...origin/master` + 11 个 `M` + 2 个 `??`（`docs/audits/stage-15d-completion-report.md`、`tests/ui/test_stage15d_m1_5_scene_flow.py`）。恰为 13 个候选文件，无越界写入，无重叠用户修改。
- `git diff --check` → exit 0，无 whitespace error；仅 LF→CRLF 信息提示。
- `git diff --stat` → 11 个 tracked 文件 `643 insertions(+), 51 deletions(-)`；两个 untracked 为新增文件（216 行 completion report、503 行新测试）。
- **`docs/audits/stage-15d1-independent-review-notes.md` 或任何 D1 专属独立审核 notes 均不存在**（`docs/audits/` 全列表实测：15-0/15A/15B/15C 有独立 notes，15D 无）。此事实构成本 notes §9 的证据链缺口登记，并把本审核确立为 D1+D2 的**累积补审核**。
- 仓库存在 `.codegraph/`；已按约定先用 CodeGraph 定位（`MainWindow.handle_render_result`/`_sync_controller_state`、`AppController.handle_render_result`/`prepare_copy_candidate`/`create_m1_render_request`、`PlotSceneResult.warnings`、`ConcretePlotType`、`PlotPreview`、`_resolved_aspect` 调用拓扑），随后读取指定章程/裁定/PRD/15-C 报告与全部候选 diff。

## 2. 审核边界声明

本审核为纯只读核查 + 本 notes 唯一写入。未修改任何 production 代码、测试、文档、completion report、章程或配置；未执行 `git add`/`commit`/`push`/`reset`/`checkout`/`clean`；未实施修复、未调整断言、未增加 skip/xfail、未延长任何超时；未进入 15-D3 或 Stage 15-E；未关闭 P0-07、未创建 checkpoint、未运行正式性能或人工 GUI 验收。主实施者 completion report 的自报计数一律不作为独立证据，四组测试命令全部由本窗口独立复跑（§7）。

## 3. 实际阅读材料

1. `docs/stage-15-execution-charter.md` 全文（§3 冻结契约第 4/5 项、§6 候选文件职责、§7 顺序门禁、§13 15D 边界/allowlist/定向门/退出条件、§17 证据真实性）。
2. `docs/decisions.md` D-002/D-003/D-004/D-017；`docs/architecture.md` §5.2 修改与新增 §7.13/§7.14；`docs/supported-formulas.md` 状态行、warning 表新列、15-D1 UI 映射表、15-D2 章节 diff。
3. `docs/audits/stage-15c-completion-report.md`、`stage-15c-independent-review-notes.md`（核验 15C APPROVE 基线与 P3-1/P3-2 遗留观察）；`docs/audits/stage-15d-completion-report.md`（仅作被核验对象）。
4. `数学绘图助手 PRD.md` §6.2、§6.4、§6.6–§6.8、§12.1–§12.3、§14、§15、§20.1、§20.4。
5. production 源码逐段：`ui/main_window.py`（全文件关键区）、`ui/widgets/viewport_panel.py`、`ui/widgets/status_panel.py`、`ui/widgets/plot_preview.py`（含未修改的 `set_stale`/`_refresh_pixmap`）、只读依赖 `app_controller.py`（`handle_render_result`/`prepare_copy_candidate`/`create_m1_render_request`/`mark_scene_edited`）、`bootstrap.py`（relay 接线）、`engine/viewport_resolver.py`（`_resolved_aspect`）、`engine/scene_executor.py`（warnings 聚合与 `INVALID_REQUEST` 文案）、`models/results.py`（`ConcretePlotType`/`PlotItemResult`/`PlotSceneResult`）、`models/errors.py`（`ErrorCode.NO_VISIBLE_CURVE`/`ViewportWarningCode`）、`models/state.py`（`AspectRequest`）、`engine/samplers.py`（四个 sampling warning code）、`services/clipboard_service.py`。
6. 全部候选测试 diff 逐行审阅（§4 清单）＋新文件 `tests/ui/test_stage15d_m1_5_scene_flow.py` 全文（503 行）。
7. `docs/benchmarks/m1-performance-v1.md` 冻结行（`| 比例 | auto |` 仍在，文件零 diff）；`benchmarks/` 与 `docs/benchmarks/` 目录零 diff 实测。

## 4. 候选 diff 与 allowlist 核验

授权的 D1+D2 累积文件并集共 13 个 literal path，实际工作树**逐项相等、无多余**：

| 文件 | 状态 | 归属 |
|---|---|---|
| `math_drawing_assistant/ui/widgets/viewport_panel.py` | M | D1 |
| `math_drawing_assistant/ui/main_window.py` | M | D2 |
| `math_drawing_assistant/ui/widgets/status_panel.py` | M | D2 |
| `math_drawing_assistant/ui/widgets/plot_preview.py` | M | D2 |
| `tests/benchmarks/test_m1_benchmark_protocol.py` | M | D1（一次性扩展授权，见 §8 P3-1） |
| `tests/test_app_controller.py` | M | D1 |
| `tests/ui/test_main_window.py` | M | D1+D2 |
| `tests/ui/test_m1_scene_flow.py` | M | D1+D2 |
| `tests/ui/test_plot_preview.py` | M | D2 |
| `tests/ui/test_stage15d_m1_5_scene_flow.py` | ?? 新增 | D2 |
| `docs/architecture.md` | M | D1+D2 |
| `docs/supported-formulas.md` | M | D1+D2 |
| `docs/audits/stage-15d-completion-report.md` | ?? 新增 | D1+D2 |

以下只读依赖相对基线**零 diff**（`git diff --name-only` 实测空）：`app_controller.py`、`bootstrap.py`、`workers/render_actor.py`、`engine/scene_executor.py`、`engine/viewport_resolver.py`、`engine/render_plan_builder.py`、`engine/samplers.py`、`engine/renderer.py`、`models/`（state/results/errors/diagnostics 等）、`services/clipboard_service.py`、`tests/test_stage13_public_api.py`、`tests/test_stage15c_production_chain.py`、`tests/services/test_clipboard_service.py`、`tests/test_bootstrap.py`、`tests/workers/*`、根目录 `main.py`/`main_window.py`/`plot_engine.py`、`docs/benchmarks/`、`benchmarks/` 全部结果文件与 hash。章程 §13.3 只读清单全部保持只读。

## 5. D1 冻结契约逐项裁定

1. **UI 固定显示"按图形默认/自动/等比例"，提交 exact default/auto/equal** — **PASS**。`viewport_panel.py:37-41`（`ASPECT_OPTIONS` 插入序 default→auto→equal）、`:74-77`（description 覆盖三态）、`:81-82`（addItem 携带 key data）；`tests/ui/test_main_window.py:137-165` 断言 itemText/itemData/顺序精确三元组。
2. **默认选中 DEFAULT，UI 不解析图形类型** — **PASS**。首项自然成为 currentIndex 0；`aspect_mode()`（`viewport_panel.py:216-219`）异常非字符串 data 回退 `default`（测试注入 `None` data 项验证回退）；`tests/ui/test_main_window.py:193-210` 对 `main_window` + `viewport_panel` 源码断言禁入 `math_drawing_assistant.engine`/`matplotlib`/`ResolvedAspect`/`PlotKind`/resolver/Builder/sampler 符号。
3. **每次真实显示配置变化只沿既有 revision 通道增加一次 revision** — **PASS**。比例下拉唯一 `currentIndexChanged → scene_edited` 连接（`viewport_panel.py:146`），经 `MainWindow._handle_scene_edited → AppController.mark_scene_edited`（`main_window.py:308-318` → `app_controller.py:167-174`）+1；同值设置不触发信号。`tests/ui/test_main_window.py:169-189`（QSignalSpy 三次真实变化 1/1/2/3 计数）与 `tests/ui/test_m1_scene_flow.py:176-204`（revision 逐次 +1、重复设值不变）双重钉住。
4. **MainWindow 生成时只采集一次不可变 UI 快照** — **PASS**。`main_window.py:335-344` 每字段恰读一次；`tests/ui/test_m1_scene_flow.py:206-259` 用计数 wrapper 在 submit 线性化点证明 10 个字段各读一次（观测点收紧的正当性已由 completion report §4.2 第 4 项诚实登记）。
5. **Controller 无损保存 AspectRequest 三态** — **PASS**。`app_controller.py:255` `AspectRequest(aspect_request)`（该文件零 diff，三态适配为既有实现）；`tests/test_app_controller.py:241-267` 参数化 DEFAULT/AUTO/EQUAL 断言 `request.viewport.aspect_request is` 各 exact 枚举且 auto 模式不复制 disabled bounds。
6. **production resolver 显函数/一般直线 DEFAULT→AUTO，圆锥曲线 DEFAULT→EQUAL** — **PASS**。`viewport_resolver.py:215-231`（`ExplicitFunctionSpec`/`LineSpec` → `AUTO`，其余 → `EQUAL`，零 diff）；纵向证据：`tests/ui/test_m1_scene_flow.py:723-797`（真实 Actor + 真实 `SceneRenderExecutor` 委托的 10 案例矩阵，含六类 DEFAULT 与显式覆盖）、`tests/ui/test_stage15d_m1_5_scene_flow.py:195-222`（正式 bootstrap 对象图六类型 + `resolved_viewport.aspect` 断言）、`tests/ui/test_m1_scene_flow.py:704-706`（既有 M1 显函数链新增 `ResolvedAspect.AUTO` 断言）。
7. **显式 AUTO/EQUAL 与 manual 四边界优先** — **PASS**。resolver 中 AUTO/EQUAL 判定先于 DEFAULT（`viewport_resolver.py:217-219`）；manual 案例（`tests/ui/test_m1_scene_flow.py:779-796`）断言 `ViewportSource.MANUAL` + exact 四边界 + DEFAULT→EQUAL 共存。
8. **benchmark 历史协议 auto 与当前 UI default 诚实拆分，冻结协议/工具/结果/hash 零修改** — **PASS**。`tests/benchmarks/test_m1_benchmark_protocol.py` 拆为 `test_m1_performance_v1_keeps_its_historical_auto_aspect_default`（只读断言协议文档保留冻结行 `| 比例 | auto | ViewportPanel 首个 aspect 项 |`，实测该行仍在 `docs/benchmarks/m1-performance-v1.md:75`）与 `test_current_ui_and_controller_defaults_are_exercised_separately`（具名 JSON 快照断言当前 `aspect_mode=default`）；`git diff -- docs/benchmarks/ benchmarks/` 空输出实测，协议、工具、结果、hash、八场景、阈值全部零修改。
9. **不存在 UI→engine/parser/sampler/renderer/Matplotlib 旁路** — **PASS**。全 `math_drawing_assistant/ui/` grep `matplotlib|engine|parser|sampler|renderer|numpy|sympy` 零命中；根目录 `main.py`/`main_window.py`/`plot_engine.py` 未被包内任何 import 引用（15-C 的 fresh-subprocess 证明用例在本轮全量中继续通过）。

## 6. D2 冻结契约逐项裁定

1. **先调用 AppController.handle_render_result，只按 disposition 更新 GUI** — **PASS**。`main_window.py:428` 首行调用 Controller 分类，其后只按 `RenderResultDisposition` 与 Controller 派生态（`last_successful_result`/`last_error_notice`/`has_plot_result`/`result_is_stale`/`task_phase`）分支；bootstrap 正式接线 `actor.result_ready → window.handle_render_result`（`bootstrap.py:53`，零 diff）。
2. **只有 ACCEPTED_SUCCESS 可替换图片、图形类型、规范化表达式和 warning** — **PASS**。四类 artifact 写入只存在于 accepted 分支（`main_window.py:436-471`）；`tests/ui/test_stage15d_m1_5_scene_flow.py:352-425` 断言 stale/failure/obsolete 三态后 image+summary+warnings+copy candidate 与基线全等。
3. **failure/cancelled/stale/obsolete 不替换 accepted artifacts** — **PASS**。`IGNORED_OBSOLETE` 分支只刷新 phase/stale UI（`main_window.py:429-434`）；`HANDLED_CURRENT_FAILURE` 只写主状态；取消结果由 Actor gate 抑制不发布（15-C 已证，本轮全量复验）。
4. **request_id/scene_revision 双门完全属于 Controller，GUI 不复制判断逻辑** — **PASS**。`grep request_id|scene_revision` 在 `ui/main_window.py` 与全部 widgets 零命中（实测 exit 1）；双门实现只在 `app_controller.py:316-360`（零 diff）。
5. **六类中文类型一套映射、同一 accepted-result 展示入口** — **PASS**。`main_window.py:64-71` 唯一 `_PLOT_TYPE_LABELS` 字典（六枚举全覆盖 `ConcretePlotType`，`models/results.py:50-58`）；唯一入口 `PlotPreview.set_result`；`tests/ui/test_stage15d_m1_5_scene_flow.py:490-503` 源级断言 `ACCEPTED_SUCCESS` 恰出现一次、`set_result(` 恰一次、无按类型 if 分支、无 engine/matplotlib。
6. **warning 是成功附加信息，全套子契约** — **PASS**：
   - 与主状态分离：`status_panel.py:50-77` 新增独立 `_warning_label`（QVBoxLayout 下方、objectName `persistentWarning`、accessibleName "绘图警告"）。
   - 持久/中文/可访问：五个 code 固定中文映射（`main_window.py:73-81`），与发布的 1 个 resolver warning（`errors.py:62`）+ 4 个 sampler warning（`samplers.py:103-106`）精确一致；`status_panel.py:103-118` 设文本并写入 accessibleDescription。
   - 复制反馈/计时器不覆盖：`_show_copy_feedback` 与 `_restore_after_copy_feedback`（`main_window.py:533-536`、`:551-552`）只经 `set_status` 写主状态；`test_stage15d_m1_5_scene_flow.py:278-291` 直接 `timeout.emit()` 后断言 warning 不变。
   - failure/stale/rendering 与上一张成功图共同保留：`set_warning_messages` 只在 accepted 分支被调用，`_sync_controller_state` 从不触碰；`test_stage15d_m1_5_scene_flow.py:325-338` 在真实 no-visible 失败后断言 warning/image/summary 三者保留。
   - 下一张 accepted success 才替换：`test_stage15d_m1_5_scene_flow.py:293-297` 断言新 accepted（warnings=()）后清空且隐藏。
7. **no_visible_curve 保持 typed failure，仅专属中文句，无 ErrorCode→中文旁路表** — **PASS**。`_failure_message`（`main_window.py:538-544`）只对 `ErrorCode.NO_VISIBLE_CURVE`（`errors.py:55`）返回专属句，其余一律透传 `notice.user_message`，不存在第二张映射表；production 侧 `renderer.py:691`/`render_plan_builder.py:2294-2327`/`samplers.py:2978` 的 typed failure 零 diff。
8. **当前请求失败且有旧图时明确显示"本次生成失败，预览仍是上一张成功图片。"** — **PASS**。`main_window.py:518-527`（含 containment 检查只追加一次）与 `:491-495`（stale 徽标同句）；production 纵向 `test_stage15d_m1_5_scene_flow.py:327-348` 断言完整状态句及该句恰出现一次。
9. **无旧图失败不伪造旧图保留状态** — **PASS**。`has_plot_result` 门（`main_window.py:485-502` else 分支 `set_stale(False)`；`:520` 追加句受 `has_plot_result` 保护）；`test_stage15d_m1_5_scene_flow.py:310-319` 断言首败后 `source_image is None`、复制禁用、状态句不含保留句。
10. **五路复制全部走 MainWindow → prepare_copy_candidate → ClipboardService** — **PASS**。唯一 `_handle_copy_requested`（`main_window.py:372-414`）；fresh/重复/rendering/failed-current/stale 五种反馈文案（`:402-413`）由 `test_stage15d_m1_5_scene_flow.py:428-487` 与既有 `tests/ui/test_m1_scene_flow.py:385-422`、`:540-560` 共同覆盖；failed-current 同 revision 场景（`result_is_stale is False` 且 `last_error_notice is not None`）明确反馈"已复制上一张成功图；本次生成失败"。
11. **复制对象只能是最近一次 GUI 正式接纳的成功图片** — **PASS**。`CopyCandidate` 只由 `last_successful_result` 构造（`app_controller.py:143-165`，零 diff）；GUI 不从 QPixmap/QImage 反取。
12. **PlotPreview 图片/类型/规范化表达式同寿命、原子替换；占位与清除同步清除摘要** — **PASS**。`plot_preview.py:99-152`：`set_result` 先验证 plot_type/normalized_input 非空再调用 `_set_image`（无效输入在变更任何状态前抛 `ValueError`，测试 `tests/ui/test_plot_preview.py:141-163` 证明原子性）；`set_image` 路径显式清空摘要；`_show_empty_state`（`:206-218`）同步清三者；旧 `set_png_bytes` 兼容分支与摘要生命周期一致。
13. **预览缩放继续从 retained source image 使用 KeepAspectRatio** — **PASS**。`plot_preview.py:219-235` `_refresh_pixmap` 从 `_source_image`（保留源图）`scaled(..., KeepAspectRatio, SmoothTransformation)`；本候选 diff 对该函数零改动（grep 实测 0 命中）。
14. **M1 显函数输入、生成、预览、复制、失败恢复和窗口行为不回归** — **PASS**。既有 `test_formal_production_chain_accepts_declared_m1_formulas`（仅新增 aspect 断言，未删旧断言）、`test_formal_failures_preserve_input_previous_preview_and_copy_state` 等全部保留并通过；全量 2571 绿（§7）。
15. **不修改 AppController、executor、Actor、公共结果协议、ErrorCode、warning code** — **PASS**。§4 零 diff 清单实测。
16. **不接回根目录旧版 main_window、plot_engine 或其他旁路** — **PASS**。见 §5 第 9 项。
17. **新纵向测试使用正式 bootstrap/Controller/Actor/SceneRenderExecutor 链；无 fake executor** — **PASS**。`production_runtime` fixture（`test_stage15d_m1_5_scene_flow.py:90-105`）经 `bootstrap.create_application_runtime` 建立正式对象图并断言 `type(runtime.executor).__name__ == "SceneRenderExecutor"`、`runtime.actor._worker._executor is runtime.executor`、`controller._render_submitter is actor`、`window.controller is controller`（`:219-222`）；`tests/ui/test_m1_scene_flow.py` 的 `_RecordingSceneExecutor`（`:569-588`）是委托真实 `SceneRenderExecutor.execute` 的观测 wrapper，非替代实现；单元级用例把手工构造的 `PlotSceneResult` 直接交给 `window.handle_render_result`，这是 GUI 边界合法注入点，production 纵向证据由上述真实链用例独立承担。

## 7. 独立运行命令与真实结果

全部命令为 Git Bash 适配形式 `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. uv run --locked pytest -q -p no:cacheprovider …`（等价于授权指令的 PowerShell 形式；`tests/conftest.py` autouse 设置 offscreen）。每次运行输出一条 `VIRTUAL_ENV=C:\ProgramData\anaconda3` 与 `.venv` 不匹配的**信息性提示**（uv 仍使用 `.venv`，不影响结果）。本轮**未发生任何沙箱权限失败**，所有命令一次通过、无重试。

| 门 | 文件集 | 本窗口真实结果 | completion report 自报 |
|---|---|---|---|
| D2 两纵向文件 | `tests/ui/test_m1_scene_flow.py tests/ui/test_stage15d_m1_5_scene_flow.py` | **27 passed**，0 failed/0 errors/0 skipped，4.99s | 27 passed（§9.4） |
| 四文件 GUI 门 | `test_plot_preview.py test_main_window.py test_m1_scene_flow.py test_stage15d_m1_5_scene_flow.py` | **72 passed**，0 failed/0 errors/0 skipped，19.13s | —（未单独自报总数） |
| 完整十文件定向门 | `test_app_controller.py test_main_window.py test_m1_scene_flow.py test_plot_preview.py test_stage15d_m1_5_scene_flow.py test_clipboard_service.py test_bootstrap.py test_render_actor.py test_stage15c_production_chain.py test_stage13_public_api.py` | **157 passed**，0 failed/0 errors/0 skipped，21.38s | **157 passed**（§10）——精确一致 |
| 全量 | 全仓库 | **2571 passed**，0 failed/0 errors/0 skipped，80.35s | **2571 passed**（§10）——精确一致 |
| `git diff --check` | — | exit 0，无 whitespace error | 通过——一致 |

completion report 记录的历史过程失败（D1 全量首发 1 个 benchmark 硬编码失败 + 15-C shutdown 用例批次性超时级联；D2 四文件门两次含 Actor 10s guard 超时）均与本次审核的最终绿色不矛盾：报告如实登记了首发失败、根因与修正路径，未隐藏；本轮独立复跑中 Actor guard 未再超时。

## 8. Findings

无 P0、无 P1。未发现安全/数据破坏/冻结契约违反/production 越界/错误成功/旧图被覆盖/线程资源泄漏/证据造假。

**P2-1（证据链缺口，流程性）："15-D1 已通过独立复核和总架构师接受"在仓库内无任何书面审核证据。**
位置：`docs/audits/stage-15d-completion-report.md:5`、`:149`、`:161`；`docs/architecture.md:5`（状态行）、`:435`（§7.13 末句，标题 `:431` 亦标"已接受"）；`docs/supported-formulas.md:4`（状态行）、`:1020`（§"Stage 15C 已验收 production 组合与 Stage 15-D1 已接受边界"）。章程 §7 第 6 步要求每子步"接受真正独立的只读审核**并写入本步 review notes**"，§17 要求 notes 只能记录真实独立审核。本窗口实测 `docs/audits/` 中不存在 D1 专属（或涵盖 D1 的先期）独立审核 notes；15-0/15A/15B/15C 均有 notes 而 15D 在本次审核前一份都没有。该状态句在本次审核开始时**不可由仓库证据证实**，且 D2 的开始门（completion report §7）以此为前提。处置：按本审核授权指令，本 notes 构成 D1+D2 的**累积补审核**——D1 全部九项契约经本窗口独立核验为 PASS（§5），技术缺口已由本文件补上；但"此前已发生独立复核与总架构师接受"这一历史事实仍未经证实，需总架构师明确二选一：(a) 追认仓库外确曾发生 D1 独立复核与接受，并接受本累积补审核为 D1 的入库 review notes；(b) 认定该状态句为失实登记，以本 notes 作为 D1 的首次独立复核记录。在该裁定作出前，上述六处"已通过独立复核和总架构师接受"语句不应被下游（15-D3、15E 及以后）当作已成立事实引用。此外章程 §7 还要求"单独写入本步 completion report"，D1+D2 共用单一 `stage-15d-completion-report.md` 而非两份，属可接受的累积式偏离，一并登记。

**P3-1（流程证据）：benchmark 文件的一次性 allowlist 扩展授权仅记录于 completion report。**
`tests/benchmarks/test_m1_benchmark_protocol.py` 不在章程 §13.2 冻结 15D allowlist 内；completion report §2/§4.6 记录总架构师一次性扩展授权。授权事实只存在于被审核方自己的报告中，无章程修订或 decisions 记录佐证。缓解因素：本次审核授权指令的 D1 累积文件清单明确包含该文件（事后追认效力），且拆分本身诚实（§5 第 8 项 PASS：冻结协议行作为只读事实保留、当前 UI 事实独立快照、协议/工具/结果/hash 零修改）。登记为流程证据观察，不需代码动作。

**P3-2（未到期义务）：`docs/manual-test-checklist-m1.5.md` 尚未创建。**
章程 §13.2/§13.4 与 PRD 矩阵要求 15D 创建人工清单并登记"未执行"。当前文件不存在（`docs/` 实测）。因 Stage 15-D 未完成、15-D3 未开始，这不构成 D1/D2 违规，但它是 15-D 出口门的未完成义务，15-D3（或 15-D 收口）必须补齐且不得预填造结果。

**P3-3（文档措辞）：completion report 对 D2 Controller 只读的理由陈述与章程字面不一致。**
`stage-15d-completion-report.md:163` 称"裁定未明确授权修改 `app_controller.py`，因此 Controller 与其测试在 D2 保持只读"；章程 §13.2 的 15D allowlist 字面上**包含** `math_drawing_assistant/app_controller.py` 与 `tests/test_app_controller.py`。实际方向是保守的（production 零修改，且 15-D1 已证明无需修改），无实质越权或失权，仅理由表述不准确。另报告 §2 表述"当前实际写入严格限于其中八个文件"对应 D1 时点，D2 后合计 13 个文件，累积口径下自洽。

**P3-4（测试可读性观察，非缺陷）：单元级 GUI 状态机用例直接构造 `PlotSceneResult` 注入 `window.handle_render_result`。**
`tests/ui/test_stage15d_m1_5_scene_flow.py:134-163`、`:352-487`。这是 GUI 边界的合法注入点且 production 纵向证据由同文件 `production_runtime` 三用例与 `test_m1_scene_flow.py` 真实链承担；但若未来有人单独引用这些用例作为"production 链证据"会失真，登记以防误引。

## 9. 对 completion report 的核对结论

- 基线/HEAD/origin/master、开始 status、`git diff --check`、allowlist 逐文件、production 零修改清单、benchmark 拆分方式、F-2 文案登记（`scene_executor.py:650` 实测为"当前阶段只支持一个手动输入的绘图项。"，与 15-B review F-2 记录一致）、定向/全量计数（157/2571 精确一致）、Actor 超时首发失败的诚实登记、未创建 review notes、未 commit/push、未进入 15-D3/15-E、未关闭 P0-07、未创建 checkpoint——除 §8 P2-1 所述"D1 已接受"状态句外，**全部与本窗口实测一致**。
- 文档未宣称 D2、Stage 15-D、M1.5 或核心 MVP 完成；architecture/support 两文档候选状态行与章节均写明"15-D2 candidate、15-D3 未开始、Stage 15-D 未完成"。

## 10. 最终裁定

**APPROVE**

- 实际 diff 严格限于授权的 D1+D2 累积 13 文件，无越界；production 唯一链文件（Controller/Actor/bootstrap/executor/resolver/Builder/samplers/renderer/models/ClipboardService/Stage 13 哨兵/15-C 测试）全部零修改；
- D1 九项契约全部 PASS（三态 UI exact 映射、默认 DEFAULT、一次 revision、一次快照、无损适配、分类型 DEFAULT 解析、显式与 manual 优先、benchmark 诚实拆分、无旁路）；
- D2 十七项契约全部 PASS（Controller-first 单入口、ACCEPTED_SUCCESS 唯一替换权、旧图保护、双门独占、六类型一套映射、持久 warning 全子契约、no-visible 专属句、失败保留句、无旧图不伪造、五路复制闭环、复制对象唯一、摘要同寿命原子、KeepAspectRatio 不变、M1 无回归、公共协议未动、无根目录旁路、真实链纵向证据）；
- 测试真实性：无删除用例、无实质放宽断言（既有文案断言随批准的产品句演进且旧路径另有覆盖）、无 skip/xfail/固定 sleep、monkeypatch 仅作观测 wrapper、Actor 超时首发失败被诚实记录；
- 四组独立验证全绿且定向 157/全量 2571 与自报精确一致；`git diff --check` 通过；
- P2-1 证据链缺口按授权指令以本累积补审核处置，需总架构师对 D1 历史状态句作出 (a)/(b) 裁定；P3-1..P3-4 为非阻塞观察。

**本 APPROVE 不代表 Stage 15-D 完成，不授权进入 15-D3 或 Stage 15-E，不关闭 P0-07，不创建 M1.5 checkpoint，不更新核心 MVP 状态。** `docs/manual-test-checklist-m1.5.md` 仍是 15-D 出口前的未完成义务（P3-2）。

当前停止，等待总架构师裁定。

## 11. 最终 Git 状态

`## master...origin/master`；11 个 `M` + `?? docs/audits/stage-15d-completion-report.md` + `?? tests/ui/test_stage15d_m1_5_scene_flow.py` + `?? docs/audits/stage-15d-independent-review-notes.md`（本文件，唯一新增写入）。HEAD 保持 `3c8984176f77936daf197183b3b0434638b54b21` 未变。`git diff --check` exit 0。

---

# Stage 15-D3 与 Stage 15-D 累积出口审核

日期：2026-08-22（Asia/Shanghai）
审核者：独立只读审核窗口（Claude Code 会话，模型 glm-5.3；非 Stage 15-D 主实施 Codex，亦非 D1+D2 累积补审核窗口）
审核对象：工作树中 Stage 15-D3 增量 + D1/D2/D3 累积候选（12 个 tracked modified + 4 个 untracked，共 16 个文件）
依据：本审核授权指令、`docs/stage-15-execution-charter.md` §1/§3/§5/§7/§9/§13/§17、`docs/decisions.md` D-002/D-003/D-004/D-017、本文件前部 D1+D2 累积审核、`docs/audits/stage-15c-completion-report.md`、`docs/audits/stage-15c-independent-review-notes.md`、`docs/audits/stage-15d-completion-report.md`（§0–§16，仅作被核验对象）、`数学绘图助手 PRD.md` §6.2/§6.4/§6.6–§6.8/§12/§14/§15/§20.1/§20.4

## D3.1 审核基线与既有内容保全声明

本窗口开始时逐条实测：

- `git rev-parse HEAD` → `3c8984176f77936daf197183b3b0434638b54b21`；`git rev-parse origin/master` → 同值。与 D1+D2 审核基线、Stage 15-C 收口基线**精确相等**，无 commit/push。
- `git status --short --branch --untracked-files=all` → `## master...origin/master` + 12 个 `M` + 4 个 `??`（`docs/audits/stage-15d-completion-report.md`、`docs/audits/stage-15d-independent-review-notes.md`、`docs/manual-test-checklist-m1.5.md`、`tests/ui/test_stage15d_m1_5_scene_flow.py`）。与授权指令预期基线**逐项相等**，无候选外修改。
- `git diff --check` → exit 0（仅 LF→CRLF 信息提示）；`git diff --stat` → 12 files changed, 784 insertions(+), 53 deletions(-)。
- 本文件（D1+D2 审核 notes）开始状态实测：**SHA-256 `d9a36e87773f2011deae15f2340bad98763b7dc07a58fc20d1fdd00e36558a73`，148 行**。本窗口对前 148 行**未做任何重写、删除、整理或润色**；本节以下内容为纯追加。审核完成后将复核前缀不变。
- 仓库存在 `.codegraph/`；已按约定先经 CodeGraph 定位（`MainWindow.handle_render_result`/`_build_layout`/`_sync_controller_state`、`PlotPreview.set_result`/`_set_image`/`_refresh_pixmap`/`_show_empty_state`、`StatusPanel.set_warning_messages`、`AppController.handle_render_result`/`prepare_copy_candidate`/`create_m1_render_request`、`bootstrap.create_application_runtime`、`resolve_single_item_viewport`→`_resolved_aspect` 调用拓扑），随后逐 hunk 读取全部候选 diff 与指定材料。

## D3.2 D3 八个实际写入文件核验

D1+D2 接受时点的权威终态（本文件 §11）为 11 个 tracked `M` + 3 个 untracked（含本 notes）。当前 12 `M` + 4 untracked 相对该终态的增量**恰好**为：新增 tracked 修改 `数学绘图助手_Codex协助开发步骤清单_v0.3.md`、新增 untracked `docs/manual-test-checklist-m1.5.md`，另有 6 个文件在 D1/D2 基础上继续写入。合计 8 个，与 completion report §13 自报的 D3 八文件清单**逐项相等、无多余**：

| 文件 | D3 增量核验方式 |
|---|---|
| `tests/ui/test_plot_preview.py` | diff 仅新增 `test_repeated_resize_cycles_preserve_source_and_scale_only_from_it`（:85-136），无 `-def` |
| `tests/ui/test_main_window.py` | diff 仅新增 `test_minimum_supported_window_keeps_actions_reachable_and_text_wrapped`（:273-335）；`test_scrollable_content_and_fixed_action_area_have_separate_ownership`（:214-239）与 `test_fixed_actions_remain_visible_when_window_is_short`（:242-270）经 hunk 锚点核实为 HEAD 既有测试，非 D3 新写 |
| `tests/ui/test_stage15d_m1_5_scene_flow.py` | 503→636 行，+133 行恰为三个新测试（:225-266、:269-288、:291-355）；D1+D2 已审核内容的全部引用行号按 +133 偏移精确吻合（旧 :352→现 :485、旧 :428→现 :561、旧 :490→现 :623、旧 :325→现 :458、旧 :310→现 :443、旧 :278-291→现 :416-419、`:90-105`/`:134-163`/`:195-222` 不变），证明 D2 断言零删除、零放宽 |
| `docs/manual-test-checklist-m1.5.md` | 新建 169 行，见 D3.6 |
| `docs/architecture.md` | 新增 §7.15 + 状态行更新；§7.13/§7.14 主体为 D1/D2 已审核内容加时间线修正 |
| `docs/supported-formulas.md` | 新增"Stage 15-D3 响应式/缩放证据与人工清单候选"节 + 状态行更新 |
| `数学绘图助手_Codex协助开发步骤清单_v0.3.md` | 仅 Stage 15 状态行一处替换（D1/D2 期间零修改，本文件首次进入 15D 候选） |
| `docs/audits/stage-15d-completion-report.md` | 新增 §0 时间线修正与 §12–§16 D3 记录 |

`tests/ui/test_m1_scene_flow.py` 的 diff 逐 hunk 归属 D1（aspect revision/snapshot/resolver 矩阵三测试）与 D2（文案观测点、`set_result`、`ResolvedAspect.AUTO` 断言），**无 D3 增量**——与 completion report §13 自报一致。

## D3.3 D3 production 零增量核验

对 `main_window.py`、`plot_preview.py`、`status_panel.py` 三个 production 文件的当前累计 diff 逐 hunk 审阅：

- `plot_preview.py`：diff 仅含 D2 已审核的摘要生命周期变更（`_summary_label` 创建、`set_result`、`_set_image` 拆分、三个访问器、`_show_empty_state` 清摘要）。`_refresh_pixmap`（:218-237）、`resizeEvent`（:199-204）、`_stale_label.setWordWrap(True)`（:53 上下文）**均不在 diff 中**，为 HEAD 既有代码。
- `main_window.py`：diff 仅含 D2 已审核的 `_PLOT_TYPE_LABELS`/`_WARNING_MESSAGES`、复制文案、accepted 分支 `set_result`、`_sync_controller_state` 分支、`_failure_message`。`_build_layout` 的 `QScrollArea` + 兄弟底部操作区（:192-243）与 `setMinimumSize(640, 480)`（:121）**不在 diff 中**，为 HEAD 既有代码。
- `status_panel.py`：diff 仅含 D2 已审核的 `_warning_label` + QVBoxLayout 拆分 + 三个 warning 方法；`_text_label.setWordWrap(True)` 为既有上下文。
- `viewport_panel.py`：diff 仅含 D1 已审核三态。

结论：D3 对三个 GUI production 文件的增量为**零**，"现有实现已满足固定底部布局、source-image 缩放、KeepAspectRatio 与 word-wrap，只补测试与文档"的自报属实。已接受 D1/D2 的累计 production diff 未被 D3 触碰；Controller、Actor、bootstrap、executor、resolver、models、ClipboardService、benchmark 协议/工具/结果/hash（`git diff --name-only -- docs/benchmarks/ benchmarks/` 空输出实测）、根目录旧入口、Stage 13 哨兵与 15-C 测试全部保持零 diff。

## D3.4 响应式与反复缩放证据裁定

1. **反复缩放**：`test_plot_preview.py:85-136` 三轮 × 五尺寸（含 360×620 竖窄、900×260 横宽、回基线）循环，逐步断言 retained `source_image` 尺寸不变**且内容相等**（`retained == original`）、displayed pixmap 不超过 label contentsRect、宽高比误差用叉积 `|w·H − h·W| ≤ max(W,H)` 界定（对 3×2 源即 ≤3，恰为整数像素舍入量级，远紧于旧用例 0.05 容差）、相同窗口尺寸重复得到相同 pixmap 尺寸（`set(baseline_sizes)` 单元素）。`_refresh_pixmap` 源级哨兵（含 `self._source_image`、禁 `_image_label.pixmap`、exact `Qt.AspectRatioMode.KeepAspectRatio`）为**补充性结构哨兵**——运行时证据（真实 pixmap 尺寸/比例逐轮断言）独立存在，未以源码搜索替代运行时验证。**裁定：证据真实、未过度宣称。**
2. **最小支持窗口**：`test_main_window.py:273-335` 使用真实 `window.minimumSize()`（640×480），断言窗口实际收窄到 minimum、滚动区 `geometry().bottom() < 底部区 top()`（兄弟不覆盖）、滚动条有范围、三按钮 `isVisibleTo(window)` 且含于底部区 rect 且两两不相交、五个长文本控件 wordWrap 开启、初始无图占位正确。另有 958×500 短窗口与滚动/底部 ownership 用例（HEAD 既有，本轮继续通过）。不依赖桌面分辨率，offscreen 下为真实 Qt 布局几何，非字符串搜索。**裁定：有效。**
3. **状态覆盖**：D3 新增无旧图 rendering（占位仍在、复制禁用、状态"正在生成图像…"）；有旧图 rendering（D2 既有"正在生成图像，当前仍显示上一张成功图片。"+复制可用）；accepted success/warning success/stale/current failure/`no_visible_curve`/obsolete 与 fresh/repeated/stale/rendering/failed-current copy 的 D1/D2 覆盖全部保留（D3.2 行号偏移法核验零删除）。**裁定：完整。**
4. **圆不变形两层组合**：`test_stage15d_m1_5_scene_flow.py:225-266` 第一层经真实 bootstrap/Controller/Actor/`SceneRenderExecutor` 渲染 `x^2+y^2=4`，断言 production `delivered.resolved_viewport.aspect is ResolvedAspect.EQUAL`（resolver `_resolved_aspect`（`viewport_resolver.py:215-227`，零 diff）圆类 DEFAULT→EQUAL 的真实链证据）；第二层对**该真实渲染图**做三轮最小/宽窗口循环，source 保留、叉积舍入界、同尺寸确定性。GUI 未重算圆或 aspect。`test_plot_preview.py` 中 3×2 PNG 标注"圆"仅用于 resize 机制的摘要入参，completion report 未把它当作圆几何证据引用。**裁定：符合"两层组合而非 GUI 重做数学"，未接受任何 3×2 PNG 冒充圆几何的论证。**
5. **测试真实性**：四个 GUI 测试文件 grep `skip|xfail|time.sleep|sleep(` 零命中；无固定 sleep（`_spin_until` 为 1ms 轮询 + guard）；未延长 Actor guard（workers 测试零 diff）；无 fake executor 冒充 production 纵向证据（`production_runtime` 经 `bootstrap.create_application_runtime` 断言 exact 对象图）；Qt 对象与 Actor teardown（close/deleteLater/processEvents、`shutdown(5_000)` 断言）可靠。

## D3.5 人工验收清单审核

`docs/manual-test-checklist-m1.5.md`（169 行）逐节核验：

- 状态明确为"**仅建立清单；全部项目未执行 / 留待 Stage 15-G**"；全文 40+ 个状态格**全部**为"未执行 / 留待 Stage 15-G"，无任何 PASS、设备通过、DPI 结果或目标软件兼容结论（grep 无命中）。
- 覆盖核对：宽/最小/窄窗口与反复缩放（§4）；Windows 100/125/150/175/200%（§4 五档齐）；logical DPI、DPR、多显示器同/异缩放（§4）；六类图形+规范化表达式+抛物线方向补充（§5）；DEFAULT/AUTO/EQUAL/manual/往返/三档可见性（§6）；五类 warning code 中文句+复制反馈隔离（§7）；无图初始、无旧图 rendering、有旧图 rendering、accepted、warning success、`no_visible_curve`、首败、成功后失败、stale、obsolete、取消、连续提交、错误恢复（§8）；fresh/repeated/stale/rendering/failed-current/无图 copy + 画图/PPT/Word/WPS/希沃粘贴矩阵（§9）；输入保留、清空、Enter/Space、Tab、焦点、非颜色状态、触控、高 DPI 文字、辅助信息（§10）；M1 回归、Unicode、断网启动、断网 OCR 降级、空闲/渲染中/失败后关闭、重复启停（§11）；执行人、环境、证据路径、最终结论与签名栏（§3、§12）。**授权清单要求的覆盖项全部在册。**
- §1 明确区分 D3 自动化证据、开发者基本观察与 Stage 15-G 正式人工验收，且声明自动化不得替代人工项目；§12 声明在 15-G 真实执行前不得用于宣称 Stage 15-D/15/M1.5/P0-07/checkpoint/核心 MVP 完成。清单未提前关闭 15-G、P0-07 或 M1.5 checkpoint。

## D3.6 P2-1 时间线与文档一致性

- completion report §0 按分支 (b) 如实登记五点时间线（D1 无可验证审核记录 → D2 因流程理解错误先行实施 → 本 notes 成为首次累积审核 → 总架构师其后接受、不回退代码 → benchmark 一次性扩展同批追认）；§6/§7 内嵌的旧叙述已被 §0 明确取代并加"当时没有可验证的 D1 独立审核记录"修正句；未再声称"D2 开始前 D1 已完成独立审核"。
- architecture.md 状态行/§7.13、supported-formulas.md 状态行/"Stage 15C 已验收 production 组合与 Stage 15-D1/D2 累积接受边界"节、步骤清单 Stage 15 状态行四处的状态口径**互相一致**：D1/D2 已接受、D3 candidate、Stage 15-D 尚未正式完成、Stage 15-E 未开始；benchmark 追认均已登记。
- 过度宣称 grep（"Stage 15 已完成/M1.5 完成/核心 MVP 完成/P0-07 已关闭/正式性能完成/人工验收通过/Stage 15-G 已"）在五份候选文档中仅命中三处**否定式免责声明**；`docs/audits/` 无任何 15e/15f/15g/final-acceptance 文件被提前创建。
- 冻结 benchmark 行实测仍在 `docs/benchmarks/m1-performance-v1.md:75`（`| 比例 | auto | … |`，带反引号）；协议/工具/结果/hash 零 diff。
- 未跟踪文件补充检查（`git diff --check` 不覆盖它们）：四文件 UTF-8 解码全部有效、无 BOM、以换行结尾；completion report 与人工清单第 3–4 行的双尾随空格为 Markdown 硬换行语法（有意为之），测试文件与本 notes 无尾随空白。

## D3.7 跨层不变量与 M1 回归复核

D3 production 零修改，累计链复核：`math_drawing_assistant/ui/` 全树 grep `matplotlib|engine|parser|sampler|renderer|numpy|sympy` 零命中（无 UI→数学/渲染旁路、无第二渲染入口）；`request_id/scene_revision` 双门只在 `app_controller.py:316-360`（零 diff），GUI 不复制判断；只有 `ACCEPTED_SUCCESS` 替换图片/类型/规范化表达式/warning（`main_window.py:436-471`），failure/cancelled/stale/obsolete 不替换（真实链测试 + 单元注入测试双重覆盖）；warning 不提升为失败、不禁用复制；`no_visible_curve` 保持 typed failure（真实链断言 `ErrorCode.NO_VISIBLE_CURVE`）；复制只经 `AppController.prepare_copy_candidate → ClipboardService`（candidate 只从 `last_successful_result.png_bytes` 构造，不从 QPixmap/QImage 反取）；Matplotlib/Figure 仍在 RenderActor 专属线程（15-C 探针测试全量复验通过）；M1 与 M1.5 共用同一 GUI 状态机（单一 `ACCEPTED_SUCCESS`/`set_result` 入口哨兵 + 无按 `ConcretePlotType` 分支）；根目录旧入口未接回（fresh-subprocess 用例 + 包内 import grep 零命中）；Stage 15-C 两项 P3 观察所在文件零 diff、原样保留；M1 显函数回归（含 `y=x`/`x=y`/`sin(x)`/`1/x`/`sqrt(x)` 链）在全量 2576 中通过。

## D3.8 独立运行命令与真实结果

命令为授权指令 PowerShell 形式的 Git Bash 等价（`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. uv run --locked pytest -q -p no:cacheprovider …`；`tests/conftest.py` autouse offscreen）。每次运行输出一条 `VIRTUAL_ENV` 不匹配的**信息性提示**（uv 仍用 `.venv`）。**本轮未发生任何沙箱/uv cache 权限失败，三门一次通过、零失败、零重试**：

| 门 | 本窗口真实结果 | completion report 自报（§15） |
|---|---|---|
| D3 受影响 GUI 门（test_plot_preview + test_main_window + test_stage15d_m1_5_scene_flow） | **57 passed**，13.15s | 57 passed，12.68s——计数精确一致 |
| 十文件完整定向门 | **162 passed**，23.26s | 162 passed，23.78s——精确一致 |
| 全量 | **2576 passed**，66.86s | 2576 passed，69.87s——精确一致 |
| `git diff --check` | exit 0，无 whitespace error | 通过——一致 |

耗时差异为机器负载，计数全部精确相等。

## D3.9 Findings

无 P0、无 P1、无 P2。未发现安全/数据破坏/冻结契约违反/production 越界/错误成功/旧图被覆盖/线程资源泄漏/证据造假/人工清单预填。

- **P3-1（登记性，前次 notes 引用精度）**：本文件前部 D1+D2 审核对 `plot_preview.py` 的行号引用（":206-218"/":219-235"）与当前实际（:206-216/:218-237）有 1–2 行出入。经本窗口逐 hunk 归属（D3.3）证实该文件累计 diff 只含 D2 变更、`_refresh_pixmap` 根本不在 diff 中，此为前次 notes 的引用取整偏差，**不指示任何 D3 production 修改**。无需动作。
- **P3-2（测试可读性，延续既有登记）**：`test_stage15d_m1_5_scene_flow.py:275` 的无旧图 rendering 用例直接调用 `window._sync_controller_state()` 驱动显示同步。这是 D1+D2 审核 P3-4 已登记的"GUI 边界合法注入点"模式的延续：状态本身来自真实 `AppController.create_m1_render_request` 后的 RENDERING 相位，且同文件 `production_runtime` 三用例独立承担 production 纵向证据。登记以防未来被单独误引为 production 链证据。
- **P3-3（流程证据，非缺陷）**：三个候选 untracked 文件不受 `git diff --check` 覆盖；本窗口已按授权指令逐项补查（UTF-8/BOM/尾随空白/末行换行，见 D3.6），唯一尾随空白为两处有意的 Markdown 硬换行。后续子步若把此类文件纳入 tracked diff 前应保持同等检查习惯。

## D3.10 最终裁定

**APPROVE**

- D3 实际增量严格限于自报八文件；三个 GUI production 文件、`tests/ui/test_m1_scene_flow.py` 及全部只读依赖相对 D1/D2 接受态零增量；
- 反复缩放、最小支持窗口、状态覆盖与圆不变形两层组合证据真实有效，未以标签冒充几何、未以源码搜索替代运行时、未把 offscreen 自动化冒充 DPI 人工验收、未把 15-G 清单当作已执行；
- 人工清单覆盖完整且全部"未执行 / 留待 Stage 15-G"，无预填；
- P2-1 分支 (b) 时间线与 benchmark 追认在 completion report、architecture、supported-formulas、步骤清单中登记一致；
- 跨层不变量与 M1 回归无损；三门独立复跑 57/162/2576 全绿且与自报精确一致；`git diff --check` 通过；
- Stage 15-D 出口条件（章程 §13.4：自动化证明 + 人工清单已建立且未执行项明确）在自动化与文档层面满足。

**边界声明（强制）**：本 APPROVE 不代表 Stage 15-D 正式完成——Stage 15-D 须经总架构师最终接受后才正式完成。Stage 15 尚未完成；Stage 15-E 未开始；Stage 15-G 人工验收尚未执行；P0-07 未关闭；M1.5 checkpoint 与核心 MVP 均未完成。本窗口未修改任何候选实现/测试/文档，未 commit/push，未执行或伪造人工验收，未创建 checkpoint。

当前停止，等待总架构师最终裁定。

## D3.11 最终 Git 状态

`## master...origin/master`；12 个 `M` + 4 个 `??`（`docs/audits/stage-15d-completion-report.md`、`docs/audits/stage-15d-independent-review-notes.md`（本文件，本节为唯一追加写入，前 148 行 D1+D2 内容保持原样）、`docs/manual-test-checklist-m1.5.md`、`tests/ui/test_stage15d_m1_5_scene_flow.py`）。HEAD 与 `origin/master` 均保持 `3c8984176f77936daf197183b3b0434638b54b21` 未变。`git diff --check` exit 0；`git diff --stat` 12 files changed, 784 insertions(+), 53 deletions(-)。
