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
            border-radius: 12px;
            color: {t.text_primary};
            outline: none;
            padding: 4px;
        }}
        QListWidget::item {{
            padding: 8px 10px;
            border-radius: 8px;
            margin: 1px 2px;
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
    """控制台日志列表：深色背景，等宽字体，弱选中高亮。"""
    return f"""
        QListWidget {{
            background: {t.bg_console};
            border: 1px solid {t.border};
            border-radius: 12px;
            color: {t.text_secondary};
            font-family: 'Cascadia Mono', 'Consolas', 'Courier New', monospace;
            font-size: 12px;
            outline: none;
            padding: 4px;
        }}
        QListWidget::item {{
            padding: 4px 8px;
            border-radius: 6px;
            margin: 1px 2px;
        }}
        QListWidget::item:selected {{
            background: {t.accent_soft};
            color: {t.text_primary};
        }}
        QListWidget::item:hover:!selected {{
            background: {t.bg_elevated};
        }}
    """


def list_event(t: ThemeTokens) -> str:
    """事件时间线列表：带左侧色条标记。"""
    return f"""
        QListWidget {{
            background: {t.bg_secondary};
            border: 1px solid {t.border};
            border-radius: 12px;
            color: {t.text_primary};
            outline: none;
            padding: 4px;
        }}
        QListWidget::item {{
            padding: 6px 8px;
            border-left: 3px solid transparent;
            border-radius: 6px;
            margin: 1px 2px;
        }}
        QListWidget::item:selected {{
            background: {t.accent_soft};
            border-left-color: {t.accent};
        }}
        QListWidget::item:hover:!selected {{
            background: {t.bg_elevated};
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
            padding: 7px 12px;
            border-radius: 8px;
        }}
        QListWidget::item:selected {{
            background: {t.accent_soft};
            color: {t.accent};
        }}
        QListWidget::item:hover:!selected {{
            background: {t.bg_elevated};
        }}
    """
