# -*- coding: utf-8 -*-
"""CLI tests for device app lookup commands."""

import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

# 确保在仓库根目录下运行
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from phone_agent.adb.device import InstalledApp
from phone_agent.device_factory import DeviceType
from main import handle_device_commands


class _FakeConnection:
    pass


class _FakeFactory:
    def get_connection_class(self):
        return _FakeConnection

    def list_devices(self):
        return []

    def list_installed_apps(self, device_id=None):
        return [InstalledApp("com.example.reader", "Reader", ".MainActivity")]

    def search_installed_apps(self, query, device_id=None):
        return [
            InstalledApp("com.example.reader", "Reader", ".MainActivity"),
            InstalledApp("com.example.reader.pro", "Reader Pro", ".MainActivity"),
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
        assert "Reader" in output
        assert "com.example.reader" in output

    def test_handle_find_app_lists_matches(self, capsys):
        args = self._make_args(find_app="reader")
        with patch("main.get_device_factory", return_value=_FakeFactory()):
            handled = handle_device_commands(args)

        assert handled is True
        output = capsys.readouterr().out
        assert "Matched installed apps (2)" in output
        assert "Reader Pro" in output

    def test_handle_find_app_rejects_non_adb(self, capsys):
        args = self._make_args(device_type=DeviceType.HDC.value, find_app="reader")
        handled = handle_device_commands(args)

        assert handled is True
        output = capsys.readouterr().out
        assert "only supported for Android ADB devices" in output
