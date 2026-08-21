# Stage 15-B Completion Report：统一 M1/M1.5 单项 Manual Production Executor

日期：2026-08-21（Asia/Shanghai）
执行者：Stage 15-B 主实施 Codex
规划依据：Stage 15 execution charter、Stage 15-A completion/independent review，以及本阶段获批实施提示词

## 1. 开始基线

- 分支：`master`
- 开始 HEAD：`124ceb215b7b5ba584456fd6c19273697ec0f887`（`feat(stage15a): unify sampled-curve renderer`）
- 开始工作树：干净，无未提交用户修改
- `.codegraph/` 存在；实施前按仓库指令优先用于代码定位和调用关系调查
- Stage 15-A 已独立审核通过；开始事实为 `render_sampled_curve_png` 已是统一 renderer，而 `SceneRenderExecutor` 仍是 explicit-only

## 2. 实际写入文件

最终实际写入路径均属于原 Stage 15-B allowlist，或属于本阶段两次明确获批的一次性最小扩展：

| 文件 | 变更范围 |
|---|---|
| `math_drawing_assistant/engine/scene_executor.py` | 将 executor 收口为唯一的单项/manual M1/M1.5 production 链；加入 exact spec/plan/sampler outcome 校验、统一 renderer 调用、typed failure/cancellation、diagnostics、warnings 和 timings |
| `math_drawing_assistant/engine/__init__.py` | 保持 `engine.__all__` 集合不变；为 scene executor 提供与正式 parameterized sampler 同一函数对象的私有绑定 |
| `math_drawing_assistant/models/results.py` | 新增 `ConcretePlotType`、item/scene result 字段及冻结映射和结果不变量 |
| `math_drawing_assistant/models/diagnostics.py` | 新增 frozen/slots 的 `PlotItemDiagnostics` 与 `PlotSceneDiagnostics` 及构造不变量 |
| `math_drawing_assistant/models/__init__.py` | 仅新增三个冻结的 model public exports |
| `tests/engine/test_scene_executor.py` | 适配统一 executor 私有拓扑，同时保留旧 M1、Actor 脱敏/恢复和取消语义强度 |
| `tests/engine/test_stage15b_unified_executor.py` | 新增六类型、requested-kind、失败、warning、no-visible、cancellation 与 timing 契约测试 |
| `tests/engine/test_stage15b_receipt_hardening.py` | 新增 P3-3/P3-4/P3-5 receipt 篡改矩阵 |
| `tests/engine/test_stage15b_sampler_identity.py` | 新增 exact sampler/outcome identity、fail-closed 与 P3-6 全取消点矩阵 |
| `tests/engine/test_stage15a_production_boundary.py` | 获批最小扩展，详见 §3.1 |
| `tests/test_models.py` | 新结果模型和不变量覆盖 |
| `tests/test_diagnostics.py` | 新 diagnostics 类型和不变量覆盖 |
| `tests/test_stage13_public_api.py` | 钉住 `PlotKind`、`ConcretePlotType`、models/engine exports 和文档版本/状态 |
| `tests/ui/test_m1_scene_flow.py` | 获批一次性最小扩展，详见 §3.2 |
| `docs/architecture.md` | 登记 Stage 15-B 唯一 executor 链和结果契约 |
| `docs/supported-formulas.md` | 版本更新为 `stage-15b-unified-executor-v1` 并登记准确阶段状态 |
| `数学绘图助手_Codex协助开发步骤清单_v0.3.md` | 仅登记 Stage 15-B 候选实施完成、等待独立审核/验收 |
| `docs/audits/stage-15b-completion-report.md` | 本报告 |

未创建或修改 `docs/audits/stage-15b-independent-review-notes.md`。

## 3. Allowlist 扩展及历史断言维护

### 3.1 Stage 15-A production boundary 测试

`tests/engine/test_stage15a_production_boundary.py` 的冻结 caller 事实与 Stage 15-B 必须形成的唯一 production 链直接冲突，因此在实施提示词中获得最小 allowlist 扩展。实际仅：

- 将旧兼容 wrapper `render_explicit_png` 的 production caller 期望改为无调用方；
- 将统一 renderer `render_sampled_curve_png` 的 production caller 期望改为仅 `scene_executor.py`；
- 同步这两个测试的名称/说明。

AST 扫描、alias self-test、renderer singleton、contour/重依赖/反向依赖禁令均未删除或放宽。

### 3.2 UI scene-flow 测试

首次全量运行暴露两个历史测试断言与 Stage 15-B 冻结事实冲突（当时结果为 `2540 passed, 2 failed`）。项目所有者随后明确批准 `tests/ui/test_m1_scene_flow.py` 的一次性最小 allowlist 扩展。实际只有两项维护：

1. `test_real_scene_executor_runs_in_actor_and_preview_updates_on_gui_thread` 原来 monkeypatch `scene_executor.render_explicit_png`。Stage 15-B 后 production executor 不再导入或调用旧 wrapper，唯一 production renderer 是 `render_sampled_curve_png`，旧私有探针因此失效。测试只把保存真实函数和 monkeypatch 目标改为 `render_sampled_curve_png`；renderer/Actor/GUI 线程归属断言全部保留。
2. `test_formal_failures_preserve_input_previous_preview_and_copy_state` 原来把 AUTO `x+y=1` 视为 `UNSUPPORTED_EQUATION`。该输入按 Stage 15-B 冻结 analyzer/requested-kind 契约必须成功分类为 `GENERAL_LINE / LINE_EQUATION`，历史失败断言因此失效。参数仅替换为已有 analyzer 契约覆盖的 `x*y=0 / ROTATED_CONIC_NOT_SUPPORTED`；输入、旧预览、错误显示和复制状态断言全部保留。

没有恢复 `render_explicit_png` 的 production 调用或兼容 alias，也没有把 AUTO `x+y=1` 改回失败。

## 4. 最终 production 链与公共结果契约

唯一链为：

`PlotSceneRequest → request gate → analyze_plot_item → PlotSceneSpec → resolve_single_item_viewport → RenderPlanBuilder.build → exact typed sampler → render_sampled_curve_png → PlotSceneResult`

- `ExplicitFunctionSpec` 只接受 exact `ExplicitRenderItemPlan` 和 exact `SampledExplicitFunction`，并调用 `sample_explicit_function`。
- `LineSpec`、`CircleSpec`、`EllipseSpec`、`HyperbolaSpec`、`ParabolaSpec` 只接受 exact `GeometryRenderItemPlan` 和 exact `SampledParameterizedCurve`，并调用正式 `sample_parameterized_curve` 函数对象。
- spec、plan、sampled union 或 item ID 不一致均 fail-closed；所有成功 sampled outcome 只调用 `render_sampled_curve_png`。
- `ConcretePlotType` 最终六成员：`EXPLICIT_FUNCTION`、`GENERAL_LINE`、`CIRCLE`、`ELLIPSE`、`HYPERBOLA`、`PARABOLA`；与既有 `PlotKind` 使用冻结的一一映射。
- `PlotItemResult` 新字段：`concrete_plot_type: ConcretePlotType | None`、`diagnostics: PlotItemDiagnostics | None`。
- `PlotSceneResult` 新字段：`diagnostics: PlotSceneDiagnostics | None`。
- `PlotItemDiagnostics` 字段：`planned_sample_point_count`、`actual_sampled_point_count`、`sampled_segment_count`、`visible_segment_count`。
- `PlotSceneDiagnostics` 字段：`total_planned_sample_point_count`、`total_actual_sampled_point_count`、`approved_estimated_memory_bytes`、`final_png_byte_count`。
- diagnostics 的正整数、非 bool、planned/actual、segment/visible、PNG 长度和出现阶段不变量均由 frozen/slots 模型和测试钉住。
- timings 的稳定有序阶段为 `request_validation`、`analysis`、`viewport_resolution`、`render_plan`、`sampling`、`rendering`；失败保留已完成前缀，合法取消保持空 timings。
- viewport warning 归 scene，sampling warning 归 item，scene 以稳定首次出现顺序去重；no-visible、stage error item ID 绑定和合法/非法 cancellation 均按冻结契约处理。
- `models.__all__` 只新增 `ConcretePlotType`、`PlotItemDiagnostics`、`PlotSceneDiagnostics`；`engine.__all__` 集合不变。

## 5. 最终验证命令与实际计数

所有命令均在 PowerShell 中以 `PYTHONDONTWRITEBYTECODE=1`、`PYTHONPATH=.`、`uv run --locked pytest -q -p no:cacheprovider` 执行。

1. UI 定向：`tests/ui/test_m1_scene_flow.py` → **17 passed，0 failed，0 errors，0 skipped；5.64s**。
2. Stage 15-B 冻结定向门：`tests/engine/test_scene_executor.py tests/engine/test_stage15b_unified_executor.py tests/engine/test_stage15b_receipt_hardening.py tests/engine/test_stage15b_sampler_identity.py tests/engine/test_render_plan.py tests/test_models.py tests/test_diagnostics.py tests/test_stage13_public_api.py` → **242 passed，0 failed，0 errors，0 skipped；9.51s**。
3. 只读依赖回归门：`tests/engine/test_renderer.py tests/engine/test_stage15a_geometry_renderer.py tests/engine/test_stage15a_production_boundary.py tests/engine/test_samplers.py tests/engine/test_stage14b1_contracts.py tests/engine/test_stage14b2_line.py tests/engine/test_stage14c_circle_ellipse.py tests/engine/test_stage14d1_hyperbola.py tests/engine/test_stage14d2_parabola.py tests/engine/test_stage14e_acceptance.py tests/workers/test_render_actor_agg_probe.py` → **848 passed，0 failed，0 errors，0 skipped；59.69s**。
4. 全量：`uv run --locked pytest -q -p no:cacheprovider` → **2542 passed，0 failed，0 errors，0 skipped；96.21s**。
5. `git diff --check` → **通过（exit 0）**；只有仓库行尾 LF→CRLF 提示，没有 whitespace error。
6. `git status --short --untracked-files=all`、`git diff --name-only`、`git diff --stat` 和 UI 文件精确 diff 已审核；写入路径未越出扩展后的 allowlist。

## 6. 只读依赖与范围声明

以下只读 production/历史依赖均零触碰：`models/state.py`、`models/render_plan.py`、`plot_analyzer.py`、`viewport_resolver.py`、`render_plan_builder.py`、`samplers.py`、`renderer.py`、limits、Actor、Controller、bootstrap、UI production、clipboard，以及 Stage 14 历史测试/结果。Stage 15-A renderer 行为测试、completion report 和独立审核记录也未修改。

没有新增第二 executor、resolver、Builder、sampler、renderer 或 receipt；没有 contour/solve fallback、multi-item、OCR、正式性能、教材证据、checkpoint 或 P0-07 关闭声明。

## 7. 停止声明

Stage 15-B 候选实施、定向测试、只读回归、全量测试、diff check 和 allowlist 审核全部完成。未执行 `git add`、`git commit` 或 `git push`；未进入 Stage 15-C。当前停止并等待真正独立的只读审核与总架构师验收。
