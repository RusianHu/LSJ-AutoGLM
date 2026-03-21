# -*- coding: utf-8 -*-
"""左侧导航按钮控件"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton


class NavButton(QPushButton):
    """左侧导航栏按钮"""

    def __init__(self, icon_text: str, label: str, parent=None):
        super().__init__(parent)
        self._icon_text = icon_text
        self._label = label
        self.setText(f"{icon_text}\n{label}")
        self.setCheckable(True)
        self.setFixedHeight(64)
        self.setCursor(Qt.PointingHandCursor)
        self._apply_style()

    def _apply_style(self):
        self.setStyleSheet("""
            NavButton {
                background: transparent;
                border: none;
                border-radius: 8px;
                color: #b0b8c8;
                font-size: 11px;
                font-weight: 500;
                padding: 4px 8px;
                text-align: center;
            }
            NavButton:hover {
                background: rgba(255,255,255,0.07);
                color: #e0e6f0;
            }
            NavButton:checked {
                background: rgba(82, 155, 245, 0.18);
                color: #529bf5;
                border-left: 3px solid #529bf5;
            }
        """)
