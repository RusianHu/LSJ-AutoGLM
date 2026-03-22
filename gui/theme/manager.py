# -*- coding: utf-8 -*-
"""
gui/theme/manager.py - 主题管理器（整个主题系统唯一入口）

职责：
  - 管理当前主题偏好和解析后的 tokens
  - 协调配置层与系统监听层
  - 向 UI 广播 theme_changed 信号
  - 是系统主题解析的唯一权威

原则：
  - 主窗口不再负责主题解析
  - 页面不直接读取配置服务判断当前主题
  - 所有主题变化都经 ThemeManager 广播
"""

from PySide6.QtCore import QObject, Signal

from gui.theme.preferences import ThemePreference, ResolvedThemeMode
from gui.theme.tokens import ThemeTokens
from gui.theme.themes import resolve_theme_tokens
from gui.theme.system_watcher import SystemThemeWatcher


class ThemeManager(QObject):
    """
    主题管理器 - 整个主题系统唯一入口。

    生命周期：
      由 MainWindow 创建，保存于 _services['theme_manager']。
      页面通过 services 获取，不需要自行实例化。

    公开能力：
      set_preference(pref)        设置主题偏好并广播
      get_preference()            获取当前偏好
      get_resolved_mode()         获取解析后的实际模式
      get_tokens()                获取当前 ThemeTokens
      refresh_from_system()       手动触发系统主题刷新
      theme_changed               信号：theme_changed(ThemeTokens)
    """

    # 主题变化信号，携带最新 ThemeTokens
    theme_changed = Signal(object)  # ThemeTokens

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._preference: ThemePreference = ThemePreference.SYSTEM
        self._tokens: ThemeTokens | None = None
        self._watcher = SystemThemeWatcher(self)
        self._watcher.system_theme_changed.connect(self._on_system_theme_changed)

    # ---------- 公开接口 ----------

    def set_preference(self, pref: str | ThemePreference):
        """
        设置主题偏好并重新广播。

        Args:
            pref: ThemePreference 枚举或字符串 ("system"/"dark"/"light")
        """
        if isinstance(pref, str):
            pref = ThemePreference.from_str(pref)
        self._preference = pref
        self._resolve_and_broadcast()

    def get_preference(self) -> ThemePreference:
        """返回当前用户主题偏好。"""
        return self._preference

    def get_resolved_mode(self) -> str:
        """
        返回实际解析后的主题模式（\"dark\" | \"light\"）。
        system 偏好时由系统主题决定，其余直接返回偏好值。
        """
        if self._preference == ThemePreference.SYSTEM:
            return self._watcher.current_mode()
        return self._preference.value

    def get_tokens(self) -> ThemeTokens:
        """
        获取当前主题令牌。
        首次调用时触发解析（懒初始化）。
        """
        if self._tokens is None:
            self._resolve_and_broadcast()
        return self._tokens

    def refresh_from_system(self):
        """
        手动触发系统主题刷新。
        system 偏好时重新检测系统主题并广播。
        """
        self._watcher.force_refresh()
        if self._preference == ThemePreference.SYSTEM:
            self._resolve_and_broadcast()

    def stop(self):
        """停止系统监听，在应用退出时调用。"""
        self._watcher.stop()

    # ---------- 内部实现 ----------

    def _on_system_theme_changed(self, _mode: str):
        """系统主题变化回调，仅在 system 偏好时响应。"""
        if self._preference == ThemePreference.SYSTEM:
            self._resolve_and_broadcast()

    def _resolve_and_broadcast(self):
        """解析当前主题并向所有订阅方广播。"""
        mode = self.get_resolved_mode()
        self._tokens = resolve_theme_tokens(mode)
        self.theme_changed.emit(self._tokens)
