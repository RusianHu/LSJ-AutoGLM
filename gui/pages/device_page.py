# -*- coding: utf-8 -*-
"""设备页 - ADB 检查、连接管理、设备切换"""

import html
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
from gui.theme.tokens import ThemeTokens
from gui.theme.themes import resolve_theme_tokens
from gui.theme.contracts import ThemeAwareDialog
from gui.theme.styles.buttons import (
    btn_primary,
    btn_subtle,
    btn_danger,
    btn_success,
)
from gui.theme.styles.dialogs import dialog_surface
from gui.theme.styles.lists import list_default
from gui.theme.styles.logs import log_console


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


class QrCodeScanDialog(ThemeAwareDialog):
    """
    PC 端生成 ADB 无线调试配对二维码，手机扫描后完成配对。

    二维码内容格式（Android 官方规范）：
        WIFI:T:ADB;S:<service_name>;P:<password>;;

    手机操作步骤：
      1. 手机「设置」→「开发者选项」→「无线调试」→「使用二维码配对设备」
      2. 用手机摄像头扫描本对话框中的二维码
      3. 手机自动完成配对，PC 端会检测到新设备
    """

    def __init__(
        self,
        known_device_ids: set,
        parent=None,
        theme: str = "dark",
        theme_manager=None,
        translator=None,
    ):
        super().__init__(parent)
        self._known_ids = known_device_ids
        self._watcher: _PairWatcher | None = None
        self._service_name = self._rand_name()
        self._password = self._rand_password()
        self._theme_mode = theme
        self._translator = translator
        self._status_text = self._t("page.device.qr_scan.waiting")
        self._status_level = "muted"
        self._qr_error_text = ""
        self._tokens = resolve_theme_tokens(self._theme_mode)
        self.setWindowTitle(self._t("page.device.qr_scan.window_title"))
        self.setMinimumWidth(420)
        self._build_ui()
        self._generate_qr()
        self._start_watcher()
        if theme_manager is not None:
            self.bind_theme_manager(theme_manager)
        else:
            # 初始应用主题
            self.apply_theme_tokens(self._tokens)

    def _t(self, key: str, **params) -> str:
        translator = self._translator
        if callable(translator):
            try:
                return translator(key, **params)
            except Exception:
                pass
        from gui.i18n.locales.cn import CN
        template = CN.get(key, f"[[{key}]]")
        try:
            return template.format(**params) if params else template
        except Exception:
            return template

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
    # ThemeAware 协议
    # ------------------------------------------------------------------

    def refresh_theme_surfaces(self) -> None:
        """刷新对话框背景和基础样式。"""
        if self._tokens is None:
            return
        t = self._tokens
        self.setStyleSheet(dialog_surface(t))
        muted = t.text_secondary
        countdown = t.text_muted
        title_color = t.text_primary
        card_style = (
            f"background:{t.bg_elevated}; border:1px solid {t.border}; border-radius:8px;"
        )
        qr_style = "background:#ffffff; border-radius:8px; padding:8px;"
        if self._qr_error_text:
            qr_style = (
                f"background:{t.bg_elevated}; color:{t.danger}; "
                "border-radius:8px; padding:8px; font-size:11px;"
            )
        if hasattr(self, "_title_lbl"):
            self._title_lbl.setStyleSheet(
                f"font-size:15px; font-weight:bold; color:{title_color};"
            )
        if hasattr(self, "_steps_frame"):
            self._steps_frame.setStyleSheet(card_style)
        for lbl in getattr(self, "_step_labels", []):
            lbl.setStyleSheet(f"color:{muted}; font-size:12px;")
        if hasattr(self, "_qr_label"):
            self._qr_label.setStyleSheet(qr_style)
            if self._qr_error_text:
                self._qr_label.setText(self._qr_error_text)
        if hasattr(self, "_countdown_lbl"):
            self._countdown_lbl.setStyleSheet(f"color:{countdown}; font-size:11px;")
        self._render_status()

    def refresh_theme_states(self) -> None:
        """刷新按钮等动态状态。"""
        if self._tokens is None:
            return
        if hasattr(self, "_close_btn"):
            self._close_btn.setStyleSheet(btn_subtle(self._tokens))

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        self._title_lbl = QLabel(self._t("page.device.qr_scan.title"))
        self._title_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._title_lbl)

        # 步骤说明
        self._steps_frame = QFrame()
        self._steps_frame.setObjectName("card")
        sf_layout = QVBoxLayout(self._steps_frame)
        sf_layout.setContentsMargins(12, 10, 12, 10)
        sf_layout.setSpacing(3)
        self._step_labels: list[QLabel] = []
        for step in [
            self._t("page.device.qr_scan.step1"),
            self._t("page.device.qr_scan.step2"),
            self._t("page.device.qr_scan.step3"),
        ]:
            lbl = QLabel(step)
            self._step_labels.append(lbl)
            sf_layout.addWidget(lbl)
        layout.addWidget(self._steps_frame)

        # 二维码显示区
        self._qr_label = QLabel()
        self._qr_label.setAlignment(Qt.AlignCenter)
        self._qr_label.setFixedSize(260, 260)
        qr_wrapper = QHBoxLayout()
        qr_wrapper.addStretch()
        qr_wrapper.addWidget(self._qr_label)
        qr_wrapper.addStretch()
        layout.addLayout(qr_wrapper)

        # 状态标签
        self._status_lbl = QLabel(self._status_text)
        self._status_lbl.setAlignment(Qt.AlignCenter)
        self._status_lbl.setWordWrap(True)
        layout.addWidget(self._status_lbl)

        # 倒计时标签
        self._countdown_lbl = QLabel("")
        self._countdown_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._countdown_lbl)

        # 关闭按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._close_btn = QPushButton(self._t("dialog.confirm.no"))
        self._close_btn.setStyleSheet(btn_subtle(self._theme_tokens))
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
            self._qr_error_text = self._t("page.device.qr_scan.error", error=str(e))
            self._qr_label.setPixmap(QPixmap())
            self.refresh_theme_surfaces()

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
        self._status_text = self._t("page.device.qr_scan.success", device_id=device_id)
        self._status_level = "success"
        self._render_status()
        self._countdown_lbl.setText("")
        self._close_btn.setText(self._t("page.device.qr_scan.btn.done"))
        # 记录成功的设备 ID 供外部读取
        self._paired_device_id = device_id

    def _on_timed_out(self):
        self._timer.stop()
        self._status_text = self._t("page.device.qr_scan.timeout")
        self._status_level = "warning"
        self._render_status()
        self._countdown_lbl.setText("")

    def _on_tick(self):
        self._remaining -= 1
        if self._remaining <= 0:
            self._timer.stop()
        else:
            self._countdown_lbl.setText(
                self._t("page.device.qr_scan.countdown", seconds=self._remaining)
            )

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

    def _render_status(self) -> None:
        if not hasattr(self, "_status_lbl") or self._tokens is None:
            return
        color_map = {
            "muted": self._tokens.text_secondary,
            "success": self._tokens.success,
            "warning": self._tokens.warning,
            "danger": self._tokens.danger,
        }
        color = color_map.get(self._status_level, self._tokens.text_secondary)
        self._status_lbl.setStyleSheet(f"color:{color}; font-size:12px;")
        self._status_lbl.setText(self._status_text)

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

class QrPairDialog(ThemeAwareDialog):
    """
    Android 11+ 无线调试二维码配对对话框（配对码手动输入方式）。

    使用步骤（手机端）：
      1. 手机 设置 -> 开发者选项 -> 无线调试 -> 使用二维码配对设备
      2. 手机屏幕会显示一个二维码，同时弹出配对码和配对端口
      3. 在本对话框填写「配对端口」（形如 192.168.x.x:3xxxx）和「配对码」（6位数字）
      4. 点击「配对」按钮，等待配对成功
      5. 配对成功后，再用 TCP/IP 连接区的「连接」按钮连接常规端口（通常显示在无线调试页）
    """

    def __init__(self, parent=None, theme: str = "dark", theme_manager=None, translator=None):
        super().__init__(parent)
        self._theme_mode = theme
        self._translator = translator
        self._status_text = ""
        self._status_level = "muted"
        self._tokens = resolve_theme_tokens(self._theme_mode)
        self.setWindowTitle(self._t("page.device.qr_pair.window_title"))
        self.setMinimumWidth(460)
        self._build_ui()
        if theme_manager is not None:
            self.bind_theme_manager(theme_manager)
        else:
            # 初始应用主题
            self.apply_theme_tokens(self._tokens)

    def _t(self, key: str, **params) -> str:
        translator = self._translator
        if callable(translator):
            try:
                return translator(key, **params)
            except Exception:
                pass
        from gui.i18n.locales.cn import CN
        template = CN.get(key, f"[[{key}]]")
        try:
            return template.format(**params) if params else template
        except Exception:
            return template

    # ------------------------------------------------------------------
    # ThemeAware 协议
    # ------------------------------------------------------------------

    def refresh_theme_surfaces(self) -> None:
        """刷新对话框背景和基础样式。"""
        if self._tokens is None:
            return
        t = self._tokens
        self.setStyleSheet(dialog_surface(t))
        card_style = f"QFrame {{ background: {t.bg_elevated}; border: 1px solid {t.border}; border-radius: 8px; }}"
        muted = t.text_secondary
        title = t.text_primary
        if hasattr(self, "_title_lbl"):
            self._title_lbl.setStyleSheet(f"color:{title}; font-size:16px; font-weight:bold;")
        if hasattr(self, "_steps_frame"):
            self._steps_frame.setStyleSheet(card_style)
        if hasattr(self, "_steps_title_lbl"):
            self._steps_title_lbl.setStyleSheet(f"color:{title}; font-size:13px; font-weight:bold;")
        for lbl in getattr(self, "_step_labels", []):
            lbl.setStyleSheet(f"color:{muted}; font-size:12px;")
        if hasattr(self, "_status_lbl"):
            self._render_status()

    def refresh_theme_states(self) -> None:
        """刷新按钮等动态状态。"""
        if self._tokens is None:
            return
        if hasattr(self, "_cancel_btn"):
            self._cancel_btn.setStyleSheet(btn_subtle(self._tokens))
        if hasattr(self, "_pair_btn"):
            self._pair_btn.setStyleSheet(btn_primary(self._tokens))

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # 标题
        self._title_lbl = QLabel(self._t("page.device.qr_pair.title"))
        layout.addWidget(self._title_lbl)

        # 操作说明卡片
        self._steps_frame = QFrame()
        steps_layout = QVBoxLayout(self._steps_frame)
        steps_layout.setContentsMargins(14, 12, 14, 12)
        steps_layout.setSpacing(4)

        self._steps_title_lbl = QLabel(self._t("page.device.qr_pair.steps_title"))
        steps_layout.addWidget(self._steps_title_lbl)

        self._step_labels: list[QLabel] = []
        steps_text = [
            self._t("page.device.qr_pair.step1"),
            self._t("page.device.qr_pair.step2"),
            self._t("page.device.qr_pair.step3"),
            self._t("page.device.qr_pair.step4"),
            self._t("page.device.qr_pair.step5"),
            self._t("page.device.qr_pair.step6"),
            self._t("page.device.qr_pair.step7"),
        ]
        for step in steps_text:
            lbl = QLabel(step)
            lbl.setWordWrap(True)
            self._step_labels.append(lbl)
            steps_layout.addWidget(lbl)

        layout.addWidget(self._steps_frame)

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
        addr_lbl = QLabel(self._t("page.device.qr_pair.addr_label"))
        addr_lbl.setFixedWidth(70)
        self._pair_addr_input = QLineEdit()
        self._pair_addr_input.setPlaceholderText(self._t("page.device.qr_pair.addr_placeholder"))
        self._pair_addr_input.setToolTip(
            self._t("page.device.qr_pair.addr_tooltip")
        )
        addr_row.addWidget(addr_lbl)
        addr_row.addWidget(self._pair_addr_input)
        form_layout.addLayout(addr_row)

        # 配对码
        code_row = QHBoxLayout()
        code_lbl = QLabel(self._t("page.device.qr_pair.code_label"))
        code_lbl.setFixedWidth(70)
        self._pair_code_input = QLineEdit()
        self._pair_code_input.setPlaceholderText(self._t("page.device.qr_pair.code_placeholder"))
        self._pair_code_input.setMaxLength(12)
        self._pair_code_input.setToolTip(self._t("page.device.qr_pair.code_tooltip"))
        code_row.addWidget(code_lbl)
        code_row.addWidget(self._pair_code_input)
        form_layout.addLayout(code_row)

        layout.addLayout(form_layout)

        # 状态标签
        self._status_lbl = QLabel("")
        self._status_lbl.setWordWrap(True)
        layout.addWidget(self._status_lbl)

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._cancel_btn = QPushButton(self._t("dialog.confirm.no"))
        self._cancel_btn.setStyleSheet(btn_subtle(self._theme_tokens))
        self._cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self._cancel_btn)

        self._pair_btn = QPushButton(self._t("page.device.qr_pair.btn.start"))
        self._pair_btn.setStyleSheet(btn_primary(self._theme_tokens))
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
            self._set_status(self._t("page.device.qr_pair.status.addr_required"), error=True)
            return
        if ":" not in addr:
            self._set_status(self._t("page.device.qr_pair.status.addr_invalid"), error=True)
            return
        if not code:
            self._set_status(self._t("page.device.qr_pair.status.code_required"), error=True)
            return
        self.accept()

    def _set_status(self, msg: str, error: bool = False):
        self._status_text = msg
        self._status_level = "danger" if error else "success"
        self._render_status()

    def _render_status(self) -> None:
        if not hasattr(self, "_status_lbl") or self._tokens is None:
            return
        color_map = {
            "muted": self._tokens.text_secondary,
            "success": self._tokens.success,
            "warning": self._tokens.warning,
            "danger": self._tokens.danger,
        }
        color = color_map.get(self._status_level, self._tokens.text_secondary)
        self._status_lbl.setStyleSheet(f"font-size:12px; color:{color};")
        self._status_lbl.setText(html.escape(self._status_text))

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
        self._config = services.get("config")
        self._theme_manager = services.get("theme_manager")
        self._theme_mode = "dark"
        self._theme_tokens = resolve_theme_tokens(self._theme_mode)
        self._theme_vars = self._theme_tokens.to_legacy_dict()
        self._build_ui()
        self._apply_action_button_styles()
        self._update_action_button_states()
        self._connect_signals()

    # ------------------------------------------------------------------
    # i18n 辅助
    # ------------------------------------------------------------------

    def _t(self, key: str, **params) -> str:
        """便捷翻译方法；优先使用 services 中的 I18nManager，无则回退内置中文。"""
        i18n = self._services.get("i18n")
        if i18n is not None:
            try:
                return i18n.t(key, **params)
            except Exception:
                pass
        from gui.i18n.locales.cn import CN
        template = CN.get(key, f"[[{key}]]")
        try:
            return template.format(**params) if params else template
        except Exception:
            return template

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)

        # 标题
        self._title_lbl = QLabel(self._t("page.device.title"))
        self._title_lbl.setProperty("role", "pageTitle")
        root.addWidget(self._title_lbl)

        # ADB 状态区
        self._adb_group = QGroupBox(self._t("page.device.section.adb"))
        adb_group = self._adb_group
        adb_layout = QVBoxLayout(adb_group)
        adb_layout.setSpacing(8)

        self._adb_status_lbl = QLabel(self._t("page.device.adb.checking"))
        self._adb_status_lbl.setProperty("role", "muted")
        self._adb_status_lbl.setStyleSheet("font-size:13px;")
        adb_layout.addWidget(self._adb_status_lbl)

        self._btn_check_adb = QPushButton(self._t("page.device.btn.check_adb"))
        self._btn_check_adb.setFixedWidth(150)
        self._btn_check_adb.setProperty("variant", "subtle")
        self._btn_check_adb.clicked.connect(self._on_check_adb)
        adb_layout.addWidget(self._btn_check_adb)
        root.addWidget(adb_group)

        # 设备列表区
        self._devices_group = QGroupBox(self._t("page.device.section.connected"))
        devices_group = self._devices_group
        devices_layout = QVBoxLayout(devices_group)
        devices_layout.setSpacing(8)

        self._device_list = QListWidget()
        self._device_list.setProperty("surface", "console")
        self._device_list.setFixedHeight(180)
        self._device_list.currentRowChanged.connect(self._on_device_selected)
        devices_layout.addWidget(self._device_list)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._btn_select = QPushButton(self._t("page.device.btn.select"))
        self._btn_select.setProperty("variant", "primary")
        self._btn_select.clicked.connect(self._on_set_active)
        btn_row.addWidget(self._btn_select)

        self._btn_disconnect = QPushButton(self._t("page.device.btn.disconnect"))
        self._btn_disconnect.setProperty("variant", "danger")
        self._btn_disconnect.clicked.connect(self._on_disconnect)
        btn_row.addWidget(self._btn_disconnect)

        self._btn_refresh = QPushButton(self._t("page.device.btn.refresh"))
        self._btn_refresh.setProperty("variant", "subtle")
        self._btn_refresh.clicked.connect(self._on_refresh)
        btn_row.addWidget(self._btn_refresh)
        btn_row.addStretch()
        devices_layout.addLayout(btn_row)
        root.addWidget(devices_group)

        # 无线连接区
        self._wifi_group = QGroupBox(self._t("page.device.section.wifi"))
        wifi_group = self._wifi_group
        wifi_outer = QVBoxLayout(wifi_group)
        wifi_outer.setSpacing(10)

        # 第一行：IP 地址连接
        wifi_row = QHBoxLayout()
        wifi_row.setSpacing(8)
        self._wifi_addr_lbl = QLabel(self._t("page.device.wifi.addr_label"))
        wifi_row.addWidget(self._wifi_addr_lbl)
        self._wifi_input = QLineEdit()
        self._wifi_input.setPlaceholderText(self._t("page.device.hint.wifi"))
        self._wifi_input.setFixedWidth(200)
        self._wifi_input.textChanged.connect(self._update_action_button_states)
        wifi_row.addWidget(self._wifi_input)

        self._btn_wifi_connect = QPushButton(self._t("page.device.btn.connect"))
        self._btn_wifi_connect.setProperty("variant", "primary")
        self._btn_wifi_connect.clicked.connect(self._on_wifi_connect)
        wifi_row.addWidget(self._btn_wifi_connect)
        wifi_row.addStretch()
        wifi_outer.addLayout(wifi_row)

        # 第二行：Android 11+ 双模式配对
        qr_row = QHBoxLayout()
        qr_row.setSpacing(8)
        qr_hint = QLabel(self._t("page.device.wifi.qr_hint"))
        self._qr_hint_lbl = qr_hint
        qr_hint.setProperty("role", "muted")
        qr_hint.setStyleSheet("font-size:12px;")
        qr_row.addWidget(qr_hint)

        # 生成二维码供手机扫描（真正的二维码配对）
        self._btn_qr_scan = QPushButton(self._t("page.device.btn.qr_scan"))
        self._btn_qr_scan.setToolTip(
            self._t("page.device.qr_scan.tooltip")
        )
        self._btn_qr_scan.setProperty("variant", "success")
        self._btn_qr_scan.clicked.connect(self._on_qr_scan_pair)
        qr_row.addWidget(self._btn_qr_scan)

        # 手动输入配对码（备用方式）
        self._btn_qr_pair = QPushButton(self._t("page.device.btn.qr_pair"))
        self._btn_qr_pair.setToolTip(
            self._t("page.device.qr_pair.tooltip")
        )
        self._btn_qr_pair.setProperty("variant", "subtle")
        self._btn_qr_pair.clicked.connect(self._on_qr_pair)
        qr_row.addWidget(self._btn_qr_pair)

        qr_row.addStretch()
        wifi_outer.addLayout(qr_row)

        root.addWidget(wifi_group)

        # 详情/日志区
        self._detail_group = QGroupBox(self._t("page.device.section.log"))
        detail_group = self._detail_group
        detail_layout = QVBoxLayout(detail_group)
        self._detail_log = QPlainTextEdit()
        self._detail_log.setReadOnly(True)
        self._detail_log.setFixedHeight(120)
        self._detail_log.setProperty("surface", "console")
        detail_layout.addWidget(self._detail_log)
        root.addWidget(detail_group)

        # ADB Keyboard 检查
        self._kbd_group = QGroupBox("ADB Keyboard")
        kbd_group = self._kbd_group
        kbd_layout = QHBoxLayout(kbd_group)
        self._kbd_status_lbl = QLabel("—")
        self._kbd_status_lbl.setProperty("role", "muted")
        kbd_layout.addWidget(self._kbd_status_lbl)
        self._btn_check_kbd = QPushButton(self._t("page.device.btn.check_kbd"))
        self._btn_check_kbd.setProperty("variant", "subtle")
        self._btn_check_kbd.clicked.connect(self._on_check_kbd)
        kbd_layout.addWidget(self._btn_check_kbd)
        kbd_layout.addStretch()
        root.addWidget(kbd_group)

        # scrcpy 状态
        self._scrcpy_group = QGroupBox(self._t("page.device.section.scrcpy"))
        scrcpy_group = self._scrcpy_group
        scrcpy_layout = QHBoxLayout(scrcpy_group)
        self._scrcpy_status_lbl = QLabel("—")
        self._scrcpy_status_lbl.setProperty("role", "muted")
        scrcpy_layout.addWidget(self._scrcpy_status_lbl)
        self._btn_check_scrcpy = QPushButton(self._t("page.device.btn.check_scrcpy"))
        self._btn_check_scrcpy.setProperty("variant", "subtle")
        self._btn_check_scrcpy.clicked.connect(self._on_check_scrcpy)
        scrcpy_layout.addWidget(self._btn_check_scrcpy)
        scrcpy_layout.addStretch()
        root.addWidget(scrcpy_group)

        root.addStretch(1)

    def _device_list_style(self) -> str:
        """设备列表样式（委托至 styles/lists.py）。"""
        return list_default(self._theme_tokens)

    def _detail_log_style(self) -> str:
        """设备操作日志样式（委托至 styles/logs.py）。"""
        return log_console(self._theme_tokens)

    def _apply_action_button_styles(self):
        btn_styles = (
            (getattr(self, "_btn_check_adb", None), btn_subtle(self._theme_tokens)),
            (getattr(self, "_btn_select", None), btn_primary(self._theme_tokens)),
            (getattr(self, "_btn_disconnect", None), btn_danger(self._theme_tokens)),
            (getattr(self, "_btn_refresh", None), btn_subtle(self._theme_tokens)),
            (getattr(self, "_btn_wifi_connect", None), btn_primary(self._theme_tokens)),
            (getattr(self, "_btn_qr_scan", None), btn_success(self._theme_tokens)),
            (getattr(self, "_btn_qr_pair", None), btn_subtle(self._theme_tokens)),
            (getattr(self, "_btn_check_kbd", None), btn_subtle(self._theme_tokens)),
            (getattr(self, "_btn_check_scrcpy", None), btn_subtle(self._theme_tokens)),
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

    def apply_theme_tokens(self, tokens: ThemeTokens) -> None:
        """
        新版主题接口 - 由 PageThemeAdapter / ThemeManager 驱动。
        缓存 tokens 后按三段式刷新。
        """
        self._theme_tokens = tokens
        self._theme_mode = tokens.mode
        self._theme_vars = tokens.to_legacy_dict()
        self.refresh_theme_surfaces()
        self.refresh_theme_states()

    def refresh_theme_surfaces(self) -> None:
        """刷新静态外观：列表、日志区背景。"""
        if self._theme_tokens is None:
            return
        if hasattr(self, '_device_list'):
            self._device_list.setStyleSheet(self._device_list_style())
        if hasattr(self, '_detail_log'):
            self._detail_log.setStyleSheet(self._detail_log_style())

    def refresh_theme_states(self) -> None:
        """刷新动态状态：按钮样式。"""
        self._apply_action_button_styles()

    def on_theme_changed(self, theme: str, theme_vars: dict):
        """[兼容] 旧版接口，由 PageThemeAdapter 在未实现新接口时调用。"""
        self._theme_mode = theme
        if getattr(self, "_theme_tokens", None) is None or self._theme_tokens.mode != theme:
            self._theme_tokens = resolve_theme_tokens(theme)
        self._theme_vars = theme_vars or self._theme_tokens.to_legacy_dict()
        self.refresh_theme_surfaces()
        self.refresh_theme_states()

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
            self._log(
                self._t(
                    "page.device.log.adb_check",
                    result=self._t("page.device.result.success") if ok else self._t("page.device.result.failed"),
                    msg=msg,
                )
            )

    def _on_adb_status(self, available: bool, msg: str):
        color = "#3fb950" if available else "#f85149"
        status = self._t("page.device.result.available") if available else self._t("page.device.result.unavailable")
        self._adb_status_lbl.setText(
            self._t("page.device.adb.status_html", color=color, status=status, msg=msg)
        )

    def _on_device_error(self, msg: str):
        self._log(self._t("page.device.log.service", msg=msg))

    def _refresh_device_list(self, devices):
        self._device_list.clear()
        if not devices:
            self._device_list.addItem(self._t("page.device.empty.list"))
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
            if self._config:
                self._config.set("OPEN_AUTOGLM_DEVICE_ID", device_id)
            self._log(self._t("page.device.selected", device_id=device_id))
            self._update_action_button_states()

    def _on_disconnect(self):
        item = self._device_list.currentItem()
        if not item:
            self._log(self._t("page.device.disconnect.no_item"))
            return

        device_id = item.data(Qt.UserRole)
        row = self._device_list.currentRow()
        self._log(
            self._t(
                "page.device.log.disconnect_triggered",
                row=row,
                text=item.text(),
                device_id=device_id or "None",
            )
        )

        if not device_id:
            self._log(self._t("page.device.disconnect.no_device_id"))
            return

        if isinstance(device_id, str) and "_adb-tls-connect._tcp" in device_id:
            self._log(self._t("page.device.disconnect.mdns_hint"))

        if self._device:
            ok, msg = self._device.disconnect_device(device_id)
            self._log(
                self._t(
                    "page.device.log.disconnect_result",
                    device_id=device_id,
                    result=self._t("page.device.result.success") if ok else self._t("page.device.result.failed"),
                    msg=msg,
                )
            )

    def _on_refresh(self):
        if self._device:
            self._device.refresh()
            self._log(self._t("page.device.log.refresh_done"))

    def _on_wifi_connect(self):
        addr = self._wifi_input.text().strip()
        if not addr:
            return
        if self._device:
            ok, msg = self._device.connect_device(addr)
            self._log(
                self._t(
                    "page.device.log.connect_result",
                    addr=addr,
                    result=self._t("page.device.result.success") if ok else self._t("page.device.result.failed"),
                    msg=msg,
                )
            )

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

        self._log(self._t("page.device.log.qr_generating"))
        dlg = QrCodeScanDialog(
            known_ids,
            parent=self,
            theme=self._theme_mode,
            theme_manager=self._theme_manager,
            translator=self._t,
        )
        dlg.exec()

        paired_id = dlg.paired_device_id
        if paired_id:
            self._log(self._t("page.device.log.qr_pair_success", device_id=paired_id))
            if self._device:
                self._device.refresh()
                # 若为 WiFi 设备（含 :），提取 IP 填入连接框
                if ":" in paired_id:
                    self._wifi_input.setText(paired_id)
                    self._log(self._t("page.device.log.addr_filled", addr=paired_id))
        else:
            self._log(self._t("page.device.log.qr_dialog_closed"))

    def _on_qr_pair(self):
        """打开配对码手动输入对话框，执行 adb pair（备用方式）"""
        dlg = QrPairDialog(self, theme=self._theme_mode, theme_manager=self._theme_manager, translator=self._t)
        if dlg.exec() != QrPairDialog.DialogCode.Accepted:
            return
        addr = dlg.pair_address
        code = dlg.pair_code
        self._log(self._t("page.device.log.pairing", addr=addr))
        if self._device:
            ok, msg = self._device.pair_device(addr, code)
            if ok:
                self._log(self._t("page.device.log.pair_success", msg=msg))
                # 配对成功后，把 IP 部分填入连接输入框方便后续连接
                ip = addr.split(":")[0]
                self._wifi_input.setText(ip)
                self._log(self._t("page.device.log.port_hint", ip=ip))
            else:
                self._log(self._t("page.device.log.pair_failed", msg=msg))
        else:
            self._log(self._t("page.device.service_unavailable"))

    def _on_check_kbd(self):
        device_id = ""
        if self._device and self._device.selected_device:
            device_id = self._device.selected_device.device_id
        if not device_id:
            self._kbd_status_lbl.setText(self._t("page.device.kbd.no_device"))
            return
        if self._device:
            ok, msg = self._device.check_adb_keyboard(device_id)
            color = "#3fb950" if ok else "#e3b341"
            self._kbd_status_lbl.setText(
                f"<span style='color:{color}'>{msg}</span>"
            )
            self._log(self._t("page.device.log.kbd_check", msg=msg))

    def _on_check_scrcpy(self):
        mirror = self._services.get("mirror")
        if mirror:
            ok, msg = mirror.check_available()
        elif self._device:
            ok, msg = self._device.check_scrcpy()
        else:
            ok, msg = False, self._t("page.device.service_unavailable")
        color = "#3fb950" if ok else "#e3b341"
        self._scrcpy_status_lbl.setText(
            f"<span style='color:{color}'>{msg}</span>"
        )
        self._log(self._t("page.device.log.scrcpy_check", msg=msg))

    def _log(self, msg: str):
        from PySide6.QtCore import QDateTime
        ts = QDateTime.currentDateTime().toString("hh:mm:ss")
        self._detail_log.appendPlainText(f"[{ts}] {msg}")

    # ------------------------------------------------------------------
    # apply_i18n - 语言切换时由 PageI18nAdapter 调用
    # ------------------------------------------------------------------

    def apply_i18n(self, i18n_manager) -> None:
        """语言切换后重绘所有静态文案。"""
        # 标题
        self._title_lbl.setText(i18n_manager.t("page.device.title"))
        # 分组标题
        self._adb_group.setTitle(i18n_manager.t("page.device.section.adb"))
        self._devices_group.setTitle(i18n_manager.t("page.device.section.connected"))
        self._wifi_group.setTitle(i18n_manager.t("page.device.section.wifi"))
        self._detail_group.setTitle(i18n_manager.t("page.device.section.log"))
        self._kbd_group.setTitle("ADB Keyboard")  # 保持英文（专有名词）
        self._scrcpy_group.setTitle(i18n_manager.t("page.device.section.scrcpy"))
        # 按钮文案
        self._btn_check_adb.setText(i18n_manager.t("page.device.btn.check_adb"))
        self._btn_select.setText(i18n_manager.t("page.device.btn.select"))
        self._btn_disconnect.setText(i18n_manager.t("page.device.btn.disconnect"))
        self._btn_refresh.setText(i18n_manager.t("page.device.btn.refresh"))
        self._btn_wifi_connect.setText(i18n_manager.t("page.device.btn.connect"))
        self._btn_qr_scan.setText(i18n_manager.t("page.device.btn.qr_scan"))
        self._btn_qr_scan.setToolTip(i18n_manager.t("page.device.qr_scan.tooltip"))
        self._btn_qr_pair.setText(i18n_manager.t("page.device.btn.qr_pair"))
        self._btn_qr_pair.setToolTip(i18n_manager.t("page.device.qr_pair.tooltip"))
        self._btn_check_kbd.setText(i18n_manager.t("page.device.btn.check_kbd"))
        self._btn_check_scrcpy.setText(i18n_manager.t("page.device.btn.check_scrcpy"))
        # 输入框 placeholder
        self._wifi_addr_lbl.setText(i18n_manager.t("page.device.wifi.addr_label"))
        self._qr_hint_lbl.setText(i18n_manager.t("page.device.wifi.qr_hint"))
        self._wifi_input.setPlaceholderText(i18n_manager.t("page.device.hint.wifi"))
        self._adb_status_lbl.setText(i18n_manager.t("page.device.adb.checking"))

    def on_page_activated(self):
        if self._device:
            self._device.refresh()
