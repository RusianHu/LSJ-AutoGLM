# -*- coding: utf-8 -*-
"""
设备服务 - 管理 ADB 设备连接、状态轮询与检查。

修复记录：
- 添加 stop() 公共接口，供 MainWindow.closeEvent 统一调用
- refresh() 改为在 QThread 中执行 ADB 命令，避免 UI 主线程阻塞
- _enrich_device_info 改为在 worker 线程中执行
"""

import re
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, List, Optional, Tuple

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from gui.services.adb_client import (
    ADB_TLS_CONNECT_SERVICE,
    AdbClient,
    AdbError,
    DEFAULT_ADB_TCP_PORT,
    MdnsService,
    is_mdns_transport_serial,
    normalize_endpoint,
)
from gui.utils.runtime import find_adb_executable, find_adb_keyboard_apk


class DeviceStatus(Enum):
    """设备连接状态"""
    UNKNOWN = "unknown"
    CONNECTED = "connected"
    UNAUTHORIZED = "unauthorized"
    OFFLINE = "offline"
    DISCONNECTED = "disconnected"


class AdbTransport(Enum):
    """ADB transport 类型；用于约束允许的连接/断开操作。"""

    USB = "usb"
    TCPIP = "tcpip"
    TLS_MDNS = "tls_mdns"
    EMULATOR = "emulator"
    UNKNOWN = "unknown"


@dataclass
class DeviceInfo:
    """设备信息"""
    device_id: str
    status: DeviceStatus
    connection_type: str = "unknown"   # usb / wifi / unknown
    transport_type: AdbTransport = AdbTransport.UNKNOWN
    model: str = ""
    android_version: str = ""
    adb_keyboard_installed: bool = False
    adb_keyboard_enabled: bool = False
    adb_keyboard_status: str = "ADB Keyboard 未安装"

    @property
    def display_name(self) -> str:
        parts = []
        if self.model:
            parts.append(self.model)
        parts.append(self.device_id)
        if self.android_version:
            parts.append(f"Android {self.android_version}")
        return " | ".join(parts)


ADB_KEYBOARD_PACKAGE = "com.android.adbkeyboard"
ADB_KEYBOARD_IME = "com.android.adbkeyboard/.AdbIME"
StopChecker = Callable[[], bool]


def _terminate_process(proc: subprocess.Popen) -> None:
    try:
        proc.kill()
    except Exception:
        pass
    try:
        proc.communicate(timeout=0.2)
    except Exception:
        pass



def _classify_transport(device_id: str) -> AdbTransport:
    """根据 ADB serial 区分 USB、传统 TCP/IP、TLS/mDNS 与模拟器。"""
    normalized = (device_id or "").strip().lower()
    if not normalized:
        return AdbTransport.UNKNOWN
    if is_mdns_transport_serial(normalized):
        return AdbTransport.TLS_MDNS
    if re.fullmatch(r"emulator-\d+", normalized):
        return AdbTransport.EMULATOR
    try:
        normalize_endpoint(normalized)
        return AdbTransport.TCPIP
    except ValueError:
        return AdbTransport.USB


def _infer_connection_type(device_id: str) -> str:
    transport = _classify_transport(device_id)
    if transport == AdbTransport.USB:
        return "usb"
    if transport in {AdbTransport.TCPIP, AdbTransport.TLS_MDNS}:
        return "wifi"
    if transport == AdbTransport.EMULATOR:
        return "emulator"
    return "unknown"


def _normalize_connect_address(address: str) -> str:
    try:
        return normalize_endpoint(address, DEFAULT_ADB_TCP_PORT)
    except ValueError:
        return (address or "").strip()



def _is_reconnectable_wifi_address(address: str) -> bool:
    normalized = _normalize_connect_address(address)
    if not normalized:
        return False
    lowered = normalized.lower()
    if (
        "._adb-tls-connect._tcp" in lowered
        or "._adb-tls-pairing._tcp" in lowered
    ):
        return False
    host, _, port = normalized.rpartition(":")
    return bool(host and port.isdigit())



def _run_adb_connect(address: str, timeout: int = 15) -> Tuple[bool, str]:
    del timeout  # AdbClient 统一管理连接超时和输出判断
    return AdbClient().connect(address)


def _deduplicate_tls_devices(devices: List[DeviceInfo], services: List[MdnsService]) -> List[DeviceInfo]:
    """用 mDNS 标记 TLS 端点，并合并同一 transport 的别名与显式地址。"""
    ids = {device.device_id for device in devices}
    tls_endpoints: dict[str, str] = {}
    for service in services:
        if service.service_type != ADB_TLS_CONNECT_SERVICE:
            continue
        alias = f"{service.instance_name}.{service.service_type}"
        tls_endpoints[service.endpoint] = alias

    result: List[DeviceInfo] = []
    for device in devices:
        alias = tls_endpoints.get(device.device_id)
        if alias:
            # adb connect <TLS endpoint> 只会在 devices 中显示 IP:port；结合
            # mDNS 服务才能与传统明文 adb tcpip transport 正确区分。
            device.transport_type = AdbTransport.TLS_MDNS
            device.connection_type = "wifi"
            if alias in ids:
                continue
        result.append(device)
    return result



def _run_adb_shell(
    device_id: str,
    args: List[str],
    timeout: int = 5,
    *,
    should_stop: StopChecker | None = None,
) -> subprocess.CompletedProcess:
    proc = subprocess.Popen(
        ["adb", "-s", device_id, "shell", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.monotonic() + max(timeout, 0)
    while True:
        if callable(should_stop) and should_stop():
            _terminate_process(proc)
            raise InterruptedError("ADB 检查已取消")
        ret = proc.poll()
        if ret is not None:
            stdout, stderr = proc.communicate()
            return subprocess.CompletedProcess(["adb", "-s", device_id, "shell", *args], ret, stdout, stderr)
        if time.monotonic() >= deadline:
            _terminate_process(proc)
            raise subprocess.TimeoutExpired(["adb", "-s", device_id, "shell", *args], timeout)
        time.sleep(0.05)



def probe_adb_keyboard_status(
    device_id: str,
    timeout: int = 5,
    *,
    should_stop: StopChecker | None = None,
) -> Tuple[bool, bool, str]:
    """返回 (是否安装, 是否已启用/可直接切换, 状态文本)。"""
    installed = False
    enabled = False
    current_ime = ""

    try:
        result = _run_adb_shell(
            device_id,
            ["pm", "list", "packages", ADB_KEYBOARD_PACKAGE],
            timeout=timeout,
            should_stop=should_stop,
        )
        installed = ADB_KEYBOARD_PACKAGE in ((result.stdout or "") + (result.stderr or ""))
    except InterruptedError:
        raise
    except Exception:
        installed = False

    try:
        result = _run_adb_shell(
            device_id,
            ["ime", "list", "-s"],
            timeout=timeout,
            should_stop=should_stop,
        )
        ime_list = ((result.stdout or "") + (result.stderr or "")).strip()
        enabled = ADB_KEYBOARD_IME in ime_list
    except InterruptedError:
        raise
    except Exception:
        enabled = False

    try:
        result = _run_adb_shell(
            device_id,
            ["settings", "get", "secure", "default_input_method"],
            timeout=timeout,
            should_stop=should_stop,
        )
        current_ime = ((result.stdout or "") + (result.stderr or "")).strip()
    except InterruptedError:
        raise
    except Exception:
        current_ime = ""

    if ADB_KEYBOARD_IME in current_ime:
        return True, True, "ADB Keyboard 当前已启用"
    if enabled:
        return installed or True, True, "ADB Keyboard 已启用"
    if installed:
        return True, False, "ADB Keyboard 已安装但未启用"
    return False, False, "ADB Keyboard 未安装"


class _RefreshWorker(QThread):
    """在后台线程中执行 adb devices 枚举，避免阻塞 UI"""
    result_ready = Signal(list)   # List[DeviceInfo]
    adb_error = Signal(str)

    def __init__(self, reconnect_address: str = "", parent=None):
        super().__init__(parent)
        self._stop_requested = False
        self._proc: Optional[subprocess.Popen] = None
        self._reconnect_address = _normalize_connect_address(reconnect_address)

    def request_stop(self):
        self._stop_requested = True
        proc = self._proc
        if proc is not None:
            _terminate_process(proc)

    def _should_stop(self) -> bool:
        return self._stop_requested

    def run(self):
        try:
            result = self._run_adb_devices(timeout=10)
            if self._should_stop():
                return
            if result.returncode != 0:
                self.adb_error.emit(f"adb devices 失败: {result.stderr}")
                return
            devices = self._parse(result.stdout)
            devices = self._deduplicate_tls_transports(devices)
            if self._should_stop():
                return

            if self._reconnect_address and not self._has_connected_device(devices, self._reconnect_address):
                self._try_reconnect(self._reconnect_address)
                if self._should_stop():
                    return
                result = self._run_adb_devices(timeout=10)
                if self._should_stop():
                    return
                if result.returncode != 0:
                    self.adb_error.emit(f"adb devices 失败: {result.stderr}")
                    return
                devices = self._parse(result.stdout)
                devices = self._deduplicate_tls_transports(devices)
                if self._should_stop():
                    return

            self.result_ready.emit(devices)
        except InterruptedError:
            return
        except FileNotFoundError:
            self.adb_error.emit("ADB 未找到，请确认已安装并加入 PATH")
        except Exception as e:
            if not self._should_stop():
                self.adb_error.emit(f"设备刷新异常: {e}")
        finally:
            self._proc = None

    @staticmethod
    def _has_connected_device(devices: List[DeviceInfo], device_id: str) -> bool:
        normalized = _normalize_connect_address(device_id)
        return any(
            d.device_id == normalized and d.status == DeviceStatus.CONNECTED
            for d in devices
        )

    @staticmethod
    def _deduplicate_tls_transports(devices: List[DeviceInfo]) -> List[DeviceInfo]:
        try:
            services = AdbClient().mdns_services()
        except (AdbError, ValueError):
            return devices
        return _deduplicate_tls_devices(devices, services)

    def _try_reconnect(self, address: str) -> None:
        try:
            _run_adb_connect(address, timeout=8)
        except FileNotFoundError:
            raise
        except Exception:
            pass

    def _run_adb_devices(self, timeout: int = 10) -> subprocess.CompletedProcess:
        self._proc = subprocess.Popen(
            ["adb", "devices", "-l"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        deadline = time.monotonic() + max(timeout, 0)
        while True:
            if self._should_stop():
                _terminate_process(self._proc)
                raise InterruptedError("设备刷新已取消")
            ret = self._proc.poll()
            if ret is not None:
                stdout, stderr = self._proc.communicate()
                return subprocess.CompletedProcess(["adb", "devices", "-l"], ret, stdout, stderr)
            if time.monotonic() >= deadline:
                _terminate_process(self._proc)
                raise subprocess.TimeoutExpired(["adb", "devices", "-l"], timeout)
            time.sleep(0.05)

    def _parse(self, output: str) -> List[DeviceInfo]:
        devices = []
        known_states = {"device", "offline", "unauthorized", "no permissions", "bootloader"}
        for line in output.splitlines()[1:]:
            line = line.strip()
            if not line:
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
            device_id = " ".join(parts[:state_index])
            status_str = parts[state_index]

            status_map = {
                "device":       DeviceStatus.CONNECTED,
                "unauthorized": DeviceStatus.UNAUTHORIZED,
                "offline":      DeviceStatus.OFFLINE,
            }
            status = status_map.get(status_str, DeviceStatus.UNKNOWN)
            conn_type = _infer_connection_type(device_id)
            transport_type = _classify_transport(device_id)

            model = ""
            for part in parts[state_index + 1:]:
                if part.startswith("model:"):
                    model = part.split(":", 1)[1].replace("_", " ")
                    break

            info = DeviceInfo(
                device_id=device_id,
                status=status,
                connection_type=conn_type,
                transport_type=transport_type,
                model=model,
            )
            if status == DeviceStatus.CONNECTED:
                self._enrich(info)
            devices.append(info)
        return devices

    def _enrich(self, info: DeviceInfo):
        """补充 Android 版本、型号、ADB Keyboard 状态"""
        if self._should_stop():
            return

        try:
            r = subprocess.run(
                ["adb", "-s", info.device_id, "shell",
                 "getprop", "ro.build.version.release"],
                capture_output=True, text=True, timeout=5
            )
            if r.returncode == 0:
                info.android_version = r.stdout.strip()
        except Exception:
            pass

        if self._should_stop():
            return

        if not info.model:
            try:
                r2 = subprocess.run(
                    ["adb", "-s", info.device_id, "shell",
                     "getprop", "ro.product.model"],
                    capture_output=True, text=True, timeout=5
                )
                if r2.returncode == 0:
                    info.model = r2.stdout.strip()
            except Exception:
                pass

        if self._should_stop():
            return

        try:
            installed, enabled, status = probe_adb_keyboard_status(
                info.device_id,
                timeout=5,
                should_stop=self._should_stop,
            )
            info.adb_keyboard_installed = installed
            info.adb_keyboard_enabled = enabled
            info.adb_keyboard_status = status
        except InterruptedError:
            return
        except Exception:
            pass


class _AdbOperationWorker(QThread):
    """串行执行一次可能耗时的 ADB 连接操作。"""

    result_ready = Signal(str, bool, str, str)

    def __init__(self, operation: str, callback, parent=None):
        super().__init__(parent)
        self.operation = operation
        self._callback = callback
        self._stop_requested = False

    def request_stop(self):
        self._stop_requested = True

    def should_stop(self) -> bool:
        return self._stop_requested

    def run(self):
        try:
            success, message, payload = self._callback(self.should_stop)
        except (AdbError, ValueError) as exc:
            success, message, payload = False, str(exc), ""
        except Exception as exc:
            success, message, payload = False, f"ADB 操作异常：{exc}", ""
        if not self._stop_requested:
            self.result_ready.emit(self.operation, bool(success), str(message), str(payload or ""))


class DeviceService(QObject):
    """
    设备服务 - 负责：
    - 枚举已连接 ADB 设备（异步，不阻塞 UI）
    - 获取设备详细信息
    - 连接/断开无线设备
    - ADB 可用性检查
    - ADB Keyboard 检查
    - 定时刷新设备状态（每 5 秒）
    """

    devices_changed = Signal(list)          # List[DeviceInfo]
    device_selected = Signal(object)        # DeviceInfo | None
    adb_status_changed = Signal(bool, str)  # (available, message)
    error_occurred = Signal(str)
    operation_started = Signal(str)
    operation_finished = Signal(str, bool, str, str)  # operation, success, message, payload

    POLL_INTERVAL_MS = 5000
    AUTO_RECONNECT_COOLDOWN_SEC = 15.0

    def __init__(self, config_service=None, parent=None):
        super().__init__(parent)
        self._config = config_service
        self._adb_path: str = "adb"
        self._adb_client = AdbClient(self._adb_path)
        self._devices: List[DeviceInfo] = []
        self._selected_device: Optional[DeviceInfo] = None
        self._adb_available: bool = False
        self._worker: Optional[_RefreshWorker] = None
        self._operation_worker: Optional[_AdbOperationWorker] = None
        self._operation_in_progress: bool = False
        self._stopping: bool = False
        self._last_auto_reconnect_address: str = ""
        self._last_auto_reconnect_at: float = 0.0

        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self.refresh)
        self._poll_timer.start(self.POLL_INTERVAL_MS)

        # 启动时延迟 200ms 做第一次检查，避免阻塞主窗口初始化
        self._initial_timer = QTimer(self)
        self._initial_timer.setSingleShot(True)
        self._initial_timer.timeout.connect(self._initial_check)
        self._initial_timer.start(200)

    def _initial_check(self):
        if self._stopping:
            return
        self.check_adb()
        self.refresh()

    # ---------- ADB 检查（同步，仅检查可执行文件，速度快） ----------

    def check_adb(self) -> Tuple[bool, str]:
        """检查 ADB 是否可用（同步，仅运行 adb version，通常极快）"""
        adb_executable = find_adb_executable()
        if adb_executable is None:
            self._adb_available = False
            msg = "ADB 未找到，请确认 ADB 已安装并加入 PATH"
            self.adb_status_changed.emit(False, msg)
            return False, msg

        try:
            result = subprocess.run(
                [str(adb_executable), "version"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                version_lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
                version_text = " | ".join(version_lines[:2]) if version_lines else "ADB"
                version_text = f"{version_text} | {adb_executable}"
                self._adb_available = True
                self._adb_path = str(adb_executable)
                self._adb_client = AdbClient(self._adb_path)
                self.adb_status_changed.emit(True, version_text)
                return True, version_text
            else:
                self._adb_available = False
                msg = f"ADB 运行异常: {result.stderr}"
                self.adb_status_changed.emit(False, msg)
                return False, msg
        except Exception as e:
            self._adb_available = False
            msg = f"ADB 检查失败: {e}"
            self.adb_status_changed.emit(False, msg)
            return False, msg

    @property
    def adb_available(self) -> bool:
        return self._adb_available

    @property
    def adb_client(self) -> AdbClient:
        return self._adb_client

    def _remember_connected_address(self, address: str):
        normalized = _normalize_connect_address(address)
        if not self._config or not _is_reconnectable_wifi_address(normalized):
            return
        current = (self._config.get("OPEN_AUTOGLM_DEVICE_ID") or "").strip()
        if current == normalized:
            return
        try:
            self._config.set("OPEN_AUTOGLM_DEVICE_ID", normalized)
        except Exception as e:
            self.error_occurred.emit(f"保存设备记忆失败: {e}")

    def _clear_remembered_address(self, address: str):
        if not self._config:
            return
        raw = (address or "").strip()
        normalized = _normalize_connect_address(raw)
        current = (self._config.get("OPEN_AUTOGLM_DEVICE_ID") or "").strip()
        # TLS mDNS 名称与历史 IP:port 可能代表同一台手机。用户主动断开
        # mDNS transport 时必须同时停用旧的自动重连地址，否则轮询线程会
        # 很快把刚断开的手机重新连上，看起来就像“断开无效”。
        disconnecting_tls = is_mdns_transport_serial(raw)
        if current not in {raw, normalized} and not (
            disconnecting_tls and _is_reconnectable_wifi_address(current)
        ):
            return
        try:
            self._config.set("OPEN_AUTOGLM_DEVICE_ID", "")
        except Exception as e:
            self.error_occurred.emit(f"清除设备记忆失败: {e}")

    def _preferred_reconnect_address(self) -> str:
        if not self._config:
            return ""
        configured = (self._config.get("OPEN_AUTOGLM_DEVICE_ID") or "").strip()
        if not _is_reconnectable_wifi_address(configured):
            return ""
        normalized = _normalize_connect_address(configured)
        if any(
            d.device_id == normalized and d.status == DeviceStatus.CONNECTED
            for d in self._devices
        ):
            return ""
        now = time.monotonic()
        if (
            self._last_auto_reconnect_address == normalized
            and now - self._last_auto_reconnect_at < self.AUTO_RECONNECT_COOLDOWN_SEC
        ):
            return ""
        self._last_auto_reconnect_address = normalized
        self._last_auto_reconnect_at = now
        return normalized

    # ---------- 异步设备枚举 ----------

    def refresh(self):
        """异步刷新设备列表（不阻塞 UI 线程）"""
        if self._stopping:
            return
        # 配对/连接/断开期间由操作线程独占连接状态；完成信号会主动刷新。
        # 避免定时轮询携带旧配置并发执行 adb connect，产生重复 transport。
        if self.operation_running:
            return
        if not self._adb_available:
            self.check_adb()
            if not self._adb_available:
                return

        # 若上一次 worker 还未完成，跳过本次刷新（避免并发）
        if self._worker and self._worker.isRunning():
            return

        reconnect_address = self._preferred_reconnect_address()
        self._worker = _RefreshWorker(reconnect_address=reconnect_address)
        self._worker.result_ready.connect(self._on_refresh_done)
        self._worker.finished.connect(self._cleanup_worker)
        self._worker.adb_error.connect(self._on_refresh_error)
        self._worker.start()

    def _on_refresh_done(self, devices: List[DeviceInfo]):
        self._devices = devices

        # 若当前选中设备已不在列表，自动清空选择；若仍存在则更新为最新对象并重新发信号
        if self._selected_device:
            ids = [d.device_id for d in devices]
            if self._selected_device.device_id not in ids:
                self._selected_device = None
                self.device_selected.emit(None)
            else:
                for d in devices:
                    if d.device_id == self._selected_device.device_id:
                        self._selected_device = d
                        self.device_selected.emit(d)
                        break

        self.devices_changed.emit(devices)

    def _on_refresh_error(self, msg: str):
        self.error_occurred.emit(msg)

    def _cleanup_worker(self, *_args):
        worker = self.sender()
        if worker and worker is self._worker:
            self._worker = None
        if worker:
            worker.deleteLater()

    # ---------- 连接管理 ----------

    def pair_device(self, address: str, pairing_code: str) -> Tuple[bool, str]:
        """
        通过配对码与设备配对（Android 11+ 无线调试 / 二维码配对模式）。
        address 格式：ip:port（配对端口，与连接端口不同）
        pairing_code：6位数字配对码
        """
        try:
            result = self._adb_client.pair_and_connect(address, pairing_code, connect_timeout=15)
            if result.connected_endpoint:
                self._remember_connected_address(result.connected_endpoint)
            self.refresh()
            return result.paired, result.message
        except (AdbError, ValueError) as exc:
            return False, str(exc)

    def connect_device(self, address: str) -> Tuple[bool, str]:
        """无线连接设备"""
        try:
            normalized = normalize_endpoint(address, DEFAULT_ADB_TCP_PORT)
            success, msg = self._adb_client.connect(normalized)
            if success:
                self._remember_connected_address(normalized)
                self.refresh()
            return success, msg
        except (AdbError, ValueError) as exc:
            return False, str(exc)

    def disconnect_device(self, device_id: str) -> Tuple[bool, str]:
        """断开指定设备"""
        transport = _classify_transport(device_id)
        if transport not in {AdbTransport.TCPIP, AdbTransport.TLS_MDNS}:
            return False, "仅无线 ADB transport 支持主动断开；USB 设备请拔出数据线"
        target = _normalize_connect_address(device_id) if _is_reconnectable_wifi_address(device_id) else device_id
        try:
            success, msg = self._adb_client.disconnect(target)
            if success:
                self._clear_remembered_address(target)
            self.refresh()
            return success, msg
        except (AdbError, ValueError) as exc:
            return False, str(exc)

    def enable_tcpip_device(self, device_id: str, port: int = DEFAULT_ADB_TCP_PORT) -> Tuple[bool, str, str]:
        """按 QtScrcpy 链路将 USB 设备切换为传统 ADB TCP/IP。"""
        device = next((item for item in self._devices if item.device_id == device_id), None)
        transport = device.transport_type if device is not None else _classify_transport(device_id)
        if transport != AdbTransport.USB:
            return False, "该操作需要先选择 USB 连接的设备", ""
        try:
            result = self._adb_client.enable_tcpip(device_id, port=port)
            if result.success and result.endpoint:
                self._remember_connected_address(result.endpoint)
                self.refresh()
            return result.success, result.message, result.endpoint
        except (AdbError, ValueError) as exc:
            return False, str(exc), ""

    def use_usb_device(self, device_id: str) -> Tuple[bool, str]:
        """要求目标 adbd 恢复 USB 传输模式。"""
        device = next((item for item in self._devices if item.device_id == device_id), None)
        transport = device.transport_type if device is not None else _classify_transport(device_id)
        if transport != AdbTransport.TCPIP:
            return False, "恢复 USB 模式仅适用于 adb tcpip 建立的传统无线连接"
        try:
            success, message = self._adb_client.use_usb(device_id)
            self.refresh()
            return success, message
        except (AdbError, ValueError) as exc:
            return False, str(exc)

    @property
    def operation_running(self) -> bool:
        return self._operation_in_progress

    def _start_operation(self, operation: str, callback) -> bool:
        if self.operation_running:
            self.error_occurred.emit("已有 ADB 连接操作正在执行，请稍候")
            return False
        worker = _AdbOperationWorker(operation, callback)
        worker.result_ready.connect(self._on_operation_done)
        worker.finished.connect(self._cleanup_operation_worker)
        self._operation_worker = worker
        self._operation_in_progress = True
        self.operation_started.emit(operation)
        worker.start()
        return True

    def connect_device_async(self, address: str) -> bool:
        def callback(should_stop):
            normalized = normalize_endpoint(address, DEFAULT_ADB_TCP_PORT)
            success, message = self._adb_client.connect(normalized, should_stop=should_stop)
            if success:
                self._remember_connected_address(normalized)
            return success, message, normalized

        return self._start_operation("connect", callback)

    def disconnect_device_async(self, device_id: str) -> bool:
        def callback(should_stop):
            transport = _classify_transport(device_id)
            if transport not in {AdbTransport.TCPIP, AdbTransport.TLS_MDNS}:
                return False, "仅无线 ADB transport 支持主动断开；USB 设备请拔出数据线", device_id
            target = _normalize_connect_address(device_id) if _is_reconnectable_wifi_address(device_id) else device_id
            success, message = self._adb_client.disconnect(target, should_stop=should_stop)
            if success:
                self._clear_remembered_address(target)
            return success, message, target

        return self._start_operation("disconnect", callback)

    def pair_device_async(self, address: str, pairing_code: str) -> bool:
        def callback(should_stop):
            result = self._adb_client.pair_and_connect(
                address,
                pairing_code,
                connect_timeout=15,
                should_stop=should_stop,
            )
            if result.connected_endpoint:
                self._remember_connected_address(result.connected_endpoint)
            return result.paired, result.message, result.connected_endpoint

        return self._start_operation("pair", callback)

    def enable_tcpip_device_async(self, device_id: str, port: int = DEFAULT_ADB_TCP_PORT) -> bool:
        def callback(should_stop):
            device = next((item for item in self._devices if item.device_id == device_id), None)
            transport = device.transport_type if device is not None else _classify_transport(device_id)
            if transport != AdbTransport.USB:
                return False, "该操作需要先选择 USB 连接的设备", ""
            result = self._adb_client.enable_tcpip(
                device_id,
                port=port,
                should_stop=should_stop,
            )
            if result.success and result.endpoint:
                self._remember_connected_address(result.endpoint)
            return result.success, result.message, result.endpoint

        return self._start_operation("tcpip", callback)

    def use_usb_device_async(self, device_id: str) -> bool:
        def callback(should_stop):
            device = next((item for item in self._devices if item.device_id == device_id), None)
            transport = device.transport_type if device is not None else _classify_transport(device_id)
            if transport != AdbTransport.TCPIP:
                return False, "恢复 USB 模式仅适用于 adb tcpip 建立的传统无线连接", device_id
            success, message = self._adb_client.use_usb(device_id, should_stop=should_stop)
            return success, message, device_id

        return self._start_operation("usb", callback)

    def _on_operation_done(self, operation: str, success: bool, message: str, payload: str):
        self._operation_in_progress = False
        self.operation_finished.emit(operation, success, message, payload)
        self.refresh()

    def _cleanup_operation_worker(self, *_args):
        worker = self.sender()
        if worker and worker is self._operation_worker:
            self._operation_worker = None
            self._operation_in_progress = False
        if worker:
            worker.deleteLater()

    def select_device(self, device_id: Optional[str]):
        """选中设备"""
        if device_id is None:
            self._selected_device = None
            self.device_selected.emit(None)
            return
        for d in self._devices:
            if d.device_id == device_id:
                self._selected_device = d
                self.device_selected.emit(d)
                return

    @property
    def selected_device(self) -> Optional[DeviceInfo]:
        return self._selected_device

    @property
    def devices(self) -> List[DeviceInfo]:
        return list(self._devices)

    # ---------- scrcpy 检查 ----------

    def check_scrcpy(self) -> Tuple[bool, str]:
        from gui.services.mirror_service import MirrorService

        path = MirrorService.find_scrcpy()
        if path:
            try:
                r = subprocess.run(
                    [path, "--version"],
                    capture_output=True, text=True, timeout=5
                )
                ver = r.stdout.strip().splitlines()[0] if r.stdout else "scrcpy"
                return True, f"{ver} ({path})"
            except Exception:
                return True, f"scrcpy: {path}"
        return False, "scrcpy 未找到"

    # ---------- ADB Keyboard 检查 ----------

    def check_adb_keyboard(self, device_id: str) -> Tuple[bool, str]:
        try:
            _installed, enabled, status = probe_adb_keyboard_status(device_id, timeout=10)
            return enabled, status
        except Exception as e:
            return False, str(e)

    def install_adb_keyboard(self, device_id: str) -> Tuple[bool, str]:
        apk_path = find_adb_keyboard_apk()
        if apk_path is None:
            return False, "未找到 ADBKeyboard.apk，请检查分发包是否完整"

        try:
            result = subprocess.run(
                ["adb", "-s", device_id, "install", "-r", str(apk_path)],
                capture_output=True,
                text=True,
                timeout=60,
            )
            stdout = (result.stdout or "").strip()
            stderr = (result.stderr or "").strip()
            merged = stdout or stderr or "ADB Keyboard 安装完成"
            if result.returncode != 0:
                return False, merged

            subprocess.run(
                ["adb", "-s", device_id, "shell", "ime", "enable", ADB_KEYBOARD_IME],
                capture_output=True,
                text=True,
                timeout=15,
            )
            return True, f"{merged}（已尝试启用 ADB Keyboard）"
        except Exception as e:
            return False, str(e)

    # ---------- 生命周期 ----------

    def stop(self):
        """停止定时器与后台 worker，供应用退出时调用"""
        self._stopping = True
        self._poll_timer.stop()
        if hasattr(self, "_initial_timer"):
            self._initial_timer.stop()
        if self._worker:
            if self._worker.isRunning():
                self._worker.request_stop()
                self._worker.wait(3000)
            if self._worker and not self._worker.isRunning():
                self._worker.deleteLater()
            self._worker = None
        if self._operation_worker:
            if self._operation_worker.isRunning():
                self._operation_worker.request_stop()
                self._operation_worker.wait(3000)
            if not self._operation_worker.isRunning():
                self._operation_worker.deleteLater()
            self._operation_worker = None
            self._operation_in_progress = False
