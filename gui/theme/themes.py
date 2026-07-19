# -*- coding: utf-8 -*-
"""
gui/theme/themes.py - 内置主题定义

职责：
  - 定义 dark / light 两套内置主题的完整 tokens
  - 提供 resolve_theme_tokens(mode) 统一工厂入口
  - 未来可扩展品牌主题、高对比度主题

配色设计（v3 - 横版壳层重设计）：
  - dark  "Obsidian"：近黑中性底 #0c0d12，侧边栏更沉 #08090d 制造纵深，
          卡片 #14161f 与悬浮层 #1a1d29 之间保持 4-5% 亮度差；
          accent 采用靛紫 #7c7ff2 -> hover #979aff
  - light "Porcelain"：瓷白冷灰底 #f3f4f8，卡片纯白抬升，
          侧边栏 #fbfbfd 接近纸面；accent #5a5fe0，语义色降低饱和保证可读性
"""

from gui.theme.tokens import ComponentTokens, ThemeTokens


def _build_dark_component_tokens() -> ComponentTokens:
    """构建暗色主题组件级令牌。"""
    return ComponentTokens(
        # 按钮
        btn_primary_bg="#7c7ff2",
        btn_primary_text="#ffffff",
        btn_primary_border="#7c7ff2",
        btn_secondary_bg="#1f2330",
        btn_secondary_text="#e8eaf2",
        btn_secondary_border="#2c3245",
        btn_disabled_bg="#171a24",
        btn_disabled_text="#565d75",
        btn_disabled_border="#232838",
        # 输入框
        input_bg="#101219",
        input_text="#e8eaf2",
        input_border="#2c3245",
        input_focus_border="#7c7ff2",
        input_placeholder="#565d75",
        input_disabled_bg="#171a24",
        # 列表
        list_bg="#14161f",
        list_item_text="#e8eaf2",
        list_item_selected_bg="rgba(124, 127, 242, 0.16)",
        list_item_hover_bg="#1a1d29",
        list_console_bg="#08090e",
        # 卡片/面板
        card_bg="#14161f",
        card_border="#232838",
        card_elevated_bg="#1a1d29",
        # 横幅
        banner_info_bg="rgba(124, 127, 242, 0.14)",
        banner_info_border="#4c4f9e",
        banner_info_text="#a3a6ff",
        banner_success_bg="rgba(52, 211, 153, 0.12)",
        banner_success_border="#1d7a55",
        banner_success_text="#3ddf9f",
        banner_warning_bg="rgba(251, 191, 36, 0.12)",
        banner_warning_border="#92690f",
        banner_warning_text="#fbbf24",
        banner_error_bg="rgba(248, 113, 113, 0.12)",
        banner_error_border="#9f3d3d",
        banner_error_text="#ff8585",
        # 对话框
        dialog_bg="#14161f",
        dialog_border="#2c3245",
        dialog_title_text="#e8eaf2",
        dialog_body_text="#9aa0b5",
    )


def _build_light_component_tokens() -> ComponentTokens:
    """构建浅色主题组件级令牌。"""
    return ComponentTokens(
        # 按钮
        btn_primary_bg="#5a5fe0",
        btn_primary_text="#ffffff",
        btn_primary_border="#5a5fe0",
        btn_secondary_bg="#eef0f6",
        btn_secondary_text="#191d27",
        btn_secondary_border="#dcdfe9",
        btn_disabled_bg="#eef0f6",
        btn_disabled_text="#9198aa",
        btn_disabled_border="#e4e7ef",
        # 输入框
        input_bg="#ffffff",
        input_text="#191d27",
        input_border="#dcdfe9",
        input_focus_border="#5a5fe0",
        input_placeholder="#9198aa",
        input_disabled_bg="#eef0f6",
        # 列表
        list_bg="#ffffff",
        list_item_text="#191d27",
        list_item_selected_bg="rgba(90, 95, 224, 0.10)",
        list_item_hover_bg="#f2f3f8",
        list_console_bg="#f8f9fc",
        # 卡片/面板
        card_bg="#ffffff",
        card_border="#e0e3ec",
        card_elevated_bg="#f6f7fb",
        # 横幅
        banner_info_bg="rgba(90, 95, 224, 0.08)",
        banner_info_border="#b9bcf2",
        banner_info_text="#4146c4",
        banner_success_bg="#e3f7ec",
        banner_success_border="#9fdec0",
        banner_success_text="#116e42",
        banner_warning_bg="#fdf3d8",
        banner_warning_border="#e5c874",
        banner_warning_text="#8a5c05",
        banner_error_bg="#fde9e9",
        banner_error_border="#f0b1b1",
        banner_error_text="#b32626",
        # 对话框
        dialog_bg="#ffffff",
        dialog_border="#e0e3ec",
        dialog_title_text="#191d27",
        dialog_body_text="#5a6172",
    )


def build_dark_theme_tokens() -> ThemeTokens:
    """构建暗色主题令牌。"""
    return ThemeTokens(
        mode="dark",
        # 背景层
        bg_main="#0c0d12",
        bg_nav="#08090d",
        bg_toolbar="#12141c",
        bg_status="#0a0b10",
        bg_secondary="#14161f",
        bg_elevated="#1a1d29",
        bg_btn="#1f2330",
        bg_console="#08090e",
        sep_color="#1c2030",
        # 文字
        text_primary="#e8eaf2",
        text_secondary="#9aa0b5",
        text_muted="#565d75",
        # 边框
        border="#232838",
        border_hover="#3a415a",
        # 强调色
        accent="#7c7ff2",
        accent_hover="#979aff",
        accent_soft="rgba(124, 127, 242, 0.16)",
        selection_bg="#33386e",
        # 状态色
        success="#34d399",
        success_bg="rgba(52, 211, 153, 0.12)",
        success_border="#1d7a55",
        warning="#fbbf24",
        warning_bg="rgba(251, 191, 36, 0.12)",
        warning_border="#92690f",
        danger="#f87171",
        danger_bg="rgba(248, 113, 113, 0.12)",
        danger_border="#9f3d3d",
        # 导航
        nav_text="#8b91a8",
        nav_text_hover="#eef0f8",
        nav_hover_bg="rgba(255, 255, 255, 0.05)",
        # 组件级令牌
        comp=_build_dark_component_tokens(),
    )


def build_light_theme_tokens() -> ThemeTokens:
    """构建浅色主题令牌。"""
    return ThemeTokens(
        mode="light",
        # 背景层
        bg_main="#f3f4f8",
        bg_nav="#fbfbfd",
        bg_toolbar="#ffffff",
        bg_status="#f6f7fa",
        bg_secondary="#ffffff",
        bg_elevated="#f6f7fb",
        bg_btn="#eef0f6",
        bg_console="#f8f9fc",
        sep_color="#e4e7ef",
        # 文字
        text_primary="#191d27",
        text_secondary="#5a6172",
        text_muted="#9198aa",
        # 边框
        border="#e0e3ec",
        border_hover="#b9bfd0",
        # 强调色
        accent="#5a5fe0",
        accent_hover="#7377f0",
        accent_soft="rgba(90, 95, 224, 0.10)",
        selection_bg="#dcdefc",
        # 状态色
        success="#178a52",
        success_bg="#e3f7ec",
        success_border="#9fdec0",
        warning="#a16207",
        warning_bg="#fdf3d8",
        warning_border="#e5c874",
        danger="#d43c3c",
        danger_bg="#fde9e9",
        danger_border="#f0b1b1",
        # 导航
        nav_text="#6b7284",
        nav_text_hover="#14181f",
        nav_hover_bg="rgba(20, 24, 40, 0.05)",
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
