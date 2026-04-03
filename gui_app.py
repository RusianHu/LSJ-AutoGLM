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

from gui.utils.runtime import (
    GUI_TASK_RUNNER_FLAG,
    app_root,
    ensure_runtime_path,
    ensure_standard_streams,
    patch_subprocess_for_gui,
)

# 确保 UTF-8 编码（仅通过环境变量，不调用 os.system/chcp，
# 避免 PyInstaller --windowed 模式下弹出黑色 cmd 控制台窗口）
os.environ["PYTHONIOENCODING"] = "utf-8"
if sys.platform == "win32":
    # chcp 65001 对无控制台的 GUI 进程没有实际作用，
    # 且 os.system() 会创建 cmd.exe 子进程导致黑框闪现，故移除。
    os.environ.setdefault("PYTHONUTF8", "1")

# 源码运行时为仓库根目录；单文件运行时为 exe 所在目录
ROOT = app_root().resolve()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 统一工作目录，保证 .env / 历史日志 / 打包脚本等路径稳定
os.chdir(ROOT)
ensure_runtime_path()
patch_subprocess_for_gui()


def _run_task_runner():
    """单文件模式下的任务子进程入口。"""
    ensure_standard_streams()
    if len(sys.argv) > 1 and sys.argv[1] == GUI_TASK_RUNNER_FLAG:
        sys.argv = [sys.argv[0], *sys.argv[2:]]

    from main import main as cli_main

    cli_main()


def main():
    if len(sys.argv) > 1 and sys.argv[1] == GUI_TASK_RUNNER_FLAG:
        _run_task_runner()
        return

    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont

    # 高 DPI 属性需在 QApplication 实例化前设置（Qt6 中此项通常默认开启，此处保留兼容写法）
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    # 使用 Fusion 风格，避免 Windows 原生样式对按钮 QSS 的干扰，
    # 提高浅色/深色主题下按钮填充、边框、文字颜色的一致性。
    app.setStyle("Fusion")
    app.setApplicationName("Open-AutoGLM")
    app.setApplicationVersion("1.0.4")
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
    device  = DeviceService(config_service=config)
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
