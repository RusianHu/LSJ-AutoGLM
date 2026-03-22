# -*- coding: utf-8 -*-
"""设备页 - ADB 检查、连接管理、设备切换"""

import io
import random
import secrets
import socket
import string

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QFont, QImage, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from gui.services.device_service import DeviceStatus


def _btn_style_template(
    theme_mode: str,
    theme_vars: dict | None = None,
    *,
    bg: str,
    hover_bg: str,
    pressed_bg: str,
    border: str,
    hover_border: str,
    pressed_border: str,
    text: str,
    compact: bool = False,
    disabled_bg: str = "",
    disabled_border: str = "",
    disabled_text: str = "",
) -> str:
    is_light = theme_mode == "light"
    v = theme_vars or {}
    radius = 6 if compact else 8
    min_height = 22 if compact else 32
    padding = "0 10px" if compact else "0 14px"
    font_weight = 500 if compact else 600
    disabled_bg = disabled_bg or ("#eef2f7" if is_light else "#161b22")
    disabled_border = disabled_border or ("#d5deea" if is_light else "#21262d")
    disabled_text = disabled_text or v.get("text_muted", "#94a3b8" if is_light else "#484f58")
    return f"""
        QPushButton {{
            background-color:{bg};
            border:1px solid {border};
            border-radius:{radius}px;
            color:{text};
            padding:{padding};
            min-height:{min_height}px;
            font-size:13px;
            font-weight:{font_weight};
        }}
        QPushButton:hover {{
            background-color:{hover_bg};
            border-color:{hover_border};
        }}
        QPushButton:pressed {{
            background-color:{pressed_bg};
            border-color:{pressed_border};
        }}
        QPushButton:disabled {{
            background-color:{disabled_bg};
            border-color:{disabled_border};
            color:{disabled_text};
        }}
    """


def _primary_btn_style(theme_mode: str, theme_vars: dict | None = None, compact: bool = False) -> str:
    v = theme_vars or {}
    if theme_mode == "light":
        return _btn_style_template(
            theme_mode,
            v,
            bg=v.get("accent", "#2563eb"),
            hover_bg="#1d4ed8",
            pressed_bg="#1e40af",
            border=v.get("accent", "#2563eb"),
            hover_border="#1d4ed8",
            pressed_border="#1e40af",
            text="#ffffff",
            compact=compact,
            disabled_bg="#dbe7ff",
            disabled_border="#c7d7fe",
            disabled_text="#8aa1d1",
        )
    return _btn_style_template(
        theme_mode,
        v,
        bg=v.get("accent", "#1f6feb"),
        hover_bg="#388bfd",
        pressed_bg="#1b62d1",
        border=v.get("accent", "#1f6feb"),
        hover_border="#388bfd",
        pressed_border="#1b62d1",
        text="#ffffff",
        compact=compact,
    )


def _danger_btn_style(theme_mode: str, theme_vars: dict | None = None, compact: bool = False) -> str:
    v = theme_vars or {}
    if theme_mode == "light":
        return _btn_style_template(
            theme_mode,
            v,
            bg=v.get("danger_bg", "#fee2e5"),
            hover_bg="#fecdd3",
            pressed_bg="#fda4af",
            border=v.get("danger_border", "#c9525a"),
            hover_border=v.get("danger", "#b91c1c"),
            pressed_border=v.get("danger", "#b91c1c"),
            text=v.get("danger", "#b91c1c"),
            compact=compact,
        )
    return _btn_style_template(
        theme_mode,
        v,
        bg="#21262d",
        hover_bg="#3d1a1a",
        pressed_bg="#4a1d1d",
        border=v.get("danger_border", "#8f2d2b"),
        hover_border=v.get("danger", "#f85149"),
        pressed_border=v.get("danger", "#f85149"),
        text=v.get("danger", "#f85149"),
        compact=compact,
        disabled_border="#21262d",
    )


def _success_btn_style(theme_mode: str, theme_vars: dict | None = None, compact: bool = False) -> str:
    v = theme_vars or {}
    if theme_mode == "light":
        return _btn_style_template(
            theme_mode,
            v,
            bg=v.get("success_bg", "#dcfce7"),
            hover_bg="#bbf7d0",
            pressed_bg="#86efac",
            border=v.get("success_border", "#16a34a"),
            hover_border=v.get("success", "#166534"),
            pressed_border=v.get("success", "#166534"),
            text=v.get("success", "#166534"),
            compact=compact,
        )
    return _btn_style_template(
        theme_mode,
        v,
        bg="#0f2418",
        hover_bg="#12351f",
        pressed_bg="#184828",
        border=v.get("success_border", "#238636"),
        hover_border=v.get("success", "#3fb950"),
        pressed_border=v.get("success", "#3fb950"),
        text=v.get("success", "#3fb950"),
        compact=compact,
        disabled_border="#21262d",
    )


def _subtle_btn_style(theme_mode: str, theme_vars: dict | None = None, compact: bool = False) -> str:
    v = theme_vars or {}
    if theme_mode == "light":
        return _btn_style_template(
            theme_mode,
            v,
            bg=v.get("bg_elevated", "#edf2f7"),
            hover_bg="#e2e8f0",
            pressed_bg="#d9e2ec",
            border=v.get("border", "#d5deea"),
            hover_border=v.get("accent", "#2563eb"),
            pressed_border=v.get("accent", "#2563eb"),
            text=v.get("text_primary", "#1f2937"),
            compact=compact,
            disabled_bg="#f8fafc",
            disabled_border="#e2e8f0",
            disabled_text="#94a3b8",
        )
    return _btn_style_template(
        theme_mode,
        v,
        bg=v.get("bg_btn", "#161b22"),
        hover_bg=v.get("bg_elevated", "#1b2432"),
        pressed_bg="#0f1724",
        border=v.get("border", "#30363d"),
        hover_border=v.get("accent", "#4f8cff"),
        pressed_border=v.get("accent", "#4f8cff"),
        text=v.get("text_primary", "#c9d1d9"),
        compact=compact,
        disabled_bg="#161b22",
        disabled_border="#21262d",
        disabled_text="#484f58",
    )


# ---------------------------------------------------------------------------
# 二维码扫描配对对话框（PC 生成二维码 → 手机扫描）
# ---------------------------------------------------------------------------

class _PairWatcher(QThread):
    """
    后台线程：每隔 2 秒执行 adb devices，检测新设备出现。
    当检测到比初始列表多出新设备时，发出 device_found 信号。
    """
    device_found = Signal(str)   # 新设备 device_id
    timed_out = Signal()

    def __init__(self, known_ids: set, timeout_sec: int = 90, parent=None):
        super().__init__(parent)
        self._known_ids = known_ids
        self._timeout_sec = timeout_sec
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        import subprocess, time
        elapsed = 0
        interval = 2
        while not self._stop and elapsed < self._timeout_sec:
            time.sleep(interval)
            elapsed += interval
            try:
                r = subprocess.run(
                    ["adb", "devices"],
                    capture_output=True, text=True, timeout=5
                )
                for line in r.stdout.splitlines()[1:]:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split()
                    if len(parts) >= 2 and parts[1] == "device":
                        dev_id = parts[0]
                        if dev_id not in self._known_ids:
                            self.device_found.emit(dev_id)
                            return
            except Exception:
                pass
        if not self._stop:
            self.timed_out.emit()


class QrCodeScanDialog(QDialog):
    """
    PC 端生成 ADB 无线调试配对二维码，手机扫描后完成配对。

    二维码内容格式（Android 官方规范）：
        WIFI:T:ADB;S:<service_name>;P:<password>;;

    手机操作步骤：
      1. 手机「设置」→「开发者选项」→「无线调试」→「使用二维码配对设备」
      2. 用手机摄像头扫描本对话框中的二维码
      3. 手机自动完成配对，PC 端会检测到新设备
    """

    _DARK_STYLE = """
        QDialog { background:#0d1117; color:#c9d1d9; }
        QLabel  { color:#c9d1d9; }
        QPushButton {
            background-color:#21262d; border:1px solid #30363d;
            border-radius:6px; color:#c9d1d9;
            padding:6px 16px; font-size:13px;
        }
        QPushButton:hover { background-color:#30363d; }
        QFrame#card {
            background:#161b22; border:1px solid #30363d; border-radius:8px;
        }
    """
    _LIGHT_STYLE = """
        QDialog { background:#f4f7fb; color:#18212f; }
        QLabel  { color:#18212f; }
        QPushButton {
            background-color:#eef2f7; border:1px solid #d5deea;
            border-radius:6px; color:#18212f;
            padding:6px 16px; font-size:13px;
        }
        QPushButton:hover { background-color:#eef3f9; border-color:#a9b6c7; }
        QFrame#card {
            background:#ffffff; border:1px solid #d5deea; border-radius:8px;
        }
    """

    def __init__(self, known_device_ids: set, parent=None, theme: str = "dark"):
        super().__init__(parent)
        self._known_ids = known_device_ids
        self._watcher: _PairWatcher | None = None
        self._service_name = self._rand_name()
        self._password = self._rand_password()
        self._theme_mode = theme
        self.setWindowTitle("二维码配对设备")
        self.setMinimumWidth(420)
        self.setStyleSheet(self._LIGHT_STYLE if theme == "light" else self._DARK_STYLE)
        self._build_ui()
        self._generate_qr()
        self._start_watcher()

    # ------------------------------------------------------------------
    # 随机凭据生成
    # ------------------------------------------------------------------
    @staticmethod
    def _rand_name(length: int = 8) -> str:
        alphabet = string.ascii_lowercase + string.digits
        return "adb-" + "".join(secrets.choice(alphabet) for _ in range(length))

    @staticmethod
    def _rand_password(length: int = 6) -> str:
        return "".join(str(secrets.randbelow(10)) for _ in range(length))

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        title_color = "#18212f" if self._theme_mode == "light" else "#c9d1d9"
        muted_color = "#526273" if self._theme_mode == "light" else "#8b949e"
        countdown_color = "#7b8aa0" if self._theme_mode == "light" else "#484f58"

        title = QLabel("使用手机扫描下方二维码配对")
        title.setStyleSheet(f"font-size:15px; font-weight:bold; color:{title_color};")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # 步骤说明
        steps_frame = QFrame()
        steps_frame.setObjectName("card")
        sf_layout = QVBoxLayout(steps_frame)
        sf_layout.setContentsMargins(12, 10, 12, 10)
        sf_layout.setSpacing(3)
        for step in [
            "1. 手机进入「设置」→「开发者选项」→「无线调试」",
            "2. 点击「使用二维码配对设备」，打开摄像头扫描框",
            "3. 用手机扫描下方二维码，等待配对完成",
        ]:
            lbl = QLabel(step)
            lbl.setStyleSheet(f"color:{muted_color}; font-size:12px;")
            sf_layout.addWidget(lbl)
        layout.addWidget(steps_frame)

        # 二维码显示区
        self._qr_label = QLabel()
        self._qr_label.setAlignment(Qt.AlignCenter)
        self._qr_label.setFixedSize(260, 260)
        self._qr_label.setStyleSheet(
            "background:#ffffff; border-radius:8px; padding:8px;"
        )
        qr_wrapper = QHBoxLayout()
        qr_wrapper.addStretch()
        qr_wrapper.addWidget(self._qr_label)
        qr_wrapper.addStretch()
        layout.addLayout(qr_wrapper)

        # 状态标签
        self._status_lbl = QLabel("等待手机扫描...")
        self._status_lbl.setAlignment(Qt.AlignCenter)
        self._status_lbl.setStyleSheet(f"color:{muted_color}; font-size:12px;")
        self._status_lbl.setWordWrap(True)
        layout.addWidget(self._status_lbl)

        # 倒计时标签
        self._countdown_lbl = QLabel("")
        self._countdown_lbl.setAlignment(Qt.AlignCenter)
        self._countdown_lbl.setStyleSheet(f"color:{countdown_color}; font-size:11px;")
        layout.addWidget(self._countdown_lbl)

        # 关闭按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._close_btn = QPushButton("关闭")
        self._close_btn.setStyleSheet(_subtle_btn_style(self._theme_mode))
        self._close_btn.clicked.connect(self._on_close)
        btn_row.addWidget(self._close_btn)
        layout.addLayout(btn_row)

        # 倒计时 timer
        self._remaining = 90
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(1000)

    # ------------------------------------------------------------------
    # 二维码生成
    # ------------------------------------------------------------------
    def _generate_qr(self):
        try:
            import qrcode
            qr_data = (
                f"WIFI:T:ADB;S:{self._service_name};"
                f"P:{self._password};;"
            )
            qr = qrcode.QRCode(
                version=None,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=8,
                border=2,
            )
            qr.add_data(qr_data)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)
            qimage = QImage.fromData(buf.read())
            pixmap = QPixmap.fromImage(qimage).scaled(
                244, 244,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._qr_label.setPixmap(pixmap)
        except Exception as e:
            error_bg = "#ffffff" if self._theme_mode == "light" else "#161b22"
            error_color = "#b91c1c" if self._theme_mode == "light" else "#f85149"
            self._qr_label.setText(f"二维码生成失败:\n{e}")
            self._qr_label.setStyleSheet(
                f"background:{error_bg}; color:{error_color}; font-size:11px;"
                "border-radius:8px; padding:8px;"
            )

    # ------------------------------------------------------------------
    # 后台监听新设备
    # ------------------------------------------------------------------
    def _start_watcher(self):
        self._watcher = _PairWatcher(set(self._known_ids), timeout_sec=90, parent=None)
        self._watcher.device_found.connect(self._on_device_found)
        self._watcher.timed_out.connect(self._on_timed_out)
        self._watcher.start()

    def _on_device_found(self, device_id: str):
        self._timer.stop()
        self._status_lbl.setText(
            f"<span style='color:#3fb950'>配对成功！检测到新设备: {device_id}</span>"
        )
        self._countdown_lbl.setText("")
        self._close_btn.setText("完成")
        # 记录成功的设备 ID 供外部读取
        self._paired_device_id = device_id

    def _on_timed_out(self):
        self._timer.stop()
        self._status_lbl.setText(
            "<span style='color:#e3b341'>等待超时，请重试。"
            "确认手机与电脑在同一局域网，且无线调试已开启。</span>"
        )
        self._countdown_lbl.setText("")

    def _on_tick(self):
        self._remaining -= 1
        if self._remaining <= 0:
            self._timer.stop()
        else:
            self._countdown_lbl.setText(f"二维码有效期剩余 {self._remaining} 秒")

    def _on_close(self):
        self._cleanup()
        self.accept()

    def _cleanup(self):
        self._timer.stop()
        if self._watcher:
            self._watcher.stop()
            self._watcher.wait(2000)
            self._watcher = None

    def closeEvent(self, event):
        self._cleanup()
        super().closeEvent(event)

    @property
    def paired_device_id(self) -> str:
        return getattr(self, "_paired_device_id", "")

    @property
    def qr_data(self) -> str:
        return (
            f"WIFI:T:ADB;S:{self._service_name};"
            f"P:{self._password};;"
        )


# ---------------------------------------------------------------------------
# 二维码配对对话框（配对码手动输入方式，保留）
# ---------------------------------------------------------------------------

class QrPairDialog(QDialog):
    """
    Android 11+ 无线调试二维码配对对话框。

    使用步骤（手机端）：
      1. 手机 设置 -> 开发者选项 -> 无线调试 -> 使用二维码配对设备
      2. 手机屏幕会显示一个二维码，同时弹出配对码和配对端口
      3. 在本对话框填写「配对端口」（形如 192.168.x.x:3xxxx）和「配对码」（6位数字）
      4. 点击「配对」按钮，等待配对成功
      5. 配对成功后，再用 TCP/IP 连接区的「连接」按钮连接常规端口（通常显示在无线调试页）
    """

    _DARK_STYLE = """
        QDialog {
            background: #0d1117;
            color: #c9d1d9;
        }
        QLabel {
            color: #c9d1d9;
        }
        QLineEdit {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 6px;
            color: #c9d1d9;
            padding: 6px 10px;
            font-size: 13px;
        }
        QLineEdit:focus {
            border-color: #1f6feb;
        }
        QPushButton {
            background-color: #21262d;
            border: 1px solid #30363d;
            border-radius: 6px;
            color: #c9d1d9;
            padding: 6px 16px;
            font-size: 13px;
        }
        QPushButton:hover {
            background-color: #30363d;
        }
        QFrame#divider {
            background: #21262d;
        }
    """
    _LIGHT_STYLE = """
        QDialog {
            background: #f4f7fb;
            color: #18212f;
        }
        QLabel {
            color: #18212f;
        }
        QLineEdit {
            background: #ffffff;
            border: 1px solid #d5deea;
            border-radius: 6px;
            color: #18212f;
            padding: 6px 10px;
            font-size: 13px;
        }
        QLineEdit:focus {
            border-color: #2563eb;
        }
        QPushButton {
            background-color: #eef2f7;
            border: 1px solid #d5deea;
            border-radius: 6px;
            color: #18212f;
            padding: 6px 16px;
            font-size: 13px;
        }
        QPushButton:hover {
            background-color: #eef3f9;
            border-color: #a9b6c7;
        }
        QFrame#divider {
            background: #d5deea;
        }
    """

    def __init__(self, parent=None, theme: str = "dark"):
        super().__init__(parent)
        self._theme_mode = theme
        self.setWindowTitle("使用二维码配对设备")
        self.setMinimumWidth(460)
        self.setStyleSheet(self._LIGHT_STYLE if theme == "light" else self._DARK_STYLE)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        title_color = "#18212f" if self._theme_mode == "light" else "#c9d1d9"
        muted_color = "#526273" if self._theme_mode == "light" else "#8b949e"
        card_bg = "#ffffff" if self._theme_mode == "light" else "#161b22"
        card_border = "#d5deea" if self._theme_mode == "light" else "#30363d"

        # 标题
        title = QLabel("二维码配对 (Android 11+)")
        title.setStyleSheet(f"font-size:16px; font-weight:bold; color:{title_color};")
        layout.addWidget(title)

        # 操作说明卡片
        steps_frame = QFrame()
        steps_frame.setStyleSheet(f"""
            QFrame {{
                background: {card_bg};
                border: 1px solid {card_border};
                border-radius: 8px;
            }}
            QLabel {{ color: {muted_color}; font-size: 12px; }}
        """)
        steps_layout = QVBoxLayout(steps_frame)
        steps_layout.setContentsMargins(14, 12, 14, 12)
        steps_layout.setSpacing(4)

        steps_title = QLabel("手机操作步骤：")
        steps_title.setStyleSheet(f"color:{title_color}; font-size:13px; font-weight:bold;")
        steps_layout.addWidget(steps_title)

        steps_text = [
            "1. 手机进入 「设置」→「开发者选项」→「无线调试」",
            "2. 点击「使用二维码配对设备」，手机将显示二维码",
            "3. 同时记录弹窗中的「配对端口」（5位数字端口号）",
            "4. 以及「配对码」（通常为 6 位数字）",
            "5. 将上述信息填入下方表单，点击「开始配对」",
            "6. 配对成功后，返回无线调试页面复制连接端口，",
            "   再使用上方 TCP/IP 连接区完成最终连接",
        ]
        for step in steps_text:
            lbl = QLabel(step)
            lbl.setStyleSheet(f"color:{muted_color}; font-size:12px;")
            lbl.setWordWrap(True)
            steps_layout.addWidget(lbl)

        layout.addWidget(steps_frame)

        # 分割线
        divider = QFrame()
        divider.setObjectName("divider")
        divider.setFixedHeight(1)
        layout.addWidget(divider)

        # 输入区
        form_layout = QVBoxLayout()
        form_layout.setSpacing(10)

        # 配对地址
        addr_row = QHBoxLayout()
        addr_lbl = QLabel("配对地址:")
        addr_lbl.setFixedWidth(70)
        self._pair_addr_input = QLineEdit()
        self._pair_addr_input.setPlaceholderText("例如: 192.168.6.155:37890")
        self._pair_addr_input.setToolTip(
            "IP 地址 + 配对端口（注意：与 TCP/IP 连接端口不同）"
        )
        addr_row.addWidget(addr_lbl)
        addr_row.addWidget(self._pair_addr_input)
        form_layout.addLayout(addr_row)

        # 配对码
        code_row = QHBoxLayout()
        code_lbl = QLabel("配对码:")
        code_lbl.setFixedWidth(70)
        self._pair_code_input = QLineEdit()
        self._pair_code_input.setPlaceholderText("例如: 123456")
        self._pair_code_input.setMaxLength(12)
        self._pair_code_input.setToolTip("手机无线调试弹窗中显示的数字配对码")
        code_row.addWidget(code_lbl)
        code_row.addWidget(self._pair_code_input)
        form_layout.addLayout(code_row)

        layout.addLayout(form_layout)

        # 状态标签
        self._status_lbl = QLabel("")
        self._status_lbl.setWordWrap(True)
        self._status_lbl.setStyleSheet(f"font-size:12px; color:{muted_color};")
        layout.addWidget(self._status_lbl)

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._cancel_btn = QPushButton("取消")
        self._cancel_btn.setStyleSheet(_subtle_btn_style(self._theme_mode))
        self._cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self._cancel_btn)

        self._pair_btn = QPushButton("开始配对")
        self._pair_btn.setStyleSheet(_primary_btn_style(self._theme_mode))
        self._pair_btn.setDefault(True)
        self._pair_btn.clicked.connect(self._on_pair)
        btn_row.addWidget(self._pair_btn)

        layout.addLayout(btn_row)

    def _on_pair(self):
        """触发配对，由 DevicePage 负责实际调用 service"""
        # 仅做基础校验，accept() 后由外部读取值执行
        addr = self._pair_addr_input.text().strip()
        code = self._pair_code_input.text().strip()
        if not addr:
            self._set_status("请填写配对地址（IP:端口）", error=True)
            return
        if ":" not in addr:
            self._set_status("配对地址格式错误，需包含端口，例如 192.168.6.155:37890", error=True)
            return
        if not code:
            self._set_status("请填写配对码", error=True)
            return
        self.accept()

    def _set_status(self, msg: str, error: bool = False):
        color = "#f85149" if error else "#3fb950"
        self._status_lbl.setText(f"<span style='color:{color}'>{msg}</span>")

    @property
    def pair_address(self) -> str:
        return self._pair_addr_input.text().strip()

    @property
    def pair_code(self) -> str:
        return self._pair_code_input.text().strip()


class DevicePage(QWidget):
    """设备页"""

    def __init__(self, services: dict, parent=None):
        super().__init__(parent)
        self._services = services
        self._device = services.get("device")
        self._theme_mode = "dark"
        self._theme_vars = {}
        self._build_ui()
        self._apply_action_button_styles()
        self._update_action_button_states()
        self._connect_signals()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)

        # 标题
        title = QLabel("设备管理")
        title.setProperty("role", "pageTitle")
        root.addWidget(title)

        # ADB 状态区
        adb_group = QGroupBox("ADB 状态")
        adb_layout = QVBoxLayout(adb_group)
        adb_layout.setSpacing(8)

        self._adb_status_lbl = QLabel("ADB 状态: 检查中...")
        self._adb_status_lbl.setProperty("role", "muted")
        self._adb_status_lbl.setStyleSheet("font-size:13px;")
        adb_layout.addWidget(self._adb_status_lbl)

        self._btn_check_adb = QPushButton("重新检查 ADB")
        self._btn_check_adb.setFixedWidth(150)
        self._btn_check_adb.setProperty("variant", "subtle")
        self._btn_check_adb.clicked.connect(self._on_check_adb)
        adb_layout.addWidget(self._btn_check_adb)
        root.addWidget(adb_group)

        # 设备列表区
        devices_group = QGroupBox("已连接设备")
        devices_layout = QVBoxLayout(devices_group)
        devices_layout.setSpacing(8)

        self._device_list = QListWidget()
        self._device_list.setProperty("surface", "console")
        self._device_list.setFixedHeight(180)
        self._device_list.currentRowChanged.connect(self._on_device_selected)
        devices_layout.addWidget(self._device_list)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._btn_select = QPushButton("选为当前设备")
        self._btn_select.setProperty("variant", "primary")
        self._btn_select.clicked.connect(self._on_set_active)
        btn_row.addWidget(self._btn_select)

        self._btn_disconnect = QPushButton("断开连接")
        self._btn_disconnect.setProperty("variant", "danger")
        self._btn_disconnect.clicked.connect(self._on_disconnect)
        btn_row.addWidget(self._btn_disconnect)

        self._btn_refresh = QPushButton("刷新")
        self._btn_refresh.setProperty("variant", "subtle")
        self._btn_refresh.clicked.connect(self._on_refresh)
        btn_row.addWidget(self._btn_refresh)
        btn_row.addStretch()
        devices_layout.addLayout(btn_row)
        root.addWidget(devices_group)

        # 无线连接区
        wifi_group = QGroupBox("无线连接（TCP/IP）")
        wifi_outer = QVBoxLayout(wifi_group)
        wifi_outer.setSpacing(10)

        # 第一行：IP 地址连接
        wifi_row = QHBoxLayout()
        wifi_row.setSpacing(8)
        wifi_row.addWidget(QLabel("设备地址:"))
        self._wifi_input = QLineEdit()
        self._wifi_input.setPlaceholderText("192.168.x.x:5555")
        self._wifi_input.setFixedWidth(200)
        self._wifi_input.textChanged.connect(self._update_action_button_states)
        wifi_row.addWidget(self._wifi_input)

        self._btn_wifi_connect = QPushButton("连接")
        self._btn_wifi_connect.setProperty("variant", "primary")
        self._btn_wifi_connect.clicked.connect(self._on_wifi_connect)
        wifi_row.addWidget(self._btn_wifi_connect)
        wifi_row.addStretch()
        wifi_outer.addLayout(wifi_row)

        # 第二行：Android 11+ 双模式配对
        qr_row = QHBoxLayout()
        qr_row.setSpacing(8)
        qr_hint = QLabel("Android 11+ 无线配对:")
        qr_hint.setProperty("role", "muted")
        qr_hint.setStyleSheet("font-size:12px;")
        qr_row.addWidget(qr_hint)

        # 生成二维码供手机扫描（真正的二维码配对）
        self._btn_qr_scan = QPushButton("生成配对二维码")
        self._btn_qr_scan.setToolTip(
            "PC 生成二维码，手机「无线调试」→「使用二维码配对」扫描（需 Android 11+）"
        )
        self._btn_qr_scan.setProperty("variant", "success")
        self._btn_qr_scan.clicked.connect(self._on_qr_scan_pair)
        qr_row.addWidget(self._btn_qr_scan)

        # 手动输入配对码（备用方式）
        self._btn_qr_pair = QPushButton("配对码配对")
        self._btn_qr_pair.setToolTip(
            "手动输入手机显示的配对地址和配对码（备用方式）"
        )
        self._btn_qr_pair.setProperty("variant", "subtle")
        self._btn_qr_pair.clicked.connect(self._on_qr_pair)
        qr_row.addWidget(self._btn_qr_pair)

        qr_row.addStretch()
        wifi_outer.addLayout(qr_row)

        root.addWidget(wifi_group)

        # 详情/日志区
        detail_group = QGroupBox("操作日志")
        detail_layout = QVBoxLayout(detail_group)
        self._detail_log = QPlainTextEdit()
        self._detail_log.setReadOnly(True)
        self._detail_log.setFixedHeight(120)
        self._detail_log.setProperty("surface", "console")
        detail_layout.addWidget(self._detail_log)
        root.addWidget(detail_group)

        # ADB Keyboard 检查
        kbd_group = QGroupBox("ADB Keyboard")
        kbd_layout = QHBoxLayout(kbd_group)
        self._kbd_status_lbl = QLabel("—")
        self._kbd_status_lbl.setProperty("role", "muted")
        kbd_layout.addWidget(self._kbd_status_lbl)
        self._btn_check_kbd = QPushButton("检查当前设备")
        self._btn_check_kbd.setProperty("variant", "subtle")
        self._btn_check_kbd.clicked.connect(self._on_check_kbd)
        kbd_layout.addWidget(self._btn_check_kbd)
        kbd_layout.addStretch()
        root.addWidget(kbd_group)

        # scrcpy 状态
        scrcpy_group = QGroupBox("scrcpy 依赖")
        scrcpy_layout = QHBoxLayout(scrcpy_group)
        self._scrcpy_status_lbl = QLabel("—")
        self._scrcpy_status_lbl.setProperty("role", "muted")
        scrcpy_layout.addWidget(self._scrcpy_status_lbl)
        self._btn_check_scrcpy = QPushButton("检查")
        self._btn_check_scrcpy.setProperty("variant", "subtle")
        self._btn_check_scrcpy.clicked.connect(self._on_check_scrcpy)
        scrcpy_layout.addWidget(self._btn_check_scrcpy)
        scrcpy_layout.addStretch()
        root.addWidget(scrcpy_group)

        root.addStretch(1)

    def _device_list_style(self) -> str:
        v = self._theme_vars or {}
        return (
            "QListWidget {"
            f"background:{v.get('bg_console', '#0a0f18')}; border:1px solid {v.get('border', '#30363d')};"
            f"border-radius:8px; color:{v.get('text_primary', '#c9d1d9')}; font-size:13px; padding:4px;"
            "}"
            "QListWidget::item { padding:8px 12px; border-radius:6px; }"
            f"QListWidget::item:selected {{ background:{v.get('selection_bg', '#264f78')}; }}"
            f"QListWidget::item:hover {{ background:{v.get('accent_soft', 'rgba(79, 140, 255, 0.16)')}; }}"
        )

    def _detail_log_style(self) -> str:
        v = self._theme_vars or {}
        return (
            "QPlainTextEdit {"
            f"background:{v.get('bg_console', '#0a0f18')}; border:1px solid {v.get('border', '#30363d')};"
            f"border-radius:8px; color:{v.get('text_secondary', '#8b949e')}; font-size:12px; padding:6px;"
            "font-family:'Consolas',monospace;"
            "}"
        )

    def _apply_action_button_styles(self):
        btn_styles = (
            (getattr(self, "_btn_check_adb", None), _subtle_btn_style(self._theme_mode, self._theme_vars)),
            (getattr(self, "_btn_select", None), _primary_btn_style(self._theme_mode, self._theme_vars)),
            (getattr(self, "_btn_disconnect", None), _danger_btn_style(self._theme_mode, self._theme_vars)),
            (getattr(self, "_btn_refresh", None), _subtle_btn_style(self._theme_mode, self._theme_vars)),
            (getattr(self, "_btn_wifi_connect", None), _primary_btn_style(self._theme_mode, self._theme_vars)),
            (getattr(self, "_btn_qr_scan", None), _success_btn_style(self._theme_mode, self._theme_vars)),
            (getattr(self, "_btn_qr_pair", None), _subtle_btn_style(self._theme_mode, self._theme_vars)),
            (getattr(self, "_btn_check_kbd", None), _subtle_btn_style(self._theme_mode, self._theme_vars)),
            (getattr(self, "_btn_check_scrcpy", None), _subtle_btn_style(self._theme_mode, self._theme_vars)),
        )
        for btn, style in btn_styles:
            if btn:
                btn.setStyleSheet(style)
                btn.update()

    def _update_action_button_states(self):
        selected_item = self._device_list.currentItem() if hasattr(self, "_device_list") else None
        selected_device_id = selected_item.data(Qt.UserRole) if selected_item else ""
        active_device_id = ""
        if self._device and self._device.selected_device:
            active_device_id = self._device.selected_device.device_id or ""

        if hasattr(self, "_btn_select"):
            self._btn_select.setEnabled(bool(selected_device_id) and selected_device_id != active_device_id)
        if hasattr(self, "_btn_disconnect"):
            self._btn_disconnect.setEnabled(bool(selected_device_id))
        if hasattr(self, "_btn_wifi_connect"):
            self._btn_wifi_connect.setEnabled(bool(self._wifi_input.text().strip()))
        if hasattr(self, "_btn_check_kbd"):
            self._btn_check_kbd.setEnabled(bool(active_device_id))

    def on_theme_changed(self, theme: str, theme_vars: dict):
        self._theme_mode = theme
        self._theme_vars = theme_vars or {}

        self._apply_action_button_styles()

        if hasattr(self, '_device_list'):
            self._device_list.setStyleSheet(self._device_list_style())
        if hasattr(self, '_detail_log'):
            self._detail_log.setStyleSheet(self._detail_log_style())

    def _connect_signals(self):
        if self._device:
            self._device.devices_changed.connect(self._refresh_device_list)
            self._device.device_selected.connect(lambda *_: self._update_action_button_states())
            self._device.adb_status_changed.connect(self._on_adb_status)
            self._device.error_occurred.connect(self._on_device_error)
            # 初始刷新
            self._refresh_device_list(self._device.devices)
            self._update_action_button_states()

    # ---------- 回调 ----------

    def _on_check_adb(self):
        if self._device:
            ok, msg = self._device.check_adb()
            self._log(f"ADB 检查: {'通过' if ok else '失败'} - {msg}")

    def _on_adb_status(self, available: bool, msg: str):
        color = "#3fb950" if available else "#f85149"
        status = "可用" if available else "不可用"
        self._adb_status_lbl.setText(
            f"ADB 状态: <span style='color:{color}'>{status}</span>  {msg}"
        )

    def _on_device_error(self, msg: str):
        self._log(f"设备服务: {msg}")

    def _refresh_device_list(self, devices):
        self._device_list.clear()
        if not devices:
            self._device_list.addItem("  （未找到设备）")
            self._update_action_button_states()
            return
        for d in devices:
            color = "#3fb950" if d.status == DeviceStatus.CONNECTED else "#e3b341"
            text = f"[{d.status.value.upper()}]  {d.display_name}"
            item = QListWidgetItem(text)
            from PySide6.QtGui import QColor
            item.setForeground(QColor(color))
            item.setData(Qt.UserRole, d.device_id)
            self._device_list.addItem(item)
        self._update_action_button_states()

    def _on_device_selected(self, row):
        self._update_action_button_states()

    def _on_set_active(self):
        item = self._device_list.currentItem()
        if not item:
            return
        device_id = item.data(Qt.UserRole)
        if device_id and self._device:
            self._device.select_device(device_id)
            self._log(f"已选择设备: {device_id}")
            self._update_action_button_states()

    def _on_disconnect(self):
        item = self._device_list.currentItem()
        if not item:
            self._log("断开操作未执行：当前没有选中设备，请先点击设备列表中的目标设备")
            return

        device_id = item.data(Qt.UserRole)
        row = self._device_list.currentRow()
        self._log(
            f"断开操作触发: row={row}, text={item.text()}, device_id={device_id or 'None'}"
        )

        if not device_id:
            self._log("断开操作未执行：当前条目没有可用的 device_id")
            return

        if isinstance(device_id, str) and "_adb-tls-connect._tcp" in device_id:
            self._log(
                "诊断提示：当前 device_id 看起来是 ADB TLS/mDNS 服务名，"
                "adb disconnect 对这类标识的支持可能不稳定"
            )

        if self._device:
            ok, msg = self._device.disconnect_device(device_id)
            self._log(f"断开 {device_id}: {'成功' if ok else '失败'} - {msg}")

    def _on_refresh(self):
        if self._device:
            self._device.refresh()
            self._log("设备列表已刷新")

    def _on_wifi_connect(self):
        addr = self._wifi_input.text().strip()
        if not addr:
            return
        if self._device:
            ok, msg = self._device.connect_device(addr)
            self._log(f"连接 {addr}: {'成功' if ok else '失败'} - {msg}")

    def _on_qr_scan_pair(self):
        """
        打开「生成配对二维码」对话框。
        PC 端生成标准 ADB 配对二维码（WIFI:T:ADB;S:...;P:...;;），
        手机「无线调试」→「使用二维码配对设备」扫描后自动配对。
        配对成功后刷新设备列表并将新设备 IP 填入连接框。
        """
        # 获取当前已知设备 ID 集合，用于检测新增设备
        known_ids: set = set()
        if self._device:
            known_ids = {d.device_id for d in self._device.devices}

        self._log("正在生成配对二维码，请用手机扫描...")
        dlg = QrCodeScanDialog(known_ids, parent=self, theme=self._theme_mode)
        dlg.exec()

        paired_id = dlg.paired_device_id
        if paired_id:
            self._log(f"二维码配对成功，新设备: {paired_id}")
            if self._device:
                self._device.refresh()
                # 若为 WiFi 设备（含 :），提取 IP 填入连接框
                if ":" in paired_id:
                    ip = paired_id.split(":")[0]
                    self._wifi_input.setText(paired_id)
                    self._log(f"已自动填写连接地址: {paired_id}")
        else:
            self._log("二维码配对对话框已关闭（未检测到新设备）")

    def _on_qr_pair(self):
        """打开配对码手动输入对话框，执行 adb pair（备用方式）"""
        dlg = QrPairDialog(self, theme=self._theme_mode)
        if dlg.exec() != QrPairDialog.DialogCode.Accepted:
            return
        addr = dlg.pair_address
        code = dlg.pair_code
        self._log(f"正在配对 {addr} ...")
        if self._device:
            ok, msg = self._device.pair_device(addr, code)
            if ok:
                self._log(f"配对成功: {msg}")
                # 配对成功后，把 IP 部分填入连接输入框方便后续连接
                ip = addr.split(":")[0]
                self._wifi_input.setText(ip)
                self._log(f"提示: 请在手机「无线调试」页面查看连接端口，填写 {ip}:<连接端口> 后点击「连接」")
            else:
                self._log(f"配对失败: {msg}")
        else:
            self._log("设备服务不可用")

    def _on_check_kbd(self):
        device_id = ""
        if self._device and self._device.selected_device:
            device_id = self._device.selected_device.device_id
        if not device_id:
            self._kbd_status_lbl.setText("请先选择设备")
            return
        if self._device:
            ok, msg = self._device.check_adb_keyboard(device_id)
            color = "#3fb950" if ok else "#f85149"
            self._kbd_status_lbl.setText(
                f"<span style='color:{color}'>{msg}</span>"
            )
            self._log(f"ADB Keyboard 检查: {msg}")

    def _on_check_scrcpy(self):
        mirror = self._services.get("mirror")
        if mirror:
            ok, msg = mirror.check_available()
        elif self._device:
            ok, msg = self._device.check_scrcpy()
        else:
            ok, msg = False, "服务不可用"
        color = "#3fb950" if ok else "#e3b341"
        self._scrcpy_status_lbl.setText(
            f"<span style='color:{color}'>{msg}</span>"
        )
        self._log(f"scrcpy 检查: {msg}")

    def _log(self, msg: str):
        from PySide6.QtCore import QDateTime
        ts = QDateTime.currentDateTime().toString("hh:mm:ss")
        self._detail_log.appendPlainText(f"[{ts}] {msg}")

    def on_page_activated(self):
        if self._device:
            self._device.refresh()
