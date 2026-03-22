# -*- coding: utf-8 -*-
"""GUI 按钮局部样式 helper。"""


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
    v = theme_vars or {}
    if theme_mode == "light":
        return button_style_template(
            theme_mode,
            v,
            bg=v.get("accent", "#2563eb"),
            hover_bg="#1d4ed8",
            pressed_bg="#1e40af",
            border=v.get("accent", "#2563eb"),
            hover_border="#1d4ed8",
            pressed_border="#1e40af",
            text="#ffffff",
            compact=compact,
            disabled_bg="#dbe7ff",
            disabled_border="#c7d7fe",
            disabled_text="#8aa1d1",
        )
    return button_style_template(
        theme_mode,
        v,
        bg=v.get("accent", "#1f6feb"),
        hover_bg="#388bfd",
        pressed_bg="#1b62d1",
        border=v.get("accent", "#1f6feb"),
        hover_border="#388bfd",
        pressed_border="#1b62d1",
        text="#ffffff",
        compact=compact,
    )


def danger_btn_style(theme_mode: str, theme_vars: dict | None = None, compact: bool = False) -> str:
    v = theme_vars or {}
    if theme_mode == "light":
        return button_style_template(
            theme_mode,
            v,
            bg=v.get("danger_bg", "#fee2e5"),
            hover_bg="#fecdd3",
            pressed_bg="#fda4af",
            border=v.get("danger_border", "#c9525a"),
            hover_border=v.get("danger", "#b91c1c"),
            pressed_border=v.get("danger", "#b91c1c"),
            text=v.get("danger", "#b91c1c"),
            compact=compact,
        )
    return button_style_template(
        theme_mode,
        v,
        bg="#21262d",
        hover_bg="#3d1a1a",
        pressed_bg="#4a1d1d",
        border=v.get("danger_border", "#8f2d2b"),
        hover_border=v.get("danger", "#f85149"),
        pressed_border=v.get("danger", "#f85149"),
        text=v.get("danger", "#f85149"),
        compact=compact,
        disabled_border="#21262d",
    )


def warning_btn_style(theme_mode: str, theme_vars: dict | None = None, compact: bool = False) -> str:
    v = theme_vars or {}
    if theme_mode == "light":
        return button_style_template(
            theme_mode,
            v,
            bg=v.get("warning_bg", "#fef3c0"),
            hover_bg="#fde68a",
            pressed_bg="#fcd34d",
            border=v.get("warning_border", "#c28b00"),
            hover_border=v.get("warning", "#92400e"),
            pressed_border=v.get("warning", "#92400e"),
            text=v.get("warning", "#92400e"),
            compact=compact,
        )
    return button_style_template(
        theme_mode,
        v,
        bg="#21262d",
        hover_bg="#3d3200",
        pressed_bg="#4a3d00",
        border=v.get("warning_border", "#6e4800"),
        hover_border=v.get("warning", "#e3b341"),
        pressed_border=v.get("warning", "#e3b341"),
        text=v.get("warning", "#e3b341"),
        compact=compact,
        disabled_border="#21262d",
    )


def success_btn_style(theme_mode: str, theme_vars: dict | None = None, compact: bool = False) -> str:
    v = theme_vars or {}
    if theme_mode == "light":
        return button_style_template(
            theme_mode,
            v,
            bg=v.get("success_bg", "#dcfce7"),
            hover_bg="#bbf7d0",
            pressed_bg="#86efac",
            border=v.get("success_border", "#16a34a"),
            hover_border=v.get("success", "#166534"),
            pressed_border=v.get("success", "#166534"),
            text=v.get("success", "#166534"),
            compact=compact,
        )
    return button_style_template(
        theme_mode,
        v,
        bg="#0f2418",
        hover_bg="#12351f",
        pressed_bg="#184828",
        border=v.get("success_border", "#238636"),
        hover_border=v.get("success", "#3fb950"),
        pressed_border=v.get("success", "#3fb950"),
        text=v.get("success", "#3fb950"),
        compact=compact,
        disabled_border="#21262d",
    )


def subtle_btn_style(theme_mode: str, theme_vars: dict | None = None, compact: bool = False) -> str:
    v = theme_vars or {}
    if theme_mode == "light":
        return button_style_template(
            theme_mode,
            v,
            bg=v.get("bg_elevated", "#edf2f7"),
            hover_bg="#e2e8f0",
            pressed_bg="#d9e2ec",
            border=v.get("border", "#d5deea"),
            hover_border=v.get("accent", "#2563eb"),
            pressed_border=v.get("accent", "#2563eb"),
            text=v.get("text_primary", "#1f2937"),
            compact=compact,
            disabled_bg="#f8fafc",
            disabled_border="#e2e8f0",
            disabled_text="#94a3b8",
        )
    return button_style_template(
        theme_mode,
        v,
        bg=v.get("bg_btn", "#161b22"),
        hover_bg=v.get("bg_elevated", "#1b2432"),
        pressed_bg="#0f1724",
        border=v.get("border", "#30363d"),
        hover_border=v.get("accent", "#4f8cff"),
        pressed_border=v.get("accent", "#4f8cff"),
        text=v.get("text_primary", "#c9d1d9"),
        compact=compact,
        disabled_bg="#161b22",
        disabled_border="#21262d",
        disabled_text="#484f58",
    )
