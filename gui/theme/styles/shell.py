# -*- coding: utf-8 -*-
"""
gui/theme/styles/shell.py - 壳层全局 QSS 生成

只负责真正适合全局化的部分：
  - 窗口/Widget 基础背景与文字
  - 导航区
  - 滚动条
  - GroupBox 框架
  - QTabWidget
  - QLabel 语义 role
  - QSplitter
  - QComboBox
  - 输入框（全局 fallback）
  - 基础按钮 fallback（variant 模式）

不在这里的：
  - 复杂业务按钮的局部样式（由 styles/buttons.py 处理）
  - 对话框业务区域（由 styles/dialogs.py 处理）
  - 横幅（由 styles/banners.py 处理）
"""

from gui.theme.tokens import ThemeTokens


def shell_global_qss(t: ThemeTokens) -> str:
    """生成完整的全局壳层 QSS。"""
    return f"""
        /* ====== 基础 ====== */
        QMainWindow, QWidget {{
            background: {t.bg_main};
            color: {t.text_primary};
            font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
            font-size: 13px;
        }}
        QWidget#NavPanel {{
            background: {t.bg_nav};
        }}
        QStackedWidget#ContentStack {{
            background: {t.bg_main};
        }}

        /* ====== 滚动条 ====== */
        QScrollBar:vertical {{
            background: {t.bg_secondary};
            width: 8px;
            border-radius: 4px;
        }}
        QScrollBar::handle:vertical {{
            background: {t.border};
            border-radius: 4px;
            min-height: 24px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {t.border_hover};
        }}
        QScrollBar::add-line, QScrollBar::sub-line {{
            height: 0;
            width: 0;
        }}
        QScrollBar:horizontal {{
            background: {t.bg_secondary};
            height: 8px;
            border-radius: 4px;
        }}
        QScrollBar::handle:horizontal {{
            background: {t.border};
            border-radius: 4px;
            min-width: 24px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: {t.border_hover};
        }}

        /* ====== 输入框 fallback ====== */
        QLineEdit, QTextEdit, QPlainTextEdit {{
            background: {t.bg_secondary};
            border: 1px solid {t.border};
            border-radius: 8px;
            color: {t.text_primary};
            padding: 6px 10px;
            selection-background-color: {t.selection_bg};
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
            border-color: {t.accent};
        }}
        QLineEdit[readOnly="true"] {{
            background: {t.bg_elevated};
            color: {t.text_muted};
        }}

        /* ====== 标签语义 ====== */
        QLabel {{
            color: {t.text_primary};
            background: transparent;
        }}
        QLabel[role="pageTitle"] {{
            color: {t.text_primary};
            font-size: 18px;
            font-weight: 700;
        }}
        QLabel[role="muted"] {{
            color: {t.text_secondary};
            font-size: 12px;
        }}
        QLabel[role="subtle"] {{
            color: {t.text_muted};
            font-size: 12px;
        }}
        QLabel[role="summaryCard"] {{
            background: {t.bg_secondary};
            border: 1px solid {t.border};
            border-radius: 8px;
            padding: 8px;
        }}
        QLabel[role="warningBanner"] {{
            background: {t.warning_bg};
            border: 1px solid {t.warning_border};
            color: {t.warning};
            border-radius: 6px;
            padding: 6px;
            font-size: 12px;
        }}
        QLabel[role="statusMeta"] {{
            color: {t.text_muted};
            font-size: 12px;
        }}

        /* ====== GroupBox ====== */
        QGroupBox {{
            background: {t.bg_secondary};
            border: 1px solid {t.border};
            border-radius: 10px;
            color: {t.text_primary};
            font-weight: 600;
            margin-top: 10px;
            padding-top: 10px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 12px;
            color: {t.text_secondary};
            font-size: 12px;
        }}

        /* ====== TabWidget ====== */
        QTabWidget::pane {{
            background: {t.bg_secondary};
            border: 1px solid {t.border};
            border-radius: 8px;
        }}
        QTabBar::tab {{
            background: transparent;
            color: {t.text_muted};
            border: none;
            padding: 8px 16px;
            font-size: 13px;
        }}
        QTabBar::tab:selected {{
            color: {t.accent};
            border-bottom: 2px solid {t.accent};
            font-weight: 600;
        }}
        QTabBar::tab:hover:!selected {{
            color: {t.text_primary};
        }}

        /* ====== Splitter ====== */
        QSplitter::handle {{
            background: {t.border};
        }}
        QSplitter::handle:horizontal {{
            width: 1px;
        }}
        QSplitter::handle:vertical {{
            height: 1px;
        }}

        /* ====== ComboBox ====== */
        QComboBox {{
            background: {t.bg_btn};
            border: 1px solid {t.border};
            border-radius: 6px;
            color: {t.text_primary};
            padding: 4px 8px;
        }}
        QComboBox:hover {{
            border-color: {t.border_hover};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 20px;
        }}
        QComboBox QAbstractItemView {{
            background: {t.bg_elevated};
            border: 1px solid {t.border};
            color: {t.text_primary};
            selection-background-color: {t.accent_soft};
            selection-color: {t.accent};
        }}

        /* ====== 按钮 fallback（variant 属性模式，全局匹配）====== */
        QPushButton {{
            background-color: {t.bg_btn};
            border: 1px solid {t.border};
            border-radius: 8px;
            color: {t.text_primary};
            padding: 6px 14px;
            font-size: 13px;
        }}
        QPushButton:hover {{
            background-color: {t.bg_elevated};
            border-color: {t.border_hover};
        }}
        QPushButton:pressed {{
            background-color: {t.bg_secondary};
        }}
        QPushButton:disabled {{
            background-color: {t.bg_elevated};
            color: {t.text_muted};
            border-color: {t.border};
        }}
        QPushButton[variant="primary"] {{
            background-color: {t.accent};
            border-color: {t.accent};
            color: #ffffff;
            font-weight: 600;
        }}
        QPushButton[variant="primary"]:hover {{
            background-color: {t.accent_hover};
            border-color: {t.accent_hover};
        }}
        QPushButton[variant="primary"]:disabled {{
            background-color: {t.bg_elevated};
            border-color: {t.border};
            color: {t.text_muted};
        }}
        QPushButton[variant="danger"] {{
            background-color: {t.danger_bg};
            border-color: {t.danger_border};
            color: {t.danger};
            font-weight: 600;
        }}
        QPushButton[variant="danger"]:hover {{
            background-color: {t.danger_bg};
            border-color: {t.danger};
        }}
        QPushButton[variant="danger"]:disabled {{
            background-color: {t.bg_elevated};
            border-color: {t.border};
            color: {t.text_muted};
        }}
        QPushButton[variant="warning"] {{
            background-color: {t.warning_bg};
            border-color: {t.warning_border};
            color: {t.warning};
            font-weight: 600;
        }}
        QPushButton[variant="warning"]:hover {{
            background-color: {t.warning_bg};
            border-color: {t.warning};
        }}
        QPushButton[variant="warning"]:disabled {{
            background-color: {t.bg_elevated};
            border-color: {t.border};
            color: {t.text_muted};
        }}
    """
