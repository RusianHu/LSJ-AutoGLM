#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GUI 离屏截图工具 - 用于自动化视觉验证（非阻塞 CLI）

用法:
    python scripts/gui_screenshot.py --theme dark --out build/ui_preview
    python scripts/gui_screenshot.py --theme both --pages dashboard,settings

说明:
    - 默认使用 QT_QPA_PLATFORM=offscreen，不弹出窗口
    - 直接调用 MainWindow.apply_theme()，不写入 .env
    - 输出 PNG: <out>/<theme>_<page>.png
"""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

PAGES = ["dashboard", "device", "history", "settings", "diag"]


def main() -> int:
    parser = argparse.ArgumentParser(description="GUI offscreen screenshot tool")
    parser.add_argument("--theme", default="both", choices=["dark", "light", "both"])
    parser.add_argument("--pages", default="all", help="逗号分隔页面 key 或 all")
    parser.add_argument("--out", default="build/ui_preview")
    parser.add_argument("--width", type=int, default=1360)
    parser.add_argument("--height", type=int, default=850)
    parser.add_argument(
        "--platform",
        default="native",
        choices=["native", "offscreen"],
        help="native: 使用系统平台+WA_DontShowOnScreen（字体完整，不弹窗）；offscreen: 纯离屏（CI 环境）",
    )
    args = parser.parse_args()

    if args.platform == "offscreen":
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    os.chdir(ROOT)

    from PySide6.QtCore import Qt, QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication
    from gui.services.config_service import ConfigService
    from gui.services.device_service import DeviceService
    from gui.services.history_service import HistoryService
    from gui.services.mirror_service import MirrorService
    from gui.services.task_service import TaskService
    from gui.main_window import MainWindow

    app = QApplication([])
    app.setStyle("Fusion")
    app.setApplicationName("Open-AutoGLM")
    app.setApplicationVersion("1.0.11")

    config = ConfigService()
    history = HistoryService()
    mirror = MirrorService()
    device = DeviceService(config_service=config)
    task = TaskService(config_service=config, history_service=history)
    window = MainWindow({
        "config": config,
        "history": history,
        "mirror": mirror,
        "device": device,
        "task": task,
    })
    window.resize(args.width, args.height)
    if args.platform == "native":
        # 完整渲染但不在屏幕上显示，避免截图时窗口闪现
        window.setAttribute(Qt.WA_DontShowOnScreen, True)
    window.show()
    app.processEvents()

    themes = ["dark", "light"] if args.theme == "both" else [args.theme]
    pages = PAGES if args.pages == "all" else [p.strip() for p in args.pages.split(",") if p.strip()]

    out_dir = ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    def wait_ms(ms: int) -> None:
        """驱动事件循环等待（让页面淡入动画播完再截图）。"""
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    saved = []
    for theme in themes:
        window.apply_theme(theme)
        app.processEvents()
        for page in pages:
            window.switch_page(page)
            wait_ms(260)
            path = out_dir / f"{theme}_{page}.png"
            window.grab().save(str(path))
            saved.append(path)

    window.close()
    app.processEvents()

    for path in saved:
        print(f"saved: {path.relative_to(ROOT)}")
    print("screenshot-ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
