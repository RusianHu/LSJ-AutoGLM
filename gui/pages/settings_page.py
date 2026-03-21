# -*- coding: utf-8 -*-
"""设置页 - .env 可视化读取与校验、模型/API 参数查看与编辑"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class SettingsPage(QWidget):
    """设置页"""

    def __init__(self, services: dict, parent=None):
        super().__init__(parent)
        self._services = services
        self._config = services.get("config")
        self._field_widgets: dict = {}   # key -> QLineEdit
        self._build_ui()
        self._load_values()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)

        title = QLabel("设置")
        title.setStyleSheet("font-size:18px; font-weight:bold; color:#c9d1d9;")
        root.addWidget(title)

        # .env 文件路径提示
        self._env_path_lbl = QLabel()
        self._env_path_lbl.setStyleSheet("color:#484f58; font-size:12px;")
        root.addWidget(self._env_path_lbl)

        # 校验提示区
        self._validate_banner = QLabel("")
        self._validate_banner.setWordWrap(True)
        self._validate_banner.setStyleSheet(
            "background:#161b22; border:1px solid #21262d; border-radius:4px; "
            "padding:8px; color:#e3b341; font-size:12px;"
        )
        self._validate_banner.hide()
        root.addWidget(self._validate_banner)

        # 滚动区
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border:none; }")
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(16)
        scroll.setWidget(scroll_widget)
        root.addWidget(scroll, 1)

        # ---- 模型与 API ----
        model_group = QGroupBox("模型与 API")
        model_form = QFormLayout(model_group)
        model_form.setLabelAlignment(Qt.AlignRight)
        model_form.setSpacing(10)

        api_fields = [
            "OPEN_AUTOGLM_BASE_URL",
            "OPEN_AUTOGLM_MODEL",
            "OPEN_AUTOGLM_API_KEY",
            "OPEN_AUTOGLM_BACKUP_API_KEY",
        ]
        self._add_fields(model_form, api_fields)
        scroll_layout.addWidget(model_group)

        # ---- 预设 Key ----
        preset_group = QGroupBox("预设 API Key")
        preset_form = QFormLayout(preset_group)
        preset_form.setLabelAlignment(Qt.AlignRight)
        preset_form.setSpacing(10)

        preset_fields = [
            "OPEN_AUTOGLM_MODELSCOPE_API_KEY",
            "OPEN_AUTOGLM_MODELSCOPE_BACKUP_API_KEY",
            "OPEN_AUTOGLM_ZHIPU_API_KEY",
            "OPEN_AUTOGLM_NEWAPI_API_KEY",
            "OPEN_AUTOGLM_NEWAPI_BASE_URL",
            "OPEN_AUTOGLM_NEWAPI_MODEL",
        ]
        self._add_fields(preset_form, preset_fields)
        scroll_layout.addWidget(preset_group)

        # ---- 运行参数 ----
        run_group = QGroupBox("运行参数")
        run_form = QFormLayout(run_group)
        run_form.setLabelAlignment(Qt.AlignRight)
        run_form.setSpacing(10)

        run_fields = [
            "OPEN_AUTOGLM_DEVICE_ID",
            "OPEN_AUTOGLM_LANG",
            "OPEN_AUTOGLM_MAX_STEPS",
            "OPEN_AUTOGLM_USE_THIRDPARTY_PROMPT",
            "OPEN_AUTOGLM_THIRDPARTY_THINKING",
            "OPEN_AUTOGLM_COMPRESS_IMAGE",
        ]
        self._add_fields(run_form, run_fields)
        scroll_layout.addWidget(run_group)
        scroll_layout.addStretch(1)

        # 底部操作按钮
        btn_row = QHBoxLayout()
        btn_save = QPushButton("保存修改")
        btn_save.setStyleSheet("""
            QPushButton {
                background:#1f6feb; border:none; border-radius:6px;
                color:#fff; padding:8px 24px; font-size:13px;
            }
            QPushButton:hover { background:#388bfd; }
        """)
        btn_save.clicked.connect(self._on_save)
        btn_row.addWidget(btn_save)

        btn_validate = QPushButton("校验配置")
        btn_validate.clicked.connect(self._on_validate)
        btn_row.addWidget(btn_validate)

        btn_reload = QPushButton("重新加载 .env")
        btn_reload.clicked.connect(self._on_reload)
        btn_row.addWidget(btn_reload)

        btn_row.addStretch(1)
        root.addLayout(btn_row)

    def _add_fields(self, form: QFormLayout, keys: list):
        """为一组配置键创建表单行"""
        if not self._config:
            return
        meta = self._config.FIELD_META
        for key in keys:
            info = meta.get(key, {})
            label_text = info.get("label", key)
            sensitive = info.get("sensitive", False)
            editable = info.get("editable", True)

            edit = QLineEdit()
            edit.setMinimumWidth(320)
            if sensitive:
                edit.setEchoMode(QLineEdit.Password)
            if not editable:
                edit.setReadOnly(True)
                edit.setStyleSheet("background:#0a0e17; color:#484f58;")

            lbl = QLabel(f"{label_text}:")
            lbl.setStyleSheet("color:#8b949e; font-size:12px;")

            # 对敏感字段添加显示/隐藏按钮
            if sensitive:
                row_widget = QWidget()
                row_layout = QHBoxLayout(row_widget)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(4)
                row_layout.addWidget(edit, 1)
                toggle_btn = QPushButton("显示")
                toggle_btn.setFixedWidth(48)
                toggle_btn.setStyleSheet(
                    "QPushButton { background:#21262d; border:1px solid #30363d; "
                    "border-radius:4px; color:#8b949e; padding:0 6px; font-size:11px; } "
                    "QPushButton:hover { color:#c9d1d9; }"
                )
                toggle_btn.clicked.connect(lambda _, e=edit, b=toggle_btn: self._toggle_visibility(e, b))
                row_layout.addWidget(toggle_btn)
                form.addRow(lbl, row_widget)
            else:
                form.addRow(lbl, edit)

            self._field_widgets[key] = edit

    def _toggle_visibility(self, edit: QLineEdit, btn: QPushButton):
        if edit.echoMode() == QLineEdit.Password:
            edit.setEchoMode(QLineEdit.Normal)
            btn.setText("隐藏")
        else:
            edit.setEchoMode(QLineEdit.Password)
            btn.setText("显示")

    def _load_values(self):
        if not self._config:
            return
        self._env_path_lbl.setText(f"配置文件: {self._config.env_path}")
        for key, edit in self._field_widgets.items():
            # 敏感字段显示真实值（密码模式隐藏）
            value = self._config.get(key)
            edit.setText(value)

    def _on_save(self):
        """收集界面值，批量写入（只写一次文件），失败时全量回滚"""
        if not self._config:
            return
        updates = {
            key: edit.text().strip()
            for key, edit in self._field_widgets.items()
        }
        # 先做校验（不污染缓存）
        errors = self._config.validate(updates)
        if errors:
            msgs = "\n".join(f"• {k}: {v}" for k, v in errors)
            QMessageBox.warning(self, "校验失败", msgs)
            return
        try:
            self._config.set_many(updates)
            self._show_banner("配置已保存到 .env 文件", ok=True)
        except Exception as e:
            QMessageBox.warning(self, "保存失败", str(e))

    def _on_validate(self):
        """
        仅校验界面当前值，不污染运行缓存。
        通过 ConfigService.validate(updates) 传入临时值副本。
        """
        if not self._config:
            return
        # 构造临时字典传入 validate，不修改 _cache
        temp_values = {
            key: edit.text().strip()
            for key, edit in self._field_widgets.items()
        }
        errors = self._config.validate(temp_values)
        if not errors:
            self._show_banner("配置校验通过", ok=True)
        else:
            msgs = "\n".join(f"• {k}: {v}" for k, v in errors)
            self._show_banner(f"校验发现问题：\n{msgs}", ok=False)

    def _on_reload(self):
        """从磁盘重新加载 .env"""
        if not self._config:
            return
        self._config.load()   # load() 无返回值，内部通过信号通知
        self._load_values()
        self._show_banner("已从 .env 文件重新加载", ok=True)

    def _show_banner(self, msg: str, ok: bool = True):
        """显示校验/操作结果横幅"""
        color   = "#3fb950" if ok else "#f0883e"
        bg      = "#0f2d1a" if ok else "#2d1a0f"
        border  = "#3fb95040" if ok else "#f0883e40"
        self._validate_banner.setText(msg)
        self._validate_banner.setStyleSheet(
            f"background:{bg}; border:1px solid {border}; border-radius:4px; "
            f"padding:8px; color:{color}; font-size:12px;"
        )
        self._validate_banner.show()

    def on_page_activated(self):
        self._load_values()
