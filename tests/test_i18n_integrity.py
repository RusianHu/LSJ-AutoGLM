# -*- coding: utf-8 -*-
"""i18n 资源与运行时入口回归测试。"""

from __future__ import annotations

import os
import string
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_i18n_catalogs_are_complete():
    from scripts.check_i18n import run_checks

    report = run_checks(ROOT)
    assert not report.errors, "\n".join(report.errors)


def test_phone_agent_language_aliases_are_consistent():
    from phone_agent.config.i18n import get_message, get_messages

    assert get_message("thinking", "en") == "Thinking"
    assert get_message("thinking", "EN-US") == "Thinking"
    assert get_message("thinking", "zh-CN") == "思考过程"
    assert set(get_messages("cn")) == set(get_messages("en"))


def test_gui_language_aliases_load_the_expected_catalog():
    from gui.i18n.manager import I18nManager

    manager = I18nManager("EN-US")
    assert manager.get_language() == "en"
    assert manager.t("shell.nav.dashboard") == "Workspace"
    manager.set_language("zh-CN")
    assert manager.get_language() == "cn"
    assert manager.t("shell.nav.dashboard") == "工作台"


def test_gui_templates_format_for_both_languages():
    from gui.i18n.locales.cn import CN
    from gui.i18n.locales.en import EN

    for catalog in (CN, EN):
        for key, template in catalog.items():
            params = {}
            for _, field_name, format_spec, _ in string.Formatter().parse(template):
                if field_name and field_name.isidentifier():
                    params[field_name] = 1.0 if "f" in format_spec else "test"
            try:
                template.format(**params)
            except (KeyError, IndexError, ValueError) as exc:
                pytest.fail(f"{key} 无法格式化: {exc}")
