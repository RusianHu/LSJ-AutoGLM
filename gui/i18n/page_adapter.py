# -*- coding: utf-8 -*-
"""
gui/i18n/page_adapter.py - 页面 i18n 适配器

职责：
  - 订阅 I18nManager.language_changed 信号
  - 将语言变化推送给所有已注册页面
  - 优先调用新接口 apply_i18n(i18n_manager) / retranslate_ui()
  - 兼容迁移期，分发失败时记录日志

迁移策略：
  - 新页面实现 apply_i18n(i18n_manager)，适配器优先调用
  - 也可实现 retranslate_ui()（无参），适配器次优先调用
  - 为迁移期保留兼容层，避免一次性重写全部页面
"""

import logging
from typing import Any

from gui.i18n.manager import I18nManager

_log = logging.getLogger(__name__)


class PageI18nAdapter:
    """
    页面 i18n 适配器。

    由 MainWindow 创建，连接到 I18nManager，
    负责将语言变化推送给所有注册页面。
    """

    def __init__(self, i18n_manager: I18nManager):
        self._manager = i18n_manager
        self._pages: list[Any] = []
        self._manager.language_changed.connect(self._on_language_changed)

    def register_page(self, page: Any) -> None:
        """
        注册需要响应语言切换的页面。

        Args:
            page: 页面实例，应实现 apply_i18n(manager) 或 retranslate_ui()
        """
        if page not in self._pages:
            self._pages.append(page)
            page_name = type(page).__name__
            _log.debug("PageI18nAdapter: 注册页面 '%s'", page_name)

    def unregister_page(self, page: Any) -> None:
        """注销页面。"""
        if page in self._pages:
            self._pages.remove(page)
            page_name = type(page).__name__
            _log.debug("PageI18nAdapter: 注销页面 '%s'", page_name)

    def push_current(self) -> None:
        """将当前 i18n 状态立即推送给所有已注册页面（初始化时使用）。"""
        self._dispatch(self._manager)

    # ---------- 内部 ----------

    def _on_language_changed(self, lang: str) -> None:
        """I18nManager.language_changed 回调。"""
        _log.debug(
            "PageI18nAdapter: 收到语言变化信号 lang='%s'，分发至 %d 个页面",
            lang,
            len(self._pages),
        )
        self._dispatch(self._manager)

    def _dispatch(self, manager: I18nManager) -> None:
        """向所有注册页面分发 i18n 更新。"""
        failed: list[str] = []
        for page in self._pages:
            page_name = type(page).__name__
            # 优先调用新接口 apply_i18n(manager)
            apply_fn = getattr(page, "apply_i18n", None)
            if callable(apply_fn):
                try:
                    apply_fn(manager)
                    continue
                except Exception as exc:
                    failed.append(page_name)
                    _log.error(
                        "PageI18nAdapter: '%s'.apply_i18n 失败: %s",
                        page_name, exc, exc_info=True,
                    )
                    continue
            # 次优先：retranslate_ui()（无参）
            retranslate_fn = getattr(page, "retranslate_ui", None)
            if callable(retranslate_fn):
                try:
                    retranslate_fn()
                    continue
                except Exception as exc:
                    failed.append(page_name)
                    _log.error(
                        "PageI18nAdapter: '%s'.retranslate_ui 失败: %s",
                        page_name, exc, exc_info=True,
                    )
                    continue
            # 页面没有实现任何 i18n 接口，静默跳过
            _log.debug(
                "PageI18nAdapter: 页面 '%s' 未实现 apply_i18n/retranslate_ui，跳过",
                page_name,
            )
        if failed:
            _log.warning(
                "PageI18nAdapter: %d 个页面分发失败: %s",
                len(failed), ", ".join(failed),
            )
