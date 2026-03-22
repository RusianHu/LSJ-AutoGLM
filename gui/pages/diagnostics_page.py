# -*- coding: utf-8 -*-
"""诊断页 - 一键系统检查：ADB、设备、API、Python 依赖、GUI 环境"""

import shutil
import subprocess
import sys

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from gui.theme.tokens import ThemeTokens
from gui.theme.themes import resolve_theme_tokens
from gui.theme.styles.buttons import btn_primary


class _DiagWorker(QThread):
    """在后台线程中运行所有诊断检查"""
    result_ready = Signal(str, bool, str)   # (check_name, passed, detail)
    all_done = Signal()

    def __init__(self, config_service=None):
        super().__init__()
        self._config = config_service
        self._stop_requested = False

    def request_stop(self):
        self._stop_requested = True

    def run(self):
        checks = [
            ("Python 版本",          self._check_python),
            ("PySide6 安装",          self._check_pyside6),
            ("ADB 可用性",            self._check_adb),
            ("设备连接",              self._check_devices),
            ("ADB Keyboard",         self._check_adb_keyboard),
            ("scrcpy 可用性",         self._check_scrcpy),
            ("openai 包",             self._check_openai),
            ("dotenv 包",             self._check_dotenv),
            ("main.py 可访问",        self._check_main_py),
            ("API 连通性",            self._check_api),
        ]
        for name, fn in checks:
            if self._stop_requested:
                break
            try:
                passed, detail = fn()
            except Exception as e:
                passed, detail = False, str(e)
            self.result_ready.emit(name, passed, detail)

        self.all_done.emit()

    # ---------- 检查项 ----------

    def _check_python(self):
        v = sys.version
        ok = sys.version_info >= (3, 10)
        return ok, f"Python {v}"

    def _check_pyside6(self):
        try:
            import PySide6
            return True, f"PySide6 {PySide6.__version__}"
        except ImportError:
            return False, "PySide6 未安装"

    def _check_adb(self):
        path = shutil.which("adb")
        if not path:
            return False, "ADB 未找到，请安装 Android Platform Tools 并加入 PATH"
        try:
            r = subprocess.run(["adb", "version"], capture_output=True, text=True, timeout=5)
            ver = r.stdout.splitlines()[0] if r.stdout else "ADB"
            return True, ver
        except Exception as e:
            return False, str(e)

    def _check_devices(self):
        try:
            r = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=10)
            lines = [l for l in r.stdout.splitlines()[1:] if l.strip() and "offline" not in l]
            if not lines:
                return False, "未找到已连接设备"
            return True, f"找到 {len(lines)} 台设备: " + ", ".join(l.split()[0] for l in lines)
        except Exception as e:
            return False, str(e)

    def _check_adb_keyboard(self):
        try:
            r = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=10)
            lines = [l.strip() for l in r.stdout.splitlines()[1:] if l.strip()]
            if not lines:
                return False, "无可用设备，跳过检查"
            device_id = lines[0].split()[0]
            r2 = subprocess.run(
                ["adb", "-s", device_id, "shell", "pm", "list", "packages", "com.android.adbkeyboard"],
                capture_output=True, text=True, timeout=10
            )
            if "com.android.adbkeyboard" in r2.stdout:
                return True, f"ADB Keyboard 已安装 ({device_id})"
            return False, f"ADB Keyboard 未安装 ({device_id})"
        except Exception as e:
            return False, str(e)

    def _check_scrcpy(self):
        path = shutil.which("scrcpy")
        if path:
            try:
                r = subprocess.run(["scrcpy", "--version"], capture_output=True, text=True, timeout=5)
                ver = r.stdout.strip().splitlines()[0] if r.stdout else "scrcpy"
                return True, ver
            except Exception:
                return True, f"scrcpy: {path}"
        return False, "scrcpy 未找到（可选项，用于实时镜像；缺少时将降级为 ADB 截图模式）"

    def _check_openai(self):
        try:
            import openai
            return True, f"openai {openai.__version__}"
        except ImportError:
            return False, "openai 包未安装，运行: pip install openai"

    def _check_dotenv(self):
        # 项目使用自实现的 .env 加载，不依赖 python-dotenv
        return True, "使用内置 .env 加载（无需 python-dotenv）"

    def _check_main_py(self):
        from pathlib import Path
        p = Path("main.py")
        if p.exists():
            return True, f"main.py 存在: {p.resolve()}"
        return False, "main.py 不存在，请检查工作目录"

    def _check_api(self):
        if not self._config:
            return False, "配置服务不可用"
        base_url = self._config.get("OPEN_AUTOGLM_BASE_URL")
        if not base_url:
            return False, "未配置 Base URL"
        try:
            import urllib.request
            # 仅检查域名可达性，不发送真实请求
            from urllib.parse import urlparse
            parsed = urlparse(base_url)
            host = parsed.netloc
            if not host:
                return False, f"Base URL 格式异常: {base_url}"
            # 尝试 TCP 连接
            import socket
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            hostname = host.split(":")[0]
            sock = socket.create_connection((hostname, port), timeout=5)
            sock.close()
            return True, f"API 端点可达: {host}"
        except Exception as e:
            return False, f"API 端点不可达: {e}"


class DiagnosticsPage(QWidget):
    """诊断页"""

    def __init__(self, services: dict, parent=None):
        super().__init__(parent)
        self._services = services
        self._config = services.get("config")
        self._worker: _DiagWorker = None
        self._theme_mode = "dark"
        self._theme_tokens = resolve_theme_tokens(self._theme_mode)
        self._theme_vars = self._theme_tokens.to_legacy_dict()
        self._last_summary_state = ("点击「一键检查」开始诊断", "idle")
        self._build_ui()
        self._apply_action_button_styles()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)

        # 标题行
        header = QHBoxLayout()
        title = QLabel("系统诊断")
        title.setProperty("role", "pageTitle")
        header.addWidget(title)
        header.addStretch(1)

        self._btn_run = QPushButton("一键检查")
        self._btn_run.setProperty("variant", "primary")
        self._btn_run.clicked.connect(self._on_run)
        header.addWidget(self._btn_run)
        root.addLayout(header)

        # 说明
        hint = QLabel("检查项包括：Python 版本、PySide6、ADB、设备连接、ADB Keyboard、scrcpy、openai 包、API 连通性等。")
        hint.setProperty("role", "subtle")
        hint.setStyleSheet("font-size:12px;")
        hint.setWordWrap(True)
        root.addWidget(hint)

        # 结果列表
        self._result_list = QListWidget()
        self._result_list.setProperty("surface", "console")
        root.addWidget(self._result_list, 1)

        # 摘要
        self._summary_lbl = QLabel("点击「一键检查」开始诊断")
        self._summary_lbl.setWordWrap(True)
        root.addWidget(self._summary_lbl)

    def _result_list_style(self) -> str:
        v = self._theme_vars or {}
        return (
            "QListWidget {"
            f"background:{v.get('bg_console', '#0a0f18')}; border:1px solid {v.get('border', '#30363d')};"
            f"border-radius:8px; color:{v.get('text_primary', '#c9d1d9')}; font-size:13px; padding:4px;"
            "}"
            "QListWidget::item {"
            f"padding:8px 12px; border-radius:4px; border-bottom:1px solid {v.get('bg_elevated', '#1b2432')};"
            "}"
            f"QListWidget::item:selected {{ background:{v.get('selection_bg', '#264f78')}; }}"
        )

    def _summary_style(self, state: str) -> str:
        v = self._theme_vars or {}
        if state == "success":
            color = v.get("success", "#3fb950")
            bg = v.get("success_bg", "#0f2d1a")
            border = v.get("success_border", "#3fb95040")
        elif state == "warning":
            color = v.get("warning", "#e3b341")
            bg = v.get("warning_bg", "#2d2200")
            border = v.get("warning_border", "#e3b34140")
        else:
            color = v.get("text_secondary", "#8b949e")
            bg = v.get("bg_secondary", "#161b22")
            border = v.get("border", "#30363d")
        return (
            f"background:{bg}; border:1px solid {border}; border-radius:8px; "
            f"padding:10px 16px; color:{color}; font-size:13px;"
            f"font-weight:{'700' if state in ('success', 'warning') else '400'};"
        )

    def _apply_action_button_styles(self):
        if hasattr(self, "_btn_run"):
            self._btn_run.setStyleSheet(btn_primary(self._theme_tokens))
            self._btn_run.update()

    def apply_theme_tokens(self, tokens: ThemeTokens) -> None:
        """
        新版主题接口 - 由 PageThemeAdapter / ThemeManager 驱动。
        直接缓存 ThemeTokens，再兼容旧式局部样式刷新逻辑。
        """
        self._theme_tokens = tokens
        self.on_theme_changed(tokens.mode, tokens.to_legacy_dict())

    def on_theme_changed(self, theme: str, theme_vars: dict):
        self._theme_mode = theme
        if getattr(self, "_theme_tokens", None) is None or self._theme_tokens.mode != theme:
            self._theme_tokens = resolve_theme_tokens(theme)
        self._theme_vars = theme_vars or self._theme_tokens.to_legacy_dict()
        self._apply_action_button_styles()
        if hasattr(self, "_result_list"):
            self._result_list.setStyleSheet(self._result_list_style())
        if hasattr(self, "_summary_lbl"):
            self._summary_lbl.setStyleSheet(self._summary_style(self._last_summary_state[1]))

    def _on_run(self):
        if self._worker and self._worker.isRunning():
            return
        if self._worker:
            self._worker.deleteLater()
            self._worker = None
        self._result_list.clear()
        self._last_summary_state = ("诊断运行中...", "warning")
        self._summary_lbl.setText(self._last_summary_state[0])
        self._summary_lbl.setStyleSheet(self._summary_style(self._last_summary_state[1]))
        self._btn_run.setEnabled(False)

        self._worker = _DiagWorker(self._config)
        self._worker.result_ready.connect(self._on_result)
        self._worker.all_done.connect(self._on_all_done)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _on_result(self, name: str, passed: bool, detail: str):
        icon = "PASS" if passed else "FAIL"
        text = f"  [{icon}]  {name}\n         {detail}"
        item = QListWidgetItem(text)
        color = "#3fb950" if passed else "#f85149"
        item.setForeground(QColor(color))
        # 非关键项（scrcpy）用警告色
        if not passed and "可选" in detail:
            item.setForeground(QColor("#e3b341"))
        self._result_list.addItem(item)
        self._result_list.scrollToBottom()

    def _on_all_done(self):
        self._btn_run.setEnabled(True)
        total = self._result_list.count()
        passed = sum(
            1 for i in range(total)
            if self._result_list.item(i).foreground().color().name() == "#3fb950"
        )
        failed = total - passed
        if failed == 0:
            msg = f"全部 {total} 项检查通过"
            color = "#3fb950"
            bg = "#0f2d1a"
            border = "#3fb95040"
        else:
            msg = f"{passed}/{total} 项通过，{failed} 项需要关注"
            color = "#e3b341" if failed <= 2 else "#f85149"
            bg = "#2d2200"
            border = "#e3b34140"
        self._last_summary_state = (msg, "success" if failed == 0 else "warning")
        self._summary_lbl.setText(msg)
        self._summary_lbl.setStyleSheet(self._summary_style(self._last_summary_state[1]))

    def _on_worker_finished(self):
        if self._worker:
            self._worker.deleteLater()
            self._worker = None

    def shutdown(self):
        if self._worker:
            if self._worker.isRunning():
                self._worker.request_stop()
                self._worker.wait(15000)
            if not self._worker.isRunning():
                self._worker.deleteLater()
                self._worker = None

    def on_page_activated(self):
        pass
