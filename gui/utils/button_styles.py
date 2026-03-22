# -*- coding: utf-8 -*-
"""
gui/utils/button_styles.py

[已废弃] 此模块是过渡兼容层。

新代码应使用：
    from gui.theme.styles.buttons import btn_primary, btn_subtle, btn_danger, ...
    from gui.theme.component_registry import get_registry

此文件在迁移完成后将被移除，
当前保留是为了避免现有页面在迁移期间崩溃。
"""

import warnings

from gui.theme.styles.buttons import (
    btn_primary as _btn_primary,
    btn_subtle as _btn_subtle,
    btn_success as _btn_success,
    btn_danger as _btn_danger,
    btn_warning as _btn_warning,
    btn_secondary as _btn_secondary,
)
from gui.theme.tokens import ThemeTokens
from gui.theme.themes import resolve_theme_tokens


def _make_tokens(theme_mode: str, theme_vars: dict | None = None) -> ThemeTokens:
    """
    从旧式 (theme_mode, theme_vars) 参数构造 ThemeTokens。
    用于兼容期间的参数桥接。
    """
    return resolve_theme_tokens(theme_mode)


def button_style_template(
    theme_mode: str,
    theme_vars: dict | None = None,
    *,
    bg: str,
    hover_bg: str,
    pressed_bg: str,
    border: str,
    hover_border: str,
    pressed_border: str,
    text: str,
    compact: bool = False,
    disabled_bg: str = "",
    disabled_border: str = "",
    disabled_text: str = "",
    font_size: int = 13,
) -> str:
    """
    [已废弃] 旧版按钮模板。
    新代码请使用 gui.theme.styles.buttons 中的函数。
    """
    is_light = theme_mode == "light"
    v = theme_vars or {}
    radius = 6 if compact else 8
    min_height = 22 if compact else 32
    padding = "0 10px" if compact else "0 14px"
    font_weight = 500 if compact else 600
    disabled_bg = disabled_bg or ("#eef2f7" if is_light else "#161b22")
    disabled_border = disabled_border or ("#d5deea" if is_light else "#21262d")
    disabled_text = disabled_text or v.get("text_muted", "#94a3b8" if is_light else "#484f58")

    return f"""
        QPushButton {{
            background-color:{bg};
            border:1px solid {border};
            border-radius:{radius}px;
            color:{text};
            padding:{padding};
            min-height:{min_height}px;
            font-size:{font_size}px;
            font-weight:{font_weight};
        }}
        QPushButton:hover {{
            background-color:{hover_bg};
            border-color:{hover_border};
        }}
        QPushButton:pressed {{
            background-color:{pressed_bg};
            border-color:{pressed_border};
        }}
        QPushButton:disabled {{
            background-color:{disabled_bg};
            border-color:{disabled_border};
            color:{disabled_text};
        }}
    """


def primary_btn_style(theme_mode: str, theme_vars: dict | None = None, compact: bool = False) -> str:
    """[已废弃] 请使用 gui.theme.styles.buttons.btn_primary"""
    t = _make_tokens(theme_mode, theme_vars)
    size = "compact" if compact else "md"
    return _btn_primary(t, size=size)


def subtle_btn_style(theme_mode: str, theme_vars: dict | None = None, compact: bool = False) -> str:
    """[已废弃] 请使用 gui.theme.styles.buttons.btn_subtle"""
    t = _make_tokens(theme_mode, theme_vars)
    size = "compact" if compact else "md"
    return _btn_subtle(t, size=size)


def danger_btn_style(theme_mode: str, theme_vars: dict | None = None, compact: bool = False) -> str:
    """[已废弃] 请使用 gui.theme.styles.buttons.btn_danger"""
    t = _make_tokens(theme_mode, theme_vars)
    size = "compact" if compact else "md"
    return _btn_danger(t, size=size)


def success_btn_style(theme_mode: str, theme_vars: dict | None = None, compact: bool = False) -> str:
    """[已废弃] 请使用 gui.theme.styles.buttons.btn_success"""
    t = _make_tokens(theme_mode, theme_vars)
    size = "compact" if compact else "md"
    return _btn_success(t, size=size)


def warning_btn_style(theme_mode: str, theme_vars: dict | None = None, compact: bool = False) -> str:
    """[已废弃] 请使用 gui.theme.styles.buttons.btn_warning"""
    t = _make_tokens(theme_mode, theme_vars)
    size = "compact" if compact else "md"
    return _btn_warning(t, size=size)
