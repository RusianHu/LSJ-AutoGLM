# -*- coding: utf-8 -*-
"""GUI 运行时路径与单文件子进程辅助。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

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


def resolve_env_path() -> Path:
    """解析 GUI 使用的 .env 路径。

    支持通过 OPEN_AUTOGLM_ENV_PATH 覆盖；相对路径按运行根目录解析。
    """
    override = (os.environ.get("OPEN_AUTOGLM_ENV_PATH") or "").strip()
    if override:
        path = Path(override)
        return path if path.is_absolute() else resolve_path(override)
    return resolve_path(".env")


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
