# -*- coding: utf-8 -*-
"""
gui/theme/styles/banners.py - 统一横幅/通知样式生成

语义：info / success / warning / error
"""

from gui.theme.tokens import ThemeTokens


def _banner_base(bg: str, border: str, color: str) -> str:
    return f"""
        QLabel {{
            background: {bg};
            border: 1px solid {border};
            color: {color};
            border-radius: 6px;
            padding: 6px 10px;
            font-size: 12px;
        }}
    """


def banner_info(t: ThemeTokens) -> str:
    """信息横幅（蓝色强调）。"""
    return _banner_base(
        bg=t.accent_soft,
        border=t.accent,
        color=t.accent,
    )


def banner_success(t: ThemeTokens) -> str:
    """成功横幅（绿色）。"""
    return _banner_base(
        bg=t.success_bg,
        border=t.success_border,
        color=t.success,
    )


def banner_warning(t: ThemeTokens) -> str:
    """警告横幅（黄色）。"""
    return _banner_base(
        bg=t.warning_bg,
        border=t.warning_border,
        color=t.warning,
    )


def banner_error(t: ThemeTokens) -> str:
    """错误横幅（红色）。"""
    return _banner_base(
        bg=t.danger_bg,
        border=t.danger_border,
        color=t.danger,
    )
