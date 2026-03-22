# -*- coding: utf-8 -*-
"""
gui/theme/page_adapter.py - 页面主题适配器

职责：
  - 订阅 ThemeManager.theme_changed 信号
  - 将 tokens 推送给已注册的页面
  - 兼容旧版 on_theme_changed(mode, vars_dict) 接口
  - 支持新版 apply_theme_tokens(tokens) 接口
  - 分发失败时记录日志，提供充分可观测性

迁移策略：
  - 新页面实现 apply_theme_tokens，适配器优先调用
  - 旧页面保留 on_theme_changed，适配器自动调用旧接口
  - 两个接口共存期间不会冲突
"""

import logging
from typing import Any

from gui.theme.tokens import ThemeTokens
from gui.theme.manager import ThemeManager

_log = logging.getLogger(__name__)


class PageThemeAdapter:
    """
    页面主题适配器。

    由 MainWindow 创建，连接到 ThemeManager，
    负责将主题变化推送给所有注册的页面。
    """

    def __init__(self, theme_manager: ThemeManager):
        self._manager = theme_manager
        self._pages: list[Any] = []
        self._manager.theme_changed.connect(self._on_theme_changed)

    def register_page(self, page: Any) -> None:
        """
        注册需要响应主题的页面。

        Args:
            page: 页面实例，应实现 apply_theme_tokens 或 on_theme_changed
        """
        if page not in self._pages:
            self._pages.append(page)
            page_name = type(page).__name__
            _log.debug("PageThemeAdapter: 注册页面 '%s'", page_name)

    def unregister_page(self, page: Any) -> None:
        """注销页面。"""
        if page in self._pages:
            self._pages.remove(page)
            page_name = type(page).__name__
            _log.debug("PageThemeAdapter: 注销页面 '%s'", page_name)

    def push_current(self) -> None:
        """将当前 tokens 立即推送给所有已注册页面（初始化时使用）。"""
        tokens = self._manager.get_tokens()
        self._dispatch(tokens)

    # ---------- 内部 ----------

    def _on_theme_changed(self, tokens: ThemeTokens) -> None:
        """ThemeManager.theme_changed 回调。"""
        _log.debug(
            "PageThemeAdapter: 收到主题变化信号，mode='%s'，分发至 %d 个页面",
            tokens.mode,
            len(self._pages),
        )
        self._dispatch(tokens)

    def _dispatch(self, tokens: ThemeTokens) -> None:
        """向所有注册页面分发 tokens。"""
        failed: list[str] = []
        for page in self._pages:
            page_name = type(page).__name__
            # 优先调用新接口
            apply_fn = getattr(page, "apply_theme_tokens", None)
            if callable(apply_fn):
                try:
                    apply_fn(tokens)
                except Exception as exc:
                    failed.append(page_name)
                    _log.error(
                        "PageThemeAdapter: 页面 '%s' apply_theme_tokens 失败: %s",
                        page_name,
                        exc,
                        exc_info=True,
                    )
            else:
                # 降级：调用旧版兼容接口
                legacy_fn = getattr(page, "on_theme_changed", None)
                if callable(legacy_fn):
                    try:
                        legacy_fn(tokens.mode, tokens.to_legacy_dict())
                    except Exception as exc:
                        failed.append(page_name)
                        _log.error(
                            "PageThemeAdapter: 页面 '%s' on_theme_changed 失败: %s",
                            page_name,
                            exc,
                            exc_info=True,
                        )
                else:
                    _log.warning(
                        "PageThemeAdapter: 页面 '%s' 未实现 apply_theme_tokens 或 on_theme_changed",
                        page_name,
                    )

        if failed:
            _log.warning(
                "PageThemeAdapter: %d 个页面主题分发失败: %s",
                len(failed),
                ", ".join(failed),
            )
