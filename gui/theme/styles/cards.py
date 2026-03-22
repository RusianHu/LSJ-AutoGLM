# -*- coding: utf-8 -*-
"""
gui/theme/styles/cards.py - 卡片/面板样式生成

语义：
  default  - 通用内容卡片
  elevated - 提升层级卡片（更深背景）
  outlined - 仅有边框无填充变体
  console  - 控制台/终端风格卡片
"""

from gui.theme.tokens import ThemeTokens


def card_default(t: ThemeTokens) -> str:
    """通用内容卡片：次级背景 + 圆角 + 边框。"""
    return f"""
        QFrame, QGroupBox {{
            background: {t.bg_secondary};
            border: 1px solid {t.border};
            border-radius: 10px;
        }}
        QGroupBox {{
            margin-top: 8px;
            padding-top: 8px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 12px;
            color: {t.text_secondary};
            font-size: 12px;
        }}
    """


def card_elevated(t: ThemeTokens) -> str:
    """提升层级卡片：稍高于基础面板的背景，用于弹出层、面板叠加。"""
    return f"""
        QFrame, QGroupBox {{
            background: {t.bg_elevated};
            border: 1px solid {t.border};
            border-radius: 10px;
        }}
        QGroupBox {{
            margin-top: 8px;
            padding-top: 8px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 12px;
            color: {t.text_secondary};
            font-size: 12px;
        }}
    """


def card_outlined(t: ThemeTokens) -> str:
    """仅边框卡片：透明背景，仅保留边框轮廓。"""
    return f"""
        QFrame, QGroupBox {{
            background: transparent;
            border: 1px solid {t.border};
            border-radius: 10px;
        }}
        QGroupBox {{
            margin-top: 8px;
            padding-top: 8px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 12px;
            color: {t.text_secondary};
            font-size: 12px;
        }}
    """


def card_console(t: ThemeTokens) -> str:
    """控制台卡片：深色背景，等宽字体，用于日志/输出区域。"""
    return f"""
        QFrame {{
            background: {t.bg_console};
            border: 1px solid {t.border};
            border-radius: 8px;
        }}
        QPlainTextEdit, QTextEdit {{
            background: {t.bg_console};
            color: {t.text_primary};
            border: 1px solid {t.border};
            border-radius: 8px;
            font-family: 'Consolas', 'Courier New', monospace;
            font-size: 12px;
            padding: 8px;
            selection-background-color: {t.selection_bg};
        }}
    """
