# -*- coding: utf-8 -*-
"""
gui/theme/global_shell.py - 全局壳层样式应用器

职责：
  - 接收 ThemeTokens，构建应用级 QPalette（背景/文字/选区基色）
  - 通过 styles/shell.py 生成 QSS 并应用到 MainWindow 根组件
  - 只处理壳层通用样式，不负责页面业务样式

设计说明：
  背景基色走 QPalette 而非全局 QWidget QSS 规则——
  全局 background 规则会在祖先样式表级联中压过 QLabel
  的透明背景，导致所有带内联样式的标签渲染出底色块。
"""

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from gui.theme.tokens import ThemeTokens
from gui.theme.styles.shell import shell_global_qss


def build_palette(tokens: ThemeTokens) -> QPalette:
    """根据主题令牌构建应用级调色板。"""
    t = tokens
    input_bg = t.comp.input_bg if t.comp else t.bg_secondary

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(t.bg_main))
    palette.setColor(QPalette.WindowText, QColor(t.text_primary))
    palette.setColor(QPalette.Base, QColor(input_bg))
    palette.setColor(QPalette.AlternateBase, QColor(t.bg_elevated))
    palette.setColor(QPalette.Text, QColor(t.text_primary))
    palette.setColor(QPalette.Button, QColor(t.bg_btn))
    palette.setColor(QPalette.ButtonText, QColor(t.text_primary))
    palette.setColor(QPalette.PlaceholderText, QColor(t.text_muted))
    palette.setColor(QPalette.Highlight, QColor(t.selection_bg))
    palette.setColor(QPalette.HighlightedText, QColor(t.text_primary))
    palette.setColor(QPalette.ToolTipBase, QColor(t.bg_elevated))
    palette.setColor(QPalette.ToolTipText, QColor(t.text_primary))
    palette.setColor(QPalette.Link, QColor(t.accent))
    palette.setColor(QPalette.BrightText, QColor("#ffffff"))

    disabled_text = QColor(t.text_muted)
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        palette.setColor(QPalette.Disabled, role, disabled_text)
    return palette


class GlobalShellStyler:
    """
    全局壳层样式应用器。

    由 MainWindow 持有，在 ThemeManager.theme_changed 时被调用，
    负责将 QPalette 应用到 QApplication、将 shell QSS 应用到主窗口。
    """

    def __init__(self, target):
        """
        Args:
            target: 接受 setStyleSheet 的对象，通常为 MainWindow 实例
        """
        self._target = target

    def apply(self, tokens: ThemeTokens) -> None:
        """应用调色板与壳层全局样式。"""
        app = QApplication.instance()
        if app is not None:
            app.setPalette(build_palette(tokens))
        qss = shell_global_qss(tokens)
        self._target.setStyleSheet(qss)
