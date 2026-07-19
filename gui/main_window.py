# -*- coding: utf-8 -*-
"""主窗口 - 横版布局：左侧边栏（品牌/导航/主题切换）+ 右侧内容区"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from gui.widgets.nav_button import NavButton
from gui.theme.icons import fa_family, icon_char
from gui.theme.manager import ThemeManager
from gui.theme.preferences import ThemePreference
from gui.theme.global_shell import GlobalShellStyler
from gui.theme.page_adapter import PageThemeAdapter
from gui.theme.tokens import ThemeTokens
from gui.theme.effects import play_page_fade
from gui.i18n.manager import I18nManager
from gui.i18n.page_adapter import PageI18nAdapter


class MainWindow(QMainWindow):
    """
    主窗口。
    布局（横版）：左侧固定宽度侧边栏（品牌 / 纵向导航 / 主题切换 / 版本）
    + 右侧内容区（StackedWidget）。

    主题系统：
      - 由 ThemeManager 统一管理主题解析与广播
      - GlobalShellStyler 负责应用壳层全局 QSS
      - PageThemeAdapter 负责将 tokens 推送到各页面
      - MainWindow.apply_theme 作为兼容入口，内部委托给 ThemeManager
    """

    MIN_WIDTH = 1024
    MIN_HEIGHT = 660
    SIDEBAR_WIDTH = 216

    def __init__(self, services: dict, parent=None):
        """
        services: {
            'config': ConfigService,
            'device': DeviceService,
            'task':   TaskService,
            'history': HistoryService,
            'mirror':  MirrorService,
        }
        """
        super().__init__(parent)
        self._services = services

        # ---------- ThemeEngine 初始化 ----------
        self._theme_manager = ThemeManager(self)
        self._shell_styler = GlobalShellStyler(self)
        self._page_adapter = PageThemeAdapter(self._theme_manager)

        # 连接主题变化 -> 壳层更新 + 导航更新
        self._theme_manager.theme_changed.connect(self._on_tokens_changed)

        # ---------- I18nEngine 初始化 ----------
        _init_lang = "cn"
        cfg = services.get("config")
        if cfg:
            _init_lang = cfg.get("OPEN_AUTOGLM_LANG") or "cn"
        self._i18n_manager = I18nManager(_init_lang, self)
        self._i18n_adapter = PageI18nAdapter(self._i18n_manager)
        # 语言切换 -> 更新壳层（标题、导航）
        self._i18n_manager.language_changed.connect(self._on_language_changed)

        # 暴露给 services，让需要的服务可以访问
        self._services["theme_manager"] = self._theme_manager
        self._services["i18n"] = self._i18n_manager
        self._services["navigate_to_page"] = self.switch_page

        self._app_version = (
            QApplication.instance().applicationVersion().strip()
            if QApplication.instance() and QApplication.instance().applicationVersion()
            else "1.0.9"
        )
        self.setWindowTitle(self._i18n_manager.t("shell.window.title"))
        self.setMinimumSize(self.MIN_WIDTH, self.MIN_HEIGHT)
        self.resize(1360, 850)
        self._build_ui()
        self._connect_signals()

        # 应用初始主题（从配置读取偏好）
        self.apply_theme(self._get_current_theme())

    # ---------- UI 构建 ----------

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 左侧边栏
        self._nav_panel = self._build_sidebar()
        root_layout.addWidget(self._nav_panel)

        # 右侧内容区
        self._stack = QStackedWidget()
        self._stack.setObjectName("ContentStack")
        root_layout.addWidget(self._stack, 1)

        # 延迟导入页面（避免循环依赖）
        self._init_pages()

    def _build_sidebar(self) -> QWidget:
        nav = QWidget()
        nav.setObjectName("SidebarPanel")
        nav.setFixedWidth(self.SIDEBAR_WIDTH)
        layout = QVBoxLayout(nav)
        layout.setContentsMargins(12, 18, 12, 14)
        layout.setSpacing(4)

        # ---- 品牌区：图标 + 名称 ----
        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(6, 0, 0, 0)
        brand_row.setSpacing(9)

        self._brand_icon_lbl = QLabel(icon_char("brand"))
        self._brand_icon_lbl.setFixedWidth(24)
        self._brand_icon_lbl.setAlignment(Qt.AlignCenter)
        brand_row.addWidget(self._brand_icon_lbl)

        brand_text_col = QVBoxLayout()
        brand_text_col.setContentsMargins(0, 0, 0, 0)
        brand_text_col.setSpacing(0)

        self._logo_lbl = QLabel("LSJ AutoGLM")
        self._logo_lbl.setFont(QFont("Segoe UI", 12, QFont.Bold))
        brand_text_col.addWidget(self._logo_lbl)

        _t = self._i18n_manager.t
        self._ver_lbl = QLabel(_t("shell.footer.version", version=self._app_version))
        brand_text_col.addWidget(self._ver_lbl)
        brand_row.addLayout(brand_text_col, 1)
        layout.addLayout(brand_row)

        layout.addSpacing(18)

        # ---- 纵向导航按钮 ----
        self._btn_group = QButtonGroup(self)
        self._btn_group.setExclusive(True)

        # (key, icon_name, i18n_key)
        nav_items = [
            ("dashboard", "dashboard", "shell.nav.dashboard"),
            ("device",    "device",    "shell.nav.device"),
            ("history",   "history",   "shell.nav.history"),
            ("settings",  "settings",  "shell.nav.settings"),
            ("diag",      "diag",      "shell.nav.diagnostics"),
        ]
        self._nav_items_meta = nav_items  # 保留供 retranslate 使用
        self._nav_buttons = {}
        for key, icon_name, i18n_key in nav_items:
            btn = NavButton(icon_name, _t(i18n_key))
            self._btn_group.addButton(btn)
            layout.addWidget(btn)
            self._nav_buttons[key] = btn
            btn.setProperty("i18n_key", i18n_key)

        layout.addStretch(1)

        # ---- 底部：主题切换器 ----
        self._theme_switcher_widget = self._build_theme_switcher()
        layout.addWidget(self._theme_switcher_widget)

        return nav

    def _build_theme_switcher(self) -> QWidget:
        """构建侧边栏底部主题切换器（三段等宽 pill 按钮组）。"""
        _t = self._i18n_manager.t

        container = QWidget()
        container.setObjectName("ThemeSwitcherBar")
        outer = QVBoxLayout(container)
        outer.setContentsMargins(2, 0, 2, 0)
        outer.setSpacing(6)

        # 小说明标签（保留供 i18n/主题刷新引用，紧凑模式下隐藏）
        self._theme_hint_lbl = QLabel(_t("shell.theme_switcher.label"))
        self._theme_hint_lbl.setObjectName("ThemeSwitcherHint")
        self._theme_hint_lbl.hide()
        outer.addWidget(self._theme_hint_lbl)

        # Pill 容器（三个按钮的外壳）
        pill = QFrame()
        pill.setObjectName("ThemeSwitcherPill")
        pill.setFixedHeight(34)
        h = QHBoxLayout(pill)
        h.setContentsMargins(3, 3, 3, 3)
        h.setSpacing(2)

        self._theme_btns: dict[str, QPushButton] = {}
        self._theme_btn_meta = [
            ("system", "shell.theme_switcher.button.system", "shell.theme_switcher.system"),
            ("dark", "shell.theme_switcher.button.dark", "shell.theme_switcher.dark"),
            ("light", "shell.theme_switcher.button.light", "shell.theme_switcher.light"),
        ]
        for mode, text_key, tooltip_key in self._theme_btn_meta:
            btn = QPushButton(_t(text_key))
            btn.setFixedHeight(28)
            btn.setMinimumWidth(0)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.setToolTip(_t(tooltip_key))
            btn.setCursor(Qt.PointingHandCursor)
            btn.setProperty("themeSwitcherMode", mode)
            btn.clicked.connect(lambda checked, m=mode: self._on_theme_btn_clicked(m))
            h.addWidget(btn, 1)
            self._theme_btns[mode] = btn

        outer.addWidget(pill)
        self._theme_pill = pill
        return container

    def _on_theme_btn_clicked(self, mode: str):
        """主题切换按钮点击 -> 写入配置 -> ThemeManager 广播"""
        cfg = self._services.get("config")
        if cfg:
            try:
                cfg.set("OPEN_AUTOGLM_THEME", mode)
            except Exception as e:
                from PySide6.QtWidgets import QMessageBox
                msg = QMessageBox(self)
                msg.setWindowTitle(self._i18n_manager.t("dialog.save_fail.title"))
                msg.setText(str(e))
                msg.setIcon(QMessageBox.Warning)
                msg.setStyleSheet(self._dialog_style())
                msg.exec()
                self._sync_theme_switcher()
        else:
            self.apply_theme(mode)

    def _sync_theme_switcher(self):
        """将切换按钮选中状态同步到当前主题设置"""
        current = self._get_current_theme()
        for mode, btn in getattr(self, "_theme_btns", {}).items():
            # 用 blockSignals 避免触发 clicked 信号
            btn.blockSignals(True)
            btn.setChecked(mode == current)
            btn.blockSignals(False)

    def _apply_theme_switcher_tokens(self, tokens: ThemeTokens):
        """根据当前 tokens 更新主题切换器壳层颜色"""
        if not hasattr(self, "_theme_btns"):
            return
        if hasattr(self, "_theme_pill"):
            self._theme_pill.setStyleSheet(
                f"QFrame#ThemeSwitcherPill {{ background:{tokens.bg_elevated};"
                f" border:1px solid {tokens.border}; border-radius:11px; }}"
            )
        if hasattr(self, "_theme_hint_lbl"):
            self._theme_hint_lbl.setStyleSheet(
                f"color:{tokens.text_muted}; font-size:10px; font-weight:600;"
                " background: transparent; border: none;"
            )
        _btn_style = f"""
            QPushButton {{
                background: transparent;
                border: 1px solid transparent;
                border-radius: 8px;
                color: {tokens.text_muted};
                font-size: 11px;
                font-weight: 600;
                padding: 0 4px;
                min-height: 24px;
            }}
            QPushButton:hover {{
                background: {tokens.nav_hover_bg};
                color: {tokens.text_primary};
            }}
            QPushButton:pressed {{
                background: {tokens.accent_soft};
                color: {tokens.accent};
            }}
            QPushButton:checked {{
                background: {tokens.bg_secondary if tokens.is_light() else tokens.bg_btn};
                border: 1px solid {tokens.border};
                color: {tokens.accent};
            }}
            QPushButton:checked:hover {{
                color: {tokens.accent_hover};
            }}
        """
        for btn in self._theme_btns.values():
            btn.setStyleSheet(_btn_style)

    def _init_pages(self):
        """初始化所有页面并加入 StackedWidget"""
        from gui.pages.dashboard_page import DashboardPage
        from gui.pages.device_page import DevicePage
        from gui.pages.history_page import HistoryPage
        from gui.pages.settings_page import SettingsPage
        from gui.pages.diagnostics_page import DiagnosticsPage

        self._page_dashboard = DashboardPage(self._services)
        self._page_device = DevicePage(self._services)
        self._page_history = HistoryPage(self._services)
        self._page_settings = SettingsPage(self._services)
        self._page_diag = DiagnosticsPage(self._services)

        self._pages = {
            "dashboard": self._page_dashboard,
            "device":    self._page_device,
            "history":   self._page_history,
            "settings":  self._page_settings,
            "diag":      self._page_diag,
        }

        for page in self._pages.values():
            self._stack.addWidget(page)
            self._page_adapter.register_page(page)
            self._i18n_adapter.register_page(page)

        self._stack.setCurrentWidget(self._page_dashboard)
        # 推送初始 i18n 状态
        self._i18n_adapter.push_current()

    def _connect_signals(self):
        for key, btn in self._nav_buttons.items():
            btn.clicked.connect(lambda checked, k=key: self._switch_page(k))

        # 默认选中工作台
        self._nav_buttons["dashboard"].setChecked(True)

        # 监听任务服务的接管请求，在任意页面都能收到
        task = self._services.get("task")
        if task:
            task.takeover_requested.connect(self._on_takeover_request)
            task.stuck_detected.connect(self._on_stuck_detected)
            # 注入 i18n 服务（TaskService 初始化时尚未有 i18n）
            if hasattr(task, "set_i18n"):
                task.set_i18n(self._i18n_manager)

        # 监听配置变化以实时切换主题
        cfg = self._services.get("config")
        if cfg:
            cfg.config_changed.connect(self._on_config_changed)

    def _switch_page(self, key: str):
        page = self._pages.get(key)
        if page:
            switching = self._stack.currentWidget() is not page
            self._stack.setCurrentWidget(page)
            # 淡入过渡；工作台页可能承载 scrcpy 原生宿主，跳过图形效果
            if switching and key != "dashboard":
                play_page_fade(page)
            # 通知页面已激活（可选刷新）
            if hasattr(page, "on_page_activated"):
                page.on_page_activated()

    def switch_page(self, key: str):
        """公开页面切换入口，供页面内部按钮/服务回调用。"""
        btn = self._nav_buttons.get(key)
        if btn:
            btn.setChecked(True)
        self._switch_page(key)

    # ---------- 接管/卡住 弹窗 ----------

    def _on_takeover_request(self, reason: str):
        from PySide6.QtWidgets import QMessageBox
        _t = self._i18n_manager.t
        msg = QMessageBox(self)
        msg.setWindowTitle(_t("dialog.takeover.title"))
        msg.setText(_t("dialog.takeover.text", reason=reason))
        msg.setInformativeText(_t("dialog.takeover.info"))
        msg.setIcon(QMessageBox.Warning)
        msg.setStandardButtons(QMessageBox.Ok)
        msg.setStyleSheet(self._dialog_style())
        # 切换到工作台以便用户操作
        self._switch_page("dashboard")
        self._nav_buttons["dashboard"].setChecked(True)
        msg.exec()

    def _on_stuck_detected(self):
        from PySide6.QtWidgets import QMessageBox
        _t = self._i18n_manager.t
        task = self._services.get("task")
        msg = QMessageBox(self)
        msg.setWindowTitle(_t("dialog.stuck.title"))
        msg.setText(_t("dialog.stuck.text"))
        msg.setInformativeText(_t("dialog.stuck.info"))
        msg.setIcon(QMessageBox.Question)
        msg.setStyleSheet(self._dialog_style())
        btn_wait = msg.addButton(_t("dialog.stuck.btn.wait"), QMessageBox.AcceptRole)
        btn_takeover = msg.addButton(_t("dialog.stuck.btn.takeover"), QMessageBox.ActionRole)
        btn_stop = msg.addButton(_t("dialog.stuck.btn.stop"), QMessageBox.DestructiveRole)
        msg.exec()
        clicked = msg.clickedButton()
        if clicked == btn_stop and task:
            task.stop_task()
        elif clicked == btn_takeover and task:
            task.request_takeover(_t("dialog.stuck.takeover_reason"))

    # ---------- 主题系统 ----------

    def _get_current_theme(self) -> str:
        """从配置服务读取主题设置，默认 system"""
        cfg = self._services.get("config")
        if cfg:
            return cfg.get("OPEN_AUTOGLM_THEME") or "system"
        return "system"

    def apply_theme(self, theme: str = "system"):
        """
        应用指定主题（兼容入口）。

        内部委托给 ThemeManager.set_preference()，
        ThemeManager 负责解析 system 模式并广播 theme_changed。
        """
        self._theme_manager.set_preference(theme)

    def _on_config_changed(self):
        """配置变化时重新应用主题；若语言变化则切换 GUI 语言。"""
        self.apply_theme(self._get_current_theme())
        cfg = self._services.get("config")
        if cfg:
            new_lang = cfg.get("OPEN_AUTOGLM_LANG") or "cn"
            if new_lang != self._i18n_manager.get_language():
                self._i18n_manager.set_language(new_lang)

    def _on_language_changed(self, lang: str):
        """I18nManager.language_changed 回调 - 更新壳层文案。"""
        self.setWindowTitle(self._i18n_manager.t("shell.window.title"))
        # 更新导航按钮文字
        for key, _icon, i18n_key in getattr(self, "_nav_items_meta", []):
            btn = self._nav_buttons.get(key)
            if btn and hasattr(btn, "set_label"):
                btn.set_label(self._i18n_manager.t(i18n_key))
            elif btn:
                # 回退：直接更新文本（NavButton 可能没有 set_label）
                if hasattr(btn, "setText"):
                    btn.setText(self._i18n_manager.t(i18n_key))
        if hasattr(self, "_ver_lbl"):
            self._ver_lbl.setText(
                self._i18n_manager.t("shell.footer.version", version=self._app_version)
            )
        # 更新主题切换器提示标签、按钮文字与 tooltip
        _t = self._i18n_manager.t
        if hasattr(self, "_theme_hint_lbl"):
            self._theme_hint_lbl.setText(_t("shell.theme_switcher.label"))
        if hasattr(self, "_theme_btns"):
            for mode, text_key, tooltip_key in getattr(self, "_theme_btn_meta", []):
                btn = self._theme_btns.get(mode)
                if btn:
                    btn.setText(_t(text_key))
                    btn.setToolTip(_t(tooltip_key))

    def _on_tokens_changed(self, tokens: ThemeTokens):
        """
        ThemeManager.theme_changed 回调。
        负责：壳层全局 QSS + 导航组件 + 侧边栏局部样式。
        页面分发由 PageThemeAdapter 处理。
        """
        # 应用全局壳层 QSS
        self._shell_styler.apply(tokens)

        # 更新壳层局部内联样式
        if hasattr(self, "_nav_panel"):
            self._nav_panel.setStyleSheet(
                f"QWidget#SidebarPanel {{ background:{tokens.bg_nav};"
                f" border-right:1px solid {tokens.sep_color}; }}"
            )
        if hasattr(self, "_stack"):
            # 必须使用作用域选择器：裸声明会作为通用规则级联到栈内
            # 所有后代控件（标签/复选框会被涂上底色块）
            self._stack.setStyleSheet(
                f"QStackedWidget#ContentStack {{ background:{tokens.bg_main}; }}"
            )
        if hasattr(self, "_brand_icon_lbl"):
            family = fa_family()
            icon_css = f"font-family:'{family}'; font-size:17px;" if family else "font-size:17px;"
            self._brand_icon_lbl.setStyleSheet(
                f"color:{tokens.accent}; background:transparent; {icon_css}"
            )
        if hasattr(self, "_logo_lbl"):
            self._logo_lbl.setStyleSheet(
                f"color:{tokens.text_primary}; background:transparent; letter-spacing:0.3px;"
            )
        if hasattr(self, "_ver_lbl"):
            self._ver_lbl.setStyleSheet(
                f"color:{tokens.text_muted}; font-size:10px; background:transparent;"
            )

        # 更新主题切换器样式并同步选中态
        self._apply_theme_switcher_tokens(tokens)
        self._sync_theme_switcher()

        # 更新导航按钮主题
        for btn in getattr(self, "_nav_buttons", {}).values():
            apply_fn = getattr(btn, "apply_theme_tokens", None)
            if callable(apply_fn):
                apply_fn(tokens)
            elif hasattr(btn, "apply_theme"):
                btn.apply_theme(tokens.to_legacy_dict(), tokens.mode)

        # 更新 themeMode 属性（用于 QSS 属性选择器）
        self.setProperty("themeMode", tokens.mode)

    def _dialog_style(self) -> str:
        """获取当前主题的 QMessageBox 样式。"""
        from gui.theme.styles.dialogs import dialog_message_box
        tokens = self._theme_manager.get_tokens()
        return dialog_message_box(tokens)

    # ---------- 窗口关闭 ----------

    def closeEvent(self, event):
        """窗口关闭时统一清理资源（按顺序：page -> task -> mirror -> device -> theme）"""
        for page in getattr(self, "_pages", {}).values():
            shutdown = getattr(page, "shutdown", None)
            if callable(shutdown):
                shutdown()

        task = self._services.get("task")
        if task:
            # shutdown() 阻塞等待子进程与 reader 线程完全结束
            task.shutdown(timeout_ms=5000)

        mirror = self._services.get("mirror")
        if mirror:
            mirror.shutdown()

        device = self._services.get("device")
        if device:
            device.stop()

        config = self._services.get("config")
        if config and hasattr(config, "shutdown"):
            config.shutdown()

        # 停止系统主题监听
        self._theme_manager.stop()

        super().closeEvent(event)
