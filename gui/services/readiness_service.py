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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, List, Optional, Sequence
from urllib.parse import urlparse

from gui.services.device_service import probe_adb_keyboard_status
from gui.utils.runtime import app_root, is_frozen

Translator = Callable[..., str]


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
    label_key: str = ""
    label_params: dict[str, Any] = field(default_factory=dict)
    detail_key: str = ""
    detail_params: dict[str, Any] = field(default_factory=dict)
    hint_key: str = ""
    hint_params: dict[str, Any] = field(default_factory=dict)


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
    title_key: str = ""
    title_params: dict[str, Any] = field(default_factory=dict)
    detail_key: str = ""
    detail_params: dict[str, Any] = field(default_factory=dict)
    action_hint_key: str = ""
    action_hint_params: dict[str, Any] = field(default_factory=dict)


def _translate_text(
    translator: Translator | None,
    key: str,
    fallback: str,
    params: dict[str, Any] | None = None,
) -> str:
    if not key or not callable(translator):
        return fallback
    try:
        return translator(key, **(params or {}))
    except Exception:
        return fallback


def _join_label_keys(
    label_keys: Sequence[str],
    translator: Translator | None,
) -> str:
    labels: list[str] = []
    for item in label_keys:
        key = item if item.startswith("readiness.") else f"readiness.{item}.label"
        fallback = item.rsplit(".", 1)[-1]
        labels.append(_translate_text(translator, key, fallback))
    return "、".join(labels)


def _prepare_params(
    params: dict[str, Any] | None,
    translator: Translator | None,
) -> dict[str, Any]:
    prepared: dict[str, Any] = {}
    for key, value in (params or {}).items():
        if key == "label_keys" and isinstance(value, (list, tuple)):
            prepared["labels"] = _join_label_keys(value, translator)
        else:
            prepared[key] = value
    return prepared


def render_check_result(
    result: ReadinessCheckResult,
    translator: Translator | None = None,
) -> tuple[str, str, str]:
    """将 ReadinessCheckResult 渲染为当前语言文本。"""
    label_key = result.label_key or f"readiness.{result.key}.label"
    label = _translate_text(
        translator,
        label_key,
        result.label,
        _prepare_params(result.label_params, translator),
    )
    detail = _translate_text(
        translator,
        result.detail_key,
        result.detail,
        _prepare_params(result.detail_params, translator),
    )
    hint = _translate_text(
        translator,
        result.hint_key,
        result.hint,
        _prepare_params(result.hint_params, translator),
    )
    return label, detail, hint


def render_summary(
    summary: ReadinessSummary,
    translator: Translator | None = None,
) -> tuple[str, str, str]:
    """将 ReadinessSummary 渲染为当前语言文本。"""
    title = _translate_text(
        translator,
        summary.title_key,
        summary.title,
        _prepare_params(summary.title_params, translator),
    )
    detail = _translate_text(
        translator,
        summary.detail_key,
        summary.detail,
        _prepare_params(summary.detail_params, translator),
    )
    action_hint = _translate_text(
        translator,
        summary.action_hint_key,
        summary.action_hint,
        _prepare_params(summary.action_hint_params, translator),
    )
    return title, detail, action_hint


def _success(
    key: str,
    label: str,
    detail: str,
    hint: str = "",
    *,
    label_key: str = "",
    label_params: dict[str, Any] | None = None,
    detail_key: str = "",
    detail_params: dict[str, Any] | None = None,
    hint_key: str = "",
    hint_params: dict[str, Any] | None = None,
) -> ReadinessCheckResult:
    return ReadinessCheckResult(
        key=key,
        label=label,
        passed=True,
        detail=detail,
        blocking=True,
        semantic="success",
        hint=hint,
        label_key=label_key,
        label_params=label_params or {},
        detail_key=detail_key,
        detail_params=detail_params or {},
        hint_key=hint_key,
        hint_params=hint_params or {},
    )


def _warning(
    key: str,
    label: str,
    detail: str,
    hint: str = "",
    *,
    blocking: bool = False,
    label_key: str = "",
    label_params: dict[str, Any] | None = None,
    detail_key: str = "",
    detail_params: dict[str, Any] | None = None,
    hint_key: str = "",
    hint_params: dict[str, Any] | None = None,
) -> ReadinessCheckResult:
    return ReadinessCheckResult(
        key=key,
        label=label,
        passed=False,
        detail=detail,
        blocking=blocking,
        semantic="warning" if not blocking else "error",
        hint=hint,
        label_key=label_key,
        label_params=label_params or {},
        detail_key=detail_key,
        detail_params=detail_params or {},
        hint_key=hint_key,
        hint_params=hint_params or {},
    )


def _error(
    key: str,
    label: str,
    detail: str,
    hint: str = "",
    *,
    label_key: str = "",
    label_params: dict[str, Any] | None = None,
    detail_key: str = "",
    detail_params: dict[str, Any] | None = None,
    hint_key: str = "",
    hint_params: dict[str, Any] | None = None,
) -> ReadinessCheckResult:
    return ReadinessCheckResult(
        key=key,
        label=label,
        passed=False,
        detail=detail,
        blocking=True,
        semantic="error",
        hint=hint,
        label_key=label_key,
        label_params=label_params or {},
        detail_key=detail_key,
        detail_params=detail_params or {},
        hint_key=hint_key,
        hint_params=hint_params or {},
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
        return _success(
            "python",
            "Python 版本",
            version_text,
            label_key="readiness.python.label",
            detail_key="readiness.python.detail.ok",
            detail_params={"version": version_text},
        )
    return _error(
        "python",
        "Python 版本",
        f"当前为 {version_text}",
        "请升级到 Python 3.10 或更高版本。",
        label_key="readiness.python.label",
        detail_key="readiness.python.detail.fail_current",
        detail_params={"version": version_text},
        hint_key="readiness.python.hint.upgrade",
    )


def check_pyside6() -> ReadinessCheckResult:
    try:
        import PySide6

        return _success(
            "pyside6",
            "PySide6 安装",
            f"PySide6 {PySide6.__version__}",
            label_key="readiness.pyside6.label",
            detail_key="readiness.pyside6.detail.ok",
            detail_params={"version": PySide6.__version__},
        )
    except ImportError:
        return _error(
            "pyside6",
            "PySide6 安装",
            "PySide6 未安装",
            "请先安装 GUI 依赖。",
            label_key="readiness.pyside6.label",
            detail_key="readiness.pyside6.detail.missing",
            hint_key="readiness.pyside6.hint.install",
        )


def check_openai_package() -> ReadinessCheckResult:
    try:
        import openai

        version = getattr(openai, "__version__", "unknown")
        return _success(
            "openai",
            "openai 包",
            f"openai {version}",
            label_key="readiness.openai.label",
            detail_key="readiness.openai.detail.ok",
            detail_params={"version": version},
        )
    except ImportError:
        return _error(
            "openai",
            "openai 包",
            "openai 包未安装",
            "请先安装 openai 依赖。",
            label_key="readiness.openai.label",
            detail_key="readiness.openai.detail.missing",
            hint_key="readiness.openai.hint.install",
        )


def check_main_py() -> ReadinessCheckResult:
    if is_frozen():
        exe_path = Path(sys.executable).resolve()
        return _success(
            "main_py",
            "任务入口可访问",
            f"单文件任务入口可用: {exe_path}",
            label_key="readiness.main_py.label",
            detail_key="readiness.main_py.detail.ok",
            detail_params={"path": str(exe_path)},
        )

    main_path = app_root() / "main.py"
    if main_path.exists():
        resolved = str(main_path.resolve())
        return _success(
            "main_py",
            "main.py 可访问",
            f"main.py 存在: {resolved}",
            label_key="readiness.main_py.label",
            detail_key="readiness.main_py.detail.ok",
            detail_params={"path": resolved},
        )
    return _error(
        "main_py",
        "main.py 可访问",
        "main.py 不存在，请检查工作目录",
        "请确认 GUI 从项目根目录启动。",
        label_key="readiness.main_py.label",
        detail_key="readiness.main_py.detail.missing",
        hint_key="readiness.main_py.hint.start_from_root",
    )


def check_adb() -> ReadinessCheckResult:
    path = shutil.which("adb")
    if not path:
        return _error(
            "adb",
            "ADB 可用性",
            "ADB 未找到",
            "请安装 Android Platform Tools 并加入 PATH。",
            label_key="readiness.adb.label",
            detail_key="readiness.adb.detail.not_found",
            hint_key="readiness.adb.hint.install",
        )

    try:
        result = _run_subprocess(["adb", "version"], timeout=5)
        if result.returncode == 0:
            version = result.stdout.splitlines()[0] if result.stdout else f"ADB ({path})"
            return _success(
                "adb",
                "ADB 可用性",
                version,
                label_key="readiness.adb.label",
                detail_key="readiness.adb.detail.ok",
                detail_params={"version": version},
            )
        err = result.stderr.strip() or "ADB 运行异常"
        return _error(
            "adb",
            "ADB 可用性",
            err,
            "请确认 adb 可在终端直接执行。",
            label_key="readiness.adb.label",
            detail_key="readiness.adb.detail.runtime_error",
            detail_params={"error": err},
            hint_key="readiness.adb.hint.exec",
        )
    except Exception as exc:
        return _error(
            "adb",
            "ADB 可用性",
            f"ADB 检查失败: {exc}",
            "请确认 adb 已正确安装。",
            label_key="readiness.adb.label",
            detail_key="readiness.adb.detail.check_failed",
            detail_params={"error": str(exc)},
            hint_key="readiness.adb.hint.install",
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
            label_key="readiness.devices.label",
            detail_key="readiness.devices.detail.adb_missing",
            hint_key="readiness.devices.hint.fix_adb",
        )
    except Exception as exc:
        return _error(
            "devices",
            "设备连接",
            str(exc),
            "请在设备页重新刷新或重新连接设备。",
            label_key="readiness.devices.label",
            detail_key="readiness.devices.detail.query_failed",
            detail_params={"error": str(exc)},
            hint_key="readiness.devices.hint.reconnect",
        )

    connected = [current_id for current_id, status in devices if status == "device"]
    pending = [f"{current_id}({status})" for current_id, status in devices if status != "device"]

    target_device = (device_id or "").strip()
    if not target_device and config_service:
        target_device = (config_service.get("OPEN_AUTOGLM_DEVICE_ID") or "").strip()

    if target_device:
        known_status = next((status for current_id, status in devices if current_id == target_device), "")
        if known_status == "device":
            return _success(
                "devices",
                "设备连接",
                f"当前目标设备已连接: {target_device}",
                label_key="readiness.devices.label",
                detail_key="readiness.devices.detail.target_connected",
                detail_params={"device_id": target_device},
            )
        if known_status:
            return _error(
                "devices",
                "设备连接",
                f"当前目标设备未就绪: {target_device} ({known_status})",
                "请在手机上确认调试授权，或在设备页重新连接。",
                label_key="readiness.devices.label",
                detail_key="readiness.devices.detail.target_not_ready",
                detail_params={"device_id": target_device, "status": known_status},
                hint_key="readiness.devices.hint.authorize",
            )
        return _error(
            "devices",
            "设备连接",
            f"当前目标设备未连接: {target_device}",
            "请在设备页重新连接该设备，或重新选择当前设备。",
            label_key="readiness.devices.label",
            detail_key="readiness.devices.detail.target_missing",
            detail_params={"device_id": target_device},
            hint_key="readiness.devices.hint.reconnect",
        )

    if connected:
        return _success(
            "devices",
            "设备连接",
            f"已连接 {len(connected)} 台设备: {', '.join(connected)}",
            label_key="readiness.devices.label",
            detail_key="readiness.devices.detail.connected_count",
            detail_params={"count": len(connected), "devices": ", ".join(connected)},
        )

    if pending:
        return _error(
            "devices",
            "设备连接",
            f"检测到设备但未就绪: {', '.join(pending)}",
            "请在手机上确认调试授权，或在设备页重新连接。",
            label_key="readiness.devices.label",
            detail_key="readiness.devices.detail.pending_only",
            detail_params={"devices": ", ".join(pending)},
            hint_key="readiness.devices.hint.authorize",
        )

    return _error(
        "devices",
        "设备连接",
        "未找到已连接设备",
        "请连接 USB 设备或在设备页完成无线调试连接。",
        label_key="readiness.devices.label",
        detail_key="readiness.devices.detail.none",
        hint_key="readiness.devices.hint.reconnect",
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
            label_key="readiness.adb_keyboard.label",
            detail_key="readiness.adb_keyboard.detail.skipped",
            detail_params={"error": str(exc)},
            hint_key="readiness.adb_keyboard.hint.wait_for_device",
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
                label_key="readiness.adb_keyboard.label",
                detail_key="readiness.adb_keyboard.detail.target_not_ready",
                detail_params={"device_id": target_device, "status": known_status},
                hint_key="readiness.adb_keyboard.hint.connect",
            )
        if not known_status:
            return _warning(
                "adb_keyboard",
                "ADB Keyboard",
                f"当前目标设备未连接: {target_device}",
                "请先在设备页连接该设备后再检查。",
                label_key="readiness.adb_keyboard.label",
                detail_key="readiness.adb_keyboard.detail.target_missing",
                detail_params={"device_id": target_device},
                hint_key="readiness.adb_keyboard.hint.connect",
            )
    elif connected:
        target_device = connected[0]
    else:
        return _warning(
            "adb_keyboard",
            "ADB Keyboard",
            "当前没有已连接设备，暂未检查 ADB Keyboard",
            "连接设备后建议在设备页确认是否已安装并启用。",
            label_key="readiness.adb_keyboard.label",
            detail_key="readiness.adb_keyboard.detail.no_device",
            hint_key="readiness.adb_keyboard.hint.connect",
        )

    try:
        installed, enabled, status = probe_adb_keyboard_status(target_device, timeout=10)
        detail = f"{status} ({target_device})"
        if enabled:
            return _success(
                "adb_keyboard",
                "ADB Keyboard",
                detail,
                label_key="readiness.adb_keyboard.label",
                detail_key="readiness.adb_keyboard.detail.status",
                detail_params={"status": status, "device_id": target_device},
            )
        if installed:
            return _warning(
                "adb_keyboard",
                "ADB Keyboard",
                detail,
                "建议在系统输入法中启用 ADB Keyboard，便于稳定输入文本。",
                label_key="readiness.adb_keyboard.label",
                detail_key="readiness.adb_keyboard.detail.status",
                detail_params={"status": status, "device_id": target_device},
                hint_key="readiness.adb_keyboard.hint.enable",
            )
        return _warning(
            "adb_keyboard",
            "ADB Keyboard",
            detail,
            "建议安装并启用，便于稳定输入文本。",
            label_key="readiness.adb_keyboard.label",
            detail_key="readiness.adb_keyboard.detail.status",
            detail_params={"status": status, "device_id": target_device},
            hint_key="readiness.adb_keyboard.hint.install",
        )
    except Exception as exc:
        return _warning(
            "adb_keyboard",
            "ADB Keyboard",
            f"检查失败: {exc}",
            "可在设备页稍后重试。",
            label_key="readiness.adb_keyboard.label",
            detail_key="readiness.adb_keyboard.detail.check_failed",
            detail_params={"error": str(exc)},
            hint_key="readiness.adb_keyboard.hint.retry",
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
            label_key="readiness.scrcpy.label",
            detail_key="readiness.scrcpy.detail.missing",
            hint_key="readiness.scrcpy.hint.optional_install",
        )

    try:
        result = _run_subprocess([path, "--version"], timeout=5)
        version = result.stdout.strip().splitlines()[0] if result.stdout else "scrcpy"
        return _success(
            "scrcpy",
            "scrcpy 可用性",
            f"{version} ({path})",
            label_key="readiness.scrcpy.label",
            detail_key="readiness.scrcpy.detail.ok",
            detail_params={"version": version, "path": path},
        )
    except Exception:
        return _success(
            "scrcpy",
            "scrcpy 可用性",
            f"scrcpy: {path}",
            label_key="readiness.scrcpy.label",
            detail_key="readiness.scrcpy.detail.ok",
            detail_params={"version": "scrcpy", "path": path},
        )


def check_api_base_url(config_service) -> ReadinessCheckResult:
    if not config_service:
        return _error(
            "api_base_url",
            "API Base URL",
            "配置服务不可用",
            "请重启 GUI 后重试。",
            label_key="readiness.api_base_url.label",
            detail_key="readiness.api_base_url.detail.service_unavailable",
            hint_key="readiness.api_base_url.hint.restart",
        )

    base_url = (config_service.get("OPEN_AUTOGLM_BASE_URL") or "").strip()
    if not base_url:
        return _error(
            "api_base_url",
            "API Base URL",
            "未配置 Base URL",
            "请在设置页选择渠道或填写 Base URL。",
            label_key="readiness.api_base_url.label",
            detail_key="readiness.api_base_url.detail.missing",
            hint_key="readiness.api_base_url.hint.fill",
        )

    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return _error(
            "api_base_url",
            "API Base URL",
            f"Base URL 格式异常: {base_url}",
            "请填写完整的 http(s) 地址。",
            label_key="readiness.api_base_url.label",
            detail_key="readiness.api_base_url.detail.invalid",
            detail_params={"url": base_url},
            hint_key="readiness.api_base_url.hint.fix",
        )

    return _success(
        "api_base_url",
        "API Base URL",
        base_url,
        label_key="readiness.api_base_url.label",
        detail_key="readiness.api_base_url.detail.ok",
        detail_params={"url": base_url},
    )


def check_api_key(config_service) -> ReadinessCheckResult:
    if not config_service:
        return _error(
            "api_key",
            "API Key",
            "配置服务不可用",
            "请重启 GUI 后重试。",
            label_key="readiness.api_key.label",
            detail_key="readiness.api_key.detail.service_unavailable",
            hint_key="readiness.api_key.hint.restart",
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
            label_key="readiness.api_key.label",
            detail_key="readiness.api_key.detail.base_url_missing",
            hint_key="readiness.api_key.hint.configure_channel",
        )

    is_local_channel = "127.0.0.1" in base_url or "localhost" in base_url
    key, source = _infer_effective_api_key(config_service)
    if key:
        return _success(
            "api_key",
            "API Key",
            f"已检测到 API Key（来源: {source}）",
            label_key="readiness.api_key.label",
            detail_key="readiness.api_key.detail.ok",
            detail_params={"source": source},
        )

    if is_local_channel or (active and active.get("id") == "local"):
        return _success(
            "api_key",
            "API Key",
            "本地渠道未配置 API Key（允许为空）",
            label_key="readiness.api_key.label",
            detail_key="readiness.api_key.detail.local_ok",
        )

    channel_name = active.get("name") if active else "当前渠道"
    return _error(
        "api_key",
        "API Key",
        f"{channel_name} 未检测到可用 API Key",
        "请在设置页填写对应渠道的 API Key。",
        label_key="readiness.api_key.label",
        detail_key="readiness.api_key.detail.missing",
        detail_params={"channel": channel_name},
        hint_key="readiness.api_key.hint.fill",
    )


def check_api_reachability(config_service) -> ReadinessCheckResult:
    if not config_service:
        return _warning(
            "api_reachability",
            "API 连通性",
            "配置服务不可用，跳过连通性检查",
            "可稍后在诊断页重新执行完整检查。",
            label_key="readiness.api_reachability.label",
            detail_key="readiness.api_reachability.detail.service_unavailable",
            hint_key="readiness.api_reachability.hint.retry",
        )

    base_url = (config_service.get("OPEN_AUTOGLM_BASE_URL") or "").strip()
    if not base_url:
        return _warning(
            "api_reachability",
            "API 连通性",
            "未配置 Base URL，暂未执行连通性检查",
            "请先在设置页完成 API 配置。",
            label_key="readiness.api_reachability.label",
            detail_key="readiness.api_reachability.detail.base_url_missing",
            hint_key="readiness.api_reachability.hint.configure",
        )

    parsed = urlparse(base_url)
    host = parsed.hostname
    if parsed.scheme not in {"http", "https"} or not host:
        return _warning(
            "api_reachability",
            "API 连通性",
            f"Base URL 格式异常，暂未执行检查: {base_url}",
            "修正 Base URL 后可重新检查。",
            label_key="readiness.api_reachability.label",
            detail_key="readiness.api_reachability.detail.invalid",
            detail_params={"url": base_url},
            hint_key="readiness.api_reachability.hint.fix_url",
        )

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        sock = socket.create_connection((host, port), timeout=5)
        sock.close()
        return _success(
            "api_reachability",
            "API 连通性",
            f"API 端点可达: {host}:{port}",
            label_key="readiness.api_reachability.label",
            detail_key="readiness.api_reachability.detail.ok",
            detail_params={"host": host, "port": port},
        )
    except Exception as exc:
        return _warning(
            "api_reachability",
            "API 连通性",
            f"API 端点暂不可达: {exc}",
            "若刚修改过网络、代理或服务地址，可稍后重试。",
            label_key="readiness.api_reachability.label",
            detail_key="readiness.api_reachability.detail.failed",
            detail_params={"error": str(exc)},
            hint_key="readiness.api_reachability.hint.retry",
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
        blocking_items = [item for item in results if not item.passed and item.blocking][:max_items]
        blocking_labels = [item.label for item in blocking_items]
        blocking_keys = [item.key for item in blocking_items]
        title = f"启动前仍有 {blocking_failed} 个关键项未就绪"
        detail = "关键项：" + "、".join(blocking_labels) if blocking_labels else "关键项尚未就绪"
        action_hint = "建议先查看诊断页，并补齐设备连接、API 配置或依赖项。"
        return ReadinessSummary(
            total=total,
            passed=passed,
            warnings=warnings,
            blocking_failed=blocking_failed,
            semantic=semantic,
            title=title,
            detail=detail,
            action_hint=action_hint,
            title_key="readiness.summary.blocking.title",
            title_params={"count": blocking_failed},
            detail_key="readiness.summary.blocking.detail",
            detail_params={"label_keys": blocking_keys},
            action_hint_key="readiness.summary.blocking.hint",
        )

    if warnings > 0:
        semantic = "warning"
        warning_items = [item for item in results if not item.passed][:max_items]
        warning_labels = [item.label for item in warning_items]
        warning_keys = [item.key for item in warning_items]
        title = f"环境基本就绪，仍有 {warnings} 个建议项可优化"
        detail = "建议关注：" + "、".join(warning_labels) if warning_labels else "仍有建议项可优化"
        action_hint = "可以直接开始任务，也可以进入诊断页查看详情。"
        return ReadinessSummary(
            total=total,
            passed=passed,
            warnings=warnings,
            blocking_failed=blocking_failed,
            semantic=semantic,
            title=title,
            detail=detail,
            action_hint=action_hint,
            title_key="readiness.summary.warning.title",
            title_params={"count": warnings},
            detail_key="readiness.summary.warning.detail",
            detail_params={"label_keys": warning_keys},
            action_hint_key="readiness.summary.warning.hint",
        )

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
        title_key="readiness.summary.success.title",
        detail_key="readiness.summary.success.detail",
        action_hint_key="readiness.summary.success.hint",
    )


def collect_blocking_labels(
    results: Sequence[ReadinessCheckResult],
    max_items: int = 3,
    translator: Translator | None = None,
) -> str:
    """提取关键失败项名称，便于 Dashboard 轻提示使用。"""
    blocking_items = [item for item in results if not item.passed and item.blocking]
    if not blocking_items:
        return ""
    head = blocking_items[:max_items]
    labels = [render_check_result(item, translator)[0] for item in head]
    suffix = "..." if len(blocking_items) > max_items else ""
    return "、".join(labels) + suffix
