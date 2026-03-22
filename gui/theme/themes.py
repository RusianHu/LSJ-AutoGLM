# -*- coding: utf-8 -*-
"""
gui/theme/themes.py - 内置主题定义

职责：
  - 定义 dark / light 两套内置主题的完整 tokens
  - 提供 resolve_theme_tokens(mode) 统一工厂入口
  - 未来可扩展品牌主题、高对比度主题
"""

from gui.theme.tokens import ThemeTokens


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
