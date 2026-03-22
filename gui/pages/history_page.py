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

from gui.theme.tokens import ThemeTokens
from gui.theme.themes import resolve_theme_tokens
from gui.theme.styles.buttons import btn_danger, btn_subtle
from gui.theme.styles.lists import list_console, list_event
from gui.theme.styles.logs import log_console


STATE_COLOR = {
    "completed": "#3fb950",
    "failed":    "#f85149",
    "cancelled": "#8b949e",
    "running":   "#e3b341",
    "paused":    "#e3b341",
}

class HistoryPage(QWidget):
    """历史页"""

    def __init__(self, services: dict, parent=None):
        super().__init__(parent)
        self._services = services
        self._history = services.get("history")
        self._current_record: dict = {}
        self._theme_mode = "dark"
        self._theme_tokens = resolve_theme_tokens(self._theme_mode)
        self._theme_vars = self._theme_tokens.to_legacy_dict()
        self._build_ui()
        self._apply_action_button_styles()
        self._connect_signals()
        self._load_history()

    # ------------------------------------------------------------------
    # i18n 辅助
    # ------------------------------------------------------------------

    def _t(self, key: str, **params) -> str:
        """便捷翻译方法；优先使用 services 中的 I18nManager，无则回退内置中文。"""
        i18n = self._services.get("i18n")
        if i18n is not None:
            try:
                return i18n.t(key, **params)
            except Exception:
                pass
        # 内置中文回退
        from gui.i18n.locales.cn import CN
        template = CN.get(key, f"[[{key}]]")
        try:
            return template.format(**params) if params else template
        except Exception:
            return template

    # ------------------------------------------------------------------
    # 构建 UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        # 标题行
        header = QHBoxLayout()
        self._title_lbl = QLabel(self._t("page.history.title"))
        self._title_lbl.setProperty("role", "pageTitle")
        header.addWidget(self._title_lbl)
        header.addStretch(1)

        # 筛选
        self._filter_label = QLabel(self._t("page.history.filter.label"))
        header.addWidget(self._filter_label)
        self._filter_combo = QComboBox()
        self._filter_combo.addItems([
            self._t("page.history.filter.all"),
            self._t("page.history.filter.completed"),
            self._t("page.history.filter.failed"),
            self._t("page.history.filter.cancelled"),
        ])
        self._filter_combo.setFixedWidth(100)
        self._filter_combo.currentIndexChanged.connect(self._load_history)
        header.addWidget(self._filter_combo)

        self._btn_refresh = QPushButton(self._t("page.history.btn.refresh"))
        self._btn_refresh.setFixedWidth(64)
        self._btn_refresh.setProperty("variant", "subtle")
        self._btn_refresh.clicked.connect(self._load_history)
        header.addWidget(self._btn_refresh)

        self._btn_clear = QPushButton(self._t("page.history.btn.clear_all"))
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
        self._detail_tabs.addTab(self._overview_widget, self._t("page.history.tab.overview"))

        # 原始日志 tab
        self._log_view = QPlainTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setProperty("surface", "console")
        self._detail_tabs.addTab(self._log_view, self._t("page.history.tab.log"))

        # 事件时间线 tab
        self._event_list = QListWidget()
        self._event_list.setProperty("surface", "console")
        self._detail_tabs.addTab(self._event_list, self._t("page.history.tab.events"))

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

        # 保存行 label 引用以供 apply_i18n() 更新
        self._ov_row_labels: list[tuple[str, QLabel]] = []
        for key, val_lbl in [
            ("page.history.overview.task",       self._ov_task),
            ("page.history.overview.state",      self._ov_state),
            ("page.history.overview.start_time", self._ov_start),
            ("page.history.overview.end_time",   self._ov_end),
            ("page.history.overview.duration",   self._ov_dur),
            ("page.history.overview.device",     self._ov_device),
            ("page.history.overview.model",      self._ov_model),
            ("page.history.overview.max_steps",  self._ov_steps),
            ("page.history.overview.log_file",   self._ov_log),
            ("page.history.overview.error",      self._ov_error),
        ]:
            lbl = QLabel(self._t(key))
            lbl.setProperty("role", "statusMeta")
            lbl.setStyleSheet("min-width:80px;")
            val_lbl.setStyleSheet("font-size:12px;")
            val_lbl.setWordWrap(True)
            h = QHBoxLayout()
            h.addWidget(lbl)
            h.addWidget(val_lbl, 1)
            layout.addLayout(h)
            self._ov_row_labels.append((key, lbl))

        layout.addStretch(1)
        return w

    def _console_list_style(self) -> str:
        """任务历史列表样式（委托至 styles/lists.py）。"""
        return list_console(self._theme_tokens)

    def _event_list_style(self) -> str:
        """事件列表样式（委托至 styles/lists.py）。"""
        return list_event(self._theme_tokens)

    def _log_view_style(self) -> str:
        """日志查看区样式（委托至 styles/logs.py）。"""
        return log_console(self._theme_tokens)

    def _apply_action_button_styles(self):
        for btn, style in (
            (getattr(self, "_btn_refresh", None), btn_subtle(self._theme_tokens)),
            (getattr(self, "_btn_clear", None), btn_danger(self._theme_tokens)),
        ):
            if btn:
                btn.setStyleSheet(style)
                btn.update()

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
        """刷新静态外观：列表、日志区背景。"""
        if self._theme_tokens is None:
            return
        if hasattr(self, "_task_list"):
            self._task_list.setStyleSheet(self._console_list_style())
        if hasattr(self, "_event_list"):
            self._event_list.setStyleSheet(self._event_list_style())
        if hasattr(self, "_log_view"):
            self._log_view.setStyleSheet(self._log_view_style())
        self._apply_action_button_styles()

    def refresh_theme_states(self) -> None:
        """刷新动态状态（当前无状态色需要刷新）。"""
        pass

    def on_theme_changed(self, theme: str, theme_vars: dict):
        """旧版主题接口，转发给新版。"""
        tokens = resolve_theme_tokens(theme)
        self.apply_theme_tokens(tokens)

    # ------------------------------------------------------------------
    # 时间 / 持续时间 格式化
    # ------------------------------------------------------------------

    @staticmethod
    def _format_time_text(value, fallback: str = "—") -> str:
        if value in (None, "", 0, 0.0):
            return fallback
        try:
            ts = float(value)
            if ts <= 0:
                return fallback
            return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
        except (TypeError, ValueError):
            return str(value) if value else fallback

    @staticmethod
    def _format_duration_text(start_time, end_time) -> str:
        try:
            start_ts = float(start_time)
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
        v = rec.get("start_time_str") or self._format_time_text(rec.get("start_time"))
        return v or "—"

    def _record_end_text(self, rec: dict) -> str:
        v = rec.get("end_time_str") or self._format_time_text(rec.get("end_time"))
        return v or "—"

    def _record_duration_text(self, rec: dict) -> str:
        v = rec.get("duration_str") or self._format_duration_text(
            rec.get("start_time"), rec.get("end_time")
        )
        return v or "—"

    # ------------------------------------------------------------------
    # 信号连接
    # ------------------------------------------------------------------

    def _connect_signals(self):
        if self._history:
            self._history.history_changed.connect(self._load_history)

    def _clear_detail_views(self):
        self._current_record = {}
        for lbl in (self._ov_task, self._ov_state, self._ov_start, self._ov_end,
                    self._ov_dur, self._ov_device, self._ov_model, self._ov_steps,
                    self._ov_error, self._ov_log):
            lbl.setText("—")
        self._log_view.clear()
        self._event_list.clear()

    # ------------------------------------------------------------------
    # 加载历史
    # ------------------------------------------------------------------

    def _load_history(self):
        # 筛选索引：0=全部, 1=已完成, 2=失败, 3=已取消
        filter_idx = self._filter_combo.currentIndex()
        filter_key_map = {
            0: "",
            1: "completed",
            2: "failed",
            3: "cancelled",
        }
        state_filter = filter_key_map.get(filter_idx, "")

        records = self._history.get_all(state_filter) if self._history else []
        selected_task_id = self._current_record.get("task_id")

        self._task_list.clear()
        selected_row = -1
        for row, rec in enumerate(records):
            state = rec.get("state", "")
            color = STATE_COLOR.get(state, "#8b949e")
            # 通过 i18n 翻译状态标签
            state_key = f"history.state.{state}" if state else "history.state.unknown"
            label = self._t(state_key)
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
        if row < 0 or not self._history:
            return
        item = self._task_list.item(row)
        if not item:
            return
        task_id = item.data(Qt.UserRole)
        record = self._history.get_record(task_id) if task_id else None
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
        # 通过 i18n 翻译状态标签
        state_key = f"history.state.{state}" if state else "history.state.unknown"
        label = self._t(state_key)

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
            self._log_view.setPlainText(self._t("page.history.empty.log"))

    def _show_events(self, task_id: str):
        self._event_list.clear()
        if not self._history:
            return
        record = self._history.get_record(task_id)
        events = record.get("events", []) if record else []
        for evt in reversed(events):
            # 优先使用 rendered_message（已翻译），回退到 message
            msg = evt.get("rendered_message") or evt.get("message", "")
            text = f"[{evt.get('time_str', '')}]  {msg}"
            item = QListWidgetItem(text)
            etype = evt.get("type", "")
            color_map = {
                "task_complete":    "#3fb950",
                "task_failed":      "#f85149",
                "error":            "#f85149",
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
            self,
            self._t("page.history.dialog.clear.title"),
            self._t("page.history.dialog.clear.text"),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes and self._history:
            self._history.clear_all()
            self._clear_detail_views()

    # ------------------------------------------------------------------
    # apply_i18n - 语言切换时由 PageI18nAdapter 调用
    # ------------------------------------------------------------------

    def apply_i18n(self, i18n_manager) -> None:
        """语言切换后重绘所有静态文案。"""
        # 标题 / 工具栏
        self._title_lbl.setText(i18n_manager.t("page.history.title"))
        self._filter_label.setText(i18n_manager.t("page.history.filter.label"))
        self._btn_refresh.setText(i18n_manager.t("page.history.btn.refresh"))
        self._btn_clear.setText(i18n_manager.t("page.history.btn.clear_all"))

        # 筛选下拉（重建选项，保持当前索引）
        cur = self._filter_combo.currentIndex()
        self._filter_combo.blockSignals(True)
        self._filter_combo.clear()
        self._filter_combo.addItems([
            i18n_manager.t("page.history.filter.all"),
            i18n_manager.t("page.history.filter.completed"),
            i18n_manager.t("page.history.filter.failed"),
            i18n_manager.t("page.history.filter.cancelled"),
        ])
        self._filter_combo.setCurrentIndex(cur)
        self._filter_combo.blockSignals(False)

        # 详情标签页标题
        self._detail_tabs.setTabText(0, i18n_manager.t("page.history.tab.overview"))
        self._detail_tabs.setTabText(1, i18n_manager.t("page.history.tab.log"))
        self._detail_tabs.setTabText(2, i18n_manager.t("page.history.tab.events"))

        # 概览行标签
        ov_keys = [
            "page.history.overview.task",
            "page.history.overview.state",
            "page.history.overview.start_time",
            "page.history.overview.end_time",
            "page.history.overview.duration",
            "page.history.overview.device",
            "page.history.overview.model",
            "page.history.overview.max_steps",
            "page.history.overview.log_file",
            "page.history.overview.error",
        ]
        for (key, lbl), new_key in zip(self._ov_row_labels, ov_keys):
            lbl.setText(i18n_manager.t(new_key))

        # 刷新列表（状态标签需重新翻译）
        self._load_history()
        # 若有当前选中记录，刷新概览
        if self._current_record:
            self._show_overview(self._current_record)

    def on_page_activated(self):
        self._load_history()
