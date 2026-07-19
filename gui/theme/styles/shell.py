# -*- coding: utf-8 -*-
"""
gui/theme/styles/shell.py - 壳层全局 QSS 生成

只负责真正适合全局化的部分：
  - 窗口/Widget 基础背景与文字
  - 侧边栏容器
  - 滚动条（悬浮式细滚动条，hover 提亮）
  - GroupBox（卡片式分区：标题置于卡片内部左上角）
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
    return f"""
        /* ====== 基础 ======
           背景由 GlobalShellStyler 设置的 QPalette 驱动；
           这里不放全局 QWidget background，避免其在祖先样式表
           级联中压过 QLabel 透明背景，给标签涂出底块。 */
        QMainWindow {{
            background: {t.bg_main};
        }}
        QWidget {{
            color: {t.text_primary};
            font-family: 'Segoe UI Variable Display', 'Segoe UI', 'Microsoft YaHei UI',
                         'Microsoft YaHei', sans-serif;
            font-size: 13px;
        }}
        QWidget#SidebarPanel {{
            background: {t.bg_nav};
            border-right: 1px solid {t.sep_color};
        }}
        QStackedWidget#ContentStack {{
            background: {t.bg_main};
        }}
        QScrollArea {{
            background: transparent;
            border: none;
        }}
        QAbstractScrollArea > QWidget > QWidget {{
            background: transparent;
        }}

        /* ====== 工具提示 ====== */
        QToolTip {{
            background: {t.bg_elevated};
            color: {t.text_primary};
            border: 1px solid {t.border};
            border-radius: 6px;
            padding: 6px 10px;
            font-size: 12px;
        }}

        /* ====== 滚动条（悬浮式）====== */
        QScrollBar:vertical {{
            background: transparent;
            width: 8px;
            margin: 2px;
        }}
        QScrollBar::handle:vertical {{
            background: {t.border};
            border-radius: 3px;
            min-height: 36px;
            margin: 0 1px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {t.border_hover};
            margin: 0;
            border-radius: 4px;
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
            height: 8px;
            margin: 2px;
        }}
        QScrollBar::handle:horizontal {{
            background: {t.border};
            border-radius: 3px;
            min-width: 36px;
            margin: 1px 0;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: {t.border_hover};
            margin: 0;
            border-radius: 4px;
        }}

        /* ====== 输入框 fallback ====== */
        QLineEdit, QTextEdit, QPlainTextEdit {{
            background: {t.comp.input_bg if t.comp else t.bg_secondary};
            border: 1px solid {t.border};
            border-radius: 10px;
            color: {t.text_primary};
            padding: 6px 12px;
            selection-background-color: {t.selection_bg};
            selection-color: {t.text_primary};
        }}
        QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover {{
            border-color: {t.border_hover};
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
            border: 1px solid {t.accent};
        }}
        QLineEdit[readOnly="true"] {{
            background: {t.bg_elevated};
            color: {t.text_muted};
        }}
        QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {{
            background: {t.bg_elevated};
            color: {t.text_muted};
            border-color: {t.border};
        }}

        /* ====== 标签语义 ====== */
        QLabel {{
            color: {t.text_primary};
            background: transparent;
        }}
        QLabel[role="pageTitle"] {{
            color: {t.text_primary};
            font-size: 20px;
            font-weight: 700;
            letter-spacing: 0.2px;
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
            padding: 10px 14px;
        }}
        QLabel[role="warningBanner"] {{
            background: {t.warning_bg};
            border: 1px solid {t.warning_border};
            color: {t.warning};
            border-radius: 10px;
            padding: 7px 12px;
            font-size: 12px;
        }}
        QLabel[role="statusMeta"] {{
            color: {t.text_muted};
            font-size: 12px;
        }}

        /* ====== GroupBox（卡片式分区）====== */
        QGroupBox {{
            background: {t.bg_secondary};
            border: 1px solid {t.border};
            border-radius: 14px;
            color: {t.text_primary};
            font-weight: 600;
            margin-top: 0px;
            padding: 8px 8px 8px 8px;
            padding-top: 34px;
        }}
        QGroupBox::title {{
            subcontrol-origin: border;
            subcontrol-position: top left;
            left: 16px;
            top: 12px;
            padding: 0;
            color: {t.text_secondary};
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 1.2px;
        }}

        /* ====== TabWidget（pill 风格）====== */
        QTabWidget::pane {{
            background: {t.bg_secondary};
            border: 1px solid {t.border};
            border-radius: 12px;
            top: 8px;
        }}
        QTabBar {{
            qproperty-drawBase: 0;
        }}
        QTabBar::tab {{
            background: transparent;
            color: {t.text_muted};
            border: 1px solid transparent;
            border-radius: 8px;
            padding: 6px 16px;
            margin-right: 4px;
            font-size: 12px;
            font-weight: 600;
        }}
        QTabBar::tab:selected {{
            background: {t.accent_soft};
            color: {t.accent};
            border-color: transparent;
        }}
        QTabBar::tab:hover:!selected {{
            background: {t.nav_hover_bg};
            color: {t.text_primary};
        }}

        /* ====== Splitter ====== */
        QSplitter::handle {{
            background: transparent;
            border-radius: 2px;
        }}
        QSplitter::handle:hover {{
            background: {t.accent_soft};
        }}
        QSplitter::handle:horizontal {{
            width: 5px;
            margin: 20px 0;
        }}
        QSplitter::handle:vertical {{
            height: 5px;
            margin: 0 20px;
        }}

        /* ====== ComboBox ====== */
        QComboBox {{
            background: {t.bg_elevated};
            border: 1px solid {t.border};
            border-radius: 10px;
            color: {t.text_primary};
            padding: 6px 12px;
            min-height: 20px;
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
            width: 24px;
        }}
        QComboBox::down-arrow {{
            width: 0;
            height: 0;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-top: 5px solid {t.text_muted};
            margin-right: 10px;
        }}
        QComboBox::down-arrow:hover {{
            border-top-color: {t.text_secondary};
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
        QComboBox QAbstractItemView::item {{
            padding: 6px 10px;
            min-height: 24px;
            border-radius: 6px;
        }}

        /* ====== CheckBox ====== */
        QCheckBox {{
            color: {t.text_secondary};
            spacing: 8px;
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
            background: {t.comp.input_bg if t.comp else t.bg_secondary};
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
        QCheckBox:disabled {{
            color: {t.text_muted};
        }}

        /* ====== 按钮基础 fallback（仅保留无任何 setStyleSheet 覆盖时的默认外观）====== */
        /* variant 语义按钮应使用 ComponentStyleRegistry 或直接调用 styles/buttons.py 函数 */
        QPushButton {{
            background-color: {t.bg_btn};
            border: 1px solid {t.border};
            border-radius: 10px;
            color: {t.text_primary};
            padding: 6px 14px;
            font-size: 13px;
            font-weight: 500;
        }}
        QPushButton:hover {{
            background-color: {t.bg_elevated};
            border-color: {t.border_hover};
        }}
        QPushButton:pressed {{
            background-color: {t.bg_secondary};
            padding-top: 7px;
        }}
        QPushButton:disabled {{
            background-color: {t.bg_elevated};
            color: {t.text_muted};
            border-color: {t.border};
        }}
    """
