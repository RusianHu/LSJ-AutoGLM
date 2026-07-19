# -*- coding: utf-8 -*-
"""
gui/theme/styles/inputs.py - 统一输入框样式生成

语义：default / readonly / invalid / success / search
"""

from gui.theme.tokens import ThemeTokens


def _input_bg(t: ThemeTokens) -> str:
    return t.comp.input_bg if t.comp else t.bg_secondary


def input_default(t: ThemeTokens) -> str:
    """默认输入框：可编辑，支持聚焦高亮。"""
    return f"""
        QLineEdit, QTextEdit, QPlainTextEdit {{
            background: {_input_bg(t)};
            border: 1px solid {t.border};
            border-radius: 10px;
            color: {t.text_primary};
            padding: 6px 12px;
            selection-background-color: {t.selection_bg};
        }}
        QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover {{
            border-color: {t.border_hover};
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
            border-radius: 10px;
            padding: 6px 12px;
        }}
    """


def input_invalid(t: ThemeTokens) -> str:
    """错误态输入框：红色边框高亮。"""
    return f"""
        QLineEdit {{
            background: {_input_bg(t)};
            border: 1px solid {t.danger_border};
            border-radius: 10px;
            color: {t.text_primary};
            padding: 6px 12px;
        }}
        QLineEdit:focus {{
            border-color: {t.danger};
        }}
    """


def input_success(t: ThemeTokens) -> str:
    """成功态输入框：绿色边框高亮。"""
    return f"""
        QLineEdit {{
            background: {_input_bg(t)};
            border: 1px solid {t.success_border};
            border-radius: 10px;
            color: {t.text_primary};
            padding: 6px 12px;
        }}
        QLineEdit:focus {{
            border-color: {t.success};
        }}
    """


def input_search(t: ThemeTokens) -> str:
    """搜索框：圆角更大，内边距略调整。"""
    return f"""
        QLineEdit {{
            background: {_input_bg(t)};
            border: 1px solid {t.border};
            border-radius: 17px;
            color: {t.text_primary};
            padding: 6px 16px;
            selection-background-color: {t.selection_bg};
        }}
        QLineEdit:focus {{
            border-color: {t.accent};
        }}
    """
