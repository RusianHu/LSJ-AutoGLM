# -*- coding: utf-8 -*-
"""CLI 设备命令处理。"""

from __future__ import annotations

from phone_agent.device_factory import DeviceType, get_device_factory
from phone_agent.xctest import XCTestConnection
from phone_agent.xctest import list_devices as list_ios_devices



def handle_ios_device_commands(args) -> bool:
    """处理 iOS 设备相关命令。"""
    conn = XCTestConnection(wda_url=args.wda_url)

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

    if args.pair:
        print("Pairing with iOS device...")
        success, message = conn.pair_device(args.device_id)
        print(f"{'✓' if success else '✗'} {message}")
        return True

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
            print("  4. For USB: Run port forwarding: iproxy 8100 8100")

        return True

    return False



def handle_device_commands(args, *, device_factory=None) -> bool:
    """处理设备相关命令。"""
    device_type = (
        DeviceType.ADB
        if args.device_type == "adb"
        else (DeviceType.HDC if args.device_type == "hdc" else DeviceType.IOS)
    )

    if device_type == DeviceType.IOS:
        return handle_ios_device_commands(args)

    device_factory = device_factory or get_device_factory()
    connection_class = device_factory.get_connection_class()
    conn = connection_class()

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

    if args.connect:
        print(f"Connecting to {args.connect}...")
        success, message = conn.connect(args.connect)
        print(f"{'✓' if success else '✗'} {message}")
        if success:
            args.device_id = args.connect
        return True

    if args.disconnect:
        if args.disconnect == "all":
            print("Disconnecting all remote devices...")
            success, message = conn.disconnect()
        else:
            print(f"Disconnecting from {args.disconnect}...")
            success, message = conn.disconnect(args.disconnect)
        print(f"{'✓' if success else '✗'} {message}")
        return True

    if args.enable_tcpip:
        port = args.enable_tcpip
        print(f"Enabling TCP/IP debugging on port {port}...")

        success, message = conn.enable_tcpip(port, args.device_id)
        print(f"{'✓' if success else '✗'} {message}")

        if success:
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
