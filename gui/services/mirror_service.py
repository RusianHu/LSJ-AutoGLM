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

import os
import re
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

            # 切为真正的子窗口并刷新 frame，避免顶层窗口样式残留
            GWL_STYLE = -16
            WS_CAPTION = 0x00C00000
            WS_THICKFRAME = 0x00040000
            WS_MINIMIZEBOX = 0x00020000
            WS_MAXIMIZEBOX = 0x00010000
            WS_SYSMENU = 0x00080000
            WS_POPUP = 0x80000000
            WS_CHILD = 0x40000000
            SWP_NOSIZE = 0x0001
            SWP_NOMOVE = 0x0002
            SWP_NOZORDER = 0x0004
            SWP_FRAMECHANGED = 0x0020
            SWP_SHOWWINDOW = 0x0040

            raw_style = user32.GetWindowLongW(hwnd, GWL_STYLE)
            style_u32 = ctypes.c_uint32(raw_style).value
            clear_mask = (
                WS_CAPTION
                | WS_THICKFRAME
                | WS_MINIMIZEBOX
                | WS_MAXIMIZEBOX
                | WS_SYSMENU
                | WS_POPUP
            )
            new_style_u32 = ((style_u32 & ~clear_mask) | WS_CHILD) & 0xFFFFFFFF
            new_style = ctypes.c_int32(new_style_u32).value
            user32.SetWindowLongW(hwnd, GWL_STYLE, new_style)
            user32.SetParent(hwnd, self._parent_wid)
            user32.SetWindowPos(
                hwnd, 0, 0, 0, 0, 0,
                SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_FRAMECHANGED | SWP_SHOWWINDOW
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
        self._device_screen_size: Optional[tuple[int, int]] = None
        self._last_resize_request: Optional[tuple[int, int, int, int]] = None
        self._mirror_debug_enabled = self._is_truthy(
            os.environ.get("OPEN_AUTOGLM_GUI_MIRROR_DEBUG", "")
        )

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

    @property
    def device_screen_size(self) -> Optional[tuple[int, int]]:
        return self._device_screen_size

    @staticmethod
    def _is_truthy(value: str) -> bool:
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def _emit_debug(self, message: str):
        if self._mirror_debug_enabled:
            self.error_occurred.emit(f"[调试] {message}")

    @staticmethod
    def _parse_screen_size_output(output: str) -> Optional[tuple[int, int]]:
        for line in output.splitlines():
            match = re.search(r"(\d+)\s*x\s*(\d+)", line)
            if not match:
                continue
            width = int(match.group(1))
            height = int(match.group(2))
            if width > 0 and height > 0:
                return width, height
        return None

    def _probe_device_screen_size(self, device_id: str) -> Optional[tuple[int, int]]:
        try:
            result = subprocess.run(
                ["adb", "-s", device_id, "shell", "wm", "size"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout:
                size = self._parse_screen_size_output(result.stdout)
                if size:
                    self._emit_debug(f"探测设备屏幕尺寸: {size[0]}x{size[1]}")
                    return size
                self._emit_debug(f"wm size 输出无法解析: {result.stdout.strip()}")
            else:
                detail = (result.stderr or result.stdout or "").strip()
                self._emit_debug(
                    f"wm size 执行失败: code={result.returncode}, output={detail or 'empty'}"
                )
        except Exception as e:
            self._emit_debug(f"探测设备屏幕尺寸异常: {e}")
        return None

    # ---------- 启动镜像 ----------

    def start(
        self,
        device_id: str,
        embed_wid: Optional[int] = None,
        embed_container_size: Optional[tuple[int, int]] = None,
    ):
        """
        启动镜像。
        embed_wid: Qt 容器窗口 WId（用于嵌入），None 表示外部独立窗口。
        embed_container_size: 嵌入宿主区域的逻辑尺寸，用于在 scrcpy 启动期做安全缩放。
        """
        if self._state in (MirrorState.RUNNING, MirrorState.STARTING):
            return

        self._device_id = device_id
        self._set_state(MirrorState.STARTING)

        scrcpy_path = self.find_scrcpy()
        if scrcpy_path:
            self._start_scrcpy(scrcpy_path, device_id, embed_wid, embed_container_size)
        else:
            self._start_adb_screenshot(device_id)

    def _start_scrcpy(
        self,
        scrcpy_path: str,
        device_id: str,
        embed_wid: Optional[int],
        embed_container_size: Optional[tuple[int, int]] = None,
    ):
        """启动 scrcpy 进程"""
        embedded_requested = bool(embed_wid and sys.platform == "win32")
        self._device_screen_size = self._probe_device_screen_size(device_id)
        self._last_resize_request = None

        safe_embed_fit_size = None
        if embedded_requested and embed_container_size and self._device_screen_size:
            container_w, container_h = embed_container_size
            device_w, device_h = self._device_screen_size
            if container_w > 0 and container_h > 0 and device_w > 0 and device_h > 0:
                scale = min(container_w / device_w, container_h / device_h)
                safe_embed_fit_size = (
                    max(1, int(device_w * scale)),
                    max(1, int(device_h * scale)),
                )

        args = [
            scrcpy_path,
            "--serial", device_id,
            "--window-title", f"AutoGLM Mirror - {device_id}",
            "--stay-awake",
        ]
        if embedded_requested:
            args += ["--window-borderless"]
            if safe_embed_fit_size:
                args += [
                    "--window-width", str(safe_embed_fit_size[0]),
                    "--window-height", str(safe_embed_fit_size[1]),
                    "--max-size", str(max(safe_embed_fit_size)),
                ]

        self._emit_debug(
            f"scrcpy 启动参数: embedded_requested={embedded_requested}, "
            f"args={subprocess.list2cmdline(args)}"
        )
        if safe_embed_fit_size:
            self._emit_debug(
                "scrcpy 启动期安全缩放: "
                f"container={embed_container_size[0]}x{embed_container_size[1]}, "
                f"fit={safe_embed_fit_size[0]}x{safe_embed_fit_size[1]}, "
                f"max_size={max(safe_embed_fit_size)}"
            )
        if self._device_screen_size:
            self._emit_debug(
                f"scrcpy 启动前缓存设备尺寸: "
                f"{self._device_screen_size[0]}x{self._device_screen_size[1]}"
            )

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

        mode = MirrorMode.SCRCPY_EMBEDDED if embedded_requested else MirrorMode.SCRCPY_EXTERNAL
        self._mode = mode
        self.mode_changed.emit(mode)
        self._set_state(MirrorState.RUNNING)
        self._emit_debug(f"scrcpy 进程已启动: pid={self._scrcpy_proc.pid}, mode={mode.value}")

        # 若是嵌入模式，在独立线程中异步等待窗口句柄（不阻塞 UI）
        if embedded_requested:
            self._emit_debug(f"等待 scrcpy 窗口嵌入: parent_wid={embed_wid}")
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
                import ctypes.wintypes

                request = (x, y, w, h)
                should_log = request != self._last_resize_request
                self._last_resize_request = request

                ctypes.windll.user32.SetWindowPos(
                    self._window_hwnd, 0, x, y, w, h, 0x0040
                )

                if should_log:
                    rect = ctypes.wintypes.RECT()
                    ctypes.windll.user32.GetWindowRect(self._window_hwnd, ctypes.byref(rect))
                    actual_w = rect.right - rect.left
                    actual_h = rect.bottom - rect.top
                    self._emit_debug(
                        "scrcpy 窗口重设: "
                        f"request=({x},{y},{w},{h}), "
                        f"actual=({rect.left},{rect.top},{actual_w},{actual_h})"
                    )
            except Exception as e:
                self._emit_debug(f"scrcpy 窗口重设异常: {e}")

    # ---------- 应用退出时的阻塞清理 ----------

    def shutdown(self):
        """应用退出时调用，确保所有资源彻底清理"""
        self.stop()
