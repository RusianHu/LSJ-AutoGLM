# -*- coding: utf-8 -*-
"""
gui/widgets/themed_button.py - 主题感知按钮组件

自动响应 ThemeManager 广播，无需页面手动刷新。

语义类型：primary / secondary / subtle / success / warning / danger / ghost / link
尺寸：sm / md (默认) / lg / compact

使用方式：
    btn = ThemedButton("开始", semantic="primary", size="md")
    # 注册到 ThemeManager 后自动跟随主题变化
    ThemeManager.instance().register_widget(btn)
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QPushButton, QWidget

from gui.theme.tokens import ThemeTokens
from gui.theme.styles.buttons import (
    btn_primary, btn_secondary, btn_subtle,
    btn_success, btn_warning, btn_danger, btn_ghost,
)

# 语义 -> 样式函数映射
_SEMANTIC_MAP = {
    "primary":   btn_primary,
    "secondary": btn_secondary,
    "subtle":    btn_subtle,
    "success":   btn_success,
    "warning":   btn_warning,
    "danger":    btn_danger,
    "ghost":     btn_ghost,
}


class ThemedButton(QPushButton):
    """
    主题感知按钮。

    通过语义类型和尺寸参数自动从 ComponentStyleRegistry
    生成正确的 QSS，并在 apply_theme_tokens 时刷新。

    Args:
        text:     按钮文字
        semantic: 语义类型，见 _SEMANTIC_MAP
        size:     尺寸 sm/md/lg/compact
        parent:   父 Widget
    """

    def __init__(
        self,
        text: str = "",
        *,
        semantic: str = "secondary",
        size: str = "md",
        parent: QWidget | None = None,
    ):
        super().__init__(text, parent)
        self._semantic = semantic
        self._size = size
        self._tokens: ThemeTokens | None = None

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def set_semantic(self, semantic: str) -> None:
        """动态更改语义类型并立即刷新样式。"""
        self._semantic = semantic
        self._refresh_style()

    def set_size(self, size: str) -> None:
        """动态更改尺寸并立即刷新样式。"""
        self._size = size
        self._refresh_style()

    # ------------------------------------------------------------------
    # ThemeAware 协议
    # ------------------------------------------------------------------

    def apply_theme_tokens(self, tokens: ThemeTokens) -> None:
        """接收新 tokens 并立即刷新样式（实现 ThemeAware 协议）。"""
        self._tokens = tokens
        self._refresh_style()

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _refresh_style(self) -> None:
        if self._tokens is None:
            return
        factory = _SEMANTIC_MAP.get(self._semantic)
        if factory is None:
            return
        try:
            qss = factory(self._tokens, size=self._size)
        except TypeError:
            # ghost 等尚不支持 size 参数时的兜底
            qss = factory(self._tokens)
        self.setStyleSheet(qss)
        self.update()
