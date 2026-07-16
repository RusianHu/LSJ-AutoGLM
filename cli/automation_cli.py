# -*- coding: utf-8 -*-
"""覆盖 TUI/GUI 后端能力的可脚本化命令行入口。"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from cli.automation_state import TERMINAL_STATES, JobStore
from cli.job_control import (
    pause_job,
    refresh_state,
    resume_job,
    start_job,
    start_task,
    stop_job,
    submit_instruction,
    wait_job,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_NOT_FOUND = 3
EXIT_CONFLICT = 4
EXIT_TIMEOUT = 5


class CliUsageError(ValueError):
    pass


class AutomationArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CliUsageError(message)


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "value"):
        return _jsonable(value.value)
    if isinstance(value, Path):
        return str(value)
    return value


def _emit(args: argparse.Namespace, data: Any, *, ok: bool = True, message: str = "") -> int:
    payload = {"ok": ok, "message": message, "data": _jsonable(data)}
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        if message:
            print(message)
        if isinstance(data, str):
            if data:
                print(data)
        else:
            print(json.dumps(_jsonable(data), ensure_ascii=False, indent=2, default=str))
    return EXIT_OK if ok else EXIT_FAILED


def _config(args: argparse.Namespace):
    from gui.services.config_service import ConfigService

    return ConfigService(env_file=Path(_resolved_env_file(args)) if args.env_file else None)


def _resolved_env_file(args: argparse.Namespace) -> str:
    return str(Path(args.env_file).expanduser().resolve()) if args.env_file else ""


def _store(args: argparse.Namespace) -> JobStore:
    return JobStore(args.state_dir or None)


def _mask_config(config, values: dict[str, str], show_secrets: bool = False) -> dict[str, str]:
    if show_secrets:
        return values
    return {
        key: (config.get_masked(key) if key in config.SENSITIVE_KEYS else value)
        for key, value in values.items()
    }


def _history_path(store: JobStore) -> Path:
    return store.root.parent / "index.json"


def _load_history(store: JobStore) -> list[dict[str, Any]]:
    path = _history_path(store)
    if not path.exists():
        return []
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, list) else []


def _save_history_unlocked(store: JobStore, records: list[dict[str, Any]]) -> None:
    JobStore._atomic_write(_history_path(store), records)


def _find_scrcpy() -> str:
    found = shutil.which("scrcpy")
    candidates = [
        Path(found) if found else None,
        PROJECT_ROOT / "scrcpy" / "scrcpy.exe",
        PROJECT_ROOT / "tools" / "scrcpy" / "scrcpy.exe",
        Path("C:/scrcpy/scrcpy.exe"),
        Path("C:/Program Files/scrcpy/scrcpy.exe"),
    ]
    for candidate in candidates:
        if candidate and candidate.exists():
            return str(candidate.resolve())
    return ""


def _adb(args: argparse.Namespace):
    from gui.services.adb_client import AdbClient
    from gui.utils.runtime import find_adb_executable

    path = find_adb_executable()
    return AdbClient(str(path) if path else "adb")


def _job_public(state: dict[str, Any]) -> dict[str, Any]:
    blocked = {"inbox_path"}
    return {key: value for key, value in state.items() if key not in blocked}


def _handle_capabilities(args: argparse.Namespace) -> int:
    matrix = {
        "schema_version": 1,
        "contract": {
            "default_output": "json",
            "non_blocking": "task start、diagnostics start、mirror start、config test-api、device *-start、build gui 默认立即返回 job_id",
            "exit_codes": {"0": "成功", "1": "执行失败", "2": "参数错误", "3": "不存在", "4": "状态冲突", "5": "超时"},
        },
        "surfaces": {
            "TUI/Agent": ["status", "task start/run/status/list/logs/wait/pause/resume/stop/instruct/takeover", "apps supported/device/find"],
            "GUI/设置": ["config list/get/set/unset/validate", "config channels/use-channel", "config action-policy", "config mirror-toolbar"],
            "GUI/设备": ["device list/select/connect/disconnect/pair/mdns/tcpip/usb/ip", "device keyboard-status/install-keyboard", "device adb-status/scrcpy-status"],
            "GUI/诊断": ["diagnostics start/run/status/result"],
            "GUI/历史": ["history list/show/logs/delete/clear"],
            "GUI/镜像": ["mirror start/status/stop/restart/check/action/paste/screenshot"],
            "GUI/构建": ["build gui/status/logs/stop", "paths"],
        },
    }
    return _emit(args, matrix, message="CLI 能力清单")


def _handle_status(args: argparse.Namespace) -> int:
    config = _config(args)
    store = _store(args)
    active_channel = config.get_active_channel() or {}
    data: dict[str, Any] = {
        "ready_config": not bool(config.validate_details()),
        "env_file": config.env_path,
        "channel": active_channel.get("id", "custom"),
        "base_url": config.get("OPEN_AUTOGLM_BASE_URL"),
        "model": config.get("OPEN_AUTOGLM_MODEL"),
        "device_type": config.get("OPEN_AUTOGLM_DEVICE_TYPE", "adb"),
        "device_id": config.get("OPEN_AUTOGLM_DEVICE_ID", ""),
        "language": config.get("OPEN_AUTOGLM_LANG", "cn"),
        "max_steps": config.get("OPEN_AUTOGLM_MAX_STEPS", "100"),
        "compress_image": config._is_truthy(config.get("OPEN_AUTOGLM_COMPRESS_IMAGE", "false")),
        "active_jobs": [_job_public(item) for item in store.list(limit=100) if item.get("state") not in TERMINAL_STATES],
    }
    if args.probe_devices:
        try:
            data["devices"] = _device_records(_adb(args).devices(long=True))
            data["adb_available"] = True
        except Exception as exc:
            data["devices"] = []
            data["adb_available"] = False
            data["adb_error"] = str(exc)
    return _emit(args, data)


def _handle_config(args: argparse.Namespace) -> int:
    config = _config(args)
    if args.config_command == "list":
        values = _mask_config(config, config.get_all(), args.show_secrets)
        return _emit(args, {"env_file": config.env_path, "values": values})
    if args.config_command == "get":
        if args.key not in config.get_all() and args.key not in config.DEFAULTS:
            return _emit(args, {}, ok=False, message=f"未知配置项：{args.key}")
        value = config.get(args.key, "") if args.show_secrets else config.get_masked(args.key)
        return _emit(args, {"key": args.key, "value": value})
    if args.config_command in {"set", "unset"}:
        if args.key not in config.DEFAULTS and args.key not in config.get_all() and not args.allow_unknown:
            return _emit(args, {}, ok=False, message=f"未知配置项：{args.key}；如确需写入请使用 --allow-unknown")
        value = "" if args.config_command == "unset" else args.value
        errors = config.validate_details({args.key: value}) if args.validate else []
        if errors:
            rendered = [config.render_validation_error(item, config.get("OPEN_AUTOGLM_LANG", "cn")) for item in errors]
            return _emit(args, {"errors": errors, "rendered": rendered}, ok=False, message="配置校验失败")
        config.set(args.key, value)
        shown = config.get_masked(args.key) if args.key in config.SENSITIVE_KEYS else value
        return _emit(args, {"key": args.key, "value": shown, "env_file": config.env_path}, message="配置已保存")
    if args.config_command == "set-many":
        try:
            updates = json.loads(Path(args.file).read_text(encoding="utf-8")) if args.file else json.loads(args.values)
        except (OSError, json.JSONDecodeError) as exc:
            return _emit(args, {}, ok=False, message=f"无法解析配置对象：{exc}")
        if not isinstance(updates, dict) or not all(isinstance(key, str) for key in updates):
            return _emit(args, {}, ok=False, message="批量配置必须是 JSON 对象")
        updates = {key: str(value) for key, value in updates.items()}
        unknown = [key for key in updates if key not in config.DEFAULTS and key not in config.get_all()]
        if unknown and not args.allow_unknown:
            return _emit(args, {"unknown": unknown}, ok=False, message="批量配置包含未知字段")
        errors = config.validate_details(updates) if args.validate else []
        if errors:
            return _emit(args, {"errors": errors}, ok=False, message="配置校验失败")
        config.set_many(updates)
        return _emit(args, {"updated": list(updates), "env_file": config.env_path}, message="配置已原子批量保存")
    if args.config_command == "validate":
        details = config.validate_details()
        lang = args.lang or config.get("OPEN_AUTOGLM_LANG", "cn")
        rendered = [config.render_validation_error(item, lang) for item in details]
        return _emit(args, {"valid": not details, "errors": details, "rendered": rendered}, ok=not details, message="配置有效" if not details else "配置无效")
    if args.config_command == "channels":
        active = config.get_active_channel() or {}
        channels = []
        for preset in config.CHANNEL_PRESETS:
            channels.append({
                "id": preset["id"],
                "name": preset["name"],
                "base_url": config.get_preset_url(preset),
                "model": config.get_preset_model(preset),
                "active": preset["id"] == active.get("id"),
            })
        return _emit(args, channels)
    if args.config_command == "use-channel":
        if not config.set_active_channel(args.channel):
            return _emit(args, {}, ok=False, message=f"渠道不存在：{args.channel}")
        active = config.get_active_channel() or {}
        return _emit(args, {"active_channel": active.get("id"), "base_url": config.get("OPEN_AUTOGLM_BASE_URL"), "model": config.get("OPEN_AUTOGLM_MODEL")}, message="渠道已切换")
    if args.config_command == "action-policy":
        from phone_agent.actions.registry import get_supported_action_names
        updates = {}
        if args.reset:
            updates = {"OPEN_AUTOGLM_USE_PLATFORM_DEFAULT_ACTIONS": "true", "OPEN_AUTOGLM_ENABLED_ACTIONS": "", "OPEN_AUTOGLM_AI_VISIBLE_ACTIONS": ""}
        elif args.select_all:
            runtime = list(get_supported_action_names(args.platform))
            visible = list(runtime)
            updates = {"OPEN_AUTOGLM_USE_PLATFORM_DEFAULT_ACTIONS": "false", "OPEN_AUTOGLM_ENABLED_ACTIONS": json.dumps(runtime), "OPEN_AUTOGLM_AI_VISIBLE_ACTIONS": json.dumps(visible)}
        elif args.clear:
            updates = {"OPEN_AUTOGLM_USE_PLATFORM_DEFAULT_ACTIONS": "false", "OPEN_AUTOGLM_ENABLED_ACTIONS": "[]", "OPEN_AUTOGLM_AI_VISIBLE_ACTIONS": "[]"}
        else:
            if args.enabled is not None: updates["OPEN_AUTOGLM_ENABLED_ACTIONS"] = args.enabled
            if args.ai_visible is not None: updates["OPEN_AUTOGLM_AI_VISIBLE_ACTIONS"] = args.ai_visible
            if args.platform_defaults is not None: updates["OPEN_AUTOGLM_USE_PLATFORM_DEFAULT_ACTIONS"] = args.platform_defaults
        if updates:
            errors = config.validate_details(updates)
            if errors:
                return _emit(args, {"errors": errors}, ok=False, message="动作策略校验失败")
            config.set_many(updates)
        return _emit(args, config.get_action_policy_settings(), message="动作策略已保存" if updates else "")
    if args.config_command == "mirror-toolbar":
        from gui.services.mirror_actions import MIRROR_TOOLBAR_ACTION_NAMES, serialize_mirror_toolbar_actions
        updates = {}
        if args.enabled is not None:
            updates["OPEN_AUTOGLM_GUI_MIRROR_TOOLBAR"] = args.enabled
        if args.select_all:
            updates["OPEN_AUTOGLM_GUI_MIRROR_TOOLBAR_ACTIONS"] = serialize_mirror_toolbar_actions(MIRROR_TOOLBAR_ACTION_NAMES)
        elif args.clear:
            updates["OPEN_AUTOGLM_GUI_MIRROR_TOOLBAR_ACTIONS"] = "[]"
        elif args.actions is not None:
            updates["OPEN_AUTOGLM_GUI_MIRROR_TOOLBAR_ACTIONS"] = serialize_mirror_toolbar_actions(json.loads(args.actions))
        if updates:
            config.set_many(updates)
        return _emit(args, config.get_mirror_toolbar_settings(), message="镜像工具栏配置已保存" if updates else "")
    if args.config_command == "swap-keys":
        primary = config.get("OPEN_AUTOGLM_API_KEY", "")
        backup = config.get("OPEN_AUTOGLM_BACKUP_API_KEY", "")
        config.set_many({"OPEN_AUTOGLM_API_KEY": backup, "OPEN_AUTOGLM_BACKUP_API_KEY": primary})
        return _emit(args, {"primary": config.get_masked("OPEN_AUTOGLM_API_KEY"), "backup": config.get_masked("OPEN_AUTOGLM_BACKUP_API_KEY")}, message="主备 API Key 已互换")
    if args.config_command == "reload":
        config.load()
        return _emit(args, {"env_file": config.env_path, "values": _mask_config(config, config.get_all())}, message="配置已重新加载")
    if args.config_command == "test-api":
        store = _store(args)
        state = start_job(store, "api_check", {"env_file": _resolved_env_file(args)}, public={"base_url": config.get("OPEN_AUTOGLM_BASE_URL"), "model": config.get("OPEN_AUTOGLM_MODEL")}, cwd=PROJECT_ROOT)
        return _emit(args, _job_public(state), ok=state.get("state") != "failed", message="API 实连测试已在后台启动")
    if args.config_command in {"api-status", "api-result"}:
        store = _store(args)
        state = refresh_state(store, args.job_id)
        if state.get("kind") != "api_check":
            return _emit(args, {}, ok=False, message="指定作业不是 API 测试")
        data = _job_public(state)
        if args.config_command == "api-result":
            data = {"job": data, "result": state.get("result"), "log": store.tail(args.job_id, args.lines)}
        return _emit(args, data, ok=state.get("state") != "failed")
    return EXIT_USAGE


def _handle_task(args: argparse.Namespace) -> int:
    store = _store(args)
    cmd = args.task_command
    if cmd == "start":
        state = start_task(store, args.text, env_file=_resolved_env_file(args), device_id=args.device_id, stuck_timeout=args.stuck_timeout, cwd=PROJECT_ROOT)
        return _emit(args, _job_public(state), ok=state.get("state") != "failed", message="任务已在后台启动")
    if cmd == "run":
        state = start_task(store, args.text, env_file=_resolved_env_file(args), device_id=args.device_id, stuck_timeout=args.stuck_timeout, cwd=PROJECT_ROOT)
        if state.get("state") == "failed":
            return _emit(args, _job_public(state), ok=False, message="任务启动失败")
        state = wait_job(store, state["job_id"], timeout=args.wait_timeout)
        result = {"job": _job_public(state), "log": store.tail(state["job_id"], args.lines)}
        return _emit(args, result, ok=state.get("state") == "completed", message=f"任务已结束：{state.get('state')}")
    if cmd == "list":
        return _emit(args, [_job_public(item) for item in store.list("task", args.limit)])
    if cmd == "status":
        return _emit(args, _job_public(refresh_state(store, args.job_id)))
    if cmd == "logs":
        state = refresh_state(store, args.job_id)
        return _emit(args, {"job": _job_public(state), "log": store.tail(args.job_id, args.lines)})
    if cmd == "pause":
        return _emit(args, _job_public(pause_job(store, args.job_id)), message="任务已暂停")
    if cmd == "resume":
        return _emit(args, _job_public(resume_job(store, args.job_id)), message="任务已恢复")
    if cmd == "stop":
        return _emit(args, _job_public(stop_job(store, args.job_id, args.stop_timeout)), message="已请求停止任务")
    if cmd == "instruct":
        entry = submit_instruction(store, args.job_id, args.text)
        return _emit(args, entry, message="追加指令已写入任务 inbox")
    if cmd == "takeover":
        state = pause_job(store, args.job_id)
        state = store.update(args.job_id, takeover=True, takeover_reason=args.reason)
        return _emit(args, _job_public(state), message="任务已暂停并进入人工接管")
    if cmd == "wait":
        state = wait_job(store, args.job_id, timeout=args.wait_timeout)
        return _emit(args, _job_public(state), ok=state.get("state") == "completed")
    return EXIT_USAGE


def _handle_jobs(args: argparse.Namespace) -> int:
    store = _store(args)
    if args.jobs_command == "list":
        return _emit(args, [_job_public(item) for item in store.list(args.kind, args.limit)])
    if args.jobs_command == "status":
        return _emit(args, _job_public(refresh_state(store, args.job_id)))
    if args.jobs_command == "logs":
        return _emit(args, {"job": _job_public(refresh_state(store, args.job_id)), "log": store.tail(args.job_id, args.lines)})
    if args.jobs_command == "stop":
        return _emit(args, _job_public(stop_job(store, args.job_id, args.stop_timeout)))
    return EXIT_USAGE


def _handle_diagnostics(args: argparse.Namespace) -> int:
    store = _store(args)
    cmd = args.diagnostics_command
    if cmd in {"start", "run"}:
        state = start_job(store, "diagnostics", {"env_file": _resolved_env_file(args), "device_id": args.device_id}, public={"device_id": args.device_id}, cwd=PROJECT_ROOT)
        if cmd == "run" and state.get("state") != "failed":
            state = wait_job(store, state["job_id"], timeout=args.wait_timeout)
        return _emit(args, _job_public(state), ok=state.get("state") not in {"failed"}, message="诊断已启动" if cmd == "start" else "诊断已结束")
    state = refresh_state(store, args.job_id)
    if cmd == "status":
        return _emit(args, _job_public(state))
    if cmd == "result":
        return _emit(args, {"job": _job_public(state), "result": state.get("result"), "log": store.tail(args.job_id, args.lines)}, ok=state.get("state") != "failed")
    return EXIT_USAGE


def _device_records(records) -> list[dict[str, Any]]:
    return [_jsonable(item) for item in records]


def _handle_device(args: argparse.Namespace) -> int:
    from gui.services.adb_client import build_pairing_qr_payload, generate_qr_credentials
    from gui.services.device_service import probe_adb_keyboard_status
    from gui.utils.runtime import find_adb_keyboard_apk

    adb = _adb(args)
    cmd = args.device_command
    async_operations = {
        "connect-start": ("connect", {"endpoint": getattr(args, "endpoint", "")}),
        "disconnect-start": ("disconnect", {"endpoint": "" if getattr(args, "endpoint", "all") == "all" else args.endpoint}),
        "pair-start": ("pair", {"endpoint": getattr(args, "endpoint", ""), "code": getattr(args, "code", ""), "connect_timeout": getattr(args, "connect_timeout", 15)}),
        "tcpip-start": ("tcpip", {"device_id": getattr(args, "device_id", ""), "port": getattr(args, "port", 5555), "connect_timeout": getattr(args, "connect_timeout", 12)}),
        "usb-start": ("usb", {"device_id": getattr(args, "device_id", "")}),
        "install-keyboard-start": ("install_keyboard", {"device_id": getattr(args, "device_id", "")}),
    }
    if cmd in async_operations:
        operation, values = async_operations[cmd]
        state = start_job(
            _store(args),
            "device_operation",
            {"operation": operation, **values},
            public={"operation": operation, **{k: v for k, v in values.items() if k != "code"}},
            cwd=PROJECT_ROOT,
        )
        return _emit(args, _job_public(state), ok=state.get("state") != "failed", message="设备操作已在后台启动")
    if cmd == "list":
        if args.platform == "ios":
            from phone_agent.xctest import list_devices
            return _emit(args, _device_records(list_devices()))
        if args.platform == "hdc":
            from phone_agent.device_factory import DeviceType, get_device_factory, set_device_type
            set_device_type(DeviceType.HDC)
            return _emit(args, _device_records(get_device_factory().list_devices()))
        return _emit(args, _device_records(adb.devices(long=True)))
    if cmd == "select":
        config = _config(args)
        config.set("OPEN_AUTOGLM_DEVICE_ID", args.device_id)
        return _emit(args, {"device_id": args.device_id}, message="目标设备已保存")
    if cmd == "connect":
        ok, message = adb.connect(args.endpoint)
        return _emit(args, {"endpoint": args.endpoint}, ok=ok, message=message)
    if cmd == "disconnect":
        ok, message = adb.disconnect("" if args.endpoint == "all" else args.endpoint)
        return _emit(args, {"endpoint": args.endpoint}, ok=ok, message=message)
    if cmd == "pair":
        result = adb.pair_and_connect(args.endpoint, args.code, connect_timeout=args.connect_timeout)
        return _emit(args, result, ok=result.paired, message=result.message)
    if cmd == "mdns":
        return _emit(args, _device_records(adb.mdns_services()))
    if cmd == "qr":
        service, password = generate_qr_credentials()
        payload = build_pairing_qr_payload(service, password)
        output = ""
        if args.output:
            import qrcode
            output_path = Path(args.output).expanduser().resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            qrcode.make(payload).save(output_path)
            output = str(output_path)
        return _emit(args, {"service_name": service, "password": password, "payload": payload, "qr_image": output}, message="二维码配对凭据已生成")
    if cmd == "qr-start":
        store = _store(args)
        state = start_job(
            store,
            "device_qr_pair",
            {"service_name": args.service_name, "password": args.password, "timeout": args.pair_timeout},
            public={"service_name": args.service_name},
            cwd=PROJECT_ROOT,
        )
        return _emit(args, _job_public(state), ok=state.get("state") != "failed", message="二维码配对等待已在后台启动")
    if cmd == "restart-adb":
        adb.run(["kill-server"], timeout=10)
        result = adb.start_server()
        return _emit(args, {"output": result.merged_output}, ok=result.returncode == 0, message=result.merged_output)
    if cmd in {"ios-pair", "wda-status"}:
        from phone_agent.xctest import XCTestConnection
        connection = XCTestConnection(wda_url=args.wda_url)
        if cmd == "ios-pair":
            ok, message = connection.pair_device(args.device_id or None)
            return _emit(args, {"device_id": args.device_id}, ok=ok, message=message)
        ready = connection.is_wda_ready()
        return _emit(args, {"ready": ready, "wda_url": args.wda_url, "status": connection.get_wda_status() if ready else None}, ok=ready, message="WebDriverAgent 已就绪" if ready else "WebDriverAgent 未就绪")
    if cmd == "tcpip":
        result = adb.enable_tcpip(args.device_id, args.port, connect_timeout=args.connect_timeout)
        return _emit(args, result, ok=result.success, message=result.message)
    if cmd == "usb":
        ok, message = adb.use_usb(args.device_id)
        return _emit(args, {"device_id": args.device_id}, ok=ok, message=message)
    if cmd == "ip":
        address = adb.get_wlan_ipv4(args.device_id)
        return _emit(args, {"device_id": args.device_id, "ip": address}, ok=bool(address), message="" if address else "无法读取 WLAN IPv4")
    if cmd == "adb-status":
        result = adb.run(["version"], timeout=5)
        return _emit(
            args,
            {
                "command": list(result.args),
                "version": result.merged_output,
                "server": adb.server_status(),
            },
            ok=result.returncode == 0,
        )
    if cmd == "scrcpy-status":
        path = _find_scrcpy()
        if not path:
            return _emit(args, {"available": False}, ok=False, message="scrcpy 未找到")
        result = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
        return _emit(args, {"available": True, "path": path, "version": (result.stdout or result.stderr).strip()}, ok=result.returncode == 0)
    if cmd == "keyboard-status":
        installed, enabled, status = probe_adb_keyboard_status(args.device_id, timeout=10)
        return _emit(args, {"installed": installed, "enabled": enabled, "status": status}, ok=enabled, message=status)
    if cmd == "install-keyboard":
        apk = find_adb_keyboard_apk()
        if not apk:
            return _emit(args, {}, ok=False, message="未找到 ADBKeyboard.apk")
        result = adb.run(["install", "-r", str(apk)], timeout=60, serial=args.device_id)
        if result.returncode == 0:
            adb.run(["shell", "ime", "enable", "com.android.adbkeyboard/.AdbIME"], timeout=15, serial=args.device_id)
        return _emit(args, {"apk": str(apk), "output": result.merged_output}, ok=result.returncode == 0, message=result.merged_output)
    return EXIT_USAGE


def _mirror_job(store: JobStore, job_id: str = "") -> dict[str, Any]:
    if job_id:
        state = refresh_state(store, job_id)
        if state.get("kind") not in {"mirror", "mirror_adb"}:
            raise RuntimeError("指定作业不是镜像作业")
        return state
    jobs = [*store.list("mirror", 20), *store.list("mirror_adb", 20)]
    jobs.sort(key=lambda item: float(item.get("created_at") or 0), reverse=True)
    active = [item for item in jobs if item.get("state") not in TERMINAL_STATES]
    if not active:
        raise KeyError("当前没有活动镜像作业")
    return refresh_state(store, active[0]["job_id"])


def _scrcpy_shortcut(pid: int, key: str) -> tuple[bool, str]:
    if os.name != "nt":
        return False, "scrcpy 快捷键控制目前仅支持 Windows"
    import ctypes
    from ctypes import wintypes

    found = []
    user32 = ctypes.windll.user32
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback_type
    def callback(hwnd, _lparam):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == int(pid) and user32.IsWindowVisible(hwnd):
            found.append(int(hwnd))
            return False
        return True

    user32.EnumWindows(callback, 0)
    if not found:
        return False, "scrcpy 窗口尚未就绪"
    hwnd = found[0]
    vk = ord(key.upper())
    user32.ShowWindow(hwnd, 9)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.08)
    user32.keybd_event(0x11, 0, 0, 0)
    user32.keybd_event(vk, 0, 0, 0)
    user32.keybd_event(vk, 0, 0x0002, 0)
    user32.keybd_event(0x11, 0, 0x0002, 0)
    return True, "快捷键已发送"


def _handle_mirror(args: argparse.Namespace) -> int:
    store = _store(args)
    cmd = args.mirror_command
    if cmd == "check":
        path = _find_scrcpy()
        return _emit(args, {"available": bool(path), "path": path}, ok=bool(path), message="scrcpy 可用" if path else "scrcpy 未找到")
    if cmd == "start":
        path = _find_scrcpy()
        if args.mode == "scrcpy" and not path:
            return _emit(args, {}, ok=False, message="scrcpy 未找到；CLI 镜像需要独立 scrcpy 窗口")
        try:
            current = _mirror_job(store)
            return _emit(args, _job_public(current), ok=False, message="已有镜像正在运行")
        except KeyError:
            pass
        if args.mode == "adb" or (args.mode == "auto" and not path):
            frame = store.root.parent / "screenshots" / f"mirror_{args.device_id.replace(':', '_')}.png"
            state = start_job(
                store,
                "mirror_adb",
                {"device_id": args.device_id, "interval": args.interval, "frame_path": str(frame)},
                public={"device_id": args.device_id, "mode": "adb_screenshot", "latest_frame": str(frame)},
                cwd=PROJECT_ROOT,
            )
            return _emit(args, _job_public(state), ok=state.get("state") != "failed", message="ADB 截图降级镜像已在后台启动")
        title = f"AutoGLM Mirror - {args.device_id}"
        command = [path, "--serial", args.device_id, "--window-title", title, "--stay-awake", "--keyboard=sdk", "--mouse=sdk", "--prefer-text", "--shortcut-mod", "lctrl,rctrl"]
        if os.name == "nt":
            command += ["--window-x", "120", "--window-y", "120"]
        state = start_job(store, "mirror", {"command": command, "cwd": str(PROJECT_ROOT)}, public={"device_id": args.device_id, "window_title": title}, cwd=PROJECT_ROOT)
        return _emit(args, _job_public(state), ok=state.get("state") != "failed", message="镜像已在独立后台作业中启动")
    if cmd == "status":
        return _emit(args, _job_public(_mirror_job(store, args.job_id)))
    if cmd == "stop":
        state = _mirror_job(store, args.job_id)
        return _emit(args, _job_public(stop_job(store, state["job_id"], args.stop_timeout)), message="镜像已停止")
    if cmd == "restart":
        old = _mirror_job(store, args.job_id)
        device_id = old.get("device_id", "")
        stop_job(store, old["job_id"], args.stop_timeout)
        args.device_id = device_id
        args.mirror_command = "start"
        args.mode = "auto"
        args.interval = 1.5
        return _handle_mirror(args)
    state = _mirror_job(store, args.job_id)
    device_id = args.device_id or state.get("device_id", "")
    if cmd in {"paste", "action"} and (cmd == "paste" or args.action in {"fullscreen", "clipboard"}):
        if state.get("kind") != "mirror":
            return _emit(args, {}, ok=False, message="该动作需要 scrcpy 原生控制通道")
        shortcut = "V" if cmd == "paste" else ("F" if args.action == "fullscreen" else "C")
        ok, message = _scrcpy_shortcut(int(state.get("process_pid") or 0), shortcut)
        return _emit(args, {"action": cmd if cmd == "paste" else args.action}, ok=ok, message=message)
    adb = _adb(args)
    if cmd == "screenshot" or (cmd == "action" and args.action == "screenshot"):
        output = Path(args.output or (store.root.parent / "screenshots" / f"screenshot_{time.strftime('%Y%m%d_%H%M%S')}.png")).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        # AdbClient 是文本接口，不适合 PNG；用其解析出的 adb 路径执行二进制命令。
        binary = subprocess.run([adb.adb_path, "-s", device_id, "exec-out", "screencap", "-p"], capture_output=True, timeout=15)
        if binary.returncode == 0 and binary.stdout:
            output.write_bytes(binary.stdout)
        return _emit(args, {"path": str(output)}, ok=output.exists(), message="截图已保存" if output.exists() else "截图失败")
    action = args.action
    if action == "notifications":
        command = ["shell", "cmd", "statusbar", "expand-notifications"]
    elif action == "touch":
        command = ["shell", "settings", "put", "system", "show_touches", args.touch]
    else:
        keyevents = {"menu": "KEYCODE_MENU", "home": "KEYCODE_HOME", "back": "KEYCODE_BACK", "app_switch": "KEYCODE_APP_SWITCH", "power": "KEYCODE_POWER", "volume_up": "KEYCODE_VOLUME_UP", "volume_down": "KEYCODE_VOLUME_DOWN", "screen_on": "KEYCODE_WAKEUP", "screen_off": "KEYCODE_SLEEP"}
        if action not in keyevents:
            return _emit(args, {}, ok=False, message=f"不支持的镜像动作：{action}")
        command = ["shell", "input", "keyevent", keyevents[action]]
    result = adb.run(command, timeout=8, serial=device_id)
    return _emit(args, {"action": action, "output": result.merged_output}, ok=result.returncode == 0, message=result.merged_output)


def _handle_history(args: argparse.Namespace) -> int:
    store = _store(args)
    records = _load_history(store)
    cmd = args.history_command
    if cmd == "list":
        filtered = [item for item in records if not args.state or item.get("state") == args.state]
        return _emit(args, filtered[: args.limit])
    match = next((item for item in records if item.get("task_id") == args.task_id), None) if hasattr(args, "task_id") else None
    if cmd == "show":
        return _emit(args, match or {}, ok=bool(match), message="" if match else "历史记录不存在")
    if cmd == "logs":
        if not match:
            return _emit(args, {}, ok=False, message="历史记录不存在")
        path = Path(match.get("log_file") or "")
        content = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        return _emit(args, {"record": match, "log": "\n".join(content.splitlines()[-args.lines:])}, ok=path.exists())
    if cmd == "delete":
        if not match:
            return _emit(args, {}, ok=False, message="历史记录不存在")
        with store.history_lock():
            current = _load_history(store)
            _save_history_unlocked(store, [item for item in current if item.get("task_id") != args.task_id])
        return _emit(args, {"task_id": args.task_id}, message="历史记录已删除")
    if cmd == "clear":
        with store.history_lock():
            deleted = len(_load_history(store))
            _save_history_unlocked(store, [])
        return _emit(args, {"deleted": deleted}, message="历史记录已清空")
    return EXIT_USAGE


def _handle_apps(args: argparse.Namespace) -> int:
    if args.apps_command == "supported":
        if args.platform == "ios":
            from phone_agent.config.apps_ios import list_supported_apps
        elif args.platform == "hdc":
            from phone_agent.config.apps_harmonyos import list_supported_apps
        else:
            from phone_agent.config.apps import list_supported_apps
        return _emit(args, sorted(list_supported_apps()))
    from phone_agent.adb.device import list_installed_apps, search_installed_apps
    apps = list_installed_apps(args.device_id)
    if args.apps_command == "find":
        apps = search_installed_apps(args.query, args.device_id)
    return _emit(args, _device_records(apps))


def _handle_build(args: argparse.Namespace) -> int:
    store = _store(args)
    if args.build_command == "gui":
        script = PROJECT_ROOT / "scripts" / "build_gui_onedir_venv.bat"
        if not script.exists():
            return _emit(args, {}, ok=False, message="GUI 打包脚本不存在")
        command = ["cmd", "/c", str(script)] if os.name == "nt" else [str(script)]
        state = start_job(store, "build", {"command": command, "cwd": str(PROJECT_ROOT)}, public={"target": "gui"}, cwd=PROJECT_ROOT)
        return _emit(args, _job_public(state), ok=state.get("state") != "failed", message="GUI 构建已在后台启动")
    if args.build_command == "status":
        return _emit(args, _job_public(refresh_state(store, args.job_id)))
    if args.build_command == "logs":
        return _emit(args, {"job": _job_public(refresh_state(store, args.job_id)), "log": store.tail(args.job_id, args.lines)})
    if args.build_command == "stop":
        return _emit(args, _job_public(stop_job(store, args.job_id, args.stop_timeout)))
    return EXIT_USAGE


def _handle_paths(args: argparse.Namespace) -> int:
    store = _store(args)
    return _emit(args, {"project": str(PROJECT_ROOT), "env_file": _resolved_env_file(args) if args.env_file else str(PROJECT_ROOT / ".env"), "state_dir": str(store.root), "history": str(store.root.parent), "scripts": str(PROJECT_ROOT / "scripts"), "release": str(PROJECT_ROOT / "release")})


def _common_job_id(sub):
    sub.add_argument("job_id")


def build_parser() -> argparse.ArgumentParser:
    parser = AutomationArgumentParser(prog="open-autoglm", description="Open-AutoGLM 自动化控制 CLI（默认 JSON、长任务默认后台）")
    parser.add_argument("--format", choices=["json", "text"], default=os.getenv("OPEN_AUTOGLM_CLI_FORMAT", "json"))
    parser.add_argument("--env-file", default=os.getenv("OPEN_AUTOGLM_ENV_PATH", ""), help="覆盖 .env 路径")
    parser.add_argument("--state-dir", default=os.getenv("OPEN_AUTOGLM_CLI_STATE_DIR", ""), help="覆盖后台作业状态目录")
    parser.add_argument("--debug", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("capabilities", help="输出机器可读能力与覆盖矩阵")
    c = commands.add_parser("status", help="输出配置、设备与后台作业总览"); c.add_argument("--probe-devices", action="store_true")
    commands.add_parser("paths", help="输出项目运行路径")

    config = commands.add_parser("config", help="配置、渠道和动作策略")
    cs = config.add_subparsers(dest="config_command", required=True)
    c = cs.add_parser("list"); c.add_argument("--show-secrets", action="store_true")
    c = cs.add_parser("get"); c.add_argument("key"); c.add_argument("--show-secrets", action="store_true")
    for name in ("set", "unset"):
        c = cs.add_parser(name); c.add_argument("key")
        if name == "set": c.add_argument("value")
        c.add_argument("--allow-unknown", action="store_true"); c.add_argument("--no-validate", dest="validate", action="store_false", default=True)
    c = cs.add_parser("set-many"); c.add_argument("values", nargs="?", default="{}"); c.add_argument("--file", default=""); c.add_argument("--allow-unknown", action="store_true"); c.add_argument("--no-validate", dest="validate", action="store_false", default=True)
    c = cs.add_parser("validate"); c.add_argument("--lang", choices=["cn", "en"], default="")
    cs.add_parser("channels")
    c = cs.add_parser("use-channel"); c.add_argument("channel", choices=["modelscope", "zhipu", "newapi", "local", "custom"])
    c = cs.add_parser("action-policy"); c.add_argument("--platform", choices=["adb", "hdc", "ios"], default="adb"); c.add_argument("--enabled"); c.add_argument("--ai-visible"); c.add_argument("--platform-defaults", choices=["true", "false"]); g=c.add_mutually_exclusive_group(); g.add_argument("--reset", action="store_true"); g.add_argument("--select-all", action="store_true"); g.add_argument("--clear", action="store_true")
    c = cs.add_parser("mirror-toolbar"); c.add_argument("--enabled", choices=["true", "false"]); c.add_argument("--actions"); g=c.add_mutually_exclusive_group(); g.add_argument("--select-all", action="store_true"); g.add_argument("--clear", action="store_true")
    cs.add_parser("swap-keys"); cs.add_parser("reload")
    cs.add_parser("test-api")
    c = cs.add_parser("api-status"); _common_job_id(c)
    c = cs.add_parser("api-result"); _common_job_id(c); c.add_argument("--lines", type=int, default=200)

    task = commands.add_parser("task", help="Agent 任务生命周期")
    ts = task.add_subparsers(dest="task_command", required=True)
    for name in ("start", "run"):
        t = ts.add_parser(name); t.add_argument("text"); t.add_argument("--device-id", default=""); t.add_argument("--stuck-timeout", type=float, default=120)
        if name == "run": t.add_argument("--wait-timeout", type=float, default=3600); t.add_argument("--lines", type=int, default=100)
    t = ts.add_parser("list"); t.add_argument("--limit", type=int, default=50)
    for name in ("status", "pause", "resume"):
        t = ts.add_parser(name); _common_job_id(t)
    t = ts.add_parser("logs"); _common_job_id(t); t.add_argument("--lines", type=int, default=100)
    t = ts.add_parser("stop"); _common_job_id(t); t.add_argument("--stop-timeout", type=float, default=3)
    t = ts.add_parser("instruct"); _common_job_id(t); t.add_argument("text")
    t = ts.add_parser("takeover"); _common_job_id(t); t.add_argument("--reason", default="人工接管")
    t = ts.add_parser("wait"); _common_job_id(t); t.add_argument("--wait-timeout", type=float, default=3600)

    jobs = commands.add_parser("jobs", help="统一后台作业控制")
    js = jobs.add_subparsers(dest="jobs_command", required=True)
    j = js.add_parser("list"); j.add_argument("--kind", default=""); j.add_argument("--limit", type=int, default=50)
    j = js.add_parser("status"); _common_job_id(j)
    j = js.add_parser("logs"); _common_job_id(j); j.add_argument("--lines", type=int, default=100)
    j = js.add_parser("stop"); _common_job_id(j); j.add_argument("--stop-timeout", type=float, default=3)

    diagnostics = commands.add_parser("diagnostics", help="完整 GUI 就绪诊断")
    ds = diagnostics.add_subparsers(dest="diagnostics_command", required=True)
    for name in ("start", "run"):
        d = ds.add_parser(name); d.add_argument("--device-id", default="")
        if name == "run": d.add_argument("--wait-timeout", type=float, default=180)
    d = ds.add_parser("status"); _common_job_id(d)
    d = ds.add_parser("result"); _common_job_id(d); d.add_argument("--lines", type=int, default=200)

    device = commands.add_parser("device", help="ADB 设备管理")
    ds = device.add_subparsers(dest="device_command", required=True)
    d = ds.add_parser("list"); d.add_argument("--platform", choices=["adb", "hdc", "ios"], default="adb")
    d = ds.add_parser("select"); d.add_argument("device_id")
    d = ds.add_parser("connect"); d.add_argument("endpoint")
    d = ds.add_parser("connect-start"); d.add_argument("endpoint")
    d = ds.add_parser("disconnect"); d.add_argument("endpoint", nargs="?", default="all")
    d = ds.add_parser("disconnect-start"); d.add_argument("endpoint", nargs="?", default="all")
    d = ds.add_parser("pair"); d.add_argument("endpoint"); d.add_argument("code"); d.add_argument("--connect-timeout", type=float, default=15)
    d = ds.add_parser("pair-start"); d.add_argument("endpoint"); d.add_argument("code"); d.add_argument("--connect-timeout", type=float, default=15)
    ds.add_parser("mdns"); d = ds.add_parser("qr"); d.add_argument("--output", default=""); ds.add_parser("restart-adb")
    d = ds.add_parser("qr-start"); d.add_argument("service_name"); d.add_argument("password"); d.add_argument("--pair-timeout", type=float, default=90)
    d = ds.add_parser("ios-pair"); d.add_argument("--device-id", default=""); d.add_argument("--wda-url", default="http://localhost:8100")
    d = ds.add_parser("wda-status"); d.add_argument("--wda-url", default="http://localhost:8100")
    d = ds.add_parser("tcpip"); d.add_argument("device_id"); d.add_argument("--port", type=int, default=5555); d.add_argument("--connect-timeout", type=float, default=12)
    d = ds.add_parser("tcpip-start"); d.add_argument("device_id"); d.add_argument("--port", type=int, default=5555); d.add_argument("--connect-timeout", type=float, default=12)
    for name in ("usb", "ip", "keyboard-status", "install-keyboard"):
        d = ds.add_parser(name); d.add_argument("device_id")
    for name in ("usb-start", "install-keyboard-start"):
        d = ds.add_parser(name); d.add_argument("device_id")
    ds.add_parser("adb-status"); ds.add_parser("scrcpy-status")

    mirror = commands.add_parser("mirror", help="scrcpy 独立镜像与工具栏动作")
    ms = mirror.add_subparsers(dest="mirror_command", required=True)
    ms.add_parser("check")
    m = ms.add_parser("start"); m.add_argument("device_id"); m.add_argument("--mode", choices=["auto", "scrcpy", "adb"], default="auto"); m.add_argument("--interval", type=float, default=1.5)
    m = ms.add_parser("status"); m.add_argument("--job-id", default="")
    for name in ("stop", "restart"):
        m = ms.add_parser(name); m.add_argument("--job-id", default=""); m.add_argument("--stop-timeout", type=float, default=3)
    m = ms.add_parser("action"); m.add_argument("action", choices=["fullscreen", "notifications", "touch", "screen_on", "screen_off", "power", "volume_up", "volume_down", "app_switch", "menu", "home", "back", "screenshot", "clipboard"]); m.add_argument("--job-id", default=""); m.add_argument("--device-id", default=""); m.add_argument("--touch", choices=["0", "1"], default="1"); m.add_argument("--output", default="")
    m = ms.add_parser("paste"); m.add_argument("--job-id", default=""); m.add_argument("--device-id", default="")
    m = ms.add_parser("screenshot"); m.add_argument("--job-id", default=""); m.add_argument("--device-id", default=""); m.add_argument("--output", default="")

    history = commands.add_parser("history", help="GUI/CLI 共享任务历史")
    hs = history.add_subparsers(dest="history_command", required=True)
    h = hs.add_parser("list"); h.add_argument("--state", default=""); h.add_argument("--limit", type=int, default=100)
    for name in ("show", "delete"):
        h = hs.add_parser(name); h.add_argument("task_id")
    h = hs.add_parser("logs"); h.add_argument("task_id"); h.add_argument("--lines", type=int, default=200)
    hs.add_parser("clear")

    apps = commands.add_parser("apps", help="支持应用与设备应用发现")
    aps = apps.add_subparsers(dest="apps_command", required=True)
    a = aps.add_parser("supported"); a.add_argument("--platform", choices=["adb", "hdc", "ios"], default="adb")
    a = aps.add_parser("device"); a.add_argument("--device-id", default="")
    a = aps.add_parser("find"); a.add_argument("query"); a.add_argument("--device-id", default="")

    build = commands.add_parser("build", help="GUI 打包后台作业")
    bs = build.add_subparsers(dest="build_command", required=True)
    bs.add_parser("gui")
    b = bs.add_parser("status"); _common_job_id(b)
    b = bs.add_parser("logs"); _common_job_id(b); b.add_argument("--lines", type=int, default=200)
    b = bs.add_parser("stop"); _common_job_id(b); b.add_argument("--stop-timeout", type=float, default=3)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except CliUsageError as exc:
        raw = list(argv or sys.argv[1:])
        text_mode = "--format" in raw and raw[raw.index("--format") + 1:raw.index("--format") + 2] == ["text"]
        if text_mode:
            print(f"参数错误：{exc}")
        else:
            print(json.dumps({"ok": False, "message": f"参数错误：{exc}", "data": {}}, ensure_ascii=False, indent=2))
        return EXIT_USAGE
    handlers = {"capabilities": _handle_capabilities, "status": _handle_status, "paths": _handle_paths, "config": _handle_config, "task": _handle_task, "jobs": _handle_jobs, "diagnostics": _handle_diagnostics, "device": _handle_device, "mirror": _handle_mirror, "history": _handle_history, "apps": _handle_apps, "build": _handle_build}
    try:
        return handlers[args.command](args)
    except KeyError as exc:
        _emit(args, {}, ok=False, message=str(exc)); return EXIT_NOT_FOUND
    except TimeoutError as exc:
        _emit(args, {}, ok=False, message=str(exc)); return EXIT_TIMEOUT
    except (RuntimeError, ValueError) as exc:
        _emit(args, {}, ok=False, message=str(exc)); return EXIT_CONFLICT
    except KeyboardInterrupt:
        _emit(args, {}, ok=False, message="操作已中断"); return 130
    except Exception as exc:
        if args.debug:
            raise
        _emit(args, {}, ok=False, message=f"{type(exc).__name__}: {exc}"); return EXIT_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
