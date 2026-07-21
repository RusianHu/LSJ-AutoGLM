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

    coordinate_action_names = {"Tap", "Swipe", "Double Tap", "Long Press"}
    if any(spec.name in coordinate_action_names for spec in action_specs):
        if lang == "cn":
            lines.extend(
                [
                    "坐标协议（必须严格遵循）：",
                    "- element、start、end 中的 [x, y] 都是 0-999 的归一化相对坐标，不是截图像素坐标。",
                    "- 左上角为 [0, 0]，右下角接近 [999, 999]；x、y 必须分别按截图宽度和高度归一化。",
                    "- 从截图像素换算模型坐标：x = round(pixel_x / screenshot_width * 1000)，y = round(pixel_y / screenshot_height * 1000)。",
                    "- 从模型坐标换算实际点击像素：pixel_x = int(x / 1000 * screenshot_width)，pixel_y = int(y / 1000 * screenshot_height)。",
                    "- 如果无法可靠读取原始像素位置，请直接按目标中心占整张截图的宽高比例估算 0-999 坐标；不要把模型内部缩放预览图的像素当作原图像素。",
                    "- 示例：截图为 1080×2400，目标中心像素为 (108, 576) 时，应输出 [100, 240]；禁止直接输出像素坐标 [108, 576]。",
                ]
            )
        else:
            lines.extend(
                [
                    "Coordinate protocol (must be followed exactly):",
                    "- Every [x, y] in element, start, and end uses normalized relative coordinates from 0 to 999, never screenshot pixel coordinates.",
                    "- The top-left is [0, 0] and the bottom-right is near [999, 999]. Normalize x by screenshot width and y by screenshot height independently.",
                    "- Convert screenshot pixels to model coordinates with x = round(pixel_x / screenshot_width * 1000) and y = round(pixel_y / screenshot_height * 1000).",
                    "- Convert model coordinates to tap pixels with pixel_x = int(x / 1000 * screenshot_width) and pixel_y = int(y / 1000 * screenshot_height).",
                    "- If original pixel positions are uncertain, estimate normalized 0-999 coordinates directly from the target center's width/height proportions in the full screenshot. Never treat pixels from an internally resized preview as original-image pixels.",
                    "- Example: for a 1080×2400 screenshot and a target center at pixel (108, 576), output [100, 240]. Never output the raw pixel coordinate [108, 576].",
                ]
            )

    for spec in action_specs:
        prompt = spec.prompt
        if prompt is None:
            continue
        summary = prompt.summary_zh if lang == "cn" else prompt.summary_en
        lines.append(f'- {prompt.signature}')
        lines.append(f"    {summary}")
        if spec.description:
            prefix = "说明" if lang == "cn" else "Description"
            lines.append(f"    {prefix}: {spec.description}")
        if spec.params:
            prefix = "参数" if lang == "cn" else "Parameters"
            lines.append(f"    {prefix}:")
            for param in spec.params:
                required = (
                    "必填" if param.required else "可选"
                ) if lang == "cn" else (
                    "required" if param.required else "optional"
                )
                detail = f"        - {param.name} ({param.type}, {required})"
                if param.description:
                    detail += f": {param.description.rstrip('。.!！')}"
                if param.example:
                    example_label = "示例" if lang == "cn" else "example"
                    separator = "；" if lang == "cn" else "; "
                    detail += f"{separator}{example_label}: {param.example}"
                lines.append(detail)
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
