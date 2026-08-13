# 阶段 14B-2：独立复审与非阻断观察处置记录

日期：2026-08-13  
状态：独立复审通过；P3 观察已核实并记录，不属于阶段 14B-2 的阻塞项或修复要求

## 目的与边界

本文记录阶段 14B-2“一般非退化直线”实现的独立只读复审结论，以及对唯一 P3 观察的后续架构核实。本文不修改《Stage 14 参数化直线与圆锥曲线采样——最终正式实施总纲 v1.0》或阶段 14B-2 的冻结实施要求，不新增验收条件，也不授权进入 14C、Stage 15 或 renderer 整合。

独立复审由外部审核者依据实际提交、源码、测试和 Git 状态完成；后续架构核实只针对 P3 观察检查了对应定义、调用位置和模块边界，没有修改实现，也没有重新运行冻结测试矩阵。

## 审核目标与结论

| 项目 | 记录 |
| --- | --- |
| Stage 14B-2 前基线 | `985ab43845c5c78c301108619228cbe3ffc97536` |
| 审核目标提交 | `254e22230a0cf4e1f7b875ed677b7d92e4baee02` |
| 提交信息 | `feat(engine): implement stage 14b-2 line sampling` |
| 分支 | `master` |
| 审核时工作树 | clean |
| 变更范围 | 冻结要求内的 12 个实现、测试和文档文件；未发现越界修改 |
| 冻结章节 | 16 项全部 PASS |
| 独立复审结论 | `APPROVE` |

审核确认四类圆锥曲线算法、contour、二维网格、斜率式主算法、第二套 viewport/plan/receipt、renderer、SceneRenderExecutor、RenderActor、AppController、UI、Stage 14C/14D/14E 和 Stage 15 均未混入。P0-06 保持打开。

## 独立复审测试记录

以下结果由独立审核者在 `PYTHONDONTWRITEBYTECODE=1`、`PYTHONPATH=.` 和 `uv run --locked pytest -q -p no:cacheprovider` 环境下报告：

| 测试范围 | passed | failed | errors | skipped | pytest warnings |
| --- | ---: | ---: | ---: | ---: | ---: |
| `tests/engine/test_stage14b2_line.py` | 99 | 0 | 0 | 0 | 0 |
| Stage 14B-1 + Stage 14B-2 | 155 | 0 | 0 | 0 | 0 |
| viewport、render plan、samplers、14B-1、14B-2 | 301 | 0 | 0 | 0 | 0 |
| Stage 13 specs/public API、limits、spec builder、numeric executor | 199 | 0 | 0 | 0 | 0 |
| renderer、scene executor、workers | 162 | 0 | 0 | 0 | 0 |
| `tests/engine` | 1401 | 0 | 0 | 0 | 0 |
| 完整回归 | 1859 | 0 | 0 | 0 | 0 |

完整回归相对阶段 14B-2 前的 `1757 passed` 基线增加 102 项测试；`git diff --check` 通过。上述数字是对独立复审报告的留档，不表示后续架构核实重新执行了这些命令。

## H-14B-2-01：归一化直线残差的局部重复实现

**独立复审观察：** `math_drawing_assistant/engine/render_plan_builder.py` 与 `math_drawing_assistant/engine/samplers.py` 各自定义了私有 `_normalized_line_residual`。两处均使用 `Fraction.from_float`，并按冻结公式计算：

```text
numerator = abs(d*x + e*y + f)
scale = abs(d)*max(1,abs(x)) + abs(e)*max(1,abs(y)) + abs(f)
residual = numerator / scale
```

Builder 在批准 `LineSegmentPlan` 前使用该结果执行 `maximum_residual_ulps=16` 的 hard 拒绝；sampler 在执行批准计划时防御性复验 hard 阈值，并根据 `target_residual_ulps=4` 决定是否追加 `SAMPLING_PRECISION_LIMITED`。两处当前公式和阈值语义一致，没有发现正确性偏差。

**架构核实结论：** 重复实现客观存在，但不违反阶段 14B-2 冻结要求。冻结要求明确强制 Builder 与 sampler 共用参数化预算函数，并未要求 residual 必须共用 helper。两次调用分别属于计划批准前检查和 sampler 执行边界的防御性复验，当前行为符合要求。

**为何不修复：** 将 residual 放入 `parameterized_budget.py` 会混淆该模块的内存预算职责；让 Builder 与 sampler 互相导入私有 helper 会引入不必要的跨层耦合；为十行纯计算新建模块则会扩大已冻结步骤的文件和架构范围。当前没有行为错误、测试缺口或验收失败足以证明该重构的必要性。

**未来触发条件：** residual 公式发生变化、两处实现产生漂移、出现第三个正式消费者，或后续阶段建立统一且职责明确的直线几何数值 helper 层时。

**可选后续处置：** 触发条件成立后，应先建立独立的小型重构任务，选择职责明确的私有模块，并用 Builder 与 sampler 的同一组边界向量验证共享语义；不得把该观察直接当作阶段 14B-2 的遗留缺陷。

**优先级：** P3，未排期，不阻塞。

## 最终处置

保留提交 `254e22230a0cf4e1f7b875ed677b7d92e4baee02`，不为 H-14B-2-01 创建修复提交，不改写独立复审的 `APPROVE` 结论。阶段 14B-2 可以按已验收状态保留；P0-06 继续打开，且本文不授权进入 14C、Stage 15 或 renderer/SceneRenderExecutor 整合。
