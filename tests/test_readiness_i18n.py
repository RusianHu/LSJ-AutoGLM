# -*- coding: utf-8 -*-
"""
测试 readiness i18n 渲染与 TaskService 结构化事件推断。

目标：
- 覆盖 [`render_check_result()`](gui/services/readiness_service.py:103) 的 key/params 翻译路径
- 覆盖 [`render_summary()`](gui/services/readiness_service.py:130) 与 [`collect_blocking_labels()`](gui/services/readiness_service.py:942)
- 覆盖 [`summarize_readiness()`](gui/services/readiness_service.py:864) 的三种摘要分支
- 覆盖 [`TaskService._infer_events_from_log()`](gui/services/task_service.py:329) 的结构化事件与错误回退行为

全部测试均为纯 Python 逻辑测试，不依赖 QApplication。
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from gui.services.readiness_service import (
    ReadinessCheckResult,
    ReadinessSummary,
    collect_blocking_labels,
    render_check_result,
    render_summary,
    summarize_readiness,
)
from gui.services.config_service import ConfigService
from gui.services.task_service import TaskService


class TestReadinessRenderHelpers:
    """验证 readiness 结构化结果的渲染行为。"""

    @staticmethod
    def _translator(key: str, **params) -> str:
        templates = {
            "readiness.devices.label": "设备连接",
            "readiness.devices.detail.missing": "未检测到设备：{device}",
            "readiness.devices.hint.reconnect": "请重新连接 {device}",
            "readiness.api_key.label": "API Key",
            "readiness.api_key.detail.missing": "{channel} 未配置 Key",
            "readiness.api_key.hint.fill": "请填写 {channel} 的 API Key",
            "readiness.summary.blocking.title": "仍有 {count} 个关键项未就绪",
            "readiness.summary.blocking.detail": "关键项：{labels}",
            "readiness.summary.blocking.hint": "请先完成关键项修复",
            "readiness.summary.warning.title": "仍有 {count} 个建议项可优化",
            "readiness.summary.warning.detail": "建议关注：{labels}",
            "readiness.summary.warning.hint": "可以直接继续",
            "readiness.summary.success.title": "环境检查通过",
            "readiness.summary.success.detail": "所有关键项均已就绪",
            "readiness.summary.success.hint": "可进入诊断页查看明细",
        }
        template = templates.get(key, f"[[{key}]]")
        return template.format(**params) if params else template

    def test_render_check_result_uses_keys_and_params(self):
        result = ReadinessCheckResult(
            key="devices",
            label="设备连接",
            passed=False,
            detail="未检测到设备",
            blocking=True,
            semantic="error",
            hint="请重新连接设备",
            label_key="readiness.devices.label",
            detail_key="readiness.devices.detail.missing",
            detail_params={"device": "emulator-5554"},
            hint_key="readiness.devices.hint.reconnect",
            hint_params={"device": "emulator-5554"},
        )

        label, detail, hint = render_check_result(result, self._translator)

        assert label == "设备连接"
        assert detail == "未检测到设备：emulator-5554"
        assert hint == "请重新连接 emulator-5554"

    def test_render_check_result_falls_back_when_translator_fails(self):
        def bad_translator(_key: str, **_params) -> str:
            raise RuntimeError("boom")

        result = ReadinessCheckResult(
            key="api_key",
            label="API Key",
            passed=False,
            detail="渠道未配置 Key",
            blocking=True,
            semantic="error",
            hint="请填写 API Key",
            label_key="readiness.api_key.label",
            detail_key="readiness.api_key.detail.missing",
            detail_params={"channel": "ModelScope"},
            hint_key="readiness.api_key.hint.fill",
            hint_params={"channel": "ModelScope"},
        )

        label, detail, hint = render_check_result(result, bad_translator)

        assert label == "API Key"
        assert detail == "渠道未配置 Key"
        assert hint == "请填写 API Key"

    def test_render_summary_translates_label_keys_into_labels(self):
        summary = ReadinessSummary(
            total=3,
            passed=1,
            warnings=0,
            blocking_failed=2,
            semantic="error",
            title="启动前仍有 2 个关键项未就绪",
            detail="关键项：设备连接、API Key",
            action_hint="请先修复关键项",
            title_key="readiness.summary.blocking.title",
            title_params={"count": 2},
            detail_key="readiness.summary.blocking.detail",
            detail_params={"label_keys": ["devices", "api_key"]},
            action_hint_key="readiness.summary.blocking.hint",
        )

        title, detail, hint = render_summary(summary, self._translator)

        assert title == "仍有 2 个关键项未就绪"
        assert detail == "关键项：设备连接、API Key"
        assert hint == "请先完成关键项修复"

    def test_collect_blocking_labels_uses_translated_labels_and_suffix(self):
        results = [
            ReadinessCheckResult(
                key="devices",
                label="设备连接",
                passed=False,
                detail="未检测到设备",
                blocking=True,
                semantic="error",
                label_key="readiness.devices.label",
            ),
            ReadinessCheckResult(
                key="api_key",
                label="API Key",
                passed=False,
                detail="未配置 Key",
                blocking=True,
                semantic="error",
                label_key="readiness.api_key.label",
            ),
            ReadinessCheckResult(
                key="scrcpy",
                label="scrcpy 可用性",
                passed=False,
                detail="未安装",
                blocking=True,
                semantic="error",
            ),
        ]

        labels = collect_blocking_labels(results, max_items=2, translator=self._translator)

        assert labels == "设备连接、API Key..."


class TestSummarizeReadiness:
    """验证 readiness 汇总结构。"""

    def test_summarize_readiness_for_blocking_failures(self):
        results = [
            ReadinessCheckResult("devices", "设备连接", False, "未检测到设备", blocking=True, semantic="error"),
            ReadinessCheckResult("api_key", "API Key", False, "未配置", blocking=True, semantic="error"),
            ReadinessCheckResult("scrcpy", "scrcpy 可用性", True, "已安装", blocking=False, semantic="success"),
        ]

        summary = summarize_readiness(results)

        assert summary.semantic == "error"
        assert summary.blocking_failed == 2
        assert summary.warnings == 0
        assert summary.title_key == "readiness.summary.blocking.title"
        assert summary.detail_key == "readiness.summary.blocking.detail"
        assert summary.action_hint_key == "readiness.summary.blocking.hint"
        assert summary.detail_params == {"label_keys": ["devices", "api_key"]}

    def test_summarize_readiness_for_warnings(self):
        results = [
            ReadinessCheckResult("devices", "设备连接", True, "已连接", blocking=True, semantic="success"),
            ReadinessCheckResult("scrcpy", "scrcpy 可用性", False, "未安装", blocking=False, semantic="warning"),
        ]

        summary = summarize_readiness(results)

        assert summary.semantic == "warning"
        assert summary.blocking_failed == 0
        assert summary.warnings == 1
        assert summary.title_key == "readiness.summary.warning.title"
        assert summary.detail_key == "readiness.summary.warning.detail"
        assert summary.action_hint_key == "readiness.summary.warning.hint"
        assert summary.detail_params == {"label_keys": ["scrcpy"]}

    def test_summarize_readiness_for_success(self):
        results = [
            ReadinessCheckResult("devices", "设备连接", True, "已连接", blocking=True, semantic="success"),
            ReadinessCheckResult("api_key", "API Key", True, "已配置", blocking=True, semantic="success"),
        ]

        summary = summarize_readiness(results)

        assert summary.semantic == "success"
        assert summary.blocking_failed == 0
        assert summary.warnings == 0
        assert summary.title_key == "readiness.summary.success.title"
        assert summary.detail_key == "readiness.summary.success.detail"
        assert summary.action_hint_key == "readiness.summary.success.hint"


class TestTaskServiceInferEvents:
    """验证 TaskService 日志推断使用结构化事件字段。"""

    @staticmethod
    def _make_service():
        svc = TaskService.__new__(TaskService)
        svc._add_event = MagicMock()
        svc.request_takeover = MagicMock()
        svc._current_record = SimpleNamespace(error_summary="")
        svc._i18n = None
        return svc

    def test_infer_events_adds_message_key_for_structured_device_event(self):
        svc = self._make_service()

        svc._infer_events_from_log("设备检查: start")

        svc._add_event.assert_called_once_with(
            "device_check",
            "设备检查开始",
            message_key="event.device_check",
            message_params={},
        )
        svc.request_takeover.assert_not_called()

    def test_infer_events_records_error_with_original_message(self):
        svc = self._make_service()

        svc._infer_events_from_log("Error: boom")

        svc._add_event.assert_called_once_with("error", "Error: boom")
        assert svc._current_record.error_summary == "Error: boom"

    def test_infer_events_takeover_routes_to_request_takeover(self):
        svc = self._make_service()

        svc._infer_events_from_log("takeover requested by operator")

        svc.request_takeover.assert_called_once_with("检测到接管请求")
        svc._add_event.assert_not_called()

    def test_infer_events_ignores_agent_step_noise(self):
        svc = self._make_service()

        svc._infer_events_from_log("Step 3/10")

        svc._add_event.assert_not_called()
        svc.request_takeover.assert_not_called()

    def test_infer_events_ignores_task_completed_log_noise(self):
        svc = self._make_service()

        svc._infer_events_from_log("task completed")

        svc._add_event.assert_not_called()
        svc.request_takeover.assert_not_called()

    def test_infer_events_takeover_uses_current_i18n_reason(self):
        svc = self._make_service()
        svc._i18n = SimpleNamespace(
            t=lambda key, **params: {
                "event.takeover_detected": "Takeover requested",
            }.get(key, f"[[{key}]]")
        )

        svc._infer_events_from_log("takeover requested by operator")

        svc.request_takeover.assert_called_once_with("Takeover requested")
        svc._add_event.assert_not_called()


class TestConfigServiceBuildCommandArgs:
    """验证 OPEN_AUTOGLM_LANG 会透传为 main.py --lang。"""

    @staticmethod
    def _make_service(lang: str):
        svc = ConfigService.__new__(ConfigService)
        values = {
            "OPEN_AUTOGLM_BASE_URL": "https://example.invalid/v1",
            "OPEN_AUTOGLM_MODEL": "demo-model",
            "OPEN_AUTOGLM_DEVICE_ID": "demo-device",
            "OPEN_AUTOGLM_MAX_STEPS": "42",
            "OPEN_AUTOGLM_LANG": lang,
            "OPEN_AUTOGLM_USE_THIRDPARTY_PROMPT": "false",
        }
        svc.get = lambda key, default="": values.get(key, default)
        svc.resolve_api_key = lambda: ("sk-test", "OPEN_AUTOGLM_API_KEY")
        svc._is_truthy = lambda value: str(value).strip().lower() in {"1", "true", "yes", "on"}
        return svc

    def test_build_command_args_includes_current_lang(self):
        svc = self._make_service("en")

        args = ConfigService.build_command_args(svc, "demo task")

        idx = args.index("--lang")
        assert args[idx + 1] == "en"
        assert args[-1] == "demo task"

    def test_build_command_args_normalizes_zh_to_cn(self):
        svc = self._make_service("zh")

        args = ConfigService.build_command_args(svc, "demo task")

        idx = args.index("--lang")
        assert args[idx + 1] == "cn"
