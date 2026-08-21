# Stage 15-C Completion Report：真实 Production 组合与回归证明

日期：2026-08-21（Asia/Shanghai）
执行者：Stage 15-C 主实施 Codex
规划依据：`docs/stage-15-execution-charter.md`、Stage 15-B completion/independent review 与本阶段获批实施提示词

## 1. 开始基线与范围

- 分支：`master`
- 开始 HEAD：`79be118c6a080915d86488b7b578a2214674e392`（`Complete Stage 15-B unified scene execution`）
- 开始 `origin/master`：`79be118c6a080915d86488b7b578a2214674e392`
- 开始工作树：tracked worktree 干净；无待保护的用户修改；`tests/test_stage15c_production_chain.py` 不存在
- `git diff --check`：开始时通过
- Stage 15-B completion report 已完成；独立审核 notes 最终裁定 **PASS**，F-1 已关闭
- 仓库存在 `.codegraph/`，并在源码定位前执行了章程指定的 `codegraph explore "RenderActor AppController SceneRenderExecutor bootstrap latest-wins cancellation request revision shutdown production chain"`
- 仓库全树未发现 `AGENTS.md`；实施期间按会话提供的仓库 CodeGraph 指令执行
- PRD 域：`数学绘图助手 PRD.md` §7.2、§12.3、§14、§20.3

## 2. 完整授权 allowlist 与实际写入

本阶段完整授权 allowlist：

- `math_drawing_assistant/app_controller.py`
- `math_drawing_assistant/workers/render_actor.py`
- `math_drawing_assistant/bootstrap.py`
- `tests/test_app_controller.py`
- `tests/test_bootstrap.py`
- `tests/workers/test_render_actor.py`
- `tests/workers/test_render_actor_agg_probe.py`
- `tests/workers/test_render_actor_shutdown.py`
- `tests/test_stage15c_production_chain.py`
- `docs/architecture.md`
- `数学绘图助手_Codex协助开发步骤清单_v0.3.md`
- `docs/audits/stage-15c-completion-report.md`

最终实际写入严格限于计划子集：

| 文件 | 实际变更 |
|---|---|
| `tests/test_stage15c_production_chain.py` | 新增 exact production bootstrap/executor/Actor/Controller 组合、线程/资源、latest-wins、双 obsolete 门禁、失败恢复、shutdown 与三类 geometry cancellation 测试 |
| `docs/architecture.md` | 登记 Stage 15-B 最终 PASS、Stage 15-C 候选 production 组合证据及未进入 15-D 的边界 |
| `数学绘图助手_Codex协助开发步骤清单_v0.3.md` | 更新实际日期与 Stage 15-B/15-C/15-D 准确状态 |
| `docs/audits/stage-15c-completion-report.md` | 本报告 |

以下三份 production 文件零修改：`math_drawing_assistant/app_controller.py`、`math_drawing_assistant/workers/render_actor.py`、`math_drawing_assistant/bootstrap.py`。五份既有 Stage 15-C 单元测试文件也全部零修改；没有删除测试、放宽既有断言或增加 skip/xfail。

## 3. 新增 production-chain 测试证明

`tests/test_stage15c_production_chain.py` 使用 exact `SceneRenderExecutor`、`RenderActor`、`AppController` 与 `bootstrap.create_application_runtime`；观测 wrapper 均调用原 production 方法，不使用 fake/mock executor。同步只使用 `threading.Event`、Qt signal、`QEventLoop` 和带超时 guard 的条件轮询，没有固定 `time.sleep()`，也不依赖测试顺序。

### A. exact bootstrap 对象图与旧入口禁令

- runtime 中 executor/Actor/Controller 分别为 exact production type；Actor worker 持有 runtime executor，Controller submitter 为 runtime Actor，Window 持有 runtime Controller；worker 只移动到 Actor 的唯一 dedicated `QThread`，并与 GUI owner thread 区分；cleanup 后线程停止且 shutdown 可重复。
- fresh Python subprocess 导入 production bootstrap 后，运行时 `sys.modules` 证据表明根目录 `main_window` 与 `plot_engine` 均未加载，而 `math_drawing_assistant.ui.main_window` 已加载。

### B. explicit、geometry、Actor 线程与资源释放

- `y=x^2` 与 `x^2+y^2=4` 均由 Controller 正式创建请求并通过 runtime Actor；结果 concrete type 分别为 `EXPLICIT_FUNCTION` 与 `CIRCLE`，PNG 非空。
- executor 收到的 token 与 Controller 当前 token 对象 identity 相同；executor、unified renderer、Figure、FigureCanvasAgg、BytesIO 全在同一非 GUI Actor worker thread；renderer `max_active == 1`。
- 每个 BytesIO 都关闭；GC 后 Figure/Canvas/BytesIO weakref 全部释放；同一 Actor 与 exact executor 随后继续完成下一张真实成功图。

### C. production latest-wins 与结果门

- 只阻塞第一份 exact executor 调用，依次提交 first/second/final 后再释放；first 调用原 executor 并观察取消，final 调用原 executor 成功。
- first token、被替换的 pending second token 均取消，final token 未取消；executor 严格只进入 `[first, final]`，最大活跃数为 1。
- first 的中性取消结果被 Actor token/result gate 抑制，second 从未进入 executor，唯一 public result 与 Controller 最终接纳结果均为 final。

### D. request_id 与 scene_revision 双门禁

- worker 内部结果 signal 使用 direct connection，先观察真实 executor 结果已通过 mailbox completion decision，再故意暂不处理 GUI queued relay。
- 分别在线性化后提交新 request、或对同 request 调用 `mark_scene_edited()`；旧结果均由原 `AppController.handle_render_result` 判为 `IGNORED_OBSOLETE`。
- request/revision 两种过期路径在处理旧成功结果前后均保持 retained baseline identity；Controller 结果处理未被重复调用。

### E. 当前失败、异常脱敏与恢复

- 先保留真实成功 baseline，再运行真实 typed `LOG_REQUIRES_BASE` failure、对 exact executor 注入一次包含秘密/路径/公式/traceback 字样的 `RuntimeError`，最后运行真实 geometry success。
- typed 与 Actor 映射的 internal failure 都是 `HANDLED_CURRENT_FAILURE` 且不覆盖 baseline；公开 ErrorInfo、result repr 与 Controller notice 不包含注入内容。
- exception 后 Actor 与同一 production executor identity 继续消费并由 Controller 接纳最终成功。

### F. shutdown timeout、submission/result gate 与 keepalive

- 建立第一份 exact executor 的确定性阻塞，提交一个 pending，并仅把测试 runtime Actor 的 shutdown timeout 改为 0 以触发现有 timeout 路径。
- Controller shutdown 取消 current/pending、进入 `SHUTTING_DOWN` 并清除 request context；Actor submission/result gate 关闭，pending 不进入 executor，第一次 shutdown 返回 `False`，shutdown 后拒绝新任务。
- 释放 current 后无晚到 public result；QThread 最终结束，timed-out keepalive registry 归零，后两次 shutdown 均返回 `True`；Qt message handler 未观察到 `QThread: Destroyed while thread is still running`；retained baseline 未被取消或晚到结果覆盖。

### G. P3-6 三类 geometry 真实取消链

- 参数化运行 oval `x^2/9+y^2/4=1`、hyperbola `x^2/9-y^2/4=1`、parabola `x^2=4*y`。
- Controller 创建的 token 被替换为 `CancellationToken` 子类，仍通过 Actor 正式 `isinstance` 门；production geometry sampler wrapper 只负责 arm token 并调用原 sampler，在真实 sampler cancellation poll 处暂停。
- Controller、Actor mailbox、executor、sampler 观察到同一 token identity。每类 sampler outcome exact type 均为 `SamplingCancelled`，只含精确 production item ID；不存在 x/y/ranges/warnings/diagnostics 或 partial sampled result。
- `SceneRenderExecutor` 返回九字段中性取消 sentinel；Actor 不发布取消结果；Controller 保留上一张成功图。本阶段没有重复 Stage 15-B 的逐 poll 点穷举。

## 4. 实际测试命令与结果

所有 pytest 命令均使用：`PYTHONDONTWRITEBYTECODE=1`、`PYTHONPATH=.`、`uv run --locked pytest -q -p no:cacheprovider`。受管理沙箱最初两次无法读取既有用户级 uv cache，均在 pytest collection 前退出；获得沙箱外既有 uv cache 授权后按同一命令执行，未安装或更新依赖。

| 门 | 实际结果 |
|---|---|
| 新文件首跑：`tests/test_stage15c_production_chain.py` | **10 passed, 1 failed**，6.54s；对象图测试把 GUI owner QThread 与 dedicated worker QThread 混为一个列表断言，随后仅在新文件明确区分两者 |
| 新文件修正复跑 | **11 passed**，0 failed / 0 errors / 0 skipped，5.95s |
| 中间门：`test_app_controller.py test_render_actor.py` | **55 passed**，0 failed / 0 errors / 0 skipped，0.60s |
| 中间门：`test_render_actor_shutdown.py` | **33 passed**，0 failed / 0 errors / 0 skipped，1.24s |
| 中间门：`test_render_actor_agg_probe.py` | **9 passed**，0 failed / 0 errors / 0 skipped，4.49s |
| 中间门：`test_bootstrap.py test_stage15c_production_chain.py` | **13 passed**，0 failed / 0 errors / 0 skipped，5.80s |
| 第一次章程完整定向门（8 文件） | **133 passed**，0 failed / 0 errors / 0 skipped，19.24s |
| 第一次全量 | **2550 passed, 3 failed**，0 errors / 0 skipped，116.40s；三项均为后续 Stage 1 import 哨兵发现新测试 fixture 留有 QApplication instance |
| 隔离修复复验：`test_stage15c_production_chain.py test_stage1_bootstrap.py` | **20 passed**，0 failed / 0 errors / 0 skipped，5.97s；只在新文件增加自有 QApplication 的确定性销毁 |
| QApplication 隔离修复后章程完整定向门（8 文件） | **133 passed**，0 failed / 0 errors / 0 skipped，12.40s |
| QApplication 隔离修复后全量 | **2553 passed**，0 failed / 0 errors / 0 skipped，92.95s |
| renderer request/token identity 观测加强后新文件复跑 | **11 passed**，0 failed / 0 errors / 0 skipped，5.82s |
| 最终章程完整定向门（8 文件） | **133 passed**，0 failed / 0 errors / 0 skipped，15.37s |
| 最终全量 | **2553 passed**，0 failed / 0 errors / 0 skipped，89.22s |
| 最终 diff 门：`git diff --check` | **通过（exit 0）**；仅有 LF→CRLF 信息性提示，无 whitespace error |
| 最终范围门：`git status --short --branch`、`git diff --name-only`、`git diff --stat`、`git ls-files --others --exclude-standard` | 分支仍为 `master...origin/master`；恰有 2 个 tracked modified + 2 个 untracked，合计仅四个计划写入文件；tracked stat 为 13 insertions / 3 deletions |

两次发现均为新测试自身问题；production、既有测试与只读依赖均未修改。没有通过删除测试、降低断言、固定 sleep、fake/mock executor 或改变取消结果来取得绿色结果。

## 5. 只读依赖与范围声明

以下 Stage 15-C 只读依赖全部零修改：`math_drawing_assistant/engine/scene_executor.py`、`math_drawing_assistant/engine/renderer.py`、`math_drawing_assistant/models/results.py`、`math_drawing_assistant/workers/cancellation.py`、`math_drawing_assistant/ui/main_window.py`、`tests/engine/test_scene_executor.py`、`tests/ui/test_m1_scene_flow.py`、`tests/test_stage13_public_api.py`、`docs/stage-15-execution-charter.md`、`docs/decisions.md`、`数学绘图助手 PRD.md`、Stage 15-B completion/review 文件、Stage 14/15A 历史记录、`docs/supported-formulas.md` 与 `联网确认.md`。

- 没有处理 Stage 15-B independent review 的 F-2/F-3。
- 没有进入 Stage 15-D、15-E、15-F 或 15-G。
- 没有运行正式性能测量，也没有执行或宣称 GUI 人工验收。
- 没有创建教材证据，没有关闭 P0-07，没有创建 checkpoint。
- 没有创建、预填或修改 `docs/audits/stage-15c-independent-review-notes.md`。
- 没有执行 `git add`、`git commit` 或 `git push`。

## 6. 停止声明

Stage 15-C 的 production 代码审查、新增组合测试、文档同步、最终定向门、最终全量门与 completion report 已完成。当前状态只为**候选完成**；立即停止，等待真正独立只读审核与总架构师验收。Stage 15-D 尚未开始。
