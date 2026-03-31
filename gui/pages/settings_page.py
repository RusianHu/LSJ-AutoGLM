# -*- coding: utf-8 -*-
"""
设置页 - .env 可视化读取与校验、模型/API 参数查看与编辑

变更记录：
- 新增「快捷预设」卡片区域，支持一键切换渠道并持久化到 .env
- 预设卡片显示名称、模型名、标签（原生/第三方），活跃预设高亮
- 监听 config_changed 信号，自动同步活跃预设高亮状态
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QSize, QPropertyAnimation, QEasingCurve, QRect, Property, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QBrush
from PySide6.QtWidgets import (
    QCheckBox,
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
from gui.widgets.action_policy_dialog import ActionPolicyDialog, summarize_action_policy
from gui.utils.runtime import (
    app_root,
    gui_build_script_path,
    gui_onefile_output_path,
    is_frozen,
)
from phone_agent.actions.registry import (
    ActionPolicyInput,
    export_gui_action_groups,
    parse_action_name_collection,
    resolve_action_policy,
)

class _ToggleSwitch(QWidget):
    """
    自绘布尔值拨动开关。
    接口与 QLineEdit 兼容：text() 返回 'true'/'false'，setText() 设置状态。
    """

    toggled = Signal(bool)

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
            self.toggled.emit(self._checked)

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
            self.toggled.emit(self._checked)
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

    def __init__(self, preset: dict, resolved_model: str = "", translator=None, parent=None):
        super().__init__(parent)
        self._preset = preset
        self._resolved_model = resolved_model  # 从 .env 读到的真实模型名
        self._active = False
        self._theme_tokens: ThemeTokens = None
        self._translator = translator
        self._use_thirdparty = bool(self._preset.get("use_thirdparty", False))
        self._build_ui()
        self.setFixedHeight(72)
        self.setCursor(Qt.PointingHandCursor)
        self.setFrameShape(QFrame.StyledPanel)

    def _t(self, key: str, **params) -> str:
        translator = self._translator
        if callable(translator):
            try:
                return translator(key, **params)
            except Exception:
                pass
        try:
            from gui.i18n.locales.cn import CN
            tmpl = CN.get(key, f"[[{key}]]")
            return tmpl.format(**params) if params else tmpl
        except Exception:
            return f"[[{key}]]"

    def set_translator(self, translator) -> None:
        self._translator = translator
        self._refresh_texts()

    def _refresh_texts(self) -> None:
        if hasattr(self, "_tag_lbl"):
            tag_key = (
                "page.settings.preset.tag.thirdparty"
                if self._use_thirdparty else "page.settings.preset.tag.native"
            )
            self._tag_lbl.setText(self._t(tag_key))
        if hasattr(self, "_model_lbl"):
            self.update_model_display(self._resolved_model)

    def set_prompt_mode(self, use_thirdparty: bool | None) -> None:
        self._use_thirdparty = (
            bool(self._preset.get("use_thirdparty", False))
            if use_thirdparty is None
            else bool(use_thirdparty)
        )
        self._refresh_texts()
        self._refresh_style()

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

        model_display = self._resolved_model or self._preset.get("default_model", "") or self._t("page.settings.field.custom")
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

        tag_key = "page.settings.preset.tag.thirdparty" if self._use_thirdparty else "page.settings.preset.tag.native"
        self._tag_lbl = QLabel(self._t(tag_key))
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
        self._resolved_model = model
        display = model or self._preset.get("default_model", "") or self._t("page.settings.field.custom")
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

        tag_color = t.warning if self._use_thirdparty else t.success
        tag_bg = t.warning_bg if self._use_thirdparty else t.success_bg

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
        self._i18n = services.get("i18n")  # I18nManager（可能启动时还未注入）
        self._field_widgets: dict = {}   # key -> QLineEdit
        self._theme_mode = "dark"
        self._theme_tokens = resolve_theme_tokens(self._theme_mode)
        self._theme_vars = self._theme_tokens.to_legacy_dict()
        self._last_banner_state = None
        self._last_banner_i18n = None
        self._visibility_toggle_buttons: list[QPushButton] = []
        self._preset_cards: list[_PresetCard] = []  # 预设卡片列表
        self._action_runtime_checks: dict[str, QCheckBox] = {}
        self._action_ai_checks: dict[str, QCheckBox] = {}
        self._action_matrix_syncing = False
        self._build_ui()
        self._theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        self._lang_combo.currentIndexChanged.connect(self._on_lang_changed)
        self._device_type_combo.currentIndexChanged.connect(self._on_device_type_changed)
        self._apply_action_button_styles()
        self._load_values()
        self._refresh_action_policy_summary()
        self._load_theme_combo()
        self._load_lang_combo()
        self._connect_config_signals()

    # ================================================================
    # i18n 支持
    # ================================================================

    def _t(self, key: str, **params) -> str:
        """便捷翻译方法；优先使用 services 中的 I18nManager，无则回退内置中文。"""
        i18n = getattr(self, "_i18n", None) or self._services.get("i18n")
        if i18n:
            return i18n.t(key, **params)
        try:
            from gui.i18n.locales.cn import CN
            tmpl = CN.get(key, f"[[{key}]]")
            return tmpl.format(**params) if params else tmpl
        except Exception:
            return f"[[{key}]]"

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
        self._refresh_action_policy_summary()

    # ================================================================
    # UI 构建
    # ================================================================

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)

        self._title_lbl = QLabel(self._t("page.settings.title"))
        self._title_lbl.setProperty("role", "pageTitle")
        root.addWidget(self._title_lbl)

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

        # ---- 快速切换渠道 ----
        preset_switch_group = self._build_preset_switch_group()
        scroll_layout.addWidget(preset_switch_group)

        # ---- 模型与 API ----
        self._model_group = QGroupBox(self._t("page.settings.section.model_api"))
        model_form = QFormLayout(self._model_group)
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
        scroll_layout.addWidget(self._model_group)

        # ---- 专家模式 ----
        self._expert_group = QGroupBox("专家模式")
        expert_form = QFormLayout(self._expert_group)
        expert_form.setLabelAlignment(Qt.AlignRight)
        expert_form.setSpacing(10)
        expert_fields = [
            "OPEN_AUTOGLM_EXPERT_MODE",
            "OPEN_AUTOGLM_EXPERT_STRICT_MODE",
            "OPEN_AUTOGLM_EXPERT_BASE_URL",
            "OPEN_AUTOGLM_EXPERT_MODEL",
            "OPEN_AUTOGLM_EXPERT_API_KEY",
            "OPEN_AUTOGLM_EXPERT_PROMPT",
            "OPEN_AUTOGLM_EXPERT_AUTO_INIT",
            "OPEN_AUTOGLM_EXPERT_AUTO_RESCUE",
            "OPEN_AUTOGLM_EXPERT_MANUAL_ACTION",
            "OPEN_AUTOGLM_EXPERT_SCREEN_UNCHANGED_THRESHOLD",
            "OPEN_AUTOGLM_EXPERT_CONSECUTIVE_FAILURE_THRESHOLD",
            "OPEN_AUTOGLM_EXPERT_MAX_RESCUES",
        ]
        self._add_fields(expert_form, expert_fields)
        self._expert_hint_lbl = QLabel("专家提示词留空时，将使用内置默认预设；默认会附带任务、截图、页面状态、动作协议摘要与最近上下文。严格模式启用后，每一步主模型决策前都会先请求一次专家，这会显著增加时延与调用成本。")
        self._expert_hint_lbl.setProperty("role", "subtle")
        self._expert_hint_lbl.setWordWrap(True)
        expert_form.addRow(QLabel("说明:"), self._expert_hint_lbl)
        scroll_layout.addWidget(self._expert_group)

        # ---- 渠道配置（动态，随活跃预设变化）----
        self._channel_group = QGroupBox(self._t("page.settings.section.channel"))
        channel_vbox = QVBoxLayout(self._channel_group)
        channel_vbox.setContentsMargins(12, 16, 12, 8)
        channel_vbox.setSpacing(8)

        self._channel_hint_lbl = QLabel(self._t("page.settings.channel.hint"))
        self._channel_hint_lbl.setProperty("role", "subtle")
        self._channel_hint_lbl.setWordWrap(True)
        channel_vbox.addWidget(self._channel_hint_lbl)

        # 动态内容容器，由 _rebuild_channel_detail() 填充
        self._channel_detail_container = QWidget()
        self._channel_detail_vbox = QVBoxLayout(self._channel_detail_container)
        self._channel_detail_vbox.setContentsMargins(0, 4, 0, 0)
        self._channel_detail_vbox.setSpacing(8)
        channel_vbox.addWidget(self._channel_detail_container)

        scroll_layout.addWidget(self._channel_group)

        # ---- 运行参数 ----
        self._run_group = QGroupBox(self._t("page.settings.section.run_params"))
        run_form = QFormLayout(self._run_group)
        run_form.setLabelAlignment(Qt.AlignRight)
        run_form.setSpacing(10)

        run_fields = [
            "OPEN_AUTOGLM_DEVICE_ID",
            "OPEN_AUTOGLM_MAX_STEPS",
        ]
        self._add_fields(run_form, run_fields)

        self._device_type_combo = QComboBox()
        self._device_type_combo.addItem(self._t("page.settings.device_type.adb"), "adb")
        self._device_type_combo.addItem(self._t("page.settings.device_type.hdc"), "hdc")
        self._device_type_combo.addItem(self._t("page.settings.device_type.ios"), "ios")
        self._device_type_combo.setMinimumWidth(160)
        self._device_type_label = QLabel(self._t("page.settings.device_type.label"))
        run_form.addRow(self._device_type_label, self._device_type_combo)

        # 语言选择 - 专用 ComboBox（不再是自由文本）
        self._lang_combo = QComboBox()
        self._lang_combo.addItem(self._t("page.settings.lang.cn"), "cn")
        self._lang_combo.addItem(self._t("page.settings.lang.en"), "en")
        self._lang_combo.setMinimumWidth(160)
        self._lang_label = QLabel(self._t("page.settings.lang.label"))
        run_form.addRow(self._lang_label, self._lang_combo)

        scroll_layout.addWidget(self._run_group)

        # ---- 动作策略 ----
        self._action_policy_group = QGroupBox(self._t("page.settings.section.action_policy"))
        action_vbox = QVBoxLayout(self._action_policy_group)
        action_vbox.setContentsMargins(14, 18, 14, 14)
        action_vbox.setSpacing(12)

        self._action_policy_hint_lbl = QLabel(self._t("page.settings.action_policy.relocated_hint"))
        self._action_policy_hint_lbl.setProperty("role", "subtle")
        self._action_policy_hint_lbl.setWordWrap(True)
        action_vbox.addWidget(self._action_policy_hint_lbl)

        self._action_policy_summary_card = QFrame()
        self._action_policy_summary_card.setObjectName("SettingsActionPolicySummaryCard")
        summary_vbox = QVBoxLayout(self._action_policy_summary_card)
        summary_vbox.setContentsMargins(14, 12, 14, 12)
        summary_vbox.setSpacing(6)

        self._action_policy_summary_title = QLabel(self._t("page.settings.action_policy.summary_title"))
        self._action_policy_summary_title.setObjectName("SettingsActionPolicySummaryTitle")
        summary_vbox.addWidget(self._action_policy_summary_title)

        self._action_policy_summary_lbl = QLabel(self._t("page.settings.action_policy.summary_empty"))
        self._action_policy_summary_lbl.setObjectName("SettingsActionPolicySummaryText")
        self._action_policy_summary_lbl.setWordWrap(True)
        summary_vbox.addWidget(self._action_policy_summary_lbl)

        self._action_policy_status_lbl = QLabel("")
        self._action_policy_status_lbl.setProperty("role", "subtle")
        self._action_policy_status_lbl.setWordWrap(True)
        self._action_policy_status_lbl.hide()
        summary_vbox.addWidget(self._action_policy_status_lbl)
        action_vbox.addWidget(self._action_policy_summary_card)

        self._action_button_strip = QFrame()
        self._action_button_strip.setObjectName("SettingsActionPolicyButtonStrip")
        action_btn_row = QHBoxLayout(self._action_button_strip)
        action_btn_row.setContentsMargins(12, 12, 12, 12)
        action_btn_row.setSpacing(8)

        self._btn_action_open_dialog = QPushButton(self._t("page.settings.action_policy.btn.open_dialog"))
        self._btn_action_open_dialog.setProperty("variant", "primary")
        self._btn_action_open_dialog.clicked.connect(self._open_action_policy_dialog)
        action_btn_row.addWidget(self._btn_action_open_dialog)

        self._btn_action_open_workspace = QPushButton(self._t("page.settings.action_policy.btn.open_workspace"))
        self._btn_action_open_workspace.setProperty("variant", "subtle")
        self._btn_action_open_workspace.clicked.connect(self._open_dashboard_page)
        action_btn_row.addWidget(self._btn_action_open_workspace)

        self._btn_action_reset_defaults = QPushButton(self._t("page.settings.actions.btn.reset_defaults"))
        self._btn_action_reset_defaults.setProperty("variant", "subtle")
        self._btn_action_reset_defaults.clicked.connect(self._on_action_policy_reset_defaults)
        action_btn_row.addWidget(self._btn_action_reset_defaults)

        self._btn_action_select_all = QPushButton(self._t("page.settings.actions.btn.select_all"))
        self._btn_action_select_all.setProperty("variant", "subtle")
        self._btn_action_select_all.clicked.connect(self._on_action_policy_select_all)
        action_btn_row.addWidget(self._btn_action_select_all)

        self._btn_action_clear_all = QPushButton(self._t("page.settings.actions.btn.clear_all"))
        self._btn_action_clear_all.setProperty("variant", "subtle")
        self._btn_action_clear_all.clicked.connect(self._on_action_policy_clear_all)
        action_btn_row.addWidget(self._btn_action_clear_all)
        action_btn_row.addStretch(1)
        action_vbox.addWidget(self._action_button_strip)

        action_form = QFormLayout()
        action_form.setLabelAlignment(Qt.AlignRight)
        action_form.setSpacing(10)
        action_fields = [
            "OPEN_AUTOGLM_ACTION_POLICY_VERSION",
            "OPEN_AUTOGLM_USE_PLATFORM_DEFAULT_ACTIONS",
        ]
        self._add_fields(action_form, action_fields)
        action_vbox.addLayout(action_form)

        self._action_matrix_container = QWidget()
        self._action_matrix_container.hide()
        self._action_matrix_vbox = QVBoxLayout(self._action_matrix_container)
        self._action_matrix_vbox.setContentsMargins(0, 4, 0, 0)
        self._action_matrix_vbox.setSpacing(10)
        action_vbox.addWidget(self._action_matrix_container)

        scroll_layout.addWidget(self._action_policy_group)

        # ---- 外观 ----
        self._appearance_group = QGroupBox(self._t("page.settings.section.appearance"))
        appearance_form = QFormLayout(self._appearance_group)
        appearance_form.setLabelAlignment(Qt.AlignRight)
        appearance_form.setSpacing(10)

        self._theme_combo = QComboBox()
        self._theme_combo.addItem(self._t("page.settings.theme.system"), "system")
        self._theme_combo.addItem(self._t("page.settings.theme.dark"), "dark")
        self._theme_combo.addItem(self._t("page.settings.theme.light"), "light")
        self._theme_combo.setMinimumWidth(160)
        self._theme_label = QLabel(self._t("page.settings.theme.label"))
        appearance_form.addRow(self._theme_label, self._theme_combo)

        self._theme_hint_lbl = QLabel("")
        self._theme_hint_lbl.setWordWrap(True)
        self._theme_hint_lbl.setProperty("role", "subtle")
        self._theme_effect_label = QLabel(self._t("page.settings.theme.effect_label"))
        appearance_form.addRow(self._theme_effect_label, self._theme_hint_lbl)
        scroll_layout.addWidget(self._appearance_group)

        # ---- 构建与脚本 ----
        build_group = self._build_build_tools_group()
        scroll_layout.addWidget(build_group)

        scroll_layout.addStretch(1)

        # 底部操作按钮
        btn_row = QHBoxLayout()
        self._btn_save = QPushButton(self._t("page.settings.btn.save"))
        self._btn_save.setProperty("variant", "primary")
        self._btn_save.clicked.connect(self._on_save)
        btn_row.addWidget(self._btn_save)

        self._btn_validate = QPushButton(self._t("page.settings.btn.validate"))
        self._btn_validate.setProperty("variant", "subtle")
        self._btn_validate.clicked.connect(self._on_validate)
        btn_row.addWidget(self._btn_validate)

        self._btn_reload = QPushButton(self._t("page.settings.btn.reload"))
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
    # 快速切换渠道卡片区
    # ----------------------------------------------------------------

    def _build_preset_switch_group(self) -> QGroupBox:
        """构建快速切换渠道卡片组"""
        self._quick_switch_group = QGroupBox(self._t("page.settings.section.quick_switch"))
        group = self._quick_switch_group
        outer = QVBoxLayout(group)
        outer.setContentsMargins(12, 16, 12, 12)
        outer.setSpacing(8)

        self._preset_hint_lbl = QLabel(self._t("page.settings.preset.hint"))
        hint = self._preset_hint_lbl
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
            card = _PresetCard(preset, resolved_model=resolved_model, translator=self._t)
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
                "",
                ok=True,
                i18n_key="page.settings.banner.switch_ok",
                i18n_params={"name": preset.get("name", channel_id)},
            )
        else:
            self._show_banner(
                "",
                ok=False,
                i18n_key="page.settings.banner.switch_fail",
                i18n_params={"channel": channel_id},
            )

    def _refresh_preset_active(self):
        """根据当前配置高亮匹配的预设卡片，并同步更新各卡片显示的真实模型名"""
        if not self._config or not self._preset_cards:
            return
        active = self._config.get_active_channel()
        active_id = active.get("id", "") if active else ""
        current_thirdparty = self._current_thirdparty_prompt_enabled()
        for card in self._preset_cards:
            # 每次都从 .env 读取该预设的实际模型名（用户可能已在设置页修改）
            resolved_model = self._config.get_preset_model(card._preset)
            card.update_model_display(resolved_model)
            is_active = card._preset.get("id") == active_id
            card.set_prompt_mode(
                current_thirdparty if is_active else card._preset.get("use_thirdparty", False)
            )
            card.set_active(is_active, self._theme_tokens)

        # 更新提示文字
        if hasattr(self, "_active_preset_lbl"):
            if active and active_id != "custom":
                model = self._config.get_preset_model(active) or active.get("default_model", "")
                self._active_preset_lbl.setText(
                    self._t(
                        "page.settings.active.channel",
                        name=active.get("name", active_id),
                        model=model,
                    )
                )
            else:
                url = self._config.get("OPEN_AUTOGLM_BASE_URL") or ""
                model = self._config.get("OPEN_AUTOGLM_MODEL") or ""
                self._active_preset_lbl.setText(
                    self._t(
                        "page.settings.active.custom",
                        url=url,
                        model=model,
                    )
                )

    # ================================================================
    # 构建与脚本
    # ================================================================

    def _build_build_tools_group(self) -> QGroupBox:
        self._build_tools_group = QGroupBox(self._t("page.settings.section.build_tools"))
        group = self._build_tools_group
        outer = QVBoxLayout(group)
        outer.setContentsMargins(12, 16, 12, 12)
        outer.setSpacing(8)

        self._build_hint_lbl = QLabel(self._t("page.settings.build.hint"))
        self._build_hint_lbl.setProperty("role", "subtle")
        self._build_hint_lbl.setWordWrap(True)
        outer.addWidget(self._build_hint_lbl)

        self._build_mode_lbl = QLabel("")
        self._build_root_lbl = QLabel("")
        self._build_script_lbl = QLabel("")
        self._build_output_lbl = QLabel("")
        for label in (
            self._build_mode_lbl,
            self._build_root_lbl,
            self._build_script_lbl,
            self._build_output_lbl,
        ):
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            outer.addWidget(label)

        btn_row = QHBoxLayout()
        self._btn_run_build = QPushButton(self._t("page.settings.build.btn.run"))
        self._btn_run_build.setProperty("variant", "primary")
        self._btn_run_build.clicked.connect(self._on_run_build_script)
        btn_row.addWidget(self._btn_run_build)

        self._btn_open_scripts_dir = QPushButton(self._t("page.settings.build.btn.open_scripts"))
        self._btn_open_scripts_dir.setProperty("variant", "subtle")
        self._btn_open_scripts_dir.clicked.connect(self._on_open_scripts_dir)
        btn_row.addWidget(self._btn_open_scripts_dir)

        self._btn_open_dist_dir = QPushButton(self._t("page.settings.build.btn.open_dist"))
        self._btn_open_dist_dir.setProperty("variant", "subtle")
        self._btn_open_dist_dir.clicked.connect(self._on_open_dist_dir)
        btn_row.addWidget(self._btn_open_dist_dir)

        btn_row.addStretch(1)
        outer.addLayout(btn_row)

        self._refresh_build_paths()
        return group

    def _refresh_build_paths(self):
        mode_key = "page.settings.build.mode.frozen" if is_frozen() else "page.settings.build.mode.source"
        root_path = app_root().resolve()
        script_path = gui_build_script_path().resolve()
        output_path = gui_onefile_output_path().resolve()

        if hasattr(self, "_build_mode_lbl"):
            self._build_mode_lbl.setText(
                self._t("page.settings.build.mode", mode=self._t(mode_key))
            )
        if hasattr(self, "_build_root_lbl"):
            self._build_root_lbl.setText(
                self._t("page.settings.build.root", path=str(root_path))
            )
        if hasattr(self, "_build_script_lbl"):
            self._build_script_lbl.setText(
                self._t("page.settings.build.script", path=str(script_path))
            )
        if hasattr(self, "_build_output_lbl"):
            self._build_output_lbl.setText(
                self._t("page.settings.build.output", path=str(output_path))
            )

    def _open_in_shell(self, path: Path, *, select_file: bool = False, ensure_dir: bool = False):
        target = Path(path)
        if ensure_dir:
            target.mkdir(parents=True, exist_ok=True)

        open_target = target
        if target.suffix and not target.exists():
            open_target = target.parent

        if os.name == "nt":
            if select_file and target.exists():
                subprocess.Popen(["explorer", f"/select,{target}"])
            else:
                os.startfile(str(open_target))
            return

        opener = ["xdg-open", str(open_target)]
        if sys.platform == "darwin":
            opener = ["open", str(open_target)]
        subprocess.Popen(opener)

    def _on_run_build_script(self):
        script_path = gui_build_script_path().resolve()
        if not script_path.exists():
            self._show_banner(
                "",
                ok=False,
                i18n_key="page.settings.build.banner.script_missing",
                i18n_params={"path": str(script_path)},
            )
            return

        try:
            subprocess.Popen(
                ["cmd", "/c", "start", "", str(script_path)],
                cwd=str(app_root()),
                autoglm_allow_console=True,
            )
            self._show_banner(
                "",
                ok=True,
                i18n_key="page.settings.build.banner.started",
            )
        except Exception as e:
            self._show_banner(
                "",
                ok=False,
                i18n_key="page.settings.build.banner.start_failed",
                i18n_params={"error": str(e)},
            )

    def _on_open_scripts_dir(self):
        self._open_in_shell(gui_build_script_path().resolve().parent, ensure_dir=True)

    def _on_open_dist_dir(self):
        output_path = gui_onefile_output_path().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self._open_in_shell(output_path, select_file=True, ensure_dir=True)

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
                hint_text = self._t("page.settings.channel.detail.shared_only")
            else:
                hint_text = self._t("page.settings.channel.detail.none")
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
                if key == "OPEN_AUTOGLM_USE_THIRDPARTY_PROMPT":
                    try:
                        edit.toggled.connect(lambda _checked: self._refresh_preset_active())
                    except Exception:
                        pass
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
                    toggle_btn = QPushButton(self._t("page.settings.btn.show"))
                    toggle_btn.setFixedWidth(48)
                    toggle_btn.setProperty("variant", "subtle")
                    toggle_btn.setProperty("sensitiveVisible", False)
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
            btn.setProperty("sensitiveVisible", True)
            btn.setText(self._t("page.settings.btn.hide"))
        else:
            edit.setEchoMode(QLineEdit.Password)
            btn.setProperty("sensitiveVisible", False)
            btn.setText(self._t("page.settings.btn.show"))

    @staticmethod
    def _resolve_i18n_fallback(text: str, fallback: str) -> str:
        if text.startswith("[[") and text.endswith("]]"):
            return fallback
        return text

    def _tr_or(self, key: str, fallback: str, **params) -> str:
        if not key:
            return fallback
        return self._resolve_i18n_fallback(self._t(key, **params), fallback)

    def _current_device_type(self) -> str:
        if hasattr(self, "_device_type_combo"):
            current = self._device_type_combo.currentData()
            if current:
                return str(current)
        if self._config:
            return (self._config.get("OPEN_AUTOGLM_DEVICE_TYPE") or "adb").strip().lower()
        return "adb"

    @staticmethod
    def _is_truthy_text(value: object) -> bool:
        return str(value).strip().lower() in ("1", "true", "yes", "on")

    def _current_use_platform_defaults(self) -> bool:
        toggle_widget = self._field_widgets.get("OPEN_AUTOGLM_USE_PLATFORM_DEFAULT_ACTIONS")
        if toggle_widget is not None:
            return self._is_truthy_text(toggle_widget.text())
        if self._config:
            return self._is_truthy_text(
                self._config.get("OPEN_AUTOGLM_USE_PLATFORM_DEFAULT_ACTIONS", "true")
            )
        return True

    def _current_thirdparty_prompt_enabled(self) -> bool:
        toggle_widget = self._field_widgets.get("OPEN_AUTOGLM_USE_THIRDPARTY_PROMPT")
        if toggle_widget is not None:
            return self._is_truthy_text(toggle_widget.text())
        if self._config:
            return self._is_truthy_text(
                self._config.get("OPEN_AUTOGLM_USE_THIRDPARTY_PROMPT", "false")
            )
        return False

    def _build_action_policy_updates(
        self,
        *,
        use_platform_defaults: bool | None = None,
    ) -> dict[str, str]:
        if use_platform_defaults is None:
            use_platform_defaults = self._current_use_platform_defaults()

        updates = {
            "OPEN_AUTOGLM_DEVICE_TYPE": self._current_device_type(),
            "OPEN_AUTOGLM_USE_PLATFORM_DEFAULT_ACTIONS": (
                "true" if use_platform_defaults else "false"
            ),
        }
        if use_platform_defaults:
            updates["OPEN_AUTOGLM_ENABLED_ACTIONS"] = ""
            updates["OPEN_AUTOGLM_AI_VISIBLE_ACTIONS"] = ""
        else:
            updates.update(self._collect_action_policy_updates())
        return updates

    def _load_device_type_combo(self):
        if not self._config or not hasattr(self, "_device_type_combo"):
            return
        current = (self._config.get("OPEN_AUTOGLM_DEVICE_TYPE") or "adb").strip().lower()
        self._device_type_combo.blockSignals(True)
        for i in range(self._device_type_combo.count()):
            if self._device_type_combo.itemData(i) == current:
                self._device_type_combo.setCurrentIndex(i)
                break
        self._device_type_combo.blockSignals(False)
        self._rebuild_action_policy_matrix(current)

    def _resolve_action_policy_for_platform(self, platform: str):
        if not self._config:
            return resolve_action_policy(platform)

        settings = self._config.get_action_policy_settings()
        enabled_actions = None
        ai_visible_actions = None

        try:
            if settings.get("enabled_actions"):
                enabled_actions = parse_action_name_collection(settings["enabled_actions"])
            if settings.get("ai_visible_actions"):
                ai_visible_actions = parse_action_name_collection(settings["ai_visible_actions"])
        except ValueError:
            enabled_actions = None
            ai_visible_actions = None

        return resolve_action_policy(
            platform,
            ActionPolicyInput(
                ai_visible_actions=ai_visible_actions,
                runtime_enabled_actions=enabled_actions,
                policy_version=int(settings.get("policy_version", 1) or 1),
                use_platform_defaults=bool(settings.get("use_platform_defaults", True)),
            ),
        )

    def _parse_action_policy_names(self, value: object) -> tuple[str, ...]:
        try:
            parsed = parse_action_name_collection(value)
        except ValueError:
            return ()
        return parsed or ()

    def _set_action_policy_check_states(
        self,
        runtime_actions: tuple[str, ...] | list[str],
        ai_visible_actions: tuple[str, ...] | list[str],
    ) -> None:
        runtime_set = set(runtime_actions)
        ai_visible_set = set(ai_visible_actions)
        self._action_matrix_syncing = True
        try:
            for action_name, runtime_checkbox in self._action_runtime_checks.items():
                runtime_checkbox.setChecked(action_name in runtime_set)
            for action_name, ai_checkbox in self._action_ai_checks.items():
                enabled = action_name in runtime_set
                ai_checkbox.setEnabled(enabled)
                ai_checkbox.setChecked(enabled and action_name in ai_visible_set)
        finally:
            self._action_matrix_syncing = False

    def _update_action_policy_compatibility_hint(self, platform: str, resolved_policy=None) -> None:
        label = getattr(self, "_action_policy_status_lbl", None)
        if label is None:
            return
        if not self._config:
            label.clear()
            label.hide()
            return

        settings = self._config.get_action_policy_settings()
        resolved = resolved_policy or self._resolve_action_policy_for_platform(platform)
        supported_actions = set(resolved.supported_actions)
        incompatible_actions: list[str] = []

        for raw_value in (settings.get("enabled_actions"), settings.get("ai_visible_actions")):
            for action_name in self._parse_action_policy_names(raw_value):
                if action_name not in supported_actions and action_name not in incompatible_actions:
                    incompatible_actions.append(action_name)

        if incompatible_actions:
            label.setText(
                self._t(
                    "page.settings.actions.compatibility.filtered",
                    actions=", ".join(incompatible_actions),
                )
            )
            label.show()
            return

        label.clear()
        label.hide()

    def _persist_action_policy_updates(self, *, use_platform_defaults: bool | None = None) -> None:
        if not self._config:
            return

        toggle_widget = self._field_widgets.get("OPEN_AUTOGLM_USE_PLATFORM_DEFAULT_ACTIONS")
        if use_platform_defaults is None:
            use_platform_defaults = self._current_use_platform_defaults()

        updates = self._build_action_policy_updates(
            use_platform_defaults=use_platform_defaults
        )

        if toggle_widget is not None:
            toggle_widget.setText(updates["OPEN_AUTOGLM_USE_PLATFORM_DEFAULT_ACTIONS"])

        try:
            self._config.set_many(updates)
            self._refresh_action_policy_summary()
        except Exception as e:
            QMessageBox.warning(self, self._t("page.settings.dialog.save_fail"), str(e))
            self._load_values()

    def _on_action_policy_reset_defaults(self):
        current_platform = self._current_device_type()
        resolved_policy = resolve_action_policy(current_platform)
        self._set_action_policy_check_states(
            resolved_policy.runtime_enabled_actions,
            resolved_policy.ai_visible_actions,
        )
        self._persist_action_policy_updates(use_platform_defaults=True)

    def _on_action_policy_select_all(self):
        all_actions = tuple(self._action_runtime_checks.keys())
        self._set_action_policy_check_states(all_actions, all_actions)
        self._persist_action_policy_updates(use_platform_defaults=False)

    def _on_action_policy_clear_all(self):
        self._set_action_policy_check_states((), ())
        self._persist_action_policy_updates(use_platform_defaults=False)

    def _refresh_action_policy_summary(self) -> None:
        if not hasattr(self, "_action_policy_summary_lbl"):
            return
        if not self._config:
            self._action_policy_summary_lbl.setText(self._t("page.settings.action_policy.summary_empty"))
            return
        summary = summarize_action_policy(self._config, self._t, platform=self._current_device_type())
        self._action_policy_summary_lbl.setText(
            self._t(
                "page.settings.action_policy.summary_text",
                platform=summary.get("platform", "adb").upper(),
                mode=summary.get("mode_text", ""),
                runtime=summary.get("runtime_count", 0),
                ai_visible=summary.get("ai_count", 0),
                supported=summary.get("supported_count", 0),
            )
        )

    def _open_dashboard_page(self):
        navigator = self._services.get("navigate_to_page")
        if callable(navigator):
            navigator("dashboard")

    def _open_action_policy_dialog(self):
        dialog = ActionPolicyDialog(self._services, parent=self)
        theme_manager = self._services.get("theme_manager")
        if theme_manager is not None and hasattr(dialog, "bind_theme_manager"):
            dialog.bind_theme_manager(theme_manager)
        dialog.exec()
        self._refresh_action_policy_summary()

    def _on_device_type_changed(self, index: int):
        if not hasattr(self, "_device_type_combo"):
            return
        platform = str(self._device_type_combo.itemData(index) or "adb")
        self._rebuild_action_policy_matrix(platform)
        if not self._config:
            return
        current_saved = (self._config.get("OPEN_AUTOGLM_DEVICE_TYPE") or "adb").strip().lower()
        if current_saved == platform.strip().lower():
            return
        self._persist_action_policy_updates(
            use_platform_defaults=self._current_use_platform_defaults()
        )

    def _on_runtime_action_toggled(self, action_name: str, checked: bool):
        ai_widget = self._action_ai_checks.get(action_name)
        if ai_widget is None or self._action_matrix_syncing:
            return
        self._action_matrix_syncing = True
        try:
            ai_widget.setEnabled(checked)
            if not checked:
                ai_widget.setChecked(False)
        finally:
            self._action_matrix_syncing = False
        self._persist_action_policy_updates(use_platform_defaults=False)

    def _on_ai_action_toggled(self, action_name: str, checked: bool):
        if self._action_matrix_syncing:
            return
        runtime_widget = self._action_runtime_checks.get(action_name)
        if checked and runtime_widget is not None and not runtime_widget.isChecked():
            self._action_matrix_syncing = True
            try:
                runtime_widget.setChecked(True)
            finally:
                self._action_matrix_syncing = False
        self._persist_action_policy_updates(use_platform_defaults=False)

    def _collect_action_policy_updates(self) -> dict[str, str]:
        runtime_actions = [
            name for name, checkbox in self._action_runtime_checks.items() if checkbox.isChecked()
        ]
        ai_visible_actions = [
            name for name, checkbox in self._action_ai_checks.items() if checkbox.isChecked()
        ]
        return {
            "OPEN_AUTOGLM_ENABLED_ACTIONS": json.dumps(runtime_actions, ensure_ascii=False),
            "OPEN_AUTOGLM_AI_VISIBLE_ACTIONS": json.dumps(ai_visible_actions, ensure_ascii=False),
        }

    def _rebuild_action_policy_matrix(self, platform: str = ""):
        container = getattr(self, "_action_matrix_container", None)
        vbox = getattr(self, "_action_matrix_vbox", None)
        if container is None or vbox is None:
            return

        self._action_runtime_checks.clear()
        self._action_ai_checks.clear()

        while vbox.count():
            item = vbox.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        current_platform = (platform or self._current_device_type() or "adb").strip().lower()
        groups = export_gui_action_groups(current_platform)
        resolved_policy = self._resolve_action_policy_for_platform(current_platform)
        self._update_action_policy_compatibility_hint(current_platform, resolved_policy)

        for btn in (
            getattr(self, "_btn_action_reset_defaults", None),
            getattr(self, "_btn_action_select_all", None),
            getattr(self, "_btn_action_clear_all", None),
        ):
            if btn is not None:
                btn.setEnabled(bool(groups))

        if not groups:
            hint = QLabel(self._t("page.settings.actions.none"))
            hint.setProperty("role", "subtle")
            hint.setWordWrap(True)
            vbox.addWidget(hint)
            return

        for group in groups:
            category_box = QGroupBox(
                self._tr_or(group.get("category_i18n_key", ""), group.get("category_label", ""))
            )
            category_vbox = QVBoxLayout(category_box)
            category_vbox.setContentsMargins(10, 12, 10, 10)
            category_vbox.setSpacing(8)

            for item in group.get("items", ()):
                action_name = item.get("name", "")
                row = QWidget()
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(12)

                text_layout = QVBoxLayout()
                text_layout.setContentsMargins(0, 0, 0, 0)
                text_layout.setSpacing(2)

                label_text = self._tr_or(item.get("label_i18n_key", ""), item.get("label", action_name))
                desc_text = self._tr_or(item.get("description_i18n_key", ""), item.get("description", ""))
                risk_text = self._tr_or(item.get("risk_i18n_key", ""), item.get("risk_level", ""))

                title_lbl = QLabel(label_text)
                title_lbl.setStyleSheet("font-weight: 600;")
                text_layout.addWidget(title_lbl)

                desc_parts = [part for part in (desc_text, f"[{risk_text}]" if risk_text else "") if part]
                desc_lbl = QLabel(" ".join(desc_parts))
                desc_lbl.setProperty("role", "subtle")
                desc_lbl.setWordWrap(True)
                text_layout.addWidget(desc_lbl)

                row_layout.addLayout(text_layout, 1)

                check_widget = QWidget()
                check_layout = QHBoxLayout(check_widget)
                check_layout.setContentsMargins(0, 0, 0, 0)
                check_layout.setSpacing(16)

                runtime_checkbox = QCheckBox(self._t("page.settings.actions.columns.runtime"))
                ai_checkbox = QCheckBox(self._t("page.settings.actions.columns.ai_visible"))
                runtime_checkbox.setChecked(action_name in resolved_policy.runtime_enabled_actions)
                ai_checkbox.setChecked(action_name in resolved_policy.ai_visible_actions)
                ai_checkbox.setEnabled(runtime_checkbox.isChecked())

                runtime_checkbox.toggled.connect(
                    lambda checked, name=action_name: self._on_runtime_action_toggled(name, checked)
                )
                ai_checkbox.toggled.connect(
                    lambda checked, name=action_name: self._on_ai_action_toggled(name, checked)
                )

                self._action_runtime_checks[action_name] = runtime_checkbox
                self._action_ai_checks[action_name] = ai_checkbox

                check_layout.addWidget(runtime_checkbox)
                check_layout.addWidget(ai_checkbox)
                row_layout.addWidget(check_widget, 0, Qt.AlignRight | Qt.AlignVCenter)

                category_vbox.addWidget(row)

            vbox.addWidget(category_box)

        vbox.addStretch(1)

    # ================================================================
    # 数据加载与保存
    # ================================================================

    def _load_values(self):
        """将配置值加载到表单字段"""
        if not self._config:
            return
        self._env_path_lbl.setText(self._t("page.settings.env_path_label", path=self._config.env_path))
        for key, edit in self._field_widgets.items():
            value = self._config.get(key)
            edit.setText(value)
        self._load_lang_combo()
        self._load_device_type_combo()
        self._show_env_status_banner_if_needed()
        self._update_theme_hint()
        self._refresh_build_paths()

    def _show_env_status_banner_if_needed(self):
        """根据 .env 当前状态显示首次运行提示。"""
        if not self._config:
            return

        getter = getattr(self._config, "get_env_file_status", None)
        if not callable(getter):
            return

        try:
            status = getter()
        except Exception:
            return

        if status.get("bootstrap_error"):
            self._show_banner(
                self._t("page.settings.env_status.bootstrap_failed", path=status.get("path", ""), error=status.get("bootstrap_error", "")),
                ok=False,
            )
            return

        if status.get("exists") and not status.get("writable"):
            self._show_banner(
                self._t("page.settings.env_status.readonly", path=status.get("path", "")),
                ok=False,
            )
            return

    def _sync_active_channel_updates(self, updates: dict) -> dict:
        """
        将“模型与 API”区当前保存值同步回当前活动渠道的专属 .env 字段。

        目的：
        - 点击“快速切换渠道”卡片时，读取的是该渠道上次保存到 .env 的值
        - 避免保存后再次点击卡片，又被旧预设值/默认值覆盖
        - 若当前渠道在下方面板展示了专属 Key 字段，则优先采用用户刚编辑的专属值
        """
        if not self._config:
            return updates

        active = self._config.get_active_channel()
        active_id = active.get("id", "") if active else ""
        if not active_id or active_id == "custom":
            return updates

        preset = next(
            (p for p in self._config.CHANNEL_PRESETS if p["id"] == active_id), None
        )
        if preset is None:
            return updates

        merged_updates = dict(updates)

        def _sync_key_pair(global_key: str, channel_key: str):
            if not channel_key:
                return
            old_global = self._config.get(global_key) or ""
            old_channel = self._config.get(channel_key) or ""
            new_global = merged_updates.get(global_key, old_global)
            new_channel = merged_updates.get(channel_key, old_channel)
            channel_field_visible = channel_key in self._field_widgets

            if channel_field_visible and new_channel != old_channel and new_global == old_global:
                merged_updates[global_key] = new_channel
                return
            if channel_field_visible and new_channel != old_channel and new_global != new_channel:
                merged_updates[global_key] = new_channel
                merged_updates[channel_key] = new_channel
                return
            if new_global != old_global:
                merged_updates[channel_key] = new_global

        _sync_key_pair(
            "OPEN_AUTOGLM_API_KEY",
            (preset.get("api_key_field") or "").strip(),
        )
        _sync_key_pair(
            "OPEN_AUTOGLM_BACKUP_API_KEY",
            (preset.get("backup_api_key_field") or "").strip(),
        )

        merged_updates.update(self._config.build_channel_updates(active_id, merged_updates))
        return merged_updates

    def _on_save(self):
        """收集界面值，批量写入（只写一次文件），失败时全量回滚"""
        if not self._config:
            return
        updates = {
            key: edit.text().strip()
            for key, edit in self._field_widgets.items()
        }
        if hasattr(self, "_device_type_combo"):
            updates["OPEN_AUTOGLM_DEVICE_TYPE"] = self._device_type_combo.currentData() or "adb"
        # 将语言下拉选择单独合并进 updates
        if hasattr(self, "_lang_combo"):
            updates["OPEN_AUTOGLM_LANG"] = self._lang_combo.currentData() or "cn"
        updates.update(self._build_action_policy_updates())

        updates = self._sync_active_channel_updates(updates)

        # 先做校验（不污染缓存）
        errors = self._config.validate(updates)
        if errors:
            msgs = "\n".join(f"• {k}: {v}" for k, v in errors)
            QMessageBox.warning(self, self._t("page.settings.dialog.validate_fail"), msgs)
            return
        try:
            self._config.set_many(updates)
            self._show_banner(
                "",
                ok=True,
                i18n_key="page.settings.banner.saved_env",
            )
            # 保存后刷新切换卡片高亮（URL/模型可能变化）
            self._refresh_preset_active()
            # 语言保存后立即切换 GUI 语言
            new_lang = updates.get("OPEN_AUTOGLM_LANG", "cn")
            i18n = self._i18n or self._services.get("i18n")
            if i18n:
                i18n.set_language(new_lang)
        except Exception as e:
            QMessageBox.warning(self, self._t("page.settings.dialog.save_fail"), str(e))

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
        if hasattr(self, "_device_type_combo"):
            temp_values["OPEN_AUTOGLM_DEVICE_TYPE"] = self._device_type_combo.currentData() or "adb"
        if hasattr(self, "_lang_combo"):
            temp_values["OPEN_AUTOGLM_LANG"] = self._lang_combo.currentData() or "cn"
        temp_values.update(self._build_action_policy_updates())
        errors = self._config.validate(temp_values)
        if not errors:
            self._show_banner(
                "",
                ok=True,
                i18n_key="page.settings.banner.validate_ok",
            )
        else:
            msgs = "\n".join(f"• {k}: {v}" for k, v in errors)
            self._show_banner(
                "",
                ok=False,
                i18n_key="page.settings.banner.validate_fail_msg",
                i18n_params={"msgs": msgs},
            )

    def _on_reload(self):
        """从磁盘重新加载 .env"""
        if not self._config:
            return
        self._config.load()
        self._load_values()
        self._refresh_preset_active()

        getter = getattr(self._config, "get_env_file_status", None)
        status = getter() if callable(getter) else {}
        if status.get("bootstrap_error"):
            self._show_banner(
                self._t(
                    "page.settings.env_status.bootstrap_failed",
                    path=status.get("path", ""),
                    error=status.get("bootstrap_error", ""),
                ),
                ok=False,
            )
            return
        if status.get("exists") and not status.get("writable"):
            self._show_banner(
                self._t("page.settings.env_status.readonly", path=status.get("path", "")),
                ok=False,
            )
            return

        self._show_banner(
            "",
            ok=True,
            i18n_key="page.settings.banner.reloaded",
        )

    def _show_banner(
        self,
        msg: str,
        ok: bool = True,
        *,
        i18n_key: str = "",
        i18n_params: dict | None = None,
    ):
        """显示校验/操作结果横幅。"""
        if i18n_key:
            params = i18n_params or {}
            msg = self._t(i18n_key, **params)
            self._last_banner_i18n = (i18n_key, params)
        else:
            self._last_banner_i18n = None
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
            actual_key = "page.settings.theme.dark" if self._theme_mode == "dark" else "page.settings.theme.light"
            actual = self._t(actual_key)
            self._theme_hint_lbl.setText(self._t("page.settings.theme.hint.system", actual=actual))
        elif current == "dark":
            self._theme_hint_lbl.setText(self._t("page.settings.theme.hint.dark"))
        elif current == "light":
            self._theme_hint_lbl.setText(self._t("page.settings.theme.hint.light"))
        else:
            self._theme_hint_lbl.setText("")

    def _apply_action_button_styles(self):
        for btn, style in (
            (getattr(self, "_btn_save", None), btn_primary(self._theme_tokens)),
            (getattr(self, "_btn_validate", None), btn_subtle(self._theme_tokens)),
            (getattr(self, "_btn_reload", None), btn_subtle(self._theme_tokens)),
            (getattr(self, "_btn_run_build", None), btn_primary(self._theme_tokens)),
            (getattr(self, "_btn_open_scripts_dir", None), btn_subtle(self._theme_tokens)),
            (getattr(self, "_btn_open_dist_dir", None), btn_subtle(self._theme_tokens)),
            (getattr(self, "_btn_action_reset_defaults", None), btn_subtle(self._theme_tokens)),
            (getattr(self, "_btn_action_select_all", None), btn_subtle(self._theme_tokens)),
            (getattr(self, "_btn_action_clear_all", None), btn_subtle(self._theme_tokens)),
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
        t = self._theme_tokens
        if self._last_banner_state and self._validate_banner.isVisible():
            msg, ok = self._last_banner_state
            if self._last_banner_i18n:
                key, params = self._last_banner_i18n
                self._show_banner(msg, ok, i18n_key=key, i18n_params=params)
            else:
                self._show_banner(msg, ok)
        self._update_theme_hint()
        # 刷新所有预设卡片主题
        for card in self._preset_cards:
            card.apply_tokens(self._theme_tokens)
        self._refresh_preset_active()
        # 刷新渠道面板中的 Toggle 开关主题
        for w in self._field_widgets.values():
            if isinstance(w, _ToggleSwitch):
                w.apply_tokens(self._theme_tokens)
        if hasattr(self, "_action_button_strip"):
            self._action_button_strip.setStyleSheet(
                f"background:{t.bg_elevated}; border:1px solid {t.border}; border-radius:16px;"
            )

    def refresh_theme_states(self) -> None:
        """刷新动态状态：按钮样式。"""
        self._apply_action_button_styles()
        if hasattr(self, "_action_policy_summary_card"):
            t = self._theme_tokens
            self._action_policy_summary_card.setStyleSheet(
                f"background:{t.bg_elevated}; border:1px solid {t.border}; border-radius:18px;"
            )
        if hasattr(self, "_action_policy_summary_title"):
            self._action_policy_summary_title.setStyleSheet(
                f"color:{self._theme_tokens.text_primary}; font-size:15px; font-weight:700;"
            )
        if hasattr(self, "_action_policy_summary_lbl"):
            self._action_policy_summary_lbl.setStyleSheet(
                f"color:{self._theme_tokens.text_secondary}; font-size:12px; line-height:1.7;"
            )
        if hasattr(self, "_action_policy_status_lbl"):
            self._action_policy_status_lbl.setStyleSheet(
                f"color:{self._theme_tokens.text_muted}; font-size:12px; line-height:1.6;"
            )

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

    def _load_lang_combo(self):
        """将配置中的语言值同步到 ComboBox 显示"""
        if not self._config:
            return
        current = self._config.get("OPEN_AUTOGLM_LANG") or "cn"
        self._lang_combo.blockSignals(True)
        for i in range(self._lang_combo.count()):
            if self._lang_combo.itemData(i) == current:
                self._lang_combo.setCurrentIndex(i)
                break
        self._lang_combo.blockSignals(False)

    def _on_lang_changed(self, index: int):
        """
        语言下拉变化时，仅更新 ComboBox 显示，不立即保存。
        保存后才生效，符合设置页保存后生效的规范。
        """
        pass  # 保存由 _on_save 统一处理

    def apply_i18n(self, i18n_manager) -> None:
        """
        PageI18nAdapter 回调 - 语言切换后更新设置页本身的静态文案。
        """
        _t = i18n_manager.t
        # 更新 i18n 服务引用（InitialState 时可能还未注入）
        self._i18n = i18n_manager
        if hasattr(self, "_title_lbl"):
            self._title_lbl.setText(_t("page.settings.title"))
        # GroupBox 标题
        if hasattr(self, "_model_group"):
            self._model_group.setTitle(_t("page.settings.section.model_api"))
        if hasattr(self, "_channel_group"):
            self._channel_group.setTitle(_t("page.settings.section.channel"))
        if hasattr(self, "_run_group"):
            self._run_group.setTitle(_t("page.settings.section.run_params"))
        if hasattr(self, "_action_policy_group"):
            self._action_policy_group.setTitle(_t("page.settings.section.action_policy"))
        if hasattr(self, "_appearance_group"):
            self._appearance_group.setTitle(_t("page.settings.section.appearance"))
        if hasattr(self, "_build_tools_group"):
            self._build_tools_group.setTitle(_t("page.settings.section.build_tools"))
        if hasattr(self, "_quick_switch_group"):
            self._quick_switch_group.setTitle(_t("page.settings.section.quick_switch"))
        # 行标签与说明
        if hasattr(self, "_channel_hint_lbl"):
            self._channel_hint_lbl.setText(_t("page.settings.channel.hint"))
        if hasattr(self, "_action_policy_hint_lbl"):
            self._action_policy_hint_lbl.setText(_t("page.settings.action_policy.relocated_hint"))
        if hasattr(self, "_action_policy_summary_title"):
            self._action_policy_summary_title.setText(_t("page.settings.action_policy.summary_title"))
        if hasattr(self, "_btn_action_open_dialog"):
            self._btn_action_open_dialog.setText(_t("page.settings.action_policy.btn.open_dialog"))
        if hasattr(self, "_btn_action_open_workspace"):
            self._btn_action_open_workspace.setText(_t("page.settings.action_policy.btn.open_workspace"))
        if hasattr(self, "_btn_action_reset_defaults"):
            self._btn_action_reset_defaults.setText(_t("page.settings.actions.btn.reset_defaults"))
        if hasattr(self, "_btn_action_select_all"):
            self._btn_action_select_all.setText(_t("page.settings.actions.btn.select_all"))
        if hasattr(self, "_btn_action_clear_all"):
            self._btn_action_clear_all.setText(_t("page.settings.actions.btn.clear_all"))
        if hasattr(self, "_build_hint_lbl"):
            self._build_hint_lbl.setText(_t("page.settings.build.hint"))
        if hasattr(self, "_device_type_label"):
            self._device_type_label.setText(_t("page.settings.device_type.label"))
        if hasattr(self, "_lang_label"):
            self._lang_label.setText(_t("page.settings.lang.label"))
        if hasattr(self, "_theme_label"):
            self._theme_label.setText(_t("page.settings.theme.label"))
        if hasattr(self, "_theme_effect_label"):
            self._theme_effect_label.setText(_t("page.settings.theme.effect_label"))
        if hasattr(self, "_env_path_lbl") and self._config:
            self._env_path_lbl.setText(_t("page.settings.env_path_label", path=self._config.env_path))
        # 语言下拉文字
        if hasattr(self, "_lang_combo"):
            self._lang_combo.setItemText(0, _t("page.settings.lang.cn"))
            self._lang_combo.setItemText(1, _t("page.settings.lang.en"))
        if hasattr(self, "_device_type_combo"):
            self._device_type_combo.setItemText(0, _t("page.settings.device_type.adb"))
            self._device_type_combo.setItemText(1, _t("page.settings.device_type.hdc"))
            self._device_type_combo.setItemText(2, _t("page.settings.device_type.ios"))
        # 主题下拉文字
        if hasattr(self, "_theme_combo"):
            self._theme_combo.setItemText(0, _t("page.settings.theme.system"))
            self._theme_combo.setItemText(1, _t("page.settings.theme.dark"))
            self._theme_combo.setItemText(2, _t("page.settings.theme.light"))
        # 按钮文字
        if hasattr(self, "_btn_save"):
            self._btn_save.setText(_t("page.settings.btn.save"))
        if hasattr(self, "_btn_validate"):
            self._btn_validate.setText(_t("page.settings.btn.validate"))
        if hasattr(self, "_btn_reload"):
            self._btn_reload.setText(_t("page.settings.btn.reload"))
        if hasattr(self, "_btn_run_build"):
            self._btn_run_build.setText(_t("page.settings.build.btn.run"))
        if hasattr(self, "_btn_open_scripts_dir"):
            self._btn_open_scripts_dir.setText(_t("page.settings.build.btn.open_scripts"))
        if hasattr(self, "_btn_open_dist_dir"):
            self._btn_open_dist_dir.setText(_t("page.settings.build.btn.open_dist"))
        for btn in self._visibility_toggle_buttons:
            is_visible = bool(btn.property("sensitiveVisible"))
            btn.setText(_t("page.settings.btn.hide") if is_visible else _t("page.settings.btn.show"))
        # 预设卡片与提示文字
        if hasattr(self, "_preset_hint_lbl"):
            self._preset_hint_lbl.setText(_t("page.settings.preset.hint"))
        for card in self._preset_cards:
            if hasattr(card, "set_translator"):
                card.set_translator(_t)
        self._update_theme_hint()
        self._refresh_build_paths()
        self._refresh_preset_active()
        self._rebuild_action_policy_matrix(self._current_device_type())
        self._refresh_action_policy_summary()
        if self._config:
            active = self._config.get_active_channel()
            active_id = active.get("id", "") if active else ""
            self._rebuild_channel_detail(active_id)
        if self._last_banner_state and self._validate_banner.isVisible():
            msg, ok = self._last_banner_state
            if self._last_banner_i18n:
                key, params = self._last_banner_i18n
                self._show_banner(msg, ok, i18n_key=key, i18n_params=params)
            else:
                self._show_banner(msg, ok)

    def _on_theme_changed(self, index: int):
        """主题下拉变化时立即写入配置并触发主题切换"""
        if not self._config:
            return
        value = self._theme_combo.itemData(index)
        self._update_theme_hint()
        if not value:
            return
        try:
            self._config.set("OPEN_AUTOGLM_THEME", value)
        except Exception as e:
            QMessageBox.warning(self, self._t("page.settings.dialog.save_fail"), str(e))
            self._load_theme_combo()

    def on_page_activated(self):
        self._load_values()
        self._load_theme_combo()
        self._refresh_preset_active()
        self._refresh_action_policy_summary()
        # 同步渠道详情面板（页面切换回来时刷新）
        if self._config:
            active = self._config.get_active_channel()
            active_id = active.get("id", "") if active else ""
            self._rebuild_channel_detail(active_id)
