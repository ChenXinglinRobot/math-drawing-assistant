# 阶段 0B-1：精确 Python 与依赖基线只读审计报告

审计日期：2026-07-19  
状态：只读审计完成；候选矩阵等待项目所有者批准。

## 1. 审计范围与明确边界

原只读审计依据最新的“架构同步版”清单，只审计当前工作树、已存在 `.venv`、分发元数据、锁文件和官方资料；未安装、升级、降级或卸载任何包，未运行 `uv sync`、`uv add`、`uv lock`、GUI、打包或测试，也未处置 `pysidedeploy.spec`。本次外部审核反馈修订仅校正本报告文字，未重新执行本地审计或联网调查。

用户授权的唯一写入是本报告；除本报告外未创建或修改仓库文件。下文的“拟动”均是阶段 0B-2 经批准后才可执行的建议，不是本轮操作。

## 2. 初始 Git 状态

采集时间在本报告创建前。分支为 `master`，`git status --short --branch` 为：

```text
## master...origin/master
 M 联网确认.md
?? docs/audits/
```

暂存区为空；未暂存的用户改动为 `联网确认.md`；已有未跟踪文件为 `docs/audits/stage-00a-environment-dependency-audit-2026-07-19.md`。`.python-version`、`pyproject.toml`、`uv.lock`、`pysidedeploy.spec` 均受 Git 跟踪。本审计没有恢复、暂存、覆盖或改动这些既有内容。

初始 SHA-256：

| 文件 | SHA-256 |
| --- | --- |
| `.python-version` | `7B55F8E67B5623C4BEF3FA691288DA9437D79D3ABA156DE48D481DB32AC7D16D` |
| `pyproject.toml` | `BD841E1CF23A925E21CFCDDE832CD4FE734D79E0C2550A57498FFD0F2A665D2F` |
| `uv.lock` | `E264A7ACFF8EC8101FB25556D51E9FA55F550BE43B18C36DF91701763BEBB160` |

## 3. 必读材料及版本 / 路径

已读取：`数学绘图助手 PRD.md` v0.3（2026-07-19）、`数学绘图助手_Codex协助开发步骤清单_v0.3.md` v0.3（架构同步版，2026-07-19）、`README.md`、`docs/architecture.md` v0.1、`docs/decisions.md` v0.1、`联网确认.md`、阶段 0A 报告 `docs/audits/stage-00a-environment-dependency-audit-2026-07-19.md`、独立审核报告 `docs/Claude_Fable5_规划文档审核报告_2026-07-19.md`，以及三份目标配置文件。

优先级采用：最新规范文档 → 当前工作树的三份配置 → 阶段 0A 的历史事实 → 独立审核报告。尤其，实际执行依据是清单首页明确标为“v0.3（架构同步版）”的文件：它已将完整请求纳入唯一 `RenderActor`、将单项 `RenderPlanBuilder` 放入阶段 8，并明确每次依赖安装、升级和 Pyright 配置均需当次批准。没有采用早期含同步快速路径、旧 Worker 名称或旧阶段编号的副本。

## 4. 当前终端环境

此处仅是当前终端事实，不是项目环境，也不进入候选列：

| 项目 | 事实 |
| --- | --- |
| `python` 实际路径 / `sys.executable` | `C:\ProgramData\anaconda3\python.exe` |
| 解释器 | Anaconda CPython 3.12.4，64 位 |
| `sys.prefix` / `sys.base_prefix` | 均为 `C:\ProgramData\anaconda3`；非虚拟环境 |
| 已安装目标包 | NumPy 1.26.4、Matplotlib 3.8.4、ContourPy 1.2.0、SymPy 1.13.1、pytest 9.0.2 |
| 未安装目标包 | PySide6、shiboken6、PySide6_Essentials、PySide6_Addons、Nuitka、Pyright |

## 5. 仓库 `.venv` 环境

此处是现有仓库环境事实，仍不等于已批准的基线：

| 项目 | 事实 |
| --- | --- |
| 解释器路径 / `sys.executable` | `D:\Python_work\math-drawing-assistant\.venv\Scripts\python.exe` |
| 解释器 | CPython 3.12.11，64 位 |
| `sys.prefix` | `D:\Python_work\math-drawing-assistant\.venv` |
| `sys.base_prefix` | `C:\Users\Chen Xinglin\AppData\Roaming\uv\python\cpython-3.12.11-windows-x86_64-none` |
| 是否虚拟环境 | 是 |
| PySide6 / shiboken6 / Essentials / Addons | 均为 6.11.1 |
| Qt runtime | 6.11.1（`PySide6.QtCore.qVersion()`） |
| NumPy / Matplotlib / ContourPy | 2.5.1 / 3.11.1 / 1.3.3 |
| SymPy / pytest / Pyright | 均未安装 |
| Nuitka | 4.1.3 |

## 6. 当前终端与仓库 `.venv` 的明确区分

当前终端不是项目 `.venv`。因此终端里的 SymPy 1.13.1 和 pytest 9.0.2 只记录为外部环境事实，不是项目候选的来源；项目候选由官方发布/包元数据、当前锁文件和架构需要共同决定。`.venv` 反映现有仓库可观察状态，`uv.lock` 才是可重建输入；二者相符也不表示完整依赖基线已经批准。

## 7. `.python-version` 摘要

当前原文为 `3.12`（仅固定 major.minor，未固定 patch）。它的职责是开发、重建和工具选择解释器，不能单独声明项目对用户的兼容范围。

## 8. `pyproject.toml` 摘要

当前 `requires-python = ">=3.12"`：有开放下限且无上限。运行时直接依赖为 `matplotlib>=3.11.1`、`numpy>=2.5.1`、`pyside6>=6.11.1`；dev 组为 `nuitka>=4.1.3`、其辅助依赖。SymPy、pytest、Pyright 均未声明；无平台 marker。

无上限的 `>=3.12` 会在以后解析时接受未验收的 3.13/3.14，且容许直接依赖漂移到未验证新版本；这与“固定经过验证的组合”不符。它不是要求 `.python-version` 与 `requires-python` 机械写成相同字符串的理由。

## 9. `uv.lock` 摘要

锁格式为 `version = 1`、`revision = 3`、`requires-python = ">=3.12"`。项目包记录的直接运行时依赖只有 PySide6、NumPy、Matplotlib；Nuitka 属 `dev`。锁定版本为 PySide6 / shiboken6 / Essentials / Addons 6.11.1，NumPy 2.5.1，Matplotlib 3.11.1，ContourPy 1.3.3，Nuitka 4.1.3；未锁 SymPy、pytest 或 Pyright。

依赖边为：`pyside6 → pyside6-addons, pyside6-essentials, shiboken6`；`matplotlib → contourpy, numpy, cycler, fonttools, kiwisolver, packaging, pillow, pyparsing, python-dateutil`；`contourpy → numpy`。同一 PySide6 族版本一致。

## 10. Context7 查询记录

先调用 `resolve-library-id`，再按下表问题调用 `query-docs`。Context7 仅作补充；无法覆盖精确版本时，最终结论回落到官方发布页/PyPI 元数据。

| 组件 | Context7 ID | 查询问题（摘要） | 覆盖精确候选？ | 结论 / 局限 |
| --- | --- | --- | --- | --- |
| CPython | `/python/cpython` | 3.12.10/11/13 生命周期与 Windows 安装器 | 否 | 返回主干源码片段，不能作为精确版本证据。 |
| PySide6 | `/websites/doc_qt_io_qtforpython-6` | 6.11.1 的 Python/Windows 支持 | 否 | 只说明一般 Python 3.10+ 安装资料。 |
| NumPy | `/numpy/numpy` | 2.5.1 Python/Windows 支持 | 否 | 返回主干依赖策略，未覆盖 2.5.1。 |
| Matplotlib | `/websites/matplotlib_stable` | 3.11.1 Python/NumPy 兼容 | 否 | 只给稳定分支最小依赖政策概述。 |
| ContourPy | `/contourpy/contourpy` | 1.3.3 Python/NumPy 兼容 | 否 | 只确认 NumPy 是运行时依赖。 |
| SymPy | `/sympy/sympy` | 1.14.0 Python 要求和 LaTeX 状态 | 部分 | 官方源码文档确认 LaTeX 解析仍为 experimental，未给 1.14.0 元数据。 |
| pytest | `/pytest-dev/pytest` | 9.0.2 Python 支持 | 系列级 | 官方源码文档明确 pytest 9.0+ 支持 Python 3.10+。 |
| Nuitka | `/websites/nuitka_net` | 4.1.3 发布元数据 | 否 | 仅覆盖 4.1 系列变更，不用于选型。 |

## 11. 精确版本候选矩阵

“保留”表示当前精确锁定组合没有阶段 0 的兼容、安全、官方构建缺失或不可重建证据要求改变；不是“有更新即升级”。官方证据均是下表 URL 所示的官方项目发布页或官方 PyPI 元数据。

| 组件 | 当前约束 | 锁 / `.venv` | 推荐精确候选 | 状态 | Requires-Python | 依赖性质 | 理由与官方证据 | 0B-2 拟动作 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CPython | `.python-version=3.12`; `>=3.12` | 3.12.11 / 3.12.11 | **3.12.11** | 暂定保留候选 | 核心包均覆盖 3.12 | 解释器 | 项目现有 `.venv` 是 uv-managed CPython 3.12.11，且已有导入与历史最小冒烟事实。uv-managed CPython 不依赖 python.org 传统 Windows 安装器；uv 可以请求精确 Python patch，但当前本机 uv 是否仍能提供或重新安装精确 3.12.11，须后续只读本地验证。3.12.10 是最后有官方 Windows x86-64 安装器的完整 3.12 维护版，但传统安装器缺失不足以构成回退理由；3.12.13 只是未验证的后续安全升级候选。证据：[3.12.10](https://www.python.org/downloads/release/python-31210/)、[3.12.11](https://www.python.org/downloads/release/python-31211/)、[3.12.13](https://www.python.org/downloads/release/python-31213/)。 | 先只读确认当前 uv 版本与精确 patch 可用性；经批准后才固定或重建。 |
| PySide6 / Qt | `>=6.11.1` | 6.11.1 / 6.11.1 | **6.11.1** | 保留 | `>=3.10,<3.15` | 运行时直接；Qt 及拆分包传递 | 官方 PyPI 的 6.11.1 元数据及 Windows x86-64 wheel；当前锁和 `.venv` 四个拆分包/Qt 一致。没有阶段 0 必须调整理由。[PySide6 6.11.1](https://pypi.org/project/PySide6/6.11.1/) | 仅把顶层 PySide6 固定；不新增拆分包。 |
| shiboken6 / Essentials / Addons | 未直接声明 | 6.11.1 / 6.11.1 | **6.11.1**（随 PySide6） | 保留 | `>=3.10,<3.15`（已装元数据） | PySide6 传递 | 由 PySide6 的精确依赖带入并需保持同版；不是项目直接依赖。 | 不写入 `pyproject.toml`。 |
| NumPy | `>=2.5.1` | 2.5.1 / 2.5.1 | **2.5.1** | 保留 | `>=3.12` | 运行时直接 | 官方 2.5.1 元数据列 Python 3.12/Windows，且有 cp312 win_amd64 wheel；当前组合已锁定。没有必须变更理由。[NumPy 2.5.1](https://pypi.org/project/numpy/2.5.1/) | 固定顶层版本。 |
| Matplotlib | `>=3.11.1` | 3.11.1 / 3.11.1 | **3.11.1** | 保留 | `>=3.11` | 运行时直接 | 当前锁的官方发布资产含 cp312 win_amd64 wheel；已声明对 NumPy `>=1.25`、ContourPy `>=1.0.1` 的传递约束。没有阶段 0 必须调整理由。[Matplotlib](https://pypi.org/project/matplotlib/) | 固定顶层版本。 |
| ContourPy | 未直接声明 | 1.3.3 / 1.3.3 | **1.3.3**（锁中保留） | 保留 | `>=3.11` | Matplotlib 的传递依赖 | 官方 1.3.3 元数据有 cp312 win_amd64 wheel，且当前锁满足 Matplotlib 约束。当前代码没有直接导入、独立 API 契约或单独约束理由，故不得提升为直接依赖。[ContourPy 1.3.3](https://pypi.org/project/contourpy/) | 保持传递；受控锁中复核。 |
| SymPy | 未声明 / 未锁 / 未装 | — | **1.14.0** | 新增候选 | `>=3.9` | 运行时直接 | PRD/架构要求数学引擎将受限 AST 转为 SymPy/NumPy 函数；官方 1.14.0 是稳定发布、列 Python 3.12，纯 Python 发行包仅需 mpmath。选择它不基于终端 1.13.1；不使用其宽松解析器作为安全边界，LaTeX API 仍是实验性。[SymPy 1.14.0](https://pypi.org/project/sympy/1.14.0/)、[官方解析文档](https://docs.sympy.org/latest/modules/parsing.html) | 添加运行时直接依赖并同步 mpmath。 |
| pytest | 未声明 / 未锁 / 未装 | — | **9.0.2** | 新增候选 | `>=3.10` | 测试/dev 组 | 官方稳定 9.0.2 元数据列 Python 3.12/Windows；pytest 官方兼容文档说明 9.0+ 支持 3.10+。选择依据官方元数据，不是终端已安装这一事实。[pytest 9.0.2](https://pypi.org/project/pytest/9.0.2/) | 仅添加至 dev/test 组。 |
| Nuitka | dev `>=4.1.3` | 4.1.3 / 4.1.3 | **4.1.3（仅记录）** | 仅记录 | 已装 METADATA 无 `Requires-Python` 字段 | dev | 当前声明、锁和 `.venv` 一致；`pysidedeploy.spec` 的 `Nuitka==4.0` 是独立遗留差异。本轮不选择或变更打包工具。[Nuitka 4.1.3](https://pypi.org/project/Nuitka/4.1.3/) | 保持原状；阶段 28 再选型。 |

## 12. Python 3.12.11 与其他候选比较

| 比较项 | Python 3.12.11 | 当前最新受支持 3.12：3.12.13 | 其他候选：3.12.10 |
| --- | --- | --- | --- |
| 发布日期 | 2025-06-03 | 2026-03-03 | 2025-04-08 |
| 生命周期 | security-only | security-only | 最后完整维护版 |
| 官方 Windows x86-64 安装器 | 无 | 无 | 有 |
| PySide6 / NumPy / Matplotlib / ContourPy / SymPy / pytest | 元数据范围均兼容 3.12 | 同为 3.12，元数据范围允许 | 元数据范围均兼容 3.12 |
| 与本项目的关系 | 当前仓库已有 uv-managed `.venv`、导入和历史最小冒烟证据；精确 patch 的未来可用性待本地确认 | 安全升级候选，尚无本项目本地验证 | 最后一个带传统安装器的 3.12 版本，但缺少后续安全修复 |
| 保留 / 调整风险 | 暂定保留；不把传统安装器缺失误作回退理由 | 不因更新而自动替换；需另行批准及同等受控验证 | 回退会引入重建/回归成本，且无阶段 0 必要理由 |

最终单一推荐：**阶段 0B-2 暂定保留 CPython 3.12.11。开始修改配置前，先以只读方式确认当前 uv 版本及其精确 patch 可用性。Python 3.12.13 作为后续安全升级候选，只有在另行批准并完成同等受控验证后才可替换。不得仅为传统安装器回退到 3.12.10。**

`.python-version` 拟为 `3.12.11`，用于固定项目开发和重建使用的精确解释器；`requires-python` 拟为 `>=3.12,<3.13`，用于声明项目允许的 Python 兼容范围。二者职责不同，不要求写成相同形式；两项均待项目所有者批准，尚未实际修改。

## 13. SymPy 单一推荐候选

唯一候选为 **SymPy 1.14.0**，作为运行时直接依赖。理由：它是 PyPI 的稳定正式发布，`Requires-Python >=3.9` 并列出 Python 3.12；与暂定 CPython 3.12.11 相容；发行物是纯 Python，官方传递约束为 `mpmath>=1.1.0,<1.4`。具体 mpmath 精确版本必须由后续受控 `uv` 锁定解析决定，不手工预选或安装。未选终端的 1.13.1，因为终端不是项目环境，且它并非基于本项目的版本裁决。

SymPy 的 LaTeX 解析在官方文档中仍标为实验性，可能需要 `antlr-python-runtime`；本项目不得因此把额外 LaTeX parser 或宽松解析器加入依赖，也不得绕开自有受限 AST 和完整消费验证。

## 14. pytest 单一推荐候选

唯一候选为 **pytest 9.0.2**，只进入测试/dev 依赖组。其官方 PyPI 元数据要求 Python `>=3.10`、列出 Python 3.12 和 Windows；这与暂定解释器相容。它是真实、稳定且兼容 Python 3.12 的固定候选；截至外部审核所依据资料时间点，已不是 pytest 的最新版本，选择它不是因为“最新版”。当前 Anaconda 终端恰好安装 pytest 9.0.2，不构成项目候选证据。它不是运行时依赖，且 Pyright 不随之加入：D-009 仍是阶段 5 的当次批准项。

## 15. 保留、调整、新增、仅记录的理由

* 保留：PySide6/Qt 6.11.1、NumPy 2.5.1、Matplotlib 3.11.1、ContourPy 1.3.3（传递）、Nuitka 4.1.3（仅记录）。不存在已证明的阶段 0 兼容、安全、缺 wheel 或不可重建理由。
* 暂定保留候选：CPython 3.12.11。现有 uv-managed 环境、导入和历史最小冒烟支持保留；后续只读确认当前 uv 的精确 patch 可用性。不得仅因缺少传统安装器回退至 3.12.10；3.12.13 仅为尚未验证的安全升级候选。
* 新增候选：SymPy 1.14.0（运行时数学引擎需求）和 pytest 9.0.2（测试需求）。
* 不新增：ContourPy、shiboken6、PySide6_Essentials、PySide6_Addons、Pyright。前四者没有项目直接依赖理由；Pyright 受 D-009 延后。

## 16. 后续拟修改清单

### 16.1 `.python-version`

当前：`3.12`。拟议：`3.12.11`。它固定开发/重建使用的精确解释器；uv-managed Python 不依赖 python.org 传统 Windows 安装器。开始配置修改前仍须以只读方式确认当前 uv 能提供或重新安装精确 3.12.11；必须由项目所有者批准，尚未实际修改。

### 16.2 `pyproject.toml`

| 项目 | 当前 | 拟议（均待批准） | 组 / 理由 | 对锁影响 |
| --- | --- | --- | --- | --- |
| `requires-python` | `>=3.12` | `>=3.12,<3.13` | 兼容声明，不等同 `.python-version` | 重新解析标记与 Python 条件。 |
| PySide6 | `>=6.11.1` | `==6.11.1` | runtime；固定已锁组合 | 顶层与拆分包维持 6.11.1。 |
| NumPy | `>=2.5.1` | `==2.5.1` | runtime；固定已锁组合 | 保持 2.5.1。 |
| Matplotlib | `>=3.11.1` | `==3.11.1` | runtime；固定已锁组合 | 保持 3.11.1 及传递边。 |
| SymPy | 无 | `sympy==1.14.0` | runtime 数学引擎 | 新增 SymPy 与 mpmath。 |
| pytest | 无 | `pytest==9.0.2` | dev/test | 新增 pytest 及其传递依赖。 |
| ContourPy | 无 | 不声明 | 保持 Matplotlib 传递依赖 | 锁中受控复核 1.3.3。 |
| Nuitka | `>=4.1.3` | 保持原状 | 阶段 28 前仅记录 | 预期 4.1.3 不变。 |
| Pyright | 无 | 不加入 | D-009 / 阶段 5 另行批准 | 不应出现。 |

### 16.3 `uv.lock`

批准后才执行一次受控同步/锁更新，不手工伪造锁内容；需记录命令、解释器、缓存隔离、解析前后差异和 Windows 11 冒烟。预期新增 SymPy、mpmath、pytest 及 pytest 传递依赖；核心 PySide6/Qt、NumPy、Matplotlib、ContourPy、Nuitka 应保持上述版本，除非解析结果有可审计的官方约束理由。

## 17. 0B-2 严格文件白名单

默认且严格的白名单仅为：

```text
.python-version
pyproject.toml
uv.lock
```

任何 Python 源文件、README、PRD、`联网确认.md`、architecture、decisions、其他 docs、`pysidedeploy.spec`、目录骨架、测试、打包或 CI 文件均不在白名单内。若三文件不足，必须另开子任务并取得批准；不得“顺手同步文档”。

## 18. Windows 10 历史最小 standalone 冒烟证据与字体记录

项目所有者确认的事实属于**用户提供的历史最小 standalone 跨机器运行冒烟证据**：早期最小 standalone 应用先在 Windows 11 开发机运行成功；同一 standalone 目录复制到另一台 Windows 10 电脑后能够启动，并成功生成 `y=x^2`。两台机器均出现同一 Matplotlib 中文 glyph 缺失警告，但该警告没有阻止程序启动和基本绘图。

该事实的边界是：尚不知道该产物的完整精确构建记录，亦不能确认其中 Python、PySide6、NumPy、Matplotlib、ContourPy 和 Nuitka 的精确版本；Windows 10 的 Edition、版本、Build、DPI 与设备配置也未知。它不等于当前最终候选依赖矩阵的 Windows 10 验证，不等于完整 Windows 10 发布兼容矩阵，不能关闭 P0-01。准确状态为：**已有一次用户确认的历史最小 standalone Windows 10 跨机器实机冒烟，但尚未完成最终批准依赖组合的 Windows 10 验证。**

Matplotlib 尝试渲染“图像预览区域”对应的中文 glyph 时，DejaVu Sans 缺少相应字形。Windows 11 与 Windows 10 的实际界面均未正常显示目标文字，而是出现六个方框状缺字占位符，视觉上近似“字字字字字字”。该问题属于字体 fallback 或字体资源覆盖不足，不属于应用启动失败、解释器失败或 standalone 构建失败。

该字体问题不阻塞阶段 0B-1，也不否定 `y=x^2` 最小运行冒烟成功；但它是视觉正确性和打包资源风险，正式 UI 或图片仍出现时不能通过最终视觉验收。阶段 27 才处理授权字体与 fallback，阶段 28 验证字体资源和许可证进入打包产物，阶段 30 在干净 Windows 11/10 环境复验。本轮不修改代码或字体资源。

## 19. 尚未解决的风险

* 元数据和 wheel 不能证明完整运行组合或应用行为。
* 尚未执行受控同步、也未安装/验证 SymPy 或 pytest 候选。
* 当前 uv 是否能重新提供精确 Python 3.12.11，尚待后续本地只读确认；Python 3.12.13 是安全升级候选但尚未验证。
* 尚未完成最终候选依赖组合的完整 Windows 11 冒烟；Windows 10 已有历史最小 standalone 实机证据，但其精确构建版本未知，且最终候选组合尚未完成 Windows 10 验证或批准的降级。
* Windows 11 与 Windows 10 均有相同的中文字体缺字占位问题：不影响最小启动和绘图结论，但影响视觉正确性。
* Qt/包元数据中的平台声明不等于本项目在目标设备通过。
* RenderActor 原型属于 P0-04，本轮没有关闭。
* `pysidedeploy.spec` 含绝对路径且记录 `Nuitka==4.0`，与当前锁 4.1.3 不一致；本轮未处置。
* 正式打包工具、许可证和发布义务仍属阶段 28 / P0-15。

## 20. 外部审核与本地验证边界、资料需求

| 事项 | 可由官方互联网资料核验 | 必须由本地 Codex 或用户验证 |
| --- | --- | --- |
| Python 3.12 生命周期 | 是 | 否 |
| uv-managed Python 的一般机制 | 是 | 否 |
| 当前本机 uv 精确版本 | 否 | 是 |
| 本机 uv 是否能提供 3.12.11 或 3.12.13 | 否 | 是 |
| 当前 `.venv` 的 Python 和依赖版本 | 否 | 是 |
| `pyproject.toml`、`uv.lock` 的实际内容 | 否 | 是 |
| PyPI 公共 Requires-Python 和公开 wheel | 是 | 否 |
| 实际锁定和安装的 wheel | 否 | 是 |
| 受控同步 | 否 | 是 |
| Windows 11 冒烟 | 否 | 是 |
| Windows 10 历史冒烟 | 否 | 是（项目所有者已提供事实） |
| 最终候选组合的 Windows 10 验证 | 否 | 是 |
| 字体实际显示 | 否 | 是 |
| Git 状态和文件哈希 | 否 | 是 |

此前报告中的 Git、路径、版本和 SHA-256 是 Codex 已采集的本地审计证据；外部审核者没有独立访问本机验证这些事实。

外部官方资料需求：无。现有官方 Python 发布页、官方 PyPI 精确版本元数据和官方 SymPy 文档足以形成候选。

本地验证需求：当前 uv 精确版本；uv 可提供的精确 Python patch；受控同步后的实际依赖；历史 standalone 产物对应版本；Windows 10 具体系统信息；以及中文字体修复后的实际显示。这些需求不授权本轮进行安装、同步或实机验证。

## 21. P0-01 状态

**仍未关闭。**Windows 10 已不再是完全没有实机证据：已有用户确认的历史最小 standalone 跨机器冒烟；但最终批准组合仍未完成 Windows 10 验证。按照阶段 0A 和 `联网确认.md`，仍需项目所有者批准候选矩阵、阶段 0B-2 的受控同步、完整 Windows 11 冒烟，以及 Windows 10 实机验证或得到批准的降级记录。

## 22. 最终 Git 状态与文件哈希

初始只读审计时已存在 `联网确认.md` 的用户改动，以及 `docs/audits/` 下未跟踪或待跟踪的报告；不得将仓库误报为 clean。本次外部审核反馈修订仅修改本报告文字，未恢复、暂存、覆盖或改动既有内容。

本次修订完成后的只读 Git 核验：分支仍为 `master`，`git status --short --branch` 仍显示 ` M 联网确认.md` 与 `?? docs/audits/`；暂存区为空。对 `.python-version`、`pyproject.toml`、`uv.lock` 和 `pysidedeploy.spec` 的暂存与未暂存差异检查均无输出、退出码为 0。相对于本次修订开始前，本轮唯一新增变化是本报告的文字修订。

三个目标文件均无暂存或未暂存 diff，最终 SHA-256 与第 2 节逐项相同：

| 文件 | 最终 SHA-256 | 与初始快照 |
| --- | --- | --- |
| `.python-version` | `7B55F8E67B5623C4BEF3FA691288DA9437D79D3ABA156DE48D481DB32AC7D16D` | 相同 |
| `pyproject.toml` | `BD841E1CF23A925E21CFCDDE832CD4FE734D79E0C2550A57498FFD0F2A665D2F` | 相同 |
| `uv.lock` | `E264A7ACFF8EC8101FB25556D51E9FA55F550BE43B18C36DF91701763BEBB160` | 相同 |

原只读审计没有创建临时目录：Python 元数据命令使用 `-B` 与 `PYTHONDONTWRITEBYTECODE=1`，未下载包或使用 Matplotlib 缓存，因此外部临时目录清理记录为“不适用（未创建）”。阶段 0A 的历史临时目录清理记录不被重用为本轮证据。本次文字修订未创建临时目录。

## 23. 停止声明

阶段 0B-1：只读审计已完成，精确版本矩阵等待项目所有者批准。

P0-01：仍未关闭。本任务只完成版本候选、证据和后续修改边界。

阶段 0B-2：尚未开始，未授权修改 `.python-version`、`pyproject.toml` 或 `uv.lock`。

Pyright：继续按 D-009 推迟到阶段 5，本任务未安装、未配置、未选定版本。

Nuitka：仅记录当前状态，正式打包工具仍属于阶段 28。

Windows 10：已有用户确认的历史最小 standalone 跨机器实机冒烟，但未因依赖资料自动验证最终候选组合或关闭风险。

停止：本次仅修订本报告文字；不修改任何配置或代码，不安装、同步、测试或打包，不处置 `pysidedeploy.spec`，不创建提交/checkpoint/tag/分支，不进入阶段 0B-2 或阶段 1。
