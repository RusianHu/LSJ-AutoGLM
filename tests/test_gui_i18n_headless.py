# -*- coding: utf-8 -*-
"""
headless GUI i18n 回归测试。

覆盖目标：
- [`MainWindow`](gui/main_window.py:29) 壳层在配置语言变化后立即重绘
- [`DashboardPage`](gui/pages/dashboard_page.py:105) / [`HistoryPage`](gui/pages/history_page.py:52) 静态 UI 即时切换
- 原始日志与旧历史事件快照在切换语言后保持原文，不被重翻
- [`TaskService._add_event()`](gui/services/task_service.py:498) 会按事件生成时语言保存 `rendered_message/lang`

说明：
- 全部测试使用 `QT_QPA_PLATFORM=offscreen`，无需人工值守
- 不依赖真实 adb / scrcpy / 子进程，仅使用最小 stub service
"""

import os
import sys
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# 确保在仓库根目录下运行
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from PySide6.QtWidgets import QApplication, QWidget

from gui.i18n.manager import I18nManager
from gui.i18n.page_adapter import PageI18nAdapter
from gui.main_window import MainWindow
from gui.pages.dashboard_page import DashboardPage
from gui.pages.history_page import HistoryPage
from gui.services.mirror_service import MirrorMode, MirrorState
from gui.services.task_service import TaskService, TaskState


@pytest.fixture(scope="module")
def app():
    app = QApplication.instance() or QApplication([])
    app.setApplicationVersion("0.1")
    yield app


class DummySignal:
    def __init__(self):
        self._callbacks = []

    def connect(self, callback):
        self._callbacks.append(callback)

    def emit(self, *args, **kwargs):
        for callback in list(self._callbacks):
            callback(*args, **kwargs)


class DummyConfig:
    CHANNEL_PRESETS = [
        {
            "id": "modelscope",
            "name": "ModelScope",
            "use_thirdparty": False,
            "default_url": "https://api-inference.modelscope.cn/v1",
            "default_model": "ZhipuAI/AutoGLM-Phone-9B",
        },
        {
            "id": "custom",
            "name": "自定义",
            "use_thirdparty": False,
            "default_url": "",
            "default_model": "",
        },
    ]

    def __init__(self, lang: str = "cn"):
        self.config_changed = DummySignal()
        self.values = {
            "OPEN_AUTOGLM_LANG": lang,
            "OPEN_AUTOGLM_THEME": "dark",
            "OPEN_AUTOGLM_MODEL": "demo-model",
            "OPEN_AUTOGLM_BASE_URL": "https://example.invalid/v1",
            "OPEN_AUTOGLM_USE_THIRDPARTY_PROMPT": "false",
            "OPEN_AUTOGLM_DEVICE_ID": "",
        }
        self.active_channel = "modelscope"

    def get(self, key, default=""):
        return self.values.get(key, default)

    def get_active_channel(self):
        return next(
            (preset for preset in self.CHANNEL_PRESETS if preset["id"] == self.active_channel),
            None,
        )

    def get_preset_url(self, preset):
        return preset.get("default_url", "")

    def get_preset_model(self, preset):
        return preset.get("default_model", "")

    @staticmethod
    def _is_truthy(value):
        return str(value).strip().lower() in {"1", "true", "yes", "on"}


class DummyTask:
    def __init__(self):
        self.state_changed = DummySignal()
        self.log_line = DummySignal()
        self.event_added = DummySignal()
        self.task_finished = DummySignal()
        self.takeover_requested = DummySignal()
        self.stuck_detected = DummySignal()
        self.state = TaskState.IDLE
        self.current_record = None
        self.i18n = None

    def set_i18n(self, i18n):
        self.i18n = i18n

    def shutdown(self, timeout_ms=0):
        return None


class DummyDevice:
    def __init__(self):
        self.devices_changed = DummySignal()
        self.device_selected = DummySignal()
        self.selected_device = None
        self.devices = []

    def stop(self):
        return None


class DummyMirror:
    def __init__(self):
        self.state_changed = DummySignal()
        self.mode_changed = DummySignal()
        self.frame_ready = DummySignal()
        self.error_occurred = DummySignal()
        self.window_created = DummySignal()
        self.state = MirrorState.IDLE
        self.mode = MirrorMode.NONE
        self.is_running = False
        self.device_screen_size = None

    def shutdown(self):
        return None


class DummyHistory:
    def __init__(self):
        self.history_changed = DummySignal()
        self.record = {
            "task_id": "task-en-cn",
            "task_text": "打开微信",
            "state": "completed",
            "start_time": 1710000000,
            "end_time": 1710000005,
            "duration_str": "5s",
            "device_id": "device-1",
            "model": "demo-model",
            "max_steps": 20,
            "log_file": "gui_history/logs/demo.log",
            "error_summary": "",
            "events": [
                {
                    "type": "task_complete",
                    "time_str": "10:00:00",
                    "message": "任务完成，耗时 5s",
                    "rendered_message": "任务完成，耗时 5s",
                    "lang": "cn",
                    "message_key": "event.task_complete",
                    "message_params": {"duration": "5s"},
                }
            ],
        }

    def get_all(self, state_filter=""):
        if state_filter and self.record.get("state") != state_filter:
            return []
        return [dict(self.record)] if self.record.get("task_id") else []

    def get_record(self, task_id):
        if task_id == self.record.get("task_id"):
            return dict(self.record)
        return None

    def get_log_content(self, task_id):
        if task_id == self.record.get("task_id"):
            return "原始日志输出\n"
        return None

    def clear_all(self):
        self.record = {"task_id": "", "events": []}


class DummyPage(QWidget):
    def __init__(self):
        super().__init__()
        self.last_lang = None

    def apply_i18n(self, manager):
        self.last_lang = manager.get_language()

    def apply_theme_tokens(self, _tokens):
        return None

    def shutdown(self):
        return None


class TestHeadlessGuiI18n:
    def test_main_window_shell_updates_on_config_lang_change(self, app, monkeypatch):
        config = DummyConfig("cn")
        task = DummyTask()
        device = DummyDevice()
        mirror = DummyMirror()
        services = {
            "config": config,
            "task": task,
            "device": device,
            "history": None,
            "mirror": mirror,
        }

        def fake_init_pages(self):
            self._page_dashboard = DummyPage()
            self._page_device = DummyPage()
            self._page_history = DummyPage()
            self._page_settings = DummyPage()
            self._page_diag = DummyPage()
            self._pages = {
                "dashboard": self._page_dashboard,
                "device": self._page_device,
                "history": self._page_history,
                "settings": self._page_settings,
                "diag": self._page_diag,
            }
            for page in self._pages.values():
                self._stack.addWidget(page)
                self._page_adapter.register_page(page)
                self._i18n_adapter.register_page(page)
            self._stack.setCurrentWidget(self._page_dashboard)
            self._i18n_adapter.push_current()

        monkeypatch.setattr(MainWindow, "_init_pages", fake_init_pages)

        window = MainWindow(services)
        try:
            assert window.windowTitle() == "LSJ AutoGLM - 手机智能体控制台"
            assert "工作台" in window._nav_buttons["dashboard"].text()
            assert task.i18n is window._i18n_manager
            assert task.i18n.get_language() == "cn"

            config.values["OPEN_AUTOGLM_LANG"] = "en"
            config.config_changed.emit()

            assert window.windowTitle() == "LSJ AutoGLM - Phone Agent Console"
            assert "Workspace" in window._nav_buttons["dashboard"].text()
            assert task.i18n.get_language() == "en"
        finally:
            window.close()

    def test_dashboard_and_history_keep_old_content_while_switching_ui_language(self, app):
        i18n = I18nManager("cn")
        config = DummyConfig("cn")
        task = DummyTask()
        device = DummyDevice()
        mirror = DummyMirror()
        history = DummyHistory()
        services = {
            "config": config,
            "task": task,
            "device": device,
            "mirror": mirror,
            "history": history,
            "i18n": i18n,
            "navigate_to_page": lambda _key: None,
        }

        dashboard = DashboardPage(services)
        history_page = HistoryPage(services)
        adapter = PageI18nAdapter(i18n)
        adapter.register_page(dashboard)
        adapter.register_page(history_page)
        adapter.push_current()
        history_page._task_list.setCurrentRow(0)

        try:
            assert dashboard._btn_start.text() == "启动任务"
            assert dashboard._btn_readiness_refresh.text() == "重新检查"
            assert history_page._title_lbl.text() == "任务历史"
            assert "已完成" in history_page._task_list.item(0).text()
            assert "任务完成，耗时 5s" in history_page._event_list.item(0).text()

            dashboard._on_log_line("原始日志输出\n")
            old_log = dashboard._log_view.toPlainText()
            assert "原始日志输出" in old_log

            i18n.set_language("en")

            assert dashboard._btn_start.text() == "Run Task"
            assert dashboard._btn_readiness_refresh.text() == "Recheck"
            assert "Model:" in dashboard._channel_combo.toolTip()
            assert history_page._title_lbl.text() == "Task History"
            assert "Completed" in history_page._task_list.item(0).text()
            # 旧历史事件保持生成时快照，不因当前 GUI 语言变化而重翻
            assert "任务完成，耗时 5s" in history_page._event_list.item(0).text()
            # 原始日志保持原文
            assert dashboard._log_view.toPlainText() == old_log

            dashboard._on_event_added(
                {
                    "time_str": "10:00:01",
                    "type": "task_complete",
                    "message": "fallback",
                    "rendered_message": "Task completed in 5s",
                }
            )
            assert "Task completed in 5s" in dashboard._event_list.item(0).text()
        finally:
            dashboard.close()
            history_page.close()

    def test_task_add_event_snapshots_language_at_creation_time(self):
        svc = TaskService.__new__(TaskService)
        svc._current_record = SimpleNamespace(events=[])
        emitted = []
        svc.event_added = SimpleNamespace(emit=lambda evt: emitted.append(evt))
        svc._i18n = I18nManager("cn")

        TaskService._add_event(
            svc,
            "task_complete",
            "任务完成，耗时 3s",
            message_key="event.task_complete",
            message_params={"duration": "3s"},
        )
        svc._i18n.set_language("en")
        TaskService._add_event(
            svc,
            "task_complete",
            "任务完成，耗时 4s",
            message_key="event.task_complete",
            message_params={"duration": "4s"},
        )

        first, second = emitted
        assert first["lang"] == "cn"
        assert first["rendered_message"] == "任务完成，耗时 3s"
        assert second["lang"] == "en"
        assert second["rendered_message"] == "Task completed in 4s"
        assert svc._current_record.events[0]["lang"] == "cn"
        assert svc._current_record.events[1]["lang"] == "en"
