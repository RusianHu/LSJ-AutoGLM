# -*- coding: utf-8 -*-
"""设备页 - ADB 检查、连接管理、设备切换"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from gui.services.device_service import DeviceStatus


class DevicePage(QWidget):
    """设备页"""

    def __init__(self, services: dict, parent=None):
        super().__init__(parent)
        self._services = services
        self._device = services.get("device")
        self._build_ui()
        self._connect_signals()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)

        # 标题
        title = QLabel("设备管理")
        title.setStyleSheet("font-size:18px; font-weight:bold; color:#c9d1d9;")
        root.addWidget(title)

        # ADB 状态区
        adb_group = QGroupBox("ADB 状态")
        adb_layout = QVBoxLayout(adb_group)
        adb_layout.setSpacing(8)

        self._adb_status_lbl = QLabel("ADB 状态: 检查中...")
        self._adb_status_lbl.setStyleSheet("color:#8b949e; font-size:13px;")
        adb_layout.addWidget(self._adb_status_lbl)

        btn_check_adb = QPushButton("重新检查 ADB")
        btn_check_adb.setFixedWidth(150)
        btn_check_adb.clicked.connect(self._on_check_adb)
        adb_layout.addWidget(btn_check_adb)
        root.addWidget(adb_group)

        # 设备列表区
        devices_group = QGroupBox("已连接设备")
        devices_layout = QVBoxLayout(devices_group)
        devices_layout.setSpacing(8)

        self._device_list = QListWidget()
        self._device_list.setStyleSheet("""
            QListWidget {
                background:#0a0e17; border:1px solid #21262d;
                border-radius:6px; color:#c9d1d9; font-size:13px;
                padding:4px;
            }
            QListWidget::item { padding:8px 12px; border-radius:4px; }
            QListWidget::item:selected { background:#264f78; }
            QListWidget::item:hover { background:#21262d; }
        """)
        self._device_list.setFixedHeight(180)
        self._device_list.currentRowChanged.connect(self._on_device_selected)
        devices_layout.addWidget(self._device_list)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._btn_select = QPushButton("选为当前设备")
        self._btn_select.clicked.connect(self._on_set_active)
        btn_row.addWidget(self._btn_select)

        self._btn_disconnect = QPushButton("断开连接")
        self._btn_disconnect.clicked.connect(self._on_disconnect)
        btn_row.addWidget(self._btn_disconnect)

        btn_refresh = QPushButton("刷新")
        btn_refresh.clicked.connect(self._on_refresh)
        btn_row.addWidget(btn_refresh)
        btn_row.addStretch()
        devices_layout.addLayout(btn_row)
        root.addWidget(devices_group)

        # 无线连接区
        wifi_group = QGroupBox("无线连接（TCP/IP）")
        wifi_layout = QHBoxLayout(wifi_group)
        wifi_layout.setSpacing(8)

        wifi_layout.addWidget(QLabel("设备地址:"))
        self._wifi_input = QLineEdit()
        self._wifi_input.setPlaceholderText("192.168.x.x:5555")
        self._wifi_input.setFixedWidth(200)
        wifi_layout.addWidget(self._wifi_input)

        btn_wifi_connect = QPushButton("连接")
        btn_wifi_connect.setStyleSheet("""
            QPushButton {
                background:#1f6feb; border:none; border-radius:6px;
                color:#fff; padding:6px 18px;
            }
            QPushButton:hover { background:#388bfd; }
        """)
        btn_wifi_connect.clicked.connect(self._on_wifi_connect)
        wifi_layout.addWidget(btn_wifi_connect)
        wifi_layout.addStretch()
        root.addWidget(wifi_group)

        # 详情/日志区
        detail_group = QGroupBox("操作日志")
        detail_layout = QVBoxLayout(detail_group)
        self._detail_log = QPlainTextEdit()
        self._detail_log.setReadOnly(True)
        self._detail_log.setFixedHeight(120)
        self._detail_log.setStyleSheet("""
            QPlainTextEdit {
                background:#0a0e17; border:none; border-radius:4px;
                color:#8b949e; font-size:12px; padding:6px;
                font-family: 'Consolas', monospace;
            }
        """)
        detail_layout.addWidget(self._detail_log)
        root.addWidget(detail_group)

        # ADB Keyboard 检查
        kbd_group = QGroupBox("ADB Keyboard")
        kbd_layout = QHBoxLayout(kbd_group)
        self._kbd_status_lbl = QLabel("—")
        self._kbd_status_lbl.setStyleSheet("color:#8b949e;")
        kbd_layout.addWidget(self._kbd_status_lbl)
        btn_check_kbd = QPushButton("检查当前设备")
        btn_check_kbd.clicked.connect(self._on_check_kbd)
        kbd_layout.addWidget(btn_check_kbd)
        kbd_layout.addStretch()
        root.addWidget(kbd_group)

        # scrcpy 状态
        scrcpy_group = QGroupBox("scrcpy 依赖")
        scrcpy_layout = QHBoxLayout(scrcpy_group)
        self._scrcpy_status_lbl = QLabel("—")
        self._scrcpy_status_lbl.setStyleSheet("color:#8b949e;")
        scrcpy_layout.addWidget(self._scrcpy_status_lbl)
        btn_check_scrcpy = QPushButton("检查")
        btn_check_scrcpy.clicked.connect(self._on_check_scrcpy)
        scrcpy_layout.addWidget(btn_check_scrcpy)
        scrcpy_layout.addStretch()
        root.addWidget(scrcpy_group)

        root.addStretch(1)

    def _connect_signals(self):
        if self._device:
            self._device.devices_changed.connect(self._refresh_device_list)
            self._device.adb_status_changed.connect(self._on_adb_status)
            # 初始刷新
            self._refresh_device_list(self._device.devices)

    # ---------- 回调 ----------

    def _on_check_adb(self):
        if self._device:
            ok, msg = self._device.check_adb()
            self._log(f"ADB 检查: {'通过' if ok else '失败'} - {msg}")

    def _on_adb_status(self, available: bool, msg: str):
        color = "#3fb950" if available else "#f85149"
        status = "可用" if available else "不可用"
        self._adb_status_lbl.setText(
            f"ADB 状态: <span style='color:{color}'>{status}</span>  {msg}"
        )

    def _refresh_device_list(self, devices):
        self._device_list.clear()
        if not devices:
            self._device_list.addItem("  （未找到设备）")
            return
        for d in devices:
            color = "#3fb950" if d.status == DeviceStatus.CONNECTED else "#e3b341"
            text = f"[{d.status.value.upper()}]  {d.display_name}"
            item = QListWidgetItem(text)
            from PySide6.QtGui import QColor
            item.setForeground(QColor(color))
            item.setData(Qt.UserRole, d.device_id)
            self._device_list.addItem(item)

    def _on_device_selected(self, row):
        pass  # 仅 UI 高亮，点击"选为当前设备"才生效

    def _on_set_active(self):
        item = self._device_list.currentItem()
        if not item:
            return
        device_id = item.data(Qt.UserRole)
        if device_id and self._device:
            self._device.select_device(device_id)
            self._log(f"已选择设备: {device_id}")

    def _on_disconnect(self):
        item = self._device_list.currentItem()
        if not item:
            return
        device_id = item.data(Qt.UserRole)
        if device_id and self._device:
            ok, msg = self._device.disconnect_device(device_id)
            self._log(f"断开 {device_id}: {msg}")

    def _on_refresh(self):
        if self._device:
            self._device.refresh()
            self._log("设备列表已刷新")

    def _on_wifi_connect(self):
        addr = self._wifi_input.text().strip()
        if not addr:
            return
        if self._device:
            ok, msg = self._device.connect_device(addr)
            self._log(f"连接 {addr}: {'成功' if ok else '失败'} - {msg}")

    def _on_check_kbd(self):
        device_id = ""
        if self._device and self._device.selected_device:
            device_id = self._device.selected_device.device_id
        if not device_id:
            self._kbd_status_lbl.setText("请先选择设备")
            return
        if self._device:
            ok, msg = self._device.check_adb_keyboard(device_id)
            color = "#3fb950" if ok else "#f85149"
            self._kbd_status_lbl.setText(
                f"<span style='color:{color}'>{msg}</span>"
            )
            self._log(f"ADB Keyboard 检查: {msg}")

    def _on_check_scrcpy(self):
        mirror = self._services.get("mirror")
        if mirror:
            ok, msg = mirror.check_available()
        elif self._device:
            ok, msg = self._device.check_scrcpy()
        else:
            ok, msg = False, "服务不可用"
        color = "#3fb950" if ok else "#e3b341"
        self._scrcpy_status_lbl.setText(
            f"<span style='color:{color}'>{msg}</span>"
        )
        self._log(f"scrcpy 检查: {msg}")

    def _log(self, msg: str):
        from PySide6.QtCore import QDateTime
        ts = QDateTime.currentDateTime().toString("hh:mm:ss")
        self._detail_log.appendPlainText(f"[{ts}] {msg}")

    def on_page_activated(self):
        if self._device:
            self._device.refresh()
