# -*- coding: utf-8 -*-
"""
gui/widgets/themed_dialog.py - 主题感知对话框基类

为对话框提供统一主题外观，统一标题、说明文、操作按钮区的视觉规范。

对话框类型：
  ThemedDialog       - 通用对话框基类（继承 ThemeAwareDialog）
  ThemedConfirmDialog - 确认/取消对话框
  ThemedInfoDialog    - 信息展示对话框

使用方式：
    class MyDialog(ThemedDialog):
        def refresh_theme_surfaces(self):
            # 刷新静态外观
        def refresh_theme_states(self):
            # 刷新动态状态

    dlg = MyDialog(parent=self)
    # 使用当前 tokens 初始化主题（例如由调用方从 services 中拿到 theme_manager）
    dlg.apply_theme_tokens(theme_manager.get_tokens())
    dlg.exec()
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gui.theme.contracts import ThemeAwareDialog
from gui.theme.tokens import ThemeTokens
from gui.theme.styles.dialogs import dialog_surface
from gui.theme.styles.buttons import btn_primary, btn_secondary, btn_danger


class ThemedDialog(ThemeAwareDialog):
    """
    主题感知对话框基类。

    继承此类后，重写 refresh_theme_surfaces / refresh_theme_states
    处理子类特有的主题刷新逻辑。
    基类已自动处理对话框背景/标签/通用按钮的样式。
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

    def refresh_theme_surfaces(self) -> None:
        """刷新对话框基础外观 QSS。"""
        if self._tokens is None:
            return
        self.setStyleSheet(dialog_surface(self._tokens))

    def refresh_theme_states(self) -> None:
        """子类重写以刷新按钮等动态状态。"""


class ThemedConfirmDialog(ThemedDialog):
    """
    统一确认/取消对话框。

    内置标题、内容标签、确认按钮、取消按钮，主题自动应用。
    """

    def __init__(
        self,
        title: str = "确认",
        message: str = "",
        *,
        confirm_text: str = "确认",
        cancel_text: str = "取消",
        confirm_semantic: str = "primary",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(360)
        self._confirm_semantic = confirm_semantic

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # 标题
        self._title_lbl = QLabel(title)
        self._title_lbl.setStyleSheet("font-size:15px; font-weight:bold;")
        layout.addWidget(self._title_lbl)

        # 消息
        self._msg_lbl = QLabel(message)
        self._msg_lbl.setWordWrap(True)
        layout.addWidget(self._msg_lbl)

        layout.addStretch(1)

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        self._btn_cancel = QPushButton(cancel_text)
        self._btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self._btn_cancel)

        self._btn_confirm = QPushButton(confirm_text)
        self._btn_confirm.setDefault(True)
        self._btn_confirm.clicked.connect(self.accept)
        btn_row.addWidget(self._btn_confirm)

        layout.addLayout(btn_row)

    def set_message(self, message: str) -> None:
        """动态更新消息文字。"""
        self._msg_lbl.setText(message)

    def refresh_theme_surfaces(self) -> None:
        """刷新对话框背景。"""
        if self._tokens is None:
            return
        self.setStyleSheet(dialog_surface(self._tokens))

    def refresh_theme_states(self) -> None:
        """刷新按钮语义样式。"""
        if self._tokens is None:
            return
        t = self._tokens
        # 确认按钮按语义着色
        confirm_factories = {
            "primary": btn_primary,
            "danger":  btn_danger,
        }
        factory = confirm_factories.get(self._confirm_semantic, btn_primary)
        self._btn_confirm.setStyleSheet(factory(t))
        self._btn_cancel.setStyleSheet(btn_secondary(t))


class ThemedInfoDialog(ThemedDialog):
    """
    信息展示对话框。

    仅含标题、内容区、关闭按钮，适合非操作性弹窗。
    """

    def __init__(
        self,
        title: str = "提示",
        message: str = "",
        *,
        close_text: str = "关闭",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(320)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        self._title_lbl = QLabel(title)
        self._title_lbl.setStyleSheet("font-size:15px; font-weight:bold;")
        layout.addWidget(self._title_lbl)

        self._msg_lbl = QLabel(message)
        self._msg_lbl.setWordWrap(True)
        layout.addWidget(self._msg_lbl)

        layout.addStretch(1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self._btn_close = QPushButton(close_text)
        self._btn_close.clicked.connect(self.accept)
        btn_row.addWidget(self._btn_close)
        layout.addLayout(btn_row)

    def refresh_theme_surfaces(self) -> None:
        if self._tokens is None:
            return
        self.setStyleSheet(dialog_surface(self._tokens))

    def refresh_theme_states(self) -> None:
        if self._tokens is None:
            return
        self._btn_close.setStyleSheet(btn_secondary(self._tokens))
