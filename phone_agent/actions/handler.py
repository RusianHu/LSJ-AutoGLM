"""Action handler for processing AI model outputs."""

import ast
import json
import re
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Callable

from phone_agent.config.timing import TIMING_CONFIG
from phone_agent.device_factory import get_device_factory


@dataclass
class ActionResult:
    """Result of an action execution."""

    success: bool
    should_finish: bool
    message: str | None = None
    requires_confirmation: bool = False


class ActionHandler:
    """
    Handles execution of actions from AI model output.

    Args:
        device_id: Optional ADB device ID for multi-device setups.
        confirmation_callback: Optional callback for sensitive action confirmation.
            Should return True to proceed, False to cancel.
        takeover_callback: Optional callback for takeover requests (login, captcha).
    """

    def __init__(
        self,
        device_id: str | None = None,
        confirmation_callback: Callable[[str], bool] | None = None,
        takeover_callback: Callable[[str], None] | None = None,
    ):
        self.device_id = device_id
        self.confirmation_callback = confirmation_callback or self._default_confirmation
        self.takeover_callback = takeover_callback or self._default_takeover

    def execute(
        self, action: dict[str, Any], screen_width: int, screen_height: int
    ) -> ActionResult:
        """
        Execute an action from the AI model.

        Args:
            action: The action dictionary from the model.
            screen_width: Current screen width in pixels.
            screen_height: Current screen height in pixels.

        Returns:
            ActionResult indicating success and whether to finish.
        """
        action_type = action.get("_metadata")

        if action_type == "finish":
            return ActionResult(
                success=True, should_finish=True, message=action.get("message")
            )

        if action_type != "do":
            return ActionResult(
                success=False,
                should_finish=True,
                message=f"Unknown action type: {action_type}",
            )

        action_name = action.get("action")
        handler_method = self._get_handler(action_name)

        if handler_method is None:
            return ActionResult(
                success=False,
                should_finish=False,
                message=f"Unknown action: {action_name}",
            )

        try:
            return handler_method(action, screen_width, screen_height)
        except Exception as e:
            return ActionResult(
                success=False, should_finish=False, message=f"Action failed: {e}"
            )

    def _get_handler(self, action_name: str) -> Callable | None:
        """Get the handler method for an action."""
        handlers = {
            "Launch": self._handle_launch,
            "Tap": self._handle_tap,
            "Type": self._handle_type,
            "Type_Name": self._handle_type,
            "Swipe": self._handle_swipe,
            "Back": self._handle_back,
            "Home": self._handle_home,
            "Double Tap": self._handle_double_tap,
            "Long Press": self._handle_long_press,
            "Wait": self._handle_wait,
            "Take_over": self._handle_takeover,
            "Note": self._handle_note,
            "Call_API": self._handle_call_api,
            "Interact": self._handle_interact,
        }
        return handlers.get(action_name)

    def _convert_relative_to_absolute(
        self, element: list[int], screen_width: int, screen_height: int
    ) -> tuple[int, int]:
        """Convert relative coordinates (0-1000) to absolute pixels."""
        x = int(element[0] / 1000 * screen_width)
        y = int(element[1] / 1000 * screen_height)
        return x, y

    def _handle_launch(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle app launch action."""
        app_name = action.get("app")
        if not app_name:
            return ActionResult(False, False, "No app name specified")

        device_factory = get_device_factory()
        success = device_factory.launch_app(app_name, self.device_id)
        if success:
            return ActionResult(True, False)
        return ActionResult(False, False, f"App not found: {app_name}")

    def _handle_tap(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle tap action."""
        element = action.get("element")
        if not element:
            return ActionResult(False, False, "No element coordinates")

        x, y = self._convert_relative_to_absolute(element, width, height)

        # Check for sensitive operation
        if "message" in action:
            if not self.confirmation_callback(action["message"]):
                return ActionResult(
                    success=False,
                    should_finish=True,
                    message="User cancelled sensitive operation",
                )

        device_factory = get_device_factory()
        device_factory.tap(x, y, self.device_id)
        return ActionResult(True, False)

    def _handle_type(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle text input action."""
        text = action.get("text", "")

        device_factory = get_device_factory()

        # Switch to ADB keyboard
        original_ime = device_factory.detect_and_set_adb_keyboard(self.device_id)
        time.sleep(TIMING_CONFIG.action.keyboard_switch_delay)

        # Clear existing text and type new text
        device_factory.clear_text(self.device_id)
        time.sleep(TIMING_CONFIG.action.text_clear_delay)

        # Handle multiline text by splitting on newlines
        device_factory.type_text(text, self.device_id)
        time.sleep(TIMING_CONFIG.action.text_input_delay)

        # Restore original keyboard
        device_factory.restore_keyboard(original_ime, self.device_id)
        time.sleep(TIMING_CONFIG.action.keyboard_restore_delay)

        return ActionResult(True, False)

    def _handle_swipe(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle swipe action."""
        start = action.get("start")
        end = action.get("end")

        if not start or not end:
            return ActionResult(False, False, "Missing swipe coordinates")

        start_x, start_y = self._convert_relative_to_absolute(start, width, height)
        end_x, end_y = self._convert_relative_to_absolute(end, width, height)

        device_factory = get_device_factory()
        device_factory.swipe(start_x, start_y, end_x, end_y, device_id=self.device_id)
        return ActionResult(True, False)

    def _handle_back(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle back button action."""
        device_factory = get_device_factory()
        device_factory.back(self.device_id)
        return ActionResult(True, False)

    def _handle_home(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle home button action."""
        device_factory = get_device_factory()
        device_factory.home(self.device_id)
        return ActionResult(True, False)

    def _handle_double_tap(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle double tap action."""
        element = action.get("element")
        if not element:
            return ActionResult(False, False, "No element coordinates")

        x, y = self._convert_relative_to_absolute(element, width, height)
        device_factory = get_device_factory()
        device_factory.double_tap(x, y, self.device_id)
        return ActionResult(True, False)

    def _handle_long_press(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle long press action."""
        element = action.get("element")
        if not element:
            return ActionResult(False, False, "No element coordinates")

        x, y = self._convert_relative_to_absolute(element, width, height)
        device_factory = get_device_factory()
        device_factory.long_press(x, y, device_id=self.device_id)
        return ActionResult(True, False)

    def _handle_wait(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle wait action."""
        duration_str = action.get("duration", "1 seconds")
        try:
            duration = float(duration_str.replace("seconds", "").strip())
        except ValueError:
            duration = 1.0

        time.sleep(duration)
        return ActionResult(True, False)

    def _handle_takeover(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle takeover request (login, captcha, etc.)."""
        message = action.get("message", "User intervention required")
        self.takeover_callback(message)
        return ActionResult(True, False)

    def _handle_note(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle note action (placeholder for content recording)."""
        # This action is typically used for recording page content
        # Implementation depends on specific requirements
        return ActionResult(True, False)

    def _handle_call_api(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle API call action (placeholder for summarization)."""
        # This action is typically used for content summarization
        # Implementation depends on specific requirements
        return ActionResult(True, False)

    def _handle_interact(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle interaction request (user choice needed)."""
        # This action signals that user input is needed
        return ActionResult(True, False, message="User interaction required")

    def _send_keyevent(self, keycode: str) -> None:
        """Send a keyevent to the device."""
        from phone_agent.device_factory import DeviceType, get_device_factory
        from phone_agent.hdc.connection import _run_hdc_command

        device_factory = get_device_factory()

        # Handle HDC devices with HarmonyOS-specific keyEvent command
        if device_factory.device_type == DeviceType.HDC:
            hdc_prefix = ["hdc", "-t", self.device_id] if self.device_id else ["hdc"]
            
            # Map common keycodes to HarmonyOS keyEvent codes
            # KEYCODE_ENTER (66) -> 2054 (HarmonyOS Enter key code)
            if keycode == "KEYCODE_ENTER" or keycode == "66":
                _run_hdc_command(
                    hdc_prefix + ["shell", "uitest", "uiInput", "keyEvent", "2054"],
                    capture_output=True,
                    text=True,
                )
            else:
                # For other keys, try to use the numeric code directly
                # If keycode is a string like "KEYCODE_ENTER", convert it
                try:
                    # Try to extract numeric code from string or use as-is
                    if keycode.startswith("KEYCODE_"):
                        # For now, only handle ENTER, other keys may need mapping
                        if "ENTER" in keycode:
                            _run_hdc_command(
                                hdc_prefix + ["shell", "uitest", "uiInput", "keyEvent", "2054"],
                                capture_output=True,
                                text=True,
                            )
                        else:
                            # Fallback to ADB-style command for unsupported keys
                            subprocess.run(
                                hdc_prefix + ["shell", "input", "keyevent", keycode],
                                capture_output=True,
                                text=True,
                            )
                    else:
                        # Assume it's a numeric code
                        _run_hdc_command(
                            hdc_prefix + ["shell", "uitest", "uiInput", "keyEvent", str(keycode)],
                            capture_output=True,
                            text=True,
                        )
                except Exception:
                    # Fallback to ADB-style command
                    subprocess.run(
                        hdc_prefix + ["shell", "input", "keyevent", keycode],
                        capture_output=True,
                        text=True,
                    )
        else:
            # ADB devices use standard input keyevent command
            cmd_prefix = ["adb", "-s", self.device_id] if self.device_id else ["adb"]
            subprocess.run(
                cmd_prefix + ["shell", "input", "keyevent", keycode],
                capture_output=True,
                text=True,
            )

    @staticmethod
    def _default_confirmation(message: str) -> bool:
        """Default confirmation callback using console input."""
        response = input(f"Sensitive operation: {message}\nConfirm? (Y/N): ")
        return response.upper() == "Y"

    @staticmethod
    def _default_takeover(message: str) -> None:
        """Default takeover callback using console input."""
        input(f"{message}\nPress Enter after completing manual operation...")


def parse_action(response: str) -> dict[str, Any]:
    """
    Parse action from model response.

    Args:
        response: Raw response string from the model.

    Returns:
        Parsed action dictionary.

    Raises:
        ValueError: If the response cannot be parsed.
    """
    print(f"Parsing action: {response}")
    try:
        def _split_top_level_args(arg_str: str) -> list[str]:
            parts: list[str] = []
            buf: list[str] = []
            depth_square = 0
            depth_curly = 0
            in_quote: str | None = None
            escape = False

            for ch in arg_str:
                if escape:
                    buf.append(ch)
                    escape = False
                    continue

                if ch == "\\":
                    buf.append(ch)
                    escape = True
                    continue

                if in_quote:
                    buf.append(ch)
                    if ch == in_quote:
                        in_quote = None
                    continue

                if ch in ("'", '"'):
                    buf.append(ch)
                    in_quote = ch
                    continue

                if ch == "[":
                    depth_square += 1
                elif ch == "]":
                    depth_square = max(0, depth_square - 1)
                elif ch == "{":
                    depth_curly += 1
                elif ch == "}":
                    depth_curly = max(0, depth_curly - 1)

                if ch == "," and depth_square == 0 and depth_curly == 0:
                    part = "".join(buf).strip()
                    if part:
                        parts.append(part)
                    buf = []
                    continue

                buf.append(ch)

            tail = "".join(buf).strip()
            if tail:
                parts.append(tail)
            return parts

        def _parse_loose_string(value: str) -> str:
            v = (value or "").strip()
            if not v:
                return ""
            if v[0] in ("'", '"'):
                q = v[0]
                end = v.rfind(q)
                inner = v[1:end] if end > 0 else v[1:]
                return (
                    inner.replace("\\n", "\n")
                    .replace("\\r", "\r")
                    .replace("\\t", "\t")
                    .strip()
                )
            return v

        def _fallback_parse_call(call_text: str) -> dict[str, Any] | None:
            t = (call_text or "").strip()
            if not (t.startswith("do(") or t.startswith("finish(")):
                return None

            open_idx = t.find("(")
            close_idx = t.rfind(")")
            if open_idx < 0 or close_idx < 0 or close_idx <= open_idx:
                return None

            fn = t[:open_idx].strip()
            args_str = t[open_idx + 1 : close_idx].strip()
            metadata = "do" if fn == "do" else "finish"
            payload: dict[str, Any] = {"_metadata": metadata}

            if not args_str:
                return payload

            for part in _split_top_level_args(args_str):
                if not part:
                    continue
                if "=" in part:
                    key, raw_val = part.split("=", 1)
                elif ":" in part:
                    key, raw_val = part.split(":", 1)
                else:
                    continue

                key = key.strip().strip('"').strip("'")
                raw_val = raw_val.strip()

                if key in ("message", "text", "app", "action", "duration"):
                    # Be tolerant of unescaped quotes inside the string (common model error),
                    # by extracting using the last matching quote.
                    payload[key] = _parse_loose_string(raw_val)
                    continue

                try:
                    safe_val = (
                        raw_val.replace("\n", "\\n")
                        .replace("\r", "\\r")
                        .replace("\t", "\\t")
                    )
                    payload[key] = ast.literal_eval(safe_val)
                except Exception:
                    payload[key] = _parse_loose_string(raw_val)

            return payload

        def _strip_wrappers(text: str) -> str:
            t = text.strip()

            # Remove common XML tags that some models output
            for tag in [
                "<think>",
                "</think>",
                "<answer>",
                "</answer>",
                "<tool_call>",
                "</tool_call>",
            ]:
                t = t.replace(tag, " ")

            # Unwrap markdown code fences if present
            fence_match = re.search(r"```(?:python)?\s*(.*?)\s*```", t, re.DOTALL)
            if fence_match:
                t = fence_match.group(1).strip()
            return t.strip()

        def _extract_first_call(text: str) -> str:
            candidates = []
            for prefix in ("do(", "finish("):
                idx = text.find(prefix)
                if idx != -1:
                    candidates.append((idx, prefix))
            if not candidates:
                return text

            start_idx, _ = min(candidates, key=lambda x: x[0])
            in_quote: str | None = None
            escaped = False
            depth = 0
            for i in range(start_idx, len(text)):
                ch = text[i]
                if in_quote:
                    if escaped:
                        escaped = False
                        continue
                    if ch == "\\":
                        escaped = True
                        continue
                    if ch == in_quote:
                        in_quote = None
                    continue

                if ch in ("'", '"'):
                    in_quote = ch
                    continue
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        return text[start_idx : i + 1].strip()

            return text[start_idx:].strip()

        def _normalize_common_typos(text: str) -> str:
            t = text.strip()
            t = (
                t.replace("“", '"')
                .replace("”", '"')
                .replace("‘", "'")
                .replace("’", "'")
                .replace("，", ",")
                .replace("：", ":")
            )

            # Fix JSON-style or malformed keyword separators in function calls
            # e.g. element": [1,2]  or  "element": [1,2]  or  element: [1,2]
            keys = r"(element|start|end|app|text|message|duration)"
            t = re.sub(rf'"{keys}"\s*:\s*', r"\1=", t)
            t = re.sub(rf"\b{keys}\"\s*:\s*", r"\1=", t)
            t = re.sub(rf"\b{keys}\s*:\s*", r"\1=", t)

            # Occasionally models output a trailing semicolon
            t = t.rstrip(";")
            return t

        raw = response
        response = _strip_wrappers(raw)

        # JSON action payload (some thirdparty models output dict directly)
        if response.startswith("{") and response.endswith("}"):
            try:
                payload = json.loads(response)
                if isinstance(payload, dict):
                    if "_metadata" not in payload:
                        payload["_metadata"] = (
                            "finish" if "message" in payload and "action" not in payload else "do"
                        )
                    return payload
            except json.JSONDecodeError:
                pass

        response = _extract_first_call(response)
        response = _normalize_common_typos(response)

        # Use AST parsing instead of eval for safety
        try:
            # Escape special characters (newlines, tabs, etc.) for valid Python syntax
            safe = response.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")

            tree = ast.parse(safe, mode="eval")
            if not isinstance(tree.body, ast.Call):
                raise ValueError("Expected a function call")

            call = tree.body
            if not isinstance(call.func, ast.Name) or call.func.id not in ("do", "finish"):
                raise ValueError("Expected do(...) or finish(...)")

            action: dict[str, Any] = {"_metadata": "do" if call.func.id == "do" else "finish"}
            for keyword in call.keywords:
                if keyword.arg is None:
                    raise ValueError("Unsupported **kwargs in action call")
                action[keyword.arg] = ast.literal_eval(keyword.value)

            return action
        except (SyntaxError, ValueError) as e:
            # Fallback: tolerate common model mistakes like unescaped quotes inside message/text.
            fallback = _fallback_parse_call(response)
            if fallback is not None:
                return fallback
            raise ValueError(f"Failed to parse action call: {e}. Raw: {raw!r}")
    except Exception as e:
        raise ValueError(f"Failed to parse action: {e}")


def do(**kwargs) -> dict[str, Any]:
    """Helper function for creating 'do' actions."""
    kwargs["_metadata"] = "do"
    return kwargs


def finish(**kwargs) -> dict[str, Any]:
    """Helper function for creating 'finish' actions."""
    kwargs["_metadata"] = "finish"
    return kwargs
