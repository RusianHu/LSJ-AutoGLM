# -*- coding: utf-8 -*-
"""GUI 任务运行时 inbox 写入器。"""

from __future__ import annotations

import json
import time
from pathlib import Path


class TaskRuntimeInboxWriter:
    """负责向运行时 JSONL inbox 追加 GUI 用户指令。"""

    def __init__(self, inbox_path: Path | None = None):
        self._inbox_path = inbox_path
        self._instruction_seq = 0

    @property
    def inbox_path(self) -> Path | None:
        return self._inbox_path

    def bind(self, inbox_path: Path | None) -> None:
        """绑定当前任务的 inbox 路径并重置序号。"""
        self._inbox_path = inbox_path
        self._instruction_seq = 0

    def reset(self) -> None:
        """清空当前绑定与序号。"""
        self._inbox_path = None
        self._instruction_seq = 0

    def is_available(self) -> bool:
        """当前 inbox 是否可写。"""
        return self._inbox_path is not None and self._inbox_path.exists()

    def write(self, text: str, source: str = "gui_dashboard") -> dict:
        """写入一条新指令，返回写入的 entry。"""
        if not self.is_available():
            raise FileNotFoundError("runtime inbox is not available")

        normalized = (text or "").strip()
        if not normalized:
            raise ValueError("instruction text is empty")

        self._instruction_seq += 1
        entry = {
            "id": f"ui-{self._instruction_seq:04d}",
            "text": normalized,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "source": source,
        }
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        assert self._inbox_path is not None
        with self._inbox_path.open("a", encoding="utf-8") as handle:
            handle.write(line)
        return entry
