# -*- coding: utf-8 -*-
"""
gui/theme/styles/shell.py - 壳层全局 QSS 生成

只负责真正适合全局化的部分：
  - 窗口/Widget 基础背景与文字
  - 导航区
  - 滚动条（悬浮式细滚动条，hover 加粗提亮）
  - GroupBox 框架
  - QTabWidget（pill 风格 TabBar）
  - QLabel 语义 role
  - QSplitter
  - QComboBox
  - QCheckBox（圆角指示器）
  - QToolTip
  - 输入框（全局 fallback，含焦点描边）
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
    nav_grad = (
        "qlineargradient(x1:0, y1:0, x2:0, y2:1, "
        f"stop:0 {t.bg_nav}, stop:1 {t.bg_main})"
    )
    return f"""
        /* ====== 基础 ====== */
        QMainWindow, QWidget {{
            background: {t.bg_main};
            color: {t.text_primary};
            font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
            font-size: 13px;
        }}
        QWidget#NavPanel {{
            background: {nav_grad};
        }}
        QStackedWidget#ContentStack {{
            background: {t.bg_main};
        }}

        /* ====== 工具提示 ====== */
        QToolTip {{
            background: {t.bg_elevated};
            color: {t.text_primary};
            border: 1px solid {t.border};
            border-radius: 6px;
            padding: 5px 8px;
            font-size: 12px;
        }}

        /* ====== 滚动条（悬浮式）====== */
        QScrollBar:vertical {{
            background: transparent;
            width: 10px;
            margin: 2px;
        }}
        QScrollBar::handle:vertical {{
            background: {t.border};
            border-radius: 3px;
            min-height: 32px;
            margin: 0 2px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {t.border_hover};
            margin: 0;
            border-radius: 5px;
        }}
        QScrollBar::add-line, QScrollBar::sub-line {{
            height: 0;
            width: 0;
        }}
        QScrollBar::add-page, QScrollBar::sub-page {{
            background: transparent;
        }}
        QScrollBar:horizontal {{
            background: transparent;
            height: 10px;
            margin: 2px;
        }}
        QScrollBar::handle:horizontal {{
            background: {t.border};
            border-radius: 3px;
            min-width: 32px;
            margin: 2px 0;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: {t.border_hover};
            margin: 0;
            border-radius: 5px;
        }}

        /* ====== 输入框 fallback ====== */
        QLineEdit, QTextEdit, QPlainTextEdit {{
            background: {t.bg_secondary};
            border: 1px solid {t.border};
            border-radius: 9px;
            color: {t.text_primary};
            padding: 6px 10px;
            selection-background-color: {t.selection_bg};
        }}
        QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover {{
            border-color: {t.border_hover};
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
            border: 1px solid {t.accent};
            background: {t.bg_main};
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
            border-radius: 8px;
            padding: 6px 10px;
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
            border-radius: 14px;
            color: {t.text_primary};
            font-weight: 600;
            margin-top: 14px;
            padding-top: 14px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 16px;
            padding: 0 6px;
            color: {t.text_secondary};
            font-size: 12px;
            letter-spacing: 0.4px;
        }}

        /* ====== TabWidget（pill 风格）====== */
        QTabWidget::pane {{
            background: {t.bg_secondary};
            border: 1px solid {t.border};
            border-radius: 10px;
            top: 6px;
        }}
        QTabBar {{
            qproperty-drawBase: 0;
        }}
        QTabBar::tab {{
            background: transparent;
            color: {t.text_muted};
            border: 1px solid transparent;
            border-radius: 8px;
            padding: 6px 14px;
            margin-right: 4px;
            font-size: 13px;
        }}
        QTabBar::tab:selected {{
            background: {t.accent_soft};
            color: {t.accent};
            border-color: transparent;
            font-weight: 600;
        }}
        QTabBar::tab:hover:!selected {{
            background: {t.nav_hover_bg};
            color: {t.text_primary};
        }}

        /* ====== Splitter ====== */
        QSplitter::handle {{
            background: {t.border};
            border-radius: 999px;
        }}
        QSplitter::handle:hover {{
            background: {t.accent};
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
            border-radius: 9px;
            color: {t.text_primary};
            padding: 6px 10px;
        }}
        QComboBox:hover {{
            border-color: {t.border_hover};
            background: {t.bg_btn};
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
            border-radius: 10px;
            color: {t.text_primary};
            selection-background-color: {t.accent_soft};
            selection-color: {t.accent};
            padding: 4px;
            outline: none;
        }}

        /* ====== CheckBox ====== */
        QCheckBox {{
            color: {t.text_secondary};
            spacing: 7px;
            background: transparent;
        }}
        QCheckBox:hover {{
            color: {t.text_primary};
        }}
        QCheckBox::indicator {{
            width: 16px;
            height: 16px;
            border: 1px solid {t.border_hover};
            border-radius: 5px;
            background: {t.bg_secondary};
        }}
        QCheckBox::indicator:hover {{
            border-color: {t.accent};
        }}
        QCheckBox::indicator:checked {{
            background: {t.accent};
            border-color: {t.accent};
        }}
        QCheckBox::indicator:disabled {{
            background: {t.bg_elevated};
            border-color: {t.border};
        }}

        /* ====== 按钮基础 fallback（仅保留无任何 setStyleSheet 覆盖时的默认外观）====== */
        /* variant 语义按钮应使用 ComponentStyleRegistry 或直接调用 styles/buttons.py 函数 */
        QPushButton {{
            background-color: {t.bg_elevated};
            border: 1px solid {t.border};
            border-radius: 9px;
            color: {t.text_primary};
            padding: 7px 14px;
            font-size: 13px;
        }}
        QPushButton:hover {{
            background-color: {t.bg_btn};
            border-color: {t.border_hover};
        }}
        QPushButton:pressed {{
            background-color: {t.bg_secondary};
            padding-top: 8px;
        }}
        QPushButton:disabled {{
            background-color: {t.bg_elevated};
            color: {t.text_muted};
            border-color: {t.border};
        }}
    """
