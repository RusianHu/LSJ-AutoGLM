# -*- coding: utf-8 -*-
"""主窗口 - 左侧多页导航框架"""

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from gui.widgets.nav_button import NavButton
from gui.theme.manager import ThemeManager
from gui.theme.preferences import ThemePreference
from gui.theme.global_shell import GlobalShellStyler
from gui.theme.page_adapter import PageThemeAdapter
from gui.theme.tokens import ThemeTokens


class MainWindow(QMainWindow):
    """
    主窗口。
    布局：左侧导航栏 (220px) + 右侧内容区（StackedWidget）。

    主题系统：
      - 由 ThemeManager 统一管理主题解析与广播
      - GlobalShellStyler 负责应用壳层全局 QSS
      - PageThemeAdapter 负责将 tokens 推送到各页面
      - MainWindow.apply_theme 作为兼容入口，内部委托给 ThemeManager
    """

    NAV_WIDTH = 200
    MIN_WIDTH = 1280
    MIN_HEIGHT = 780

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

        # 暴露给 services，让需要的服务可以访问
        self._services["theme_manager"] = self._theme_manager

        self.setWindowTitle("LSJ AutoGLM")
        self.setMinimumSize(self.MIN_WIDTH, self.MIN_HEIGHT)
        self.resize(1440, 900)
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

        # 左侧导航
        self._nav_panel = self._build_nav()
        root_layout.addWidget(self._nav_panel)

        # 分隔线
        self._sep = QFrame()
        self._sep.setObjectName("MainSeparator")
        self._sep.setFrameShape(QFrame.VLine)
        self._sep.setStyleSheet("background:#1e2330; border:none; max-width:1px;")
        root_layout.addWidget(self._sep)

        # 右侧内容区
        self._stack = QStackedWidget()
        self._stack.setObjectName("ContentStack")
        self._stack.setStyleSheet("background:#0d1117;")
        root_layout.addWidget(self._stack, 1)

        # 延迟导入页面（避免循环依赖）
        self._init_pages()

    def _build_nav(self) -> QWidget:
        nav = QWidget()
        nav.setObjectName("NavPanel")
        nav.setFixedWidth(self.NAV_WIDTH)
        nav.setStyleSheet("background:#13192a;")
        layout = QVBoxLayout(nav)
        layout.setContentsMargins(12, 20, 12, 20)
        layout.setSpacing(4)

        # Logo
        self._logo_lbl = QLabel("LSJ AutoGLM")
        self._logo_lbl.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self._logo_lbl.setStyleSheet("color:#529bf5; padding:4px 8px 16px 8px;")
        layout.addWidget(self._logo_lbl)

        # 导航按钮
        self._btn_group = QButtonGroup(self)
        self._btn_group.setExclusive(True)

        nav_items = [
            ("dashboard", "[=]", "工作台"),
            ("device",    "[D]", "设备"),
            ("history",   "[H]", "历史"),
            ("settings",  "[S]", "设置"),
            ("diag",      "[?]", "诊断"),
        ]
        self._nav_buttons = {}
        for key, icon, label in nav_items:
            btn = NavButton(icon, label)
            self._btn_group.addButton(btn)
            layout.addWidget(btn)
            self._nav_buttons[key] = btn

        layout.addStretch(1)

        # 底部版本号
        self._ver_lbl = QLabel("v0.1 Alpha")
        self._ver_lbl.setStyleSheet("color:#3a4560; font-size:10px; padding:4px 8px;")
        layout.addWidget(self._ver_lbl)

        return nav

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

        self._stack.setCurrentWidget(self._page_dashboard)

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

        # 监听配置变化以实时切换主题
        cfg = self._services.get("config")
        if cfg:
            cfg.config_changed.connect(self._on_config_changed)

    def _switch_page(self, key: str):
        page = self._pages.get(key)
        if page:
            self._stack.setCurrentWidget(page)
            # 通知页面已激活（可选刷新）
            if hasattr(page, "on_page_activated"):
                page.on_page_activated()

    # ---------- 接管/卡住 弹窗 ----------

    def _on_takeover_request(self, reason: str):
        from PySide6.QtWidgets import QMessageBox
        msg = QMessageBox(self)
        msg.setWindowTitle("人工接管请求")
        msg.setText(f"Agent 请求人工接管\n\n原因：{reason}")
        msg.setInformativeText("任务已暂停，请在手机镜像中完成操作后点击\"继续执行\"。")
        msg.setIcon(QMessageBox.Warning)
        msg.setStandardButtons(QMessageBox.Ok)
        msg.setStyleSheet(self._dialog_style())
        # 切换到工作台以便用户操作
        self._switch_page("dashboard")
        self._nav_buttons["dashboard"].setChecked(True)
        msg.exec()

    def _on_stuck_detected(self):
        from PySide6.QtWidgets import QMessageBox
        task = self._services.get("task")
        msg = QMessageBox(self)
        msg.setWindowTitle("任务可能卡住")
        msg.setText("超过 120 秒未收到输出，任务可能已卡住。")
        msg.setInformativeText("请选择处理方式：")
        msg.setIcon(QMessageBox.Question)
        msg.setStyleSheet(self._dialog_style())
        btn_wait = msg.addButton("继续等待", QMessageBox.AcceptRole)
        btn_takeover = msg.addButton("人工接管", QMessageBox.ActionRole)
        btn_stop = msg.addButton("终止任务", QMessageBox.DestructiveRole)
        msg.exec()
        clicked = msg.clickedButton()
        if clicked == btn_stop and task:
            task.stop_task()
        elif clicked == btn_takeover and task:
            task.request_takeover("用户响应卡住提示")

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
        """配置变化时重新应用主题。"""
        self.apply_theme(self._get_current_theme())

    def _on_tokens_changed(self, tokens: ThemeTokens):
        """
        ThemeManager.theme_changed 回调。
        负责：壳层全局 QSS + 导航组件 + 分隔线等壳层局部样式。
        页面分发由 PageThemeAdapter 处理。
        """
        # 应用全局壳层 QSS
        self._shell_styler.apply(tokens)

        # 更新壳层局部内联样式
        if hasattr(self, "_nav_panel"):
            self._nav_panel.setStyleSheet(f"background:{tokens.bg_nav};")
        if hasattr(self, "_sep"):
            self._sep.setStyleSheet(
                f"background:{tokens.sep_color}; border:none; max-width:1px;"
            )
        if hasattr(self, "_stack"):
            self._stack.setStyleSheet(f"background:{tokens.bg_main};")
        if hasattr(self, "_logo_lbl"):
            self._logo_lbl.setStyleSheet(
                f"color:{tokens.accent}; padding:4px 8px 16px 8px;"
            )
        if hasattr(self, "_ver_lbl"):
            self._ver_lbl.setStyleSheet(
                f"color:{tokens.text_muted}; font-size:10px; padding:4px 8px;"
            )

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

        # 停止系统主题监听
        self._theme_manager.stop()

        super().closeEvent(event)
