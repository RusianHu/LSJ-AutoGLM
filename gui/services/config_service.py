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

import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QObject, Signal

_ENV_FILE = Path(".env")


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
        "OPEN_AUTOGLM_DEVICE_ID": "",
        "OPEN_AUTOGLM_LANG": "cn",
        "OPEN_AUTOGLM_MAX_STEPS": "100",
        "OPEN_AUTOGLM_USE_THIRDPARTY_PROMPT": "false",
        "OPEN_AUTOGLM_THIRDPARTY_THINKING": "true",
        "OPEN_AUTOGLM_COMPRESS_IMAGE": "false",
        "OPEN_AUTOGLM_NEWAPI_API_KEY": "",
        "OPEN_AUTOGLM_NEWAPI_BASE_URL": "https://ai.yanshanlaosiji.top/v1",
        "OPEN_AUTOGLM_NEWAPI_MODEL": "Qwen/Qwen3-VL-235B-A22B-Instruct",
        "OPEN_AUTOGLM_MODELSCOPE_API_KEY": "",
        "OPEN_AUTOGLM_MODELSCOPE_BACKUP_API_KEY": "",
        "OPEN_AUTOGLM_ZHIPU_API_KEY": "",
        "OPEN_AUTOGLM_LOCAL_OPENAI_API_KEY": "",
        "OPEN_AUTOGLM_THEME": "system",
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
    }

    # 字段元数据，供 SettingsPage 渲染表单行
    FIELD_META: Dict[str, dict] = {
        "OPEN_AUTOGLM_BASE_URL": {"label": "Base URL", "sensitive": False, "editable": True},
        "OPEN_AUTOGLM_MODEL": {"label": "模型名称", "sensitive": False, "editable": True},
        "OPEN_AUTOGLM_API_KEY": {"label": "API Key", "sensitive": True, "editable": True},
        "OPEN_AUTOGLM_BACKUP_API_KEY": {"label": "备用 API Key", "sensitive": True, "editable": True},
        "OPEN_AUTOGLM_MODELSCOPE_API_KEY": {"label": "ModelScope Key", "sensitive": True, "editable": True},
        "OPEN_AUTOGLM_MODELSCOPE_BACKUP_API_KEY": {"label": "ModelScope 备用 Key", "sensitive": True, "editable": True},
        "OPEN_AUTOGLM_ZHIPU_API_KEY": {"label": "智谱 API Key", "sensitive": True, "editable": True},
        "OPEN_AUTOGLM_NEWAPI_API_KEY": {"label": "API Key", "sensitive": True, "editable": True},
        "OPEN_AUTOGLM_NEWAPI_BASE_URL": {"label": "Base URL", "sensitive": False, "editable": True},
        "OPEN_AUTOGLM_NEWAPI_MODEL": {"label": "模型名称", "sensitive": False, "editable": True},
        "OPEN_AUTOGLM_LOCAL_OPENAI_BASE_URL": {"label": "Base URL", "sensitive": False, "editable": True},
        "OPEN_AUTOGLM_LOCAL_OPENAI_MODEL": {"label": "模型名称", "sensitive": False, "editable": True},
        "OPEN_AUTOGLM_LOCAL_OPENAI_API_KEY": {"label": "API Key (可选)", "sensitive": True, "editable": True},
        "OPEN_AUTOGLM_DEVICE_ID": {"label": "设备 ID", "sensitive": False, "editable": True},
        "OPEN_AUTOGLM_LANG": {"label": "语言", "sensitive": False, "editable": True},
        "OPEN_AUTOGLM_MAX_STEPS": {"label": "最大步数", "sensitive": False, "editable": True},
        "OPEN_AUTOGLM_USE_THIRDPARTY_PROMPT": {"label": "启用第三方提示词工程", "sensitive": False, "editable": True, "boolean": True},
        "OPEN_AUTOGLM_THIRDPARTY_THINKING": {"label": "第三方思考输出 (think/answer 标签)", "sensitive": False, "editable": True, "boolean": True},
        "OPEN_AUTOGLM_COMPRESS_IMAGE": {"label": "截图压缩", "sensitive": False, "editable": True, "boolean": True},
        "OPEN_AUTOGLM_THEME": {"label": "界面主题", "sensitive": False, "editable": False},
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
            "url_field": "",
            "model_field": "",
            "default_url": "https://api-inference.modelscope.cn/v1",
            "default_model": "ZhipuAI/AutoGLM-Phone-9B",
            "use_thirdparty": False,
            "compress_image": False,
            "api_key_field": "OPEN_AUTOGLM_MODELSCOPE_API_KEY",
        },
        {
            "id": "zhipu",
            "name": "智谱",
            "url_field": "",
            "model_field": "",
            "default_url": "https://open.bigmodel.cn/api/paas/v4",
            "default_model": "AutoGLM-Phone-9B",
            "use_thirdparty": False,
            "compress_image": False,
            "api_key_field": "OPEN_AUTOGLM_ZHIPU_API_KEY",
        },
        {
            "id": "newapi",
            "name": "自建中转站",
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
            "default_url": "http://127.0.0.1:8000/v1",
            "default_model": "local-model",
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
        self.load()

    @property
    def env_path(self) -> str:
        """返回 .env 文件路径字符串（供 SettingsPage 显示）"""
        return str(self._env_file.resolve())

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

        if not self._env_file.exists():
            self._normalize_aliases()
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
    def _is_truthy(value: str) -> bool:
        return str(value).strip().lower() in ("1", "true", "yes", "on")

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
        tmp_path = self._env_file.with_suffix(".env.tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
            tmp_path.replace(self._env_file)
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

    def validate(self, updates: Optional[Dict[str, str]] = None) -> List[Tuple[str, str]]:
        """
        校验配置项（不修改缓存）。
        updates: 临时覆盖值用于校验；为 None 则校验当前缓存。
        返回：[(key, error_message), ...]
        """
        values = dict(self._cache)
        if updates:
            values.update(updates)  # 只在本地副本上操作，不污染缓存

        errors = []

        base_url = values.get("OPEN_AUTOGLM_BASE_URL", "")
        if base_url and not (base_url.startswith("http://") or
                             base_url.startswith("https://")):
            errors.append(("OPEN_AUTOGLM_BASE_URL", "Base URL 必须以 http:// 或 https:// 开头"))

        model = values.get("OPEN_AUTOGLM_MODEL", "")
        if not model:
            errors.append(("OPEN_AUTOGLM_MODEL", "模型名称不能为空"))

        max_steps = values.get("OPEN_AUTOGLM_MAX_STEPS", "100")
        try:
            s = int(max_steps)
            if s < 1 or s > 1000:
                errors.append(("OPEN_AUTOGLM_MAX_STEPS",
                               "最大步数应在 1-1000 之间"))
        except ValueError:
            errors.append(("OPEN_AUTOGLM_MAX_STEPS", "最大步数必须是整数"))

        lang = (values.get("OPEN_AUTOGLM_LANG") or
                values.get("OPEN_AUTOGLM_LANGUAGE") or "cn").strip().lower()
        if lang not in ("cn", "en", "zh"):
            errors.append(("OPEN_AUTOGLM_LANG", "语言仅支持 cn / en / zh"))

        return errors

    # ---------- 渠道预设 ----------

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
        - BASE_URL/MODEL 使用该渠道在 .env 中的专用字段值（或 default 值）
        - 若渠道对应的 api_key_field 已有值，同步到 OPEN_AUTOGLM_API_KEY
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

        # 动态读取该渠道实际的 URL 和模型（含用户在 .env 中已自定义的值）
        resolved_url = self.get_preset_url(preset)
        resolved_model = self.get_preset_model(preset)

        updates: Dict[str, str] = {
            "OPEN_AUTOGLM_BASE_URL": resolved_url,
            "OPEN_AUTOGLM_MODEL": resolved_model,
        }
        # 若渠道专用 api_key_field 有值，同步到通用 API_KEY
        key_field = preset.get("api_key_field", "")
        if key_field:
            channel_key = self.get(key_field)
            if channel_key:
                updates["OPEN_AUTOGLM_API_KEY"] = channel_key
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
        """构建启动 main.py 的命令行参数列表"""
        args = [sys.executable, "-u", "main.py"]

        base_url = self.get("OPEN_AUTOGLM_BASE_URL")
        if base_url:
            args += ["--base-url", base_url]

        model = self.get("OPEN_AUTOGLM_MODEL")
        if model:
            args += ["--model", model]

        api_key, _ = self.resolve_api_key()
        if api_key:
            args += ["--apikey", api_key]

        device_id = (device_id_override or self.get("OPEN_AUTOGLM_DEVICE_ID") or "").strip()
        if device_id:
            args += ["--device-id", device_id]

        max_steps = self.get("OPEN_AUTOGLM_MAX_STEPS", "100")
        args += ["--max-steps", max_steps]

        language = (self.get("OPEN_AUTOGLM_LANG", "cn") or "cn").strip().lower()
        if language == "zh":
            language = "cn"
        args += ["--lang", language]

        # 第三方模型（非 AutoGLM 原生）提示词工程参数，与 launcher.py 保持一致
        if self._is_truthy(self.get("OPEN_AUTOGLM_USE_THIRDPARTY_PROMPT", "false")):
            args.append("--thirdparty")
            thinking_enabled = self._is_truthy(self.get("OPEN_AUTOGLM_THIRDPARTY_THINKING", "true"))
            args.append("--thirdparty-thinking" if thinking_enabled else "--thirdparty-no-thinking")

            compress_image = self._is_truthy(self.get("OPEN_AUTOGLM_COMPRESS_IMAGE", "false"))
            if not compress_image:
                args.append("--no-compress-image")

        args.append(task_text)
        return args
