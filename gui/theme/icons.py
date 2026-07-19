# -*- coding: utf-8 -*-
"""
gui/theme/icons.py - 图标字体（Font Awesome 4）统一加载与代码点表

复用随项目分发的 QtScrcpy fontawesome-webfont.ttf。
加载失败时调用方应使用 ICON_FALLBACKS 中的文本符号降级。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase

# 壳层与页面通用图标（Font Awesome 4 代码点）
ICON_CODES = {
    # 侧边栏导航
    "dashboard": 0xF0E4,   # tachometer
    "device": 0xF10B,      # mobile
    "history": 0xF1DA,     # history
    "settings": 0xF013,    # cog
    "diag": 0xF21E,        # heartbeat
    # 主题切换
    "theme_system": 0xF108,  # desktop
    "theme_dark": 0xF186,    # moon-o
    "theme_light": 0xF185,   # sun-o
    # 品牌
    "brand": 0xF135,       # rocket
}

# 字体缺失时的字符降级
ICON_FALLBACKS = {
    "dashboard": "◧",
    "device": "▯",
    "history": "↺",
    "settings": "⚙",
    "diag": "∿",
    "theme_system": "◐",
    "theme_dark": "●",
    "theme_light": "○",
    "brand": "◆",
}

_FONT_FAMILY: str | None = None


def fa_family() -> str:
    """
    返回 Font Awesome 字体族名；加载失败返回空字符串。
    进程内只加载一次。
    """
    global _FONT_FAMILY
    if _FONT_FAMILY is not None:
        return _FONT_FAMILY

    candidates = [
        Path(__file__).resolve().parents[1] / "assets" / "fontawesome-webfont.ttf",
        Path(__file__).resolve().parents[2] / "resources" / "fontawesome-webfont.ttf",
    ]
    try:
        from gui.utils.runtime import bundle_root

        candidates += [
            bundle_root() / "gui" / "assets" / "fontawesome-webfont.ttf",
            bundle_root() / "resources" / "fontawesome-webfont.ttf",
        ]
    except Exception:
        pass

    _FONT_FAMILY = ""
    for path in candidates:
        if not path.exists():
            continue
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id < 0:
            continue
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            _FONT_FAMILY = families[0]
            break
    return _FONT_FAMILY


def icon_char(name: str) -> str:
    """返回图标字符：字体可用时为 FA 代码点字符，否则为降级符号。"""
    if fa_family() and name in ICON_CODES:
        return chr(ICON_CODES[name])
    return ICON_FALLBACKS.get(name, "")


def icon_font(point_size: int = 13) -> QFont:
    """返回图标字体对象；字体缺失时退回默认 UI 字体。"""
    family = fa_family()
    font = QFont(family) if family else QFont()
    font.setPointSize(point_size)
    return font
