# -*- coding: utf-8 -*-
"""QtScrcpy 风格的设备镜像工具栏控件。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QFrame, QToolButton, QVBoxLayout, QWidget

from gui.services.mirror_actions import MIRROR_TOOLBAR_ACTIONS


_ICON_CODES = {
    # 与 QtScrcpy ToolForm 使用的 Font Awesome 字符保持一致。
    "fullscreen": 0xF0B2,
    "notifications": 0xF103,
    "touch": 0xF111,
    "screen_on": 0xF06E,
    "screen_off": 0xF070,
    "power": 0xF011,
    "volume_up": 0xF028,
    "volume_down": 0xF027,
    "app_switch": 0xF24D,
    "menu": 0xF096,
    "home": 0xF1DB,
    "back": 0xF053,
    "screenshot": 0xF0C4,
    "clipboard": 0xF0C5,
}

_FALLBACK_ICONS = {
    "fullscreen": "□",
    "notifications": "↑",
    "touch": "•",
    "screen_on": "◉",
    "screen_off": "○",
    "power": "⏻",
    "volume_up": "+",
    "volume_down": "−",
    "app_switch": "▣",
    "menu": "≡",
    "home": "⌂",
    "back": "‹",
    "screenshot": "▧",
    "clipboard": "▤",
}


def _load_fontawesome() -> tuple[str, int]:
    """加载随项目分发的 QtScrcpy Font Awesome 字体，失败时由调用方降级。"""

    candidates = (
        Path(__file__).resolve().parents[1] / "assets" / "fontawesome-webfont.ttf",
        Path(__file__).resolve().parents[2] / "resources" / "fontawesome-webfont.ttf",
    )
    try:
        from gui.utils.runtime import bundle_root

        candidates += (
            bundle_root() / "gui" / "assets" / "fontawesome-webfont.ttf",
            bundle_root() / "resources" / "fontawesome-webfont.ttf",
        )
    except Exception:
        pass

    for path in candidates:
        if not path.exists():
            continue
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id < 0:
            continue
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            return families[0], font_id
    return "", -1


class MirrorToolbar(QFrame):
    """QtScrcpy ToolForm 内部的竖向图标按钮区。

    控件本身不负责窗口吸附；外部窗口模式由
    :class:`gui.widgets.mirror_toolbar_window.MirrorToolbarWindow` 承载，
    这样同一个按钮控件也能用于内嵌镜像和 ADB 截图降级模式。
    """

    action_triggered = Signal(str)

    def __init__(self, translator=None, parent: QWidget | None = None):
        super().__init__(parent)
        self._translator = translator
        self._buttons: dict[str, QToolButton] = {}
        self._fullscreen_spacer: QWidget | None = None
        self._font_family, self._font_id = _load_fontawesome()

        self.setObjectName("MirrorToolbar")
        self.setFixedWidth(63)
        self.setMinimumHeight(220)
        self.setFrameShape(QFrame.StyledPanel)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 30, 6, 10)
        layout.setSpacing(4)

        for spec in MIRROR_TOOLBAR_ACTIONS:
            button = QToolButton(self)
            button.setObjectName(f"MirrorToolbar_{spec.name}")
            button.setToolButtonStyle(Qt.ToolButtonTextOnly)
            button.setAutoRaise(False)
            button.setFixedSize(49, 29)
            button.clicked.connect(
                lambda _checked=False, name=spec.name: self.action_triggered.emit(name)
            )
            self._buttons[spec.name] = button
            layout.addWidget(button, 0, Qt.AlignHCenter)
            if spec.name == "fullscreen":
                self._fullscreen_spacer = QWidget(self)
                self._fullscreen_spacer.setFixedHeight(16)
                layout.addWidget(self._fullscreen_spacer)

        layout.addStretch(1)
        self.apply_theme({})
        self.set_translator(translator)

    @property
    def buttons(self) -> dict[str, QToolButton]:
        return dict(self._buttons)

    def set_translator(self, translator) -> None:
        self._translator = translator
        for spec in MIRROR_TOOLBAR_ACTIONS:
            button = self._buttons.get(spec.name)
            if button is None:
                continue
            if self._font_family:
                icon_font = QFont(self._font_family)
                icon_font.setPixelSize(16)
                button.setFont(icon_font)
                button.setText(chr(_ICON_CODES.get(spec.name, 0x25A1)))
            else:
                button.setFont(QFont())
                button.setText(_FALLBACK_ICONS.get(spec.name, "□"))
            button.setToolTip(self._translate(spec.tooltip_key, spec.name))

    def set_actions(self, actions) -> None:
        selected = {
            spec.name for spec in MIRROR_TOOLBAR_ACTIONS
        } if actions is None else {str(item) for item in actions}
        for name, button in self._buttons.items():
            button.setVisible(name in selected)
        if self._fullscreen_spacer is not None:
            self._fullscreen_spacer.setVisible("fullscreen" in selected)

    def set_action_enabled(self, enabled: bool) -> None:
        for button in self._buttons.values():
            button.setEnabled(bool(enabled))

    def apply_theme(self, theme_vars: dict | None) -> None:
        """使用主程序主题色，同时保留 QtScrcpy 的紧凑按钮结构。"""

        values = theme_vars or {}
        panel = values.get("bg_elevated", "#383838")
        button_bg = values.get("bg_secondary", panel)
        button_hover = values.get("bg_hover", values.get("accent_soft", "#646464"))
        border = values.get("border", "#242424")
        border_hover = values.get("border_hover", values.get("accent", "#4f8cff"))
        text = values.get("text_primary", "#DCDCDC")
        disabled_text = values.get("text_muted", "#777777")
        # 图标字体族必须写进自身样式表：全局壳层 QSS 的 font-family
        # 会覆盖 setFont() 程序化设置。
        icon_font_css = (
            f"font-family: '{self._font_family}'; font-size: 16px;"
            if self._font_family
            else ""
        )
        self.setStyleSheet(
            f"""
            QFrame#MirrorToolbar {{
                background: {panel};
                border: 1px solid {border};
                border-radius: 8px;
            }}
            QToolButton {{
                border: 1px solid {border};
                color: {text};
                padding: 5px;
                min-height: 15px;
                border-radius: 6px;
                background: {button_bg};
                {icon_font_css}
            }}
            QToolButton:hover {{
                border-color: {border_hover};
                background: {button_hover};
            }}
            QToolButton:pressed {{
                background: {values.get("accent_soft", button_hover)};
            }}
            QToolButton:disabled {{
                color: {disabled_text};
                background: {button_bg};
            }}
            """
        )

    def _translate(self, key: str, fallback: str) -> str:
        if callable(self._translator):
            try:
                value = self._translator(key)
                if value and not (value.startswith("[[") and value.endswith("]]")):
                    return value
            except Exception:
                pass
        return fallback
