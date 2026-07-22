from __future__ import annotations

import copy
from types import SimpleNamespace
from unittest.mock import patch

from phone_agent.actions import ActionResult
from phone_agent.adb.device import InstalledApp, list_installed_apps, search_installed_apps
from phone_agent.agent import AgentConfig, PhoneAgent
from phone_agent.model.client import MessageBuilder, ModelClient, ModelConfig
from phone_agent.runtime.step_tracker import AgentStepTracker


class _FakeCompletions:
    def __init__(self, chunks):
        self.chunks = chunks
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return iter(self.chunks)


def _chunk(*, reasoning=None, content=None):
    delta = SimpleNamespace(reasoning_content=reasoning, content=content)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)], usage=None)


def test_model_client_keeps_reasoning_and_visible_content_separate(capsys):
    completions = _FakeCompletions(
        [
            _chunk(reasoning="先确认应用包名。"),
            _chunk(content='do(action="Find_App", query="美团")'),
        ]
    )
    client = object.__new__(ModelClient)
    client.config = ModelConfig(model_name="mimo-v2.5", lang="cn")
    client.client = SimpleNamespace(
        chat=SimpleNamespace(completions=completions)
    )

    response = client.request([{"role": "user", "content": "打开美团"}])

    assert response.reasoning_content == "先确认应用包名。"
    assert response.content == 'do(action="Find_App", query="美团")'
    assert response.thinking == "先确认应用包名。"
    assert response.action == 'do(action="Find_App", query="美团")'
    assert completions.kwargs["messages"] == [
        {"role": "user", "content": "打开美团"}
    ]
    capsys.readouterr()


def test_assistant_message_only_emits_reasoning_field_when_provider_supplied_it():
    assert MessageBuilder.create_assistant_message("answer") == {
        "role": "assistant",
        "content": "answer",
    }
    assert MessageBuilder.create_assistant_message("answer", "reason") == {
        "role": "assistant",
        "content": "answer",
        "reasoning_content": "reason",
    }


def test_every_subsequent_agent_request_replays_all_reasoning_history():
    screenshot = SimpleNamespace(width=1080, height=2400, base64_data="c2NyZWVu")
    page = SimpleNamespace(
        app_name="com.miui.home",
        page_title="com.miui.home/.Launcher",
        title_source="test",
    )
    factory = SimpleNamespace(
        get_screenshot=lambda _device_id: screenshot,
        get_current_page_state=lambda _device_id: page,
    )
    responses = [
        SimpleNamespace(
            thinking=f"reason-{index}",
            reasoning_content=f"reason-{index}",
            content='do(action="Wait", duration="0 seconds")',
            action='do(action="Wait", duration="0 seconds")',
        )
        for index in range(1, 4)
    ]
    captured_requests: list[list[dict]] = []

    def fake_request(messages):
        captured_requests.append(copy.deepcopy(messages))
        return responses[len(captured_requests) - 1]

    agent = PhoneAgent(
        agent_config=AgentConfig(
            verbose=False,
            platform="adb",
            system_prompt="test prompt",
        )
    )
    agent.model_client.request = fake_request

    with patch("phone_agent.agent.get_device_factory", return_value=factory), patch.object(
        agent.action_handler,
        "execute",
        return_value=ActionResult(True, False),
    ):
        agent.step("test task")
        agent.step()
        agent.step()

    second_assistants = [
        message for message in captured_requests[1] if message["role"] == "assistant"
    ]
    third_assistants = [
        message for message in captured_requests[2] if message["role"] == "assistant"
    ]
    assert [message["reasoning_content"] for message in second_assistants] == [
        "reason-1"
    ]
    assert [message["reasoning_content"] for message in third_assistants] == [
        "reason-1",
        "reason-2",
    ]
    assert all(
        message["content"] == 'do(action="Wait", duration="0 seconds")'
        for message in third_assistants
    )


def test_find_app_resolves_installed_chinese_alias_before_package_fuzzy_search():
    apps = [
        InstalledApp(
            "com.sankuai.meituan",
            None,
            "com.meituan.android.pt.homepage.activity.MainActivity",
        ),
        InstalledApp("com.xiaomi.smarthome", None, ".SmartHomeMainActivity"),
    ]
    with patch("phone_agent.adb.device.list_installed_apps", return_value=apps):
        matches = search_installed_apps("美团")

    assert [app.package_name for app in matches] == ["com.sankuai.meituan"]


def test_fast_installed_app_list_attaches_known_display_names():
    output = (
        "com.sankuai.meituan/com.meituan.android.pt.homepage.activity.MainActivity\n"
        "com.example.reader/.MainActivity\n"
    )
    with patch("phone_agent.adb.device._run_adb_shell", return_value=output):
        apps = list_installed_apps()

    assert apps[0].display_name == "美团"
    assert apps[1].display_name is None


def test_step_tracker_detects_a_repeated_screen_action_transition():
    tracker = AgentStepTracker()
    transition = (
        "screen-hash",
        "com.miui.home",
        "com.miui.home/.Launcher",
        'Tap:{"element":[700,270]}',
        "com.xiaomi.smarthome",
        "com.xiaomi.smarthome/.Main",
    )
    tracker.record_transition(*transition)
    tracker.record_transition(*transition)

    assert tracker.repeated_transition_outcome(*transition[:4]) == (
        "com.xiaomi.smarthome",
        "com.xiaomi.smarthome/.Main",
        2,
    )
    tracker.reset()
    assert tracker.repeated_transition_outcome(*transition[:4]) is None


def test_agent_blocks_third_identical_tap_transition():
    state = {"page": "home"}

    def current_page(_device_id):
        if state["page"] == "home":
            return SimpleNamespace(
                app_name="com.miui.home",
                page_title="com.miui.home/.Launcher",
                title_source="test",
            )
        return SimpleNamespace(
            app_name="com.xiaomi.smarthome",
            page_title="com.xiaomi.smarthome/.Main",
            title_source="test",
        )

    def screenshot(_device_id):
        return SimpleNamespace(
            width=1080,
            height=2400,
            base64_data="aG9tZQ==" if state["page"] == "home" else "dGFyZ2V0",
        )

    factory = SimpleNamespace(
        get_screenshot=screenshot,
        get_current_page_state=current_page,
    )
    actions = [
        'do(action="Tap", element=[700, 270])',
        'do(action="Back")',
        'do(action="Tap", element=[700, 270])',
        'do(action="Back")',
        'do(action="Tap", element=[700, 270])',
    ]

    def fake_request(_messages):
        action = actions.pop(0)
        return SimpleNamespace(thinking="test", action=action)

    def execute(action, _width, _height):
        if action.get("action") == "Tap":
            state["page"] = "target"
        elif action.get("action") == "Back":
            state["page"] = "home"
        return ActionResult(True, False)

    agent = PhoneAgent(
        agent_config=AgentConfig(
            verbose=False,
            platform="adb",
            system_prompt="test prompt",
        )
    )
    agent.model_client.request = fake_request

    with patch("phone_agent.agent.get_device_factory", return_value=factory), patch.object(
        agent.action_handler,
        "execute",
        side_effect=execute,
    ) as execute_mock:
        results = [agent.step("task")]
        results.extend(agent.step() for _ in range(4))

    assert execute_mock.call_count == 4
    assert results[-1].success is False
    assert "已阻止重复动作" in (results[-1].message or "")
    assert state["page"] == "home"
