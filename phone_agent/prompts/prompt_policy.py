"""Prompt policy helpers derived from the shared action registry."""

from __future__ import annotations

from dataclasses import dataclass

from phone_agent.actions.registry import (
    ActionPolicyInput,
    ActionSpec,
    PlatformName,
    ResolvedActionPolicy,
    export_prompt_action_specs,
    resolve_action_policy,
)
from phone_agent.device_factory import DeviceType


@dataclass(frozen=True)
class PromptPolicy:
    """Resolved prompt policy for a specific platform and runtime configuration."""

    platform: PlatformName
    lang: str = "cn"
    thirdparty: bool = False
    thinking: bool = True
    minimal: bool = False
    include_examples: bool = True
    include_rules: bool = True
    runtime_policy: ResolvedActionPolicy | None = None

    @property
    def normalized_lang(self) -> str:
        lang = (self.lang or "cn").strip().lower()
        if lang == "zh":
            return "cn"
        if lang not in {"cn", "en"}:
            return "cn"
        return lang

    @property
    def ai_visible_actions(self) -> tuple[str, ...]:
        if self.runtime_policy is None:
            return ()
        return self.runtime_policy.ai_visible_actions

    @property
    def runtime_enabled_actions(self) -> tuple[str, ...]:
        if self.runtime_policy is None:
            return ()
        return self.runtime_policy.runtime_enabled_actions

    def export_action_specs(self) -> tuple[ActionSpec, ...]:
        return export_prompt_action_specs(
            self.platform,
            lang=self.normalized_lang,
            include_actions=self.ai_visible_actions,
            thirdparty=self.thirdparty,
            minimal=self.minimal,
        )



def normalize_platform_name(platform: str | PlatformName | DeviceType | None) -> PlatformName:
    if isinstance(platform, DeviceType):
        return platform.value
    if platform is None:
        return "adb"
    text = str(platform).strip().lower()
    if text in {"adb", "hdc", "ios"}:
        return text  # type: ignore[return-value]
    raise ValueError(f"Unsupported platform: {platform}")



def build_prompt_policy(
    *,
    platform: str | PlatformName | DeviceType | None = None,
    lang: str = "cn",
    thirdparty: bool = False,
    thinking: bool = True,
    minimal: bool = False,
    include_examples: bool = True,
    include_rules: bool = True,
    action_policy: ActionPolicyInput | None = None,
) -> PromptPolicy:
    resolved_platform = normalize_platform_name(platform)
    runtime_policy = resolve_action_policy(resolved_platform, action_policy)
    return PromptPolicy(
        platform=resolved_platform,
        lang=lang,
        thirdparty=thirdparty,
        thinking=thinking,
        minimal=minimal,
        include_examples=include_examples,
        include_rules=include_rules,
        runtime_policy=runtime_policy,
    )


__all__ = [
    "PromptPolicy",
    "build_prompt_policy",
    "normalize_platform_name",
]
