#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Open-AutoGLM 交互式启动器
一个全面的检查、配置和启动工具
"""

import os
import sys
import subprocess
import shutil
import time
import json
import getpass
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional, Tuple, List, Union, Any, Dict

# 确保 UTF-8 编码
os.environ['PYTHONIOENCODING'] = 'utf-8'
if sys.platform == 'win32':
    os.system('chcp 65001 >nul 2>&1')


def _env_truthy(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "y", "on")


def _load_env_file(env_path: Union[str, Path], override: bool = False) -> Tuple[bool, str]:
    """
    Load a minimal .env file into process environment.

    - Supports KEY=VALUE (VALUE may be quoted).
    - Ignores blank lines and lines starting with '#'.
    - By default does NOT override existing environment variables.
    """
    try:
        p = Path(env_path).expanduser().resolve()
    except Exception:
        p = Path(env_path)

    if not p.exists() or not p.is_file():
        return False, f".env 文件不存在: {p}"

    try:
        for raw_line in p.read_text(encoding="utf-8-sig").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export ") :].strip()
            if "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()

            if not key:
                continue

            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                value = value[1:-1]

            if not override and key in os.environ:
                continue

            os.environ[key] = value
        return True, f".env 已加载: {p}"
    except Exception as e:
        return False, f".env 读取失败: {type(e).__name__}: {e}"


def allow_config_file_secrets() -> bool:
    return _env_truthy("OPEN_AUTOGLM_ALLOW_CONFIG_FILE_SECRETS", default=False)


# 尝试加载 .env（用于把敏感信息/配置从脚本中剥离）
# 仅在环境变量未设置时生效（避免覆盖用户的系统环境变量）
_env_path = os.environ.get("OPEN_AUTOGLM_ENV_PATH", ".env").strip() or ".env"
_ENV_LOAD_OK, _ENV_LOAD_MSG = _load_env_file(_env_path, override=False)
if _env_truthy("OPEN_AUTOGLM_DEBUG", default=False):
    print(f"[debug] {_ENV_LOAD_MSG}")


# ============== 配置 ==============
# 配置文件路径（用于持久化 launcher 配置）
CONFIG_PATH = Path(
    os.environ.get(
        "OPEN_AUTOGLM_LAUNCHER_CONFIG",
        str(Path.home() / ".open-autoglm-launcher.json"),
    )
)

DEFAULT_ADB_PORT = 5555
ADB_KEYBOARD_APK_ENV = "OPEN_AUTOGLM_ADBKEYBOARD_APK"
ADB_KEYBOARD_APK_NAME = "ADBKeyboard.apk"

# 预设的 API 配置（不包含任何硬编码敏感信息）
def _env_str(name: str, default: str = "") -> str:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip()


API_PRESETS = {
    "modelscope": {
        "name": "ModelScope (魔搭社区)",
        "base_url": "https://api-inference.modelscope.cn/v1",
        "model": "ZhipuAI/AutoGLM-Phone-9B",
        "compatible": True,
        "note": "API Key 请在 .env 中设置 OPEN_AUTOGLM_MODELSCOPE_API_KEY/OPEN_AUTOGLM_MODELSCOPE_BACKUP_API_KEY",
    },
    "zhipu": {
        "name": "智谱 BigModel",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "autoglm-phone",
        "compatible": True,
        "note": "API Key 请在 .env 中设置 OPEN_AUTOGLM_ZHIPU_API_KEY",
    },
    "newapi": {
        "name": "第三方API",
        "base_url": _env_str("OPEN_AUTOGLM_NEWAPI_BASE_URL", "https://ai.yanshanlaosiji.top/v1"),
        "model": _env_str("OPEN_AUTOGLM_NEWAPI_MODEL", "Qwen/Qwen3-VL-235B-A22B-Instruct"),
        "compatible": True,                 # 使用第三方提示词工程后兼容
        "use_thirdparty_prompt": _env_truthy("OPEN_AUTOGLM_NEWAPI_USE_THIRDPARTY_PROMPT", default=True),
        "thirdparty_thinking": _env_truthy("OPEN_AUTOGLM_NEWAPI_THIRDPARTY_THINKING", default=True),
        "note": "API Key 请在 .env 中设置 OPEN_AUTOGLM_NEWAPI_API_KEY",
    },
    "local_openai": {
        "name": "本地 OpenAI 兼容服务",
        "base_url": _env_str("OPEN_AUTOGLM_LOCAL_OPENAI_BASE_URL", "http://127.0.0.1:1234"),
        "model": _env_str("OPEN_AUTOGLM_LOCAL_OPENAI_MODEL", "autoglm-phone-9b"),
        "use_thirdparty_prompt": False,      # 标记需要使用第三方提示词
        "allow_empty_key": _env_truthy("OPEN_AUTOGLM_LOCAL_OPENAI_ALLOW_EMPTY_KEY", default=True),
        "compatible": True,
        "note": "可选 Key：OPEN_AUTOGLM_LOCAL_OPENAI_API_KEY；部分本地服务允许不填 Key",
    }
}

@dataclass
class Config:
    """API 和设备配置（默认从 .env / 环境变量读取）"""

    base_url: str = field(
        default_factory=lambda: os.environ.get(
            "OPEN_AUTOGLM_BASE_URL", "https://api-inference.modelscope.cn/v1"
        ).strip()
    )
    model: str = field(
        default_factory=lambda: os.environ.get(
            "OPEN_AUTOGLM_MODEL", "ZhipuAI/AutoGLM-Phone-9B"
        ).strip()
    )

    # 敏感信息：从环境变量读取，默认留空
    api_key: str = field(default_factory=lambda: os.environ.get("OPEN_AUTOGLM_API_KEY", "").strip())
    backup_api_key: str = field(
        default_factory=lambda: os.environ.get("OPEN_AUTOGLM_BACKUP_API_KEY", "").strip()
    )

    # 设备
    device_id: Optional[str] = field(
        default_factory=lambda: (os.environ.get("OPEN_AUTOGLM_DEVICE_ID", "").strip() or None)
    )

    # 语言
    lang: str = field(default_factory=lambda: os.environ.get("OPEN_AUTOGLM_LANG", "cn").strip() or "cn")

    max_steps: int = field(
        default_factory=lambda: int(os.environ.get("OPEN_AUTOGLM_MAX_STEPS", "100").strip() or "100")
    )

    # 第三方模型提示词工程
    use_thirdparty_prompt: bool = field(
        default_factory=lambda: _env_truthy("OPEN_AUTOGLM_USE_THIRDPARTY_PROMPT", default=False)
    )

    # 第三方模式启用思考（规范输出 <think>/<answer>；部分中转站不兼容可关闭）
    thirdparty_thinking: bool = field(
        default_factory=lambda: _env_truthy("OPEN_AUTOGLM_THIRDPARTY_THINKING", default=True)
    )

    # 第三方模式截图压缩（部分模型/中转站对大图敏感；但压缩过度会影响识别）
    compress_image: bool = field(
        default_factory=lambda: _env_truthy("OPEN_AUTOGLM_COMPRESS_IMAGE", default=False)
    )

CONFIG = Config()
_SKIP_CLEAR_ONCE = False

# ============== 工具函数 ==============
def clear_screen():
    """清屏"""
    os.system('cls' if sys.platform == 'win32' else 'clear')

def mask_secret(value: str, show_start: int = 6, show_end: int = 4) -> str:
    """遮蔽敏感信息显示（避免在屏幕/录屏中泄露）"""
    if not value:
        return "(未设置)"
    if len(value) <= show_start + show_end:
        return "*" * len(value)
    return f"{value[:show_start]}...{value[-show_end:]}"

def prompt_secret(prompt: str) -> str:
    """输入敏感信息（尽量不回显）"""
    try:
        return getpass.getpass(prompt)
    except Exception:
        return input(prompt)

def parse_port(port: Union[str, int]) -> Tuple[Optional[int], str]:
    """解析端口号并校验范围"""
    try:
        port_int = int(str(port).strip())
    except Exception:
        return None, "端口号无效（需要数字）"
    if not (1 <= port_int <= 65535):
        return None, "端口号无效（范围 1-65535）"
    return port_int, ""

def parse_host_port(addr: str, default_port: int = DEFAULT_ADB_PORT) -> Tuple[Optional[Tuple[str, int]], str]:
    """解析 host:port（缺省端口时自动补全）"""
    raw = (addr or "").strip()
    if not raw:
        return None, "地址不能为空"

    if ":" not in raw:
        raw = f"{raw}:{default_port}"

    host, port_str = raw.rsplit(":", 1)
    host = host.strip()
    if not host:
        return None, "IP/主机名不能为空"

    port_int, err = parse_port(port_str)
    if port_int is None:
        return None, err

    return (host, port_int), ""

def normalize_openai_base_url(base_url: str) -> str:
    """
    Normalize OpenAI-compatible base_url.

    Most OpenAI-compatible servers expose endpoints under /v1.
    If the user provides a host root like http://127.0.0.1:8080, we auto-append /v1.
    """
    raw = (base_url or "").strip().rstrip("/")
    if not raw:
        return raw
    if raw.endswith("/v1"):
        return raw
    return f"{raw}/v1"

def effective_api_key(api_key: str) -> str:
    """
    OpenAI python SDK requires api_key to be set.

    Some local OpenAI-compatible servers do not require a real key; allow user to leave it blank
    and use a placeholder for compatibility.
    """
    return api_key if (api_key or "").strip() else "EMPTY"

def find_adb_keyboard_apk() -> Optional[Path]:
    """查找 ADB Keyboard APK 路径（支持环境变量覆盖）"""
    env_path = os.environ.get(ADB_KEYBOARD_APK_ENV, "").strip()
    if env_path:
        p = Path(env_path)
        return p if p.exists() else None

    candidates = [
        Path(__file__).resolve().parent / ADB_KEYBOARD_APK_NAME,
        Path.cwd() / ADB_KEYBOARD_APK_NAME,
    ]
    for p in candidates:
        if p.exists():
            return p
    return None

def load_config_from_file() -> Tuple[bool, str]:
    """
    从本地文件加载配置（可选）

    默认不从配置文件读取敏感信息（API Key），防止无意间落盘/共享导致泄露；
    如确需允许，请设置环境变量 OPEN_AUTOGLM_ALLOW_CONFIG_FILE_SECRETS=true
    """
    if not CONFIG_PATH.exists():
        return False, "未找到配置文件"
    try:
        data: Dict[str, Any] = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        return False, f"读取配置失败: {type(e).__name__}: {e}"

    if isinstance(data.get("base_url"), str) and data["base_url"].strip():
        CONFIG.base_url = data["base_url"].strip()
    if isinstance(data.get("model"), str) and data["model"].strip():
        CONFIG.model = data["model"].strip()

    if (not allow_config_file_secrets()) and _env_truthy("OPEN_AUTOGLM_DEBUG", default=False):
        if isinstance(data.get("api_key"), str) or isinstance(data.get("backup_api_key"), str):
            print(
                "[debug] 已忽略配置文件中的 api_key/backup_api_key "
                "(OPEN_AUTOGLM_ALLOW_CONFIG_FILE_SECRETS=false)"
            )

    if allow_config_file_secrets():
        if isinstance(data.get("api_key"), str):
            CONFIG.api_key = data["api_key"].strip()
        if isinstance(data.get("backup_api_key"), str):
            CONFIG.backup_api_key = data["backup_api_key"].strip()

    if isinstance(data.get("device_id"), str):
        CONFIG.device_id = data["device_id"].strip() or None
    if data.get("lang") in ("cn", "en"):
        CONFIG.lang = data["lang"]
    if "max_steps" in data:
        try:
            max_steps = int(data["max_steps"])
            if max_steps > 0:
                CONFIG.max_steps = max_steps
        except Exception:
            pass
    if isinstance(data.get("use_thirdparty_prompt"), bool):
        CONFIG.use_thirdparty_prompt = data["use_thirdparty_prompt"]
    if isinstance(data.get("thirdparty_thinking"), bool):
        CONFIG.thirdparty_thinking = data["thirdparty_thinking"]
    if isinstance(data.get("compress_image"), bool):
        CONFIG.compress_image = data["compress_image"]
    return True, "配置已加载"

def save_config_to_file() -> Tuple[bool, str]:
    """
    保存配置到本地文件

    默认不落盘保存敏感信息（API Key）；
    如确需允许，请设置环境变量 OPEN_AUTOGLM_ALLOW_CONFIG_FILE_SECRETS=true
    """
    try:
        payload = asdict(CONFIG)
        if not allow_config_file_secrets():
            payload.pop("api_key", None)
            payload.pop("backup_api_key", None)

        tmp_path = CONFIG_PATH.with_suffix(CONFIG_PATH.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(CONFIG_PATH)
        if allow_config_file_secrets():
            return True, f"配置已保存(包含敏感字段): {CONFIG_PATH}"
        return True, f"配置已保存: {CONFIG_PATH}"
    except Exception as e:
        return False, f"保存失败: {type(e).__name__}: {e}"

def run_cmd(cmd: List[str], timeout: int = 10) -> Tuple[bool, str]:
    """运行命令并返回结果"""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return result.returncode == 0, (result.stdout + result.stderr).strip()
    except subprocess.TimeoutExpired:
        return False, "命令超时"
    except FileNotFoundError:
        return False, f"未找到命令: {cmd[0]}"
    except Exception as e:
        return False, str(e)

def print_header(clear: bool = True):
    """打印标题"""
    global _SKIP_CLEAR_ONCE
    if clear and not _SKIP_CLEAR_ONCE:
        clear_screen()
    _SKIP_CLEAR_ONCE = False
    print("=" * 60)
    print("  🤖 Open-AutoGLM 交互式启动器")
    print("  📱 AI 驱动的手机自动化控制系统")
    print("=" * 60)

def print_divider(title: str = ""):
    """打印分隔线"""
    if title:
        print(f"\n{'─' * 20} {title} {'─' * 20}")
    else:
        print("─" * 60)

# ============== ADB 相关函数 ==============
def check_adb_installed() -> Tuple[bool, str]:
    """检查 ADB 是否安装"""
    if shutil.which("adb") is None:
        return False, "未安装"
    success, output = run_cmd(["adb", "version"])
    if success:
        version = output.split('\n')[0] if output else "未知版本"
        return True, version
    return False, "无法获取版本"

def get_connected_devices() -> List[dict]:
    """获取已连接的设备列表"""
    success, output = run_cmd(["adb", "devices", "-l"])
    if not success:
        return []
    
    devices = []
    for line in output.split('\n')[1:]:
        if not line.strip() or 'offline' in line:
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[1] == 'device':
            device = {'id': parts[0], 'model': '', 'type': 'USB'}
            if ':' in parts[0]:
                device['type'] = '无线'
            for part in parts[2:]:
                if part.startswith('model:'):
                    device['model'] = part.split(':')[1]
            devices.append(device)
    return devices

def check_adb_keyboard(device_id: Optional[str] = None) -> bool:
    """检查 ADB Keyboard 是否安装"""
    cmd = ["adb"]
    if device_id:
        cmd.extend(["-s", device_id])
    cmd.extend(["shell", "ime", "list", "-s"])
    success, output = run_cmd(cmd)
    return success and "com.android.adbkeyboard/.AdbIME" in output

def connect_wireless(ip: str, port: Union[str, int]) -> Tuple[bool, str]:
    """无线连接设备"""
    port_int, err = parse_port(port)
    if port_int is None:
        return False, err
    address = f"{ip}:{port_int}"
    success, output = run_cmd(["adb", "connect", address], timeout=15)
    if success and ("connected" in output.lower() or "already" in output.lower()):
        return True, f"已连接到 {address}"
    return False, output

def disconnect_device(device_id: str = "") -> Tuple[bool, str]:
    """断开设备连接"""
    cmd = ["adb", "disconnect"]
    if device_id:
        cmd.append(device_id)
    return run_cmd(cmd)

def restart_adb_server() -> Tuple[bool, str]:
    """重启 ADB 服务"""
    run_cmd(["adb", "kill-server"])
    time.sleep(1)
    return run_cmd(["adb", "start-server"])

def get_device_ip(device_id: Optional[str] = None) -> Optional[str]:
    """获取设备 IP 地址"""
    cmd = ["adb"]
    if device_id:
        cmd.extend(["-s", device_id])
    cmd.extend(["shell", "ip", "route"])
    success, output = run_cmd(cmd)
    if success:
        for line in output.split('\n'):
            if 'src' in line:
                parts = line.split()
                for i, p in enumerate(parts):
                    if p == 'src' and i + 1 < len(parts):
                        return parts[i + 1]
    return None

def enable_tcpip(port: int = DEFAULT_ADB_PORT, device_id: Optional[str] = None) -> Tuple[bool, str]:
    """启用 TCP/IP 调试"""
    cmd = ["adb"]
    if device_id:
        cmd.extend(["-s", device_id])
    cmd.extend(["tcpip", str(port)])
    success, output = run_cmd(cmd)
    if success:
        time.sleep(2)
        return True, f"已在端口 {port} 启用 TCP/IP 模式"
    return False, output

# ============== API 检查 ==============
def check_api_connection() -> Tuple[bool, str]:
    """检查 API 连接"""
    def _format_err(e: Exception) -> str:
        msg = f"{type(e).__name__}: {e}"
        msg = msg.replace("\n", " ").strip()
        return msg[:160] if len(msg) > 160 else msg

    try:
        from openai import OpenAI
        client = OpenAI(
            base_url=normalize_openai_base_url(CONFIG.base_url),
            api_key=effective_api_key(CONFIG.api_key),
            timeout=30,
        )

        # 1) 优先尝试 models.list（不涉及对话内容，更不容易被策略拦截）
        try:
            client.models.list()
            return True, "API 连接正常"
        except Exception:
            pass

        # 2) 回退到最小对话请求
        response = client.chat.completions.create(
            model=CONFIG.model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
            stream=False,
        )
        if getattr(response, "choices", None):
            return True, "API 连接正常"
        return False, "API 返回空响应"
    except Exception as e:
        return False, _format_err(e)

# ============== 显示函数 ==============
def show_status():
    """显示系统状态"""
    print_header()
    print_divider("系统状态")

    # ADB 状态
    adb_ok, adb_ver = check_adb_installed()
    print(f"  {'✅' if adb_ok else '❌'} ADB: {adb_ver}")

    # 设备状态
    devices = get_connected_devices()
    if devices:
        print(f"  ✅ 已连接设备: {len(devices)} 台")
        for d in devices:
            model = f" ({d['model']})" if d['model'] else ""
            kbd = "✓键盘" if check_adb_keyboard(d['id']) else "✗键盘"
            print(f"     📱 {d['id']} [{d['type']}]{model} {kbd}")
            if CONFIG.device_id is None:
                CONFIG.device_id = d['id']
    else:
        print("  ❌ 已连接设备: 无")

    print_divider("API 配置")
    print(f"  🌐 API地址: {CONFIG.base_url}")
    print(f"  🤖 模型: {CONFIG.model}")
    print(f"  🔑 API Key: {mask_secret(CONFIG.api_key)}")

    print_divider("当前设置")
    print(f"  🎯 目标设备: {CONFIG.device_id or '自动检测'}")
    print(f"  🌍 语言: {'中文' if CONFIG.lang == 'cn' else '英文'}")
    print(f"  📊 最大步数: {CONFIG.max_steps}")
    if CONFIG.use_thirdparty_prompt:
        print(f"  📝 提示词模式: 第三方模型适配")

def show_main_menu():
    """显示主菜单"""
    print_divider("主菜单")
    print("  [1] 🚀 启动 Phone Agent (交互模式)")
    print("  [2] 📝 执行单个任务")
    print("  [3] 📱 设备管理")
    print("  [4] 🔧 选择模型/API")
    print("  [5] ⚙️  配置设置")
    print("  [6] 🔍 系统检查")
    print("  [7] 📖 使用帮助")
    print("  [0] 🚪 退出")
    print_divider()

def show_api_menu():
    """显示模型/API 选择菜单（主界面快捷入口）"""
    print_header()
    print_divider("选择模型/API")
    print("  请选择一个预设:")
    print(f"    [1] 🔄 {API_PRESETS['modelscope']['name']} (推荐)")
    print(f"    [2] 🔄 {API_PRESETS['zhipu']['name']}")
    print(f"    [3] 🔄 {API_PRESETS['newapi']['name']} (第三方提示词工程)")
    print(f"    [4] 🔄 {API_PRESETS['local_openai']['name']} (本地/自建)")
    print_divider("其他")
    print("  [t] 🧪 测试 API 连接")
    print("  [0] ↩️  返回主菜单")
    print_divider()

def apply_api_preset(preset_key: str) -> None:
    preset = API_PRESETS[preset_key]
    CONFIG.base_url = preset["base_url"]
    CONFIG.model = preset["model"]
    # Avoid leaking keys across presets; start clean and then apply preset-specific keys.
    CONFIG.api_key = ""
    CONFIG.backup_api_key = ""

    # 从环境变量注入预设 Key（不在代码中存储敏感信息）
    if preset_key == "modelscope":
        modelscope_key = os.environ.get("OPEN_AUTOGLM_MODELSCOPE_API_KEY", "").strip()
        modelscope_backup = os.environ.get("OPEN_AUTOGLM_MODELSCOPE_BACKUP_API_KEY", "").strip()
        if modelscope_key:
            CONFIG.api_key = modelscope_key
        if modelscope_backup:
            CONFIG.backup_api_key = modelscope_backup
    elif preset_key == "zhipu":
        zhipu_key = os.environ.get("OPEN_AUTOGLM_ZHIPU_API_KEY", "").strip()
        if zhipu_key:
            CONFIG.api_key = zhipu_key
    elif preset_key == "newapi":
        newapi_key = os.environ.get("OPEN_AUTOGLM_NEWAPI_API_KEY", "").strip()
        if newapi_key:
            CONFIG.api_key = newapi_key
    elif preset_key == "local_openai":
        local_key = os.environ.get("OPEN_AUTOGLM_LOCAL_OPENAI_API_KEY", "").strip()
        if local_key:
            CONFIG.api_key = local_key

    # 允许空 Key 的本地服务
    if preset.get("allow_empty_key", False) and not (CONFIG.api_key or "").strip():
        CONFIG.api_key = ""
        CONFIG.backup_api_key = ""

    CONFIG.use_thirdparty_prompt = preset.get("use_thirdparty_prompt", False)
    CONFIG.thirdparty_thinking = preset.get("thirdparty_thinking", True)
    note = preset.get("note", "")
    print(f"  ✅ 已切换到 {preset['name']}")
    if preset_key == "zhipu" and not (CONFIG.api_key or "").strip():
        print("  ⚠️  未检测到智谱 API Key：请在 .env 设置 OPEN_AUTOGLM_ZHIPU_API_KEY 或在配置设置中手动输入")
    if preset_key == "modelscope" and not (CONFIG.api_key or "").strip():
        print("  ⚠️  未检测到 ModelScope API Key：请在 .env 设置 OPEN_AUTOGLM_MODELSCOPE_API_KEY 或在配置设置中手动输入")
    if preset_key == "newapi" and not (CONFIG.api_key or "").strip():
        print("  ⚠️  未检测到第三方 API Key：请在 .env 设置 OPEN_AUTOGLM_NEWAPI_API_KEY 或在配置设置中手动输入")
    if CONFIG.use_thirdparty_prompt:
        print("  📝 已自动启用第三方模型提示词工程")
    if note:
        print(f"  {note}")

def handle_api_menu():
    """处理模型/API 选择菜单"""
    while True:
        show_api_menu()
        choice = input("  请选择: ").strip().lower()

        if choice == "0":
            break
        if choice == "1":
            apply_api_preset("modelscope")
            input("  按回车键继续...")
        elif choice == "2":
            apply_api_preset("zhipu")
            input("  按回车键继续...")
        elif choice == "3":
            apply_api_preset("newapi")
            input("  按回车键继续...")
        elif choice == "4":
            apply_api_preset("local_openai")
            input("  按回车键继续...")
        elif choice == "t":
            print("\n  🔍 正在测试 API 连接...")
            ok, msg = check_api_connection()
            print(f"  {'✅' if ok else '❌'} {msg}")
            input("  按回车键继续...")
        else:
            print("  ⚠️  无效选择，请重试")
            time.sleep(1)

def show_device_menu():
    """显示设备管理菜单"""
    print_header()
    print_divider("设备管理")

    devices = get_connected_devices()
    if devices:
        print("  已连接设备:")
        for i, d in enumerate(devices, 1):
            model = f" ({d['model']})" if d['model'] else ""
            current = " ← 当前" if d['id'] == CONFIG.device_id else ""
            conn_type = "无线" if ':' in d['id'] else "USB"
            print(f"    [{i}] {d['id']} [{conn_type}]{model}{current}")
    else:
        print("  ⚠️  当前没有已连接的设备")

    print_divider("连接操作")
    print("  [1] 🔗 无线连接 (输入 IP:端口)")
    print("  [2] 🔌 USB 连接引导")
    print("  [3] 📡 USB → 无线 (传统 tcpip 模式)")
    print("  [4] 📱 USB → 无线 (Android 11+ 新版)")
    print_divider("其他操作")
    print("  [5] ❌ 断开设备连接")
    print("  [6] 🔄 重启 ADB 服务")
    print("  [7] 📍 获取设备 IP 地址")
    print("  [8] 📦 安装 ADB Keyboard")
    print("  [9] 🎯 选择目标设备")
    print("  [0] ↩️  返回主菜单")
    print_divider()

def show_config_menu():
    """显示配置菜单"""
    print_header()
    print_divider("当前配置")
    print(f"  [1] API 地址: {CONFIG.base_url}")
    print(f"  [2] 模型名称: {CONFIG.model}")
    print(f"  [3] API Key: {mask_secret(CONFIG.api_key)}")
    print(f"  [4] 备用 Key: {mask_secret(CONFIG.backup_api_key)}")
    print(f"  [5] 目标设备: {CONFIG.device_id or '自动检测'}")
    print(f"  [6] 语言: {'中文' if CONFIG.lang == 'cn' else '英文'}")
    print(f"  [7] 最大步数: {CONFIG.max_steps}")
    thirdparty_status = "✅ 启用" if CONFIG.use_thirdparty_prompt else "❌ 禁用"
    print(f"  [p] 第三方提示词: {thirdparty_status}")
    if CONFIG.use_thirdparty_prompt:
        thinking_status = "✅ 启用" if CONFIG.thirdparty_thinking else "❌ 禁用"
        print(f"  [k] 第三方思考: {thinking_status}")
        compress_status = "✅ 启用" if CONFIG.compress_image else "❌ 禁用"
        print(f"  [i] 截图压缩: {compress_status}")
    print_divider("其他操作")
    print("  [w] 💾 保存配置到文件")
    print("  [r] 🔄 从文件重新加载配置")
    print("  [s] 🔀 切换主/备用 API Key")
    print("  [t] 🧪 测试 API 连接")
    print("  [0] ↩️  返回主菜单")
    print_divider()

def show_help():
    """显示帮助信息"""
    print_header()
    print_divider("使用说明")
    print("""
  📌 快速开始:
     1. 确保手机已开启 USB 调试
     2. 用数据线连接手机到电脑
     3. 手机上点击"允许 USB 调试"
     4. 选择 [1] 启动交互模式

  📌 无线调试:
     1. 手机和电脑连接同一 WiFi
     2. 手机设置 → 开发者选项 → 无线调试
     3. 查看显示的 IP 和端口
     4. 在设备管理中选择无线连接

  📌 任务示例:
     • "打开微信发消息给文件传输助手"
     • "打开设置查看存储空间"
     • "打开淘宝搜索无线耳机"
     • "打开抖音刷3个视频"

  📌 注意事项:
     • 需要安装 ADB Keyboard 才能输入中文
     • 部分敏感页面(支付/密码)无法截图
     • 遇到验证码等需要手动接管
    """)
    input("\n  按回车键返回...")

def run_system_check():
    """运行完整系统检查"""
    print_header()
    print_divider("系统检查")

    all_ok = True

    # 1. ADB
    print("  [1/5] 检查 ADB 安装...", end=" ", flush=True)
    adb_ok, adb_info = check_adb_installed()
    print(f"{'✅' if adb_ok else '❌'} {adb_info}")
    all_ok = all_ok and adb_ok

    # 2. 设备
    print("  [2/5] 检查设备连接...", end=" ", flush=True)
    devices = get_connected_devices()
    if devices:
        print(f"✅ {len(devices)} 台设备")
    else:
        print("❌ 无设备")
        all_ok = False

    # 3. ADB Keyboard
    print("  [3/5] 检查 ADB Keyboard...", end=" ", flush=True)
    if devices:
        kbd_ok = check_adb_keyboard(devices[0]['id'])
        print(f"{'✅ 已安装' if kbd_ok else '❌ 未安装'}")
        all_ok = all_ok and kbd_ok
    else:
        print("⏭️  跳过(无设备)")

    # 4. API
    print("  [4/5] 检查 API 连接...", end=" ", flush=True)
    api_ok, api_info = check_api_connection()
    print(f"{'✅' if api_ok else '❌'} {api_info}")
    all_ok = all_ok and api_ok

    # 5. Python 依赖
    print("  [5/5] 检查 Python 依赖...", end=" ", flush=True)
    try:
        import openai, PIL
        print("✅ 已安装")
    except ImportError as e:
        print(f"❌ 缺少: {e.name}")
        all_ok = False

    print_divider()
    if all_ok:
        print("  ✅ 所有检查通过! 系统已就绪。")
    else:
        print("  ⚠️  部分检查未通过，请根据提示修复。")

    input("\n  按回车键返回...")

# ============== 操作函数 ==============
def run_agent_interactive():
    """启动交互模式"""
    global _SKIP_CLEAR_ONCE
    print("\n  🚀 正在启动 Phone Agent 交互模式...\n")
    cmd = [
        sys.executable, "main.py",
        "--base-url", normalize_openai_base_url(CONFIG.base_url),
        "--model", CONFIG.model,
        "--apikey", effective_api_key(CONFIG.api_key),
        "--lang", CONFIG.lang,
        "--max-steps", str(CONFIG.max_steps)
    ]
    if CONFIG.device_id:
        cmd.extend(["--device-id", CONFIG.device_id])
    if CONFIG.use_thirdparty_prompt:
        cmd.append("--thirdparty")
        cmd.append("--thirdparty-thinking" if CONFIG.thirdparty_thinking else "--thirdparty-no-thinking")
        if not CONFIG.compress_image:
            cmd.append("--no-compress-image")

    if _env_truthy("OPEN_AUTOGLM_DEBUG", default=False):
        sanitized = []
        redact_next = False
        for part in cmd:
            if redact_next:
                sanitized.append("<redacted>")
                redact_next = False
                continue
            if part == "--apikey":
                sanitized.append(part)
                redact_next = True
                continue
            sanitized.append(str(part))
        print(
            "[debug] launch flags: "
            f"thirdparty={CONFIG.use_thirdparty_prompt} "
            f"thirdparty_thinking={CONFIG.thirdparty_thinking} "
            f"compress_image={CONFIG.compress_image}"
        )
        print(f"[debug] cmd: {' '.join(sanitized)}")

    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\n  已中断")
    ans = input("\n  回车返回主菜单(保留输出)，输入 c 清屏后返回: ").strip().lower()
    if ans != "c":
        _SKIP_CLEAR_ONCE = True

def run_single_task():
    """执行单个任务"""
    print_header()
    print_divider("执行任务")
    print("  输入要执行的任务 (输入 q 取消):")
    task = input("  >>> ").strip()

    if task.lower() == 'q' or not task:
        return

    print(f"\n  🚀 正在执行: {task}\n")
    cmd = [
        sys.executable, "main.py",
        "--base-url", normalize_openai_base_url(CONFIG.base_url),
        "--model", CONFIG.model,
        "--apikey", effective_api_key(CONFIG.api_key),
        "--lang", CONFIG.lang,
        "--max-steps", str(CONFIG.max_steps),
        task
    ]
    if CONFIG.device_id:
        cmd.extend(["--device-id", CONFIG.device_id])
    if CONFIG.use_thirdparty_prompt:
        cmd.append("--thirdparty")
        cmd.append("--thirdparty-thinking" if CONFIG.thirdparty_thinking else "--thirdparty-no-thinking")
        if not CONFIG.compress_image:
            cmd.append("--no-compress-image")

    if _env_truthy("OPEN_AUTOGLM_DEBUG", default=False):
        sanitized = []
        redact_next = False
        for part in cmd:
            if redact_next:
                sanitized.append("<redacted>")
                redact_next = False
                continue
            if part == "--apikey":
                sanitized.append(part)
                redact_next = True
                continue
            sanitized.append(str(part))
        print(
            "[debug] launch flags: "
            f"thirdparty={CONFIG.use_thirdparty_prompt} "
            f"thirdparty_thinking={CONFIG.thirdparty_thinking} "
            f"compress_image={CONFIG.compress_image}"
        )
        print(f"[debug] cmd: {' '.join(sanitized)}")

    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\n  已中断")
    input("\n  按回车键返回...")

def handle_device_menu():
    """处理设备管理菜单"""
    while True:
        show_device_menu()
        choice = input("  请选择: ").strip()

        if choice == '0':
            break
        elif choice == '1':
            print("\n  输入设备 IP 和端口 (例如: 192.168.1.100:5555):")
            addr = input("  >>> ").strip()
            if addr:
                parsed, err = parse_host_port(addr, default_port=DEFAULT_ADB_PORT)
                if parsed is None:
                    print(f"  ❌ {err}")
                else:
                    host, port = parsed
                    ok, msg = connect_wireless(host, port)
                    print(f"  {'✅' if ok else '❌'} {msg}")
                    if ok:
                        CONFIG.device_id = f"{host}:{port}"
                input("  按回车键继续...")
        elif choice == '2':
            print("""
  📱 USB 连接步骤:

  1. 在手机上:
     • 设置 → 关于手机 → 连续点击"版本号" 7次
     • 返回设置 → 开发者选项 → 开启 USB 调试
     • 部分手机需同时开启"USB调试(安全设置)"

  2. 用 USB 数据线连接手机和电脑
     • 确保数据线支持数据传输(非仅充电线)

  3. 手机上会弹出"允许USB调试?"
     • 点击"允许"或"确定"

  4. 返回本程序刷新设备列表
            """)
            input("  按回车键继续...")
        elif choice == '3':
            # 传统 tcpip 模式 (Android 10 及更早)
            devices = get_connected_devices()
            usb_devices = [d for d in devices if ':' not in d['id']]
            if not usb_devices:
                print("  ❌ 没有 USB 连接的设备")
            else:
                dev = usb_devices[0]['id']
                ok, msg = enable_tcpip(DEFAULT_ADB_PORT, dev)
                print(f"  {'✅' if ok else '❌'} {msg}")
                if ok:
                    ip = get_device_ip(dev)
                    if ip:
                        print(f"  📍 设备 IP: {ip}")
                        print(f"  💡 现在可以断开 USB，使用无线连接: {ip}:{DEFAULT_ADB_PORT}")
                        print("\n  是否立即连接无线? (y/n)")
                        if input("  >>> ").strip().lower() == 'y':
                            time.sleep(1)
                            ok2, msg2 = connect_wireless(ip, DEFAULT_ADB_PORT)
                            print(f"  {'✅' if ok2 else '❌'} {msg2}")
                            if ok2:
                                CONFIG.device_id = f"{ip}:{DEFAULT_ADB_PORT}"
            input("  按回车键继续...")
        elif choice == '4':
            # Android 11+ 新版无线调试
            devices = get_connected_devices()
            usb_devices = [d for d in devices if ':' not in d['id']]
            if not usb_devices:
                print("  ❌ 没有 USB 连接的设备")
            else:
                dev = usb_devices[0]['id']
                ip = get_device_ip(dev)
                print(f"""
  📱 Android 11+ 新版无线调试

  当前设备 IP: {ip or '未知'}

  请在手机上操作:
  1. 设置 → 开发者选项 → 无线调试
  2. 确保无线调试已开启
  3. 查看显示的 IP 地址和端口号

  端口号每次开启都会变化，请输入当前显示的端口:
                """)
                port = input("  端口号 >>> ").strip()
                if port and ip:
                    port_int, err = parse_port(port)
                    if port_int is None:
                        print(f"  ❌ {err}")
                    else:
                        addr = f"{ip}:{port_int}"
                        ok, msg = connect_wireless(ip, port_int)
                        print(f"  {'✅' if ok else '❌'} {msg}")
                        if ok:
                            CONFIG.device_id = addr
                            print(f"  💡 已切换到无线连接: {addr}")
                elif not ip:
                    print("  ❌ 无法获取设备 IP，请确保手机已连接 WiFi")
            input("  按回车键继续...")
        elif choice == '5':
            print("\n  输入要断开的设备地址 (留空断开所有):")
            addr = input("  >>> ").strip()
            ok, msg = disconnect_device(addr)
            print(f"  {'✅' if ok else '❌'} {msg}")
            if addr == CONFIG.device_id:
                CONFIG.device_id = None
            input("  按回车键继续...")
        elif choice == '6':
            print("  🔄 正在重启 ADB 服务...")
            ok, msg = restart_adb_server()
            print(f"  {'✅' if ok else '❌'} {msg}")
            input("  按回车键继续...")
        elif choice == '7':
            devices = get_connected_devices()
            if devices:
                for d in devices:
                    ip = get_device_ip(d['id'])
                    print(f"  📍 {d['id']}: IP = {ip or '无法获取'}")
            else:
                print("  ❌ 没有连接的设备")
            input("  按回车键继续...")
        elif choice == '8':
            print("\n  📦 正在安装 ADB Keyboard...")
            apk_path = find_adb_keyboard_apk()
            if apk_path is None:
                print("  ❌ 未找到 ADBKeyboard.apk 文件")
                print(f"  💡 将 {ADB_KEYBOARD_APK_NAME} 放到项目根目录，或设置环境变量 {ADB_KEYBOARD_APK_ENV}")
                print("  💡 下载地址: https://github.com/senzhk/ADBKeyBoard/raw/master/ADBKeyboard.apk")
            else:
                dev_arg = ["-s", CONFIG.device_id] if CONFIG.device_id else []
                ok, msg = run_cmd(["adb"] + dev_arg + ["install", str(apk_path)], timeout=60)
                print(f"  {'✅ 安装成功' if ok else '❌ 安装失败'}")
                if ok:
                    run_cmd(["adb"] + dev_arg + ["shell", "ime", "enable", "com.android.adbkeyboard/.AdbIME"])
                    print("  ✅ 已启用 ADB Keyboard")
            input("  按回车键继续...")
        elif choice == '9':
            devices = get_connected_devices()
            if not devices:
                print("  ❌ 没有连接的设备")
            else:
                print("\n  选择目标设备:")
                for i, d in enumerate(devices, 1):
                    current = " ← 当前" if d['id'] == CONFIG.device_id else ""
                    print(f"    [{i}] {d['id']}{current}")
                idx = input("  >>> ").strip()
                if idx.isdigit() and 1 <= int(idx) <= len(devices):
                    CONFIG.device_id = devices[int(idx)-1]['id']
                    print(f"  ✅ 已选择: {CONFIG.device_id}")
            input("  按回车键继续...")

def handle_config_menu():
    """处理配置菜单"""
    while True:
        show_config_menu()
        choice = input("  请选择: ").strip()

        if choice == '0':
            break
        elif choice == '1':
            print(f"\n  当前: {CONFIG.base_url}")
            new_val = input("  新地址: ").strip()
            if new_val:
                CONFIG.base_url = new_val
        elif choice == '2':
            print(f"\n  当前: {CONFIG.model}")
            new_val = input("  新模型: ").strip()
            if new_val:
                CONFIG.model = new_val
        elif choice == '3':
            print(f"\n  当前: {mask_secret(CONFIG.api_key)}")
            new_val = prompt_secret("  新 Key(留空取消): ").strip()
            if new_val:
                CONFIG.api_key = new_val
        elif choice == '4':
            print(f"\n  当前备用 Key: {mask_secret(CONFIG.backup_api_key)}")
            new_val = prompt_secret("  新备用 Key(留空取消): ").strip()
            if new_val:
                CONFIG.backup_api_key = new_val
        elif choice == '5':
            devices = get_connected_devices()
            print("\n  可用设备:")
            for i, d in enumerate(devices):
                print(f"    [{i+1}] {d['id']}")
            print("    [0] 自动检测")
            idx = input("  选择: ").strip()
            if idx == '0':
                CONFIG.device_id = None
            elif idx.isdigit() and 1 <= int(idx) <= len(devices):
                CONFIG.device_id = devices[int(idx)-1]['id']
        elif choice == '6':
            CONFIG.lang = 'en' if CONFIG.lang == 'cn' else 'cn'
            print(f"  ✅ 已切换到: {'中文' if CONFIG.lang == 'cn' else '英文'}")
            input("  按回车键继续...")
        elif choice == '7':
            print(f"\n  当前: {CONFIG.max_steps}")
            new_val = input("  新值: ").strip()
            if new_val.isdigit():
                CONFIG.max_steps = int(new_val)
        elif choice.lower() == 'p':
            # 切换第三方提示词模式
            CONFIG.use_thirdparty_prompt = not CONFIG.use_thirdparty_prompt
            status = "启用" if CONFIG.use_thirdparty_prompt else "禁用"
            print(f"  ✅ 第三方提示词工程已{status}")
            input("  按回车键继续...")
        elif choice.lower() == 'k':
            if not CONFIG.use_thirdparty_prompt:
                print("  ⚠️  仅在启用第三方提示词模式时可设置第三方思考")
            else:
                CONFIG.thirdparty_thinking = not CONFIG.thirdparty_thinking
                status = "启用" if CONFIG.thirdparty_thinking else "禁用"
                print(f"  ✅ 第三方思考已{status}")
                if not CONFIG.thirdparty_thinking:
                    print("  📝 已切换为纯动作输出（更兼容部分中转站）")
            input("  按回车键继续...")
        elif choice.lower() == 'i':
            if not CONFIG.use_thirdparty_prompt:
                print("  ⚠️  仅在启用第三方提示词模式时可设置截图压缩")
            else:
                CONFIG.compress_image = not CONFIG.compress_image
                status = "启用" if CONFIG.compress_image else "禁用"
                print(f"  ✅ 截图压缩已{status}")
            input("  按回车键继续...")
        elif choice.lower() == 's':
            # 切换主/备用 Key
            CONFIG.api_key, CONFIG.backup_api_key = CONFIG.backup_api_key, CONFIG.api_key
            print(f"  ✅ 已切换! 当前 Key: {mask_secret(CONFIG.api_key)}")
            input("  按回车键继续...")
        elif choice.lower() == 'w':
            ok, msg = save_config_to_file()
            print(f"  {'✅' if ok else '❌'} {msg}")
            input("  按回车键继续...")
        elif choice.lower() == 'r':
            ok, msg = load_config_from_file()
            print(f"  {'✅' if ok else '❌'} {msg}")
            input("  按回车键继续...")
        elif choice.lower() == 't':
            print("\n  🔍 正在测试 API 连接...")
            ok, msg = check_api_connection()
            print(f"  {'✅' if ok else '❌'} {msg}")
            input("  按回车键继续...")

# ============== 主函数 ==============
def main():
    """主函数"""
    print("  正在初始化...")

    # 尝试从文件恢复配置（可选）
    load_config_from_file()

    # 自动检测设备
    devices = get_connected_devices()
    if devices:
        CONFIG.device_id = devices[0]['id']

    while True:
        show_status()
        show_main_menu()

        choice = input("  请选择: ").strip()

        if choice == '0':
            print("\n  👋 再见!")
            break
        elif choice == '1':
            run_agent_interactive()
        elif choice == '2':
            run_single_task()
        elif choice == '3':
            handle_device_menu()
        elif choice == '4':
            handle_api_menu()
        elif choice == '5':
            handle_config_menu()
        elif choice == '6':
            run_system_check()
        elif choice == '7':
            show_help()
        else:
            print("  ⚠️  无效选择，请重试")
            time.sleep(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  👋 已退出")
    except Exception as e:
        print(f"\n  ❌ 错误: {e}")
        input("  按回车键退出...")
