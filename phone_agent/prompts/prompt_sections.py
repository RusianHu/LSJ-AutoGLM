"""Prompt section formatters built from the shared action registry."""

from __future__ import annotations

from typing import Iterable

from phone_agent.actions.registry import ActionSpec


def _normalize_lang(lang: str) -> str:
    normalized = (lang or "cn").strip().lower()
    if normalized == "zh":
        return "cn"
    if normalized not in {"cn", "en"}:
        return "cn"
    return normalized


def render_action_protocol_section(
    action_specs: Iterable[ActionSpec],
    *,
    lang: str = "cn",
    include_examples: bool = True,
    include_rules: bool = True,
) -> str:
    normalized_lang = _normalize_lang(lang)
    specs = list(action_specs)
    if not specs:
        if normalized_lang == "en":
            return "No actions are currently available. If the task is already complete, use finish(message=\"Task completed\")."
        return "当前没有可用动作。如果任务已完成，请使用 finish(message=\"任务完成\")。"

    return _render_standard_action_guide(
        specs,
        lang=normalized_lang,
        include_examples=include_examples,
        include_rules=include_rules,
    )



def render_rule_section(rules: Iterable[str], *, lang: str = "cn") -> str:
    items = [item.strip() for item in rules if item and item.strip()]
    if not items:
        return ""
    normalized_lang = _normalize_lang(lang)
    title = "必须遵循的规则：" if normalized_lang == "cn" else "Rules you must follow:"
    body = "\n".join(f"{index}. {item}" for index, item in enumerate(items, start=1))
    return f"{title}\n{body}"



def render_action_name_list(action_specs: Iterable[ActionSpec]) -> str:
    return ", ".join(spec.name for spec in action_specs)



def _render_standard_action_guide(
    action_specs: list[ActionSpec],
    *,
    lang: str,
    include_examples: bool,
    include_rules: bool,
) -> str:
    title = "操作指令及其作用如下：" if lang == "cn" else "Available actions:"
    lines = [title]
    if lang == "cn":
        lines.append("任务完成时，必须输出 finish(message=\"完成说明\")；不要使用 do(action=\"Note\", ...) 作为结束动作。")
    else:
        lines.append("When the task is complete, you must output finish(message=\"completion note\") instead of do(action=\"Note\", ...).")
    for spec in action_specs:
        prompt = spec.prompt
        if prompt is None:
            continue
        summary = prompt.summary_zh if lang == "cn" else prompt.summary_en
        lines.append(f'- {prompt.signature}')
        lines.append(f"    {summary}")
        if include_rules and prompt.rules:
            for rule in prompt.rules:
                prefix = "规则" if lang == "cn" else "Rule"
                lines.append(f"    {prefix}: {rule}")
        if include_examples and prompt.examples:
            for example in prompt.examples:
                prefix = "示例" if lang == "cn" else "Example"
                lines.append(f"    {prefix}: {example}")
    return "\n".join(lines)

__all__ = [
    "render_action_name_list",
    "render_action_protocol_section",
    "render_rule_section",
]
