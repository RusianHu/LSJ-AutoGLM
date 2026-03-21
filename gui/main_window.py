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
        self.setWindowTitle("Open-AutoGLM")
        self.setMinimumSize(self.MIN_WIDTH, self.MIN_HEIGHT)
        self.resize(1440, 900)
        self._apply_global_style()
        self._build_ui()
        self._connect_signals()

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
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("background:#1e2330; border:none; max-width:1px;")
        root_layout.addWidget(sep)

        # 右侧内容区
        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background:#0d1117;")
        root_layout.addWidget(self._stack, 1)

        # 延迟导入页面（避免循环依赖）
        self._init_pages()

    def _build_nav(self) -> QWidget:
        nav = QWidget()
        nav.setFixedWidth(self.NAV_WIDTH)
        nav.setStyleSheet("background:#13192a;")
        layout = QVBoxLayout(nav)
        layout.setContentsMargins(12, 20, 12, 20)
        layout.setSpacing(4)

        # Logo
        logo_lbl = QLabel("AutoGLM")
        logo_lbl.setFont(QFont("Segoe UI", 15, QFont.Bold))
        logo_lbl.setStyleSheet("color:#529bf5; padding:4px 8px 16px 8px;")
        layout.addWidget(logo_lbl)

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
        ver_lbl = QLabel("v0.1 Alpha")
        ver_lbl.setStyleSheet("color:#3a4560; font-size:10px; padding:4px 8px;")
        layout.addWidget(ver_lbl)

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

    # ---------- 全局样式 ----------

    def _apply_global_style(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background: #0d1117;
                color: #c9d1d9;
                font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
                font-size: 13px;
            }
            QScrollBar:vertical {
                background: #161b22;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #30363d;
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #484f58;
            }
            QScrollBar:horizontal {
                background: #161b22;
                height: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:horizontal {
                background: #30363d;
                border-radius: 4px;
                min-width: 20px;
            }
            QScrollBar::add-line, QScrollBar::sub-line { height:0; width:0; }
            QPushButton {
                background: #21262d;
                border: 1px solid #30363d;
                border-radius: 6px;
                color: #c9d1d9;
                padding: 6px 14px;
                font-size: 13px;
            }
            QPushButton:hover {
                background: #30363d;
                border-color: #484f58;
            }
            QPushButton:pressed {
                background: #161b22;
            }
            QPushButton:disabled {
                background: #161b22;
                color: #484f58;
                border-color: #21262d;
            }
            QLineEdit, QTextEdit, QPlainTextEdit {
                background: #161b22;
                border: 1px solid #30363d;
                border-radius: 6px;
                color: #c9d1d9;
                padding: 6px 10px;
                selection-background-color: #264f78;
            }
            QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
                border-color: #529bf5;
            }
            QLabel {
                color: #c9d1d9;
                background: transparent;
            }
            QGroupBox {
                border: 1px solid #30363d;
                border-radius: 8px;
                margin-top: 12px;
                padding: 12px 8px 8px 8px;
                color: #8b949e;
                font-size: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                color: #8b949e;
            }
            QComboBox {
                background: #161b22;
                border: 1px solid #30363d;
                border-radius: 6px;
                color: #c9d1d9;
                padding: 5px 10px;
            }
            QComboBox:focus { border-color: #529bf5; }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background: #161b22;
                border: 1px solid #30363d;
                selection-background-color: #264f78;
            }
            QSplitter::handle {
                background: #21262d;
            }
            QSplitter::handle:horizontal { width: 4px; }
            QSplitter::handle:vertical  { height: 4px; }
            QTableWidget {
                background: #0d1117;
                border: 1px solid #21262d;
                gridline-color: #21262d;
                color: #c9d1d9;
            }
            QTableWidget::item:selected {
                background: #264f78;
            }
            QHeaderView::section {
                background: #161b22;
                color: #8b949e;
                border: none;
                border-bottom: 1px solid #21262d;
                padding: 6px 10px;
                font-size: 12px;
            }
            QTabWidget::pane {
                border: 1px solid #21262d;
                border-radius: 4px;
            }
            QTabBar::tab {
                background: #161b22;
                color: #8b949e;
                border: 1px solid #21262d;
                border-bottom: none;
                padding: 6px 16px;
                border-radius: 4px 4px 0 0;
            }
            QTabBar::tab:selected {
                background: #0d1117;
                color: #c9d1d9;
                border-color: #30363d;
            }
            QTabBar::tab:hover {
                background: #21262d;
            }
        """)

    @staticmethod
    def _dialog_style() -> str:
        return """
            QMessageBox {
                background: #161b22;
                color: #c9d1d9;
            }
            QMessageBox QLabel {
                color: #c9d1d9;
            }
            QPushButton {
                background: #21262d;
                border: 1px solid #30363d;
                border-radius: 6px;
                color: #c9d1d9;
                padding: 6px 18px;
                min-width: 80px;
            }
            QPushButton:hover { background: #30363d; }
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
