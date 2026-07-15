# -*- coding: utf-8 -*-
"""
gui/theme/themes.py - 内置主题定义

职责：
  - 定义 dark / light 两套内置主题的完整 tokens
  - 提供 resolve_theme_tokens(mode) 统一工厂入口
  - 未来可扩展品牌主题、高对比度主题

配色设计（v2）：
  - dark  以 #0b0f17 为底的深蓝黑序列，层级间约 4-6% 亮度差，
          accent 采用高饱和蓝紫 #5b8def -> #7aa5ff 渐变端点
  - light 以 #f5f7fb 为底的冷灰白序列，卡片纯白抬升，
          accent 采用 #3b6ef5，hover 提亮
"""

from gui.theme.tokens import ComponentTokens, ThemeTokens


def _build_dark_component_tokens() -> ComponentTokens:
    """构建暗色主题组件级令牌。"""
    return ComponentTokens(
        # 按钮
        btn_primary_bg="#5b8def",
        btn_primary_text="#ffffff",
        btn_primary_border="#5b8def",
        btn_secondary_bg="#1d2534",
        btn_secondary_text="#dde5ef",
        btn_secondary_border="#2e3a4e",
        btn_disabled_bg="#171e2b",
        btn_disabled_text="#5d6d84",
        btn_disabled_border="#252f40",
        # 输入框
        input_bg="#131a26",
        input_text="#dde5ef",
        input_border="#2e3a4e",
        input_focus_border="#5b8def",
        input_placeholder="#5d6d84",
        input_disabled_bg="#171e2b",
        # 列表
        list_bg="#131a26",
        list_item_text="#dde5ef",
        list_item_selected_bg="rgba(91, 141, 239, 0.18)",
        list_item_hover_bg="#1a2333",
        list_console_bg="#0a0e16",
        # 卡片/面板
        card_bg="#131a26",
        card_border="#2e3a4e",
        card_elevated_bg="#1a2333",
        # 横幅
        banner_info_bg="rgba(91, 141, 239, 0.16)",
        banner_info_border="#5b8def",
        banner_info_text="#7aa5ff",
        banner_success_bg="rgba(63, 197, 116, 0.14)",
        banner_success_border="#2c8f57",
        banner_success_text="#4ad584",
        banner_warning_bg="rgba(240, 180, 65, 0.14)",
        banner_warning_border="#9a6d13",
        banner_warning_text="#f0b441",
        banner_error_bg="rgba(248, 97, 92, 0.14)",
        banner_error_border="#a83c38",
        banner_error_text="#ff7b72",
        # 对话框
        dialog_bg="#131a26",
        dialog_border="#2e3a4e",
        dialog_title_text="#dde5ef",
        dialog_body_text="#9fadbf",
    )


def _build_light_component_tokens() -> ComponentTokens:
    """构建浅色主题组件级令牌。"""
    return ComponentTokens(
        # 按钮
        btn_primary_bg="#3b6ef5",
        btn_primary_text="#ffffff",
        btn_primary_border="#3b6ef5",
        btn_secondary_bg="#eef2f8",
        btn_secondary_text="#1a2434",
        btn_secondary_border="#d3dce8",
        btn_disabled_bg="#eef2f8",
        btn_disabled_text="#8896ab",
        btn_disabled_border="#dee5ef",
        # 输入框
        input_bg="#ffffff",
        input_text="#1a2434",
        input_border="#d3dce8",
        input_focus_border="#3b6ef5",
        input_placeholder="#8896ab",
        input_disabled_bg="#eef2f8",
        # 列表
        list_bg="#ffffff",
        list_item_text="#1a2434",
        list_item_selected_bg="rgba(59, 110, 245, 0.10)",
        list_item_hover_bg="#f0f4fa",
        list_console_bg="#f9fbfe",
        # 卡片/面板
        card_bg="#ffffff",
        card_border="#d3dce8",
        card_elevated_bg="#f0f4fa",
        # 横幅
        banner_info_bg="rgba(59, 110, 245, 0.10)",
        banner_info_border="#3b6ef5",
        banner_info_text="#2c56c9",
        banner_success_bg="#e5f8ec",
        banner_success_border="#31a35f",
        banner_success_text="#186a3d",
        banner_warning_bg="#fdf3d7",
        banner_warning_border="#c79422",
        banner_warning_text="#8a5a09",
        banner_error_bg="#fde8e8",
        banner_error_border="#d4626a",
        banner_error_text="#b42323",
        # 对话框
        dialog_bg="#ffffff",
        dialog_border="#d3dce8",
        dialog_title_text="#1a2434",
        dialog_body_text="#54657c",
    )


def build_dark_theme_tokens() -> ThemeTokens:
    """构建暗色主题令牌。"""
    return ThemeTokens(
        mode="dark",
        # 背景层
        bg_main="#0b0f17",
        bg_nav="#0e1420",
        bg_toolbar="#101725",
        bg_status="#0a0f19",
        bg_secondary="#131a26",
        bg_elevated="#1a2333",
        bg_btn="#1d2534",
        bg_console="#0a0e16",
        sep_color="#222d3f",
        # 文字
        text_primary="#dde5ef",
        text_secondary="#9fadbf",
        text_muted="#5d6d84",
        # 边框
        border="#2e3a4e",
        border_hover="#485871",
        # 强调色
        accent="#5b8def",
        accent_hover="#7aa5ff",
        accent_soft="rgba(91, 141, 239, 0.18)",
        selection_bg="#28527f",
        # 状态色
        success="#4ad584",
        success_bg="rgba(63, 197, 116, 0.14)",
        success_border="#2c8f57",
        warning="#f0b441",
        warning_bg="rgba(240, 180, 65, 0.14)",
        warning_border="#9a6d13",
        danger="#ff7b72",
        danger_bg="rgba(248, 97, 92, 0.14)",
        danger_border="#a83c38",
        # 导航
        nav_text="#9fadbf",
        nav_text_hover="#e8eef6",
        nav_hover_bg="rgba(255,255,255,0.07)",
        # 组件级令牌
        comp=_build_dark_component_tokens(),
    )


def build_light_theme_tokens() -> ThemeTokens:
    """构建浅色主题令牌。"""
    return ThemeTokens(
        mode="light",
        # 背景层
        bg_main="#f5f7fb",
        bg_nav="#fbfcfe",
        bg_toolbar="#ffffff",
        bg_status="#f7f9fc",
        bg_secondary="#ffffff",
        bg_elevated="#f0f4fa",
        bg_btn="#eef2f8",
        bg_console="#f9fbfe",
        sep_color="#dee5ef",
        # 文字
        text_primary="#1a2434",
        text_secondary="#54657c",
        text_muted="#8896ab",
        # 边框
        border="#d3dce8",
        border_hover="#a7b6ca",
        # 强调色
        accent="#3b6ef5",
        accent_hover="#5d89ff",
        accent_soft="rgba(59, 110, 245, 0.10)",
        selection_bg="#d6e3ff",
        # 状态色
        success="#1e7f49",
        success_bg="#e5f8ec",
        success_border="#31a35f",
        warning="#8a5a09",
        warning_bg="#fdf3d7",
        warning_border="#c79422",
        danger="#c22a2a",
        danger_bg="#fde8e8",
        danger_border="#d4626a",
        # 导航
        nav_text="#5c6d86",
        nav_text_hover="#16202f",
        nav_hover_bg="rgba(59, 110, 245, 0.08)",
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
