# -*- coding: utf-8 -*-

from phone_agent.actions.handler import ActionHandler
from phone_agent.actions.handler_ios import IOSActionHandler
from phone_agent.actions.registry import (
    ACTION_DISABLED_ERROR,
    ACTION_PLATFORM_UNSUPPORTED_ERROR,
    ACTION_UNKNOWN_ERROR,
    ActionPolicyInput,
    check_action_availability,
    export_gui_action_groups,
    parse_action_name_collection,
    resolve_action_policy,
)
from phone_agent.config import get_system_prompt
from phone_agent.prompts import build_system_prompt


class TestActionRegistryPolicy:
    def test_parse_action_name_collection_normalizes_alias_and_csv(self):
        assert parse_action_name_collection("Launch, Type_Name, Launch") == (
            "Launch",
            "Type",
        )

    def test_resolve_action_policy_filters_unknown_and_platform_unsupported_actions(self):
        resolved = resolve_action_policy(
            "ios",
            ActionPolicyInput(
                runtime_enabled_actions=("Launch", "Find_App", "Unknown_Action"),
                ai_visible_actions=("Find_App", "Unknown_Action"),
                use_platform_defaults=False,
                policy_version=3,
            ),
        )

        assert resolved.runtime_enabled_actions == ("Launch",)
        assert resolved.ai_visible_actions == ()
        assert resolved.unknown_actions == ("Unknown_Action",)
        assert resolved.platform_filtered_actions == ("Find_App",)
        assert resolved.policy_version == 3

    def test_export_gui_action_groups_filters_platform_specific_actions(self):
        adb_action_names = {
            item["name"]
            for group in export_gui_action_groups("adb")
            for item in group["items"]
        }
        ios_action_names = {
            item["name"]
            for group in export_gui_action_groups("ios")
            for item in group["items"]
        }

        assert "Find_App" in adb_action_names
        assert "Find_App" not in ios_action_names
        assert "Launch" in adb_action_names
        assert "Launch" in ios_action_names

    def test_check_action_availability_reports_missing_unknown_disabled_and_platform_errors(self):
        ios_policy = resolve_action_policy(
            "ios",
            ActionPolicyInput(
                runtime_enabled_actions=("Launch",),
                ai_visible_actions=("Launch",),
                use_platform_defaults=False,
            ),
        )
        adb_policy = resolve_action_policy(
            "adb",
            ActionPolicyInput(
                runtime_enabled_actions=("Launch",),
                ai_visible_actions=("Launch",),
                use_platform_defaults=False,
            ),
        )

        missing = check_action_availability(None, ios_policy)
        unknown = check_action_availability("Nope", ios_policy)
        unsupported = check_action_availability("Find_App", ios_policy)
        disabled = check_action_availability("Tap", adb_policy)

        assert missing.error_code == ACTION_UNKNOWN_ERROR
        assert missing.reason == "Missing action name"
        assert unknown.error_code == ACTION_UNKNOWN_ERROR
        assert unknown.reason == "Unknown action: Nope"
        assert unsupported.error_code == ACTION_PLATFORM_UNSUPPORTED_ERROR
        assert unsupported.reason == "Action not supported on platform ios: Find_App"
        assert disabled.error_code == ACTION_DISABLED_ERROR
        assert disabled.reason == "Action disabled by runtime policy: Tap"

    def test_check_action_availability_accepts_alias_when_runtime_enabled(self):
        policy = resolve_action_policy(
            "adb",
            ActionPolicyInput(
                runtime_enabled_actions=("Type",),
                ai_visible_actions=("Type",),
                use_platform_defaults=False,
            ),
        )

        availability = check_action_availability("Type_Name", policy)

        assert availability.allowed is True
        assert availability.action_name == "Type"


class TestPromptBuilderCompatibility:
    def test_build_system_prompt_limits_prompt_visible_actions_but_keeps_runtime_summary(self):
        text = build_system_prompt(
            lang="en",
            platform="adb",
            include_examples=False,
            include_rules=False,
            action_policy=ActionPolicyInput(
                runtime_enabled_actions=("Launch", "Tap"),
                ai_visible_actions=("Launch",),
                use_platform_defaults=False,
            ),
        )

        assert 'do(action="Launch", app="app_name")' in text
        assert 'do(action="Tap", element=[x, y])' not in text
        assert "Prompt-visible actions: Launch" in text
        assert "Runtime-enabled actions: Launch, Tap" in text

    def test_get_system_prompt_normalizes_zh_and_matches_builder_output(self):
        action_policy = ActionPolicyInput(
            runtime_enabled_actions=("Launch", "Wait"),
            ai_visible_actions=("Launch",),
            use_platform_defaults=False,
        )

        from_config = get_system_prompt(
            lang="zh",
            platform="adb",
            action_policy=action_policy,
        )
        from_builder = build_system_prompt(
            lang="cn",
            platform="adb",
            action_policy=action_policy,
        )

        assert from_config == from_builder
        assert "当前提示词可见动作：Launch" in from_config
        assert "当前运行时允许动作：Launch，Wait" in from_config


class TestRuntimePolicyRejections:
    def test_action_handler_execute_rejects_disabled_action_before_device_call(self):
        handler = ActionHandler(
            runtime_policy=resolve_action_policy(
                "adb",
                ActionPolicyInput(
                    runtime_enabled_actions=("Launch",),
                    ai_visible_actions=("Launch",),
                    use_platform_defaults=False,
                ),
            )
        )

        result = handler.execute(
            {"_metadata": "do", "action": "Tap", "element": [500, 500]},
            1080,
            2400,
        )

        assert result.success is False
        assert result.should_finish is False
        assert result.message == "[ActionDisabled] Action disabled by runtime policy: Tap"

    def test_ios_action_handler_execute_rejects_platform_unsupported_action_before_wda_call(self):
        handler = IOSActionHandler(
            runtime_policy=resolve_action_policy(
                "ios",
                ActionPolicyInput(
                    runtime_enabled_actions=("Launch",),
                    ai_visible_actions=("Launch",),
                    use_platform_defaults=False,
                ),
            )
        )

        result = handler.execute(
            {"_metadata": "do", "action": "Find_App", "query": "settings"},
            1179,
            2556,
        )

        assert result.success is False
        assert result.should_finish is False
        assert result.message == (
            "[PlatformNotSupported] Action not supported on platform ios: Find_App"
        )
