import sys
import time
from pathlib import Path

from PySide6.QtCore import QCoreApplication

from cli.automation_cli import main
from gui.services.task_service import TaskService, TaskState


class FakeConfig:
    def __init__(self, runner: Path):
        self.runner = runner

    def get(self, key, default=""):
        values = {
            "OPEN_AUTOGLM_DEVICE_ID": "test-device",
            "OPEN_AUTOGLM_MODEL": "test-model",
            "OPEN_AUTOGLM_BASE_URL": "http://127.0.0.1:9/v1",
            "OPEN_AUTOGLM_MAX_STEPS": "1",
        }
        return values.get(key, default)

    def build_command_args(self, task_text, device_id_override=""):
        return [sys.executable, "-u", str(self.runner), task_text]


def test_cli_controls_task_started_by_gui(tmp_path, monkeypatch, capsys):
    QCoreApplication.instance() or QCoreApplication([])
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPEN_AUTOGLM_CLI_STATE_DIR", raising=False)
    runner = tmp_path / "runner.py"
    runner.write_text(
        "import argparse,time\n"
        "p=argparse.ArgumentParser(); p.add_argument('--runtime-inbox-path'); p.add_argument('task'); p.parse_args()\n"
        "print('ready', flush=True); time.sleep(60)\n",
        encoding="utf-8",
    )
    service = TaskService(config_service=FakeConfig(runner))
    assert service.start_task("gui-owned") is True
    job_id = service.automation_job_id
    assert job_id

    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        state = service._automation_store.read(job_id)
        if state.get("state") == "running" and state.get("process_pid"):
            break
        time.sleep(0.05)

    assert main(["--state-dir", str(service._automation_store.root), "task", "pause", job_id]) == 0
    capsys.readouterr()
    service._poll_process()
    assert service.state == TaskState.PAUSED

    assert main(["--state-dir", str(service._automation_store.root), "task", "resume", job_id]) == 0
    capsys.readouterr()
    service._poll_process()
    assert service.state == TaskState.RUNNING

    assert main(["--state-dir", str(service._automation_store.root), "task", "stop", job_id, "--stop-timeout", "2"]) == 0
    capsys.readouterr()
    deadline = time.monotonic() + 10
    while service.state not in {TaskState.CANCELLED, TaskState.FAILED} and time.monotonic() < deadline:
        service._poll_process()
        time.sleep(0.05)
    assert service.state == TaskState.CANCELLED
    assert service._automation_store.read(job_id)["state"] == "cancelled"
    service.shutdown()
