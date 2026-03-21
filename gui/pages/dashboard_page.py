# -*- coding: utf-8 -*-
"""
工作台页面 - 首版核心页面。

布局：
  顶部工具区（任务输入 + 控制按钮 + 状态条）
  ├── 主区A：设备与镜像（左侧）
  └── 主区B：日志与事件（右侧）
"""

import time

from PySide6.QtCore import QEvent, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QFont, QPixmap, QTextCursor
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
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from gui.services.task_service import TaskState
from gui.services.mirror_service import MirrorMode, MirrorState


# 任务状态 -> (显示文字, 颜色)
STATE_DISPLAY = {
    TaskState.IDLE:      ("空闲",   "#8b949e"),
    TaskState.STARTING:  ("启动中", "#e3b341"),
    TaskState.RUNNING:   ("运行中", "#3fb950"),
    TaskState.PAUSED:    ("已暂停", "#e3b341"),
    TaskState.STOPPING:  ("停止中", "#f85149"),
    TaskState.COMPLETED: ("已完成", "#3fb950"),
    TaskState.FAILED:    ("失败",   "#f85149"),
    TaskState.CANCELLED: ("已取消", "#8b949e"),
}

# 镜像状态 -> 显示文字
MIRROR_STATE_DISPLAY = {
    MirrorState.IDLE:     ("未启动", "#8b949e"),
    MirrorState.STARTING: ("启动中", "#e3b341"),
    MirrorState.RUNNING:  ("运行中", "#3fb950"),
    MirrorState.ERROR:    ("出错",   "#f85149"),
    MirrorState.STOPPED:  ("已停止", "#8b949e"),
}


class DashboardPage(QWidget):
    """工作台页面"""

    def __init__(self, services: dict, parent=None):
        super().__init__(parent)
        self._services = services
        self._task = services.get("task")
        self._device = services.get("device")
        self._mirror = services.get("mirror")
        self._config = services.get("config")

        self._mirror_label: QLabel = None   # ADB 截图降级时的图片显示
        self._mirror_container: QWidget = None
        self._mirror_embedded = False

        self._build_ui()
        self._connect_signals()
        self._update_button_states(TaskState.IDLE)
        self._refresh_status_bar()

    # ================================================================
    # UI 构建
    # ================================================================

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 顶部工具区
        root.addWidget(self._build_toolbar())

        # 状态条
        root.addWidget(self._build_status_bar())

        # 主内容区（双主区 Splitter）
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(4)
        splitter.addWidget(self._build_mirror_panel())
        splitter.addWidget(self._build_log_panel())
        splitter.setSizes([480, 760])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)

    # ----------------------------------------------------------------
    # 顶部工具区
    # ----------------------------------------------------------------

    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(60)
        bar.setStyleSheet("background:#161b22; border-bottom:1px solid #21262d;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(10)

        # 任务输入框
        self._task_input = QLineEdit()
        self._task_input.setPlaceholderText("输入任务描述，例如：打开微信发消息给张三...")
        self._task_input.setMinimumWidth(380)
        self._task_input.returnPressed.connect(self._on_start)
        layout.addWidget(self._task_input, 1)

        # 开始按钮
        self._btn_start = QPushButton("开始")
        self._btn_start.setFixedWidth(72)
        self._btn_start.setStyleSheet(self._btn_primary_style())
        self._btn_start.clicked.connect(self._on_start)
        layout.addWidget(self._btn_start)

        # 停止按钮
        self._btn_stop = QPushButton("停止")
        self._btn_stop.setFixedWidth(72)
        self._btn_stop.setStyleSheet(self._btn_danger_style())
        self._btn_stop.clicked.connect(self._on_stop)
        layout.addWidget(self._btn_stop)

        # 暂停/恢复按钮
        self._btn_pause = QPushButton("暂停")
        self._btn_pause.setFixedWidth(72)
        self._btn_pause.clicked.connect(self._on_pause_resume)
        layout.addWidget(self._btn_pause)

        # 接管按钮
        self._btn_takeover = QPushButton("接管")
        self._btn_takeover.setFixedWidth(72)
        self._btn_takeover.setStyleSheet(self._btn_warning_style())
        self._btn_takeover.clicked.connect(self._on_takeover)
        layout.addWidget(self._btn_takeover)

        return bar

    # ----------------------------------------------------------------
    # 状态条
    # ----------------------------------------------------------------

    def _build_status_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(32)
        bar.setStyleSheet("background:#0d1117; border-bottom:1px solid #21262d;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(20)

        self._lbl_task_state = self._make_status_chip("状态", "空闲", "#8b949e")
        self._lbl_device_status = self._make_status_chip("设备", "未检测", "#8b949e")
        self._lbl_model_info = self._make_status_chip("模型", "—", "#8b949e")
        self._lbl_mirror_status = self._make_status_chip("镜像", "未启动", "#8b949e")

        layout.addWidget(self._lbl_task_state)
        layout.addWidget(self._make_sep())
        layout.addWidget(self._lbl_device_status)
        layout.addWidget(self._make_sep())
        layout.addWidget(self._lbl_model_info)
        layout.addWidget(self._make_sep())
        layout.addWidget(self._lbl_mirror_status)
        layout.addStretch(1)

        # 镜像控制按钮
        self._btn_mirror_toggle = QPushButton("启动镜像")
        self._btn_mirror_toggle.setFixedHeight(22)
        self._btn_mirror_toggle.setStyleSheet("""
            QPushButton {
                background: #21262d; border:1px solid #30363d; border-radius:4px;
                color:#8b949e; padding:0 10px; font-size:11px;
            }
            QPushButton:hover { background:#30363d; color:#c9d1d9; }
        """)
        self._btn_mirror_toggle.clicked.connect(self._on_mirror_toggle)
        layout.addWidget(self._btn_mirror_toggle)

        return bar

    def _make_status_chip(self, key: str, value: str, color: str) -> QLabel:
        lbl = QLabel(f"<span style='color:#484f58'>{key}:</span> "
                     f"<span style='color:{color}'>{value}</span>")
        lbl.setStyleSheet("font-size:12px;")
        return lbl

    def _make_sep(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setFixedHeight(16)
        sep.setStyleSheet("color:#21262d;")
        return sep

    # ----------------------------------------------------------------
    # 主区 A：设备与镜像
    # ----------------------------------------------------------------

    def _build_mirror_panel(self) -> QWidget:
        panel = QGroupBox("设备与镜像")
        panel.setMinimumWidth(380)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 16, 8, 8)
        layout.setSpacing(8)

        # 设备信息区
        self._device_info_lbl = QLabel("未连接任何设备")
        self._device_info_lbl.setStyleSheet("color:#8b949e; font-size:12px; padding:4px;")
        self._device_info_lbl.setWordWrap(True)
        layout.addWidget(self._device_info_lbl)

        # 镜像显示容器
        self._mirror_container = QWidget()
        self._mirror_container.setStyleSheet("background:#0a0e17; border-radius:6px;")
        self._mirror_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._mirror_container.installEventFilter(self)
        mirror_layout = QVBoxLayout(self._mirror_container)
        mirror_layout.setContentsMargins(0, 0, 0, 0)

        # 占位标签（scrcpy 外部窗口模式或未启动时）
        self._mirror_placeholder = QLabel("镜像未启动\n\n点击状态栏「启动镜像」按钮\n或使用 scrcpy 外部窗口")
        self._mirror_placeholder.setAlignment(Qt.AlignCenter)
        self._mirror_placeholder.setStyleSheet("""
            color:#484f58; font-size:13px; line-height:1.8;
        """)
        mirror_layout.addWidget(self._mirror_placeholder)

        # ADB 截图降级时的图片显示
        self._mirror_label = QLabel()
        self._mirror_label.setAlignment(Qt.AlignCenter)
        self._mirror_label.setScaledContents(False)
        self._mirror_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._mirror_label.hide()
        mirror_layout.addWidget(self._mirror_label)

        layout.addWidget(self._mirror_container, 1)

        # 接管提示横幅（隐藏）
        self._takeover_banner = QLabel("[ 接管模式 ] 请手动操作手机，完成后点击「继续执行」")
        self._takeover_banner.setAlignment(Qt.AlignCenter)
        self._takeover_banner.setStyleSheet("""
            background:#3d2800; color:#e3b341; font-size:12px;
            border:1px solid #6e4800; border-radius:4px; padding:6px;
        """)
        self._takeover_banner.hide()
        layout.addWidget(self._takeover_banner)

        # 继续执行按钮（接管模式下显示）
        self._btn_resume_exec = QPushButton("继续执行")
        self._btn_resume_exec.setStyleSheet(self._btn_primary_style())
        self._btn_resume_exec.hide()
        self._btn_resume_exec.clicked.connect(self._on_resume_after_takeover)
        layout.addWidget(self._btn_resume_exec)

        return panel

    # ----------------------------------------------------------------
    # 主区 B：日志与事件
    # ----------------------------------------------------------------

    def _build_log_panel(self) -> QWidget:
        panel = QGroupBox("日志与事件")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 16, 8, 8)
        layout.setSpacing(0)

        tabs = QTabWidget()
        tabs.setDocumentMode(True)

        # 原始日志 Tab
        self._log_view = QPlainTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setStyleSheet("""
            QPlainTextEdit {
                background:#0a0e17; color:#c9d1d9;
                border:none; border-radius:4px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size:12px;
                padding:8px;
            }
        """)
        self._log_view.setMaximumBlockCount(5000)
        tabs.addTab(self._log_view, "原始日志")

        # 事件时间线 Tab
        self._event_list = QListWidget()
        self._event_list.setStyleSheet("""
            QListWidget {
                background:#0a0e17; border:none; border-radius:4px;
                color:#c9d1d9; font-size:12px; padding:4px;
            }
            QListWidget::item {
                padding:4px 8px;
                border-bottom:1px solid #161b22;
            }
            QListWidget::item:selected { background:#264f78; }
        """)
        tabs.addTab(self._event_list, "事件时间线")

        layout.addWidget(tabs, 1)

        # 底部结果摘要区
        self._result_lbl = QLabel("")
        self._result_lbl.setWordWrap(True)
        self._result_lbl.setStyleSheet("""
            background:#161b22; border:1px solid #21262d;
            border-radius:4px; padding:8px; font-size:12px; color:#8b949e;
            margin-top:6px;
        """)
        self._result_lbl.setMinimumHeight(40)
        layout.addWidget(self._result_lbl)

        return panel

    # ================================================================
    # 信号连接
    # ================================================================

    def _connect_signals(self):
        if self._task:
            self._task.state_changed.connect(self._on_task_state_changed)
            self._task.log_line.connect(self._on_log_line)
            self._task.event_added.connect(self._on_event_added)
            self._task.task_finished.connect(self._on_task_finished)

        if self._device:
            self._device.devices_changed.connect(self._on_devices_changed)
            self._device.device_selected.connect(self._on_device_selected)

        if self._mirror:
            self._mirror.state_changed.connect(self._on_mirror_state_changed)
            self._mirror.mode_changed.connect(self._on_mirror_mode_changed)
            self._mirror.frame_ready.connect(self._on_mirror_frame)
            self._mirror.error_occurred.connect(self._on_mirror_error)
            self._mirror.window_created.connect(self._on_mirror_window_created)

    # ================================================================
    # 按钮回调
    # ================================================================

    def _on_start(self):
        text = self._task_input.text().strip()
        if not text:
            self._task_input.setFocus()
            return
        if self._task:
            # 清空上次日志
            self._log_view.clear()
            self._event_list.clear()
            self._result_lbl.setText("")
            self._task.start_task(text)

    def _on_stop(self):
        if self._task:
            self._task.stop_task()

    def _on_pause_resume(self):
        if not self._task:
            return
        state = self._task.state
        if state == TaskState.RUNNING:
            self._task.pause_task()
        elif state == TaskState.PAUSED:
            self._task.resume_task()

    def _on_takeover(self):
        if self._task:
            self._task.request_takeover("用户主动接管")

    def _on_resume_after_takeover(self):
        if self._task:
            self._task.resume_task()

    def _on_mirror_toggle(self):
        if not self._mirror:
            return
        if self._mirror.is_running:
            self._mirror.stop()
        else:
            device_id = ""
            if self._device and self._device.selected_device:
                device_id = self._device.selected_device.device_id
            elif self._config:
                device_id = self._config.get("OPEN_AUTOGLM_DEVICE_ID")
            if not device_id:
                # 尝试从设备列表取第一个
                if self._device and self._device.devices:
                    device_id = self._device.devices[0].device_id
            if device_id:
                embed_wid = None
                if self._mirror_container and self._mirror_container.isVisible():
                    try:
                        embed_wid = int(self._mirror_container.winId())
                    except Exception:
                        embed_wid = None
                self._mirror.start(device_id, embed_wid=embed_wid)
                self._append_log(
                    f"[镜像] 启动请求: device_id={device_id}, embed_wid={embed_wid or 'None'}\n"
                )
            else:
                self._append_log("[GUI] 未找到可用设备，无法启动镜像\n")

    # ================================================================
    # 任务状态回调
    # ================================================================

    def _on_task_state_changed(self, state: TaskState):
        self._update_button_states(state)
        text, color = STATE_DISPLAY.get(state, ("未知", "#8b949e"))
        self._lbl_task_state.setText(
            f"<span style='color:#484f58'>状态:</span> "
            f"<span style='color:{color}'>{text}</span>"
        )

        # 接管/暂停态显示操作提示
        if state == TaskState.PAUSED:
            self._takeover_banner.show()
            self._btn_resume_exec.show()
        else:
            self._takeover_banner.hide()
            self._btn_resume_exec.hide()

    def _update_button_states(self, state: TaskState):
        running_states = {TaskState.RUNNING, TaskState.STARTING, TaskState.PAUSED}
        idle_states = {TaskState.IDLE, TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED}

        self._btn_start.setEnabled(state in idle_states)
        self._btn_stop.setEnabled(state in running_states or state == TaskState.STOPPING)
        self._btn_pause.setEnabled(state in {TaskState.RUNNING, TaskState.PAUSED})
        self._btn_takeover.setEnabled(state == TaskState.RUNNING)

        if state == TaskState.PAUSED:
            self._btn_pause.setText("恢复")
        else:
            self._btn_pause.setText("暂停")

    def _on_log_line(self, line: str):
        self._append_log(line)

    def _append_log(self, line: str):
        self._log_view.moveCursor(QTextCursor.End)
        self._log_view.insertPlainText(line)
        self._log_view.moveCursor(QTextCursor.End)

    def _on_event_added(self, evt: dict):
        item = QListWidgetItem(
            f"[{evt['time_str']}] {evt['message']}"
        )
        color_map = {
            "task_complete": "#3fb950",
            "task_failed":   "#f85149",
            "error":         "#f85149",
            "takeover_request": "#e3b341",
            "user_pause":    "#e3b341",
            "stuck_detected":"#f0883e",
        }
        color = color_map.get(evt["type"])
        if color:
            item.setForeground(QColor(color))
        self._event_list.insertItem(0, item)

    def _on_task_finished(self, record):
        state = record.state
        text, color = STATE_DISPLAY.get(state, ("未知", "#8b949e"))
        summary = (
            f"任务：{record.task_text[:60]}\n"
            f"状态：{text}  |  耗时：{record.duration_str}  |  "
            f"设备：{record.device_id or '—'}  |  模型：{record.model or '—'}"
        )
        if record.error_summary:
            summary += f"\n错误：{record.error_summary[:120]}"
        self._result_lbl.setStyleSheet(
            f"background:#161b22; border:1px solid {color}40;"
            f"border-radius:4px; padding:8px; font-size:12px; color:{color}; margin-top:6px;"
        )
        self._result_lbl.setText(summary)

    # ================================================================
    # 设备回调
    # ================================================================

    def _on_devices_changed(self, devices):
        if not devices:
            self._device_info_lbl.setText("未连接任何设备")
            self._update_device_status("未连接", "#f85149")
            return

        current = self._device.selected_device if self._device else None
        if current:
            current_ids = {d.device_id for d in devices}
            if current.device_id in current_ids:
                return

        # 尝试自动选择 AGENTS.md 中指定的设备
        preferred_id = ""
        if self._config:
            preferred_id = self._config.get("OPEN_AUTOGLM_DEVICE_ID")
        if preferred_id:
            for d in devices:
                if d.device_id == preferred_id:
                    if self._device:
                        self._device.select_device(d.device_id)
                    return
        # 否则自动选第一个 CONNECTED 设备
        for d in devices:
            from gui.services.device_service import DeviceStatus
            if d.status == DeviceStatus.CONNECTED:
                if self._device:
                    self._device.select_device(d.device_id)
                return

    def _on_device_selected(self, device_info):
        from gui.services.device_service import DeviceStatus
        if device_info is None:
            self._device_info_lbl.setText("未选择设备")
            self._update_device_status("未选择", "#8b949e")
            return
        lines = [f"<b>{device_info.display_name}</b>"]
        conn_type = {"usb": "USB", "wifi": "WiFi"}.get(device_info.connection_type, "未知")
        lines.append(f"连接方式: {conn_type}")
        kbd = "已安装" if device_info.adb_keyboard_installed else "未安装"
        lines.append(f"ADB Keyboard: {kbd}")
        self._device_info_lbl.setText("<br>".join(lines))
        self._device_info_lbl.setStyleSheet("color:#c9d1d9; font-size:12px; padding:4px;")

        if device_info.status == DeviceStatus.CONNECTED:
            self._update_device_status(device_info.device_id, "#3fb950")
        else:
            self._update_device_status(f"{device_info.device_id} ({device_info.status.value})", "#e3b341")

    def _update_device_status(self, text: str, color: str):
        self._lbl_device_status.setText(
            f"<span style='color:#484f58'>设备:</span> "
            f"<span style='color:{color}'>{text}</span>"
        )

    # ================================================================
    # 镜像回调
    # ================================================================

    def _on_mirror_state_changed(self, state: MirrorState):
        text, color = MIRROR_STATE_DISPLAY.get(state, ("未知", "#8b949e"))
        self._lbl_mirror_status.setText(
            f"<span style='color:#484f58'>镜像:</span> "
            f"<span style='color:{color}'>{text}</span>"
        )
        if state == MirrorState.RUNNING:
            self._btn_mirror_toggle.setText("停止镜像")
        else:
            self._btn_mirror_toggle.setText("启动镜像")

    def _on_mirror_mode_changed(self, mode: MirrorMode):
        self._mirror_embedded = mode == MirrorMode.SCRCPY_EMBEDDED
        if mode == MirrorMode.ADB_SCREENSHOT:
            self._mirror_placeholder.hide()
            self._mirror_label.show()
        elif mode == MirrorMode.NONE:
            self._mirror_label.hide()
            self._mirror_placeholder.show()
            self._mirror_placeholder.setText("镜像已停止")
        elif mode == MirrorMode.SCRCPY_EXTERNAL:
            self._mirror_label.hide()
            self._mirror_placeholder.show()
            self._mirror_placeholder.setText("scrcpy 镜像运行中（独立窗口）\n\n内嵌模式不可用时使用此模式")
        elif mode == MirrorMode.SCRCPY_EMBEDDED:
            self._mirror_label.hide()
            self._mirror_placeholder.hide()
            self._sync_embedded_mirror_geometry()

    def _on_mirror_frame(self, pixmap: QPixmap):
        """ADB 截图降级模式下收到帧"""
        if not self._mirror_label.isVisible():
            return
        w = self._mirror_label.width()
        h = self._mirror_label.height()
        scaled = pixmap.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._mirror_label.setPixmap(scaled)

    def _on_mirror_error(self, msg: str):
        self._append_log(f"[镜像] {msg}\n")

    def _on_mirror_window_created(self, hwnd: int):
        self._append_log(f"[镜像] scrcpy 窗口已嵌入，HWND={hwnd}\n")
        QTimer.singleShot(0, self._sync_embedded_mirror_geometry)

    def _sync_embedded_mirror_geometry(self):
        if not (self._mirror and self._mirror_container and self._mirror_embedded):
            return
        rect = self._mirror_container.contentsRect()
        if rect.width() <= 0 or rect.height() <= 0:
            return
        self._mirror.resize_scrcpy_window(rect.x(), rect.y(), rect.width(), rect.height())

    def eventFilter(self, watched, event):
        if watched is self._mirror_container and event.type() in (QEvent.Resize, QEvent.Show):
            QTimer.singleShot(0, self._sync_embedded_mirror_geometry)
        return super().eventFilter(watched, event)

    # ================================================================
    # 状态条刷新
    # ================================================================

    def _refresh_status_bar(self):
        if self._config:
            model = self._config.get("OPEN_AUTOGLM_MODEL") or "—"
            self._lbl_model_info.setText(
                f"<span style='color:#484f58'>模型:</span> "
                f"<span style='color:#8b949e'>{model[:30]}</span>"
            )

    def on_page_activated(self):
        """页面激活时刷新状态"""
        self._refresh_status_bar()

    # ================================================================
    # 按钮样式
    # ================================================================

    @staticmethod
    def _btn_primary_style() -> str:
        return """
            QPushButton {
                background:#1f6feb; border:1px solid #388bfd40;
                border-radius:6px; color:#fff; padding:6px 14px;
            }
            QPushButton:hover { background:#388bfd; }
            QPushButton:disabled { background:#1f2535; color:#484f58; border-color:#21262d; }
        """

    @staticmethod
    def _btn_danger_style() -> str:
        return """
            QPushButton {
                background:#21262d; border:1px solid #f8514940;
                border-radius:6px; color:#f85149; padding:6px 14px;
            }
            QPushButton:hover { background:#3d1a1a; border-color:#f85149; }
            QPushButton:disabled { background:#161b22; color:#484f58; border-color:#21262d; }
        """

    @staticmethod
    def _btn_warning_style() -> str:
        return """
            QPushButton {
                background:#21262d; border:1px solid #e3b34140;
                border-radius:6px; color:#e3b341; padding:6px 14px;
            }
            QPushButton:hover { background:#3d3200; border-color:#e3b341; }
            QPushButton:disabled { background:#161b22; color:#484f58; border-color:#21262d; }
        """
