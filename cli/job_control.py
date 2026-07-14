# -*- coding: utf-8 -*-
"""非阻塞作业启动和跨进程控制。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import psutil

from cli.automation_state import ACTIVE_STATES, TERMINAL_STATES, JobStore


def _worker_command(store: JobStore, job_id: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "cli.job_worker",
        "--state-dir",
        str(store.root),
        "--job-id",
        job_id,
    ]


def _launch_worker(store: JobStore, state: dict[str, Any], cwd: str | Path) -> dict[str, Any]:
    flags = 0
    kwargs: dict[str, Any] = {}
    if os.name == "nt":
        flags = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
    else:
        kwargs["start_new_session"] = True
    process = subprocess.Popen(
        _worker_command(store, state["job_id"]),
        cwd=str(cwd),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        creationflags=flags,
        **kwargs,
    )
    return store.update(state["job_id"], worker_pid=process.pid)


def start_job(
    store: JobStore,
    kind: str,
    spec: dict[str, Any],
    *,
    public: dict[str, Any] | None = None,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    state = store.create(kind, spec, public)
    try:
        return _launch_worker(store, state, cwd or Path.cwd())
    except Exception as exc:
        try:
            store.spec_path(state["job_id"]).unlink(missing_ok=True)
        except OSError:
            pass
        return store.update(state["job_id"], state="failed", error=str(exc), returncode=127)


def start_task(
    store: JobStore,
    task_text: str,
    *,
    env_file: str = "",
    device_id: str = "",
    stuck_timeout: float = 120,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    task_text = (task_text or "").strip()
    if not task_text:
        raise ValueError("任务描述不能为空")
    job_id_preview = uuid.uuid4().hex
    runtime_dir = store.root.parent / "runtime" / f"cli_{int(time.time())}_{job_id_preview[:8]}"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    inbox_path = runtime_dir / "inbox.jsonl"
    inbox_path.write_text("", encoding="utf-8")
    spec = {
        "task_text": task_text,
        "device_id": device_id,
        "env_file": env_file,
        "inbox_path": str(inbox_path),
        "cwd": str(cwd or Path.cwd()),
        "stuck_timeout": max(1.0, float(stuck_timeout)),
    }
    return start_job(
        store,
        "task",
        spec,
        public={"task_text": task_text, "device_id": device_id, "inbox_path": str(inbox_path)},
        cwd=cwd,
    )


def _processes(state: dict[str, Any]) -> list[psutil.Process]:
    pid = state.get("process_pid") or state.get("worker_pid")
    if not pid:
        return []
    try:
        root = psutil.Process(int(pid))
        return [*root.children(recursive=True), root]
    except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError, TypeError):
        return []


def refresh_state(store: JobStore, job_id: str) -> dict[str, Any]:
    state = store.read(job_id)
    if state.get("state") in ACTIVE_STATES:
        worker_pid = state.get("worker_pid")
        # Windows venv 的 python.exe 可能先启动基础解释器再退出，worker 会随即
        # 用真实 PID 覆盖状态。保留短暂启动宽限，避免把正常换手误判为崩溃。
        age = time.time() - float(state.get("updated_at") or state.get("created_at") or 0)
        if worker_pid and age > 3 and not psutil.pid_exists(int(worker_pid)):
            state = store.update(job_id, state="failed", error="后台执行器已退出但未写入终态", returncode=1)
    return state


def pause_job(store: JobStore, job_id: str) -> dict[str, Any]:
    state = refresh_state(store, job_id)
    if state.get("state") != "running":
        raise RuntimeError(f"仅运行中的作业可暂停，当前状态：{state.get('state')}")
    processes = _processes(state)
    if not processes:
        raise RuntimeError("作业进程不存在")
    for process in reversed(processes):
        try:
            process.suspend()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return store.update(job_id, state="paused")


def resume_job(store: JobStore, job_id: str) -> dict[str, Any]:
    state = refresh_state(store, job_id)
    if state.get("state") != "paused":
        raise RuntimeError(f"仅暂停中的作业可恢复，当前状态：{state.get('state')}")
    processes = _processes(state)
    if not processes:
        raise RuntimeError("作业进程不存在")
    for process in processes:
        try:
            process.resume()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return store.update(job_id, state="running")


def stop_job(store: JobStore, job_id: str, timeout: float = 5) -> dict[str, Any]:
    state = refresh_state(store, job_id)
    if state.get("state") in TERMINAL_STATES:
        return state
    # 先恢复暂停进程，否则 Windows 上 terminate 可能无法及时完成。
    processes = _processes(state)
    for process in processes:
        try:
            process.resume()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    state = store.update(job_id, state="stopping", stop_requested=True)
    process_pid = state.get("process_pid")
    targets = []
    if process_pid:
        try:
            root = psutil.Process(int(process_pid))
            targets = [*root.children(recursive=True), root]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            targets = []
    for process in reversed(targets):
        try:
            process.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    _, alive = psutil.wait_procs(targets, timeout=max(0.1, timeout)) if targets else ([], [])
    for process in alive:
        try:
            process.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    # 无子进程的协作式 worker（二维码配对、ADB 镜像等）通过 stop_requested 自行退出。
    # 有子进程的 worker 会在子进程退出后写入 cancelled。
    deadline = time.monotonic() + 0.8
    while time.monotonic() < deadline:
        current = store.read(job_id)
        if current.get("state") in TERMINAL_STATES:
            return current
        time.sleep(0.05)
    return store.read(job_id)


def submit_instruction(store: JobStore, job_id: str, text: str, source: str = "cli") -> dict[str, Any]:
    state = refresh_state(store, job_id)
    if state.get("kind") != "task" or state.get("state") not in {"running", "paused"}:
        raise RuntimeError("只有运行中或暂停中的 Agent 任务可接收追加指令")
    instruction = (text or "").strip()
    if not instruction:
        raise ValueError("追加指令不能为空")
    inbox = Path(state.get("inbox_path") or "")
    if not inbox:
        raise RuntimeError("任务未配置运行时指令 inbox")
    entry = {
        "id": uuid.uuid4().hex,
        "timestamp": time.time(),
        "source": source,
        "text": instruction,
    }
    with open(inbox, "a", encoding="utf-8") as stream:
        stream.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return entry


def wait_job(store: JobStore, job_id: str, timeout: float = 300, interval: float = 0.2) -> dict[str, Any]:
    deadline = time.monotonic() + max(0, timeout)
    while True:
        state = refresh_state(store, job_id)
        if state.get("state") in TERMINAL_STATES:
            return state
        if time.monotonic() >= deadline:
            raise TimeoutError(f"等待作业超时：{job_id}")
        time.sleep(max(0.05, min(interval, 2)))
