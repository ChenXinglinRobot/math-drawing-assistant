# 阶段 14D-1：独立审核与非阻塞观察处置记录

日期：2026-08-14
状态：独立审核与总架构师复核通过；Stage 14D-1 已关闭，可进入 Stage 14D-2

## 目的与边界

本文归档 Stage 14D-1“双曲线参数化采样”的独立只读审核结论，并记录审核报告中的两项非阻塞观察及其处置。本文不修改 Stage 14D-1 的实现、冻结契约或验收条件，不把观察升级为 P0/P1/P2/P3 finding，也不授权提前实施 Stage 14E、Stage 15、geometry renderer、contour 后备链路、多 item 或应用层整合。

Stage 14D-1 的已验收提交保持不变。后续 Stage 14D-2 若不需要修改相关共享代码，不得以“顺手加固”为由调整已关闭的双曲线路径。

## 审核目标与结论

| 项目 | 记录 |
| --- | --- |
| 固定审核基线 | `f53956c3bee72c78d04dacca2b7f958d25488140` |
| 审核目标提交 | `b19fe168936b736ce51b635bace8c9ec2f5a7b23` |
| 提交信息 | `feat(engine): implement Stage 14D-1 hyperbola sampling` |
| 分支 | `master` |
| 审核时工作树 | clean；相对 `origin/master` ahead 1 |
| 变更范围 | 14 个实现、测试和文档文件；未发现 renderer、SceneRenderExecutor、Actor、Controller、UI、contour 或 limits version 越界修改 |
| 独立审核 findings | 未发现 P0/P1/P2/P3 |
| 独立审核结论 | `APPROVE` |
| 总架构师复核 | 通过；Stage 14D-1 退出门关闭，允许进入 Stage 14D-2 |

审核确认双曲线数学与 branch identity、有限可见参数区间、float64 与 `sinh/cosh` 安全边界、资源预算、approval receipt、防篡改、取消语义及阶段边界均满足 Stage 14D-1 要求。P0-06 继续保持打开，等待 Stage 14E 完整验收。

## 独立审核测试记录

以下结果由独立审核者在只读审核中报告：

| 测试范围 | passed | failed | errors | skipped |
| --- | ---: | ---: | ---: | ---: |
| `tests/engine/test_stage14d1_hyperbola.py` | 82 | 0 | 0 | 0 |
| Stage 14B-1 + 14B-2 + 14C + 14D-1 | 309 | 0 | 0 | 0 |
| `tests/engine` | 1555 | 0 | 0 | 0 |
| 完整回归 | 2013 | 0 | 0 | 0 |

完整回归只有 `uv` 关于外部 `VIRTUAL_ENV` 的环境警告；测试计数与实现方报告一致，耗时差异属于机器运行波动，不影响审核结论。

## O-14D-1-01：顶点邻域的保守 fail-closed 假拒绝

**独立审核观察：** `math_drawing_assistant/engine/render_plan_builder.py` 的 `_finite_acosh_root` 使用最近舍入后的 `semi_transverse_float` 作为分母，并以 `ratio <= 1.0` 拒绝。视口边界恰好落在双曲线顶点约 ±1 ULP 的极端情况下，理论上可能把一个原本安全可表示的根保守地拒绝为可恢复的 `NUMERIC_RANGE_UNSUPPORTED`。

**影响判断：** 该输入属于 measure-zero 的病理边界。失败方向为 fail-closed：不会产出错误图形、跨分支误连、NaN、Inf 或崩溃，且 sampler 仍有逐点视口与残差复核。它不影响 Stage 14D-1 已审核的正确性、安全性或资源上界。

**处置：** 接受当前风险，不创建 Stage 14D-1 修复提交，不加入 Stage 14D-2 的默认范围。

**未来触发条件：** 模糊测试或真实输入能够稳定复现；产品要求把顶点 ±1 ULP 邻域纳入强制成功语义；相关根求解器或共享区间规划代码因后续阶段发生实质修改。触发后应创建独立的小型数值边界任务，补充定向测试，并重新审核 error taxonomy、outward enclosure 和 receipt/预算不变量。

**优先级：** 非 finding；已接受观察，未排期，不阻塞。

## O-14D-1-02：坍缩与不可见的错误语义措辞澄清

**独立审核观察：** 审核材料中的一处措辞曾把“float64 坍缩单点”概括为 `NO_VISIBLE_CURVE`；当前实现对不能有限、安全表示的 float64 坍缩返回 `NUMERIC_RANGE_UNSUPPORTED`，只有 exact 判定后的不可见或孤立切点不形成可绘制区间。

**架构核实结论：** 当前代码与 `docs/supported-formulas.md` 的权威分类一致：数学上不可见使用 `NO_VISIBLE_CURVE`，不能有限安全表示使用 `NUMERIC_RANGE_UNSUPPORTED`。这是对审核措辞的澄清，不是实现缺陷，也不是产品文档缺口。

**处置：** 以权威文档和当前代码语义为准；不创建修复任务、不修改错误类型、不增加阶段验收条件。若未来审核或实施提示词引用该边界，应沿用本段分类，避免重新引入措辞歧义。

**优先级：** 非 finding；语义澄清，无待办。

## 最终处置

保留提交 `b19fe168936b736ce51b635bace8c9ec2f5a7b23`，不为 O-14D-1-01 或 O-14D-1-02 创建 Stage 14D-1 修复提交，不改写独立审核的 `APPROVE` 结论。Stage 14D-1 现按已验收状态关闭，Stage 14D-2 可以开始；P0-06、Stage 14E、Stage 15、renderer 与应用整合仍未完成或获准提前进入。
