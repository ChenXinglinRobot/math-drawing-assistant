# M1 性能测量协议：m1-performance-v1

状态：已冻结；尚未运行正式测量。
协议版本：`m1-performance-v1`
工具版本：`m1-benchmark-tools-v1`
调度 seed：`20260801`
阶段 12A 基线提交：`645a3eaa0dd58ab1937930365008c29a17af0dfe`（`feat: add clipboard flow and runtime factory`）

本文冻结阶段 12 的 M1 性能测量口径。它只适用于 Windows 11 开发参考机，不能外推为课堂设备、教学一体机或 Windows 10 性能结论。本次阶段 12B 只冻结协议、工具和工具测试，不生成性能通过/失败结论。

## 1. 真实生产接口与组装

阶段 12A 提供的共享正式 factory 是：

```python
create_application_runtime(application: QApplication) -> _ApplicationRuntime
```

它只组装一套生产对象：

```text
SceneRenderExecutor()
→ RenderActor(executor)
→ AppController(render_submitter=actor)
→ ClipboardService(application.clipboard())
→ MainWindow(controller=controller, clipboard_service=clipboard_service)
→ actor.result_ready.connect(window.handle_render_result)
```

`_ApplicationRuntime` 同时强引用 `executor`、`actor`、`controller`、`clipboard_service` 和 `window`。热基准必须且只能调用这个 factory。工具启动后验证：

```text
runtime.actor._worker._executor is runtime.executor
runtime.controller._render_submitter is runtime.actor
runtime.window._controller is runtime.controller
```

任一不成立即为 harness error；不得创建 test-only Actor、第二个 Executor，或在 benchmark 中复制组装逻辑。

阶段 12A 的实际复制接口为：

```python
@dataclass(frozen=True, slots=True)
class CopyCandidate:
    png_bytes: bytes
    request_id: int
    scene_revision: int
    is_stale: bool

AppController.prepare_copy_candidate() -> CopyPreparation
ClipboardService.write_candidate(candidate: CopyCandidate) -> ClipboardWriteResult
```

`ClipboardService` 构造参数是具有 `setImage(QImage)` 的 `ClipboardBackend`，写入方法只能在 GUI 线程调用。benchmark 允许该 service 留在正式依赖图中，但永远不发出 `copy_requested`，不点击复制按钮，不调用 `prepare_copy_candidate` 或 `write_candidate`，不调用 QClipboard 读写方法，也不连接 clipboard change signal。热批次前后都要求 `ClipboardService.write_history == ()`。

## 2. 现有内容盘点

冻结前仓库没有 `benchmarks/`、startup probe 或 M1 性能协议。现有性能相关内容只有：

- PRD §7.2 的暂定启动、绘图与 GUI 响应阈值；
- `docs/performance-environment.md` 的阶段 5 开发机证据基线，明确没有 P50/P95；
- `PlotSceneResult.elapsed_ms` 的阶段诊断字段；
- 阶段 10/11 的 Actor/Agg 测试和历史 GUI heartbeat 证据，它们不是正式性能测量；
- `联网确认.md` 的临时 `MPLCONFIGDIR` 测试策略和开发参考机边界。

因此本工具不是既有 benchmark 的平行副本。

## 3. 正式 UI 默认值

正式 `ViewportPanel` 和 `AppController` 的当前默认值与阶段 12B 输入一致，无差异：

| 参数 | 冻结值 | 真实来源 |
|---|---:|---|
| 视口 | `auto` | `ViewportPanel` 首个 mode 项 |
| 比例 | `auto` | `ViewportPanel` 首个 aspect 项 |
| 网格 | `true` | grid checkbox 初始 checked |
| 图片宽度 | `800` | width spin box |
| 图片高度 | `600` | height spin box |
| DPI | `96` | `AppController.M1_DEFAULT_DPI` |
| 图例 | `false` | `AppController.M1_SHOW_LEGEND` |

工具从真实控件读取这些值，不在 benchmark 内重建请求或覆盖生产默认值。

## 4. 八个冻结 M1 场景

以下精确字符串来自当前 `docs/supported-formulas.md` 的已批准 M1 语法、正向样例或正式采样诊断。协议提交后、正式测量前不得替换。

| ID | 精确输入 | 选择理由 | 覆盖路径 |
|---|---|---|---|
| `identity` | `x=y` | 文档明确支持的左右直接互换恒等/线性基线 | equation split、直接 y-side swap、普通连续采样 |
| `quadratic` | `x^2` | 典型二次多项式和转折点 | power AST、非线性 auto viewport、方向变化 |
| `reciprocal` | `1/x` | 典型反比例和垂直渐近线 | division、非有限值、断线 |
| `restricted_domain` | `ln(x)` | 定义域受限函数 | log executor、partial-domain warning、可见片段 |
| `trigonometric` | `sin(x)` | 常见三角函数 | trig executor、多单调段 |
| `exponential` | `exp(x)` | 已批准指数写法 | exp executor、陡峭但连续曲线 |
| `logarithmic` | `log(x,10)` | 已批准显式底数对数 | 两参数 log 验证与 executor、自动视口 |
| `dense_oscillation` | `sin(1000*x)` | supported-formulas 中冻结的密集振荡正例 | 正式采样诊断与 warning 传播 |

不以只选择简单公式换取更好结果。

## 5. 热绘图进程模型

正式热绘图使用一个长期存在的 native Windows GUI 进程：

```text
一个 QApplication
一个 MainWindow
一个 AppController
一个 RenderActor
一个 SceneRenderExecutor
```

同一进程和同一生产 runtime 依次完成 40 个预热样本和 240 个正式样本。Qt platform name 必须精确为 `windows`；`offscreen`、`minimal` 或其他平台直接拒绝。窗口必须 visible 且具有 native `windowHandle()`。

正式入口是：

```python
runtime.window.generate_button.click()
```

它发出生产 `MainWindow.generate_requested`，由 `_handle_generate_requested` 读取 UI、调用 AppController、提交唯一 Actor。工具不得绕过 MainWindow 直接调用 Controller、Actor 或 Engine。

## 6. 样本调度

固定 seed 为 `20260801`。每轮以以下稳定派生种子建立独立 `random.Random`：

```text
sha256("m1-performance-v1:<seed>:<sample_kind>:<round_index>")
```

摘要解释为大端整数后打乱八个场景。该算法不使用 Python 进程随机 hash。

```text
预热：5 轮 × 每轮 8 个公式各一次 = 40
正式：30 轮 × 每轮 8 个公式各一次 = 240
```

每轮都是八个场景的完整排列；同一 seed 重复得到完全相同的总顺序，不同轮次不全部采用同一排列。工具测试验证每个公式预热恰好 5 次、正式恰好 30 次，无遗漏和重复。

## 7. 每个热样本的前置条件

公式写入正式 `FormulaInputPanel` 后，工具先处理已排队 GUI 事件并确认：

- Controller 为 `IDLE`；
- `current_render_request_id is None`；
- Actor mailbox 的 `pending` 与 `current_token` 都为 `None`；
- 正式输入控件文本等于当前精确字符串；
- 再运行一次 GUI 事件处理后 `current_scene_revision` 不变；
- 本样本尚未提交。

预览可以保存上一成功图。提交前，工具直接读取 GUI 线程中 `PlotPreview` retained `_source_image` 的稳定 `QImage.cacheKey()`；不得读取每次返回 copy 的 `source_image` 属性来判断身份。公式写入、`processEvents()`、retained image 或前置条件读取中的普通 `Exception` 必须由样本外层安全边界保留为当前 scheduled sample 的 `benchmark_harness_exception`，记录完整必需字段和固定 `error_code`，但不记录异常正文、`repr`、traceback 或路径。该记录出现后停止继续提交；`KeyboardInterrupt`、`SystemExit` 等不属于 `Exception` 的控制流异常继续向外传播。

## 8. 热绘图计时边界

开始：启动 20 ms PreciseTimer 后，在即将调用 `generate_button.click()` 前记录 `time.monotonic()`。

结束必须全部满足：

1. Actor GUI relay 收到恰好一个匹配本次 `request_id + scene_revision` 的结果；
2. 该结果自身的 `request_id`、`scene_revision` 与提交后冻结的值一致；
3. MainWindow 已让 Controller 接纳同一对象，`controller.last_successful_result is result`，且 Controller 回到 `IDLE`；
4. 后续 event-loop turn 中重新读取的 retained `_source_image` 非空，且稳定 cache key 不同于提交前 retained image；
5. 通过 `QTimer.singleShot(0, ...)` 至少完成一次后续 GUI event-loop turn；
6. 随后记录 completion monotonic。

该边界包括 UI 值读取、不可变请求创建、Actor 调度、Engine、viewport/plan/sampler、Agg、GUI relay、PNG → QImage 和 preview 更新，不声称测量物理显示器刷新。

工具不从 `Controller.submit` 后开始、不以 Actor 发出结果但 preview 未更新为结束、不 sleep 猜测完成，也不把 Engine 内部 `elapsed_ms` 冒充提交到预览耗时。单样本 timeout 固定 30 秒。

## 9. 冷启动 READY 边界

正式冷启动是 20 个独立子进程。父进程已经由项目环境启动后，计时命令固定为：

```text
<project-python> -B <startup-probe>
```

父进程在 `subprocess.Popen` 前记录 monotonic；命令 tuple 的首项是传入的项目解释器，第二项是 `-B`，第三项是 probe 文件，永远不包含 `uv`。

child 使用生产 `create_application_runtime(QApplication)`，启动生产 Actor、show 正式 MainWindow、进入 event loop；第一个 `QTimer.singleShot(0, ...)` 回调证明至少完成一轮事件循环。此时要求窗口 visible，且正式公式 `QLineEdit` visible、enabled。随后 `ReadyEmitter.emit_once()` 向 stdout 写唯一一行：

```text
READY
```

parent 收到完整 READY 行时立即结束计时。child 随后通过第二个 event-loop callback 调用正式 `MainWindow.close()`；关闭失败时由 event loop 以 50 ms 重试，不把失败改写为成功。parent 要求 child 在 15 秒内退出、exit code 为 0、READY 总数精确为 1。READY timeout 为 30 秒。异常、超时、重复 READY 或非零退出全部保留为失败样本。

“冷启动”在本协议中指进程冷启动，不声称清空 Windows 文件缓存或硬件缓存。

## 10. MPLCONFIGDIR

预热和正式样本、父进程与全部 startup children 使用同一个预先准备的仓库外目录。目录不能位于 repository 内，也不能提交。空目录不算已准备。

首次字体缓存准备是独立操作：

```powershell
$env:MPLCONFIGDIR = '<external-mplconfigdir>'
uv run --locked python -B -m benchmarks.m1_gui_benchmark --prepare-font-cache --mplconfigdir $env:MPLCONFIGDIR
```

字体查找成功后，工具按 basename 排序枚举目录直属的全部 `fontlist-v*.json`；匹配项必须至少有一个且全部是非符号链接的普通文件。每个 fontlist 必须是严格 UTF-8 JSON object，并包含非空、由 object 组成的 `ttflist`，不能以空文件、损坏 JSON、`{}` 或空 `ttflist` 充当已准备缓存。全部结构检查通过后，该命令才在目录内原子写入 `m1-font-cache-ready.json`。marker 的 `schema` 固定为 `m1-font-cache-ready`、`schema_version` 固定为 `2`，记录当前 `tool_version`、Matplotlib distribution version，以及按 basename 排序的 `font_cache_manifest`；其中每项只含 `basename`、byte `size` 和 SHA-256，不记录 repository、home、cache 根目录或任何其他绝对路径。该命令 stdout 的唯一状态仍是 `MPLCONFIGDIR_READY`；构建、结构检查或 marker 原子写入失败时不得打印成功状态或留下有效 marker，且不得删除无法确认归本次创建的 fontlist 或其他目录内容。

正式 `--run` 在导入生产 bootstrap、创建 `QApplication` 或启动任一样本之前，只用 Python 标准库验证：目录在仓库外且存在；marker 是严格 UTF-8 JSON，冻结字段集合、schema version、tool version 和当前 Matplotlib distribution version 全部匹配；marker 中 fontlist basename 集合与目录中的实际直属普通文件集合精确一致；每个 size/SHA-256 未改变且内容仍通过最低结构检查。前置校验不得提前 import Matplotlib 或 `font_manager`。缺 marker、损坏/伪造 marker、版本不匹配、空缓存、额外/漏记 fontlist、结构损坏或准备后篡改全部必须在任何正式样本前拒绝。首次创建耗时不进入正式分布。正式结果只记录策略占位符 `<external-mplconfigdir>`，不记录用户完整本地路径。

## 11. GUI 响应性代理

每个热样本使用：

```text
Qt.PreciseTimer
interval = 20 ms
```

timer 在正式 UI 提交前启动。每次 tick 记录 monotonic。`timer_max_gap_ms` 是以下间隔的最大值：

- submission 到第一个 tick；
- 相邻 tick；
- 最后一个 tick 到完成时刻；若没有 tick，则为 submission 到完成。

因此不会遗漏尾部 gap。

## 12. invalid sample 与 invalid batch

单样本 `invalid_reason` 只能是：

```text
application_process_exit
request_failed
request_cancelled
request_timeout
request_id_revision_mismatch
missing_result
duplicate_result
benchmark_harness_exception
incomplete_monotonic_record
preview_not_updated
```

性能慢不是 invalid；慢值原样写入 JSONL 并参与统计。

整个批次 `invalid_batch_reasons` 只能是：

```text
windows_sleep_or_resume
benchmark_process_crash
user_closed_window
environment_changed
schedule_corrupted
result_integrity_failed
```

`environment_changed` 包括显示器拓扑、DPI/缩放或电源模式变化。Windows sleep/resume 使用 `GetTickCount64` 与 `QueryUnbiasedInterruptTime` 的 elapsed 差值检测，差值超过 1000 ms 时判定。不得以主观卡顿删除样本。

## 13. 百分位算法与报告统计

采用 nearest-rank：

```text
rank = ceil(p × n)
```

升序排序后使用 1-based rank。因此：

```text
每公式 n=30：P50 第 15 个，P95 第 29 个
冷启动 n=20：P50 第 10 个，P95 第 19 个
```

报告每公式 duration P50/P95/max、每公式 timer max-gap P95、全部 240 个正式样本描述统计、冷启动 P50/P95/max，以及 failure、invalid、cancelled、timeout 数。逐公式 P95 是 M1 绘图主判据；总体平均值不得稀释慢场景。只在对应样本数完整且均为有效成功时计算正式 percentile，否则为 `null`/`unavailable`。

## 14. 暂定阈值与 10% 复测

本协议只评价“Windows 11 开发参考机上的暂定阈值”：

```text
冷启动到可输入状态 P95 ≤ 5000 ms
M1 常见显函数提交到预览逐公式 P95 ≤ 1000 ms
GUI 主线程单次不可响应代理逐公式 P95 ≤ 200 ms
```

距离阈值不足 10% 的精确定义是：

```text
0.9 × threshold < P95 ≤ threshold
```

落入该开区间/闭区间的任一关键指标要求第二个完整批次，并以 `retest_of` 指向第一批。第二批必须使用不同的新 `batch-id`、新的且尚不存在的仓库外 `output-dir`，以及 `--retest-of <first-batch-id>`；`batch-id` 与 `retest-of` 采用同一字符规则，且禁止 self-retest。第一批允许不传 `--retest-of`。第一批结果目录保留且工具禁止覆盖；工具不跨目录搜索旧批次。两批均通过才能写“稳定达到暂定阈值”；一批通过、一批失败写“结果不稳定”；首批超过阈值直接记录未达到，诊断批次不得覆盖首批失败。恰好 `0.9 × threshold` 不触发复测。

## 15. 结果目录与原始 schema

正式入口必须在调用任何 startup/hot 测量函数之前 resolve `output-dir`，确认它位于仓库外且最终路径尚不存在。写 bundle 时重复相同防御性检查，在最终目录的同一父目录创建本次调用专属 staging 目录；九个文件全部写入 staging，并在 staging 上通过完整 `validate_result_bundle` 后，才以一次不覆盖现有目标的原子 rename 发布。校验成功前最终目录不得出现。写入、校验或发布失败时，只清理由本次调用明确创建的 staging，保留任何未知路径；第二次写同一路径继续拒绝。“精确九项”比较结果目录中的全部直属条目（包括文件和目录），不允许额外普通文件、额外目录或缺项；以下九项都必须是非符号链接的普通文件：

```text
manifest.json
environment.json
startup-samples.jsonl
render-samples.jsonl
summary.json
protocol.sha256
tools.sha256
stdout.txt
stderr.txt
```

`manifest.json` 的冻结字段精确为 `protocol_version`、`tool_version`、`batch_id`、`retest_of`、`formal_measurement`、`invalid_batch`、`invalid_batch_reasons`、`artifact_hashes`、`result_file_sha256`、`startup_command` 和 `render_schedule`。校验器要求 protocol/tool version 与本工具一致；batch id 合法，`retest_of` 为 null 或合法且非 self-retest；`formal_measurement is True`；`invalid_batch` 是 bool，reasons 是只含封闭 `InvalidBatchReason` 值的 list，且两者布尔状态一致；三个冻结 artifact hash 精确匹配批准值；启动命令精确为脱敏占位命令；seed、轮次和 40/240 样本数精确匹配冻结常量。`result_file_sha256` 必须精确索引除 `manifest.json` 外的其余八个文件并逐一匹配。manifest 不对自身做递归哈希，但仍必须通过上述完整 schema、类型和值校验。

每个热样本至少包含：

```text
protocol_version
tool_version
project_commit
batch_id
round_index
formula_id
exact_input
sample_kind
submission_monotonic
completion_monotonic
duration_ms
timer_max_gap_ms
request_id
scene_revision
success
invalid_reason
error_code
preview_updated
```

每个冷启动样本至少包含：

```text
protocol_version
tool_version
project_commit
batch_id
sample_index
start_monotonic
ready_monotonic
duration_ms
ready_count
child_pid
exit_code
success
invalid_reason
error_code
```

`environment.json` 至少记录 Windows edition/version/build、CPU、逻辑处理器、总内存、Python、PySide6/Qt、NumPy、Matplotlib、SymPy、项目 commit、显示器拓扑、逻辑/物理 DPI、device pixel ratio、活动电源模式和 MPLCONFIGDIR 策略。失败日志按路径长度从长到短脱敏 repository、home、MPLCONFIGDIR、project interpreter、`sys.prefix`、`sys.base_prefix`，以及存在的 `LOCALAPPDATA`、`APPDATA`、`TEMP`、`TMP`、`UV_CACHE_DIR`、`XDG_CACHE_HOME`；Windows 大小写与正反斜杠变体等价。不得记录 traceback 或异常 `repr`。完整 repository、home、cache 或 interpreter 路径不得写入结果，`RESULT_BUNDLE` 状态也只打印固定 `<external-result-directory>` 占位符和 batch id，不打印绝对结果目录。

热样本和冷启动 records 的 protocol/tool version、batch id 必须与 manifest 一致，project commit 必须与 environment 一致；summary 的 protocol/tool version 必须一致；environment 的 protocol version 和 project commit 必须有效且不得与 records/manifest 自相矛盾。缺字段、类型或冻结值不匹配、关键标识冲突、冻结 hash 不匹配、结果文件 hash 不匹配、额外条目或缺文件时，结果目录不能作为正式批次。

本轮冻结时的开发环境版本记录为：

| 项目 | 版本 |
|---|---|
| Python | CPython 3.12.11 |
| PySide6 / Qt | 6.11.1 / 6.11.1 |
| NumPy | 2.5.1 |
| Matplotlib | 3.11.1 |
| SymPy | 1.14.0 |
| 阶段 12A 项目 commit | `645a3eaa0dd58ab1937930365008c29a17af0dfe` |

正式批次仍必须重新采集实际版本和实际项目 commit；不能用本表替代 `environment.json`。

## 16. 冻结 SHA-256 与正式命令

协议文件不能把自身 SHA-256 嵌入自身而保持哈希不变，因此三个值在 review/commit 后以只读命令计算，并作为正式命令的显式批准参数；同样值写入 `manifest.json`、`protocol.sha256` 和 `tools.sha256`。工具入口：

```powershell
uv run --locked python -B -m benchmarks.m1_gui_benchmark --print-hashes
```

正式命令模板：

```powershell
$env:MPLCONFIGDIR = '<prepared-external-mplconfigdir>'
uv run --locked python -B -m benchmarks.m1_gui_benchmark `
  --run `
  --batch-id '<unique-batch-id>' `
  --output-dir '<new-external-result-directory>' `
  --mplconfigdir $env:MPLCONFIGDIR `
  --project-python '<project-python>' `
  --expected-protocol-sha256 '<approved-protocol-sha256>' `
  --expected-benchmark-sha256 '<approved-benchmark-sha256>' `
  --expected-startup-probe-sha256 '<approved-startup-probe-sha256>'
```

当首批结论要求复测时，第二批正式命令模板固定为：

```powershell
$env:MPLCONFIGDIR = '<same-prepared-external-mplconfigdir>'
uv run --locked python -B -m benchmarks.m1_gui_benchmark `
  --run `
  --batch-id '<new-unique-batch-id>' `
  --retest-of '<first-batch-id>' `
  --output-dir '<new-nonexistent-external-result-directory>' `
  --mplconfigdir $env:MPLCONFIGDIR `
  --project-python '<project-python>' `
  --expected-protocol-sha256 '<approved-protocol-sha256>' `
  --expected-benchmark-sha256 '<approved-benchmark-sha256>' `
  --expected-startup-probe-sha256 '<approved-startup-probe-sha256>'
```

外层 `uv run --locked` 只进入已锁定项目环境。冷启动计时从内部直接 `Popen(<project-python> -B <startup-probe>)` 开始，因此不包含 uv 自身启动时间。

正式运行还要求：

- Windows native Qt platform；
- `HEAD == origin/master`；
- 工作区和暂存区干净；
- 三个批准 SHA-256 精确匹配；
- MPLCONFIGDIR 在仓库外，ready marker 与当前版本匹配，且包含实际 fontlist cache；
- 输出目录已在测量前确认位于仓库外且尚不存在，发布时仍不得覆盖。

## 17. 阶段 12B 停止边界

本轮只运行很小的 fake/纯函数工具测试，不运行上述正式命令，不产生 40+240 热样本，不产生 20 次冷启动，不写正式结果目录，不触发真实剪贴板，不形成性能结论，不修改生产行为，也不宣布阶段 12 或 M1 完成。

协议与工具已冻结，尚未运行正式测量。
