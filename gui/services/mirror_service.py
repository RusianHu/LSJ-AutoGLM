# -*- coding: utf-8 -*-
"""
镜像服务 - 管理 scrcpy 实时镜像进程的生命周期。

策略：
- 首选：内嵌 scrcpy 进程，通过窗口句柄嵌入 Qt 容器（Windows）
- 降级：外部独立 scrcpy 窗口（可视化但不嵌入）
- 兜底：ADB 截图轮询预览模式

修复记录：
- _ScreenshotPoller 改为在线程内仅传输 bytes，由主线程构造 QPixmap，避免线程内创建 GUI 资源
- MirrorService.stop() 增加 terminate -> wait -> kill 三阶段回收
- _try_embed_window 改用独立线程异步轮询，不阻塞 UI 事件循环
- 统一增加 shutdown() 接口供应用退出调用
"""

import shutil
import subprocess
import sys
import time
from enum import Enum
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QThread, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap


class MirrorMode(Enum):
    """镜像模式"""
    NONE = "none"
    SCRCPY_EMBEDDED = "scrcpy_embedded"
    SCRCPY_EXTERNAL = "scrcpy_external"
    ADB_SCREENSHOT = "adb_screenshot"


class MirrorState(Enum):
    """镜像状态"""
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"
    STOPPED = "stopped"


class _ScreenshotPoller(QThread):
    """
    ADB 截图降级模式的轮询线程。
    修复：仅在线程中传输 bytes，由主线程（槽函数）构造 QPixmap，
    保证 GUI 资源始终在主线程创建。
    """
    # 传输原始 PNG bytes，主线程负责解码为 QPixmap
    frame_bytes_ready = Signal(bytes)

    def __init__(self, device_id: str, interval_ms: int = 1500):
        super().__init__()
        self._device_id = device_id
        self._interval = interval_ms / 1000.0
        self._running = False

    def run(self):
        self._running = True
        while self._running:
            try:
                result = subprocess.run(
                    ["adb", "-s", self._device_id, "exec-out", "screencap", "-p"],
                    capture_output=True,
                    timeout=10,
                )
                if result.returncode == 0 and result.stdout:
                    self.frame_bytes_ready.emit(result.stdout)
            except Exception:
                pass
            # 分段 sleep，便于快速响应 stop()
            deadline = time.time() + self._interval
            while self._running and time.time() < deadline:
                time.sleep(0.1)

    def stop(self):
        self._running = False


class _EmbedWindowThread(QThread):
    """
    异步等待 scrcpy 窗口出现并嵌入（仅 Windows）。
    修复：从主线程移出，避免 while + sleep 阻塞事件循环。
    """
    embed_done = Signal(int)   # HWND
    embed_failed = Signal(str)

    WINDOW_WAIT_TIMEOUT = 8

    def __init__(self, parent_wid: int, device_id: str):
        super().__init__()
        self._parent_wid = parent_wid
        self._device_id = device_id

    def run(self):
        if sys.platform != "win32":
            self.embed_failed.emit("非 Windows 平台，跳过嵌入")
            return
        try:
            import ctypes
            import ctypes.wintypes

            user32 = ctypes.windll.user32
            hwnd = None
            deadline = time.time() + self.WINDOW_WAIT_TIMEOUT

            WNDENUMPROC = ctypes.WINFUNCTYPE(
                ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM
            )

            def enum_callback(h, _):
                nonlocal hwnd
                buf = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(h, buf, 256)
                title = buf.value.lower()
                if "autoglm mirror" in title or "scrcpy" in title:
                    hwnd = h
                    return False
                return True

            cb = WNDENUMPROC(enum_callback)

            while hwnd is None and time.time() < deadline:
                user32.EnumWindows(cb, 0)
                if hwnd is None:
                    time.sleep(0.5)

            if not hwnd:
                self.embed_failed.emit("未找到 scrcpy 窗口，将以独立窗口显示")
                return

            # 移除边框并设置为子窗口
            GWL_STYLE = -16
            WS_CAPTION = 0x00C00000
            style = user32.GetWindowLongW(hwnd, GWL_STYLE)
            style = style & ~WS_CAPTION
            user32.SetWindowLongW(hwnd, GWL_STYLE, style)
            user32.SetParent(hwnd, self._parent_wid)
            user32.SetWindowPos(
                hwnd, 0, 0, 0, 0, 0,
                0x0001 | 0x0002 | 0x0040  # SWP_NOSIZE | SWP_NOMOVE | SWP_SHOWWINDOW
            )
            self.embed_done.emit(hwnd)

        except Exception as e:
            self.embed_failed.emit(f"窗口嵌入失败: {e}")


class MirrorService(QObject):
    """
    镜像服务。

    信号：
    - state_changed(MirrorState)
    - mode_changed(MirrorMode)
    - frame_ready(QPixmap)         -- ADB 截图模式下的帧（已在主线程构造）
    - error_occurred(str)
    - window_created(int)          -- scrcpy 窗口句柄（Windows）
    """

    state_changed = Signal(object)    # MirrorState
    mode_changed = Signal(object)     # MirrorMode
    frame_ready = Signal(object)      # QPixmap
    error_occurred = Signal(str)
    window_created = Signal(int)      # HWND

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = MirrorState.IDLE
        self._mode = MirrorMode.NONE
        self._device_id: Optional[str] = None
        self._scrcpy_proc: Optional[subprocess.Popen] = None
        self._screenshot_poller: Optional[_ScreenshotPoller] = None
        self._embed_thread: Optional[_EmbedWindowThread] = None
        self._window_hwnd: Optional[int] = None

        # 进程存活监控定时器
        self._monitor_timer = QTimer(self)
        self._monitor_timer.timeout.connect(self._monitor_process)

    # ---------- 状态属性 ----------

    @property
    def state(self) -> MirrorState:
        return self._state

    @property
    def mode(self) -> MirrorMode:
        return self._mode

    @property
    def is_running(self) -> bool:
        return self._state == MirrorState.RUNNING

    def _set_state(self, state: MirrorState):
        self._state = state
        self.state_changed.emit(state)

    # ---------- 检查 scrcpy ----------

    @staticmethod
    def find_scrcpy() -> Optional[str]:
        """查找 scrcpy 可执行文件路径"""
        p = shutil.which("scrcpy")
        if p:
            return p
        candidates = [
            Path("scrcpy") / "scrcpy.exe",
            Path("tools") / "scrcpy" / "scrcpy.exe",
            Path("C:/scrcpy/scrcpy.exe"),
            Path("C:/Program Files/scrcpy/scrcpy.exe"),
        ]
        for c in candidates:
            if c.exists():
                return str(c)
        return None

    def check_available(self) -> tuple:
        """检查 scrcpy 是否可用"""
        path = self.find_scrcpy()
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
        return False, "scrcpy 未找到，将使用 ADB 截图降级模式"

    # ---------- 启动镜像 ----------

    def start(self, device_id: str, embed_wid: Optional[int] = None):
        """
        启动镜像。
        embed_wid: Qt 容器窗口 WId（用于嵌入），None 表示外部独立窗口。
        """
        if self._state in (MirrorState.RUNNING, MirrorState.STARTING):
            return

        self._device_id = device_id
        self._set_state(MirrorState.STARTING)

        scrcpy_path = self.find_scrcpy()
        if scrcpy_path:
            self._start_scrcpy(scrcpy_path, device_id, embed_wid)
        else:
            self._start_adb_screenshot(device_id)

    def _start_scrcpy(self, scrcpy_path: str, device_id: str, embed_wid: Optional[int]):
        """启动 scrcpy 进程"""
        args = [
            scrcpy_path,
            "--serial", device_id,
            "--window-title", f"AutoGLM Mirror - {device_id}",
            "--stay-awake",
            "--turn-screen-off",
        ]
        if embed_wid and sys.platform == "win32":
            args += ["--window-borderless"]

        try:
            self._scrcpy_proc = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
        except Exception as e:
            self.error_occurred.emit(f"scrcpy 启动失败: {e}")
            self._start_adb_screenshot(device_id)
            return

        embedded_requested = bool(embed_wid and sys.platform == "win32")
        mode = MirrorMode.SCRCPY_EMBEDDED if embedded_requested else MirrorMode.SCRCPY_EXTERNAL
        self._mode = mode
        self.mode_changed.emit(mode)
        self._set_state(MirrorState.RUNNING)

        # 若是嵌入模式，在独立线程中异步等待窗口句柄（不阻塞 UI）
        if embedded_requested:
            self._embed_thread = _EmbedWindowThread(embed_wid, device_id)
            self._embed_thread.embed_done.connect(self._on_embed_done)
            self._embed_thread.embed_failed.connect(self._on_embed_failed)
            self._embed_thread.start()

        # 启动进程监控
        self._monitor_timer.start(2000)

    def _on_embed_done(self, hwnd: int):
        self._window_hwnd = hwnd
        self.window_created.emit(hwnd)
        if self._embed_thread:
            self._embed_thread.deleteLater()
            self._embed_thread = None

    def _on_embed_failed(self, msg: str):
        self.error_occurred.emit(msg)
        if self._mode == MirrorMode.SCRCPY_EMBEDDED:
            self._mode = MirrorMode.SCRCPY_EXTERNAL
            self.mode_changed.emit(MirrorMode.SCRCPY_EXTERNAL)
        if self._embed_thread:
            self._embed_thread.deleteLater()
            self._embed_thread = None

    def _start_adb_screenshot(self, device_id: str):
        """降级：启动 ADB 截图轮询"""
        self._mode = MirrorMode.ADB_SCREENSHOT
        self.mode_changed.emit(MirrorMode.ADB_SCREENSHOT)

        self._screenshot_poller = _ScreenshotPoller(device_id, interval_ms=1500)
        # 修复：在主线程槽函数中解码 bytes -> QPixmap，保证 GUI 资源在主线程创建
        self._screenshot_poller.frame_bytes_ready.connect(self._on_frame_bytes)
        self._screenshot_poller.start()
        self._set_state(MirrorState.RUNNING)

    def _on_frame_bytes(self, data: bytes):
        """在主线程中将 bytes 解码为 QPixmap 后发出 frame_ready"""
        img = QImage()
        img.loadFromData(data, "PNG")
        if not img.isNull():
            pix = QPixmap.fromImage(img)
            self.frame_ready.emit(pix)

    # ---------- 停止镜像 ----------

    def stop(self):
        """停止镜像（三阶段清理）"""
        self._monitor_timer.stop()

        # 停止截图线程
        if self._screenshot_poller:
            self._screenshot_poller.stop()
            self._screenshot_poller.wait(3000)
            self._screenshot_poller.deleteLater()
            self._screenshot_poller = None

        # 停止嵌入等待线程
        if self._embed_thread:
            if self._embed_thread.isRunning():
                self._embed_thread.wait(2000)
            self._embed_thread.deleteLater()
            self._embed_thread = None

        # 三阶段终止 scrcpy
        self._kill_scrcpy()

        self._window_hwnd = None
        self._mode = MirrorMode.NONE
        self.mode_changed.emit(MirrorMode.NONE)
        self._set_state(MirrorState.STOPPED)

    def _kill_scrcpy(self):
        """三阶段回收 scrcpy 进程：terminate -> wait(2s) -> kill"""
        if self._scrcpy_proc is None:
            return
        proc = self._scrcpy_proc
        self._scrcpy_proc = None
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
                proc.wait(timeout=1)
            except Exception:
                pass
        except Exception:
            pass

    def restart(self):
        """重启镜像"""
        device_id = self._device_id
        if not device_id:
            return
        self.stop()
        QTimer.singleShot(1000, lambda: self.start(device_id))

    # ---------- 监控 ----------

    def _monitor_process(self):
        """监控 scrcpy 进程存活"""
        if self._scrcpy_proc:
            ret = self._scrcpy_proc.poll()
            if ret is not None:
                self._scrcpy_proc = None
                self._monitor_timer.stop()
                self.error_occurred.emit(f"scrcpy 进程已退出（code={ret}）")
                self._set_state(MirrorState.ERROR)
                # 降级到 ADB 截图模式
                if self._device_id:
                    self.error_occurred.emit("切换到 ADB 截图降级模式...")
                    QTimer.singleShot(1000, lambda: self._start_adb_screenshot(self._device_id))

    # ---------- 截图（错误取证） ----------

    def capture_screenshot(self, output_path: Optional[str] = None) -> Optional[str]:
        """通过 ADB 截图并保存，返回文件路径"""
        if not self._device_id:
            return None
        if output_path is None:
            ts = time.strftime("%Y%m%d_%H%M%S")
            output_path = str(Path("gui_history") / "screenshots" / f"screenshot_{ts}.png")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        try:
            result = subprocess.run(
                ["adb", "-s", self._device_id, "exec-out", "screencap", "-p"],
                capture_output=True,
                timeout=15,
            )
            if result.returncode == 0 and result.stdout:
                Path(output_path).write_bytes(result.stdout)
                return output_path
        except Exception:
            pass
        return None

    def resize_scrcpy_window(self, x: int, y: int, w: int, h: int):
        """调整 scrcpy 嵌入窗口大小（Windows）"""
        if self._window_hwnd and sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.user32.SetWindowPos(
                    self._window_hwnd, 0, x, y, w, h, 0x0040
                )
            except Exception:
                pass

    # ---------- 应用退出时的阻塞清理 ----------

    def shutdown(self):
        """应用退出时调用，确保所有资源彻底清理"""
        self.stop()
