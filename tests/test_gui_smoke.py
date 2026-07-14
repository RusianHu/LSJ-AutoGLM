import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_gui_constructs_and_shuts_down_offscreen():
    script = """
from PySide6.QtWidgets import QApplication
from gui.services.config_service import ConfigService
from gui.services.device_service import DeviceService
from gui.services.history_service import HistoryService
from gui.services.mirror_service import MirrorService
from gui.services.task_service import TaskService
from gui.main_window import MainWindow
app = QApplication([])
config = ConfigService()
history = HistoryService()
mirror = MirrorService()
device = DeviceService(config_service=config)
task = TaskService(config_service=config, history_service=history)
window = MainWindow({'config': config, 'history': history, 'mirror': mirror, 'device': device, 'task': task})
window.show()
app.processEvents()
window.close()
app.processEvents()
print('gui-smoke-ok')
"""
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "gui-smoke-ok" in result.stdout
