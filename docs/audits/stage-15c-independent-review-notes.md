# Stage 15-C 独立只读审核 notes

日期：2026-08-21（Asia/Shanghai）
审核者：独立只读审核窗口（Claude Code 会话，非 Stage 15-C 主实施 Codex）
审核基线：`master @ 79be118c6a080915d86488b7b578a2214674e392`（`Complete Stage 15-B unified scene execution`）
审核对象：工作树中 Stage 15-C 全部候选变更（2 个 tracked modified + 2 个 untracked，共 4 个计划写入文件）
依据：本审核授权指令、`docs/stage-15-execution-charter.md` §1/§3/§4/§7/§12/§17、`docs/audits/stage-15b-completion-report.md`、`docs/audits/stage-15b-independent-review-notes.md`、`docs/decisions.md` D-003/D-004/D-007/D-008/D-017、`数学绘图助手 PRD.md` §7.2/§12.3/§14/§20.3

## 1. 基线与开始状态

本窗口开始时逐条实测并记录原始输出：

- `git rev-parse HEAD` → `79be118c6a080915d86488b7b578a2214674e392`，与冻结基线**精确相等**。
- `git rev-parse origin/master` → `79be118c6a080915d86488b7b578a2214674e392`，与基线相等。
- `git log -5 --oneline --decorate` → 首条 `79be118 (HEAD -> master, origin/master) Complete Stage 15-B unified scene execution`；未发现实施者 commit/reset/checkout/clean/push。
- `git status --short --branch --untracked-files=all` → `## master...origin/master` + `M docs/architecture.md` + `M 数学绘图助手_Codex协助开发步骤清单_v0.3.md` + `?? docs/audits/stage-15c-completion-report.md` + `?? tests/test_stage15c_production_chain.py`。恰为 4 个候选文件，无越界写入，无需要保护的用户修改。
- `docs/audits/stage-15c-independent-review-notes.md` 初始不存在（符合"实施者不得预建"要求）。
- `git diff --check` → exit 0；仅有 LF→CRLF 信息性提示，无 whitespace error。
- `git diff --stat` → 2 个 tracked 文件 `13 insertions(+), 3 deletions(-)`；两个 untracked 为新增文件（completion report 与 production-chain 测试）。
- Stage 15-B 已由 `docs/audits/stage-15b-independent-review-notes.md` 正式裁定 **PASS**（F-1 由项目所有者追认关闭，F-2/F-3 为非阻塞 P3）。
- 仓库根存在 `.codegraph/`；已按约定优先经 CodeGraph 定位（`RenderActor`/`AppController`/`SceneRenderExecutor`/`bootstrap`/`render_sampled_curve_png`/`handle_render_result` 调用拓扑）。
- `AGENTS.md` 全树不存在（如实登记）。

## 2. 审核边界声明

本审核为纯只读核查 + 本 notes 唯一写入。未修改任何 production 代码、测试、`docs/architecture.md`、步骤清单、completion report、执行章程、Stage 15-B 历史或任何其他文件；未执行 `git add`/`commit`/`push`/`reset`/`checkout`/`clean`；未实施修复；未进入 Stage 15-D；未运行正式性能、未做人工 GUI 验收、未创建教材证据、未关闭 P0-07、未创建 checkpoint。主实施者的 completion report 与自报结果一律不作为独立证据，全部定向/回归/全量命令由本窗口独立复跑。

## 3. 实际阅读材料

1. `docs/stage-15-execution-charter.md` 全文（§1 优先级、§3 八项冻结契约、§4 唯一目标链、§6 候选文件职责、§7 顺序门禁、§12 15C 边界/allowlist/退出、§17 证据真实性）。
2. `docs/audits/stage-15b-completion-report.md`、`docs/audits/stage-15b-independent-review-notes.md`（核验 15B PASS 与 F-1/F-2/F-3 状态）。
3. `docs/audits/stage-15c-completion-report.md`（仅作被核验对象，不作证据）。
4. `数学绘图助手 PRD.md` §7.2、§12.3、§14、§20.3。
5. `docs/decisions.md` D-003、D-004、D-007、D-008、D-017。
6. `docs/architecture.md` 状态行与新增 §7.12 diff；步骤清单 diff。
7. production 源码逐文件：`bootstrap.py`、`app_controller.py`、`workers/render_actor.py`、`workers/cancellation.py`、`engine/scene_executor.py`、`engine/renderer.py`（含 import 段与 `_render_png` 全函数）、`models/results.py`、`ui/main_window.py`（`handle_render_result`）、根目录旧 `main_window.py`/`plot_engine.py`。
8. 新测试 `tests/test_stage15c_production_chain.py` 全文（844 行）逐行审阅。
9. `tests/conftest.py`（offscreen 平台 autouse 夹具）。

## 4. 候选 diff 与 allowlist 核验

冻结实施方案（本审核授权 §五）预期恰好 4 个候选写入文件，实际工作树**逐项相等**：

| 预期文件 | 实际状态 |
|---|---|
| `tests/test_stage15c_production_chain.py` | `??` 新增（未跟踪） |
| `docs/architecture.md` | `M`（状态行 + 新增 §7.12） |
| `数学绘图助手_Codex协助开发步骤清单_v0.3.md` | `M`（首页日期 + Stage 15 状态行） |
| `docs/audits/stage-15c-completion-report.md` | `??` 新增（未跟踪） |

以下三个 production 文件相对基线**零 diff**（`git diff --name-only -- <files>` 空输出实测）：

- `math_drawing_assistant/app_controller.py`
- `math_drawing_assistant/workers/render_actor.py`
- `math_drawing_assistant/bootstrap.py`

以下七个既有测试文件相对基线**零 diff**（同法实测）：

- `tests/test_app_controller.py`、`tests/test_bootstrap.py`、`tests/workers/test_render_actor.py`、`tests/workers/test_render_actor_agg_probe.py`、`tests/workers/test_render_actor_shutdown.py`、`tests/ui/test_m1_scene_flow.py`、`tests/test_stage13_public_api.py`

无越界写入，无删除/放宽既有断言，无新增 skip/xfail（对全仓 grep `skip|xfail|time.sleep|sleep` 在新测试文件内零命中）。completion report 的 allowlist 描述与上述事实一致，且正确未创建 `docs/audits/stage-15c-independent-review-notes.md`。

## 5. Production 组合与对象身份

`test_bootstrap_builds_the_exact_single_production_object_graph` 真实运行 `bootstrap.create_application_runtime` 并断言 exact type 与对象 identity：

- `type(runtime.executor) is SceneRenderExecutor`、`type(runtime.actor) is RenderActor`、`type(runtime.controller) is AppController`；
- `runtime.actor._worker._executor is runtime.executor`（identity）、`runtime.controller._render_submitter is runtime.actor`、`runtime.window.controller is runtime.controller`；
- `runtime.actor._worker.thread() is runtime.actor._thread`；Actor 实例 dict 内恰有且仅有 `_owner_thread` 与 `_thread` 两个 `QThread`，二者区分；owner 为 GUI 主线程，worker 线程不同。

`test_fresh_bootstrap_import_does_not_load_legacy_root_entry_points` 用 fresh subprocess（`sys.executable -c`、明确 `cwd=project_root`、`QT_QPA_PLATFORM=offscreen`、`timeout=30`、`check=False` + 检查 returncode/stderr）证明导入 production bootstrap 后 `sys.modules` 中无根目录 `main_window`/`plot_engine`，且 `math_drawing_assistant.ui.main_window` 已加载。这是运行行为证明，非源码字符串比对。

以上覆盖 §六.1 全部 bootstrap 契约。

## 6. Token、latest-wins 与双门禁

- **Token identity**：`test_explicit_and_geometry_use_one_actor_thread_and_release_agg_resources` 用 `threading.local` 在 actor 线程内贯通 executor→renderer，断言 `observe_renderer` 收到的 `kwargs["cancellation_probe"] is render_context.token`；`executor_calls`/`renderer_calls` 逐一以 `is`/列表相等核对 token 与 Controller `_current_render_token` 同一对象。P3-6 测试进一步用 `ControllerSamplerGateToken` 子类钉住 Controller→mailbox→executor→sampler 同一 token identity（`created_tokens == [token]`、`sampler_token is token`、`executor_token is token`、`controller._current_render_token is token`、`mailbox.current_token is token`），且子类仍通过 Actor 的 `isinstance(token, CancellationToken)` 门。§六.2 成立。
- **latest-wins**：`test_production_latest_wins_skips_middle_and_publishes_only_final` 只阻塞第一份 exact executor 调用，依次提交 first/second/final 后释放。实测断言 first/second token 均取消、final 未取消、`entered_ids == [first, final]`、second 不进入 executor、`max_active == 1`、first 返回中性取消 sentinel（success=False/error=None/png_bytes=None/item_results=()）且被 Actor gate 抑制、唯一 public result 与 Controller 最终接纳均为 final。同步用 `Event` + `QEventLoop` guard，无固定 sleep。§六.4 成立。
- **双门禁**：`test_prelinearized_real_result_is_rejected_by_each_controller_gate` 参数化 `request_id`/`scene_revision`。用 direct connection 在 worker 内部 `_result_ready` 处先拿到真实结果对象（在 mailbox completion decision 之后、GUI queued relay 处理之前），再分别提交新 request 或 `mark_scene_edited()`。断言 `dispositions[0].result is worker_result`（identity，非伪造结果）、判 `IGNORED_OBSOLETE`、`retained_before/after` 均为 baseline、revision 路径还验证 same-request old-revision 正确清空 foreground context。§六.5、§六.6 成立。

## 7. Matplotlib 线程和资源释放

`test_explicit_and_geometry_use_one_actor_thread_and_release_agg_resources`：

- `y=x^2` → `EXPLICIT_FUNCTION`、`x^2+y^2=4` → `CIRCLE`，均 success 且 PNG 非空（`_PNG_SIGNATURE` 校验）。
- executor、renderer、`Figure`、`FigureCanvasAgg`、`BytesIO` 的 `get_ident()` 全部等于唯一 worker 线程，且该线程 ≠ GUI 主线程；`renderer_max_active == 1`。
- `_ResourceTracker` 用 `weakref` + `get_ident()` 子类 monkeypatch `renderer.Figure`/`renderer.FigureCanvasAgg`/`renderer.BytesIO`（已核对 renderer.py 顶层 `from io import BytesIO`/`from matplotlib.backends.backend_agg import FigureCanvasAgg`/`from matplotlib.figure import Figure`，故 monkeypatch 命中 `_render_png` 内部未限定引用）。断言每个 BytesIO 关闭、GC 后 Figure/Canvas/BytesIO weakref 全释放。
- continuation `y=x+1` 证明同一 Actor/exact executor 随后仍能继续成功。§六.3 成立。测试未访问 GUI 私有展示细节（不触 `_plot_preview`/`_status_panel`），无 15-D 提前实施。

## 8. 异常、取消与 shutdown

- **异常脱敏与恢复**：`test_current_failures_are_redacted_preserve_baseline_and_recover` 在 exact production executor 边界注入一次含 secret/路径/公式/traceback 字样的 `RuntimeError`，wrapper 对非注入输入调用原 `SceneRenderExecutor.execute`。typed `log(x)` → `LOG_REQUIRES_BASE`；注入 → Actor 映射 `INTERNAL_ERROR`；`last_successful_result` 全程保持 baseline；`notice is internal_failure.error`（identity）；`repr(result)+repr(error)+repr(notice)` 不含 forbidden 字符串；`all(executor is runtime.executor ...)` 且 `_worker._executor is runtime.executor`；随后 `x^2+y^2=4` 恢复成功。§六.7 成立。
- **shutdown**：`test_production_shutdown_timeout_closes_gates_and_suppresses_late_result` 只把测试 runtime Actor 的 `_shutdown_timeout_ms` 置 0 触发真实 timeout 路径（不改 production）。实测 current/pending token 取消、result/submission gate 关闭、pending 不进入 executor、`shutdown()` 返回 False、`_timed_out_keepalive_count()==1`、释放 current 后线程结束、keepalive 归零、无晚到 public result（`public_results == [baseline]`）、后两次 `shutdown()` 返回 True、Qt message handler 未捕获 `QThread: Destroyed while thread is still running`。既有 `test_render_actor_shutdown.py`（33 passed）继续覆盖细粒度关闭矩阵，二者共同满足 §六.8。

## 9. P3-6 真实取消链

`test_real_geometry_cancellation_keeps_one_token_and_no_partial_result` 参数化 oval `x^2/9+y^2/4=1`、hyperbola `x^2/9-y^2/4=1`、parabola `x^2=4*y`。用 `CancellationToken` 子类在真实 sampler 首个 poll 暂停，`cancel_active_task()` 后释放。实测：sampler outcome exact type `SamplingCancelled`、`item_id` 精确等于 production item_id、`dataclasses.fields == ["item_id"]`、无 x/y/ranges/warnings/diagnostics；executor 返回九字段中性取消 sentinel（success=False/error=None/png_bytes=None/item_results=()/resolved_viewport=None/warnings=()/diagnostics=None/elapsed_ms=()）；Actor 不发布取消结果（`public_results == [baseline]`）；Controller 保留旧成功图。本步未重复 Stage 15-B 逐 poll 穷举（章程允许）。§六.9 成立。

## 10. 文档和 completion report 核验

- `docs/architecture.md`：状态行将 15B 改为"已独立审核 PASS"、15C 写"真实 production 组合候选实施已完成并等待独立审核/总架构师验收"、15D 及后续"尚未开始"；新增 §7.12 准确描述 15C 候选组合契约，并明确"不冒充人工验收或正式性能、不处理 F-2/F-3、不关闭 P0-07、不创建 checkpoint"。未改写 15A/15B 历史契约（diff 仅新增 §7.12 + 状态行）。日期 2026-08-21 = 实际实施日。
- 步骤清单：首页日期同步为 2026-08-21；Stage 15 状态行登记 15A APPROVE、15B 最终 PASS、15C 候选完成待审核、15D 未开始，并声明不表示 GUI 闭环/正式性能/教材/P0-07/checkpoint/核心 MVP 完成。未扩大 15C 文件授权。
- completion report 与实际事实核对：起始基线、PRD 域、allowlist、实际写入文件、production 零修改、`git diff --check` 通过、tracked stat 13 insertions/3 deletions、未创建 review notes、未 commit/push、未进入 15-D/15-E/15-F/15-G、未运行正式性能/人工验收、未关闭 P0-07、未创建 checkpoint——全部与本窗口实测一致。其自报测试计数与下述本窗口独立复跑一致（详见 §11）。

## 11. 独立运行命令与真实结果

全部命令前缀 `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. uv run --locked pytest -q -p no:cacheprovider`（Git Bash 适配；`tests/conftest.py` autouse 设置 `QT_QPA_PLATFORM=offscreen`）。每次运行另输出一条 `VIRTUAL_ENV=C:\ProgramData\anaconda3` 与 `.venv` 不匹配的**信息性提示**（uv 仍使用 `.venv`，不影响结果）。

| 门 | 命令（相对前缀） | 本窗口真实结果 |
|---|---|---|
| 小门 1 | `tests/test_app_controller.py tests/workers/test_render_actor.py` | **55 passed**，0 failed / 0 errors / 0 skipped，0.45s |
| 小门 2 | `tests/workers/test_render_actor_shutdown.py` | **33 passed**，0 failed / 0 errors / 0 skipped，0.81s |
| 小门 3 | `tests/workers/test_render_actor_agg_probe.py` | **9 passed**，0 failed / 0 errors / 0 skipped，4.43s |
| 小门 4 | `tests/test_bootstrap.py tests/test_stage15c_production_chain.py` | **13 passed**（新文件 11 + bootstrap 2），0 failed / 0 errors / 0 skipped，4.41s |
| 章程定向门（8 文件） | `test_app_controller.py test_bootstrap.py test_render_actor.py test_render_actor_agg_probe.py test_render_actor_shutdown.py test_stage15c_production_chain.py test_m1_scene_flow.py test_stage13_public_api.py` | **133 passed**，0 failed / 0 errors / 0 skipped，15.97s |
| 全量 | 全仓库 | **2553 passed**，0 failed / 0 errors / 0 skipped，128.52s |
| diff 检查 | `git diff --check` | exit 0（仅 LF→CRLF 信息提示） |

一次通过、无失败、无重试。全量耗时与 completion report 的 89.22s 不同，属机器负载差异，计数一致（2553 精确相等）。

## 12. Findings

无未关闭 P0/P1/P2 finding。无安全/数据破坏/进程崩溃/证据造假；无冻结契约违反；无 production/allowlist 越界；无错误成功或旧图被覆盖；无线程/资源泄漏；新测试确实使用当前 production executor/Actor/Controller/bootstrap；定向与全量独立全绿；`git diff --check` 通过；文档与 completion report 与事实一致。

P3 观察（非阻塞）：

- **P3-1：Actor 线程内 wrapper 断言可被 production 异常边界吞掉**。位置 `tests/test_stage15c_production_chain.py:302-306`、`:403`、`:630`、`:723`、`:769-770`。这些 monkeypatch wrapper 在 actor 线程内运行，若其 `assert`（如 `release_first.wait()` guard 超时、`cancellation is render_context.token` 身份断言）失败，会抛 `AssertionError`，被 production `_drain_mailbox`/`_execute_task`（`render_actor.py:161-171`、`:174-203`）的 `except Exception` 捕获并映射为 `_internal_failure`，从而以"下游结果失配/guard 超时"而非直接的断言信息呈现。属 actor 边界测试的固有特性，且各测试均另有 GUI 线程侧的下游断言兜底，不削弱所证契约；登记为后续测试可读性观察。
- **P3-2：`_ResourceTracker.assert_released()` 无非空 guard**。位置 `tests/test_stage15c_production_chain.py:262-269`。若未来 `renderer.py` 把 `Figure`/`FigureCanvasAgg`/`BytesIO` 改为非模块全局名（本地别名），monkeypatch 会静默失效、`created_buffer_ids` 为空，`assert_released()` 与线程归属断言将空集通过（空真），使资源释放证明被削弱而不报错。当前已核对 renderer.py 顶层 import 与 `_render_png` 未限定引用完全匹配，故为纯健壮性观察，非当前缺陷。

退回责任：无。

## 13. 最终 Git 状态

`## master...origin/master`；`M docs/architecture.md`、`M 数学绘图助手_Codex协助开发步骤清单_v0.3.md`；`?? docs/audits/stage-15c-completion-report.md`、`?? tests/test_stage15c_production_chain.py`、`?? docs/audits/stage-15c-independent-review-notes.md`（本文件，唯一新增写入）。HEAD 保持 `79be118c6a080915d86488b7b578a2214674e392` 未变。`git diff --check` exit 0。

## 14. 最终裁定

**APPROVE**

- 实际 diff 严格符合冻结范围（恰 4 个候选文件）；
- production 三文件（app_controller.py / render_actor.py / bootstrap.py）零修改；
- 新测试确实使用当前 production executor、Actor、Controller、bootstrap；
- 所有 Stage 15-C 契约（bootstrap 对象图、token identity、latest-wins、双门禁、旧成功结果保护、异常脱敏与恢复、shutdown、P3-6 真实取消链）均有有效自动证据；
- 无固定 sleep、无测试顺序依赖、无 mock/fake executor 替代 production；
- 定向门独立全绿（133 passed）、全量门独立全绿（2553 passed）、`git diff --check` 通过；
- 文档与 completion report 与实际事实一致；
- 无未关闭 P0/P1/P2 finding；存在 2 条非阻塞 P3 观察；
- 所有测试一次通过，未发生重试；
- 本窗口未修改候选代码或测试、未进入 Stage 15-D、未运行正式性能或人工验收、未 commit/push。

当前停止，等待总架构师验收。
