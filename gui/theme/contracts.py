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

from typing import Any, Protocol, runtime_checkable

from PySide6.QtGui import QCloseEvent
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
    如需在对话框打开期间跟随主题变化，可调用 bind_theme_manager()。
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._tokens: ThemeTokens | None = None
        self._theme_manager: Any | None = None

    def apply_theme_tokens(self, tokens: ThemeTokens) -> None:
        """接收并缓存 tokens，然后触发完整刷新。"""
        self._tokens = tokens
        self.refresh_theme_surfaces()
        self.refresh_theme_states()

    def bind_theme_manager(self, theme_manager: Any | None) -> None:
        """
        绑定 ThemeManager，使对话框在显示期间跟随主题变化。
        绑定后会立即推送当前 tokens。
        """
        if theme_manager is self._theme_manager:
            return
        self._unbind_theme_manager()
        self._theme_manager = theme_manager
        if self._theme_manager is None:
            return
        self._theme_manager.theme_changed.connect(self.apply_theme_tokens)
        self.apply_theme_tokens(self._theme_manager.get_tokens())

    def _unbind_theme_manager(self) -> None:
        """解绑 ThemeManager 广播，避免关闭后的冗余更新。"""
        if self._theme_manager is None:
            return
        try:
            self._theme_manager.theme_changed.disconnect(self.apply_theme_tokens)
        except (RuntimeError, TypeError):
            pass
        self._theme_manager = None

    def done(self, result: int) -> None:
        """对话框结束时自动解绑主题广播。"""
        self._unbind_theme_manager()
        super().done(result)

    def closeEvent(self, event: QCloseEvent) -> None:
        """窗口关闭时自动解绑主题广播。"""
        self._unbind_theme_manager()
        super().closeEvent(event)

    def refresh_theme_surfaces(self) -> None:
        """刷新静态外观，子类重写。"""

    def refresh_theme_states(self) -> None:
        """刷新动态状态，子类重写。"""
