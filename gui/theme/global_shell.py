# -*- coding: utf-8 -*-
"""
gui/theme/global_shell.py - 全局壳层样式应用器

职责：
  - 接收 ThemeTokens，通过 styles/shell.py 生成 QSS
  - 应用到 QApplication 或 MainWindow 根组件
  - 只处理壳层通用样式，不负责页面业务样式
"""

from gui.theme.tokens import ThemeTokens
from gui.theme.styles.shell import shell_global_qss


class GlobalShellStyler:
    """
    全局壳层样式应用器。

    由 MainWindow 持有，在 ThemeManager.theme_changed 时被调用，
    负责将 shell QSS 应用到主窗口。
    """

    def __init__(self, target):
        """
        Args:
            target: 接受 setStyleSheet 的对象，通常为 MainWindow 实例
        """
        self._target = target

    def apply(self, tokens: ThemeTokens) -> None:
        """应用壳层全局样式。"""
        qss = shell_global_qss(tokens)
        self._target.setStyleSheet(qss)
