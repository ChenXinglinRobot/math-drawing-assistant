# Stage 15A 独立只读审核 notes：统一 Geometry Renderer 候选变更

日期：2026-08-21（Asia/Shanghai）
审核者：独立审核窗口（Claude Code 会话，非 Stage 15A 主实施者）
审核对象：工作树中 Stage 15A 全部候选变更（10 个文件：7 modified + 3 untracked）
授权基线：`master @ 2f9a4ad8c9186acd33936de38e0906b81d72a3bb`
依据：`docs/stage-15-execution-charter.md` §7/§10/§17、Stage 15A 实施规划 v2、规划 v2 复审裁定（APPROVE 附 A–D 修订 + 3 硬约束）、总架构师绑定裁定 BC-15A-01

## 1. 审核边界声明

本审核为纯只读核查 + 本 notes 写入；未修改任何生产代码、测试、架构文档、completion report 或既有候选差异；未执行 `git add`/`commit`/`push`/`reset`/`checkout`/`clean`；未进入 15B。主实施者的 completion report 与自报测试结果一律不作为独立证据，全部命令由本窗口独立复跑。

## 2. 基线与开始工作区状态（本窗口实测）

- `git rev-parse HEAD` → `2f9a4ad8c9186acd33936de38e0906b81d72a3bb`，与授权基线**精确相等**
- `git status --short --branch` → `## master...origin/master` + 10 条变更（7 `M` + 3 `??`），与"审核 notes 写入前应有 10 个 Stage 15A 变更文件"预期一致；`docs/audits/stage-15a-independent-review-notes.md` 初始不存在（预期，非缺陷）
- `git diff --name-status` / `--stat` / `--numstat`：renderer.py `+329/-49`；test_renderer.py `+114/-0`（严格纯追加）；engine/__init__.py `+2/-0`；test_stage13_public_api.py `+4/-2`（仅哨兵同步两行替换）；architecture.md `+9/-3`；supported-formulas.md `+17/-5`；步骤清单 `+1/-1`；合计 `476 insertions / 60 deletions`（7 文件）+ 3 个 untracked 新文件
- `git diff --check` → 通过（仅仓库既有 LF/CRLF 信息性警告，非 diff --check 失败项）

## 3. 阅读的授权材料

1. `docs/stage-15-execution-charter.md` 全文（重点 §7 顺序门禁、§10 15A 边界/allowlist/退出条件、§17 证据真实性规则）
2. `docs/audits/stage-15a-completion-report.md` 全文
3. Stage 15A 全部 diff（`git diff` 7 个 modified 文件逐 hunk + 3 个 untracked 新文件全文）
4. 规划原文 `C:\Users\Chen Xinglin\.codex\attachments\a0a84cb5-9a54-4455-8a45-ae00de56bb77\pasted-text.txt`（可访问）
5. 规划 v2 复审裁定 `C:\Users\Chen Xinglin\.codex\attachments\3f29621c-f99b-4592-ad12-f727697518c3\pasted-text.txt`（可访问）
6. 受影响公开 API / 架构 / 公式文档（engine/__init__.py、architecture.md、supported-formulas.md 现行全文与 diff）
7. 只读依赖源码（经 CodeGraph + Read 核验，未修改）：`models/render_plan.py`（含 `_validate_oval_parameter_plan`/`_validate_hyperbola_parameter_plan`/`_validate_parabola_parameter_plan`/`GeometryRenderItemPlan.__post_init__`/`ParameterizedRenderMemoryBudget`）、`engine/samplers.py`（`SampledParameterizedCurve.__post_init__`、`SampledSegmentMetadata.__post_init__`、`_sampled_parameterized_curve_matches_approved_plan`、`_frozen_owned_ranges`）、`engine/render_plan_builder.py`（oval 区间 CLOSED 产生点）、`engine/parameterized_budget.py`（五类预算公式）；`tests/engine/test_scene_executor.py`（:564-576 裸名唯一性断言）
8. `.codegraph/` 存在，代码理解按 AGENTS 约定优先经 CodeGraph 完成

## 4. allowlist 与只读依赖核验

- 章程 §10.2 allowlist 共 11 条；工作树触碰 10 条（唯一未触碰项为本 review notes，属预期）；**无任何 allowlist 外条目**；全部 10 条逐字比对命中
- 章程 §10.3 只读依赖 + 规划补列的 `engine/parameterized_budget.py` 共 12 条：git status 全部零触碰（`READONLY_TOUCHED=0`）
- 无 Stage 15B/Actor/GUI/Controller/limits/render plan/sampler/预算公式/benchmark/results 越界改动；无新依赖、Pyright、CI 文件

## 5. 实际运行命令与真实结果（本窗口，Git Bash 适配）

| 门 | 命令 | 结果 |
|---|---|---|
| 定向门 | `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. uv run --locked pytest -q -p no:cacheprovider tests/engine/test_renderer.py tests/engine/test_stage15a_geometry_renderer.py tests/engine/test_stage15a_production_boundary.py tests/engine/test_stage14e_acceptance.py tests/test_stage13_public_api.py` | **406 passed** in 21.09s，0 failed / 0 errors / 0 skipped |
| 旧链证明 | 同前缀 `pytest -q -p no:cacheprovider tests/engine/test_scene_executor.py tests/workers/test_render_actor_agg_probe.py` | **38 passed** in 3.66s，0 failed / 0 errors / 0 skipped |
| 全量门 | 同前缀 `pytest -q -p no:cacheprovider`（全仓库） | **2416 passed** in 47.85s，0 failed / 0 errors / 0 skipped |
| 结构预算下界 | `uv run --locked python -B`（临时脚本，只读计算） | line 20,500 / oval(64) 94,714 / hyperbola 116,017 / parabola 90,617 bytes，全部 ≥ 32 |
| 差异检查 | `git diff --check` | 通过（仅既有 LF/CRLF 提示） |
| 状态 | `git status --short --branch` | 见 §9 |

环境注记：uv 每次运行输出 `VIRTUAL_ENV=C:\ProgramData\anaconda3` 与项目 `.venv` 不匹配的警告，属本机环境既有提示，不影响 `--locked` 解析与测试结果；`-p no:cacheprovider` 下未出现 `.pytest_cache` 权限警告。三次 pytest 均一次成功，无重试。

## 6. 核心审核结论（实现 / 测试 / 文档三方交叉验证）

### 6.1 唯一实现核心

- `_render_png`（renderer.py:110-383）持有唯一渲染行为链：receipt 第一操作 → item plan 联合分发 → outcome 三分发 → 显函数/几何流 → 共享资源/PNG/finally 尾部；取消轮询循环与取消/ErrorInfo 返回契约全部在核心内
- `render_sampled_curve_png`（:73-91）与 `render_explicit_png`（:94-107）**都只调用 `_render_png`**（geometry_allowed=True/False），彼此零转发——满足复审裁定硬约束 2
- 无第二套 renderer/resolver/Builder/sampler/executor：engine 目录 `*renderer*.py` 文件集仍为单例（P3-1 测试断言 + glob 复核）；`engine/__init__.py` 仅新增一个统一导出，无分类型 renderer 导出
- `SceneRenderExecutor` 仍是 `render_explicit_png` 唯一生产调用方：P3-1 别名解析扫描断言 callers == [scene_executor.py]，且既有 test_scene_executor.py:564-576 裸名断言通过（38 passed 旧链）
- 统一入口生产调用方为零（全生产包 grep 仅 renderer.py 定义/`__all__` 与 engine/__init__.py 导出两处命中）——15B 未被提前实施

### 6.2 旧 M1 零漂移

- `tests/engine/test_renderer.py` numstat `+114/-0`，追加 hunk 起于 `@@ -1709,3 +1709,117 @@`，既有断言零修改零删除；全部通过
- 机械比对：HEAD 版 `render_explicit_png` 显函数流（outcome 三分发后至 memory_budget 前 17 条语句）与新版 else 分支（16 条 + 被提取锚点吞掉的首行类型检查）空白归一后**逐字相同**；segment 循环与资源/PNG/finally 尾部为共享代码未改
- executor 与 Agg probe 拓扑继续通过（38 passed，含轮询计数与 pass_polls 约束）

### 6.3 几何契约门

- receipt 为第一实质校验（:121-129）；provenance 门（:158-165）→ geometry context（:167-176）→ sampled contract（:178-184）全部先于 `memory_budget` 检查（:207）与 Figure/Canvas/Axes/BytesIO 创建（:224-238）
- `SampledParameterizedCurve.__post_init__()` 先于跨 plan 复验调用（:456），随后逐段 `SampledSegmentMetadata.__post_init__()`（:475）并精确绑定 branch ID/closure/逐段 sample_count/从 0 连续 ranges/最终完整覆盖（:476-492）——2026-08-21 子架构复核两项阻塞缺口的修复落实到位，且均有资源前负例（七类篡改矩阵）
- 零 ranges 篡改：`__post_init__` 以 `parameterized sampling needs at least one segment`（samplers.py:370-371）拒绝 → INTERNAL_ERROR `sampled result contract validation failed`，非 NO_VISIBLE_CURVE（负例实测通过，篡改数组 `setflags(write=False)`+owndata 确保命中目标分支，`_frozen_owned_ranges` samplers.py:2857-2863 接受空 (0,2) 只读自有数组已源码确认）
- 完全不可见合法结果仅上游 ErrorInfo 原样透传（:142-148），item_id 一致性检查保持；几何路径无任何 `_no_visible_error` 合成
- 封闭联合：`type(item_plan) is ExplicitRenderItemPlan` / `geometry_allowed and type(...) is GeometryRenderItemPlan` 精确类型检查（:134-139）；`_GEOMETRY_SPEC_TYPES` 五元封闭集 + `type(spec) not in` 检查（:418）；outcome 经 `_sampled_parameterized_curve_matches_approved_plan` 精确类型 + snapshot 相等（samplers.py:425-437）；无宽松子类旁路
- 所有错误携带正确 item_id（context 类错误 None/审计与显函数路径同构，其余绑定 item_id）

### 6.4 绘制正确性

- 六类 sampled output（显函数 y=x^2 + 直线/圆/椭圆/双曲线/抛物线）均经统一入口渲染出 PNG，签名 + IHDR 宽高与 plan 精确一致（矩阵 1 + test_renderer 追加）
- 双曲线双支、抛物线双区间、圆部分四弧逐 segment 数据级断言（artist 数 == range 数、每 artist 数据 == 对应冻结切片），无跨 range 误连
- CLOSED 圆/椭圆 = 主段 N 点冻结数组 view + 恰一条 2 点 chord：chord 数据精确等于 `([x[stop-1], x[start]], [y[stop-1], y[start]])`，样式与主段一致、无 label（`get_label().startswith("_")`）、chord 数据 nbytes == 32；OPEN 段（直线/双曲线/抛物线/部分弧）零 chord；渲染后采样数组仍 WRITEABLE=False
- legend 条目文本 == `spec.provenance.normalized_input`，多 segment 单条目，chord 不产生额外条目；show_legend=False 无 legend
- EQUAL 视口：autoscale off、aspect equal/box、绘制后 xlim/ylim 与 plan 一致无漂移（绘制后二次 set_xlim/set_ylim 防线保留 renderer.py:311-312）

### 6.5 取消、PNG、异常与资源

- 六检查点真实存在且序正确：资源前（:215）→ 每段前/段间（:257，双曲线双段即含段间）→ 编码前（:316）→ 编码后（:330）→ 返回前（:351）；几何双曲线 6 检查点与显函数单段 5 检查点同构（`1 + segment 数 + 3`），取消矩阵按 call_number 1-6 参数化逐一通过且 plot/encode/getvalue 事件计数精确
- 取消与失败路径全部进入 finally（:367-383）：buffer close → axes.clear 吞异常 → figure.clear 吞异常 → 引用置空；矩阵以弱引用 + gc.collect 证明 Figure/Canvas/Axes/BytesIO 全释放无滞留
- PNG 上限复用 `min(png_buffer_reserve_bytes, png_copy_bytes)` + 实际字节数 + 签名 + IHDR 宽高既有正式逻辑（:339-347）；上限测试 monkeypatch 经类级 print_png 补丁 + 资源跟踪子类叠加，**真实编码后追加 padding 超限**（断言 `size_at_close > approved_png_limit`、getvalue 未发生、encode 恰一次）——确实触发目标分支，非夹具自证
- MemoryError → RESOURCE_LIMIT_EXCEEDED、RuntimeError/编码异常 → RENDER_FAILED，technical_message 仅含异常类型名、不含注入的 secret 细节（脱敏负例通过）

### 6.6 P3-1 生产边界测试

- 包根 `Path(__file__).resolve().parents[2] / "math_drawing_assistant"`（:16），与 14E:913 同式，不依赖 CWD
- 扫描生产包全部 `.py`（`rglob`，断言 >40 文件），含 renderer 专项角色
- AST 规则覆盖：直接 import、`from ... import`（含 `as` 别名绑定解析 `_import_bindings`）、模块别名属性链（`_resolved_call_name`）、常量参数动态 import（`importlib.import_module`/`__import__`）、`matplotlib.pyplot` 属性链、`.contour` 调用、renderer 投影模块禁入、renderer sampler/analyzer/resolver/Builder 入口禁调、engine（renderer 外）matplotlib 禁入、engine 禁 workers/ui/app_controller、tests/benchmarks 禁入
- renderer 两个生产入口调用按解析后调用名检查：`render_explicit_png` 调用方恰为 scene_executor.py、统一入口零生产调用方
- 自证用例独立性：11 个 synthetic 总集 + 8 个 renderer 别名用例逐一断言 `_analyze(...) == {单一违规}`（互不遮蔽）+ 4 个生产入口别名用例逐一断言 `_production_entry_calls(...) == {entry}`；合法 backend_agg/Figure import 放行断言
- 冻结声明范围诚实：docstring 明示不覆盖名称重赋值、`getattr`、star import 与任意动态 Python；易绕过形式（如 relative import `from .tests import x`）在声明范围外且生产包无 tests 子包，不构成实质缺口
- Actor/UI/Controller 排除：engine 禁 workers/ui/app_controller import 测试 + 15A 文件集断言

### 6.7 公共 API 与文档

- 哨兵三处 lockstep：`engine.__all__`（+1 纯追加）+ `_EXPECTED_ENGINE_EXPORTS`（+1）+ supported-formulas 版本串 `stage-15a-renderer-v1`（测试断言与文档 :3 一致）
- 只新增统一入口；六个分类型 renderer 名显式断言不在 `__all__`
- `ERROR_CODE_REGISTRY` 块与 `LIMIT_FIELD_INDEX` 块与 HEAD **逐字节精确相等**（本窗口正则提取比对：3487 / 3763 chars，HEAD 与工作树各自相等；completion report 记录的 3553/3825 为含标记行的另一提取口径，"精确相等"的实质声明为真）
- 文档措辞核验：architecture.md/supported-formulas.md/步骤清单均仅宣称"15A renderer 层完成、待独立审核与总架构师验收；executor 统一/Actor/Controller/UI/15B 起未开始"；不宣称 Actor 唯一 Matplotlib 进入者、M1.5 闭环、P0-07 关闭、checkpoint、正式性能——无越权宣称
- completion report 与实证一致：10 文件清单、+114/-0、406/38/2416 passed（本窗口独立复跑逐项吻合）、git diff --check 通过、零触碰声明属实、§4 A-D 勾销与 §4.1 两项阻塞修复描述与代码实证吻合
- untracked 新文件行尾空白（`git diff --check` 不覆盖）：两个新测试文件零行尾空白；completion report :3-5 的行尾双空格为既有 audit 文档通用的 Markdown 硬换行惯例（stage-00a/0B-1/0B-2/14b-2 均有先例），非缺陷

## 7. BC-15A-01 专项结论（源码级，非仅测试断言）

1. **无 O(N) concatenate 补首点**：renderer.py 全文无 concatenate/拼接路径；主段以冻结数组 view `sampled_curve.x[start:stop]` 绘制（:524-525），与显函数路径同法，零 O(L) 新分配
2. **主段冻结数组 view**：上述 + 渲染后 WRITEABLE=False 断言
3. **每 item 至多一条两点 chord**：结构性证明——Builder 仅在全可见时产生单段 `((0.0, tau, SegmentClosure.CLOSED),)`（render_plan_builder.py:973-974），部分弧恒 OPEN（:1000）；审批校验强制 CLOSED ⇒ 恰一 interval、恰 [0,2π]、sample_count ≥ 64（render_plan.py:1261-1274），部分区间必须 OPEN（:1279-1280）；双曲线恒 OPEN（:1313-1314）、抛物线恒 OPEN（:1357-1358）、Line `closure` 属性恒 OPEN（:382-384）；renderer 逐段 `metadata.closure == segment.closure` 与获批 plan 精确绑定（renderer.py:481-482），任何 metadata 篡改在资源前被拒。阶段 liveness：`validation_workspace_bytes` 属 `ParameterizedRenderMemoryBudget.batch_bytes` 批处理阶段（render_plan.py:582-587），该阶段为 sampler 内部工作区，sampler 返回后即死亡，渲染期复用其容量属阶段复用口径
4. **chord 正式数据 4 × float64 = 32 bytes**：两条长度 2 列表 → 4 float64；测试断言 chord xdata+ydata nbytes == 32
5. **`32 <= validation_workspace_bytes` 独立验证**：五类预算公式在结构最小输入（最小 sample_count/batch_size=1/1×1 图像）下 validation_workspace_bytes = 20,500–116,017 bytes，全部 ≥ 32——对任意获批 plan 结构性成立，不依赖五个采样样例
6. **预算公式/limits/plan/sampler 零修改**：render_plan.py、samplers.py、limits.py、parameterized_budget.py 全部零触碰（git status）
7. **32 bytes 表述边界**：renderer docstring（:512-521）与 supported-formulas 新小节均把 32 bytes 限定为"项目自建 chord 正式绘图输入数据"，并以"阶段 8C-1 豁免句仅作类比引用（其对象是库内部不可观测分配）"限定措辞区分第三方库内部分配——未把 Matplotlib 内部复制虚假描述为只有 32 bytes

## 8. findings

**P3-1（非阻塞）：`docs/architecture.md:4` "最后更新：2026-08-16" 日期滞后**

- 违反条款：无硬性章程条款；属 §17 证据真实性精神下的小型文档准确性问题（非"文档实质不一致"——内容本身准确）
- 证据：architecture.md §7.10 含"逐段显式调用 `SampledSegmentMetadata.__post_init__()`，并把 segment 数、branch ID、closure……与获批 plan 精确绑定"表述，该行为是 completion report §4.1 登记的 2026-08-21 子架构复核修复后才存在的设计（v2 规划 §3.1 原设计无逐段 metadata 复验）；故本文件最后实质修改日为 2026-08-21，:4 日期仍为 2026-08-16
- 为什么现有测试没有阻止它：文档日期无任何自动化哨兵覆盖（哨兵只锁版本串与状态句子串）
- 建议责任点：15A allowlist 内的后续文档触点（或 15G 文档一致性复查）顺手更正为实际最后修改日期；不阻塞验收

除此项外**无 P0/P1/P2 findings**：无阻塞缺陷、无契约违反、无越界改动、无证据造假、退出门全部满足。

## 9. 审核结束状态与最终裁定

- 审核结束后 `git status --short --branch`：`## master...origin/master`；`M docs/architecture.md`、`M docs/supported-formulas.md`、`M math_drawing_assistant/engine/__init__.py`、`M math_drawing_assistant/engine/renderer.py`、`M tests/engine/test_renderer.py`、`M tests/test_stage13_public_api.py`、`M 数学绘图助手_Codex协助开发步骤清单_v0.3.md`；`?? docs/audits/stage-15a-completion-report.md`、`?? tests/engine/test_stage15a_geometry_renderer.py`、`?? tests/engine/test_stage15a_production_boundary.py`、`?? docs/audits/stage-15a-independent-review-notes.md`（本文件，唯一新增写入）。HEAD 保持 `2f9a4ad8c9186acd33936de38e0906b81d72a3bb` 未变
- 最终裁定：**APPROVE Stage 15A**
  - Stage 15A 候选实现可提交总架构师验收（唯一 P3 finding 非阻塞，已登记供后续文档触点更正）
  - 可以在总架构师确认后创建独立 Stage 15A 基线提交
  - 在总架构师验收和基线提交完成前，15B 保持不得开始
