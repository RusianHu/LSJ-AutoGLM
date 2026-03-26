"""Composable system prompt builder backed by the shared action registry."""

from __future__ import annotations

from dataclasses import dataclass

from phone_agent.actions.registry import ActionPolicyInput
from phone_agent.prompts.prompt_policy import PromptPolicy, build_prompt_policy
from phone_agent.prompts.prompt_sections import (
    render_action_name_list,
    render_action_protocol_section,
    render_rule_section,
)
from phone_agent.prompts.prompt_templates import (
    CN_GENERAL_RULES,
    CN_HEADER,
    EN_GENERAL_RULES,
    EN_HEADER,
    MINIMAL_HEADER_EN,
    MINIMAL_HEADER_ZH,
    THIRDPARTY_GENERAL_RULES_EN,
    THIRDPARTY_GENERAL_RULES_ZH,
    THIRDPARTY_HEADER_EN,
    THIRDPARTY_HEADER_ZH,
    THIRDPARTY_THINKING_HEADER_EN,
    THIRDPARTY_THINKING_HEADER_ZH,
    format_today,
)


@dataclass(frozen=True)
class BuiltPrompt:
    policy: PromptPolicy
    text: str


class PromptBuilder:
    """Generate structured system prompts from prompt policy and action registry."""

    def build(self, policy: PromptPolicy) -> BuiltPrompt:
        sections = [self._build_date_line(policy)]
        sections.extend(self._build_body_sections(policy))
        text = "\n\n".join(section.strip() for section in sections if section and section.strip())
        return BuiltPrompt(policy=policy, text=text)

    def build_text(self, policy: PromptPolicy) -> str:
        return self.build(policy).text

    def _build_date_line(self, policy: PromptPolicy) -> str:
        if policy.normalized_lang == "en":
            return f"The current date: {format_today('en')}"
        return f"今天的日期是: {format_today('cn')}"

    def _build_body_sections(self, policy: PromptPolicy) -> list[str]:
        action_specs = policy.export_action_specs()
        sections: list[str] = []

        if policy.thirdparty:
            sections.append(self._build_thirdparty_header(policy))
            sections.append(
                render_action_protocol_section(
                    action_specs,
                    lang=policy.normalized_lang,
                    thirdparty=True,
                    minimal=policy.minimal,
                    include_examples=policy.include_examples,
                    include_rules=policy.include_rules,
                )
            )
            rules = (
                THIRDPARTY_GENERAL_RULES_EN
                if policy.normalized_lang == "en"
                else THIRDPARTY_GENERAL_RULES_ZH
            )
            sections.append(render_rule_section(rules, lang=policy.normalized_lang))
            sections.append(self._build_action_set_summary(policy, action_specs))
            return sections

        sections.append(EN_HEADER if policy.normalized_lang == "en" else CN_HEADER)
        sections.append(
            render_action_protocol_section(
                action_specs,
                lang=policy.normalized_lang,
                include_examples=policy.include_examples,
                include_rules=policy.include_rules,
            )
        )
        rules = EN_GENERAL_RULES if policy.normalized_lang == "en" else CN_GENERAL_RULES
        sections.append(render_rule_section(rules, lang=policy.normalized_lang))
        sections.append(self._build_action_set_summary(policy, action_specs))
        return sections

    def _build_thirdparty_header(self, policy: PromptPolicy) -> str:
        if policy.minimal:
            return MINIMAL_HEADER_EN if policy.normalized_lang == "en" else MINIMAL_HEADER_ZH
        if policy.thinking:
            return (
                THIRDPARTY_THINKING_HEADER_EN
                if policy.normalized_lang == "en"
                else THIRDPARTY_THINKING_HEADER_ZH
            )
        return THIRDPARTY_HEADER_EN if policy.normalized_lang == "en" else THIRDPARTY_HEADER_ZH

    def _build_action_set_summary(self, policy: PromptPolicy, action_specs) -> str:
        action_list = render_action_name_list(action_specs)
        if policy.normalized_lang == "en":
            return (
                "Prompt-visible actions: "
                + (action_list or "(none)")
                + "\nRuntime-enabled actions: "
                + (", ".join(policy.runtime_enabled_actions) or "(none)")
            )
        return (
            "当前提示词可见动作："
            + (action_list or "（无）")
            + "\n当前运行时允许动作："
            + ("，".join(policy.runtime_enabled_actions) or "（无）")
        )


_DEFAULT_BUILDER = PromptBuilder()



def build_system_prompt(
    *,
    lang: str = "cn",
    platform: str | None = None,
    thirdparty: bool = False,
    thinking: bool = True,
    minimal: bool = False,
    include_examples: bool = True,
    include_rules: bool = True,
    action_policy: ActionPolicyInput | None = None,
) -> str:
    policy = build_prompt_policy(
        platform=platform,
        lang=lang,
        thirdparty=thirdparty,
        thinking=thinking,
        minimal=minimal,
        include_examples=include_examples,
        include_rules=include_rules,
        action_policy=action_policy,
    )
    return _DEFAULT_BUILDER.build_text(policy)


__all__ = [
    "BuiltPrompt",
    "PromptBuilder",
    "build_system_prompt",
]
