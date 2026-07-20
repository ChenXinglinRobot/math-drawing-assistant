# 阶段 0B-3：退役遗留 `pysidedeploy.spec` 记录

记录日期：2026-07-20  
范围：仅处置受 Git 跟踪的遗留实验配置；未运行打包、测试、安装或同步，未修改源码、依赖、正式打包配置或 `deployment/` 历史产物。

## 只读确认

已确认旧 `pysidedeploy.spec` 包含开发机绝对路径、旧项目名 `pyside_app_demo`、`Nuitka==4.0` 和早期实验性 `pyside6-deploy` 配置。仓库引用搜索未发现 `.py`、`.ps1`、`.cmd`、`.bat`、构建脚本、CI、任务配置或当前有效命令读取该文件；命中仅为 `.gitignore` 忽略规则及审计/风险/候选工具说明，不构成运行依赖。

## 处置与边界

已删除旧实验性部署配置。删除原因是其开发机绝对路径、旧项目名和过时工具版本容易造成误用。

该删除不代表放弃 `pyside6-deploy` 或 Nuitka，也不选择 standalone、onefile、`pyside6-deploy` 或其他正式发布方案；正式打包工具和配置仍留待阶段 28 决定。

0B-2 冒烟直接通过 `uv run --locked python -m nuitka` 使用 Nuitka 4.1.3 构建；该次构建未使用 `pysidedeploy.spec`。

阶段 0 仍未因此通过，本记录不进入阶段 1。
