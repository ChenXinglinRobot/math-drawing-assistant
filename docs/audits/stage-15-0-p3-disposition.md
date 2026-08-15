# Stage 15-0：Stage 14E P3 原始证据与逐项处置

日期：2026-08-15（Asia/Shanghai）<br>
当前核验基线：`master @ 9b4dc91b322e04ea5764ea6836dcfc8c68308ec5`<br>
状态：Stage 15-0 裁定输入；P3-1 至 P3-7 尚未实施，P3-8 已在 Stage 14 收口中解决

## 1. 原始来源与真实性

原始报告为项目所有者提供的《Stage 14E 候选变更独立审计报告（只读）》：

- 审计日期：2026-08-15；
- 审计基线：`master @ ec11449fb4a45beec639a6807c96dc9205389b2c`；
- 来源：项目所有者提供的 Claude Code/GLM 独立只读审核原文；
- 原始附件：`C:\Users\Chen Xinglin\.codex\attachments\dac6bffb-dfd2-4dd6-ad4e-c86fbc7aa67e\pasted-text.txt`；
- 实测：126 行、15,413 bytes；
- 实测 SHA-256：`90EF170459886451F1CE0D5811A512D55D70C6FAC2BD7A71D2DDC14BE53CABC0`；
- 仓库内完整归档：`docs/audits/stage-14e-candidate-independent-audit-2026-08-15.md`。

原附件第 41 行开始 P3 表，第 46、50、54、58、62、66、70、74 行分别开始 P3-1 至 P3-8。以下摘要忠实压缩原 finding 的位置、观察、影响和最小修复，但不以外部报告代替当前事实。当前状态均针对 `HEAD 9b4dc91b322e04ea5764ea6836dcfc8c68308ec5` 重新核验。

## 2. 状态语义

- `accepted`：原观察成立，已分配 Stage 15 责任子步和退出证据，但尚未实施完成；
- `already_resolved`：当前 HEAD 已有直接证据证明原观察已解决；
- `superseded`：后续批准契约使原建议不再是正确出口；
- `deferred`：观察成立但经批准延后到 Stage 15 之外；
- `not-applicable`：原观察不适用于当前产品或代码边界。

本表没有把 P3-1 至 P3-7 标记为已实施。它们均为 `accepted`，并在责任子步退出前保持开放。

## 3. 逐项处置

| P3 | 原始位置、观察与证据 | 当前 HEAD 复核 | 裁定 | 责任子步 | 精确允许文件 | 退出证据 | 性能结果失效 | Stage 15 入口 |
|---|---|---|---|---|---|---|---|---|
| P3-1 | 原附件 46–49 行；`tests/engine/test_stage14e_acceptance.py:873-909`（候选基线行号）。静态边界使用可绕过的字符串匹配，contour 扫描集合不是由全生产包 Python 文件派生；`__all__` 内省部分有效。 | 当前 `tests/engine/test_stage14e_acceptance.py:912-961` 仍读取源码并匹配字符串；contour 集合仍为若干指名文件加 workers/UI，未以 AST 对全部生产 Python 文件做 `Import`、`ImportFrom`、`Call` 检查。生产树当前未发现 forbidden 接线，但这不能填补测试机制缺口。 | `accepted` | 15A 实施；15G 复验 | `tests/engine/test_stage15a_production_boundary.py` | 测试从 `math_drawing_assistant` 根以 `Path.rglob("*.py")` 得到文件集合，使用 `ast.parse`/`ast.walk` 检查 forbidden imports/calls、第二入口和 benchmark 反向导入；别名导入用例证明扫描不可被绕过；15G 再运行该测试。`tests/engine/test_stage14e_acceptance.py` 保持只读历史证据。 | 测试加固本身不失效性能；若发现并修复生产边界违规，任何已形成的 15F 结果必须按生产变更规则失效。 | 不阻塞 15-0；阻塞 15A 退出与 15G 最终出口。 |
| P3-2 | 原附件 50–53 行；`tests/engine/test_stage14e_acceptance.py:589-609`。残差 oracle 与生产 helper 同源转写冻结公式并读取同一 coefficients，不能独立发现尺度定义或分类系数的系统性错误。 | 当前 `tests/engine/test_stage14e_acceptance.py:583-610` 仍直接从 `spec.coefficients` 重算同一 primitive normalized residual。竖直双曲线 branch oracle 已补齐，但未消除本 finding 的系数/尺度同源盲区。 | `accepted` | 15E | `tests/acceptance/test_stage15e_independent_geometry_oracle.py`；`tests/data/m1_5_textbook_matrix_v1.json` | 每个受支持具体图形至少有一项由教材矩阵提供的结构性异构 oracle：钉住预期 primitive coefficients，并以几何参数公式独立复算；样例必须通过 production executor，且不调用生产 residual/projector/planner。 | 是。该矩阵是 15F 场景来源；15E 矩阵、oracle 判定或获批场景集合在正式测量后变化，使对应 15F 结果失效。 | 不阻塞 15-0；阻塞 15E 退出，并因此阻塞 15F 启动。 |
| P3-3 | 原附件 54–57 行；`tests/engine/test_stage14e_acceptance.py:419-443`。11 个 geometry Fraction 字段由 receipt snapshot 密封并在运行时比对，但缺逐字段篡改回归。 | `math_drawing_assistant/models/render_plan.py:1036-1097` 仍 snapshot Circle、Ellipse、Hyperbola、Parabola 的 14 个 Fraction 项（原报告按其候选集合称 11 个）；`tests/engine/test_stage14e_acceptance.py:420-443` 的公共 target 未逐项篡改 `fraction_fields`。保护逻辑存在，回归锁仍不完整。 | `accepted` | 15B | `tests/engine/test_stage15b_receipt_hardening.py` | 对当前 `_snapshot_geometry_spec` 的每个 Fraction 字段逐字段原位篡改，`validate_approved_render_plan` 全部拒绝且不补发 receipt；测试从 dataclass/spec 字段建立明确参数表并固定字段数。 | 测试加固本身不失效性能；若测试暴露生产 receipt 缺陷并修改生产契约，已形成的 15F 结果失效。 | 不阻塞 15-0；阻塞 15B 退出。 |
| P3-4 | 原附件 58–61 行；候选 `test_stage14e_acceptance.py:478-487`、`tests/engine/test_render_plan.py:388-395`。scene-spec 级 `item_id` 被 snapshot 密封，但现有测试只篡改 item-plan 级字段。 | 当前 geometry 公共 target 在 `tests/engine/test_stage14e_acceptance.py:479-488` 仍改 `plan.item_plan.item_id`；`tests/engine/test_render_plan.py:397-405` 的显函数 item-plan 参数未含 `item_id`，且两条链都没有篡改 `plan.scene_spec.items[0].item_id`。 | `accepted` | 15B | `tests/engine/test_stage15b_receipt_hardening.py` | 显函数与五种 exact geometry 都分别篡改 scene-spec `item_id` 并被 receipt 校验拒绝；显函数 item-plan `item_id` 也有独立回归。 | 同 P3-3。 | 不阻塞 15-0；阻塞 15B 退出。 |
| P3-5 | 原附件 62–65 行；`tests/engine/test_render_plan.py`。M1 显函数 approval snapshot 的计划侧字段缺完整参数化篡改；geometry 矩阵不能覆盖 explicit snapshot 分支。 | 当前 `tests/engine/test_render_plan.py:361-365` 只单独篡改 `image_width`；既有 item-plan 参数覆盖 sample/batch/segment/liveness，但没有把 `image_height`、`dpi`、`show_legend` 等显函数计划侧 snapshot 字段组成完整矩阵。 | `accepted` | 15B | `tests/engine/test_stage15b_receipt_hardening.py` | 对一个正式显函数 plan 参数化篡改其 explicit approval snapshot 的全部计划侧拷贝点，逐项拒绝、receipt identity 不变；保留旧 M1 错误和采样语义。 | 同 P3-3。 | 不阻塞 15-0；阻塞 15B 退出。 |
| P3-6 | 原附件 66–69 行；`test_stage14c_circle_ellipse.py:925-930` 及 14d1/14d2 同型。oval/hyperbola/parabola 的中间取消测试缺 `SamplingCancelled.item_id` 断言。 | 当前 `tests/engine/test_stage14d1_hyperbola.py:969-981` 因 P2-5 修复已逐点断言 `item_id`；`tests/engine/test_stage14c_circle_ellipse.py:925-930` 和 `tests/engine/test_stage14d2_parabola.py:779-790` 仍只断言类型与 poll 数。整体 finding 尚未解决。 | `accepted`（双曲线子项已随 P2-5 顺带解决） | 15B 实施；15C 真实取消链复验 | `tests/engine/test_stage15b_sampler_identity.py`；`tests/test_stage15c_production_chain.py` | 15B 对 oval、hyperbola、parabola 的全部可达取消点断言 exact `item_id` 且无部分结果；15C 证明 production executor/Actor 传递同一 cancellation token，取消结果不发布为当前成功且不替换旧图。Stage 14 历史测试保持只读。 | 测试加固本身不失效性能；若生产取消/采样代码改变，则已形成的 15F 结果失效。 | 不阻塞 15-0；阻塞 15B，并由 15C 复验后关闭链路风险。 |
| P3-7 | 原附件 70–73 行；`benchmarks/stage14_parameterized_probe.py:571-582`。Stage 14 evidence-only 探针 `main()` 无条件返回 0，Stage 15 脚本化正式测量需要机器可读失败信号。 | 当前 `benchmarks/stage14_parameterized_probe.py:571-582` 仍无条件 `return 0`，与其历史 evidence-only 边界一致；当前无需改写该探针或四文件证据包。 | `accepted` | 15F | `benchmarks/m1_5_performance_v1.py`；`tests/benchmarks/test_m1_5_performance_v1.py`；`docs/benchmarks/m1.5-performance-v1.md` | 新工具对 typed failure、GUI 成功判定失败、非中性取消、协议/场景/hash 不匹配和测量不完整返回非零；同时无条件写出可解析状态，测试覆盖成功/失败退出码。历史 `benchmarks/stage14_parameterized_probe.py` 与 Stage 14 bundle 只读。 | 是。工具、协议、场景集合、成功判定或 hash 变化使 `m1.5-performance-v1` 正式结果失效，必须变更控制后重冻和复测。 | 不阻塞 15-0；阻塞 15F 第一门和正式测量。 |
| P3-8 | 原附件 74–77 行；`docs/benchmarks/stage14-parameterized-prototype-v1.md:54` 曾引用不存在的 `ParameterizedMemoryBudget`。 | 当前该行已写为真实 `ParameterizedRenderMemoryBudget`；生产类型位于 `math_drawing_assistant/models/render_plan.py:533`，公开哨兵位于 `tests/test_stage13_public_api.py:106`。修复包含在当前 HEAD `9b4dc91b322e04ea5764ea6836dcfc8c68308ec5`。 | `already_resolved` | Stage 14 历史闭环；15G 只读复验 | 无 | 对 `docs/benchmarks/stage14-parameterized-prototype-v1.md`、`math_drawing_assistant/models/render_plan.py` 和 `tests/test_stage13_public_api.py` 定向搜索：旧名 `ParameterizedMemoryBudget` 不得出现，真实类名 `ParameterizedRenderMemoryBudget` 必须存在；完整保存旧 finding 的外部原文归档和本处置说明明确排除在旧名禁用搜索范围外。Stage 14 历史文档和证据包不再修改。 | 否。文档类名修正不改变测量或生产行为。 | 不影响 Stage 15 入口；不得重复实施。 |

## 4. P2 与历史边界

外部报告的 P2-1 至 P2-5 和 P3-8 已由后续 Stage 14 收口形成当前 HEAD。15-0 只建立来源链和核对当前事实：

- `联网确认.md:173`、`:184` 已区分 Stage 14 原型与 Stage 15 renderer/正式性能；
- `docs/supported-formulas.md:41` 已区分 Stage 14 viewport/规划/采样与尚未完成的 Stage 15 renderer/应用整合；
- `tests/engine/test_stage14e_acceptance.py:617-639` 已按 transverse axis 核对双曲线 branch 方向；
- `tests/engine/test_stage14d1_hyperbola.py:969-981` 已遍历全部可达取消点并断言 `item_id`；
- `docs/benchmarks/stage14-parameterized-prototype-v1.md:54` 已使用真实类型名。

这些核对不重写 `docs/audits/stage-14-final-acceptance-2026-08-14.md`，不重新生成 `benchmarks/results/20260814T160403Z-stage14-parameterized-prototype-v1/environment.json`、`manifest.json`、`records.jsonl` 或 `summary.json`，也不把 Stage 14 完成扩大为 Stage 15、正式 M1.5 性能或 M1.5 checkpoint 完成。

## 5. 入口裁定

P3 原始证据门已满足。P3-1 至 P3-7 均有可核查来源、当前状态、责任子步、精确文件和退出证据；它们不阻塞 Stage 15-0 文档门完成，但必须按表中责任子步关闭，不能以本处置表冒充实现。P3-8 已解决且不得重复修改。15A 仍须由独立任务显式开始；本文件不授权自动进入 15A。
