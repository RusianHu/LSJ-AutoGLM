"""Action registry and policy utilities for Phone Agent."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Iterable, Literal

PlatformName = Literal["adb", "hdc", "ios"]
RiskLevel = Literal["low", "medium", "high"]
ActionCategory = Literal[
    "navigation",
    "input",
    "app_control",
    "system",
    "coordination",
    "integration",
]

ACTION_POLICY_VERSION = 1
ACTION_DISABLED_ERROR = "ActionDisabled"
ACTION_UNKNOWN_ERROR = "UnknownAction"
ACTION_PLATFORM_UNSUPPORTED_ERROR = "PlatformNotSupported"
ACTION_INVALID_ARGS_ERROR = "InvalidActionArgs"

CATEGORY_I18N_KEYS: dict[ActionCategory, str] = {
    "navigation": "page.settings.actions.category.navigation",
    "input": "page.settings.actions.category.input",
    "app_control": "page.settings.actions.category.app_control",
    "system": "page.settings.actions.category.system",
    "coordination": "page.settings.actions.category.coordination",
    "integration": "page.settings.actions.category.integration",
}

CATEGORY_DEFAULT_LABELS: dict[ActionCategory, str] = {
    "navigation": "导航类",
    "input": "输入类",
    "app_control": "应用控制类",
    "system": "系统类",
    "coordination": "协同类",
    "integration": "扩展能力类",
}


@dataclass(frozen=True)
class ActionParamSpec:
    name: str
    type: str
    required: bool = True
    description: str = ""
    example: str = ""


@dataclass(frozen=True)
class ActionPromptSpec:
    signature: str
    summary_zh: str
    summary_en: str
    rules: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()


@dataclass(frozen=True)
class ActionSupportSpec:
    platforms: tuple[PlatformName, ...]
    visible_to_ai_by_default: bool = True
    runtime_enabled_by_default: bool = True
    allow_in_thirdparty_prompt: bool = True
    allow_in_minimal_prompt: bool = True


@dataclass(frozen=True)
class ActionSpec:
    name: str
    label: str
    category: ActionCategory
    risk_level: RiskLevel
    description: str
    params: tuple[ActionParamSpec, ...] = ()
    prompt: ActionPromptSpec | None = None
    support: ActionSupportSpec | None = None
    tags: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    sort_order: int = 0
    i18n_key_prefix: str = ""

    @property
    def supported_platforms(self) -> tuple[PlatformName, ...]:
        return self.support.platforms if self.support else ()

    @property
    def resolved_i18n_key_prefix(self) -> str:
        if self.i18n_key_prefix:
            return self.i18n_key_prefix
        normalized = (
            self.name.lower()
            .replace(" ", "_")
            .replace("-", "_")
        )
        return f"action.{normalized}"

    @property
    def label_i18n_key(self) -> str:
        return f"{self.resolved_i18n_key_prefix}.label"

    @property
    def description_i18n_key(self) -> str:
        return f"{self.resolved_i18n_key_prefix}.description"

    @property
    def hint_i18n_key(self) -> str:
        return f"{self.resolved_i18n_key_prefix}.hint"

    def supports_platform(self, platform: PlatformName) -> bool:
        return platform in self.supported_platforms


@dataclass(frozen=True)
class ActionPolicyInput:
    ai_visible_actions: tuple[str, ...] | None = None
    runtime_enabled_actions: tuple[str, ...] | None = None
    policy_version: int = ACTION_POLICY_VERSION
    use_platform_defaults: bool = True


@dataclass(frozen=True)
class ResolvedActionPolicy:
    platform: PlatformName
    supported_actions: tuple[str, ...]
    runtime_enabled_actions: tuple[str, ...]
    ai_visible_actions: tuple[str, ...]
    unknown_actions: tuple[str, ...] = ()
    platform_filtered_actions: tuple[str, ...] = ()
    used_defaults_for_runtime: bool = False
    used_defaults_for_ai_visible: bool = False
    policy_version: int = ACTION_POLICY_VERSION

    def is_runtime_enabled(self, action_name: str) -> bool:
        canonical = canonicalize_action_name(action_name)
        return canonical in self.runtime_enabled_actions

    def is_ai_visible(self, action_name: str) -> bool:
        canonical = canonicalize_action_name(action_name)
        return canonical in self.ai_visible_actions

    def supports_action(self, action_name: str) -> bool:
        canonical = canonicalize_action_name(action_name)
        return canonical in self.supported_actions


@dataclass(frozen=True)
class ActionAvailability:
    action_name: str
    allowed: bool
    error_code: str | None = None
    reason: str | None = None


_ACTIONS: tuple[ActionSpec, ...] = (
    ActionSpec(
        name="Launch",
        label="启动应用",
        category="app_control",
        risk_level="low",
        description="启动指定应用或包名。",
        params=(
            ActionParamSpec(
                name="app",
                type="str",
                required=True,
                description="应用名称、包名或 Bundle ID。",
                example='"微信"',
            ),
        ),
        prompt=ActionPromptSpec(
            signature='do(action="Launch", app="app_name")',
            summary_zh="启动应用或指定包名。",
            summary_en="Launch the target app or package.",
            examples=('do(action="Launch", app="com.android.settings")',),
        ),
        support=ActionSupportSpec(platforms=("adb", "hdc", "ios")),
        tags=("safe", "core"),
        sort_order=100,
        i18n_key_prefix="action.launch",
    ),
    ActionSpec(
        name="Find_App",
        label="查找应用包名",
        category="app_control",
        risk_level="low",
        description="在 Android ADB 设备上查找已安装应用的包名和 Activity。",
        params=(
            ActionParamSpec(
                name="query",
                type="str",
                required=True,
                description="应用名称或包名关键词。",
                example='"settings"',
            ),
        ),
        prompt=ActionPromptSpec(
            signature='do(action="Find_App", query="keyword")',
            summary_zh="查找 Android 设备上的应用包名后再启动。",
            summary_en="Search installed Android packages before launching.",
            examples=('do(action="Find_App", query="微信")',),
        ),
        support=ActionSupportSpec(platforms=("adb",), allow_in_minimal_prompt=False),
        tags=("safe", "android_only"),
        sort_order=110,
        i18n_key_prefix="action.find_app",
    ),
    ActionSpec(
        name="Tap",
        label="点击",
        category="navigation",
        risk_level="low",
        description="点击屏幕相对坐标。",
        params=(
            ActionParamSpec(
                name="element",
                type="list[int]",
                required=True,
                description="二维相对坐标，范围 0-999。",
                example="[500, 500]",
            ),
        ),
        prompt=ActionPromptSpec(
            signature='do(action="Tap", element=[x, y])',
            summary_zh="点击指定坐标。",
            summary_en="Tap the specified coordinate.",
            rules=("坐标必须为整数", "坐标范围为 0-999"),
            examples=('do(action="Tap", element=[500, 500])',),
        ),
        support=ActionSupportSpec(platforms=("adb", "hdc", "ios")),
        tags=("safe", "core"),
        sort_order=200,
        i18n_key_prefix="action.tap",
    ),
    ActionSpec(
        name="Type",
        label="输入文本",
        category="input",
        risk_level="medium",
        description="清空并输入文本。",
        params=(
            ActionParamSpec(
                name="text",
                type="str",
                required=True,
                description="要输入的文本内容。",
                example='"你好"',
            ),
        ),
        prompt=ActionPromptSpec(
            signature='do(action="Type", text="...")',
            summary_zh="在当前输入框输入文本。",
            summary_en="Type text into the current input field.",
            examples=('do(action="Type", text="hello")',),
        ),
        support=ActionSupportSpec(platforms=("adb", "hdc", "ios")),
        tags=("core",),
        aliases=("Type_Name",),
        sort_order=210,
        i18n_key_prefix="action.type",
    ),
    ActionSpec(
        name="Swipe",
        label="滑动",
        category="navigation",
        risk_level="low",
        description="从起点滑动到终点。",
        params=(
            ActionParamSpec("start", "list[int]", True, "起点相对坐标", "[500, 800]"),
            ActionParamSpec("end", "list[int]", True, "终点相对坐标", "[500, 200]"),
        ),
        prompt=ActionPromptSpec(
            signature='do(action="Swipe", start=[x1, y1], end=[x2, y2])',
            summary_zh="执行滑动操作。",
            summary_en="Swipe from the start coordinate to the end coordinate.",
            examples=('do(action="Swipe", start=[500, 800], end=[500, 200])',),
        ),
        support=ActionSupportSpec(platforms=("adb", "hdc", "ios")),
        tags=("safe", "core"),
        sort_order=220,
        i18n_key_prefix="action.swipe",
    ),
    ActionSpec(
        name="Back",
        label="返回",
        category="navigation",
        risk_level="low",
        description="返回上一级界面。",
        prompt=ActionPromptSpec(
            signature='do(action="Back")',
            summary_zh="执行返回。",
            summary_en="Go back.",
            examples=('do(action="Back")',),
        ),
        support=ActionSupportSpec(platforms=("adb", "hdc", "ios")),
        tags=("safe", "core"),
        sort_order=230,
        i18n_key_prefix="action.back",
    ),
    ActionSpec(
        name="Home",
        label="回到主屏幕",
        category="system",
        risk_level="low",
        description="回到设备主屏幕。",
        prompt=ActionPromptSpec(
            signature='do(action="Home")',
            summary_zh="回到主屏幕。",
            summary_en="Go to the home screen.",
            examples=('do(action="Home")',),
        ),
        support=ActionSupportSpec(platforms=("adb", "hdc", "ios")),
        tags=("safe",),
        sort_order=240,
        i18n_key_prefix="action.home",
    ),
    ActionSpec(
        name="Double Tap",
        label="双击",
        category="navigation",
        risk_level="low",
        description="双击屏幕相对坐标。",
        params=(
            ActionParamSpec("element", "list[int]", True, "二维相对坐标", "[500, 500]"),
        ),
        prompt=ActionPromptSpec(
            signature='do(action="Double Tap", element=[x, y])',
            summary_zh="双击指定坐标。",
            summary_en="Double tap the specified coordinate.",
            examples=('do(action="Double Tap", element=[500, 500])',),
        ),
        support=ActionSupportSpec(platforms=("adb", "hdc", "ios")),
        tags=("safe",),
        sort_order=250,
        i18n_key_prefix="action.double_tap",
    ),
    ActionSpec(
        name="Long Press",
        label="长按",
        category="navigation",
        risk_level="medium",
        description="长按屏幕相对坐标。",
        params=(
            ActionParamSpec("element", "list[int]", True, "二维相对坐标", "[500, 500]"),
        ),
        prompt=ActionPromptSpec(
            signature='do(action="Long Press", element=[x, y])',
            summary_zh="长按指定坐标。",
            summary_en="Long press the specified coordinate.",
            examples=('do(action="Long Press", element=[500, 500])',),
        ),
        support=ActionSupportSpec(platforms=("adb", "hdc", "ios")),
        tags=("core",),
        sort_order=260,
        i18n_key_prefix="action.long_press",
    ),
    ActionSpec(
        name="Wait",
        label="等待",
        category="coordination",
        risk_level="low",
        description="等待指定时长后继续。",
        params=(
            ActionParamSpec("duration", "str", True, "等待时长，例如 '1 seconds'。", '"1 seconds"'),
        ),
        prompt=ActionPromptSpec(
            signature='do(action="Wait", duration="1 seconds")',
            summary_zh="等待一段时间。",
            summary_en="Wait for a short period.",
            examples=('do(action="Wait", duration="2 seconds")',),
        ),
        support=ActionSupportSpec(platforms=("adb", "hdc", "ios")),
        tags=("safe",),
        sort_order=300,
        i18n_key_prefix="action.wait",
    ),
    ActionSpec(
        name="Take_over",
        label="请求接管",
        category="coordination",
        risk_level="medium",
        description="请求用户接管当前任务，例如登录或验证码。",
        params=(
            ActionParamSpec("message", "str", False, "接管说明。", '"请手动完成登录"'),
        ),
        prompt=ActionPromptSpec(
            signature='do(action="Take_over", message="...")',
            summary_zh="请求用户手动接管当前步骤。",
            summary_en="Request manual user takeover for the current step.",
            examples=('do(action="Take_over", message="请处理验证码")',),
        ),
        support=ActionSupportSpec(platforms=("adb", "hdc", "ios")),
        tags=("manual_assist",),
        sort_order=310,
        i18n_key_prefix="action.take_over",
    ),
    ActionSpec(
        name="Note",
        label="记录说明",
        category="coordination",
        risk_level="low",
        description="记录说明性文本，不触发物理操作。",
        params=(
            ActionParamSpec("message", "str", False, "说明文本。", '"已到达首页"'),
        ),
        prompt=ActionPromptSpec(
            signature='do(action="Note", message="...")',
            summary_zh="记录当前观察或中间结论。",
            summary_en="Record an observation or intermediate note.",
            examples=('do(action="Note", message="已打开设置页")',),
        ),
        support=ActionSupportSpec(platforms=("adb", "hdc", "ios")),
        tags=("safe", "non_physical"),
        sort_order=320,
        i18n_key_prefix="action.note",
    ),
    ActionSpec(
        name="Ask_AI",
        label="请求专家协助",
        category="coordination",
        risk_level="low",
        description="请求独立专家模型分析当前卡点并返回指导建议。",
        params=(
            ActionParamSpec("message", "str", False, "向专家补充的问题或上下文。", '"当前页面像登录确认，请给出下一步建议"'),
        ),
        prompt=ActionPromptSpec(
            signature='do(action="Ask_AI", message="...")',
            summary_zh="请求专家模型给出策略指导。",
            summary_en="Ask the expert model for guidance.",
            examples=('do(action="Ask_AI", message="请分析为何当前页面停滞")',),
        ),
        support=ActionSupportSpec(platforms=("adb", "hdc", "ios")),
        tags=("safe", "expert_assist"),
        sort_order=325,
        i18n_key_prefix="action.ask_ai",
    ),
    ActionSpec(
        name="Call_API",
        label="调用外部 API",
        category="integration",
        risk_level="high",
        description="调用外部 API 或扩展能力。当前执行器仅提供占位实现。",
        params=(
            ActionParamSpec("instruction", "str", False, "API 调用意图或说明。", '"总结页面内容"'),
        ),
        prompt=ActionPromptSpec(
            signature='do(action="Call_API", instruction="...")',
            summary_zh="调用外部 API 或扩展能力。",
            summary_en="Call an external API or extension capability.",
            examples=('do(action="Call_API", instruction="总结页面内容")',),
        ),
        support=ActionSupportSpec(
            platforms=("adb", "hdc", "ios"),
            visible_to_ai_by_default=False,
            runtime_enabled_by_default=False,
        ),
        tags=("experimental", "api_related"),
        sort_order=400,
        i18n_key_prefix="action.call_api",
    ),
    ActionSpec(
        name="Interact",
        label="请求交互确认",
        category="coordination",
        risk_level="medium",
        description="请求额外的人机交互确认。当前执行器仅提供占位实现。",
        params=(
            ActionParamSpec("message", "str", False, "交互说明。", '"请选择目标联系人"'),
        ),
        prompt=ActionPromptSpec(
            signature='do(action="Interact", message="...")',
            summary_zh="请求用户额外确认或提供信息。",
            summary_en="Request additional user interaction or confirmation.",
            examples=('do(action="Interact", message="请选择目标项")',),
        ),
        support=ActionSupportSpec(platforms=("adb", "hdc", "ios")),
        tags=("manual_assist",),
        sort_order=330,
        i18n_key_prefix="action.interact",
    ),
)

_ACTIONS_BY_NAME: dict[str, ActionSpec] = {spec.name: spec for spec in _ACTIONS}
_ACTION_NAMES: tuple[str, ...] = tuple(spec.name for spec in sorted(_ACTIONS, key=lambda item: item.sort_order))
_ACTION_ALIASES: dict[str, str] = {
    alias: spec.name for spec in _ACTIONS for alias in spec.aliases
}


def get_all_action_specs() -> tuple[ActionSpec, ...]:
    return tuple(sorted(_ACTIONS, key=lambda item: item.sort_order))



def get_all_action_names() -> tuple[str, ...]:
    return _ACTION_NAMES



def get_action_map(include_aliases: bool = True) -> dict[str, ActionSpec]:
    mapping = dict(_ACTIONS_BY_NAME)
    if include_aliases:
        for alias, canonical in _ACTION_ALIASES.items():
            mapping[alias] = _ACTIONS_BY_NAME[canonical]
    return mapping



def canonicalize_action_name(action_name: str | None) -> str | None:
    if not action_name:
        return None
    candidate = str(action_name).strip()
    if not candidate:
        return None
    if candidate in _ACTIONS_BY_NAME:
        return candidate
    return _ACTION_ALIASES.get(candidate)



def get_action_spec(action_name: str | None) -> ActionSpec | None:
    canonical = canonicalize_action_name(action_name)
    if canonical is None:
        return None
    return _ACTIONS_BY_NAME.get(canonical)



def get_supported_action_specs(platform: PlatformName) -> tuple[ActionSpec, ...]:
    return tuple(spec for spec in get_all_action_specs() if spec.supports_platform(platform))



def get_supported_action_names(platform: PlatformName) -> tuple[str, ...]:
    return tuple(spec.name for spec in get_supported_action_specs(platform))



def get_default_runtime_action_names(platform: PlatformName) -> tuple[str, ...]:
    return tuple(
        spec.name
        for spec in get_supported_action_specs(platform)
        if spec.support and spec.support.runtime_enabled_by_default
    )



def get_default_ai_visible_action_names(platform: PlatformName) -> tuple[str, ...]:
    runtime_defaults = set(get_default_runtime_action_names(platform))
    return tuple(
        spec.name
        for spec in get_supported_action_specs(platform)
        if spec.support
        and spec.support.visible_to_ai_by_default
        and spec.name in runtime_defaults
    )



def parse_action_name_collection(value: object) -> tuple[str, ...] | None:
    if value is None:
        return None
    if isinstance(value, tuple):
        raw_items = list(value)
    elif isinstance(value, list):
        raw_items = value
    elif isinstance(value, set):
        raw_items = list(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = [part.strip() for part in text.split(",") if part.strip()]
        if isinstance(parsed, str):
            raw_items = [parsed]
        elif isinstance(parsed, (list, tuple, set)):
            raw_items = list(parsed)
        else:
            raise ValueError("Action collection must be a JSON array or a comma separated string")
    else:
        raise ValueError("Unsupported action collection type")

    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        canonical = canonicalize_action_name(str(item))
        if canonical is None:
            item_text = str(item).strip()
            if item_text and item_text not in seen:
                normalized.append(item_text)
                seen.add(item_text)
            continue
        if canonical not in seen:
            normalized.append(canonical)
            seen.add(canonical)
    return tuple(normalized)



def _normalize_requested_actions(actions: tuple[str, ...] | None) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if not actions:
        return (), ()
    valid: list[str] = []
    unknown: list[str] = []
    seen_valid: set[str] = set()
    seen_unknown: set[str] = set()
    for name in actions:
        canonical = canonicalize_action_name(name)
        if canonical is None:
            unknown_name = str(name).strip()
            if unknown_name and unknown_name not in seen_unknown:
                unknown.append(unknown_name)
                seen_unknown.add(unknown_name)
            continue
        if canonical not in seen_valid:
            valid.append(canonical)
            seen_valid.add(canonical)
    return tuple(valid), tuple(unknown)



def resolve_action_policy(
    platform: PlatformName,
    policy: ActionPolicyInput | None = None,
) -> ResolvedActionPolicy:
    policy = policy or ActionPolicyInput()
    supported = get_supported_action_names(platform)
    supported_set = set(supported)

    requested_runtime, runtime_unknown = _normalize_requested_actions(policy.runtime_enabled_actions)
    runtime_filtered = tuple(name for name in requested_runtime if name in supported_set)
    runtime_platform_filtered = tuple(name for name in requested_runtime if name not in supported_set)

    if runtime_filtered:
        runtime_actions = runtime_filtered
        used_runtime_default = False
    elif policy.use_platform_defaults:
        runtime_actions = get_default_runtime_action_names(platform)
        used_runtime_default = True
    else:
        runtime_actions = ()
        used_runtime_default = False

    requested_ai_visible, ai_unknown = _normalize_requested_actions(policy.ai_visible_actions)
    ai_filtered = tuple(
        name for name in requested_ai_visible if name in supported_set and name in set(runtime_actions)
    )
    ai_platform_filtered = tuple(
        name for name in requested_ai_visible if name not in supported_set or name not in set(runtime_actions)
    )

    if ai_filtered:
        ai_visible_actions = ai_filtered
        used_ai_default = False
    elif policy.ai_visible_actions is None or policy.use_platform_defaults:
        ai_visible_actions = tuple(
            name for name in get_default_ai_visible_action_names(platform) if name in set(runtime_actions)
        )
        if not ai_visible_actions:
            ai_visible_actions = tuple(runtime_actions)
        used_ai_default = True
    else:
        ai_visible_actions = ()
        used_ai_default = False

    unknown_actions: list[str] = []
    for name in (*runtime_unknown, *ai_unknown):
        if name not in unknown_actions:
            unknown_actions.append(name)

    platform_filtered_actions: list[str] = []
    for name in (*runtime_platform_filtered, *ai_platform_filtered):
        if name not in platform_filtered_actions:
            platform_filtered_actions.append(name)

    return ResolvedActionPolicy(
        platform=platform,
        supported_actions=tuple(supported),
        runtime_enabled_actions=tuple(runtime_actions),
        ai_visible_actions=tuple(ai_visible_actions),
        unknown_actions=tuple(unknown_actions),
        platform_filtered_actions=tuple(platform_filtered_actions),
        used_defaults_for_runtime=used_runtime_default,
        used_defaults_for_ai_visible=used_ai_default,
        policy_version=policy.policy_version,
    )



def export_prompt_action_specs(
    platform: PlatformName,
    *,
    lang: str = "cn",
    include_actions: Iterable[str] | None = None,
    thirdparty: bool = False,
    minimal: bool = False,
) -> tuple[ActionSpec, ...]:
    allowed = None
    if include_actions is not None:
        allowed = {name for name in include_actions if name}
    result: list[ActionSpec] = []
    for spec in get_supported_action_specs(platform):
        if allowed is not None and spec.name not in allowed:
            continue
        support = spec.support
        if support is None:
            continue
        if thirdparty and not support.allow_in_thirdparty_prompt:
            continue
        if minimal and not support.allow_in_minimal_prompt:
            continue
        result.append(spec)
    return tuple(result)



def export_gui_action_groups(platform: PlatformName) -> tuple[dict, ...]:
    grouped: dict[ActionCategory, list[dict]] = {category: [] for category in CATEGORY_I18N_KEYS}
    for spec in get_supported_action_specs(platform):
        grouped[spec.category].append(
            {
                "name": spec.name,
                "label": spec.label,
                "description": spec.description,
                "category": spec.category,
                "category_i18n_key": CATEGORY_I18N_KEYS[spec.category],
                "category_label": CATEGORY_DEFAULT_LABELS[spec.category],
                "risk_level": spec.risk_level,
                "risk_i18n_key": f"action.risk.{spec.risk_level}",
                "platforms": spec.supported_platforms,
                "visible_to_ai_by_default": bool(spec.support and spec.support.visible_to_ai_by_default),
                "runtime_enabled_by_default": bool(spec.support and spec.support.runtime_enabled_by_default),
                "label_i18n_key": spec.label_i18n_key,
                "description_i18n_key": spec.description_i18n_key,
                "hint_i18n_key": spec.hint_i18n_key,
                "aliases": spec.aliases,
                "sort_order": spec.sort_order,
            }
        )

    ordered_groups: list[dict] = []
    for category in CATEGORY_I18N_KEYS:
        items = sorted(grouped[category], key=lambda item: item["sort_order"])
        if not items:
            continue
        ordered_groups.append(
            {
                "category": category,
                "category_i18n_key": CATEGORY_I18N_KEYS[category],
                "category_label": CATEGORY_DEFAULT_LABELS[category],
                "items": tuple(items),
            }
        )
    return tuple(ordered_groups)



def check_action_availability(
    action_name: str | None,
    policy: ResolvedActionPolicy,
) -> ActionAvailability:
    if not action_name:
        return ActionAvailability(
            action_name="",
            allowed=False,
            error_code=ACTION_UNKNOWN_ERROR,
            reason="Missing action name",
        )

    canonical = canonicalize_action_name(action_name)
    if canonical is None:
        return ActionAvailability(
            action_name=str(action_name),
            allowed=False,
            error_code=ACTION_UNKNOWN_ERROR,
            reason=f"Unknown action: {action_name}",
        )

    if canonical not in policy.supported_actions:
        return ActionAvailability(
            action_name=canonical,
            allowed=False,
            error_code=ACTION_PLATFORM_UNSUPPORTED_ERROR,
            reason=f"Action not supported on platform {policy.platform}: {canonical}",
        )

    if canonical not in policy.runtime_enabled_actions:
        return ActionAvailability(
            action_name=canonical,
            allowed=False,
            error_code=ACTION_DISABLED_ERROR,
            reason=f"Action disabled by runtime policy: {canonical}",
        )

    return ActionAvailability(action_name=canonical, allowed=True)


__all__ = [
    "ACTION_DISABLED_ERROR",
    "ACTION_INVALID_ARGS_ERROR",
    "ACTION_PLATFORM_UNSUPPORTED_ERROR",
    "ACTION_POLICY_VERSION",
    "ACTION_UNKNOWN_ERROR",
    "ActionAvailability",
    "ActionCategory",
    "ActionParamSpec",
    "ActionPolicyInput",
    "ActionPromptSpec",
    "ActionSpec",
    "ActionSupportSpec",
    "CATEGORY_DEFAULT_LABELS",
    "CATEGORY_I18N_KEYS",
    "PlatformName",
    "ResolvedActionPolicy",
    "RiskLevel",
    "canonicalize_action_name",
    "check_action_availability",
    "export_gui_action_groups",
    "export_prompt_action_specs",
    "get_action_map",
    "get_action_spec",
    "get_all_action_names",
    "get_all_action_specs",
    "get_default_ai_visible_action_names",
    "get_default_runtime_action_names",
    "get_supported_action_names",
    "get_supported_action_specs",
    "parse_action_name_collection",
    "resolve_action_policy",
]
