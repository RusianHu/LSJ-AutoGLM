# -*- coding: utf-8 -*-
"""GUI 任务日志事件解析器。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ParsedLogEvent:
    """从单行日志中推断出的高层事件。"""

    event_type: str
    payload: str | None = None
    message_key: str | None = None
    needs_takeover: bool = False
    ignore: bool = False
    raw_error: bool = False
    error_summary: str | None = None
    message_params: dict[str, Any] = field(default_factory=dict)


class TaskLogEventParser:
    """基于关键字规则将任务日志映射为高层事件。"""

    _TRIGGERS = (
        {
            "keywords": ("设备检查", "checking system"),
            "event_type": "device_check",
            "message_key": "event.device_check",
        },
        {
            "keywords": ("device connected", "设备已连接"),
            "event_type": "device_connected",
            "message_key": "event.device_connected",
        },
        {
            "keywords": ("api",),
            "event_type": "api_check",
            "message_key": "event.api_check",
        },
        {
            "keywords": ("agent start",),
            "event_type": "agent_start",
            "message_key": "event.agent_start",
        },
        {"keywords": ("step ",), "ignore": True},
        {"keywords": ("task completed", "任务完成"), "ignore": True},
        {
            "keywords": ("error", "错误", "traceback"),
            "event_type": "error",
            "raw_error": True,
        },
        {
            "keywords": ("takeover", "接管"),
            "event_type": "takeover",
            "needs_takeover": True,
            "message_key": "event.takeover_detected",
        },
    )

    def parse(self, line: str) -> ParsedLogEvent | None:
        """解析单行日志。无法识别时返回 `None`。"""
        stripped = (line or "").strip()
        if not stripped:
            return None

        expert_event = self._parse_expert_event(stripped)
        if expert_event is not None:
            return expert_event

        lower = stripped.lower()
        for trigger in self._TRIGGERS:
            if not any(keyword in lower for keyword in trigger["keywords"]):
                continue
            if trigger.get("ignore"):
                return ParsedLogEvent(event_type="ignored", ignore=True)
            if trigger.get("raw_error"):
                summary = stripped[:200]
                return ParsedLogEvent(
                    event_type="error",
                    payload=summary,
                    raw_error=True,
                    error_summary=summary,
                )
            return ParsedLogEvent(
                event_type=trigger["event_type"],
                payload=stripped,
                message_key=trigger.get("message_key"),
                needs_takeover=bool(trigger.get("needs_takeover")),
            )
        return None

    @staticmethod
    def _parse_expert_event(stripped: str) -> ParsedLogEvent | None:
        if not stripped.startswith("[EXPERT]"):
            return None

        payload = stripped[len("[EXPERT]") :].strip()
        if "失败" in payload:
            return ParsedLogEvent(
                event_type="expert_failure",
                payload=payload,
                error_summary=payload[:200],
            )
        if "发起专家请求" in payload:
            return ParsedLogEvent(event_type="expert_request", payload=payload)
        if "请求成功" in payload:
            return ParsedLogEvent(event_type="expert_success", payload=payload)
        if "触发严格模式专家咨询" in payload:
            return ParsedLogEvent(event_type="expert_strict_trigger", payload=payload)
        if "自动专家救援" in payload:
            return ParsedLogEvent(event_type="expert_auto_rescue", payload=payload)
        if "跳过严格模式专家咨询" in payload:
            return ParsedLogEvent(event_type="expert_strict_skip", payload=payload)
        if "Ask_AI 请求专家协助" in payload:
            return ParsedLogEvent(event_type="expert_manual_request", payload=payload)
        if "已注入主模型上下文" in payload:
            return ParsedLogEvent(event_type="expert_context_injected", payload=payload)
        if payload.startswith("专家建议（") or payload.startswith("  "):
            return ParsedLogEvent(event_type="expert_guidance", payload=payload)
        return None
