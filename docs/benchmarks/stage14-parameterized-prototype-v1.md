# Stage 14 参数化采样原型探针 v1

协议版本：`stage14-parameterized-prototype-v1`<br>
登记日期：2026-08-15<br>
确定性证据包 UTC：2026-08-14T16:04:03Z<br>
状态：Stage 14 开发机原型证据；不是 Stage 15 或 M1.5 正式性能验收

## 1. 目的与边界

本探针回答 Stage 14 的有限问题：受支持的直线与圆锥曲线能否沿唯一审批链路稳定形成 typed spec、解析 viewport、建立带 receipt 的 RenderPlan、完成可预算参数化采样，并留下可复核的原始记录。

唯一测量链路是：

```text
analyze_plot_item
→ PlotSceneSpec
→ resolve_single_item_viewport
→ RenderPlanBuilder.build
→ sample_parameterized_curve
```

探针明确不测量 renderer、`SceneRenderExecutor`、RenderActor、AppController、Qt、PNG 编码、preview、copy、完整场景或 GUI。开发机结果只能作为 Stage 15 的必要筛查证据，不能代替冻结协议下的 P50/P95、峰值内存、目标设备或真实教材验收。

## 2. 固定场景

协议按以下顺序运行 14 个场景；顺序、输入、viewport/aspect 和测量次数均由代码固定：

1. 竖直直线；
2. 一般斜直线；
3. 原点圆；
4. 平移圆；
5. 原点椭圆；
6. 平移椭圆；
7. 水平双曲线；
8. 竖直双曲线；
9. 单数学分支被 viewport 拆成两个 segment 的双曲线；
10. 上开口抛物线；
11. 下开口抛物线；
12. 右开口抛物线；
13. 左开口抛物线；
14. 顶点被 viewport 排除、形成两个 segment 的抛物线。

每个场景先运行 1 次不保留的预热，再运行 5 次保留测量。协议不随机化、不从环境变量读取输入，也不记录用户名、主目录、工作区绝对路径或其他个人路径。

## 3. 记录字段

每条 JSONL 记录包括：

* 协议、场景、measurement index、公式、item ID、typed spec 类型；
* resolved aspect 与 viewport source；
* analyzer、resolver、Builder、sampler 和总耗时的原始纳秒值；
* typed success/failure、failure stage、稳定 error code；
* 数学分支数、计划/实际 segment 数、sample count、batch size；
* `ParameterizedRenderMemoryBudget` 的全部字段，以及派生的 fixed、batch 和 total bytes；
* 实际 x、y 和 segment ranges 缓冲字节数；
* warning codes；
* 中性取消探针的调用次数与耗时。

`summary.json` 只保留原始总耗时和每场景/整体的 min/max；`formal_percentiles_computed` 固定为 `false`。本协议不计算或宣称正式 P50/P95。

## 4. 执行方式

在仓库根目录运行：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH='.'
uv run --locked python -B -m benchmarks.stage14_parameterized_probe
```

测试协议与证据包 schema：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH='.'
uv run --locked pytest -q -p no:cacheprovider tests/benchmarks/test_stage14_parameterized_probe.py
```

## 5. 确定性证据包

路径：`benchmarks/results/20260814T160403Z-stage14-parameterized-prototype-v1/`

| 文件 | SHA-256 |
|---|---|
| `environment.json` | `30DF3D7B39027EA5C38EE2A14C7E3E15A7A78BBB2E65B760E1D7DB27E3FA23B0` |
| `manifest.json` | `6FBD01F807E99C618BAB0076543BE9B5F6BECBD232D20CF930CFA838BC142A8A` |
| `records.jsonl` | `ECFC8A81497BD5F982EB4B4DFB49EE277B6022AF4AF92252FF868653341D039D` |
| `summary.json` | `190541ECBF72D89BCC48ECC9538C2E82768852C2286D4E183CE2D5C04F446E7A` |

环境记录：Windows 11 build 26200、AMD64、CPython 3.12.11、NumPy 2.5.1，Git 基线 `ec11449fb4a45beec639a6807c96dc9205389b2c`。

## 6. 结果

| 指标 | 结果 |
|---|---:|
| 固定场景 | 14 |
| 每场景预热 | 1 |
| 每场景保留测量 | 5 |
| 保留记录 | 70 |
| success / typed failure | 70 / 0 |
| 原始 total 最小值 | 923,500 ns（0.9235 ms） |
| 原始 total 最大值 | 70,923,500 ns（70.9235 ms） |
| sample count 范围 | 2–2400 |
| actual segment 范围 | 1–2 |
| 最大获批 total memory budget | 69,301,000 bytes |
| 中性取消探针耗时 | 25,300–95,700 ns |

最慢记录和最大预算都来自 `hyperbola-one-branch-split`；该场景有 2400 个样本、2 个 segment，实际 x/y/ranges 缓冲分别为 19,200 / 19,200 / 32 bytes。70 条记录全部低于两秒开发筛查线，全部取消探针调用次数为 1 且保持中性。

## 7. 解释限制

本结果证明 Stage 14 参数化原型在当前开发机、固定输入和直接采样链路上可执行、可预算、可复现。它不证明课堂低配置设备性能，不给出 renderer/Actor/GUI 端到端延迟，不形成 P50/P95 或峰值进程内存结论，也不关闭 P0-07。上述内容属于 Stage 15 及其正式协议。
