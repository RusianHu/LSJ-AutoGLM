# -*- coding: utf-8 -*-
"""
gui/theme/system_watcher.py - 系统主题监听器

职责：
  - 监听 Windows 系统深浅色变化
  - 与 UI 解耦，只负责检测并发出信号
  - 不可监听时降级为轮询
  - 不做任何样式应用，只通知 ThemeManager
"""

from PySide6.QtCore import QObject, Signal, QTimer


class SystemThemeWatcher(QObject):
    """
    系统主题变化监听器。

    通过周期轮询 Qt palette 的亮度检测当前深浅色。
    当系统主题切换时，发出 system_theme_changed 信号。

    Windows 11 支持跟随系统深浅色，
    不可监听的平台会静默降级（继续轮询，但平台不切换时不发信号）。
    """

    # 发出解析后的模式字符串："dark" | "light"
    system_theme_changed = Signal(str)

    # 轮询间隔（毫秒）
    _POLL_INTERVAL_MS = 2000

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._current_mode: str = self._detect_mode()
        self._timer = QTimer(self)
        self._timer.setInterval(self._POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._poll)
        self._timer.start()

    # ---------- 公开接口 ----------

    def current_mode(self) -> str:
        """返回最近检测到的系统主题模式（\"dark\" | \"light\"）。"""
        return self._current_mode

    def stop(self):
        """停止轮询，通常在应用退出时调用。"""
        if self._timer.isActive():
            self._timer.stop()

    def force_refresh(self):
        """立即重新检测并广播（如手动刷新需求）。"""
        self._poll()

    # ---------- 内部实现 ----------

    @staticmethod
    def _detect_mode() -> str:
        """
        通过 Qt palette 的窗口背景亮度推断系统深浅色。
        lightness < 128 视为深色。
        """
        try:
            from PySide6.QtWidgets import QApplication
            from PySide6.QtGui import QPalette
            app = QApplication.instance()
            if app is None:
                return "dark"
            palette = app.palette()
            lightness = palette.color(QPalette.ColorRole.Window).lightness()
            return "dark" if lightness < 128 else "light"
        except Exception:
            return "dark"

    def _poll(self):
        """轮询检测，如有变化则发出信号。"""
        new_mode = self._detect_mode()
        if new_mode != self._current_mode:
            self._current_mode = new_mode
            self.system_theme_changed.emit(new_mode)
