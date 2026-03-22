# -*- coding: utf-8 -*-
"""
启动环境检查服务。

为 Dashboard 摘要与 Diagnostics 详情页提供统一的检查逻辑，
避免两处页面重复维护各自的环境检查代码。
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence
from urllib.parse import urlparse

from gui.services.device_service import probe_adb_keyboard_status


@dataclass(frozen=True)
class ReadinessCheckResult:
    """单项环境检查结果。"""

    key: str
    label: str
    passed: bool
    detail: str
    blocking: bool = True
    semantic: str = "success"  # success / warning / error
    hint: str = ""


@dataclass(frozen=True)
class ReadinessSummary:
    """环境检查汇总结果。"""

    total: int
    passed: int
    warnings: int
    blocking_failed: int
    semantic: str
    title: str
    detail: str
    action_hint: str


def _success(key: str, label: str, detail: str, hint: str = "") -> ReadinessCheckResult:
    return ReadinessCheckResult(
        key=key,
        label=label,
        passed=True,
        detail=detail,
        blocking=True,
        semantic="success",
        hint=hint,
    )


def _warning(
    key: str,
    label: str,
    detail: str,
    hint: str = "",
    *,
    blocking: bool = False,
) -> ReadinessCheckResult:
    return ReadinessCheckResult(
        key=key,
        label=label,
        passed=False,
        detail=detail,
        blocking=blocking,
        semantic="warning" if not blocking else "error",
        hint=hint,
    )


def _error(key: str, label: str, detail: str, hint: str = "") -> ReadinessCheckResult:
    return ReadinessCheckResult(
        key=key,
        label=label,
        passed=False,
        detail=detail,
        blocking=True,
        semantic="error",
        hint=hint,
    )


def _run_subprocess(args: List[str], timeout: int = 5) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def _list_adb_devices() -> list[tuple[str, str]]:
    result = _run_subprocess(["adb", "devices"], timeout=10)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "adb devices 执行失败")

    devices: list[tuple[str, str]] = []
    for raw_line in result.stdout.splitlines()[1:]:
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split()
        device_id = parts[0]
        status = parts[1] if len(parts) > 1 else "unknown"
        devices.append((device_id, status))
    return devices


def _infer_effective_api_key(config_service) -> tuple[str, str]:
    """兼容旧调用，统一委托给 ConfigService.resolve_api_key。"""
    if not config_service:
        return "", ""

    resolver = getattr(config_service, "resolve_api_key", None)
    if callable(resolver):
        try:
            return resolver()
        except Exception:
            pass

    general_key = (config_service.get("OPEN_AUTOGLM_API_KEY") or "").strip()
    if general_key:
        return general_key, "OPEN_AUTOGLM_API_KEY"

    return "", ""


def check_python_version() -> ReadinessCheckResult:
    version_text = sys.version.splitlines()[0]
    if sys.version_info >= (3, 10):
        return _success("python", "Python 版本", f"{version_text}")
    return _error(
        "python",
        "Python 版本",
        f"当前为 {version_text}",
        "请升级到 Python 3.10 或更高版本。",
    )


def check_pyside6() -> ReadinessCheckResult:
    try:
        import PySide6

        return _success("pyside6", "PySide6 安装", f"PySide6 {PySide6.__version__}")
    except ImportError:
        return _error(
            "pyside6",
            "PySide6 安装",
            "PySide6 未安装",
            "请先安装 GUI 依赖。",
        )


def check_openai_package() -> ReadinessCheckResult:
    try:
        import openai

        return _success("openai", "openai 包", f"openai {openai.__version__}")
    except ImportError:
        return _error(
            "openai",
            "openai 包",
            "openai 包未安装",
            "请先安装 openai 依赖。",
        )


def check_main_py() -> ReadinessCheckResult:
    main_path = Path("main.py")
    if main_path.exists():
        return _success("main_py", "main.py 可访问", f"main.py 存在: {main_path.resolve()}")
    return _error(
        "main_py",
        "main.py 可访问",
        "main.py 不存在，请检查工作目录",
        "请确认 GUI 从项目根目录启动。",
    )


def check_adb() -> ReadinessCheckResult:
    path = shutil.which("adb")
    if not path:
        return _error(
            "adb",
            "ADB 可用性",
            "ADB 未找到",
            "请安装 Android Platform Tools 并加入 PATH。",
        )

    try:
        result = _run_subprocess(["adb", "version"], timeout=5)
        if result.returncode == 0:
            version = result.stdout.splitlines()[0] if result.stdout else f"ADB ({path})"
            return _success("adb", "ADB 可用性", version)
        return _error(
            "adb",
            "ADB 可用性",
            result.stderr.strip() or "ADB 运行异常",
            "请确认 adb 可在终端直接执行。",
        )
    except Exception as exc:
        return _error(
            "adb",
            "ADB 可用性",
            f"ADB 检查失败: {exc}",
            "请确认 adb 已正确安装。",
        )


def check_devices(config_service=None, device_id: str = "") -> ReadinessCheckResult:
    try:
        devices = _list_adb_devices()
    except FileNotFoundError:
        return _error(
            "devices",
            "设备连接",
            "ADB 未找到，无法检查设备连接",
            "请先修复 ADB 环境。",
        )
    except Exception as exc:
        return _error(
            "devices",
            "设备连接",
            str(exc),
            "请在设备页重新刷新或重新连接设备。",
        )

    connected = [current_id for current_id, status in devices if status == "device"]
    pending = [f"{current_id}({status})" for current_id, status in devices if status != "device"]

    target_device = (device_id or "").strip()
    if not target_device and config_service:
        target_device = (config_service.get("OPEN_AUTOGLM_DEVICE_ID") or "").strip()

    if target_device:
        known_status = next((status for current_id, status in devices if current_id == target_device), "")
        if known_status == "device":
            detail = f"当前目标设备已连接: {target_device}"
            extra = [current_id for current_id in connected if current_id != target_device]
            if extra:
                detail += f"；另有已连接设备: {', '.join(extra)}"
            if pending:
                detail += f"；另有未就绪设备: {', '.join(pending)}"
            return _success("devices", "设备连接", detail)
        if known_status:
            return _error(
                "devices",
                "设备连接",
                f"当前目标设备未就绪: {target_device} ({known_status})",
                "请在手机上确认调试授权，或在设备页重新连接。",
            )
        return _error(
            "devices",
            "设备连接",
            f"当前目标设备未连接: {target_device}",
            "请在设备页重新连接该设备，或重新选择当前设备。",
        )

    if connected:
        detail = f"已连接 {len(connected)} 台设备: {', '.join(connected)}"
        if pending:
            detail += f"；另有未就绪设备: {', '.join(pending)}"
        return _success("devices", "设备连接", detail)

    if pending:
        return _error(
            "devices",
            "设备连接",
            f"检测到设备但未就绪: {', '.join(pending)}",
            "请在手机上确认调试授权，或在设备页重新连接。",
        )

    return _error(
        "devices",
        "设备连接",
        "未找到已连接设备",
        "请连接 USB 设备或在设备页完成无线调试连接。",
    )


def check_adb_keyboard(config_service=None, device_id: str = "") -> ReadinessCheckResult:
    try:
        devices = _list_adb_devices()
    except Exception as exc:
        return _warning(
            "adb_keyboard",
            "ADB Keyboard",
            f"暂未执行检查: {exc}",
            "待 ADB 与设备连接正常后可重新检查。",
        )

    connected = [current_id for current_id, status in devices if status == "device"]
    target_device = (device_id or "").strip()
    if not target_device and config_service:
        target_device = (config_service.get("OPEN_AUTOGLM_DEVICE_ID") or "").strip()

    if target_device:
        known_status = next((status for current_id, status in devices if current_id == target_device), "")
        if known_status and known_status != "device":
            return _warning(
                "adb_keyboard",
                "ADB Keyboard",
                f"当前目标设备未就绪: {target_device} ({known_status})",
                "请先在设备页完成连接或调试授权。",
            )
        if not known_status:
            return _warning(
                "adb_keyboard",
                "ADB Keyboard",
                f"当前目标设备未连接: {target_device}",
                "请先在设备页连接该设备后再检查。",
            )
    elif connected:
        target_device = connected[0]
    else:
        return _warning(
            "adb_keyboard",
            "ADB Keyboard",
            "当前没有已连接设备，暂未检查 ADB Keyboard",
            "连接设备后建议在设备页确认是否已安装并启用。",
        )

    try:
        installed, enabled, status = probe_adb_keyboard_status(target_device, timeout=10)
        detail = f"{status} ({target_device})"
        if enabled:
            return _success("adb_keyboard", "ADB Keyboard", detail)
        hint = "建议安装并启用，便于稳定输入文本。"
        if installed:
            hint = "建议在系统输入法中启用 ADB Keyboard，便于稳定输入文本。"
        return _warning("adb_keyboard", "ADB Keyboard", detail, hint)
    except Exception as exc:
        return _warning(
            "adb_keyboard",
            "ADB Keyboard",
            f"检查失败: {exc}",
            "可在设备页稍后重试。",
        )


def check_scrcpy() -> ReadinessCheckResult:
    from gui.services.mirror_service import MirrorService

    path = MirrorService.find_scrcpy()
    if not path:
        return _warning(
            "scrcpy",
            "scrcpy 可用性",
            "scrcpy 未找到（将降级为 ADB 截图模式）",
            "如需更流畅镜像体验，可选装 scrcpy。",
        )

    try:
        result = _run_subprocess([path, "--version"], timeout=5)
        version = result.stdout.strip().splitlines()[0] if result.stdout else "scrcpy"
        return _success("scrcpy", "scrcpy 可用性", f"{version} ({path})")
    except Exception:
        return _success("scrcpy", "scrcpy 可用性", f"scrcpy: {path}")


def check_api_base_url(config_service) -> ReadinessCheckResult:
    if not config_service:
        return _error(
            "api_base_url",
            "API Base URL",
            "配置服务不可用",
            "请重启 GUI 后重试。",
        )

    base_url = (config_service.get("OPEN_AUTOGLM_BASE_URL") or "").strip()
    if not base_url:
        return _error(
            "api_base_url",
            "API Base URL",
            "未配置 Base URL",
            "请在设置页选择渠道或填写 Base URL。",
        )

    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return _error(
            "api_base_url",
            "API Base URL",
            f"Base URL 格式异常: {base_url}",
            "请填写完整的 http(s) 地址。",
        )

    return _success("api_base_url", "API Base URL", base_url)


def check_api_key(config_service) -> ReadinessCheckResult:
    if not config_service:
        return _error(
            "api_key",
            "API Key",
            "配置服务不可用",
            "请重启 GUI 后重试。",
        )

    base_url = (config_service.get("OPEN_AUTOGLM_BASE_URL") or "").strip().lower()
    active = None
    try:
        active = config_service.get_active_channel()
    except Exception:
        active = None

    if not base_url:
        return _error(
            "api_key",
            "API Key",
            "当前尚未配置 Base URL，无法判断 API Key",
            "请先在设置页完成模型渠道配置。",
        )

    is_local_channel = "127.0.0.1" in base_url or "localhost" in base_url
    key, source = _infer_effective_api_key(config_service)
    if key:
        if is_local_channel:
            return _success("api_key", "API Key", f"已检测到本地渠道 API Key（来源: {source}）")
        return _success("api_key", "API Key", f"已检测到 API Key（来源: {source}）")

    if is_local_channel or (active and active.get("id") == "local"):
        return _success("api_key", "API Key", "本地渠道未配置 API Key（允许为空）")

    channel_name = active.get("name") if active else "当前渠道"
    return _error(
        "api_key",
        "API Key",
        f"{channel_name} 未检测到可用 API Key",
        "请在设置页填写对应渠道的 API Key。",
    )


def check_api_reachability(config_service) -> ReadinessCheckResult:
    if not config_service:
        return _warning(
            "api_reachability",
            "API 连通性",
            "配置服务不可用，跳过连通性检查",
            "可稍后在诊断页重新执行完整检查。",
        )

    base_url = (config_service.get("OPEN_AUTOGLM_BASE_URL") or "").strip()
    if not base_url:
        return _warning(
            "api_reachability",
            "API 连通性",
            "未配置 Base URL，暂未执行连通性检查",
            "请先在设置页完成 API 配置。",
        )

    parsed = urlparse(base_url)
    host = parsed.hostname
    if parsed.scheme not in {"http", "https"} or not host:
        return _warning(
            "api_reachability",
            "API 连通性",
            f"Base URL 格式异常，暂未执行检查: {base_url}",
            "修正 Base URL 后可重新检查。",
        )

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        sock = socket.create_connection((host, port), timeout=5)
        sock.close()
        return _success("api_reachability", "API 连通性", f"API 端点可达: {host}:{port}")
    except Exception as exc:
        return _warning(
            "api_reachability",
            "API 连通性",
            f"API 端点暂不可达: {exc}",
            "若刚修改过网络、代理或服务地址，可稍后重试。",
        )


def run_readiness_checks(
    config_service=None,
    *,
    device_id: str = "",
) -> list[ReadinessCheckResult]:
    """运行完整环境检查。"""
    return [
        check_python_version(),
        check_pyside6(),
        check_openai_package(),
        check_main_py(),
        check_adb(),
        check_devices(config_service, device_id=device_id),
        check_adb_keyboard(config_service, device_id=device_id),
        check_scrcpy(),
        check_api_base_url(config_service),
        check_api_key(config_service),
        check_api_reachability(config_service),
    ]


def summarize_readiness(
    results: Sequence[ReadinessCheckResult],
    *,
    max_items: int = 3,
) -> ReadinessSummary:
    """将多项环境检查结果汇总为首页/诊断页可直接展示的摘要。"""
    total = len(results)
    passed = sum(1 for item in results if item.passed)
    warnings = sum(1 for item in results if not item.passed and not item.blocking)
    blocking_failed = sum(1 for item in results if not item.passed and item.blocking)

    if blocking_failed > 0:
        semantic = "error"
        labels = [item.label for item in results if not item.passed and item.blocking][:max_items]
        title = f"启动前仍有 {blocking_failed} 个关键项未就绪"
        detail = "关键项：" + "、".join(labels) if labels else "关键项尚未就绪"
        action_hint = "建议先查看诊断页，并补齐设备连接、API 配置或依赖项。"
    elif warnings > 0:
        semantic = "warning"
        labels = [item.label for item in results if not item.passed][:max_items]
        title = f"环境基本就绪，仍有 {warnings} 个建议项可优化"
        detail = "建议关注：" + "、".join(labels) if labels else "仍有建议项可优化"
        action_hint = "可以直接开始任务，也可以进入诊断页查看详情。"
    else:
        semantic = "success"
        title = "环境检查通过，可以开始任务"
        detail = "ADB、设备、API 配置与核心依赖均已就绪。"
        action_hint = "如需查看明细，可进入诊断页执行完整检查。"

    return ReadinessSummary(
        total=total,
        passed=passed,
        warnings=warnings,
        blocking_failed=blocking_failed,
        semantic=semantic,
        title=title,
        detail=detail,
        action_hint=action_hint,
    )


def collect_blocking_labels(results: Sequence[ReadinessCheckResult], max_items: int = 3) -> str:
    """提取关键失败项名称，便于 Dashboard 轻提示使用。"""
    labels = [item.label for item in results if not item.passed and item.blocking]
    if not labels:
        return ""
    head = labels[:max_items]
    suffix = " 等" if len(labels) > max_items else ""
    return "、".join(head) + suffix
