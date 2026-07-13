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
from queue import Empty, Queue

from PySide6.QtCore import Qt, QRect, QThread, QTimer, Signal
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


class _AdbInputWorker(QThread):
    """串行处理截图降级模式下的键盘输入，避免快速输入时丢字符。"""

    failed = Signal(str)

    def __init__(self, device_id: str):
        super().__init__()
        self._device_id = device_id
        self._commands: Queue[tuple[str, object | None]] = Queue()
        self._running = True
        self._original_ime = ""
        self._keyboard_active = False

    def activate(self):
        self._commands.put(("activate", None))

    def type_text(self, text: str):
        if text:
            self._commands.put(("text", text))

    def keyevent(self, keycode: int):
        self._commands.put(("key", int(keycode)))

    def deactivate(self):
        self._commands.put(("deactivate", None))

    def stop(self):
        self._running = False
        self._commands.put(("stop", None))

    def _activate_keyboard(self):
        if self._keyboard_active:
            return
        from phone_agent.adb.input import detect_and_set_adb_keyboard

        self._original_ime = detect_and_set_adb_keyboard(self._device_id)
        self._keyboard_active = True

    def _restore_keyboard(self):
        if not self._keyboard_active:
            return
        try:
            from phone_agent.adb.input import restore_keyboard

            if self._original_ime:
                restore_keyboard(self._original_ime, self._device_id)
        finally:
            self._keyboard_active = False
            self._original_ime = ""

    def run(self):
        try:
            while self._running:
                try:
                    command, payload = self._commands.get(timeout=0.25)
                except Empty:
                    continue

                if command == "stop":
                    break
                try:
                    if command == "activate":
                        self._activate_keyboard()
                    elif command == "deactivate":
                        self._restore_keyboard()
                    elif command == "text":
                        self._activate_keyboard()
                        from phone_agent.adb.input import type_text

                        type_text(str(payload), self._device_id)
                    elif command == "key":
                        result = subprocess.run(
                            ["adb", "-s", self._device_id, "shell", "input", "keyevent", str(payload)],
                            capture_output=True,
                            text=True,
                            encoding="utf-8",
                            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                            timeout=8,
                        )
                        if result.returncode != 0:
                            detail = (result.stderr or result.stdout or "").strip()
                            raise RuntimeError(detail or f"adb keyevent failed (code={result.returncode})")
                except Exception as exc:
                    self.failed.emit(str(exc))
        finally:
            try:
                self._restore_keyboard()
            except Exception as exc:
                self.failed.emit(str(exc))


class MirrorLabel(QLabel):
    """
    自适应镜像图片显示控件。

    使用方式：
        label = MirrorLabel()
        label.set_device_id("77eaf689")
        label.set_raw_pixmap(pixmap)  # 每次收到新帧时调用
    """

    tap_failed = Signal(str)

    def __init__(self, parent=None, translator=None):
        super().__init__(parent)
        self._translator = translator
        self._raw_pixmap: QPixmap | None = None   # 原始帧（手机分辨率）
        self._device_id: str = ""
        self._tap_enabled: bool = True
        self._tap_worker: _AdbTapWorker | None = None
        self._input_worker: _AdbInputWorker | None = None
        self._text_buffer = ""
        self._text_flush_timer = QTimer(self)
        self._text_flush_timer.setSingleShot(True)
        self._text_flush_timer.setInterval(45)
        self._text_flush_timer.timeout.connect(self._flush_text_buffer)

        self.setAlignment(Qt.AlignCenter)
        self.setScaledContents(False)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(1, 1)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_InputMethodEnabled, True)
        # 显示手型光标，提示可点击
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.set_tap_enabled(True)

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def set_translator(self, translator=None):
        """设置翻译回调并立即刷新镜像控件 tooltip。"""
        self._translator = translator
        if self._tap_enabled:
            self.setToolTip(self._translate("page.dashboard.mirror.control.tooltip"))

    def _translate(self, key: str) -> str:
        if callable(self._translator):
            try:
                return self._translator(key)
            except Exception:
                pass
        from gui.i18n.locales.cn import CN

        return CN.get(key, f"[[{key}]]")

    def set_device_id(self, device_id: str):
        """设置目标 ADB 设备 ID"""
        resolved = device_id or ""
        if resolved == self._device_id:
            return
        self.shutdown_input()
        self._device_id = resolved

    def set_tap_enabled(self, enabled: bool):
        """是否响应鼠标点击（任务运行中可禁用手动操控）"""
        self._tap_enabled = enabled
        self.setCursor(
            QCursor(Qt.PointingHandCursor) if enabled else QCursor(Qt.ArrowCursor)
        )
        self.setToolTip(
            self._translate("page.dashboard.mirror.control.tooltip") if enabled else ""
        )

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

    def shutdown_input(self):
        """停止输入分发线程并恢复进入镜像前的手机输入法。"""
        self._text_flush_timer.stop()
        self._text_buffer = ""
        worker = self._input_worker
        self._input_worker = None
        if worker:
            worker.stop()
            worker.wait(3000)
            worker.deleteLater()

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
            self._flush_text_buffer()
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
            self._flush_text_buffer()
            self._adb_keyevent(keycode)
            event.accept()
            return

        text = event.text()
        if text and not (event.modifiers() & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier)):
            self._queue_text(text)
            event.accept()
            return

        super().keyPressEvent(event)

    def inputMethodEvent(self, event):
        """接收电脑输入法提交的中文等 Unicode 文本。"""
        commit = event.commitString()
        if commit:
            self._queue_text(commit)
        event.accept()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        worker = self._ensure_input_worker()
        if worker:
            worker.activate()

    def focusOutEvent(self, event):
        self._flush_text_buffer()
        if self._input_worker:
            self._input_worker.deactivate()
        super().focusOutEvent(event)

    def closeEvent(self, event):
        self.shutdown_input()
        super().closeEvent(event)

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

    def _ensure_input_worker(self) -> _AdbInputWorker | None:
        if not self._device_id:
            return None
        # start() 后的极短时间内 isRunning() 仍可能为 False；只要实例存在，
        # 就必须复用同一个串行队列，否则快速输入会并发创建多个 QThread。
        if self._input_worker:
            return self._input_worker
        worker = _AdbInputWorker(self._device_id)
        worker.failed.connect(self.tap_failed.emit)
        self._input_worker = worker
        worker.start()
        return worker

    def _queue_text(self, text: str):
        self._text_buffer += text
        self._text_flush_timer.start()

    def _flush_text_buffer(self):
        text = self._text_buffer
        self._text_buffer = ""
        self._text_flush_timer.stop()
        if text:
            self._adb_type_text(text)

    def _adb_type_text(self, text: str):
        """把文本加入串行 ADBKeyboard 输入队列。"""
        worker = self._ensure_input_worker()
        if worker:
            worker.type_text(text)

    def _adb_keyevent(self, keycode: int):
        """把按键加入串行 adb shell input keyevent 队列。"""
        worker = self._ensure_input_worker()
        if worker:
            worker.keyevent(keycode)
