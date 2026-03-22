# -*- coding: utf-8 -*-
"""
gui/theme/contracts.py - 主题感知接口协议

定义统一的主题接口约束：
  ThemeAware         协议接口（Protocol），可与任意类组合
  ThemeAwareWidget   Widget 基类，集成主题响应
  ThemeAwareDialog   Dialog 基类，集成主题响应

页面和组件应实现 apply_theme_tokens，
不再自行决定主题 QSS 拼接细节。
"""

from typing import Protocol, runtime_checkable

from PySide6.QtWidgets import QWidget, QDialog

from gui.theme.tokens import ThemeTokens


@runtime_checkable
class ThemeAware(Protocol):
    """
    可感知主题的组件协议。

    实现此协议的类可被 PageThemeAdapter / ThemeManager 自动推送主题更新。
    无需继承，鸭子类型兼容即可。
    """

    def apply_theme_tokens(self, tokens: ThemeTokens) -> None:
        """
        接收最新 ThemeTokens 并缓存。
        此方法只存储不渲染，渲染在 refresh_theme_surfaces / refresh_theme_states。
        """
        ...

    def refresh_theme_surfaces(self) -> None:
        """刷新静态外观：容器、列表、面板背景等。"""
        ...

    def refresh_theme_states(self) -> None:
        """刷新动态状态：按钮、横幅、运行态、禁用态等。"""
        ...


class ThemeAwareWidget(QWidget):
    """
    支持主题感知的 Widget 基类。

    子类应重写 refresh_theme_surfaces / refresh_theme_states，
    通常不需要重写 apply_theme_tokens。
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._tokens: ThemeTokens | None = None

    def apply_theme_tokens(self, tokens: ThemeTokens) -> None:
        """接收并缓存 tokens，然后触发完整刷新。"""
        self._tokens = tokens
        self.refresh_theme_surfaces()
        self.refresh_theme_states()

    def refresh_theme_surfaces(self) -> None:
        """刷新静态外观，子类重写。"""

    def refresh_theme_states(self) -> None:
        """刷新动态状态，子类重写。"""


class ThemeAwareDialog(QDialog):
    """
    支持主题感知的 Dialog 基类。

    子类应重写 refresh_theme_surfaces / refresh_theme_states。
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._tokens: ThemeTokens | None = None

    def apply_theme_tokens(self, tokens: ThemeTokens) -> None:
        """接收并缓存 tokens，然后触发完整刷新。"""
        self._tokens = tokens
        self.refresh_theme_surfaces()
        self.refresh_theme_states()

    def refresh_theme_surfaces(self) -> None:
        """刷新静态外观，子类重写。"""

    def refresh_theme_states(self) -> None:
        """刷新动态状态，子类重写。"""
