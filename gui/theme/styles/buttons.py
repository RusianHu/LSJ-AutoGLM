# -*- coding: utf-8 -*-
"""
gui/theme/styles/buttons.py - 统一按钮样式生成

所有按钮语义：primary / secondary / subtle / success / warning / danger / ghost
所有尺寸：md（默认）/ sm / lg / compact

交互设计（v2）：
  - primary 使用纵向渐变填充，hover 提亮、pressed 压暗
  - success / warning / danger 平时为柔和底色，hover 时反转为实心填充，
    强化"即将执行该语义动作"的反馈
  - pressed 统一通过 padding-top 偏移 1px 制造下沉感

函数签名：btn_xxx(tokens, *, size="md") -> str
  返回可直接用于 setStyleSheet 的 QSS 字符串。
"""

from gui.theme.tokens import ThemeTokens


# ---------- 尺寸预设 ----------

_SIZE_PRESETS = {
    "sm":      {"radius": 7,  "min_height": 24, "padding": "0 10px", "font_size": 12, "font_weight": 500},
    "md":      {"radius": 9,  "min_height": 32, "padding": "0 14px", "font_size": 13, "font_weight": 600},
    "lg":      {"radius": 10, "min_height": 40, "padding": "0 20px", "font_size": 14, "font_weight": 600},
    "compact": {"radius": 7,  "min_height": 24, "padding": "0 10px", "font_size": 12, "font_weight": 500},
}


def _vgrad(top: str, bottom: str) -> str:
    """纵向线性渐变（QSS qlineargradient）。"""
    return (
        "qlineargradient(x1:0, y1:0, x2:0, y2:1, "
        f"stop:0 {top}, stop:1 {bottom})"
    )


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
    """主要操作按钮（品牌色渐变填充）。"""
    return _base_btn(
        t,
        bg=_vgrad(t.accent_hover, t.accent),
        hover_bg=_vgrad(t.accent_hover, t.accent_hover),
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
    """低调操作按钮（不突出，hover 时蓝色描边提示可点）。"""
    if t.is_light():
        return _base_btn(
            t,
            bg=t.bg_elevated,
            hover_bg="#e4ebf5",
            pressed_bg="#d9e3f0",
            border=t.border,
            hover_border=t.accent,
            pressed_border=t.accent,
            text_color=t.text_primary,
            disabled_bg="#f6f8fc",
            disabled_border="#e4ebf3",
            disabled_text="#9aa8bc",
            size=size,
        )
    return _base_btn(
        t,
        bg=t.bg_btn,
        hover_bg=t.bg_elevated,
        pressed_bg="#0f1521",
        border=t.border,
        hover_border=t.accent,
        pressed_border=t.accent,
        text_color=t.text_primary,
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
    fill_text = "#0b2416" if t.is_dark() else "#ffffff"
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
