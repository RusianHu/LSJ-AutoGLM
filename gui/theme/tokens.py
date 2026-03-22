# -*- coding: utf-8 -*-
"""
gui/theme/tokens.py - 主题令牌数据结构

三层语义：
  BasePalette      原始色板（不对外暴露原始键）
  SemanticColors   语义颜色（成功/危险/警告/强调）
  ComponentTokens  组件级令牌（按钮、输入、列表等）
  ThemeTokens      最终聚合对象，页面和组件唯一消费入口
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
class ComponentTokens:
    """
    组件级令牌。

    提供从语义色到具体组件属性的映射，
    避免页面直接消费原始颜色键名。

    页面应通过 ThemeTokens.comp 访问此层级。
    """
    # 按钮组件
    btn_primary_bg: str
    btn_primary_text: str
    btn_primary_border: str
    btn_secondary_bg: str
    btn_secondary_text: str
    btn_secondary_border: str
    btn_disabled_bg: str
    btn_disabled_text: str
    btn_disabled_border: str

    # 输入框组件
    input_bg: str
    input_text: str
    input_border: str
    input_focus_border: str
    input_placeholder: str
    input_disabled_bg: str

    # 列表组件
    list_bg: str
    list_item_text: str
    list_item_selected_bg: str
    list_item_hover_bg: str
    list_console_bg: str

    # 卡片/面板
    card_bg: str
    card_border: str
    card_elevated_bg: str

    # 横幅
    banner_info_bg: str
    banner_info_border: str
    banner_info_text: str
    banner_success_bg: str
    banner_success_border: str
    banner_success_text: str
    banner_warning_bg: str
    banner_warning_border: str
    banner_warning_text: str
    banner_error_bg: str
    banner_error_border: str
    banner_error_text: str

    # 对话框
    dialog_bg: str
    dialog_border: str
    dialog_title_text: str
    dialog_body_text: str


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
        comp  = tokens.comp            # 组件级令牌（推荐）
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

    # 组件级令牌（可选，向后兼容设为 None 时降级到基础层）
    comp: ComponentTokens | None = None

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
