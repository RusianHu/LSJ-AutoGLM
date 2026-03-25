# -*- coding: utf-8 -*-
"""ADB app lookup and launch fallback tests."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

# 确保在仓库根目录下运行
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from phone_agent.actions.handler import ActionHandler
from phone_agent.device_factory import AppLaunchResult, DeviceFactory, DeviceType
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
        outputs = [
            _CompletedProcess(
                stdout=(
                    "com.example.reader/.MainActivity\n"
                    "com.example.chat/.LauncherActivity\n"
                )
            ),
            _CompletedProcess(stdout="nonLocalizedLabel=Reader\n"),
            _CompletedProcess(stdout="nonLocalizedLabel=Chat\n"),
        ]

        with patch("phone_agent.adb.device.subprocess.run", side_effect=outputs):
            apps = list_installed_apps()

        assert [app.package_name for app in apps] == [
            "com.example.reader",
            "com.example.chat",
        ]
        assert apps[0].display_name == "Reader"
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

    def test_launch_app_falls_back_to_dynamic_lookup(self):
        outputs = [
            _CompletedProcess(stdout="com.example.reader/.MainActivity\n"),
            _CompletedProcess(stdout="nonLocalizedLabel=Reader\n"),
            _CompletedProcess(stdout="com.example.reader/.MainActivity\n"),
            _CompletedProcess(stdout="Starting: Intent { cmp=com.example.reader/.MainActivity }\n"),
        ]

        with patch("phone_agent.adb.device.subprocess.run", side_effect=outputs), patch(
            "phone_agent.adb.device.time.sleep", return_value=None
        ):
            result = launch_app("Reader", delay=0)

        assert result.success is True
        assert result.package_name == "com.example.reader"
        assert "通过设备查找启动" in (result.message or "")

    def test_launch_app_reports_ambiguous_candidates(self):
        apps = [
            InstalledApp("com.example.reader", "Reader"),
            InstalledApp("com.example.reader.pro", "Reader Pro"),
        ]
        with patch("phone_agent.adb.device.search_installed_apps", return_value=apps):
            result = launch_app("reader", delay=0)

        assert result.success is False
        assert "多个候选应用" in (result.message or "")

    def test_launch_app_returns_not_found_message(self):
        with patch(
            "phone_agent.adb.device.subprocess.run",
            return_value=_CompletedProcess(stdout=""),
        ):
            result = launch_app("不存在的应用", delay=0)

        assert result.success is False
        assert result.message == "未找到应用：不存在的应用"

    def test_list_installed_apps_falls_back_to_package_suffix_when_tools_missing(self):
        with patch(
            "phone_agent.adb.device._run_adb_shell",
            side_effect=[
                "com.example.reader/.MainActivity\n",
                "",
                "package:/data/app/com.example.reader/base.apk",
            ],
        ), patch("phone_agent.adb.device._find_apk_label_tool", return_value=None):
            apps = list_installed_apps()

        assert len(apps) == 1
        assert apps[0].display_name == "reader"

    def test_list_installed_apps_falls_back_to_package_suffix_when_pull_fails(self):
        with patch(
            "phone_agent.adb.device._run_adb_shell",
            side_effect=[
                "com.example.reader/.MainActivity\n",
                "",
                "package:/data/app/com.example.reader/base.apk",
            ],
        ), patch("phone_agent.adb.device._find_apk_label_tool", return_value="aapt"), patch(
            "phone_agent.adb.device._adb_pull_file", return_value=False
        ):
            apps = list_installed_apps()

        assert len(apps) == 1
        assert apps[0].display_name == "reader"

    def test_list_installed_apps_falls_back_to_package_suffix_on_unexpected_label_error(self):
        with patch(
            "phone_agent.adb.device._run_adb_shell",
            return_value="com.example.reader/.MainActivity\n",
        ), patch(
            "phone_agent.adb.device._get_application_label_from_dumpsys",
            side_effect=RuntimeError("boom"),
        ), patch(
            "phone_agent.adb.device._get_application_label_from_apk",
            side_effect=RuntimeError("boom"),
        ):
            apps = list_installed_apps()

        assert len(apps) == 1
        assert apps[0].display_name == "reader"


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
            return_value=AppLaunchResult(True, "已通过设备查找启动 Reader (com.example.reader)"),
        ):
            result = handler._handle_launch({"app": "Reader"}, 1080, 2400)

        assert result.success is True
        assert "Reader" in (result.message or "")
