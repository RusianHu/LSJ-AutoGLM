"""Configuration module for Phone Agent."""

from __future__ import annotations

from phone_agent.actions.registry import ActionPolicyInput
from phone_agent.config.apps import APP_PACKAGES
from phone_agent.config.apps_ios import APP_PACKAGES_IOS
from phone_agent.config.i18n import get_message, get_messages
from phone_agent.config.prompts_en import SYSTEM_PROMPT as SYSTEM_PROMPT_EN
from phone_agent.config.prompts_en import get_system_prompt_en
from phone_agent.config.prompts_thirdparty import (
    THIRDPARTY_MINIMAL_PROMPT,
    THIRDPARTY_MINIMAL_PROMPT_WITH_THINKING,
    THIRDPARTY_SYSTEM_PROMPT,
    THIRDPARTY_SYSTEM_PROMPT_WITH_THINKING,
    get_thirdparty_system_prompt,
)
from phone_agent.config.prompts_zh import SYSTEM_PROMPT as SYSTEM_PROMPT_ZH
from phone_agent.config.prompts_zh import get_system_prompt_zh
from phone_agent.config.timing import (
    TIMING_CONFIG,
    ActionTimingConfig,
    ConnectionTimingConfig,
    DeviceTimingConfig,
    TimingConfig,
    get_timing_config,
    update_timing_config,
)



def get_system_prompt(
    lang: str = "cn",
    *,
    platform: str | None = None,
    thirdparty: bool = False,
    thirdparty_thinking: bool = True,
    minimal: bool = False,
    action_policy: ActionPolicyInput | None = None,
) -> str:
    """Get system prompt by language and runtime strategy."""
    normalized_lang = (lang or "cn").strip().lower()
    if normalized_lang == "zh":
        normalized_lang = "cn"

    if thirdparty:
        return get_thirdparty_system_prompt(
            lang=normalized_lang,
            platform=platform,
            thinking=thirdparty_thinking,
            minimal=minimal,
            action_policy=action_policy,
        )

    if normalized_lang == "en":
        return get_system_prompt_en(
            platform=platform,
            action_policy=action_policy,
        )
    return get_system_prompt_zh(
        platform=platform,
        action_policy=action_policy,
    )


# Default to Chinese for backward compatibility
SYSTEM_PROMPT = SYSTEM_PROMPT_ZH

__all__ = [
    "APP_PACKAGES",
    "APP_PACKAGES_IOS",
    "SYSTEM_PROMPT",
    "SYSTEM_PROMPT_ZH",
    "SYSTEM_PROMPT_EN",
    "THIRDPARTY_SYSTEM_PROMPT",
    "THIRDPARTY_SYSTEM_PROMPT_WITH_THINKING",
    "THIRDPARTY_MINIMAL_PROMPT",
    "THIRDPARTY_MINIMAL_PROMPT_WITH_THINKING",
    "get_system_prompt",
    "get_system_prompt_en",
    "get_system_prompt_zh",
    "get_thirdparty_system_prompt",
    "get_messages",
    "get_message",
    "TIMING_CONFIG",
    "TimingConfig",
    "ActionTimingConfig",
    "DeviceTimingConfig",
    "ConnectionTimingConfig",
    "get_timing_config",
    "update_timing_config",
]
