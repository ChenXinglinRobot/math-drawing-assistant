# Stage 14E 候选变更独立审计报告（外部只读原文归档）

## 归档元数据与解释边界

- 标题：Stage 14E 候选变更独立审计报告（只读）
- 审计日期：2026-08-15
- 审计基线：`master @ ec11449fb4a45beec639a6807c96dc9205389b2c`
- 来源：项目所有者提供的 Claude Code/GLM 独立只读审核原文
- 原始附件：`C:\Users\Chen Xinglin\.codex\attachments\dac6bffb-dfd2-4dd6-ad4e-c86fbc7aa67e\pasted-text.txt`
- 原始附件 SHA-256：`90EF170459886451F1CE0D5811A512D55D70C6FAC2BD7A71D2DDC14BE53CABC0`
- 原始附件规模：126 行，15,413 bytes
- 归档日期：2026-08-15（Asia/Shanghai）

本文件完整保留外部报告正文，不改写 finding 内容。外部审核针对候选变更基线 `ec11449fb4a45beec639a6807c96dc9205389b2c`；其中关于代码、测试和文档的陈述不能自动提升为当前仓库事实。Stage 15-0 对当前 `HEAD 9b4dc91b322e04ea5764ea6836dcfc8c68308ec5` 的复核和处置另见 `docs/audits/stage-15-0-p3-disposition.md`。本归档不修改或重写 `docs/audits/stage-14-final-acceptance-2026-08-14.md` 的历史结论。

## 原始报告正文（完整、未改写）

```text
Stage 14E 候选变更独立审计报告（只读）
审计日期：2026-08-15 · 基线：master @ ec11449fb4a45beec639a6807c96dc9205389b2c（= origin/master，已亲核）· 全程未修改任何文件、未执行 commit/push、未污染工作树
Findings（按严重程度排序）
P0：未发现。 无安全问题、无数据破坏、无根本架构错误。生产代码确实仅 docstring 一行变化（字节级比对：3018 行仅第 551 行差异，samplers.py:551），无版本升级、无新公开 API、无 renderer/Actor/UI/contour/重入接线、无 benchmark 反向导入。
P1：未发现。 P0-06 全部关闭条件经独立验证实质满足。
P2-1｜联网确认.md C-09 状态行与同文件 P0-06 关闭自相矛盾
• 严重程度：P2（对抗核实：CONFIRMED）
• 位置：联网确认.md:173
• 证据：状态行结尾"…阶段 11 UI 整合尚未验收，M1.5 曲线原型仍待后续阶段"。同文件 第 245 行 已登记"已关闭（2026-08-15）"，第 12 节（726 行起）完整登记关闭。该行是"## 2. 资料已确认的事实"中的现行状态声明（非带日期的历史记录），本轮 diff 将文件头改为"最后核实：2026-08-15"却漏改此行（与 HEAD 逐字节相同）。
• 为什么是问题：关闭台账文件在同一提交内自相矛盾；文件第 27 行的映射表把 D-007/P0-06 追溯读者引到 C-09，读到的是“原型仍待确认”。
• 影响：不推翻关闭（登记本身完整、有日期、跨文档一致；陈旧方向保守，只低估不多报），但属于必须在提交前修复的交付物内部矛盾。
• 最小修复：行尾子句改为"…M1.5 曲线采样原型已随阶段 14 关闭（见第 12 节），renderer/UI 整合仍待阶段 15"。仅此一句，前半段阶段 10/11 历史保留。
P2-2｜联网确认.md C-09 收尾段六项“待确认”中五项已被 Stage 14 确认
• 严重程度：P2（对抗核实：CONFIRMED）
• 位置：联网确认.md:184
• 证据："仍需后续原型确认：参数化直线/圆锥曲线的可见参数区间、分支、裁切、性能、内存与残差容差…"——其中可见参数区间、分支、裁切、内存、残差容差恰是第 12.1 节登记为“通过”的项目；仅正式 P50/P95 性能确属 Stage 15（开发机筛查探针也已跑过）。
• 为什么是问题：同 P2-1，现行状态声明；且是全部矛盾中最尖锐的一处（逐项与 12.1 对着写）。
• 影响：同 P2-1。
• 最小修复：该句改为“参数化直线/圆锥曲线的可见参数区间、分支、裁切、内存预算与残差容差已由阶段 14 参数化原型确认（见第 12 节）；正式性能基准（P50/P95）与 renderer/UI 整合仍待阶段 15，不能用阶段 10 的显函数结果外推。"
P2-3｜supported-formulas.md 当前边界章节仍称 equation Spec 数值/采样“属于尚未完成的阶段 14/15”
• 严重程度：P2（对抗核实：CONFIRMED）
• 位置：docs/supported-formulas.md:41
• 证据：“equation Spec 的后续数值、采样与渲染能力属于尚未完成的阶段 14/15"（我已亲核原文）。同文件第 4 行版本哨兵宣布"stage-14e-final-acceptance-v1 / Stage 14B 至 14E 已完成…P0-06 已关闭”，第 986 行同。该句前半（analyze_plot_item 不生成 PlotSceneSpec）仍与代码一致，仅“数值、采样”半句过时。
• 为什么是问题：权威契约文档的“当前实现边界”章节内部自相矛盾，误导读者的生产边界认知。
• 影响：不影响验收证据；无测试钉住此句（已核实），修复无需改测试。
• 最小修复：该子句改为"…equation Spec 的 viewport/数值/参数化采样原型已由阶段 14 完成，但尚未接入 SceneRenderExecutor；渲染能力属于尚未完成的阶段 15"。
P2-4｜双曲线 branch 方向 oracle 仅支持水平横轴；竖直横轴方向在全测试套件中零断言，审计报告声明超出证据
• 严重程度：P2（对抗核实：CONFIRMED）
• 位置：tests/engine/test_stage14e_acceptance.py:113-122、644-655；关联 samplers.py:1174-1194
• 证据：GEOMETRY_CASES 只含水平双曲线 x^2/9-y^2=4…（x^2/9-y^2/4=1）；oracle 分支判定只沿 x（branch 0: x < center_x）。全 tests/ grep：竖直形式 y^2/4-x^2/9=1 仅出现在 14d1 三处，其中采样测试（679-703 行）只断言有限性与生产残差——残差对两侧分支都成立，标签互换/方向翻转的竖直采样可通过全部 2332 个测试。而审计报告第 59 行列"branch sign"为已验证数值证据、第 66 行称 oracle 覆盖“branch sign”、第 68 行称代表性输入含“水平/竖直双曲线”。
• 为什么是问题：冻结合同（supported-formulas.md 双曲线节）对两种轴向都定义了 branch 0=左/下、1=右/上；验收声明未获测试支撑。
• 影响：不推翻 P0-06“双曲线两支”关闭条件（branch identity 与区间拓扑在 14d1 已测）；但审计报告的 branch sign 声明对竖直方向言过其实，且该回归通道无锁。
• 最小修复：GEOMETRY_CASES（或独立参数化测试）补竖直双曲线用例，oracle 按 spec.transverse_axis 轴感知：水平断言 x 侧、竖直断言 y 侧（branch 0: y < center_y）。修复将同时首次动态确认生产竖直路径当前行为正确。
P2-5｜双曲线合作取消矩阵止步第 14/25 次轮询：尾部四检查点（metadata/freeze/snapshot/return 前）从未被任何测试执行
• 严重程度：P2（对抗核实：CONFIRMED，含动态复证）
• 位置：tests/engine/test_stage14d1_hyperbola.py:969-974；未覆盖的生产检查点在 samplers.py:1308-1398
• 证据：参数化列表 [1,2,3,4,5,6,8,10,12,14]，而该 fixture 成功运行共轮询 25 次；22-25 次（metadata 前/冻结前/snapshot 前/返回前）只在手动视口 fixture 可达，列表却止于 14。line/oval/parabola 的同类尾部检查点均已穷尽覆盖（14b2:682-686、14c:925-930、14d2:779-790），唯双曲线缺失。审计报告第 76/178 行声明“六类路径 neutral、无部分结果”按类型成立言过其实。
• 为什么是问题：双曲线采样器尾部重构若回归（如最后一次轮询后仍返回结果、泄露部分结果），全套件无测试失败。
• 影响：不推翻验收——审核方以只读内存探针动态复证：当前生产代码在该 fixture 全部 25 个检查点取消均精确返回中性 SamplingCancelled；这是回归锁缺口而非现行缺陷。注意该文件本身是已提交的 14D-1 交付物（不在本次 diff 内），但 Stage 14E 的关闭声明使其进入本次审核责任范围。
• 最小修复：参数化列表扩为 list(range(1, 26))（或照抄 14d2 的“先计数后逐点取消”模式）。
P3（非阻塞加固，共 8 项）
#
位置
摘要
最小修复
P3-1
test_stage14e_acceptance.py:873-909
静态边界断言为可绕过的子串匹配（别名导入可绕过；contour 扫描仅覆盖 7 个指名文件+workers/ui，非全包）。当前生产树经独立 rg 复核干净，属潜在弱点；897-906 行的 __all__ 内省检查是扎实的
改用 ast.walk 断言 Import/ImportFrom/Call 节点，文件集从 rglob("*.py") 派生
P3-2
test_stage14e_acceptance.py:589-609
oracle 残差公式与生产 helper 是同一冻结合同公式的同源转写、读同一 spec.coefficients：归一化尺度定义错误或分类器系数系统性错误对两者同时不可见。真实的独立性在于点生成路径（参数化 vs 隐式方程）与全点复验；系数推导另有套件钉住
每类型补一条结构性异构检查：钉住期望 PrimitiveEquationCoefficients，或用几何参数（如圆的 (x-h)^2+(y-k)^2-r^2）做第二残差变体
P3-3
test_stage14e_acceptance.py:419-443
11 个几何 fraction 字段（CircleSpec.center_x/center_y、EllipseSpec 四个、HyperbolaSpec.center_y 等）被 receipt 密封且运行时确会比对，但无篡改测试——从 _snapshot_geometry_spec 删掉任一 fraction_fields 条目不会有测试失败
按 14b1:616-636 既有模式逐字段 in-place 篡改断言拒绝
P3-4
test_stage14e_acceptance.py:478-487、test_render_plan.py:388-395
scene-spec 级 item_id 被两种 snapshot 密封（render_plan.py:653/1080）但从未被篡改测试（现有 target 只改 item_plan 级）；test_render_plan.py 的显式 item_plan 篡改列表也整体漏掉 item_id
各补一条 spec.item_id 篡改用例
P3-5
tests/engine/test_render_plan.py
M1 显式 receipt 篡改覆盖实际在此文件（test_stage13_public_api.py 无篡改测试）；显式 snapshot 分支（render_plan.py:886-903）的 image_height/dpi/show_legend 等计划侧拷贝点无篡改测试——几何矩阵不执行该代码路径
为一个显式 plan 镜像 14E 公共矩阵模式补参数化篡改
P3-6
test_stage14c_circle_ellipse.py:925-930（14d1/14d2 同型）
oval/hyperbola/parabola 的中间检查点取消测试不断言返回的 SamplingCancelled.item_id（仅 line 与 14E 首检查点断言）；生产各返回点确传 context id，属缺断言非行为缺陷
三个测试各加一行 item_id 断言
P3-7
stage14_parameterized_probe.py:571-582
J2 裁定：main() 无条件 return 0。判定为 (c) 符合“仅记录证据”的既定边界，非 P0-06 阻塞——探针 docstring/BOUNDARY_STATEMENTS/报告第 7 节均声明 evidence-only，Stage 14 用法是一次性人工查验（本次 bundle 干净：70/70、全部 <2s、全部 neutral，exit 0 未掩盖任何异常）。残余风险：Stage 15 脚本化重跑无机器可读失败信号
bundle 无条件写盘后按 below_two_second_development_screen/typed_failure/cancellation_neutral 分支返回 1（保持 evidence-only 契约），或加 --strict 旗标
P3-8
docs/benchmarks/stage14-parameterized-prototype-v1.md:54
引用不存在的类名 ParameterizedMemoryBudget（全仓唯一匹配即此行，我已亲核；真名 ParameterizedRenderMemoryBudget）
一词改正
￼
一、测试与证据复验摘要（全部第一手执行）
测试复验（bash 等价命令：PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. uv run --locked pytest -q -p no:cacheprovider …）：
命令对象
期望
实测
结果
tests/engine/test_stage14e_acceptance.py tests/benchmarks/test_stage14_parameterized_probe.py
251
251 passed in 12.20s
✅ 0F/0E/0S
全量
2332
2332 passed in 46.09s
✅ 0F/0E/0S
tests/engine
1867
1867 passed in 24.83s
✅
tests/test_stage13_public_api.py
5
5 passed in 0.76s
✅
tests/benchmarks
101
101 passed in 3.89s
✅
Stage 14 六文件联合矩阵（14b1/b2/c/d1/d2/e）
621
621 passed in 15.12s
✅
测试后 git status --short 与基线完全一致——无 bytecode/缓存/结果目录污染。另经 AST 静态重算独立复现全部计数（14E 文件 244 = 5+1+7+5×23+5×11+4+4×5+5+4+6+5+5+5+6+1；探针测试 7；54+97+76+82+68+244=621；全仓 2332），两份新测试文件零 skip/xfail 标记，计数非虚增。
证据包复验（uv run --locked python -B 只读重算）：四个 SHA-256 全部 MATCH（30DF3D7B…/6FBD01F8…/ECFC8A81…/190541EC…）；70 条记录/14 场景；success 70/typed failure 0；total 923,500–70,923,500 ns（全部 <2s，约 28× 裕量）；sample 2–2400；segment 1–2；最大 memory_budget.total_bytes = 69,301,000；cancel probe 25,300–95,700 ns；最慢与最大预算均为 hyperbola-one-branch-split（2400 样本/2 段/19200/19200/32 bytes）；70/70 记录实际缓冲 ≤ 获批预算（含逐项 final_x/final_y/segment_index_range/total 四重比较与 derived fixed/batch/total 恒等式）；cancellation_neutral 全 true、探针调用数全为 1；manifest scenario_order = records 首现序 = summary 聚合序；P50/P95 字样仅存在于否定性免责声明且 formal_percentiles_computed=false、无数值分位字段；environment.json 仅 12 个平台/版本键，无个人路径、无环境变量、无秘密。
基线与边界：git rev-parse HEAD = origin/master = ec11449…；git diff --check 干净；生产 diff 字节级验证仅 docstring 一行；四个版本常量（limits/render-plan/parameterized-sampler/numeric-executor）全部未动；engine/__all__ 逐项与 HEAD 一致。
审计方法披露：多智能体审计共 26 个 agent（9 维度审查 + 对抗核实 + 完整性批评，两轮以补齐两次 API 限流失败），所有 P2 均经独立对抗核实 CONFIRMED；既有审计报告的每一条可静态核验声明（diff 范围、矩阵用例、benchmark 数字、命令文件清单、P0-06 逐行证据、日期链 UTC 2026-08-14T16:04:03Z = 上海 2026-08-15 00:04）均独立复核通过——本报告不是对原报告的转述。
二、未解决风险
1. 竖直双曲线 branch 方向的生产行为当前既无测试锁定、也无动态验证（P2-4 修复将同时补上；现有残差/有限性测试对方向翻转不敏感）。
2. oracle 对归一化尺度定义与分类器系数推导的同源盲区（P3-2）：若冻结合同的尺度公式本身有概念错误，生产与 oracle 一同失明；现有缓解是系数推导另有独立套件钉住。
3. 静态边界检查的子串机制（P3-1）：别名/动态导入可绕过；今日生产树干净，属潜在弱点。
4. 探针无机器可读失败信号（P3-7）：Stage 15 若将筛查脚本化/CI 化需先加固 exit code。
5. 证据包时序（J1 裁定）：git_commit=ec11449 生成于探针/测试/文档未提交之时且未存探针源码 hash。判定：不削弱证据、不构成 P0-06 缺陷——bundle 是被 SHA-256 钉住的冻结证据而非再生承诺；计时数据本就依赖主机，bit-exact 再生不可能；且 bundle 生成时工作树相对 ec11449 的生产代码差异仅一行行为惰性的 docstring（已字节级验证），git_commit 字段准确描述了被测生产代码。建议：随本次提交一并落库（选项 b），使探针源码与证据同 commit；未来协议版本再把 probe-source SHA-256 写入 environment.json（P3 加固）。不建议为此重新生成证据包——会无谓改动三份文档引用的四个 hash，且达不到 bit-exact。
三、最终裁定
REQUEST CHANGES（窄范围：仅上述 5 项 P2；不推翻算法验收、不推翻 P0-06 关闭的实质成立）。修复均为最小文本/测试改动，完成后无需重新审计，重跑 tests/engine/test_stage14d1_hyperbola.py tests/engine/test_stage14e_acceptance.py 及文档哨兵测试即可（全量回归仅 46s，建议顺手重跑）。
四、是否同意
• P0-06 正式关闭：同意——关闭条件逐项独立验证实质满足（含六类取消路径当前行为动态复证中性、70/70 探针、逐字段预算/篡改、独立 oracle）；P2 修复属提交卫生，非关闭条件。
• Stage 14 完成：同意（以上述 P2 修复随同一提交落地为前提）。
• 进入 Stage 15：同意。P0-07 保持打开、正式 P50/P95、真实教材矩阵、renderer/Actor/UI 整合均未开始，各文档声明与此一致，无越权宣称。
五、是否建议提交当前 working-tree diff
不建议按当前状态直接提交。 先完成：① P2-1/2/3 三处文档句子修正（约 5 分钟）；② P2-4/P2-5 两处测试矩阵补齐（照既有 14d2 模式，各约 10 行）；建议同提交顺带 P3-8 一词改正。P3-1~P3-7 可延后至 Stage 15 前的加固任务，不阻塞本次提交。
```
