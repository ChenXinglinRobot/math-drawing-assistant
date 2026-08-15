# Stage 14 最终验收与 P0-06 关闭审计

审计文件名日期：2026-08-14（任务指定）<br>
本地关闭日期：2026-08-15（Asia/Shanghai）<br>
确定性证据包日期：2026-08-14T16:04:03Z<br>
结论：Stage 14 通过；P0-06 关闭；允许进入 Stage 15

## 1. 审计范围与基线

本审计只验收 Stage 14 的参数化直线和圆锥曲线采样原型，不实施 renderer、Actor、Controller、UI、多 item、Stage 15、正式 M1.5 性能或真实教材矩阵。

开始基线：

```text
branch: master
HEAD:   ec11449fb4a45beec639a6807c96dc9205389b2c
origin/master: ec11449fb4a45beec639a6807c96dc9205389b2c
initial worktree: clean
```

Stage 14D-2 起始门禁：

```text
68 passed in 2.04s
0 failed / 0 errors / 0 skipped
```

本轮没有创建版本或修改 limits/RenderPlan/receipt/public sampler 契约；最终门禁通过后只创建本任务指定的 Stage 14E 收口提交，未 push。唯一生产代码变化是把 `sample_parameterized_curve` 的 docstring 从列举部分几何类型改为准确的“approved parameterized geometry plan”；执行语义不变。

## 2. 实际修改

生产与验证：

* `math_drawing_assistant/engine/samplers.py`：仅 docstring 精确化；
* `tests/engine/test_stage14e_acceptance.py`：跨类型最终验收矩阵；
* `tests/test_stage13_public_api.py`：把 supported-formulas 文档版本与阶段状态哨兵同步到 Stage 14E，不放宽 public API 行为契约；
* `benchmarks/stage14_parameterized_probe.py`：固定参数化开发探针；
* `tests/benchmarks/test_stage14_parameterized_probe.py`：协议、schema、边界和可解析性测试；
* `benchmarks/results/20260814T160403Z-stage14-parameterized-prototype-v1/`：四文件确定性证据包。

文档闭环：

* `docs/architecture.md`；
* `docs/decisions.md`；
* `docs/supported-formulas.md`；
* `docs/benchmarks/stage14-parameterized-prototype-v1.md`；
* `docs/audits/stage-14-final-acceptance-2026-08-14.md`；
* `数学绘图助手_Codex协助开发步骤清单_v0.3.md`；
* `联网确认.md`。

## 3. 跨类型矩阵

| 类型 | exact/路由证据 | viewport/aspect | topology 与不误连 | 数值与资源 | 取消/失败 |
|---|---|---|---|---|---|
| M1 显函数 | 原 class、签名、字段；`branch_id=None` | 既有显函数 viewport | 原 segment metadata | 原预算/结果契约 | 原 M1 路径保持 |
| LineSpec | 竖直与一般直线 | AUTO_GEOMETRY / AUTO | 单个 OPEN segment | exact 矩形交点、2 点、receipt/budget | neutral cancel；越界 typed |
| CircleSpec | 原点、平移、完整与裁切 | AUTO_GEOMETRY / EQUAL | CLOSED 完整圆；裁切最多 4 arc | 独立 exact residual、只读数组 | neutral cancel；不可见 typed |
| EllipseSpec | 原点与平移 | AUTO_GEOMETRY / EQUAL | 完整/裁切 arc 不误连 | 独立 exact residual、预算/receipt | neutral cancel；极端合法成功 |
| HyperbolaSpec | 水平/竖直、平移 | AUTO_GEOMETRY / EQUAL | 两数学分支；单支可拆两段；ranges 不跨支 | branch sign、ULP 边界、2400 点场景 | neutral cancel；range/no-visible typed |
| ParabolaSpec | 上/下/左/右、平移 | AUTO_GEOMETRY / EQUAL | branch 0；顶点排除时两个 OPEN interval | 四向 primitive residual、ULP 边界 | neutral cancel；range/no-visible typed |

公共矩阵另外复验：exact plan/result 字段、所有参数化 budget 字段、line endpoints、parameter interval 字段、approval snapshot、warning/error、实际缓冲不超过获批预算、数组自有且只读。每一类 receipt 篡改都由 validator 拒绝，且不会签发替代 receipt。

## 4. 独立数值对照与教学代表性

独立 oracle 使用 `Fraction.from_float` 和各类型 primitive equation 计算归一化残差，不调用生产 normalized residual、projector、viewport planner 或 interval planner。检查同时覆盖 float64 viewport ULP 边界、双曲线 branch sign 与抛物线四种开口方向。

代表性输入包括：一般/竖直直线，原点/平移圆和椭圆，水平/竖直双曲线、单支拆分双曲线，四向平移抛物线和顶点被排除的双段抛物线。极端、扁平、小尺度、坐标上限附近和窄合法 viewport 成功；不可证明范围保持 `NUMERIC_RANGE_UNSUPPORTED`，无可见曲线保持 `NO_VISIBLE_CURVE`。

这些是确定性教学代表样例与独立数值对照，不是 Stage 15 的真实教材表达式矩阵；P0-07 仍打开。

## 5. topology、取消与静态生产边界

验收确认：直线为一个 segment；完整圆为显式 CLOSED；裁切圆最多四弧；椭圆裁切弧互不误连；双曲线数学分支 ID 稳定，单支拆分时 ranges 不跨段；抛物线顶点被排除时形成两个 OPEN interval，均属于 branch 0。

显函数与五种 exact geometry 都验证了“receipt/plan validation 先于 cancellation probe”。取消返回中性 `SamplingCancelled`，item ID 正确，不暴露 typed failure，也不保留部分结果。

静态检查覆盖生产目录并确认：

* 参数化 sampler 没有 contour 导入；
* sampler 没有重入 resolver、Builder 或 geometry interval planner；
* renderer、`SceneRenderExecutor`、workers/Actor、Controller/UI 没有新增几何执行路径；
* 没有第二套公开 resolver/Builder/sampler 流水线；
* benchmark 模块没有被生产包导入。

因此二维 contour 保持诊断/未来研究边界，没有成为正式主实现或隐式后备。

## 6. benchmark 证据

证据包：`benchmarks/results/20260814T160403Z-stage14-parameterized-prototype-v1/`

| 指标 | 结果 |
|---|---:|
| 场景 / 保留记录 | 14 / 70 |
| success / typed failure | 70 / 0 |
| 原始 total min / max | 0.9235 / 70.9235 ms |
| sample count | 2–2400 |
| actual segments | 1–2 |
| 最大获批总内存预算 | 69,301,000 bytes |
| cancel probe elapsed | 25.3–95.7 μs |

最慢和最大预算场景均为 `hyperbola-one-branch-split`。证据包记录 Python、OS、CPU、NumPy、Git commit、UTC、原始阶段耗时、typed 结果、spec/aspect/source、计划/实际 segment、sample/batch、全部参数化预算字段、实际缓冲、warning 和取消探针。

边界声明：该探针只测直接 analyzer/resolver/Builder/sampler 链；开发机全部低于两秒只是 Stage 15 必要筛查，不是正式 M1.5 达标。协议明确 `formal_percentiles_computed=false`，不计算或宣称 P50/P95。

## 7. 自动化命令与结果

以下命令均从仓库根目录运行，使用锁定环境，禁用 bytecode 和 pytest cache provider。

Stage 14D-1/14E、public API 与 benchmark 契约定向复验：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='.'; uv run --locked pytest -q -p no:cacheprovider tests/engine/test_stage14d1_hyperbola.py tests/engine/test_stage14e_acceptance.py tests/test_stage13_public_api.py tests/benchmarks/test_stage14_parameterized_probe.py
```

结果：`331 passed`，0 failed / 0 errors / 0 skipped。

Stage 14 全阶段联合矩阵：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='.'; uv run --locked pytest -q -p no:cacheprovider tests/engine/test_stage14b1_contracts.py tests/engine/test_stage14b2_line.py tests/engine/test_stage14c_circle_ellipse.py tests/engine/test_stage14d1_hyperbola.py tests/engine/test_stage14d2_parabola.py tests/engine/test_stage14e_acceptance.py
```

结果：`614 passed`，0 failed / 0 errors / 0 skipped。

完整 engine：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='.'; uv run --locked pytest -q -p no:cacheprovider tests/engine
```

结果：`1860 passed`，0 failed / 0 errors / 0 skipped。

Stage 13 public API 保护：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='.'; uv run --locked pytest -q -p no:cacheprovider tests/test_stage13_public_api.py
```

结果：`5 passed`，0 failed / 0 errors / 0 skipped。

全部 benchmark tests：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='.'; uv run --locked pytest -q -p no:cacheprovider tests/benchmarks
```

结果：`101 passed`，0 failed / 0 errors / 0 skipped。

全量回归：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='.'; uv run --locked pytest -q -p no:cacheprovider
```

结果：`2325 passed`，0 failed / 0 errors / 0 skipped。

确定性探针：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='.'; uv run --locked python -B -m benchmarks.stage14_parameterized_probe
```

结果：`records=70 success=70 typed_failure=0`，写入上述唯一保留证据包。

## 8. P0-06 逐项关闭

| 关闭条件 | 证据 | 结论 |
|---|---|---|
| 直线与 viewport 求交 | exact endpoint、一般/竖直矩阵 | 通过 |
| 圆/椭圆角参数 | 完整 CLOSED、裁切 arc、seam/多弧既有矩阵 | 通过 |
| 双曲线两支 | 横/竖轴、branch identity、单支拆分 | 通过 |
| 抛物线开口 | 上/下/左/右、branch 0、顶点排除 | 通过 |
| 有限可见参数区间 | exact-before-root、typed invisible/singleton | 通过 |
| 裁切与精度提示 | warning code、实际 segment count、独立 residual | 通过 |
| 采样/分支/内存上限 | plan/budget 重算、逐字段篡改、实际缓冲 | 通过 |
| 极端数值 | 合法极端成功；range unsupported typed 拒绝 | 通过 |
| 合作取消 | 六类路径 neutral、无部分结果 | 通过 |
| 开发机性能筛查 | 70/70，raw max 70.9235 ms | 通过（非正式性能） |
| contour 只作诊断 | 静态生产边界无导入/无后备 | 通过 |

P0-06 的既定关闭条件全部通过，无跳过、失败或错误。

## 9. 独立审核修复闭环

独立审核发现的 P2-1/P2-2/P2-3 文档状态矛盾已修复；竖直双曲线 branch 方向的动态独立 oracle 已补齐；双曲线成功路径实际到达的全部取消检查点已通过先计数、再逐点取消的回归测试穷尽；P3-8 的参数化预算类型名已修正为真实类型名。P3-1 至 P3-7 未在本轮实施，作为非阻塞观察保留给 Stage 15 前加固，不影响 P0-06 的当前裁定。

## 10. 最终出口与明确未实现

Stage 14E 通过，P0-06 关闭，Stage 14 完成；仓库可以进入 Stage 15 的独立实施任务。

仍未实现或未关闭：geometry renderer、`SceneRenderExecutor`/RenderActor/AppController/UI 整合、多 item、正式端到端 P50/P95 与峰值内存、目标课堂设备性能、真实教材表达式矩阵、P0-07、Stage 15、M1.5 checkpoint 和核心 MVP。Stage 14 的完成不自动授权或表示这些工作已经开始。
