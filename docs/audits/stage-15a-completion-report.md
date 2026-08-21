# Stage 15A Completion Report：统一 Geometry Renderer（typed sampled curve → Agg/PNG）

日期：2026-08-16（Asia/Shanghai）
执行者：Stage 15A 主实施者（Claude Code 会话）
规划依据：Stage 15A 实施规划 v2（APPROVE）+ 总架构师绑定修正 BC-15A-01
执行章程：`docs/stage-15-execution-charter.md` §10

## 1. 开始基线与核验

- 开始 HEAD：`2f9a4ad8c9186acd33936de38e0906b81d72a3bb`（与授权基线精确相等，`git rev-parse HEAD` 核验）
- 开始 `git status --short --branch`：`## master...origin/master`，工作树干净，无用户修改
- 章程 §10.2 allowlist 逐字核验；§10.3 只读依赖零触碰（见 §7）
- `.codegraph/` 存在，代码理解优先经 CodeGraph 完成

## 2. 实际写入文件（⊆ 章程 §10.2 allowlist 11 条，无 allowlist 外条目）

| 文件 | 变更 |
|---|---|
| `math_drawing_assistant/engine/renderer.py` | 重构为唯一实现核心 `_render_png`；新增统一公共入口 `render_sampled_curve_png`（`geometry_allowed=True`）；旧入口 `render_explicit_png` 变为兼容 wrapper（`geometry_allowed=False`，签名与消息逐字保持）；新增 `_validate_geometry_provenance`、`_validated_geometry_render_context`、`_validate_geometry_sampled_contract`、`_plot_geometry_segment`、`_GEOMETRY_SPEC_TYPES`；模块 docstring 与 `__all__` 同步 |
| `math_drawing_assistant/engine/__init__.py` | 纯追加（+2/-0）：import 块与 `__all__` 各增 `render_sampled_curve_png` |
| `tests/engine/test_renderer.py` | 纯追加（+114/-0，`git diff --numstat` 证实）：统一入口签本钉住、统一入口渲染显函数管线、旧入口对五类几何 plan/outcome 的拒绝（零资源证明）；既有断言零修改 |
| `tests/engine/test_stage15a_geometry_renderer.py` | 新建：十组矩阵（六类型成功、segment 独立、CLOSED chord、legend、比例、取消、校验/错误契约、PNG 上限、异常映射、warnings 存活）；子架构复核后补 CLOSED↔OPEN、非 enum closure、错误/负 branch ID、逐段边界漂移和 gap 的资源前负例 |
| `tests/engine/test_stage15a_production_boundary.py` | 新建：P3-1 AST 全包扫描（`__file__` 包根，不依赖 CWD）+ 别名/间接/动态 import synthetic self-test + 15A 排除事实；子架构复核后增加 direct import alias 解析、module alias 属性调用和两个 renderer 生产入口调用解析 |
| `tests/test_stage13_public_api.py` | 哨兵同步：`_EXPECTED_ENGINE_EXPORTS` 增 `render_sampled_curve_png`；版本串断言改 `stage-15a-renderer-v1`；:395 状态句改新事实；:396 保持；五个 HTML 标记对保留 |
| `docs/architecture.md` | :4 日期、:5 状态、:387 仅 renderer/Stage15 子句、新增 §7.10「Stage 15A 统一 renderer 契约」；:383/:385 历史句未改写 |
| `docs/supported-formulas.md` | :3 版本、:4 状态、:41 renderer 子句改写而「尚未接入 SceneRenderExecutor」保留、:733 STAGE_13_STATUS 状态句、:986 状态句、新增「Stage 15A 统一 renderer 契约」小节；diff hunk 证实 ERROR_CODE_REGISTRY 与 LIMIT_FIELD_INDEX 标记区零变化 |
| `数学绘图助手_Codex协助开发步骤清单_v0.3.md` | :297 阶段 15 状态行更新为 15A renderer 层完成、待验收 |
| `docs/audits/stage-15a-completion-report.md` | 本文件 |
| `docs/audits/stage-15a-independent-review-notes.md` | 未由主实施者创建——按章程 §17，review notes 只能记录真正独立只读审核，待独立审核者写入 |

## 3. BC-15A-01 落实清单（绑定修正，最高优先级）

- ☑ 禁止 O(N) concatenate：主段以冻结数组 view 绘制（`_plot_geometry_segment` 首个 `axes.plot`），无任何拼接拷贝
- ☑ 每 item 至多一个 2 点 chord：仅 `closure is SegmentClosure.CLOSED` 时绘制一条；每 item 至多一个 CLOSED segment 由审批契约结构性保证（`render_plan.py` `_validate_oval_parameter_plan`：CLOSED 恰一、恰 [0, 2π]、`sample_count ≥ 64`）
- ☑ chord 正式数据上限 32 bytes：数据为两个长度 2 的 list → 4 个 float64 = 32 bytes；自动化断言 chord artist xdata+ydata `nbytes == 32`（`test_closed_oval_renders_main_points_plus_exact_chord`）
- ☑ 由 sampler 返回后不再存活的 `validation_workspace_bytes` 阶段复用覆盖：`ParameterizedRenderMemoryBudget.validation_workspace_bytes`（`render_plan.py:543`，属 `batch_bytes` 批处理阶段）在渲染期已死，32 bytes 落在其容量内；文档按此口径登记（supported-formulas「Stage 15A 统一 renderer 契约」小节，含「阶段 8C-1 豁免句仅作类比引用」的限定措辞）
- ☑ 自动测试断言 `32 <= validation_workspace_bytes`：`test_bc_15a_01_chord_bytes_stay_inside_validation_workspace_budget`（五类几何全参数化）
- ☑ 不修改任何预算公式、limits、plan 或 sampler：`render_plan.py`、`samplers.py`、`limits.py`、`parameterized_budget.py` 零变更（git status 无这些文件）

## 4. v2 复审四项文面修订勾销

- **A（§3.1 括注改述，已被 2026-08-21 子架构复核纠正）**：原结论错误地把获批 plan/snapshot 的 closure 防线等同于当前 sampled metadata 防线；snapshot 不含当前 metadata，且 `SampledParameterizedCurve.__post_init__()` 不调用逐条 metadata `__post_init__()`。renderer 现已显式逐条复验 metadata 自有不变量，并把 branch ID、closure、sample_count 和连续 ranges 精确绑定到获批 segments；相应资源前篡改负例已补齐
- **B（篡改用例精度）**：已吸收——零 ranges 用例使用 `setflags(write=False)` 且 owndata 的 `(0,2)` int64 数组，实测命中「≥1 segment」分支（`__post_init__` 的 `parameterized sampling needs at least one segment` ValueError → INTERNAL_ERROR），测试注释写明实际命中分支
- **C（§9 措辞）**：已吸收——status 为「⊆ 11 条 allowlist 且无 allowlist 外条目」：本报告落笔时 10/11 触碰（review notes 留待独立审核），git status 无 allowlist 外条目
- **D（§7 执行注记）**：已吸收——命令按 Git Bash 环境前缀适配执行（`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. uv run --locked pytest ...`），未遇 uv cache 沙箱摩擦；renderer 新 import 全部全限定路径

### 4.1 2026-08-21 子架构复核阻塞修复

总架构师子架构复核发现两个 Stage 15A 阻塞缺口，均已在 §10.2 allowlist 内修复，未进入 15B：

1. **sampled metadata 未与获批 plan 精确绑定**：既有 provenance snapshot 不含当前 sampled metadata，且 `SampledParameterizedCurve.__post_init__()` 不调用每个 `SampledSegmentMetadata.__post_init__()`。`_validate_geometry_sampled_contract` 现于 sampled curve 自校验后逐段显式复验 metadata，自 segments/ranges/metadata 等数起，精确检查 branch ID、closure、每段 sample_count、从 0 连续 ranges 和最终完整覆盖；所有失败保持既有 `INTERNAL_ERROR / sampled result contract validation failed`，且发生在任何 Figure/Canvas/Axes/BytesIO 之前。新增七类资源前篡改负例覆盖 CLOSED→OPEN、OPEN→CLOSED、非 `SegmentClosure`、错误/负 branch ID、总 sample_count 不变的逐段边界漂移、最终 stop 仍伪装完整覆盖的 gap。
2. **P3-1 漏检 import alias**：scanner 现静态解析直接 `import`、`from ... import` 的 alias 绑定与模块 alias 属性调用；renderer 的 sampler/analyzer/resolver/Builder 禁止入口和 `render_explicit_png` / `render_sampled_curve_png` 生产调用均使用解析后调用名。每一种 from-import alias、module-attribute 形式都有独立 synthetic 等值断言，确保由目标规则本身捕获；合法 backend_agg/Figure import 继续放行。冻结声明仅限这些静态 AST 形式及既有常量字符串动态 import 边界，不声称识别名称重赋值、`getattr`、star import 或任意动态 Python。

本轮未修改 `samplers.py`、`render_plan.py`、limits、预算公式、15A 前既有 `test_renderer.py` 内容或任何独立审核 notes；未执行 `git add`/`commit`/`push`。

## 5. 实际执行的验证与真实结果

1. 2026-08-21 子架构复核修复后定向（章程 §10.4，PowerShell）：`$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='.'; uv run --locked pytest -q -p no:cacheprovider tests/engine/test_renderer.py tests/engine/test_stage15a_geometry_renderer.py tests/engine/test_stage15a_production_boundary.py tests/engine/test_stage14e_acceptance.py tests/test_stage13_public_api.py` → **406 passed，0 failed / 0 errors / 0 skipped**
2. 2026-08-21 全量回归（章程 §7）：同前缀 `uv run --locked pytest -q -p no:cacheprovider` → **2416 passed，0 failed / 0 errors / 0 skipped**
3. 旧断言零漂移直接证据：`tests/engine/test_renderer.py` 既有断言零修改（numstat +114/-0）且全部通过；`tests/engine/test_scene_executor.py` + `tests/workers/test_render_actor_agg_probe.py` 单独复跑 **38 passed**（含既有轮询计数、静态边界和 Agg actor probe 拓扑）
4. `git diff --check`：通过（仅仓库既有 LF/CRLF 提示，非 diff --check 失败）；最终 `git status --short --branch` 见本轮交付报告
5. 边界机械证明：status 共 10 条写入路径，`ALLOWLIST_OUTSIDE=0`；章程 §10.3 加 `engine/parameterized_budget.py` 共 12 条只读依赖，`READONLY_TOUCHED=0`；独立审核 notes 不存在；从 HEAD 与工作树抽取并统一换行后，`LIMIT_FIELD_INDEX` 块精确相等（3825 chars），`ERROR_CODE_REGISTRY` 块精确相等（3553 chars）。`tests/engine/test_renderer.py` 为唯一 `@@ -1711,0 +1712,114` 追加 hunk、numstat `114/0`，Stage 15A 前既有内容零修改
6. 禁令机械自查：renderer.py 整文件子串禁令（`SampledParameterizedCurve`、`sample_parameterized_curve`、`hyperbola_geometry`、`parabola_geometry`、lowered `pyside6`/`matplotlib.pyplot`/`pyplot`/`plt.`、`sample_explicit_function(` 等调用型禁令、AST 调用/标识符/导入禁令）程序化核验全部 ok；engine `__init__` 无 numpy/pyside/sympy 字样；`matplotlib.figure` 与 `matplotlib.backends.backend_agg` import 原形保留

## 6. 退出判定对表（章程 §10.4）

- ☑ 六种 exact 类型 sampled output 均经 `render_sampled_curve_png` 渲染为 PNG（签名 + IHDR 与 plan 精确一致）；显函数管线经统一入口同样可渲染
- ☑ segment 独立（双曲线双支/抛物线双区间/圆四弧逐 slice 数据级断言，无跨 range 连线）；CLOSED 圆/椭圆 = 主 artist N 点 + 恰一条 2 点 chord（数据精确断言、样式一致、无 label、无额外 legend 条目）；OPEN 无 chord；采样数组渲染后仍 WRITEABLE=False
- ☑ receipt、provenance 与 sampled metadata/segment 精确绑定先于任何 Matplotlib/BytesIO 资源（plan 篡改、普通构造、零 ranges、计数不符、closure/branch/range 篡改、跨类型混配均为零资源事件）
- ☑ 取消六检查点（资源前/首段前/段间/编码前/编码后/返回前，双曲线双段）、PNG 上限、签名/IHDR、异常映射（RuntimeError→RENDER_FAILED、MemoryError→RESOURCE_LIMIT_EXCEEDED，消息脱敏）、finally 全释放矩阵通过
- ☑ 几何 sampled curve `__post_init__` 先行，随后每条 metadata `__post_init__` 与获批 segment 精确绑定；零 ranges → INTERNAL_ERROR（非 NO_VISIBLE_CURVE）；合法不可见仅上游 ErrorInfo 原样透传且 item_id 归属正确；SamplingCancelled → RenderCancelled
- ☑ P3-1：`__file__` 包根 AST 全包扫描 + 原别名/间接/dynamic import 自证 + renderer 四类禁止入口的 from-import/module alias 独立自证 + 两个生产 renderer 入口的 import-alias/module-attribute 独立自证通过；合法 backend_agg/Figure import 无误报；14E 历史测试只读且仍通过
- ☑ 无 Actor/GUI/Controller 接线（统一入口无任何已冻结静态形式的生产调用方、engine 无 workers/ui/app_controller import、renderer 文件集仍为单例）；旧入口同类生产调用方仍恰为 `scene_executor.py`；engine `__all__` 仅新增一个统一导出，哨兵三处 lockstep 同步
- ☑ 无新依赖/Pyright/CI/PlotKind/结果模型/limits/预算公式改动；`ERROR_CODE_REGISTRY` 与 `LIMIT_FIELD_INDEX` 零变化
- ☑ 文档措辞仅限「15A renderer 层完成」；不宣称 Actor 唯一进入者、executor 统一、M1.5 闭环、P0-07 关闭、checkpoint、正式性能

## 7. 只读依赖零触碰声明

`math_drawing_assistant/models/render_plan.py`、`engine/samplers.py`、`config/limits.py`、`engine/parameterized_budget.py`、`tests/engine/test_stage14b2_line.py`、`test_stage14c_circle_ellipse.py`、`test_stage14d1_hyperbola.py`、`test_stage14d2_parabola.py`、`test_stage14e_acceptance.py`、`tests/workers/test_render_actor_agg_probe.py`、`docs/stage-15-execution-charter.md`、`数学绘图助手 PRD.md` 均未修改（git status 可证）。实施中未发现需修改任一只读依赖的情形；Q2 未触发。

## 8. 实施发现登记（供独立审核与 15G 文档一致性复查）

1. **几何 PNG 上限的测试途径**：parameterized sampler 以 `DEFAULT_LIMITS` 复算预算并要求与 plan 完全相等（`samplers.py` 各 `_validated_*_context` 的 `recomputed_budget != budget` 门），因此显函数路径的 tight-_limits 夹具对几何不可用（会产生 `internal_error`「…budget is not active」）。几何 PNG 上限改为类级放大编码产物（真实编码后追加 padding 超过获批 reserve）驱动，先套 `print_png` 补丁再建资源跟踪子类以保证 encode 事件仍被捕获。此为测试技法差异，非生产缺陷
2. **消息发射点登记**（与规划登记一致）：`sampled result contract validation failed` 为既有消息在几何路径的第二发射点；几何 provenance 门把 type 与 snapshot 两类拒绝合并为一条 `sampling outcome type mismatch`（与显函数两条消息的粒度不对称，Q1 既定取舍）；`no_visible_curve` registry 行（supported-formulas :364 区域）口径：几何 renderer 路径不合成该码，仅上游透传——该事实已写入新契约小节，registry 表本体零变化
3. **「阶段 8C-1」豁免句引用措辞**：新契约小节按复审裁定将其限定为类比引用（其对象是库内部不可观测分配；chord 覆盖依据是 validation_workspace_bytes 阶段复用论证），防止 15G 整句 grep 误报（预算哲学句跨行位于 :452-454）
4. **v1→v2 修订链来源**：六项 REQUEST CHANGES + Q1 裁定与 BC-15A-01 均来自仓库外总架构裁定文本，仓库内无独立留档
5. **取消检查点数**：几何路径与显函数路径同为「1 + segment 数 + 3」；双曲线双段为 6 个检查点（显函数单段为 5），矩阵按双曲线参数化覆盖段间检查点

## 9. 停止声明

Stage 15A 实施完成并停止。未 `git add`/`commit`/`push`；未进入 15B（15B 未获授权）。等待独立只读审核（`docs/audits/stage-15a-independent-review-notes.md`）与总架构师验收。
