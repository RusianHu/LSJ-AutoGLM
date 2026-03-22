# -*- coding: utf-8 -*-
"""
gui/theme/component_registry.py - 组件样式注册中心

统一注册组件语义样式生成器，
页面不再自己拼 QSS，通过注册表按语义名称获取样式字符串。

语义命名约定：
  button.primary   button.secondary  button.subtle
  button.success   button.warning    button.danger
  button.ghost
  input.default    input.readonly    input.search
  list.default     list.console      list.event
  banner.info      banner.success    banner.warning   banner.error
  dialog.surface   dialog.message_box

尺寸后缀（按钮）：
  .sm  .md（默认）  .lg  .compact
"""

from typing import Callable

from gui.theme.tokens import ThemeTokens
from gui.theme.styles import (
    btn_primary, btn_secondary, btn_subtle,
    btn_success, btn_warning, btn_danger, btn_ghost,
    input_default, input_readonly, input_search,
    list_default, list_console,
    banner_info, banner_success, banner_warning, banner_error,
    dialog_surface, dialog_message_box,
)
from gui.theme.styles.lists import list_event

# 类型别名
StyleFactory = Callable[[ThemeTokens], str]


class ComponentStyleRegistry:
    """
    组件样式注册中心。

    每次调用 get() 都会用当前 tokens 生成最新样式，
    不缓存（tokens 是不可变的，每次主题切换都是新 tokens）。

    用法：
        registry = ComponentStyleRegistry()
        qss = registry.get("button.primary", tokens)
        btn.setStyleSheet(qss)

        # 带尺寸
        qss = registry.get("button.primary.compact", tokens)
    """

    def __init__(self):
        self._factories: dict[str, StyleFactory] = {}
        self._register_defaults()

    def register(self, name: str, factory: StyleFactory) -> None:
        """
        注册自定义样式生成器。

        Args:
            name:    语义名称，如 "button.brand"
            factory: 接受 ThemeTokens，返回 QSS 字符串的可调用对象
        """
        self._factories[name] = factory

    def get(self, name: str, tokens: ThemeTokens) -> str:
        """
        按语义名称获取样式 QSS。

        Args:
            name:   如 "button.primary" 或 "button.primary.compact"
            tokens: 当前 ThemeTokens

        Returns:
            QSS 字符串，未注册时返回空字符串。
        """
        factory = self._factories.get(name)
        if factory is None:
            return ""
        return factory(tokens)

    def has(self, name: str) -> bool:
        """是否注册了指定语义名称。"""
        return name in self._factories

    def names(self) -> list[str]:
        """所有已注册的语义名称列表。"""
        return list(self._factories.keys())

    # ---------- 内部：注册内置样式 ----------

    def _register_defaults(self):
        """注册所有内置组件样式。"""
        # 按钮 - md（默认尺寸）
        self._factories["button.primary"]   = btn_primary
        self._factories["button.secondary"] = btn_secondary
        self._factories["button.subtle"]    = btn_subtle
        self._factories["button.success"]   = btn_success
        self._factories["button.warning"]   = btn_warning
        self._factories["button.danger"]    = btn_danger
        self._factories["button.ghost"]     = btn_ghost

        # 按钮 - sm
        self._factories["button.primary.sm"]   = lambda t: btn_primary(t, size="sm")
        self._factories["button.secondary.sm"] = lambda t: btn_secondary(t, size="sm")
        self._factories["button.subtle.sm"]    = lambda t: btn_subtle(t, size="sm")
        self._factories["button.success.sm"]   = lambda t: btn_success(t, size="sm")
        self._factories["button.danger.sm"]    = lambda t: btn_danger(t, size="sm")

        # 按钮 - compact
        self._factories["button.primary.compact"]   = lambda t: btn_primary(t, size="compact")
        self._factories["button.secondary.compact"] = lambda t: btn_secondary(t, size="compact")
        self._factories["button.subtle.compact"]    = lambda t: btn_subtle(t, size="compact")
        self._factories["button.success.compact"]   = lambda t: btn_success(t, size="compact")
        self._factories["button.danger.compact"]    = lambda t: btn_danger(t, size="compact")
        self._factories["button.warning.compact"]   = lambda t: btn_warning(t, size="compact")

        # 按钮 - lg
        self._factories["button.primary.lg"]   = lambda t: btn_primary(t, size="lg")
        self._factories["button.danger.lg"]    = lambda t: btn_danger(t, size="lg")

        # 输入框
        self._factories["input.default"]  = input_default
        self._factories["input.readonly"] = input_readonly
        self._factories["input.search"]   = input_search

        # 列表
        self._factories["list.default"] = list_default
        self._factories["list.console"] = list_console
        self._factories["list.event"]   = list_event

        # 横幅
        self._factories["banner.info"]    = banner_info
        self._factories["banner.success"] = banner_success
        self._factories["banner.warning"] = banner_warning
        self._factories["banner.error"]   = banner_error

        # 对话框
        self._factories["dialog.surface"]     = dialog_surface
        self._factories["dialog.message_box"] = dialog_message_box


# 模块级默认注册表，供全局直接导入使用
_default_registry: ComponentStyleRegistry | None = None


def get_registry() -> ComponentStyleRegistry:
    """获取全局默认注册表（懒初始化单例）。"""
    global _default_registry
    if _default_registry is None:
        _default_registry = ComponentStyleRegistry()
    return _default_registry
