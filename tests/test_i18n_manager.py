# -*- coding: utf-8 -*-
"""
测试 I18nManager 核心功能：
- 语言初始化、切换、信号广播
- t() 翻译、参数化模板、缺词占位
- 别名规范化
"""

import sys
import os

import pytest
from unittest.mock import patch

# 确保在仓库根目录下运行
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ---------------------------------------------------------------------------
# 跳过需要 Qt 环境的测试（如 CI 无显示器）
# ---------------------------------------------------------------------------

def _requires_qt():
    try:
        from PySide6.QtWidgets import QApplication
        return False
    except ImportError:
        return True


pytest_plugins = []


class TestI18nManagerUnit:
    """不需要 QApplication 的纯逻辑测试（通过 mock）。"""

    def _make_manager(self, lang="cn"):
        """创建无 QApplication 的简单 manager（通过 mock Signal）。"""
        # 使用 unittest.mock 替换 Signal 避免 Qt 依赖
        from unittest.mock import MagicMock, patch
        with patch("gui.i18n.manager.QObject.__init__", return_value=None):
            with patch("gui.i18n.manager.Signal"):
                from gui.i18n.manager import I18nManager
                mgr = I18nManager.__new__(I18nManager)
                mgr._lang = "cn"
                mgr._dict = {}
                mgr.language_changed = MagicMock()
                mgr._load_dict(lang)
                return mgr

    def test_default_language_is_cn(self):
        mgr = self._make_manager("cn")
        assert mgr.get_language() == "cn"

    def test_real_init_respects_en_language(self):
        from gui.i18n.manager import I18nManager
        mgr = I18nManager("en")
        assert mgr.get_language() == "en"
        assert mgr.t("shell.nav.dashboard") == "Workspace"

    def test_real_init_normalizes_zh_alias_to_cn(self):
        from gui.i18n.manager import I18nManager
        mgr = I18nManager("zh")
        assert mgr.get_language() == "cn"
        assert mgr.t("shell.nav.dashboard") == "工作台"

    def test_t_returns_chinese_for_cn(self):
        mgr = self._make_manager("cn")
        result = mgr.t("shell.nav.dashboard")
        assert result == "工作台"

    def test_t_returns_english_for_en(self):
        mgr = self._make_manager("en")
        result = mgr.t("shell.nav.dashboard")
        assert result == "Workspace"

    def test_t_parameterized(self):
        mgr = self._make_manager("cn")
        result = mgr.t("event.task_complete", duration="5s")
        assert "5s" in result

    def test_t_missing_key_returns_placeholder(self):
        mgr = self._make_manager("cn")
        result = mgr.t("nonexistent.key.xyz")
        assert "nonexistent.key.xyz" in result
        assert "[[" in result

    def test_normalize_alias_zh(self):
        mgr = self._make_manager("cn")
        from gui.i18n.manager import _LANG_ALIASES
        assert _LANG_ALIASES.get("zh") == "cn"
        assert _LANG_ALIASES.get("zh-cn") == "cn"

    def test_cn_dict_not_empty(self):
        from gui.i18n.locales.cn import CN
        assert isinstance(CN, dict)
        assert len(CN) > 50

    def test_en_dict_not_empty(self):
        from gui.i18n.locales.en import EN
        assert isinstance(EN, dict)
        assert len(EN) > 50

    def test_cn_en_same_key_count(self):
        """两个词典的 key 集合应基本一致（允许少量差异）。"""
        from gui.i18n.locales.cn import CN
        from gui.i18n.locales.en import EN
        cn_keys = set(CN.keys())
        en_keys = set(EN.keys())
        only_in_cn = cn_keys - en_keys
        only_in_en = en_keys - cn_keys
        # 差异不超过 10 个（宽松检查）
        assert len(only_in_cn) <= 10, f"CN 独有 key: {only_in_cn}"
        assert len(only_in_en) <= 10, f"EN 独有 key: {only_in_en}"

    def test_cn_has_required_keys(self):
        from gui.i18n.locales.cn import CN
        required = [
            "shell.window.title",
            "shell.nav.dashboard",
            "shell.nav.device",
            "shell.nav.history",
            "shell.nav.settings",
            "page.dashboard.toolbar.btn.start",
            "page.history.title",
            "page.device.title",
            "page.device.qr_scan.window_title",
            "page.device.qr_pair.window_title",
            "page.device.log.adb_check",
            "page.device.result.success",
            "page.device.result.failed",
            "page.diagnostics.title",
            "event.task_start",
            "event.task_complete",
            "event.task_failed",
        ]
        missing = [k for k in required if k not in CN]
        assert not missing, f"CN 词典缺少必要 key: {missing}"

    def test_en_has_required_keys(self):
        from gui.i18n.locales.en import EN
        required = [
            "shell.window.title",
            "shell.nav.dashboard",
            "page.dashboard.toolbar.btn.start",
            "page.history.title",
            "page.device.title",
            "page.device.qr_scan.window_title",
            "page.device.qr_pair.window_title",
            "page.device.log.adb_check",
            "page.device.result.success",
            "page.device.result.failed",
            "page.diagnostics.title",
        ]
        missing = [k for k in required if k not in EN]
        assert not missing, f"EN 词典缺少必要 key: {missing}"

    def test_parameterized_template_missing_param_does_not_crash(self):
        """模板参数缺失时不应崩溃，应返回原模板。"""
        mgr = self._make_manager("cn")
        # event.task_complete 需要 {duration}，此处不传
        result = mgr.t("event.task_complete")  # 不传 duration 参数
        # 应返回模板原文（不崩溃即通过）
        assert isinstance(result, str)
        assert len(result) > 0
