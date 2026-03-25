"""Device factory for selecting ADB or HDC based on device type."""

from dataclasses import dataclass
from enum import Enum
from typing import Any


@dataclass
class AppLaunchResult:
    """Detailed result for app launch attempts."""

    success: bool
    message: str | None = None
    package_name: str | None = None


class DeviceType(Enum):
    """Type of device connection tool."""

    ADB = "adb"
    HDC = "hdc"
    IOS = "ios"


class DeviceFactory:
    """
    Factory class for getting device-specific implementations.

    This allows the system to work with both Android (ADB) and HarmonyOS (HDC) devices.
    """

    def __init__(self, device_type: DeviceType = DeviceType.ADB):
        """
        Initialize the device factory.

        Args:
            device_type: The type of device to use (ADB or HDC).
        """
        self.device_type = device_type
        self._module = None

    @property
    def module(self):
        """Get the appropriate device module (adb or hdc)."""
        if self._module is None:
            if self.device_type == DeviceType.ADB:
                from phone_agent import adb

                self._module = adb
            elif self.device_type == DeviceType.HDC:
                from phone_agent import hdc

                self._module = hdc
            else:
                raise ValueError(f"Unknown device type: {self.device_type}")
        return self._module

    def get_screenshot(self, device_id: str | None = None, timeout: int = 10):
        """Get screenshot from device."""
        return self.module.get_screenshot(device_id, timeout)

    def get_current_app(self, device_id: str | None = None) -> str:
        """Get current app name."""
        return self.module.get_current_app(device_id)

    def tap(
        self, x: int, y: int, device_id: str | None = None, delay: float | None = None
    ):
        """Tap at coordinates."""
        return self.module.tap(x, y, device_id, delay)

    def double_tap(
        self, x: int, y: int, device_id: str | None = None, delay: float | None = None
    ):
        """Double tap at coordinates."""
        return self.module.double_tap(x, y, device_id, delay)

    def long_press(
        self,
        x: int,
        y: int,
        duration_ms: int = 3000,
        device_id: str | None = None,
        delay: float | None = None,
    ):
        """Long press at coordinates."""
        return self.module.long_press(x, y, duration_ms, device_id, delay)

    def swipe(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration_ms: int | None = None,
        device_id: str | None = None,
        delay: float | None = None,
    ):
        """Swipe from start to end."""
        return self.module.swipe(
            start_x, start_y, end_x, end_y, duration_ms, device_id, delay
        )

    def back(self, device_id: str | None = None, delay: float | None = None):
        """Press back button."""
        return self.module.back(device_id, delay)

    def home(self, device_id: str | None = None, delay: float | None = None):
        """Press home button."""
        return self.module.home(device_id, delay)

    def launch_app(
        self, app_name: str, device_id: str | None = None, delay: float | None = None
    ) -> bool:
        """Launch an app."""
        return self.launch_app_detailed(app_name, device_id, delay).success

    def launch_app_detailed(
        self, app_name: str, device_id: str | None = None, delay: float | None = None
    ) -> AppLaunchResult:
        """Launch an app and return detailed result."""
        launch_callable = getattr(self.module, "launch_app_detailed", self.module.launch_app)
        result = launch_callable(app_name, device_id, delay)
        if isinstance(result, AppLaunchResult):
            return result
        if isinstance(result, tuple) and len(result) == 3:
            success, message, package_name = result
            return AppLaunchResult(success, message, package_name)
        if isinstance(result, tuple) and len(result) == 2:
            success, message = result
            return AppLaunchResult(success, message)
        if isinstance(result, bool):
            return AppLaunchResult(result)
        raise TypeError(f"Unsupported launch_app result type: {type(result)!r}")

    def type_text(self, text: str, device_id: str | None = None):
        """Type text."""
        return self.module.type_text(text, device_id)

    def clear_text(self, device_id: str | None = None):
        """Clear text."""
        return self.module.clear_text(device_id)

    def detect_and_set_adb_keyboard(self, device_id: str | None = None) -> str:
        """Detect and set keyboard."""
        return self.module.detect_and_set_adb_keyboard(device_id)

    def restore_keyboard(self, ime: str, device_id: str | None = None):
        """Restore keyboard."""
        return self.module.restore_keyboard(ime, device_id)

    def list_devices(self):
        """List connected devices."""
        return self.module.list_devices()

    def list_installed_apps(self, device_id: str | None = None):
        """List installed apps when supported by the current device backend."""
        if not hasattr(self.module, "list_installed_apps"):
            raise NotImplementedError(
                f"Device type '{self.device_type.value}' does not support installed app lookup"
            )
        return self.module.list_installed_apps(device_id)

    def find_installed_app(self, query: str, device_id: str | None = None):
        """Find an installed app when supported by the current device backend."""
        if not hasattr(self.module, "find_installed_app"):
            raise NotImplementedError(
                f"Device type '{self.device_type.value}' does not support installed app lookup"
            )
        return self.module.find_installed_app(query, device_id)

    def search_installed_apps(self, query: str, device_id: str | None = None):
        """Search installed apps when supported by the current device backend."""
        if not hasattr(self.module, "search_installed_apps"):
            raise NotImplementedError(
                f"Device type '{self.device_type.value}' does not support installed app lookup"
            )
        return self.module.search_installed_apps(query, device_id)

    def get_connection_class(self):
        """Get the connection class (ADBConnection or HDCConnection)."""
        if self.device_type == DeviceType.ADB:
            from phone_agent.adb import ADBConnection

            return ADBConnection
        elif self.device_type == DeviceType.HDC:
            from phone_agent.hdc import HDCConnection

            return HDCConnection
        else:
            raise ValueError(f"Unknown device type: {self.device_type}")


# Global device factory instance
_device_factory: DeviceFactory | None = None


def set_device_type(device_type: DeviceType):
    """
    Set the global device type.

    Args:
        device_type: The device type to use (ADB or HDC).
    """
    global _device_factory
    _device_factory = DeviceFactory(device_type)


def get_device_factory() -> DeviceFactory:
    """
    Get the global device factory instance.

    Returns:
        The device factory instance.
    """
    global _device_factory
    if _device_factory is None:
        _device_factory = DeviceFactory(DeviceType.ADB)  # Default to ADB
    return _device_factory
