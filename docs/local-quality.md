# 本地质量与类型政策

状态：阶段 5 工具无关基线。

## 类型政策

- 公开函数和方法标注参数与返回类型；
- dataclass 字段全部有明确类型；
- Models、Engine、Services 公共接口不使用无理由的 `Any`；
- 使用 Python 3.12 现代注解；
- 集合优先使用 tuple 表达不可变快照；
- 类型忽略必须局部并说明原因，不得整文件关闭检查；
- pytest 与类型检查分开运行、分开报告；
- 项目只采用一个强制类型检查器，不同时强制多个工具。

候选类型检查器是 Pyright。D-009 当前仍为 `Proposed`，本轮没有批准其工具、版本、命令、配置范围或迁移策略；因此当前不安装、不配置、不运行 Pyright，也不改用 mypy。类型检查命令：**等待项目所有者批准后确定**。

## 当前可执行测试入口

在仓库根目录运行阶段 5 定向测试：

```powershell
$env:PYTHONPATH='.'
uv run --locked pytest -v tests/test_limits.py tests/test_errors.py tests/test_diagnostics.py tests/test_logging_config.py
```

运行完整回归：

```powershell
$env:PYTHONPATH='.'
uv run --locked pytest -v
```

pytest 不隐式调用类型检查器。依赖同步、打包、性能基准和 CI 不属于本地 pytest 入口。

## 日志位置与安全清理

默认日志文件是 `%LOCALAPPDATA%\数学绘图助手\logs\application.log`，与 bootstrap 已设置的应用名称一致。若 `LOCALAPPDATA` 不可用，日志模块仅回退到系统临时目录。测试和探针必须显式注入临时目录，不访问用户真实日志目录。

日志按 `DEFAULT_LIMITS.max_log_file_bytes` 容量轮转，备份上限由 `DEFAULT_LIMITS.log_backup_count` 决定。轮转文件使用 `application.log.1` 等名称。

安全清理步骤：

1. 关闭应用；
2. 只打开上述精确的 `logs` 目录；
3. 删除 `application.log` 和同目录的 `application.log.*` 轮转备份；
4. 不删除 `%LOCALAPPDATA%`、应用上级目录或其他程序数据。

## 一次性临时探针

以下命令只写系统临时目录，并在进程结束时清理；不会向仓库加入调试脚本：

```powershell
$env:PYTHONPATH='.'
uv run --locked python -c "from pathlib import Path; from tempfile import TemporaryDirectory; from math_drawing_assistant.logging_config import LOG_FILE_NAME, configure_logging, log_event; temp=TemporaryDirectory(); directory=Path(temp.name); logger=configure_logging(directory, logger_name='math_drawing_assistant.manual_probe'); log_event(logger, 'manual_probe', authorization='Bearer probe-secret', formula='y=x^2', path=r'C:\private\lesson.txt', png_bytes=b'PNG-secret'); [handler.flush() for handler in logger.handlers]; print((directory / LOG_FILE_NAME).read_text(encoding='utf-8')); [(logger.removeHandler(handler), handler.close()) for handler in tuple(logger.handlers)]; temp.cleanup()"
```

输出应只包含脱敏占位、长度、允许的安全文件名和结构字段，不包含凭据、完整公式、完整路径或图片内容。

日志目录失败隔离探针同样只使用系统临时目录：

```powershell
$env:PYTHONPATH='.'
uv run --locked python -c "from pathlib import Path; from tempfile import TemporaryDirectory; from math_drawing_assistant.logging_config import configure_logging, log_event; temp=TemporaryDirectory(); blocker=Path(temp.name) / 'not-a-directory'; blocker.write_text('x', encoding='utf-8'); logger=configure_logging(blocker / 'logs', logger_name='math_drawing_assistant.failure_probe'); log_event(logger, 'still_running'); print('continued'); [(logger.removeHandler(handler), handler.close()) for handler in tuple(logger.handlers)]; temp.cleanup()"
```

预期输出为 `continued`，证明日志目录或 handler 失败不进入用户业务错误流。
