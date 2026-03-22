# -*- coding: utf-8 -*-
"""
gui/theme/styles/buttons.py - 统一按钮样式生成

所有按钮语义：primary / secondary / subtle / success / warning / danger / ghost
所有尺寸：md（默认）/ sm / compact

函数签名：btn_xxx(tokens, *, size="md") -> str
  返回可直接用于 setStyleSheet 的 QSS 字符串。
"""

from gui.theme.tokens import ThemeTokens


# ---------- 尺寸预设 ----------

_SIZE_PRESETS = {
    "sm":      {"radius": 6,  "min_height": 24, "padding": "0 8px",  "font_size": 12, "font_weight": 500},
    "md":      {"radius": 8,  "min_height": 32, "padding": "0 14px", "font_size": 13, "font_weight": 600},
    "lg":      {"radius": 8,  "min_height": 40, "padding": "0 20px", "font_size": 14, "font_weight": 600},
    "compact": {"radius": 6,  "min_height": 22, "padding": "0 10px", "font_size": 12, "font_weight": 500},
}


def _base_btn(
    t: ThemeTokens,
    *,
    bg: str,
    hover_bg: str,
    pressed_bg: str,
    border: str,
    hover_border: str,
    pressed_border: str,
    text_color: str,
    disabled_bg: str,
    disabled_border: str,
    disabled_text: str,
    size: str = "md",
) -> str:
    """通用按钮 QSS 模板。"""
    p = _SIZE_PRESETS.get(size, _SIZE_PRESETS["md"])
    return f"""
        QPushButton {{
            background-color: {bg};
            border: 1px solid {border};
            border-radius: {p['radius']}px;
            color: {text_color};
            padding: {p['padding']};
            min-height: {p['min_height']}px;
            font-size: {p['font_size']}px;
            font-weight: {p['font_weight']};
        }}
        QPushButton:hover {{
            background-color: {hover_bg};
            border-color: {hover_border};
        }}
        QPushButton:pressed {{
            background-color: {pressed_bg};
            border-color: {pressed_border};
        }}
        QPushButton:disabled {{
            background-color: {disabled_bg};
            border-color: {disabled_border};
            color: {disabled_text};
        }}
    """


# ---------- 语义样式函数 ----------

def btn_primary(t: ThemeTokens, *, size: str = "md") -> str:
    """主要操作按钮（品牌色填充）。"""
    return _base_btn(
        t,
        bg=t.accent,
        hover_bg=t.accent_hover,
        pressed_bg=t.accent,
        border=t.accent,
        hover_border=t.accent_hover,
        pressed_border=t.accent,
        text_color="#ffffff",
        disabled_bg=t.bg_elevated,
        disabled_border=t.border,
        disabled_text=t.text_muted,
        size=size,
    )


def btn_secondary(t: ThemeTokens, *, size: str = "md") -> str:
    """次要操作按钮（带边框，浅背景）。"""
    return _base_btn(
        t,
        bg=t.bg_btn,
        hover_bg=t.bg_elevated,
        pressed_bg=t.bg_secondary,
        border=t.border,
        hover_border=t.border_hover,
        pressed_border=t.border_hover,
        text_color=t.text_primary,
        disabled_bg=t.bg_elevated,
        disabled_border=t.border,
        disabled_text=t.text_muted,
        size=size,
    )


def btn_subtle(t: ThemeTokens, *, size: str = "md") -> str:
    """低调操作按钮（不突出，弱化边框）。"""
    if t.is_light():
        return _base_btn(
            t,
            bg=t.bg_elevated,
            hover_bg="#e2e8f0",
            pressed_bg="#d9e2ec",
            border=t.border,
            hover_border=t.accent,
            pressed_border=t.accent,
            text_color=t.text_primary,
            disabled_bg="#f8fafc",
            disabled_border="#e2e8f0",
            disabled_text="#94a3b8",
            size=size,
        )
    return _base_btn(
        t,
        bg=t.bg_btn,
        hover_bg=t.bg_elevated,
        pressed_bg="#0f1724",
        border=t.border,
        hover_border=t.accent,
        pressed_border=t.accent,
        text_color=t.text_primary,
        disabled_bg=t.bg_elevated,
        disabled_border=t.border,
        disabled_text=t.text_muted,
        size=size,
    )


def btn_success(t: ThemeTokens, *, size: str = "md") -> str:
    """成功/确认类按钮。"""
    return _base_btn(
        t,
        bg=t.success_bg,
        hover_bg=t.success_bg,
        pressed_bg=t.success_bg,
        border=t.success_border,
        hover_border=t.success,
        pressed_border=t.success,
        text_color=t.success,
        disabled_bg=t.bg_elevated,
        disabled_border=t.border,
        disabled_text=t.text_muted,
        size=size,
    )


def btn_warning(t: ThemeTokens, *, size: str = "md") -> str:
    """警告类按钮。"""
    return _base_btn(
        t,
        bg=t.warning_bg,
        hover_bg=t.warning_bg,
        pressed_bg=t.warning_bg,
        border=t.warning_border,
        hover_border=t.warning,
        pressed_border=t.warning,
        text_color=t.warning,
        disabled_bg=t.bg_elevated,
        disabled_border=t.border,
        disabled_text=t.text_muted,
        size=size,
    )


def btn_danger(t: ThemeTokens, *, size: str = "md") -> str:
    """危险/删除类按钮。"""
    return _base_btn(
        t,
        bg=t.danger_bg,
        hover_bg=t.danger_bg,
        pressed_bg=t.danger_bg,
        border=t.danger_border,
        hover_border=t.danger,
        pressed_border=t.danger,
        text_color=t.danger,
        disabled_bg=t.bg_elevated,
        disabled_border=t.border,
        disabled_text=t.text_muted,
        size=size,
    )


def btn_ghost(t: ThemeTokens, *, size: str = "md") -> str:
    """幽灵按钮（透明背景，仅边框）。"""
    return _base_btn(
        t,
        bg="transparent",
        hover_bg=t.accent_soft,
        pressed_bg=t.accent_soft,
        border=t.border,
        hover_border=t.accent,
        pressed_border=t.accent,
        text_color=t.text_secondary,
        disabled_bg="transparent",
        disabled_border=t.border,
        disabled_text=t.text_muted,
        size=size,
    )
