# Stage 15-0 完成报告

日期：2026-08-15<br>
任务：Stage 15-0——入口收口与执行章程<br>
结论：完成 15-0 文档与裁定门；停止，等待总架构师验收<br>

## 1. 基线与初始工作区

- 分支：`master`
- HEAD：`9b4dc91b322e04ea5764ea6836dcfc8c68308ec5`
- 远端跟踪：`origin/master`
- 初始 `git status --short --branch`：除 `.pytest_cache/` 因权限无法读取的警告外，没有可见修改或未跟踪文件。
- Stage 14 已完成，P0-06 已关闭；Stage 15、P0-07、真实教材矩阵、正式 M1.5 性能和 M1.5 checkpoint 在入口时均未完成。

没有改写审计基线 `ec11449fb4a45beec639a6807c96dc9205389b2c` 上的外部结论；所有当前事实另针对本节 HEAD 核验。

## 2. P3 原始证据与处置

原始证据：

- 标题：Stage 14E 候选变更独立审计报告（只读）
- 审计日期：2026-08-15
- 外部候选变更基线：`master @ ec11449fb4a45beec639a6807c96dc9205389b2c`
- 来源：项目所有者提供的 Claude Code/GLM 独立只读审核原文
- 原始附件：`C:\Users\Chen Xinglin\.codex\attachments\dac6bffb-dfd2-4dd6-ad4e-c86fbc7aa67e\pasted-text.txt`
- SHA-256：`90EF170459886451F1CE0D5811A512D55D70C6FAC2BD7A71D2DDC14BE53CABC0`
- 完整性：15,413 bytes、126 行、无 UTF-8 BOM、末尾无 LF；归档正文与附件 126/126 行逐行一致，差异 0。

逐项裁定以 `docs/audits/stage-15-0-p3-disposition.md` 为完整证据表：

| finding | 当前 HEAD 裁定 | 责任与边界 |
|---|---|---|
| P3-1 可绕过的字符串静态边界测试 | `accepted`，尚未实施 | 15A 新 AST/全包生产边界门；15G 复验 |
| P3-2 残差 oracle 与生产系数同源 | `accepted`，尚未实施 | 15E 教材矩阵和异构几何 oracle；其变更会使相应 15F 结果失效 |
| P3-3 geometry Fraction receipt 缺逐字段篡改 | `accepted`，尚未实施 | 15B receipt hardening |
| P3-4 scene-spec `item_id` 缺篡改 | `accepted`，尚未实施 | 15B receipt hardening |
| P3-5 M1 显函数计划侧 receipt 缺完整篡改 | `accepted`，尚未实施 | 15B receipt hardening |
| P3-6 中间取消缺 `item_id` 断言 | `accepted`，尚未完整实施；双曲线子项已随 Stage 14 P2-5 解决 | 15B typed sampler identity；15C 真实取消链复验 |
| P3-7 Stage 14 探针无机器可读失败退出 | `accepted`，尚未实施 | 15F 新 `m1.5-performance-v1` 工具关闭；历史探针和证据包只读；工具/协议变化使正式结果失效 |
| P3-8 benchmark 文档类名错误 | `already_resolved` | 当前文档、生产类型与公开 API 哨兵均使用 `ParameterizedRenderMemoryBudget`，不重复修改 |

P3-1 至 P3-7 均没有被写成已经实施。P2-1 至 P2-5 和 P3-8 只核对当前状态，没有重复实施或改写 Stage 14 历史。

## 3. 创建和修改的文件

新增：

- `docs/audits/stage-14e-candidate-independent-audit-2026-08-15.md`
- `docs/audits/stage-15-0-p3-disposition.md`
- `docs/audits/stage-15-0-independent-review-notes.md`
- `docs/audits/stage-15-0-completion-report.md`
- `docs/stage-15-execution-charter.md`

修改：

- `docs/architecture.md`
- `数学绘图助手_Codex协助开发步骤清单_v0.3.md`

经一致性核对但保持不变：

- `docs/decisions.md`
- `docs/m1.5-math-input-scope.md`
- `docs/supported-formulas.md`
- `联网确认.md`

没有修改 `数学绘图助手 PRD.md`、生产代码、测试、benchmark 工具、Stage 12/14 既有历史文件、四个 Stage 14 证据文件或其 SHA-256。

## 4. Stage 15 执行章程冻结结果

`docs/stage-15-execution-charter.md` 已冻结：

- 八项总架构师跨层契约，包括粗粒度 `PlotKind`、正交具体类型信息、`PlotItemResult` 可见片段/资源诊断、DEFAULT/AUTO/EQUAL 三态、非阻塞告警、OS/进程级原生峰值内存、limits 状态粒度和 15E→15F 顺序；
- 当前实现链与唯一目标链；
- PRD §§4.2、6.2、6.4、7.2、10.4、10.5、10.5.1、12.1–12.3、14、15、20.1、20.4、21、23 的追踪矩阵；
- 15A–15G 的固定顺序、阶段边界、自动测试、公开 API 哨兵、文档同步、独立审核、退出条件和失效/退回规则；
- 15A、15B、15C、15D、15E、15F、15G 各自逐文件 literal-path 写入 allowlist 与逐文件只读依赖；
- 每步新测试、教材 JSON、来源 ledger、人工清单、性能协议、性能工具、固定性能结果、review notes 和 completion report 的具体文件名；
- 15F 固定主证据目录中的九个 literal file，没有时间戳通配符或整个结果目录写权限；
- 宽/窄窗口、100/125/150/175/200% DPI、圆不变形、失败旧图保护和重复复制的人工目标；
- 15E 只形成教材候选证据并保持 P0-07 打开；只有 15G 综合证据全部通过后才能正式关闭 P0-07。

公开 API 哨兵写权限经独立审核收窄：只在有公共契约责任的 15A、15B、15F 可写，15C、15D、15E、15G 均为只读执行。

## 5. 实际验证结果

### 定向测试

命令：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='.'; uv run --locked pytest -q -p no:cacheprovider tests/test_stage13_public_api.py tests/test_models.py tests/test_limits.py
```

- 首次：`58 passed in 1.18s`
- 独立审核修正后复跑：`58 passed in 1.21s`

### 全量回归

命令：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='.'; uv run --locked pytest -q -p no:cacheprovider
```

- 首次：`2325 passed in 69.67s`
- 独立审核修正后复跑：`2325 passed in 52.36s`

两类命令在默认沙箱内最初因现有 uv cache 路径权限失败，随后按授权在沙箱外使用同一锁定环境运行；这不是测试失败。命令均设置 `PYTHONDONTWRITEBYTECODE=1` 并关闭 pytest cache provider。

### 文档与差异检查

- 提前完成状态搜索：未发现“Stage 15 已完成”“P0-07 已关闭”“M1.5 checkpoint 已创建/完成”“核心 MVP 已更新/完成”或“正式 M1.5 性能已通过/完成”的事实宣称；相关命中均为历史事实、未来条件或明确否定。
- P3-8 定向搜索：`docs/benchmarks/stage14-parameterized-prototype-v1.md`、`math_drawing_assistant/models/render_plan.py`、`tests/test_stage13_public_api.py` 中旧名 `ParameterizedMemoryBudget` 为 0；真实名 `ParameterizedRenderMemoryBudget` 存在。外部原文归档和处置说明按设计排除。
- 新增文档行尾空白搜索：0 命中。
- `git diff --check`：通过；只有 Git 提示两份既有工作副本未来可能 LF→CRLF，没有 whitespace error。
- 最终 `git status --short --branch` 仅显示本报告 §3 列出的授权文档；`.pytest_cache/` 仍有只读权限警告。

## 6. 独立只读审核

获授权的独立子代理严格只读。首轮结论为 `REQUEST CHANGES`：P0 无，P1 一项、P2 两项、P3 一项：

1. 15E 被错误授权提前关闭 P0-07；
2. 一次性外部归档与既有 Stage 12/14 历史只读边界表述冲突；
3. 15E/15G 对公开 API 哨兵的写权限过宽；
4. P3-8 的旧名搜索范围没有排除必须原样保存的来源文件。

主执行者只在 15-0 allowlist 内修正。独立审核者复核后判定四项全部 `resolved`，新增 P0/P1/P2/P3 均无，最终结论 `APPROVE`。真实审核过程与逐项处置见 `docs/audits/stage-15-0-independent-review-notes.md`。

## 7. 剩余开放项与停止边界

- P3-1 至 P3-7 继续开放，必须在处置表分配的 15A–15F 责任步关闭；
- 15A–15G 均未开始实施；每步需由独立任务显式开始，完成后停止，不自动进入下一步；
- P0-07 保持打开，真实教材来源与产品矩阵尚未执行；
- M1.5 自动/人工/性能综合验收尚未执行；
- 正式 M1.5 性能、课堂设备外推和 M1.6 入口资源冻结尚未执行；
- M1.5 checkpoint 和核心 MVP 状态均未更新。

## 8. 明确声明

- 未进入 15A；
- 未修改生产代码；
- 未修改测试或 benchmark 工具；
- 未运行正式性能测量；
- 未重新生成 Stage 14 benchmark bundle；
- 未改写 `docs/audits/stage-14-final-acceptance-2026-08-14.md` 或其历史内容；
- P0-07 仍打开；
- 未创建 M1.5 checkpoint；
- 未更新核心 MVP 状态；
- 未执行 `git add`、`git commit` 或 `git push`。

Stage 15-0 至此停止，等待总架构师验收。
