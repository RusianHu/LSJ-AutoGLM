# -*- coding: utf-8 -*-
"""
gui/utils/layout.py - 布局辅助工具

横版壳层下的通用布局模式：
  - wrap_center_column: 将内容控件包进居中限宽列，
    避免表单/卡片在宽窗口下无限拉伸影响可读性。
"""

from PySide6.QtWidgets import QHBoxLayout, QWidget


def wrap_center_column(content: QWidget, max_width: int = 900) -> QWidget:
    """
    返回一个包装容器：内容列居中且不超过 max_width。

    内容列拿到远高于两侧弹簧的伸展权重，
    因此在窄窗口时优先占满可用宽度，宽窗口时被 max_width 截断并居中。
    """
    content.setMaximumWidth(max_width)
    wrapper = QWidget()
    row = QHBoxLayout(wrapper)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(0)
    row.addStretch(1)
    row.addWidget(content, 100)
    row.addStretch(1)
    return wrapper
