# 性能环境记录

状态：阶段 12 `m1-performance-v1` 正式结果及有限 M1 单显函数 checkpoint 已通过总架构师独立审核。

## 开发参考机

以下事实来自阶段 0 审计及阶段 12 正式 bundle：

- Windows 11 25H2，OS Build 26200.8875；正式环境记录同时保留注册表原始 ProductName `Windows 10 Home China`。操作系统代际依据 DisplayVersion、OS Build 及微软发布信息判定；不改写 bundle 原始字段。
- CPU：Intel Core Ultra 9 185H；已观察到 22 个逻辑处理器；
- 物理内存：31.6 GiB；单屏 1536 × 960，200% 缩放；logical DPI 96、physical DPI 125.0462、device pixel ratio 2.0；平衡电源模式。
- 项目解释器：CPython 3.12.11；
- PySide6 / Qt 6.11.1；
- NumPy 2.5.1、Matplotlib 3.11.1、ContourPy 1.3.3；
- SymPy 1.14.0、mpmath 1.3.0、pytest 9.1.1；
- 正式 batch：`20260801T151238Z-m1-performance-v1-primary`；协议、GUI benchmark、startup probe SHA-256 分别为 `cce41d42be1ffbd328bde92fcd2a2194db81be873470fe777e8ebf0ba5f91f97`、`47d6d39bdf8a95f62561c5e2f9feddbc5b8124d39e70520e37e53e8f360e8b84`、`3fb8c00abac7331fbef2f55d0639e098b2f31e0f70d016955c5899edf4348d64`。
- startup P50/P95/max：1422/2266/5469 ms；240 个正式热样本总体 P50/P95/max：156/203/265 ms。
- 八公式 duration P95 均不超过 1000 ms，GUI gap P95 均不超过 200 ms；`failed/invalid/cancelled/timeout = 0/0/0/0`。完整指标见[正式结果摘要](benchmarks/m1-performance-v1-results.md)。

startup max 为 5469 ms，按冻结协议的 P95 门禁不构成失败，必须保留该值。当前 Windows 11 开发参考机达到暂定阈值；不外推为课堂设备、教学一体机、Windows 10 或发布性能结论。

## 证据边界

当前设备是开发参考机，不是课堂代表设备，也不是教学一体机验证结论。尚未完成课堂性能、触控、DPI 和多显示器验证。

阶段 12 数据只属于开发参考数据；不得外推为课堂性能结论。D-015 要求在阶段 26 重新打开课堂设备实机验证风险，并最迟在阶段 30 发布候选验收前完成实机验证或形成新的明确降级决定。

## 仍未关闭的范围

`DEFAULT_LIMITS` 中资源值仍是安全上限，不是课堂或发布性能承诺。阶段 26 的实机门禁以及阶段 30 的实机与兼容性门禁保持开放。
