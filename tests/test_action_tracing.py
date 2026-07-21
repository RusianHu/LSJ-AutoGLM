from __future__ import annotations

import json

from phone_agent.actions.handler import ActionHandler
from phone_agent.adb.device import (
    _parse_current_app_from_window_dump,
    _parse_focused_window_title,
)
from phone_agent.agent import PhoneAgent


def test_coordinate_trace_records_model_and_absolute_coordinates():
    handler = ActionHandler()

    model, absolute = handler.describe_action_coordinates(
        {"_metadata": "do", "action": "Tap", "element": [100, 240]},
        1080,
        2400,
    )

    assert model == {"element": [100, 240]}
    assert absolute == {"element": [108, 576]}


def test_coordinate_trace_handles_swipe_endpoints():
    handler = ActionHandler()

    model, absolute = handler.describe_action_coordinates(
        {
            "_metadata": "do",
            "action": "Swipe",
            "start": [500, 800],
            "end": [500, 200],
        },
        1080,
        2400,
    )

    assert model == {"start": [500, 800], "end": [500, 200]}
    assert absolute == {"start": [540, 1920], "end": [540, 480]}


def test_adb_window_dump_parsers_return_app_and_page_title():
    output = """
      mCurrentFocus=Window{72a0526 u0 com.tencent.mm/com.tencent.mm.ui.LauncherUI}
      mFocusedApp=ActivityRecord{17565856 u0 com.tencent.mm/.ui.LauncherUI t19769}
    """

    assert _parse_current_app_from_window_dump(output) == "微信"
    assert (
        _parse_focused_window_title(output)
        == "com.tencent.mm/com.tencent.mm.ui.LauncherUI"
    )


def test_action_trace_line_is_machine_readable(capsys):
    payload = {
        "phase": "before",
        "action": "Tap",
        "screenshot": {"width": 1080, "height": 2400},
        "model_coordinates": {"element": [100, 240]},
        "absolute_coordinates": {"element": [108, 576]},
    }

    PhoneAgent._print_action_trace(payload)

    line = capsys.readouterr().out.strip()
    prefix = "[ACTION_TRACE] "
    assert line.startswith(prefix)
    assert json.loads(line.removeprefix(prefix)) == payload
