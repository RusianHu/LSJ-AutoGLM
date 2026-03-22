# -*- coding: utf-8 -*-
"""
gui/widgets/themed_input.py - 主题感知输入框组件

统一输入框样式、聚焦态、错误态、只读态、成功态、搜索态。

语义类型：default / readonly / invalid / success / search

使用方式：
    edit = ThemedInput(semantic="default")
    edit.set_semantic("invalid")   # 动态切换状态
"""

from PySide6.QtWidgets import QLineEdit, QWidget

from gui.theme.tokens import ThemeTokens
from gui.theme.styles.inputs import (
    input_default, input_readonly, input_invalid,
    input_success, input_search,
)

_SEMANTIC_MAP = {
    "default":  input_default,
    "readonly": input_readonly,
    "invalid":  input_invalid,
    "success":  input_success,
    "search":   input_search,
}


class ThemedInput(QLineEdit):
    """
    主题感知输入框。

    通过语义类型自动匹配样式，并在 apply_theme_tokens 时刷新。
    """

    def __init__(
        self,
        text: str = "",
        *,
        semantic: str = "default",
        parent: QWidget | None = None,
    ):
        super().__init__(text, parent)
        self._semantic = semantic
        self._tokens: ThemeTokens | None = None

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def set_semantic(self, semantic: str) -> None:
        """动态切换语义状态并立即刷新样式。"""
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
        factory = _SEMANTIC_MAP.get(self._semantic, input_default)
        qss = factory(self._tokens)
        self.setStyleSheet(qss)
        self.update()
