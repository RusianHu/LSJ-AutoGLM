# -*- coding: utf-8 -*-
"""左侧导航按钮控件"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QSizePolicy


class NavButton(QPushButton):
    """左侧导航栏按钮"""

    def __init__(self, icon_text: str, label: str, parent=None):
        super().__init__(parent)
        self._icon_text = icon_text
        self._label = label
        self.setObjectName("NavButton")
        self.setText(f"{icon_text}\n{label}")
        self.setCheckable(True)
        self.setFixedHeight(64)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self._apply_style()

    def apply_theme(self, theme_vars: dict, theme_mode: str = "dark"):
        self.setProperty("themeMode", theme_mode)
        self.setStyleSheet(f"""
            NavButton {{
                background: transparent;
                border: none;
                border-radius: 12px;
                color: {theme_vars['nav_text']};
                font-size: 11px;
                font-weight: 600;
                padding: 6px 10px;
                text-align: center;
            }}
            NavButton:hover {{
                background: {theme_vars['nav_hover_bg']};
                color: {theme_vars['nav_text_hover']};
            }}
            NavButton:checked {{
                background: {theme_vars['accent_soft']};
                color: {theme_vars['accent']};
                border-left: 3px solid {theme_vars['accent']};
            }}
        """)

    def _apply_style(self):
        self.apply_theme(
            {
                "nav_text": "#a9b5c7",
                "nav_text_hover": "#e2e8f0",
                "nav_hover_bg": "rgba(255,255,255,0.06)",
                "accent_soft": "rgba(79, 140, 255, 0.16)",
                "accent": "#4f8cff",
            },
            "dark",
        )
