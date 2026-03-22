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


class MainWindow(QMainWindow):
    """
    主窗口。
    布局：左侧导航栏 (220px) + 右侧内容区（StackedWidget）。
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
        self.setWindowTitle("LSJ AutoGLM")
        self.setMinimumSize(self.MIN_WIDTH, self.MIN_HEIGHT)
        self.resize(1440, 900)
        self._build_ui()
        self._connect_signals()
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

        pages = [
            ("dashboard", self._page_dashboard),
            ("device",    self._page_device),
            ("history",   self._page_history),
            ("settings",  self._page_settings),
            ("diag",      self._page_diag),
        ]
        self._pages = {}
        for key, page in pages:
            self._stack.addWidget(page)
            self._pages[key] = page

    # ---------- 信号连接 ----------

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

    # ---------- 主题常量 ----------

    _DARK_VARS = {
        "bg_main":       "#0d1117",
        "bg_nav":        "#101826",
        "bg_toolbar":    "#111827",
        "bg_status":     "#0b1220",
        "bg_secondary":  "#161b22",
        "bg_elevated":   "#1b2432",
        "bg_btn":        "#21262d",
        "bg_console":    "#0a0f18",
        "sep_color":     "#243042",
        "text_primary":  "#d7dee7",
        "text_secondary":"#9ba7b4",
        "text_muted":    "#66778d",
        "border":        "#303b4a",
        "border_hover":  "#4b5b70",
        "accent":        "#4f8cff",
        "accent_hover":  "#6aa4ff",
        "accent_soft":   "rgba(79, 140, 255, 0.16)",
        "selection_bg":  "#264f78",
        "success":       "#3fb950",
        "success_bg":    "#0f2d1a",
        "success_border": "#1f6d3c",
        "warning":       "#e3b341",
        "warning_bg":    "#3d2800",
        "warning_border": "#6e4800",
        "danger":        "#f85149",
        "danger_bg":     "#3d1a1a",
        "danger_border": "#8f2d2b",
        "nav_text":      "#a9b5c7",
        "nav_text_hover": "#e2e8f0",
        "nav_hover_bg":  "rgba(255,255,255,0.06)",
    }

    _LIGHT_VARS = {
        "bg_main":       "#f4f7fb",
        "bg_nav":        "#edf3fb",
        "bg_toolbar":    "#ffffff",
        "bg_status":     "#f7f9fc",
        "bg_secondary":  "#ffffff",
        "bg_elevated":   "#eef3f9",
        "bg_btn":        "#eef2f7",
        "bg_console":    "#f8fbff",
        "sep_color":     "#d7dee8",
        "text_primary":  "#18212f",
        "text_secondary":"#526273",
        "text_muted":    "#7b8aa0",
        "border":        "#d5deea",
        "border_hover":  "#a9b6c7",
        "accent":        "#2563eb",
        "accent_hover":  "#3b82f6",
        "accent_soft":   "rgba(37, 99, 235, 0.12)",
        "selection_bg":  "#dbeafe",
        "success":       "#166534",
        "success_bg":    "#dcfce7",
        "success_border": "#16a34a",
        "warning":       "#92400e",
        "warning_bg":    "#fef3c0",
        "warning_border": "#c28b00",
        "danger":        "#b91c1c",
        "danger_bg":     "#fee2e5",
        "danger_border": "#c9525a",
        "nav_text":      "#60708a",
        "nav_text_hover": "#1e2a3a",
        "nav_hover_bg":  "rgba(37, 99, 235, 0.08)",
    }

    # ---------- 主题切换 ----------

    def _get_current_theme(self) -> str:
        """从配置服务读取主题设置，默认 system"""
        cfg = self._services.get("config")
        if cfg:
            return cfg.get("OPEN_AUTOGLM_THEME") or "system"
        return "system"

    def apply_theme(self, theme: str = "system"):
        """应用指定主题（system/dark/light），system 时自动检测操作系统深浅色"""
        if theme == "system":
            from PySide6.QtWidgets import QApplication
            from PySide6.QtGui import QPalette
            palette = QApplication.instance().palette()
            is_dark = palette.color(QPalette.ColorRole.Window).lightness() < 128
            theme = "dark" if is_dark else "light"

        v = self._DARK_VARS if theme == "dark" else self._LIGHT_VARS
        self._resolved_theme = theme
        self._theme_vars = v
        self.setProperty("themeMode", theme)
        self._apply_global_style(v)

        # 更新各子组件内联样式
        if hasattr(self, "_nav_panel"):
            self._nav_panel.setStyleSheet(f"background:{v['bg_nav']};")
        if hasattr(self, "_sep"):
            self._sep.setStyleSheet(
                f"background:{v['sep_color']}; border:none; max-width:1px;"
            )
        if hasattr(self, "_stack"):
            self._stack.setStyleSheet(f"background:{v['bg_main']};")
        if hasattr(self, "_logo_lbl"):
            self._logo_lbl.setStyleSheet(
                f"color:{v['accent']}; padding:4px 8px 16px 8px;"
            )
        if hasattr(self, "_ver_lbl"):
            self._ver_lbl.setStyleSheet(
                f"color:{v['text_muted']}; font-size:10px; padding:4px 8px;"
            )
        for btn in getattr(self, "_nav_buttons", {}).values():
            if hasattr(btn, "apply_theme"):
                btn.apply_theme(v, theme)
        for page in getattr(self, "_pages", {}).values():
            on_theme_changed = getattr(page, "on_theme_changed", None)
            if callable(on_theme_changed):
                on_theme_changed(theme, v)

    def _on_config_changed(self):
        """配置变化时重新应用主题"""
        self.apply_theme(self._get_current_theme())

    # ---------- 全局样式 ----------

    def _apply_global_style(self, v: dict):
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background: {v['bg_main']};
                color: {v['text_primary']};
                font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
                font-size: 13px;
            }}
            QWidget#NavPanel {{
                background: {v['bg_nav']};
            }}
            QStackedWidget#ContentStack {{
                background: {v['bg_main']};
            }}
            QWidget[role="toolbar"] {{
                background: {v['bg_toolbar']};
                border-bottom: 1px solid {v['border']};
            }}
            QWidget[role="statusBar"] {{
                background: {v['bg_status']};
                border-bottom: 1px solid {v['border']};
            }}
            QFrame#MainSeparator {{
                background: {v['sep_color']};
                border: none;
                max-width: 1px;
            }}
            QFrame[role="separator"] {{
                background: {v['border']};
                border: none;
                max-width: 1px;
            }}
            QFrame[role="divider"] {{
                background: {v['border']};
                border: none;
                max-height: 1px;
            }}
            QScrollArea {{
                border: none;
                background: transparent;
            }}
            QScrollArea > QWidget > QWidget {{
                background: transparent;
            }}
            QScrollBar:vertical {{
                background: {v['bg_elevated']};
                width: 10px;
                border-radius: 5px;
                margin: 2px;
            }}
            QScrollBar::handle:vertical {{
                background: {v['border']};
                border-radius: 5px;
                min-height: 28px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {v['border_hover']};
            }}
            QScrollBar:horizontal {{
                background: {v['bg_elevated']};
                height: 10px;
                border-radius: 5px;
                margin: 2px;
            }}
            QScrollBar::handle:horizontal {{
                background: {v['border']};
                border-radius: 5px;
                min-width: 28px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {v['border_hover']};
            }}
            QScrollBar::add-line, QScrollBar::sub-line {{
                height: 0;
                width: 0;
            }}
            QPushButton {{
                background-color: {v['bg_btn']};
                border: 1px solid {v['border']};
                border-radius: 8px;
                color: {v['text_primary']};
                padding: 6px 14px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {v['bg_elevated']};
                border-color: {v['border_hover']};
            }}
            QPushButton:pressed {{
                background-color: {v['bg_secondary']};
            }}
            QPushButton:disabled {{
                background-color: {v['bg_elevated']};
                color: {v['text_muted']};
                border-color: {v['border']};
            }}
            QPushButton[variant="primary"] {{
                background-color: {v['accent']};
                border-color: {v['accent']};
                color: #ffffff;
                font-weight: 600;
            }}
            QPushButton[variant="primary"]:hover {{
                background-color: {v['accent_hover']};
                border-color: {v['accent_hover']};
            }}
            QPushButton[variant="danger"] {{
                background-color: {v['danger_bg']};
                border-color: {v['danger_border']};
                color: {v['danger']};
                font-weight: 600;
            }}
            QPushButton[variant="danger"]:hover {{
                background-color: {v['danger_bg']};
                border-color: {v['danger']};
            }}
            QPushButton[variant="danger"]:disabled {{
                background-color: {v['bg_elevated']};
                border-color: {v['border']};
                color: {v['text_muted']};
            }}
            QPushButton[variant="warning"] {{
                background-color: {v['warning_bg']};
                border-color: {v['warning_border']};
                color: {v['warning']};
                font-weight: 600;
            }}
            QPushButton[variant="warning"]:hover {{
                background-color: {v['warning_bg']};
                border-color: {v['warning']};
            }}
            QPushButton[variant="warning"]:disabled {{
                background-color: {v['bg_elevated']};
                border-color: {v['border']};
                color: {v['text_muted']};
            }}
            QPushButton[variant="subtle"] {{
                background-color: {v['bg_btn']};
                border-color: {v['border']};
                color: {v['text_secondary']};
            }}
            QPushButton[variant="subtle"]:hover {{
                background-color: {v['bg_elevated']};
                color: {v['text_primary']};
                border-color: {v['border_hover']};
            }}
            QPushButton[variant="subtle"]:disabled {{
                background-color: {v['bg_elevated']};
                border-color: {v['border']};
                color: {v['text_muted']};
            }}
            QPushButton[variant="primary"]:disabled {{
                background-color: {v['bg_elevated']};
                border-color: {v['border']};
                color: {v['text_muted']};
            }}
            QPushButton[variant="success"] {{
                background-color: {v['success_bg']};
                border-color: {v['success_border']};
                color: {v['success']};
                font-weight: 600;
            }}
            QPushButton[variant="success"]:hover {{
                background-color: {v['success_bg']};
                border-color: {v['success']};
            }}
            QPushButton[variant="success"]:disabled {{
                background-color: {v['bg_elevated']};
                border-color: {v['border']};
                color: {v['text_muted']};
            }}
            QLineEdit, QTextEdit, QPlainTextEdit {{
                background: {v['bg_secondary']};
                border: 1px solid {v['border']};
                border-radius: 8px;
                color: {v['text_primary']};
                padding: 6px 10px;
                selection-background-color: {v['selection_bg']};
            }}
            QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
                border-color: {v['accent']};
            }}
            QLineEdit[readOnly="true"] {{
                background: {v['bg_elevated']};
                color: {v['text_muted']};
            }}
            QLabel {{
                color: {v['text_primary']};
                background: transparent;
            }}
            QLabel[role="pageTitle"] {{
                color: {v['text_primary']};
                font-size: 18px;
                font-weight: 700;
            }}
            QLabel[role="muted"] {{
                color: {v['text_secondary']};
                font-size: 12px;
            }}
            QLabel[role="subtle"] {{
                color: {v['text_muted']};
                font-size: 12px;
            }}
            QLabel[role="summaryCard"] {{
                background: {v['bg_secondary']};
                border: 1px solid {v['border']};
                border-radius: 8px;
                padding: 8px;
            }}
            QLabel[role="warningBanner"] {{
                background: {v['warning_bg']};
                border: 1px solid {v['warning_border']};
                color: {v['warning']};
                border-radius: 6px;
                padding: 6px;
                font-size: 12px;
            }}
            QGroupBox {{
                background: {v['bg_secondary']};
                border: 1px solid {v['border']};
                border-radius: 10px;
                margin-top: 14px;
                padding: 12px 10px 10px 10px;
                color: {v['text_secondary']};
                font-size: 12px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                color: {v['text_secondary']};
                background: {v['bg_main']};
            }}
            QComboBox {{
                background: {v['bg_secondary']};
                border: 1px solid {v['border']};
                border-radius: 8px;
                color: {v['text_primary']};
                padding: 5px 10px;
            }}
            QComboBox:hover {{
                border-color: {v['border_hover']};
            }}
            QComboBox:focus {{
                border-color: {v['accent']};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}
            QComboBox QAbstractItemView {{
                background: {v['bg_secondary']};
                border: 1px solid {v['border']};
                selection-background-color: {v['selection_bg']};
                color: {v['text_primary']};
                outline: none;
            }}
            QListWidget {{
                background: {v['bg_secondary']};
                border: 1px solid {v['border']};
                border-radius: 8px;
                color: {v['text_primary']};
                padding: 4px;
            }}
            QListWidget::item:selected {{
                background: {v['selection_bg']};
            }}
            QListWidget::item:hover {{
                background: {v['accent_soft']};
            }}
            QWidget[surface="console"] {{
                background: {v['bg_console']};
                border-radius: 8px;
            }}
            QPlainTextEdit[surface="console"],
            QListWidget[surface="console"] {{
                background: {v['bg_console']};
                border: 1px solid {v['border']};
                border-radius: 8px;
                color: {v['text_primary']};
            }}
            QListWidget[surface="console"]::item {{
                border-bottom: 1px solid {v['bg_elevated']};
            }}
            QSplitter::handle {{
                background: {v['bg_btn']};
            }}
            QSplitter::handle:horizontal {{
                width: 4px;
            }}
            QSplitter::handle:vertical {{
                height: 4px;
            }}
            QTableWidget {{
                background: {v['bg_secondary']};
                border: 1px solid {v['border']};
                gridline-color: {v['border']};
                color: {v['text_primary']};
            }}
            QTableWidget::item:selected {{
                background: {v['selection_bg']};
            }}
            QHeaderView::section {{
                background: {v['bg_elevated']};
                color: {v['text_secondary']};
                border: none;
                border-bottom: 1px solid {v['border']};
                padding: 6px 10px;
                font-size: 12px;
            }}
            QTabWidget::pane {{
                background: {v['bg_secondary']};
                border: 1px solid {v['border']};
                border-radius: 8px;
            }}
            QTabBar::tab {{
                background: {v['bg_elevated']};
                color: {v['text_secondary']};
                border: 1px solid {v['border']};
                border-bottom: none;
                padding: 6px 16px;
                border-radius: 8px 8px 0 0;
            }}
            QTabBar::tab:selected {{
                background: {v['bg_secondary']};
                color: {v['text_primary']};
                border-color: {v['border_hover']};
            }}
            QTabBar::tab:hover {{
                background: {v['bg_btn']};
            }}
        """)

    def _dialog_style(self) -> str:
        v = getattr(self, "_theme_vars", self._DARK_VARS)
        return f"""
            QMessageBox {{
                background: {v['bg_secondary']};
                color: {v['text_primary']};
            }}
            QMessageBox QLabel {{
                color: {v['text_primary']};
            }}
            QPushButton {{
                background-color: {v['bg_btn']};
                border: 1px solid {v['border']};
                border-radius: 8px;
                color: {v['text_primary']};
                padding: 6px 18px;
                min-width: 80px;
            }}
            QPushButton:hover {{
                background-color: {v['bg_elevated']};
                border-color: {v['border_hover']};
            }}
        """

    def closeEvent(self, event):
        """窗口关闭时统一清理资源（按顺序：page -> task -> mirror -> device）"""
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

        super().closeEvent(event)
