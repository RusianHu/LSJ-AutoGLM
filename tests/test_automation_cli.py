import json
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from cli.automation_cli import main
from cli.automation_state import JobStore
from cli.job_control import (
    pause_job,
    resume_job,
    start_job,
    stop_job,
    submit_instruction,
    wait_job,
)
from cli.job_worker import _run_device_operation, _wait_task_process


def run_cli(capsys, *argv):
    code = main(list(argv))
    output = capsys.readouterr().out
    return code, json.loads(output)


def test_capabilities_describe_every_surface(capsys):
    code, payload = run_cli(capsys, "capabilities")
    assert code == 0
    assert payload["ok"] is True
    surfaces = payload["data"]["surfaces"]
    assert {"TUI/Agent", "GUI/设置", "GUI/设备", "GUI/诊断", "GUI/历史", "GUI/镜像", "GUI/构建"} == set(surfaces)
    assert payload["data"]["contract"]["default_output"] == "json"


def test_invalid_arguments_still_return_json_envelope(capsys):
    code, payload = run_cli(capsys, "task", "status")
    assert code == 2
    assert payload["ok"] is False
    assert "参数错误" in payload["message"]


def test_config_commands_share_isolated_env_and_mask_secrets(tmp_path, capsys):
    env_file = tmp_path / ".env"
    common = ("--env-file", str(env_file), "--state-dir", str(tmp_path / "state"))

    code, payload = run_cli(capsys, *common, "config", "set-many", json.dumps({
        "OPEN_AUTOGLM_LANG": "en",
        "OPEN_AUTOGLM_API_KEY": "test-value-not-a-real-secret",
    }))
    assert code == 0
    assert set(payload["data"]["updated"]) == {"OPEN_AUTOGLM_LANG", "OPEN_AUTOGLM_API_KEY"}

    code, payload = run_cli(capsys, *common, "config", "get", "OPEN_AUTOGLM_API_KEY")
    assert code == 0
    assert "secret" not in payload["data"]["value"]

    code, payload = run_cli(capsys, *common, "config", "validate")
    assert code == 0
    assert payload["data"]["valid"] is True


def test_channel_and_policy_mutations_are_scriptable(tmp_path, capsys):
    common = ("--env-file", str(tmp_path / ".env"), "--state-dir", str(tmp_path / "state"))
    code, payload = run_cli(capsys, *common, "config", "use-channel", "newapi")
    assert code == 0
    assert payload["data"]["active_channel"] == "newapi"

    code, payload = run_cli(capsys, *common, "config", "action-policy", "--platform", "adb", "--clear")
    assert code == 0
    assert payload["data"]["use_platform_defaults"] is False
    assert payload["data"]["enabled_actions"] == "[]"

    code, payload = run_cli(capsys, *common, "config", "mirror-toolbar", "--clear", "--enabled", "false")
    assert code == 0
    assert payload["data"] == {"enabled": False, "actions": []}


def test_detached_job_finishes_and_captures_log(tmp_path):
    store = JobStore(tmp_path / "state")
    started_at = time.monotonic()
    state = start_job(
        store,
        "test",
        {"command": [sys.executable, "-u", "-c", "print('background-ok')"], "cwd": str(Path.cwd())},
        cwd=Path.cwd(),
    )
    assert time.monotonic() - started_at < 2
    assert state["state"] == "starting"
    final = wait_job(store, state["job_id"], timeout=15)
    assert final["state"] == "completed"
    assert final["returncode"] == 0
    assert "background-ok" in store.tail(state["job_id"])


def test_job_pause_resume_stop_across_processes(tmp_path):
    store = JobStore(tmp_path / "state")
    state = start_job(
        store,
        "test",
        {"command": [sys.executable, "-u", "-c", "import time; print('ready'); time.sleep(60)"], "cwd": str(Path.cwd())},
        cwd=Path.cwd(),
    )
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        state = store.read(state["job_id"])
        if state["state"] == "running" and state.get("process_pid"):
            break
        time.sleep(0.05)
    assert state["state"] == "running"
    assert pause_job(store, state["job_id"])["state"] == "paused"
    assert resume_job(store, state["job_id"])["state"] == "running"
    stopped = stop_job(store, state["job_id"], timeout=2)
    if stopped["state"] == "stopping":
        stopped = wait_job(store, state["job_id"], timeout=10)
    assert stopped["state"] == "cancelled"


def test_runtime_instruction_inbox_is_cross_process_safe(tmp_path):
    store = JobStore(tmp_path / "state")
    inbox = tmp_path / "inbox.jsonl"
    inbox.write_text("", encoding="utf-8")
    state = store.create("task", {"unused": True}, {"inbox_path": str(inbox)})
    store.update(state["job_id"], state="running")
    entry = submit_instruction(store, state["job_id"], "继续并检查结果")
    saved = json.loads(inbox.read_text(encoding="utf-8").strip())
    assert saved["id"] == entry["id"]
    assert saved["text"] == "继续并检查结果"


def test_concurrent_job_updates_do_not_lose_fields(tmp_path):
    store = JobStore(tmp_path / "state")
    state = store.create("test", {"unused": True})
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda index: store.update(state["job_id"], **{f"field_{index}": index}), range(20)))
    saved = store.read(state["job_id"])
    assert all(saved[f"field_{index}"] == index for index in range(20))


def test_task_worker_exposes_tokens_events_takeover_and_resume(tmp_path):
    store = JobStore(tmp_path / "state")
    state = store.create("task", {"unused": True})
    process = subprocess.Popen(
        [
            sys.executable,
            "-u",
            "-c",
            "import time; print('[TOKENS] prompt=10 completion=2 total=12 cached=1 ttft=0.2 throughput=5.5'); print('Agent requested takeover'); time.sleep(0.3)",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
    )
    store.update(state["job_id"], state="running", process_pid=process.pid)
    log_path = store.log_path(state["job_id"])
    result = {}

    def wait_in_worker():
        with open(log_path, "w", encoding="utf-8", buffering=1) as log:
            result["returncode"] = _wait_task_process(process, log, store, state["job_id"], 10)

    thread = threading.Thread(target=wait_in_worker)
    thread.start()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and store.read(state["job_id"])["state"] != "paused":
        time.sleep(0.05)
    saved = store.read(state["job_id"])
    assert saved["state"] == "paused"
    assert saved["takeover"] is True
    assert saved["tokens_stats"]["total"] == 12
    assert saved["tokens_stats"]["steps"] == 1
    assert any(event["type"] == "takeover" for event in saved["events"])
    resume_job(store, state["job_id"])
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert result["returncode"] == 0


def test_task_worker_marks_silent_process_as_stuck(tmp_path):
    store = JobStore(tmp_path / "state")
    state = store.create("task", {"unused": True})
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(0.5)"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
    )
    store.update(state["job_id"], state="running", process_pid=process.pid)
    with open(store.log_path(state["job_id"]), "w", encoding="utf-8") as log:
        assert _wait_task_process(process, log, store, state["job_id"], 0.1) == 0
    assert store.read(state["job_id"])["stuck_detected"] is True


def test_device_operation_worker_persists_structured_result(tmp_path, monkeypatch):
    import gui.services.adb_client as adb_module

    class FakeAdbClient:
        def __init__(self, _path):
            pass

        def connect(self, endpoint, should_stop=None):
            assert endpoint == "127.0.0.1:5555"
            assert should_stop() is False
            return True, "connected"

    monkeypatch.setattr(adb_module, "AdbClient", FakeAdbClient)
    store = JobStore(tmp_path / "state")
    state = store.create("device_operation", {"unused": True})
    code = _run_device_operation(
        store,
        state["job_id"],
        {"operation": "connect", "endpoint": "127.0.0.1:5555"},
    )
    saved = store.read(state["job_id"])
    assert code == 0
    assert saved["state"] == "completed"
    assert saved["result"]["message"] == "connected"


def test_history_crud_uses_gui_compatible_index(tmp_path, capsys):
    store = JobStore(tmp_path / "state")
    history = store.root.parent / "index.json"
    history.write_text(json.dumps([{"task_id": "abc", "state": "completed", "log_file": ""}]), encoding="utf-8")
    common = ("--state-dir", str(store.root))
    code, payload = run_cli(capsys, *common, "history", "show", "abc")
    assert code == 0 and payload["data"]["task_id"] == "abc"
    code, payload = run_cli(capsys, *common, "history", "delete", "abc")
    assert code == 0
    assert json.loads(history.read_text(encoding="utf-8")) == []
