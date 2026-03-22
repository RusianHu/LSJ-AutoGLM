# -*- coding: utf-8 -*-
"""
设置页 - .env 可视化读取与校验、模型/API 参数查看与编辑

变更记录：
- 新增「快捷预设」卡片区域，支持一键切换渠道并持久化到 .env
- 预设卡片显示名称、模型名、标签（原生/第三方），活跃预设高亮
- 监听 config_changed 信号，自动同步活跃预设高亮状态
"""

from PySide6.QtCore import Qt, QSize, QPropertyAnimation, QEasingCurve, QRect, Property
from PySide6.QtGui import QPainter, QColor, QPen, QBrush
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
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

from gui.theme.tokens import ThemeTokens
from gui.theme.themes import resolve_theme_tokens
from gui.theme.styles.buttons import btn_primary, btn_subtle

class _ToggleSwitch(QWidget):
    """
    自绘布尔值拨动开关。
    接口与 QLineEdit 兼容：text() 返回 'true'/'false'，setText() 设置状态。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._checked = False
        self._tokens: ThemeTokens = None
        self._anim_offset = 0.0
        self.setFixedSize(48, 24)
        self.setCursor(Qt.PointingHandCursor)

    # ---- 与 QLineEdit 兼容的接口 ----
    def text(self) -> str:
        return "true" if self._checked else "false"

    def setText(self, value: str):
        on = str(value).strip().lower() in ("1", "true", "yes", "on")
        if on != self._checked:
            self._checked = on
            self._anim_offset = 1.0 if on else 0.0
            self.update()

    def isChecked(self) -> bool:
        return self._checked

    def apply_tokens(self, tokens: ThemeTokens):
        self._tokens = tokens
        self.update()

    # ---- 交互 ----
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._checked = not self._checked
            self._anim_offset = 1.0 if self._checked else 0.0
            self.update()
        super().mousePressEvent(event)

    # ---- 绘制 ----
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        t = self._tokens
        track_on  = t.accent       if t else "#4f8cff"
        track_off = t.border       if t else "#444c56"
        thumb_col = t.bg_main      if t else "#ffffff"

        track_color = track_on if self._checked else track_off
        w, h = self.width(), self.height()
        r = h // 2

        # 轨道
        p.setBrush(QBrush(QColor(track_color)))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(0, 0, w, h, r, r)

        # 滑块
        padding = 3
        diameter = h - padding * 2
        max_x = w - padding - diameter
        x = int(max_x * self._anim_offset) + padding
        p.setBrush(QBrush(QColor(thumb_col)))
        p.drawEllipse(x, padding, diameter, diameter)
        p.end()


# 预设图标（emoji-free，用 Unicode 符号）
_PRESET_ICONS = {
    "modelscope": "MS",
    "zhipu":      "ZP",
    "newapi":     "3rd",
    "local":      "LCL",
    "custom":     "?",
}

# 每个渠道对应的专属配置字段（动态渠道配置面板用）
_CHANNEL_FIELDS: dict = {
    "modelscope": [
        "OPEN_AUTOGLM_MODELSCOPE_API_KEY",
        "OPEN_AUTOGLM_MODELSCOPE_BACKUP_API_KEY",
    ],
    "zhipu": [
        "OPEN_AUTOGLM_ZHIPU_API_KEY",
    ],
    "newapi": [
        "OPEN_AUTOGLM_NEWAPI_API_KEY",
        "OPEN_AUTOGLM_NEWAPI_BASE_URL",
        "OPEN_AUTOGLM_NEWAPI_MODEL",
    ],
    "local": [
        "OPEN_AUTOGLM_LOCAL_OPENAI_BASE_URL",
        "OPEN_AUTOGLM_LOCAL_OPENAI_MODEL",
        "OPEN_AUTOGLM_LOCAL_OPENAI_API_KEY",
    ],
    "custom": [],
}


class _PresetCard(QFrame):
    """
    单个预设渠道卡片。

    外观：
      - 圆角卡片，宽度拉伸，高度固定
      - 左侧圆形图标徽章（缩写字母）
      - 右侧：主标题（渠道名） + 副标题（模型名，截断）
      - 右上角标签（原生 AutoGLM / 第三方提示词）
      - 活跃状态：accent 色边框 + 淡色背景高亮
    """

    def __init__(self, preset: dict, resolved_model: str = "", parent=None):
        super().__init__(parent)
        self._preset = preset
        self._resolved_model = resolved_model  # 从 .env 读到的真实模型名
        self._active = False
        self._theme_tokens: ThemeTokens = None
        self._build_ui()
        self.setFixedHeight(72)
        self.setCursor(Qt.PointingHandCursor)
        self.setFrameShape(QFrame.StyledPanel)

    # ----------------------------------------------------------------
    # 构建
    # ----------------------------------------------------------------

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        # 左侧圆形图标
        self._icon_lbl = QLabel(_PRESET_ICONS.get(self._preset.get("id", ""), "?"))
        self._icon_lbl.setAlignment(Qt.AlignCenter)
        self._icon_lbl.setFixedSize(QSize(40, 40))
        layout.addWidget(self._icon_lbl)

        # 文字区
        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)

        self._name_lbl = QLabel(self._preset.get("name", ""))
        self._name_lbl.setObjectName("presetCardName")

        model_display = self._resolved_model or self._preset.get("default_model", "") or "自定义"
        if len(model_display) > 38:
            model_display = model_display[:35] + "..."
        self._model_lbl = QLabel(model_display)
        self._model_lbl.setObjectName("presetCardModel")

        text_col.addWidget(self._name_lbl)
        text_col.addWidget(self._model_lbl)
        layout.addLayout(text_col, 1)

        # 右侧标签 + 活跃指示
        right_col = QVBoxLayout()
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(4)
        right_col.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        use_thirdparty = self._preset.get("use_thirdparty", False)
        tag_text = "第三方提示词" if use_thirdparty else "原生 AutoGLM"
        self._tag_lbl = QLabel(tag_text)
        self._tag_lbl.setObjectName("presetCardTag")
        self._tag_lbl.setAlignment(Qt.AlignRight)

        self._active_dot = QLabel("")
        self._active_dot.setFixedSize(QSize(8, 8))
        self._active_dot.setObjectName("presetActiveDot")
        self._active_dot.setAlignment(Qt.AlignRight)

        right_col.addWidget(self._tag_lbl)
        right_col.addWidget(self._active_dot, 0, Qt.AlignRight)
        layout.addLayout(right_col)

    # ----------------------------------------------------------------
    # 状态更新
    # ----------------------------------------------------------------

    def set_active(self, active: bool, tokens: ThemeTokens = None):
        self._active = active
        if tokens:
            self._theme_tokens = tokens
        self._refresh_style()

    def apply_tokens(self, tokens: ThemeTokens):
        self._theme_tokens = tokens
        self._refresh_style()

    def update_model_display(self, model: str):
        """动态更新卡片副标题（模型名），供配置变更后调用"""
        display = model or self._preset.get("default_model", "") or "自定义"
        if len(display) > 38:
            display = display[:35] + "..."
        self._model_lbl.setText(display)

    def _refresh_style(self):
        t = self._theme_tokens
        if t is None:
            return

        if self._active:
            card_bg = t.accent_soft
            card_border = t.accent
            name_color = t.accent
            dot_color = t.accent
        else:
            card_bg = t.bg_secondary
            card_border = t.border
            name_color = t.text_primary
            dot_color = "transparent"

        use_thirdparty = self._preset.get("use_thirdparty", False)
        tag_color = t.warning if use_thirdparty else t.success
        tag_bg = t.warning_bg if use_thirdparty else t.success_bg

        self.setStyleSheet(f"""
            _PresetCard, QFrame#presetCard {{
                background: {card_bg};
                border: 1.5px solid {card_border};
                border-radius: 10px;
            }}
        """)

        icon_bg = t.accent if self._active else t.bg_elevated
        icon_color = t.bg_main if self._active else t.text_secondary
        self._icon_lbl.setStyleSheet(f"""
            QLabel {{
                background: {icon_bg};
                color: {icon_color};
                border-radius: 20px;
                font-size: 11px;
                font-weight: bold;
            }}
        """)

        self._name_lbl.setStyleSheet(f"""
            QLabel {{
                color: {name_color};
                font-size: 13px;
                font-weight: bold;
                background: transparent;
                border: none;
            }}
        """)

        self._model_lbl.setStyleSheet(f"""
            QLabel {{
                color: {t.text_secondary};
                font-size: 11px;
                background: transparent;
                border: none;
            }}
        """)

        self._tag_lbl.setStyleSheet(f"""
            QLabel {{
                background: {tag_bg};
                color: {tag_color};
                font-size: 10px;
                padding: 2px 6px;
                border-radius: 4px;
                border: none;
            }}
        """)

        self._active_dot.setStyleSheet(f"""
            QLabel {{
                background: {dot_color};
                border-radius: 4px;
                border: none;
            }}
        """)

    # ----------------------------------------------------------------
    # 鼠标交互
    # ----------------------------------------------------------------

    def enterEvent(self, event):
        if not self._active and self._theme_tokens:
            t = self._theme_tokens
            self.setStyleSheet(f"""
                QFrame {{
                    background: {t.bg_elevated};
                    border: 1.5px solid {t.border_hover};
                    border-radius: 10px;
                }}
            """)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._refresh_style()
        super().leaveEvent(event)


class SettingsPage(QWidget):
    """设置页"""

    def __init__(self, services: dict, parent=None):
        super().__init__(parent)
        self._services = services
        self._config = services.get("config")
        self._field_widgets: dict = {}   # key -> QLineEdit
        self._theme_mode = "dark"
        self._theme_tokens = resolve_theme_tokens(self._theme_mode)
        self._theme_vars = self._theme_tokens.to_legacy_dict()
        self._last_banner_state = None
        self._visibility_toggle_buttons: list[QPushButton] = []
        self._preset_cards: list[_PresetCard] = []  # 预设卡片列表
        self._build_ui()
        self._theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        self._apply_action_button_styles()
        self._load_values()
        self._load_theme_combo()
        self._connect_config_signals()

    # ================================================================
    # 信号连接
    # ================================================================

    def _connect_config_signals(self):
        """连接 ConfigService 信号，实时同步预设高亮"""
        if self._config:
            try:
                self._config.config_changed.connect(self._on_config_changed)
            except Exception:
                pass

    def _on_config_changed(self):
        """配置变化时刷新预设高亮状态"""
        self._refresh_preset_active()
        if self._config:
            active = self._config.get_active_channel()
            active_id = active.get("id", "") if active else ""
            self._rebuild_channel_detail(active_id)
        self._load_values()  # 同步表单字段值

    # ================================================================
    # UI 构建
    # ================================================================

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)

        title = QLabel("设置")
        title.setProperty("role", "pageTitle")
        root.addWidget(title)

        # .env 文件路径提示
        self._env_path_lbl = QLabel()
        self._env_path_lbl.setProperty("role", "subtle")
        root.addWidget(self._env_path_lbl)

        # 校验提示区
        self._validate_banner = QLabel("")
        self._validate_banner.setWordWrap(True)
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

        # ---- 快捷预设 ----
        preset_switch_group = self._build_preset_switch_group()
        scroll_layout.addWidget(preset_switch_group)

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
            "OPEN_AUTOGLM_USE_THIRDPARTY_PROMPT",
            "OPEN_AUTOGLM_THIRDPARTY_THINKING",
            "OPEN_AUTOGLM_COMPRESS_IMAGE",
        ]
        self._add_fields(model_form, api_fields)
        scroll_layout.addWidget(model_group)

        # ---- 渠道配置（动态，随活跃预设变化）----
        channel_group = QGroupBox("渠道配置")
        channel_vbox = QVBoxLayout(channel_group)
        channel_vbox.setContentsMargins(12, 16, 12, 8)
        channel_vbox.setSpacing(8)

        channel_hint = QLabel("下方仅显示当前切换渠道中未在上方展示的额外专属字段。")
        channel_hint.setProperty("role", "subtle")
        channel_hint.setWordWrap(True)
        channel_vbox.addWidget(channel_hint)

        # 动态内容容器，由 _rebuild_channel_detail() 填充
        self._channel_detail_container = QWidget()
        self._channel_detail_vbox = QVBoxLayout(self._channel_detail_container)
        self._channel_detail_vbox.setContentsMargins(0, 4, 0, 0)
        self._channel_detail_vbox.setSpacing(8)
        channel_vbox.addWidget(self._channel_detail_container)

        scroll_layout.addWidget(channel_group)

        # ---- 运行参数 ----
        run_group = QGroupBox("运行参数")
        run_form = QFormLayout(run_group)
        run_form.setLabelAlignment(Qt.AlignRight)
        run_form.setSpacing(10)

        run_fields = [
            "OPEN_AUTOGLM_DEVICE_ID",
            "OPEN_AUTOGLM_LANG",
            "OPEN_AUTOGLM_MAX_STEPS",
        ]
        self._add_fields(run_form, run_fields)
        scroll_layout.addWidget(run_group)

        # ---- 外观 ----
        appearance_group = QGroupBox("外观")
        appearance_form = QFormLayout(appearance_group)
        appearance_form.setLabelAlignment(Qt.AlignRight)
        appearance_form.setSpacing(10)

        self._theme_combo = QComboBox()
        self._theme_combo.addItem("跟随系统", "system")
        self._theme_combo.addItem("深色", "dark")
        self._theme_combo.addItem("浅色", "light")
        self._theme_combo.setMinimumWidth(160)
        appearance_form.addRow(QLabel("界面主题"), self._theme_combo)

        self._theme_hint_lbl = QLabel("")
        self._theme_hint_lbl.setWordWrap(True)
        self._theme_hint_lbl.setProperty("role", "subtle")
        appearance_form.addRow(QLabel("当前效果"), self._theme_hint_lbl)
        scroll_layout.addWidget(appearance_group)

        scroll_layout.addStretch(1)

        # 底部操作按钮
        btn_row = QHBoxLayout()
        self._btn_save = QPushButton("保存修改")
        self._btn_save.setProperty("variant", "primary")
        self._btn_save.clicked.connect(self._on_save)
        btn_row.addWidget(self._btn_save)

        self._btn_validate = QPushButton("校验配置")
        self._btn_validate.setProperty("variant", "subtle")
        self._btn_validate.clicked.connect(self._on_validate)
        btn_row.addWidget(self._btn_validate)

        self._btn_reload = QPushButton("重新加载 .env")
        self._btn_reload.setProperty("variant", "subtle")
        self._btn_reload.clicked.connect(self._on_reload)
        btn_row.addWidget(self._btn_reload)

        btn_row.addStretch(1)
        root.addLayout(btn_row)

        # 初始化渠道配置面板（在所有 UI 构建完毕后执行）
        if self._config:
            active = self._config.get_active_channel()
            active_id = active.get("id", "") if active else ""
            self._rebuild_channel_detail(active_id)

    # ----------------------------------------------------------------
    # 快捷预设卡片区
    # ----------------------------------------------------------------

    def _build_preset_switch_group(self) -> QGroupBox:
        """构建快速切换卡片组"""
        group = QGroupBox("快速切换")
        outer = QVBoxLayout(group)
        outer.setContentsMargins(12, 16, 12, 12)
        outer.setSpacing(8)

        hint = QLabel("点击卡片快速切换当前生效的模型渠道，不会覆盖下方已保存的运行开关")
        hint.setProperty("role", "subtle")
        hint.setWordWrap(True)
        outer.addWidget(hint)

        # 卡片网格：每行两列
        if not self._config:
            return group

        presets = [p for p in self._config.CHANNEL_PRESETS if p["id"] != "custom"]
        grid_widget = QWidget()
        grid_layout = QHBoxLayout(grid_widget)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setSpacing(10)

        self._preset_cards.clear()
        for preset in presets:
            # 读取该预设在 .env 中的真实模型名（本地预设等有专用字段）
            resolved_model = self._config.get_preset_model(preset)
            card = _PresetCard(preset, resolved_model=resolved_model)
            card.apply_tokens(self._theme_tokens)
            card.mousePressEvent = lambda e, p=preset, c=card: self._on_preset_card_clicked(p, c)
            grid_layout.addWidget(card)
            self._preset_cards.append(card)

        outer.addWidget(grid_widget)

        # 当前预设提示行
        self._active_preset_lbl = QLabel("")
        self._active_preset_lbl.setProperty("role", "subtle")
        self._active_preset_lbl.setWordWrap(True)
        outer.addWidget(self._active_preset_lbl)

        # 初始高亮
        self._refresh_preset_active()
        return group

    def _on_preset_card_clicked(self, preset: dict, card: _PresetCard):
        """点击卡片时快速切换当前生效渠道并持久化"""
        if not self._config:
            return
        channel_id = preset.get("id", "")
        ok = self._config.set_active_channel(channel_id)
        if ok:
            self._refresh_preset_active()
            self._rebuild_channel_detail(channel_id)
            self._load_values()  # 刷新表单字段
            self._show_banner(
                f"已切换到渠道「{preset.get('name', channel_id)}」，当前生效配置已写入 .env",
                ok=True,
            )
        else:
            self._show_banner(f"切换渠道失败: {channel_id}", ok=False)

    def _refresh_preset_active(self):
        """根据当前配置高亮匹配的预设卡片，并同步更新各卡片显示的真实模型名"""
        if not self._config or not self._preset_cards:
            return
        active = self._config.get_active_channel()
        active_id = active.get("id", "") if active else ""
        for card in self._preset_cards:
            # 每次都从 .env 读取该预设的实际模型名（用户可能已在设置页修改）
            resolved_model = self._config.get_preset_model(card._preset)
            card.update_model_display(resolved_model)
            is_active = card._preset.get("id") == active_id
            card.set_active(is_active, self._theme_tokens)

        # 更新提示文字
        if hasattr(self, "_active_preset_lbl"):
            if active and active_id != "custom":
                model = self._config.get_preset_model(active) or active.get("default_model", "")
                self._active_preset_lbl.setText(
                    f"当前切换渠道：{active.get('name', active_id)}  |  模型：{model}"
                )
            else:
                url = self._config.get("OPEN_AUTOGLM_BASE_URL") or ""
                model = self._config.get("OPEN_AUTOGLM_MODEL") or ""
                self._active_preset_lbl.setText(
                    f"当前模式：自定义  |  URL：{url}  |  模型：{model}"
                )

    # ================================================================
    # 渠道详情动态面板
    # ================================================================

    def _rebuild_channel_detail(self, channel_id: str = ""):
        """
        根据 channel_id 重建渠道专属配置字段面板。
        在点击预设卡片、配置变化、页面激活时调用。
        """
        container = getattr(self, "_channel_detail_container", None)
        vbox = getattr(self, "_channel_detail_vbox", None)
        if container is None or vbox is None:
            return

        # 1. 从 _field_widgets 中移除所有渠道专属字段
        all_channel_keys: set = set()
        for keys in _CHANNEL_FIELDS.values():
            all_channel_keys.update(keys)
        for k in list(all_channel_keys):
            self._field_widgets.pop(k, None)

        # 2. 清空容器内的所有子 widget
        while vbox.count():
            item = vbox.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        # 3. 构建新字段
        keys = _CHANNEL_FIELDS.get(channel_id, [])
        if channel_id in {"newapi", "local"}:
            keys = []
        if not keys:
            if channel_id in {"newapi", "local"}:
                hint_text = "当前渠道没有额外专属字段；上方“模型与 API”保存的是当前生效配置，不会反向覆盖快速切换卡片。"
            else:
                hint_text = "当前渠道无专属配置字段（使用 模型与 API 区的全局字段即可）。"
            hint = QLabel(hint_text)
            hint.setProperty("role", "subtle")
            hint.setWordWrap(True)
            vbox.addWidget(hint)
            return

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setSpacing(8)
        self._add_fields(form, keys)
        vbox.addLayout(form)

        # 4. 加载当前值
        if self._config:
            for key in keys:
                w = self._field_widgets.get(key)
                if w:
                    w.setText(self._config.get(key) or "")

        # 5. 刷新 Toggle 主题
        if self._theme_tokens:
            for key in keys:
                w = self._field_widgets.get(key)
                if isinstance(w, _ToggleSwitch):
                    w.apply_tokens(self._theme_tokens)

    # ================================================================
    # 表单字段
    # ================================================================

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
            is_boolean = info.get("boolean", False)

            lbl = QLabel(f"{label_text}:")
            lbl.setProperty("role", "statusMeta")

            if is_boolean:
                # 布尔字段使用 Toggle 开关
                edit = _ToggleSwitch()
                if self._theme_tokens:
                    edit.apply_tokens(self._theme_tokens)
                row_widget = QWidget()
                row_layout = QHBoxLayout(row_widget)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(0)
                row_layout.addWidget(edit)
                row_layout.addStretch(1)
                form.addRow(lbl, row_widget)
                self._field_widgets[key] = edit
            else:
                edit = QLineEdit()
                edit.setMinimumWidth(320)
                if sensitive:
                    edit.setEchoMode(QLineEdit.Password)
                if not editable:
                    edit.setReadOnly(True)

                # 对敏感字段添加显示/隐藏按钮
                if sensitive:
                    row_widget = QWidget()
                    row_layout = QHBoxLayout(row_widget)
                    row_layout.setContentsMargins(0, 0, 0, 0)
                    row_layout.setSpacing(4)
                    row_layout.addWidget(edit, 1)
                    toggle_btn = QPushButton("显示")
                    toggle_btn.setFixedWidth(48)
                    toggle_btn.setProperty("variant", "subtle")
                    toggle_btn.clicked.connect(lambda _, e=edit, b=toggle_btn: self._toggle_visibility(e, b))
                    self._visibility_toggle_buttons.append(toggle_btn)
                    row_layout.addWidget(toggle_btn)
                    form.addRow(lbl, row_widget)
                else:
                    form.addRow(lbl, edit)

                self._field_widgets[key] = edit

    def _toggle_visibility(self, edit: QLineEdit, btn: QPushButton):
        """切换敏感字段的显示/隐藏"""
        if edit.echoMode() == QLineEdit.Password:
            edit.setEchoMode(QLineEdit.Normal)
            btn.setText("隐藏")
        else:
            edit.setEchoMode(QLineEdit.Password)
            btn.setText("显示")

    # ================================================================
    # 数据加载与保存
    # ================================================================

    def _load_values(self):
        """将配置值加载到表单字段"""
        if not self._config:
            return
        self._env_path_lbl.setText(f"配置文件: {self._config.env_path}")
        for key, edit in self._field_widgets.items():
            value = self._config.get(key)
            edit.setText(value)
        self._update_theme_hint()

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
            # 保存后刷新切换卡片高亮（URL/模型可能变化）
            self._refresh_preset_active()
        except Exception as e:
            QMessageBox.warning(self, "保存失败", str(e))

    def _on_validate(self):
        """
        仅校验界面当前值，不污染运行缓存。
        通过 ConfigService.validate(updates) 传入临时值副本。
        """
        if not self._config:
            return
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
        self._config.load()
        self._load_values()
        self._refresh_preset_active()
        self._show_banner("已从 .env 文件重新加载", ok=True)

    def _show_banner(self, msg: str, ok: bool = True):
        """显示校验/操作结果横幅"""
        v = self._theme_vars or {}
        color = v.get("success", "#3fb950") if ok else v.get("warning", "#f0883e")
        bg = v.get("success_bg", "#0f2d1a") if ok else v.get("warning_bg", "#2d1a0f")
        border = v.get("success_border", "#3fb95040") if ok else v.get("warning_border", "#f0883e40")
        self._last_banner_state = (msg, ok)
        self._validate_banner.setText(msg)
        self._validate_banner.setStyleSheet(
            f"background:{bg}; border:1px solid {border}; border-radius:8px; "
            f"padding:8px; color:{color}; font-size:12px;"
        )
        self._validate_banner.show()

    # ================================================================
    # 主题
    # ================================================================

    def _update_theme_hint(self):
        if not hasattr(self, "_theme_combo") or not hasattr(self, "_theme_hint_lbl"):
            return
        current = self._theme_combo.currentData()
        if current == "system":
            actual = "深色" if self._theme_mode == "dark" else "浅色"
            self._theme_hint_lbl.setText(f"当前为跟随系统，实际生效外观：{actual}")
        elif current == "dark":
            self._theme_hint_lbl.setText("已固定为深色主题")
        elif current == "light":
            self._theme_hint_lbl.setText("已固定为浅色主题")
        else:
            self._theme_hint_lbl.setText("")

    def _apply_action_button_styles(self):
        for btn, style in (
            (getattr(self, "_btn_save", None), btn_primary(self._theme_tokens)),
            (getattr(self, "_btn_validate", None), btn_subtle(self._theme_tokens)),
            (getattr(self, "_btn_reload", None), btn_subtle(self._theme_tokens)),
        ):
            if btn:
                btn.setStyleSheet(style)
                btn.update()

        for btn in self._visibility_toggle_buttons:
            btn.setStyleSheet(btn_subtle(self._theme_tokens, size="compact"))
            btn.update()

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
        """刷新静态外观：横幅、主题提示、预设卡片、Toggle 开关。"""
        if self._theme_tokens is None:
            return
        if self._last_banner_state and self._validate_banner.isVisible():
            self._show_banner(*self._last_banner_state)
        self._update_theme_hint()
        # 刷新所有预设卡片主题
        for card in self._preset_cards:
            card.apply_tokens(self._theme_tokens)
        self._refresh_preset_active()
        # 刷新渠道面板中的 Toggle 开关主题
        for w in self._field_widgets.values():
            if isinstance(w, _ToggleSwitch):
                w.apply_tokens(self._theme_tokens)

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

    def _load_theme_combo(self):
        """将配置中的主题值同步到 ComboBox 显示"""
        if not self._config:
            return
        current = self._config.get("OPEN_AUTOGLM_THEME") or "system"
        self._theme_combo.blockSignals(True)
        for i in range(self._theme_combo.count()):
            if self._theme_combo.itemData(i) == current:
                self._theme_combo.setCurrentIndex(i)
                break
        self._theme_combo.blockSignals(False)
        self._update_theme_hint()

    def _on_theme_changed(self, index: int):
        """主题下拉变化时立即写入配置并触发主题切换"""
        if not self._config:
            return
        value = self._theme_combo.itemData(index)
        self._update_theme_hint()
        if value:
            self._config.set("OPEN_AUTOGLM_THEME", value)

    def on_page_activated(self):
        self._load_values()
        self._load_theme_combo()
        self._refresh_preset_active()
        # 同步渠道详情面板（页面切换回来时刷新）
        if self._config:
            active = self._config.get_active_channel()
            active_id = active.get("id", "") if active else ""
            self._rebuild_channel_detail(active_id)
