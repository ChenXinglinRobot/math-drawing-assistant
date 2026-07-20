# 阶段 0A：环境与依赖资料审计记录

审计日期：2026-07-19  
状态：通过（只读审计交付物）；不代表阶段 0、P0-01 或 P0-02 已关闭。

## 1. 范围与边界

本记录汇总阶段 0A 只读审计及补正结果。审计未修改项目配置、锁文件或依赖，未安装/升级/删除依赖，未运行 GUI 事件循环、完整测试套件、打包命令或 Git 写操作。

阶段 0A 通过仅表示：当前仓库、环境、依赖资料、遗留产物与待决事项已经盘点，可作为后续阶段 0B 的决策输入。它不授权自动进入阶段 0B。

## 2. Git 与目录基线

* 分支：`master`；审计开始和结束时工作区、暂存区及未跟踪文件均为空。
* 根目录现有 `main.py`、`main_window.py` 和 `plot_engine.py` 是早期演示骨架，不代表目标架构已实现。
* `math_drawing_assistant/`、`tests/`、`resources/` 当前不存在；`docs/` 存在。
* `deployment/`、`pyside_app_demo.dist/`、`.venv/` 与根目录 `__pycache__/` 均为既有忽略项；本轮未删除或改写它们。

## 3. 系统与设备事实（补正后）

| 项目 | 事实 | 证据与说明 |
|---|---|---|
| 系统家族 | Windows 11 | Microsoft 将 OS Build 26200 对应为 Windows 11 25H2。 |
| Edition | Home China | 注册表辅助字段；其 `ProductName` 标签陈旧地写作 Windows 10，不能覆盖 Build 对应关系。 |
| DisplayVersion | 25H2 | 注册表辅助字段。 |
| Build | 26200.8655 | `cmd /c ver` 与注册表 Build/UBR 相互对应。 |
| 架构 | x64 | 运行时架构查询。 |
| CPU | Intel Core Ultra 9 185H | 只读注册表查询。 |
| 逻辑处理器 | 22 | .NET 运行时查询。 |
| 主显示器 | 1536×960，观察到 1 块显示器 | Windows Forms 只读查询。 |
| 项目盘 | 总 451.64 GiB、可用 48.73 GiB | .NET `DriveInfo`；替代先前无效的 0 GiB 结果。 |

`Get-ComputerInfo` 的 `WindowsProductName=Windows 10 Home China`、`WindowsVersion=2009` 与 Build 26200 冲突，且多个 OS 字段为空；已记录为陈旧/不完整来源。当前设备不得作为 Windows 10 实机证据。

物理核心数、总内存、可靠 DPI/缩放、触控、教学一体机属性和电源模式尚未确认。

## 4. Python、依赖与锁文件

### 当前终端

* CPython 3.12.4，非仓库 `.venv`。
* 已安装 NumPy 1.26.4、Matplotlib 3.8.4、ContourPy 1.2.0、SymPy 1.13.1、pytest 9.0.2。
* 未安装 PySide6、shiboken6、Nuitka、Pyright。

### 仓库 `.venv`

* CPython 3.12.11，PySide6/shiboken6/Qt 6.11.1。
* NumPy 2.5.1、Matplotlib 3.11.1、ContourPy 1.3.3、Nuitka 4.1.3。
* SymPy、pytest、Pyright 未安装。

### 配置/锁文件结论

* `.python-version=3.12` 与 `requires-python=>=3.12` 语义相容，但均未固定精确补丁版本。
* `uv.lock`（format 1/revision 3）静态上与 `pyproject.toml` 的直接依赖相对应。
* 仓库 `.venv` 的核心版本与锁文件一致；当前终端环境与其不一致。
* 本轮未执行会触发解析或同步的 uv 命令，故不能把锁文件一致性判为最终通过。

## 5. 外部资料与精确 Python 范围

* PySide6 6.11.1 的已安装 wheel 元数据为 `Requires-Python: >=3.10,<3.15`，明确支持 Python 3.12。
* NumPy 2.5.1 的已安装元数据为 `Requires-Python: >=3.12`；其官方 release notes 明确支持 Python 3.12–3.14。
* Qt 6.11 官方平台资料确认 Windows 10 1809+ 与 Windows 11 的 x86_64 支持；这不替代本项目的 Windows 实机验证。
* SymPy 属于 P0-01 所需固定组合，候选版本资料优先级为 P0；本轮未选择、安装或锁定最终 SymPy 版本。

精确 Python 范围已确认，不等同于依赖组合、应用功能或目标平台验证完成。

## 6. 最小模块导入检查

使用仓库现有 `.venv`，以 `python -B` 导入 `main`、`main_window` 与 `plot_engine`，同时设置 `PYTHONDONTWRITEBYTECODE=1`，并将 `MPLCONFIGDIR` 定向到仓库外的独立 `<TEMP>` 目录。

| 模块 | 结果 | 说明 |
|---|---|---|
| `main` | 成功 | 未执行 `__main__` 入口。 |
| `main_window` | 成功 | 未创建 `QApplication`。 |
| `plot_engine` | 成功 | 未绘图、未启动事件循环。 |

Matplotlib 尝试在隔离临时目录建立字体缓存时遇到权限拒绝；三个模块均已成功导入。临时目录随后被确认清理，仓库内未新增 `.pyc`、Matplotlib 缓存、日志、构建产物或 Git 变化。

## 7. 用户确认的最小冒烟与既有打包产物

用户确认：此前已在当前 Windows 11 开发机完成最小冒烟，能够绘制 `y=x^2`，并已生成 `.exe` 包。

对话附件中的资源管理器截图显示既有 `deployment/main.dist/` 中存在 `main.exe`，并包含 PySide6、NumPy、Matplotlib、ContourPy 等运行时文件。该截图可作为“既有 standalone 打包目录和主可执行文件存在”的用户提供证据；截图本身不直接展示曲线画面，因此 `y=x^2` 绘图成功按用户明确确认记录，而不是本轮重复执行结论。

本轮未运行 `.exe`、未启动 GUI、未重新打包。该最小冒烟不构成阶段 0 的完整 Windows 11 应用冒烟，也不构成 Windows 10 验证、正式发布验证或阶段 28 打包工具选型结论。

## 8. `pysidedeploy.spec` 与遗留产物

`pysidedeploy.spec` 已受 Git 跟踪，且包含开发机绝对路径、旧项目名 `pyside_app_demo` 和 `Nuitka==4.0`，与当前锁定 Nuitka 4.1.3 不一致。

在该文件保留现状时，阶段 0 的“仓库无开发机绝对路径”检查不能通过。本轮不修改；应在阶段 0B 前或阶段 0B 内创建获批的遗留配置处置子任务，并先扩展允许修改文件，再决定改写、移除或归档。正式打包工具选择仍推迟至阶段 28。

## 9. P0 状态

### P0-01：锁定可复现依赖基线

当前不可关闭。已取得当前配置、锁定版本、仓库 `.venv`、精确 Python 范围及 Windows 11 最小导入/用户最小冒烟证据；仍需要最终版本批准、阶段 0B 受控同步、完整 Windows 11 冒烟，以及 Windows 10 实机验证或项目所有者批准的降级记录。

### P0-02：确定课堂基准设备

当前不可关闭。已取得部分开发机资料；仍缺内存、物理核心、可靠 DPI/缩放、触控和教学一体机信息，并需要项目所有者决定是否将当前开发机作为临时代表设备。

## 10. 阶段 0A 结论

* 阶段 0A：通过。
* P0-01：尚未关闭。
* P0-02：尚未关闭。
* 阶段 0：尚未完成。
* 阶段 0B：等待总架构师方案和项目所有者明确批准。

