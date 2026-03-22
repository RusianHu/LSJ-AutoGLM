# -*- coding: utf-8 -*-
"""
gui/theme/preferences.py - 主题偏好枚举

定义：
  ThemePreference  用户配置偏好（system / light / dark）
  ResolvedThemeMode 实际解析结果（light / dark）
"""

from enum import Enum


class ThemePreference(str, Enum):
    """
    用户可选的主题偏好。

    - SYSTEM：跟随操作系统深浅色（默认）
    - LIGHT：强制浅色
    - DARK：强制深色
    """
    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"

    @classmethod
    def from_str(cls, value: str) -> "ThemePreference":
        """从字符串安全解析，未知值降级为 SYSTEM。"""
        try:
            return cls(value.lower())
        except (ValueError, AttributeError):
            return cls.SYSTEM


class ResolvedThemeMode(str, Enum):
    """
    实际解析后的主题模式（只有 light/dark 两种）。

    由 ThemeManager 根据 ThemePreference 和系统主题决策得出，
    是唯一允许下游消费的最终状态。
    """
    LIGHT = "light"
    DARK = "dark"

    def is_dark(self) -> bool:
        return self == ResolvedThemeMode.DARK

    def is_light(self) -> bool:
        return self == ResolvedThemeMode.LIGHT
