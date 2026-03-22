# -*- coding: utf-8 -*-
"""
工作台页面 - 首版核心页面。

布局：
  顶部工具区（任务输入 + 控制按钮 + 状态条）
  ├── 主区A：设备与镜像（左侧）
  └── 主区B：日志与事件（右侧）
"""

import os
import time

from PySide6.QtCore import QEvent, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QFont, QPixmap, QTextCursor
from gui.widgets.mirror_label import MirrorLabel
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedLayout,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from gui.services.readiness_service import (
    collect_blocking_labels,
    run_readiness_checks,
    summarize_readiness,
)
from gui.services.task_service import TaskState
from gui.services.mirror_service import MirrorMode, MirrorState
from gui.theme.tokens import ThemeTokens
from gui.theme.themes import resolve_theme_tokens
from gui.theme.styles.buttons import (
    btn_primary,
    btn_danger,
    btn_warning,
    btn_success,
    btn_subtle,
)
from gui.theme.styles.lists import list_event
from gui.theme.styles.logs import log_console


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


class _ReadinessWorker(QThread):
    """后台执行启动环境检查，避免阻塞工作台页面。"""

    results_ready = Signal(object)  # list[ReadinessCheckResult]

    def __init__(self, config_service=None, device_id: str = ""):
        super().__init__()
        self._config = config_service
        self._device_id = device_id
        self._stop_requested = False

    def request_stop(self):
        self._stop_requested = True

    def run(self):
        results = run_readiness_checks(self._config, device_id=self._device_id)
        if self._stop_requested:
            return
        self.results_ready.emit(results)


class DashboardPage(QWidget):
    """工作台页面"""

    def __init__(self, services: dict, parent=None):
        super().__init__(parent)
        self._services = services
        self._task = services.get("task")
        self._device = services.get("device")
        self._mirror = services.get("mirror")
        self._config = services.get("config")
        self._theme_mode = "dark"
        self._theme_tokens = resolve_theme_tokens(self._theme_mode)
        self._theme_vars = self._theme_tokens.to_legacy_dict()
        self._last_task_status = ("空闲", "#8b949e")
        self._last_device_status = ("未检测", "#8b949e")
        self._last_mirror_status = ("未启动", "#8b949e")
        self._last_result_color = ""
        self._last_readiness_state = ("正在检查启动环境...", "info")
        self._last_readiness_tooltip = "启动环境检查尚未开始"
        self._readiness_results = []
        self._readiness_summary = None
        self._readiness_worker = None
        self._pending_readiness_refresh = False
        self._last_readiness_check_at = 0.0

        self._mirror_label: MirrorLabel = None   # ADB 截图降级时的图片显示
        self._mirror_container: QWidget = None
        self._mirror_host: QWidget = None        # scrcpy 内嵌专用原生宿主控件
        self._mirror_stack: QStackedLayout = None
        self._mirror_embedded = False
        self._last_mirror_geometry_debug = None
        self._mirror_debug_enabled = self._is_truthy(
            os.environ.get("OPEN_AUTOGLM_GUI_MIRROR_DEBUG", "")
        )
        self._readiness_refresh_timer = QTimer(self)
        self._readiness_refresh_timer.setSingleShot(True)
        self._readiness_refresh_timer.timeout.connect(self._run_readiness_check)

        self._build_ui()
        self._apply_action_button_styles()
        self._connect_signals()
        self._update_button_states(TaskState.IDLE)
        self._refresh_status_bar()
        # 初始化时同步已选中设备的 device_id 到镜像控件
        if self._device and self._device.selected_device and self._mirror_label:
            self._mirror_label.set_device_id(self._device.selected_device.device_id)
        QTimer.singleShot(500, lambda: self._schedule_readiness_check(0))

    def _current_device_id(self) -> str:
        if self._device and self._device.selected_device:
            return (self._device.selected_device.device_id or "").strip()

        if self._config:
            configured = (self._config.get("OPEN_AUTOGLM_DEVICE_ID") or "").strip()
            if configured:
                return configured

        if self._device and self._device.devices:
            from gui.services.device_service import DeviceStatus

            for info in self._device.devices:
                if info.status == DeviceStatus.CONNECTED:
                    return (info.device_id or "").strip()

        return ""

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

        # 低侵入环境摘要条
        root.addWidget(self._build_readiness_bar())

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
        self._toolbar = bar
        bar.setProperty("role", "toolbar")
        bar.setFixedHeight(60)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(10)

        # 渠道切换下拉框
        self._channel_combo = QComboBox()
        self._channel_combo.setFixedHeight(32)
        self._channel_combo.setMinimumWidth(220)
        self._channel_combo.setMaximumWidth(280)
        self._populate_channel_combo()
        self._channel_combo.currentIndexChanged.connect(self._on_channel_changed)
        layout.addWidget(self._channel_combo)

        # 任务输入框
        self._task_input = QLineEdit()
        self._task_input.setPlaceholderText("输入任务描述，例如：打开微信发消息给张三...")
        self._task_input.setMinimumWidth(300)
        self._task_input.returnPressed.connect(self._on_start)
        layout.addWidget(self._task_input, 1)

        # 开始按钮
        self._btn_start = QPushButton("开始")
        self._btn_start.setFixedWidth(72)
        self._btn_start.setProperty("variant", "primary")
        self._btn_start.clicked.connect(self._on_start)
        layout.addWidget(self._btn_start)

        # 停止按钮
        self._btn_stop = QPushButton("停止")
        self._btn_stop.setFixedWidth(72)
        self._btn_stop.setProperty("variant", "danger")
        self._btn_stop.clicked.connect(self._on_stop)
        layout.addWidget(self._btn_stop)

        # 暂停/恢复按钮
        self._btn_pause = QPushButton("暂停")
        self._btn_pause.setFixedWidth(72)
        self._btn_pause.setProperty("variant", "warning")
        self._btn_pause.clicked.connect(self._on_pause_resume)
        layout.addWidget(self._btn_pause)

        # 接管按钮
        self._btn_takeover = QPushButton("接管")
        self._btn_takeover.setFixedWidth(72)
        self._btn_takeover.setProperty("variant", "warning")
        self._btn_takeover.clicked.connect(self._on_takeover)
        layout.addWidget(self._btn_takeover)

        return bar

    # ----------------------------------------------------------------
    # 状态条
    # ----------------------------------------------------------------

    def _build_status_bar(self) -> QWidget:
        bar = QWidget()
        self._status_bar = bar
        bar.setProperty("role", "statusBar")
        bar.setFixedHeight(32)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(20)

        self._lbl_task_state = self._make_status_chip("状态", "空闲", "#8b949e")
        self._lbl_device_status = self._make_status_chip("设备", "未检测", "#8b949e")
        self._lbl_mirror_status = self._make_status_chip("镜像", "未启动", "#8b949e")

        layout.addWidget(self._lbl_task_state)
        layout.addWidget(self._make_sep())
        layout.addWidget(self._lbl_device_status)
        layout.addWidget(self._make_sep())
        layout.addWidget(self._lbl_mirror_status)
        layout.addStretch(1)

        # 镜像控制按钮
        self._btn_mirror_toggle = QPushButton("启动镜像")
        self._btn_mirror_toggle.setFixedHeight(22)
        self._btn_mirror_toggle.setProperty("variant", "subtle")
        self._btn_mirror_toggle.clicked.connect(self._on_mirror_toggle)
        layout.addWidget(self._btn_mirror_toggle)

        return bar

    def _make_status_chip(self, key: str, value: str, color: str) -> QLabel:
        lbl = QLabel(self._format_status_chip(key, value, color))
        lbl.setStyleSheet("font-size:12px;")
        return lbl

    def _make_sep(self) -> QFrame:
        sep = QFrame()
        sep.setProperty("role", "separator")
        sep.setFrameShape(QFrame.VLine)
        sep.setFixedHeight(16)
        sep.setStyleSheet("")
        return sep

    def _build_readiness_bar(self) -> QWidget:
        bar = QFrame()
        self._readiness_bar = bar
        bar.setObjectName("DashboardReadinessBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(10)

        self._readiness_text_lbl = QLabel(self._last_readiness_state[0])
        self._readiness_text_lbl.setObjectName("DashboardReadinessText")
        self._readiness_text_lbl.setWordWrap(True)
        layout.addWidget(self._readiness_text_lbl, 1)

        self._btn_open_diag = QPushButton("查看诊断")
        self._btn_open_diag.setProperty("variant", "subtle")
        self._btn_open_diag.setFixedHeight(28)
        self._btn_open_diag.clicked.connect(self._open_diagnostics_page)
        layout.addWidget(self._btn_open_diag)

        self._btn_readiness_refresh = QPushButton("重新检查")
        self._btn_readiness_refresh.setProperty("variant", "subtle")
        self._btn_readiness_refresh.setFixedHeight(28)
        self._btn_readiness_refresh.clicked.connect(lambda: self._schedule_readiness_check(0))
        layout.addWidget(self._btn_readiness_refresh)

        self._set_readiness_state(*self._last_readiness_state, tooltip=self._last_readiness_tooltip)
        return bar

    def _readiness_bar_style(self, semantic: str) -> str:
        v = self._theme_vars or {}
        if semantic == "success":
            bg = v.get("success_bg", "#0f2d1a")
            border = v.get("success_border", "#3fb95040")
            text = v.get("success", "#3fb950")
        elif semantic == "error":
            bg = v.get("danger_bg", "#3d1a1a")
            border = v.get("danger_border", "#8f2d2b")
            text = v.get("danger", "#f85149")
        elif semantic == "warning":
            bg = v.get("warning_bg", "#3d2800")
            border = v.get("warning_border", "#6e4800")
            text = v.get("warning", "#e3b341")
        else:
            bg = v.get("bg_secondary", "#161b22")
            border = v.get("border", "#30363d")
            text = v.get("text_secondary", "#8b949e")
        return (
            f"QFrame#DashboardReadinessBar {{ background:{bg}; border-bottom:1px solid {border}; }}"
            f"QLabel#DashboardReadinessText {{ color:{text}; font-size:12px; }}"
        )

    def _set_readiness_state(self, text: str, semantic: str = "info", tooltip: str = ""):
        self._last_readiness_state = (text, semantic)
        self._last_readiness_tooltip = tooltip or text
        if hasattr(self, "_readiness_text_lbl"):
            self._readiness_text_lbl.setText(text)
            self._readiness_text_lbl.setToolTip(self._last_readiness_tooltip)
        if hasattr(self, "_readiness_bar"):
            self._readiness_bar.setToolTip(self._last_readiness_tooltip)
            self._readiness_bar.setStyleSheet(self._readiness_bar_style(semantic))

    def _schedule_readiness_check(self, delay_ms: int = 300):
        if self._readiness_worker and self._readiness_worker.isRunning():
            self._pending_readiness_refresh = True
            return
        self._readiness_refresh_timer.start(max(0, delay_ms))

    def _run_readiness_check(self):
        if self._readiness_worker and self._readiness_worker.isRunning():
            self._pending_readiness_refresh = True
            return
        self._pending_readiness_refresh = False
        self._set_readiness_state("正在检查启动环境...", "info", "正在执行启动环境检查")
        if hasattr(self, "_btn_readiness_refresh"):
            self._btn_readiness_refresh.setEnabled(False)
        device_id = self._current_device_id()
        self._readiness_worker = _ReadinessWorker(self._config, device_id=device_id)
        self._readiness_worker.results_ready.connect(self._on_readiness_results)
        self._readiness_worker.finished.connect(self._on_readiness_worker_finished)
        self._readiness_worker.start()

    def _on_readiness_results(self, results):
        self._readiness_results = results or []
        self._last_readiness_check_at = time.monotonic()
        if not self._readiness_results:
            self._readiness_summary = None
            self._set_readiness_state("启动环境检查未返回结果", "warning")
            return

        self._readiness_summary = summarize_readiness(self._readiness_results)
        summary_text = f"{self._readiness_summary.title} · {self._readiness_summary.detail}"
        tooltip = summary_text
        if self._readiness_summary.action_hint:
            tooltip += f"\n{self._readiness_summary.action_hint}"
        self._set_readiness_state(summary_text, self._readiness_summary.semantic, tooltip)

    def _on_readiness_worker_finished(self):
        if hasattr(self, "_btn_readiness_refresh"):
            self._btn_readiness_refresh.setEnabled(True)
        if self._readiness_worker:
            self._readiness_worker.deleteLater()
            self._readiness_worker = None
        if self._pending_readiness_refresh:
            self._pending_readiness_refresh = False
            self._schedule_readiness_check(350)

    def _open_diagnostics_page(self):
        navigator = self._services.get("navigate_to_page")
        if callable(navigator):
            navigator("diag")
            return

        main_window = self.window()
        if hasattr(main_window, "switch_page"):
            main_window.switch_page("diag")
            return
        if hasattr(main_window, "_nav_buttons") and "diag" in getattr(main_window, "_nav_buttons", {}):
            main_window._nav_buttons["diag"].setChecked(True)
        if hasattr(main_window, "_switch_page"):
            main_window._switch_page("diag")

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
        self._mirror_stack = QStackedLayout(self._mirror_container)
        self._mirror_stack.setContentsMargins(0, 0, 0, 0)

        # 占位标签（scrcpy 外部窗口模式或未启动时）
        self._mirror_placeholder = QLabel("镜像未启动\n\n点击状态栏「启动镜像」按钮\n或使用 scrcpy 外部窗口")
        self._mirror_placeholder.setAlignment(Qt.AlignCenter)
        self._mirror_placeholder.setStyleSheet("""
            color:#484f58; font-size:13px; line-height:1.8;
        """)
        self._mirror_stack.addWidget(self._mirror_placeholder)

        # ADB 截图降级时的图片显示（MirrorLabel 自带自适应缩放和鼠标 tap 控制）
        self._mirror_label = MirrorLabel()
        self._mirror_stack.addWidget(self._mirror_label)

        # scrcpy 内嵌专用原生宿主控件，避免直接挂到带 Qt 布局的容器上
        self._mirror_host = QWidget()
        self._mirror_host.setStyleSheet("background:#0a0e17;")
        self._mirror_host.setAttribute(Qt.WA_NativeWindow, True)
        self._mirror_host.installEventFilter(self)
        self._mirror_stack.addWidget(self._mirror_host)
        self._mirror_stack.setCurrentWidget(self._mirror_placeholder)

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
        self._btn_resume_exec.setProperty("variant", "primary")
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

    def _format_status_chip(self, key: str, value: str, color: str) -> str:
        meta_color = self._theme_vars.get("text_muted", "#66778d")
        return (
            f"<span style='color:{meta_color}'>{key}:</span> "
            f"<span style='color:{color}'>{value}</span>"
        )

    def _set_task_status(self, text: str, color: str):
        self._last_task_status = (text, color)
        if hasattr(self, "_lbl_task_state"):
            self._lbl_task_state.setText(self._format_status_chip("状态", text, color))

    def _set_device_status(self, text: str, color: str):
        self._last_device_status = (text, color)
        if hasattr(self, "_lbl_device_status"):
            self._lbl_device_status.setText(self._format_status_chip("设备", text, color))

    def _set_mirror_status(self, text: str, color: str):
        self._last_mirror_status = (text, color)
        if hasattr(self, "_lbl_mirror_status"):
            self._lbl_mirror_status.setText(self._format_status_chip("镜像", text, color))

    def _summary_style(self, color: str = "") -> str:
        v = self._theme_vars or {}
        summary_color = color or v.get("text_secondary", "#526273")
        border_color = f"{summary_color}40" if summary_color.startswith("#") else v.get("border", "#d5deea")
        return (
            f"background:{v.get('bg_secondary', '#ffffff')}; "
            f"border:1px solid {border_color}; border-radius:8px; padding:8px; "
            f"font-size:12px; color:{summary_color}; margin-top:6px;"
        )

    def _channel_combo_style(self, theme_vars: dict) -> str:
        v = theme_vars or {}
        return f"""
            QComboBox {{
                background:{v.get('bg_secondary', '#161b22')};
                border:1px solid {v.get('border', '#30363d')};
                border-radius:8px;
                color:{v.get('text_primary', '#c9d1d9')};
                padding:0 10px;
                font-size:12px;
            }}
            QComboBox:hover {{ border-color:{v.get('accent', '#4f8cff')}; }}
            QComboBox::drop-down {{
                border:none;
                width:24px;
            }}
            QComboBox::down-arrow {{
                width:0;
                height:0;
                border-left:5px solid transparent;
                border-right:5px solid transparent;
                border-top:6px solid {v.get('text_secondary', '#8b949e')};
                margin-right:8px;
            }}
            QComboBox QAbstractItemView {{
                background:{v.get('bg_secondary', '#161b22')};
                border:1px solid {v.get('border', '#30363d')};
                selection-background-color:{v.get('selection_bg', '#264f78')};
                color:{v.get('text_primary', '#c9d1d9')};
                padding:2px;
                outline:none;
            }}
            QComboBox QAbstractItemView::item {{
                padding:4px 8px;
                min-height:24px;
            }}
        """

    def apply_theme_tokens(self, tokens: ThemeTokens) -> None:
        """
        新版主题接口 - 由 PageThemeAdapter / ThemeManager 驱动。
        缓存 tokens 后按三段式刷新。
        """
        self._theme_tokens = tokens
        self._theme_mode = tokens.mode
        self._theme_vars = tokens.to_legacy_dict()
        self.refresh_theme_surfaces()
        self.refresh_theme_states()

    def refresh_theme_surfaces(self) -> None:
        """刷新静态外观：工具栏、状态栏、列表、日志区、镜像区背景。"""
        if self._theme_tokens is None:
            return
        v = self._theme_vars

        # 工具栏与状态栏仍由全局 role 选择器控制容器外观；
        # 顶部动作按钮改为页面内显式样式，绕过真实窗口里异常的全局 variant 链路。
        for widget, role in (
            (getattr(self, "_toolbar", None), "toolbar"),
            (getattr(self, "_status_bar", None), "statusBar"),
        ):
            if widget:
                widget.setProperty("role", role)
                widget.setStyleSheet("")
                widget.style().unpolish(widget)
                widget.style().polish(widget)
                widget.update()

        if hasattr(self, "_mirror_container"):
            self._mirror_container.setStyleSheet(
                f"background:{v.get('bg_console', '#0a0f18')}; "
                f"border:1px solid {v.get('border', '#30363d')}; border-radius:8px;"
            )
        if hasattr(self, "_mirror_host"):
            self._mirror_host.setStyleSheet(
                f"background:{v.get('bg_console', '#0a0f18')}; border-radius:8px;"
            )
        if hasattr(self, "_mirror_placeholder"):
            self._mirror_placeholder.setStyleSheet(
                f"color:{v.get('text_muted', '#66778d')}; font-size:13px; line-height:1.8;"
            )
        if hasattr(self, "_device_info_lbl"):
            self._device_info_lbl.setStyleSheet(
                f"color:{v.get('text_secondary', '#526273')}; font-size:12px; padding:4px;"
            )
        if hasattr(self, "_readiness_bar"):
            self._readiness_bar.setStyleSheet(self._readiness_bar_style(self._last_readiness_state[1]))
        if hasattr(self, "_takeover_banner"):
            self._takeover_banner.setStyleSheet(
                f"background:{v.get('warning_bg', '#3d2800')}; color:{v.get('warning', '#e3b341')}; "
                f"font-size:12px; border:1px solid {v.get('warning_border', '#6e4800')}; "
                f"border-radius:8px; padding:6px;"
            )
        if hasattr(self, "_log_view"):
            self._log_view.setStyleSheet(log_console(self._theme_tokens))
        if hasattr(self, "_event_list"):
            self._event_list.setStyleSheet(list_event(self._theme_tokens))
        if hasattr(self, "_result_lbl"):
            self._result_lbl.setStyleSheet(
                self._summary_style(self._last_result_color or v.get("text_secondary", "#526273"))
            )

        self._set_task_status(*self._last_task_status)
        self._set_device_status(*self._last_device_status)
        self._set_mirror_status(*self._last_mirror_status)

    def refresh_theme_states(self) -> None:
        """刷新动态状态：按钮样式、渠道下拉框。"""
        if self._theme_tokens is None:
            return
        v = self._theme_vars
        self._apply_action_button_styles()
        if hasattr(self, "_channel_combo"):
            self._channel_combo.setStyleSheet(self._channel_combo_style(v))

    def on_theme_changed(self, theme: str, theme_vars: dict):
        """[兼容] 旧版接口，由 PageThemeAdapter 在未实现新接口时调用。"""
        self._theme_mode = theme
        if getattr(self, "_theme_tokens", None) is None or self._theme_tokens.mode != theme:
            self._theme_tokens = resolve_theme_tokens(theme)
        self._theme_vars = theme_vars or self._theme_tokens.to_legacy_dict()
        self.refresh_theme_surfaces()
        self.refresh_theme_states()

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

        # 配置变化时同步渠道下拉框（例如设置页保存后）
        if self._config:
            self._config.config_changed.connect(self._sync_channel_combo)
            self._config.config_changed.connect(lambda: self._schedule_readiness_check(300))

    # ================================================================
    # 渠道切换
    # ================================================================

    def _populate_channel_combo(self):
        """填充渠道下拉框选项（仅填充，不触发切换逻辑）"""
        if not self._config:
            return
        self._channel_combo.blockSignals(True)
        self._channel_combo.clear()
        presets = self._config.CHANNEL_PRESETS
        for preset in presets:
            self._channel_combo.addItem(preset["name"], userData=preset["id"])
        self._channel_combo.blockSignals(False)

    def _sync_channel_combo(self):
        """config_changed 信号触发：同步下拉框并刷新 tooltip。"""
        self._refresh_status_bar()

    def _on_channel_changed(self, index: int):
        """用户切换渠道时触发"""
        if not self._config or index < 0:
            return
        channel_id = self._channel_combo.itemData(index)
        if not channel_id:
            return

        # 任务运行中禁止切换渠道
        if self._task:
            idle_states = {
                TaskState.IDLE, TaskState.COMPLETED,
                TaskState.FAILED, TaskState.CANCELLED,
            }
            if self._task.state not in idle_states:
                QMessageBox.warning(
                    self, "无法切换渠道",
                    "任务运行中不能切换模型渠道，请先停止当前任务。"
                )
                # 回滚下拉框选中项
                self._sync_channel_combo()
                return

        ok = self._config.set_active_channel(channel_id)
        if not ok:
            QMessageBox.warning(self, "切换失败", f"渠道切换失败: {channel_id}")
            self._sync_channel_combo()
            return

        # 刷新状态条模型显示（config_changed 信号已连接 _sync_channel_combo，
        # 但此处直接调用以确保及时刷新）
        self._refresh_status_bar()
        preset = next(
            (p for p in self._config.CHANNEL_PRESETS if p["id"] == channel_id), None
        )
        if preset and channel_id != "custom":
            thirdparty_hint = "(第三方提示词)" if preset["use_thirdparty"] else "(原生AutoGLM)"
            resolved_url = self._config.get_preset_url(preset)
            resolved_model = self._config.get_preset_model(preset)
            self._append_log(
                f"[渠道] 已切换至: {preset['name']} {thirdparty_hint}\n"
                f"[渠道] Base URL: {resolved_url}\n"
                f"[渠道] 模型: {resolved_model}\n"
            )
        else:
            self._append_log("[渠道] 已切换至自定义模式（保留当前 URL/模型设置）\n")

    # ================================================================
    # 按钮回调
    # ================================================================

    def _on_start(self):
        text = self._task_input.text().strip()
        if not text:
            self._task_input.setFocus()
            return

        if not self._readiness_results:
            self._set_readiness_state(
                "正在检查启动环境，请稍候片刻再开始任务。",
                "info",
                "启动环境检查仍在进行或尚未开始，请稍后重试。",
            )
            self._schedule_readiness_check(0)
            return

        blocking_labels = collect_blocking_labels(self._readiness_results)
        if blocking_labels:
            warning_text = f"启动前仍有关键项未就绪：{blocking_labels}"
            self._set_readiness_state(
                warning_text,
                "error",
                warning_text + "\n建议先查看诊断页并完成必要配置。",
            )
            msg = QMessageBox(self)
            msg.setWindowTitle("启动前检查未通过")
            msg.setText(f"当前仍有关键项未就绪：{blocking_labels}")
            msg.setInformativeText("建议先查看“诊断”页详情，补齐设备连接、API 配置或依赖项后再开始任务。")
            btn_diag = msg.addButton("查看诊断", QMessageBox.ActionRole)
            msg.addButton("取消", QMessageBox.RejectRole)
            msg.exec()
            if msg.clickedButton() == btn_diag:
                self._open_diagnostics_page()
            return

        if self._task:
            # 清空上次日志
            self._log_view.clear()
            self._event_list.clear()
            self._last_result_color = ""
            self._result_lbl.setText("")
            self._result_lbl.setStyleSheet(
                self._summary_style(self._theme_vars.get("text_secondary", "#526273"))
            )
            self._task.start_task(text, device_id_override=self._current_device_id())

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
            device_id = self._current_device_id()
            if device_id:
                embed_wid = None
                embed_container_size = None
                if self._mirror_host and self._mirror_container and self._mirror_container.isVisible():
                    try:
                        if self._mirror_stack:
                            self._mirror_stack.setCurrentWidget(self._mirror_host)
                        self._mirror_host.show()
                        host_rect = self._mirror_host.contentsRect()
                        if host_rect.width() > 0 and host_rect.height() > 0:
                            embed_container_size = (host_rect.width(), host_rect.height())
                        else:
                            container_rect = self._mirror_container.contentsRect()
                            if container_rect.width() > 0 and container_rect.height() > 0:
                                embed_container_size = (container_rect.width(), container_rect.height())
                        embed_wid = int(self._mirror_host.winId())
                    except Exception:
                        embed_wid = None
                        embed_container_size = None
                self._mirror.start(
                    device_id,
                    embed_wid=embed_wid,
                    embed_container_size=embed_container_size,
                )
                self._append_mirror_debug_log(
                    f"[镜像] 启动请求: device_id={device_id}, embed_wid={embed_wid or 'None'}, "
                    f"embed_size={embed_container_size or 'None'}\n"
                )
            else:
                self._append_log("[GUI] 未找到可用设备，无法启动镜像\n")

    # ================================================================
    # 任务状态回调
    # ================================================================

    def _on_task_state_changed(self, state: TaskState):
        self._update_button_states(state)
        text, color = STATE_DISPLAY.get(state, ("未知", "#8b949e"))
        self._set_task_status(text, color)

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
            self._btn_pause.setProperty("variant", "success")
        else:
            self._btn_pause.setText("暂停")
            self._btn_pause.setProperty("variant", "warning")
        self._apply_action_button_styles(task_state=state)

    def _on_log_line(self, line: str):
        self._append_log(line)

    def _append_log(self, line: str):
        self._log_view.moveCursor(QTextCursor.End)
        self._log_view.insertPlainText(line)
        self._log_view.moveCursor(QTextCursor.End)

    @staticmethod
    def _is_truthy(value: str) -> bool:
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def _append_mirror_debug_log(self, line: str):
        if self._mirror_debug_enabled:
            self._append_log(line)

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
        self._last_result_color = color
        self._result_lbl.setStyleSheet(self._summary_style(color))
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
            # 清除镜像控件的设备绑定
            if self._mirror_label:
                self._mirror_label.set_device_id("")
            return
        # 更新镜像控件绑定的 ADB 设备 ID（用于鼠标 tap 转发）
        if self._mirror_label:
            self._mirror_label.set_device_id(device_info.device_id)
        lines = [f"<b>{device_info.display_name}</b>"]
        conn_type = {"usb": "USB", "wifi": "WiFi"}.get(device_info.connection_type, "未知")
        lines.append(f"连接方式: {conn_type}")
        kbd = device_info.adb_keyboard_status or (
            "ADB Keyboard 已启用" if device_info.adb_keyboard_enabled else "ADB Keyboard 未安装"
        )
        if kbd.startswith("ADB Keyboard "):
            kbd = kbd[len("ADB Keyboard "):]
        lines.append(f"ADB Keyboard: {kbd}")
        self._device_info_lbl.setText("<br>".join(lines))
        self._device_info_lbl.setStyleSheet("font-size:12px; padding:4px;")

        if device_info.status == DeviceStatus.CONNECTED:
            self._update_device_status(device_info.device_id, "#3fb950")
        else:
            self._update_device_status(f"{device_info.device_id} ({device_info.status.value})", "#e3b341")

        self._schedule_readiness_check(300)

    def _update_device_status(self, text: str, color: str):
        self._set_device_status(text, color)

    # ================================================================
    # 镜像回调
    # ================================================================

    def _on_mirror_state_changed(self, state: MirrorState):
        text, color = MIRROR_STATE_DISPLAY.get(state, ("未知", "#8b949e"))
        self._set_mirror_status(text, color)
        if state == MirrorState.RUNNING:
            self._btn_mirror_toggle.setText("停止镜像")
            self._btn_mirror_toggle.setProperty("variant", "danger")
        else:
            self._btn_mirror_toggle.setText("启动镜像")
            self._btn_mirror_toggle.setProperty("variant", "subtle")
        self._apply_action_button_styles(mirror_running=(state == MirrorState.RUNNING))

    def _on_mirror_mode_changed(self, mode: MirrorMode):
        self._mirror_embedded = mode == MirrorMode.SCRCPY_EMBEDDED
        if mode == MirrorMode.ADB_SCREENSHOT:
            if self._mirror_stack and self._mirror_label:
                self._mirror_stack.setCurrentWidget(self._mirror_label)
        elif mode == MirrorMode.NONE:
            self._mirror_placeholder.setText("镜像已停止")
            if self._mirror_stack and self._mirror_placeholder:
                self._mirror_stack.setCurrentWidget(self._mirror_placeholder)
        elif mode == MirrorMode.SCRCPY_EXTERNAL:
            self._mirror_placeholder.setText("scrcpy 镜像运行中（独立窗口）\n\n内嵌模式不可用时使用此模式")
            if self._mirror_stack and self._mirror_placeholder:
                self._mirror_stack.setCurrentWidget(self._mirror_placeholder)
        elif mode == MirrorMode.SCRCPY_EMBEDDED:
            if self._mirror_stack and self._mirror_host:
                self._mirror_stack.setCurrentWidget(self._mirror_host)
            self._sync_embedded_mirror_geometry()

    def _on_mirror_frame(self, pixmap: QPixmap):
        """ADB 截图降级模式下收到帧"""
        if not self._mirror_label.isVisible():
            return
        # MirrorLabel.set_raw_pixmap 内部负责自适应缩放（包括 resizeEvent 时重新缩放）
        self._mirror_label.set_raw_pixmap(pixmap)

    def _on_mirror_error(self, msg: str):
        self._append_log(f"[镜像] {msg}\n")

    def _on_mirror_window_created(self, hwnd: int):
        self._last_mirror_geometry_debug = None
        self._append_mirror_debug_log(f"[镜像] scrcpy 窗口已嵌入，HWND={hwnd}\n")
        QTimer.singleShot(0, self._sync_embedded_mirror_geometry)

    @staticmethod
    def _calc_aspect_fit_rect(
        container_w: int,
        container_h: int,
        content_w: int,
        content_h: int,
    ):
        if container_w <= 0 or container_h <= 0 or content_w <= 0 or content_h <= 0:
            return None
        scale = min(container_w / content_w, container_h / content_h)
        fit_w = max(1, int(content_w * scale))
        fit_h = max(1, int(content_h * scale))
        fit_x = (container_w - fit_w) // 2
        fit_y = (container_h - fit_h) // 2
        return fit_x, fit_y, fit_w, fit_h

    def _sync_embedded_mirror_geometry(self):
        host = self._mirror_host or self._mirror_container
        if not (self._mirror and host and self._mirror_embedded):
            return
        if not host.isVisible():
            return
        rect = host.contentsRect()
        if rect.width() <= 0 or rect.height() <= 0:
            return

        device_size = getattr(self._mirror, "device_screen_size", None)
        fit_rect = None
        if device_size:
            fit_rect = self._calc_aspect_fit_rect(
                rect.width(), rect.height(), device_size[0], device_size[1]
            )

        scale_factor = 1.0
        try:
            scale_factor = max(1.0, float(host.devicePixelRatioF()))
        except Exception:
            scale_factor = 1.0

        target_rect = fit_rect or (rect.x(), rect.y(), rect.width(), rect.height())
        native_rect = (
            int(round(target_rect[0] * scale_factor)),
            int(round(target_rect[1] * scale_factor)),
            max(1, int(round(target_rect[2] * scale_factor))),
            max(1, int(round(target_rect[3] * scale_factor))),
        )

        debug_signature = (
            rect.x(), rect.y(), rect.width(), rect.height(),
            device_size[0] if device_size else None,
            device_size[1] if device_size else None,
            *(fit_rect or (None, None, None, None)),
            round(scale_factor, 4),
            *native_rect,
        )
        if debug_signature != self._last_mirror_geometry_debug:
            self._last_mirror_geometry_debug = debug_signature
            if fit_rect:
                self._append_mirror_debug_log(
                    "[镜像][调试] 容器="
                    f"({rect.x()},{rect.y()},{rect.width()},{rect.height()})，"
                    f"设备={device_size[0]}x{device_size[1]}，"
                    f"DPR={scale_factor:.2f}，"
                    "按比例适配(fit)="
                    f"({fit_rect[0]},{fit_rect[1]},{fit_rect[2]},{fit_rect[3]})，"
                    "下发原生(native)="
                    f"({native_rect[0]},{native_rect[1]},{native_rect[2]},{native_rect[3]})\n"
                )
            else:
                self._append_mirror_debug_log(
                    "[镜像][调试] 尚未获取设备屏幕尺寸，"
                    f"DPR={scale_factor:.2f}，按容器 full rect 下发原生窗口="
                    f"({native_rect[0]},{native_rect[1]},{native_rect[2]},{native_rect[3]})\n"
                )

        self._mirror.resize_scrcpy_window(
            native_rect[0], native_rect[1], native_rect[2], native_rect[3]
        )

    def eventFilter(self, watched, event):
        if watched in (self._mirror_container, self._mirror_host) and event.type() in (QEvent.Resize, QEvent.Show):
            QTimer.singleShot(0, self._sync_embedded_mirror_geometry)
        return super().eventFilter(watched, event)

    # ================================================================
    # 状态条刷新
    # ================================================================

    def _refresh_status_bar(self):
        """同步渠道下拉框选中项，并在下拉框 tooltip 中显示当前 Base URL 和模型。"""
        if not self._config:
            return
        # 同步下拉框选中项（blockSignals 防止递归）
        active = self._config.get_active_channel()
        active_id = active["id"] if active else "custom"
        self._channel_combo.blockSignals(True)
        for i in range(self._channel_combo.count()):
            if self._channel_combo.itemData(i) == active_id:
                self._channel_combo.setCurrentIndex(i)
                break
        self._channel_combo.blockSignals(False)
        # 更新 tooltip 显示完整的 Base URL 和模型名
        base_url = self._config.get("OPEN_AUTOGLM_BASE_URL") or "—"
        model = self._config.get("OPEN_AUTOGLM_MODEL") or "—"
        is_thirdparty = self._config._is_truthy(
            self._config.get("OPEN_AUTOGLM_USE_THIRDPARTY_PROMPT", "false")
        )
        tp_hint = "[第三方提示词]" if is_thirdparty else "[原生AutoGLM]"
        # 渠道下拉框显示名加上动态模型名后缀（便于区分同渠道不同模型）
        active = self._config.get_active_channel()
        active_id = active["id"] if active else "custom"
        if active_id != "custom":
            display_model = model[:24] if len(model) > 24 else model
            self._channel_combo.setItemText(
                self._channel_combo.currentIndex(),
                f"{active['name']}  [{display_model}]"
            )
        else:
            # 自定义模式：显示当前实际模型名
            display_model = model[:24] if len(model) > 24 else model
            self._channel_combo.setItemText(
                self._channel_combo.currentIndex(),
                f"自定义  [{display_model}]" if display_model and display_model != "—" else "自定义"
            )
        self._channel_combo.setToolTip(
            f"Base URL: {base_url}\n模型: {model}\n{tp_hint}"
        )

    def on_page_activated(self):
        """页面激活时刷新状态"""
        self._sync_channel_combo()
        self._refresh_status_bar()
        if (not self._readiness_results) or (time.monotonic() - self._last_readiness_check_at > 45):
            self._schedule_readiness_check(0)

    def shutdown(self):
        if hasattr(self, "_readiness_refresh_timer"):
            self._readiness_refresh_timer.stop()
        if self._readiness_worker:
            if self._readiness_worker.isRunning():
                self._readiness_worker.request_stop()
                self._readiness_worker.wait(15000)
            if not self._readiness_worker.isRunning():
                self._readiness_worker.deleteLater()
                self._readiness_worker = None

    # ================================================================
    # 按钮样式
    # ================================================================

    def _apply_action_button_styles(self, task_state=None, mirror_running=None):
        if task_state is None:
            task_state = self._task.state if self._task else TaskState.IDLE
        if mirror_running is None:
            mirror_running = bool(self._mirror and self._mirror.is_running)

        btn_specs = (
            (getattr(self, "_btn_start", None), btn_primary(self._theme_tokens)),
            (getattr(self, "_btn_stop", None), btn_danger(self._theme_tokens)),
            (
                getattr(self, "_btn_pause", None),
                btn_success(self._theme_tokens) if task_state == TaskState.PAUSED else btn_warning(self._theme_tokens),
            ),
            (getattr(self, "_btn_takeover", None), btn_warning(self._theme_tokens)),
            (getattr(self, "_btn_resume_exec", None), btn_primary(self._theme_tokens)),
            (
                getattr(self, "_btn_mirror_toggle", None),
                btn_danger(self._theme_tokens, size="compact") if mirror_running else btn_subtle(self._theme_tokens, size="compact"),
            ),
            (getattr(self, "_btn_open_diag", None), btn_subtle(self._theme_tokens, size="compact")),
            (getattr(self, "_btn_readiness_refresh", None), btn_subtle(self._theme_tokens, size="compact")),
        )
        for btn, style in btn_specs:
            if btn:
                btn.setStyleSheet(style)
                btn.update()


