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
        # ConfigService 为包含引号的 .env 值加了一层转义引号，兼容该写法。
        if '\\"' in raw:
            raw = raw.replace('\\"', '\"')
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            parsed = [part.strip() for part in raw.split(",")]

    if isinstance(parsed, dict):
        parsed = parsed.get("actions", [])
    if not isinstance(parsed, (list, tuple, set)):
        return list(MIRROR_TOOLBAR_DEFAULT_ACTIONS)

    selected = {str(item).strip() for item in parsed if str(item).strip()}
    return [name for name in MIRROR_TOOLBAR_ACTION_NAMES if name in selected]


def serialize_mirror_toolbar_actions(actions: Iterable[str]) -> str:
    """以稳定顺序序列化动作集合，便于写入 .env。"""

    normalized = normalize_mirror_toolbar_actions(list(actions))
    return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))
