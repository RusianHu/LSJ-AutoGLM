#!/usr/bin/env python3
"""
Phone Agent CLI - AI-powered phone automation.

Usage:
    python main.py [OPTIONS]

Environment Variables:
    PHONE_AGENT_BASE_URL: Model API base URL (default: http://localhost:8000/v1)
    PHONE_AGENT_MODEL: Model name (default: autoglm-phone-9b)
    PHONE_AGENT_API_KEY: API key for model authentication (default: EMPTY)
    PHONE_AGENT_MAX_STEPS: Maximum steps per task (default: 100)
    PHONE_AGENT_DEVICE_ID: ADB device ID for multi-device setups
"""

import argparse
import os
import shutil
import subprocess
import sys
from urllib.parse import urlparse

from openai import OpenAI

from phone_agent import PhoneAgent
from phone_agent.actions.registry import (
    ACTION_POLICY_VERSION,
    ActionPolicyInput,
    canonicalize_action_name,
    get_supported_action_names,
    parse_action_name_collection,
    resolve_action_policy,
)
from phone_agent.agent import AgentConfig
from phone_agent.agent_ios import IOSAgentConfig, IOSPhoneAgent
from phone_agent.config.apps import list_supported_apps
from phone_agent.config.apps_harmonyos import list_supported_apps as list_harmonyos_apps
from phone_agent.config.apps_ios import list_supported_apps as list_ios_apps
from phone_agent.device_factory import DeviceType, get_device_factory, set_device_type
from phone_agent.model import ExpertConfig, ModelConfig
from phone_agent.xctest import XCTestConnection
from phone_agent.xctest import list_devices as list_ios_devices


def check_system_requirements(
    device_type: DeviceType = DeviceType.ADB, wda_url: str = "http://localhost:8100"
) -> bool:
    """
    Check system requirements before running the agent.

    Checks:
    1. ADB/HDC/iOS tools installed
    2. At least one device connected
    3. ADB Keyboard installed on the device (for ADB only)
    4. WebDriverAgent running (for iOS only)

    Args:
        device_type: Type of device tool (ADB, HDC, or IOS).
        wda_url: WebDriverAgent URL (for iOS only).

    Returns:
        True if all checks pass, False otherwise.
    """
    print("🔍 Checking system requirements...")
    print("-" * 50)

    all_passed = True

    # Determine tool name and command
    if device_type == DeviceType.IOS:
        tool_name = "libimobiledevice"
        tool_cmd = "idevice_id"
    else:
        tool_name = "ADB" if device_type == DeviceType.ADB else "HDC"
        tool_cmd = "adb" if device_type == DeviceType.ADB else "hdc"

    # Check 1: Tool installed
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
        else:  # IOS
            print("     - macOS: brew install libimobiledevice")
            print("     - Linux: sudo apt-get install libimobiledevice-utils")
        all_passed = False
    else:
        # Double check by running version command
        try:
            if device_type == DeviceType.ADB:
                version_cmd = [tool_cmd, "version"]
            elif device_type == DeviceType.HDC:
                version_cmd = [tool_cmd, "-v"]
            else:  # IOS
                version_cmd = [tool_cmd, "-ln"]

            result = subprocess.run(
                version_cmd, capture_output=True, text=True, timeout=10
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

    # If ADB is not installed, skip remaining checks
    if not all_passed:
        print("-" * 50)
        print("❌ System check failed. Please fix the issues above.")
        return False

    # Check 2: Device connected
    print("2. Checking connected devices...", end=" ")
    try:
        if device_type == DeviceType.ADB:
            result = subprocess.run(
                ["adb", "devices"], capture_output=True, text=True, timeout=10
            )
            lines = result.stdout.strip().split("\n")
            # Filter out header and empty lines, look for 'device' status
            devices = [
                line for line in lines[1:] if line.strip() and "\tdevice" in line
            ]
        elif device_type == DeviceType.HDC:
            result = subprocess.run(
                ["hdc", "list", "targets"], capture_output=True, text=True, timeout=10
            )
            lines = result.stdout.strip().split("\n")
            devices = [line for line in lines if line.strip()]
        else:  # IOS
            ios_devices = list_ios_devices()
            devices = [d.device_id for d in ios_devices]

        if not devices:
            print("❌ FAILED")
            print("   Error: No devices connected.")
            print("   Solution:")
            if device_type == DeviceType.ADB:
                print("     1. Enable USB debugging on your Android device")
                print("     2. Connect via USB and authorize the connection")
                print(
                    "     3. Or connect remotely: python main.py --connect <ip>:<port>"
                )
            elif device_type == DeviceType.HDC:
                print("     1. Enable USB debugging on your HarmonyOS device")
                print("     2. Connect via USB and authorize the connection")
                print(
                    "     3. Or connect remotely: python main.py --device-type hdc --connect <ip>:<port>"
                )
            else:  # IOS
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
            else:  # IOS
                device_ids = devices
            print(
                f"✅ OK ({len(devices)} device(s): {', '.join(device_ids[:2])}{'...' if len(device_ids) > 2 else ''})"
            )
    except subprocess.TimeoutExpired:
        print("❌ FAILED")
        print(f"   Error: {tool_name} command timed out.")
        all_passed = False
    except Exception as e:
        print("❌ FAILED")
        print(f"   Error: {e}")
        all_passed = False

    # If no device connected, skip ADB Keyboard check
    if not all_passed:
        print("-" * 50)
        print("❌ System check failed. Please fix the issues above.")
        return False

    # Check 3: ADB Keyboard installed (only for ADB) or WebDriverAgent (for iOS)
    if device_type == DeviceType.ADB:
        print("3. Checking ADB Keyboard...", end=" ")
        try:
            result = subprocess.run(
                ["adb", "shell", "ime", "list", "-s"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            ime_list = result.stdout.strip()

            if "com.android.adbkeyboard/.AdbIME" in ime_list:
                print("✅ OK")
            else:
                print("❌ FAILED")
                print("   Error: ADB Keyboard is not installed on the device.")
                print("   Solution:")
                print("     1. Download ADB Keyboard APK from:")
                print(
                    "        https://github.com/senzhk/ADBKeyBoard/blob/master/ADBKeyboard.apk"
                )
                print("     2. Install it on your device: adb install ADBKeyboard.apk")
                print(
                    "     3. Enable it in Settings > System > Languages & Input > Virtual Keyboard"
                )
                all_passed = False
        except subprocess.TimeoutExpired:
            print("❌ FAILED")
            print("   Error: ADB command timed out.")
            all_passed = False
        except Exception as e:
            print("❌ FAILED")
            print(f"   Error: {e}")
            all_passed = False
    elif device_type == DeviceType.HDC:
        # For HDC, skip keyboard check as it uses different input method
        print("3. Skipping keyboard check for HarmonyOS...", end=" ")
        print("✅ OK (using native input)")
    else:  # IOS
        # Check WebDriverAgent
        print(f"3. Checking WebDriverAgent ({wda_url})...", end=" ")
        try:
            conn = XCTestConnection(wda_url=wda_url)

            if conn.is_wda_ready():
                print("✅ OK")
                # Get WDA status for additional info
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
        except Exception as e:
            print("❌ FAILED")
            print(f"   Error: {e}")
            all_passed = False

    print("-" * 50)

    if all_passed:
        print("✅ All system checks passed!\n")
    else:
        print("❌ System check failed. Please fix the issues above.")

    return all_passed


def check_model_api(base_url: str, model_name: str, api_key: str = "EMPTY") -> bool:
    """
    Check if the model API is accessible and the specified model exists.

    Checks:
    1. Network connectivity to the API endpoint
    2. Model exists in the available models list

    Args:
        base_url: The API base URL
        model_name: The model name to check
        api_key: The API key for authentication

    Returns:
        True if all checks pass, False otherwise.
    """
    print("🔍 Checking model API...")
    print("-" * 50)

    all_passed = True

    # Check 1: Network connectivity using chat API
    print(f"1. Checking API connectivity ({base_url})...", end=" ")
    try:
        # Create OpenAI client
        client = OpenAI(base_url=base_url, api_key=api_key, timeout=30.0)

        # Use chat completion to test connectivity (more universally supported than /models)
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=5,
            temperature=0.0,
            stream=False,
        )

        # Check if we got a valid response
        if response.choices and len(response.choices) > 0:
            print("✅ OK")
        else:
            print("❌ FAILED")
            print("   Error: Received empty response from API")
            all_passed = False

    except Exception as e:
        print("❌ FAILED")
        error_msg = str(e)

        # Provide more specific error messages
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
            print(f"   Error: Cannot resolve hostname")
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


def _env_truthy(primary_key: str, fallback_key: str | None = None, default: str = "") -> bool:
    raw = os.getenv(primary_key)
    if raw is None and fallback_key:
        raw = os.getenv(fallback_key)
    if raw is None:
        raw = default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")



def _env_value(primary_key: str, fallback_key: str | None = None, default: str = "") -> str:
    value = os.getenv(primary_key)
    if value in (None, "") and fallback_key:
        value = os.getenv(fallback_key)
    if value is None:
        value = default
    return value



def _parse_cli_action_collection(raw_value: str | None, option_name: str) -> tuple[str, ...] | None:
    if raw_value is None:
        return None
    try:
        return parse_action_name_collection(raw_value)
    except ValueError as exc:
        raise ValueError(f"{option_name} 格式无效：{exc}") from exc



def _build_action_policy_from_args(args: argparse.Namespace, platform: str):
    runtime_actions = _parse_cli_action_collection(args.enabled_actions, "--enabled-actions")
    ai_visible_actions = _parse_cli_action_collection(args.ai_visible_actions, "--ai-visible-actions")

    policy = ActionPolicyInput(
        ai_visible_actions=ai_visible_actions,
        runtime_enabled_actions=runtime_actions,
        policy_version=args.action_policy_version,
        use_platform_defaults=args.use_platform_default_actions,
    )

    resolved = resolve_action_policy(platform, policy)
    supported_actions = set(get_supported_action_names(platform))

    if resolved.unknown_actions:
        raise ValueError(f"未知动作名：{', '.join(resolved.unknown_actions)}")

    if runtime_actions is None and not args.use_platform_default_actions:
        raise ValueError(
            "运行时启用动作集合未提供，且已禁用平台默认动作回退。请至少指定一个动作集合（允许显式传 []），或开启平台默认动作。"
        )

    if ai_visible_actions is None and not args.use_platform_default_actions:
        raise ValueError(
            "AI 可见动作集合未提供，且已禁用平台默认动作回退。请至少指定一个 AI 可见动作集合（允许显式传 []），或开启平台默认动作。"
        )

    if runtime_actions:
        unsupported_runtime = [name for name in runtime_actions if canonicalize_action_name(name) not in supported_actions]
        if unsupported_runtime:
            raise ValueError(
                f"平台 {platform} 不支持这些运行时动作：{', '.join(unsupported_runtime)}"
            )

    if ai_visible_actions:
        unsupported_ai = [name for name in ai_visible_actions if canonicalize_action_name(name) not in supported_actions]
        if unsupported_ai:
            raise ValueError(
                f"平台 {platform} 不支持这些 AI 可见动作：{', '.join(unsupported_ai)}"
            )

        runtime_enabled_set = set(resolved.runtime_enabled_actions)
        not_enabled_for_runtime = [
            name for name in ai_visible_actions if canonicalize_action_name(name) in supported_actions and canonicalize_action_name(name) not in runtime_enabled_set
        ]
        if not_enabled_for_runtime:
            raise ValueError(
                "以下 AI 可见动作未包含在运行时启用集合中："
                + ", ".join(not_enabled_for_runtime)
            )

    return policy, resolved



def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Phone Agent - AI-powered phone automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run with default settings (Android)
    python main.py

    # Specify model endpoint
    python main.py --base-url http://localhost:8000/v1

    # Use API key for authentication
    python main.py --apikey sk-xxxxx

    # Run with specific device
    python main.py --device-id emulator-5554

    # Connect to remote device
    python main.py --connect 192.168.1.100:5555

    # List connected devices
    python main.py --list-devices

    # Enable TCP/IP on USB device and get connection info
    python main.py --enable-tcpip

    # List supported apps
    python main.py --list-apps

    # Restrict runtime actions explicitly
    python main.py --enabled-actions '["Launch", "Tap", "Type", "Swipe", "Back", "Home", "Wait", "Note", "Take_over"]'

    # iOS specific examples
    # Run with iOS device
    python main.py --device-type ios "Open Safari and search for iPhone tips"

    # Use WiFi connection for iOS
    python main.py --device-type ios --wda-url http://192.168.1.100:8100

    # List connected iOS devices
    python main.py --device-type ios --list-devices

    # Check WebDriverAgent status
    python main.py --device-type ios --wda-status

    # Pair with iOS device
    python main.py --device-type ios --pair
        """,
    )

    # Model options
    parser.add_argument(
        "--base-url",
        type=str,
        default=os.getenv("PHONE_AGENT_BASE_URL", "http://localhost:8000/v1"),
        help="Model API base URL",
    )

    parser.add_argument(
        "--model",
        type=str,
        default=os.getenv("PHONE_AGENT_MODEL", "autoglm-phone-9b"),
        help="Model name",
    )

    parser.add_argument(
        "--apikey",
        type=str,
        default=os.getenv("PHONE_AGENT_API_KEY", "EMPTY"),
        help="API key for model authentication",
    )

    parser.add_argument(
        "--max-steps",
        type=int,
        default=int(os.getenv("PHONE_AGENT_MAX_STEPS", "100")),
        help="Maximum steps per task",
    )

    # Device options
    parser.add_argument(
        "--device-id",
        "-d",
        type=str,
        default=os.getenv("PHONE_AGENT_DEVICE_ID"),
        help="ADB device ID",
    )

    parser.add_argument(
        "--connect",
        "-c",
        type=str,
        metavar="ADDRESS",
        help="Connect to remote device (e.g., 192.168.1.100:5555)",
    )

    parser.add_argument(
        "--disconnect",
        type=str,
        nargs="?",
        const="all",
        metavar="ADDRESS",
        help="Disconnect from remote device (or 'all' to disconnect all)",
    )

    parser.add_argument(
        "--list-devices", action="store_true", help="List connected devices and exit"
    )

    parser.add_argument(
        "--enable-tcpip",
        type=int,
        nargs="?",
        const=5555,
        metavar="PORT",
        help="Enable TCP/IP debugging on USB device (default port: 5555)",
    )

    # iOS specific options
    parser.add_argument(
        "--wda-url",
        type=str,
        default=os.getenv("PHONE_AGENT_WDA_URL", "http://localhost:8100"),
        help="WebDriverAgent URL for iOS (default: http://localhost:8100)",
    )

    parser.add_argument(
        "--pair",
        action="store_true",
        help="Pair with iOS device (required for some operations)",
    )

    parser.add_argument(
        "--wda-status",
        action="store_true",
        help="Show WebDriverAgent status and exit (iOS only)",
    )

    # Other options
    parser.add_argument(
        "--quiet", "-q", action="store_true", help="Suppress verbose output"
    )

    parser.add_argument(
        "--list-apps", action="store_true", help="List supported apps and exit"
    )

    parser.add_argument(
        "--list-device-apps",
        action="store_true",
        help="List launchable Android package/activity entries discovered on the connected device and exit",
    )

    parser.add_argument(
        "--find-app",
        type=str,
        metavar="QUERY",
        help="Search installed Android package/activity entries on the connected device and exit",
    )

    parser.add_argument(
        "--lang",
        type=str,
        choices=["cn", "en"],
        default=os.getenv("PHONE_AGENT_LANG", "cn"),
        help="Language for system prompt (cn or en, default: cn)",
    )

    parser.add_argument(
        "--thirdparty",
        action="store_true",
        default=os.getenv("PHONE_AGENT_THIRDPARTY", "").lower() == "true",
        help="Use thirdparty prompt engineering for non-AutoGLM models (e.g., Qwen3-VL)",
    )

    thirdparty_thinking_group = parser.add_mutually_exclusive_group()
    thirdparty_thinking_group.add_argument(
        "--thirdparty-thinking",
        dest="thirdparty_thinking",
        action="store_true",
        default=None,
        help="Enable <think>/<answer> output format in thirdparty mode (default: enabled)",
    )
    thirdparty_thinking_group.add_argument(
        "--thirdparty-no-thinking",
        dest="thirdparty_thinking",
        action="store_false",
        default=None,
        help="Disable <think>/<answer> output format in thirdparty mode (fallback to action-only)",
    )

    parser.add_argument(
        "--compress-image",
        action="store_true",
        default=os.getenv("PHONE_AGENT_COMPRESS_IMAGE", "").lower() == "true",
        help="Enable screenshot compression in thirdparty mode (some APIs are sensitive to large images)",
    )

    parser.add_argument(
        "--no-compress-image",
        action="store_true",
        default=os.getenv("PHONE_AGENT_NO_COMPRESS_IMAGE", "").lower() == "true",
        help="Disable screenshot compression in thirdparty mode (default in thirdparty mode; useful if UI recognition is poor)",
    )

    parser.add_argument(
        "--device-type",
        type=str,
        choices=["adb", "hdc", "ios"],
        default=os.getenv("PHONE_AGENT_DEVICE_TYPE", "adb"),
        help="Device type: adb for Android, hdc for HarmonyOS, ios for iPhone (default: adb)",
    )

    parser.add_argument(
        "--expert-mode",
        action="store_true",
        default=_env_truthy("PHONE_AGENT_EXPERT_MODE", "OPEN_AUTOGLM_EXPERT_MODE", "false"),
        help="Enable expert guidance mode with a dedicated multimodal expert model.",
    )
    parser.add_argument(
        "--expert-base-url",
        type=str,
        default=_env_value("PHONE_AGENT_EXPERT_BASE_URL", "OPEN_AUTOGLM_EXPERT_BASE_URL", ""),
        help="Expert model API base URL.",
    )
    parser.add_argument(
        "--expert-model",
        type=str,
        default=_env_value("PHONE_AGENT_EXPERT_MODEL", "OPEN_AUTOGLM_EXPERT_MODEL", ""),
        help="Expert model name.",
    )
    parser.add_argument(
        "--expert-apikey",
        type=str,
        default=_env_value("PHONE_AGENT_EXPERT_API_KEY", "OPEN_AUTOGLM_EXPERT_API_KEY", ""),
        help="API key for the expert model.",
    )
    parser.add_argument(
        "--expert-prompt",
        type=str,
        default=_env_value("PHONE_AGENT_EXPERT_PROMPT", "OPEN_AUTOGLM_EXPERT_PROMPT", ""),
        help="Optional custom expert prompt.",
    )
    parser.add_argument(
        "--expert-strict-mode",
        action="store_true",
        default=_env_truthy("PHONE_AGENT_EXPERT_STRICT_MODE", "OPEN_AUTOGLM_EXPERT_STRICT_MODE", "false"),
        help="Force an expert consultation before every main-model decision step.",
    )
    expert_auto_init_group = parser.add_mutually_exclusive_group()
    expert_auto_init_group.add_argument(
        "--expert-auto-init",
        dest="expert_auto_init",
        action="store_true",
        default=_env_truthy("PHONE_AGENT_EXPERT_AUTO_INIT", "OPEN_AUTOGLM_EXPERT_AUTO_INIT", "true"),
        help="Request expert guidance before the first main-model step.",
    )
    expert_auto_init_group.add_argument(
        "--expert-no-auto-init",
        dest="expert_auto_init",
        action="store_false",
        help="Disable automatic expert guidance on task initialization.",
    )
    expert_auto_rescue_group = parser.add_mutually_exclusive_group()
    expert_auto_rescue_group.add_argument(
        "--expert-auto-rescue",
        dest="expert_auto_rescue",
        action="store_true",
        default=_env_truthy("PHONE_AGENT_EXPERT_AUTO_RESCUE", "OPEN_AUTOGLM_EXPERT_AUTO_RESCUE", "true"),
        help="Enable automatic expert rescue when the agent appears stuck.",
    )
    expert_auto_rescue_group.add_argument(
        "--expert-no-auto-rescue",
        dest="expert_auto_rescue",
        action="store_false",
        help="Disable automatic expert rescue.",
    )
    expert_manual_action_group = parser.add_mutually_exclusive_group()
    expert_manual_action_group.add_argument(
        "--expert-manual-action",
        dest="expert_manual_action",
        action="store_true",
        default=_env_truthy("PHONE_AGENT_EXPERT_MANUAL_ACTION", "OPEN_AUTOGLM_EXPERT_MANUAL_ACTION", "true"),
        help="Allow Ask_AI action to request expert assistance explicitly.",
    )
    expert_manual_action_group.add_argument(
        "--expert-no-manual-action",
        dest="expert_manual_action",
        action="store_false",
        help="Disable Ask_AI explicit expert assistance action.",
    )
    parser.add_argument(
        "--expert-screen-unchanged-threshold",
        type=int,
        default=int(_env_value("PHONE_AGENT_EXPERT_SCREEN_UNCHANGED_THRESHOLD", "OPEN_AUTOGLM_EXPERT_SCREEN_UNCHANGED_THRESHOLD", "4")),
        help="Trigger automatic expert rescue after this many unchanged-screen steps.",
    )
    parser.add_argument(
        "--expert-consecutive-failure-threshold",
        type=int,
        default=int(_env_value("PHONE_AGENT_EXPERT_CONSECUTIVE_FAILURE_THRESHOLD", "OPEN_AUTOGLM_EXPERT_CONSECUTIVE_FAILURE_THRESHOLD", "3")),
        help="Trigger automatic expert rescue after this many consecutive failures.",
    )
    parser.add_argument(
        "--expert-max-rescues",
        type=int,
        default=int(_env_value("PHONE_AGENT_EXPERT_MAX_RESCUES", "OPEN_AUTOGLM_EXPERT_MAX_RESCUES", "3")),
        help="Maximum automatic expert rescue attempts per task.",
    )

    parser.add_argument(
        "--enabled-actions",
        type=str,
        default=_env_value("PHONE_AGENT_ENABLED_ACTIONS", "OPEN_AUTOGLM_ENABLED_ACTIONS"),
        help="Runtime enabled action whitelist. Supports JSON array or comma separated names.",
    )

    parser.add_argument(
        "--ai-visible-actions",
        type=str,
        default=_env_value("PHONE_AGENT_AI_VISIBLE_ACTIONS", "OPEN_AUTOGLM_AI_VISIBLE_ACTIONS"),
        help="AI-visible action whitelist. Supports JSON array or comma separated names.",
    )

    parser.add_argument(
        "--action-policy-version",
        type=int,
        default=int(_env_value("PHONE_AGENT_ACTION_POLICY_VERSION", "OPEN_AUTOGLM_ACTION_POLICY_VERSION", str(ACTION_POLICY_VERSION))),
        help="Action policy schema version.",
    )

    platform_default_group = parser.add_mutually_exclusive_group()
    platform_default_group.add_argument(
        "--use-platform-default-actions",
        dest="use_platform_default_actions",
        action="store_true",
        default=_env_truthy(
            "PHONE_AGENT_USE_PLATFORM_DEFAULT_ACTIONS",
            "OPEN_AUTOGLM_USE_PLATFORM_DEFAULT_ACTIONS",
            "true",
        ),
        help="Fallback to platform default action sets when explicit whitelists are empty.",
    )
    platform_default_group.add_argument(
        "--disable-platform-default-actions",
        dest="use_platform_default_actions",
        action="store_false",
        help="Disable platform default action fallback and require explicit action sets.",
    )

    parser.add_argument(
        "task",
        nargs="?",
        type=str,
        help="Task to execute (interactive mode if not provided)",
    )

    return parser.parse_args()


def handle_ios_device_commands(args) -> bool:
    """
    Handle iOS device-related commands.

    Returns:
        True if a device command was handled (should exit), False otherwise.
    """
    conn = XCTestConnection(wda_url=args.wda_url)

    # Handle --list-devices
    if args.list_devices:
        devices = list_ios_devices()
        if not devices:
            print("No iOS devices connected.")
            print("\nTroubleshooting:")
            print("  1. Connect device via USB")
            print("  2. Unlock device and trust this computer")
            print("  3. Run: idevice_id -l")
        else:
            print("Connected iOS devices:")
            print("-" * 70)
            for device in devices:
                conn_type = device.connection_type.value
                model_info = f"{device.model}" if device.model else "Unknown"
                ios_info = f"iOS {device.ios_version}" if device.ios_version else ""
                name_info = device.device_name or "Unnamed"

                print(f"  ✓ {name_info}")
                print(f"    UUID: {device.device_id}")
                print(f"    Model: {model_info}")
                print(f"    OS: {ios_info}")
                print(f"    Connection: {conn_type}")
                print("-" * 70)
        return True

    # Handle --pair
    if args.pair:
        print("Pairing with iOS device...")
        success, message = conn.pair_device(args.device_id)
        print(f"{'✓' if success else '✗'} {message}")
        return True

    # Handle --wda-status
    if args.wda_status:
        print(f"Checking WebDriverAgent status at {args.wda_url}...")
        print("-" * 50)

        if conn.is_wda_ready():
            print("✓ WebDriverAgent is running")

            status = conn.get_wda_status()
            if status:
                print(f"\nStatus details:")
                value = status.get("value", {})
                print(f"  Session ID: {status.get('sessionId', 'N/A')}")
                print(f"  Build: {value.get('build', {}).get('time', 'N/A')}")

                current_app = value.get("currentApp", {})
                if current_app:
                    print(f"\nCurrent App:")
                    print(f"  Bundle ID: {current_app.get('bundleId', 'N/A')}")
                    print(f"  Process ID: {current_app.get('pid', 'N/A')}")
        else:
            print("✗ WebDriverAgent is not running")
            print("\nPlease start WebDriverAgent on your iOS device:")
            print("  1. Open WebDriverAgent.xcodeproj in Xcode")
            print("  2. Select your device")
            print("  3. Run WebDriverAgentRunner (Product > Test or Cmd+U)")
            print(f"  4. For USB: Run port forwarding: iproxy 8100 8100")

        return True

    return False


def handle_device_commands(args) -> bool:
    """
    Handle device-related commands.

    Returns:
        True if a device command was handled (should exit), False otherwise.
    """
    device_type = (
        DeviceType.ADB
        if args.device_type == "adb"
        else (DeviceType.HDC if args.device_type == "hdc" else DeviceType.IOS)
    )

    # Handle iOS-specific commands
    if device_type == DeviceType.IOS:
        return handle_ios_device_commands(args)

    device_factory = get_device_factory()
    ConnectionClass = device_factory.get_connection_class()
    conn = ConnectionClass()

    # Handle --list-devices
    if args.list_devices:
        devices = device_factory.list_devices()
        if not devices:
            print("No devices connected.")
        else:
            print("Connected devices:")
            print("-" * 60)
            for device in devices:
                status_icon = "✓" if device.status == "device" else "✗"
                conn_type = device.connection_type.value
                model_info = f" ({device.model})" if device.model else ""
                print(
                    f"  {status_icon} {device.device_id:<30} [{conn_type}]{model_info}"
                )
        return True

    if args.list_device_apps:
        if device_type != DeviceType.ADB:
            print("--list-device-apps is currently only supported for Android ADB devices.")
            return True

        apps = device_factory.list_installed_apps(args.device_id)
        if not apps:
            print("No launchable app packages found on the connected device.")
            return True

        print("Launchable package/activity entries discovered on device:")
        print("-" * 80)
        for app in sorted(apps, key=lambda item: item.package_name):
            activity = app.activity_name or "(unknown activity)"
            print(f"  - {app.package_name} [{activity}]")
        return True

    if args.find_app:
        if device_type != DeviceType.ADB:
            print("--find-app is currently only supported for Android ADB devices.")
            return True

        matches = device_factory.search_installed_apps(args.find_app, args.device_id)
        if not matches:
            print(f"No installed package matched: {args.find_app}")
            return True

        print(f"Matched package/activity entries ({len(matches)}):")
        print("-" * 80)
        for app in matches[:10]:
            print(f"  Package:  {app.package_name}")
            print(f"  Activity: {app.activity_name or '(unknown activity)'}")
            print("-" * 80)
        return True

    # Handle --connect
    if args.connect:
        print(f"Connecting to {args.connect}...")
        success, message = conn.connect(args.connect)
        print(f"{'✓' if success else '✗'} {message}")
        if success:
            # Set as default device
            args.device_id = args.connect
        return not success  # Continue if connection succeeded

    # Handle --disconnect
    if args.disconnect:
        if args.disconnect == "all":
            print("Disconnecting all remote devices...")
            success, message = conn.disconnect()
        else:
            print(f"Disconnecting from {args.disconnect}...")
            success, message = conn.disconnect(args.disconnect)
        print(f"{'✓' if success else '✗'} {message}")
        return True

    # Handle --enable-tcpip
    if args.enable_tcpip:
        port = args.enable_tcpip
        print(f"Enabling TCP/IP debugging on port {port}...")

        success, message = conn.enable_tcpip(port, args.device_id)
        print(f"{'✓' if success else '✗'} {message}")

        if success:
            # Try to get device IP
            ip = conn.get_device_ip(args.device_id)
            if ip:
                print(f"\nYou can now connect remotely using:")
                print(f"  python main.py --connect {ip}:{port}")
                print(f"\nOr via ADB directly:")
                print(f"  adb connect {ip}:{port}")
            else:
                print("\nCould not determine device IP. Check device WiFi settings.")
        return True

    return False


def main():
    """Main entry point."""
    args = parse_args()

    # Set device type globally based on args
    if args.device_type == "adb":
        device_type = DeviceType.ADB
    elif args.device_type == "hdc":
        device_type = DeviceType.HDC
    else:  # ios
        device_type = DeviceType.IOS

    # Set device type globally for non-iOS devices
    if device_type != DeviceType.IOS:
        set_device_type(device_type)

    try:
        action_policy, resolved_action_policy = _build_action_policy_from_args(
            args,
            args.device_type,
        )
    except ValueError as exc:
        print(f"Error: {exc}")
        sys.exit(2)

    # Enable HDC verbose mode if using HDC
    if device_type == DeviceType.HDC:
        from phone_agent.hdc import set_hdc_verbose

        set_hdc_verbose(True)

    # Handle --list-apps (no system check needed)
    if args.list_apps:
        if device_type == DeviceType.HDC:
            print("Supported HarmonyOS apps:")
            apps = list_harmonyos_apps()
        elif device_type == DeviceType.IOS:
            print("Supported iOS apps:")
            print("\nNote: For iOS apps, Bundle IDs are configured in:")
            print("  phone_agent/config/apps_ios.py")
            print("\nCurrently configured apps:")
            apps = list_ios_apps()
        else:
            print("Supported Android apps:")
            apps = list_supported_apps()

        for app in sorted(apps):
            print(f"  - {app}")

        if device_type == DeviceType.IOS:
            print(
                "\nTo add iOS apps, find the Bundle ID and add to APP_PACKAGES_IOS dictionary."
            )
        return

    # Handle device commands (these may need partial system checks)
    if handle_device_commands(args):
        return

    # Run system requirements check before proceeding
    if not check_system_requirements(
        device_type,
        wda_url=args.wda_url
        if device_type == DeviceType.IOS
        else "http://localhost:8100",
    ):
        sys.exit(1)

    # Check model API connectivity and model availability
    if not check_model_api(args.base_url, args.model, args.apikey):
        sys.exit(1)

    # Create configurations and agent based on device type
    model_config = ModelConfig(
        base_url=args.base_url,
        model_name=args.model,
        api_key=args.apikey,
        lang=args.lang,
    )

    expert_enabled = bool(args.expert_mode)
    expert_strict_mode = bool(args.expert_strict_mode) and expert_enabled
    expert_config = ExpertConfig(
        enabled=expert_enabled,
        base_url=args.expert_base_url,
        model_name=args.expert_model,
        api_key=args.expert_apikey,
        prompt=args.expert_prompt,
        auto_init=bool(args.expert_auto_init),
        auto_rescue=bool(args.expert_auto_rescue),
        manual_action=bool(args.expert_manual_action),
        strict_mode=expert_strict_mode,
        screen_unchanged_threshold=max(1, int(args.expert_screen_unchanged_threshold)),
        consecutive_failure_threshold=max(1, int(args.expert_consecutive_failure_threshold)),
        max_rescues=max(1, int(args.expert_max_rescues)),
        lang=args.lang,
    )

    if device_type == DeviceType.IOS:
        if args.thirdparty:
            print("Warning: --thirdparty is not supported on iOS yet; ignoring.")
        if args.expert_mode:
            print("Warning: expert mode is not supported on iOS yet; ignoring.")
        if args.expert_strict_mode:
            print("Warning: expert strict mode is not supported on iOS yet; ignoring.")

        # Create iOS agent
        agent_config = IOSAgentConfig(
            max_steps=args.max_steps,
            wda_url=args.wda_url,
            device_id=args.device_id,
            verbose=not args.quiet,
            lang=args.lang,
            action_policy=action_policy,
            runtime_action_policy=resolved_action_policy,
        )

        agent = IOSPhoneAgent(
            model_config=model_config,
            agent_config=agent_config,
        )
    else:
        # Create Android/HarmonyOS agent
        agent_config = AgentConfig(
            max_steps=args.max_steps,
            device_id=args.device_id,
            verbose=not args.quiet,
            lang=args.lang,
            use_thirdparty_prompt=args.thirdparty,
            thirdparty_thinking=(
                True
                if args.thirdparty and args.thirdparty_thinking is None
                else bool(args.thirdparty_thinking)
            ),
            platform=args.device_type,
            action_policy=action_policy,
            runtime_action_policy=resolved_action_policy,
            expert_config=expert_config,
        )

        # 第三方模式截图压缩开关：
        # - CLI 默认：不压缩（与 launcher.py 行为一致）
        # - 显式开启：--compress-image 或 PHONE_AGENT_COMPRESS_IMAGE=true
        # - 显式关闭：--no-compress-image 或 PHONE_AGENT_NO_COMPRESS_IMAGE=true
        if args.thirdparty:
            argv = set(sys.argv[1:])
            flag_compress = "--compress-image" in argv
            flag_no_compress = "--no-compress-image" in argv

            if flag_compress and flag_no_compress:
                print(
                    "Error: --compress-image and --no-compress-image cannot be used together."
                )
                sys.exit(2)

            env_no_compress = (
                os.getenv("PHONE_AGENT_NO_COMPRESS_IMAGE", "").lower() == "true"
            )
            env_compress = (
                os.getenv("PHONE_AGENT_COMPRESS_IMAGE", "").lower() == "true"
            )

            if flag_compress:
                compress = True
            elif flag_no_compress:
                compress = False
            elif env_no_compress:
                compress = False
            elif env_compress:
                compress = True
            else:
                compress = False

            if compress:
                os.environ["PHONE_AGENT_COMPRESS_IMAGE"] = "true"
            else:
                if os.environ.get("PHONE_AGENT_COMPRESS_IMAGE", "").lower() == "true":
                    os.environ.pop("PHONE_AGENT_COMPRESS_IMAGE", None)

        agent = PhoneAgent(
            model_config=model_config,
            agent_config=agent_config,
        )

    # Print header
    print("=" * 50)
    if device_type == DeviceType.IOS:
        print("Phone Agent iOS - AI-powered iOS automation")
    else:
        print("Phone Agent - AI-powered phone automation")
    print("=" * 50)
    print(f"Model: {model_config.model_name}")
    print(f"Base URL: {model_config.base_url}")
    print(f"Max Steps: {agent_config.max_steps}")
    print(f"Language: {agent_config.lang}")
    print(f"Device Type: {args.device_type.upper()}")
    print(f"Action Policy Version: {resolved_action_policy.policy_version}")
    if device_type != DeviceType.IOS:
        print(f"Expert Mode: {'ON' if agent_config.expert_config and agent_config.expert_config.enabled else 'OFF'}")
        if agent_config.expert_config and agent_config.expert_config.enabled:
            print(f"Expert Strict Mode: {'ON' if agent_config.expert_config.strict_mode else 'OFF'}")
            print(f"Expert Model: {agent_config.expert_config.model_name}")
    print(
        "Runtime Actions: "
        + (", ".join(resolved_action_policy.runtime_enabled_actions) or "(none)")
    )
    print(
        "AI Visible Actions: "
        + (", ".join(resolved_action_policy.ai_visible_actions) or "(none)")
    )
    if args.thirdparty:
        print("Prompt Mode: 第三方模型适配 (Thirdparty)")

    # Show iOS-specific config
    if device_type == DeviceType.IOS:
        print(f"WDA URL: {args.wda_url}")

    # Show device info
    if device_type == DeviceType.IOS:
        devices = list_ios_devices()
        if agent_config.device_id:
            print(f"Device: {agent_config.device_id}")
        elif devices:
            device = devices[0]
            print(f"Device: {device.device_name or device.device_id[:16]}")
            if device.model and device.ios_version:
                print(f"        {device.model}, iOS {device.ios_version}")
    else:
        device_factory = get_device_factory()
        devices = device_factory.list_devices()
        if agent_config.device_id:
            print(f"Device: {agent_config.device_id}")
        elif devices:
            print(f"Device: {devices[0].device_id} (auto-detected)")

    print("=" * 50)

    # Run with provided task or enter interactive mode
    if args.task:
        print(f"\nTask: {args.task}\n")
        result = agent.run(args.task)
        print(f"\nResult: {result}")
    else:
        # Interactive mode
        print("\nEntering interactive mode. Type 'quit' to exit.\n")

        while True:
            try:
                task = input("Enter your task: ").strip()

                if task.lower() in ("quit", "exit", "q"):
                    print("Goodbye!")
                    break

                if not task:
                    continue

                print()
                result = agent.run(task)
                print(f"\nResult: {result}\n")
                agent.reset()

            except KeyboardInterrupt:
                print("\n\nInterrupted. Goodbye!")
                break
            except Exception as e:
                print(f"\nError: {e}\n")


if __name__ == "__main__":
    main()
