# -*- coding: utf-8 -*-
"""CLI 动作策略解析与校验工具。"""

from __future__ import annotations

import argparse

from phone_agent.actions.registry import (
    ActionPolicyInput,
    canonicalize_action_name,
    get_supported_action_names,
    parse_action_name_collection,
    resolve_action_policy,
)


def parse_cli_action_collection(
    raw_value: str | None,
    option_name: str,
) -> tuple[str, ...] | None:
    """解析 CLI 传入的动作集合表达式。"""
    if raw_value is None:
        return None
    try:
        return parse_action_name_collection(raw_value)
    except ValueError as exc:
        raise ValueError(f"{option_name} 格式无效：{exc}") from exc



def build_action_policy_from_args(
    args: argparse.Namespace,
    platform: str,
):
    """基于 CLI 参数构建动作策略输入与解析结果。"""
    runtime_actions = parse_cli_action_collection(
        getattr(args, "enabled_actions", None),
        "--enabled-actions",
    )
    ai_visible_actions = parse_cli_action_collection(
        getattr(args, "ai_visible_actions", None),
        "--ai-visible-actions",
    )

    policy = ActionPolicyInput(
        ai_visible_actions=ai_visible_actions,
        runtime_enabled_actions=runtime_actions,
        policy_version=args.action_policy_version,
        use_platform_defaults=args.use_platform_default_actions,
    )

    resolved = resolve_action_policy(platform, policy)
    supported_actions = set(get_supported_action_names(platform))

    if resolved.unknown_actions:
        raise ValueError(f"未知动作名：{', '.join(resolved.unknown_actions)}")

    if runtime_actions is None and not args.use_platform_default_actions:
        raise ValueError(
            "运行时启用动作集合未提供，且已禁用平台默认动作回退。请至少指定一个动作集合（允许显式传 []），或开启平台默认动作。"
        )

    if ai_visible_actions is None and not args.use_platform_default_actions:
        raise ValueError(
            "AI 可见动作集合未提供，且已禁用平台默认动作回退。请至少指定一个 AI 可见动作集合（允许显式传 []），或开启平台默认动作。"
        )

    if runtime_actions:
        unsupported_runtime = [
            name
            for name in runtime_actions
            if canonicalize_action_name(name) not in supported_actions
        ]
        if unsupported_runtime:
            raise ValueError(
                f"平台 {platform} 不支持这些运行时动作：{', '.join(unsupported_runtime)}"
            )

    if ai_visible_actions:
        unsupported_ai = [
            name
            for name in ai_visible_actions
            if canonicalize_action_name(name) not in supported_actions
        ]
        if unsupported_ai:
            raise ValueError(
                f"平台 {platform} 不支持这些 AI 可见动作：{', '.join(unsupported_ai)}"
            )

        runtime_enabled_set = set(resolved.runtime_enabled_actions)
        not_enabled_for_runtime = [
            name
            for name in ai_visible_actions
            if canonicalize_action_name(name) in supported_actions
            and canonicalize_action_name(name) not in runtime_enabled_set
        ]
        if not_enabled_for_runtime:
            raise ValueError(
                "以下 AI 可见动作未包含在运行时启用集合中："
                + ", ".join(not_enabled_for_runtime)
            )

    return policy, resolved
