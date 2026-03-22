# -*- coding: utf-8 -*-
"""
gui/widgets/themed_banner.py - 主题感知横幅组件

统一成功、警告、错误、信息横幅的视觉规范。

语义类型：info / success / warning / error

使用方式：
    banner = ThemedBanner(semantic="warning")
    banner.setText("配置文件未找到")
    banner.show()
"""

from PySide6.QtWidgets import QLabel, QWidget

from gui.theme.tokens import ThemeTokens
from gui.theme.styles.banners import (
    banner_info, banner_success, banner_warning, banner_error,
)

_SEMANTIC_MAP = {
    "info":    banner_info,
    "success": banner_success,
    "warning": banner_warning,
    "error":   banner_error,
}


class ThemedBanner(QLabel):
    """
    主题感知横幅 Label。

    通过语义类型自动匹配背景色/边框/文字颜色，
    并在 apply_theme_tokens 时刷新。
    """

    def __init__(
        self,
        text: str = "",
        *,
        semantic: str = "info",
        parent: QWidget | None = None,
    ):
        super().__init__(text, parent)
        self._semantic = semantic
        self._tokens: ThemeTokens | None = None
        self.setWordWrap(True)

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def set_semantic(self, semantic: str) -> None:
        """动态切换语义类型并立即刷新样式。"""
        self._semantic = semantic
        self._refresh_style()

    def show_message(self, text: str, semantic: str | None = None) -> None:
        """设置文字、可选切换语义，并显示横幅。"""
        if semantic:
            self._semantic = semantic
        self.setText(text)
        self._refresh_style()
        self.show()

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
        factory = _SEMANTIC_MAP.get(self._semantic, banner_info)
        qss = factory(self._tokens)
        self.setStyleSheet(qss)
        self.update()
