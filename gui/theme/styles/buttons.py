# -*- coding: utf-8 -*-
"""
gui/theme/styles/buttons.py - 统一按钮样式生成

所有按钮语义：primary / secondary / subtle / success / warning / danger / ghost
所有尺寸：md（默认）/ sm / lg / compact

交互设计（v3）：
  - primary 实心品牌色填充，hover 提亮、pressed 压暗，现代扁平风
  - success / warning / danger 平时为柔和底色，hover 时反转为实心填充，
    强化"即将执行该语义动作"的反馈
  - pressed 统一通过 padding-top 偏移 1px 制造下沉感

函数签名：btn_xxx(tokens, *, size="md") -> str
  返回可直接用于 setStyleSheet 的 QSS 字符串。
"""

from gui.theme.tokens import ThemeTokens


# ---------- 尺寸预设 ----------

_SIZE_PRESETS = {
    "sm":      {"radius": 8,  "min_height": 26, "padding": "0 12px", "font_size": 12, "font_weight": 500},
    "md":      {"radius": 10, "min_height": 34, "padding": "0 16px", "font_size": 13, "font_weight": 600},
    "lg":      {"radius": 11, "min_height": 42, "padding": "0 22px", "font_size": 14, "font_weight": 600},
    "compact": {"radius": 8,  "min_height": 26, "padding": "0 12px", "font_size": 12, "font_weight": 500},
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
    hover_text: str = "",
    pressed_text: str = "",
    disabled_bg: str,
    disabled_border: str,
    disabled_text: str,
    size: str = "md",
) -> str:
    """通用按钮 QSS 模板。"""
    p = _SIZE_PRESETS.get(size, _SIZE_PRESETS["md"])
    hover_text = hover_text or text_color
    pressed_text = pressed_text or hover_text
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
            color: {hover_text};
        }}
        QPushButton:pressed {{
            background-color: {pressed_bg};
            border-color: {pressed_border};
            color: {pressed_text};
            padding-top: 1px;
        }}
        QPushButton:focus {{
            border-color: {hover_border};
        }}
        QPushButton:disabled {{
            background-color: {disabled_bg};
            border-color: {disabled_border};
            color: {disabled_text};
        }}
    """


# ---------- 语义样式函数 ----------

def btn_primary(t: ThemeTokens, *, size: str = "md") -> str:
    """主要操作按钮（品牌色实心填充）。"""
    pressed_bg = "#5c5fd6" if t.is_dark() else "#4348c9"
    return _base_btn(
        t,
        bg=t.accent,
        hover_bg=t.accent_hover,
        pressed_bg=pressed_bg,
        border=t.accent,
        hover_border=t.accent_hover,
        pressed_border=pressed_bg,
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
    """低调操作按钮（不突出，hover 时品牌色描边提示可点）。"""
    if t.is_light():
        return _base_btn(
            t,
            bg="#ffffff",
            hover_bg="#f2f3fa",
            pressed_bg="#e9ebf5",
            border=t.border,
            hover_border=t.accent,
            pressed_border=t.accent,
            text_color=t.text_secondary,
            hover_text=t.text_primary,
            disabled_bg="#f6f7fb",
            disabled_border="#e8eaf1",
            disabled_text="#a7adbe",
            size=size,
        )
    return _base_btn(
        t,
        bg=t.bg_btn,
        hover_bg=t.bg_elevated,
        pressed_bg="#12141d",
        border=t.border,
        hover_border=t.accent,
        pressed_border=t.accent,
        text_color=t.text_secondary,
        hover_text=t.text_primary,
        disabled_bg=t.bg_elevated,
        disabled_border=t.border,
        disabled_text=t.text_muted,
        size=size,
    )


def _semantic_btn(
    t: ThemeTokens,
    *,
    soft_bg: str,
    soft_border: str,
    tone: str,
    fill_text: str,
    size: str,
) -> str:
    """语义动作按钮：平时柔和底色，hover 反转为实心填充。"""
    return _base_btn(
        t,
        bg=soft_bg,
        hover_bg=tone,
        pressed_bg=tone,
        border=soft_border,
        hover_border=tone,
        pressed_border=tone,
        text_color=tone,
        hover_text=fill_text,
        pressed_text=fill_text,
        disabled_bg=t.bg_elevated,
        disabled_border=t.border,
        disabled_text=t.text_muted,
        size=size,
    )


def btn_success(t: ThemeTokens, *, size: str = "md") -> str:
    """成功/确认类按钮。"""
    fill_text = "#06281a" if t.is_dark() else "#ffffff"
    return _semantic_btn(
        t,
        soft_bg=t.success_bg,
        soft_border=t.success_border,
        tone=t.success,
        fill_text=fill_text,
        size=size,
    )


def btn_warning(t: ThemeTokens, *, size: str = "md") -> str:
    """警告类按钮。"""
    fill_text = "#2b1e02" if t.is_dark() else "#ffffff"
    return _semantic_btn(
        t,
        soft_bg=t.warning_bg,
        soft_border=t.warning_border,
        tone=t.warning,
        fill_text=fill_text,
        size=size,
    )


def btn_danger(t: ThemeTokens, *, size: str = "md") -> str:
    """危险/删除类按钮。"""
    fill_text = "#2b0d0b" if t.is_dark() else "#ffffff"
    return _semantic_btn(
        t,
        soft_bg=t.danger_bg,
        soft_border=t.danger_border,
        tone=t.danger,
        fill_text=fill_text,
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
        hover_text=t.accent,
        disabled_bg="transparent",
        disabled_border=t.border,
        disabled_text=t.text_muted,
        size=size,
    )
