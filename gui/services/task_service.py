# -*- coding: utf-8 -*-
"""
任务服务 - 管理任务生命周期、子进程执行与状态机。

架构：GUI 主进程 + 任务子进程
- 每次任务创建独立子进程运行 main.py
- GUI 捕获 stdout/stderr 并通过信号推送到日志区
- 任务状态机：idle -> starting -> running -> paused/stopping -> completed/failed/cancelled

修复记录：
- 补充子进程 stop/wait/kill 完整三阶段回收
- _poll_process 双路径防重入保护
- reader 线程完成后同步等待再清理引用
- 窗口关闭时提供 shutdown() 阻塞等待接口
"""

import os
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, List, Optional

try:
    import psutil as _psutil
except ImportError:  # psutil 未安装时优雅降级（进程挂起不可用）
    _psutil = None

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from gui.utils.runtime import app_root


class TaskState(Enum):
    """任务状态机"""
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskRecord:
    """单次任务的元数据记录"""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    task_text: str = ""
    start_time: float = 0.0
    end_time: float = 0.0
    state: TaskState = TaskState.IDLE
    device_id: str = ""
    model: str = ""
    base_url: str = ""
    max_steps: str = "100"
    exit_code: Optional[int] = None
    error_summary: str = ""
    log_file: str = ""
    events: List[dict] = field(default_factory=list)

    @property
    def duration(self) -> float:
        if self.end_time and self.start_time:
            return self.end_time - self.start_time
        elif self.start_time:
            return time.time() - self.start_time
        return 0.0

    @property
    def duration_str(self) -> str:
        secs = int(self.duration)
        if secs < 60:
            return f"{secs}s"
        return f"{secs // 60}m{secs % 60}s"


class _LogReaderThread(QThread):
    """
    在独立线程中读取子进程 stdout/stderr，
    通过信号将日志行推送给主线程，避免阻塞 UI。
    """
    line_ready = Signal(str)
    finished_reading = Signal()

    def __init__(self, process: subprocess.Popen, log_file: Optional[Path] = None):
        super().__init__()
        self._process = process
        self._log_file = log_file

    def run(self):
        log_fp = None
        try:
            if self._log_file:
                try:
                    log_fp = open(self._log_file, "w", encoding="utf-8", buffering=1)
                except Exception:
                    log_fp = None

            for raw_line in iter(self._process.stdout.readline, b""):
                try:
                    line = raw_line.decode("utf-8", errors="replace")
                except Exception:
                    line = repr(raw_line) + "\n"
                self.line_ready.emit(line)
                if log_fp:
                    try:
                        log_fp.write(line)
                    except Exception:
                        pass
        except Exception:
            pass
        finally:
            if log_fp:
                try:
                    log_fp.close()
                except Exception:
                    pass
            self.finished_reading.emit()


class TaskService(QObject):
    """
    任务服务。

    信号：
    - state_changed(TaskState)
    - log_line(str)            -- 实时日志行
    - event_added(dict)        -- 关键事件
    - task_started(TaskRecord)
    - task_finished(TaskRecord)
    - takeover_requested(str)  -- 接管请求
    - stuck_detected()         -- 疑似卡住
    """

    state_changed = Signal(object)      # TaskState
    log_line = Signal(str)
    event_added = Signal(dict)
    task_started = Signal(object)       # TaskRecord
    task_finished = Signal(object)      # TaskRecord
    takeover_requested = Signal(str)    # reason
    stuck_detected = Signal()

    # 无输出超时判定（秒）
    STUCK_TIMEOUT_S = 120
    # 终止后等待进程退出的超时（毫秒）
    TERMINATE_WAIT_MS = 3000

    def __init__(self, config_service=None, history_service=None, i18n_service=None, parent=None):
        super().__init__(parent)
        self._config = config_service
        self._history = history_service
        self._i18n = i18n_service  # I18nManager（可后期通过 set_i18n() 注入）
        self._state = TaskState.IDLE
        self._process: Optional[subprocess.Popen] = None
        self._current_record: Optional[TaskRecord] = None
        self._reader: Optional[_LogReaderThread] = None
        self._finishing = False   # 防止 _finish_task 重入

        # 卡住检测定时器
        self._stuck_timer = QTimer(self)
        self._stuck_timer.setSingleShot(True)
        self._stuck_timer.timeout.connect(self._on_stuck_timeout)
        self._last_output_time: float = 0.0

        # 进程结束轮询（200ms）
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_process)

    # ---------- 状态 ----------

    @property
    def state(self) -> TaskState:
        return self._state

    @property
    def current_record(self) -> Optional[TaskRecord]:
        return self._current_record

    def _set_state(self, state: TaskState):
        self._state = state
        self.state_changed.emit(state)

    # ---------- 启动任务 ----------

    def start_task(self, task_text: str, device_id_override: str = "") -> bool:
        """
        启动任务子进程。
        返回 True 表示已成功启动子进程，False 表示失败。
        """
        idle_states = {TaskState.IDLE, TaskState.COMPLETED,
                       TaskState.FAILED, TaskState.CANCELLED}
        if self._state not in idle_states:
            return False

        if not self._config:
            return False

        effective_device_id = (device_id_override or self._config.get("OPEN_AUTOGLM_DEVICE_ID") or "").strip()
        args = self._config.build_command_args(task_text, device_id_override=effective_device_id)
        env = self._build_env()

        # 构建日志文件路径
        log_dir = Path("gui_history") / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        task_id = str(uuid.uuid4())[:8]
        ts = time.strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"{ts}_{task_id}.log"

        record = TaskRecord(
            task_id=task_id,
            task_text=task_text,
            start_time=time.time(),
            state=TaskState.STARTING,
            device_id=effective_device_id,
            model=self._config.get("OPEN_AUTOGLM_MODEL"),
            base_url=self._config.get("OPEN_AUTOGLM_BASE_URL"),
            max_steps=self._config.get("OPEN_AUTOGLM_MAX_STEPS"),
            log_file=str(log_file),
        )
        self._current_record = record
        self._finishing = False
        self._set_state(TaskState.STARTING)
        self._add_event("task_start", f"任务启动: {task_text}",
                        message_key="event.task_start",
                        message_params={"task_text": task_text})

        try:
            self._process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                cwd=str(app_root()),
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
        except Exception as e:
            self._add_event("start_error", f"子进程启动失败: {e}",
                            message_key="event.process_start_error",
                            message_params={"error": str(e)})
            record.state = TaskState.FAILED
            record.error_summary = str(e)
            record.end_time = time.time()
            self._set_state(TaskState.FAILED)
            self.task_finished.emit(record)
            self._save_history()
            return False

        self._add_event("process_started", f"子进程已启动，PID={self._process.pid}",
                        message_key="event.process_started",
                        message_params={"pid": self._process.pid})
        self._set_state(TaskState.RUNNING)
        record.state = TaskState.RUNNING
        self.task_started.emit(record)

        # 启动日志读取线程
        self._reader = _LogReaderThread(self._process, log_file)
        self._reader.line_ready.connect(self._on_log_line)
        self._reader.finished_reading.connect(self._on_reader_finished)
        self._reader.start()

        # 启动卡住检测
        self._last_output_time = time.time()
        self._stuck_timer.start(self.STUCK_TIMEOUT_S * 1000)

        # 启动进程结束轮询
        self._poll_timer.start(200)

        return True

    def _build_env(self) -> dict:
        """构建子进程环境变量（继承当前进程环境）"""
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        return env

    # ---------- 停止/暂停/恢复 ----------

    def stop_task(self):
        """用户主动停止任务（优雅终止 -> 超时强杀）"""
        if self._state not in (TaskState.RUNNING, TaskState.PAUSED, TaskState.STARTING):
            return
        self._set_state(TaskState.STOPPING)
        self._add_event("user_stop", "用户终止任务",
                        message_key="event.user_stop", message_params={})
        self._terminate_process()

    def pause_task(self, reason: str = "用户暂停"):
        """暂停任务：挂起子进程（自动化真正停止）并标记 PAUSED 态。

        先尝试系统级挂起整个进程树，无论是否成功都标记 GUI 为暂停态。
        挂起失败时（psutil 不可用或权限不足）向日志输出警告。
        """
        if self._state != TaskState.RUNNING:
            return
        # 停止卡住检测
        self._stuck_timer.stop()
        # 先做系统调用再改状态（避免假 PAUSED）
        suspended = self._suspend_process()
        if not suspended and self._process is not None and _psutil is not None:
            self.log_line.emit("[WARN] 进程树挂起失败，人工接管可能无法完全停止自动化")
        self._set_state(TaskState.PAUSED)
        self._add_event("user_pause", f"任务暂停: {reason}",
                        message_key="event.user_pause", message_params={})

    def resume_task(self):
        """恢复任务：检查进程存活 -> 恢复进程树 -> 切回 RUNNING 态。"""
        if self._state != TaskState.PAUSED:
            return
        # 若进程在暂停期间已退出，直接走收尾流程而非强切 RUNNING
        if self._process is not None and self._process.poll() is not None:
            self._poll_process(force=True)
            return
        # 先恢复被挂起的进程树，再改状态
        self._resume_process()
        self._set_state(TaskState.RUNNING)
        self._add_event("user_resume", "任务恢复执行",
                        message_key="event.user_resume", message_params={})
        # 重启卡住检测
        self._last_output_time = time.time()
        self._stuck_timer.start(self.STUCK_TIMEOUT_S * 1000)

    def request_takeover(self, reason: str = "人工接管"):
        """触发人工接管：暂停任务并发送接管信号"""
        if self._state == TaskState.RUNNING:
            self.pause_task(reason)
            self._add_event("takeover_request", f"接管请求: {reason}",
                            message_key="event.takeover_request",
                            message_params={"reason": reason})
            self.takeover_requested.emit(reason)

    # ---------- 内部事件处理 ----------

    def _on_log_line(self, line: str):
        """收到日志行"""
        self._last_output_time = time.time()
        # 重置卡住检测（仅在 running 态）
        if self._state == TaskState.RUNNING:
            self._stuck_timer.start(self.STUCK_TIMEOUT_S * 1000)

        self.log_line.emit(line)
        self._infer_events_from_log(line)

    def _translate_text(self, key: str, **params) -> str:
        """Translate an event/helper key using injected i18n or CN fallback."""
        i18n = getattr(self, "_i18n", None)
        if i18n is not None:
            try:
                return i18n.t(key, **params)
            except Exception:
                pass
        try:
            from gui.i18n.locales.cn import CN
            template = CN.get(key, f"[[{key}]]")
            return template.format(**params) if params else template
        except Exception:
            return f"[[{key}]]"

    def _infer_events_from_log(self, line: str):
        """从日志内容推断高层事件（基于关键字匹配）。"""
        stripped = line.strip()
        lower = stripped.lower()
        triggers = (
            {"keywords": ("设备检查", "checking system"), "event_type": "device_check", "message_key": "event.device_check"},
            {"keywords": ("device connected", "设备已连接"), "event_type": "device_connected", "message_key": "event.device_connected"},
            {"keywords": ("api",), "event_type": "api_check", "message_key": "event.api_check"},
            {"keywords": ("agent start",), "event_type": "agent_start", "message_key": "event.agent_start"},
            {"keywords": ("step ",), "ignore": True},
            {"keywords": ("task completed", "任务完成"), "ignore": True},
            {"keywords": ("error", "错误", "traceback"), "event_type": "error", "raw": True},
            {"keywords": ("takeover", "接管"), "event_type": "takeover", "reason_key": "event.takeover_detected"},
        )
        for trigger in triggers:
            if not any(keyword in lower for keyword in trigger["keywords"]):
                continue
            if trigger.get("ignore"):
                return
            if trigger.get("raw"):
                if self._current_record:
                    self._current_record.error_summary = stripped[:200]
                self._add_event("error", stripped[:200])
                return
            if trigger["event_type"] == "takeover":
                self.request_takeover(self._translate_text(trigger["reason_key"]))
                return
            message_key = trigger["message_key"]
            self._add_event(
                trigger["event_type"],
                self._translate_text(message_key),
                message_key=message_key,
                message_params={},
            )
            return

    def _on_reader_finished(self):
        """日志读取线程结束时触发进程收尾"""
        # 等待 reader 线程完全退出再清理引用
        if self._reader:
            self._reader.wait(2000)
        self._poll_process(force=True)

    def _poll_process(self, force: bool = False):
        """轮询子进程是否结束（防重入）"""
        if self._process is None:
            self._poll_timer.stop()
            return

        ret = self._process.poll()
        if ret is None and not force:
            return

        # 进程已退出，防止重入
        if self._finishing:
            return
        self._finish_task(ret)

    def _finish_task(self, ret: Optional[int]):
        """统一收尾：停止定时器、清理引用、更新记录、发出信号。防重入。"""
        if self._finishing:
            return
        self._finishing = True

        self._poll_timer.stop()
        self._stuck_timer.stop()

        # 确保进程已完全退出，获取真实退出码
        if self._process is not None:
            if ret is None:
                try:
                    self._process.wait(timeout=2)
                    ret = self._process.returncode
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    ret = self._process.wait()
            self._process = None

        # 清理 reader 引用
        self._reader = None

        exit_code = ret if ret is not None else -1
        record = self._current_record
        if record:
            record.end_time = time.time()
            record.exit_code = exit_code

            if self._state == TaskState.STOPPING:
                record.state = TaskState.CANCELLED
                self._set_state(TaskState.CANCELLED)
                self._add_event("cancelled", "任务已取消",
                                message_key="event.cancelled", message_params={})
            elif exit_code == 0:
                record.state = TaskState.COMPLETED
                self._set_state(TaskState.COMPLETED)
                self._add_event("task_complete", f"任务完成，耗时 {record.duration_str}",
                                message_key="event.task_complete",
                                message_params={"duration": record.duration_str})
            else:
                record.state = TaskState.FAILED
                self._set_state(TaskState.FAILED)
                self._add_event("task_failed", f"任务失败，退出码 {exit_code}",
                                message_key="event.task_failed",
                                message_params={"exit_code": exit_code})

            self.task_finished.emit(record)
            self._save_history()

    def _terminate_process(self):
        """
        三阶段终止：
        1. SIGTERM / terminate()
        2. 等待 TERMINATE_WAIT_MS
        3. 超时后 SIGKILL / kill()
        """
        if self._process is None:
            return

        # 若进程处于挂起状态，先恢复再发送终止信号
        # （挂起的进程在部分系统上无法接收 SIGTERM）
        self._resume_process()

        # 阶段 1：优雅终止
        try:
            if sys.platform == "win32":
                self._process.terminate()
            else:
                try:
                    os.killpg(os.getpgid(self._process.pid), signal.SIGTERM)
                except ProcessLookupError:
                    self._process.terminate()
        except Exception:
            pass

        # 阶段 2：等待（非阻塞，通过 QTimer 延迟强杀）
        QTimer.singleShot(self.TERMINATE_WAIT_MS, self._force_kill_process)

    def _suspend_process(self) -> bool:
        """递归挂起整个进程树（父进程 + 所有后代）。

        Windows: SuspendThread；Linux/macOS: SIGSTOP。
        先挂起叶子节点再挂起父节点，避免父挂起后无法枚举子进程。

        Returns:
            True  - 至少父进程挂起成功
            False - psutil 不可用或权限不足等原因失败
        """
        if self._process is None or _psutil is None:
            return False
        try:
            parent = _psutil.Process(self._process.pid)
        except _psutil.NoSuchProcess:
            return False
        # 先递归挂起所有子进程（避免父挂起后子进程继续独立运行）
        try:
            children = parent.children(recursive=True)
        except Exception:
            children = []
        for child in reversed(children):  # 叶子节点优先
            try:
                child.suspend()
            except Exception:
                pass
        # 最后挂起父进程
        try:
            parent.suspend()
            return True
        except Exception as exc:
            self.log_line.emit(f"[WARN] _suspend_process 失败: {exc}")
            return False

    def _resume_process(self) -> bool:
        """递归恢复整个进程树（父进程 + 所有后代）。

        先恢复父进程，再恢复子进程；对未挂起进程调用是幂等的。

        Returns:
            True  - 至少父进程恢复成功（或进程已不存在）
            False - psutil 不可用或权限不足等原因失败
        """
        if self._process is None or _psutil is None:
            return False
        try:
            parent = _psutil.Process(self._process.pid)
        except _psutil.NoSuchProcess:
            return True  # 进程已退出，视为无需恢复
        # 先恢复父进程
        ok = True
        try:
            parent.resume()
        except Exception as exc:
            self.log_line.emit(f"[WARN] _resume_process 失败: {exc}")
            ok = False
        # 再恢复子进程
        try:
            children = parent.children(recursive=True)
        except Exception:
            children = []
        for child in children:
            try:
                child.resume()
            except Exception:
                pass
        return ok

    def _force_kill_process(self):
        """若进程仍未退出，强制 SIGKILL"""
        if self._process is None:
            return
        if self._process.poll() is not None:
            return  # 已自然退出
        try:
            self._process.kill()
        except Exception:
            pass

    def _on_stuck_timeout(self):
        """超时无输出，认为卡住"""
        self._add_event(
            "stuck_detected",
            f"{self.STUCK_TIMEOUT_S}s 无输出，疑似卡住",
            message_key="event.stuck_detected",
            message_params={"timeout": self.STUCK_TIMEOUT_S},
        )
        self.stuck_detected.emit()

    def _add_event(
        self,
        event_type: str,
        message: str,
        *,
        message_key: str = "",
        message_params: dict | None = None,
    ):
        """
        记录关键事件。

        新字段（i18n）：
          message_key     - i18n 词典 key
          message_params  - 翻译参数
          rendered_message - 按当前 GUI 语言渲染的文本
          lang            - 生成时的 GUI 语言
        旧字段 message 继续保留，供历史兼容回退。
        """
        # 渲染翻译后的消息
        rendered = message  # 默认回退到原始文本
        lang = "cn"
        if message_key and self._i18n:
            lang = self._i18n.get_language()
            try:
                rendered = self._i18n.t(message_key, **(message_params or {}))
            except Exception:
                rendered = message
        elif message_key:
            # i18n 未注入时，尝试直接加载中文词典
            try:
                from gui.i18n.locales.cn import CN
                tmpl = CN.get(message_key, "")
                if tmpl:
                    rendered = tmpl.format(**(message_params or {})) if message_params else tmpl
            except Exception:
                pass

        evt = {
            "time": time.time(),
            "time_str": time.strftime("%H:%M:%S"),
            "type": event_type,
            "message": message,           # 旧字段，保留兼容
            # --- 新 i18n 字段 ---
            "message_key": message_key,
            "message_params": message_params or {},
            "rendered_message": rendered,
            "lang": lang,
        }
        if self._current_record:
            self._current_record.events.append(evt)
        self.event_added.emit(evt)

    def set_i18n(self, i18n_service) -> None:
        """动态注入 I18nManager（MainWindow 初始化完毕后调用）。"""
        self._i18n = i18n_service

    def _save_history(self):
        """保存任务历史"""
        if self._history and self._current_record:
            self._history.save_record(self._current_record)

    # ---------- 应用退出时的阻塞清理 ----------

    def shutdown(self, timeout_ms: int = 5000):
        """
        应用退出时调用。阻塞等待子进程与 reader 线程完全结束。
        """
        # 先发停止信号
        if self._state in (TaskState.RUNNING, TaskState.PAUSED, TaskState.STARTING):
            self.stop_task()

        # 强杀进程（不等优雅超时）
        if self._process:
            try:
                self._process.kill()
            except Exception:
                pass
            try:
                self._process.wait(timeout=3)
            except Exception:
                pass
            self._process = None

        # 等待 reader 线程
        if self._reader and self._reader.isRunning():
            self._reader.wait(timeout_ms)
        self._reader = None

        self._poll_timer.stop()
        self._stuck_timer.stop()
