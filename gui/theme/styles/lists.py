# -*- coding: utf-8 -*-
"""
gui/theme/styles/lists.py - 统一列表样式生成

语义：default / console / event / side
"""

from gui.theme.tokens import ThemeTokens


def list_default(t: ThemeTokens) -> str:
    """通用列表：标准背景与选中高亮。"""
    return f"""
        QListWidget {{
            background: {t.bg_secondary};
            border: 1px solid {t.border};
            border-radius: 8px;
            color: {t.text_primary};
            outline: none;
        }}
        QListWidget::item {{
            padding: 6px 10px;
            border-radius: 4px;
        }}
        QListWidget::item:selected {{
            background: {t.accent_soft};
            color: {t.accent};
        }}
        QListWidget::item:hover:!selected {{
            background: {t.bg_elevated};
        }}
    """


def list_console(t: ThemeTokens) -> str:
    """控制台日志列表：深色背景，等宽字体，无选中高亮。"""
    return f"""
        QListWidget {{
            background: {t.bg_console};
            border: 1px solid {t.border};
            border-radius: 8px;
            color: {t.text_secondary};
            font-family: 'Consolas', 'Courier New', monospace;
            font-size: 12px;
            outline: none;
        }}
        QListWidget::item {{
            padding: 2px 8px;
        }}
        QListWidget::item:selected {{
            background: {t.bg_elevated};
            color: {t.text_primary};
        }}
    """


def list_event(t: ThemeTokens) -> str:
    """事件时间线列表：带左侧色条标记。"""
    return f"""
        QListWidget {{
            background: {t.bg_secondary};
            border: 1px solid {t.border};
            border-radius: 8px;
            color: {t.text_primary};
            outline: none;
        }}
        QListWidget::item {{
            padding: 4px 8px;
            border-left: 3px solid transparent;
        }}
        QListWidget::item:selected {{
            background: {t.accent_soft};
            border-left-color: {t.accent};
        }}
    """


def list_side(t: ThemeTokens) -> str:
    """侧边面板列表：无边框，轻量背景。"""
    return f"""
        QListWidget {{
            background: transparent;
            border: none;
            color: {t.text_primary};
            outline: none;
        }}
        QListWidget::item {{
            padding: 6px 12px;
            border-radius: 6px;
        }}
        QListWidget::item:selected {{
            background: {t.accent_soft};
            color: {t.accent};
        }}
        QListWidget::item:hover:!selected {{
            background: {t.bg_elevated};
        }}
    """
