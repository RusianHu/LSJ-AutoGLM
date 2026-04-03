# -*- coding: utf-8 -*-
"""
工作台页面。

布局：
  顶部工具区（任务输入 + 控制按钮 + 状态条）
  └── 主工作区三列：
      - 左列：控制摘要 / 动作策略 / 渠道 / 就绪状态
      - 中列：日志与事件
      - 右列：大尺寸设备镜像
"""

import os
import time
import subprocess
import sys

from PySide6.QtCore import QEvent, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QFont, QPixmap, QTextCharFormat, QTextCursor
from gui.widgets.action_policy_dialog import ActionPolicyDialog, summarize_action_policy
from gui.widgets.mirror_label import MirrorLabel
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
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
    render_summary,
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


# 任务状态 -> 颜色（文字由 i18n 提供）
STATE_COLORS = {
    TaskState.IDLE:      "#8b949e",
    TaskState.STARTING:  "#e3b341",
    TaskState.RUNNING:   "#3fb950",
    TaskState.PAUSED:    "#e3b341",
    TaskState.STOPPING:  "#f85149",
    TaskState.COMPLETED: "#3fb950",
    TaskState.FAILED:    "#f85149",
    TaskState.CANCELLED: "#8b949e",
}

# 镜像状态 -> 颜色（文字由 i18n 提供）
MIRROR_STATE_COLORS = {
    MirrorState.IDLE:     "#8b949e",
    MirrorState.STARTING: "#e3b341",
    MirrorState.RUNNING:  "#3fb950",
    MirrorState.ERROR:    "#f85149",
    MirrorState.STOPPED:  "#8b949e",
}

# --- 向后兼容别名（防止导入方报错）---
STATE_DISPLAY = {k: (k.value, v) for k, v in STATE_COLORS.items()}
MIRROR_STATE_DISPLAY = {k: (k.value, v) for k, v in MIRROR_STATE_COLORS.items()}


class _MirrorClipboardPasteWorker(QThread):
    failed = Signal(str)
    succeeded = Signal(str)

    def __init__(self, device_id: str, text: str):
        super().__init__()
        self._device_id = device_id
        self._text = text or ""

    def run(self):
        try:
            if not self._device_id:
                self.failed.emit("当前未绑定设备，无法粘贴")
                return
            if not self._text:
                self.failed.emit("剪贴板为空，无法粘贴")
                return

            from phone_agent.adb.input import detect_and_set_adb_keyboard, restore_keyboard, type_text

            original_ime = detect_and_set_adb_keyboard(self._device_id)
            try:
                type_text(self._text, self._device_id)
            finally:
                if original_ime:
                    restore_keyboard(original_ime, self._device_id)
            self.succeeded.emit(self._text)
        except Exception as e:
            self.failed.emit(f"{e}；请先点击设备输入框聚焦后再重试")


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
        try:
            results = run_readiness_checks(
                self._config,
                device_id=self._device_id,
                should_stop=lambda: self._stop_requested,
            )
        except InterruptedError:
            return
        if self._stop_requested:
            return
        self.results_ready.emit(results)


class _MirrorPopupWindow(QWidget):
    """设备镜像顶层窗口。"""

    closing = Signal()

    def __init__(self):
        super().__init__(None)
        self._closing_in_progress = False
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowMinMaxButtonsHint
            | Qt.WindowCloseButtonHint
        )
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setMinimumSize(420, 760)
        self.resize(520, 920)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(0)

        self._container = QWidget(self)
        self._container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._stack = QStackedLayout(self._container)
        self._stack.setContentsMargins(0, 0, 0, 0)

        self._placeholder = QLabel()
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setWordWrap(True)
        self._stack.addWidget(self._placeholder)

        self._label = MirrorLabel()
        self._stack.addWidget(self._label)

        self._host = QWidget()
        self._host.setAttribute(Qt.WA_NativeWindow, True)
        self._stack.addWidget(self._host)
        self._stack.setCurrentWidget(self._placeholder)

        layout.addWidget(self._container, 1)

    def container_widget(self) -> QWidget:
        return self._container

    def host_widget(self) -> QWidget:
        return self._host

    def label_widget(self) -> MirrorLabel:
        return self._label

    def set_placeholder_text(self, text: str):
        self._placeholder.setText(text)

    def show_placeholder(self):
        self._stack.setCurrentWidget(self._placeholder)

    def show_label(self):
        self._stack.setCurrentWidget(self._label)

    def show_host(self):
        self._stack.setCurrentWidget(self._host)

    def show_frame(self, pixmap: QPixmap):
        self._label.set_raw_pixmap(pixmap)
        self.show_label()

    def is_closing(self) -> bool:
        return self._closing_in_progress

    def restore_and_show(self):
        self._closing_in_progress = False
        state = self.windowState()
        if state & Qt.WindowMinimized:
            self.setWindowState((state & ~Qt.WindowMinimized) | Qt.WindowActive)
        self.show()
        app = QApplication.instance()
        platform_name = (app.platformName() if app else "").lower()
        if platform_name not in {"offscreen", "minimal"}:
            self.raise_()
            self.activateWindow()

    def closeEvent(self, event):
        self._closing_in_progress = True
        self.closing.emit()
        super().closeEvent(event)


class DashboardPage(QWidget):
    """工作台页面"""

    def __init__(self, services: dict, parent=None):
        super().__init__(parent)
        self._services = services
        self._task = services.get("task")
        self._device = services.get("device")
        self._mirror = services.get("mirror")
        self._config = services.get("config")
        self._i18n = services.get("i18n")  # I18nManager
        self._theme_mode = "dark"
        self._theme_tokens = resolve_theme_tokens(self._theme_mode)
        self._theme_vars = self._theme_tokens.to_legacy_dict()
        self._last_task_status = (self._t("state.idle"), "#8b949e")
        self._last_device_status = (self._t("page.dashboard.status.no_device"), "#8b949e")
        self._last_mirror_status = (self._t("mirror.state.idle"), "#8b949e")
        self._last_result_color = ""
        self._last_readiness_state = (self._t("page.dashboard.readiness.checking"), "info")
        self._last_readiness_tooltip = self._t("page.dashboard.readiness.checking")
        self._readiness_results = []
        self._readiness_summary = None
        self._readiness_worker = None
        self._pending_readiness_refresh = False
        self._last_readiness_check_at = 0.0
        self._last_device_readiness_snapshot = None

        self._mirror_label: MirrorLabel = None   # ADB 截图降级时的图片显示
        self._mirror_container: QWidget = None
        self._mirror_host: QWidget = None        # scrcpy 内嵌专用原生宿主控件
        self._mirror_stack: QStackedLayout = None
        self._mirror_view_stack: QStackedLayout = None
        self._mirror_open_in_new_window_check: QCheckBox = None
        self._btn_mirror_paste_clipboard: QPushButton = None
        self._mirror_clipboard_worker: _MirrorClipboardPasteWorker | None = None
        self._mirror_detached_placeholder: QLabel = None
        self._mirror_popup_window: _MirrorPopupWindow = None
        self._mirror_embedded = False
        self._mirror_popup_ignore_close = False
        self._shutting_down = False
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
        self._sync_mirror_open_mode_preference()
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

    def _make_device_readiness_snapshot(self, device_info) -> tuple | None:
        if device_info is None:
            return None
        status = getattr(getattr(device_info, "status", None), "value", "")
        return (
            getattr(device_info, "device_id", "") or "",
            status,
            bool(getattr(device_info, "adb_keyboard_installed", False)),
            bool(getattr(device_info, "adb_keyboard_enabled", False)),
            str(getattr(device_info, "adb_keyboard_status", "") or ""),
        )

    # ================================================================
    # UI 构建
    # ================================================================

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(16)

        root.addWidget(self._build_hero_panel())

        left_panel = self._build_workspace_overview()
        left_panel.setMinimumWidth(320)
        left_panel.setMaximumWidth(420)
        left_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        center_panel = self._build_log_panel()
        center_panel.setMinimumWidth(420)
        center_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        right_panel = self._build_mirror_panel()
        right_panel.setMinimumWidth(520)
        right_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        splitter = QSplitter(Qt.Horizontal)
        self._main_splitter = splitter
        splitter.setObjectName("DashboardMainSplitter")
        splitter.setHandleWidth(8)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(left_panel)
        splitter.addWidget(center_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([360, 620, 860])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 2)
        root.addWidget(splitter, 1)

        self._refresh_workspace_overview()

    def _build_hero_panel(self) -> QWidget:
        panel = QFrame()
        self._hero_panel = panel
        panel.setObjectName("DashboardHeroPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(22, 14, 22, 16)
        layout.setSpacing(8)

        layout.addWidget(self._build_toolbar())
        layout.addWidget(self._build_instruction_bar())
        layout.addWidget(self._build_status_bar())
        layout.addWidget(self._build_readiness_bar())
        return panel

    def _build_workspace_overview(self) -> QWidget:
        panel = QFrame()
        self._workspace_overview_panel = panel
        panel.setObjectName("DashboardWorkspacePanel")
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)

        self._workspace_section_lbl = QLabel(self._t("page.dashboard.workspace.section"))
        self._workspace_section_lbl.setObjectName("DashboardWorkspaceSection")
        outer.addWidget(self._workspace_section_lbl)

        cards_column = QVBoxLayout()
        cards_column.setContentsMargins(0, 0, 0, 0)
        cards_column.setSpacing(12)

        self._policy_card = self._create_workspace_card("DashboardPolicyCard")
        self._policy_title_lbl = QLabel(self._t("page.dashboard.workspace.card.action_policy.title"))
        self._policy_title_lbl.setObjectName("DashboardWorkspaceCardTitle")
        self._policy_summary_lbl = QLabel(self._t("page.dashboard.workspace.card.action_policy.desc"))
        self._policy_summary_lbl.setObjectName("DashboardWorkspaceCardSummary")
        self._policy_summary_lbl.setWordWrap(True)
        self._policy_meta_lbl = QLabel("--")
        self._policy_meta_lbl.setObjectName("DashboardWorkspaceCardMeta")
        self._policy_meta_lbl.setWordWrap(True)
        self._btn_policy_manage = QPushButton(self._t("page.dashboard.workspace.card.action_policy.manage"))
        self._btn_policy_manage.clicked.connect(self._open_action_policy_dialog)
        self._policy_card._content_layout.addWidget(self._policy_title_lbl)
        self._policy_card._content_layout.addWidget(self._policy_summary_lbl)
        self._policy_card._content_layout.addWidget(self._policy_meta_lbl)
        self._policy_card._content_layout.addStretch(1)
        self._policy_card._content_layout.addWidget(self._btn_policy_manage, 0, Qt.AlignLeft)
        cards_column.addWidget(self._policy_card)

        self._channel_card = self._create_workspace_card("DashboardChannelCard")
        self._channel_title_lbl = QLabel(self._t("page.dashboard.workspace.card.channel.title"))
        self._channel_title_lbl.setObjectName("DashboardWorkspaceCardTitle")
        self._channel_summary_lbl = QLabel(self._t("page.dashboard.workspace.card.channel.desc"))
        self._channel_summary_lbl.setObjectName("DashboardWorkspaceCardSummary")
        self._channel_summary_lbl.setWordWrap(True)
        self._channel_meta_lbl = QLabel("--")
        self._channel_meta_lbl.setObjectName("DashboardWorkspaceCardMeta")
        self._channel_meta_lbl.setWordWrap(True)
        self._btn_channel_settings = QPushButton(self._t("page.dashboard.workspace.card.channel.cta"))
        self._btn_channel_settings.clicked.connect(self._open_settings_page)
        self._channel_card._content_layout.addWidget(self._channel_title_lbl)
        self._channel_card._content_layout.addWidget(self._channel_summary_lbl)
        self._channel_card._content_layout.addWidget(self._channel_meta_lbl)
        self._channel_card._content_layout.addStretch(1)
        self._channel_card._content_layout.addWidget(self._btn_channel_settings, 0, Qt.AlignLeft)
        cards_column.addWidget(self._channel_card)

        self._readiness_card = self._create_workspace_card("DashboardReadinessCard")
        self._readiness_title_lbl = QLabel(self._t("page.dashboard.workspace.card.readiness.title"))
        self._readiness_title_lbl.setObjectName("DashboardWorkspaceCardTitle")
        self._readiness_summary_lbl = QLabel(self._t("page.dashboard.workspace.card.readiness.desc"))
        self._readiness_summary_lbl.setObjectName("DashboardWorkspaceCardSummary")
        self._readiness_summary_lbl.setWordWrap(True)
        self._readiness_meta_lbl = QLabel("--")
        self._readiness_meta_lbl.setObjectName("DashboardWorkspaceCardMeta")
        self._readiness_meta_lbl.setWordWrap(True)
        self._btn_readiness_diagnostics = QPushButton(self._t("page.dashboard.workspace.card.readiness.cta"))
        self._btn_readiness_diagnostics.clicked.connect(self._open_diagnostics_page)
        self._readiness_card._content_layout.addWidget(self._readiness_title_lbl)
        self._readiness_card._content_layout.addWidget(self._readiness_summary_lbl)
        self._readiness_card._content_layout.addWidget(self._readiness_meta_lbl)
        self._readiness_card._content_layout.addStretch(1)
        self._readiness_card._content_layout.addWidget(self._btn_readiness_diagnostics, 0, Qt.AlignLeft)
        cards_column.addWidget(self._readiness_card)

        cards_column.addStretch(1)
        outer.addLayout(cards_column)
        return panel

    def _create_workspace_card(self, object_name: str) -> QFrame:
        card = QFrame()
        card.setObjectName(object_name)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)
        card._content_layout = layout
        return card

    def _refresh_workspace_overview(self) -> None:
        self._refresh_action_policy_card()
        self._refresh_channel_card()
        self._refresh_readiness_card()

    def _refresh_action_policy_card(self) -> None:
        if not hasattr(self, "_policy_summary_lbl"):
            return
        if not self._config:
            self._policy_summary_lbl.setText(self._t("page.dashboard.workspace.card.action_policy.desc"))
            self._policy_meta_lbl.setText("--")
            return
        summary = summarize_action_policy(self._config, self._t)
        self._policy_summary_lbl.setText(summary.get("headline", ""))
        self._policy_meta_lbl.setText(
            self._t(
                "page.dashboard.workspace.card.action_policy.meta",
                platform=summary.get("platform", "adb").upper(),
                mode=summary.get("mode_text", ""),
                runtime=summary.get("runtime_count", 0),
                ai_visible=summary.get("ai_count", 0),
            )
        )

    def _refresh_channel_card(self) -> None:
        if not hasattr(self, "_channel_summary_lbl"):
            return
        if not self._config:
            self._channel_summary_lbl.setText(self._t("page.dashboard.workspace.card.channel.desc"))
            self._channel_meta_lbl.setText("--")
            return
        active = self._config.get_active_channel()
        active_name = self._channel_name(active) if active else self._t("page.dashboard.channel.display.custom_plain")
        base_url = self._config.get("OPEN_AUTOGLM_BASE_URL") or "—"
        model = self._config.get("OPEN_AUTOGLM_MODEL") or "—"
        is_thirdparty = self._config._is_truthy(
            self._config.get("OPEN_AUTOGLM_USE_THIRDPARTY_PROMPT", "false")
        )
        mode_hint = self._t(
            "page.dashboard.channel.hint.thirdparty_bracketed"
            if is_thirdparty else
            "page.dashboard.channel.hint.native_bracketed"
        )
        self._channel_summary_lbl.setText(
            self._t(
                "page.dashboard.workspace.card.channel.summary",
                name=active_name,
                model=model,
            )
        )
        self._channel_meta_lbl.setText(
            self._t(
                "page.dashboard.workspace.card.channel.meta",
                base_url=base_url,
                mode_hint=mode_hint,
            )
        )

    def _refresh_readiness_card(self) -> None:
        if not hasattr(self, "_readiness_summary_lbl"):
            return
        readiness_text, semantic = self._last_readiness_state
        self._readiness_summary_lbl.setText(readiness_text)
        self._readiness_meta_lbl.setText(
            self._t(
                "page.dashboard.workspace.card.readiness.meta",
                task=self._last_task_status[0],
                mirror=self._last_mirror_status[0],
            )
        )
        if hasattr(self, "_readiness_card"):
            self._readiness_card.setProperty("semantic", semantic)
            self._readiness_card.style().unpolish(self._readiness_card)
            self._readiness_card.style().polish(self._readiness_card)
            self._readiness_card.update()

    def _open_action_policy_dialog(self) -> None:
        dialog = ActionPolicyDialog(self._services, parent=self)
        theme_manager = self._services.get("theme_manager")
        if theme_manager is not None and hasattr(dialog, "bind_theme_manager"):
            dialog.bind_theme_manager(theme_manager)
        dialog.exec()
        self._refresh_workspace_overview()

    def _open_settings_page(self) -> None:
        navigator = self._services.get("navigate_to_page")
        if callable(navigator):
            navigator("settings")

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
        self._task_input.setPlaceholderText(self._t("page.dashboard.toolbar.task_placeholder"))
        self._task_input.setMinimumWidth(300)
        self._task_input.returnPressed.connect(self._on_start)
        layout.addWidget(self._task_input, 1)

        # 开始按钮
        self._btn_start = QPushButton(self._t("page.dashboard.toolbar.btn.start"))
        self._btn_start.setProperty("variant", "primary")
        self._btn_start.clicked.connect(self._on_start)
        layout.addWidget(self._btn_start)

        # 停止按钮
        self._btn_stop = QPushButton(self._t("page.dashboard.toolbar.btn.stop"))
        self._btn_stop.setProperty("variant", "danger")
        self._btn_stop.clicked.connect(self._on_stop)
        layout.addWidget(self._btn_stop)

        # 暂停/恢复按钮
        self._btn_pause = QPushButton(self._t("page.dashboard.toolbar.btn.pause"))
        self._btn_pause.setProperty("variant", "warning")
        self._btn_pause.clicked.connect(self._on_pause_resume)
        layout.addWidget(self._btn_pause)

        # 接管按钮
        self._btn_takeover = QPushButton(self._t("page.dashboard.toolbar.btn.takeover"))
        self._btn_takeover.setProperty("variant", "warning")
        self._btn_takeover.clicked.connect(self._on_takeover)
        layout.addWidget(self._btn_takeover)

        self._sync_toolbar_action_button_widths()
        return bar

    def _build_instruction_bar(self) -> QWidget:
        """构建运行中追加指令栏（位于工具栏下方、状态条上方）。"""
        bar = QFrame()
        self._instruction_bar = bar
        bar.setObjectName("DashboardInstructionBar")

        # 使用垂直布局：上行（标题+状态+输入框+按钮），下行（说明文字）
        outer = QVBoxLayout(bar)
        outer.setContentsMargins(16, 10, 16, 10)
        outer.setSpacing(6)

        # 上行：标题 + 状态 + 输入框 + 按钮
        row = QHBoxLayout()
        row.setSpacing(10)

        # 标题标签
        title_lbl = QLabel(self._t("page.dashboard.instruction.card.title"))
        title_lbl.setObjectName("DashboardInstructionBarTitle")
        self._instruction_bar_title_lbl = title_lbl
        row.addWidget(title_lbl)

        # 状态指示器
        status_chip = QLabel()
        status_chip.setObjectName("DashboardInstructionBarStatusChip")
        self._instruction_status_chip = status_chip
        row.addWidget(status_chip)

        # 指令输入框
        self._instruction_input = QLineEdit()
        self._instruction_input.setPlaceholderText(
            self._t("page.dashboard.instruction.input.placeholder")
        )
        self._instruction_input.setObjectName("DashboardInstructionInput")
        self._instruction_input.setFixedHeight(32)
        self._instruction_input.returnPressed.connect(self._on_send_instruction)
        row.addWidget(self._instruction_input, 1)

        # 发送按钮
        self._btn_send_instruction = QPushButton(self._t("page.dashboard.instruction.btn.send"))
        self._btn_send_instruction.setProperty("variant", "primary")
        self._btn_send_instruction.setFixedHeight(32)
        self._btn_send_instruction.clicked.connect(self._on_send_instruction)
        row.addWidget(self._btn_send_instruction)

        # 清空按钮
        self._btn_clear_instruction = QPushButton(self._t("page.dashboard.instruction.btn.clear"))
        self._btn_clear_instruction.setProperty("variant", "subtle")
        self._btn_clear_instruction.setFixedHeight(32)
        self._btn_clear_instruction.clicked.connect(self._on_clear_instruction)
        row.addWidget(self._btn_clear_instruction)

        outer.addLayout(row)

        # 下行：说明文字
        self._instruction_hint_lbl = QLabel(self._t("page.dashboard.instruction.hint"))
        self._instruction_hint_lbl.setObjectName("DashboardInstructionBarHint")
        self._instruction_hint_lbl.setWordWrap(True)
        outer.addWidget(self._instruction_hint_lbl)

        # 初始状态更新
        self._update_instruction_card_state()

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

        self._lbl_task_state = self._make_status_chip(
            self._t("page.dashboard.status.label.state"),
            self._t("state.idle"), "#8b949e"
        )
        self._lbl_device_status = self._make_status_chip(
            self._t("page.dashboard.status.label.device"),
            self._t("page.dashboard.status.no_device"), "#8b949e"
        )
        self._lbl_mirror_status = self._make_status_chip(
            self._t("page.dashboard.status.label.mirror"),
            self._t("mirror.state.idle"), "#8b949e"
        )

        layout.addWidget(self._lbl_task_state)
        layout.addWidget(self._make_sep())
        layout.addWidget(self._lbl_device_status)
        layout.addWidget(self._make_sep())
        layout.addWidget(self._lbl_mirror_status)
        layout.addStretch(1)

        # 镜像兜底粘贴按钮（主要用于独立 scrcpy 窗口模式）
        self._btn_mirror_paste_clipboard = QPushButton(self._t("page.dashboard.mirror.btn.paste_clipboard"))
        self._btn_mirror_paste_clipboard.setFixedHeight(22)
        self._btn_mirror_paste_clipboard.setProperty("variant", "subtle")
        self._btn_mirror_paste_clipboard.clicked.connect(self._on_mirror_paste_clipboard)
        self._btn_mirror_paste_clipboard.setEnabled(False)
        layout.addWidget(self._btn_mirror_paste_clipboard)

        # 镜像控制按钮
        self._btn_mirror_toggle = QPushButton(self._t("page.dashboard.mirror.btn.start_mirror"))
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

        self._btn_open_diag = QPushButton(self._t("shell.nav.diagnostics"))
        self._btn_open_diag.setProperty("variant", "subtle")
        self._btn_open_diag.setFixedHeight(28)
        self._btn_open_diag.clicked.connect(self._open_diagnostics_page)
        layout.addWidget(self._btn_open_diag)

        self._btn_readiness_refresh = QPushButton(self._t("page.dashboard.readiness.btn.refresh"))
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
        self._refresh_readiness_card()

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
        checking_txt = self._t("page.dashboard.readiness.checking")
        self._set_readiness_state(checking_txt, "info", checking_txt)
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
            self._set_readiness_state(self._t("page.dashboard.readiness.no_results"), "warning")
            return

        self._readiness_summary = summarize_readiness(self._readiness_results)
        title, detail, action_hint = render_summary(self._readiness_summary, self._t)
        summary_text = f"{title} · {detail}"
        tooltip = summary_text
        if action_hint:
            tooltip += f"\n{action_hint}"
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
        self._mirror_panel_group = QGroupBox(self._t("page.dashboard.mirror.title"))
        panel = self._mirror_panel_group
        panel.setMinimumWidth(520)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 18, 12, 12)
        layout.setSpacing(10)

        # 设备信息区
        self._device_info_lbl = QLabel(self._t("page.dashboard.mirror.no_device"))
        self._device_info_lbl.setStyleSheet("color:#8b949e; font-size:12px; padding:4px;")
        self._device_info_lbl.setWordWrap(True)
        layout.addWidget(self._device_info_lbl)

        # 镜像打开方式
        self._mirror_open_in_new_window_check = QCheckBox(
            self._t("page.dashboard.mirror.open_in_new_window")
        )
        self._mirror_open_in_new_window_check.toggled.connect(self._on_mirror_open_mode_toggled)
        layout.addWidget(self._mirror_open_in_new_window_check, 0, Qt.AlignLeft)

        # 镜像显示容器
        self._mirror_container = QWidget()
        self._mirror_container.setStyleSheet("background:#0a0e17; border-radius:6px;")
        self._mirror_container.setMinimumWidth(360)
        self._mirror_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._mirror_container.installEventFilter(self)
        self._mirror_stack = QStackedLayout(self._mirror_container)
        self._mirror_stack.setContentsMargins(0, 0, 0, 0)

        # 占位标签（scrcpy 外部窗口模式或未启动时）
        self._mirror_placeholder = QLabel(self._t("page.dashboard.mirror.placeholder"))
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

        self._mirror_detached_placeholder = QLabel(
            self._t("page.dashboard.mirror.detached_placeholder")
        )
        self._mirror_detached_placeholder.setAlignment(Qt.AlignCenter)
        self._mirror_detached_placeholder.setWordWrap(True)

        mirror_viewport = QWidget()
        self._mirror_view_stack = QStackedLayout(mirror_viewport)
        self._mirror_view_stack.setContentsMargins(0, 0, 0, 0)
        self._mirror_view_stack.addWidget(self._mirror_container)
        self._mirror_view_stack.addWidget(self._mirror_detached_placeholder)
        self._mirror_view_stack.setCurrentWidget(self._mirror_container)

        layout.addWidget(mirror_viewport, 1)

        # 接管提示横幅（隐藏）
        self._takeover_banner = QLabel(self._t("page.dashboard.takeover.banner"))
        self._takeover_banner.setAlignment(Qt.AlignCenter)
        self._takeover_banner.setStyleSheet("""
            background:#3d2800; color:#e3b341; font-size:12px;
            border:1px solid #6e4800; border-radius:4px; padding:6px;
        """)
        self._takeover_banner.hide()
        layout.addWidget(self._takeover_banner)

        # 继续执行按钮（接管模式下显示）
        self._btn_resume_exec = QPushButton(self._t("page.dashboard.takeover.btn.restore"))
        self._btn_resume_exec.setProperty("variant", "primary")
        self._btn_resume_exec.hide()
        self._btn_resume_exec.clicked.connect(self._on_resume_after_takeover)
        layout.addWidget(self._btn_resume_exec)

        return panel

    # ----------------------------------------------------------------
    # 主区 B：日志与事件
    # ----------------------------------------------------------------

    def _build_log_panel(self) -> QWidget:
        self._log_panel_group = QGroupBox(self._t("event.result_summary"))
        panel = self._log_panel_group
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 16, 8, 8)
        layout.setSpacing(0)

        self._log_tabs = QTabWidget()
        tabs = self._log_tabs
        tabs.setDocumentMode(True)

        # 原始日志 Tab
        self._log_view = QPlainTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setObjectName("DashboardLogView")
        self._log_view.setMaximumBlockCount(5000)
        tabs.addTab(self._log_view, self._t("page.dashboard.log.tab.log"))

        # 事件时间线 Tab
        self._event_list = QListWidget()
        self._event_list.setObjectName("DashboardEventList")
        tabs.addTab(self._event_list, self._t("page.dashboard.log.tab.events"))

        layout.addWidget(tabs, 1)

        # 底部结果摘要区
        self._result_lbl = QLabel(self._t("page.dashboard.log.empty_result"))
        self._result_lbl.setObjectName("DashboardResultSummary")
        self._result_lbl.setWordWrap(True)
        self._result_lbl.setMinimumHeight(40)
        layout.addWidget(self._result_lbl)

        return panel

    # ----------------------------------------------------------------
    # 运行中追加指令栏回调
    # ----------------------------------------------------------------

    def _on_send_instruction(self):
        """发送运行中追加指令到 TaskService inbox。"""
        text = self._instruction_input.text().strip()
        if not text:
            return

        submit_instruction = getattr(self._task, "submit_runtime_instruction", None)
        if callable(submit_instruction) and submit_instruction(text):
            self._instruction_input.clear()
            self._append_log(
                self._t("page.dashboard.instruction.log.sent", instruction=text[:80])
            )

    def _on_clear_instruction(self):
        """清空指令输入框。"""
        self._instruction_input.clear()

    def _on_instruction_submitted(self, instruction_text: str):
        """处理运行时指令提交成功后的 UI 同步。"""
        self._update_instruction_card_state()
        if hasattr(self, "_instruction_status_chip"):
            self._instruction_status_chip.setText(
                self._t("page.dashboard.instruction.status.ready")
            )

    def _update_instruction_card_state(self):
        """更新指令栏状态（启用/禁用、状态文字、主题样式）。"""
        if not hasattr(self, "_btn_send_instruction"):
            return

        task = self._task
        runtime_inbox_path = getattr(task, "runtime_inbox_path", None) if task is not None else None
        can_send = (
            task is not None
            and runtime_inbox_path is not None
            and task.state in {TaskState.RUNNING, TaskState.PAUSED}
        )
        self._btn_send_instruction.setEnabled(can_send)
        self._btn_clear_instruction.setEnabled(can_send)
        self._instruction_input.setEnabled(can_send)

        v = self._theme_vars or {}
        if not can_send:
            if task is None or task.state == TaskState.IDLE:
                status_text = self._t("page.dashboard.instruction.status.idle")
            else:
                status_text = self._t("page.dashboard.instruction.status.completed")
            status_color = v.get("text_muted", "#8b949e")
            self._instruction_status_chip.setText(status_text)
            self._instruction_status_chip.setStyleSheet(f"color:{status_color};")
            self._instruction_input.setPlaceholderText(
                self._t("page.dashboard.instruction.input.placeholder_disabled")
            )
        else:
            status_text = self._t("page.dashboard.instruction.status.ready")
            status_color = v.get("success", "#3fb950")
            self._instruction_status_chip.setText(status_text)
            self._instruction_status_chip.setStyleSheet(f"color:{status_color};")
            self._instruction_input.setPlaceholderText(
                self._t("page.dashboard.instruction.input.placeholder")
            )

        # 应用主题样式
        self._apply_instruction_bar_tokens()

    def _apply_instruction_bar_tokens(self):
        """应用主题 tokens 到指令栏各组件。"""
        if not hasattr(self, "_instruction_bar"):
            return
        v = self._theme_vars or {}

        # 指令栏外壳
        if hasattr(self, "_instruction_bar"):
            self._instruction_bar.setStyleSheet(
                f"background:{v.get('bg_elevated', '#f7f9fc')}; "
                f"border:1px solid {v.get('border', '#d5deea')}; "
                f"border-radius:12px;"
            )

        # 标题文字
        if hasattr(self, "_instruction_bar_title_lbl"):
            self._instruction_bar_title_lbl.setStyleSheet(
                f"color:{v.get('text_primary', '#18212f')}; font-size:12px; font-weight:600;"
            )

        # 输入框
        if hasattr(self, "_instruction_input"):
            task = self._task
            runtime_inbox_path = getattr(task, "runtime_inbox_path", None) if task is not None else None
            can_send = (
                task is not None
                and runtime_inbox_path is not None
                and task.state in {TaskState.RUNNING, TaskState.PAUSED}
            )
            if can_send:
                bg = v.get('input_bg', '#ffffff')
                text = v.get('input_text', '#18212f')
                border = v.get('input_border', '#d5deea')
                placeholder = v.get('input_placeholder', '#7b8aa0')
            else:
                bg = v.get('input_disabled_bg', '#eef3f9')
                text = v.get('text_muted', '#7b8aa0')
                border = v.get('border', '#d5deea')
                placeholder = v.get('input_placeholder', '#7b8aa0')
            self._instruction_input.setStyleSheet(
                f"background:{bg}; color:{text}; "
                f"border:1px solid {border}; border-radius:8px; "
                f"padding:0 12px; font-size:13px; min-height:32px;"
            )

        # 说明文字
        if hasattr(self, "_instruction_hint_lbl"):
            self._instruction_hint_lbl.setStyleSheet(
                f"color:{v.get('text_secondary', '#526273')}; font-size:11px;"
            )

    def _format_status_chip(self, key: str, value: str, color: str) -> str:
        meta_color = self._theme_vars.get("text_muted", "#66778d")
        return (
            f"<span style='color:{meta_color}'>{key}:</span> "
            f"<span style='color:{color}'>{value}</span>"
        )

    def _set_task_status(self, text: str, color: str):
        self._last_task_status = (text, color)
        if hasattr(self, "_lbl_task_state"):
            self._lbl_task_state.setText(
                self._format_status_chip(self._t("page.dashboard.status.label.state"), text, color)
            )
        self._refresh_readiness_card()

    def _set_device_status(self, text: str, color: str):
        self._last_device_status = (text, color)
        if hasattr(self, "_lbl_device_status"):
            self._lbl_device_status.setText(
                self._format_status_chip(self._t("page.dashboard.status.label.device"), text, color)
            )

    def _set_mirror_status(self, text: str, color: str):
        self._last_mirror_status = (text, color)
        if hasattr(self, "_lbl_mirror_status"):
            self._lbl_mirror_status.setText(
                self._format_status_chip(self._t("page.dashboard.status.label.mirror"), text, color)
            )
        self._refresh_readiness_card()

    def _summary_style(self, color: str = "") -> str:
        v = self._theme_vars or {}
        summary_color = color or v.get("text_secondary", "#526273")
        border_color = f"{summary_color}33" if summary_color.startswith("#") else v.get("border", "#d5deea")
        return (
            f"background:{v.get('bg_elevated', '#f7f9fc')}; "
            f"border:1px solid {border_color}; border-radius:12px; padding:10px 12px; "
            f"font-size:12px; color:{summary_color}; margin-top:8px;"
        )

    def _panel_group_style(self) -> str:
        v = self._theme_vars or {}
        return f"""
            QGroupBox {{
                background:{v.get('bg_secondary', '#161b22')};
                border:1px solid {v.get('border', '#30363d')};
                border-radius:22px;
                margin-top:18px;
                padding-top:18px;
                color:{v.get('text_primary', '#c9d1d9')};
                font-size:13px;
                font-weight:700;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left:18px;
                padding:0 6px;
                color:{v.get('text_primary', '#c9d1d9')};
            }}
        """

    def _workspace_card_style(self, semantic: str = "default") -> str:
        v = self._theme_vars or {}
        semantic_map = {
            "accent": (v.get("accent_soft", "#162033"), v.get("accent_soft", "#162033")),
            "success": (v.get("success_bg", "#0f2d1a"), v.get("success_border", v.get("success", "#3fb950"))),
            "warning": (v.get("warning_bg", "#3d2800"), v.get("warning_border", v.get("warning", "#e3b341"))),
            "error": (v.get("danger_bg", "#3d1a1a"), v.get("danger_border", v.get("danger", "#f85149"))),
            "info": (v.get("bg_elevated", "#121924"), v.get("border", "#30363d")),
            "default": (v.get("bg_secondary", "#161b22"), v.get("border", "#30363d")),
        }
        bg, border = semantic_map.get(semantic, semantic_map["default"])
        return (
            f"background:{bg}; border:1px solid {border}; border-radius:22px;"
        )

    def _channel_combo_style(self, theme_vars: dict) -> str:
        v = theme_vars or {}
        return f"""
            QComboBox {{
                background:{v.get('bg_elevated', '#121924')};
                border:1px solid {v.get('border', '#30363d')};
                border-radius:12px;
                color:{v.get('text_primary', '#c9d1d9')};
                padding:0 12px;
                font-size:12px;
            }}
            QComboBox:hover {{ border-color:{v.get('border_hover', v.get('accent', '#4f8cff'))}; }}
            QComboBox:focus {{ border-color:{v.get('accent', '#4f8cff')}; }}
            QComboBox::drop-down {{
                border:none;
                width:26px;
            }}
            QComboBox::down-arrow {{
                width:0;
                height:0;
                border-left:5px solid transparent;
                border-right:5px solid transparent;
                border-top:6px solid {v.get('text_secondary', '#8b949e')};
                margin-right:10px;
            }}
            QComboBox QAbstractItemView {{
                background:{v.get('bg_elevated', '#121924')};
                border:1px solid {v.get('border', '#30363d')};
                border-radius:12px;
                selection-background-color:{v.get('selection_bg', '#264f78')};
                color:{v.get('text_primary', '#c9d1d9')};
                padding:4px;
                outline:none;
            }}
            QComboBox QAbstractItemView::item {{
                padding:6px 10px;
                min-height:26px;
                border-radius:8px;
            }}
        """

    def apply_theme_tokens(self, tokens: ThemeTokens) -> None:
        """
        New theme hook driven by PageThemeAdapter / ThemeManager.
        Cache tokens first, then refresh surfaces and dynamic states.
        """
        self._theme_tokens = tokens
        self._theme_mode = tokens.mode
        self._theme_vars = tokens.to_legacy_dict()
        self.refresh_theme_surfaces()
        self.refresh_theme_states()

    def refresh_theme_surfaces(self) -> None:
        """刷新静态外观：英雄区、概览卡片、日志区、镜像区背景。"""
        if self._theme_tokens is None:
            return
        v = self._theme_vars

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

        if hasattr(self, "_hero_panel"):
            self._hero_panel.setStyleSheet(
                f"background:{v.get('bg_elevated', '#121924')};"
                f"border:1px solid {v.get('border', '#30363d')}; border-radius:22px;"
            )
        if hasattr(self, "_workspace_overview_panel"):
            self._workspace_overview_panel.setStyleSheet(
                f"background:{v.get('bg_elevated', '#121924')}; border:none; border-radius:26px;"
            )
        if hasattr(self, "_workspace_section_lbl"):
            self._workspace_section_lbl.setStyleSheet(
                f"color:{v.get('text_primary', '#c9d1d9')}; font-size:15px; font-weight:700;"
            )
        if hasattr(self, "_hero_title_lbl"):
            self._hero_title_lbl.setStyleSheet(
                f"color:{v.get('text_primary', '#c9d1d9')}; font-size:20px; font-weight:700;"
            )
        if hasattr(self, "_main_splitter"):
            self._main_splitter.setStyleSheet(
                f"QSplitter::handle {{ background:{v.get('border', '#30363d')}; border-radius:999px; margin:18px 8px; }}"
            )
        if hasattr(self, "_policy_card"):
            self._policy_card.setStyleSheet(self._workspace_card_style("default"))
        if hasattr(self, "_channel_card"):
            self._channel_card.setStyleSheet(self._workspace_card_style("info"))
        if hasattr(self, "_readiness_card"):
            self._readiness_card.setStyleSheet(self._workspace_card_style(self._last_readiness_state[1]))
        for label in (
            getattr(self, "_policy_title_lbl", None),
            getattr(self, "_channel_title_lbl", None),
            getattr(self, "_readiness_title_lbl", None),
        ):
            if label is not None:
                label.setStyleSheet(
                    f"color:{v.get('text_primary', '#c9d1d9')}; font-size:15px; font-weight:700;"
                )
        for label in (
            getattr(self, "_policy_summary_lbl", None),
            getattr(self, "_channel_summary_lbl", None),
            getattr(self, "_readiness_summary_lbl", None),
        ):
            if label is not None:
                label.setStyleSheet(
                    f"color:{v.get('text_primary', '#c9d1d9')}; font-size:13px; line-height:1.5;"
                )
        for label in (
            getattr(self, "_policy_meta_lbl", None),
            getattr(self, "_channel_meta_lbl", None),
            getattr(self, "_readiness_meta_lbl", None),
        ):
            if label is not None:
                label.setStyleSheet(
                    f"color:{v.get('text_secondary', '#8b949e')}; font-size:12px; line-height:1.5;"
                )

        if hasattr(self, "_mirror_panel_group"):
            self._mirror_panel_group.setStyleSheet(self._panel_group_style())
        if hasattr(self, "_log_panel_group"):
            self._log_panel_group.setStyleSheet(self._panel_group_style())
        if hasattr(self, "_mirror_container"):
            self._mirror_container.setStyleSheet(
                f"background:{v.get('bg_console', '#0a0f18')}; "
                f"border:none; border-radius:16px;"
            )
        if hasattr(self, "_mirror_host"):
            self._mirror_host.setStyleSheet(
                f"background:{v.get('bg_console', '#0a0f18')}; border-radius:16px;"
            )
        if hasattr(self, "_mirror_placeholder"):
            self._mirror_placeholder.setStyleSheet(
                f"color:{v.get('text_muted', '#66778d')}; font-size:13px; line-height:1.8; padding:16px;"
            )
        if hasattr(self, "_mirror_detached_placeholder"):
            self._mirror_detached_placeholder.setStyleSheet(
                f"color:{v.get('text_muted', '#66778d')}; font-size:13px; line-height:1.8; padding:24px;"
            )
        if hasattr(self, "_device_info_lbl"):
            self._device_info_lbl.setStyleSheet(
                f"color:{v.get('text_secondary', '#526273')}; font-size:12px; padding:4px 6px 8px 6px;"
            )
        if hasattr(self, "_mirror_open_in_new_window_check"):
            self._mirror_open_in_new_window_check.setStyleSheet(
                f"QCheckBox {{ color:{v.get('text_secondary', '#526273')}; font-size:12px; padding:2px 4px 8px 4px; }}"
            )
        if getattr(self, "_mirror_popup_window", None):
            self._mirror_popup_window.setStyleSheet(
                f"background:{v.get('bg_main', '#0d1117')};"
            )
        if hasattr(self, "_readiness_bar"):
            self._readiness_bar.setStyleSheet(self._readiness_bar_style(self._last_readiness_state[1]))
        if hasattr(self, "_takeover_banner"):
            self._takeover_banner.setStyleSheet(
                f"background:{v.get('warning_bg', '#3d2800')}; color:{v.get('warning', '#e3b341')}; "
                f"font-size:12px; border:1px solid {v.get('warning_border', '#6e4800')}; "
                f"border-radius:12px; padding:10px 12px;"
            )
        # 运行中追加指令栏样式
        self._apply_instruction_bar_tokens()
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
        self._refresh_workspace_overview()

    def refresh_theme_states(self) -> None:
        """刷新动态状态：按钮样式、渠道下拉框与工作台入口按钮。"""
        if self._theme_tokens is None:
            return
        v = self._theme_vars
        self._apply_action_button_styles()
        self._update_instruction_card_state()
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
            instruction_submitted = getattr(self._task, "instruction_submitted", None)
            if instruction_submitted is not None:
                instruction_submitted.connect(self._on_instruction_submitted)

        if self._device:
            self._device.devices_changed.connect(self._on_devices_changed)
            self._device.device_selected.connect(self._on_device_selected)

        if self._mirror:
            self._mirror.state_changed.connect(self._on_mirror_state_changed)
            self._mirror.mode_changed.connect(self._on_mirror_mode_changed)
            self._mirror.frame_ready.connect(self._on_mirror_frame)
            self._mirror.error_occurred.connect(self._on_mirror_error)
            self._mirror.window_created.connect(self._on_mirror_window_created)
        if self._mirror_label:
            self._mirror_label.tap_failed.connect(self._on_mirror_error)

        # 配置变化时同步渠道下拉框（例如设置页保存后）
        if self._config:
            self._config.config_changed.connect(self._sync_channel_combo)
            self._config.config_changed.connect(self._sync_mirror_open_mode_preference)
            self._config.config_changed.connect(lambda: self._schedule_readiness_check(300))

    # ================================================================
    # 渠道切换
    # ================================================================

    def _channel_name(self, preset: dict | None) -> str:
        """Return the localized channel name, falling back to preset.name."""
        if not preset:
            return ""
        channel_id = (preset.get("id") or "").strip()
        fallback = preset.get("name") or channel_id
        if not channel_id:
            return fallback
        key = f"page.dashboard.channel.preset.{channel_id}"
        translated = self._t(key)
        return fallback if translated == f"[[{key}]]" else translated

    def _populate_channel_combo(self):
        """填充渠道下拉框选项（仅填充，不触发切换逻辑）"""
        if not self._config:
            return
        self._channel_combo.blockSignals(True)
        self._channel_combo.clear()
        presets = self._config.CHANNEL_PRESETS
        for preset in presets:
            self._channel_combo.addItem(self._channel_name(preset), userData=preset["id"])
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
                    self,
                    self._t("page.dashboard.channel.switch_blocked.title"),
                    self._t("page.dashboard.channel.switch_blocked.text"),
                )
                # 回滚下拉框选中项
                self._sync_channel_combo()
                return

        ok = self._config.set_active_channel(channel_id)
        if not ok:
            QMessageBox.warning(
                self,
                self._t("page.dashboard.channel.switch_failed.title"),
                self._t("page.dashboard.channel.switch_failed.text", channel_id=channel_id),
            )
            self._sync_channel_combo()
            return

        # 刷新状态条模型显示（config_changed 信号已连接 _sync_channel_combo，
        # 但此处直接调用以确保及时刷新）
        self._refresh_status_bar()
        preset = next(
            (p for p in self._config.CHANNEL_PRESETS if p["id"] == channel_id), None
        )
        if preset and channel_id != "custom":
            mode_hint = self._t(
                "page.dashboard.channel.hint.thirdparty_inline"
                if preset["use_thirdparty"]
                else "page.dashboard.channel.hint.native_inline"
            )
            resolved_url = self._config.get_preset_url(preset)
            resolved_model = self._config.get_preset_model(preset)
            self._append_log(
                self._t(
                    "page.dashboard.channel.log.switch_preset",
                    name=self._channel_name(preset),
                    mode_hint=mode_hint,
                    base_url=resolved_url,
                    model=resolved_model,
                )
            )
        else:
            self._append_log(self._t("page.dashboard.channel.log.switch_custom"))

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
                self._t("page.dashboard.readiness.checking"),
                "info",
                self._t("page.dashboard.readiness.hint_retry"),
            )
            self._schedule_readiness_check(0)
            return

        blocking_labels = collect_blocking_labels(self._readiness_results, translator=self._t)
        if blocking_labels:
            warning_text = self._t("page.dashboard.blocking.warning", labels=blocking_labels)
            self._set_readiness_state(
                warning_text,
                "error",
                warning_text + "\n" + self._t("page.dashboard.blocking.hint"),
            )
            msg = QMessageBox(self)
            msg.setWindowTitle(self._t("page.dashboard.blocking.dialog.title"))
            msg.setText(self._t("page.dashboard.blocking.dialog.text", labels=blocking_labels))
            msg.setInformativeText(self._t("page.dashboard.blocking.dialog.info"))
            btn_diag = msg.addButton(self._t("page.dashboard.blocking.dialog.btn.diag"), QMessageBox.ActionRole)
            msg.addButton(self._t("dialog.confirm.no"), QMessageBox.RejectRole)
            msg.exec()
            if msg.clickedButton() == btn_diag:
                self._open_diagnostics_page()
            return

        if self._task:
            # 清空上次日志
            self._log_view.clear()
            self._event_list.clear()
            self._last_result_color = ""
            self._result_lbl.setText(self._t("page.dashboard.log.empty_result"))
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
            self._task.request_takeover(self._t("page.dashboard.takeover.user_reason"))

    def _on_resume_after_takeover(self):
        if self._task:
            self._task.resume_task()

    def _mirror_prefers_new_window(self) -> bool:
        if self._mirror_open_in_new_window_check is not None:
            return self._mirror_open_in_new_window_check.isChecked()
        if self._config:
            return self._is_truthy(self._config.get("OPEN_AUTOGLM_GUI_MIRROR_NEW_WINDOW", "false"))
        return False

    def _sync_mirror_open_mode_preference(self):
        if not self._mirror_open_in_new_window_check:
            return
        checked = False
        if self._config:
            checked = self._is_truthy(
                self._config.get("OPEN_AUTOGLM_GUI_MIRROR_NEW_WINDOW", "false")
            )
        self._mirror_open_in_new_window_check.blockSignals(True)
        self._mirror_open_in_new_window_check.setChecked(checked)
        self._mirror_open_in_new_window_check.blockSignals(False)

    def _on_mirror_open_mode_toggled(self, checked: bool):
        if not self._config:
            return
        try:
            self._config.set(
                "OPEN_AUTOGLM_GUI_MIRROR_NEW_WINDOW",
                "true" if checked else "false",
            )
        except Exception as exc:
            self._mirror_open_in_new_window_check.blockSignals(True)
            self._mirror_open_in_new_window_check.setChecked(not checked)
            self._mirror_open_in_new_window_check.blockSignals(False)
            self._append_log(
                self._t(
                    "page.dashboard.mirror.log.preference_save_failed",
                    error=str(exc),
                )
            )

    def _set_dashboard_mirror_detached(self, detached: bool):
        if not self._mirror_view_stack or not self._mirror_detached_placeholder or not self._mirror_container:
            return
        self._mirror_view_stack.setCurrentWidget(
            self._mirror_detached_placeholder if detached else self._mirror_container
        )

    def _popup_window_active(self) -> bool:
        return bool(
            self._mirror_popup_window
            and self._mirror_popup_window.isVisible()
            and not self._mirror_popup_window.is_closing()
        )

    def _update_mirror_popup_title(self, device_id: str = ""):
        if self._mirror_popup_window is None:
            return
        resolved_device_id = device_id or self._current_device_id()
        self._mirror_popup_window.setWindowTitle(
            self._t(
                "page.dashboard.mirror.popup.window_title",
                device_id=resolved_device_id or "—",
            )
        )

    def _ensure_mirror_popup_window(self):
        if self._mirror_popup_window is None:
            self._mirror_popup_window = _MirrorPopupWindow()
            self._mirror_popup_window.closing.connect(self._on_mirror_popup_window_closing)
            self._mirror_popup_window.container_widget().installEventFilter(self)
            self._mirror_popup_window.host_widget().installEventFilter(self)
            self._mirror_popup_window.label_widget().tap_failed.connect(self._on_mirror_error)
        self._mirror_popup_window.set_placeholder_text(self._t("page.dashboard.mirror.placeholder"))
        self._mirror_popup_window.label_widget().set_device_id(self._current_device_id())
        self._update_mirror_popup_title()
        if self._theme_tokens is not None:
            self.refresh_theme_surfaces()
        return self._mirror_popup_window

    def _show_mirror_popup_window(self, device_id: str = ""):
        window = self._ensure_mirror_popup_window()
        self._update_mirror_popup_title(device_id)
        window.label_widget().set_device_id(device_id or self._current_device_id())
        self._set_dashboard_mirror_detached(True)
        window.restore_and_show()
        return window

    def _close_mirror_popup_window(self, *, ignore_stop: bool):
        if not self._mirror_popup_window:
            self._set_dashboard_mirror_detached(False)
            return
        self._mirror_popup_ignore_close = ignore_stop
        try:
            if self._mirror_popup_window.isVisible():
                self._mirror_popup_window.close()
            else:
                self._set_dashboard_mirror_detached(False)
        finally:
            self._mirror_popup_ignore_close = False

    def _on_mirror_popup_window_closing(self):
        should_stop_mirror = (
            not self._mirror_popup_ignore_close
            and not self._shutting_down
            and bool(self._mirror and self._mirror.is_running)
        )
        self._set_dashboard_mirror_detached(False)
        if should_stop_mirror:
            self._mirror.stop()

    def _active_mirror_widgets(self):
        if self._mirror_prefers_new_window() and self._popup_window_active():
            popup = self._mirror_popup_window
            return popup.host_widget(), popup.container_widget(), popup.label_widget(), popup
        return self._mirror_host, self._mirror_container, self._mirror_label, None

    def _build_mirror_start_context(self, device_id: str):
        embed_wid = None
        embed_container_size = None
        host = None
        container = None

        if self._mirror_prefers_new_window():
            popup = self._show_mirror_popup_window(device_id)
            popup.show_host()
            host = popup.host_widget()
            container = popup.container_widget()
        elif self._mirror_host and self._mirror_container:
            if self._mirror_stack:
                self._mirror_stack.setCurrentWidget(self._mirror_host)
            self._mirror_host.show()
            self._set_dashboard_mirror_detached(False)
            host = self._mirror_host
            container = self._mirror_container

        if not (host and container and container.isVisible()):
            return embed_wid, embed_container_size

        try:
            host_rect = host.contentsRect()
            if host_rect.width() > 0 and host_rect.height() > 0:
                embed_container_size = (host_rect.width(), host_rect.height())
            else:
                container_rect = container.contentsRect()
                if container_rect.width() > 0 and container_rect.height() > 0:
                    embed_container_size = (container_rect.width(), container_rect.height())
            embed_wid = int(host.winId())
        except Exception:
            embed_wid = None
            embed_container_size = None
        return embed_wid, embed_container_size

    def _start_mirror_for_device(self, device_id: str, external_window: bool = False):
        if not self._mirror or not device_id:
            return
        if external_window:
            embed_wid = None
            embed_container_size = None
            self._close_mirror_popup_window(ignore_stop=True)
            self._set_dashboard_mirror_detached(False)
        else:
            embed_wid, embed_container_size = self._build_mirror_start_context(device_id)
        self._mirror.start(
            device_id,
            embed_wid=embed_wid,
            embed_container_size=embed_container_size,
        )
        self._append_mirror_debug_log(
            self._t(
                "page.dashboard.mirror.debug.start_request",
                device_id=device_id,
                embed_wid=embed_wid or "None",
                embed_size=embed_container_size or "None",
            )
        )

    def _schedule_popup_mirror_start(self, device_id: str, attempt: int = 0):
        if not self._mirror or self._shutting_down:
            return
        if self._mirror.is_running or self._mirror.state == MirrorState.STARTING:
            return
        if not self._mirror_prefers_new_window():
            return
        self._start_mirror_for_device(device_id, external_window=True)

    def _on_mirror_toggle(self):
        if not self._mirror:
            return
        if self._mirror.is_running:
            self._mirror.stop()
        else:
            device_id = self._current_device_id()
            if not device_id:
                self._append_log(self._t("page.dashboard.mirror.log.no_device"))
                return
            if self._mirror_prefers_new_window():
                self._start_mirror_for_device(device_id, external_window=True)
            else:
                self._start_mirror_for_device(device_id)

    # ================================================================
    # 任务状态回调
    # ================================================================

    def _on_task_state_changed(self, state: TaskState):
        self._update_button_states(state)
        self._update_instruction_card_state()  # 同步更新指令卡片状态

        # i18n 化状态文字
        state_key = f"state.{state.value}"
        color = STATE_COLORS.get(state, "#8b949e")
        text = self._t(state_key)
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
            self._btn_pause.setText(self._t("page.dashboard.toolbar.btn.resume"))
            self._btn_pause.setProperty("variant", "success")
        else:
            self._btn_pause.setText(self._t("page.dashboard.toolbar.btn.pause"))
            self._btn_pause.setProperty("variant", "warning")
        self._sync_toolbar_action_button_widths()
        self._apply_action_button_styles(task_state=state)

    def _on_log_line(self, line: str):
        self._append_log(line)

    @staticmethod
    def _log_color_for_line(line: str) -> str:
        stripped = line.strip()
        if not stripped:
            return "#c9d1d9"
        if "专家请求失败" in stripped or stripped.startswith("⚠️"):
            return "#f85149"
        if "专家请求成功" in stripped or "已注入主模型上下文" in stripped:
            return "#3fb950"
        if "触发严格模式专家咨询" in stripped or "触发自动专家救援" in stripped:
            return "#e3b341"
        if "跳过严格模式专家咨询" in stripped:
            return "#8b949e"
        if stripped.startswith("[EXPERT]"):
            return "#79c0ff"
        return "#c9d1d9"

    def _append_log(self, line: str):
        cursor = self._log_view.textCursor()
        cursor.movePosition(QTextCursor.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(self._log_color_for_line(line)))
        cursor.insertText(line, fmt)
        self._log_view.setTextCursor(cursor)
        self._log_view.moveCursor(QTextCursor.End)

    @staticmethod
    def _is_truthy(value: str) -> bool:
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def _append_mirror_debug_log(self, line: str):
        if self._mirror_debug_enabled:
            self._append_log(line)

    def _on_event_added(self, evt: dict):
        message = evt.get("rendered_message") or evt.get("message", "")
        item = QListWidgetItem(
            f"[{evt.get('time_str', '')}] {message}"
        )
        color_map = {
            "task_complete": "#3fb950",
            "task_failed":   "#f85149",
            "error":         "#f85149",
            "takeover_request": "#e3b341",
            "user_pause":    "#e3b341",
            "stuck_detected":"#f0883e",
        }
        color = color_map.get(evt.get("type"))
        if color:
            item.setForeground(QColor(color))
        self._event_list.insertItem(0, item)

    def _on_task_finished(self, record):
        state = record.state
        state_key = f"state.{state.value}"
        color = STATE_COLORS.get(state, "#8b949e")
        text = self._t(state_key)
        summary = (
            f"{self._t('page.history.overview.task')}：{record.task_text[:60]}\n"
            f"{self._t('page.history.overview.state')}：{text}  |  "
            f"{self._t('page.history.overview.duration')}：{record.duration_str}  |  "
            f"{self._t('page.history.overview.device')}：{record.device_id or '—'}  |  "
            f"{self._t('page.history.overview.model')}：{record.model or '—'}"
        )
        if record.error_summary:
            summary += f"\n{self._t('page.history.overview.error')}：{record.error_summary[:120]}"
        self._last_result_color = color
        self._result_lbl.setStyleSheet(self._summary_style(color))
        self._result_lbl.setText(summary)

    # ================================================================
    # 设备回调
    # ================================================================

    def _on_devices_changed(self, devices):
        if not devices:
            self._device_info_lbl.setText(self._t("page.device.no_device"))
            self._update_device_status(self._t("page.device.status.disconnected"), "#f85149")
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

        snapshot = self._make_device_readiness_snapshot(device_info)
        readiness_changed = snapshot != self._last_device_readiness_snapshot
        self._last_device_readiness_snapshot = snapshot

        if device_info is None:
            self._device_info_lbl.setText(self._t("page.dashboard.device_info.no_device"))
            self._update_device_status(self._t("page.dashboard.device_info.no_selected"), "#8b949e")
            # 清除镜像控件的设备绑定
            if self._mirror_label:
                self._mirror_label.set_device_id("")
            if readiness_changed:
                self._schedule_readiness_check(300)
            return
        # 更新镜像控件绑定的 ADB 设备 ID（用于鼠标 tap 转发）
        if self._mirror_label:
            self._mirror_label.set_device_id(device_info.device_id)
        lines = [f"<b>{device_info.display_name}</b>"]
        conn_type = {"usb": "USB", "wifi": "WiFi"}.get(
            device_info.connection_type,
            self._t("page.dashboard.device_info.conn_type.unknown")
        )
        lines.append(self._t("page.dashboard.device_info.conn_label", conn_type=conn_type))
        _kbd_raw = device_info.adb_keyboard_status
        if _kbd_raw:
            # 剥离旧数据中可能存在的 "ADB Keyboard " 前缀，仅保留状态词
            kbd = _kbd_raw[len("ADB Keyboard "):] if _kbd_raw.startswith("ADB Keyboard ") else _kbd_raw
        else:
            kbd = self._t("page.dashboard.device_info.kbd_enabled") if device_info.adb_keyboard_enabled \
                else self._t("page.dashboard.device_info.kbd_missing")
        lines.append(self._t("page.dashboard.device_info.kbd_label", status=kbd))
        self._device_info_lbl.setText("<br>".join(lines))
        self._device_info_lbl.setStyleSheet("font-size:12px; padding:4px;")

        if device_info.status == DeviceStatus.CONNECTED:
            self._update_device_status(device_info.device_id, "#3fb950")
        else:
            self._update_device_status(f"{device_info.device_id} ({device_info.status.value})", "#e3b341")

        self._update_mirror_aux_buttons()
        if readiness_changed:
            self._schedule_readiness_check(300)

    def _update_device_status(self, text: str, color: str):
        self._set_device_status(text, color)

    # ================================================================
    # 镜像回调
    # ================================================================

    def _on_mirror_state_changed(self, state: MirrorState):
        color = MIRROR_STATE_COLORS.get(state, "#8b949e")
        text = self._t(f"mirror.state.{state.value}")
        self._set_mirror_status(text, color)
        if state == MirrorState.RUNNING:
            self._btn_mirror_toggle.setText(self._t("page.dashboard.mirror.btn.stop_mirror"))
            self._btn_mirror_toggle.setProperty("variant", "danger")
        else:
            self._btn_mirror_toggle.setText(self._t("page.dashboard.mirror.btn.start_mirror"))
            self._btn_mirror_toggle.setProperty("variant", "subtle")
        self._apply_action_button_styles(mirror_running=(state == MirrorState.RUNNING))

    def _on_mirror_mode_changed(self, mode: MirrorMode):
        self._mirror_embedded = mode == MirrorMode.SCRCPY_EMBEDDED
        popup = self._mirror_popup_window if self._popup_window_active() else None
        if popup is not None:
            self._set_dashboard_mirror_detached(True)
        elif not self._mirror_prefers_new_window():
            self._set_dashboard_mirror_detached(False)

        if mode == MirrorMode.ADB_SCREENSHOT:
            if popup is not None:
                popup.show_label()
            elif self._mirror_stack and self._mirror_label:
                self._mirror_stack.setCurrentWidget(self._mirror_label)
        elif mode == MirrorMode.NONE:
            stopped_text = self._t("page.dashboard.mirror.stopped")
            self._mirror_placeholder.setText(stopped_text)
            if self._mirror_stack and self._mirror_placeholder:
                self._mirror_stack.setCurrentWidget(self._mirror_placeholder)
            if popup is not None:
                popup.set_placeholder_text(stopped_text)
                popup.show_placeholder()
        elif mode == MirrorMode.SCRCPY_EXTERNAL:
            external_text = self._t("page.dashboard.mirror.scrcpy_external")
            self._mirror_placeholder.setText(external_text)
            if self._mirror_stack and self._mirror_placeholder:
                self._mirror_stack.setCurrentWidget(self._mirror_placeholder)
            if popup is not None:
                popup.set_placeholder_text(external_text)
                popup.show_placeholder()
        elif mode == MirrorMode.SCRCPY_EMBEDDED:
            if popup is not None:
                popup.show_host()
            elif self._mirror_stack and self._mirror_host:
                self._mirror_stack.setCurrentWidget(self._mirror_host)
            self._sync_embedded_mirror_geometry()
        self._update_mirror_aux_buttons()

    def _on_mirror_frame(self, pixmap: QPixmap):
        """ADB 截图降级模式下收到帧"""
        if self._popup_window_active() and self._mirror_prefers_new_window():
            self._set_dashboard_mirror_detached(True)
            self._mirror_popup_window.show_frame(pixmap)
            return
        if self._mirror_stack and self._mirror_label:
            self._mirror_stack.setCurrentWidget(self._mirror_label)
        # MirrorLabel.set_raw_pixmap 内部负责自适应缩放（包括 resizeEvent 时重新缩放）
        self._mirror_label.set_raw_pixmap(pixmap)

    def _on_mirror_error(self, msg: str):
        self._append_log(self._t("page.dashboard.mirror.log.error", msg=msg))

    def _update_mirror_aux_buttons(self):
        btn = getattr(self, "_btn_mirror_paste_clipboard", None)
        if btn is None:
            return
        current_device_id = self._current_device_id()
        mirror_mode = self._mirror.mode if self._mirror else MirrorMode.NONE
        mirror_state = self._mirror.state if self._mirror else MirrorState.IDLE
        worker_busy = bool(self._mirror_clipboard_worker and self._mirror_clipboard_worker.isRunning())
        enabled = (
            bool(current_device_id)
            and mirror_mode == MirrorMode.SCRCPY_EXTERNAL
            and mirror_state == MirrorState.RUNNING
            and not worker_busy
        )
        btn.setEnabled(enabled)
        if worker_busy:
            btn.setText(self._t("page.dashboard.mirror.btn.pasting_clipboard"))
        else:
            btn.setText(self._t("page.dashboard.mirror.btn.paste_clipboard"))

    def _paste_clipboard_to_device_text(self, text: str):
        device_id = self._current_device_id()
        if not device_id:
            self._append_log(self._t("page.dashboard.mirror.log.no_device"))
            return
        if self._mirror_clipboard_worker and self._mirror_clipboard_worker.isRunning():
            return
        worker = _MirrorClipboardPasteWorker(device_id, text)
        worker.failed.connect(self._on_mirror_error)
        worker.succeeded.connect(
            lambda pasted_text: self._append_log(
                self._t(
                    "page.dashboard.mirror.log.clipboard_paste_done",
                    chars=len(pasted_text),
                )
            )
        )
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(self._on_mirror_clipboard_worker_finished)
        self._mirror_clipboard_worker = worker
        self._append_log(
            self._t(
                "page.dashboard.mirror.log.clipboard_paste_start",
                chars=len(text),
            )
        )
        self._update_mirror_aux_buttons()
        worker.start()

    def _on_mirror_clipboard_worker_finished(self):
        self._mirror_clipboard_worker = None
        self._update_mirror_aux_buttons()

    def _on_mirror_paste_clipboard(self):
        clipboard = QApplication.clipboard()
        text = clipboard.text() if clipboard is not None else ""
        if not text:
            self._on_mirror_error(self._t("page.dashboard.mirror.log.clipboard_empty_inline"))
            return
        self._paste_clipboard_to_device_text(text)

    def _on_mirror_window_created(self, hwnd: int):
        self._last_mirror_geometry_debug = None
        self._append_mirror_debug_log(
            self._t("page.dashboard.mirror.debug.window_embedded", hwnd=hwnd)
        )
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
        host, _container, _label, _popup = self._active_mirror_widgets()
        host = host or self._mirror_container
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
                    self._t(
                        "page.dashboard.mirror.debug.fit_rect",
                        x=rect.x(),
                        y=rect.y(),
                        w=rect.width(),
                        h=rect.height(),
                        device_w=device_size[0],
                        device_h=device_size[1],
                        dpr=scale_factor,
                        fit_x=fit_rect[0],
                        fit_y=fit_rect[1],
                        fit_w=fit_rect[2],
                        fit_h=fit_rect[3],
                        native_x=native_rect[0],
                        native_y=native_rect[1],
                        native_w=native_rect[2],
                        native_h=native_rect[3],
                    )
                )
            else:
                self._append_mirror_debug_log(
                    self._t(
                        "page.dashboard.mirror.debug.full_rect",
                        dpr=scale_factor,
                        native_x=native_rect[0],
                        native_y=native_rect[1],
                        native_w=native_rect[2],
                        native_h=native_rect[3],
                    )
                )

        self._mirror.resize_scrcpy_window(
            native_rect[0], native_rect[1], native_rect[2], native_rect[3]
        )

    def eventFilter(self, watched, event):
        popup_container = self._mirror_popup_window.container_widget() if self._mirror_popup_window else None
        popup_host = self._mirror_popup_window.host_widget() if self._mirror_popup_window else None
        if watched in (self._mirror_container, self._mirror_host, popup_container, popup_host) and event.type() in (QEvent.Resize, QEvent.Show):
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
        tp_hint = self._t(
            "page.dashboard.channel.hint.thirdparty_bracketed"
            if is_thirdparty
            else "page.dashboard.channel.hint.native_bracketed"
        )
        # 渠道下拉框显示名加上动态模型名后缀（便于区分同渠道不同模型）
        active = self._config.get_active_channel()
        active_id = active["id"] if active else "custom"
        display_model = model[:24] if len(model) > 24 else model
        if active_id != "custom":
            self._channel_combo.setItemText(
                self._channel_combo.currentIndex(),
                self._t(
                    "page.dashboard.channel.display.preset",
                    name=self._channel_name(active),
                    model=display_model,
                )
            )
        else:
            self._channel_combo.setItemText(
                self._channel_combo.currentIndex(),
                self._t("page.dashboard.channel.display.custom_with_model", model=display_model)
                if display_model and display_model != "—"
                else self._t("page.dashboard.channel.display.custom_plain")
            )
        self._channel_combo.setToolTip(
            self._t(
                "page.dashboard.channel.tooltip",
                base_url=base_url,
                model=model,
                mode_hint=tp_hint,
            )
        )
        self._refresh_channel_card()

    def on_page_activated(self):
        """页面激活时刷新状态"""
        self._sync_channel_combo()
        self._refresh_status_bar()
        self._refresh_workspace_overview()
        if (not self._readiness_results) or (time.monotonic() - self._last_readiness_check_at > 45):
            self._schedule_readiness_check(0)

    def shutdown(self):
        self._shutting_down = True
        self._close_mirror_popup_window(ignore_stop=True)
        if hasattr(self, "_readiness_refresh_timer"):
            self._readiness_refresh_timer.stop()
        if self._mirror_clipboard_worker:
            if self._mirror_clipboard_worker.isRunning():
                self._mirror_clipboard_worker.wait(8000)
            self._mirror_clipboard_worker.deleteLater()
            self._mirror_clipboard_worker = None
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

    def _toolbar_action_buttons(self) -> tuple[QPushButton, ...]:
        return tuple(
            btn for btn in (
                getattr(self, "_btn_start", None),
                getattr(self, "_btn_stop", None),
                getattr(self, "_btn_pause", None),
                getattr(self, "_btn_takeover", None),
            ) if btn is not None
        )

    def _sync_toolbar_action_button_widths(self) -> None:
        buttons = self._toolbar_action_buttons()
        if not buttons:
            return

        padding = 36
        min_width = 84
        max_width = max(
            min_width,
            max(btn.fontMetrics().horizontalAdvance(btn.text()) + padding for btn in buttons),
        )
        for btn in buttons:
            btn.setFixedWidth(max_width)

    def _apply_action_button_styles(self, task_state=None, mirror_running=None):
        if task_state is None:
            task_state = self._task.state if self._task else TaskState.IDLE
        if mirror_running is None:
            mirror_running = bool(self._mirror and self._mirror.is_running)

        self._sync_toolbar_action_button_widths()

        btn_specs = (
            (getattr(self, "_btn_start", None), btn_primary(self._theme_tokens)),
            (getattr(self, "_btn_stop", None), btn_danger(self._theme_tokens)),
            (
                getattr(self, "_btn_pause", None),
                btn_success(self._theme_tokens) if task_state == TaskState.PAUSED else btn_warning(self._theme_tokens),
            ),
            (getattr(self, "_btn_takeover", None), btn_warning(self._theme_tokens)),
            (getattr(self, "_btn_resume_exec", None), btn_primary(self._theme_tokens)),
            (getattr(self, "_btn_mirror_paste_clipboard", None), btn_subtle(self._theme_tokens, size="compact")),
            (
                getattr(self, "_btn_mirror_toggle", None),
                btn_danger(self._theme_tokens, size="compact") if mirror_running else btn_subtle(self._theme_tokens, size="compact"),
            ),
            (getattr(self, "_btn_open_diag", None), btn_subtle(self._theme_tokens, size="compact")),
            (getattr(self, "_btn_readiness_refresh", None), btn_subtle(self._theme_tokens, size="compact")),
            (getattr(self, "_btn_policy_manage", None), btn_primary(self._theme_tokens, size="compact")),
            (getattr(self, "_btn_channel_settings", None), btn_subtle(self._theme_tokens, size="compact")),
            (getattr(self, "_btn_readiness_diagnostics", None), btn_subtle(self._theme_tokens, size="compact")),
        )
        for btn, style in btn_specs:
            if btn:
                btn.setStyleSheet(style)
                btn.update()

    # ================================================================
    # i18n 支持
    # ================================================================

    def _t(self, key: str, **params) -> str:
        """便捷翻译方法，优先使用 services 中的 I18nManager，无则回退内置中文。"""
        i18n = getattr(self, "_i18n", None) or self._services.get("i18n")
        if i18n:
            return i18n.t(key, **params)
        # 回退：中文词典兜底
        try:
            from gui.i18n.locales.cn import CN
            tmpl = CN.get(key, f"[[{key}]]")
            return tmpl.format(**params) if params else tmpl
        except Exception:
            return f"[[{key}]]"

    def apply_i18n(self, i18n_manager) -> None:
        """PageI18nAdapter 回调 - 语言切换后立即更新工作台静态文案。"""
        self._i18n = i18n_manager
        _t = i18n_manager.t

        if hasattr(self, "_hero_title_lbl"):
            self._hero_title_lbl.setText(_t("page.dashboard.title"))
        if hasattr(self, "_workspace_section_lbl"):
            self._workspace_section_lbl.setText(_t("page.dashboard.workspace.section"))
        if hasattr(self, "_policy_title_lbl"):
            self._policy_title_lbl.setText(_t("page.dashboard.workspace.card.action_policy.title"))
        if hasattr(self, "_channel_title_lbl"):
            self._channel_title_lbl.setText(_t("page.dashboard.workspace.card.channel.title"))
        if hasattr(self, "_readiness_title_lbl"):
            self._readiness_title_lbl.setText(_t("page.dashboard.workspace.card.readiness.title"))
        if hasattr(self, "_btn_policy_manage"):
            self._btn_policy_manage.setText(_t("page.dashboard.workspace.card.action_policy.manage"))
        if hasattr(self, "_btn_channel_settings"):
            self._btn_channel_settings.setText(_t("page.dashboard.workspace.card.channel.cta"))
        if hasattr(self, "_btn_readiness_diagnostics"):
            self._btn_readiness_diagnostics.setText(_t("page.dashboard.workspace.card.readiness.cta"))

        if hasattr(self, "_task_input"):
            self._task_input.setPlaceholderText(_t("page.dashboard.toolbar.task_placeholder"))
        if hasattr(self, "_btn_start"):
            self._btn_start.setText(_t("page.dashboard.toolbar.btn.start"))
        if hasattr(self, "_btn_stop"):
            self._btn_stop.setText(_t("page.dashboard.toolbar.btn.stop"))
        if hasattr(self, "_btn_takeover"):
            self._btn_takeover.setText(_t("page.dashboard.toolbar.btn.takeover"))
        if hasattr(self, "_btn_pause"):
            task_state = self._task.state if self._task else None
            from gui.services.task_service import TaskState as _TS
            if task_state == _TS.PAUSED:
                self._btn_pause.setText(_t("page.dashboard.toolbar.btn.resume"))
            else:
                self._btn_pause.setText(_t("page.dashboard.toolbar.btn.pause"))
        self._sync_toolbar_action_button_widths()

        if self._task:
            self._on_task_state_changed(self._task.state)
        else:
            self._set_task_status(_t("state.idle"), "#8b949e")
        if self._device and self._device.selected_device:
            self._on_device_selected(self._device.selected_device)
        else:
            if hasattr(self, "_device_info_lbl"):
                self._device_info_lbl.setText(_t("page.dashboard.device_info.no_device"))
            self._set_device_status(_t("page.dashboard.device_info.no_selected"), "#8b949e")
        if hasattr(self, "_mirror_panel_group"):
            self._mirror_panel_group.setTitle(_t("page.dashboard.mirror.title"))
        if hasattr(self, "_mirror_open_in_new_window_check"):
            self._mirror_open_in_new_window_check.setText(_t("page.dashboard.mirror.open_in_new_window"))
        if hasattr(self, "_btn_mirror_paste_clipboard"):
            self._btn_mirror_paste_clipboard.setText(_t("page.dashboard.mirror.btn.paste_clipboard"))
        if hasattr(self, "_mirror_detached_placeholder"):
            self._mirror_detached_placeholder.setText(_t("page.dashboard.mirror.detached_placeholder"))
        self._update_mirror_popup_title()
        if hasattr(self, "_takeover_banner"):
            self._takeover_banner.setText(_t("page.dashboard.takeover.banner"))
        if hasattr(self, "_btn_resume_exec"):
            self._btn_resume_exec.setText(_t("page.dashboard.takeover.btn.restore"))
        if self._mirror:
            self._on_mirror_state_changed(self._mirror.state)
            self._on_mirror_mode_changed(self._mirror.mode)
        else:
            self._update_mirror_aux_buttons()
        if hasattr(self, "_channel_combo"):
            self._populate_channel_combo()
            self._refresh_status_bar()

        if hasattr(self, "_btn_readiness_refresh"):
            self._btn_readiness_refresh.setText(_t("page.dashboard.readiness.btn.refresh"))
        if hasattr(self, "_btn_open_diag"):
            self._btn_open_diag.setText(_t("shell.nav.diagnostics"))
        if self._readiness_summary:
            title, detail, action_hint = render_summary(self._readiness_summary, _t)
            summary_text = f"{title} · {detail}"
            tooltip = summary_text + (f"\n{action_hint}" if action_hint else "")
            self._set_readiness_state(summary_text, self._readiness_summary.semantic, tooltip)
        elif not self._readiness_results:
            self._set_readiness_state(_t("page.dashboard.readiness.checking"), self._last_readiness_state[1])

        if hasattr(self, "_log_panel_group"):
            self._log_panel_group.setTitle(_t("event.result_summary"))
        if hasattr(self, "_log_tabs"):
            self._log_tabs.setTabText(0, _t("page.dashboard.log.tab.log"))
            self._log_tabs.setTabText(1, _t("page.dashboard.log.tab.events"))
        if self._task and self._task.current_record and self._task.current_record.state in {
            TaskState.COMPLETED,
            TaskState.FAILED,
            TaskState.CANCELLED,
        }:
            self._on_task_finished(self._task.current_record)
        elif hasattr(self, "_result_lbl") and not self._last_result_color:
            self._result_lbl.setText(_t("page.dashboard.log.empty_result"))

        # 运行中追加指令栏翻译
        if hasattr(self, "_instruction_bar_title_lbl"):
            self._instruction_bar_title_lbl.setText(_t("page.dashboard.instruction.card.title"))
        if hasattr(self, "_btn_send_instruction"):
            self._btn_send_instruction.setText(_t("page.dashboard.instruction.btn.send"))
        if hasattr(self, "_btn_clear_instruction"):
            self._btn_clear_instruction.setText(_t("page.dashboard.instruction.btn.clear"))
        if hasattr(self, "_instruction_hint_lbl"):
            self._instruction_hint_lbl.setText(_t("page.dashboard.instruction.hint"))
        self._update_instruction_card_state()

        self._refresh_workspace_overview()