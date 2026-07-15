# -*- coding: utf-8 -*-
"""设备镜像侧边工具栏的动作定义与配置解析。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class MirrorToolbarAction:
    """一个侧边工具栏按钮的静态描述。"""

    name: str
    label_key: str
    tooltip_key: str


MIRROR_TOOLBAR_ACTIONS: tuple[MirrorToolbarAction, ...] = (
    MirrorToolbarAction("fullscreen", "mirror.toolbar.action.fullscreen", "mirror.toolbar.action.fullscreen"),
    MirrorToolbarAction("notifications", "mirror.toolbar.action.notifications", "mirror.toolbar.action.notifications"),
    MirrorToolbarAction("touch", "mirror.toolbar.action.touch", "mirror.toolbar.action.touch"),
    MirrorToolbarAction("screen_on", "mirror.toolbar.action.screen_on", "mirror.toolbar.action.screen_on"),
    MirrorToolbarAction("screen_off", "mirror.toolbar.action.screen_off", "mirror.toolbar.action.screen_off"),
    MirrorToolbarAction("power", "mirror.toolbar.action.power", "mirror.toolbar.action.power"),
    MirrorToolbarAction("volume_up", "mirror.toolbar.action.volume_up", "mirror.toolbar.action.volume_up"),
    MirrorToolbarAction("volume_down", "mirror.toolbar.action.volume_down", "mirror.toolbar.action.volume_down"),
    MirrorToolbarAction("app_switch", "mirror.toolbar.action.app_switch", "mirror.toolbar.action.app_switch"),
    MirrorToolbarAction("menu", "mirror.toolbar.action.menu", "mirror.toolbar.action.menu"),
    MirrorToolbarAction("home", "mirror.toolbar.action.home", "mirror.toolbar.action.home"),
    MirrorToolbarAction("back", "mirror.toolbar.action.back", "mirror.toolbar.action.back"),
    MirrorToolbarAction("screenshot", "mirror.toolbar.action.screenshot", "mirror.toolbar.action.screenshot"),
    MirrorToolbarAction("clipboard", "mirror.toolbar.action.clipboard", "mirror.toolbar.action.clipboard"),
)

MIRROR_TOOLBAR_ACTION_NAMES: tuple[str, ...] = tuple(item.name for item in MIRROR_TOOLBAR_ACTIONS)
MIRROR_TOOLBAR_DEFAULT_ACTIONS: tuple[str, ...] = MIRROR_TOOLBAR_ACTION_NAMES


def normalize_mirror_toolbar_actions(value: object) -> list[str]:
    """解析 JSON/逗号分隔的动作集合，过滤未知项并保持固定顺序。"""

    parsed: object = value
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return list(MIRROR_TOOLBAR_DEFAULT_ACTIONS)
        # ConfigService 反复保存含引号的 .env 值时会累积多层反斜杠转义
        # （\" -> \\\" -> ...）。这里循环剥离，直到能被 json.loads 解析，
        # 兼容任意层数的历史脏数据。
        parsed = _loads_escaped_json(raw)
        if parsed is None:
            # 无法解析为 JSON 时退回逗号分隔，并顺带清掉残留的反斜杠与引号。
            parsed = [
                part.strip().strip('\\"').strip()
                for part in raw.replace("\\", "").replace('"', "").split(",")
            ]

    if isinstance(parsed, dict):
        parsed = parsed.get("actions", [])
    if not isinstance(parsed, (list, tuple, set)):
        return list(MIRROR_TOOLBAR_DEFAULT_ACTIONS)

    selected = {str(item).strip() for item in parsed if str(item).strip()}
    return [name for name in MIRROR_TOOLBAR_ACTION_NAMES if name in selected]


def _loads_escaped_json(raw: str) -> object | None:
    """尝试解析可能被多层反斜杠转义包裹的 JSON 字符串。"""

    candidate = raw
    for _ in range(8):
        try:
            return json.loads(candidate)
        except (TypeError, ValueError, json.JSONDecodeError):
            if "\\" not in candidate:
                return None
            # 每轮去掉一层反斜杠转义后重试。
            candidate = candidate.replace("\\", "")
    return None


def serialize_mirror_toolbar_actions(actions: Iterable[str]) -> str:
    """以稳定顺序序列化动作集合，便于写入 .env。"""

    normalized = normalize_mirror_toolbar_actions(list(actions))
    return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))
