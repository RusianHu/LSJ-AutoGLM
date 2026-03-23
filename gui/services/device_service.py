# -*- coding: utf-8 -*-
"""
设备服务 - 管理 ADB 设备连接、状态轮询与检查。

修复记录：
- 添加 stop() 公共接口，供 MainWindow.closeEvent 统一调用
- refresh() 改为在 QThread 中执行 ADB 命令，避免 UI 主线程阻塞
- _enrich_device_info 改为在 worker 线程中执行
"""

import shutil
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, List, Optional, Tuple

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from gui.utils.runtime import find_adb_keyboard_apk


class DeviceStatus(Enum):
    """设备连接状态"""
    UNKNOWN = "unknown"
    CONNECTED = "connected"
    UNAUTHORIZED = "unauthorized"
    OFFLINE = "offline"
    DISCONNECTED = "disconnected"


@dataclass
class DeviceInfo:
    """设备信息"""
    device_id: str
    status: DeviceStatus
    connection_type: str = "unknown"   # usb / wifi / unknown
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



def _infer_connection_type(device_id: str) -> str:
    """根据 adb 设备 ID 推断连接方式。"""
    normalized = (device_id or "").strip().lower()
    if not normalized:
        return "unknown"
    if ":" in normalized:
        return "wifi"
    if (
        "._adb-tls-connect._tcp" in normalized
        or "._adb-tls-pairing._tcp" in normalized
    ):
        return "wifi"
    return "usb"


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

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop_requested = False
        self._proc: Optional[subprocess.Popen] = None

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
        for line in output.splitlines()[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            device_id = parts[0]
            status_str = parts[1]

            status_map = {
                "device":       DeviceStatus.CONNECTED,
                "unauthorized": DeviceStatus.UNAUTHORIZED,
                "offline":      DeviceStatus.OFFLINE,
            }
            status = status_map.get(status_str, DeviceStatus.UNKNOWN)
            conn_type = _infer_connection_type(device_id)

            model = ""
            for part in parts[2:]:
                if part.startswith("model:"):
                    model = part.split(":", 1)[1].replace("_", " ")
                    break

            info = DeviceInfo(
                device_id=device_id,
                status=status,
                connection_type=conn_type,
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

    POLL_INTERVAL_MS = 5000

    def __init__(self, parent=None):
        super().__init__(parent)
        self._adb_path: str = "adb"
        self._devices: List[DeviceInfo] = []
        self._selected_device: Optional[DeviceInfo] = None
        self._adb_available: bool = False
        self._worker: Optional[_RefreshWorker] = None
        self._stopping: bool = False

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
        path = shutil.which("adb")
        if path is None:
            self._adb_available = False
            msg = "ADB 未找到，请确认 ADB 已安装并加入 PATH"
            self.adb_status_changed.emit(False, msg)
            return False, msg

        try:
            result = subprocess.run(
                ["adb", "version"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                version_line = result.stdout.splitlines()[0] if result.stdout else "ADB"
                self._adb_available = True
                self._adb_path = path
                self.adb_status_changed.emit(True, version_line)
                return True, version_line
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

    # ---------- 异步设备枚举 ----------

    def refresh(self):
        """异步刷新设备列表（不阻塞 UI 线程）"""
        if self._stopping:
            return
        if not self._adb_available:
            self.check_adb()
            if not self._adb_available:
                return

        # 若上一次 worker 还未完成，跳过本次刷新（避免并发）
        if self._worker and self._worker.isRunning():
            return

        self._worker = _RefreshWorker()
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
        if ":" not in address:
            return False, "地址格式错误，需包含配对端口，例如：192.168.x.x:37890"
        try:
            r = subprocess.run(
                ["adb", "pair", address, pairing_code],
                capture_output=True, text=True, timeout=30
            )
            output = (r.stdout + r.stderr).strip()
            # adb pair 成功输出包含 "Successfully paired"
            success = "successfully paired" in output.lower()
            if success:
                self.refresh()
            return success, output or "无输出"
        except FileNotFoundError:
            return False, "ADB 未找到，请确认已安装并加入 PATH"
        except Exception as e:
            return False, str(e)

    def connect_device(self, address: str) -> Tuple[bool, str]:
        """无线连接设备"""
        if ":" not in address:
            address = f"{address}:5555"
        try:
            r = subprocess.run(
                ["adb", "connect", address],
                capture_output=True, text=True, timeout=15
            )
            success = "connected" in r.stdout.lower()
            msg = r.stdout.strip() or r.stderr.strip()
            if success:
                self.refresh()
            return success, msg
        except Exception as e:
            return False, str(e)

    def disconnect_device(self, device_id: str) -> Tuple[bool, str]:
        """断开指定设备"""
        try:
            r = subprocess.run(
                ["adb", "disconnect", device_id],
                capture_output=True, text=True, timeout=10
            )
            msg = r.stdout.strip() or r.stderr.strip()
            self.refresh()
            return r.returncode == 0, msg
        except Exception as e:
            return False, str(e)

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
