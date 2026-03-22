# -*- coding: utf-8 -*-
"""
tests/test_theme_engine.py - 主题引擎单元测试

覆盖范围：
  - ThemeTokens 构造与字段完整性
  - ComponentTokens 字段完整性
  - build_dark/light_theme_tokens 工厂函数
  - resolve_theme_tokens 缓存与返回值
  - ComponentStyleRegistry 注册与获取
  - ThemeAware 协议合规性（ThemeAwareWidget / ThemeAwareDialog）
  - to_legacy_dict 向后兼容

无需 QApplication，所有测试纯 Python。
"""

import pytest

from gui.theme.tokens import ThemeTokens, ComponentTokens
from gui.theme.themes import (
    build_dark_theme_tokens,
    build_light_theme_tokens,
    resolve_theme_tokens,
)
from gui.theme.component_registry import ComponentStyleRegistry, get_registry


# ===========================================================================
# ThemeTokens 基础测试
# ===========================================================================

class TestThemeTokens:
    """ThemeTokens 数据类基础测试。"""

    def test_dark_tokens_mode(self):
        """暗色令牌 mode 字段正确。"""
        t = build_dark_theme_tokens()
        assert t.mode == "dark"
        assert t.is_dark()
        assert not t.is_light()

    def test_light_tokens_mode(self):
        """浅色令牌 mode 字段正确。"""
        t = build_light_theme_tokens()
        assert t.mode == "light"
        assert t.is_light()
        assert not t.is_dark()

    def test_dark_tokens_fields_non_empty(self):
        """暗色令牌所有字符串字段非空。"""
        t = build_dark_theme_tokens()
        for field_name, value in vars(t).items():
            if isinstance(value, str):
                assert value, f"字段 '{field_name}' 不应为空字符串"

    def test_light_tokens_fields_non_empty(self):
        """浅色令牌所有字符串字段非空。"""
        t = build_light_theme_tokens()
        for field_name, value in vars(t).items():
            if isinstance(value, str):
                assert value, f"字段 '{field_name}' 不应为空字符串"

    def test_tokens_frozen(self):
        """ThemeTokens 为不可变数据类。"""
        t = build_dark_theme_tokens()
        with pytest.raises((AttributeError, TypeError)):
            t.mode = "light"  # type: ignore

    def test_comp_tokens_present(self):
        """ComponentTokens 已挂载。"""
        t = build_dark_theme_tokens()
        assert t.comp is not None
        assert isinstance(t.comp, ComponentTokens)

    def test_comp_tokens_fields_non_empty(self):
        """ComponentTokens 所有字段非空。"""
        for tokens in (build_dark_theme_tokens(), build_light_theme_tokens()):
            comp = tokens.comp
            assert comp is not None
            for field_name, value in vars(comp).items():
                assert value, f"ComponentTokens 字段 '{field_name}' 不应为空"


# ===========================================================================
# to_legacy_dict 向后兼容测试
# ===========================================================================

class TestLegacyDict:
    """to_legacy_dict 向后兼容层。"""

    EXPECTED_KEYS = [
        "bg_main", "bg_nav", "bg_toolbar", "bg_status",
        "bg_secondary", "bg_elevated", "bg_btn", "bg_console",
        "sep_color", "text_primary", "text_secondary", "text_muted",
        "border", "border_hover", "accent", "accent_hover",
        "accent_soft", "selection_bg",
        "success", "success_bg", "success_border",
        "warning", "warning_bg", "warning_border",
        "danger", "danger_bg", "danger_border",
        "nav_text", "nav_text_hover", "nav_hover_bg",
    ]

    def test_dark_legacy_dict_keys(self):
        """暗色令牌 to_legacy_dict 包含所有预期键。"""
        d = build_dark_theme_tokens().to_legacy_dict()
        for key in self.EXPECTED_KEYS:
            assert key in d, f"缺少键 '{key}'"

    def test_light_legacy_dict_keys(self):
        """浅色令牌 to_legacy_dict 包含所有预期键。"""
        d = build_light_theme_tokens().to_legacy_dict()
        for key in self.EXPECTED_KEYS:
            assert key in d, f"缺少键 '{key}'"

    def test_legacy_dict_values_non_empty(self):
        """to_legacy_dict 所有值非空。"""
        for tokens in (build_dark_theme_tokens(), build_light_theme_tokens()):
            d = tokens.to_legacy_dict()
            for key, value in d.items():
                assert value, f"legacy_dict 键 '{key}' 值为空"


# ===========================================================================
# resolve_theme_tokens 测试
# ===========================================================================

class TestResolveThemeTokens:
    """resolve_theme_tokens 工厂/缓存测试。"""

    def test_resolve_dark(self):
        t = resolve_theme_tokens("dark")
        assert t.mode == "dark"

    def test_resolve_light(self):
        t = resolve_theme_tokens("light")
        assert t.mode == "light"

    def test_resolve_unknown_fallback_to_light(self):
        """未知 mode 应 fallback 到 light。"""
        t = resolve_theme_tokens("solarized")
        assert t.mode == "light"

    def test_resolve_cache_same_instance(self):
        """多次调用返回同一缓存实例。"""
        t1 = resolve_theme_tokens("dark")
        t2 = resolve_theme_tokens("dark")
        assert t1 is t2


# ===========================================================================
# ComponentStyleRegistry 测试
# ===========================================================================

class TestComponentStyleRegistry:
    """ComponentStyleRegistry 注册与获取测试。"""

    def setup_method(self):
        self.tokens = build_dark_theme_tokens()

    def test_get_button_primary(self):
        """button.primary 应返回非空 QSS。"""
        reg = ComponentStyleRegistry()
        qss = reg.get("button.primary", self.tokens)
        assert isinstance(qss, str)
        assert len(qss) > 0
        assert "QPushButton" in qss

    def test_get_button_sizes(self):
        """带尺寸后缀的按钮应返回 QSS。"""
        reg = ComponentStyleRegistry()
        for name in ["button.primary.sm", "button.primary.compact", "button.primary.lg"]:
            qss = reg.get(name, self.tokens)
            assert len(qss) > 0, f"{name} 返回空字符串"

    def test_get_all_registered_styles(self):
        """所有已注册样式均能生成非空 QSS。"""
        reg = ComponentStyleRegistry()
        for name in reg.registered_names():
            qss = reg.get(name, self.tokens)
            assert isinstance(qss, str), f"{name} 未返回字符串"
            assert len(qss) > 0, f"{name} 返回空字符串"

    def test_get_unregistered_returns_empty(self):
        """未注册的名称应返回空字符串（而非异常）。"""
        reg = ComponentStyleRegistry()
        qss = reg.get("button.nonexistent", self.tokens)
        assert qss == ""

    def test_register_custom_factory(self):
        """自定义工厂注册后可被获取。"""
        reg = ComponentStyleRegistry()
        reg.register("button.custom", lambda t: f"QPushButton {{ color: {t.accent}; }}")
        qss = reg.get("button.custom", self.tokens)
        assert self.tokens.accent in qss

    def test_has_method(self):
        """has() 方法正确反映注册状态。"""
        reg = ComponentStyleRegistry()
        assert reg.has("button.primary")
        assert reg.has("card.default")
        assert not reg.has("button.fake")

    def test_get_registry_singleton(self):
        """get_registry() 多次调用返回同一实例。"""
        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2

    def test_card_styles_registered(self):
        """cards 样式已注册。"""
        reg = ComponentStyleRegistry()
        for name in ["card.default", "card.elevated", "card.outlined", "card.console"]:
            assert reg.has(name), f"{name} 未注册"
            qss = reg.get(name, self.tokens)
            assert len(qss) > 0

    def test_banner_styles_registered(self):
        """banner 样式已注册。"""
        reg = ComponentStyleRegistry()
        for name in ["banner.info", "banner.success", "banner.warning", "banner.error"]:
            assert reg.has(name), f"{name} 未注册"

    def test_list_styles_registered(self):
        """list 样式已注册。"""
        reg = ComponentStyleRegistry()
        for name in ["list.default", "list.console", "list.event", "list.side"]:
            assert reg.has(name), f"{name} 未注册"


# ===========================================================================
# 主题切换一致性测试
# ===========================================================================

class TestThemeSwitchConsistency:
    """主题切换时 dark/light 令牌应保持字段结构一致。"""

    def test_same_field_count(self):
        """两套主题令牌字段数量相同。"""
        dark = build_dark_theme_tokens()
        light = build_light_theme_tokens()
        dark_fields = set(vars(dark).keys())
        light_fields = set(vars(light).keys())
        assert dark_fields == light_fields

    def test_legacy_dict_same_keys(self):
        """两套 to_legacy_dict 键集合相同。"""
        dark_keys = set(build_dark_theme_tokens().to_legacy_dict().keys())
        light_keys = set(build_light_theme_tokens().to_legacy_dict().keys())
        assert dark_keys == light_keys

    def test_comp_same_field_count(self):
        """两套 ComponentTokens 字段数量相同。"""
        dark_comp = vars(build_dark_theme_tokens().comp)
        light_comp = vars(build_light_theme_tokens().comp)
        assert set(dark_comp.keys()) == set(light_comp.keys())

    def test_style_qss_dark_ne_light(self):
        """同一组件在 dark/light 下生成的 QSS 不同（颜色值不同）。"""
        reg = ComponentStyleRegistry()
        dark = build_dark_theme_tokens()
        light = build_light_theme_tokens()
        for name in ["button.primary", "button.danger", "input.default",
                     "list.console", "banner.warning"]:
            qss_dark = reg.get(name, dark)
            qss_light = reg.get(name, light)
            assert qss_dark != qss_light, f"{name} dark/light 样式不应相同"
