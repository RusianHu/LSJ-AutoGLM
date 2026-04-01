"""Input utilities for Android device text input."""

import base64
import subprocess
from typing import Optional


ADB_KEYBOARD_IME = "com.android.adbkeyboard/.AdbIME"


def _format_result_detail(result: subprocess.CompletedProcess) -> str:
    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    merged = " | ".join(part for part in (stdout, stderr) if part)
    return merged or "empty"



def type_text(text: str, device_id: str | None = None) -> None:
    """
    Type text into the currently focused input field using ADB Keyboard.

    Args:
        text: The text to type.
        device_id: Optional ADB device ID for multi-device setups.

    Note:
        Requires ADB Keyboard to be installed on the device.
        See: https://github.com/nicnocquee/AdbKeyboard
    """
    adb_prefix = _get_adb_prefix(device_id)
    encoded_text = base64.b64encode(text.encode("utf-8")).decode("utf-8")

    result = subprocess.run(
        adb_prefix
        + [
            "shell",
            "am",
            "broadcast",
            "-a",
            "ADB_INPUT_B64",
            "--es",
            "msg",
            encoded_text,
        ],
        capture_output=True,
        text=True,
    )
    detail = _format_result_detail(result)
    if result.returncode != 0:
        raise RuntimeError(f"ADBKeyboard 广播失败(code={result.returncode}): {detail}")
    if "Broadcast completed" not in detail and "result=" not in detail and text:
        raise RuntimeError(f"ADBKeyboard 广播结果异常: {detail}")


def clear_text(device_id: str | None = None) -> None:
    """
    Clear text in the currently focused input field.

    Args:
        device_id: Optional ADB device ID for multi-device setups.
    """
    adb_prefix = _get_adb_prefix(device_id)

    subprocess.run(
        adb_prefix + ["shell", "am", "broadcast", "-a", "ADB_CLEAR_TEXT"],
        capture_output=True,
        text=True,
    )


def detect_and_set_adb_keyboard(device_id: str | None = None) -> str:
    """
    Detect current keyboard and switch to ADB Keyboard if needed.

    Args:
        device_id: Optional ADB device ID for multi-device setups.

    Returns:
        The original keyboard IME identifier for later restoration.
    """
    adb_prefix = _get_adb_prefix(device_id)

    # Get current IME
    result = subprocess.run(
        adb_prefix + ["shell", "settings", "get", "secure", "default_input_method"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"读取默认输入法失败(code={result.returncode}): {_format_result_detail(result)}"
        )
    current_ime = (result.stdout + result.stderr).strip()

    # Switch to ADB Keyboard if not already set
    if ADB_KEYBOARD_IME not in current_ime:
        switch_result = subprocess.run(
            adb_prefix + ["shell", "ime", "set", ADB_KEYBOARD_IME],
            capture_output=True,
            text=True,
        )
        if switch_result.returncode != 0:
            raise RuntimeError(
                "切换到 ADBKeyboard 失败"
                f"(code={switch_result.returncode}): {_format_result_detail(switch_result)}"
            )

        verify_result = subprocess.run(
            adb_prefix + ["shell", "settings", "get", "secure", "default_input_method"],
            capture_output=True,
            text=True,
        )
        if verify_result.returncode != 0:
            raise RuntimeError(
                "切换后校验输入法失败"
                f"(code={verify_result.returncode}): {_format_result_detail(verify_result)}"
            )
        current_after = (verify_result.stdout + verify_result.stderr).strip()
        if ADB_KEYBOARD_IME not in current_after:
            raise RuntimeError(f"ADBKeyboard 未生效，当前输入法为: {current_after or 'empty'}")

    # Warm up the keyboard
    type_text("", device_id)

    return current_ime


def restore_keyboard(ime: str, device_id: str | None = None) -> None:
    """
    Restore the original keyboard IME.

    Args:
        ime: The IME identifier to restore.
        device_id: Optional ADB device ID for multi-device setups.
    """
    adb_prefix = _get_adb_prefix(device_id)

    result = subprocess.run(
        adb_prefix + ["shell", "ime", "set", ime], capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"恢复输入法失败(code={result.returncode}): {_format_result_detail(result)}"
        )


def _get_adb_prefix(device_id: str | None) -> list:
    """Get ADB command prefix with optional device specifier."""
    if device_id:
        return ["adb", "-s", device_id]
    return ["adb"]
