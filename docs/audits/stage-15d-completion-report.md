# Stage 15-D Completion Report：D1/D2/D3 已接受；Stage 15-D 正式完成

日期：2026-08-22（Asia/Shanghai）
执行者：Stage 15-D1 / 15-D2 / 15-D3 主实施 Codex
当前状态：**Stage 15-D1/D2/D3 均已通过独立审核并获总架构师最终接受；Stage 15-D 正式完成**。Stage 15-E 在本提交前仍未开始；本报告不得解读为 Stage 15、正式人工验收、P0-07、M1.5 checkpoint 或核心 MVP 完成。

## 0. P2-1 权威时间线修正（分支 b）

以下时间线取代本报告早期 D1/D2 实施记录中“D2 开始前 D1 已完成独立审核”的错误表述：

1. D1 实施完成时没有可验证的独立审核记录；
2. D2 因流程理解错误，在该独立审核门尚未形成书面证据时先行实施；
3. `docs/audits/stage-15d-independent-review-notes.md` 随后成为 D1+D2 的首次累积独立审核，完整覆盖两子步并裁定 `APPROVE`；
4. 总架构师在该累积补审核之后正式接受 D1+D2；流程偏差已补救，不需要回退已通过审核的代码；
5. 总架构师同时正式追认 `tests/benchmarks/test_m1_benchmark_protocol.py` 的一次性 D1 allowlist 扩展；冻结性能协议、工具、结果和 hash 始终零修改。

本报告后续 D1/D2 小节保留当时的实施与测试事实，但其任何旧“前置审核/接受”叙述均以本节为准。

## 1. 开始基线与前置门

- 分支：`master`
- 开始 HEAD：`3c8984176f77936daf197183b3b0434638b54b21`（`Complete Stage 15-C production chain verification`）
- 开始 `origin/master`：`3c8984176f77936daf197183b3b0434638b54b21`
- 开始 `git status --short --branch`：`## master...origin/master`；无 tracked/untracked 用户修改，仅 Git 报告既有 `.pytest_cache/` 无读取权限
- 开始 `git diff --check`：exit 0，无 whitespace error
- Stage 15-C：completion report 已完成；独立只读审核最终裁定 `APPROVE`；当前 HEAD/提交说明确认已通过总架构师验收
- 仓库存在 `.codegraph/`；在 grep/文件读取前已执行 `codegraph explore`，定位 `ViewportPanel`、`MainWindow`、`AppController`、`AspectRequest`、viewport resolver、revision/request 通道和相关测试
- 已完整读取本步指定的执行章程、architecture 章节、D-003/D-004/D-017、Stage 15-C completion/review、PRD 章节、相关 production 源码、allowlist 测试、只读 resolver/public API/Stage 15-C 测试及根目录旧入口
- 前置结论：Stage 15-C 已验收，开始工作树干净且不存在重叠用户修改，允许开始 15-D1

PRD 域：`数学绘图助手 PRD.md` §6.2、§12、§14、§20.1、§20.4。阶段边界严格为 Aspect 三态与 revision/request 纵向契约，不含 15-D2、15-D3 或 Stage 15-E。

## 2. 本步精确写入 allowlist

用户授权的完整 allowlist：

- `math_drawing_assistant/ui/widgets/viewport_panel.py`
- `math_drawing_assistant/ui/main_window.py`
- `tests/test_app_controller.py`
- `tests/ui/test_main_window.py`
- `tests/ui/test_m1_scene_flow.py`
- `docs/architecture.md`
- `docs/supported-formulas.md`
- `docs/audits/stage-15d-completion-report.md`
- `tests/benchmarks/test_m1_benchmark_protocol.py`（总架构师一次性扩展授权，仅用于拆分 `m1-performance-v1` 历史冻结 `auto` 与 Stage 15-D1 当前 UI 默认 `default` 两项事实）

当前实际写入严格限于其中八个文件：

| 文件 | 当前实际变更 |
|---|---|
| `math_drawing_assistant/ui/widgets/viewport_panel.py` | 增加“按图形默认/自动/等比例”三态，首项 default，更新 accessible description，`aspect_mode()` 异常 data 回退 default |
| `tests/test_app_controller.py` | 钉住 AppController 对 exact DEFAULT/AUTO/EQUAL 的无损请求适配与 auto 模式不复制 disabled bounds |
| `tests/ui/test_main_window.py` | 钉住三态顺序/label/data/默认/可访问性/安全回退、每次真实变化一次 `scene_edited`、UI 无数学解析/第二渲染链依赖 |
| `tests/ui/test_m1_scene_flow.py` | 钉住每次真实比例变化一次 revision、request snapshot、各字段在 submit 线性化点各读一次、production resolver 分类型映射、显式覆盖、manual 四边界优先及既有 M1 预览 |
| `tests/benchmarks/test_m1_benchmark_protocol.py` | 将历史冻结协议仍记录 aspect `auto` 与当前生产 UI 快照 aspect `default` 拆成两个具名事实；未机械保留旧测试含义 |
| `docs/architecture.md` | 修正 §5.2 二态旧描述并登记 15-D1 候选纵向契约和未进入后续阶段的边界 |
| `docs/supported-formulas.md` | 登记三态 UI 映射、Stage 15-C 已验收状态、resolver 责任和 15-D1 candidate 边界 |
| `docs/audits/stage-15d-completion-report.md` | 本执行中报告 |

`math_drawing_assistant/ui/main_window.py` 当前零修改：它已有一次性读取每个 UI 字段并把快照交给 `AppController.create_m1_render_request` 的正确实现；本步用更强测试证明该事实，没有为制造 diff 重写 production。

## 3. 实施结果与边界

- `ViewportPanel.ASPECT_OPTIONS` 的 insertion order 固定为 `default → auto → equal`，显示为“按图形默认 → 自动 → 等比例”；QComboBox 因首项自然默认选中 `default`。
- accessible name 不变，description 已同步覆盖三态。
- `aspect_mode()` 仅返回当前字符串 data；异常非字符串 data 安全回退 `default`。
- 比例下拉仍只有一个 `currentIndexChanged → scene_edited` 连接；未增加 debounce、timer、第二信号或本地 revision。
- MainWindow 仍沿唯一 `scene_edited → _handle_scene_edited → AppController.mark_scene_edited` 通道立即增加 revision；生成时仅采集一次不可变 UI 快照。
- UI 不查看公式/具体图形来选择比例，不解析 DEFAULT，不导入 parser、engine、sampler、renderer 或 Matplotlib。
- AppController、`AspectRequest`、`ResolvedAspect`、`ViewportRequest`、resolver、executor、Actor、bootstrap 和公共结果协议均零修改。
- production 纵向测试确认：显函数/一般直线 DEFAULT→AUTO；圆/椭圆/双曲线/抛物线 DEFAULT→EQUAL；显式 AUTO/EQUAL 优先；manual 四边界及 `ViewportSource.MANUAL` 优先。
- 没有第二条渲染管线，没有 UI 本地 resolver 模拟，没有删除测试、放宽既有断言或增加 skip/xfail。

## 4. 首次失败、原因与实际修正

### 4.1 修改前定向基线

1. 首次执行用户指定定向命令在 pytest collection 前失败：uv 无权读取 `C:\Users\Chen Xinglin\AppData\Local\uv\cache`，exit 1；不是代码/测试失败。
2. 获得沙箱外复用既有 uv cache 的授权后，原命令不变重跑：**159 passed**，0 failed / 0 errors / 0 skipped，26.76s。

### 4.2 新 D1 测试首次红灯

先只增加 D1 契约测试，首次运行三个 allowlist 测试文件得到 **86 passed, 4 failed**：

1. UI 只有“自动/等比例”二态，缺少首项“按图形默认”；
2. 初始为 auto，设置 auto 不是真实变化，因此新信号测试的首次计数为 0；
3. `aspect_mode()` 初始返回 auto，不符合 D1 default；
4. 一次性快照测试在整个 click 完成后统计 `viewport_mode()`，得到 2 次：一次属于 submit 前快照，另一次属于提交后 `_sync_controller_state → set_inputs_enabled` 的显示启用状态读取。

实际修正：前三项仅通过 `ViewportPanel` 的三态、description 和 fallback 最小生产修改解决；第四项不改 production，而把测试观测点收紧到 submit 线性化点，证明交给 Controller 前每个快照字段恰读一次，同时允许提交后的独立显示状态同步。修正后该三文件门为 **90 passed**。

### 4.3 production resolver 纵向测试

新增 exact Actor/Controller/MainWindow/SceneRenderExecutor 纵向矩阵后，`tests/ui/test_m1_scene_flow.py`：**20 passed**，0 failed / 0 errors / 0 skipped，7.08s。

### 4.4 用户指定完整定向门

命令：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='.'; uv run --locked pytest -q -p no:cacheprovider tests/test_app_controller.py tests/ui/test_main_window.py tests/ui/test_m1_scene_flow.py tests/engine/test_viewport_resolver.py tests/engine/test_stage14b1_contracts.py tests/test_stage13_public_api.py
```

首次完成结果：**168 passed**，0 failed / 0 errors / 0 skipped，19.50s。总架构师授权 benchmark 语义拆分后，原命令不变最终复跑：**168 passed**，0 failed / 0 errors / 0 skipped，39.13s。`tests/test_stage13_public_api.py` 保持只读并通过。

### 4.5 全量首次运行与隔离诊断

用户指定全量命令首次结果：**2555 passed, 7 failed, 25 errors**，99.23s。

稳定、可重复的 D1 相关失败只有：

- `tests/benchmarks/test_m1_benchmark_protocol.py::test_frozen_defaults_match_the_real_ui_and_controller` 仍硬编码当前 UI tuple 为 `["auto", "auto", true, 800, 600, 96]`；D1 的真实 tuple 已按冻结需求成为 `["auto", "default", true, 800, 600, 96]`。
- 该用例在独立进程复跑仍为 **1 failed**，精确差异只在 index 1：`default != auto`。
- 此文件不在用户 allowlist，主实施者未修改。

同次全量的另一个首发失败位于 Stage 15-C shutdown timeout 用例；其失败后 `_TIMED_OUT_KEEPALIVES` 留有 1 项，随后导致 Actor/shutdown 测试对 registry count 的 25 个 teardown error 与若干级联 failure。该 Stage 15-C 用例在干净独立进程复跑为 **1 passed**（1.32s），证明它不是稳定 D1 回归；Stage 15-C production/测试文件保持只读。

### 4.6 总架构师一次性扩展授权与实际修正

总架构师随后一次性将 `tests/benchmarks/test_m1_benchmark_protocol.py` 加入 15-D1 allowlist，授权范围只限于拆分两个不同时间语义，禁止修改性能协议、工具、正式结果、hash、场景或阈值。

实际修正不是把旧 tuple 的第二项从 `auto` 机械改成 `default`：

1. 新增独立历史事实测试，直接确认只读 `docs/benchmarks/m1-performance-v1.md` 仍保留阶段 12B 冻结行 `| 比例 | auto | ViewportPanel 首个 aspect 项 |`；
2. 将当前生产事实改为具名 JSON 快照，独立确认 `viewport_mode=auto`、`aspect_mode=default`、grid、图片尺寸和 Controller DPI；
3. benchmark 协议、工具、正式结果、hash、八个场景、调度、阈值及性能结论全部零修改。

该 benchmark 文件首次沙箱内执行在 collection 前因既有 uv cache 权限失败，exit 1；以原命令在已授权环境复跑为 **12 passed**，0 failed / 0 errors / 0 skipped，3.13s。该失败不是代码或测试断言失败。

## 5. 最终门状态

一次性 allowlist 扩展已解除历史协议与当前 UI 快照混用造成的阻塞。最终证据为：

- 授权新增 benchmark 测试文件：**12 passed**，3.13s；
- 用户指定六文件定向门：**168 passed**，39.13s；
- 用户指定全量门：**2563 passed**，0 failed / 0 errors / 0 skipped，83.32s；此前稳定 benchmark 失败已消除，先前隔离通过的 Actor shutdown 偶发超时本次未复现；
- `git diff --check`：通过，无 whitespace error；
- 最终 `git status --short --branch` 与精确 diff/allowlist 审计见下方收尾记录；
- 未执行 commit、push、reset、checkout 或 clean。

最终 `git status --short --branch`：

```text
## master...origin/master
 M docs/architecture.md
 M docs/supported-formulas.md
 M math_drawing_assistant/ui/widgets/viewport_panel.py
 M tests/benchmarks/test_m1_benchmark_protocol.py
 M tests/test_app_controller.py
 M tests/ui/test_m1_scene_flow.py
 M tests/ui/test_main_window.py
?? docs/audits/stage-15d-completion-report.md
```

精确 allowlist 审计确认：七个 tracked diff 加一个 untracked completion report，合计八个实际写入文件，全部位于原始 allowlist 或本轮总架构师一次性扩展项中；`math_drawing_assistant/ui/main_window.py` 保持零 diff。Git 仅另行报告既有 `.pytest_cache/` 无读取权限和工作副本 LF→CRLF 信息提示，二者均未形成仓库变更。

全量绿色只证明该工作树达到 15-D1 候选门；独立复核与总架构师接受仍是后续外部门禁。

## 6. 未进入后续阶段声明

- 历史实施时点仅达到 D1 候选；D2 后续曾因流程理解错误先行实施。D1/D2 现在已经首次累积独立审核并获总架构师正式接受，准确时间线见 §0。
- 本段形成时 15-D3 尚未开始；当前 D3 状态见 §12–§16。Stage 15-E 仍未开始。
- 没有修改 Stage 15-C 两项 P3 观察。
- 没有关闭 P0-07，没有创建 M1.5 checkpoint，没有更新核心 MVP。
- 没有运行或宣称人工 GUI 验收、正式性能或教材证据。
- 没有修改历史 benchmark 协议、工具、正式结果、hash、场景、阈值或 performance 结论。

## 7. Stage 15-D2 开始门与裁定边界

- 分支与 HEAD：`master @ 3c8984176f77936daf197183b3b0434638b54b21`；`origin/master` 同步。
- D2 开始 `git status --short --branch`：D1 的七个 tracked diff 加一个 untracked completion report；无 D2 外来用户修改。D1 基线文件为 `docs/architecture.md`、`docs/supported-formulas.md`、`math_drawing_assistant/ui/widgets/viewport_panel.py`、`tests/benchmarks/test_m1_benchmark_protocol.py`、`tests/test_app_controller.py`、`tests/ui/test_m1_scene_flow.py`、`tests/ui/test_main_window.py` 与本报告。
- 开始 `git diff --check`：exit 0；只有 Git 的 LF→CRLF 与 `.pytest_cache/` 读取权限信息提示，无 whitespace error。
- 上一子步技术基线：D1 定向 **168 passed**、全量 **2563 passed**、`git diff --check` 通过；但当时没有可验证的 D1 独立审核记录，D2 因流程理解错误先行实施。后续累积补审核与接受见 §0。
- 仓库存在 `.codegraph/`；已先用 CodeGraph 定位 `MainWindow.handle_render_result`、`_sync_controller_state`、`PlotPreview`、`StatusPanel`、`prepare_copy_candidate`、`PlotSceneResult`、`ConcretePlotType` 与 warning 传播路径，随后完整读取指定规划/章程/PRD/15-D1 completion、当前源码、测试及 Stage 15-C completion/review。
- F-GUI-01 本轮书面裁定只允许 GUI 对 `no_visible_curve` 使用专属中文句，明确禁止完整 ErrorCode→中文旁路表。裁定未明确授权修改 `app_controller.py`，因此 Controller 与其测试在 D2 保持只读；Stage 15-B F-2 的用户可见 `INVALID_REQUEST` 文案变化只做文档登记。

## 8. Stage 15-D2 实际写入与实现结果

D2 实际写入严格限于：

- `math_drawing_assistant/ui/main_window.py`
- `math_drawing_assistant/ui/widgets/status_panel.py`
- `math_drawing_assistant/ui/widgets/plot_preview.py`
- `tests/ui/test_main_window.py`
- `tests/ui/test_m1_scene_flow.py`
- `tests/ui/test_plot_preview.py`
- `tests/ui/test_stage15d_m1_5_scene_flow.py`
- `docs/architecture.md`
- `docs/supported-formulas.md`
- `docs/audits/stage-15d-completion-report.md`

实现结果：

1. `MainWindow` 只在 `ACCEPTED_SUCCESS` 后替换 accepted PNG、类型、normalized input 与 scene warning；failure/obsolete 不替换。六类固定标签经一套映射和一个 `set_result` 接受点展示，没有分类型状态机。
2. `PlotPreview` 的图片与“图形类型/规范化表达式”摘要同寿命；替换、占位和清除同步处理摘要。stale、rendering-old 与 failed-old 只更新保留标识，不改 accepted artifacts。
3. `StatusPanel` 主状态和持久 warning 分离。warning 按 scene 顺序固定映射五个已发布 code，位于主状态下方并有独立 accessibility；复制 timer 只覆盖主状态，warning 与保留成功图绑定，直到新 accepted success 替换。
4. `no_visible_curve` 保持 production typed failure，GUI 专属句为“当前视口内没有发现曲线，请调整 x、y 范围。”；有旧图时追加一次“本次生成失败，预览仍是上一张成功图片。”。rendering-old 与 stale 使用冻结状态句。
5. fresh/repeated/stale/rendering/failed-current 复制均只调用 `AppController.prepare_copy_candidate` 与 `ClipboardService`。失败与 accepted success revision 相同的情况下，复制反馈仍明确“上一张成功图”。
6. `tests/ui/test_stage15d_m1_5_scene_flow.py` 使用同一个 production bootstrap/Controller/Actor/GUI 对象图证明六类 exact success、实际 DEFAULT aspect、实际 warning、实际 no-visible、旧图保护与复制闭环；没有 fake executor 代替 production 纵向证据。
7. `models/results.py`、`models/errors.py`、`models/state.py`、executor/resolver/Builder/samplers/renderer、Actor/bootstrap/ClipboardService、Stage 13 API 哨兵、Stage 15-C production test 与历史根目录入口均零修改。公开 API、ErrorCode、warning code 与公共结果协议未改变。

## 9. Stage 15-D2 失败、根因与修正记录

1. 首次最小 UI 命令在 collection 前因沙箱无权初始化 `C:\Users\Chen Xinglin\AppData\Local\uv\cache` 失败（exit 1），不是代码/测试失败。按授权复用锁定 uv 缓存后运行。
2. 首次四文件 UI 门：**69 passed, 3 failed**。两项是既有 M1 测试仍断言旧“上一张图”文案或仍 monkeypatch 已被 accepted-summary 入口取代的 `set_png_bytes`；一项既有 production Actor 用例的 10 秒 guard 在该批次超时。修正只更新测试观测点到“上一张成功图”和 `PlotPreview.set_result`，未改 Actor/executor；超时用例隔离复跑 **1 passed**（1.34s），确认无稳定 production 回归。
3. 第二次四文件 UI 门：**70 passed, 2 failed**。一处遗漏的第二个旧复制文案断言再次失败；其后同一 Actor guard 批次超时。根因为前一失败在无 `finally` 的历史用例中提前中止清理，加上批次环境波动；补齐最后一个文案断言后，没有延长 guard、降低断言或修改 production。
4. 两个纵向 UI 文件复跑：**27 passed**（6.17s），包括既有 Actor→GUI 与新增 D2 production 证据；无失败。
5. 所有修正均为新/既有测试观测点与 D2 production 契约对齐。没有删除旧 M1 用例、放宽断言、固定 sleep、skip/xfail 或 fake executor 替代 production。

## 10. Stage 15-D2 最终自动门

用户指定完整定向命令（十文件，含 Controller、GUI、Clipboard、bootstrap、Actor、Stage 15-C production 与 Stage 13 API 哨兵）：

- **157 passed**，0 failed / 0 errors / 0 skipped，25.07s。

全量命令：

- **2571 passed**，0 failed / 0 errors / 0 skipped，86.42s。

最终 Git 静态门：

- `git diff --check`：exit 0，无 whitespace error；仅有工作副本 LF→CRLF 信息提示。
- `git status --short --branch`：`master...origin/master`；D1 保留变更与 D2 allowlist 变更并存。D2 新增的唯一测试为 `tests/ui/test_stage15d_m1_5_scene_flow.py`；completion report 仍为未跟踪候选文件；`.pytest_cache/` 读取权限提示未形成仓库变更。
- `math_drawing_assistant/app_controller.py`、`tests/test_app_controller.py` 的 D2 增量为零；status 中 `tests/test_app_controller.py` 的修改完全属于已接受 D1 基线。

## 11. Stage 15-D2 停止声明

该实施时点只达到 **15-D2 candidate**。D1/D2 后续已经首次累积独立审核并获总架构师接受；当前 D3 状态见下文。Stage 15-E 未开始；未修改 Stage 15-C P3 观察，未关闭 P0-07，未创建 checkpoint，未 commit/push。D1/D2 的 independent review notes 由真正独立只读审核者创建，主实施者未改写。

## 12. Stage 15-D3 开始基线、裁定与 allowlist

- D3 开始日期：2026-08-21；收口日期：2026-08-22（Asia/Shanghai）。
- 分支：`master`；开始 HEAD 与 `origin/master` 均为 `3c8984176f77936daf197183b3b0434638b54b21`。
- 开始累积工作树：D1/D2 的 11 个 tracked modified 加 completion report、D1+D2 independent review notes、D2 新纵向测试 3 个 untracked；`.pytest_cache/` 仅报告既有读取权限提示。
- 开始 tracked `git diff --stat`：11 files changed, 643 insertions(+), 51 deletions(-)；开始 `git diff --check` exit 0，仅 LF→CRLF 信息提示。
- 已按要求在任何 grep/源码读取前用 CodeGraph 定位 `MainWindow`、`PlotPreview`、`StatusPanel`、Controller/Actor/executor/bootstrap/clipboard 调用链；随后读取执行章程、Stage 15-0 裁定、architecture、supported-formulas、D1/D2 与 Stage 15-C completion/review、指定 PRD 章节、GUI 源码/测试和只读 production/API 哨兵。
- 当时的正式裁定：P2-1 选择分支 (b)，准确时间线见 §0；D1/D2 已接受；D3 尚未完成独立审核；Stage 15-D 当时尚未达到正式完成门；Stage 15-E 未开始。该历史状态已由 §17 取代。

D3 完整授权 allowlist：

- `math_drawing_assistant/ui/main_window.py`
- `math_drawing_assistant/ui/widgets/plot_preview.py`
- `math_drawing_assistant/ui/widgets/status_panel.py`
- `tests/ui/test_main_window.py`
- `tests/ui/test_plot_preview.py`
- `tests/ui/test_m1_scene_flow.py`
- `tests/ui/test_stage15d_m1_5_scene_flow.py`
- `docs/manual-test-checklist-m1.5.md`
- `docs/architecture.md`
- `docs/supported-formulas.md`
- `数学绘图助手_Codex协助开发步骤清单_v0.3.md`
- `docs/audits/stage-15d-completion-report.md`

## 13. Stage 15-D3 实际写入与 production 结论

D3 实际写入严格限于 allowlist 的八个文件：

| 文件 | D3 实际变更 |
|---|---|
| `tests/ui/test_plot_preview.py` | 多轮宽/窄尺寸循环，钉住 retained source 内容/尺寸、显示宽高比、相同尺寸稳定性以及只从 source + `KeepAspectRatio` 缩放 |
| `tests/ui/test_main_window.py` | 最小支持窗口固定底部操作区、滚动内容、按钮可达/不重叠、长状态/warning/摘要/占位/旧图标签 word-wrap 证据 |
| `tests/ui/test_stage15d_m1_5_scene_flow.py` | 无旧图 rendering、窄窗口 accepted summary/warning/stale 区域、production 圆 DEFAULT→EQUAL 与反复窗口缩放的两层联合证据 |
| `docs/manual-test-checklist-m1.5.md` | 新建 Stage 15-G 正式人工矩阵；所有项目均为“未执行 / 留待 Stage 15-G” |
| `docs/architecture.md` | 修正 P2-1 时间线、登记 D1/D2 累积接受与 D3 审核前架构证据 |
| `docs/supported-formulas.md` | 同步相同状态与 D3 横切契约，不改变数学支持范围 |
| `数学绘图助手_Codex协助开发步骤清单_v0.3.md` | 同步 D1/D2 已接受、D3 审核前状态、Stage 15-D 未正式完成、Stage 15-E 未开始 |
| `docs/audits/stage-15d-completion-report.md` | 本报告的时间线修正与 D3 实际收口记录 |

D3 对 `math_drawing_assistant/ui/main_window.py`、`plot_preview.py`、`status_panel.py` 的 production 修改均为 **零**：现有实现已经满足固定底部布局、source-image 缩放、`KeepAspectRatio` 和 word-wrap 要求，因此只补强测试和文档证据。`tests/ui/test_m1_scene_flow.py` 也无需 D3 增量；D1/D2 已接受断言未删除或放宽。

所有指定只读文件保持不变，包括 D1+D2 independent review notes、章程、decisions、PRD、Controller、viewport panel、models、engine、Actor、bootstrap、ClipboardService、Stage 13 API 哨兵、Stage 15-C production 测试、一次性 benchmark 文件及全部 benchmark 协议/工具/结果/hash。D3 未重新设计或大规模重写 D1/D2 代码。

## 14. Stage 15-D3 自动化证据

1. `PlotPreview` 在多轮 300×200、宽、竖窄、横宽尺寸之间反复 resize；每一步 retained `source_image` 内容与尺寸均不变，displayed pixmap 保持源图宽高比（仅允许整数像素舍入），回到相同尺寸时 pixmap 尺寸一致；源码门同时钉住 `_source_image`、禁止从 `_image_label.pixmap` 继续缩放，并要求 exact `Qt.AspectRatioMode.KeepAspectRatio`。
2. 最小支持窗口以 `MainWindow.minimumSize()` 为准，不依赖桌面分辨率；滚动内容与固定底部区保持兄弟 ownership，生成/清空/复制按钮可见、位于底部区且彼此不重叠，可增长内容通过滚动条到达。
3. 无图占位、图片、摘要、warning、stale/rendering/failure 提示具有互斥或分离布局；状态、warning、占位、摘要和旧图提示均证明启用 word-wrap。窄窗口 accepted 场景中 preview、summary、warning 和 stale 区域均有正尺寸且不相交。
4. 圆不变形由两层真实证据共同证明：同一 production bootstrap/Controller/Actor/`SceneRenderExecutor` 对 `x^2+y^2=4` 的 DEFAULT 解析为 `ResolvedAspect.EQUAL`；随后窗口反复宽窄 resize 时预览从保留源图保持比例。GUI 未重新计算圆或 aspect。
5. D1/D2 既有状态矩阵保持并通过；D3 新增无旧图 rendering 的占位/复制禁用证据。accepted success、warning success、stale、current failure、`no_visible_curve`、obsolete，以及 fresh/repeated/stale/rendering/failed-current copy 均继续由既有和新增测试覆盖。
6. M1 与 M1.5 继续共享一个 GUI 状态机；没有按 `ConcretePlotType` 增加状态分支，没有 fake executor 冒充 production 纵向证据，没有固定 sleep 或桌面分辨率假设。

## 15. Stage 15-D3 失败、诊断、修正与独立审核验证结果

失败与诊断记录：

- D3 实施前的只读 Qt 几何探针首次在 Python 启动前失败：受管理沙箱无权初始化既有用户级 uv cache（`拒绝访问`，exit 1）。这是环境权限失败，不是代码或测试失败；获得复用既有锁定 uv cache 的授权后原探针成功，确认 640×480 时三个底部按钮均可见且滚动区存在。
- 新增测试实施后首次受影响 GUI 门一次通过；没有 assertion failure、Actor guard timeout、skip/xfail、固定 sleep、延长既有 Actor guard、删除测试或降低断言。production 零修改，因此没有代码缺陷修正记录。

真实运行结果：

| 门 | 结果 |
|---|---|
| 受影响 GUI 门：`test_plot_preview.py test_main_window.py test_stage15d_m1_5_scene_flow.py` | **57 passed**，0 failed / 0 errors / 0 skipped，12.68s |
| 用户指定十文件完整定向门 | **162 passed**，0 failed / 0 errors / 0 skipped，23.78s |
| 全量回归 | **2576 passed**，0 failed / 0 errors / 0 skipped，69.87s |

最终 Git 静态门：

- `git diff --check`：exit 0，无 whitespace error；仅报告工作副本 LF→CRLF 信息提示。
- `git status --short --branch`：`master...origin/master`，累计工作树为 12 个 tracked modified + 4 个 untracked；唯一额外信息是既有 `.pytest_cache/` 读取权限警告。
- `git diff --name-status`：12 个 tracked modified，均属于已接受 D1/D2 或本轮 D3 allowlist；untracked 为 `stage-15d-completion-report.md`、只读 `stage-15d-independent-review-notes.md`、新人工清单和 D2/D3 纵向测试。
- `git diff --stat`：12 files changed, 784 insertions(+), 53 deletions(-)；该 tracked 统计按 Git 语义不包含四个 untracked 文件。
- HEAD 与 `origin/master` 均保持 `3c8984176f77936daf197183b3b0434638b54b21`；没有 commit 或 push。

## 16. 人工清单、历史停止声明与未完成事项

- `docs/manual-test-checklist-m1.5.md` 已建立，覆盖宽/最小/窄窗口、Windows 100%–200% 缩放、logical DPI/DPR、多显示器、六类图形、DEFAULT/AUTO/EQUAL/manual、五类 warning、no-visible、旧图/过期/取消/复制、输入恢复、快速提交、键盘/焦点/触控/高 DPI、M1 回归、断网、目标软件粘贴、关闭和残留进程。
- 所有清单项目均明确标记“未执行 / 留待 Stage 15-G”；D3 未填写 PASS、设备结果、DPI 结果、目标软件兼容结果或正式人工结论。
- D3 未 commit/push，未自动创建或修改独立审核 notes，未进入 Stage 15-E，未关闭 P0-07，未创建 M1.5 checkpoint，未宣称目标设备性能、Stage 15-D 正式完成、M1.5 或核心 MVP 完成。
- 历史实施收口时 D3 是候选；该状态已由下节的独立审核和总架构师最终接受取代。

## 17. 总架构师最终接受

- 总架构师最终裁定：**Stage 15-D3 ACCEPT；Stage 15-D 正式完成**。D1、D2、D3 均已接受。
- D3 独立审核实际绿色结果：受影响 GUI 门 **57 passed**、十文件完整定向门 **162 passed**、全量回归 **2576 passed**；均为 0 failed / 0 errors / 0 skipped。
- `git diff --check` 通过；独立审核未发现 P0、P1 或 P2。
- P3-1、P3-2、P3-3 均登记为非阻塞观察，不阻碍本次接受或 Stage 15-D 正式完成。
- `docs/manual-test-checklist-m1.5.md` 的 Stage 15-G 正式人工清单仍全部未执行；没有填写 DPI、设备、触控、多显示器或目标软件兼容结论。
- Stage 15-E 在本提交前仍未开始；本次提交完成且工作树干净后，才允许由新的独立窗口开始。
- Stage 15、P0-07、M1.5 checkpoint 和核心 MVP 均未完成；正式性能与教材矩阵也仍未完成。本次仅完成 Stage 15-D 文档收口和本地提交，不开始任何后续阶段。
