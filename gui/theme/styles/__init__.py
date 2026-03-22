# -*- coding: utf-8 -*-
"""
gui/theme/styles - 组件样式生成模块

每个子模块只负责单一组件类别的 QSS 生成，
接收 ThemeTokens，输出 QSS 字符串。
"""

from gui.theme.styles.buttons import (
    btn_primary,
    btn_secondary,
    btn_subtle,
    btn_success,
    btn_warning,
    btn_danger,
    btn_ghost,
)
from gui.theme.styles.inputs import (
    input_default,
    input_readonly,
    input_search,
    input_invalid,
    input_success,
)
from gui.theme.styles.banners import (
    banner_info,
    banner_success,
    banner_warning,
    banner_error,
)
from gui.theme.styles.dialogs import dialog_surface, dialog_message_box
from gui.theme.styles.shell import shell_global_qss
from gui.theme.styles.navigation import nav_panel_qss, nav_button_qss
from gui.theme.styles.lists import list_console, list_default, list_event, list_side
from gui.theme.styles.logs import log_console
from gui.theme.styles.cards import (
    card_default,
    card_elevated,
    card_outlined,
    card_console,
)

__all__ = [
    # buttons
    "btn_primary",
    "btn_secondary",
    "btn_subtle",
    "btn_success",
    "btn_warning",
    "btn_danger",
    "btn_ghost",
    # inputs
    "input_default",
    "input_readonly",
    "input_search",
    "input_invalid",
    "input_success",
    # banners
    "banner_info",
    "banner_success",
    "banner_warning",
    "banner_error",
    # dialogs
    "dialog_surface",
    "dialog_message_box",
    # shell
    "shell_global_qss",
    # navigation
    "nav_panel_qss",
    "nav_button_qss",
    # lists
    "list_console",
    "list_default",
    "list_event",
    "list_side",
    # logs
    "log_console",
    # cards
    "card_default",
    "card_elevated",
    "card_outlined",
    "card_console",
]
