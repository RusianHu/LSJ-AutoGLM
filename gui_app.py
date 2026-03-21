#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Open-AutoGLM GUI 启动入口

用法:
    python gui_app.py

依赖:
    pip install PySide6

修复记录:
- 退出清理改为调用服务的统一 shutdown()/stop() 接口，不再直接操作私有成员
- QApplication 属性设置移至实例化之前（Qt.AA_UseHighDpiPixmaps）
"""

import os
import sys
from pathlib import Path

# 确保 UTF-8 编码
os.environ["PYTHONIOENCODING"] = "utf-8"
if sys.platform == "win32":
    os.system("chcp 65001 >nul 2>&1")

# 确保项目根目录在 sys.path 中
ROOT = Path(__file__).parent.resolve()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 切换工作目录到项目根（保证 main.py 子进程路径正确）
os.chdir(ROOT)


def main():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont

    # 高 DPI 属性需在 QApplication 实例化前设置（Qt6 中此项通常默认开启，此处保留兼容写法）
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("Open-AutoGLM")
    app.setApplicationVersion("0.1")
    app.setOrganizationName("Open-AutoGLM")

    # 设置默认字体
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # ---------- 初始化服务层 ----------
    from gui.services.config_service import ConfigService
    from gui.services.device_service import DeviceService
    from gui.services.history_service import HistoryService
    from gui.services.mirror_service import MirrorService
    from gui.services.task_service import TaskService

    config  = ConfigService()
    history = HistoryService()
    mirror  = MirrorService()
    device  = DeviceService()
    task    = TaskService(config_service=config, history_service=history)

    services = {
        "config":  config,
        "device":  device,
        "task":    task,
        "history": history,
        "mirror":  mirror,
    }

    # ---------- 启动主窗口 ----------
    from gui.main_window import MainWindow
    window = MainWindow(services)
    window.show()

    ret = app.exec()
    # closeEvent 已在窗口关闭时完成所有清理，此处无需重复调用

    sys.exit(ret)


if __name__ == "__main__":
    main()
