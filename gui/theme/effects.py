# -*- coding: utf-8 -*-
"""
gui/theme/effects.py - 主题感知的图形效果助手

基于 QGraphicsDropShadowEffect 提供真实高斯投影（QSS 无法实现），
用于卡片/导航条的"悬浮"层级感。所有函数幂等：重复调用只更新参数。

注意：
  - 不要对承载原生窗口（scrcpy 内嵌宿主）的容器应用任何 QGraphicsEffect，
    否则会强制离屏渲染导致原生子窗口显示异常。
"""

from PySide6.QtCore import QPropertyAnimation, QEasingCurve, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QWidget

from gui.theme.tokens import ThemeTokens

# 供动画对象防 GC 引用
_PAGE_FADE_ANIM_ATTR = "_theme_fade_anim"


def _shadow_color(tokens: ThemeTokens, strength: str) -> QColor:
    """根据主题模式返回投影颜色（暗色更深，浅色更淡且偏冷灰蓝）。"""
    if tokens.is_dark():
        alpha = {"soft": 110, "card": 150, "bar": 180}.get(strength, 150)
        return QColor(0, 0, 0, alpha)
    alpha = {"soft": 26, "card": 38, "bar": 50}.get(strength, 38)
    return QColor(31, 45, 70, alpha)


def apply_card_shadow(
    widget: QWidget,
    tokens: ThemeTokens,
    *,
    blur: int = 22,
    y_offset: int = 3,
    strength: str = "card",
) -> None:
    """
    为卡片类控件应用主题感知投影。幂等：已有投影时仅更新颜色/参数。

    strength: "soft" | "card" | "bar"（透明度递增）
    """
    if widget is None:
        return
    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsDropShadowEffect):
        effect = QGraphicsDropShadowEffect(widget)
        widget.setGraphicsEffect(effect)
    effect.setBlurRadius(blur)
    effect.setXOffset(0)
    effect.setYOffset(y_offset)
    effect.setColor(_shadow_color(tokens, strength))


def apply_bar_shadow(widget: QWidget, tokens: ThemeTokens) -> None:
    """顶部导航条投影：更贴近的短投影，制造 app bar 悬浮感。"""
    apply_card_shadow(widget, tokens, blur=18, y_offset=2, strength="bar")


def clear_effect(widget: QWidget) -> None:
    """移除控件上的图形效果。"""
    if widget is not None:
        widget.setGraphicsEffect(None)


def play_page_fade(page: QWidget, duration_ms: int = 160) -> None:
    """
    页面切换淡入动画。动画结束后自动移除效果，恢复常规渲染路径。

    调用方需自行确保 page 不承载原生子窗口（如 scrcpy 内嵌宿主）。
    """
    if page is None:
        return
    # 已在播放则跳过，避免叠加效果
    old_anim = getattr(page, _PAGE_FADE_ANIM_ATTR, None)
    if old_anim is not None:
        return

    effect = QGraphicsOpacityEffect(page)
    effect.setOpacity(0.0)
    page.setGraphicsEffect(effect)

    anim = QPropertyAnimation(effect, b"opacity", page)
    anim.setDuration(duration_ms)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.OutCubic)

    def _cleanup():
        page.setGraphicsEffect(None)
        if getattr(page, _PAGE_FADE_ANIM_ATTR, None) is anim:
            setattr(page, _PAGE_FADE_ANIM_ATTR, None)

    anim.finished.connect(_cleanup)
    setattr(page, _PAGE_FADE_ANIM_ATTR, anim)
    anim.start(QPropertyAnimation.DeleteWhenStopped)
