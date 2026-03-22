# -*- coding: utf-8 -*-
"""
gui/theme/styles/inputs.py - 统一输入框样式生成

语义：default / readonly / invalid / success / search
"""

from gui.theme.tokens import ThemeTokens


def input_default(t: ThemeTokens) -> str:
    """默认输入框：可编辑，支持聚焦高亮。"""
    return f"""
        QLineEdit, QTextEdit, QPlainTextEdit {{
            background: {t.bg_secondary};
            border: 1px solid {t.border};
            border-radius: 8px;
            color: {t.text_primary};
            padding: 6px 10px;
            selection-background-color: {t.selection_bg};
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
            border-color: {t.accent};
        }}
        QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {{
            background: {t.bg_elevated};
            color: {t.text_muted};
        }}
    """


def input_readonly(t: ThemeTokens) -> str:
    """只读输入框：弱化视觉，不可编辑。"""
    return f"""
        QLineEdit[readOnly="true"], QTextEdit[readOnly="true"] {{
            background: {t.bg_elevated};
            color: {t.text_muted};
            border: 1px solid {t.border};
            border-radius: 8px;
            padding: 6px 10px;
        }}
    """


def input_invalid(t: ThemeTokens) -> str:
    """错误态输入框：红色边框高亮。"""
    return f"""
        QLineEdit {{
            background: {t.bg_secondary};
            border: 1px solid {t.danger_border};
            border-radius: 8px;
            color: {t.text_primary};
            padding: 6px 10px;
        }}
        QLineEdit:focus {{
            border-color: {t.danger};
        }}
    """


def input_success(t: ThemeTokens) -> str:
    """成功态输入框：绿色边框高亮。"""
    return f"""
        QLineEdit {{
            background: {t.bg_secondary};
            border: 1px solid {t.success_border};
            border-radius: 8px;
            color: {t.text_primary};
            padding: 6px 10px;
        }}
        QLineEdit:focus {{
            border-color: {t.success};
        }}
    """


def input_search(t: ThemeTokens) -> str:
    """搜索框：圆角更大，内边距略调整。"""
    return f"""
        QLineEdit {{
            background: {t.bg_secondary};
            border: 1px solid {t.border};
            border-radius: 16px;
            color: {t.text_primary};
            padding: 5px 14px;
            selection-background-color: {t.selection_bg};
        }}
        QLineEdit:focus {{
            border-color: {t.accent};
        }}
    """
