import json

from gui.services.history_service import HistoryService


def test_open_gui_history_service_observes_cli_index_updates(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    service = HistoryService()
    assert service.get_all() == []

    index = tmp_path / "gui_history" / "index.json"
    index.write_text(
        json.dumps([{"task_id": "cli-task", "state": "completed", "events": []}]),
        encoding="utf-8",
    )

    assert service.get_all()[0]["task_id"] == "cli-task"
    assert service.get_record("cli-task")["state"] == "completed"


def test_gui_save_preserves_cli_record_added_after_service_start(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    service = HistoryService()
    index = tmp_path / "gui_history" / "index.json"
    index.write_text(
        json.dumps([{"task_id": "cli-task", "state": "completed", "events": []}]),
        encoding="utf-8",
    )

    service.save_record({"task_id": "gui-task", "state": "completed", "events": []})
    ids = [item["task_id"] for item in json.loads(index.read_text(encoding="utf-8"))]
    assert ids == ["gui-task", "cli-task"]
