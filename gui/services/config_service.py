# -*- coding: utf-8 -*-
"""
配置服务 - 读取/写回 .env 配置文件。

修复记录：
- _write_env 改为临时文件 + 原子替换，防止写入中断损坏 .env
- _write_env 对含空格/特殊字符的值自动加引号
- load() 与 _write_env 统一使用 utf-8 编码
- set() 先写文件后更新缓存，写失败时回滚缓存
- _on_validate（仅校验）不再污染运行缓存
- build_command_args 补充第三方模型参数选择逻辑
"""

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QObject, Signal

from gui.utils.runtime import build_task_subprocess_command, resolve_env_path
from phone_agent.actions.registry import (
    ACTION_POLICY_VERSION,
    ActionPolicyInput,
    parse_action_name_collection,
    resolve_action_policy,
)

_ENV_FILE = resolve_env_path()


class ConfigService(QObject):
    """
    配置服务。

    信号：
    - config_changed()     -- 任意配置项变化
    - config_saved()       -- 配置成功写回 .env
    - config_error(str)    -- 读写错误
    """

    config_changed = Signal()
    config_saved = Signal()
    config_error = Signal(str)

    # 默认配置（与 .env.example / launcher.py / main.py 对齐）
    DEFAULTS = {
        "OPEN_AUTOGLM_BASE_URL": "https://api-inference.modelscope.cn/v1",
        "OPEN_AUTOGLM_MODEL": "ZhipuAI/AutoGLM-Phone-9B",
        "OPEN_AUTOGLM_API_KEY": "",
        "OPEN_AUTOGLM_BACKUP_API_KEY": "",
        "OPEN_AUTOGLM_DEVICE_TYPE": "adb",
        "OPEN_AUTOGLM_DEVICE_ID": "",
        "OPEN_AUTOGLM_LANG": "cn",
        "OPEN_AUTOGLM_MAX_STEPS": "100",
        "OPEN_AUTOGLM_USE_THIRDPARTY_PROMPT": "false",
        "OPEN_AUTOGLM_THIRDPARTY_THINKING": "true",
        "OPEN_AUTOGLM_COMPRESS_IMAGE": "false",
        "OPEN_AUTOGLM_ACTION_POLICY_VERSION": str(ACTION_POLICY_VERSION),
        "OPEN_AUTOGLM_USE_PLATFORM_DEFAULT_ACTIONS": "true",
        "OPEN_AUTOGLM_ENABLED_ACTIONS": "",
        "OPEN_AUTOGLM_AI_VISIBLE_ACTIONS": "",
        "OPEN_AUTOGLM_MODELSCOPE_BASE_URL": "https://api-inference.modelscope.cn/v1",
        "OPEN_AUTOGLM_MODELSCOPE_MODEL": "ZhipuAI/AutoGLM-Phone-9B",
        "OPEN_AUTOGLM_MODELSCOPE_API_KEY": "",
        "OPEN_AUTOGLM_MODELSCOPE_BACKUP_API_KEY": "",
        "OPEN_AUTOGLM_ZHIPU_BASE_URL": "https://open.bigmodel.cn/api/paas/v4",
        "OPEN_AUTOGLM_ZHIPU_MODEL": "AutoGLM-Phone-9B",
        "OPEN_AUTOGLM_ZHIPU_API_KEY": "",
        "OPEN_AUTOGLM_NEWAPI_API_KEY": "",
        "OPEN_AUTOGLM_NEWAPI_BASE_URL": "https://ai.yanshanlaosiji.top/v1",
        "OPEN_AUTOGLM_NEWAPI_MODEL": "Qwen/Qwen3-VL-235B-A22B-Instruct",
        "OPEN_AUTOGLM_LOCAL_OPENAI_BASE_URL": "http://127.0.0.1:1234",
        "OPEN_AUTOGLM_LOCAL_OPENAI_MODEL": "autoglm-phone-9b",
        "OPEN_AUTOGLM_LOCAL_OPENAI_API_KEY": "",
        "OPEN_AUTOGLM_EXPERT_MODE": "false",
        "OPEN_AUTOGLM_EXPERT_STRICT_MODE": "false",
        "OPEN_AUTOGLM_EXPERT_BASE_URL": "",
        "OPEN_AUTOGLM_EXPERT_MODEL": "",
        "OPEN_AUTOGLM_EXPERT_API_KEY": "",
        "OPEN_AUTOGLM_EXPERT_PROMPT": "",
        "OPEN_AUTOGLM_EXPERT_AUTO_INIT": "true",
        "OPEN_AUTOGLM_EXPERT_AUTO_RESCUE": "true",
        "OPEN_AUTOGLM_EXPERT_MANUAL_ACTION": "true",
        "OPEN_AUTOGLM_EXPERT_SCREEN_UNCHANGED_THRESHOLD": "4",
        "OPEN_AUTOGLM_EXPERT_CONSECUTIVE_FAILURE_THRESHOLD": "3",
        "OPEN_AUTOGLM_EXPERT_MAX_RESCUES": "3",
        "OPEN_AUTOGLM_THEME": "system",
        "OPEN_AUTOGLM_GUI_MIRROR_NEW_WINDOW": "false",
    }

    # 敏感字段（显示时遮罩）
    SENSITIVE_KEYS = {
        "OPEN_AUTOGLM_API_KEY",
        "OPEN_AUTOGLM_BACKUP_API_KEY",
        "OPEN_AUTOGLM_NEWAPI_API_KEY",
        "OPEN_AUTOGLM_MODELSCOPE_API_KEY",
        "OPEN_AUTOGLM_MODELSCOPE_BACKUP_API_KEY",
        "OPEN_AUTOGLM_ZHIPU_API_KEY",
        "OPEN_AUTOGLM_LOCAL_OPENAI_API_KEY",
        "OPEN_AUTOGLM_EXPERT_API_KEY",
    }

    # 字段元数据，供 SettingsPage 渲染表单行
    FIELD_META: Dict[str, dict] = {
        "OPEN_AUTOGLM_BASE_URL": {"label": "Base URL", "label_i18n_key": "page.settings.field.base_url", "sensitive": False, "editable": True},
        "OPEN_AUTOGLM_MODEL": {"label": "模型名称", "label_i18n_key": "page.settings.field.model", "sensitive": False, "editable": True},
        "OPEN_AUTOGLM_API_KEY": {"label": "API Key", "label_i18n_key": "page.settings.field.api_key", "sensitive": True, "editable": True},
        "OPEN_AUTOGLM_BACKUP_API_KEY": {"label": "备用 API Key", "label_i18n_key": "page.settings.field.backup_api_key", "sensitive": True, "editable": True},
        "OPEN_AUTOGLM_MODELSCOPE_API_KEY": {"label": "ModelScope Key", "label_i18n_key": "page.settings.field.modelscope_api_key", "sensitive": True, "editable": True},
        "OPEN_AUTOGLM_MODELSCOPE_BACKUP_API_KEY": {"label": "ModelScope 备用 Key", "label_i18n_key": "page.settings.field.modelscope_backup_api_key", "sensitive": True, "editable": True},
        "OPEN_AUTOGLM_ZHIPU_API_KEY": {"label": "智谱 API Key", "label_i18n_key": "page.settings.field.zhipu_api_key", "sensitive": True, "editable": True},
        "OPEN_AUTOGLM_NEWAPI_API_KEY": {"label": "API Key", "label_i18n_key": "page.settings.field.api_key", "sensitive": True, "editable": True},
        "OPEN_AUTOGLM_NEWAPI_BASE_URL": {"label": "Base URL", "label_i18n_key": "page.settings.field.base_url", "sensitive": False, "editable": True},
        "OPEN_AUTOGLM_NEWAPI_MODEL": {"label": "模型名称", "label_i18n_key": "page.settings.field.model", "sensitive": False, "editable": True},
        "OPEN_AUTOGLM_LOCAL_OPENAI_BASE_URL": {"label": "Base URL", "label_i18n_key": "page.settings.field.base_url", "sensitive": False, "editable": True},
        "OPEN_AUTOGLM_LOCAL_OPENAI_MODEL": {"label": "模型名称", "label_i18n_key": "page.settings.field.model", "sensitive": False, "editable": True},
        "OPEN_AUTOGLM_LOCAL_OPENAI_API_KEY": {"label": "API Key (可选)", "label_i18n_key": "page.settings.field.api_key_optional", "sensitive": True, "editable": True},
        "OPEN_AUTOGLM_EXPERT_MODE": {"label": "启用专家模式", "label_i18n_key": "page.settings.field.expert_mode", "sensitive": False, "editable": True, "boolean": True},
        "OPEN_AUTOGLM_EXPERT_STRICT_MODE": {"label": "严格模式", "label_i18n_key": "page.settings.field.expert_strict_mode", "sensitive": False, "editable": True, "boolean": True},
        "OPEN_AUTOGLM_EXPERT_BASE_URL": {"label": "专家 Base URL", "label_i18n_key": "page.settings.field.expert_base_url", "sensitive": False, "editable": True},
        "OPEN_AUTOGLM_EXPERT_MODEL": {"label": "专家模型", "label_i18n_key": "page.settings.field.expert_model", "sensitive": False, "editable": True},
        "OPEN_AUTOGLM_EXPERT_API_KEY": {"label": "专家 API Key", "label_i18n_key": "page.settings.field.expert_api_key", "sensitive": True, "editable": True},
        "OPEN_AUTOGLM_EXPERT_PROMPT": {"label": "专家提示词", "label_i18n_key": "page.settings.field.expert_prompt", "sensitive": False, "editable": True},
        "OPEN_AUTOGLM_EXPERT_AUTO_INIT": {"label": "初始化咨询", "label_i18n_key": "page.settings.field.expert_auto_init", "sensitive": False, "editable": True, "boolean": True},
        "OPEN_AUTOGLM_EXPERT_AUTO_RESCUE": {"label": "自动救援", "label_i18n_key": "page.settings.field.expert_auto_rescue", "sensitive": False, "editable": True, "boolean": True},
        "OPEN_AUTOGLM_EXPERT_MANUAL_ACTION": {"label": "允许 Ask_AI 动作", "label_i18n_key": "page.settings.field.expert_manual_action", "sensitive": False, "editable": True, "boolean": True},
        "OPEN_AUTOGLM_EXPERT_SCREEN_UNCHANGED_THRESHOLD": {"label": "页面不变阈值", "label_i18n_key": "page.settings.field.expert_screen_unchanged_threshold", "sensitive": False, "editable": True},
        "OPEN_AUTOGLM_EXPERT_CONSECUTIVE_FAILURE_THRESHOLD": {"label": "连续失败阈值", "label_i18n_key": "page.settings.field.expert_consecutive_failure_threshold", "sensitive": False, "editable": True},
        "OPEN_AUTOGLM_EXPERT_MAX_RESCUES": {"label": "最大救援次数", "label_i18n_key": "page.settings.field.expert_max_rescues", "sensitive": False, "editable": True},
        "OPEN_AUTOGLM_DEVICE_TYPE": {"label": "设备平台", "label_i18n_key": "page.settings.field.device_type", "sensitive": False, "editable": True},
        "OPEN_AUTOGLM_DEVICE_ID": {"label": "设备 ID", "label_i18n_key": "page.settings.field.device_id", "sensitive": False, "editable": True},
        "OPEN_AUTOGLM_LANG": {"label": "语言", "label_i18n_key": "page.settings.field.lang", "sensitive": False, "editable": True},
        "OPEN_AUTOGLM_MAX_STEPS": {"label": "最大步数", "label_i18n_key": "page.settings.field.max_steps", "sensitive": False, "editable": True},
        "OPEN_AUTOGLM_USE_THIRDPARTY_PROMPT": {"label": "启用第三方提示词工程", "label_i18n_key": "page.settings.field.use_thirdparty_prompt", "sensitive": False, "editable": True, "boolean": True},
        "OPEN_AUTOGLM_THIRDPARTY_THINKING": {"label": "第三方思考输出 (think/answer 标签)", "label_i18n_key": "page.settings.field.thirdparty_thinking", "sensitive": False, "editable": True, "boolean": True},
        "OPEN_AUTOGLM_COMPRESS_IMAGE": {"label": "截图压缩", "label_i18n_key": "page.settings.field.compress_image", "sensitive": False, "editable": True, "boolean": True},
        "OPEN_AUTOGLM_ACTION_POLICY_VERSION": {"label": "动作策略版本", "label_i18n_key": "page.settings.field.action_policy_version", "sensitive": False, "editable": True},
        "OPEN_AUTOGLM_USE_PLATFORM_DEFAULT_ACTIONS": {"label": "启用平台默认动作回退", "label_i18n_key": "page.settings.field.use_platform_default_actions", "sensitive": False, "editable": True, "boolean": True},
        "OPEN_AUTOGLM_ENABLED_ACTIONS": {"label": "运行时启用动作集合", "label_i18n_key": "page.settings.field.enabled_actions", "sensitive": False, "editable": True},
        "OPEN_AUTOGLM_AI_VISIBLE_ACTIONS": {"label": "AI 可见动作集合", "label_i18n_key": "page.settings.field.ai_visible_actions", "sensitive": False, "editable": True},
        "OPEN_AUTOGLM_THEME": {"label": "界面主题", "label_i18n_key": "page.settings.field.theme", "sensitive": False, "editable": False},
        "OPEN_AUTOGLM_GUI_MIRROR_NEW_WINDOW": {"label": "镜像新窗口模式", "label_i18n_key": "page.settings.field.gui_mirror_new_window", "sensitive": False, "editable": False, "boolean": True},
    }

    # 兼容第一轮 GUI 中已写入/读取过的旧键名
    KEY_ALIASES: Dict[str, tuple] = {
        "OPEN_AUTOGLM_LANG": ("OPEN_AUTOGLM_LANGUAGE",),
        "OPEN_AUTOGLM_USE_THIRDPARTY_PROMPT": ("OPEN_AUTOGLM_THIRDPARTY",),
    }

    # 渠道预设元信息。
    # url_field/model_field: 从 .env 读取实际值的字段名
    # default_url/default_model: 对应字段为空时的兜底默认值
    # use_thirdparty: 是否启用第三方提示词工程（--thirdparty 参数）
    # api_key_field: 该渠道对应的 API Key 环境变量名
    CHANNEL_PRESETS: List[Dict] = [
        {
            "id": "modelscope",
            "name": "ModelScope",
            "url_field": "OPEN_AUTOGLM_MODELSCOPE_BASE_URL",
            "model_field": "OPEN_AUTOGLM_MODELSCOPE_MODEL",
            "default_url": "https://api-inference.modelscope.cn/v1",
            "default_model": "ZhipuAI/AutoGLM-Phone-9B",
            "use_thirdparty": False,
            "compress_image": False,
            "api_key_field": "OPEN_AUTOGLM_MODELSCOPE_API_KEY",
            "backup_api_key_field": "OPEN_AUTOGLM_MODELSCOPE_BACKUP_API_KEY",
        },
        {
            "id": "zhipu",
            "name": "智谱",
            "url_field": "OPEN_AUTOGLM_ZHIPU_BASE_URL",
            "model_field": "OPEN_AUTOGLM_ZHIPU_MODEL",
            "default_url": "https://open.bigmodel.cn/api/paas/v4",
            "default_model": "AutoGLM-Phone-9B",
            "use_thirdparty": False,
            "compress_image": False,
            "api_key_field": "OPEN_AUTOGLM_ZHIPU_API_KEY",
        },
        {
            "id": "newapi",
            "name": "第三方模型",
            "url_field": "OPEN_AUTOGLM_NEWAPI_BASE_URL",
            "model_field": "OPEN_AUTOGLM_NEWAPI_MODEL",
            "default_url": "https://ai.yanshanlaosiji.top/v1",
            "default_model": "Qwen/Qwen3-VL-235B-A22B-Instruct",
            "use_thirdparty": True,
            "compress_image": False,
            "api_key_field": "OPEN_AUTOGLM_NEWAPI_API_KEY",
        },
        {
            "id": "local",
            "name": "本地 (localhost)",
            "url_field": "OPEN_AUTOGLM_LOCAL_OPENAI_BASE_URL",
            "model_field": "OPEN_AUTOGLM_LOCAL_OPENAI_MODEL",
            "default_url": "http://127.0.0.1:1234",
            "default_model": "autoglm-phone-9b",
            "use_thirdparty": True,
            "compress_image": False,
            "api_key_field": "OPEN_AUTOGLM_LOCAL_OPENAI_API_KEY",
        },
        {
            "id": "custom",
            "name": "自定义",
            "url_field": "",
            "model_field": "",
            "default_url": "",
            "default_model": "",
            "use_thirdparty": False,
            "compress_image": False,
            "api_key_field": "OPEN_AUTOGLM_API_KEY",
        },
    ]

    def __init__(self, env_file: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self._env_file = env_file or _ENV_FILE
        self._cache: Dict[str, str] = {}
        self._env_bootstrap_created = False
        self._env_bootstrap_error = ""
        self.load()

    @property
    def env_path(self) -> str:
        """返回 .env 文件路径字符串（供 SettingsPage 显示）"""
        return str(self._env_file.resolve())

    def get_env_file_status(self) -> Dict[str, Any]:
        """返回当前 .env 文件状态，供诊断页与设置页使用。"""
        try:
            resolved_path = self._env_file.resolve()
        except Exception:
            resolved_path = self._env_file

        parent = self._env_file.parent
        exists = self._env_file.exists()
        parent_exists = parent.exists()
        if exists:
            writable = os.access(self._env_file, os.W_OK)
        else:
            writable = parent_exists and os.access(parent, os.W_OK)

        return {
            "path": str(resolved_path),
            "exists": exists,
            "parent_exists": parent_exists,
            "writable": writable,
            "bootstrapped": self._env_bootstrap_created,
            "bootstrap_error": self._env_bootstrap_error,
        }

    # ---------- 读取 ----------

    def _normalize_aliases(self):
        """将旧键名归一化到新键名，避免默认值遮蔽兼容回退。"""
        for canonical_key, aliases in self.KEY_ALIASES.items():
            canonical_value = self._cache.get(canonical_key, "")
            default_value = self.DEFAULTS.get(canonical_key, "")
            for alias in aliases:
                alias_value = self._cache.get(alias, "")
                if alias_value not in (None, "") and canonical_value in (None, "", default_value):
                    self._cache[canonical_key] = alias_value
                    canonical_value = alias_value
                self._cache.pop(alias, None)

    def load(self):
        """从 .env 文件读取配置到内存缓存"""
        # 先用环境变量初始化（低优先级）
        self._cache = {k: os.environ.get(k, v) for k, v in self.DEFAULTS.items()}
        self._env_bootstrap_created = False
        self._env_bootstrap_error = ""

        if not self._env_file.exists():
            self._normalize_aliases()
            # 首次启动时自动生成初始 .env，保证配置可持久化
            self._bootstrap_env()
            return

        try:
            with open(self._env_file, "r", encoding="utf-8") as f:
                for lineno, raw_line in enumerate(f, 1):
                    line = raw_line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    key = key.strip()
                    val = val.strip()
                    # 去除引号
                    if (val.startswith('"') and val.endswith('"')) or \
                       (val.startswith("'") and val.endswith("'")):
                        val = val[1:-1]
                    # 若文件中该键为空占位（KEY=），但环境变量中有非空注入值，
                    # 则保留环境变量值，避免首次引导生成的空敏感占位行覆盖注入配置。
                    env_val = os.environ.get(key)
                    if val == "" and env_val:
                        self._cache[key] = env_val
                    else:
                        self._cache[key] = val
        except Exception as e:
            self.config_error.emit(f".env 读取失败 (行 {lineno if 'lineno' in dir() else '?'}): {e}")

        self._normalize_aliases()
        self.config_changed.emit()

    def get(self, key: str, default: str = "") -> str:
        """读取配置值（兼容旧键名回退）"""
        for candidate in self._iter_candidate_keys(key):
            value = self._cache.get(candidate)
            if value not in (None, ""):
                return value
        return default

    @classmethod
    def _iter_candidate_keys(cls, key: str):
        yield key
        for alias in cls.KEY_ALIASES.get(key, ()):
            yield alias

    @staticmethod
    def _normalize_lang(lang: str) -> str:
        normalized = (lang or "cn").strip().lower()
        return "cn" if normalized in {"zh", "zh-cn", "zh_cn"} else normalized

    @classmethod
    def _get_locale_dict(cls, lang: str = "cn") -> Dict[str, str]:
        normalized = cls._normalize_lang(lang)
        if normalized == "en":
            from gui.i18n.locales.en import EN
            return EN
        from gui.i18n.locales.cn import CN
        return CN

    @classmethod
    def get_field_label_static(cls, key: str, lang: str = "cn") -> str:
        info = cls.FIELD_META.get(key, {})
        fallback = info.get("label", key)
        label_i18n_key = info.get("label_i18n_key", "")
        if not label_i18n_key:
            return fallback
        locale = cls._get_locale_dict(lang)
        return locale.get(label_i18n_key, fallback)

    def get_field_label(self, key: str, lang: str = "cn") -> str:
        return self.get_field_label_static(key, lang)

    def render_validation_error(self, detail: Dict[str, Any], lang: str = "cn") -> str:
        locale = self._get_locale_dict(lang)
        message_key = str(detail.get("message_key") or "")
        fallback = str(detail.get("fallback") or message_key or "")
        template = locale.get(message_key, fallback)
        params = dict(detail.get("params") or {})
        field_key = str(params.pop("field_key", "") or "")
        if field_key:
            params["field"] = self.get_field_label(field_key, lang)
        try:
            return template.format(**params) if params else template
        except (KeyError, IndexError, ValueError):
            return fallback or template

    @staticmethod
    def _is_truthy(value: str) -> bool:
        return str(value).strip().lower() in ("1", "true", "yes", "on")

    @staticmethod
    def _normalize_action_collection(value: object) -> str:
        parsed = parse_action_name_collection(value)
        if parsed is None:
            return ""
        return json.dumps(list(parsed), ensure_ascii=False)

    def get_action_policy_settings(self) -> Dict[str, Any]:
        policy_version_raw = (
            self.get("OPEN_AUTOGLM_ACTION_POLICY_VERSION", str(ACTION_POLICY_VERSION))
            or str(ACTION_POLICY_VERSION)
        ).strip()
        try:
            policy_version = int(policy_version_raw)
        except ValueError:
            policy_version = ACTION_POLICY_VERSION

        enabled_actions_raw = (self.get("OPEN_AUTOGLM_ENABLED_ACTIONS", "") or "").strip()
        ai_visible_actions_raw = (self.get("OPEN_AUTOGLM_AI_VISIBLE_ACTIONS", "") or "").strip()

        enabled_actions = (
            self._normalize_action_collection(enabled_actions_raw)
            if enabled_actions_raw
            else ""
        )
        ai_visible_actions = (
            self._normalize_action_collection(ai_visible_actions_raw)
            if ai_visible_actions_raw
            else ""
        )

        return {
            "policy_version": policy_version,
            "use_platform_defaults": self._is_truthy(
                self.get("OPEN_AUTOGLM_USE_PLATFORM_DEFAULT_ACTIONS", "true")
            ),
            "enabled_actions": enabled_actions,
            "ai_visible_actions": ai_visible_actions,
        }

    def get_masked(self, key: str) -> str:
        """读取配置值，敏感字段返回遮罩"""
        val = self.get(key)
        if key in self.SENSITIVE_KEYS and val:
            if len(val) > 8:
                return val[:4] + "*" * (len(val) - 8) + val[-4:]
            return "***"
        return val

    def get_all(self) -> Dict[str, str]:
        """返回所有配置的副本"""
        return dict(self._cache)

    # ---------- 写入 ----------

    def set(self, key: str, value: str):
        """
        写入单个配置项。
        先写文件，成功后再更新缓存；失败时抛出异常而不修改缓存。
        """
        old_value = self._cache.get(key)
        # 临时更新缓存以供 _write_env 读取
        self._cache[key] = value
        try:
            self._write_env()
            self.config_changed.emit()
        except Exception as e:
            # 写入失败：回滚缓存
            if old_value is None:
                self._cache.pop(key, None)
            else:
                self._cache[key] = old_value
            raise e

    def set_many(self, updates: Dict[str, str]):
        """
        批量写入配置（只写一次文件）。
        先写文件，成功后再批量更新缓存；失败时全量回滚。
        """
        old_values = {k: self._cache.get(k) for k in updates}
        # 临时更新缓存
        for k, v in updates.items():
            self._cache[k] = v
        try:
            self._write_env()
            self.config_changed.emit()
            self.config_saved.emit()
        except Exception as e:
            # 失败：回滚
            for k, ov in old_values.items():
                if ov is None:
                    self._cache.pop(k, None)
                else:
                    self._cache[k] = ov
            self.config_error.emit(f"配置保存失败: {e}")
            raise e

    def _bootstrap_env(self):
        """首次启动时自动生成初始 .env 文件。

        仅在 .env 不存在时调用。将当前 DEFAULTS 中所有 key 写入新文件，
        以注释标注来源，并标记敏感字段为空值（不写入默认密钥）。
        写入失败时静默忽略，不影响 GUI 正常启动。
        """
        try:
            self._env_file.parent.mkdir(parents=True, exist_ok=True)
            lines: List[str] = [
                "# Open-AutoGLM 配置文件\n",
                "# 首次启动时由 GUI 自动生成，可直接编辑此文件。\n",
                "# 敏感字段（API Key）请在 GUI 设置页填写后保存。\n",
                "\n",
            ]
            for key, default_val in self.DEFAULTS.items():
                # 敏感字段用空值占位，避免示例密钥误入磁盘
                if key in self.SENSITIVE_KEYS:
                    lines.append(f"{key}=\n")
                else:
                    # 非敏感字段：取已含环境变量覆盖的缓存值，而非硬编码默认值，
                    # 避免首次引导文件写入后环境变量注入的配置被默认值覆盖。
                    cached_val = self._cache.get(key, default_val)
                    lines.append(f"{key}={self._quote_value(cached_val)}\n")
            with open(self._env_file, "w", encoding="utf-8") as f:
                f.writelines(lines)
            self._env_bootstrap_created = True
            self._env_bootstrap_error = ""
        except Exception as exc:
            self._env_bootstrap_created = False
            self._env_bootstrap_error = f"{type(exc).__name__}: {exc}"
            # 生成失败不阻塞启动（如分发包在只读目录等情况）
            pass

    def _write_env(self):
        """
        将当前缓存写回 .env 文件。

        策略：
        - 保留现有文件中已有的行（注释、空行）
        - 对已知 key 进行原地替换
        - 对缓存中有但文件里没有的 key 追加
        - 使用临时文件 + 原子替换，防止写入中途崩溃损坏原文件
        - 含空格或特殊字符的值用双引号包裹
        """
        existing_lines: List[str] = []
        found_keys: set = set()

        if self._env_file.exists():
            try:
                with open(self._env_file, "r", encoding="utf-8") as f:
                    existing_lines = f.readlines()
            except Exception as e:
                raise RuntimeError(f".env 读取失败: {e}")

        # 遍历现有行，替换已有 key
        new_lines: List[str] = []
        for raw_line in existing_lines:
            line = raw_line.rstrip("\n").rstrip("\r")
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key, _, _ = stripped.partition("=")
                key = key.strip()
                if key in self._cache:
                    new_lines.append(f"{key}={self._quote_value(self._cache[key])}\n")
                    found_keys.add(key)
                    continue
            new_lines.append(raw_line if raw_line.endswith("\n") else raw_line + "\n")

        # 追加缓存中有但文件里没有的 key
        append_keys = [k for k in self._cache if k not in found_keys and self._cache[k]]
        if append_keys:
            new_lines.append("\n")
            for k in append_keys:
                new_lines.append(f"{k}={self._quote_value(self._cache[k])}\n")

        # 原子替换：先写临时文件，再 replace
        # Windows 下某些安全软件、同步盘或索引进程会短暂占用目标文件，
        # 导致 replace 抛 PermissionError。这里增加短暂重试；若仍失败，
        # 回退为直接覆盖写入，尽量避免 GUI 因瞬时占用而保存失败。
        tmp_path = self._env_file.parent / f"{self._env_file.name}.tmp"
        replace_error: Optional[Exception] = None
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)

            retry_count = 5 if os.name == "nt" else 1
            for attempt in range(retry_count):
                try:
                    tmp_path.replace(self._env_file)
                    replace_error = None
                    break
                except PermissionError as e:
                    replace_error = e
                    if os.name != "nt" or attempt >= retry_count - 1:
                        break
                    time.sleep(0.05 * (attempt + 1))
                except Exception as e:
                    replace_error = e
                    break

            if replace_error is not None:
                try:
                    with open(self._env_file, "w", encoding="utf-8") as f:
                        f.writelines(new_lines)
                    replace_error = None
                except Exception as overwrite_error:
                    replace_error = overwrite_error
                finally:
                    try:
                        tmp_path.unlink(missing_ok=True)
                    except Exception:
                        pass

            if replace_error is not None:
                raise replace_error
        except Exception as e:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
            raise RuntimeError(f".env 写入失败: {e}")

    @staticmethod
    def _quote_value(value: str) -> str:
        """
        若值含空格、引号、#、$、换行等特殊字符则用双引号包裹，
        并对内部双引号进行转义。
        """
        needs_quote = any(c in value for c in ' \t\n\r#$\'"')
        if needs_quote:
            escaped = value.replace('\\', '\\\\').replace('"', '\\"')
            return f'"{escaped}"'
        return value

    # ---------- 校验（不污染缓存） ----------

    def validate_details(self, updates: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
        """
        校验配置项（不修改缓存），返回可国际化的结构化错误明细。
        updates: 临时覆盖值用于校验；为 None 则校验当前缓存。
        返回：[{
            "key": str,
            "message_key": str,
            "params": dict,
            "fallback": str,
        }, ...]
        """
        values = dict(self._cache)
        if updates:
            values.update(updates)  # 只在本地副本上操作，不污染缓存

        errors: List[Dict[str, Any]] = []

        def _error(key: str, message_key: str, fallback: str, **params: Any) -> None:
            errors.append(
                {
                    "key": key,
                    "message_key": message_key,
                    "params": params,
                    "fallback": fallback,
                }
            )

        base_url = values.get("OPEN_AUTOGLM_BASE_URL", "")
        if base_url and not (base_url.startswith("http://") or base_url.startswith("https://")):
            _error(
                "OPEN_AUTOGLM_BASE_URL",
                "page.settings.validation.base_url.invalid_scheme",
                "Base URL 必须以 http:// 或 https:// 开头",
            )

        model = values.get("OPEN_AUTOGLM_MODEL", "")
        if not model:
            _error(
                "OPEN_AUTOGLM_MODEL",
                "page.settings.validation.model.required",
                "模型名称不能为空",
            )

        max_steps = values.get("OPEN_AUTOGLM_MAX_STEPS", "100")
        try:
            s = int(max_steps)
            if s < 1 or s > 1000:
                _error(
                    "OPEN_AUTOGLM_MAX_STEPS",
                    "page.settings.validation.max_steps.range",
                    "最大步数应在 1-1000 之间",
                )
        except ValueError:
            _error(
                "OPEN_AUTOGLM_MAX_STEPS",
                "page.settings.validation.max_steps.integer",
                "最大步数必须是整数",
            )

        device_type = (values.get("OPEN_AUTOGLM_DEVICE_TYPE") or "adb").strip().lower()
        if device_type not in ("adb", "hdc", "ios"):
            _error(
                "OPEN_AUTOGLM_DEVICE_TYPE",
                "page.settings.validation.device_type.invalid",
                "设备平台仅支持 adb / hdc / ios",
            )

        expert_mode = self._is_truthy(values.get("OPEN_AUTOGLM_EXPERT_MODE", "false"))
        expert_strict_mode = self._is_truthy(values.get("OPEN_AUTOGLM_EXPERT_STRICT_MODE", "false"))
        expert_base_url = (values.get("OPEN_AUTOGLM_EXPERT_BASE_URL") or "").strip()
        expert_model = (values.get("OPEN_AUTOGLM_EXPERT_MODEL") or "").strip()
        if expert_strict_mode and not expert_mode:
            _error(
                "OPEN_AUTOGLM_EXPERT_STRICT_MODE",
                "page.settings.validation.expert_strict_requires_mode",
                "启用严格模式前，必须先启用专家模式",
            )
        if expert_mode:
            if not expert_base_url:
                _error(
                    "OPEN_AUTOGLM_EXPERT_BASE_URL",
                    "page.settings.validation.expert_base_url.required",
                    "启用专家模式时，专家 Base URL 不能为空",
                )
            elif not (expert_base_url.startswith("http://") or expert_base_url.startswith("https://")):
                _error(
                    "OPEN_AUTOGLM_EXPERT_BASE_URL",
                    "page.settings.validation.expert_base_url.invalid_scheme",
                    "专家 Base URL 必须以 http:// 或 https:// 开头",
                )
            if not expert_model:
                _error(
                    "OPEN_AUTOGLM_EXPERT_MODEL",
                    "page.settings.validation.expert_model.required",
                    "启用专家模式时，专家模型不能为空",
                )

        for key in (
            "OPEN_AUTOGLM_EXPERT_SCREEN_UNCHANGED_THRESHOLD",
            "OPEN_AUTOGLM_EXPERT_CONSECUTIVE_FAILURE_THRESHOLD",
            "OPEN_AUTOGLM_EXPERT_MAX_RESCUES",
        ):
            raw_value = (values.get(key) or "").strip()
            try:
                parsed_value = int(raw_value)
                if parsed_value < 1:
                    _error(
                        key,
                        "page.settings.validation.integer_min",
                        f"{self.get_field_label(key, 'cn')}必须是大于等于 1 的整数",
                        field_key=key,
                        min=1,
                    )
            except ValueError:
                _error(
                    key,
                    "page.settings.validation.integer_required",
                    f"{self.get_field_label(key, 'cn')}必须是整数",
                    field_key=key,
                )

        lang = (values.get("OPEN_AUTOGLM_LANG") or values.get("OPEN_AUTOGLM_LANGUAGE") or "cn").strip().lower()
        if lang not in ("cn", "en", "zh"):
            _error(
                "OPEN_AUTOGLM_LANG",
                "page.settings.validation.lang.invalid",
                "语言仅支持 cn / en / zh",
            )

        policy_version = (values.get("OPEN_AUTOGLM_ACTION_POLICY_VERSION") or str(ACTION_POLICY_VERSION)).strip()
        normalized_policy_version = ACTION_POLICY_VERSION
        try:
            version = int(policy_version)
            if version < 1:
                _error(
                    "OPEN_AUTOGLM_ACTION_POLICY_VERSION",
                    "page.settings.validation.action_policy_version.range",
                    "动作策略版本必须是大于等于 1 的整数",
                )
            else:
                normalized_policy_version = version
        except ValueError:
            _error(
                "OPEN_AUTOGLM_ACTION_POLICY_VERSION",
                "page.settings.validation.action_policy_version.integer",
                "动作策略版本必须是整数",
            )

        normalized_action_values: Dict[str, tuple[str, ...] | None] = {}
        for action_key in ("OPEN_AUTOGLM_ENABLED_ACTIONS", "OPEN_AUTOGLM_AI_VISIBLE_ACTIONS"):
            raw_value = (values.get(action_key) or "").strip()
            if not raw_value:
                normalized_action_values[action_key] = None
                continue
            try:
                normalized_action_values[action_key] = parse_action_name_collection(raw_value)
            except ValueError as exc:
                _error(
                    action_key,
                    "page.settings.validation.actions.invalid_format",
                    f"动作集合格式无效: {exc}",
                    error=str(exc),
                )

        use_platform_defaults = self._is_truthy(
            values.get("OPEN_AUTOGLM_USE_PLATFORM_DEFAULT_ACTIONS", "true")
        )
        runtime_actions = normalized_action_values.get("OPEN_AUTOGLM_ENABLED_ACTIONS")
        ai_visible_actions = normalized_action_values.get("OPEN_AUTOGLM_AI_VISIBLE_ACTIONS")

        if not use_platform_defaults:
            if runtime_actions is None:
                _error(
                    "OPEN_AUTOGLM_ENABLED_ACTIONS",
                    "page.settings.validation.actions.runtime_required_when_defaults_disabled",
                    "禁用平台默认动作回退时，必须显式提供运行时动作集合（允许使用 [] 表示全部禁用）",
                )
            if ai_visible_actions is None:
                _error(
                    "OPEN_AUTOGLM_AI_VISIBLE_ACTIONS",
                    "page.settings.validation.actions.ai_visible_required_when_defaults_disabled",
                    "禁用平台默认动作回退时，必须显式提供 AI 可见动作集合（允许使用 [] 表示全部隐藏）",
                )

        if errors:
            return errors

        resolved_policy = resolve_action_policy(
            device_type,
            ActionPolicyInput(
                ai_visible_actions=ai_visible_actions,
                runtime_enabled_actions=runtime_actions,
                policy_version=normalized_policy_version,
                use_platform_defaults=use_platform_defaults,
            ),
        )

        if resolved_policy.unknown_actions:
            unknown_text = ", ".join(resolved_policy.unknown_actions)
            _error(
                "OPEN_AUTOGLM_ENABLED_ACTIONS",
                "page.settings.validation.actions.unknown",
                f"存在未知动作名：{unknown_text}",
                actions=unknown_text,
            )

        if runtime_actions:
            unsupported_runtime = [
                name for name in runtime_actions if name not in resolved_policy.supported_actions
            ]
            if unsupported_runtime:
                unsupported_text = ", ".join(unsupported_runtime)
                _error(
                    "OPEN_AUTOGLM_ENABLED_ACTIONS",
                    "page.settings.validation.actions.runtime_unsupported",
                    f"当前平台 {device_type} 不支持这些运行时动作：{unsupported_text}",
                    platform=device_type,
                    actions=unsupported_text,
                )

        if ai_visible_actions:
            unsupported_ai = [
                name for name in ai_visible_actions if name not in resolved_policy.supported_actions
            ]
            if unsupported_ai:
                unsupported_text = ", ".join(unsupported_ai)
                _error(
                    "OPEN_AUTOGLM_AI_VISIBLE_ACTIONS",
                    "page.settings.validation.actions.ai_unsupported",
                    f"当前平台 {device_type} 不支持这些 AI 可见动作：{unsupported_text}",
                    platform=device_type,
                    actions=unsupported_text,
                )

            runtime_enabled_set = set(resolved_policy.runtime_enabled_actions)
            not_enabled_for_runtime = [
                name
                for name in ai_visible_actions
                if name in resolved_policy.supported_actions
                and name not in runtime_enabled_set
            ]
            if not_enabled_for_runtime:
                not_enabled_text = ", ".join(not_enabled_for_runtime)
                _error(
                    "OPEN_AUTOGLM_AI_VISIBLE_ACTIONS",
                    "page.settings.validation.actions.ai_not_in_runtime",
                    "以下 AI 可见动作未包含在运行时启用集合中：" + not_enabled_text,
                    actions=not_enabled_text,
                )

        return errors

    def validate(self, updates: Optional[Dict[str, str]] = None) -> List[Tuple[str, str]]:
        """
        兼容旧接口：返回 [(key, error_message), ...]。
        默认按中文渲染，便于旧调用方和既有测试继续工作。
        """
        details = self.validate_details(updates)
        return [
            (str(detail.get("key") or ""), self.render_validation_error(detail, lang="cn"))
            for detail in details
        ]

    # ---------- 渠道预设 ----------

    def build_channel_updates(
        self,
        channel_id: str,
        updates: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        """
        基于当前生效配置构建渠道专属持久化字段。

        作用：
        - 设置页在保存“模型与 API”区后，将当前渠道的 URL / MODEL / API Key
          同步回该渠道的专属 .env 字段
        - 后续点击“快速切换渠道”卡片时，读取到的是用户在 .env 中最后保存的该渠道配置
        """
        preset = next(
            (p for p in self.CHANNEL_PRESETS if p["id"] == channel_id), None
        )
        if preset is None or channel_id == "custom":
            return {}

        merged = dict(self._cache)
        if updates:
            merged.update(updates)

        channel_updates: Dict[str, str] = {}

        url_field = (preset.get("url_field") or "").strip()
        if url_field:
            channel_updates[url_field] = merged.get("OPEN_AUTOGLM_BASE_URL", "") or ""

        model_field = (preset.get("model_field") or "").strip()
        if model_field:
            channel_updates[model_field] = merged.get("OPEN_AUTOGLM_MODEL", "") or ""

        api_key_field = (preset.get("api_key_field") or "").strip()
        if api_key_field:
            channel_updates[api_key_field] = merged.get("OPEN_AUTOGLM_API_KEY", "") or ""

        backup_api_key_field = (preset.get("backup_api_key_field") or "").strip()
        if backup_api_key_field:
            channel_updates[backup_api_key_field] = merged.get("OPEN_AUTOGLM_BACKUP_API_KEY", "") or ""

        return channel_updates

    def get_preset_url(self, preset: Dict) -> str:
        """读取渠道预设的实际 Base URL（优先 .env 专用字段，兜底用 default_url）"""
        field = preset.get("url_field", "")
        if field:
            val = self.get(field)
            if val:
                return val
        return preset.get("default_url", "")

    def get_preset_model(self, preset: Dict) -> str:
        """读取渠道预设的实际模型名（优先 .env 专用字段，兜底用 default_model）"""
        field = preset.get("model_field", "")
        if field:
            val = self.get(field)
            if val:
                return val
        return preset.get("default_model", "")

    def get_active_channel(self) -> Optional[Dict]:
        """
        根据当前 BASE_URL + MODEL 匹配最接近的渠道预设。
        匹配时动态读取渠道的实际 URL 和模型（含用户自定义值）。
        若找不到精确匹配，返回 'custom' 预设。
        """
        current_url = self.get("OPEN_AUTOGLM_BASE_URL").rstrip("/")
        current_model = self.get("OPEN_AUTOGLM_MODEL")
        for preset in self.CHANNEL_PRESETS:
            if preset["id"] == "custom":
                continue
            preset_url = self.get_preset_url(preset).rstrip("/")
            preset_model = self.get_preset_model(preset)
            if preset_url == current_url and preset_model == current_model:
                return preset
        return next((p for p in self.CHANNEL_PRESETS if p["id"] == "custom"), None)

    def set_active_channel(self, channel_id: str) -> bool:
        """
        快速切换到指定渠道，并写回当前生效配置。
        - BASE_URL / MODEL 从该渠道在 .env 中保存的专属字段读取
        - OPEN_AUTOGLM_API_KEY / OPEN_AUTOGLM_BACKUP_API_KEY 同步为该渠道已保存值
        - 不覆盖 USE_THIRDPARTY_PROMPT / COMPRESS_IMAGE 等用户单独保存的运行开关
        - 「自定义」模式不主动改写当前配置
        返回 True 表示切换成功。
        """
        preset = next(
            (p for p in self.CHANNEL_PRESETS if p["id"] == channel_id), None
        )
        if preset is None:
            return False

        if channel_id == "custom":
            return True

        # 动态读取该渠道实际的 URL / 模型 / Key（含用户在 .env 中已自定义的值）
        resolved_url = self.get_preset_url(preset)
        resolved_model = self.get_preset_model(preset)

        key_field = (preset.get("api_key_field") or "").strip()
        backup_key_field = (preset.get("backup_api_key_field") or "").strip()

        updates: Dict[str, str] = {
            "OPEN_AUTOGLM_BASE_URL": resolved_url,
            "OPEN_AUTOGLM_MODEL": resolved_model,
            "OPEN_AUTOGLM_API_KEY": self.get(key_field) if key_field else "",
            "OPEN_AUTOGLM_BACKUP_API_KEY": self.get(backup_key_field) if backup_key_field else "",
        }
        try:
            self.set_many(updates)
        except Exception:
            return False
        return True

    def resolve_api_key(self) -> Tuple[str, str]:
        """按运行时优先级解析当前实际生效的 API Key 与来源字段。"""
        api_key = (self.get("OPEN_AUTOGLM_API_KEY") or "").strip()
        if api_key:
            return api_key, "OPEN_AUTOGLM_API_KEY"

        base_url = (self.get("OPEN_AUTOGLM_BASE_URL") or "").strip().lower()
        if "modelscope" in base_url:
            primary = (self.get("OPEN_AUTOGLM_MODELSCOPE_API_KEY") or "").strip()
            if primary:
                return primary, "OPEN_AUTOGLM_MODELSCOPE_API_KEY"
            backup = (self.get("OPEN_AUTOGLM_MODELSCOPE_BACKUP_API_KEY") or "").strip()
            if backup:
                return backup, "OPEN_AUTOGLM_MODELSCOPE_BACKUP_API_KEY"
        elif "bigmodel" in base_url:
            zhipu_key = (self.get("OPEN_AUTOGLM_ZHIPU_API_KEY") or "").strip()
            if zhipu_key:
                return zhipu_key, "OPEN_AUTOGLM_ZHIPU_API_KEY"
        elif "127.0.0.1" in base_url or "localhost" in base_url:
            local_key = (self.get("OPEN_AUTOGLM_LOCAL_OPENAI_API_KEY") or "").strip()
            if local_key:
                return local_key, "OPEN_AUTOGLM_LOCAL_OPENAI_API_KEY"
        else:
            newapi_key = (self.get("OPEN_AUTOGLM_NEWAPI_API_KEY") or "").strip()
            if newapi_key:
                return newapi_key, "OPEN_AUTOGLM_NEWAPI_API_KEY"

        active = self.get_active_channel()
        if active:
            field_name = (active.get("api_key_field") or "").strip()
            if field_name:
                value = (self.get(field_name) or "").strip()
                if value:
                    return value, field_name

        return "", ""

    # ---------- 构建命令行参数 ----------

    def build_command_args(self, task_text: str, device_id_override: str = "") -> List[str]:
        """构建任务子进程命令行参数列表。"""
        cli_args: List[str] = []

        base_url = self.get("OPEN_AUTOGLM_BASE_URL")
        if base_url:
            cli_args += ["--base-url", base_url]

        model = self.get("OPEN_AUTOGLM_MODEL")
        if model:
            cli_args += ["--model", model]

        api_key, _ = self.resolve_api_key()
        if api_key:
            cli_args += ["--apikey", api_key]

        device_type = (self.get("OPEN_AUTOGLM_DEVICE_TYPE", "adb") or "adb").strip().lower()
        cli_args += ["--device-type", device_type]

        device_id = (device_id_override or self.get("OPEN_AUTOGLM_DEVICE_ID") or "").strip()
        if device_id:
            cli_args += ["--device-id", device_id]

        max_steps = self.get("OPEN_AUTOGLM_MAX_STEPS", "100")
        cli_args += ["--max-steps", max_steps]

        language = (self.get("OPEN_AUTOGLM_LANG", "cn") or "cn").strip().lower()
        if language == "zh":
            language = "cn"
        cli_args += ["--lang", language]

        action_policy = self.get_action_policy_settings()
        cli_args += ["--action-policy-version", str(action_policy["policy_version"])]
        if not action_policy["use_platform_defaults"]:
            cli_args.append("--disable-platform-default-actions")
        if action_policy["enabled_actions"]:
            cli_args += ["--enabled-actions", action_policy["enabled_actions"]]
        if action_policy["ai_visible_actions"]:
            cli_args += ["--ai-visible-actions", action_policy["ai_visible_actions"]]

        # 第三方模型（非 AutoGLM 原生）提示词工程参数，与 launcher.py 保持一致
        if self._is_truthy(self.get("OPEN_AUTOGLM_USE_THIRDPARTY_PROMPT", "false")):
            cli_args.append("--thirdparty")
            thinking_enabled = self._is_truthy(self.get("OPEN_AUTOGLM_THIRDPARTY_THINKING", "true"))
            cli_args.append("--thirdparty-thinking" if thinking_enabled else "--thirdparty-no-thinking")

            compress_image = self._is_truthy(self.get("OPEN_AUTOGLM_COMPRESS_IMAGE", "false"))
            if not compress_image:
                cli_args.append("--no-compress-image")

        if self._is_truthy(self.get("OPEN_AUTOGLM_EXPERT_MODE", "false")):
            cli_args.append("--expert-mode")
            expert_base_url = (self.get("OPEN_AUTOGLM_EXPERT_BASE_URL") or "").strip()
            expert_model = (self.get("OPEN_AUTOGLM_EXPERT_MODEL") or "").strip()
            expert_api_key = (self.get("OPEN_AUTOGLM_EXPERT_API_KEY") or "").strip()
            expert_prompt = self.get("OPEN_AUTOGLM_EXPERT_PROMPT") or ""
            if expert_base_url:
                cli_args += ["--expert-base-url", expert_base_url]
            if expert_model:
                cli_args += ["--expert-model", expert_model]
            if expert_api_key:
                cli_args += ["--expert-apikey", expert_api_key]
            if expert_prompt.strip():
                cli_args += ["--expert-prompt", expert_prompt]
            if self._is_truthy(self.get("OPEN_AUTOGLM_EXPERT_STRICT_MODE", "false")):
                cli_args.append("--expert-strict-mode")
            if self._is_truthy(self.get("OPEN_AUTOGLM_EXPERT_AUTO_INIT", "true")):
                cli_args.append("--expert-auto-init")
            else:
                cli_args.append("--expert-no-auto-init")
            if self._is_truthy(self.get("OPEN_AUTOGLM_EXPERT_AUTO_RESCUE", "true")):
                cli_args.append("--expert-auto-rescue")
            else:
                cli_args.append("--expert-no-auto-rescue")
            if self._is_truthy(self.get("OPEN_AUTOGLM_EXPERT_MANUAL_ACTION", "true")):
                cli_args.append("--expert-manual-action")
            else:
                cli_args.append("--expert-no-manual-action")
            cli_args += [
                "--expert-screen-unchanged-threshold",
                self.get("OPEN_AUTOGLM_EXPERT_SCREEN_UNCHANGED_THRESHOLD", "4") or "4",
                "--expert-consecutive-failure-threshold",
                self.get("OPEN_AUTOGLM_EXPERT_CONSECUTIVE_FAILURE_THRESHOLD", "3") or "3",
                "--expert-max-rescues",
                self.get("OPEN_AUTOGLM_EXPERT_MAX_RESCUES", "3") or "3",
            ]

        cli_args.append(task_text)
        return build_task_subprocess_command(cli_args)
