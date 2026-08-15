# Stage 15-0 独立只读审核记录

日期：2026-08-15<br>
审核对象：Stage 15-0 当前工作树文档变更<br>
审核方式：获项目所有者明确授权的独立子代理，只读审核；主执行者未把自审冒充独立审核<br>
最终结论：`APPROVE`

## 1. 审核输入与只读边界

审核者只读取工作区、Git diff、相关规范、两份附件及主执行者报告的真实测试结果，没有修改、创建或删除文件，也没有运行正式性能。主要输入：

- 原 Stage 15-0 提示：`C:\Users\Chen Xinglin\.codex\attachments\2ebf8ffc-9bf0-46c5-b916-23f0c04ff2dd\pasted-text-1.txt`；
- 外部 Stage 14E 审核原文：`C:\Users\Chen Xinglin\.codex\attachments\dac6bffb-dfd2-4dd6-ad4e-c86fbc7aa67e\pasted-text.txt`；
- 原文 SHA-256：`90EF170459886451F1CE0D5811A512D55D70C6FAC2BD7A71D2DDC14BE53CABC0`；
- 审计基线：`master @ 9b4dc91b322e04ea5764ea6836dcfc8c68308ec5`；
- 主执行者实际测试结果：定向 `58 passed`，全量 `2325 passed`；
- `docs/audits/stage-14e-candidate-independent-audit-2026-08-15.md`、`docs/audits/stage-15-0-p3-disposition.md`、`docs/stage-15-execution-charter.md` 及同步文档。

审核重点是 P3 证据真实性、当前事实与外部陈述的隔离、P3 裁定、跨层契约、逐子步 literal-path allowlist、15E→15F 顺序、进程级原生峰值内存、limits 状态粒度，以及禁止提前完成的状态。

## 2. 首轮 findings

### P0

无。

### P1

1. **P0-07 被错误授权在 15E 提前关闭。** 首轮 `docs/stage-15-execution-charter.md:478` 允许 15E 完整通过后在 `联网确认.md` 关闭 P0-07，但冻结分解把正式关闭归属 15G。审核要求 15E 只形成候选教材证据并保持 P0-07 打开，15G 在自动、人工、性能、教材和外部证据全部通过后正式关闭。

### P2

1. **15-0 写入边界内部表述冲突。** 首轮章程第 33 行允许新增外部 Stage 14E 审核归档，第 41 行却笼统把所有 Stage 12/14 审核记录列为只读。审核要求明确一次性新增归档例外，并把禁令限定为既有历史记录。
2. **公开 API 哨兵写权限过宽。** 首轮把 `tests/test_stage13_public_api.py` 放入 15E、15G 写入 allowlist；这两步没有公共 API 变更责任。审核要求仅在确有公共契约变化的 15A、15B、15F 保留写权限，15E、15G 移为只读依赖但继续执行。

### P3

1. **P3-8 退出搜索范围不可执行。** 首轮处置表写“`rg` 只允许真实类名”，但必须原样保存的外部归档和处置说明必然包含旧错误名。审核要求把禁用旧名的搜索限定到当前 benchmark 文档、生产类型和公开 API 哨兵，并明确排除原文归档与处置说明。

## 3. 主执行者处置

主执行者只修改 15-0 allowlist 内的 `docs/stage-15-execution-charter.md` 和 `docs/audits/stage-15-0-p3-disposition.md`：

1. 15E 的 `联网确认.md` 从写入 allowlist 移到只读依赖；15E 只形成教材候选证据并保持 P0-07 打开，15G 才有正式关闭权限。
2. 15-0 禁写规则改为保护“既有”Stage 12/14 历史结果和审核记录，同时明确第 33 行一次性新增外部归档是唯一例外。
3. `tests/test_stage13_public_api.py` 的写入责任收窄为 15A、15B、15F；15E、15G 均列为只读依赖。
4. P3-8 退出证据改为三个 literal path 的定向搜索，并明确排除完整原文归档和处置说明。

## 4. 独立复核

同一独立审核者在修正后再次只读核验：

| finding | 复核结果 |
|---|---|
| 15E 提前关闭 P0-07 | `resolved` |
| 一次性归档与历史只读边界冲突 | `resolved` |
| 15E/15G 公开 API 哨兵写权限过宽 | `resolved` |
| P3-8 搜索范围不可执行 | `resolved` |

复核确认：

- 外部附件为 15,413 bytes、126 行，SHA-256 与提供值一致；归档正文与附件 126/126 行逐行一致；
- 归档清楚区分 `ec11449fb4a45beec639a6807c96dc9205389b2c` 候选基线的外部陈述和当前 `9b4dc91b322e04ea5764ea6836dcfc8c68308ec5` 事实；
- P3-1 至 P3-7 均为 `accepted`，未写成已实施；P3-8 的 `already_resolved` 有当前 HEAD 直接证据；
- 15E→15F、OS/进程峰值内存主口径、limits 状态粒度、`PlotKind`、`PlotItemResult`、比例三态和非阻塞警告契约完整；
- 未修改生产代码、测试或既有 Stage 14 历史审计；未宣称 Stage 15/M1.5 完成，未关闭 P0-07，未创建 checkpoint，未运行正式性能。

复核新增 findings：P0 无、P1 无、P2 无、P3 无。最终结论：`APPROVE`。
