# -*- coding: utf-8 -*-
"""
gui/i18n/manager.py - GUI i18n 管理器（整个 i18n 系统唯一入口）

职责：
  - 管理当前 GUI 语言（cn / en）
  - 提供 set_language() / get_language() / t(key, **params)
  - 维护当前词典，并发出 language_changed 信号
  - 缺词时返回显式占位，例如 [[page.dashboard.btn.start]]
  - 记录缺词日志，便于补齐

架构：
  与 ThemeManager 平行，由 MainWindow 创建并注入 services。
  页面不需要自行实例化，通过 services['i18n'] 获取。
"""

import logging
from typing import Any

from PySide6.QtCore import QObject, Signal

_log = logging.getLogger(__name__)

# 支持的语言列表
SUPPORTED_LANGUAGES = ("cn", "en")

# 别名映射（兼容旧值）
_LANG_ALIASES: dict[str, str] = {
    "zh": "cn",
    "zh-cn": "cn",
    "zh_cn": "cn",
    "chinese": "cn",
    "english": "en",
}


class I18nManager(QObject):
    """
    GUI i18n 管理器 - 整个翻译系统唯一入口。

    生命周期：
      由 MainWindow 创建，保存于 _services['i18n']。
      页面通过 services 获取，不需要自行实例化。

    公开能力：
      set_language(lang)      设置语言并广播
      get_language()          获取当前语言码 ('cn' | 'en')
      t(key, **params)        翻译 key，支持参数化
      language_changed        信号：language_changed(str lang)
    """

    # 语言切换信号，携带新语言码
    language_changed = Signal(str)  # lang: str

    def __init__(self, lang: str = "cn", parent: QObject | None = None):
        super().__init__(parent)
        normalized = self._normalize(lang)
        if normalized not in SUPPORTED_LANGUAGES:
            _log.warning(
                "I18nManager: 不支持的初始化语言 '%s'，回退到 'cn'", lang
            )
            normalized = "cn"
        self._lang: str = normalized
        self._dict: dict[str, str] = {}
        self._load_dict(normalized)

    # ---------- 公开接口 ----------

    def set_language(self, lang: str) -> None:
        """
        设置当前语言并广播 language_changed 信号。

        Args:
            lang: 'cn' | 'en'（或别名，如 'zh'）
        """
        normalized = self._normalize(lang)
        if normalized not in SUPPORTED_LANGUAGES:
            _log.warning(
                "I18nManager: 不支持的语言 '%s'，回退到 'cn'", lang
            )
            normalized = "cn"
        if normalized == self._lang:
            return  # 无变化，不广播
        self._load_dict(normalized)
        self._lang = normalized
        _log.debug("I18nManager: 语言切换 -> '%s'", normalized)
        self.language_changed.emit(normalized)

    def get_language(self) -> str:
        """返回当前语言码。"""
        return self._lang

    def t(self, key: str, **params: Any) -> str:
        """
        翻译指定 key，支持参数化。

        缺词时返回显式占位 [[key]]，并记录日志。

        Args:
            key: 扁平 dot key，例如 'page.dashboard.btn.start'
            **params: 模板变量，例如 t('event.task_start', task_text='...')

        Returns:
            翻译后的文本，或 '[[key]]' 占位符。
        """
        template = self._dict.get(key)
        if template is None:
            _log.warning("I18nManager: 缺词 key='%s' lang='%s'", key, self._lang)
            return f"[[{key}]]"
        if not params:
            return template
        try:
            return template.format(**params)
        except (KeyError, IndexError, ValueError) as exc:
            _log.warning(
                "I18nManager: 参数化失败 key='%s' params=%s error=%s",
                key, params, exc
            )
            return template

    # ---------- 内部 ----------

    @staticmethod
    def _normalize(lang: str) -> str:
        """标准化语言码，处理别名与大小写。"""
        lang = (lang or "").strip().lower()
        return _LANG_ALIASES.get(lang, lang)

    def _load_dict(self, lang: str) -> None:
        """加载指定语言词典。"""
        try:
            if lang == "en":
                from gui.i18n.locales.en import EN
                self._dict = dict(EN)
            else:
                from gui.i18n.locales.cn import CN
                self._dict = dict(CN)
            _log.debug(
                "I18nManager: 已加载词典 lang='%s'，共 %d 项",
                lang, len(self._dict)
            )
        except ImportError as exc:
            _log.error("I18nManager: 加载词典失败 lang='%s': %s", lang, exc)
            self._dict = {}
