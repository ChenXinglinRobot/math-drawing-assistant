"""Centralised QSS theme loading and application.

职责：
1. 定位 resources/styles/ 下的 QSS 文件；
2. 加载并应用到 QApplication；
3. 列出可用主题名称。

不在控件内零散调用 setStyleSheet()，不实现完整品牌视觉系统。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication


def _resource_dir() -> Path:
    """Return the resources directory relative to this module."""
    return Path(__file__).resolve().parent.parent.parent / "resources"


def load_theme(app: QApplication, theme_name: str = "light") -> str:
    """Load a QSS stylesheet by name and apply it to *app*.

    Args:
        app: Target QApplication instance.
        theme_name: Stem of the QSS file inside ``resources/styles/``
                    (default ``"light"``).

    Returns:
        The raw stylesheet content (non-empty).

    Raises:
        FileNotFoundError: The QSS file does not exist.
        ValueError: The stylesheet is empty after stripping.
    """
    qss_path = _resource_dir() / "styles" / f"{theme_name}.qss"
    stylesheet = qss_path.read_text(encoding="utf-8")

    stripped = stylesheet.strip()
    if not stripped:
        raise ValueError(f"Theme file {qss_path} is empty.")

    app.setStyleSheet(stylesheet)
    return stylesheet


def available_themes() -> list[str]:
    """Return a sorted list of available QSS theme names (file stems)."""
    styles_dir = _resource_dir() / "styles"
    if not styles_dir.is_dir():
        return []
    return sorted(
        p.stem for p in styles_dir.glob("*.qss") if p.is_file()
    )
