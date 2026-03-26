# -*- coding: utf-8 -*-
"""ADB app lookup and launch fallback tests."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

# 确保在仓库根目录下运行
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from phone_agent.actions.handler import ActionHandler, ActionResult, parse_action
from phone_agent.agent import AgentConfig, PhoneAgent
from phone_agent.device_factory import AppLaunchResult, DeviceFactory, DeviceType, set_device_type
from phone_agent.adb.device import (
    InstalledApp,
    _extract_label_with_aapt,
    _find_apk_label_tool,
    find_installed_app,
    get_current_app,
    launch_app,
    list_installed_apps,
    search_installed_apps,
)


class _CompletedProcess:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class TestAdbDeviceLookup:
    def test_get_current_app_returns_package_name_for_unknown_app(self):
        with patch(
            "phone_agent.adb.device.subprocess.run",
            return_value=_CompletedProcess(
                stdout="mCurrentFocus=Window{42 u0 com.example.reader/.MainActivity}\n"
            ),
        ):
            assert get_current_app() == "com.example.reader"

    def test_get_current_app_returns_system_home_on_shell_failure(self):
        with patch(
            "phone_agent.adb.device.subprocess.run",
            return_value=_CompletedProcess(stderr="boom", returncode=1),
        ):
            assert get_current_app() == "System Home"

    def test_list_installed_apps_parses_launcher_components(self):
        with patch(
            "phone_agent.adb.device.subprocess.run",
            return_value=_CompletedProcess(
                stdout=(
                    "com.example.reader/.MainActivity\n"
                    "com.example.chat/.LauncherActivity\n"
                )
            ),
        ):
            apps = list_installed_apps()

        assert [app.package_name for app in apps] == [
            "com.example.reader",
            "com.example.chat",
        ]
        assert apps[0].display_name is None
        assert apps[1].activity_name == ".LauncherActivity"

    def test_find_installed_app_prefers_exact_display_name(self):
        apps = [
            InstalledApp("com.example.reader", "Reader"),
            InstalledApp("com.example.reader.pro", "Reader Pro"),
        ]
        with patch("phone_agent.adb.device.list_installed_apps", return_value=apps):
            matched = find_installed_app("Reader")

        assert matched is not None
        assert matched.package_name == "com.example.reader"

    def test_search_installed_apps_returns_multiple_candidates(self):
        apps = [
            InstalledApp("com.example.reader", "Reader"),
            InstalledApp("com.example.reader.pro", "Reader Pro"),
        ]
        with patch("phone_agent.adb.device.list_installed_apps", return_value=apps):
            matches = search_installed_apps("read")

        assert [app.package_name for app in matches] == [
            "com.example.reader",
            "com.example.reader.pro",
        ]

    def test_launch_app_accepts_package_name_directly(self):
        outputs = [
            _CompletedProcess(stdout="com.example.reader/.MainActivity\n"),
            _CompletedProcess(stdout="Starting: Intent { cmp=com.example.reader/.MainActivity }\n"),
        ]

        with patch("phone_agent.adb.device.subprocess.run", side_effect=outputs), patch(
            "phone_agent.adb.device.time.sleep", return_value=None
        ):
            result = launch_app("com.example.reader", delay=0)

        assert result.success is True
        assert result.package_name == "com.example.reader"
        assert "通过包名启动" in (result.message or "")

    def test_launch_app_returns_not_found_message(self):
        result = launch_app("不存在的应用", delay=0)

        assert result.success is False
        assert 'do(action="Find_App", query="不存在的应用")' in (result.message or "")


class TestApkLabelResolution:
    def test_extract_label_with_aapt_prefers_chinese_label(self):
        output = (
            "application-label:'WeChat'\n"
            "application-label-en:'WeChat'\n"
            "application-label-zh-CN:'微信'\n"
        )
        with patch(
            "phone_agent.adb.device.subprocess.run",
            return_value=_CompletedProcess(stdout=output),
        ):
            assert _extract_label_with_aapt("fake.apk", "aapt") == "微信"

    def test_find_apk_label_tool_falls_back_to_sdk_build_tools(self, tmp_path):
        sdk_root = tmp_path / "Android" / "Sdk"
        version_dir = sdk_root / "build-tools" / "36.0.0"
        version_dir.mkdir(parents=True)
        aapt_path = version_dir / "aapt.exe"
        aapt_path.write_text("", encoding="utf-8")

        def fake_which(name):
            return None

        with patch("phone_agent.adb.device.shutil.which", side_effect=fake_which), patch.dict(
            "phone_agent.adb.device.os.environ",
            {"LOCALAPPDATA": str(tmp_path)},
            clear=True,
        ):
            tool = _find_apk_label_tool()

        assert tool == str(aapt_path)

    def test_find_apk_label_tool_prefers_aapt_over_apkanalyzer(self):
        def fake_which(name):
            mapping = {
                "aapt": r"C:\sdk\build-tools\36.0.0\aapt.exe",
                "aapt2": r"C:\sdk\build-tools\36.0.0\aapt2.exe",
                "apkanalyzer": r"C:\sdk\cmdline-tools\latest\bin\apkanalyzer.bat",
            }
            return mapping.get(name)

        with patch("phone_agent.adb.device.shutil.which", side_effect=fake_which):
            tool = _find_apk_label_tool()

        assert tool == r"C:\sdk\build-tools\36.0.0\aapt.exe"


class TestLaunchActionHandler:
    def test_handle_launch_uses_detailed_message(self):
        handler = ActionHandler()
        fake_factory = DeviceFactory(DeviceType.ADB)

        with patch(
            "phone_agent.actions.handler.get_device_factory", return_value=fake_factory
        ), patch.object(
            fake_factory,
            "launch_app_detailed",
            return_value=AppLaunchResult(True, "已通过包名启动 com.example.reader"),
        ):
            result = handler._handle_launch({"app": "com.example.reader"}, 1080, 2400)

        assert result.success is True
        assert "com.example.reader" in (result.message or "")

    def test_handle_find_app_returns_candidates(self):
        handler = ActionHandler()
        fake_factory = DeviceFactory(DeviceType.ADB)
        matches = [
            InstalledApp("com.example.reader", None, ".MainActivity"),
            InstalledApp("com.example.reader.pro", None, ".ProActivity"),
        ]

        with patch(
            "phone_agent.actions.handler.get_device_factory", return_value=fake_factory
        ), patch.object(fake_factory, "search_installed_apps", return_value=matches):
            result = handler._handle_find_app({"query": "reader"}, 1080, 2400)

        assert result.success is True
        assert "已找到 2 个匹配包名" in (result.message or "")
        assert "com.example.reader" in (result.message or "")
        assert 'do(action="Launch", app="com.example.reader")' in (result.message or "")

    def test_handle_launch_auto_falls_back_to_find_app_candidates(self):
        handler = ActionHandler()
        fake_factory = DeviceFactory(DeviceType.ADB)
        matches = [InstalledApp("com.nethack.main", None, ".MainActivity")]

        with patch(
            "phone_agent.actions.handler.get_device_factory", return_value=fake_factory
        ), patch.object(
            fake_factory,
            "launch_app_detailed",
            return_value=AppLaunchResult(False, "未找到应用：nethack"),
        ), patch.object(fake_factory, "search_installed_apps", return_value=matches):
            result = handler._handle_launch({"app": "nethack"}, 1080, 2400)

        assert result.success is True
        assert "已自动转为查找包名" in (result.message or "")
        assert "com.nethack.main" in (result.message or "")

    def test_handle_find_app_rejects_empty_query(self):
        handler = ActionHandler()
        result = handler._handle_find_app({}, 1080, 2400)

        assert result.success is False
        assert result.message == "No app query specified"

    def test_handle_find_app_rejects_non_adb(self):
        handler = ActionHandler()
        fake_factory = DeviceFactory(DeviceType.HDC)

        with patch(
            "phone_agent.actions.handler.get_device_factory", return_value=fake_factory
        ):
            result = handler._handle_find_app({"query": "settings"}, 1080, 2400)

        assert result.success is False
        assert "only supported for Android ADB devices" in (result.message or "")

    def test_handle_find_app_reports_not_found(self):
        handler = ActionHandler()
        fake_factory = DeviceFactory(DeviceType.ADB)

        with patch(
            "phone_agent.actions.handler.get_device_factory", return_value=fake_factory
        ), patch.object(fake_factory, "search_installed_apps", return_value=[]):
            result = handler._handle_find_app({"query": "missing"}, 1080, 2400)

        assert result.success is False
        assert "未找到匹配包名：missing" == result.message


class TestActionParsing:
    def test_parse_action_accepts_find_app_query(self):
        action = parse_action('do(action="Find_App", query="settings")')

        assert action["_metadata"] == "do"
        assert action["action"] == "Find_App"
        assert action["query"] == "settings"


class TestPhoneAgentActionResultContext:
    def test_step_appends_action_result_message_to_context(self):
        class _FakeScreenshot:
            width = 1080
            height = 2400
            base64_data = "ZmFrZQ=="

        class _FakeModelResponse:
            thinking = ""
            action = 'do(action="Find_App", query="settings")'

        fake_factory = DeviceFactory(DeviceType.ADB)
        agent = PhoneAgent(
            agent_config=AgentConfig(verbose=False, system_prompt="test system prompt")
        )
        action_message = (
            "已找到 1 个匹配包名：\n"
            "1. com.android.settings [.Settings]\n"
            '下一步请直接使用 do(action="Launch", app="com.android.settings")'
        )

        with patch("phone_agent.agent.get_device_factory", return_value=fake_factory), patch.object(
            fake_factory, "get_screenshot", return_value=_FakeScreenshot()
        ), patch.object(
            fake_factory, "get_current_app", return_value="com.android.launcher"
        ), patch.object(
            agent.model_client, "request", return_value=_FakeModelResponse()
        ), patch.object(
            agent.action_handler,
            "execute",
            return_value=ActionResult(True, False, action_message),
        ):
            result = agent.step("找到设置包名")

        assert result.success is True
        last_message = agent.context[-1]
        assert last_message["role"] == "user"
        assert last_message["content"][-1]["type"] == "text"
        assert last_message["content"][-1]["text"].startswith("** Action Result **")
        assert "Action succeeded" in last_message["content"][-1]["text"]
        assert "com.android.settings" in last_message["content"][-1]["text"]

    def test_step_overrides_wrong_tap_with_recommended_find_app(self):
        class _FakeScreenshot:
            width = 1080
            height = 2400
            base64_data = "ZmFrZQ=="

        class _FakeModelResponse:
            thinking = "先查包名"
            action = 'do(action="Tap", element=[930,72])'

        fake_factory = DeviceFactory(DeviceType.ADB)
        agent = PhoneAgent(
            agent_config=AgentConfig(verbose=False, system_prompt="test system prompt")
        )
        agent._context.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": '** Action Result **\n\nAction failed: 未找到应用：nethack。下一步请先执行 do(action="Find_App", query="nethack")'
                    }
                ],
            }
        )

        with patch("phone_agent.agent.get_device_factory", return_value=fake_factory), patch.object(
            fake_factory, "get_screenshot", return_value=_FakeScreenshot()
        ), patch.object(
            fake_factory, "get_current_app", return_value="com.android.launcher"
        ), patch.object(
            agent.model_client, "request", return_value=_FakeModelResponse()
        ), patch.object(
            agent.action_handler,
            "execute",
            return_value=ActionResult(True, False, "已找到 1 个匹配包名：\n1. com.nethack.main [.MainActivity]"),
        ) as execute_mock:
            result = agent.step("打开 nethack")

        assert result.success is True
        executed_action = execute_mock.call_args.args[0]
        assert executed_action["action"] == "Find_App"
        assert executed_action["query"] == "nethack"
