# -*- coding: utf-8 -*-
"""
历史服务 - 管理任务历史记录的持久化存储。

目录结构：
  gui_history/
    index.json            -- 任务历史索引
    logs/<ts>_<id>.log    -- 原始日志文件
    screenshots/<...>.png -- 错误取证截图

修复记录：
- _save_index 改为临时文件 + 原子替换，防止写入中断损坏 index.json
- _load_index 损坏时自动备份原文件，不再静默吞掉异常
- save_record 对 events 字段做安全序列化清洗
"""

import json
import shutil
import time
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QObject, Signal

_HISTORY_DIR = Path("gui_history")
_INDEX_FILE  = _HISTORY_DIR / "index.json"
_LOGS_DIR    = _HISTORY_DIR / "logs"
_SHOTS_DIR   = _HISTORY_DIR / "screenshots"


class HistoryService(QObject):
    """
    历史服务。

    信号：
    - history_changed()    -- 历史列表有变化
    - error_occurred(str)
    """

    history_changed = Signal()
    error_occurred  = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        _HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        _LOGS_DIR.mkdir(parents=True, exist_ok=True)
        _SHOTS_DIR.mkdir(parents=True, exist_ok=True)
        self._records: List[dict] = []
        self._load_index()

    # ---------- 索引加载 ----------

    def _load_index(self):
        """加载索引文件；损坏时备份原文件并重置为空列表"""
        if not _INDEX_FILE.exists():
            self._records = []
            return
        try:
            with open(_INDEX_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                self._records = [
                    self._normalize_record(item)
                    for item in data
                    if isinstance(item, dict)
                ]
            else:
                raise ValueError("索引格式非列表")
        except Exception as e:
            # 备份损坏文件
            backup = _INDEX_FILE.with_suffix(f".json.bak_{int(time.time())}")
            try:
                shutil.copy2(_INDEX_FILE, backup)
            except Exception:
                pass
            self._records = []
            self.error_occurred.emit(
                f"历史索引损坏，已备份至 {backup.name}，错误: {e}"
            )

    @staticmethod
    def _format_time(ts) -> str:
        try:
            ts = float(ts)
        except (TypeError, ValueError):
            return ""
        if ts <= 0:
            return ""
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))

    @staticmethod
    def _format_duration(start_time, end_time) -> str:
        try:
            start_ts = float(start_time)
        except (TypeError, ValueError):
            return ""
        if start_ts <= 0:
            return ""
        try:
            end_ts = float(end_time) if end_time else time.time()
        except (TypeError, ValueError):
            end_ts = time.time()
        secs = max(0, int(end_ts - start_ts))
        if secs < 60:
            return f"{secs}s"
        return f"{secs // 60}m{secs % 60}s"

    def _normalize_record(self, record: dict) -> dict:
        raw = dict(record or {})
        events = raw.get("events", [])
        # 兼容新旧事件结构：确保每个事件都有 message_key/rendered_message 字段（旧记录补空）
        normalized_events = []
        for evt in (events if isinstance(events, list) else []):
            if isinstance(evt, dict):
                evt.setdefault("message_key", "")
                evt.setdefault("message_params", {})
                evt.setdefault("rendered_message", evt.get("message", ""))
                evt.setdefault("lang", "cn")
                normalized_events.append(evt)
        raw["events"] = normalized_events
        raw["start_time_str"] = raw.get("start_time_str") or self._format_time(raw.get("start_time"))
        raw["end_time_str"] = raw.get("end_time_str") or self._format_time(raw.get("end_time"))
        raw["duration_str"] = raw.get("duration_str") or self._format_duration(
            raw.get("start_time"), raw.get("end_time")
        )
        return raw

    # ---------- 原子写入索引 ----------

    def _save_index(self):
        """原子写入索引（临时文件 + replace）"""
        tmp = _INDEX_FILE.with_suffix(".json.tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._records, f, ensure_ascii=False, indent=2,
                          default=str)  # default=str 防止非 JSON 可序列化对象
            tmp.replace(_INDEX_FILE)
        except Exception as e:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
            self.error_occurred.emit(f"历史索引保存失败: {e}")

    # ---------- 保存记录 ----------

    def save_record(self, record):
        """
        保存任务记录（接受 TaskRecord dataclass 或 dict）。
        """
        try:
            if hasattr(record, "__dataclass_fields__"):
                raw = asdict(record)
            elif isinstance(record, dict):
                raw = dict(record)
            else:
                raw = vars(record)

            # 清洗 state（Enum -> str）
            if hasattr(raw.get("state"), "value"):
                raw["state"] = raw["state"].value
            elif hasattr(raw.get("state"), "__str__"):
                raw["state"] = str(raw["state"])

            # 清洗 events 列表（防止非 JSON 可序列化对象）
            safe_events = []
            for evt in raw.get("events", []):
                try:
                    json.dumps(evt)  # 快速验证
                    safe_events.append(evt)
                except Exception:
                    safe_events.append({"type": "unknown", "message": str(evt)})
            raw["events"] = safe_events
            raw = self._normalize_record(raw)

            # 移除旧记录（同 task_id）
            self._records = [
                r for r in self._records
                if r.get("task_id") != raw.get("task_id")
            ]
            self._records.insert(0, raw)  # 最新在前

            self._save_index()
            self.history_changed.emit()
        except Exception as e:
            self.error_occurred.emit(f"任务记录保存失败: {e}")

    # ---------- 查询 ----------

    def get_all(self, state_filter: str = "") -> List[dict]:
        """
        返回所有历史记录（按时间倒序）。
        state_filter: 若非空则按 state 字段过滤，例如 'failed'/'completed'。
        """
        records = list(self._records)
        if state_filter:
            records = [r for r in records if r.get("state") == state_filter]
        return records

    def get_record(self, task_id: str) -> Optional[dict]:
        """按 task_id 查找记录"""
        for r in self._records:
            if r.get("task_id") == task_id:
                return r
        return None

    def get_by_id(self, task_id: str) -> Optional[dict]:
        """兼容旧页面调用，等价于 get_record()。"""
        return self.get_record(task_id)

    def get_events(self, task_id: str) -> List[dict]:
        """返回指定任务的事件列表。"""
        record = self.get_record(task_id)
        if not record:
            return []
        events = record.get("events", [])
        return list(events) if isinstance(events, list) else []

    def get_log_content(self, task_id: str) -> Optional[str]:
        """读取任务原始日志文件"""
        record = self.get_record(task_id)
        if not record:
            return None
        log_path_str = record.get("log_file", "")
        if not log_path_str:
            return None

        log_path = Path(log_path_str)
        # 安全性：限制在 gui_history 目录下
        try:
            log_path.resolve().relative_to(_HISTORY_DIR.resolve())
        except ValueError:
            return None

        if not log_path.exists():
            return None
        try:
            return log_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            self.error_occurred.emit(f"日志读取失败: {e}")
            return None

    def delete_record(self, task_id: str):
        """删除单条历史记录"""
        self._records = [r for r in self._records if r.get("task_id") != task_id]
        self._save_index()
        self.history_changed.emit()

    def clear_all(self):
        """清空所有历史记录"""
        self._records = []
        self._save_index()
        self.history_changed.emit()
