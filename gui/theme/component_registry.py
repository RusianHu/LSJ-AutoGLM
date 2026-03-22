# -*- coding: utf-8 -*-
"""
gui/theme/component_registry.py - 组件样式注册中心

统一注册组件语义样式生成器，
页面不再自己拼 QSS，通过注册表按语义名称获取样式字符串。

语义命名约定：
  button.primary   button.secondary  button.subtle
  button.success   button.warning    button.danger
  button.ghost
  input.default    input.readonly    input.search    input.invalid   input.success
  list.default     list.console      list.event      list.side
  banner.info      banner.success    banner.warning  banner.error
  dialog.surface   dialog.message_box
  card.default     card.elevated     card.outlined   card.console
  log.console

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
from gui.theme.styles.inputs import input_invalid, input_success as input_success_style
from gui.theme.styles.lists import list_event, list_side
from gui.theme.styles.logs import log_console
from gui.theme.styles.cards import (
    card_default, card_elevated, card_outlined, card_console,
)

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
            QSS 字符串，未找到时返回空字符串并打印警告。
        """
        factory = self._factories.get(name)
        if factory is None:
            import logging
            logging.getLogger(__name__).warning(
                "ComponentStyleRegistry: 未注册的样式 '%s'", name
            )
            return ""
        return factory(tokens)

    def has(self, name: str) -> bool:
        """检查指定语义名称是否已注册。"""
        return name in self._factories

    def registered_names(self) -> list[str]:
        """返回所有已注册的语义名称列表。"""
        return sorted(self._factories.keys())

    def _register_defaults(self) -> None:
        """注册所有内置组件样式。"""

        # ---------- 按钮 - md（默认） ----------
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
        self._factories["button.danger.sm"]    = lambda t: btn_danger(t, size="sm")

        # 按钮 - compact
        self._factories["button.primary.compact"]   = lambda t: btn_primary(t, size="compact")
        self._factories["button.secondary.compact"] = lambda t: btn_secondary(t, size="compact")
        self._factories["button.subtle.compact"]    = lambda t: btn_subtle(t, size="compact")
        self._factories["button.danger.compact"]    = lambda t: btn_danger(t, size="compact")
        self._factories["button.warning.compact"]   = lambda t: btn_warning(t, size="compact")
        self._factories["button.success.compact"]   = lambda t: btn_success(t, size="compact")

        # 按钮 - lg
        self._factories["button.primary.lg"]   = lambda t: btn_primary(t, size="lg")
        self._factories["button.danger.lg"]    = lambda t: btn_danger(t, size="lg")

        # ---------- 输入框 ----------
        self._factories["input.default"]  = input_default
        self._factories["input.readonly"] = input_readonly
        self._factories["input.search"]   = input_search
        self._factories["input.invalid"]  = input_invalid
        self._factories["input.success"]  = input_success_style

        # ---------- 列表 ----------
        self._factories["list.default"] = list_default
        self._factories["list.console"] = list_console
        self._factories["list.event"]   = list_event
        self._factories["list.side"]    = list_side

        # ---------- 横幅 ----------
        self._factories["banner.info"]    = banner_info
        self._factories["banner.success"] = banner_success
        self._factories["banner.warning"] = banner_warning
        self._factories["banner.error"]   = banner_error

        # ---------- 对话框 ----------
        self._factories["dialog.surface"]     = dialog_surface
        self._factories["dialog.message_box"] = dialog_message_box

        # ---------- 日志区 ----------
        self._factories["log.console"] = log_console

        # ---------- 卡片/面板 ----------
        self._factories["card.default"]  = card_default
        self._factories["card.elevated"] = card_elevated
        self._factories["card.outlined"] = card_outlined
        self._factories["card.console"]  = card_console


# 模块级默认注册表，供全局直接导入使用
_default_registry: ComponentStyleRegistry | None = None


def get_registry() -> ComponentStyleRegistry:
    """获取全局默认注册表（懒初始化单例）。"""
    global _default_registry
    if _default_registry is None:
        _default_registry = ComponentStyleRegistry()
    return _default_registry