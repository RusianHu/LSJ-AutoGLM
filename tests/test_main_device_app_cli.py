# -*- coding: utf-8 -*-
"""CLI tests for device app lookup commands."""

import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

# 确保在仓库根目录下运行
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from phone_agent.adb.device import InstalledApp
from phone_agent.device_factory import DeviceType
from main import _build_action_policy_from_args, handle_device_commands


class _FakeConnection:
    def connect(self, address):
        return True, f"connected to {address}"


class _FakeFactory:
    def get_connection_class(self):
        return _FakeConnection

    def list_devices(self):
        return []

    def list_installed_apps(self, device_id=None):
        return [InstalledApp("com.example.reader", None, ".MainActivity")]

    def search_installed_apps(self, query, device_id=None):
        return [
            InstalledApp("com.example.reader", None, ".MainActivity"),
            InstalledApp("com.example.reader.pro", None, ".MainActivity"),
        ]


class TestMainDeviceAppCli:
    def _make_args(self, **overrides):
        base = {
            "device_type": "adb",
            "list_devices": False,
            "list_device_apps": False,
            "find_app": None,
            "connect": None,
            "disconnect": None,
            "enable_tcpip": None,
            "device_id": None,
        }
        base.update(overrides)
        return SimpleNamespace(**base)

    def test_handle_list_device_apps(self, capsys):
        args = self._make_args(list_device_apps=True)
        with patch("main.get_device_factory", return_value=_FakeFactory()):
            handled = handle_device_commands(args)

        assert handled is True
        output = capsys.readouterr().out
        assert "Launchable package/activity entries discovered on device" in output
        assert "com.example.reader" in output
        assert ".MainActivity" in output

    def test_handle_find_app_lists_matches(self, capsys):
        args = self._make_args(find_app="reader")
        with patch("main.get_device_factory", return_value=_FakeFactory()):
            handled = handle_device_commands(args)

        assert handled is True
        output = capsys.readouterr().out
        assert "Matched package/activity entries (2)" in output
        assert "com.example.reader.pro" in output

    def test_handle_find_app_rejects_non_adb(self, capsys):
        args = self._make_args(device_type=DeviceType.HDC.value, find_app="reader")
        handled = handle_device_commands(args)

        assert handled is True
        output = capsys.readouterr().out
        assert "only supported for Android ADB devices" in output

    def test_handle_connect_success_returns_handled_and_updates_device_id(self, capsys):
        args = self._make_args(connect="192.168.1.2:5555")

        with patch("main.get_device_factory", return_value=_FakeFactory()):
            handled = handle_device_commands(args)

        assert handled is True
        assert args.device_id == "192.168.1.2:5555"
        output = capsys.readouterr().out
        assert "Connecting to 192.168.1.2:5555..." in output
        assert "connected to 192.168.1.2:5555" in output

    def test_handle_connect_failure_still_returns_handled(self, capsys):
        class _FailingConnection:
            def connect(self, address):
                return False, f"failed to connect to {address}"

        class _FailingFactory(_FakeFactory):
            def get_connection_class(self):
                return _FailingConnection

        args = self._make_args(connect="192.168.1.2:5555")

        with patch("main.get_device_factory", return_value=_FailingFactory()):
            handled = handle_device_commands(args)

        assert handled is True
        assert args.device_id is None
        output = capsys.readouterr().out
        assert "failed to connect to 192.168.1.2:5555" in output


class TestMainActionPolicyCli:
    @staticmethod
    def _make_policy_args(**overrides):
        base = {
            "enabled_actions": None,
            "ai_visible_actions": None,
            "action_policy_version": 1,
            "use_platform_default_actions": True,
        }
        base.update(overrides)
        return SimpleNamespace(**base)

    def test_build_action_policy_from_args_accepts_supported_ios_actions(self):
        args = self._make_policy_args(
            enabled_actions='["Launch", "Tap", "Wait"]',
            ai_visible_actions='["Launch", "Tap"]',
            use_platform_default_actions=False,
            action_policy_version=2,
        )

        policy, resolved = _build_action_policy_from_args(args, "ios")

        assert policy.policy_version == 2
        assert policy.use_platform_defaults is False
        assert resolved.platform == "ios"
        assert resolved.runtime_enabled_actions == ("Launch", "Tap", "Wait")
        assert resolved.ai_visible_actions == ("Launch", "Tap")

    def test_build_action_policy_from_args_rejects_unknown_actions(self):
        args = self._make_policy_args(enabled_actions='["Launch", "Unknown_Action"]')

        with pytest.raises(ValueError, match="未知动作名"):
            _build_action_policy_from_args(args, "adb")

    def test_build_action_policy_from_args_rejects_platform_unsupported_actions(self):
        args = self._make_policy_args(
            enabled_actions='["Launch", "Find_App"]',
            ai_visible_actions='["Launch"]',
            use_platform_default_actions=False,
        )

        with pytest.raises(ValueError, match="平台 ios 不支持这些运行时动作"):
            _build_action_policy_from_args(args, "ios")

    def test_build_action_policy_from_args_rejects_missing_sets_when_defaults_disabled(self):
        args = self._make_policy_args(
            enabled_actions=None,
            ai_visible_actions=None,
            use_platform_default_actions=False,
        )

        with pytest.raises(ValueError, match="运行时启用动作集合未提供"):
            _build_action_policy_from_args(args, "adb")

    def test_build_action_policy_from_args_accepts_explicit_empty_sets_when_defaults_disabled(self):
        args = self._make_policy_args(
            enabled_actions='[]',
            ai_visible_actions='[]',
            use_platform_default_actions=False,
        )

        policy, resolved = _build_action_policy_from_args(args, "adb")

        assert policy.use_platform_defaults is False
        assert resolved.runtime_enabled_actions == ()
        assert resolved.ai_visible_actions == ()
