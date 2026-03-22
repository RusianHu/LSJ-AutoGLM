# -*- coding: utf-8 -*-
"""
gui/widgets/themed_list.py - 主题感知列表组件

统一 console list、event list、普通 list、侧边 list 的视觉层级。

语义类型：default / console / event / side

使用方式：
    lst = ThemedList(semantic="console")
    lst.addItem("日志行")
"""

from PySide6.QtWidgets import QListWidget, QWidget

from gui.theme.tokens import ThemeTokens
from gui.theme.styles.lists import (
    list_default, list_console, list_event, list_side,
)

_SEMANTIC_MAP = {
    "default": list_default,
    "console": list_console,
    "event":   list_event,
    "side":    list_side,
}


class ThemedList(QListWidget):
    """
    主题感知列表控件。

    通过语义类型自动匹配样式，并在 apply_theme_tokens 时刷新。
    """

    def __init__(
        self,
        *,
        semantic: str = "default",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._semantic = semantic
        self._tokens: ThemeTokens | None = None

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def set_semantic(self, semantic: str) -> None:
        """动态切换语义类型并立即刷新样式。"""
        self._semantic = semantic
        self._refresh_style()

    # ------------------------------------------------------------------
    # ThemeAware 协议
    # ------------------------------------------------------------------

    def apply_theme_tokens(self, tokens: ThemeTokens) -> None:
        """接收新 tokens 并立即刷新样式。"""
        self._tokens = tokens
        self._refresh_style()

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _refresh_style(self) -> None:
        if self._tokens is None:
            return
        factory = _SEMANTIC_MAP.get(self._semantic, list_default)
        qss = factory(self._tokens)
        self.setStyleSheet(qss)
        self.update()
