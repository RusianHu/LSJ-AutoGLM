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
  - 基础按钮 fallback（无 variant）

不在这里的：
  - variant 按钮样式（由 styles/buttons.py + ComponentStyleRegistry 处理）
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
            background: {t.bg_elevated};
            border: 1px solid {t.border};
            border-radius: 12px;
            padding: 10px 12px;
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
            border-radius: 16px;
            color: {t.text_primary};
            font-weight: 600;
            margin-top: 14px;
            padding-top: 14px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 16px;
            padding: 0 4px;
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
            border-radius: 999px;
        }}
        QSplitter::handle:horizontal {{
            width: 3px;
            margin: 14px 0;
        }}
        QSplitter::handle:vertical {{
            height: 3px;
            margin: 0 14px;
        }}

        /* ====== ComboBox ====== */
        QComboBox {{
            background: {t.bg_elevated};
            border: 1px solid {t.border};
            border-radius: 12px;
            color: {t.text_primary};
            padding: 6px 10px;
        }}
        QComboBox:hover {{
            border-color: {t.border_hover};
        }}
        QComboBox:focus {{
            border-color: {t.accent};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 22px;
        }}
        QComboBox QAbstractItemView {{
            background: {t.bg_elevated};
            border: 1px solid {t.border};
            border-radius: 12px;
            color: {t.text_primary};
            selection-background-color: {t.accent_soft};
            selection-color: {t.accent};
            padding: 4px;
            outline: none;
        }}

        /* ====== 按钮基础 fallback（仅保留无任何 setStyleSheet 覆盖时的默认外观）====== */
        /* variant 语义按钮应使用 ComponentStyleRegistry 或直接调用 styles/buttons.py 函数 */
        QPushButton {{
            background-color: {t.bg_elevated};
            border: 1px solid {t.border};
            border-radius: 12px;
            color: {t.text_primary};
            padding: 7px 14px;
            font-size: 13px;
        }}
        QPushButton:hover {{
            background-color: {t.bg_secondary};
            border-color: {t.border_hover};
        }}
        QPushButton:pressed {{
            background-color: {t.bg_btn};
        }}
        QPushButton:disabled {{
            background-color: {t.bg_elevated};
            color: {t.text_muted};
            border-color: {t.border};
        }}
    """
