"""Configuration module for Phone Agent."""

from phone_agent.config.apps import APP_PACKAGES
from phone_agent.config.i18n import get_message, get_messages
from phone_agent.config.prompts_en import SYSTEM_PROMPT as SYSTEM_PROMPT_EN
from phone_agent.config.prompts_zh import SYSTEM_PROMPT as SYSTEM_PROMPT_ZH
from phone_agent.config.prompts_thirdparty import (
    THIRDPARTY_SYSTEM_PROMPT,
    THIRDPARTY_SYSTEM_PROMPT_WITH_THINKING,
    THIRDPARTY_SIMPLE_PROMPT,
    THIRDPARTY_MINIMAL_PROMPT,
    THIRDPARTY_MINIMAL_PROMPT_WITH_THINKING,
    build_thirdparty_messages,
)
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
    lang: str = "cn", use_thirdparty: bool = False, thirdparty_thinking: bool = True
) -> str:
    """
    Get system prompt by language.

    Args:
        lang: Language code, 'cn' for Chinese, 'en' for English.
        use_thirdparty: If True, use thirdparty prompt for non-AutoGLM models.
        thirdparty_thinking: If True, thirdparty mode outputs <think>/<answer> like default.

    Returns:
        System prompt string.
    """
    if use_thirdparty:
        # 第三方模式：保持提示词精简，但可选启用规范化思考输出。
        # 某些 API 对长提示词/系统角色/XML 敏感会返回空，可关闭 thirdparty_thinking 回退到纯动作输出。
        return (
            THIRDPARTY_MINIMAL_PROMPT_WITH_THINKING
            if thirdparty_thinking
            else THIRDPARTY_MINIMAL_PROMPT
        )
    if lang == "en":
        return SYSTEM_PROMPT_EN
    return SYSTEM_PROMPT_ZH


# Default to Chinese for backward compatibility
SYSTEM_PROMPT = SYSTEM_PROMPT_ZH

__all__ = [
    "APP_PACKAGES",
    "SYSTEM_PROMPT",
    "SYSTEM_PROMPT_ZH",
    "SYSTEM_PROMPT_EN",
    "THIRDPARTY_SYSTEM_PROMPT",
    "THIRDPARTY_SYSTEM_PROMPT_WITH_THINKING",
    "THIRDPARTY_SIMPLE_PROMPT",
    "THIRDPARTY_MINIMAL_PROMPT",
    "THIRDPARTY_MINIMAL_PROMPT_WITH_THINKING",
    "get_system_prompt",
    "build_thirdparty_messages",
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
