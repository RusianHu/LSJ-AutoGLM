# -*- coding: utf-8 -*-
"""
gui/theme/styles/dialogs.py - 统一对话框样式生成

语义：surface（通用弹窗）/ message_box（QMessageBox）
"""

from gui.theme.tokens import ThemeTokens


def dialog_surface(t: ThemeTokens) -> str:
    """通用对话框外观：背景、标签、基础按钮。"""
    input_bg = t.comp.input_bg if t.comp else t.bg_elevated
    return f"""
        QDialog {{
            background: {t.bg_secondary};
            color: {t.text_primary};
        }}
        QDialog QLabel {{
            color: {t.text_primary};
            background: transparent;
        }}
        QDialog QGroupBox {{
            background: {t.bg_secondary};
            border: 1px solid {t.border};
            border-radius: 12px;
            color: {t.text_primary};
            margin-top: 8px;
            padding-top: 8px;
        }}
        QDialog QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            color: {t.text_secondary};
            font-size: 12px;
        }}
        QDialog QLineEdit, QDialog QTextEdit, QDialog QPlainTextEdit {{
            background: {input_bg};
            border: 1px solid {t.border};
            border-radius: 8px;
            color: {t.text_primary};
            padding: 6px 10px;
        }}
        QDialog QLineEdit:focus, QDialog QTextEdit:focus {{
            border-color: {t.accent};
        }}
        QDialog QPushButton {{
            background-color: {t.bg_btn};
            border: 1px solid {t.border};
            border-radius: 10px;
            color: {t.text_primary};
            padding: 7px 18px;
            min-width: 80px;
            font-weight: 500;
        }}
        QDialog QPushButton:hover {{
            background-color: {t.bg_elevated};
            border-color: {t.border_hover};
        }}
    """


def dialog_message_box(t: ThemeTokens) -> str:
    """QMessageBox 样式：用于系统消息框主题适配。"""
    return f"""
        QMessageBox {{
            background: {t.bg_secondary};
            color: {t.text_primary};
        }}
        QMessageBox QLabel {{
            color: {t.text_primary};
            background: transparent;
            font-size: 13px;
        }}
        QPushButton {{
            background-color: {t.bg_btn};
            border: 1px solid {t.border};
            border-radius: 10px;
            color: {t.text_primary};
            padding: 7px 18px;
            min-width: 80px;
            font-weight: 500;
        }}
        QPushButton:hover {{
            background-color: {t.bg_elevated};
            border-color: {t.accent};
        }}
        QPushButton:pressed {{
            padding-top: 8px;
        }}
    """
