# -*- coding: utf-8 -*-
"""CLI 系统环境与模型 API 检查。"""

from __future__ import annotations

import shutil
import subprocess

from openai import OpenAI

from phone_agent.device_factory import DeviceType
from phone_agent.xctest import XCTestConnection
from phone_agent.xctest import list_devices as list_ios_devices



def check_system_requirements(
    device_type: DeviceType = DeviceType.ADB,
    wda_url: str = "http://localhost:8100",
    device_id: str | None = None,
) -> bool:
    """检查运行前的系统依赖与设备连通性。"""
    print("🔍 Checking system requirements...")
    print("-" * 50)

    all_passed = True
    resolved_device_id = (device_id or "").strip() or None
    device_ids: list[str] = []

    if device_type == DeviceType.IOS:
        tool_name = "libimobiledevice"
        tool_cmd = "idevice_id"
    else:
        tool_name = "ADB" if device_type == DeviceType.ADB else "HDC"
        tool_cmd = "adb" if device_type == DeviceType.ADB else "hdc"

    print(f"1. Checking {tool_name} installation...", end=" ")
    if shutil.which(tool_cmd) is None:
        print("❌ FAILED")
        print(f"   Error: {tool_name} is not installed or not in PATH.")
        print(f"   Solution: Install {tool_name}:")
        if device_type == DeviceType.ADB:
            print("     - macOS: brew install android-platform-tools")
            print("     - Linux: sudo apt install android-tools-adb")
            print(
                "     - Windows: Download from https://developer.android.com/studio/releases/platform-tools"
            )
        elif device_type == DeviceType.HDC:
            print(
                "     - Download from HarmonyOS SDK or https://gitee.com/openharmony/docs"
            )
            print("     - Add to PATH environment variable")
        else:
            print("     - macOS: brew install libimobiledevice")
            print("     - Linux: sudo apt-get install libimobiledevice-utils")
        all_passed = False
    else:
        try:
            if device_type == DeviceType.ADB:
                version_cmd = [tool_cmd, "version"]
            elif device_type == DeviceType.HDC:
                version_cmd = [tool_cmd, "-v"]
            else:
                version_cmd = [tool_cmd, "-ln"]

            result = subprocess.run(
                version_cmd,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                version_line = result.stdout.strip().split("\n")[0]
                print(f"✅ OK ({version_line if version_line else 'installed'})")
            else:
                print("❌ FAILED")
                print(f"   Error: {tool_name} command failed to run.")
                all_passed = False
        except FileNotFoundError:
            print("❌ FAILED")
            print(f"   Error: {tool_name} command not found.")
            all_passed = False
        except subprocess.TimeoutExpired:
            print("❌ FAILED")
            print(f"   Error: {tool_name} command timed out.")
            all_passed = False

    if not all_passed:
        print("-" * 50)
        print("❌ System check failed. Please fix the issues above.")
        return False

    print("2. Checking connected devices...", end=" ")
    try:
        if device_type == DeviceType.ADB:
            result = subprocess.run(
                ["adb", "devices"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            lines = result.stdout.strip().split("\n")
            devices = [
                line for line in lines[1:] if line.strip() and "\tdevice" in line
            ]
        elif device_type == DeviceType.HDC:
            result = subprocess.run(
                ["hdc", "list", "targets"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            lines = result.stdout.strip().split("\n")
            devices = [line for line in lines if line.strip()]
        else:
            ios_devices = list_ios_devices()
            devices = [d.device_id for d in ios_devices]

        if not devices:
            print("❌ FAILED")
            print("   Error: No devices connected.")
            print("   Solution:")
            if device_type == DeviceType.ADB:
                print("     1. Enable USB debugging on your Android device")
                print("     2. Connect via USB and authorize the connection")
                print("     3. Or connect remotely: python main.py --connect <ip>:<port>")
            elif device_type == DeviceType.HDC:
                print("     1. Enable USB debugging on your HarmonyOS device")
                print("     2. Connect via USB and authorize the connection")
                print(
                    "     3. Or connect remotely: python main.py --device-type hdc --connect <ip>:<port>"
                )
            else:
                print("     1. Connect your iOS device via USB")
                print("     2. Unlock device and tap 'Trust This Computer'")
                print("     3. Verify: idevice_id -l")
                print("     4. Or connect via WiFi using device IP")
            all_passed = False
        else:
            if device_type == DeviceType.ADB:
                device_ids = [d.split("\t")[0] for d in devices]
            elif device_type == DeviceType.HDC:
                device_ids = [d.strip() for d in devices]
            else:
                device_ids = devices

            if resolved_device_id and resolved_device_id not in device_ids:
                print("❌ FAILED")
                print(f"   Error: Target device is not connected: {resolved_device_id}")
                print("   Connected devices:")
                for current_device_id in device_ids[:5]:
                    print(f"     - {current_device_id}")
                all_passed = False
            else:
                target_suffix = f" | target: {resolved_device_id}" if resolved_device_id else ""
                print(
                    f"✅ OK ({len(devices)} device(s): {', '.join(device_ids[:2])}{'...' if len(device_ids) > 2 else ''}{target_suffix})"
                )
    except subprocess.TimeoutExpired:
        print("❌ FAILED")
        print(f"   Error: {tool_name} command timed out.")
        all_passed = False
    except Exception as exc:
        print("❌ FAILED")
        print(f"   Error: {exc}")
        all_passed = False

    if not all_passed:
        print("-" * 50)
        print("❌ System check failed. Please fix the issues above.")
        return False

    if device_type == DeviceType.ADB:
        print("3. Checking ADB Keyboard...", end=" ")
        try:
            target_device_id = resolved_device_id
            if not target_device_id:
                if len(device_ids) == 1:
                    target_device_id = device_ids[0]
                elif len(device_ids) > 1:
                    print("❌ FAILED")
                    print(
                        "   Error: Multiple ADB devices are connected, so the target device for ADB Keyboard check is ambiguous."
                    )
                    print("   Solution:")
                    print("     1. Re-run with: python main.py --device-id <device_id> ...")
                    print("     2. Or disconnect extra devices and try again")
                    all_passed = False
                    target_device_id = None

            if target_device_id:
                package_result = subprocess.run(
                    ["adb", "-s", target_device_id, "shell", "pm", "list", "packages", "com.android.adbkeyboard"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if package_result.returncode != 0:
                    raise RuntimeError((package_result.stderr or package_result.stdout).strip() or "adb pm list packages failed")

                ime_result = subprocess.run(
                    ["adb", "-s", target_device_id, "shell", "ime", "list", "-s"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if ime_result.returncode != 0:
                    raise RuntimeError((ime_result.stderr or ime_result.stdout).strip() or "adb ime list failed")

                package_output = ((package_result.stdout or "") + (package_result.stderr or "")).strip()
                ime_list = ((ime_result.stdout or "") + (ime_result.stderr or "")).strip()
                installed = "com.android.adbkeyboard" in package_output
                enabled = "com.android.adbkeyboard/.AdbIME" in ime_list

                if enabled:
                    print(f"✅ OK ({target_device_id})")
                elif installed:
                    print("❌ FAILED")
                    print(f"   Error: ADB Keyboard is installed but not enabled on device {target_device_id}.")
                    print("   Solution:")
                    print("     1. Open Settings > System > Languages & Input > Virtual Keyboard")
                    print("     2. Enable ADB Keyboard")
                    print("     3. Re-run the system check")
                    all_passed = False
                else:
                    print("❌ FAILED")
                    print(f"   Error: ADB Keyboard is not installed on device {target_device_id}.")
                    print("   Solution:")
                    print("     1. Download ADB Keyboard APK from:")
                    print(
                        "        https://github.com/senzhk/ADBKeyBoard/blob/master/ADBKeyboard.apk"
                    )
                    print(f"     2. Install it on your device: adb -s {target_device_id} install ADBKeyboard.apk")
                    print(
                        "     3. Enable it in Settings > System > Languages & Input > Virtual Keyboard"
                    )
                    all_passed = False
        except subprocess.TimeoutExpired:
            print("❌ FAILED")
            print("   Error: ADB command timed out.")
            all_passed = False
        except Exception as exc:
            print("❌ FAILED")
            print(f"   Error: {exc}")
            all_passed = False
    elif device_type == DeviceType.HDC:
        print("3. Skipping keyboard check for HarmonyOS...", end=" ")
        print("✅ OK (using native input)")
    else:
        print(f"3. Checking WebDriverAgent ({wda_url})...", end=" ")
        try:
            conn = XCTestConnection(wda_url=wda_url)

            if conn.is_wda_ready():
                print("✅ OK")
                status = conn.get_wda_status()
                if status:
                    session_id = status.get("sessionId", "N/A")
                    print(f"   Session ID: {session_id}")
            else:
                print("❌ FAILED")
                print("   Error: WebDriverAgent is not running or not accessible.")
                print("   Solution:")
                print("     1. Run WebDriverAgent on your iOS device via Xcode")
                print("     2. For USB: Set up port forwarding: iproxy 8100 8100")
                print(
                    "     3. For WiFi: Use device IP, e.g., --wda-url http://192.168.1.100:8100"
                )
                print("     4. Verify in browser: open http://localhost:8100/status")
                all_passed = False
        except Exception as exc:
            print("❌ FAILED")
            print(f"   Error: {exc}")
            all_passed = False

    print("-" * 50)

    if all_passed:
        print("✅ All system checks passed!\n")
    else:
        print("❌ System check failed. Please fix the issues above.")

    return all_passed



def check_model_api(base_url: str, model_name: str, api_key: str = "EMPTY") -> bool:
    """检查模型 API 是否可用且目标模型可访问。"""
    print("🔍 Checking model API...")
    print("-" * 50)

    all_passed = True

    print(f"1. Checking API connectivity ({base_url})...", end=" ")
    try:
        client = OpenAI(base_url=base_url, api_key=api_key, timeout=30.0)
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=5,
            temperature=0.0,
            stream=False,
        )

        if response.choices and len(response.choices) > 0:
            print("✅ OK")
        else:
            print("❌ FAILED")
            print("   Error: Received empty response from API")
            all_passed = False

    except Exception as exc:
        print("❌ FAILED")
        error_msg = str(exc)

        if "Connection refused" in error_msg or "Connection error" in error_msg:
            print(f"   Error: Cannot connect to {base_url}")
            print("   Solution:")
            print("     1. Check if the model server is running")
            print("     2. Verify the base URL is correct")
            print(f"     3. Try: curl {base_url}/chat/completions")
        elif "timed out" in error_msg.lower() or "timeout" in error_msg.lower():
            print(f"   Error: Connection to {base_url} timed out")
            print("   Solution:")
            print("     1. Check your network connection")
            print("     2. Verify the server is responding")
        elif (
            "Name or service not known" in error_msg
            or "nodename nor servname" in error_msg
        ):
            print("   Error: Cannot resolve hostname")
            print("   Solution:")
            print("     1. Check the URL is correct")
            print("     2. Verify DNS settings")
        else:
            print(f"   Error: {error_msg}")

        all_passed = False

    print("-" * 50)

    if all_passed:
        print("✅ Model API checks passed!\n")
    else:
        print("❌ Model API check failed. Please fix the issues above.")

    return all_passed
