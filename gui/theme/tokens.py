# -*- coding: utf-8 -*-
"""
gui/theme/tokens.py - 主题令牌数据结构

三层语义：
  BasePalette     原始色板（不对外暴露原始键）
  SemanticColors  语义颜色（成功/危险/警告/强调）
  ComponentTokens 组件级令牌（按钮、输入、列表等）
  ThemeTokens     最终聚合对象，页面和组件唯一消费入口
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class BasePalette:
    """原始色板，仅在 themes.py 中构造，外部不直接使用。"""
    bg_main: str
    bg_nav: str
    bg_toolbar: str
    bg_status: str
    bg_secondary: str
    bg_elevated: str
    bg_btn: str
    bg_console: str
    sep_color: str


@dataclass(frozen=True)
class SemanticColors:
    """语义颜色层。"""
    text_primary: str
    text_secondary: str
    text_muted: str
    border: str
    border_hover: str
    accent: str
    accent_hover: str
    accent_soft: str
    selection_bg: str
    success: str
    success_bg: str
    success_border: str
    warning: str
    warning_bg: str
    warning_border: str
    danger: str
    danger_bg: str
    danger_border: str


@dataclass(frozen=True)
class NavigationTokens:
    """导航区专用令牌。"""
    nav_text: str
    nav_text_hover: str
    nav_hover_bg: str
    nav_bg: str


@dataclass(frozen=True)
class ThemeTokens:
    """
    主题令牌聚合对象。

    页面和组件唯一消费入口，不允许直接构造，
    只能通过 gui.theme.themes 中的工厂函数获取。

    使用方式：
        from gui.theme import ThemeManager
        tokens = ThemeManager.instance().get_tokens()
        color = tokens.accent          # 直接属性访问
        bg    = tokens.bg_secondary    # 背景色
    """
    # 解析后的模式
    mode: str  # "dark" | "light"

    # 背景层
    bg_main: str
    bg_nav: str
    bg_toolbar: str
    bg_status: str
    bg_secondary: str
    bg_elevated: str
    bg_btn: str
    bg_console: str
    sep_color: str

    # 文字
    text_primary: str
    text_secondary: str
    text_muted: str

    # 边框
    border: str
    border_hover: str

    # 强调色
    accent: str
    accent_hover: str
    accent_soft: str
    selection_bg: str

    # 语义状态色
    success: str
    success_bg: str
    success_border: str
    warning: str
    warning_bg: str
    warning_border: str
    danger: str
    danger_bg: str
    danger_border: str

    # 导航
    nav_text: str
    nav_text_hover: str
    nav_hover_bg: str

    def is_dark(self) -> bool:
        return self.mode == "dark"

    def is_light(self) -> bool:
        return self.mode == "light"

    def to_legacy_dict(self) -> dict:
        """
        向后兼容：将 tokens 转换为旧格式 dict。
        用于渐进迁移期间，旧代码仍消费 dict 的场景。
        """
        return {
            "bg_main":       self.bg_main,
            "bg_nav":        self.bg_nav,
            "bg_toolbar":    self.bg_toolbar,
            "bg_status":     self.bg_status,
            "bg_secondary":  self.bg_secondary,
            "bg_elevated":   self.bg_elevated,
            "bg_btn":        self.bg_btn,
            "bg_console":    self.bg_console,
            "sep_color":     self.sep_color,
            "text_primary":  self.text_primary,
            "text_secondary": self.text_secondary,
            "text_muted":    self.text_muted,
            "border":        self.border,
            "border_hover":  self.border_hover,
            "accent":        self.accent,
            "accent_hover":  self.accent_hover,
            "accent_soft":   self.accent_soft,
            "selection_bg":  self.selection_bg,
            "success":       self.success,
            "success_bg":    self.success_bg,
            "success_border": self.success_border,
            "warning":       self.warning,
            "warning_bg":    self.warning_bg,
            "warning_border": self.warning_border,
            "danger":        self.danger,
            "danger_bg":     self.danger_bg,
            "danger_border": self.danger_border,
            "nav_text":      self.nav_text,
            "nav_text_hover": self.nav_text_hover,
            "nav_hover_bg":  self.nav_hover_bg,
        }
