from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from gui.services.adb_client import (
    ADB_TLS_PAIRING_SERVICE,
    AdbClient,
    AdbCommandResult,
    MdnsService,
    PairResult,
    parse_adb_server_status,
)


def test_parse_adb_server_status_unescapes_windows_path():
    output = (
        'version: "37.0.0"\n'
        'mdns_backend: LIBADBMDNS\n'
        'log_absolute_path: "C:\\\\Users\\\\tester\\\\Temp\\\\adb.log"\n'
        'mdns_enabled: true\n'
    )

    status = parse_adb_server_status(output)

    assert status["version"] == "37.0.0"
    assert status["mdns_backend"] == "LIBADBMDNS"
    assert status["log_absolute_path"] == r"C:\Users\tester\Temp\adb.log"
    assert status["mdns_enabled"] == "true"


def test_pair_recovers_tcp_timeout_hidden_by_protocol_fault(tmp_path: Path):
    adb_log = tmp_path / "adb.log"
    adb_log.write_text("existing log\n", encoding="utf-8")

    def runner(command, **_kwargs):
        if command[1:] == ["server-status"]:
            escaped = str(adb_log).replace("\\", "\\\\")
            return subprocess.CompletedProcess(
                command,
                0,
                f'log_absolute_path: "{escaped}"\n',
                "",
            )
        if command[1:3] == ["pair", "192.168.6.155:46571"]:
            with adb_log.open("a", encoding="utf-8") as stream:
                stream.write(
                    "E adb : pairing_client.cpp:133 Failed to start pairing connection client "
                    "[cannot connect to 192.168.6.155:46571: connection timed out (10060)]\n"
                )
            return subprocess.CompletedProcess(
                command,
                1,
                "",
                "error: protocol fault (couldn't read status message): No error",
            )
        raise AssertionError(command)

    result = AdbClient(runner=runner).pair("192.168.6.155:46571", "secret")

    assert not result.paired
    assert "TCP 通道不可达" in result.message
    assert "10060" in result.message
    assert "6 位码" not in result.message


class _RetryingQrClient(AdbClient):
    def __init__(self):
        super().__init__(runner=lambda *_args, **_kwargs: None)
        self.pair_calls = 0
        self.restart_calls = 0

    def start_server(self, should_stop=None):
        return AdbCommandResult(("adb", "start-server"), 0)

    def restart_server(self, should_stop=None):
        self.restart_calls += 1
        return AdbCommandResult(("adb", "start-server"), 0)

    def mdns_check(self, should_stop=None):
        return True, "ok"

    def mdns_services(self, should_stop=None):
        return [
            MdnsService(
                "studio-abcdefghij",
                ADB_TLS_PAIRING_SERVICE,
                "192.168.6.155:46571",
            )
        ]

    def pair(self, endpoint, pairing_code, should_stop=None):
        self.pair_calls += 1
        if self.pair_calls == 1:
            return PairResult(False, "TCP 通道不可达", pairing_endpoint=endpoint)
        return PairResult(True, "Successfully paired", pairing_endpoint=endpoint)

    def wait_for_connection(self, host, timeout=15, should_stop=None):
        return "adb-77eaf689._adb-tls-connect._tcp"


def test_qr_pair_refreshes_discovery_and_retries_exact_service():
    client = _RetryingQrClient()

    with (
        patch("gui.services.adb_client._interruptible_sleep"),
        patch("gui.services.adb_client.clear_host_neighbor_cache") as clear_neighbor,
    ):
        result = client.pair_via_qr(
            "studio-abcdefghij",
            "secret123456",
            timeout=10,
        )

    assert result.paired
    assert result.pairing_endpoint == "192.168.6.155:46571"
    assert result.connected_endpoint == "adb-77eaf689._adb-tls-connect._tcp"
    assert client.pair_calls == 2
    assert client.restart_calls == 1
    clear_neighbor.assert_called_once_with("192.168.6.155")
