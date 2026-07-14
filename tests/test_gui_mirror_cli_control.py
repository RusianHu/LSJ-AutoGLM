from PySide6.QtCore import QCoreApplication

from cli.automation_cli import main
from gui.services.mirror_service import MirrorMode, MirrorService, MirrorState


def test_cli_discovers_and_stops_gui_adb_mirror(tmp_path, monkeypatch, capsys):
    app = QCoreApplication.instance() or QCoreApplication([])
    assert app is not None
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPEN_AUTOGLM_CLI_STATE_DIR", raising=False)
    service = MirrorService()

    def fake_adb_start(device_id):
        service._mode = MirrorMode.ADB_SCREENSHOT
        service._set_state(MirrorState.RUNNING)
        service._publish_automation_state(
            "running", mode=MirrorMode.ADB_SCREENSHOT.value, process_pid=None
        )

    monkeypatch.setattr(service, "find_scrcpy", lambda: None)
    monkeypatch.setattr(service, "_start_adb_screenshot", fake_adb_start)
    service.start("gui-device")
    job_id = service.automation_job_id
    assert job_id
    state = service._automation_store.read(job_id)
    assert state["owner"] == "gui"
    assert state["state"] == "running"

    assert main(["--state-dir", str(service._automation_store.root), "mirror", "stop", "--job-id", job_id, "--stop-timeout", "0.1"]) == 0
    capsys.readouterr()
    assert service._automation_store.read(job_id)["state"] == "stopping"
    service._sync_external_automation_control()
    assert service.state == MirrorState.STOPPED
    assert service._automation_store.read(job_id)["state"] == "cancelled"
