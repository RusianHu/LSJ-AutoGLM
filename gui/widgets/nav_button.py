# -*- coding: utf-8 -*-
"""侧边栏导航按钮控件（横版壳层，纵向排布：图标 + 文字 + 选中指示条）"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy

from gui.theme.icons import fa_family, icon_char


class NavButton(QPushButton):
    """侧边栏导航按钮。

    结构：[指示条][图标][文字]，整体为可勾选按钮。
    颜色状态（默认/悬停/选中）由 Python 驱动子标签样式，
    避免依赖 QSS 祖先伪态选择器的兼容性。
    """

    def __init__(self, icon_name: str, label: str, parent=None):
        super().__init__(parent)
        self._icon_name = icon_name
        self._label = label
        self._tokens = None
        self._hovered = False

        self.setObjectName("NavButton")
        self.setCheckable(True)
        self.setFixedHeight(40)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(label)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 12, 0)
        row.setSpacing(0)

        # 选中指示条（占位固定宽度，未选中时透明）
        self._indicator = QFrame(self)
        self._indicator.setFixedSize(3, 18)
        self._indicator.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        row.addWidget(self._indicator, 0, Qt.AlignVCenter)

        self._icon_lbl = QLabel(icon_char(icon_name), self)
        self._icon_lbl.setFixedWidth(34)
        self._icon_lbl.setAlignment(Qt.AlignCenter)
        self._icon_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        row.addWidget(self._icon_lbl, 0, Qt.AlignVCenter)

        self._text_lbl = QLabel(label, self)
        self._text_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        row.addWidget(self._text_lbl, 1, Qt.AlignVCenter)

        self.toggled.connect(lambda _checked: self._refresh_children())
        self._apply_default_style()

    # ---------- 公开接口 ----------

    def set_label(self, label: str) -> None:
        """更新显示文案（语言切换时由 MainWindow 调用）。"""
        self._label = label
        self._text_lbl.setText(label)
        self.setToolTip(label)

    def apply_theme_tokens(self, tokens) -> None:
        """接受 ThemeTokens 对象应用主题（首选接口，由 ThemeManager 驱动）。"""
        self._tokens = tokens
        self.setProperty("themeMode", tokens.mode)
        self.setStyleSheet(f"""
            NavButton {{
                background: transparent;
                border: none;
                border-radius: 10px;
                text-align: left;
            }}
            NavButton:hover {{
                background: {tokens.nav_hover_bg};
            }}
            NavButton:checked {{
                background: {tokens.accent_soft};
            }}
        """)
        self._refresh_children()

    def apply_theme(self, theme_vars: dict, theme_mode: str = "dark"):
        """[兼容层] 接受旧式 dict 格式主题变量。"""
        from gui.theme.themes import resolve_theme_tokens

        self.apply_theme_tokens(resolve_theme_tokens(theme_mode))

    # ---------- 内部 ----------

    def _refresh_children(self) -> None:
        """根据当前状态刷新图标/文字/指示条颜色。"""
        t = self._tokens
        if t is None:
            return
        checked = self.isChecked()
        if checked:
            color = t.accent
            weight = 600
        elif self._hovered:
            color = t.nav_text_hover
            weight = 500
        else:
            color = t.nav_text
            weight = 500
        # 图标字体族必须写进自身样式表：全局 QSS 的 font-family
        # 会覆盖 setFont() 程序化设置，自身样式表优先级更高。
        family = fa_family()
        icon_font_css = f"font-family:'{family}'; font-size:14px;" if family else "font-size:14px;"
        self._icon_lbl.setStyleSheet(
            f"color:{color}; background:transparent; {icon_font_css}"
        )
        self._text_lbl.setStyleSheet(
            f"color:{color}; background:transparent; font-size:13px; font-weight:{weight};"
        )
        self._indicator.setStyleSheet(
            f"background:{t.accent if checked else 'transparent'}; border-radius:1px;"
        )

    def enterEvent(self, event):
        self._hovered = True
        self._refresh_children()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._refresh_children()
        super().leaveEvent(event)

    def _apply_default_style(self):
        """启动时使用暗色默认值，等待 ThemeManager 推送真实 tokens。"""
        from gui.theme.themes import resolve_theme_tokens

        self.apply_theme_tokens(resolve_theme_tokens("dark"))
