# 阶段 0B-2：受控依赖基线与 standalone 最小冒烟记录

记录日期：2026-07-20  
状态：**通过，带已知中文字体警告**  
范围：仅登记已确认的依赖基线、构建与实机冒烟结果，以及 P0-01 关闭；不重新审核或验证，不修改源码、正式打包配置、资源或历史产物。

## 1. 已确认的精确基线

| 组件 | 版本 |
| --- | --- |
| CPython | 3.12.11 |
| PySide6 / Qt | 6.11.1 |
| NumPy | 2.5.1 |
| Matplotlib | 3.11.1 |
| ContourPy | 1.3.3 |
| SymPy | 1.14.0 |
| mpmath | 1.3.0 |
| pytest | 9.1.1 |
| Nuitka | 4.1.3 |

已确认结果：`uv sync --locked` 通过；配置、`uv.lock` 与 `.venv` 一致；直接及传递依赖版本核对通过；`main`、`main_window`、`plot_engine` 导入通过；项目环境中的 Nuitka 4.1.3 运行检查通过。

ContourPy、mpmath、shiboken6、PySide6-Essentials 和 PySide6-Addons 均保持传递依赖，不作为项目直接依赖。

## 2. Windows 11 standalone 构建与人工冒烟

构建在 Windows 11 x64 的 Developer PowerShell for Visual Studio 中完成，使用 CPython 3.12.11 x64、Nuitka 4.1.3 和 MSVC `cl` 14.5 x64。模式为 standalone，已启用 PySide6 插件；输出目录为 `deployment\smoke-0b2\main.dist`，主程序为 `deployment\smoke-0b2\main.dist\main.exe`，构建成功。

构建通过 `uv run --locked` 使用项目 `.venv`；未运行 `pyside6-deploy`，未制作 onefile 或安装包，未修改正式打包配置，未删除或覆盖历史 `deployment\main.dist`。standalone 必须以完整目录为运行单位。

Windows 11 人工冒烟结果：启动通过，`y=x^2` 绘图通过，正常关闭通过；未发现缺失 DLL 或残留进程。

## 3. Windows 10 跨机器最小冒烟

同一个新的完整 standalone 目录复制至至少一台 Windows 10 存量设备后，跨机器启动、`y=x^2` 绘图和正常关闭均通过；未发现缺失 DLL 或杀毒阻断。

结论严格限定为：**当前 standalone 候选 Windows 10 跨机器最小冒烟：通过。**

尚未补录 Windows 10 Edition、具体版本、Build、是否预装 Python、DPI、硬件信息和是否为教学一体机。因此，本记录不构成 Windows 10 正式兼容矩阵、Windows 10 1809 及以上全部版本验证、干净无 Python 系统验证、安装/升级/卸载验证或最终 Windows 10 支持声明；这些事项保留至阶段 28–30。

## 4. 已知中文字体警告

Matplotlib 初始占位图“图像预览区域”使用默认 DejaVu Sans 时缺少中文 glyph，显示为方框；Qt 窗口标题和控件中文显示正常。该警告不影响启动、`y=x^2` 绘图或正常关闭，不阻塞 0B-2。

该问题映射至 **P1-04 中文字体 fallback、资源和许可风险**，尚未处理；本任务未修复字体、源码或打包参数。

## 5. P0-01 正式关闭登记

```text
ID：P0-01
核实日期：2026-07-20
核实人：既有实施记录未单列人员姓名；本登记不虚构姓名
批准人/责任角色：项目所有者 / 总架构师（既定裁定）
状态：已关闭
阻塞里程碑：阶段 0 验收
官方来源及版本：既有 0B-1 依赖审计与当前锁定版本记录
原型或实机环境：Windows 11 x64 + MSVC cl 14.5；至少一台 Windows 10 存量设备
观察结果：依赖同步、导入、standalone 构建及两台机器最小冒烟通过
产品决策：P0-01 技术关闭条件满足
降级方案：无
剩余风险：Windows 10 正式矩阵、中文字体、正式打包和发布事项仍待后续阶段
已同步文件：联网确认.md；docs/audits/stage-0B-2-controlled-dependency-baseline-and-smoke.md
下次复查日期：阶段 28–30 或发布候选前
```

P0-01 的关闭范围仅为阶段 0 的精确依赖基线、Windows 11 standalone 最小实机冒烟，以及同一 standalone 候选在至少一台 Windows 10 存量设备的跨机器最小冒烟。它不表示 P0-02 已关闭、阶段 0 已完成、正式打包工具已选定、standalone 已成为最终发布格式、onefile 或安装包已经完成，或 Windows 10 正式兼容矩阵已经完成。

## 6. 明确未完成事项与停止边界

* **P0-02：仍未关闭。**
* **阶段 0：仍未完成。**
* `pysidedeploy.spec` 的绝对路径问题尚未处理。
* **P1-04** 中文字体 fallback、资源和许可风险尚未处理。
* 正式打包工具与发布格式留待阶段 28 再决定。
* Windows 10 正式兼容矩阵留待阶段 28–30 完成。

本记录不创建 0B-3，也不进入阶段 1。
