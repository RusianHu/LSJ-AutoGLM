"""Chinese system prompt compatibility wrapper."""

from __future__ import annotations

from phone_agent.actions.registry import ActionPolicyInput
from phone_agent.prompts import build_system_prompt



def get_system_prompt_zh(
    *,
    platform: str | None = None,
    action_policy: ActionPolicyInput | None = None,
) -> str:
    return build_system_prompt(
        lang="cn",
        platform=platform,
        action_policy=action_policy,
    )


SYSTEM_PROMPT = get_system_prompt_zh()
