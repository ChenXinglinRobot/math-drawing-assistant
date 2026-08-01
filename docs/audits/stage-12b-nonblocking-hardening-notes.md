# 阶段 12B：非阻塞未来加固备忘

日期：2026-08-01
状态：已记录；不属于阶段 12B 的阻塞项或验收条件

## 目的与边界

本文记录阶段 12B 独立复审发现的两项未来加固机会，作为后续维护提醒。它们不改变已冻结的 M1 性能测量协议、工具行为、正式计时边界或当前验收结论；不得据此重写阶段 12B 的通过结论，也不要求在进入 12C-1 前实施。

正式协议及其批准 SHA-256 继续以 `docs/benchmarks/m1-performance-v1.md` 为准。本文不是协议的补充或替代，不参与正式性能结果的有效性判定。

## H-12B-01：字体缓存 marker 的来源认证

**当前结论：** `prepare_font_cache` 经真实 Matplotlib `findfont` / 字体缓存构建后，才写入包含 `fontlist` 名称、大小和 SHA-256 的 schema v2 marker；正式 preflight 会复核这些信息。因此，在既定的正式运行流程中，首次字体缓存成本不会混入正式分布，准备后对缓存文件的改动也会被检测到。

**已知边界：** 现有 fake fontlist 测试验证的是 marker 所要求的最低 JSON 结构，而不是 Matplotlib 对 fontlist 的完整反序列化行为。若操作者主动伪造一套自洽的 marker 与 fontlist 文件，现有机制不提供密码学意义上的来源认证。

**为何不阻塞：** 当前冻结协议信任本地受控的 prepare → preflight 流程，并由真实 prepare、大小与哈希复核保障运行完整性；该边界不会在正常流程中制造虚假的热绘图 P50/P95。

**未来触发条件：** 需要抵御操作者主动伪造 marker，或将该机制用于跨主机、跨信任边界的结果认证时。

**可选加固：** 为 marker 或准备产物引入受信任签名/证明，或在独立受控环境中完整验证 Matplotlib fontlist 的可反序列化性。

**优先级：** P3，未排期。

## H-12B-02：结果 bundle 的独立样本计数取证

**当前结论：** `validate_result_bundle` 已封闭验证目录条目、必需文件类型、manifest 字段、版本与状态、冻结调度、启动命令、artifact hashes，以及 environment、summary、render/startup records 的关键标识一致性。正式 CLI 另由 `run_hot_samples`、startup count 和 `schedule_corrupted` 确保实际调度与样本数正确。

**已知边界：** validator 目前不会独立地根据 manifest 调度重新核对每个场景的全部实际样本数量。

**为何不阻塞：** 在当前正式 CLI 路径中，样本数与调度完整性已在执行时被强制保证；该边界不会让冻结正式运行产生虚假的 P50/P95。

**未来触发条件：** 将 validator 定位为可接受任意第三方 result bundle 的通用取证工具，或需要脱离原正式 CLI 独立认证 bundle 时。

**可选加固：** 从 manifest 的冻结调度派生预期场景计数、热样本总数和启动样本总数，并逐项与 records 交叉验证；不一致时将 bundle 判为 `result_integrity_failed`。

**优先级：** P3，未排期。

## 后续处置

任一事项在其触发条件成立前保持为备忘，不自动进入阶段计划或验收门槛。若决定实施，应先创建对应的正式决策或阶段任务，并同步更新受影响的协议、测试和批准哈希。
