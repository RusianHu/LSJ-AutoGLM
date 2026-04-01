# -*- coding: utf-8 -*-
"""
MirrorLabel - 设备镜像显示控件。

功能：
- 自适应容器大小缩放（保持手机宽高比）
- 鼠标左键点击 -> 换算为手机坐标 -> adb shell input tap
- 支持设置当前 device_id 以控制目标设备
"""

import subprocess
import sys

from PySide6.QtCore import Qt, QRect, QPoint, QThread, Signal
from PySide6.QtGui import QPixmap, QCursor, QKeySequence
from PySide6.QtWidgets import QApplication, QLabel, QSizePolicy


class _AdbTapWorker(QThread):
    failed = Signal(str)

    def __init__(self, device_id: str, x: int, y: int):
        super().__init__()
        self._device_id = device_id
        self._x = x
        self._y = y

    def run(self):
        try:
            result = subprocess.run(
                ["adb", "-s", self._device_id, "shell", "input", "tap", str(self._x), str(self._y)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                timeout=8,
            )
        except Exception as e:
            self.failed.emit(str(e))
            return

        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            self.failed.emit(detail or f"adb tap failed (code={result.returncode})")


class _AdbTextWorker(QThread):
    failed = Signal(str)

    def __init__(self, device_id: str, text: str | None = None, keycode: int | None = None):
        super().__init__()
        self._device_id = device_id
        self._text = text
        self._keycode = keycode

    def run(self):
        try:
            if self._keycode is not None:
                result = subprocess.run(
                    ["adb", "-s", self._device_id, "shell", "input", "keyevent", str(self._keycode)],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                    timeout=8,
                )
                if result.returncode != 0:
                    detail = (result.stderr or result.stdout or "").strip()
                    self.failed.emit(detail or f"adb keyevent failed (code={result.returncode})")
                return

            if not self._text:
                return

            from phone_agent.adb.input import detect_and_set_adb_keyboard, restore_keyboard, type_text

            original_ime = detect_and_set_adb_keyboard(self._device_id)
            try:
                type_text(self._text, self._device_id)
            finally:
                if original_ime:
                    restore_keyboard(original_ime, self._device_id)
        except Exception as e:
            self.failed.emit(str(e))


class MirrorLabel(QLabel):
    """
    自适应镜像图片显示控件。

    使用方式：
        label = MirrorLabel()
        label.set_device_id("77eaf689")
        label.set_raw_pixmap(pixmap)  # 每次收到新帧时调用
    """

    tap_failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._raw_pixmap: QPixmap | None = None   # 原始帧（手机分辨率）
        self._device_id: str = ""
        self._tap_enabled: bool = True
        self._tap_worker: _AdbTapWorker | None = None
        self._input_worker: _AdbTextWorker | None = None

        self.setAlignment(Qt.AlignCenter)
        self.setScaledContents(False)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(1, 1)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        # 显示手型光标，提示可点击
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setToolTip("点击此处控制手机；点击后可直接键盘输入，Ctrl+V 粘贴")

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def set_device_id(self, device_id: str):
        """设置目标 ADB 设备 ID"""
        self._device_id = device_id or ""

    def set_tap_enabled(self, enabled: bool):
        """是否响应鼠标点击（任务运行中可禁用手动操控）"""
        self._tap_enabled = enabled
        self.setCursor(
            QCursor(Qt.PointingHandCursor) if enabled else QCursor(Qt.ArrowCursor)
        )
        self.setToolTip("点击此处控制手机；点击后可直接键盘输入，Ctrl+V 粘贴" if enabled else "")

    def set_raw_pixmap(self, pixmap: QPixmap):
        """
        更新原始帧并重新缩放至当前控件尺寸显示。
        每次收到 ADB 截图帧时调用。
        """
        self._raw_pixmap = pixmap
        self._refresh_display()

    def clear_frame(self):
        """清除当前帧"""
        self._raw_pixmap = None
        self.clear()

    # ------------------------------------------------------------------
    # 内部：缩放显示
    # ------------------------------------------------------------------

    def _refresh_display(self):
        """将 _raw_pixmap 缩放到当前控件大小并显示"""
        if self._raw_pixmap is None or self._raw_pixmap.isNull():
            return
        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return
        scaled = self._raw_pixmap.scaled(
            w, h,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.setPixmap(scaled)

    # ------------------------------------------------------------------
    # 重写事件
    # ------------------------------------------------------------------

    def resizeEvent(self, event):
        """窗口 resize 时重新缩放已有帧，避免图片拉伸或留黑边"""
        super().resizeEvent(event)
        self._refresh_display()

    def mousePressEvent(self, event):
        """
        鼠标左键点击 -> 换算为手机坐标 -> adb shell input tap x y

        坐标换算说明：
        由于图片使用 KeepAspectRatio 居中显示，实际图片区域不一定与控件等大，
        需要先算出图片在控件内的实际 Rect，再将点击坐标映射到手机原始分辨率。
        """
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        if not self._tap_enabled:
            event.ignore()
            return
        if not self._device_id:
            self.tap_failed.emit("当前未绑定设备，无法点击")
            event.accept()
            return
        if self._raw_pixmap is None or self._raw_pixmap.isNull():
            event.ignore()
            return

        # 计算图片在控件内居中时的实际 Rect
        img_rect = self._image_rect()
        if img_rect is None:
            event.ignore()
            return

        # 点击坐标（相对于控件）
        click_pos = event.position().toPoint()  # PySide6 返回 QPointF

        # 判断点击是否在图片区域内
        if not img_rect.contains(click_pos):
            event.ignore()
            return

        # 换算为图片内相对坐标
        rel_x = click_pos.x() - img_rect.x()
        rel_y = click_pos.y() - img_rect.y()

        # 换算为手机原始分辨率坐标
        phone_w = self._raw_pixmap.width()
        phone_h = self._raw_pixmap.height()
        scale_x = phone_w / img_rect.width()
        scale_y = phone_h / img_rect.height()
        tap_x = int(rel_x * scale_x)
        tap_y = int(rel_y * scale_y)

        # 确保坐标在合理范围内
        tap_x = max(0, min(tap_x, phone_w - 1))
        tap_y = max(0, min(tap_y, phone_h - 1))

        self.setFocus(Qt.MouseFocusReason)
        self._adb_tap(tap_x, tap_y)
        event.accept()

    def keyPressEvent(self, event):
        if not self._device_id:
            self.tap_failed.emit("当前未绑定设备，无法输入")
            event.accept()
            return

        if event.matches(QKeySequence.Paste):
            clipboard = QApplication.clipboard()
            text = clipboard.text() if clipboard is not None else ""
            if text:
                self._adb_type_text(text)
            else:
                self.tap_failed.emit("剪贴板为空，无法粘贴")
            event.accept()
            return

        key_map = {
            Qt.Key_Return: 66,
            Qt.Key_Enter: 66,
            Qt.Key_Backspace: 67,
            Qt.Key_Delete: 112,
            Qt.Key_Tab: 61,
            Qt.Key_Left: 21,
            Qt.Key_Right: 22,
            Qt.Key_Up: 19,
            Qt.Key_Down: 20,
            Qt.Key_Escape: 4,
        }
        keycode = key_map.get(event.key())
        if keycode is not None:
            self._adb_keyevent(keycode)
            event.accept()
            return

        text = event.text()
        if text:
            self._adb_type_text(text)
            event.accept()
            return

        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _image_rect(self) -> QRect | None:
        """
        返回当前缩放图片在控件内的实际 QRect（居中对齐）。
        若没有当前帧则返回 None。
        """
        if self._raw_pixmap is None or self._raw_pixmap.isNull():
            return None
        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return None

        # 根据 KeepAspectRatio 计算缩放后的尺寸
        raw_w = self._raw_pixmap.width()
        raw_h = self._raw_pixmap.height()
        if raw_w <= 0 or raw_h <= 0:
            return None

        scale = min(w / raw_w, h / raw_h)
        img_w = int(raw_w * scale)
        img_h = int(raw_h * scale)

        # 居中偏移
        x_offset = (w - img_w) // 2
        y_offset = (h - img_h) // 2
        return QRect(x_offset, y_offset, img_w, img_h)

    def _adb_tap(self, x: int, y: int):
        """在后台异步执行 adb shell input tap"""
        if self._tap_worker and self._tap_worker.isRunning():
            return
        worker = _AdbTapWorker(self._device_id, x, y)
        worker.failed.connect(self.tap_failed.emit)
        worker.finished.connect(worker.deleteLater)
        self._tap_worker = worker
        worker.start()

    def _adb_type_text(self, text: str):
        """在后台异步执行 ADB Keyboard 文本输入"""
        if self._input_worker and self._input_worker.isRunning():
            return
        worker = _AdbTextWorker(self._device_id, text=text)
        worker.failed.connect(self.tap_failed.emit)
        worker.finished.connect(worker.deleteLater)
        self._input_worker = worker
        worker.start()

    def _adb_keyevent(self, keycode: int):
        """在后台异步执行 adb shell input keyevent"""
        if self._input_worker and self._input_worker.isRunning():
            return
        worker = _AdbTextWorker(self._device_id, keycode=keycode)
        worker.failed.connect(self.tap_failed.emit)
        worker.finished.connect(worker.deleteLater)
        self._input_worker = worker
        worker.start()
