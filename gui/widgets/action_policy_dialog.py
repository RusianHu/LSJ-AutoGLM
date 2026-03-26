# -*- coding: utf-8 -*-
"""
gui/widgets/action_policy_dialog.py - 工作台动作策略管理弹窗

将动作策略编辑能力从设置页中抽离，供工作台与设置页复用：
- 支持平台切换（adb / hdc / ios）
- 支持运行时动作 / AI 可见动作矩阵编辑
- 支持平台默认、全选、清空
- 变更即时持久化到 ConfigService
- 自带主题感知与摘要信息展示
"""

from __future__ import annotations

import json
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from gui.theme.styles.buttons import btn_primary, btn_secondary, btn_subtle
from gui.theme.styles.dialogs import dialog_surface
from gui.theme.tokens import ThemeTokens
from gui.widgets.themed_dialog import ThemedDialog
from phone_agent.actions.registry import (
    ActionPolicyInput,
    export_gui_action_groups,
    parse_action_name_collection,
    resolve_action_policy,
)


def summarize_action_policy(config, translator: Callable[[str], str], platform: str | None = None) -> dict:
    """构建动作策略摘要信息，供工作台卡片与设置页入口使用。"""
    _t = translator
    current_platform = ((platform or (config.get("OPEN_AUTOGLM_DEVICE_TYPE") if config else "") or "adb").strip().lower())
    settings = config.get_action_policy_settings() if config else {
        "policy_version": 1,
        "use_platform_defaults": True,
        "enabled_actions": "",
        "ai_visible_actions": "",
    }

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

    resolved = resolve_action_policy(
        current_platform,
        ActionPolicyInput(
            ai_visible_actions=ai_visible_actions,
            runtime_enabled_actions=enabled_actions,
            policy_version=int(settings.get("policy_version", 1) or 1),
            use_platform_defaults=bool(settings.get("use_platform_defaults", True)),
        ),
    )

    runtime_count = len(resolved.runtime_enabled_actions)
    ai_count = len(resolved.ai_visible_actions)
    supported_count = len(resolved.supported_actions)
    default_mode = bool(settings.get("use_platform_defaults", True))

    return {
        "platform": current_platform,
        "policy_version": int(settings.get("policy_version", 1) or 1),
        "runtime_count": runtime_count,
        "ai_count": ai_count,
        "supported_count": supported_count,
        "is_default_mode": default_mode,
        "mode_text": _t("page.dashboard.action_policy.mode.default") if default_mode else _t("page.dashboard.action_policy.mode.custom"),
        "headline": _t(
            "page.dashboard.action_policy.summary.default"
            if default_mode else
            "page.dashboard.action_policy.summary.custom",
            runtime=runtime_count,
            ai_visible=ai_count,
            supported=supported_count,
        ),
        "compatibility_hint": (
            _t("page.dashboard.action_policy.summary.filtered", actions=", ".join(resolved.unknown_actions))
            if resolved.unknown_actions else ""
        ),
    }


class ActionPolicyDialog(ThemedDialog):
    """工作台动作策略管理弹窗。"""

    def __init__(self, services: dict, parent=None):
        super().__init__(parent)
        self._services = services
        self._config = services.get("config")
        self._i18n = services.get("i18n")
        self._action_runtime_checks: dict[str, QCheckBox] = {}
        self._action_ai_checks: dict[str, QCheckBox] = {}
        self._action_matrix_syncing = False
        self._summary_cache: dict = {}
        self._build_ui()
        self._connect_signals()
        self.refresh_from_config()

    def _t(self, key: str, **params) -> str:
        i18n = getattr(self, "_i18n", None) or self._services.get("i18n")
        if i18n:
            return i18n.t(key, **params)
        try:
            from gui.i18n.locales.cn import CN
            tmpl = CN.get(key, f"[[{key}]]")
            return tmpl.format(**params) if params else tmpl
        except Exception:
            return f"[[{key}]]"

    def _build_ui(self) -> None:
        self.setWindowTitle(self._t("page.dashboard.action_policy.dialog.title"))
        self.setModal(True)
        self.resize(1080, 760)
        self.setMinimumSize(920, 640)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(16)

        header = QFrame()
        header.setObjectName("ActionPolicyHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(20, 18, 20, 18)
        header_layout.setSpacing(12)

        self._eyebrow_lbl = QLabel(self._t("page.dashboard.action_policy.dialog.eyebrow"))
        self._eyebrow_lbl.setObjectName("ActionPolicyEyebrow")
        header_layout.addWidget(self._eyebrow_lbl)

        self._title_lbl = QLabel(self._t("page.dashboard.action_policy.dialog.title"))
        self._title_lbl.setObjectName("ActionPolicyTitle")
        header_layout.addWidget(self._title_lbl)

        self._desc_lbl = QLabel(self._t("page.dashboard.action_policy.dialog.desc"))
        self._desc_lbl.setObjectName("ActionPolicyDesc")
        self._desc_lbl.setWordWrap(True)
        header_layout.addWidget(self._desc_lbl)

        stats_row = QHBoxLayout()
        stats_row.setContentsMargins(0, 6, 0, 0)
        stats_row.setSpacing(12)
        self._summary_platform_card = self._create_metric_card("ActionPolicySummaryPlatform")
        self._summary_mode_card = self._create_metric_card("ActionPolicySummaryMode")
        self._summary_runtime_card = self._create_metric_card("ActionPolicySummaryRuntime")
        self._summary_ai_card = self._create_metric_card("ActionPolicySummaryAi")
        for card in (
            self._summary_platform_card,
            self._summary_mode_card,
            self._summary_runtime_card,
            self._summary_ai_card,
        ):
            stats_row.addWidget(card, 1)
        header_layout.addLayout(stats_row)
        root.addWidget(header)

        toolbar = QFrame()
        toolbar.setObjectName("ActionPolicyToolbar")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(18, 14, 18, 14)
        toolbar_layout.setSpacing(12)

        self._platform_label = QLabel(self._t("page.settings.device_type.label"))
        toolbar_layout.addWidget(self._platform_label)

        self._platform_combo = QComboBox()
        self._platform_combo.addItem(self._t("page.settings.device_type.adb"), "adb")
        self._platform_combo.addItem(self._t("page.settings.device_type.hdc"), "hdc")
        self._platform_combo.addItem(self._t("page.settings.device_type.ios"), "ios")
        self._platform_combo.setMinimumWidth(180)
        toolbar_layout.addWidget(self._platform_combo)

        self._defaults_checkbox = QCheckBox(self._t("page.dashboard.action_policy.use_defaults"))
        toolbar_layout.addWidget(self._defaults_checkbox)
        toolbar_layout.addStretch(1)

        self._btn_reset_defaults = QPushButton(self._t("page.settings.actions.btn.reset_defaults"))
        self._btn_select_all = QPushButton(self._t("page.settings.actions.btn.select_all"))
        self._btn_clear_all = QPushButton(self._t("page.settings.actions.btn.clear_all"))
        toolbar_layout.addWidget(self._btn_reset_defaults)
        toolbar_layout.addWidget(self._btn_select_all)
        toolbar_layout.addWidget(self._btn_clear_all)
        root.addWidget(toolbar)

        self._status_banner = QLabel("")
        self._status_banner.setObjectName("ActionPolicyStatusBanner")
        self._status_banner.setWordWrap(True)
        self._status_banner.hide()
        root.addWidget(self._status_banner)

        self._hint_lbl = QLabel(self._t("page.settings.actions.hint"))
        self._hint_lbl.setObjectName("ActionPolicyHint")
        self._hint_lbl.setWordWrap(True)
        root.addWidget(self._hint_lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setObjectName("ActionPolicyScroll")
        scroll_widget = QWidget()
        self._content_vbox = QVBoxLayout(scroll_widget)
        self._content_vbox.setContentsMargins(0, 0, 4, 0)
        self._content_vbox.setSpacing(14)
        scroll.setWidget(scroll_widget)
        self._matrix_scroll = scroll
        root.addWidget(scroll, 1)

        footer = QFrame()
        footer.setObjectName("ActionPolicyFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(18, 12, 18, 12)
        footer_layout.setSpacing(12)

        self._footer_note_lbl = QLabel(self._t("page.dashboard.action_policy.dialog.footer"))
        self._footer_note_lbl.setObjectName("ActionPolicyFooterNote")
        self._footer_note_lbl.setWordWrap(True)
        footer_layout.addWidget(self._footer_note_lbl, 1)

        self._btn_close = QPushButton(self._t("page.dashboard.action_policy.dialog.btn.close"))
        self._btn_close.clicked.connect(self.accept)
        footer_layout.addWidget(self._btn_close)
        root.addWidget(footer)

    def _create_metric_card(self, object_name: str) -> QFrame:
        card = QFrame()
        card.setObjectName(object_name)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)
        label = QLabel("")
        label.setObjectName(f"{object_name}Label")
        value = QLabel("--")
        value.setObjectName(f"{object_name}Value")
        layout.addWidget(label)
        layout.addWidget(value)
        card._metric_label = label
        card._metric_value = value
        return card

    def _connect_signals(self) -> None:
        self._platform_combo.currentIndexChanged.connect(self._on_platform_changed)
        self._defaults_checkbox.toggled.connect(self._on_defaults_toggled)
        self._btn_reset_defaults.clicked.connect(self._on_action_policy_reset_defaults)
        self._btn_select_all.clicked.connect(self._on_action_policy_select_all)
        self._btn_clear_all.clicked.connect(self._on_action_policy_clear_all)

    def refresh_from_config(self) -> None:
        if self._config is None:
            return
        platform = (self._config.get("OPEN_AUTOGLM_DEVICE_TYPE") or "adb").strip().lower()
        self._platform_combo.blockSignals(True)
        for index in range(self._platform_combo.count()):
            if self._platform_combo.itemData(index) == platform:
                self._platform_combo.setCurrentIndex(index)
                break
        self._platform_combo.blockSignals(False)

        settings = self._config.get_action_policy_settings()
        self._defaults_checkbox.blockSignals(True)
        self._defaults_checkbox.setChecked(bool(settings.get("use_platform_defaults", True)))
        self._defaults_checkbox.blockSignals(False)
        self._rebuild_action_policy_matrix(platform)
        self._sync_defaults_state_ui()
        self._update_summary_cards(platform)

    def _current_device_type(self) -> str:
        current = self._platform_combo.currentData()
        return str(current or "adb")

    @staticmethod
    def _is_truthy_text(value: object) -> bool:
        return str(value).strip().lower() in ("1", "true", "yes", "on")

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

    def _build_action_policy_updates(self, *, use_platform_defaults: bool | None = None) -> dict[str, str]:
        defaults_enabled = self._defaults_checkbox.isChecked() if use_platform_defaults is None else bool(use_platform_defaults)
        updates = {
            "OPEN_AUTOGLM_DEVICE_TYPE": self._current_device_type(),
            "OPEN_AUTOGLM_USE_PLATFORM_DEFAULT_ACTIONS": "true" if defaults_enabled else "false",
        }
        if defaults_enabled:
            updates["OPEN_AUTOGLM_ENABLED_ACTIONS"] = ""
            updates["OPEN_AUTOGLM_AI_VISIBLE_ACTIONS"] = ""
        else:
            updates.update(self._collect_action_policy_updates())
        return updates

    def _persist_action_policy_updates(self, *, use_platform_defaults: bool | None = None) -> None:
        if not self._config:
            return
        updates = self._build_action_policy_updates(use_platform_defaults=use_platform_defaults)
        try:
            self._config.set_many(updates)
        except Exception as exc:
            QMessageBox.warning(self, self._t("page.settings.dialog.save_fail"), str(exc))
            self.refresh_from_config()
            return
        self._update_summary_cards(self._current_device_type())
        self._update_action_policy_compatibility_hint(self._current_device_type())
        self._sync_defaults_state_ui()

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

    def _sync_defaults_state_ui(self) -> None:
        use_defaults = self._defaults_checkbox.isChecked()
        for btn in (self._btn_select_all, self._btn_clear_all):
            btn.setEnabled(not use_defaults and bool(self._action_runtime_checks))
        self._matrix_scroll.setEnabled(True)
        for checkbox in self._action_runtime_checks.values():
            checkbox.setEnabled(not use_defaults)
        for name, checkbox in self._action_ai_checks.items():
            runtime_checkbox = self._action_runtime_checks.get(name)
            checkbox.setEnabled((not use_defaults) and bool(runtime_checkbox and runtime_checkbox.isChecked()))

    def _update_action_policy_compatibility_hint(self, platform: str, resolved_policy=None) -> None:
        label = self._status_banner
        if label is None:
            return
        if not self._config:
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

        label.hide()

    def _update_summary_cards(self, platform: str) -> None:
        if not self._config:
            return
        summary = summarize_action_policy(self._config, self._t, platform=platform)
        self._summary_cache = summary
        self._summary_platform_card._metric_label.setText(self._t("page.dashboard.action_policy.metric.platform"))
        self._summary_platform_card._metric_value.setText(summary["platform"].upper())
        self._summary_mode_card._metric_label.setText(self._t("page.dashboard.action_policy.metric.mode"))
        self._summary_mode_card._metric_value.setText(summary["mode_text"])
        self._summary_runtime_card._metric_label.setText(self._t("page.dashboard.action_policy.metric.runtime"))
        self._summary_runtime_card._metric_value.setText(str(summary["runtime_count"]))
        self._summary_ai_card._metric_label.setText(self._t("page.dashboard.action_policy.metric.ai_visible"))
        self._summary_ai_card._metric_value.setText(str(summary["ai_count"]))
        self._desc_lbl.setText(summary["headline"])

    def _rebuild_action_policy_matrix(self, platform: str = "") -> None:
        vbox = self._content_vbox
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
        self._btn_reset_defaults.setEnabled(bool(groups))
        self._btn_select_all.setEnabled(bool(groups))
        self._btn_clear_all.setEnabled(bool(groups))

        if not groups:
            hint = QLabel(self._t("page.settings.actions.none"))
            hint.setObjectName("ActionPolicyEmptyHint")
            hint.setWordWrap(True)
            vbox.addWidget(hint)
            vbox.addStretch(1)
            self._sync_defaults_state_ui()
            self._update_summary_cards(current_platform)
            return

        for group in groups:
            category_box = QGroupBox(
                self._translate_or_fallback(group.get("category_i18n_key", ""), group.get("category_label", ""))
            )
            category_box.setObjectName("ActionPolicyCategoryBox")
            category_vbox = QVBoxLayout(category_box)
            category_vbox.setContentsMargins(14, 14, 14, 14)
            category_vbox.setSpacing(10)

            for item in group.get("items", ()):
                action_name = item.get("name", "")
                row = QFrame()
                row.setObjectName("ActionPolicyRow")
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(14, 12, 14, 12)
                row_layout.setSpacing(14)

                text_layout = QVBoxLayout()
                text_layout.setContentsMargins(0, 0, 0, 0)
                text_layout.setSpacing(4)

                label_text = self._translate_or_fallback(item.get("label_i18n_key", ""), item.get("label", action_name))
                desc_text = self._translate_or_fallback(item.get("description_i18n_key", ""), item.get("description", ""))
                risk_text = self._translate_or_fallback(item.get("risk_i18n_key", ""), item.get("risk_level", ""))

                title_lbl = QLabel(label_text)
                title_lbl.setObjectName("ActionPolicyRowTitle")
                text_layout.addWidget(title_lbl)

                desc_parts = [part for part in (desc_text, f"[{risk_text}]" if risk_text else "") if part]
                desc_lbl = QLabel(" ".join(desc_parts))
                desc_lbl.setObjectName("ActionPolicyRowDesc")
                desc_lbl.setWordWrap(True)
                text_layout.addWidget(desc_lbl)

                row_layout.addLayout(text_layout, 1)

                checks_box = QFrame()
                checks_box.setObjectName("ActionPolicyChecksBox")
                checks_layout = QGridLayout(checks_box)
                checks_layout.setContentsMargins(0, 0, 0, 0)
                checks_layout.setHorizontalSpacing(12)
                checks_layout.setVerticalSpacing(4)

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

                checks_layout.addWidget(runtime_checkbox, 0, 0)
                checks_layout.addWidget(ai_checkbox, 1, 0)
                row_layout.addWidget(checks_box, 0, Qt.AlignRight | Qt.AlignVCenter)
                category_vbox.addWidget(row)

            vbox.addWidget(category_box)

        vbox.addStretch(1)
        self._sync_defaults_state_ui()
        self._update_summary_cards(current_platform)

    def _translate_or_fallback(self, key: str, fallback: str, **params) -> str:
        if not key:
            return fallback
        translated = self._t(key, **params)
        if translated.startswith("[[") and translated.endswith("]]"):
            return fallback
        return translated

    def _on_platform_changed(self, index: int) -> None:
        platform = str(self._platform_combo.itemData(index) or "adb")
        self._rebuild_action_policy_matrix(platform)
        self._persist_action_policy_updates(
            use_platform_defaults=self._defaults_checkbox.isChecked()
        )

    def _on_defaults_toggled(self, checked: bool) -> None:
        self._sync_defaults_state_ui()
        self._persist_action_policy_updates(use_platform_defaults=checked)

    def _on_action_policy_reset_defaults(self) -> None:
        current_platform = self._current_device_type()
        resolved_policy = resolve_action_policy(current_platform)
        self._set_action_policy_check_states(
            resolved_policy.runtime_enabled_actions,
            resolved_policy.ai_visible_actions,
        )
        self._defaults_checkbox.blockSignals(True)
        self._defaults_checkbox.setChecked(True)
        self._defaults_checkbox.blockSignals(False)
        self._persist_action_policy_updates(use_platform_defaults=True)

    def _on_action_policy_select_all(self) -> None:
        all_actions = tuple(self._action_runtime_checks.keys())
        self._set_action_policy_check_states(all_actions, all_actions)
        self._persist_action_policy_updates(use_platform_defaults=False)

    def _on_action_policy_clear_all(self) -> None:
        self._set_action_policy_check_states((), ())
        self._persist_action_policy_updates(use_platform_defaults=False)

    def _on_runtime_action_toggled(self, action_name: str, checked: bool) -> None:
        ai_widget = self._action_ai_checks.get(action_name)
        if ai_widget is None or self._action_matrix_syncing:
            return
        self._action_matrix_syncing = True
        try:
            ai_widget.setEnabled(checked and not self._defaults_checkbox.isChecked())
            if not checked:
                ai_widget.setChecked(False)
        finally:
            self._action_matrix_syncing = False
        self._defaults_checkbox.blockSignals(True)
        self._defaults_checkbox.setChecked(False)
        self._defaults_checkbox.blockSignals(False)
        self._persist_action_policy_updates(use_platform_defaults=False)

    def _on_ai_action_toggled(self, action_name: str, checked: bool) -> None:
        if self._action_matrix_syncing:
            return
        runtime_widget = self._action_runtime_checks.get(action_name)
        if checked and runtime_widget is not None and not runtime_widget.isChecked():
            self._action_matrix_syncing = True
            try:
                runtime_widget.setChecked(True)
            finally:
                self._action_matrix_syncing = False
        self._defaults_checkbox.blockSignals(True)
        self._defaults_checkbox.setChecked(False)
        self._defaults_checkbox.blockSignals(False)
        self._persist_action_policy_updates(use_platform_defaults=False)

    def refresh_theme_surfaces(self) -> None:
        if self._tokens is None:
            return
        t: ThemeTokens = self._tokens
        self.setStyleSheet(
            dialog_surface(t)
            + f"""
            QFrame#ActionPolicyHeader {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {t.bg_elevated}, stop:1 {t.accent_soft});
                border: 1px solid {t.border};
                border-radius: 18px;
            }}
            QLabel#ActionPolicyEyebrow {{
                color: {t.accent};
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 1px;
                text-transform: uppercase;
            }}
            QLabel#ActionPolicyTitle {{
                color: {t.text_primary};
                font-size: 26px;
                font-weight: 700;
            }}
            QLabel#ActionPolicyDesc {{
                color: {t.text_secondary};
                font-size: 13px;
                line-height: 1.6;
            }}
            QFrame#ActionPolicyToolbar, QFrame#ActionPolicyFooter {{
                background: {t.bg_secondary};
                border: 1px solid {t.border};
                border-radius: 16px;
            }}
            QLabel#ActionPolicyHint, QLabel#ActionPolicyFooterNote {{
                color: {t.text_secondary};
                font-size: 12px;
                line-height: 1.6;
            }}
            QLabel#ActionPolicyStatusBanner {{
                background: {t.warning_bg};
                color: {t.warning};
                border: 1px solid {t.warning_border};
                border-radius: 12px;
                padding: 10px 12px;
                font-size: 12px;
            }}
            QFrame#ActionPolicySummaryPlatform,
            QFrame#ActionPolicySummaryMode,
            QFrame#ActionPolicySummaryRuntime,
            QFrame#ActionPolicySummaryAi {{
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid {t.border};
                border-radius: 14px;
            }}
            QLabel#ActionPolicySummaryPlatformLabel,
            QLabel#ActionPolicySummaryModeLabel,
            QLabel#ActionPolicySummaryRuntimeLabel,
            QLabel#ActionPolicySummaryAiLabel {{
                color: {t.text_muted};
                font-size: 11px;
            }}
            QLabel#ActionPolicySummaryPlatformValue,
            QLabel#ActionPolicySummaryModeValue,
            QLabel#ActionPolicySummaryRuntimeValue,
            QLabel#ActionPolicySummaryAiValue {{
                color: {t.text_primary};
                font-size: 19px;
                font-weight: 700;
            }}
            QGroupBox#ActionPolicyCategoryBox {{
                background: {t.bg_secondary};
                border: 1px solid {t.border};
                border-radius: 16px;
                margin-top: 14px;
                padding-top: 12px;
                color: {t.text_primary};
                font-weight: 700;
            }}
            QGroupBox#ActionPolicyCategoryBox::title {{
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 6px;
                color: {t.text_primary};
            }}
            QFrame#ActionPolicyRow {{
                background: {t.bg_main};
                border: 1px solid {t.border};
                border-radius: 14px;
            }}
            QLabel#ActionPolicyRowTitle {{
                color: {t.text_primary};
                font-size: 13px;
                font-weight: 700;
            }}
            QLabel#ActionPolicyRowDesc {{
                color: {t.text_secondary};
                font-size: 12px;
                line-height: 1.5;
            }}
            QLabel#ActionPolicyEmptyHint {{
                color: {t.text_secondary};
                font-size: 13px;
                padding: 24px 8px;
            }}
            QComboBox {{
                background: {t.bg_main};
                border: 1px solid {t.border};
                border-radius: 10px;
                color: {t.text_primary};
                padding: 6px 12px;
                min-height: 20px;
            }}
            QComboBox:hover {{ border-color: {t.accent}; }}
            QComboBox QAbstractItemView {{
                background: {t.bg_secondary};
                color: {t.text_primary};
                border: 1px solid {t.border};
                selection-background-color: {t.selection_bg};
            }}
            QCheckBox {{
                color: {t.text_primary};
                spacing: 8px;
                font-size: 12px;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border-radius: 5px;
                border: 1px solid {t.border};
                background: {t.bg_main};
            }}
            QCheckBox::indicator:checked {{
                background: {t.accent};
                border-color: {t.accent};
            }}
            QScrollArea#ActionPolicyScroll {{
                border: none;
                background: transparent;
            }}
            """
        )

    def refresh_theme_states(self) -> None:
        if self._tokens is None:
            return
        self._btn_close.setStyleSheet(btn_primary(self._tokens))
        self._btn_reset_defaults.setStyleSheet(btn_secondary(self._tokens))
        self._btn_select_all.setStyleSheet(btn_subtle(self._tokens))
        self._btn_clear_all.setStyleSheet(btn_subtle(self._tokens))
