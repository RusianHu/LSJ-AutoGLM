# -*- coding: utf-8 -*-
"""后台作业执行器；由自动化 CLI 分离启动，不供用户直接调用。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import asdict
from pathlib import Path

from cli.automation_state import JobStore


def _parse_token_payload(payload: str) -> dict[str, int | float]:
    import re

    data: dict[str, int | float] = {}
    for part in (payload or "").split():
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        match = re.match(r"^\s*([+-]?\d+(?:\.\d+)?)", value)
        if match:
            raw = match.group(1)
            data[key.strip()] = float(raw) if "." in raw else int(raw)
    return data


def _consume_task_output(stream, log, store: JobStore, job_id: str, context: dict) -> None:
    from cli.job_control import pause_job
    from gui.services.task_event_parser import TaskLogEventParser

    parser = TaskLogEventParser()
    for line in iter(stream.readline, ""):
        log.write(line)
        log.flush()
        context["last_output_at"] = time.time()
        if context.get("stuck"):
            context["stuck"] = False
            store.update(job_id, stuck_detected=False, stuck_since=None)
        parsed = parser.parse(line)
        if parsed is None or parsed.ignore:
            continue
        state = store.read(job_id)
        if parsed.event_type == "tokens_stats":
            values = _parse_token_payload(parsed.payload or "")
            stats = dict(state.get("tokens_stats") or {
                "prompt": 0,
                "completion": 0,
                "total": 0,
                "cached": 0,
                "ttft": 0.0,
                "throughput": 0.0,
                "steps": 0,
            })
            for key in ("prompt", "completion", "total", "cached"):
                if key in values:
                    stats[key] = int(stats.get(key, 0)) + int(values[key])
            for key in ("ttft", "throughput"):
                if key in values:
                    stats[key] = float(values[key])
            stats["steps"] = int(stats.get("steps", 0)) + 1
            store.update(job_id, tokens_stats=stats)
            continue

        event = {
            "type": parsed.event_type,
            "timestamp": time.time(),
            "message_key": parsed.message_key or "",
            "payload": parsed.payload or "",
        }
        events = list(state.get("events") or [])[-499:]
        events.append(event)
        updates = {"events": events}
        if parsed.error_summary:
            updates["error_summary"] = parsed.error_summary
        store.update(job_id, **updates)
        if parsed.needs_takeover:
            try:
                pause_job(store, job_id)
                store.update(
                    job_id,
                    takeover=True,
                    takeover_reason=parsed.payload or "Agent requested takeover",
                )
            except Exception:
                pass


def _wait_task_process(
    process: subprocess.Popen,
    log,
    store: JobStore,
    job_id: str,
    stuck_timeout: float,
) -> int:
    context = {"last_output_at": time.time(), "stuck": False}
    reader = threading.Thread(
        target=_consume_task_output,
        args=(process.stdout, log, store, job_id, context),
        name=f"autoglm-log-{job_id}",
        daemon=True,
    )
    reader.start()
    last_publish = 0.0
    while process.poll() is None:
        now = time.time()
        state = store.read(job_id)
        if state.get("state") == "paused":
            context["last_output_at"] = now
        elif now - float(context["last_output_at"]) >= stuck_timeout and not context.get("stuck"):
            context["stuck"] = True
            store.update(job_id, stuck_detected=True, stuck_since=now)
        if now - last_publish >= 2:
            store.update(job_id, last_output_at=context["last_output_at"])
            last_publish = now
        time.sleep(0.1)
    reader.join(timeout=5)
    return int(process.returncode if process.returncode is not None else process.wait())


def _task_command(spec: dict) -> tuple[list[str], dict]:
    from gui.services.config_service import ConfigService

    env_file = Path(spec["env_file"]) if spec.get("env_file") else None
    config = ConfigService(env_file=env_file)
    command = config.build_command_args(spec["task_text"], spec.get("device_id", ""))
    inbox = spec.get("inbox_path", "")
    if inbox:
        command = command[:-1] + ["--runtime-inbox-path", inbox, command[-1]]
    public = {
        "task_text": spec["task_text"],
        "device_id": spec.get("device_id", "") or config.get("OPEN_AUTOGLM_DEVICE_ID", ""),
        "model": config.get("OPEN_AUTOGLM_MODEL", ""),
        "base_url": config.get("OPEN_AUTOGLM_BASE_URL", ""),
        "max_steps": config.get("OPEN_AUTOGLM_MAX_STEPS", "100"),
    }
    return command, public


def _run_diagnostics(store: JobStore, job_id: str, spec: dict) -> int:
    from gui.services.config_service import ConfigService
    from gui.services.readiness_service import run_readiness_checks, summarize_readiness

    config = ConfigService(env_file=Path(spec["env_file"]) if spec.get("env_file") else None)
    store.update(job_id, state="running", worker_pid=os.getpid())
    results = run_readiness_checks(
        config,
        device_id=spec.get("device_id", ""),
        should_stop=lambda: _stop_requested(store, job_id),
    )
    if _stop_requested(store, job_id):
        store.update(job_id, state="cancelled", returncode=0)
        return 0
    summary = summarize_readiness(results)
    payload = {
        "checks": [asdict(item) for item in results],
        "summary": asdict(summary),
    }
    with open(store.log_path(job_id), "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, default=str)
    exit_code = 1 if summary.blocking_failed else 0
    store.update(job_id, state="failed" if exit_code else "completed", returncode=exit_code, result=payload)
    return exit_code


def _stop_requested(store: JobStore, job_id: str) -> bool:
    try:
        return bool(store.read(job_id).get("stop_requested"))
    except Exception:
        return True


def _run_api_check(store: JobStore, job_id: str, spec: dict) -> int:
    from gui.services.config_service import ConfigService

    config = ConfigService(env_file=Path(spec["env_file"]) if spec.get("env_file") else None)
    log_path = store.log_path(job_id)
    with open(log_path, "a", encoding="utf-8", errors="replace", buffering=1) as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "cli.api_probe", "--env-file", spec.get("env_file", "")],
            cwd=str(Path(__file__).resolve().parents[1]),
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        store.update(job_id, state="running", worker_pid=os.getpid(), process_pid=process.pid)
        returncode = process.wait()
    current = store.read(job_id)
    cancelled = bool(current.get("stop_requested"))
    result = {
        "base_url": config.get("OPEN_AUTOGLM_BASE_URL"),
        "model": config.get("OPEN_AUTOGLM_MODEL"),
        "reachable": returncode == 0,
    }
    final_state = "cancelled" if cancelled else ("completed" if returncode == 0 else "failed")
    store.update(job_id, state=final_state, returncode=returncode, process_pid=None, result=result)
    return returncode


def _run_qr_pair(store: JobStore, job_id: str, spec: dict) -> int:
    from gui.services.adb_client import AdbClient
    from gui.utils.runtime import find_adb_executable

    adb_path = find_adb_executable()
    client = AdbClient(str(adb_path) if adb_path else "adb")
    store.update(job_id, state="running", worker_pid=os.getpid())
    result = client.pair_via_qr(
        spec["service_name"],
        spec["password"],
        timeout=float(spec.get("timeout", 90)),
        should_stop=lambda: _stop_requested(store, job_id),
        on_service_found=lambda endpoint: store.update(job_id, pairing_endpoint=endpoint),
    )
    current = store.read(job_id)
    final_state = "cancelled" if current.get("stop_requested") else ("completed" if result.paired else "failed")
    store.log_path(job_id).write_text(result.message, encoding="utf-8")
    store.update(job_id, state=final_state, returncode=0 if result.paired else 1, result=asdict(result))
    return 0 if result.paired else 1


def _run_device_operation(store: JobStore, job_id: str, spec: dict) -> int:
    from gui.services.adb_client import AdbClient
    from gui.utils.runtime import find_adb_executable, find_adb_keyboard_apk

    client = AdbClient(str(find_adb_executable() or "adb"))
    operation = spec["operation"]
    stop = lambda: _stop_requested(store, job_id)
    store.update(job_id, state="running", worker_pid=os.getpid())
    payload: dict = {"operation": operation}
    if operation == "connect":
        ok, message = client.connect(spec["endpoint"], should_stop=stop)
    elif operation == "disconnect":
        ok, message = client.disconnect(spec.get("endpoint", ""), should_stop=stop)
    elif operation == "pair":
        result = client.pair_and_connect(
            spec["endpoint"],
            spec["code"],
            connect_timeout=float(spec.get("connect_timeout", 15)),
            should_stop=stop,
        )
        ok, message = result.paired, result.message
        payload.update(asdict(result))
    elif operation == "tcpip":
        result = client.enable_tcpip(
            spec["device_id"],
            int(spec.get("port", 5555)),
            connect_timeout=float(spec.get("connect_timeout", 12)),
            should_stop=stop,
        )
        ok, message = result.success, result.message
        payload.update(asdict(result))
    elif operation == "usb":
        ok, message = client.use_usb(spec["device_id"], should_stop=stop)
    elif operation == "install_keyboard":
        apk = find_adb_keyboard_apk()
        if not apk:
            ok, message = False, "未找到 ADBKeyboard.apk"
        else:
            result = client.run(
                ["install", "-r", str(apk)],
                timeout=60,
                serial=spec["device_id"],
                should_stop=stop,
            )
            ok, message = result.returncode == 0, result.merged_output
            if ok and not stop():
                client.run(
                    ["shell", "ime", "enable", "com.android.adbkeyboard/.AdbIME"],
                    timeout=15,
                    serial=spec["device_id"],
                    should_stop=stop,
                )
            payload["apk"] = str(apk)
    else:
        raise ValueError(f"未知设备后台操作：{operation}")

    current = store.read(job_id)
    cancelled = bool(current.get("stop_requested"))
    final_state = "cancelled" if cancelled else ("completed" if ok else "failed")
    payload["message"] = message
    store.log_path(job_id).write_text(message or "", encoding="utf-8")
    store.update(
        job_id,
        state=final_state,
        returncode=0 if ok else 1,
        result=payload,
    )
    return 0 if ok else 1


def _run_adb_mirror(store: JobStore, job_id: str, spec: dict) -> int:
    from gui.utils.runtime import find_adb_executable

    adb = str(find_adb_executable() or "adb")
    device_id = spec["device_id"]
    interval = max(0.3, float(spec.get("interval", 1.5)))
    frame = Path(spec["frame_path"])
    frame.parent.mkdir(parents=True, exist_ok=True)
    store.update(job_id, state="running", worker_pid=os.getpid(), latest_frame=str(frame), mode="adb_screenshot")
    failures = 0
    while not _stop_requested(store, job_id):
        try:
            result = subprocess.run(
                [adb, "-s", device_id, "exec-out", "screencap", "-p"],
                capture_output=True,
                timeout=15,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
            )
            if result.returncode == 0 and result.stdout:
                tmp = frame.with_suffix(".tmp")
                tmp.write_bytes(result.stdout)
                tmp.replace(frame)
                failures = 0
                store.update(job_id, latest_frame=str(frame), last_frame_at=time.time())
            else:
                failures += 1
        except Exception as exc:
            failures += 1
            store.update(job_id, error=str(exc))
        if failures >= 5:
            store.update(job_id, state="failed", returncode=1, error="ADB 镜像连续截图失败")
            return 1
        deadline = time.monotonic() + interval
        while time.monotonic() < deadline and not _stop_requested(store, job_id):
            time.sleep(0.1)
    store.update(job_id, state="cancelled", returncode=0)
    return 0


def _append_history(store: JobStore, state: dict, final_state: str) -> None:
    if state.get("kind") != "task":
        return
    history_dir = store.root.parent
    index_path = history_dir / "index.json"
    history_dir.mkdir(parents=True, exist_ok=True)
    with store.history_lock():
        try:
            records = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else []
            if not isinstance(records, list):
                records = []
        except Exception:
            records = []
        start = float(state.get("created_at") or time.time())
        end = float(state.get("updated_at") or time.time())
        record = {
            "task_id": state["job_id"],
            "task_text": state.get("task_text", ""),
            "start_time": start,
            "end_time": end,
            "state": final_state,
            "device_id": state.get("device_id", ""),
            "model": state.get("model", ""),
            "base_url": state.get("base_url", ""),
            "max_steps": state.get("max_steps", ""),
            "log_file": state.get("log_file", ""),
            "events": list(state.get("events") or []),
            "result_summary": "后台 CLI 任务执行完成" if final_state == "completed" else "",
            "error_summary": state.get("error_summary", "") or (
                state.get("error", "") if final_state == "failed" else ""
            ),
            "tokens_stats": dict(state.get("tokens_stats") or {}),
        }
        records = [item for item in records if item.get("task_id") != state["job_id"]]
        records.insert(0, record)
        JobStore._atomic_write(index_path, records)


def _run_process(store: JobStore, job_id: str, spec: dict) -> int:
    state = store.read(job_id)
    if state.get("stop_requested"):
        store.update(job_id, state="cancelled", worker_pid=os.getpid(), returncode=0)
        return 0
    if state.get("kind") == "task":
        command, public = _task_command(spec)
        state = store.update(job_id, **public)
    else:
        command = [str(item) for item in spec["command"]]

    env = os.environ.copy()
    env.update({str(k): str(v) for k, v in spec.get("env", {}).items()})
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    cwd = spec.get("cwd") or os.getcwd()
    log_path = store.log_path(job_id)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    is_task = state.get("kind") == "task"
    with open(log_path, "a", encoding="utf-8", errors="replace", buffering=1) as log:
        try:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE if is_task else log,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
            )
        except Exception as exc:
            final = store.update(job_id, state="failed", worker_pid=os.getpid(), error=str(exc), returncode=127)
            _append_history(store, final, "failed")
            return 127
        store.update(job_id, state="running", worker_pid=os.getpid(), process_pid=process.pid)
        returncode = (
            _wait_task_process(
                process,
                log,
                store,
                job_id,
                float(spec.get("stuck_timeout", 120)),
            )
            if is_task
            else process.wait()
        )

    current = store.read(job_id)
    if current.get("stop_requested"):
        final_state = "cancelled"
    else:
        final_state = "completed" if returncode == 0 else "failed"
    final = store.update(job_id, state=final_state, returncode=returncode, process_pid=None)
    _append_history(store, final, final_state)
    return returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args(argv)
    store = JobStore(args.state_dir)
    try:
        spec = store.read_spec(args.job_id, consume=True)
        kind = store.read(args.job_id).get("kind")
        if kind == "diagnostics":
            return _run_diagnostics(store, args.job_id, spec)
        if kind == "api_check":
            return _run_api_check(store, args.job_id, spec)
        if kind == "device_qr_pair":
            return _run_qr_pair(store, args.job_id, spec)
        if kind == "device_operation":
            return _run_device_operation(store, args.job_id, spec)
        if kind == "mirror_adb":
            return _run_adb_mirror(store, args.job_id, spec)
        return _run_process(store, args.job_id, spec)
    except Exception as exc:
        cancelled = False
        try:
            current = store.read(args.job_id)
            cancelled = bool(current.get("stop_requested"))
            store.update(
                args.job_id,
                state="cancelled" if cancelled else "failed",
                worker_pid=os.getpid(),
                error="" if cancelled else str(exc),
                returncode=0 if cancelled else 1,
            )
        except Exception:
            pass
        return 0 if cancelled else 1


if __name__ == "__main__":
    raise SystemExit(main())
