import os

from PySide6.QtCore import QCoreApplication

from gui.services.config_service import ConfigService
from gui.services.device_service import DeviceInfo, DeviceService, DeviceStatus


def test_open_gui_config_observes_cli_atomic_write(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    assert app is not None
    env_file = tmp_path / ".env"
    gui_config = ConfigService(env_file=env_file)
    cli_config = ConfigService(env_file=env_file)

    cli_config.set("OPEN_AUTOGLM_LANG", "en")
    assert gui_config.get("OPEN_AUTOGLM_LANG") == "cn"
    gui_config._check_external_change()
    assert gui_config.get("OPEN_AUTOGLM_LANG") == "en"

    gui_config.shutdown()
    cli_config.shutdown()


def test_external_change_detection_handles_same_timestamp_and_size(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    assert app is not None
    env_file = tmp_path / ".env"
    config = ConfigService(env_file=env_file)
    config.set("OPEN_AUTOGLM_LANG", "cn")
    original_stat = env_file.stat()

    content = env_file.read_text(encoding="utf-8")
    updated = content.replace("OPEN_AUTOGLM_LANG=cn", "OPEN_AUTOGLM_LANG=en")
    assert len(updated) == len(content)
    env_file.write_text(updated, encoding="utf-8")
    os.utime(
        env_file,
        ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
    )

    config._check_external_change()

    assert config.get("OPEN_AUTOGLM_LANG") == "en"
    config.shutdown()


def test_device_service_applies_externally_selected_device(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    assert app is not None
    config = ConfigService(env_file=tmp_path / ".env")
    service = DeviceService(config_service=config)
    service._initial_timer.stop()
    service._poll_timer.stop()
    service._devices = [
        DeviceInfo("first", DeviceStatus.CONNECTED),
        DeviceInfo("second", DeviceStatus.CONNECTED),
    ]
    service.select_device("first")
    config.set("OPEN_AUTOGLM_DEVICE_ID", "second")
    assert service.selected_device.device_id == "second"
    service.stop()
    config.shutdown()
