# -*- coding: utf-8 -*-
"""ADB 连接、配对和 mDNS 发现的无界面实现。

该模块只负责执行 ADB 与解析结果，不依赖 Qt。GUI、TUI 和测试可以共享同一套
连接语义，避免在界面回调里拼接命令或判断英文输出。
"""

from __future__ import annotations

import ipaddress
import json
import re
import secrets
import string
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional, Sequence


ADB_TLS_PAIRING_SERVICE = "_adb-tls-pairing._tcp"
ADB_TLS_CONNECT_SERVICE = "_adb-tls-connect._tcp"
DEFAULT_ADB_TCP_PORT = 5555


@dataclass(frozen=True)
class AdbCommandResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def output(self) -> str:
        return (self.stdout or "").strip() or (self.stderr or "").strip()

    @property
    def merged_output(self) -> str:
        return "\n".join(part.strip() for part in (self.stdout, self.stderr) if part and part.strip())


@dataclass(frozen=True)
class AdbDeviceRecord:
    serial: str
    state: str
    attributes: dict[str, str]


@dataclass(frozen=True)
class MdnsService:
    instance_name: str
    service_type: str
    endpoint: str


@dataclass(frozen=True)
class PairResult:
    paired: bool
    message: str
    pairing_endpoint: str = ""
    connected_endpoint: str = ""
    timed_out: bool = False


@dataclass(frozen=True)
class TcpIpResult:
    success: bool
    message: str
    endpoint: str = ""


class AdbError(RuntimeError):
    """ADB 命令无法执行或输入无效。"""


def is_mdns_transport_serial(value: str) -> bool:
    lowered = (value or "").strip().lower()
    return (
        f".{ADB_TLS_CONNECT_SERVICE}" in lowered
        or f".{ADB_TLS_PAIRING_SERVICE}" in lowered
    )


def _creation_flags() -> int:
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))


def clear_host_neighbor_cache(host: str) -> bool:
    """清除 Windows 上单个 IPv4 主机的失败 ARP/邻居项。

    无线调试端口已经由 mDNS 更新，但 Windows 偶尔仍会把目标邻居保持为
    ``Unreachable``。这里只删除目标手机的一项；非 Windows、IPv6 或命令失败时
    静默跳过，由后续正常重试处理。
    """
    if sys.platform != "win32":
        return False
    try:
        address = ipaddress.ip_address((host or "").strip())
    except ValueError:
        return False
    if not isinstance(address, ipaddress.IPv4Address):
        return False
    try:
        result = subprocess.run(
            ["arp.exe", "-d", str(address)],
            capture_output=True,
            timeout=5,
            creationflags=_creation_flags(),
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def normalize_endpoint(value: str, default_port: Optional[int] = None) -> str:
    """规范化 ``host:port``，并正确处理带方括号的 IPv6。"""
    raw = (value or "").strip()
    if not raw:
        raise ValueError("设备地址不能为空")

    if raw.startswith("["):
        match = re.fullmatch(r"\[([^]]+)](?::(\d+))?", raw)
        if not match:
            raise ValueError("IPv6 地址格式错误，应为 [IPv6]:端口")
        host, port_text = match.groups()
        try:
            ipaddress.IPv6Address(host)
        except ValueError as exc:
            raise ValueError("IPv6 地址无效") from exc
        port = _validated_port(port_text, default_port)
        return f"[{host}]:{port}"

    colon_count = raw.count(":")
    if colon_count == 0:
        if default_port is None:
            raise ValueError("地址必须包含端口")
        host = raw
        port = _validated_port(None, default_port)
    elif colon_count == 1:
        host, port_text = raw.rsplit(":", 1)
        if not host:
            raise ValueError("设备地址缺少主机名或 IP")
        port = _validated_port(port_text, default_port)
    else:
        raise ValueError("IPv6 地址必须使用 [IPv6]:端口 格式")

    if any(ch.isspace() for ch in host):
        raise ValueError("设备地址不能包含空格")
    return f"{host}:{port}"


def _validated_port(port_text: Optional[str], default_port: Optional[int]) -> int:
    if not port_text:
        if default_port is None:
            raise ValueError("地址必须包含端口")
        port = int(default_port)
    elif port_text.isdigit():
        port = int(port_text)
    else:
        raise ValueError("端口必须是数字")
    if not 1 <= port <= 65535:
        raise ValueError("端口范围必须为 1-65535")
    return port


def endpoint_host(endpoint: str) -> str:
    normalized = normalize_endpoint(endpoint)
    if normalized.startswith("["):
        return normalized[1 : normalized.index("]")]
    return normalized.rsplit(":", 1)[0]


def build_pairing_qr_payload(service_name: str, password: str) -> str:
    """生成 Android ADB Wi-Fi 二维码负载。

    凭据由本模块生成时只含字母数字，不需要 WIFI QR 的额外转义。对外部输入仍
    拒绝会破坏字段边界的字符，避免显示一个手机无法解析的二维码。
    """
    for label, value in (("服务名", service_name), ("配对密码", password)):
        if not value:
            raise ValueError(f"{label}不能为空")
        if any(ch in value for ch in ";\\"):
            raise ValueError(f"{label}包含二维码保留字符")
    return f"WIFI:T:ADB;S:{service_name};P:{password};;"


def generate_qr_credentials() -> tuple[str, str]:
    alphabet = string.ascii_letters + string.digits
    suffix = "".join(secrets.choice(alphabet) for _ in range(10))
    password = "".join(secrets.choice(alphabet) for _ in range(12))
    return f"studio-{suffix}", password


def parse_mdns_services(output: str) -> list[MdnsService]:
    services: list[MdnsService] = []
    for raw_line in (output or "").splitlines():
        line = raw_line.strip()
        if not line or line.lower().startswith("list of discovered"):
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        instance_name, service_type, endpoint = parts[0], parts[1], parts[2]
        try:
            endpoint = normalize_endpoint(endpoint)
        except ValueError:
            continue
        services.append(MdnsService(instance_name, service_type, endpoint))
    return services


def parse_adb_server_status(output: str) -> dict[str, str]:
    """解析 ``adb server-status`` 的 ``key: value`` 输出。"""
    status: dict[str, str] = {}
    for raw_line in (output or "").splitlines():
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
            try:
                value = str(json.loads(value))
            except (TypeError, ValueError, json.JSONDecodeError):
                value = value[1:-1]
        status[key] = value
    return status


def parse_adb_devices(output: str) -> list[AdbDeviceRecord]:
    records: list[AdbDeviceRecord] = []
    known_states = {"device", "offline", "unauthorized", "no permissions", "bootloader"}
    for raw_line in (output or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("List of devices attached") or line.startswith("*"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        state_index = next(
            (index for index, token in enumerate(parts) if token in known_states),
            1,
        )
        if state_index <= 0 or state_index >= len(parts):
            continue
        serial = " ".join(parts[:state_index])
        state = parts[state_index]
        attrs: dict[str, str] = {}
        for token in parts[state_index + 1:]:
            if ":" in token:
                key, value = token.split(":", 1)
                attrs[key] = value
        records.append(AdbDeviceRecord(serial, state, attrs))
    return records


def parse_wlan_ipv4(outputs: Iterable[str]) -> str:
    """从 ``ip route`` / ``ip addr`` / ``ifconfig`` 输出提取 wlan IPv4。"""
    patterns = (
        re.compile(r"\bsrc\s+((?:\d{1,3}\.){3}\d{1,3})\b"),
        re.compile(r"\binet\s+(?:addr:)?((?:\d{1,3}\.){3}\d{1,3})(?:/\d+)?\b"),
    )
    for output in outputs:
        for pattern in patterns:
            for match in pattern.finditer(output or ""):
                candidate = match.group(1)
                try:
                    address = ipaddress.IPv4Address(candidate)
                except ValueError:
                    continue
                if not address.is_loopback and not address.is_unspecified:
                    return candidate
    return ""


class AdbClient:
    """可测试、无 Qt 依赖的 ADB 客户端。"""

    def __init__(self, adb_path: str = "adb", runner: Optional[Callable[..., subprocess.CompletedProcess]] = None):
        self.adb_path = adb_path or "adb"
        self._runner = runner or subprocess.run

    def run(
        self,
        args: Sequence[str],
        timeout: float = 15,
        serial: str = "",
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> AdbCommandResult:
        command = [self.adb_path]
        if serial:
            command.extend(["-s", serial])
        command.extend(str(arg) for arg in args)
        try:
            if should_stop is not None and self._runner is subprocess.run:
                completed = self._run_interruptible(command, timeout, should_stop)
            else:
                completed = self._runner(
                    command,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout,
                    creationflags=_creation_flags(),
                )
        except FileNotFoundError as exc:
            raise AdbError("ADB 未找到，请确认 Android SDK Platform-Tools 已安装并加入 PATH") from exc
        except subprocess.TimeoutExpired as exc:
            raise AdbError(f"ADB 命令超时：{' '.join(command[1:])}") from exc
        except OSError as exc:
            raise AdbError(f"ADB 启动失败：{exc}") from exc
        return AdbCommandResult(
            tuple(command),
            int(completed.returncode),
            completed.stdout or "",
            completed.stderr or "",
        )

    @staticmethod
    def _run_interruptible(
        command: list[str],
        timeout: float,
        should_stop: Callable[[], bool],
    ) -> subprocess.CompletedProcess:
        proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_creation_flags(),
        )
        deadline = time.monotonic() + max(timeout, 0)
        while True:
            if should_stop():
                _terminate_subprocess(proc)
                raise AdbError("ADB 操作已取消")
            returncode = proc.poll()
            if returncode is not None:
                stdout, stderr = proc.communicate()
                return subprocess.CompletedProcess(command, returncode, stdout, stderr)
            if time.monotonic() >= deadline:
                _terminate_subprocess(proc)
                raise AdbError(f"ADB 命令超时：{' '.join(command[1:])}")
            time.sleep(0.05)

    def start_server(
        self,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> AdbCommandResult:
        return self.run(["start-server"], timeout=10, should_stop=should_stop)

    def restart_server(
        self,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> AdbCommandResult:
        """重启 ADB server，以清空失效 transport 和 mDNS 发现状态。"""
        self.run(["kill-server"], timeout=10, should_stop=should_stop)
        return self.start_server(should_stop=should_stop)

    def server_status(
        self,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> dict[str, str]:
        """读取 ADB server 配置；旧版 ADB 不支持时返回空字典。"""
        result = self.run(["server-status"], timeout=5, should_stop=should_stop)
        if result.returncode != 0:
            return {}
        return parse_adb_server_status(result.merged_output)

    def _pairing_log_cursor(
        self,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> tuple[Path, int] | None:
        """记录配对前的 ADB 日志位置，用于还原被客户端隐藏的 server 错误。"""
        try:
            raw_path = self.server_status(should_stop=should_stop).get("log_absolute_path", "")
            if not raw_path:
                return None
            path = Path(raw_path)
            return path, path.stat().st_size if path.exists() else 0
        except (AdbError, OSError, ValueError):
            return None

    @staticmethod
    def _pairing_log_failure(cursor: tuple[Path, int] | None) -> str:
        if cursor is None:
            return ""
        path, offset = cursor
        try:
            with path.open("rb") as stream:
                if path.stat().st_size >= offset:
                    stream.seek(offset)
                appended = stream.read().decode("utf-8", errors="replace")
        except OSError:
            return ""

        marker = "Failed to start pairing connection client ["
        failures: list[str] = []
        for line in appended.splitlines():
            if marker not in line:
                continue
            detail = line.split(marker, 1)[1]
            if detail.endswith("]"):
                detail = detail[:-1]
            if detail.strip():
                failures.append(detail.strip())
        return failures[-1] if failures else ""

    @staticmethod
    def _format_pair_failure(endpoint: str, output: str, detail: str) -> str:
        evidence = detail or output
        lowered = evidence.lower()
        if "cannot connect to" in lowered and (
            "10060" in lowered
            or "timed out" in lowered
            or "没有正确答复" in evidence
            or "连接尝试失败" in evidence
        ):
            summary = (
                f"ADB 无法连接手机配对端口 {endpoint}：mDNS 已发现服务，但 TCP 通道不可达。"
                "该端口是临时配对端口，与手机无线调试主页显示的 TLS 连接端口不同是正常现象。"
                "请确认手机和电脑位于同一局域网，关闭访客网络/AP 隔离或会抢占局域网路由的 VPN，"
                "并在手机上关闭再开启无线调试后重新扫码。"
            )
        elif "cannot connect to" in lowered and (
            "10061" in lowered or "actively refused" in lowered or "积极拒绝" in evidence
        ):
            summary = (
                f"手机配对端口 {endpoint} 已关闭或发生变化。"
                "该端口与手机无线调试主页显示的 TLS 连接端口不同是正常现象。"
                "请保持手机配对窗口开启，并重新扫码获取当前端口。"
            )
        elif "cannot resolve host" in lowered:
            summary = f"ADB 无法解析配对地址 {endpoint}，请检查地址格式和网络配置。"
        elif "protocol fault" in output.lower():
            summary = (
                "ADB 配对失败；当前 ADB 的 protocol fault 可能只是错误回传缺陷，"
                "不能据此判定为配对码错误。请保持手机配对窗口开启后重试。"
            )
        else:
            return output
        return f"{summary} | ADB 详情：{evidence}" if evidence else summary

    def mdns_check(
        self,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> tuple[bool, str]:
        result = self.run(["mdns", "check"], timeout=8, should_stop=should_stop)
        output = result.merged_output or "ADB mDNS 未返回信息"
        return result.returncode == 0 and "error" not in output.lower(), output

    def mdns_services(self, should_stop: Optional[Callable[[], bool]] = None) -> list[MdnsService]:
        result = self.run(["mdns", "services"], timeout=8, should_stop=should_stop)
        if result.returncode != 0:
            raise AdbError(result.merged_output or "ADB mDNS 服务发现失败")
        return parse_mdns_services(result.stdout)

    def devices(
        self,
        long: bool = True,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> list[AdbDeviceRecord]:
        args = ["devices", "-l"] if long else ["devices"]
        result = self.run(args, timeout=10, should_stop=should_stop)
        if result.returncode != 0:
            raise AdbError(result.merged_output or "ADB 设备枚举失败")
        return parse_adb_devices(result.stdout)

    def pair(
        self,
        endpoint: str,
        pairing_code: str,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> PairResult:
        normalized = normalize_endpoint(endpoint)
        code = (pairing_code or "").strip()
        if not code:
            raise ValueError("配对码不能为空")
        log_cursor = self._pairing_log_cursor(should_stop=should_stop)
        result = self.run(["pair", normalized, code], timeout=35, should_stop=should_stop)
        output = result.merged_output or "ADB 未返回配对结果"
        lowered = output.lower()
        paired = result.returncode == 0 and (
            "successfully paired" in lowered
            or "already paired" in lowered
            or ("paired to" in lowered and "failed" not in lowered)
        )
        if not paired:
            detail = self._pairing_log_failure(log_cursor)
            output = self._format_pair_failure(normalized, output, detail)
        return PairResult(paired, output, pairing_endpoint=normalized)

    def resolve_pairing_endpoint(
        self,
        endpoint: str,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> tuple[str, bool]:
        """用同一主机唯一的 mDNS 配对服务纠正误填的连接端口。"""
        normalized = normalize_endpoint(endpoint)
        host = endpoint_host(normalized)
        try:
            candidates = [
                service.endpoint
                for service in self.mdns_services(should_stop=should_stop)
                if service.service_type == ADB_TLS_PAIRING_SERVICE
                and endpoint_host(service.endpoint).lower() == host.lower()
            ]
        except AdbError:
            return normalized, False
        unique = list(dict.fromkeys(candidates))
        if len(unique) == 1 and unique[0] != normalized:
            return unique[0], True
        return normalized, False

    def connect(
        self,
        endpoint: str,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> tuple[bool, str]:
        if is_mdns_transport_serial(endpoint):
            raise ValueError("mDNS 设备名不能用于 adb connect；设备已由 ADB 自动发现，请直接在设备列表中使用")
        normalized = normalize_endpoint(endpoint, DEFAULT_ADB_TCP_PORT)
        result = self.run(["connect", normalized], timeout=20, should_stop=should_stop)
        output = result.merged_output or "ADB 未返回连接结果"
        lowered = output.lower()
        success = result.returncode == 0 and (
            "connected to" in lowered or "already connected" in lowered
        )
        return success, output

    def disconnect(
        self,
        endpoint: str = "",
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> tuple[bool, str]:
        args = ["disconnect"]
        if endpoint:
            raw = endpoint.strip()
            args.append(raw if is_mdns_transport_serial(raw) else normalize_endpoint(raw, DEFAULT_ADB_TCP_PORT))
        result = self.run(args, timeout=12, should_stop=should_stop)
        output = result.merged_output or "ADB 未返回断开结果"
        return result.returncode == 0, output

    def connect_services(
        self,
        host: str = "",
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> list[MdnsService]:
        result = []
        for service in self.mdns_services(should_stop=should_stop):
            if service.service_type != ADB_TLS_CONNECT_SERVICE:
                continue
            if host and endpoint_host(service.endpoint).lower() != host.lower():
                continue
            result.append(service)
        return result

    def wait_for_connection(
        self,
        host: str,
        timeout: float = 15,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> str:
        """等待主机在线；同时主动连接新发现的 TLS mDNS 端点。"""
        deadline = time.monotonic() + max(timeout, 0)
        passive_deadline = min(deadline, time.monotonic() + 3.0)
        attempted: set[str] = set()
        while time.monotonic() < deadline:
            if should_stop and should_stop():
                return ""
            try:
                records = self.devices(long=False, should_stop=should_stop)
                services = self.connect_services(host, should_stop=should_stop)
                service_aliases = {
                    f"{service.instance_name}.{service.service_type}"
                    for service in services
                }
                for record in records:
                    if record.state == "device" and _serial_matches_host(record.serial, host):
                        return record.serial
                    if record.state == "device" and record.serial in service_aliases:
                        return record.serial

                # adb pair 按官方实现会自行尝试连接。先给自动连接留出时间，避免
                # 同时执行 adb connect 导致同一手机出现 IP 与 mDNS 两条 transport。
                if time.monotonic() < passive_deadline:
                    _interruptible_sleep(0.25, should_stop)
                    continue
                for service in services:
                    if service.endpoint not in attempted:
                        attempted.add(service.endpoint)
                        ok, _ = self.connect(service.endpoint, should_stop=should_stop)
                        if ok:
                            return service.endpoint
            except AdbError:
                pass
            _interruptible_sleep(0.5, should_stop)
        return ""

    def pair_and_connect(
        self,
        endpoint: str,
        pairing_code: str,
        connect_timeout: float = 15,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> PairResult:
        resolved_endpoint, corrected = self.resolve_pairing_endpoint(endpoint, should_stop=should_stop)
        paired = self.pair(resolved_endpoint, pairing_code, should_stop=should_stop)
        if not paired.paired:
            return paired
        host = endpoint_host(paired.pairing_endpoint)
        connected = self.wait_for_connection(host, connect_timeout, should_stop)
        message = paired.message
        if corrected:
            message = f"已通过 mDNS 自动纠正配对端口为 {resolved_endpoint} | {message}"
        if connected:
            message += f" | 已连接：{connected}"
        else:
            message += " | 配对已完成，暂未发现连接端口；请保持手机无线调试开启后刷新"
        return PairResult(True, message, paired.pairing_endpoint, connected)

    def pair_via_qr(
        self,
        service_name: str,
        password: str,
        timeout: float = 90,
        should_stop: Optional[Callable[[], bool]] = None,
        on_service_found: Optional[Callable[[str], None]] = None,
    ) -> PairResult:
        """等待二维码指定的 mDNS 实例，配对并连接对应手机。"""
        if not service_name.startswith("studio-"):
            raise ValueError("二维码配对服务名必须以 studio- 开头")
        build_pairing_qr_payload(service_name, password)
        self.start_server(should_stop=should_stop)
        mdns_ok, mdns_message = self.mdns_check(should_stop=should_stop)
        if not mdns_ok:
            return PairResult(False, mdns_message)

        deadline = time.monotonic() + max(timeout, 0)
        last_error = ""
        attempts_by_endpoint: dict[str, int] = {}
        discovery_restarted = False
        while time.monotonic() < deadline:
            if should_stop and should_stop():
                return PairResult(False, "二维码配对已取消")
            try:
                target = next(
                    (
                        item
                        for item in self.mdns_services(should_stop=should_stop)
                        if item.service_type == ADB_TLS_PAIRING_SERVICE
                        and item.instance_name == service_name
                    ),
                    None,
                )
                if target is not None:
                    attempts = attempts_by_endpoint.get(target.endpoint, 0)
                    if attempts < 2:
                        attempts_by_endpoint[target.endpoint] = attempts + 1
                        if on_service_found:
                            on_service_found(target.endpoint)
                        paired = self.pair(target.endpoint, password, should_stop=should_stop)
                        if paired.paired:
                            host = endpoint_host(paired.pairing_endpoint)
                            connected = self.wait_for_connection(host, 15, should_stop)
                            message = paired.message
                            if connected:
                                message += f" | 已连接：{connected}"
                            else:
                                message += " | 配对已完成，暂未发现连接端口；请保持手机无线调试开启后刷新"
                            return PairResult(
                                True,
                                message,
                                paired.pairing_endpoint,
                                connected,
                            )

                        last_error = paired.message
                        # ADB 的 mDNS 结果偶尔会保留已失效端口。首次失败后只刷新一次
                        # server；TCP 不可达时同时清除 Windows 中目标手机的失败邻居项。
                        # 若手机仍在配对页，同一服务会被重新发现并重试。
                        if not discovery_restarted and time.monotonic() < deadline:
                            if "TCP 通道不可达" in paired.message:
                                clear_host_neighbor_cache(endpoint_host(target.endpoint))
                            self.restart_server(should_stop=should_stop)
                            discovery_restarted = True
                            mdns_ok, mdns_message = self.mdns_check(should_stop=should_stop)
                            if not mdns_ok:
                                return PairResult(False, mdns_message)
            except AdbError as exc:
                last_error = str(exc)
            _interruptible_sleep(0.5, should_stop)
        message = "等待二维码配对服务超时，请确认手机与电脑在同一局域网并重新扫码"
        if last_error:
            message += f" | 最后错误：{last_error}"
        return PairResult(False, message, timed_out=True)

    def get_wlan_ipv4(
        self,
        serial: str,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> str:
        outputs: list[str] = []
        commands = (
            ["shell", "ip", "-f", "inet", "addr", "show", "wlan0"],
            ["shell", "ip", "route", "get", "8.8.8.8"],
            ["shell", "ip", "route"],
            ["shell", "ifconfig", "wlan0"],
        )
        for command in commands:
            result = self.run(command, timeout=8, serial=serial, should_stop=should_stop)
            outputs.append(result.merged_output)
            address = parse_wlan_ipv4(outputs[-1:])
            if address:
                return address
        return ""

    def enable_tcpip(
        self,
        serial: str,
        port: int = DEFAULT_ADB_TCP_PORT,
        connect_timeout: float = 12,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> TcpIpResult:
        if not serial:
            return TcpIpResult(False, "请先选择通过 USB 连接的设备")
        port = _validated_port(str(port), None)
        address = self.get_wlan_ipv4(serial, should_stop=should_stop)
        if not address:
            return TcpIpResult(False, "无法读取手机 WLAN IPv4，请确认手机已连接 Wi-Fi")
        endpoint = normalize_endpoint(address, port)
        result = self.run(
            ["tcpip", str(port)],
            timeout=20,
            serial=serial,
            should_stop=should_stop,
        )
        output = result.merged_output or "ADB 未返回 tcpip 切换结果"
        if result.returncode != 0 or "error" in output.lower() or "failed" in output.lower():
            return TcpIpResult(False, output, endpoint)

        deadline = time.monotonic() + max(connect_timeout, 0)
        last_message = output
        while time.monotonic() < deadline:
            if should_stop and should_stop():
                return TcpIpResult(False, "USB 转无线操作已取消", endpoint)
            try:
                ok, last_message = self.connect(endpoint, should_stop=should_stop)
                if ok:
                    return TcpIpResult(True, f"{output} | {last_message}", endpoint)
            except AdbError as exc:
                last_message = str(exc)
            _interruptible_sleep(0.75, should_stop)
        return TcpIpResult(False, f"{output} | 无线连接失败：{last_message}", endpoint)

    def use_usb(
        self,
        serial: str,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> tuple[bool, str]:
        if not serial:
            return False, "请先选择设备"
        result = self.run(["usb"], timeout=15, serial=serial, should_stop=should_stop)
        output = result.merged_output or "ADB 未返回 USB 模式切换结果"
        lowered = output.lower()
        return result.returncode == 0 and "error" not in lowered and "failed" not in lowered, output


def _serial_matches_host(serial: str, host: str) -> bool:
    try:
        return endpoint_host(serial).lower() == host.lower()
    except ValueError:
        return host.lower() in serial.lower() and ADB_TLS_CONNECT_SERVICE in serial


def _terminate_subprocess(proc: subprocess.Popen) -> None:
    try:
        proc.kill()
    except Exception:
        pass
    try:
        proc.communicate(timeout=0.5)
    except Exception:
        pass


def _interruptible_sleep(seconds: float, should_stop: Optional[Callable[[], bool]]) -> None:
    deadline = time.monotonic() + max(seconds, 0)
    while time.monotonic() < deadline:
        if should_stop and should_stop():
            return
        time.sleep(min(0.05, max(0, deadline - time.monotonic())))
