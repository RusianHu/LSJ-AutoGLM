# -*- coding: utf-8 -*-
"""吸附在 scrcpy 独立窗口边缘的 QtScrcpy 风格工具栏。"""

from __future__ import annotations

import sys

from PySide6.QtCore import QPoint, QRect, QTimer, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QVBoxLayout, QWidget

from gui.widgets.mirror_toolbar import MirrorToolbar


class MirrorToolbarWindow(QWidget):
    """把工具栏作为独立 Qt.Tool 窗口贴在原生 scrcpy 窗口右侧。

    scrcpy 是 SDL 原生窗口，不能使用 Qt 的 eventFilter 监听它。因此这里
    使用轻量的 Win32 窗口矩形轮询，等价实现 QtScrcpy MagneticWidget 对
    Move/Resize/Show 的跟随行为，同时不 reparent scrcpy 窗口。

    工具栏不是全局置顶窗口，而是通过 Win32 owner 关系挂在 scrcpy
    窗口组下。这样它仍然显示在镜像窗口侧边，但主控制台或其它窗口被
    激活时可以自然地盖住整组窗口。
    """

    action_triggered = Signal(str)

    def __init__(self, translator=None, parent=None):
        super().__init__(parent)
        self.setObjectName("MirrorToolbarWindow")
        self.setWindowFlags(
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        # 工具栏窗口从不激活（WindowDoesNotAcceptFocus）。默认情况下 Qt
        # 只在激活窗口内显示 tooltip，因此必须显式允许非激活窗口弹出提示，
        # 否则悬停按钮不会出现文字气泡。
        self.setAttribute(Qt.WA_AlwaysShowToolTips, True)
        self.setFixedWidth(63)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._toolbar = MirrorToolbar(translator=translator, parent=self)
        self._toolbar.action_triggered.connect(self.action_triggered)
        layout.addWidget(self._toolbar)

        self._target_hwnd = 0
        self._enabled = True
        self._last_geometry: tuple[int, int, int, int] | None = None
        self._owner_bound = False
        self._follow_timer = QTimer(self)
        self._follow_timer.setInterval(120)
        self._follow_timer.timeout.connect(self.sync_geometry)
        self._follow_timer.start()

    def set_target_hwnd(self, hwnd: int | None) -> None:
        self._target_hwnd = int(hwnd or 0)
        self._last_geometry = None
        self._owner_bound = False
        self._set_native_owner(self._target_hwnd)
        self.sync_geometry()

    def set_toolbar_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)
        if not self._enabled:
            self.hide()
            self._owner_bound = False
        else:
            self.sync_geometry()

    def set_actions(self, actions) -> None:
        self._toolbar.set_actions(actions)
        self._last_geometry = None
        self.sync_geometry()

    def set_action_enabled(self, enabled: bool) -> None:
        self._toolbar.set_action_enabled(enabled)

    def set_translator(self, translator) -> None:
        self._toolbar.set_translator(translator)
        self._last_geometry = None
        self.sync_geometry()

    def apply_theme(self, theme_vars: dict | None) -> None:
        self._toolbar.apply_theme(theme_vars)

    def shutdown(self) -> None:
        self._follow_timer.stop()
        self._target_hwnd = 0
        self._set_native_owner(0)
        self.hide()

    def sync_geometry(self) -> None:
        if not self._enabled or sys.platform != "win32" or not self._target_hwnd:
            if self.isVisible():
                self.hide()
                self._owner_bound = False
            return

        target = self._get_window_rect(self._target_hwnd)
        if target is None or target.width() <= 0 or target.height() <= 0:
            if self.isVisible():
                self.hide()
                self._owner_bound = False
            return

        if self._is_iconic(self._target_hwnd):
            if self.isVisible():
                self.hide()
                self._owner_bound = False
            return

        screen = QGuiApplication.screenAt(target.topLeft())
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        available = screen.availableGeometry() if screen else QRect(0, 0, 3840, 2160)

        preferred_height = max(220, self._toolbar.sizeHint().height())
        height = min(preferred_height, max(180, target.height() - 8))
        self.setFixedHeight(height)
        width = self.width()

        # QtScrcpy 的 AP_OUTSIDE_RIGHT：优先贴在镜像窗口右侧；屏幕边缘
        # 没有空间时退到左侧，避免工具栏被屏幕裁切。
        right_x = target.right()
        left_x = target.left() - width
        if right_x + width <= available.right() + 1:
            x = right_x
        elif left_x >= available.left():
            x = left_x
        else:
            x = max(available.left(), min(right_x, available.right() - width + 1))

        y = target.top() + 30
        if y + height > available.bottom() + 1:
            y = available.bottom() - height + 1
        y = max(available.top(), y)

        geometry = (int(x), int(y), int(width), int(height))
        geometry_changed = geometry != self._last_geometry
        if geometry_changed:
            self.setGeometry(*geometry)
            self._last_geometry = geometry
        just_shown = not self.isVisible()
        if just_shown:
            self.show()
        # 仅在几何变化或首次显示时重绑 owner。稳定状态下不再每 120ms
        # 调用 SetWindowPos —— 持续扰动窗口会不断重置 Qt 的悬停计时，
        # 导致按钮 tooltip 永远无法弹出。
        if geometry_changed or just_shown or not self._owner_bound:
            self._set_native_owner(self._target_hwnd)
            self._owner_bound = True

    @staticmethod
    def _set_window_long_ptr(user32, hwnd: int, index: int, value: int) -> None:
        """兼容 32/64 位 Python 的 SetWindowLongPtrW。"""
        import ctypes

        setter = getattr(user32, "SetWindowLongPtrW", None)
        if setter is None:
            setter = user32.SetWindowLongW
        setter.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        setter.restype = ctypes.c_void_p
        setter(ctypes.c_void_p(hwnd), index, ctypes.c_void_p(value))

    def _set_native_owner(self, owner_hwnd: int) -> None:
        """把 Qt 工具栏挂到 scrcpy 的 Z-order 窗口组下。

        这里使用 owner 而不是 parent：工具栏仍是独立顶层窗口，可以
        绘制在 scrcpy 右侧；同时 Windows 会把它作为 scrcpy 的 owned
        window 参与显示、隐藏、最小化和 Z-order 管理。
        """
        if sys.platform != "win32" or not self.winId():
            return
        try:
            import ctypes

            user32 = ctypes.windll.user32
            user32.IsWindow.argtypes = [ctypes.c_void_p]
            user32.IsWindow.restype = ctypes.c_bool
            user32.SetWindowPos.argtypes = [
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_uint,
            ]
            user32.SetWindowPos.restype = ctypes.c_bool
            toolbar_hwnd = int(self.winId())
            if not user32.IsWindow(ctypes.c_void_p(toolbar_hwnd)):
                return
            if owner_hwnd and not user32.IsWindow(ctypes.c_void_p(int(owner_hwnd))):
                owner_hwnd = 0

            # GWLP_HWNDPARENT 对顶层窗口表示 owner，而不是 child parent。
            self._set_window_long_ptr(
                user32,
                toolbar_hwnd,
                -8,  # GWLP_HWNDPARENT
                int(owner_hwnd),
            )

            # 重新放回 owner 附近的普通 Z-order；不激活、不改变几何，
            # 也不使用 HWND_TOPMOST。
            if owner_hwnd:
                user32.SetWindowPos(
                    ctypes.c_void_p(toolbar_hwnd),
                    ctypes.c_void_p(int(owner_hwnd)),
                    0,
                    0,
                    0,
                    0,
                    0x0001  # SWP_NOSIZE
                    | 0x0002  # SWP_NOMOVE
                    | 0x0010  # SWP_NOACTIVATE
                    | 0x0200,  # SWP_NOOWNERZORDER
                )
        except Exception:
            # 非 Windows 环境或窗口已经销毁时，Qt 工具栏仍可安全隐藏。
            return

    @staticmethod
    def _get_window_rect(hwnd: int) -> QRect | None:
        try:
            import ctypes
            import ctypes.wintypes

            rect = ctypes.wintypes.RECT()
            if not ctypes.windll.user32.IsWindow(hwnd):
                return None
            if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return None
            return QRect(
                int(rect.left),
                int(rect.top),
                int(rect.right - rect.left),
                int(rect.bottom - rect.top),
            )
        except Exception:
            return None

    @staticmethod
    def _is_iconic(hwnd: int) -> bool:
        try:
            import ctypes

            return bool(ctypes.windll.user32.IsIconic(hwnd))
        except Exception:
            return False

    def closeEvent(self, event) -> None:
        # 工具栏没有独立的生命周期；关闭主应用时由父页面统一清理。
        self.hide()
        event.ignore()
