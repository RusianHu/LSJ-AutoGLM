# -*- coding: utf-8 -*-
"""跨进程自动化作业状态存储。"""

from __future__ import annotations

import json
import os
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any


TERMINAL_STATES = {"completed", "failed", "cancelled"}
ACTIVE_STATES = {"starting", "running", "paused", "stopping"}


def default_state_dir() -> Path:
    override = (os.environ.get("OPEN_AUTOGLM_CLI_STATE_DIR") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (Path.cwd() / "gui_history" / "automation").resolve()


def make_job_id(kind: str) -> str:
    prefix = "".join(ch for ch in kind.lower() if ch.isalnum())[:8] or "job"
    return f"{prefix}-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"


class JobStore:
    """以原子 JSON 文件保存可由多次 CLI 调用控制的作业。"""

    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or default_state_dir()).expanduser().resolve()
        self.jobs_dir = self.root / "jobs"
        self.specs_dir = self.root / "specs"
        self.logs_dir = self.root / "logs"
        for path in (self.jobs_dir, self.specs_dir, self.logs_dir):
            path.mkdir(parents=True, exist_ok=True)

    def state_path(self, job_id: str) -> Path:
        self._validate_id(job_id)
        return self.jobs_dir / f"{job_id}.json"

    def spec_path(self, job_id: str) -> Path:
        self._validate_id(job_id)
        return self.specs_dir / f"{job_id}.json"

    def log_path(self, job_id: str) -> Path:
        self._validate_id(job_id)
        return self.logs_dir / f"{job_id}.log"

    @staticmethod
    def _validate_id(job_id: str) -> None:
        if not job_id or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in job_id):
            raise ValueError("无效的作业 ID")

    @staticmethod
    def _atomic_write(path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        for attempt in range(6):
            try:
                tmp.replace(path)
                return
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(0.03 * (attempt + 1))

    def create(self, kind: str, spec: dict[str, Any], public: dict[str, Any] | None = None) -> dict[str, Any]:
        job_id = make_job_id(kind)
        now = time.time()
        state = {
            "schema_version": 1,
            "job_id": job_id,
            "kind": kind,
            "state": "starting",
            "created_at": now,
            "updated_at": now,
            "worker_pid": None,
            "process_pid": None,
            "returncode": None,
            "log_file": str(self.log_path(job_id)),
            "stop_requested": False,
            "error": "",
            **(public or {}),
        }
        self._atomic_write(self.spec_path(job_id), spec)
        self._atomic_write(self.state_path(job_id), state)
        return state

    def read(self, job_id: str) -> dict[str, Any]:
        path = self.state_path(job_id)
        if not path.exists():
            raise KeyError(f"作业不存在：{job_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def read_spec(self, job_id: str, *, consume: bool = False) -> dict[str, Any]:
        path = self.spec_path(job_id)
        if not path.exists():
            raise KeyError(f"作业规格不存在：{job_id}")
        value = json.loads(path.read_text(encoding="utf-8"))
        if consume:
            path.unlink(missing_ok=True)
        return value

    @contextmanager
    def _job_lock(self, job_id: str, timeout: float = 5):
        lock = self.state_path(job_id).with_suffix(".lock")
        deadline = time.monotonic() + timeout
        descriptor = None
        while descriptor is None:
            try:
                descriptor = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(descriptor, f"{os.getpid()} {time.time()}".encode("ascii"))
            except FileExistsError:
                try:
                    stale = time.time() - lock.stat().st_mtime > 30
                except OSError:
                    stale = False
                if stale:
                    try:
                        lock.unlink()
                    except OSError:
                        pass
                    continue
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"等待作业状态锁超时：{job_id}")
                time.sleep(0.01)
        try:
            yield
        finally:
            os.close(descriptor)
            try:
                lock.unlink()
            except OSError:
                pass

    @contextmanager
    def history_lock(self, timeout: float = 5):
        """序列化 GUI 兼容历史索引的跨进程读改写。"""
        history_dir = self.root.parent
        history_dir.mkdir(parents=True, exist_ok=True)
        lock = history_dir / ".index.lock"
        deadline = time.monotonic() + timeout
        descriptor = None
        while descriptor is None:
            try:
                descriptor = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(descriptor, f"{os.getpid()} {time.time()}".encode("ascii"))
            except FileExistsError:
                try:
                    stale = time.time() - lock.stat().st_mtime > 30
                except OSError:
                    stale = False
                if stale:
                    try:
                        lock.unlink()
                    except OSError:
                        pass
                    continue
                if time.monotonic() >= deadline:
                    raise TimeoutError("等待历史索引锁超时")
                time.sleep(0.01)
        try:
            yield
        finally:
            os.close(descriptor)
            try:
                lock.unlink()
            except OSError:
                pass

    def update(self, job_id: str, **updates: Any) -> dict[str, Any]:
        with self._job_lock(job_id):
            state = self.read(job_id)
            state.update(updates)
            state["updated_at"] = time.time()
            self._atomic_write(self.state_path(job_id), state)
            return state

    def list(self, kind: str = "", limit: int = 50) -> list[dict[str, Any]]:
        states: list[dict[str, Any]] = []
        for path in self.jobs_dir.glob("*.json"):
            try:
                item = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if kind and item.get("kind") != kind:
                continue
            states.append(item)
        states.sort(key=lambda item: float(item.get("created_at") or 0), reverse=True)
        return states[: max(1, limit)]

    def tail(self, job_id: str, lines: int = 100) -> str:
        path = Path(self.read(job_id).get("log_file") or self.log_path(job_id))
        if not path.exists():
            return ""
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(content[-max(1, lines):])
