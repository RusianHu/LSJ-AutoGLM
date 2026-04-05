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
import sys
from urllib.parse import urlparse

from cli.action_policy import (
    build_action_policy_from_args,
    parse_cli_action_collection,
)
from cli.device_commands import (
    handle_device_commands as cli_handle_device_commands,
    handle_ios_device_commands as cli_handle_ios_device_commands,
)
from cli.system_checks import (
    check_model_api as cli_check_model_api,
    check_system_requirements as cli_check_system_requirements,
)
from phone_agent import PhoneAgent
from phone_agent.actions.registry import ACTION_POLICY_VERSION
from phone_agent.agent import AgentConfig
from phone_agent.agent_ios import IOSAgentConfig, IOSPhoneAgent
from phone_agent.config.apps import list_supported_apps
from phone_agent.config.apps_harmonyos import list_supported_apps as list_harmonyos_apps
from phone_agent.config.apps_ios import list_supported_apps as list_ios_apps
from phone_agent.device_factory import DeviceType, get_device_factory, set_device_type
from phone_agent.model import ExpertConfig, ModelConfig
from phone_agent.xctest import list_devices as list_ios_devices


def check_system_requirements(
    device_type: DeviceType = DeviceType.ADB,
    wda_url: str = "http://localhost:8100",
    device_id: str | None = None,
) -> bool:
    """兼容包装：委托给 [`cli_check_system_requirements()`](cli/system_checks.py:17)。"""
    return cli_check_system_requirements(
        device_type=device_type,
        wda_url=wda_url,
        device_id=device_id,
    )



def check_model_api(base_url: str, model_name: str, api_key: str = "EMPTY") -> bool:
    """兼容包装：委托给 [`cli_check_model_api()`](cli/system_checks.py:221)。"""
    return cli_check_model_api(base_url=base_url, model_name=model_name, api_key=api_key)

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
    """兼容包装：委托给 [`parse_cli_action_collection()`](cli/action_policy.py:16)。"""
    return parse_cli_action_collection(raw_value, option_name)



def _build_action_policy_from_args(args: argparse.Namespace, platform: str):
    """兼容包装：委托给 [`build_action_policy_from_args()`](cli/action_policy.py:31)。"""
    return build_action_policy_from_args(args, platform)



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

    # Runtime user instruction inbox (GUI bridge)
    parser.add_argument(
        "--runtime-inbox-path",
        type=str,
        default=None,
        help="[Internal] Path to a JSONL inbox file for runtime user instructions injected by GUI.",
    )

    return parser.parse_args()


def handle_ios_device_commands(args) -> bool:
    """兼容包装：委托给 [`cli_handle_ios_device_commands()`](cli/device_commands.py:12)。"""
    return cli_handle_ios_device_commands(args)



def handle_device_commands(args) -> bool:
    """兼容包装：委托给 [`cli_handle_device_commands()`](cli/device_commands.py:80)。"""
    return cli_handle_device_commands(args, device_factory=get_device_factory())

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
        device_id=args.device_id,
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
            runtime_inbox_path=getattr(args, "runtime_inbox_path", None) or None,
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
            runtime_inbox_path=getattr(args, "runtime_inbox_path", None) or None,
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
