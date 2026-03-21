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

from PySide6.QtCore import Qt, QRect, QPoint
from PySide6.QtGui import QPixmap, QCursor
from PySide6.QtWidgets import QLabel, QSizePolicy


class MirrorLabel(QLabel):
    """
    自适应镜像图片显示控件。

    使用方式：
        label = MirrorLabel()
        label.set_device_id("77eaf689")
        label.set_raw_pixmap(pixmap)  # 每次收到新帧时调用
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._raw_pixmap: QPixmap | None = None   # 原始帧（手机分辨率）
        self._device_id: str = ""
        self._tap_enabled: bool = True

        self.setAlignment(Qt.AlignCenter)
        self.setScaledContents(False)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(1, 1)
        # 显示手型光标，提示可点击
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setToolTip("点击此处控制手机")

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
        self.setToolTip("点击此处控制手机" if enabled else "")

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
        super().mousePressEvent(event)

        if event.button() != Qt.LeftButton:
            return
        if not self._tap_enabled:
            return
        if not self._device_id:
            return
        if self._raw_pixmap is None or self._raw_pixmap.isNull():
            return

        # 计算图片在控件内居中时的实际 Rect
        img_rect = self._image_rect()
        if img_rect is None:
            return

        # 点击坐标（相对于控件）
        click_pos = event.position().toPoint()  # PySide6 返回 QPointF

        # 判断点击是否在图片区域内
        if not img_rect.contains(click_pos):
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

        self._adb_tap(tap_x, tap_y)

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
        try:
            subprocess.Popen(
                ["adb", "-s", self._device_id, "shell", "input", "tap",
                 str(x), str(y)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
        except Exception:
            pass
