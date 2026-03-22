# -*- coding: utf-8 -*-
"""
测试 HistoryService 新旧记录 i18n 字段兼容性：
- 旧记录（缺少 message_key/rendered_message）加载时能被正确 normalize
- 新记录保留 message_key / message_params / rendered_message / lang
- _normalize_record 对各种边界情况不崩溃
"""

import sys
import os
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ---------------------------------------------------------------------------
# 最小化 _normalize_record 逻辑（不依赖 Qt / HistoryService 实例）
# ---------------------------------------------------------------------------

def _normalize_record(record: dict) -> dict:
    """
    从 HistoryService 提取出来的纯函数版本，仅用于测试 normalize 逻辑。
    与 gui/services/history_service.py 中的逻辑保持一致。
    """
    raw = dict(record or {})
    events = raw.get("events", [])
    normalized_events = []
    for evt in (events if isinstance(events, list) else []):
        if isinstance(evt, dict):
            evt = dict(evt)  # 不修改原始对象
            evt.setdefault("message_key", "")
            evt.setdefault("message_params", {})
            evt.setdefault("rendered_message", evt.get("message", ""))
            evt.setdefault("lang", "cn")
            normalized_events.append(evt)
    raw["events"] = normalized_events
    return raw


class TestNormalizeRecord:
    """测试 _normalize_record 对新旧记录的兼容性。"""

    def test_old_record_no_events(self):
        """旧记录无 events 字段 → normalize 后 events 为 []。"""
        record = {"task_id": "t1", "state": "completed"}
        result = _normalize_record(record)
        assert result["events"] == []

    def test_old_event_missing_i18n_fields(self):
        """旧事件缺少 message_key 等字段 → 补默认值。"""
        old_event = {
            "type": "task_complete",
            "time_str": "10:00:00",
            "message": "任务完成",
        }
        record = {"task_id": "t1", "events": [old_event]}
        result = _normalize_record(record)
        evt = result["events"][0]
        assert evt["message_key"] == ""
        assert evt["message_params"] == {}
        assert evt["rendered_message"] == "任务完成"  # 回退到 message
        assert evt["lang"] == "cn"

    def test_new_event_preserves_i18n_fields(self):
        """新事件已有 i18n 字段 → 不被覆盖。"""
        new_event = {
            "type": "task_complete",
            "time_str": "10:00:00",
            "message": "任务完成，耗时 5s",
            "message_key": "event.task_complete",
            "message_params": {"duration": "5s"},
            "rendered_message": "任务完成，耗时 5s",
            "lang": "cn",
        }
        record = {"task_id": "t2", "events": [new_event]}
        result = _normalize_record(record)
        evt = result["events"][0]
        assert evt["message_key"] == "event.task_complete"
        assert evt["message_params"] == {"duration": "5s"}
        assert evt["rendered_message"] == "任务完成，耗时 5s"
        assert evt["lang"] == "cn"

    def test_mixed_events_old_and_new(self):
        """同一 record 中混合新旧事件 → 各自正确处理。"""
        old_evt = {"type": "user_stop", "message": "用户停止"}
        new_evt = {
            "type": "task_start",
            "message": "任务启动：测试",
            "message_key": "event.task_start",
            "message_params": {"task_text": "测试"},
            "rendered_message": "任务启动：测试",
            "lang": "cn",
        }
        record = {"task_id": "t3", "events": [old_evt, new_evt]}
        result = _normalize_record(record)
        assert len(result["events"]) == 2
        # 旧事件 → 补默认
        assert result["events"][0]["message_key"] == ""
        assert result["events"][0]["rendered_message"] == "用户停止"
        # 新事件 → 保留
        assert result["events"][1]["message_key"] == "event.task_start"

    def test_none_record(self):
        """None 输入 → 不崩溃，返回空 dict。"""
        result = _normalize_record(None)
        assert isinstance(result, dict)
        assert result["events"] == []

    def test_empty_record(self):
        """空 dict → events 为 []。"""
        result = _normalize_record({})
        assert result["events"] == []

    def test_events_not_list(self):
        """events 字段为非 list → 当作空列表处理。"""
        record = {"task_id": "t4", "events": "corrupted"}
        result = _normalize_record(record)
        assert result["events"] == []

    def test_event_not_dict(self):
        """events 列表中有非 dict 项 → 跳过，不崩溃。"""
        record = {"task_id": "t5", "events": [None, 123, {"type": "ok", "message": "ok"}]}
        result = _normalize_record(record)
        # 只有 dict 项被保留
        assert len(result["events"]) == 1
        assert result["events"][0]["message"] == "ok"

    def test_rendered_message_falls_back_to_message(self):
        """旧事件无 rendered_message → 回退到 message 字段。"""
        evt = {"type": "error", "message": "出错了"}
        result = _normalize_record({"events": [evt]})
        assert result["events"][0]["rendered_message"] == "出错了"

    def test_rendered_message_when_message_also_missing(self):
        """旧事件 message 和 rendered_message 都缺 → 回退为空字符串。"""
        evt = {"type": "error"}
        result = _normalize_record({"events": [evt]})
        assert result["events"][0]["rendered_message"] == ""

    def test_en_lang_preserved(self):
        """lang=en 的新事件 → lang 不被覆盖为 cn。"""
        evt = {
            "type": "task_complete",
            "message": "Task complete, took 3s",
            "message_key": "event.task_complete",
            "message_params": {"duration": "3s"},
            "rendered_message": "Task complete, took 3s",
            "lang": "en",
        }
        result = _normalize_record({"events": [evt]})
        assert result["events"][0]["lang"] == "en"
