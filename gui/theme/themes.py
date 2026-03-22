# -*- coding: utf-8 -*-
"""
gui/theme/themes.py - 内置主题定义

职责：
  - 定义 dark / light 两套内置主题的完整 tokens
  - 提供 resolve_theme_tokens(mode) 统一工厂入口
  - 未来可扩展品牌主题、高对比度主题
"""

from gui.theme.tokens import ComponentTokens, ThemeTokens


def _build_dark_component_tokens() -> ComponentTokens:
    """构建暗色主题组件级令牌。"""
    return ComponentTokens(
        # 按钮
        btn_primary_bg="#4f8cff",
        btn_primary_text="#ffffff",
        btn_primary_border="#4f8cff",
        btn_secondary_bg="#21262d",
        btn_secondary_text="#d7dee7",
        btn_secondary_border="#303b4a",
        btn_disabled_bg="#1b2432",
        btn_disabled_text="#66778d",
        btn_disabled_border="#303b4a",
        # 输入框
        input_bg="#161b22",
        input_text="#d7dee7",
        input_border="#303b4a",
        input_focus_border="#4f8cff",
        input_placeholder="#66778d",
        input_disabled_bg="#1b2432",
        # 列表
        list_bg="#161b22",
        list_item_text="#d7dee7",
        list_item_selected_bg="rgba(79, 140, 255, 0.16)",
        list_item_hover_bg="#1b2432",
        list_console_bg="#0a0f18",
        # 卡片/面板
        card_bg="#161b22",
        card_border="#303b4a",
        card_elevated_bg="#1b2432",
        # 横幅
        banner_info_bg="rgba(79, 140, 255, 0.16)",
        banner_info_border="#4f8cff",
        banner_info_text="#4f8cff",
        banner_success_bg="#0f2d1a",
        banner_success_border="#1f6d3c",
        banner_success_text="#3fb950",
        banner_warning_bg="#3d2800",
        banner_warning_border="#6e4800",
        banner_warning_text="#e3b341",
        banner_error_bg="#3d1a1a",
        banner_error_border="#8f2d2b",
        banner_error_text="#f85149",
        # 对话框
        dialog_bg="#161b22",
        dialog_border="#303b4a",
        dialog_title_text="#d7dee7",
        dialog_body_text="#9ba7b4",
    )


def _build_light_component_tokens() -> ComponentTokens:
    """构建浅色主题组件级令牌。"""
    return ComponentTokens(
        # 按钮
        btn_primary_bg="#2563eb",
        btn_primary_text="#ffffff",
        btn_primary_border="#2563eb",
        btn_secondary_bg="#eef2f7",
        btn_secondary_text="#18212f",
        btn_secondary_border="#d5deea",
        btn_disabled_bg="#eef3f9",
        btn_disabled_text="#7b8aa0",
        btn_disabled_border="#d5deea",
        # 输入框
        input_bg="#ffffff",
        input_text="#18212f",
        input_border="#d5deea",
        input_focus_border="#2563eb",
        input_placeholder="#7b8aa0",
        input_disabled_bg="#eef3f9",
        # 列表
        list_bg="#ffffff",
        list_item_text="#18212f",
        list_item_selected_bg="rgba(37, 99, 235, 0.12)",
        list_item_hover_bg="#eef3f9",
        list_console_bg="#f8fbff",
        # 卡片/面板
        card_bg="#ffffff",
        card_border="#d5deea",
        card_elevated_bg="#eef3f9",
        # 横幅
        banner_info_bg="rgba(37, 99, 235, 0.12)",
        banner_info_border="#2563eb",
        banner_info_text="#2563eb",
        banner_success_bg="#dcfce7",
        banner_success_border="#16a34a",
        banner_success_text="#166534",
        banner_warning_bg="#fef3c0",
        banner_warning_border="#c28b00",
        banner_warning_text="#92400e",
        banner_error_bg="#fee2e5",
        banner_error_border="#c9525a",
        banner_error_text="#b91c1c",
        # 对话框
        dialog_bg="#ffffff",
        dialog_border="#d5deea",
        dialog_title_text="#18212f",
        dialog_body_text="#526273",
    )


def build_dark_theme_tokens() -> ThemeTokens:
    """构建暗色主题令牌。"""
    return ThemeTokens(
        mode="dark",
        # 背景层
        bg_main="#0d1117",
        bg_nav="#101826",
        bg_toolbar="#111827",
        bg_status="#0b1220",
        bg_secondary="#161b22",
        bg_elevated="#1b2432",
        bg_btn="#21262d",
        bg_console="#0a0f18",
        sep_color="#243042",
        # 文字
        text_primary="#d7dee7",
        text_secondary="#9ba7b4",
        text_muted="#66778d",
        # 边框
        border="#303b4a",
        border_hover="#4b5b70",
        # 强调色
        accent="#4f8cff",
        accent_hover="#6aa4ff",
        accent_soft="rgba(79, 140, 255, 0.16)",
        selection_bg="#264f78",
        # 状态色
        success="#3fb950",
        success_bg="#0f2d1a",
        success_border="#1f6d3c",
        warning="#e3b341",
        warning_bg="#3d2800",
        warning_border="#6e4800",
        danger="#f85149",
        danger_bg="#3d1a1a",
        danger_border="#8f2d2b",
        # 导航
        nav_text="#a9b5c7",
        nav_text_hover="#e2e8f0",
        nav_hover_bg="rgba(255,255,255,0.06)",
        # 组件级令牌
        comp=_build_dark_component_tokens(),
    )


def build_light_theme_tokens() -> ThemeTokens:
    """构建浅色主题令牌。"""
    return ThemeTokens(
        mode="light",
        # 背景层
        bg_main="#f4f7fb",
        bg_nav="#edf3fb",
        bg_toolbar="#ffffff",
        bg_status="#f7f9fc",
        bg_secondary="#ffffff",
        bg_elevated="#eef3f9",
        bg_btn="#eef2f7",
        bg_console="#f8fbff",
        sep_color="#d7dee8",
        # 文字
        text_primary="#18212f",
        text_secondary="#526273",
        text_muted="#7b8aa0",
        # 边框
        border="#d5deea",
        border_hover="#a9b6c7",
        # 强调色
        accent="#2563eb",
        accent_hover="#3b82f6",
        accent_soft="rgba(37, 99, 235, 0.12)",
        selection_bg="#dbeafe",
        # 状态色
        success="#166534",
        success_bg="#dcfce7",
        success_border="#16a34a",
        warning="#92400e",
        warning_bg="#fef3c0",
        warning_border="#c28b00",
        danger="#b91c1c",
        danger_bg="#fee2e5",
        danger_border="#c9525a",
        # 导航
        nav_text="#60708a",
        nav_text_hover="#1e2a3a",
        nav_hover_bg="rgba(37, 99, 235, 0.08)",
        # 组件级令牌
        comp=_build_light_component_tokens(),
    )


# 预构建缓存，避免重复创建
_DARK_TOKENS: ThemeTokens | None = None
_LIGHT_TOKENS: ThemeTokens | None = None


def resolve_theme_tokens(mode: str) -> ThemeTokens:
    """
    根据解析后的模式返回对应主题令牌。

    Args:
        mode: "dark" 或 "light"（不接受 "system"，应由 ThemeManager 提前解析）

    Returns:
        对应的 ThemeTokens 实例（复用缓存）
    """
    global _DARK_TOKENS, _LIGHT_TOKENS
    if mode == "dark":
        if _DARK_TOKENS is None:
            _DARK_TOKENS = build_dark_theme_tokens()
        return _DARK_TOKENS
    else:
        if _LIGHT_TOKENS is None:
            _LIGHT_TOKENS = build_light_theme_tokens()
        return _LIGHT_TOKENS
