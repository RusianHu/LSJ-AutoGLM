# -*- coding: utf-8 -*-
"""诊断页 - 一键系统检查：ADB、设备、API、Python 依赖、GUI 环境"""

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gui.services.readiness_service import (
    ReadinessCheckResult,
    render_check_result,
    render_summary,
    run_readiness_checks,
    summarize_readiness,
)
from gui.theme.tokens import ThemeTokens
from gui.theme.themes import resolve_theme_tokens
from gui.theme.styles.buttons import btn_primary
from gui.theme.styles.lists import list_default


class _DiagWorker(QThread):
    """在后台线程中运行所有诊断检查"""

    result_ready = Signal(object)   # ReadinessCheckResult
    all_done = Signal(object)       # list[ReadinessCheckResult]

    def __init__(self, config_service=None, device_id: str = ""):
        super().__init__()
        self._config = config_service
        self._device_id = device_id
        self._stop_requested = False

    def request_stop(self):
        self._stop_requested = True

    def run(self):
        results = run_readiness_checks(self._config, device_id=self._device_id)
        emitted_results = []
        for result in results:
            if self._stop_requested:
                break
            emitted_results.append(result)
            self.result_ready.emit(result)
        self.all_done.emit(emitted_results)


class DiagnosticsPage(QWidget):
    """诊断页"""

    def __init__(self, services: dict, parent=None):
        super().__init__(parent)
        self._services = services
        self._config = services.get("config")
        self._worker: _DiagWorker | None = None
        self._last_results: list[ReadinessCheckResult] = []
        self._theme_mode = "dark"
        self._theme_tokens = resolve_theme_tokens(self._theme_mode)
        self._theme_vars = self._theme_tokens.to_legacy_dict()
        self._summary_kind = "idle"
        self._last_summary_state = (self._t("page.diagnostics.status.idle"), "idle")
        self._build_ui()
        self._apply_action_button_styles()

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
        from gui.i18n.locales.cn import CN
        template = CN.get(key, f"[[{key}]]")
        try:
            return template.format(**params) if params else template
        except Exception:
            return template

    def _current_device_id(self) -> str:
        device_service = self._services.get("device")
        if device_service and device_service.selected_device:
            return (device_service.selected_device.device_id or "").strip()
        if self._config:
            return (self._config.get("OPEN_AUTOGLM_DEVICE_ID") or "").strip()
        return ""

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)

        # 标题行
        header = QHBoxLayout()
        self._title_lbl = QLabel(self._t("page.diagnostics.title"))
        title = self._title_lbl
        title.setProperty("role", "pageTitle")
        header.addWidget(title)
        header.addStretch(1)

        self._btn_run = QPushButton(self._t("page.diagnostics.btn.run"))
        self._btn_run.setProperty("variant", "primary")
        self._btn_run.clicked.connect(self._on_run)
        header.addWidget(self._btn_run)
        root.addLayout(header)

        # 说明
        hint = QLabel(self._t("page.diagnostics.description"))
        self._hint_lbl = hint
        hint.setProperty("role", "subtle")
        hint.setStyleSheet("font-size:12px;")
        hint.setWordWrap(True)
        root.addWidget(hint)

        # 结果列表
        self._result_list = QListWidget()
        self._result_list.setProperty("surface", "console")
        root.addWidget(self._result_list, 1)

        # 摘要
        self._summary_lbl = QLabel(self._t("page.diagnostics.status.idle"))
        self._summary_lbl.setWordWrap(True)
        root.addWidget(self._summary_lbl)

    def _result_list_style(self) -> str:
        """诊断结果列表样式（委托至 styles/lists.py）。"""
        return list_default(self._theme_tokens)

    def _summary_style(self, state: str) -> str:
        v = self._theme_vars or {}
        if state == "success":
            color = v.get("success", "#3fb950")
            bg = v.get("success_bg", "#0f2d1a")
            border = v.get("success_border", "#3fb95040")
        elif state == "warning":
            color = v.get("warning", "#e3b341")
            bg = v.get("warning_bg", "#2d2200")
            border = v.get("warning_border", "#e3b34140")
        elif state == "error":
            color = v.get("danger", "#f85149")
            bg = v.get("danger_bg", "#3d1a1a")
            border = v.get("danger_border", "#f8514940")
        else:
            color = v.get("text_secondary", "#8b949e")
            bg = v.get("bg_secondary", "#161b22")
            border = v.get("border", "#30363d")
        return (
            f"background:{bg}; border:1px solid {border}; border-radius:8px; "
            f"padding:10px 16px; color:{color}; font-size:13px;"
            f"font-weight:{'700' if state in ('success', 'warning', 'error') else '400'};"
        )

    def _apply_action_button_styles(self):
        if hasattr(self, "_btn_run"):
            self._btn_run.setStyleSheet(btn_primary(self._theme_tokens))
            self._btn_run.update()

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
        """刷新静态外观：列表、摘要区背景。"""
        if self._theme_tokens is None:
            return
        if hasattr(self, "_result_list"):
            self._result_list.setStyleSheet(self._result_list_style())
        if hasattr(self, "_summary_lbl"):
            self._summary_lbl.setStyleSheet(self._summary_style(self._last_summary_state[1]))

    def refresh_theme_states(self) -> None:
        """刷新动态状态：按钮样式。"""
        self._apply_action_button_styles()

    def on_theme_changed(self, theme: str, theme_vars: dict):
        """[兼容] 旧版接口，由 PageThemeAdapter 在未实现新接口时调用。"""
        self._theme_mode = theme
        if getattr(self, "_theme_tokens", None) is None or self._theme_tokens.mode != theme:
            self._theme_tokens = resolve_theme_tokens(theme)
        self._theme_vars = theme_vars or self._theme_tokens.to_legacy_dict()
        self.refresh_theme_surfaces()
        self.refresh_theme_states()

    def _on_run(self):
        if self._worker and self._worker.isRunning():
            return
        if self._worker:
            self._worker.deleteLater()
            self._worker = None
        self._last_results = []
        self._result_list.clear()
        self._summary_kind = "running"
        self._last_summary_state = (self._t("page.diagnostics.status.running"), "warning")
        self._summary_lbl.setText(self._last_summary_state[0])
        self._summary_lbl.setStyleSheet(self._summary_style(self._last_summary_state[1]))
        self._btn_run.setEnabled(False)

        self._worker = _DiagWorker(self._config, device_id=self._current_device_id())
        self._worker.result_ready.connect(self._on_result)
        self._worker.all_done.connect(self._on_all_done)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _format_result_text(self, result: ReadinessCheckResult) -> str:
        if result.passed:
            icon = self._t("page.diagnostics.result.passed")
        elif result.blocking:
            icon = self._t("page.diagnostics.result.failed")
        else:
            icon = self._t("page.diagnostics.result.warning")

        label, detail, hint = render_check_result(result, self._t)
        hint_prefix = self._t("page.diagnostics.hint_prefix")
        lines = [f"  [{icon}]  {label}", f"         {detail}"]
        if hint:
            lines.append(f"         {hint_prefix}{hint}")
        return "\n".join(lines)

    def _result_color(self, result: ReadinessCheckResult) -> str:
        if result.passed:
            return self._theme_vars.get("success", "#3fb950")
        if result.blocking:
            return self._theme_vars.get("danger", "#f85149")
        return self._theme_vars.get("warning", "#e3b341")

    def _on_result(self, result: ReadinessCheckResult):
        self._last_results.append(result)
        item = QListWidgetItem(self._format_result_text(result))
        item.setForeground(QColor(self._result_color(result)))
        self._result_list.addItem(item)
        self._result_list.scrollToBottom()

    def _on_all_done(self, results):
        self._btn_run.setEnabled(True)
        if not results:
            self._summary_kind = "stopped"
            self._last_summary_state = (self._t("page.diagnostics.status.stopped"), "warning")
            self._summary_lbl.setText(self._last_summary_state[0])
            self._summary_lbl.setStyleSheet(self._summary_style(self._last_summary_state[1]))
            return

        summary = summarize_readiness(results)
        state = summary.semantic if summary.semantic in {"success", "warning", "error"} else "warning"
        title, detail, action_hint = render_summary(summary, self._t)
        message = f"{title}。{detail}"
        if action_hint:
            message += f"\n{action_hint}"
        self._summary_kind = "done"
        self._last_summary_state = (message, state)
        self._summary_lbl.setText(message)
        self._summary_lbl.setStyleSheet(self._summary_style(self._last_summary_state[1]))

    def _on_worker_finished(self):
        if self._worker:
            self._worker.deleteLater()
            self._worker = None

    def shutdown(self):
        if self._worker:
            if self._worker.isRunning():
                self._worker.request_stop()
                self._worker.wait(15000)
            if not self._worker.isRunning():
                self._worker.deleteLater()
                self._worker = None

    # ------------------------------------------------------------------
    # apply_i18n - 语言切换时由 PageI18nAdapter 调用
    # ------------------------------------------------------------------

    def apply_i18n(self, i18n_manager) -> None:
        """语言切换后重绘所有静态文案。"""
        self._title_lbl.setText(i18n_manager.t("page.diagnostics.title"))
        self._hint_lbl.setText(i18n_manager.t("page.diagnostics.description"))
        self._btn_run.setText(i18n_manager.t("page.diagnostics.btn.run"))

        if self._last_results:
            self._result_list.clear()
            for result in self._last_results:
                item = QListWidgetItem(self._format_result_text(result))
                item.setForeground(QColor(self._result_color(result)))
                self._result_list.addItem(item)
            summary = summarize_readiness(self._last_results)
            title, detail, action_hint = render_summary(summary, i18n_manager.t)
            state = summary.semantic if summary.semantic in {"success", "warning", "error"} else "warning"
            message = f"{title}。{detail}"
            if action_hint:
                message += f"\n{action_hint}"
            self._last_summary_state = (message, state)
            self._summary_lbl.setText(message)
            self._summary_lbl.setStyleSheet(self._summary_style(state))
            return

        _kind = getattr(self, "_summary_kind", "idle")
        state_text, state_sem = self._last_summary_state
        if _kind == "running":
            new_text = i18n_manager.t("page.diagnostics.status.running")
        elif _kind == "stopped":
            new_text = i18n_manager.t("page.diagnostics.status.stopped")
        else:
            new_text = i18n_manager.t("page.diagnostics.status.idle")
        self._last_summary_state = (new_text, state_sem)
        self._summary_lbl.setText(new_text)
        self._summary_lbl.setStyleSheet(self._summary_style(state_sem))

    def on_page_activated(self):
        if not self._last_results and not (self._worker and self._worker.isRunning()):
            self._on_run()
