# -*- coding: utf-8 -*-
"""
gui/theme/styles/logs.py - 日志区域 QSS 生成

提供 QPlainTextEdit / QTextEdit 日志显示区域的统一样式。
语义：console（控制台日志，主题背景 + monospace 字体）
"""

from gui.theme.tokens import ThemeTokens


def log_console(t: ThemeTokens) -> str:
    """控制台日志区：主题感知的背景与高对比度文字。"""
    return f"""
        QPlainTextEdit, QTextEdit {{
            background: {t.bg_console};
            border: 1px solid {t.border};
            border-radius: 10px;
            color: {t.text_primary};
            font-family: 'Cascadia Mono', 'Consolas', 'Courier New', monospace;
            font-size: 12px;
            padding: 8px;
            selection-background-color: {t.selection_bg};
            selection-color: {t.text_primary};
        }}
    """
