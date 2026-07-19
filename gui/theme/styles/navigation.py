# -*- coding: utf-8 -*-
"""
gui/theme/styles/navigation.py - 导航区样式生成（横版侧边栏）
"""

from gui.theme.tokens import ThemeTokens


def nav_panel_qss(t: ThemeTokens) -> str:
    """侧边导航面板背景。"""
    return f"background: {t.bg_nav}; border-right: 1px solid {t.sep_color};"


def nav_button_qss(t: ThemeTokens) -> str:
    """导航按钮：未选中 / hover / checked 状态。"""
    return f"""
        QPushButton {{
            background: transparent;
            border: none;
            border-radius: 10px;
            color: {t.nav_text};
            text-align: left;
            padding: 9px 14px;
            font-size: 13px;
        }}
        QPushButton:hover {{
            background: {t.nav_hover_bg};
            color: {t.nav_text_hover};
        }}
        QPushButton:checked {{
            background: {t.accent_soft};
            color: {t.accent};
            font-weight: 600;
        }}
        QPushButton:checked:hover {{
            background: {t.accent_soft};
            color: {t.accent};
        }}
    """
