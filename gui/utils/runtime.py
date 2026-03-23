# -*- coding: utf-8 -*-
"""GUI 运行时路径与单文件子进程辅助。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

GUI_ONEFILE_EXE_NAME = "OpenAutoGLM-GUI.exe"
GUI_TASK_RUNNER_FLAG = "--gui-task-runner"


def is_frozen() -> bool:
    """当前是否运行于 PyInstaller/Nuitka 等冻结环境。"""
    return bool(getattr(sys, "frozen", False))


def bundle_root() -> Path:
    """返回打包资源根目录；源码运行时回退到项目根目录。"""
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        return Path(meipass).resolve()
    return Path(__file__).resolve().parents[2]


def app_root() -> Path:
    """返回运行根目录。

    - 源码运行：仓库根目录
    - 单文件运行：exe 所在目录
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def resolve_path(*parts: str) -> Path:
    """基于运行根目录拼接路径。"""
    return app_root().joinpath(*parts)



def _iter_search_roots() -> list[Path]:
    roots: list[Path] = []
    for candidate in (app_root(), bundle_root(), app_root().parent):
        try:
            resolved = candidate.resolve()
        except Exception:
            resolved = candidate
        if resolved not in roots:
            roots.append(resolved)
    return roots



def find_adb_executable() -> Path | None:
    """定位 adb 可执行文件。

    优先级：
    1. OPEN_AUTOGLM_ADB_PATH / OPEN_AUTOGLM_ADB
    2. 打包内置资源 / 运行根目录附近的常见相对路径
    3. 当前 PATH 中的 adb
    """
    env_override = (os.environ.get("OPEN_AUTOGLM_ADB_PATH") or os.environ.get("OPEN_AUTOGLM_ADB") or "").strip()
    if env_override:
        candidate = Path(env_override)
        if not candidate.is_absolute():
            candidate = app_root() / candidate
        if candidate.exists():
            return candidate.resolve()

    adb_name = "adb.exe" if sys.platform == "win32" else "adb"
    candidates: list[Path] = []
    for root in _iter_search_roots():
        candidates.extend([
            root / adb_name,
            root / "platform-tools" / adb_name,
            root / "tools" / "platform-tools" / adb_name,
            root / "adb" / adb_name,
            root / "tools" / "adb" / adb_name,
        ])

    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    which_path = shutil.which("adb")
    if which_path:
        return Path(which_path).resolve()
    return None



def ensure_runtime_path() -> None:
    """将运行期依赖目录注入 PATH，兼容 Windows 单文件打包启动。"""
    path_entries = os.environ.get("PATH", "").split(os.pathsep) if os.environ.get("PATH") else []
    normalized = {entry.lower() if sys.platform == "win32" else entry for entry in path_entries if entry}

    def _prepend(entry: Path | None) -> None:
        if entry is None:
            return
        try:
            resolved = str(entry.resolve())
        except Exception:
            resolved = str(entry)
        if not resolved:
            return
        key = resolved.lower() if sys.platform == "win32" else resolved
        if key in normalized:
            return
        path_entries.insert(0, resolved)
        normalized.add(key)

    adb_path = find_adb_executable()
    if adb_path is not None:
        _prepend(adb_path.parent)

    for root in _iter_search_roots():
        _prepend(root)
        _prepend(root / "platform-tools")
        _prepend(root / "scrcpy")

    os.environ["PATH"] = os.pathsep.join(path_entries)


def resolve_env_path() -> Path:
    """解析 GUI 使用的 .env 路径。

    支持通过 OPEN_AUTOGLM_ENV_PATH 覆盖；相对路径按运行根目录解析。
    """
    override = (os.environ.get("OPEN_AUTOGLM_ENV_PATH") or "").strip()
    if override:
        path = Path(override)
        return path if path.is_absolute() else resolve_path(override)
    return resolve_path(".env")


def find_adb_keyboard_apk() -> Path | None:
    """定位 ADBKeyboard.apk。

    优先级：
    1. OPEN_AUTOGLM_ADBKEYBOARD_APK
    2. 打包内置资源 / 运行根目录中的 ADBKeyboard.apk
    """
    env_override = (os.environ.get("OPEN_AUTOGLM_ADBKEYBOARD_APK") or "").strip()
    if env_override:
        candidate = Path(env_override)
        if not candidate.is_absolute():
            candidate = app_root() / candidate
        if candidate.exists():
            return candidate.resolve()

    for root in _iter_search_roots():
        candidate = root / "ADBKeyboard.apk"
        if candidate.exists():
            return candidate.resolve()
    return None


def gui_build_script_path() -> Path:
    """GUI 单文件打包脚本路径。"""
    return resolve_path("scripts", "build_gui_onefile.bat")


def gui_dist_dir() -> Path:
    """GUI 打包输出目录。"""
    return resolve_path("dist")


def gui_onefile_output_path() -> Path:
    """GUI 单文件 exe 预期输出路径。"""
    return gui_dist_dir() / GUI_ONEFILE_EXE_NAME


def build_task_subprocess_command(cli_args: list[str] | tuple[str, ...]) -> list[str]:
    """构建任务子进程命令。

    - 源码运行：python -u main.py ...
    - 单文件运行：当前 exe --gui-task-runner ...
    """
    normalized_args = list(cli_args)
    if is_frozen():
        return [str(Path(sys.executable).resolve()), GUI_TASK_RUNNER_FLAG, *normalized_args]
    return [sys.executable, "-u", str(resolve_path("main.py")), *normalized_args]


def _apply_windows_hidden_subprocess_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    """在 Windows GUI 进程中隐藏 console 子进程窗口。"""
    if sys.platform != "win32":
        return kwargs

    prepared = dict(kwargs)
    prepared["creationflags"] = int(prepared.get("creationflags") or 0) | int(
        getattr(subprocess, "CREATE_NO_WINDOW", 0) or 0
    )

    startupinfo = prepared.get("startupinfo")
    if startupinfo is None and hasattr(subprocess, "STARTUPINFO"):
        startupinfo = subprocess.STARTUPINFO()
    if startupinfo is not None:
        startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 0)
        startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
        prepared["startupinfo"] = startupinfo
    return prepared


def gui_run_subprocess(args: list[str] | tuple[str, ...], **kwargs) -> subprocess.CompletedProcess:
    """运行 GUI 侧后台命令；Windows 下隐藏 adb/scrcpy 等控制台窗口。"""
    return subprocess.run(list(args), **_apply_windows_hidden_subprocess_kwargs(kwargs))



def gui_popen_subprocess(args: list[str] | tuple[str, ...], **kwargs) -> subprocess.Popen:
    """启动 GUI 侧后台子进程；Windows 下隐藏 console 窗口。"""
    return subprocess.Popen(list(args), **_apply_windows_hidden_subprocess_kwargs(kwargs))


def patch_subprocess_for_gui() -> None:
    """为 GUI 进程补丁 subprocess，默认隐藏 Windows 控制台窗口。

    注意：只能保留 subprocess.Popen 的“类”语义，不能把它替换为普通函数。
    asyncio.windows_utils 等标准库模块会通过 ``class X(subprocess.Popen)``
    继承它；若被替换成函数，打包后的 openai/pydantic/asyncio 导入链会在
    Windows 上触发 ``TypeError: function() argument 'code' must be code, not str``。
    """
    if sys.platform != "win32":
        return
    if getattr(subprocess, "_autoglm_gui_patched", False):
        return

    original_popen = subprocess.Popen

    class _PatchedPopen(original_popen):
        """保持 Popen 仍为可继承类，同时注入隐藏控制台窗口参数。"""

        def __init__(self, *popenargs, **kwargs):
            allow_console = kwargs.pop("autoglm_allow_console", False)
            if not allow_console:
                kwargs = _apply_windows_hidden_subprocess_kwargs(kwargs)
            super().__init__(*popenargs, **kwargs)

    subprocess.Popen = _PatchedPopen
    subprocess._autoglm_gui_patched = True



def ensure_standard_streams() -> None:
    """为 windowed 单文件子进程补齐标准流。

    PyInstaller 在 --windowed 模式下可能把 sys.stdout/sys.stderr 设为 None。
    任务子进程仍需要把 CLI 日志通过 PIPE 回传给 GUI，因此在 runner 模式中显式补齐。
    """
    _ensure_stream("stdin", 0, "r")
    _ensure_stream("stdout", 1, "w")
    _ensure_stream("stderr", 2, "w")


def _ensure_stream(name: str, fd: int, mode: str) -> None:
    stream = getattr(sys, name, None)
    if stream is not None:
        return

    try:
        buffering = -1 if "r" in mode else 1
        replacement = open(fd, mode, encoding="utf-8", buffering=buffering, closefd=False)
    except Exception:
        fallback_mode = "r" if "r" in mode else "w"
        replacement = open(os.devnull, fallback_mode, encoding="utf-8")

    setattr(sys, name, replacement)
