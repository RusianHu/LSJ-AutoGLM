# -*- coding: utf-8 -*-
"""历史页 - 任务历史列表、日志查看、关键事件与错误上下文"""

import time

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from gui.utils.button_styles import danger_btn_style, subtle_btn_style


STATE_COLOR = {
    "completed": "#3fb950",
    "failed":    "#f85149",
    "cancelled": "#8b949e",
    "running":   "#e3b341",
    "paused":    "#e3b341",
}

STATE_LABEL = {
    "completed": "已完成",
    "failed":    "失败",
    "cancelled": "已取消",
    "running":   "运行中",
    "paused":    "已暂停",
    "idle":      "空闲",
}


class HistoryPage(QWidget):
    """历史页"""

    def __init__(self, services: dict, parent=None):
        super().__init__(parent)
        self._services = services
        self._history = services.get("history")
        self._current_record: dict = {}
        self._theme_mode = "dark"
        self._theme_vars = {}
        self._build_ui()
        self._apply_action_button_styles()
        self._connect_signals()
        self._load_history()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        # 标题行
        header = QHBoxLayout()
        title = QLabel("任务历史")
        title.setProperty("role", "pageTitle")
        header.addWidget(title)
        header.addStretch(1)

        # 筛选
        header.addWidget(QLabel("筛选:"))
        self._filter_combo = QComboBox()
        self._filter_combo.addItems(["全部", "已完成", "失败", "已取消"])
        self._filter_combo.setFixedWidth(100)
        self._filter_combo.currentIndexChanged.connect(self._load_history)
        header.addWidget(self._filter_combo)

        self._btn_refresh = QPushButton("刷新")
        self._btn_refresh.setFixedWidth(64)
        self._btn_refresh.setProperty("variant", "subtle")
        self._btn_refresh.clicked.connect(self._load_history)
        header.addWidget(self._btn_refresh)

        self._btn_clear = QPushButton("清空全部")
        self._btn_clear.setFixedWidth(80)
        self._btn_clear.setProperty("variant", "danger")
        self._btn_clear.clicked.connect(self._on_clear_all)
        header.addWidget(self._btn_clear)
        root.addLayout(header)

        # 主体 Splitter
        splitter = QSplitter(Qt.Horizontal)

        # 左：任务列表
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        self._task_list = QListWidget()
        self._task_list.setProperty("surface", "console")
        self._task_list.currentRowChanged.connect(self._on_task_selected)
        left_layout.addWidget(self._task_list, 1)
        splitter.addWidget(left)

        # 右：详情
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        self._detail_tabs = QTabWidget()
        self._detail_tabs.setDocumentMode(True)

        # 概览 tab
        self._overview_widget = self._build_overview_tab()
        self._detail_tabs.addTab(self._overview_widget, "概览")

        # 原始日志 tab
        self._log_view = QPlainTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setProperty("surface", "console")
        self._detail_tabs.addTab(self._log_view, "原始日志")

        # 事件时间线 tab
        self._event_list = QListWidget()
        self._event_list.setProperty("surface", "console")
        self._detail_tabs.addTab(self._event_list, "事件时间线")

        right_layout.addWidget(self._detail_tabs, 1)
        splitter.addWidget(right)
        splitter.setSizes([340, 700])
        root.addWidget(splitter, 1)

    def _build_overview_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        def row(key: str, value_lbl: QLabel) -> QHBoxLayout:
            h = QHBoxLayout()
            k = QLabel(key)
            k.setProperty("role", "statusMeta")
            k.setStyleSheet("min-width:80px;")
            value_lbl.setStyleSheet("font-size:12px;")
            value_lbl.setWordWrap(True)
            h.addWidget(k)
            h.addWidget(value_lbl, 1)
            return h

        self._ov_task   = QLabel("—")
        self._ov_state  = QLabel("—")
        self._ov_start  = QLabel("—")
        self._ov_end    = QLabel("—")
        self._ov_dur    = QLabel("—")
        self._ov_device = QLabel("—")
        self._ov_model  = QLabel("—")
        self._ov_steps  = QLabel("—")
        self._ov_error  = QLabel("—")
        self._ov_log    = QLabel("—")

        for k, v in [
            ("任务", self._ov_task),
            ("状态", self._ov_state),
            ("开始", self._ov_start),
            ("结束", self._ov_end),
            ("耗时", self._ov_dur),
            ("设备", self._ov_device),
            ("模型", self._ov_model),
            ("最大步数", self._ov_steps),
            ("日志文件", self._ov_log),
            ("错误摘要", self._ov_error),
        ]:
            layout.addLayout(row(k, v))

        layout.addStretch(1)
        return w

    def _console_list_style(self) -> str:
        v = self._theme_vars or {}
        return (
            "QListWidget {"
            f"background:{v.get('bg_console', '#0a0f18')}; border:1px solid {v.get('border', '#30363d')};"
            f"border-radius:8px; color:{v.get('text_primary', '#c9d1d9')}; font-size:12px; padding:4px;"
            "}"
            "QListWidget::item {"
            f"padding:8px 10px; border-radius:4px; border-bottom:1px solid {v.get('bg_elevated', '#1b2432')};"
            "}"
            f"QListWidget::item:selected {{ background:{v.get('selection_bg', '#264f78')}; }}"
            f"QListWidget::item:hover {{ background:{v.get('accent_soft', 'rgba(79, 140, 255, 0.16)')}; }}"
        )

    def _event_list_style(self) -> str:
        v = self._theme_vars or {}
        return (
            "QListWidget {"
            f"background:{v.get('bg_console', '#0a0f18')}; border:1px solid {v.get('border', '#30363d')};"
            f"border-radius:8px; color:{v.get('text_primary', '#c9d1d9')}; font-size:12px; padding:4px;"
            "}"
            "QListWidget::item {"
            f"padding:5px 8px; border-bottom:1px solid {v.get('bg_elevated', '#1b2432')};"
            "}"
            f"QListWidget::item:selected {{ background:{v.get('selection_bg', '#264f78')}; }}"
        )

    def _log_view_style(self) -> str:
        v = self._theme_vars or {}
        return (
            "QPlainTextEdit {"
            f"background:{v.get('bg_console', '#0a0f18')}; color:{v.get('text_primary', '#c9d1d9')};"
            f"border:1px solid {v.get('border', '#30363d')}; border-radius:8px;"
            "font-family:'Consolas','Courier New',monospace; font-size:12px; padding:8px;"
            "}"
        )

    def _apply_action_button_styles(self):
        for btn, style in (
            (getattr(self, "_btn_refresh", None), subtle_btn_style(self._theme_mode, self._theme_vars)),
            (getattr(self, "_btn_clear", None), danger_btn_style(self._theme_mode, self._theme_vars)),
        ):
            if btn:
                btn.setStyleSheet(style)
                btn.update()

    def on_theme_changed(self, theme: str, theme_vars: dict):
        self._theme_mode = theme
        self._theme_vars = theme_vars or {}
        self._apply_action_button_styles()
        if hasattr(self, "_task_list"):
            self._task_list.setStyleSheet(self._console_list_style())
        if hasattr(self, "_log_view"):
            self._log_view.setStyleSheet(self._log_view_style())
        if hasattr(self, "_event_list"):
            self._event_list.setStyleSheet(self._event_list_style())

    def _connect_signals(self):
        if self._history:
            self._history.history_changed.connect(self._load_history)

    @staticmethod
    def _format_time_text(value, fallback: str = "—") -> str:
        if value in (None, "", 0, 0.0):
            return fallback
        try:
            ts = float(value)
        except (TypeError, ValueError):
            return str(value)
        if ts <= 0:
            return fallback
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))

    @staticmethod
    def _format_duration_text(start_time, end_time) -> str:
        try:
            start_ts = float(start_time or 0)
        except (TypeError, ValueError):
            return "—"
        if start_ts <= 0:
            return "—"
        try:
            end_ts = float(end_time) if end_time else time.time()
        except (TypeError, ValueError):
            end_ts = time.time()
        secs = max(0, int(end_ts - start_ts))
        if secs < 60:
            return f"{secs}s"
        return f"{secs // 60}m{secs % 60}s"

    def _record_start_text(self, rec: dict) -> str:
        return rec.get("start_time_str") or self._format_time_text(rec.get("start_time"))

    def _record_end_text(self, rec: dict) -> str:
        return rec.get("end_time_str") or self._format_time_text(rec.get("end_time"))

    def _record_duration_text(self, rec: dict) -> str:
        return rec.get("duration_str") or self._format_duration_text(
            rec.get("start_time"), rec.get("end_time")
        )

    def _clear_detail_views(self):
        self._current_record = {}
        for lbl in (
            self._ov_task,
            self._ov_state,
            self._ov_start,
            self._ov_end,
            self._ov_dur,
            self._ov_device,
            self._ov_model,
            self._ov_steps,
            self._ov_error,
            self._ov_log,
        ):
            lbl.setText("—")
        self._log_view.clear()
        self._event_list.clear()

    def _load_history(self):
        filter_map = {
            "全部": None,
            "已完成": "completed",
            "失败": "failed",
            "已取消": "cancelled",
        }
        filter_text = self._filter_combo.currentText()
        state_filter = filter_map.get(filter_text)

        records = self._history.get_all(state_filter) if self._history else []
        selected_task_id = self._current_record.get("task_id")

        self._task_list.clear()
        selected_row = -1
        for row, rec in enumerate(records):
            state = rec.get("state", "")
            color = STATE_COLOR.get(state, "#8b949e")
            label = STATE_LABEL.get(state, state)
            task_text = rec.get("task_text", "")[:40]
            start = self._record_start_text(rec)
            dur = self._record_duration_text(rec)
            text = f"[{label}]  {task_text}\n{start}  {dur}"
            item = QListWidgetItem(text)
            item.setForeground(QColor(color))
            item.setData(Qt.UserRole, rec.get("task_id"))
            self._task_list.addItem(item)
            if rec.get("task_id") == selected_task_id:
                selected_row = row

        if self._task_list.count() == 0:
            self._clear_detail_views()
            return

        if selected_row >= 0:
            self._task_list.setCurrentRow(selected_row)
        elif self._task_list.currentRow() < 0:
            self._task_list.setCurrentRow(0)

    def _on_task_selected(self, row: int):
        item = self._task_list.item(row)
        if not item:
            self._clear_detail_views()
            return
        task_id = item.data(Qt.UserRole)
        if not task_id or not self._history:
            self._clear_detail_views()
            return
        record = self._history.get_record(task_id)
        if not record:
            self._clear_detail_views()
            return
        self._current_record = record
        self._show_overview(record)
        self._show_log(task_id)
        self._show_events(task_id)

    def _show_overview(self, rec: dict):
        state = rec.get("state", "")
        color = STATE_COLOR.get(state, "#8b949e")
        label = STATE_LABEL.get(state, state)

        self._ov_task.setText(rec.get("task_text", "—"))
        self._ov_state.setText(
            f"<span style='color:{color}'>{label}</span>"
        )
        self._ov_start.setText(self._record_start_text(rec))
        self._ov_end.setText(self._record_end_text(rec))
        self._ov_dur.setText(self._record_duration_text(rec))
        self._ov_device.setText(rec.get("device_id", "—") or "—")
        self._ov_model.setText(rec.get("model", "—") or "—")
        self._ov_steps.setText(str(rec.get("max_steps", "—")))
        self._ov_log.setText(rec.get("log_file", "—") or "—")
        err = rec.get("error_summary", "") or "—"
        err_color = "#f85149" if err != "—" else "#8b949e"
        self._ov_error.setText(f"<span style='color:{err_color}'>{err}</span>")

    def _show_log(self, task_id: str):
        self._log_view.clear()
        if not self._history:
            return
        content = self._history.get_log_content(task_id)
        if content:
            self._log_view.setPlainText(content)
        else:
            self._log_view.setPlainText("（无日志文件）")

    def _show_events(self, task_id: str):
        self._event_list.clear()
        if not self._history:
            return
        record = self._history.get_record(task_id)
        events = record.get("events", []) if record else []
        for evt in reversed(events):
            text = f"[{evt.get('time_str', '')}]  {evt.get('message', '')}"
            item = QListWidgetItem(text)
            etype = evt.get("type", "")
            color_map = {
                "task_complete": "#3fb950",
                "task_failed":   "#f85149",
                "error":         "#f85149",
                "takeover_request": "#e3b341",
                "stuck_detected":   "#f0883e",
            }
            c = color_map.get(etype)
            if c:
                item.setForeground(QColor(c))
            self._event_list.addItem(item)

    def _on_clear_all(self):
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "确认清空",
            "确定要清空全部历史记录吗？（日志文件不会被删除）",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes and self._history:
            self._history.clear_all()
            self._clear_detail_views()

    def on_page_activated(self):
        self._load_history()
