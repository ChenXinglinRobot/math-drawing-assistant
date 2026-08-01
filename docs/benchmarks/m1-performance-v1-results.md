# m1-performance-v1 正式结果

状态：阶段 12C-2 复核与总架构师独立审核均已通过；阶段 12 及有限 M1 单显函数 checkpoint 已通过。

## 冻结基线与证据

- 阶段 12B commit：`03ea18dc527b02cd361b22f0cf13d2153fee0c17`
- 协议 SHA-256：`cce41d42be1ffbd328bde92fcd2a2194db81be873470fe777e8ebf0ba5f91f97`
- GUI benchmark SHA-256：`47d6d39bdf8a95f62561c5e2f9feddbc5b8124d39e70520e37e53e8f360e8b84`
- startup probe SHA-256：`3fb8c00abac7331fbef2f55d0639e098b2f31e0f70d016955c5899edf4348d64`
- 主批次：`20260801T151238Z-m1-performance-v1-primary`
- 复测：未触发；`threshold_conclusion` 为 `met`。
- 外部原件：仓库外 FormalEvidence 原件已保留，并已完成与仓库副本的逐文件 SHA-256 比对。
- 仓库副本：[benchmarks/results/20260801T151238Z-m1-performance-v1-primary](../../benchmarks/results/20260801T151238Z-m1-performance-v1-primary/)。

## 开发参考机环境

- Windows 11 25H2，OS Build 26200.8875；正式环境记录同时保留注册表原始 ProductName `Windows 10 Home China`。操作系统代际依据 DisplayVersion、OS Build 及微软发布信息判定；该原始字段保留于 bundle，未被改写或删除。Intel Core Ultra 9 185H，22 个逻辑处理器，31.6 GiB 物理内存。
- Python 3.12.11；PySide6 / Qt 6.11.1 / 6.11.1；NumPy 2.5.1；Matplotlib 3.11.1；SymPy 1.14.0。
- 1 个显示器，1536 × 960；逻辑 DPI 96，物理 DPI 125.0462，device pixel ratio 2.0（200% 缩放）；平衡电源模式。

这仅是 Windows 11 开发参考机数据，不代表课堂设备、教学一体机、低配置设备、Windows 10 或发布性能认证。

## 正式主批次

正式字体缓存已使用外部、独立的 `MPLCONFIGDIR` 准备并通过 marker v2 验证：一个 `fontlist-v*.json` 文件，非空 manifest，工具版本 `m1-benchmark-tools-v1`、Matplotlib 版本 3.11.1，marker 不含绝对路径。

- bundle 独立 validator：`RESULT_BUNDLE_VALID`
- 文件：恰好九个普通、非符号链接文件。
- 记录：20 个冷启动；40 个预热；240 个正式热绘图；每个公式 30 个正式样本。
- `failed` / `invalid` / `cancelled` / `timeout`：0 / 0 / 0 / 0。
- 冻结调度、三个 artifact hash、manifest、样本数、完整性索引与路径脱敏检查均通过。
- benchmark 中的 `ClipboardService.write_history` 前后检查通过；未发出复制意图，也未读写真实剪贴板。

### 冷启动（ms）

| P50 | P95 | Max | 阈值 |
|---:|---:|---:|---:|
| 1422 | 2266 | 5469 | P95 ≤ 5000 |

### 提交到预览与 GUI 响应性（ms）

| 公式 | duration P50 | duration P95 | duration Max | GUI gap P95 |
|---|---:|---:|---:|---:|
| `x=y` | 156 | 203 | 203 | 62 |
| `x^2` | 141 | 204 | 235 | 63 |
| `1/x` | 156 | 188 | 188 | 47 |
| `ln(x)` | 141 | 203 | 203 | 62 |
| `sin(x)` | 156 | 203 | 234 | 62 |
| `exp(x)` | 141 | 188 | 265 | 47 |
| `log(x,10)` | 156 | 188 | 188 | 47 |
| `sin(1000*x)` | 156 | 188 | 219 | 62 |

全部逐公式 duration P95 均不超过 1000 ms，全部 GUI gap P95 均不超过 200 ms，冷启动 P95 不超过 5000 ms。因此当前 Windows 11 开发参考机在 `m1-performance-v1` 下达到暂定阈值。

## 自动回归

- 阶段 12 定向：160 passed。
- Actor / Engine / UI：802 passed。
- 全量：1012 passed。
- 类型检查：不适用；当前仓库尚无批准的 Pyright/mypy 入口或配置。

## 原件与仓库副本逐文件 SHA-256

仓库外 FormalEvidence 原件保留不动。下列每个仓库文件均已与对应原件逐字节匹配：

| 文件 | SHA-256 |
|---|---|
| `environment.json` | `650634eaea72e0521916bc5146d74e70c0a74105fb8de49eccef4c5f05f9e7ee` |
| `manifest.json` | `108129111d0f794edf60b0d8e2bac3571e796a12365c6cff992c033427f20561` |
| `protocol.sha256` | `d9333aaca9089b5d4ee1c73969e6327e60edb102c28fba21ac0828ddaae5ac39` |
| `render-samples.jsonl` | `ea578d222ec0833e278d702916eaaf05bec4e816b66fa76be1982a6e183a1a8c` |
| `startup-samples.jsonl` | `a8b37c71e3dcea563db1155c2c85b59f821d124083884d3bd3b7ac926943b377` |
| `stderr.txt` | `01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b` |
| `stdout.txt` | `ca7d7bc6d4ac53f47126a202a0ddf58a629f6f465c8608d20f3d147b6c6f3ea3` |
| `summary.json` | `9f5d5530da7920db452cf733a22d11ee39cb7a9331af6c0ca8fbf76ecec975a2` |
| `tools.sha256` | `75a5245aa4019b0842882b0b573a016f56e8280ddaf8f5f151b24963c1bcd7cb` |

## 人工验收记录（项目所有者选择的替代验证）

- Windows 画图 11.2605.71.0：fresh、stale、渲染期间复制旧图、失败后复制旧图和重复复制均通过。渲染期间场景使用高负载嵌套 `tan` 公式和 4096 × 4096 分辨率；未发现异常。
- WPS Office 12.1.0.19302：WPS 演示中 fresh、stale 和两张不同结果均通过；WPS 文字中 fresh 和两张不同结果均通过。不同输出分辨率的图片在 WPS 中显示效果存在差异，已记录为观察项，未判为失败。
- Microsoft PowerPoint 与 Microsoft Word：当前测试环境未安装，项目所有者决定不测试。因此本文**不声明**对 Microsoft PowerPoint 或 Microsoft Word 的兼容性；上述 WPS 结果仅作为项目所有者批准的有限阶段性替代验证。
- 断网：通过；断网后本地绘图、预览、复制和粘贴仍可使用。
- 关闭生命周期：通过；正常关闭后，项目所有者在任务管理器中未发现本应用残留的 Python/Pythonw 进程。

该替代验证不改变冻结的性能协议、自动回归或 Microsoft Office 未验证的事实；完整目标软件矩阵仍由 P0-14 和阶段 30 关闭。阶段 12 及有限 M1 单显函数 checkpoint 已通过总架构师独立审核；未进入阶段 13。
