"""Device control utilities for Android automation."""

import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from phone_agent.config.apps import APP_PACKAGES
from phone_agent.config.timing import TIMING_CONFIG
from phone_agent.device_factory import AppLaunchResult


@dataclass
class InstalledApp:
    """Installed Android app discovered from the device."""

    package_name: str
    display_name: str | None = None
    activity_name: str | None = None

    @property
    def search_blob(self) -> str:
        """Return lowercase text used for fuzzy matching."""
        parts = [self.package_name]
        if self.display_name:
            parts.append(self.display_name)
        return "\n".join(parts).lower()


def get_current_app(device_id: str | None = None) -> str:
    """
    Get the currently focused app name.

    Args:
        device_id: Optional ADB device ID for multi-device setups.

    Returns:
        The app name if recognized, otherwise package name or "System Home".
    """
    try:
        output = _run_adb_shell(["dumpsys", "window"], device_id)
    except Exception:
        return "System Home"
    if not output:
        return "System Home"

    # Parse window focus info
    for line in output.split("\n"):
        if "mCurrentFocus" in line or "mFocusedApp" in line:
            for app_name, package in APP_PACKAGES.items():
                if package in line:
                    return app_name

            package_match = re.search(r"([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+)/", line)
            if package_match:
                return package_match.group(1)

    return "System Home"


def tap(
    x: int, y: int, device_id: str | None = None, delay: float | None = None
) -> None:
    """
    Tap at the specified coordinates.

    Args:
        x: X coordinate.
        y: Y coordinate.
        device_id: Optional ADB device ID.
        delay: Delay in seconds after tap. If None, uses configured default.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_tap_delay

    adb_prefix = _get_adb_prefix(device_id)

    subprocess.run(
        adb_prefix + ["shell", "input", "tap", str(x), str(y)], capture_output=True
    )
    time.sleep(delay)


def double_tap(
    x: int, y: int, device_id: str | None = None, delay: float | None = None
) -> None:
    """
    Double tap at the specified coordinates.

    Args:
        x: X coordinate.
        y: Y coordinate.
        device_id: Optional ADB device ID.
        delay: Delay in seconds after double tap. If None, uses configured default.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_double_tap_delay

    adb_prefix = _get_adb_prefix(device_id)

    subprocess.run(
        adb_prefix + ["shell", "input", "tap", str(x), str(y)], capture_output=True
    )
    time.sleep(TIMING_CONFIG.device.double_tap_interval)
    subprocess.run(
        adb_prefix + ["shell", "input", "tap", str(x), str(y)], capture_output=True
    )
    time.sleep(delay)


def long_press(
    x: int,
    y: int,
    duration_ms: int = 3000,
    device_id: str | None = None,
    delay: float | None = None,
) -> None:
    """
    Long press at the specified coordinates.

    Args:
        x: X coordinate.
        y: Y coordinate.
        duration_ms: Duration of press in milliseconds.
        device_id: Optional ADB device ID.
        delay: Delay in seconds after long press. If None, uses configured default.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_long_press_delay

    adb_prefix = _get_adb_prefix(device_id)

    subprocess.run(
        adb_prefix
        + ["shell", "input", "swipe", str(x), str(y), str(x), str(y), str(duration_ms)],
        capture_output=True,
    )
    time.sleep(delay)


def swipe(
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
    duration_ms: int | None = None,
    device_id: str | None = None,
    delay: float | None = None,
) -> None:
    """
    Swipe from start to end coordinates.

    Args:
        start_x: Starting X coordinate.
        start_y: Starting Y coordinate.
        end_x: Ending X coordinate.
        end_y: Ending Y coordinate.
        duration_ms: Duration of swipe in milliseconds (auto-calculated if None).
        device_id: Optional ADB device ID.
        delay: Delay in seconds after swipe. If None, uses configured default.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_swipe_delay

    adb_prefix = _get_adb_prefix(device_id)

    if duration_ms is None:
        # Calculate duration based on distance
        dist_sq = (start_x - end_x) ** 2 + (start_y - end_y) ** 2
        duration_ms = int(dist_sq / 1000)
        duration_ms = max(1000, min(duration_ms, 2000))  # Clamp between 1000-2000ms

    subprocess.run(
        adb_prefix
        + [
            "shell",
            "input",
            "swipe",
            str(start_x),
            str(start_y),
            str(end_x),
            str(end_y),
            str(duration_ms),
        ],
        capture_output=True,
    )
    time.sleep(delay)


def back(device_id: str | None = None, delay: float | None = None) -> None:
    """
    Press the back button.

    Args:
        device_id: Optional ADB device ID.
        delay: Delay in seconds after pressing back. If None, uses configured default.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_back_delay

    adb_prefix = _get_adb_prefix(device_id)

    subprocess.run(
        adb_prefix + ["shell", "input", "keyevent", "4"], capture_output=True
    )
    time.sleep(delay)


def home(device_id: str | None = None, delay: float | None = None) -> None:
    """
    Press the home button.

    Args:
        device_id: Optional ADB device ID.
        delay: Delay in seconds after pressing home. If None, uses configured default.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_home_delay

    adb_prefix = _get_adb_prefix(device_id)

    subprocess.run(
        adb_prefix + ["shell", "input", "keyevent", "KEYCODE_HOME"], capture_output=True
    )
    time.sleep(delay)


def launch_app(
    app_name: str, device_id: str | None = None, delay: float | None = None
) -> AppLaunchResult:
    """
    Launch an app by name.

    Args:
        app_name: The app name or package identifier.
        device_id: Optional ADB device ID.
        delay: Delay in seconds after launching. If None, uses configured default.

    Returns:
        Detailed launch result.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_launch_delay

    package = APP_PACKAGES.get(app_name)
    if package:
        launch_result = _launch_package(package, device_id, delay)
        if launch_result.success:
            launch_result.message = f"已启动 {app_name} ({package})"
        return launch_result

    matches = search_installed_apps(app_name, device_id)
    if not matches:
        return AppLaunchResult(False, f"未找到应用：{app_name}")
    if len(matches) > 1:
        candidates = ", ".join(
            f"{app.display_name or app.package_name} ({app.package_name})"
            for app in matches[:5]
        )
        return AppLaunchResult(
            False,
            f"找到多个候选应用，请改用更精确的名称：{candidates}",
        )

    matched_app = matches[0]
    launch_result = _launch_package(matched_app.package_name, device_id, delay)
    if launch_result.success:
        display_name = matched_app.display_name or app_name
        launch_result.message = f"已通过设备查找启动 {display_name} ({matched_app.package_name})"
    return launch_result


def list_installed_apps(device_id: str | None = None) -> list[InstalledApp]:
    """List launchable apps installed on the connected device."""
    output = _run_adb_shell(
        [
            "cmd",
            "package",
            "query-activities",
            "-a",
            "android.intent.action.MAIN",
            "-c",
            "android.intent.category.LAUNCHER",
            "--brief",
            "--components",
        ],
        device_id,
        check=False,
    )
    if not output:
        return []

    apps: list[InstalledApp] = []
    seen_packages: set[str] = set()
    for line in output.splitlines():
        component = line.strip()
        if not component or "/" not in component or component.startswith("priority="):
            continue
        package_name, activity_name = component.split("/", 1)
        if package_name in seen_packages:
            continue
        seen_packages.add(package_name)
        apps.append(
            InstalledApp(
                package_name=package_name,
                display_name=_get_application_label(package_name, device_id),
                activity_name=activity_name,
            )
        )

    return apps


def find_installed_app(query: str, device_id: str | None = None) -> InstalledApp | None:
    """Find the best matching installed app by package name or display name."""
    matches = search_installed_apps(query, device_id)
    if not matches:
        return None
    return matches[0]


def search_installed_apps(query: str, device_id: str | None = None) -> list[InstalledApp]:
    """Search installed apps by package name or display name."""
    normalized_query = (query or "").strip().lower()
    if not normalized_query:
        return []

    apps = list_installed_apps(device_id)
    if not apps:
        return []

    exact_matches = [
        app
        for app in apps
        if normalized_query == app.package_name.lower()
        or normalized_query == (app.display_name or "").lower()
    ]
    if exact_matches:
        return exact_matches

    package_suffix_matches = [
        app for app in apps if app.package_name.lower().endswith(f".{normalized_query}")
    ]
    if package_suffix_matches:
        return package_suffix_matches

    fuzzy_matches = [app for app in apps if normalized_query in app.search_blob]
    fuzzy_matches.sort(
        key=lambda app: (
            app.package_name.lower() != normalized_query,
            normalized_query not in (app.display_name or "").lower(),
            len(app.package_name),
        )
    )
    return fuzzy_matches


def _launch_package(
    package_name: str, device_id: str | None = None, delay: float | None = None
) -> AppLaunchResult:
    """Launch a specific package safely."""
    if delay is None:
        delay = TIMING_CONFIG.device.default_launch_delay

    activity_name = _resolve_launchable_activity(package_name, device_id)
    if activity_name:
        launch_output = _run_adb_shell(
            [
                "am",
                "start",
                "-n",
                f"{package_name}/{activity_name}",
            ],
            device_id,
            check=False,
        )
        if "Error:" not in launch_output and "Exception" not in launch_output:
            time.sleep(delay)
            return AppLaunchResult(True, package_name=package_name)

    adb_prefix = _get_adb_prefix(device_id)
    result = subprocess.run(
        adb_prefix
        + [
            "shell",
            "monkey",
            "-p",
            package_name,
            "-c",
            "android.intent.category.LAUNCHER",
            "1",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode == 0 and "No activities found" not in output:
        time.sleep(delay)
        return AppLaunchResult(True, package_name=package_name)

    message = output.strip() or f"启动失败：{package_name}"
    return AppLaunchResult(False, message, package_name)


def _resolve_launchable_activity(
    package_name: str, device_id: str | None = None
) -> str | None:
    """Resolve the launcher activity for a package if available."""
    output = _run_adb_shell(
        [
            "cmd",
            "package",
            "resolve-activity",
            "--brief",
            "-a",
            "android.intent.action.MAIN",
            "-c",
            "android.intent.category.LAUNCHER",
            package_name,
        ],
        device_id,
        check=False,
    )
    if not output:
        return None

    for line in output.splitlines():
        component = line.strip()
        if component.startswith(package_name + "/"):
            _, activity_name = component.split("/", 1)
            return activity_name
    return None


def _get_application_label(
    package_name: str, device_id: str | None = None
) -> str | None:
    """Best-effort application label lookup with safe fallbacks."""
    try:
        label = _get_application_label_from_dumpsys(package_name, device_id)
        if label:
            return label
    except Exception:
        pass

    try:
        label = _get_application_label_from_apk(package_name, device_id)
        if label:
            return label
    except Exception:
        pass

    return package_name.split(".")[-1]


def _get_application_label_from_dumpsys(
    package_name: str, device_id: str | None = None
) -> str | None:
    """Try to resolve an application label from dumpsys package output."""
    output = _run_adb_shell(["dumpsys", "package", package_name], device_id, check=False)
    if not output:
        return None

    non_localized = re.search(r"nonLocalizedLabel=([^\n\r]+)", output)
    if non_localized:
        label = non_localized.group(1).strip().strip('"')
        if label:
            return label

    return None


def _get_application_label_from_apk(
    package_name: str, device_id: str | None = None
) -> str | None:
    """Resolve an application label by pulling the APK and inspecting it locally."""
    apk_path = _get_base_apk_path(package_name, device_id)
    if not apk_path:
        return None

    tool_path = _find_apk_label_tool()
    if not tool_path:
        return None

    with tempfile.TemporaryDirectory(prefix="open-autoglm-apk-") as temp_dir:
        local_apk_path = os.path.join(temp_dir, "base.apk")
        if not _adb_pull_file(apk_path, local_apk_path, device_id):
            return None
        return _extract_label_from_local_apk(local_apk_path, tool_path)


def _get_base_apk_path(package_name: str, device_id: str | None = None) -> str | None:
    """Return the device path to a package base APK when available."""
    output = _run_adb_shell(["pm", "path", package_name], device_id, check=False)
    if not output:
        return None

    for line in output.splitlines():
        candidate = line.strip()
        if candidate.startswith("package:") and candidate.endswith("base.apk"):
            return candidate.split(":", 1)[1].strip()
    return None


def _find_apk_label_tool() -> str | None:
    """Find a local APK inspection tool capable of printing app labels."""
    for tool_name in ("aapt", "aapt2"):
        candidate = shutil.which(tool_name)
        if candidate:
            return candidate

    android_sdk_root = os.environ.get("ANDROID_SDK_ROOT") or os.environ.get("ANDROID_HOME")
    if not android_sdk_root:
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            android_sdk_root = os.path.join(local_appdata, "Android", "Sdk")

    if android_sdk_root:
        sdk_root = Path(android_sdk_root)
        build_tools_dir = sdk_root / "build-tools"
        if build_tools_dir.exists():
            version_dirs = sorted(
                (path for path in build_tools_dir.iterdir() if path.is_dir()),
                key=lambda path: path.name,
                reverse=True,
            )
            for version_dir in version_dirs:
                for tool_name in ("aapt.exe", "aapt", "aapt2.exe", "aapt2"):
                    candidate = version_dir / tool_name
                    if candidate.exists():
                        return str(candidate)

        for tool_name in ("apkanalyzer.bat", "apkanalyzer"):
            candidate = sdk_root / "cmdline-tools" / "latest" / "bin" / tool_name
            if candidate.exists():
                return str(candidate)

    return shutil.which("apkanalyzer")


def _adb_pull_file(
    remote_path: str, local_path: str, device_id: str | None = None
) -> bool:
    """Pull a file from device storage to a local path."""
    adb_prefix = _get_adb_prefix(device_id)
    result = subprocess.run(
        adb_prefix + ["pull", remote_path, local_path],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.returncode == 0 and os.path.exists(local_path)


def _extract_label_from_local_apk(local_apk_path: str, tool_path: str) -> str | None:
    """Extract the best available human-readable label from a local APK."""
    tool_name = Path(tool_path).name.lower()
    if tool_name.startswith("aapt"):
        return _extract_label_with_aapt(local_apk_path, tool_path)
    return _extract_label_with_apkanalyzer(local_apk_path, tool_path)


def _extract_label_with_aapt(local_apk_path: str, tool_path: str) -> str | None:
    """Extract application label using aapt/aapt2 dump badging."""
    try:
        result = subprocess.run(
            [tool_path, "dump", "badging", local_apk_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None

    output = (result.stdout or "") + (result.stderr or "")
    preferred_prefixes = (
        "application-label-zh-CN:",
        "application-label-zh_CN:",
        "application-label-zh:",
        "application-label:",
        "application-label-en:",
    )
    for prefix in preferred_prefixes:
        label = _extract_quoted_value_from_lines(output, prefix)
        if label:
            return label
    return None


def _extract_label_with_apkanalyzer(local_apk_path: str, tool_path: str) -> str | None:
    """Fallback label extraction using manifest/resource inspection via apkanalyzer."""
    try:
        manifest_result = subprocess.run(
            [tool_path, "manifest", "print", local_apk_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError:
        return None
    if manifest_result.returncode != 0:
        return None

    manifest_output = manifest_result.stdout or ""
    label_ref_match = re.search(
        r"<application[\s\S]*?android:label=\"([^\"]+)\"",
        manifest_output,
    )
    if not label_ref_match:
        return None

    label_ref = label_ref_match.group(1).strip()
    if not label_ref or not label_ref.startswith("@ref/"):
        return label_ref or None

    resource_name = _resolve_resource_name_from_ref(local_apk_path, label_ref, tool_path)
    if not resource_name:
        return None

    for config in ("zh-rCN", "zh", "default", "en"):
        label = _resolve_resource_value(local_apk_path, resource_name, config, tool_path)
        if label:
            return label
    return None


def _resolve_resource_name_from_ref(
    local_apk_path: str, resource_ref: str, tool_path: str
) -> str | None:
    """Resolve a @ref/0x... string resource to its resource name."""
    try:
        xml_result = subprocess.run(
            [tool_path, "resources", "xml", "--file", "AndroidManifest.xml", local_apk_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError:
        return None
    if xml_result.returncode != 0:
        return None

    xml_output = xml_result.stdout or ""
    ref_pattern = re.escape(resource_ref)
    match = re.search(
        rf"name=\"android:label\"[^\n]*?value=\"{ref_pattern}\"[^\n]*?raw=\"([^\"]+)\"",
        xml_output,
    )
    if match:
        return match.group(1).strip()
    return None


def _resolve_resource_value(
    local_apk_path: str, resource_name: str, config: str, tool_path: str
) -> str | None:
    """Resolve a string resource value for a specific resource configuration."""
    try:
        result = subprocess.run(
            [
                tool_path,
                "resources",
                "value",
                "--type",
                "string",
                "--config",
                config,
                "--name",
                resource_name,
                local_apk_path,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None

    value = (result.stdout or "").strip().strip('"')
    return value or None


def _extract_quoted_value_from_lines(output: str, prefix: str) -> str | None:
    """Extract a quoted value from command output lines with a given prefix."""
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped.startswith(prefix):
            continue
        match = re.search(r"'([^']*)'", stripped)
        if match:
            value = match.group(1).strip()
            if value:
                return value
    return None


def _run_adb_shell(
    shell_args: list[str], device_id: str | None = None, check: bool = True
) -> str:
    """Run an adb shell command and return combined output."""
    adb_prefix = _get_adb_prefix(device_id)
    result = subprocess.run(
        adb_prefix + ["shell", *shell_args],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    output = (result.stdout or "") + (result.stderr or "")
    if check and result.returncode != 0:
        raise RuntimeError(output.strip() or f"ADB shell command failed: {' '.join(shell_args)}")
    return output.strip()


def _get_adb_prefix(device_id: str | None) -> list:
    """Get ADB command prefix with optional device specifier."""
    if device_id:
        return ["adb", "-s", device_id]
    return ["adb"]
