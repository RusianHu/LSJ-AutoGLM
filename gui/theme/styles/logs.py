# -*- coding: utf-8 -*-
"""
gui/theme/styles/logs.py - 日志区域 QSS 生成

提供 QPlainTextEdit / QTextEdit 日志显示区域的统一样式。
语义：console（控制台日志，深色背景 + monospace 字体）
"""

from gui.theme.tokens import ThemeTokens


def log_console(t: ThemeTokens) -> str:
    """控制台日志区：深色背景，等宽字体，用于 QPlainTextEdit / QTextEdit 日志显示。"""
    return f"""
        QPlainTextEdit, QTextEdit {{
            background: {t.bg_console};
            border: 1px solid {t.border};
            border-radius: 8px;
            color: {t.text_secondary};
            font-family: 'Consolas', 'Courier New', monospace;
            font-size: 12px;
            padding: 6px;
        }}
    """
